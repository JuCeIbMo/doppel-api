"""El router corre en cada turno, con sesgo de continuidad y sin handoffs.

Esto reemplaza al swarm con routing pegajoso: antes `active_agent` vivía en el
checkpoint y `route_from_start` saltaba directo al especialista, así que el router
LLM clasificaba una sola vez por thread y la derivación posterior quedaba en manos
de tools `handoff_to_*` que los especialistas se llamaban entre sí. Nada cortaba un
ping-pong entre dos especialistas: los caps de `ToolCallLimitMiddleware` acotan el
loop *dentro* de uno, y el único freno entre ellos era `GRAPH_RECURSION_LIMIT`, que
deja al cliente sin respuesta.

Ahora el grafo es `START -> classify_intent -> route_dispatch -> <especialista> -> END`
y `active_agent` sólo alimenta el sesgo del router y el tracing.

Los dos tests que más importan son los últimos: el sesgo es lo que distingue este
diseño del intento que se revirtió (un aside en medio del cierre no puede tirar al
cliente de vuelta al catálogo), y el fallback es lo que impide que un proveedor
caído deje **cualquier** mensaje sin respuesta (`bridge.respond` contesta un turno
fallido con silencio).

app.config instantiates Settings() at import time, requiring these env vars.
Set safe test defaults before import.
"""

import os

os.environ.setdefault("META_APP_ID", "test-app-id")
os.environ.setdefault("META_APP_SECRET", "test-app-secret")
os.environ.setdefault("META_VERIFY_TOKEN", "test-verify-token")
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "x.eyJyb2xlIjogInNlcnZpY2Vfcm9sZSJ9.y")
os.environ.setdefault("ENCRYPTION_KEY", "oZRrOD525wcQ0CJveupENSX1tDwKfP6e1XrDGn9P1Kw=")
os.environ.setdefault("CHAT_DB_URL", "postgresql://ai:ai@localhost:5532/chat")

import asyncio

import pytest
from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver

import app.ai_core.agents.public_agent as public_agent_module
import app.ai_core.agents.router as router_module
from app.ai_core.agents.public_agent import build_public_agent, run_public_agent_turn
from app.ai_core.agents.router import ROUTER_MAX_ATTEMPTS, classify_intent
from app.ai_core.config.tenant import AdminAgentConfig, PublicAgentConfig, TenantConfig


def _tenant(**public_overrides) -> TenantConfig:
    return TenantConfig(
        tenant_id="t1",
        business_name="Kiosco",
        public_agent=PublicAgentConfig(**public_overrides),
        admin_agent=AdminAgentConfig(),
    )


class _FakeClassifier:
    """Reemplaza al nodo router: devuelve intents de a uno, sin red."""

    def __init__(self, selected: str | list[str]):
        self.selections = [selected] if isinstance(selected, str) else list(selected)
        self.calls = 0

    async def __call__(self, state):
        index = min(self.calls, len(self.selections) - 1)
        self.calls += 1
        return {"intent": self.selections[index], "confidence": 1.0}


class _ResponderModel(BaseChatModel):
    """Contesta con su propia etiqueta, así el test sabe quién atendió el turno."""

    label: str
    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "responder"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        raise NotImplementedError("async only")

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        self.calls += 1
        return ChatResult(
            generations=[
                ChatGeneration(message=AIMessage(content=f"{self.label} response"))
            ]
        )

    def bind_tools(self, tools, **kwargs):
        return self


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    """Sin Postgres y sin Supabase: checkpoint en memoria y tracing mudo."""

    async def _in_memory():
        return InMemorySaver()

    async def _no_trace(**kwargs):
        return None

    monkeypatch.setattr(public_agent_module, "open_checkpointer", _in_memory)
    monkeypatch.setattr(public_agent_module, "trace_turn", _no_trace)


def _patch_specialists(monkeypatch, models: dict):
    builders = {}
    for name in public_agent_module._SPECIALIST_BUILDERS:

        def build(_tenant, name=name):
            return create_agent(model=models[name], tools=[], name=name)

        builders[name] = build
    monkeypatch.setattr(public_agent_module, "_SPECIALIST_BUILDERS", builders)


def _responders() -> dict:
    return {
        name: _ResponderModel(label=name)
        for name in public_agent_module._SPECIALIST_BUILDERS
    }


def _turn(agent, tenant, thread_id, text):
    return asyncio.run(run_public_agent_turn(agent, tenant, thread_id, text))


# --------------------------------------------------------------------------
# El router corre en cada turno
# --------------------------------------------------------------------------


def test_router_runs_on_every_turn_and_can_switch_specialist(monkeypatch):
    tenant = _tenant()
    router = _FakeClassifier(["catalog", "close"])
    models = _responders()
    monkeypatch.setattr(public_agent_module, "classify_intent", lambda _t: router)
    _patch_specialists(monkeypatch, models)

    agent = asyncio.run(build_public_agent(tenant))
    thread_id = "t1:public:+per-turn"
    first = _turn(agent, tenant, thread_id, "Mostrame remeras")
    second = _turn(agent, tenant, thread_id, "Dale, la quiero comprar")
    state = asyncio.run(agent.aget_state({"configurable": {"thread_id": thread_id}}))

    assert router.calls == 2
    assert first["active_agent"] == "catalog"
    assert second["active_agent"] == "closer"
    assert state.values["active_agent"] == "closer"
    assert models["catalog"].calls == 1
    assert models["closer"].calls == 1


def test_disabled_router_target_falls_back_to_first_enabled_specialist(monkeypatch):
    tenant = _tenant(allowed_subagents=["catalog", "closer"])
    monkeypatch.setattr(
        public_agent_module, "classify_intent", lambda _t: _FakeClassifier("objection")
    )
    _patch_specialists(monkeypatch, _responders())

    agent = asyncio.run(build_public_agent(tenant))
    result = _turn(agent, tenant, "t1:public:+fallback", "Tengo una duda")

    assert result["active_agent"] == "catalog"
    assert result["messages"][-1].content == "catalog response"


def test_full_history_is_checkpointed(monkeypatch):
    """Sacar el routing pegajoso no puede costar la persistencia del historial."""
    tenant = _tenant()
    monkeypatch.setattr(
        public_agent_module, "classify_intent", lambda _t: _FakeClassifier("greeting")
    )
    _patch_specialists(monkeypatch, _responders())

    agent = asyncio.run(build_public_agent(tenant))
    thread_id = "t1:public:+history"
    _turn(agent, tenant, thread_id, "primero")
    _turn(agent, tenant, thread_id, "segundo")
    state = asyncio.run(agent.aget_state({"configurable": {"thread_id": thread_id}}))

    assert len(state.values["messages"]) == 4


# --------------------------------------------------------------------------
# El nodo router: sesgo de continuidad y fallback
# --------------------------------------------------------------------------


class _RecordingClassifierModel:
    """Devuelve un intent fijo y guarda los prompts que recibió."""

    def __init__(self, intent="catalog"):
        self.intent = intent
        self.seen: list[list] = []

    def with_structured_output(self, *args, **kwargs):
        return self

    async def ainvoke(self, messages, **kwargs):
        self.seen.append(list(messages))
        return router_module.IntentClassification(
            intent=self.intent, confidence=1.0, reason="test"
        )


class _FailingClassifierModel:
    def __init__(self):
        self.attempts = 0

    def with_structured_output(self, *args, **kwargs):
        return self

    async def ainvoke(self, messages, **kwargs):
        self.attempts += 1
        raise RuntimeError("provider down")


def _system_texts(prompts) -> str:
    return "\n".join(m.content for m in prompts if isinstance(m, SystemMessage))


def test_router_prompt_carries_the_previous_specialist(monkeypatch):
    """El sesgo: sin él, un aside en medio del cierre reclasifica a catalog."""
    model = _RecordingClassifierModel()
    monkeypatch.setattr(router_module, "build_chat_model", lambda *a, **k: model)
    node = classify_intent(_tenant())

    asyncio.run(node({"messages": [HumanMessage(content="hola")]}))
    asyncio.run(
        node({"messages": [HumanMessage(content="¿y en rojo?")], "active_agent": "closer"})
    )

    assert "currently handling" not in _system_texts(model.seen[0])
    assert "closer" in _system_texts(model.seen[1])


def test_classifier_failure_keeps_the_previous_specialist(monkeypatch):
    """Un proveedor caído no puede dejar el turno sin respuesta.

    `bridge.respond` contesta un turno que revienta con silencio: sin este
    fallback, el router pasaría de fallar sólo en el primer mensaje del thread a
    poder fallar en cualquiera.
    """
    model = _FailingClassifierModel()
    monkeypatch.setattr(router_module, "build_chat_model", lambda *a, **k: model)
    node = classify_intent(_tenant())

    result = asyncio.run(
        node({"messages": [HumanMessage(content="hola")], "active_agent": "closer"})
    )

    assert model.attempts == ROUTER_MAX_ATTEMPTS
    assert result == {"intent": None, "confidence": None}


def test_failed_classification_dispatches_to_the_previous_specialist(monkeypatch):
    """`intent=None` recorre el grafo entero y sale por el especialista anterior."""
    tenant = _tenant()

    async def _always_fails(state):
        return {"intent": None, "confidence": None}

    models = _responders()
    monkeypatch.setattr(public_agent_module, "classify_intent", lambda _t: _always_fails)
    _patch_specialists(monkeypatch, models)

    agent = asyncio.run(build_public_agent(tenant))
    thread_id = "t1:public:+classifier-down"
    result = _turn(agent, tenant, thread_id, "hola")

    # Sin active_agent previo cae al primer especialista habilitado.
    assert result["active_agent"] == "greeter"
    assert result["messages"][-1].content == "greeter response"

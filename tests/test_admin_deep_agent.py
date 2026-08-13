"""El agente admin sobre el harness de deepagents: inventario de tools y aislamiento.

Dos invariantes, y la primera existe para proteger a la segunda:

1. **Inventario exacto.** El dueño ve `ADMIN_TOOLS ∪ HARNESS_TOOLS`, ni una más ni una
   menos. `create_deep_agent` agrega tools por su cuenta (subagente general-purpose, `glob`,
   `grep`, `delete`, `execute`) y las apagamos por configuración, no por suerte: si un
   upgrade de deepagents cambia esos defaults, este test rompe en vez de ampliarle la
   superficie al dueño en silencio.

2. **Aislamiento entre tenants.** Las memorias de un negocio no pueden filtrarse a otro
   *aunque el modelo esté comprometido*. Los tests de abajo no le piden nada al modelo: le
   ponen en la boca exactamente la llamada que haría un atacante (leer el archivo del otro
   tenant, escaparse con `../`) y comprueban que el código la frena.

Todo corre sin red: `InMemorySaver`, `InMemoryStore` y un chat model scripteado.
"""

import asyncio

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from app.ai_core.admin import agent as admin_agent
from app.ai_core.admin.agent import (
    MEMORY_FILE,
    build_admin_agent,
    memory_namespace,
)
from app.ai_core.admin.tools import ADMIN_TOOLS
from app.ai_core.channel.outbox import TurnRuntime
from app.ai_core.common import middleware as common_middleware
from app.ai_core.config.tenant import (
    HARNESS_TOOLS,
    AdminAgentConfig,
    PublicAgentConfig,
    TenantConfig,
)

TENANT_A = TenantConfig(
    tenant_id="ferreteria-juan",
    business_name="Ferretería Juan",
    public_agent=PublicAgentConfig(),
    admin_agent=AdminAgentConfig(allowed_numbers=["59170000001"]),
)
TENANT_B = TenantConfig(
    tenant_id="moda-maria",
    business_name="Moda María",
    public_agent=PublicAgentConfig(),
    admin_agent=AdminAgentConfig(allowed_numbers=["59170000002"]),
)

SECRET = "El proveedor de tornillos es Acme y nos hace 30% de descuento."


class ScriptedModel(BaseChatModel):
    """Emite una lista fija de tool calls, una por vuelta, y después contesta.

    Se hace pasar por DeepSeek a propósito: `create_deep_agent` resuelve el harness profile
    por el `ls_provider` que devuelve `_get_ls_params()` (no por `_llm_type`, que la clase
    base sólo usa para derivarlo del nombre de la clase). Sin esto el test correría con el
    stack default —subagente general-purpose incluido— y no probaría el de producción.
    `ChatDeepSeek` real devuelve `ls_provider='deepseek'`, que es lo que se imita acá.
    """

    scripted_calls: list[dict] = []

    @property
    def _llm_type(self) -> str:
        return "deepseek"

    def _get_ls_params(self, stop=None, **kwargs):
        return {"ls_provider": "deepseek", "ls_model_name": "deepseek-v4-flash",
                "ls_model_type": "chat"}

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        raise NotImplementedError("async only")

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        done = sum(1 for m in messages if isinstance(m, AIMessage) and m.tool_calls)
        if done < len(self.scripted_calls):
            call = self.scripted_calls[done]
            message = AIMessage(
                content="",
                tool_calls=[{**call, "id": f"call-{done}"}],
            )
        else:
            message = AIMessage(content="listo")
        return ChatResult(generations=[ChatGeneration(message=message)])

    def bind_tools(self, tools, **kwargs):
        return self


@pytest.fixture
def store():
    return InMemoryStore()


@pytest.fixture
def build(monkeypatch, store):
    """Construye un admin agent real, con las dependencias de red reemplazadas."""
    saver = InMemorySaver()

    async def fake_checkpointer():
        return saver

    async def fake_store():
        return store

    monkeypatch.setattr(admin_agent, "open_checkpointer", fake_checkpointer)
    monkeypatch.setattr(admin_agent, "open_store", fake_store)

    def _build(tenant: TenantConfig, calls: list[dict] | None = None):
        monkeypatch.setattr(
            admin_agent,
            "build_chat_model",
            lambda role, temperature: ScriptedModel(scripted_calls=calls or []),
        )
        return asyncio.run(build_admin_agent(tenant))

    return _build


def _run(agent, tenant: TenantConfig, thread_id: str) -> list:
    result = asyncio.run(
        agent.ainvoke(
            {"messages": [HumanMessage(content="hola")]},
            config={"configurable": {"thread_id": thread_id, "turn_id": "wamid-1"}},
            context=TurnRuntime(tenant_id=tenant.tenant_id),
        )
    )
    return result["messages"]


def _tool_output(messages, name: str) -> str:
    """Contenido del ToolMessage de `name`, o falla con contexto útil."""
    for message in messages:
        if isinstance(message, ToolMessage) and message.name == name:
            return str(message.content)
    raise AssertionError(f"no hubo ToolMessage de {name!r} en {messages}")


# --------------------------------------------------------------------------
# 1. Inventario de tools
# --------------------------------------------------------------------------

def test_tool_inventory_is_exactly_business_plus_harness(build):
    """Ni una tool de más (`task`, `execute`, `glob`…) ni una de menos."""
    agent = build(TENANT_A)
    registered = set(agent.nodes["tools"].bound._tools_by_name)

    expected = {tool.name for tool in ADMIN_TOOLS} | set(HARNESS_TOOLS)
    assert registered == expected


@pytest.mark.parametrize("forbidden", ["task", "execute"])
def test_dangerous_builtins_are_not_registered(build, forbidden):
    """Superficie de ataque real: `execute` es shell y `task` le da las tools ERP del
    dueño a un subagente genérico."""
    agent = build(TENANT_A)
    assert forbidden not in agent.nodes["tools"].bound._tools_by_name


@pytest.mark.parametrize("excluded", ["glob", "grep", "delete"])
def test_low_value_builtins_are_not_registered(build, excluded):
    """Estas NO se excluyen por aislamiento — ver el test de abajo, que prueba que serían
    igual de seguras. Se excluyen porque no aportan: hay un único archivo de memoria, así
    que `glob`/`grep` sólo gastan tokens de schema en cada llamada al modelo, y `delete`
    deja que el modelo borre de un saque toda la memoria acumulada del dueño (pérdida de
    datos, no fuga). `edit_file` cubre corregir un hecho viejo, que es lo único que el
    prompt pide.
    """
    agent = build(TENANT_A)
    assert excluded not in agent.nodes["tools"].bound._tools_by_name


def test_admin_gets_a_higher_tool_call_budget_than_public():
    """Planificar gasta llamadas: con el límite del público el agente se queda corto."""
    assert (
        common_middleware.MAX_TOOL_CALLS_PER_RUN_ADMIN
        > common_middleware.MAX_TOOL_CALLS_PER_RUN
    )

    def run_limit(role):
        stack = common_middleware.specialist_middleware(TENANT_A, role)
        return stack[0].run_limit

    assert run_limit("admin") == common_middleware.MAX_TOOL_CALLS_PER_RUN_ADMIN
    assert run_limit("public") == common_middleware.MAX_TOOL_CALLS_PER_RUN


def test_guardrail_lets_harness_tools_through_only_for_admin():
    """El público no corre sobre deepagents: su allow-list no se toca."""
    admin = common_middleware.build_tool_guardrail(TENANT_A, "admin")
    public = common_middleware.build_tool_guardrail(TENANT_A, "public")

    assert HARNESS_TOOLS <= admin.allowed
    assert not (HARNESS_TOOLS & public.allowed)


# --------------------------------------------------------------------------
# 2. Aislamiento multitenant
# --------------------------------------------------------------------------

def _write_secret(build, tenant):
    agent = build(tenant, [{"name": "write_file", "args": {"file_path": MEMORY_FILE,
                                                           "content": SECRET}}])
    return _run(agent, tenant, f"{tenant.tenant_id}:admin:59170000001")


def test_memory_lands_in_the_tenants_own_namespace(build, store):
    """La tupla de namespace es la frontera dura; el path es sólo una key adentro."""
    _write_secret(build, TENANT_A)

    mine = store.search(memory_namespace(TENANT_A.tenant_id))
    assert [item.key for item in mine] == ["/AGENTS.md"]
    assert SECRET in mine[0].value["content"]

    assert store.search(memory_namespace(TENANT_B.tenant_id)) == []


def test_another_tenant_cannot_read_the_same_path(build):
    """Mismo path literal, otro tenant: el archivo no existe para él."""
    _write_secret(build, TENANT_A)

    agent_b = build(TENANT_B, [{"name": "read_file", "args": {"file_path": MEMORY_FILE}}])
    output = _tool_output(_run(agent_b, TENANT_B, "moda-maria:admin:59170000002"), "read_file")

    assert SECRET not in output
    assert "not found" in output.lower()


def test_path_traversal_cannot_escape_the_namespace(build):
    """`../` no cambia de namespace: queda como key literal dentro del mismo."""
    _write_secret(build, TENANT_A)

    escape = f"/memories/../../{TENANT_A.tenant_id}/admin/memories/AGENTS.md"
    agent_b = build(TENANT_B, [{"name": "read_file", "args": {"file_path": escape}}])
    output = _tool_output(_run(agent_b, TENANT_B, "moda-maria:admin:59170000002"), "read_file")

    assert SECRET not in output


def test_memory_survives_into_a_brand_new_conversation(build):
    """El punto de usar el Store y no el checkpoint: sobrevive al thread."""
    _write_secret(build, TENANT_A)

    agent = build(TENANT_A, [{"name": "read_file", "args": {"file_path": MEMORY_FILE}}])
    messages = _run(agent, TENANT_A, "ferreteria-juan:admin:otro-thread-nuevo")

    assert SECRET in _tool_output(messages, "read_file")


class _FakeRuntime:
    """Lo que ve el factory en producción: el `Runtime` de LangGraph, con el
    `TurnRuntime` colgando de `.context`."""

    def __init__(self, context):
        self.context = context


def test_namespace_factory_refuses_a_turn_from_another_tenant():
    """Defensa en profundidad: si el caché de agentes se equivoca, falla ruidoso."""
    factory = admin_agent._namespace_factory("ferreteria-juan")
    expected = memory_namespace("ferreteria-juan")

    assert factory(_FakeRuntime(TurnRuntime(tenant_id="ferreteria-juan"))) == expected
    # Sin `TurnRuntime` (tests, CLI) no hay con qué contrastar: manda el de build time.
    assert factory(None) == expected
    assert factory(_FakeRuntime(None)) == expected

    with pytest.raises(RuntimeError, match="namespace mismatch"):
        factory(_FakeRuntime(TurnRuntime(tenant_id="moda-maria")))


def test_every_backend_operation_is_namespace_scoped(build, store):
    """El aislamiento no depende de qué tools expongamos: es el `namespace`.

    `ls`/`grep`/`glob`/`delete` resuelven la tupla por el mismo `_get_namespace()` que
    `read`/`write`, así que serían tan seguras como las que sí exponemos. Se prueba acá,
    a nivel de backend, porque el agente no las registra: si algún día se re-habilita
    alguna, este test ya dice qué garantía tiene que seguir valiendo — y si deepagents
    alguna vez rompe el scoping de una de ellas, rompe acá.
    """
    _write_secret(build, TENANT_A)
    # El mismo constructor que usa `build_admin_agent`, no una réplica del test.
    backend = admin_agent.build_memory_backend(TENANT_B.tenant_id, store)

    assert backend.ls("/memories/").entries == []
    assert backend.grep("proveedor", path="/memories/").matches == []
    assert backend.glob("**/*.md", path="/memories/").matches == []
    assert backend.delete(MEMORY_FILE).error is not None

    # Y el archivo del otro tenant sigue intacto después del intento de borrado.
    assert store.search(memory_namespace(TENANT_A.tenant_id))[0].value["content"] == SECRET


def test_writing_outside_memories_is_denied(build, store):
    """Todo lo escribible tiene que caer en el route persistente y namespaceado.

    Si no, va al `StateBackend`, que se serializa entero en cada checkpoint de un thread
    que no termina nunca.
    """
    agent = build(TENANT_A, [{"name": "write_file",
                              "args": {"file_path": "/notas.txt", "content": SECRET}}])
    output = _tool_output(_run(agent, TENANT_A, "ferreteria-juan:admin:59170000001"),
                          "write_file")

    assert "denied" in output.lower() or "permission" in output.lower()
    assert store.search(memory_namespace(TENANT_A.tenant_id)) == []

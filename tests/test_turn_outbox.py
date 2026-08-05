"""Canario del outbox por turno.

Todo el envío de fotos, botones y listas depende de una propiedad de LangGraph:
que el objeto pasado como ``context=`` llegue intacto a una tool que corre dentro
del subgrafo de un especialista. Si un upgrade la rompe, las tools encolan en el
vacío, el webhook no entrega nada y **nadie se entera**: el cliente recibe el
texto y ninguna foto, sin un solo error en los logs.

Por eso este test arma el sándwich real (StateGraph padre + create_agent +
ToolContextMiddleware + @contextual_tool) en vez de mockear el runtime.

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
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import asyncio

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.types import Command

from app.ai_core.agents.context_middleware import build_tool_context
from app.ai_core.channel.actions import SendTextAction
from app.ai_core.channel.outbox import TurnOutbox, TurnRuntime
from app.ai_core.config.tenant import AdminAgentConfig, PublicAgentConfig, TenantConfig
from app.ai_core.tools.context import ToolContext, contextual_tool

TENANT = TenantConfig(
    tenant_id="t1",
    business_name="Kiosco",
    public_agent=PublicAgentConfig(),
    admin_agent=AdminAgentConfig(),
)


@contextual_tool
async def queue_probe(note: str, ctx: ToolContext) -> str:
    """Encola una acción de canal. Sonda del test, no es una tool de negocio."""
    if ctx.outbox is None:
        return "no-outbox"
    ctx.outbox.add(SendTextAction(body=note))
    return "queued"


class ToolThenAnswerModel(BaseChatModel):
    """Pide `queue_probe` una vez y después contesta. Sin red."""

    @property
    def _llm_type(self) -> str:
        return "fake-tool-then-answer"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        raise NotImplementedError("async only")

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        from langchain_core.outputs import ChatGeneration, ChatResult

        already_called = any(getattr(m, "tool_calls", None) for m in messages)
        if already_called:
            message = AIMessage(content="listo")
        else:
            message = AIMessage(
                content="",
                tool_calls=[
                    {"name": "queue_probe", "args": {"note": "ping"}, "id": "call-1"},
                ],
            )
        return ChatResult(generations=[ChatGeneration(message=message)])

    def bind_tools(self, tools, **kwargs):
        return self


def _build_graph():
    """Especialista dentro de un StateGraph padre: la topología real del swarm."""
    specialist = create_agent(
        name="probe_specialist",
        model=ToolThenAnswerModel(),
        system_prompt="probe",
        tools=[queue_probe],
        middleware=[build_tool_context(TENANT, "public")],
        context_schema=TurnRuntime,
    )

    async def entry(state) -> Command:
        return Command(goto="probe_specialist")

    builder = StateGraph(MessagesState, context_schema=TurnRuntime)
    builder.add_node("entry", entry, destinations=("probe_specialist",))
    builder.add_node("probe_specialist", specialist)
    builder.add_edge(START, "entry")
    return builder.compile(checkpointer=InMemorySaver())


def _run(graph, runtime: TurnRuntime, thread_id: str, text: str):
    return asyncio.run(
        graph.ainvoke(
            {"messages": [HumanMessage(content=text)]},
            config={"configurable": {"thread_id": thread_id, "turn_id": "wamid-1"}},
            context=runtime,
        )
    )


def test_a_tool_inside_a_subgraph_reaches_the_callers_outbox():
    """El corazón del diseño: el append de la tool lo ve quien invocó el grafo."""
    graph = _build_graph()
    runtime = TurnRuntime()

    _run(graph, runtime, "thread-a", "hola")

    assert [action.body for action in runtime.outbox.actions] == ["ping"]


def test_each_turn_starts_with_an_empty_outbox():
    """Un TurnRuntime nuevo por turno es lo que impide que se filtre entre clientes."""
    graph = _build_graph()

    first = TurnRuntime()
    _run(graph, first, "thread-a", "hola")
    second = TurnRuntime()
    _run(graph, second, "thread-b", "hola")

    assert len(first.outbox.actions) == 1
    assert len(second.outbox.actions) == 1


def test_the_outbox_never_reaches_the_checkpoint():
    """El checkpoint es durable: un objeto no serializable lo rompería."""
    graph = _build_graph()
    runtime = TurnRuntime()
    config = {"configurable": {"thread_id": "thread-c", "turn_id": "wamid-1"}}

    asyncio.run(
        graph.ainvoke(
            {"messages": [HumanMessage(content="hola")]},
            config=config,
            context=runtime,
        )
    )
    snapshot = asyncio.run(graph.aget_state(config))

    assert "outbox" not in snapshot.values
    assert "channel_actions" not in snapshot.values
    for value in snapshot.metadata.values():
        assert isinstance(value, (str, int, float, bool, dict, type(None))), value


def test_turn_runtime_is_truthy_when_empty():
    """`Runtime.merge` hace `other.context or self.context`.

    Un contexto falsy se pierde en silencio al cruzar al subgrafo. Si alguien le
    agrega `__bool__`/`__len__` a TurnRuntime, esto tiene que romper acá y no en
    producción con las fotos que no se mandan.
    """
    assert bool(TurnRuntime())
    assert bool(TurnRuntime(outbox=TurnOutbox()))


def test_drain_empties_the_buffer():
    outbox = TurnOutbox()
    outbox.add(SendTextAction(body="a"))

    assert [action.body for action in outbox.drain()] == ["a"]
    assert outbox.actions == []

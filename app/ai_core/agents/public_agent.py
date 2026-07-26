import logging
import time
import uuid
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.types import Command

from app.ai_core.agents.guardrails import (
    InputTooLongError,
    sanitize_user_input,
)
from app.ai_core.agents.handoffs import (
    build_handoff_tools,
    handoff_targets,
)
from app.ai_core.agents.llm import resolve_model_name
from app.ai_core.agents.router import build_router_graph
from app.ai_core.config.tenant import TenantConfig
from app.ai_core.observability.langfuse import (
    invocation_config,
    trace_attributes,
)
from app.ai_core.observability.tracing import trace_turn
from app.ai_core.persistence.checkpointer import open_checkpointer
from app.ai_core.subagents import (
    build_catalog,
    build_closer,
    build_greeter,
    build_objection,
)

logger = logging.getLogger(__name__)

_INTENT_TO_SPECIALIST = {
    "greeting": "greeter",
    "catalog": "catalog",
    "objection": "objection",
    "close": "closer",
}

_SPECIALIST_BUILDERS = {
    "greeter": build_greeter,
    "catalog": build_catalog,
    "objection": build_objection,
    "closer": build_closer,
}

ROUTER_CONTEXT_MESSAGES = 10

_INPUT_TOO_LONG_RESPONSE = (
    "Lo siento, tu mensaje es demasiado largo. ¿Puedes resumirlo? / "
    "Sorry, your message is too long. Can you shorten it?"
)
_EMPTY_INPUT_RESPONSE = "No recibí tu mensaje, ¿puedes repetirlo? / I didn't get a message, can you repeat it?"


class PublicSwarmState(MessagesState):
    """Shared, checkpointed state for the public specialist swarm."""

    active_agent: str | None


def _message_to_router_dict(message: BaseMessage | dict) -> dict | None:
    """Keep only conversational messages relevant to initial intent routing."""
    if isinstance(message, BaseMessage):
        role = message.type
        content = message.content
    else:
        role = message.get("role") or message.get("type")
        content = message.get("content", "")
    if role == "tool":
        return None
    return {"role": role, "content": content}


def _sum_tokens(usage: dict) -> int:
    if not isinstance(usage, dict):
        return 0
    total = usage.get("total_tokens")
    if total is not None:
        return int(total)
    return int((usage.get("input_tokens") or 0) + (usage.get("output_tokens") or 0))


def _extract_usage(messages: list) -> tuple[int, str]:
    tokens = 0
    tool_calls: list[str] = []
    for message in messages:
        tokens += _sum_tokens(getattr(message, "usage_metadata", None) or {})
        for call in getattr(message, "tool_calls", None) or []:
            tool_calls.append(call.get("name", str(call)))
    return tokens, str(tool_calls)


def _enabled_specialists(tenant: TenantConfig) -> tuple[str, ...]:
    configured = tenant.public_agent.allowed_subagents
    unknown = sorted(set(configured) - set(_SPECIALIST_BUILDERS))
    if unknown:
        logger.warning(
            "Ignoring unknown public specialists for tenant %s: %s",
            tenant.tenant_id,
            unknown,
        )
    enabled = tuple(name for name in _SPECIALIST_BUILDERS if name in configured)
    if not enabled:
        raise ValueError(
            f"Tenant '{tenant.tenant_id}' has no enabled public specialists"
        )
    return enabled


async def build_public_agent(tenant: TenantConfig):
    """Build the stateful public swarm and its specialist agent nodes."""
    enabled = _enabled_specialists(tenant)
    router_graph = build_router_graph(tenant)
    specialists = {
        name: _SPECIALIST_BUILDERS[name](
            tenant,
            build_handoff_tools(name, enabled),
        )
        for name in enabled
    }
    fallback = enabled[0]
    checkpointer = await open_checkpointer()

    async def initial_router(state: PublicSwarmState) -> Command:
        recent_messages = [
            normalized
            for normalized in (
                _message_to_router_dict(message)
                for message in state["messages"][-ROUTER_CONTEXT_MESSAGES:]
            )
            if normalized is not None
        ]
        routed = await router_graph.ainvoke({"messages": recent_messages})
        target = _INTENT_TO_SPECIALIST.get(routed["selected_specialist"], fallback)
        if target not in specialists:
            logger.info(
                "Router selected disabled specialist '%s'; using '%s'",
                target,
                fallback,
            )
            target = fallback
        return Command(update={"active_agent": target}, goto=target)

    def route_from_start(state: PublicSwarmState) -> str:
        active = state.get("active_agent")
        return active if active in specialists else "initial_router"

    builder = StateGraph(PublicSwarmState)
    builder.add_node(
        "initial_router",
        initial_router,
        destinations=tuple(specialists),
    )
    for name, specialist in specialists.items():
        builder.add_node(
            name,
            specialist,
            destinations=handoff_targets(name, enabled),
        )
    builder.add_conditional_edges(
        START,
        route_from_start,
        path_map=["initial_router", *enabled],
    )

    return builder.compile(checkpointer=checkpointer)


async def run_public_agent_turn(
    agent,
    tenant: TenantConfig,
    thread_id: str,
    user_message: str,
    message_id: str | None = None,
) -> dict[str, Any]:
    """Run one public turn; the checkpoint resumes the last active specialist.

    ``message_id`` is the inbound WhatsApp message id when the caller has one. It
    doubles as this turn's identity for tool idempotency (see `invocation_config`),
    so a redelivered message cannot register the same order twice.
    """
    try:
        user_message = sanitize_user_input(user_message)
    except InputTooLongError:
        logger.info("Rejected over-long message on thread %s", thread_id)
        return {"messages": [AIMessage(content=_INPUT_TOO_LONG_RESPONSE)]}
    if not user_message:
        return {"messages": [AIMessage(content=_EMPTY_INPUT_RESPONSE)]}

    # The graph message id stays unique per invocation (it is how the turn's own
    # messages are located below); `turn_id` is the one that must be stable across
    # a redelivery of the same inbound message.
    turn_id = message_id or str(uuid.uuid4())
    message_id = str(uuid.uuid4())
    start = time.time()
    run_name = "public-support-turn"
    with trace_attributes(
        thread_id=thread_id,
        tenant_id=tenant.tenant_id,
        role="public",
        run_name=run_name,
    ):
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=user_message, id=message_id)]},
            config=invocation_config(thread_id, run_name, turn_id=turn_id),
        )
    latency_ms = int((time.time() - start) * 1000)

    messages = list(result.get("messages", []))
    turn_start = next(
        (
            index
            for index, message in enumerate(messages)
            if getattr(message, "id", None) == message_id
        ),
        max(len(messages) - 1, 0),
    )
    turn_messages = messages[turn_start:]
    last_message = turn_messages[-1] if turn_messages else None
    output_text = (
        last_message.content
        if last_message is not None and hasattr(last_message, "content")
        else ""
    )
    active_agent = result.get("active_agent") or "unassigned"

    try:
        tokens, tools_called = _extract_usage(turn_messages)
        await trace_turn(
            tenant=tenant,
            thread_id=thread_id,
            role="public",
            subagent=active_agent,
            model=resolve_model_name("public"),
            input_text=user_message,
            output_text=output_text,
            tokens=tokens,
            tools_called=tools_called,
            latency_ms=latency_ms,
        )
    except Exception as exc:  # noqa: BLE001 - tracing must never fail a customer turn
        logger.warning("Turn tracing failed: %s", exc)

    return {**result, "messages": turn_messages}

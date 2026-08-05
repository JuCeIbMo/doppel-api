import logging
import time
import uuid
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.types import Command

from app.ai_core.common.middleware import (
    InputTooLongError,
    sanitize_user_input,
)
from app.ai_core.common.llm import resolve_model_name
from app.ai_core.channel.outbox import TurnRuntime
from app.ai_core.public.router import classify_intent
from app.ai_core.config.tenant import TenantConfig
from app.ai_core.observability.langfuse import (
    invocation_config,
    trace_attributes,
)
from app.ai_core.observability.tracing import trace_turn
from app.ai_core.persistence.checkpointer import open_checkpointer
from app.ai_core.public.specialists import (
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

_INPUT_TOO_LONG_RESPONSE = (
    "Lo siento, tu mensaje es demasiado largo. ¿Puedes resumirlo? / "
    "Sorry, your message is too long. Can you shorten it?"
)
_EMPTY_INPUT_RESPONSE = "No recibí tu mensaje, ¿puedes repetirlo? / I didn't get a message, can you repeat it?"


class PublicAgentState(MessagesState):
    """Checkpointed state for the public turn graph.

    ``active_agent`` is never control flow. The router re-classifies on every
    turn instead of resuming the last active specialist, and ``active_agent``
    serves two other purposes: it biases the next turn's classification towards
    continuity (``router._continuity_prompt``) and it is what ``trace_turn``
    records as the turn's specialist. ``intent``/``confidence`` are the router's
    raw output for the current turn; ``intent`` is ``None`` when classification
    failed, which ``route_dispatch`` reads as "keep the previous specialist".
    """

    active_agent: str | None
    intent: str | None
    confidence: float | None


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
    """Build the public turn graph: the router dispatches fresh on every turn.

    ``START -> classify_intent -> route_dispatch -> <specialist> -> END``. There
    is no sticky routing and no handoff between specialists: a specialist cannot
    jump to another one, so the ping-pong that had no safety net once the router
    stopped running is structurally impossible. If the specialist needs to
    change, the next turn's router call handles it -- biased towards continuity
    by the previous ``active_agent``.
    """
    enabled = _enabled_specialists(tenant)
    router_node = classify_intent(tenant)
    specialists = {name: _SPECIALIST_BUILDERS[name](tenant) for name in enabled}
    fallback = enabled[0]
    checkpointer = await open_checkpointer()

    def route_dispatch(state: PublicAgentState) -> Command:
        intent = state.get("intent")
        if intent is None:
            # Classification failed after its retries: continuity beats silence.
            target = state.get("active_agent") or fallback
        else:
            target = _INTENT_TO_SPECIALIST.get(intent, fallback)
        # Also catches an `active_agent` checkpointed before the tenant disabled
        # that specialist.
        if target not in specialists:
            logger.info(
                "Router selected disabled specialist '%s'; using '%s'",
                target,
                fallback,
            )
            target = fallback
        return Command(update={"active_agent": target}, goto=target)

    builder = StateGraph(PublicAgentState, context_schema=TurnRuntime)
    builder.add_node("classify_intent", router_node)
    builder.add_node("route_dispatch", route_dispatch, destinations=tuple(specialists))
    for name, specialist in specialists.items():
        builder.add_node(name, specialist)
        builder.add_edge(name, END)
    builder.add_edge(START, "classify_intent")
    builder.add_edge("classify_intent", "route_dispatch")

    return builder.compile(checkpointer=checkpointer)


async def run_public_agent_turn(
    agent,
    tenant: TenantConfig,
    thread_id: str,
    user_message: str,
    message_id: str | None = None,
) -> dict[str, Any]:
    """Run one public turn; the router picks the specialist, the checkpoint the history.

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
    # One per invocation: this is what keeps the channel actions of two
    # concurrent conversations apart. See `channel/outbox.py`.
    turn_runtime = TurnRuntime()
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
            context=turn_runtime,
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

    return {
        **result,
        "messages": turn_messages,
        "channel_actions": turn_runtime.outbox.drain(),
    }

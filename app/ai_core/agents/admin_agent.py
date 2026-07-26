import logging
import time
import uuid
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage

from app.ai_core.agents.guardrails import (
    InputTooLongError,
    sanitize_user_input,
)
from app.ai_core.agents.lifecycle import attach_lifecycle
from app.ai_core.agents.llm import build_chat_model, resolve_model_name
from app.ai_core.config.tenant import TenantConfig
from app.ai_core.observability.langfuse import (
    invocation_config,
    trace_attributes,
)
from app.ai_core.observability.tracing import trace_turn
from app.ai_core.persistence.checkpointer import open_checkpointer
from app.ai_core.subagents._base import (
    allowed_tools_for,
    load_prompt,
    specialist_middleware,
)
from app.ai_core.tools import (
    add_product,
    check_stock,
    get_sales_report,
    search_catalog,
    update_config,
    update_stock,
)

logger = logging.getLogger(__name__)

_ADMIN_DEFAULT_TOOLS = [
    get_sales_report,
    add_product,
    update_stock,
    update_config,
    search_catalog,
    check_stock,
]

_INPUT_TOO_LONG_RESPONSE = (
    "El mensaje es demasiado largo. Envíalo en partes más cortas. / "
    "The message is too long. Send it in shorter parts."
)
_EMPTY_INPUT_RESPONSE = "Mensaje vacío. / Empty message."


async def build_admin_agent(tenant: TenantConfig):
    system_prompt = load_prompt(tenant, "admin", "admin_agent")
    tools = allowed_tools_for(tenant, "admin", _ADMIN_DEFAULT_TOOLS)
    model = build_chat_model("admin", temperature=0.3)
    checkpointer_ctx, checkpointer = await open_checkpointer()

    agent = create_agent(
        name="admin_agent",
        model=model,
        system_prompt=system_prompt,
        tools=tools,
        checkpointer=checkpointer,
        middleware=specialist_middleware(tenant, "admin"),
    )

    agent._checkpointer_ctx = checkpointer_ctx

    attach_lifecycle(agent)

    return agent


async def run_admin_agent_turn(
    agent,
    tenant: TenantConfig,
    thread_id: str,
    user_message: str,
) -> dict[str, Any]:
    """Run one admin turn with input guardrails and per-turn tracing.

    Mirrors the public agent's entry point so both roles get the same
    robustness (sanitized input) and observability (trace per turn).
    """
    try:
        user_message = sanitize_user_input(user_message)
    except InputTooLongError:
        logger.info("Rejected over-long admin message on thread %s", thread_id)
        return {"messages": [AIMessage(content=_INPUT_TOO_LONG_RESPONSE)]}
    if not user_message:
        return {"messages": [AIMessage(content=_EMPTY_INPUT_RESPONSE)]}

    message_id = str(uuid.uuid4())
    start = time.time()
    run_name = "admin-support-turn"
    with trace_attributes(
        thread_id=thread_id,
        tenant_id=tenant.tenant_id,
        role="admin",
        run_name=run_name,
    ):
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=user_message, id=message_id)]},
            config=invocation_config(thread_id, run_name),
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

    try:
        await trace_turn(
            tenant=tenant,
            thread_id=thread_id,
            role="admin",
            subagent="admin_agent",
            model=resolve_model_name("admin"),
            input_text=user_message,
            output_text=output_text,
            tokens=0,
            tools_called="[]",
            latency_ms=latency_ms,
        )
    except Exception as exc:  # noqa: BLE001 - tracing must never fail an admin turn
        logger.warning("Admin turn tracing failed: %s", exc)

    return {**result, "messages": turn_messages}

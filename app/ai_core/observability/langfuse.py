"""Minimal Langfuse wiring for top-level LangGraph invocations."""

import hashlib
import logging
import os
from contextlib import contextmanager, nullcontext
from typing import Any

logger = logging.getLogger(__name__)

_handler: Any = None
_initialized = False

# Supersteps allowed per graph invocation. Each subgraph gets its own budget of
# this size, not a share of the parent's, so a specialist alternating
# model -> tools -> model can do (limit - 1) // 2 tool round-trips before
# LangGraph raises GraphRecursionError and kills the turn without a reply.
#
# Kept above 2 * MAX_TOOL_CALLS_PER_RUN + 1 on purpose: the tool-call cap has
# to be what stops a runaway loop, because it blocks tools while letting the
# model still answer. This limit is the crash-shaped backstop behind it.
GRAPH_RECURSION_LIMIT = 12


def tracing_enabled() -> bool:
    """Return whether both Langfuse project credentials are configured."""
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))


def get_handler():
    """Return one process-wide LangChain callback handler, or ``None``."""
    global _handler, _initialized
    if _initialized:
        return _handler
    _initialized = True

    if not tracing_enabled():
        return None

    try:
        from langfuse.langchain import CallbackHandler

        _handler = CallbackHandler()
    except Exception as exc:  # noqa: BLE001 - observability must not break the app
        logger.warning("Langfuse initialization failed; tracing disabled: %s", exc)
        _handler = None
    return _handler


def invocation_config(
    thread_id: str, run_name: str, turn_id: str | None = None,
    confirmed_action_id: str | None = None,
) -> dict[str, Any]:
    """Build the LangGraph config and attach Langfuse when configured.

    ``turn_id`` identifies this single turn (the inbound WhatsApp message id when
    there is one). It travels in `configurable` so `ToolContextMiddleware` can
    hand it to the tools: `create_order` derives its idempotency key from it, so
    a retry inside one turn dedupes while the same order placed again in a later
    message is a genuinely new sale.
    """
    config: dict[str, Any] = {
        "configurable": {"thread_id": thread_id, "turn_id": turn_id or "",
                         "confirmed_action_id": confirmed_action_id or ""},
        "recursion_limit": GRAPH_RECURSION_LIMIT,
        "run_name": run_name,
    }
    handler = get_handler()
    if handler is not None:
        config["callbacks"] = [handler]
    return config


@contextmanager
def trace_attributes(
    *,
    thread_id: str,
    tenant_id: str,
    role: str,
    run_name: str,
):
    """Propagate searchable, non-PII attributes to every observation."""
    if get_handler() is None:
        with nullcontext():
            yield
        return

    from langfuse import propagate_attributes

    with propagate_attributes(
        trace_name=run_name,
        session_id=_opaque_id(thread_id),
        user_id=_opaque_id(_contact_from_thread_id(thread_id)),
        tags=[f"tenant:{tenant_id}", f"role:{role}"],
        metadata={"tenant_id": tenant_id, "role": role},
    ):
        yield


def flush() -> None:
    """Send buffered events before a short-lived CLI process exits."""
    if not tracing_enabled():
        return
    try:
        from langfuse import get_client

        get_client().flush()
    except Exception as exc:  # noqa: BLE001 - shutdown must remain best-effort
        logger.warning("Langfuse flush failed: %s", exc)


def _contact_from_thread_id(thread_id: str) -> str:
    parts = thread_id.split(":", 2)
    return parts[2] if len(parts) == 3 else thread_id


def _opaque_id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]

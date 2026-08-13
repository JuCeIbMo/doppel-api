import logging
import re

from langchain.agents.middleware import AgentMiddleware, ToolCallLimitMiddleware, ToolCallRequest
from langchain_core.messages import ToolMessage, trim_messages

from app.ai_core.config.tenant import HARNESS_TOOLS, TenantConfig
from app.ai_core.tools.context import ToolContext

logger = logging.getLogger(__name__)

MAX_TOOL_CALLS_PER_RUN = 5
# El admin planifica: un pedido abierto ("¿por qué bajaron las ventas?") gasta un
# `write_todos`, varias lecturas encadenadas y quizá un `write_file` a memoria. Con el
# límite del público (5) el agente se queda sin llamadas antes de terminar de mirar.
MAX_TOOL_CALLS_PER_RUN_ADMIN = 20
MAX_CATALOG_SEARCHES_PER_RUN = 3


class MessageWindowMiddleware(AgentMiddleware):
    """Bound model context while the parent graph keeps full durable history.

    This caps the size of each model call's prompt; it is NOT a loop breaker.
    Runaway tool loops are stopped by `MAX_TOOL_CALLS_PER_RUN` /
    `MAX_CATALOG_SEARCHES_PER_RUN` in this module, with
    `GRAPH_RECURSION_LIMIT` as the backstop behind them.
    """

    def __init__(self, max_messages: int = 40):
        self.max_messages = max_messages

    def _trim(self, request):
        messages = trim_messages(
            request.messages,
            max_tokens=self.max_messages,
            token_counter=len,
            strategy="last",
            start_on="human",
            # Without this, `strategy="last"` drops the system prompt as soon as
            # the history outgrows the window: the specialist silently loses its
            # instructions and the business name mid-conversation, and starts
            # answering like a generic chatbot. Pinning it costs one slot of
            # history and leaves the window itself unchanged.
            include_system=True,
        )
        return request.override(messages=messages)

    def wrap_model_call(self, request, handler):
        return handler(self._trim(request))

    async def awrap_model_call(self, request, handler):
        return await handler(self._trim(request))


class ToolContextMiddleware(AgentMiddleware):
    """Inject the run-scoped ToolContext into tools that accept a ``ctx`` arg.

    LangChain does not automatically inject this project's custom ``ToolContext``.
    This middleware sets ``request.tool_call["args"]["ctx"]``
    for any tool whose schema includes a ``ctx`` field, so tenant, role and
    thread_id are always available to the business tools without relying on the
    model to supply them.

    The injected context object is stripped from the stored tool_call before the
    result is returned, so the non-JSON-serializable object does not leak into
    checkpointed state or back to the model.
    """

    tools = ()

    def __init__(self, tenant: TenantConfig, role: str):
        self.tenant = tenant
        self.role = role

    def _inject(self, request: ToolCallRequest):
        """Return (injected?, original_args) after adding ctx to the call args."""
        tool = request.tool
        original_args = request.tool_call.get("args", {})
        if tool is None or not _tool_accepts_ctx(tool):
            return False, original_args
        configurable = request.runtime.config.get("configurable", {})
        thread_id = configurable.get("thread_id", "")
        turn_id = configurable.get("turn_id", "")
        confirmed_action_id = configurable.get("confirmed_action_id", "")
        images = configurable.get("images", [])
        # The outbox comes from the run-scoped `context=` instead of `configurable`
        # because it is mutable and per-turn: this middleware lives inside an agent
        # that `bridge` caches across turns and conversations, so anything stored on
        # `self` would leak between customers. See `channel/outbox.py`.
        turn_runtime = getattr(request.runtime, "context", None)
        # Inject ctx into a copy of the args so the original tool_call stored in
        # the assistant message is not polluted with a non-JSON-serializable object.
        request.tool_call["args"] = {
            **original_args,
            "ctx": ToolContext(
                tenant=self.tenant,
                role=self.role,
                thread_id=thread_id,
                turn_id=turn_id,
                confirmed_action_id=confirmed_action_id,
                outbox=getattr(turn_runtime, "outbox", None),
                images=images,
            ),
        }
        return True, original_args

    def _restore(self, request: ToolCallRequest, injected: bool, original_args) -> None:
        # Restore the original args (without ctx) so subsequent model calls can
        # serialize the tool_call history without exposing the injected context.
        if injected:
            request.tool_call["args"] = original_args

    def wrap_tool_call(self, request: ToolCallRequest, handler):
        injected, original_args = self._inject(request)
        try:
            return handler(request)
        finally:
            self._restore(request, injected, original_args)

    async def awrap_tool_call(self, request: ToolCallRequest, handler):
        injected, original_args = self._inject(request)
        try:
            return await handler(request)
        finally:
            self._restore(request, injected, original_args)


def _tool_accepts_ctx(tool) -> bool:
    """Return True if the tool's argument schema exposes a ``ctx`` field."""
    schema = getattr(tool, "args_schema", None)
    if schema is None:
        return False
    fields = getattr(schema, "model_fields", None)
    if fields is None:
        return False
    return "ctx" in fields


def build_tool_context(tenant: TenantConfig, role: str) -> ToolContextMiddleware:
    return ToolContextMiddleware(tenant, role)


def build_message_window(max_messages: int = 40) -> MessageWindowMiddleware:
    return MessageWindowMiddleware(max_messages)


class ToolGuardrailMiddleware(AgentMiddleware):
    """Reject tool calls outside the allow-list for the active role.

    For tools passed in `tools=` this duplicates what `allowed_tools_for` already did at
    build time. Its non-redundant job is policing tools injected by *middleware*, which never
    pass through `ADMIN_TOOLS` nor the tenant allow-list — that is what the admin agent's
    deepagents harness adds (see `HARNESS_TOOLS`). Keeping it fail-closed means a future
    deepagents upgrade that ships a new built-in gets rejected loudly instead of quietly
    widening what the business owner can reach.
    """

    tools = ()

    def __init__(self, tenant: TenantConfig, role: str):
        self.allowed = set(
            tenant.public_agent.allowed_tools
            if role == "public"
            else tenant.admin_agent.allowed_tools
        )
        # Only the admin agent runs on the deepagents harness. The public agent binds none of
        # these, so leaving it strictly fail-closed costs nothing and keeps the surface where
        # customers talk to the bot as narrow as it is today.
        if role == "admin":
            self.allowed |= HARNESS_TOOLS
        self.role = role

    def _rejection(self, request: ToolCallRequest) -> ToolMessage | None:
        tool_name = request.tool_call["name"]
        if tool_name in self.allowed:
            return None
        return ToolMessage(
            content=f"Error: tool '{tool_name}' is not allowed for role '{self.role}'.",
            tool_call_id=request.tool_call.get("id", ""),
        )

    def wrap_tool_call(self, request: ToolCallRequest, handler):
        rejection = self._rejection(request)
        return rejection if rejection is not None else handler(request)

    async def awrap_tool_call(self, request: ToolCallRequest, handler):
        rejection = self._rejection(request)
        return rejection if rejection is not None else await handler(request)

    def __call__(self, request, handler):
        return self.wrap_tool_call(request, handler)


class ToolErrorMiddleware(AgentMiddleware):
    """Convert tool exceptions into structured error messages for the model."""

    tools = ()

    def _error_result(self, request: ToolCallRequest, exc: Exception) -> ToolMessage:
        tool_name = request.tool_call.get("name", "unknown")
        logger.warning("Tool '%s' failed: %s", tool_name, exc)
        return ToolMessage(
            content=f"Error: {exc}",
            tool_call_id=request.tool_call.get("id", ""),
            status="error",
        )

    def wrap_tool_call(self, request: ToolCallRequest, handler):
        try:
            return handler(request)
        except Exception as exc:  # noqa: BLE001 - tool error boundary
            return self._error_result(request, exc)

    async def awrap_tool_call(self, request: ToolCallRequest, handler):
        try:
            return await handler(request)
        except Exception as exc:  # noqa: BLE001 - tool error boundary
            return self._error_result(request, exc)

    def __call__(self, request, handler):
        return self.wrap_tool_call(request, handler)


def build_tool_guardrail(tenant: TenantConfig, role: str) -> ToolGuardrailMiddleware:
    return ToolGuardrailMiddleware(tenant, role)


def build_tool_error_boundary() -> ToolErrorMiddleware:
    return ToolErrorMiddleware()


MAX_USER_MESSAGE_CHARS = 2000
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class InputTooLongError(ValueError):
    """Raised when a user message exceeds the accepted length."""


def sanitize_user_input(text: str, max_chars: int = MAX_USER_MESSAGE_CHARS) -> str:
    cleaned = _CONTROL_CHARS_RE.sub("", text or "").strip()
    if len(cleaned) > max_chars:
        raise InputTooLongError(
            f"message length {len(cleaned)} exceeds limit {max_chars}"
        )
    return cleaned


def specialist_middleware(tenant: TenantConfig, role: str) -> list:
    """Shared async middleware stack for every specialist and the admin agent."""
    run_limit = (
        MAX_TOOL_CALLS_PER_RUN_ADMIN if role == "admin" else MAX_TOOL_CALLS_PER_RUN
    )
    return [
        ToolCallLimitMiddleware(
            run_limit=run_limit,
            exit_behavior="continue",
        ),
        ToolCallLimitMiddleware(
            tool_name="search_catalog",
            run_limit=MAX_CATALOG_SEARCHES_PER_RUN,
            exit_behavior="continue",
        ),
        build_tool_error_boundary(),
        build_tool_guardrail(tenant, role),
        build_tool_context(tenant, role),
        build_message_window(),
    ]

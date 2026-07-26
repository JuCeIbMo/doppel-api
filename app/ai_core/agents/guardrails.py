import logging
import re

from langchain.agents.middleware import AgentMiddleware, ToolCallRequest
from langchain_core.messages import ToolMessage

from app.ai_core.config.tenant import TenantConfig

logger = logging.getLogger(__name__)


class ToolGuardrailMiddleware(AgentMiddleware):
    """Middleware that rejects tool calls outside the role's allow-list."""

    tools = ()

    def __init__(
        self,
        tenant: TenantConfig,
        role: str,
        extra_allowed_tools: set[str] | None = None,
    ):
        self.allowed = set(
            tenant.public_agent.allowed_tools
            if role == "public"
            else tenant.admin_agent.allowed_tools
        )
        self.allowed.update(extra_allowed_tools or ())
        self.role = role

    def _error_message(self, tool_name: str) -> str:
        return f"Error: tool '{tool_name}' is not allowed for role '{self.role}'."

    def _rejection(self, request: ToolCallRequest) -> ToolMessage | None:
        tool_name = request.tool_call["name"]
        if tool_name in self.allowed:
            return None
        return ToolMessage(
            content=self._error_message(tool_name),
            tool_call_id=request.tool_call.get("id", ""),
        )

    def wrap_tool_call(self, request: ToolCallRequest, handler):
        """AgentMiddleware hook used by create_agent."""
        rejection = self._rejection(request)
        return rejection if rejection is not None else handler(request)

    async def awrap_tool_call(self, request: ToolCallRequest, handler):
        rejection = self._rejection(request)
        return rejection if rejection is not None else await handler(request)

    def __call__(self, request, handler):
        """Functional interface used by unit tests."""
        return self.wrap_tool_call(request, handler)


class ToolErrorMiddleware(AgentMiddleware):
    """Convert tool exceptions into structured error ToolMessages.

    A failing tool (insufficient stock, permission error, DB
    hiccup) would kill the whole turn and leave the customer without a
    response. This boundary returns the error to the model as an ordinary tool
    result so the specialist can apologize, retry, or offer alternatives.
    """

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
        except Exception as exc:  # noqa: BLE001 - this is the tool error boundary
            return self._error_result(request, exc)

    async def awrap_tool_call(self, request: ToolCallRequest, handler):
        try:
            return await handler(request)
        except Exception as exc:  # noqa: BLE001 - this is the tool error boundary
            return self._error_result(request, exc)

    def __call__(self, request, handler):
        """Functional interface used by unit tests."""
        return self.wrap_tool_call(request, handler)


def build_tool_guardrail(
    tenant: TenantConfig,
    role: str,
    extra_allowed_tools: set[str] | None = None,
):
    return ToolGuardrailMiddleware(tenant, role, extra_allowed_tools)


def build_tool_error_boundary() -> ToolErrorMiddleware:
    return ToolErrorMiddleware()


# --------------------------------------------------------------------------
# Input guardrail (minimal): length cap + control-character stripping.
# --------------------------------------------------------------------------

MAX_USER_MESSAGE_CHARS = 2000

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class InputTooLongError(ValueError):
    """Raised when a user message exceeds the allowed length."""


def sanitize_user_input(text: str, max_chars: int = MAX_USER_MESSAGE_CHARS) -> str:
    """Strip control characters and enforce a maximum message length.

    Returns the cleaned text (possibly empty). Raises ``InputTooLongError``
    when the cleaned text exceeds ``max_chars`` so the caller can reply with a
    canned, polite refusal without spending a model call.
    """
    cleaned = _CONTROL_CHARS_RE.sub("", text or "").strip()
    if len(cleaned) > max_chars:
        raise InputTooLongError(
            f"message length {len(cleaned)} exceeds limit {max_chars}"
        )
    return cleaned

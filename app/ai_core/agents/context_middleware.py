from langchain.agents.middleware import AgentMiddleware, ToolCallRequest
from langchain_core.messages import trim_messages

from app.ai_core.config.tenant import TenantConfig
from app.ai_core.tools.context import ToolContext


class MessageWindowMiddleware(AgentMiddleware):
    """Bound model context while the parent graph keeps full durable history."""

    def __init__(self, max_messages: int = 40):
        self.max_messages = max_messages

    def wrap_model_call(self, request, handler):
        messages = trim_messages(
            request.messages,
            max_tokens=self.max_messages,
            token_counter=len,
            strategy="last",
            start_on="human",
        )
        return handler(request.override(messages=messages))


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

    def wrap_tool_call(self, request: ToolCallRequest, handler):
        tool = request.tool
        original_args = request.tool_call.get("args", {})
        if tool is not None and _tool_accepts_ctx(tool):
            thread_id = request.runtime.config.get("configurable", {}).get(
                "thread_id", ""
            )
            # Inject ctx into a copy of the args so the original tool_call stored in
            # the assistant message is not polluted with a non-JSON-serializable object.
            request.tool_call["args"] = {
                **original_args,
                "ctx": ToolContext(
                    tenant=self.tenant,
                    role=self.role,
                    thread_id=thread_id,
                ),
            }
        try:
            return handler(request)
        finally:
            # Restore the original args (without ctx) so subsequent model calls can
            # serialize the tool_call history without exposing the injected context.
            if tool is not None and _tool_accepts_ctx(tool):
                request.tool_call["args"] = original_args


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

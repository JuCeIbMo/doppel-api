import inspect
from dataclasses import dataclass
from typing import Annotated

from langchain.tools import tool
from langchain_core.tools import InjectedToolArg, StructuredTool
from pydantic import BaseModel

from app.ai_core.channel.outbox import TurnOutbox
from app.ai_core.config.tenant import TenantConfig


@dataclass
class ToolContext:
    tenant: TenantConfig
    role: str
    thread_id: str
    # Identifies the turn this tool call belongs to (the inbound WhatsApp message
    # id when available, otherwise a per-turn uuid). `create_order` keys its
    # idempotency off it — see `tools/sales.py`.
    turn_id: str = ""
    # Set only by bridge after it validated a raw WhatsApp confirmation button.
    # It prevents a model from executing an old action merely by seeing its id in
    # durable conversation history.
    confirmed_action_id: str = ""
    # Channel actions queued during this turn, delivered by the webhook once the
    # graph finishes. ``None`` when the graph was invoked without a `TurnRuntime`
    # (tests, CLI): the channel tools degrade to a no-op instead of raising.
    outbox: TurnOutbox | None = None


# `ctx: InjectedCtx` instead of a bare `ctx: ToolContext`: with `InjectedToolArg`,
# LangChain drops the field from `tool_call_schema` (what the model sees) and from
# `_filter_injected_args` (what reaches the Langfuse trace), while still keeping it
# in `args_schema.model_fields` so `_tool_accepts_ctx` and the middleware injection
# below keep working. A bare annotation survives both and leaks the tenant's whole
# `TenantConfig` into every tool call's trace.
InjectedCtx = Annotated[ToolContext, InjectedToolArg]


def contextual_tool(func):
    """Decorate a function that needs a runtime-injected ``ToolContext``.

    The returned tool validates ``ctx`` at execution time (so the middleware can
    inject it), but ``ctx`` is omitted from the JSON schema sent to the LLM via the
    ``InjectedCtx`` annotation on the argument itself.

    Every business tool in this package is an ``async def``, so it must be passed
    to ``from_function`` as ``coroutine=``, never as ``func=``: LangChain treats
    ``func`` as synchronous and would hand the model an un-awaited coroutine
    object instead of the tool's result.
    """
    base_tool = tool(func)
    is_async = inspect.iscoroutinefunction(func)

    async def _acoroutine(*args, **kwargs):
        result = await func(*args, **kwargs)
        return result.model_dump(exclude_none=True) if isinstance(result, BaseModel) else result

    class ContextualTool(StructuredTool):
        def __call__(self, *args, **kwargs):
            """Allow the tool to be invoked like a plain function in tests.

            For an async tool this returns the ``ainvoke`` coroutine, so callers
            await it exactly as they would await the undecorated function.
            """
            tool_input = {}
            for name, value in zip(self.args_schema.model_fields.keys(), args):
                tool_input[name] = value
            tool_input.update(kwargs)
            return self.ainvoke(tool_input) if is_async else self.invoke(tool_input)

    return ContextualTool.from_function(
        func=None if is_async else func,
        coroutine=_acoroutine if is_async else None,
        name=base_tool.name,
        description=base_tool.description,
        args_schema=base_tool.args_schema,
    )

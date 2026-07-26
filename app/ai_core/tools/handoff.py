from app.ai_core.tools.context import ToolContext, contextual_tool
from app.ai_core.tools.models import HandoffResult
from app.services.erp.context import bot_context, log_activity


@contextual_tool
async def human_handoff(reason: str, ctx: ToolContext) -> HandoffResult:
    """Request a handoff to a human agent."""
    if ctx.role != "public":
        raise PermissionError("human_handoff requires public role")

    log_activity(
        bot_context(ctx.tenant.tenant_id, actor="whatsapp_bot"),
        action="handoff.requested", module="ai", detail={"reason": reason, "thread_id": ctx.thread_id},
    )
    return HandoffResult(status="handoff_requested", reason=reason)

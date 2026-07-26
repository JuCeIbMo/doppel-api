from app.ai_core.tools.context import ToolContext, contextual_tool
from app.services.erp.context import bot_context
from app.services.erp.reports import ReportsService, default_period


@contextual_tool
async def get_sales_report(ctx: ToolContext) -> dict:
    """Return a summary of the current month's sales and revenue. Admin-only."""
    if ctx.role != "admin":
        raise PermissionError("get_sales_report requires admin role")

    erp_ctx = bot_context(ctx.tenant.tenant_id, actor="admin_bot")
    date_from, date_to = default_period(None, None)
    report = await ReportsService().dashboard(erp_ctx, date_from=date_from, date_to=date_to)
    return {"order_count": report["sales_count"], "total_revenue": report["sales_total"]}

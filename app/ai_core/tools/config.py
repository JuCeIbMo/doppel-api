from app.ai_core.config.loader import load_tenant_config
from app.ai_core.tools.context import ToolContext, contextual_tool


@contextual_tool
async def update_config(ctx: ToolContext, requested_changes: str = "") -> dict:
    """Read the current tenant configuration and suggest changes.

    This tool intentionally does not write any changes. It returns the current
    configuration so the owner can review it and confirm updates separately.
    """
    if ctx.role != "admin":
        raise PermissionError("update_config requires admin role")

    config = load_tenant_config(ctx.tenant.tenant_id)
    return {
        "current_config": config.model_dump(),
        "requested_changes": requested_changes,
        "note": "Changes are suggestions only. Apply nothing without explicit owner confirmation.",
    }

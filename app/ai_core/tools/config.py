"""Read-only view of the tenant's bot configuration.

Deliberately read-only, and named to say so. This used to be `update_config`
with a `requested_changes` argument while the body only ever read: the model
picks its action from the tool name and signature, so it would call it for
"cambiá el horario", get a success payload back, and tell the owner the change
was applied. Nothing had changed. A read tool must not be named like a write.

Applying changes stays in the dashboard, where the owner sees and confirms them.
"""

from app.ai_core.config.loader import load_tenant_config
from app.ai_core.tools.context import ToolContext, contextual_tool


@contextual_tool
async def get_config(ctx: ToolContext) -> dict:
    """Read the current bot configuration for this business.

    Read-only: this cannot change any setting. To actually apply a change, the
    owner must edit it in the dashboard — say so instead of implying it is done.
    """
    if ctx.role != "admin":
        raise PermissionError("get_config requires admin role")

    config = await load_tenant_config(ctx.tenant.tenant_id)
    return {
        "current_config": config.model_dump(),
        "writable": False,
        "note": (
            "Read-only view. No setting was modified. Changes must be made by the "
            "owner in the dashboard; never tell them a change has been applied."
        ),
    }

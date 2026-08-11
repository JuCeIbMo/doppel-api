from typing import Annotated

from pydantic import Field

from app.ai_core.tools.context import InjectedCtx, ToolContext, contextual_tool
from app.ai_core.tools.models import StockResult
from app.services.erp.context import bot_context
from app.services.erp.exceptions import NotFound
from app.services.erp.inventory import InventoryService
from app.services.erp.products import ProductsService


def _erp_ctx(ctx: ToolContext):
    actor = "whatsapp_bot" if ctx.role == "public" else "admin_bot"
    return bot_context(ctx.tenant.tenant_id, actor=actor)


@contextual_tool
async def check_stock(product_id: str, ctx: InjectedCtx) -> StockResult:
    """Check available stock for a product by its id (as returned by search_catalog).

    If `found` is false the id does not exist — do not tell the customer the
    product is out of stock. Search the catalog again to get a real id.
    """
    if ctx.role not in {"public", "admin"}:
        raise PermissionError("check_stock requires public or admin role")

    try:
        product = await ProductsService().get(_erp_ctx(ctx), product_id)
    except NotFound:
        return StockResult(product_id=product_id, quantity=0, found=False)
    return StockResult(
        product_id=product_id, quantity=float(product.get("stock", 0)), found=True
    )


@contextual_tool
async def update_stock(
    product_id: str,
    quantity: Annotated[float, Field(ge=0)],
    ctx: InjectedCtx,
) -> StockResult:
    """Set the stock quantity for a product to a specific count. Admin-only."""
    if ctx.role != "admin":
        raise PermissionError("update_stock requires admin role")

    result = await InventoryService().adjust(
        _erp_ctx(ctx), product_id=product_id, variant_id=None,
        new_quantity=quantity, delta=None, note="Ajuste vía agente IA (update_stock)",
    )
    return StockResult(product_id=product_id, quantity=result["quantity"])

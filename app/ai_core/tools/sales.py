"""`create_order`: registers a sale through the real ERP (atomic Postgres RPC).

Body calls `storefront.register_sale`, which delegates to `SalesService.create_sale`
(an atomic `create_sale` Postgres RPC — stock, finance and client rollups commit
together or not at all). That covers the ported project's "no overselling"
guarantee natively.

KNOWN GAP vs. the ported project: the ported `create_order` deduped retries by a
thread-scoped `idempotency_key` (checked against a stored order before creating).
`sales.create_sale` has no such column/check today, so an LLM retry of this tool
with the same items WILL create a second sale. Closing this gap needs a schema
change (a unique `idempotency_key` on `sales`, checked before the RPC) — flagged
here rather than faked with an in-process cache, which wouldn't survive a restart
or work across multiple workers.
"""

from app.ai_core.tools.context import ToolContext, contextual_tool
from app.ai_core.tools.models import OrderItemInput, OrderItemResult, OrderResult
from app.services import storefront
from app.services.erp.context import bot_context


def _customer_phone(ctx: ToolContext) -> str | None:
    """thread_id is `{tenant_id}:{role}:{phone}`; public threads carry the customer phone."""
    parts = ctx.thread_id.split(":", 2)
    return parts[2] if len(parts) == 3 and parts[1] == "public" else None


@contextual_tool
async def create_order(items: list[OrderItemInput], ctx: ToolContext) -> OrderResult:
    """Create a confirmed order after verifying stock. Confirm product, quantity
    and price with the customer before calling this."""
    if ctx.role != "public":
        raise PermissionError("create_order requires public role")
    if not items:
        raise ValueError("items must contain at least one product")

    erp_ctx = bot_context(ctx.tenant.tenant_id, actor="whatsapp_bot")
    result = await storefront.register_sale(
        erp_ctx,
        [{"product_id": i.product_id, "quantity": i.quantity} for i in items],
        customer_phone=_customer_phone(ctx),
        payment_method="whatsapp",
    )
    if not result["ok"]:
        raise ValueError(f"{result['error']}: {result['message']}")

    return OrderResult(
        total=result["total"],
        items=[
            OrderItemResult(
                product_id=items[idx].product_id,
                name=line["name"],
                quantity=line["qty"],
                subtotal=line["subtotal"],
            )
            for idx, line in enumerate(result["items"])
        ],
    )

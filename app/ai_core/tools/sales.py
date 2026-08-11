"""`create_order`: registers a sale through the real ERP (atomic Postgres RPC).

Body calls `storefront.register_sale`, which delegates to `SalesService.create_sale`
(an atomic `create_sale` Postgres RPC — stock, finance and client rollups commit
together or not at all). That covers the ported project's "no overselling"
guarantee natively.

Retries are deduped by an `idempotency_key` derived here and enforced by the RPC
(`migration_v10_sale_idempotency.sql`: unique index on `sales(tenant_id,
idempotency_key)` plus an advisory lock, so the check and the insert share one
transaction). The guarantee deliberately lives in Postgres and not in an
in-process cache, which would not survive a restart nor work across workers.

The key is scoped to one turn (`thread_id` + `turn_id` + the items), which is the
line between the two cases: the model calling `create_order` twice for the same
order — same turn, one sale — and the customer genuinely ordering the same thing
again in a later message — different turn, a second sale, as it should be. The
turn id is the inbound WhatsApp message id when there is one, so a redelivery
from Meta lands on the same key too.
"""

import hashlib
import json

from app.ai_core.tools.context import InjectedCtx, ToolContext, contextual_tool
from app.ai_core.tools.models import OrderItemInput, OrderItemResult, OrderResult
from app.services import storefront
from app.services.erp.context import bot_context


def _customer_phone(ctx: ToolContext) -> str | None:
    """thread_id is `{tenant_id}:{role}:{phone}`; public threads carry the customer phone."""
    parts = ctx.thread_id.split(":", 2)
    return parts[2] if len(parts) == 3 and parts[1] == "public" else None


def _idempotency_key(ctx: ToolContext, items: list[OrderItemInput]) -> str | None:
    """Stable key for one order attempt: same turn + same items = same sale.

    Items are sorted so the model listing them in a different order on a retry
    still hashes to the same key, and quantities go through `float` so `2` and
    `2.0` do not read as different orders.

    Returns None without a turn id: a key made of thread + items alone would span
    the whole conversation and swallow a customer's genuine repeat order as a
    duplicate. Losing a real sale is worse than the duplicate this guards against,
    so no key means the pre-idempotency behaviour.
    """
    if not ctx.turn_id:
        return None
    payload = json.dumps(
        {
            "thread_id": ctx.thread_id,
            "turn_id": ctx.turn_id,
            "items": sorted(
                ([i.product_id, float(i.quantity)] for i in items),
                key=lambda pair: (pair[0], pair[1]),
            ),
        },
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


@contextual_tool
async def create_order(items: list[OrderItemInput], ctx: InjectedCtx) -> OrderResult:
    """Create a confirmed order after verifying stock. Confirm product, quantity
    and price with the customer before calling this.

    Calling it twice for the same order is safe: the second call returns the same
    order with `duplicate: true` instead of registering another sale. When that
    happens the order is already placed — do not announce it again."""
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
        idempotency_key=_idempotency_key(ctx, items),
    )
    if not result["ok"]:
        raise ValueError(f"{result['error']}: {result['message']}")

    return OrderResult(
        total=result["total"],
        duplicate=result.get("duplicate", False),
        items=[
            OrderItemResult(
                # `product_id` viene del shape de storefront; el fallback por
                # índice sostiene los shapes viejos sin el campo.
                product_id=line.get("product_id") or items[min(idx, len(items) - 1)].product_id,
                name=line["name"],
                quantity=line["qty"],
                subtotal=line["subtotal"],
            )
            for idx, line in enumerate(result["items"])
        ],
    )

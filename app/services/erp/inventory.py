"""Inventory service: read stock, list movements, and apply manual adjustments.

Important invariant: the backend NEVER writes `inventory.quantity` directly. Stock only
changes by inserting an `inventory_movement` row — the DB trigger applies the delta. This
keeps an immutable audit trail and guarantees stock and its history can't drift apart.
"""

from __future__ import annotations

from app.services.erp.context import ERPContext, log_activity
from app.services.erp.exceptions import InsufficientStock, ValidationError
from app.services.supabase_client import get_supabase


def _current_stock(tenant_id: str, product_id: str, variant_id: str | None) -> float:
    q = (
        get_supabase().table("inventory").select("quantity")
        .eq("tenant_id", tenant_id).eq("product_id", product_id)
    )
    q = q.is_("variant_id", "null") if variant_id is None else q.eq("variant_id", variant_id)
    rows = q.limit(1).execute().data
    return float(rows[0]["quantity"]) if rows else 0.0


class InventoryService:
    async def list_stock(self, ctx: ERPContext, *, limit: int = 200, offset: int = 0) -> list[dict]:
        rows = (
            get_supabase().table("inventory")
            .select("product_id, variant_id, quantity, products(name, category, unit, low_stock_threshold)")
            .eq("tenant_id", ctx.tenant_id).range(offset, offset + limit - 1).execute()
        ).data or []
        out = []
        for r in rows:
            p = r.get("products") or {}
            out.append({
                "product_id": r["product_id"],
                "product_name": p.get("name", ""),
                "variant_id": r.get("variant_id"),
                "category": p.get("category"),
                "unit": p.get("unit", "unidad"),
                "quantity": float(r["quantity"]),
                "low_stock_threshold": p.get("low_stock_threshold", 5),
            })
        return out

    async def low_stock(self, ctx: ERPContext) -> list[dict]:
        rows = await self.list_stock(ctx, limit=1000)
        return [r for r in rows if r["quantity"] <= r["low_stock_threshold"]]

    async def movements(self, ctx: ERPContext, *, product_id: str | None = None,
                        limit: int = 50, offset: int = 0) -> list[dict]:
        q = (
            get_supabase().table("inventory_movements")
            .select("id, product_id, variant_id, type, quantity, unit_cost, reference_id, notes, actor, created_at, products(name)")
            .eq("tenant_id", ctx.tenant_id).order("created_at", desc=True)
        )
        if product_id:
            q = q.eq("product_id", product_id)
        rows = (q.range(offset, offset + limit - 1).execute()).data or []
        for r in rows:
            r["product_name"] = (r.pop("products", None) or {}).get("name")
        return rows

    async def adjust(self, ctx: ERPContext, *, product_id: str, variant_id: str | None,
                     new_quantity: float | None, delta: float | None, note: str) -> dict:
        """Apply a manual stock correction by inserting one adjustment movement.

        Accepts EITHER an absolute target (`new_quantity`) OR a signed `delta`.
        Computes the movement type + positive quantity via `_resolve_adjustment` below.
        """
        if (new_quantity is None) == (delta is None):
            raise ValidationError("Indica exactamente uno: new_quantity o delta")

        current = _current_stock(ctx.tenant_id, product_id, variant_id)
        move_type, move_qty = _resolve_adjustment(product_id, current, new_quantity, delta)

        if move_qty == 0:
            return {"ok": True, "product_id": product_id, "quantity": current, "movement": None}

        movement = {
            "tenant_id": ctx.tenant_id,
            "product_id": product_id,
            "variant_id": variant_id,
            "type": move_type,
            "quantity": move_qty,
            "notes": note,
            "actor": ctx.actor,
        }
        get_supabase().table("inventory_movements").insert(movement).execute()
        log_activity(ctx, action="stock.adjusted", module="inventory",
                     detail={"product_id": product_id, "type": move_type, "quantity": move_qty, "note": note})
        return {
            "ok": True,
            "product_id": product_id,
            "quantity": _current_stock(ctx.tenant_id, product_id, variant_id),
            "movement": {"type": move_type, "quantity": move_qty},
        }


def _resolve_adjustment(
    product_id: str, current: float, new_quantity: float | None, delta: float | None
) -> tuple[str, float]:
    """Decide the movement type ('adjustment_in' | 'adjustment_out') and the POSITIVE
    quantity to record, given the current stock and the requested change.

    A target `new_quantity` becomes the change (new_quantity - current); a `delta` is the
    change itself. Positive -> 'adjustment_in', negative -> 'adjustment_out' (absolute value).
    Zero is a no-op. An 'adjustment_out' that would drive stock below 0 is REJECTED rather
    than clamped — a count that doesn't add up is a real discrepancy worth surfacing.

    Returns: (movement_type, positive_quantity)
    """
    change = round((new_quantity - current) if new_quantity is not None else (delta or 0), 3)
    if change == 0:
        return ("adjustment_in", 0)
    if change > 0:
        return ("adjustment_in", change)

    out_qty = -change
    if out_qty > current:
        raise InsufficientStock(product_id=product_id, available=current, requested=out_qty)
    return ("adjustment_out", out_qty)

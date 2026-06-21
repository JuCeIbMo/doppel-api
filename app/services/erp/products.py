"""Products + variants service. All logic + Supabase access for the catalog.

Reuses the existing `products` table (extended in migration_v8_erp.sql). Stock is
read from the `inventory` table and merged in, so a single product response carries
its current quantity — IA-friendly for the bot.
"""

from __future__ import annotations

from typing import Any

from app.services.erp.context import ERPContext, log_activity
from app.services.erp.exceptions import NotFound
from app.services.supabase_client import get_supabase

_FIELDS = (
    "id, name, description, sku, barcode, category, image_url, cost_price, price, "
    "unit, available, has_variants, low_stock_threshold, tags, created_at"
)


def _stock_map(tenant_id: str, product_ids: list[str]) -> dict[str, float]:
    """Sum inventory quantity per product (across variants) for the given products."""
    if not product_ids:
        return {}
    rows = (
        get_supabase()
        .table("inventory")
        .select("product_id, quantity")
        .eq("tenant_id", tenant_id)
        .in_("product_id", product_ids)
        .execute()
    ).data or []
    totals: dict[str, float] = {}
    for r in rows:
        totals[r["product_id"]] = totals.get(r["product_id"], 0) + float(r["quantity"])
    return totals


class ProductsService:
    async def list(
        self, ctx: ERPContext, *, category: str | None = None, search: str | None = None,
        available: bool | None = None, limit: int = 50, offset: int = 0,
    ) -> list[dict]:
        q = (
            get_supabase().table("products").select(_FIELDS)
            .eq("tenant_id", ctx.tenant_id).order("name")
        )
        if category:
            q = q.eq("category", category)
        if search:
            q = q.ilike("name", f"%{search}%")
        if available is True:
            q = q.eq("available", True)
        rows = (q.range(offset, offset + limit - 1).execute()).data or []
        stock = _stock_map(ctx.tenant_id, [r["id"] for r in rows])
        for r in rows:
            r["stock"] = stock.get(r["id"], 0)
        return rows

    async def get(self, ctx: ERPContext, product_id: str) -> dict:
        rows = (
            get_supabase().table("products").select(_FIELDS)
            .eq("tenant_id", ctx.tenant_id).eq("id", product_id).limit(1).execute()
        ).data
        if not rows:
            raise NotFound("Producto no encontrado", product_id=product_id)
        product = rows[0]
        product["stock"] = _stock_map(ctx.tenant_id, [product_id]).get(product_id, 0)
        return product

    async def get_by_barcode(self, ctx: ERPContext, code: str) -> dict:
        rows = (
            get_supabase().table("products").select(_FIELDS)
            .eq("tenant_id", ctx.tenant_id).eq("barcode", code).limit(1).execute()
        ).data
        if not rows:
            raise NotFound("No hay producto con ese código de barras", barcode=code)
        product = rows[0]
        product["stock"] = _stock_map(ctx.tenant_id, [product["id"]]).get(product["id"], 0)
        return product

    async def create(self, ctx: ERPContext, data: dict[str, Any]) -> dict:
        payload = {**data, "tenant_id": ctx.tenant_id}
        row = (get_supabase().table("products").insert(payload).execute()).data[0]
        log_activity(ctx, action="product.created", module="inventory",
                     detail={"product_id": row["id"], "name": row["name"]})
        return row

    async def update(self, ctx: ERPContext, product_id: str, data: dict[str, Any]) -> dict:
        await self.get(ctx, product_id)  # 404 if missing / other tenant
        clean = {k: v for k, v in data.items() if v is not None}
        row = (
            get_supabase().table("products").update(clean)
            .eq("tenant_id", ctx.tenant_id).eq("id", product_id).execute()
        ).data[0]
        log_activity(ctx, action="product.updated", module="inventory",
                     detail={"product_id": product_id, "changed": list(clean.keys())})
        return row

    async def soft_delete(self, ctx: ERPContext, product_id: str) -> dict:
        await self.get(ctx, product_id)
        (
            get_supabase().table("products").update({"available": False})
            .eq("tenant_id", ctx.tenant_id).eq("id", product_id).execute()
        )
        log_activity(ctx, action="product.deactivated", module="inventory",
                     detail={"product_id": product_id})
        return {"ok": True, "product_id": product_id}

    # --- variants ---
    async def add_variant(self, ctx: ERPContext, product_id: str, data: dict[str, Any]) -> dict:
        await self.get(ctx, product_id)
        payload = {**data, "tenant_id": ctx.tenant_id, "product_id": product_id}
        row = (get_supabase().table("product_variants").insert(payload).execute()).data[0]
        (
            get_supabase().table("products").update({"has_variants": True})
            .eq("tenant_id", ctx.tenant_id).eq("id", product_id).execute()
        )
        log_activity(ctx, action="variant.created", module="inventory",
                     detail={"product_id": product_id, "variant_id": row["id"]})
        return row

    async def update_variant(self, ctx: ERPContext, product_id: str, variant_id: str,
                             data: dict[str, Any]) -> dict:
        clean = {k: v for k, v in data.items() if v is not None}
        rows = (
            get_supabase().table("product_variants").update(clean)
            .eq("tenant_id", ctx.tenant_id).eq("id", variant_id).eq("product_id", product_id)
            .execute()
        ).data
        if not rows:
            raise NotFound("Variante no encontrada", variant_id=variant_id)
        return rows[0]

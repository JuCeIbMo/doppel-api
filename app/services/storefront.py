"""Capa de lectura/venta del agente vendedor de cara al público (WhatsApp).

Recibe siempre un ERPContext con actor="whatsapp_bot", scopea por tenant_id en un
solo lugar y devuelve shapes lean optimizados para IA (sin la info de más del ERP).
Reusa los ERP services existentes para que la lógica viva en un solo sitio.
"""

from __future__ import annotations

from app.services.erp.context import ERPContext
from app.services.erp.products import ProductsService
from app.services.supabase_client import get_supabase

_BIZ_FIELDS = "name, description, hours, address, payment_methods"
_BIZ_BLANK = {"name": "", "description": "", "hours": "", "address": "", "payment_methods": ""}


async def business_info(ctx: ERPContext) -> dict:
    """Perfil del negocio para inyectar al prompt (no es una tool)."""
    result = (
        get_supabase().table("business_info").select(_BIZ_FIELDS)
        .eq("tenant_id", ctx.tenant_id).limit(1).execute()
    )
    return result.data[0] if result.data else dict(_BIZ_BLANK)


async def search_catalog(ctx: ERPContext, query: str | None = None) -> list[dict]:
    """Lista lean de productos disponibles. Incluye `id` como ancla para la venta."""
    rows = await ProductsService().list(ctx, search=query, limit=50)
    return [
        {"id": r["id"], "name": r["name"], "price": r["price"],
         "in_stock": float(r.get("stock", 0)) > 0}
        for r in rows
        if r.get("available")
    ]

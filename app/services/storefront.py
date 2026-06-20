"""Capa de lectura/venta del agente vendedor de cara al público (WhatsApp).

Recibe siempre un ERPContext con actor="whatsapp_bot", scopea por tenant_id en un
solo lugar y devuelve shapes lean optimizados para IA (sin la info de más del ERP).
Reusa los ERP services existentes para que la lógica viva en un solo sitio.
"""

from __future__ import annotations

from app.services.erp.clients import ClientsService
from app.services.erp.context import ERPContext
from app.services.erp.exceptions import ERPError, NotFound
from app.services.erp.products import ProductsService
from app.services.erp.sales import SalesService
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
    rows = await ProductsService().list(ctx, search=query, available=True, limit=50)
    return [
        {"id": r["id"], "name": r["name"], "price": r["price"],
         "in_stock": float(r.get("stock", 0)) > 0}
        for r in rows
    ]


async def register_sale(
    ctx: ERPContext,
    items: list[dict],
    customer_phone: str | None = None,
    payment_method: str = "whatsapp",
) -> dict:
    """Registra una venta del vendedor público. `items` = [{product_id, quantity}]
    usando el id que la IA ya obtuvo de search_catalog (no re-resuelve por nombre).
    Delega en SalesService.create_sale (atómico). Devuelve confirmación lean."""
    if not items:
        return {"error": "validation_error",
                "message": "Se requiere al menos un ítem", "detail": {}}

    client_id = None
    if customer_phone:
        try:
            client_id = (await ClientsService().get_by_phone(ctx, customer_phone))["id"]
        except (NotFound, ERPError):
            client_id = None

    body = {
        "client_id": client_id,
        "payment_method": payment_method,
        "cash_account_id": None,
        "discount": 0,
        "notes": None,
        "items": items,
    }
    try:
        sale = await SalesService().create_sale(ctx, body)
    except ERPError as exc:
        return {"error": exc.code, "message": exc.message, "detail": exc.detail}

    return {
        "ok": True,
        "total": sale.get("total"),
        "items": [
            {"name": it.get("product_name"), "qty": it.get("quantity"),
             "subtotal": it.get("subtotal")}
            for it in sale.get("items", [])
        ],
    }

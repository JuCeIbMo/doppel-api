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
        await get_supabase().table("business_info").select(_BIZ_FIELDS)
        .eq("tenant_id", ctx.tenant_id).limit(1).execute()
    )
    return result.data[0] if result.data else dict(_BIZ_BLANK)


# Productos por página. Un catálogo grande devuelto entero en un solo turno es
# la clase de "info innecesaria" que infla cada mensaje al modelo aunque el
# cliente sólo pidió ver "qué tienen" — la IA repagina en vez de recibirlo todo.
CATALOG_PAGE_SIZE = 20


async def search_catalog(ctx: ERPContext, query: str | None = None, page: int = 0) -> dict:
    """Página lean de productos disponibles. Incluye `id` como ancla para la venta y
    `description`/`tags` para que el vendedor matchee la consulta del cliente.

    Pide `page_size + 1` filas para saber si hay más sin una query de COUNT
    aparte, y recorta la fila de sobra antes de devolver."""
    offset = page * CATALOG_PAGE_SIZE
    service = ProductsService()
    normalized_query = (query or "").strip()
    if normalized_query:
        rows = await service.search_available(
            ctx,
            normalized_query,
            limit=CATALOG_PAGE_SIZE + 1,
            offset=offset,
        )
    else:
        rows = await service.list(
            ctx,
            available=True,
            limit=CATALOG_PAGE_SIZE + 1,
            offset=offset,
        )
    has_more = len(rows) > CATALOG_PAGE_SIZE
    rows = rows[:CATALOG_PAGE_SIZE]
    items = [
        {"id": r["id"], "name": r["name"], "price": r["price"],
         "in_stock": float(r.get("stock", 0)) > 0,
         "has_image": bool(r.get("has_image", r.get("image_url"))),
         "description": r.get("description") or "", "tags": r.get("tags") or []}
        for r in rows
    ]
    return {"items": items, "page": page, "has_more": has_more}


async def get_product_image(ctx: ERPContext, product_id: str) -> str | None:
    """URL pública de la foto de un producto, o None si no tiene.

    Aparte de `search_catalog` a propósito: la URL nunca entra al shape lean que
    ve el modelo, porque si la ve la pega en el texto de la respuesta. El agente
    trabaja con el `id` y el canal resuelve la foto.
    """
    rows = (
        await get_supabase().table("products").select("image_url")
        .eq("tenant_id", ctx.tenant_id)
        .eq("id", product_id)
        .eq("available", True)
        .limit(1)
        .execute()
    ).data or []
    return (rows[0].get("image_url") or None) if rows else None


async def register_sale(
    ctx: ERPContext,
    items: list[dict],
    customer_phone: str | None = None,
    payment_method: str = "whatsapp",
    idempotency_key: str | None = None,
) -> dict:
    """Registra una venta del vendedor público. `items` = [{product_id, quantity}]
    usando el id que la IA ya obtuvo de search_catalog (no re-resuelve por nombre).
    Delega en SalesService.create_sale (atómico). Devuelve confirmación lean.

    Con `idempotency_key`, un reintento con la misma clave devuelve la venta ya
    registrada (`duplicate: True`) en vez de crear una segunda."""
    if not items:
        return {"ok": False, "error": "validation_error",
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
        "idempotency_key": idempotency_key,
        "items": items,
    }
    try:
        sale = await SalesService().create_sale(ctx, body)
    except ERPError as exc:
        return {"ok": False, "error": exc.code, "message": exc.message, "detail": exc.detail}

    return {
        "ok": True,
        # True = el RPC devolvió una venta que ya existía con esta clave, no creó otra.
        "duplicate": bool(sale.get("idempotent_replay")),
        "total": sale.get("total"),
        "items": [
            # `product_id` va en el shape para que el consumidor no tenga que
            # aparear por índice contra lo que pidió (el orden de sale_items no
            # está garantizado, y en un replay viene de la venta guardada).
            # El importe de línea es `total` en sale_items; `subtotal` es el
            # fallback para los shapes viejos.
            {"product_id": it.get("product_id"),
             "name": it.get("product_name"), "qty": it.get("quantity"),
             "subtotal": it.get("total", it.get("subtotal"))}
            for it in sale.get("items", [])
        ],
    }

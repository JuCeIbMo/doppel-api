"""Catalog tools. Body reads/writes doppel-api's real ERP, not SQLite.

`search_catalog` reuses `app.services.storefront` (already tenant-scoped, lean
shape for AI). `create_product_from_photo` (admin-only) is the whole product
alta flow: it hands the turn's attached image and the owner's text to
`ProductCreationService`, which optimizes it, uploads it to Storage and gets
Gemini to fill in description/tags — the same pipeline the front's
`/erp/products/analyze-image` uses.
"""

import asyncio
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field

from app.ai_core.tools import render
from app.ai_core.tools.context import InjectedCtx, ToolContext, contextual_tool
from app.ai_core.tools.models import CatalogPage, ProductResult
from app.services import storefront
from app.services.erp.context import bot_context
from app.services.erp.inventory import InventoryService
from app.services.erp.product_creation import ProductCreationService


def _erp_ctx(ctx: ToolContext):
    actor = "whatsapp_bot" if ctx.role == "public" else "admin_bot"
    return bot_context(ctx.tenant.tenant_id, actor=actor)


@contextual_tool
async def search_catalog(query: str | None, ctx: InjectedCtx, page: int = 0) -> CatalogPage:
    """Search available products by name, description and tags.

    Omit `query` to list everything available. Search terms are normalized for
    Spanish and ranked by relevance, with product names weighted highest.

    Results are paginated (20 per page). If the response has `has_more: true`,
    call this again with `page` incremented by 1 to see more — do not assume
    the first page is the whole catalog."""
    if ctx.role not in {"public", "admin"}:
        raise PermissionError("search_catalog requires public or admin role")

    result = await storefront.search_catalog(_erp_ctx(ctx), query, page=page)
    return CatalogPage(
        items=[
            ProductResult(
                id=r["id"], name=r["name"], description=r["description"],
                price=r["price"], in_stock=r["in_stock"],
                has_image=r["has_image"], tags=r["tags"],
            )
            for r in result["items"]
        ],
        page=result["page"],
        has_more=result["has_more"],
    )


@contextual_tool
async def create_product_from_photo(
    ctx: InjectedCtx,
    name: Annotated[str, Field(min_length=1)],
    price: Annotated[float, Field(gt=0)],
    description: str | None = None,
    category: str | None = None,
    cost_price: Annotated[float, Field(ge=0)] | None = None,
    stock: Annotated[float, Field(ge=0)] | None = None,
) -> str:
    """Dar de alta un producto a partir de la foto que el dueño acaba de mandar.
    Requiere que el mensaje traiga una imagen. Gemini completa descripción y
    tags a partir de la foto si no los indicás. Si el dueño dice cuántas
    unidades tiene, pasalas en `stock`."""
    if ctx.role != "admin":
        raise PermissionError("create_product_from_photo requires admin role")
    if not ctx.images:
        return "Necesito la foto del producto para darlo de alta. Mandámela y lo cargo."

    raw_image = await asyncio.to_thread(Path(ctx.images[0]["path"]).read_bytes)

    erp_ctx = _erp_ctx(ctx)
    product_data: dict[str, Any] = {"name": name, "price": price}
    if description is not None:
        product_data["description"] = description
    if category is not None:
        product_data["category"] = category
    if cost_price is not None:
        product_data["cost_price"] = cost_price

    product = await ProductCreationService().create(erp_ctx, product_data, raw_image)

    if stock is not None:
        await InventoryService().adjust(
            erp_ctx, product_id=product["id"], new_quantity=stock, delta=None,
            note="Alta vía agente admin",
        )

    return render.product_created({
        "name": product["name"], "price": product["price"],
        "stock": stock, "has_image": True,
    })

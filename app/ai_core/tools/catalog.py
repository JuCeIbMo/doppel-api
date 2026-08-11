"""Catalog tools. Body reads/writes doppel-api's real ERP, not SQLite.

`search_catalog` reuses `app.services.storefront` (already tenant-scoped, lean
shape for AI). `add_product` (admin-only) goes through `ProductsService`, the
same service the owner's dashboard uses.
"""

from typing import Annotated

from pydantic import Field

from app.ai_core.tools.context import InjectedCtx, ToolContext, contextual_tool
from app.ai_core.tools.models import CatalogPage, ProductResult
from app.services import storefront
from app.services.erp.context import bot_context
from app.services.erp.products import ProductsService


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
async def add_product(
    ctx: InjectedCtx,
    name: Annotated[str, Field(min_length=1)],
    price: Annotated[float, Field(gt=0)],
    description: str | None = None,
    category: str | None = None,
) -> ProductResult:
    """Add a new product to the catalog. Admin-only. Price must be positive."""
    if ctx.role != "admin":
        raise PermissionError("add_product requires admin role")

    row = await ProductsService().create(
        _erp_ctx(ctx),
        {"name": name, "price": price, "description": description, "category": category},
    )
    return ProductResult(
        id=row["id"], name=row["name"], description=row.get("description"),
        price=row["price"], in_stock=False, tags=row.get("tags") or [],
    )

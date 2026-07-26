"""Catalog tools. Body reads/writes doppel-api's real ERP, not SQLite.

`search_catalog` reuses `app.services.storefront` (already tenant-scoped, lean
shape for AI). `add_product` (admin-only) goes through `ProductsService`, the
same service the owner's dashboard uses.
"""

from typing import Annotated

from pydantic import Field

from app.ai_core.tools.context import ToolContext, contextual_tool
from app.ai_core.tools.models import ProductResult
from app.services import storefront
from app.services.erp.context import bot_context
from app.services.erp.products import ProductsService


def _erp_ctx(ctx: ToolContext):
    actor = "whatsapp_bot" if ctx.role == "public" else "admin_bot"
    return bot_context(ctx.tenant.tenant_id, actor=actor)


@contextual_tool
async def search_catalog(query: str | None, ctx: ToolContext) -> list[ProductResult]:
    """Search the product catalog by name. Omit `query` to list everything available."""
    if ctx.role not in {"public", "admin"}:
        raise PermissionError("search_catalog requires public or admin role")

    rows = await storefront.search_catalog(_erp_ctx(ctx), query)
    return [
        ProductResult(
            id=r["id"], name=r["name"], description=r["description"],
            price=r["price"], in_stock=r["in_stock"], tags=r["tags"],
        )
        for r in rows
    ]


@contextual_tool
async def add_product(
    ctx: ToolContext,
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

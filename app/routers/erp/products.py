"""Products + variants endpoints. Thin: validate input, delegate to ProductsService."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from app.models.erp_schemas import (
    ProductCreate,
    ProductResponse,
    ProductUpdate,
    VariantCreate,
    VariantResponse,
)
from app.services.erp.context import ERPContext, get_erp_context
from app.services.erp.product_creation import ProductCreationService
from app.services.erp.products import ProductsService
from app.services.images import MAX_BYTES

router = APIRouter()
service = ProductsService()
creation_service = ProductCreationService(service)


async def _product_create_form(
    name: Annotated[str, Form()],
    description: Annotated[str | None, Form()] = None,
    sku: Annotated[str | None, Form()] = None,
    barcode: Annotated[str | None, Form()] = None,
    category: Annotated[str | None, Form()] = None,
    cost_price: Annotated[float, Form()] = 0,
    price: Annotated[float, Form()] = 0,
    unit: Annotated[str, Form()] = "unidad",
    available: Annotated[bool, Form()] = True,
    low_stock_threshold: Annotated[int, Form()] = 5,
    tags: Annotated[list[str] | None, Form()] = None,
) -> ProductCreate:
    """Expose ProductCreate as ordinary multipart fields in OpenAPI/Swagger."""
    return ProductCreate(
        name=name,
        description=description,
        sku=sku,
        barcode=barcode,
        category=category,
        cost_price=cost_price,
        price=price,
        unit=unit,
        available=available,
        low_stock_threshold=low_stock_threshold,
        tags=tags or [],
    )


@router.get("", response_model=list[ProductResponse])
async def list_products(
    ctx: ERPContext = Depends(get_erp_context),
    category: str | None = None,
    search: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    return await service.list(ctx, category=category, search=search, limit=limit, offset=offset)


@router.post("", response_model=ProductResponse)
async def create_product(
    image: Annotated[UploadFile, File(description="Imagen principal obligatoria")],
    body: ProductCreate = Depends(_product_create_form),
    ctx: ERPContext = Depends(get_erp_context),
):
    """Create a complete product from metadata and its required primary image."""
    return await creation_service.create(
        ctx,
        body.model_dump(exclude_none=True),
        await image.read(MAX_BYTES + 1),
    )


@router.get("/barcode/{code}", response_model=ProductResponse)
async def get_by_barcode(code: str, ctx: ERPContext = Depends(get_erp_context)):
    return await service.get_by_barcode(ctx, code)


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(product_id: str, ctx: ERPContext = Depends(get_erp_context)):
    return await service.get(ctx, product_id)


@router.put("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: str, body: ProductUpdate, ctx: ERPContext = Depends(get_erp_context)
):
    return await service.update(ctx, product_id, body.model_dump(exclude_unset=True))


@router.delete("/{product_id}")
async def delete_product(product_id: str, ctx: ERPContext = Depends(get_erp_context)):
    return await service.soft_delete(ctx, product_id)


@router.post("/{product_id}/variants", response_model=VariantResponse)
async def add_variant(
    product_id: str, body: VariantCreate, ctx: ERPContext = Depends(get_erp_context)
):
    return await service.add_variant(ctx, product_id, body.model_dump(exclude_none=True))


@router.put("/{product_id}/variants/{variant_id}", response_model=VariantResponse)
async def update_variant(
    product_id: str, variant_id: str, body: VariantCreate,
    ctx: ERPContext = Depends(get_erp_context),
):
    return await service.update_variant(ctx, product_id, variant_id, body.model_dump(exclude_unset=True))

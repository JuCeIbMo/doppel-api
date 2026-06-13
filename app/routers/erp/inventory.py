"""Inventory endpoints. Thin: validate, delegate to InventoryService."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.models.erp_schemas import AdjustmentRequest, InventoryRow, MovementResponse
from app.services.erp.context import ERPContext, get_erp_context
from app.services.erp.inventory import InventoryService

router = APIRouter()
service = InventoryService()


@router.get("", response_model=list[InventoryRow])
async def list_stock(
    ctx: ERPContext = Depends(get_erp_context),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    return await service.list_stock(ctx, limit=limit, offset=offset)


@router.get("/low-stock", response_model=list[InventoryRow])
async def low_stock(ctx: ERPContext = Depends(get_erp_context)):
    return await service.low_stock(ctx)


@router.post("/adjustment")
async def adjust_stock(body: AdjustmentRequest, ctx: ERPContext = Depends(get_erp_context)):
    return await service.adjust(
        ctx,
        product_id=body.product_id,
        variant_id=body.variant_id,
        new_quantity=body.new_quantity,
        delta=body.delta,
        note=body.note,
    )


@router.get("/movements", response_model=list[MovementResponse])
async def movements(
    ctx: ERPContext = Depends(get_erp_context),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    return await service.movements(ctx, limit=limit, offset=offset)


@router.get("/movements/{product_id}", response_model=list[MovementResponse])
async def movements_for_product(
    product_id: str,
    ctx: ERPContext = Depends(get_erp_context),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    return await service.movements(ctx, product_id=product_id, limit=limit, offset=offset)

"""Sales endpoints. Thin: validate, delegate to SalesService (atomic RPCs)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.models.erp_schemas import CreateSaleRequest, SaleResponse
from app.services.erp.context import ERPContext, get_erp_context
from app.services.erp.sales import SalesService

router = APIRouter()
service = SalesService()


@router.post("", response_model=SaleResponse)
async def create_sale(body: CreateSaleRequest, ctx: ERPContext = Depends(get_erp_context)):
    return await service.create_sale(ctx, body.model_dump())


@router.get("", response_model=list[SaleResponse])
async def list_sales(
    ctx: ERPContext = Depends(get_erp_context),
    client_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    return await service.list(
        ctx, client_id=client_id, date_from=date_from, date_to=date_to, limit=limit, offset=offset
    )


@router.get("/{sale_id}", response_model=SaleResponse)
async def get_sale(sale_id: str, ctx: ERPContext = Depends(get_erp_context)):
    return await service.get(ctx, sale_id)


@router.post("/{sale_id}/cancel", response_model=SaleResponse)
async def cancel_sale(sale_id: str, ctx: ERPContext = Depends(get_erp_context)):
    return await service.cancel_sale(ctx, sale_id)

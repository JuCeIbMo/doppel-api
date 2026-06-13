"""Reports endpoints. All accept ?date_from=&date_to= (default = current month)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.models.erp_schemas import DashboardResponse
from app.services.erp.context import ERPContext, get_erp_context
from app.services.erp.reports import ReportsService, default_period

router = APIRouter()
service = ReportsService()


@router.get("/dashboard", response_model=DashboardResponse)
async def dashboard(
    ctx: ERPContext = Depends(get_erp_context),
    date_from: str | None = None,
    date_to: str | None = None,
):
    f, t = default_period(date_from, date_to)
    return await service.dashboard(ctx, date_from=f, date_to=t)


@router.get("/top-products")
async def top_products(
    ctx: ERPContext = Depends(get_erp_context),
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = Query(5, ge=1, le=50),
):
    f, t = default_period(date_from, date_to)
    return await service.top_products(ctx, date_from=f, date_to=t, limit=limit)


@router.get("/sales-by-period")
async def sales_by_period(
    ctx: ERPContext = Depends(get_erp_context),
    date_from: str | None = None,
    date_to: str | None = None,
    group_by: str = Query("day", pattern="^(day|week|month)$"),
):
    f, t = default_period(date_from, date_to)
    return await service.sales_by_period(ctx, date_from=f, date_to=t, group_by=group_by)


@router.get("/margin")
async def margin(
    ctx: ERPContext = Depends(get_erp_context),
    date_from: str | None = None,
    date_to: str | None = None,
):
    f, t = default_period(date_from, date_to)
    return await service.margin(ctx, date_from=f, date_to=t)


@router.get("/clients")
async def clients_report(
    ctx: ERPContext = Depends(get_erp_context),
    date_from: str | None = None,
    date_to: str | None = None,
):
    f, t = default_period(date_from, date_to)
    return await service.clients(ctx, date_from=f, date_to=t)

"""Finance endpoints. Thin: validate, delegate to FinanceService."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query

from app.models.erp_schemas import (
    CashAccountCreate,
    CashAccountResponse,
    CashAccountUpdate,
    TransactionCreate,
    TransactionResponse,
)
from app.services.erp.context import ERPContext, get_erp_context
from app.services.erp.finance import FinanceService

router = APIRouter()
service = FinanceService()


@router.get("/transactions", response_model=list[TransactionResponse])
async def list_transactions(
    ctx: ERPContext = Depends(get_erp_context),
    type: str | None = None,
    category: str | None = None,
    account_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    return await service.list_transactions(
        ctx, type=type, category=category, account_id=account_id,
        date_from=date_from, date_to=date_to, limit=limit, offset=offset,
    )


@router.post("/transactions", response_model=TransactionResponse)
async def create_transaction(body: TransactionCreate, ctx: ERPContext = Depends(get_erp_context)):
    return await service.create_transaction(ctx, body.model_dump())


@router.get("/categories", response_model=list[str])
async def categories(ctx: ERPContext = Depends(get_erp_context)):
    return await service.categories(ctx)


@router.get("/accounts", response_model=list[CashAccountResponse])
async def list_accounts(ctx: ERPContext = Depends(get_erp_context)):
    return await service.list_accounts(ctx)


@router.post("/accounts", response_model=CashAccountResponse)
async def create_account(body: CashAccountCreate, ctx: ERPContext = Depends(get_erp_context)):
    return await service.create_account(ctx, body.model_dump(exclude_none=True))


@router.put("/accounts/{account_id}", response_model=CashAccountResponse)
async def update_account(
    account_id: str, body: CashAccountUpdate, ctx: ERPContext = Depends(get_erp_context)
):
    return await service.update_account(ctx, account_id, body.model_dump(exclude_unset=True))


@router.get("/cashflow")
async def cashflow(
    ctx: ERPContext = Depends(get_erp_context),
    date_from: str | None = None,
    date_to: str | None = None,
    group_by: str = Query("day", pattern="^(day|week|month)$"),
):
    today = date.today()
    date_from = date_from or today.replace(day=1).isoformat()
    date_to = date_to or today.isoformat()
    return await service.cashflow(ctx, date_from=date_from, date_to=date_to, group_by=group_by)

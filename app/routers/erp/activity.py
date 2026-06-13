"""Activity endpoints. Thin: delegate to ActivityService."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.services.erp.activity import ActivityService
from app.services.erp.context import ERPContext, get_erp_context

router = APIRouter()
service = ActivityService()


@router.get("")
async def activity_feed(
    ctx: ERPContext = Depends(get_erp_context),
    actor: str | None = None,
    module: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    return await service.feed(
        ctx, actor=actor, module=module, date_from=date_from, date_to=date_to,
        limit=limit, offset=offset,
    )


@router.get("/ai")
async def ai_activity_feed(
    ctx: ERPContext = Depends(get_erp_context),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    return await service.ai_feed(ctx, limit=limit, offset=offset)

"""Clients endpoints. Thin: validate, delegate to ClientsService."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.models.erp_schemas import ClientCreate, ClientResponse, ClientUpdate
from app.services.erp.clients import ClientsService
from app.services.erp.context import ERPContext, get_erp_context

router = APIRouter()
service = ClientsService()


@router.get("", response_model=list[ClientResponse])
async def list_clients(
    ctx: ERPContext = Depends(get_erp_context),
    search: str | None = None,
    tag: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    return await service.list(ctx, search=search, tag=tag, limit=limit, offset=offset)


@router.post("", response_model=ClientResponse)
async def create_client(body: ClientCreate, ctx: ERPContext = Depends(get_erp_context)):
    return await service.create(ctx, body.model_dump(exclude_none=True))


@router.get("/phone/{phone}", response_model=ClientResponse)
async def get_by_phone(phone: str, ctx: ERPContext = Depends(get_erp_context)):
    return await service.get_by_phone(ctx, phone)


@router.get("/whatsapp/{wa_id}", response_model=ClientResponse)
async def get_by_whatsapp(wa_id: str, ctx: ERPContext = Depends(get_erp_context)):
    return await service.get_by_whatsapp(ctx, wa_id)


@router.get("/{client_id}")
async def get_client(client_id: str, ctx: ERPContext = Depends(get_erp_context)):
    return await service.get(ctx, client_id)


@router.put("/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: str, body: ClientUpdate, ctx: ERPContext = Depends(get_erp_context)
):
    return await service.update(ctx, client_id, body.model_dump(exclude_unset=True))

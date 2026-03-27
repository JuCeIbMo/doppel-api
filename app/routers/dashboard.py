import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import get_current_tenant
from app.models.schemas import (
    BotConfigResponse,
    BotConfigUpdateRequest,
    MessageResponse,
    PaginatedMessages,
    TenantResponse,
    WhatsAppAccountResponse,
)
from app.services.supabase_client import get_supabase

logger = logging.getLogger("doppel.dashboard")
router = APIRouter(prefix="/me")


@router.get("/tenant", response_model=TenantResponse)
async def get_tenant(tenant: dict = Depends(get_current_tenant)):
    return TenantResponse(**{k: str(v) if v is not None else v for k, v in tenant.items() if k in TenantResponse.model_fields})


@router.get("/whatsapp", response_model=list[WhatsAppAccountResponse])
async def get_whatsapp_accounts(tenant: dict = Depends(get_current_tenant)):
    result = (
        get_supabase()
        .table("whatsapp_accounts")
        .select("id, waba_id, phone_number_id, display_phone, status, created_at")
        .eq("tenant_id", tenant["id"])
        .execute()
    )
    return [WhatsAppAccountResponse(**{k: str(v) if v is not None else v for k, v in row.items()}) for row in result.data]


@router.get("/bot-config", response_model=BotConfigResponse)
async def get_bot_config(tenant: dict = Depends(get_current_tenant)):
    result = (
        get_supabase()
        .table("bot_configs")
        .select("id, system_prompt, welcome_message, language, ai_model")
        .eq("tenant_id", tenant["id"])
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot config no encontrado.")
    return BotConfigResponse(**result.data)


@router.put("/bot-config", response_model=BotConfigResponse)
async def update_bot_config(
    data: BotConfigUpdateRequest,
    tenant: dict = Depends(get_current_tenant),
):
    update_data = data.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No hay campos para actualizar.")

    supabase = get_supabase()
    result = (
        supabase.table("bot_configs")
        .update(update_data)
        .eq("tenant_id", tenant["id"])
        .select("id, system_prompt, welcome_message, language, ai_model")
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot config no encontrado.")
    return BotConfigResponse(**result.data[0])


@router.get("/messages", response_model=PaginatedMessages)
async def get_messages(
    tenant: dict = Depends(get_current_tenant),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    supabase = get_supabase()
    tenant_id = tenant["id"]

    count_result = (
        supabase.table("messages")
        .select("id", count="exact")
        .eq("tenant_id", tenant_id)
        .execute()
    )
    total = count_result.count or 0

    data_result = (
        supabase.table("messages")
        .select("id, user_phone, direction, content, message_type, created_at")
        .eq("tenant_id", tenant_id)
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )

    messages = [MessageResponse(**row) for row in data_result.data]
    return PaginatedMessages(messages=messages, total=total, limit=limit, offset=offset)


@router.delete("/whatsapp", status_code=status.HTTP_200_OK)
async def disconnect_whatsapp(tenant: dict = Depends(get_current_tenant)):
    supabase = get_supabase()
    connected = (
        supabase.table("whatsapp_accounts")
        .select("id")
        .eq("tenant_id", tenant["id"])
        .eq("status", "connected")
        .execute()
    )
    if not connected.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No tienes una cuenta de WhatsApp conectada.")

    supabase.table("whatsapp_accounts").update({
        "status": "disconnected",
        "webhook_active": False,
    }).eq("tenant_id", tenant["id"]).execute()

    logger.info("WhatsApp disconnected for tenant_id=%s", tenant["id"])
    return {"message": "WhatsApp desconectado exitosamente."}

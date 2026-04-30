import logging

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.dependencies import get_current_tenant
from app.models.schemas import (
    AdminPhonesResponse,
    AdminPhonesUpdateRequest,
    BotConfigResponse,
    BotConfigUpdateRequest,
    BusinessInfoResponse,
    BusinessInfoUpdateRequest,
    DeleteAccountResponse,
    MessageResponse,
    PaginatedMessages,
    ProductCreateRequest,
    ProductResponse,
    ProductUpdateRequest,
    TenantResponse,
    WhatsAppAccountResponse,
)
from app.services.manager_tools import normalize_phone
from app.services.supabase_client import get_supabase

logger = logging.getLogger("doppel.dashboard")
router = APIRouter(prefix="/me", tags=["Dashboard"])


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
        .select("id, system_prompt, welcome_message, language, ai_model, bot_enabled")
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
        .select("id, system_prompt, welcome_message, language, ai_model, bot_enabled")
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot config no encontrado.")
    return BotConfigResponse(**result.data[0])


@router.get("/admin-phones", response_model=AdminPhonesResponse)
async def get_admin_phones(tenant: dict = Depends(get_current_tenant)):
    """List the operator's admin WhatsApp numbers for this tenant."""
    result = (
        get_supabase()
        .table("bot_configs")
        .select("admin_phones")
        .eq("tenant_id", tenant["id"])
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot config no encontrado.")
    return AdminPhonesResponse(phones=list(result.data.get("admin_phones") or []))


@router.put("/admin-phones", response_model=AdminPhonesResponse)
async def update_admin_phones(
    data: AdminPhonesUpdateRequest,
    tenant: dict = Depends(get_current_tenant),
):
    """Replace the admin WhatsApp numbers list for this tenant.

    Each entry is normalized to digits only (matching the format Meta sends in
    webhooks). Empty entries are dropped, duplicates collapsed, order preserved.
    """
    cleaned: list[str] = []
    for raw in data.phones:
        digits = normalize_phone(raw)
        if digits and digits not in cleaned:
            cleaned.append(digits)

    supabase = get_supabase()
    result = (
        supabase.table("bot_configs")
        .update({"admin_phones": cleaned})
        .eq("tenant_id", tenant["id"])
        .select("admin_phones")
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot config no encontrado.")
    logger.info("Admin phones updated tenant=%s count=%s", tenant["id"], len(cleaned))
    return AdminPhonesResponse(phones=list(result.data[0].get("admin_phones") or []))


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
        "access_token_encrypted": "",
    }).eq("tenant_id", tenant["id"]).execute()

    supabase.table("bot_configs").update({
        "bot_enabled": False,
    }).eq("tenant_id", tenant["id"]).execute()

    logger.info("WhatsApp disconnected for tenant_id=%s", tenant["id"])
    return {
        "message": (
            "WhatsApp desconectado en Doppel. Se desactivaron los webhooks internos "
            "y las respuestas automáticas."
        )
    }


_BUSINESS_FIELDS = "id, name, description, hours, address, payment_methods"


def _serialize_business(row: dict) -> BusinessInfoResponse:
    return BusinessInfoResponse(
        id=str(row["id"]),
        name=row.get("name") or "",
        description=row.get("description") or "",
        hours=row.get("hours") or "",
        address=row.get("address") or "",
        payment_methods=row.get("payment_methods") or "",
    )


def _serialize_product(row: dict) -> ProductResponse:
    return ProductResponse(
        id=str(row["id"]),
        name=row["name"],
        description=row.get("description") or "",
        price=float(row["price"]) if row.get("price") is not None else None,
        available=bool(row.get("available", True)),
    )


@router.get("/business-info", response_model=BusinessInfoResponse)
async def get_business_info(tenant: dict = Depends(get_current_tenant)):
    """Return the tenant's business profile, autocreating an empty row if none exists."""
    supabase = get_supabase()
    existing = (
        supabase.table("business_info")
        .select(_BUSINESS_FIELDS)
        .eq("tenant_id", tenant["id"])
        .limit(1)
        .execute()
    )
    if existing.data:
        return _serialize_business(existing.data[0])

    created = (
        supabase.table("business_info")
        .insert({"tenant_id": tenant["id"]})
        .execute()
    )
    if not created.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo inicializar la informacion del negocio.",
        )
    return _serialize_business(created.data[0])


@router.put("/business-info", response_model=BusinessInfoResponse)
async def update_business_info(
    data: BusinessInfoUpdateRequest,
    tenant: dict = Depends(get_current_tenant),
):
    update_data = data.model_dump(exclude_none=True)
    supabase = get_supabase()

    existing = (
        supabase.table("business_info")
        .select("id")
        .eq("tenant_id", tenant["id"])
        .limit(1)
        .execute()
    )
    if existing.data:
        if not update_data:
            current = (
                supabase.table("business_info")
                .select(_BUSINESS_FIELDS)
                .eq("tenant_id", tenant["id"])
                .single()
                .execute()
            )
            return _serialize_business(current.data)
        result = (
            supabase.table("business_info")
            .update(update_data)
            .eq("tenant_id", tenant["id"])
            .execute()
        )
    else:
        payload = {"tenant_id": tenant["id"], **update_data}
        result = supabase.table("business_info").insert(payload).execute()

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo guardar la informacion del negocio.",
        )
    logger.info("Business info upserted tenant=%s", tenant["id"])
    return _serialize_business(result.data[0])


@router.get("/products", response_model=list[ProductResponse])
async def list_products(tenant: dict = Depends(get_current_tenant)):
    result = (
        get_supabase()
        .table("products")
        .select("id, name, description, price, available, created_at")
        .eq("tenant_id", tenant["id"])
        .order("created_at", desc=False)
        .execute()
    )
    return [_serialize_product(row) for row in result.data or []]


@router.post("/products", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    data: ProductCreateRequest,
    tenant: dict = Depends(get_current_tenant),
):
    payload = {
        "tenant_id": tenant["id"],
        "name": data.name.strip(),
        "description": data.description,
        "price": data.price,
        "available": data.available,
    }
    if not payload["name"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El nombre es obligatorio.")
    result = get_supabase().table("products").insert(payload).execute()
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo crear el producto.",
        )
    logger.info("Product created tenant=%s", tenant["id"])
    return _serialize_product(result.data[0])


@router.patch("/products/{product_id}", response_model=ProductResponse)
async def update_product(
    data: ProductUpdateRequest,
    product_id: str = Path(...),
    tenant: dict = Depends(get_current_tenant),
):
    update_data = data.model_dump(exclude_none=True)
    if "name" in update_data:
        update_data["name"] = update_data["name"].strip()
        if not update_data["name"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El nombre no puede estar vacio.")
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No hay campos para actualizar.")

    supabase = get_supabase()
    result = (
        supabase.table("products")
        .update(update_data)
        .eq("id", product_id)
        .eq("tenant_id", tenant["id"])
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Producto no encontrado.")
    return _serialize_product(result.data[0])


@router.delete("/products/{product_id}", status_code=status.HTTP_200_OK)
async def delete_product(
    product_id: str = Path(...),
    tenant: dict = Depends(get_current_tenant),
):
    supabase = get_supabase()
    result = (
        supabase.table("products")
        .delete()
        .eq("id", product_id)
        .eq("tenant_id", tenant["id"])
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Producto no encontrado.")
    return {"success": True, "id": product_id}


@router.delete("/account", response_model=DeleteAccountResponse)
async def delete_account(tenant: dict = Depends(get_current_tenant)):
    supabase = get_supabase()

    supabase.table("tenants").delete().eq("id", tenant["id"]).execute()
    logger.info("Account deleted for tenant_id=%s", tenant["id"])
    return DeleteAccountResponse(
        success=True,
        message="Cuenta y datos asociados eliminados de Doppel.",
    )

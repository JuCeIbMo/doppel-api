import logging

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from app.config import settings
from app.dependencies import get_current_user
from app.models.schemas import OAuthExchangeRequest, OAuthExchangeResponse
from app.security import encrypt_token
from app.services import meta_api
from app.services.supabase_client import get_supabase

logger = logging.getLogger("doppel.oauth")
router = APIRouter(tags=["OAuth"])


async def _run_smb_sync(phone_number_id: str, access_token: str) -> None:
    """Background task: trigger contact + history sync for coexistence numbers (must run within 24hs)."""
    async with httpx.AsyncClient() as client:
        for sync_type in ("smb_app_state_sync", "history"):
            try:
                await meta_api.trigger_smb_sync(
                    client, phone_number_id, access_token, sync_type, settings.META_API_VERSION
                )
                logger.info("SMB sync triggered: phone=%s type=%s", phone_number_id, sync_type)
            except Exception:
                logger.exception("SMB sync failed: phone=%s type=%s", phone_number_id, sync_type)


@router.post("/oauth/exchange", response_model=OAuthExchangeResponse)
async def oauth_exchange(
    request: Request,
    data: OAuthExchangeRequest,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user),
):
    """
    Receives the OAuth code from the frontend after Embedded Signup.
    Supports both standard (new number) and coexistence (existing Business App number) flows.
    """
    http: httpx.AsyncClient = request.app.state.http_client
    supabase = get_supabase()
    user_id = str(current_user.id)

    # Check if user already has a tenant
    existing_tenant = supabase.table("tenants").select("id").eq("user_id", user_id).execute()

    # 1. Exchange code for access token
    try:
        access_token = await meta_api.exchange_code_for_token(
            http, data.code, settings.META_APP_ID, settings.META_APP_SECRET, settings.META_API_VERSION
        )
    except httpx.HTTPStatusError as e:
        logger.error("Meta token exchange failed: %s", e.response.text)
        if e.response.status_code == 400:
            raise HTTPException(status_code=400, detail="Invalid authorization code")
        raise HTTPException(status_code=502, detail="Meta API error during token exchange")

    # 2. Get WABA details (business name)
    try:
        waba = await meta_api.get_waba_details(
            http, data.waba_id, access_token, settings.META_API_VERSION
        )
    except httpx.HTTPStatusError as e:
        logger.error("Failed to get WABA details: %s", e.response.text)
        raise HTTPException(status_code=502, detail="Meta API error fetching WABA details")

    business_name = waba.get("name", "Negocio sin nombre")

    # 3. Phone number: coexistence fetches from WABA, standard registers it
    display_phone = None
    if data.is_coexistence:
        try:
            phones = await meta_api.get_waba_phone_numbers(
                http, data.waba_id, access_token, settings.META_API_VERSION
            )
        except httpx.HTTPStatusError as e:
            logger.error("Failed to get WABA phone numbers: %s", e.response.text)
            raise HTTPException(status_code=502, detail="Meta API error fetching phone numbers")

        if not phones:
            raise HTTPException(status_code=422, detail="No hay números de teléfono asociados a esta WABA")

        phone_number_id = phones[0]["id"]
        display_phone = phones[0].get("display_phone_number")
        logger.info("Coexistence onboarding: waba=%s phone=%s", data.waba_id, phone_number_id)
    else:
        if not data.phone_number_id:
            raise HTTPException(status_code=422, detail="phone_number_id requerido para flujo estándar")
        phone_number_id = data.phone_number_id
        try:
            await meta_api.register_phone_number(
                http, phone_number_id, access_token, settings.WA_REGISTRATION_PIN, settings.META_API_VERSION
            )
        except httpx.HTTPStatusError as e:
            logger.error("Phone registration failed: %s", e.response.text)
            raise HTTPException(status_code=502, detail="Meta API error registering phone number")

    # 4. Subscribe app to WABA webhooks (standard)
    try:
        await meta_api.subscribe_app_to_waba(
            http, data.waba_id, access_token, settings.META_API_VERSION
        )
    except httpx.HTTPStatusError as e:
        logger.error("WABA subscription failed: %s", e.response.text)
        raise HTTPException(status_code=502, detail="Meta API error subscribing to WABA")

    # 5. Coexistence: subscribe additional webhook fields
    if data.is_coexistence:
        try:
            await meta_api.subscribe_coexistence_fields(
                http, data.waba_id, access_token, settings.META_API_VERSION
            )
        except Exception:
            logger.warning("Coexistence webhook fields subscription failed (non-fatal)")

    # 6. Encrypt token before storing
    encrypted_token = encrypt_token(access_token, settings.ENCRYPTION_KEY)

    # 7. Save to Supabase
    try:
        if existing_tenant.data:
            tenant_id = existing_tenant.data[0]["id"]

            connected = (
                supabase.table("whatsapp_accounts")
                .select("id")
                .eq("tenant_id", tenant_id)
                .eq("status", "connected")
                .execute()
            )
            if connected.data:
                raise HTTPException(status_code=409, detail="Ya tienes un WhatsApp activo conectado.")

            supabase.table("whatsapp_accounts").upsert({
                "tenant_id": tenant_id,
                "waba_id": data.waba_id,
                "phone_number_id": phone_number_id,
                "display_phone": display_phone,
                "access_token_encrypted": encrypted_token,
                "status": "connected",
                "webhook_active": True,
                "is_coexistence": data.is_coexistence,
            }, on_conflict="waba_id,phone_number_id").execute()

            logger.info("Tenant reconnected: tenant_id=%s waba_id=%s coexistence=%s", tenant_id, data.waba_id, data.is_coexistence)

        else:
            tenant_result = supabase.table("tenants").insert({
                "business_name": business_name,
                "user_id": user_id,
                "email": current_user.email,
            }).execute()
            tenant_id = tenant_result.data[0]["id"]

            supabase.table("whatsapp_accounts").insert({
                "tenant_id": tenant_id,
                "waba_id": data.waba_id,
                "phone_number_id": phone_number_id,
                "display_phone": display_phone,
                "access_token_encrypted": encrypted_token,
                "is_coexistence": data.is_coexistence,
            }).execute()

            supabase.table("bot_configs").insert({"tenant_id": tenant_id}).execute()

            logger.info("Tenant onboarded: tenant_id=%s waba_id=%s coexistence=%s", tenant_id, data.waba_id, data.is_coexistence)

    except HTTPException:
        raise
    except Exception:
        logger.exception("Database error during onboarding")
        raise HTTPException(status_code=500, detail="Database error")

    # 8. Coexistence: trigger smb sync in background (must complete within 24hs)
    if data.is_coexistence:
        background_tasks.add_task(_run_smb_sync, phone_number_id, access_token)

    return OAuthExchangeResponse(
        success=True,
        tenant_id=tenant_id,
        message="WhatsApp conectado exitosamente",
        display_phone=display_phone,
        business_name=business_name,
    )

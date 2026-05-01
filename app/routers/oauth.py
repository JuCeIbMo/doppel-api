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


def _update_account_status(supabase, tenant_id: str, waba_id: str, phone_number_id: str, status: str) -> None:
    try:
        supabase.table("whatsapp_accounts").update({"status": status}).eq(
            "tenant_id", tenant_id
        ).eq("waba_id", waba_id).eq("phone_number_id", phone_number_id).execute()
    except Exception:
        logger.exception("Failed to update whatsapp_accounts.status to %s", status)


@router.post("/oauth/exchange", response_model=OAuthExchangeResponse)
async def oauth_exchange(
    request: Request,
    data: OAuthExchangeRequest,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user),
):
    """Exchange Embedded Signup code and onboard/reconnect the tenant's WhatsApp account."""
    http: httpx.AsyncClient = request.app.state.http_client
    supabase = get_supabase()
    user_id = str(current_user.id)

    logger.info(
        "oauth/exchange start: user=%s waba=%s phone=%s coexistence=%s",
        user_id, data.waba_id, data.phone_number_id, data.is_coexistence,
    )

    # Existing tenant check (we will create lazily below if absent)
    existing_tenant = supabase.table("tenants").select("id").eq("user_id", user_id).execute()

    # --- 1. Exchange code for access token ---
    try:
        access_token = await meta_api.exchange_code_for_token(
            http, data.code, settings.META_APP_ID, settings.META_APP_SECRET, settings.META_API_VERSION
        )
        logger.info("step 1/7 token exchange ok")
    except httpx.HTTPStatusError as e:
        detail = meta_api.meta_error_detail(e.response)
        logger.error("step 1/7 token exchange failed: %s", detail)
        status_code = 400 if e.response.status_code == 400 else 502
        raise HTTPException(status_code=status_code, detail=f"Meta token exchange: {detail}")

    # --- 2. Encrypt the token NOW, before any Meta mutation ---
    # Startup validated ENCRYPTION_KEY; this is just a defensive second line.
    try:
        encrypted_token = encrypt_token(access_token, settings.ENCRYPTION_KEY)
        logger.info("step 2/7 token encrypted ok")
    except Exception:
        logger.exception("step 2/7 encryption failed")
        raise HTTPException(
            status_code=500,
            detail="Error de cifrado en el servidor. Contacta soporte (ENCRYPTION_KEY).",
        )

    # --- 3. Get WABA details ---
    try:
        waba = await meta_api.get_waba_details(
            http, data.waba_id, access_token, settings.META_API_VERSION
        )
        logger.info("step 3/7 WABA details ok: name=%s", waba.get("name"))
    except httpx.HTTPStatusError as e:
        detail = meta_api.meta_error_detail(e.response)
        logger.error("step 3/7 WABA details failed: %s", detail)
        raise HTTPException(status_code=502, detail=f"Meta WABA details: {detail}")

    business_name = waba.get("name", "Negocio sin nombre")

    # --- 4. Resolve phone_number_id (coexistence fetches it, standard supplies it) ---
    display_phone: str | None = None
    if data.is_coexistence:
        try:
            phones = await meta_api.get_waba_phone_numbers(
                http, data.waba_id, access_token, settings.META_API_VERSION
            )
        except httpx.HTTPStatusError as e:
            detail = meta_api.meta_error_detail(e.response)
            logger.error("step 4/7 WABA phones failed: %s", detail)
            raise HTTPException(status_code=502, detail=f"Meta WABA phones: {detail}")
        if not phones:
            raise HTTPException(status_code=422, detail="No hay números de teléfono asociados a esta WABA")
        phone_number_id = phones[0]["id"]
        display_phone = phones[0].get("display_phone_number")
        logger.info("step 4/7 coexistence phone resolved: %s (%s)", phone_number_id, display_phone)
    else:
        if not data.phone_number_id:
            raise HTTPException(status_code=422, detail="phone_number_id requerido para flujo estándar")
        phone_number_id = data.phone_number_id
        logger.info("step 4/7 standard phone: %s", phone_number_id)

    # --- 5. Upsert tenant + whatsapp_account with status='pending' ---
    # This gives us a durable record BEFORE any Meta mutation, so retries can pick up where they left off.
    try:
        if existing_tenant.data:
            tenant_id = existing_tenant.data[0]["id"]

            # Block if user already has a DIFFERENT number fully connected.
            connected = (
                supabase.table("whatsapp_accounts")
                .select("id, waba_id, phone_number_id")
                .eq("tenant_id", tenant_id)
                .eq("status", "connected")
                .execute()
            )
            conflicting = [
                r for r in (connected.data or [])
                if r["waba_id"] != data.waba_id or r["phone_number_id"] != phone_number_id
            ]
            if conflicting:
                raise HTTPException(status_code=409, detail="Ya tienes un WhatsApp activo conectado.")
        else:
            tenant_result = supabase.table("tenants").insert({
                "business_name": business_name,
                "user_id": user_id,
                "email": current_user.email,
            }).execute()
            tenant_id = tenant_result.data[0]["id"]
            supabase.table("bot_configs").insert({
                "tenant_id": tenant_id,
                "bot_enabled": False,
                "admin_phones": [],
            }).execute()
            logger.info("tenant created: id=%s name=%s", tenant_id, business_name)

        supabase.table("whatsapp_accounts").upsert({
            "tenant_id": tenant_id,
            "waba_id": data.waba_id,
            "phone_number_id": phone_number_id,
            "display_phone": display_phone,
            "access_token_encrypted": encrypted_token,
            "status": "pending",
            "webhook_active": False,
            "is_coexistence": data.is_coexistence,
        }, on_conflict="waba_id,phone_number_id").execute()
        logger.info("step 5/7 whatsapp_account upserted: tenant=%s status=pending", tenant_id)
    except HTTPException:
        raise
    except Exception:
        logger.exception("step 5/7 database upsert failed")
        raise HTTPException(status_code=500, detail="Error de base de datos guardando el estado inicial.")

    # --- 6. Register phone number (standard flow only) ---
    if not data.is_coexistence:
        try:
            await meta_api.register_phone_number(
                http, phone_number_id, access_token, settings.WA_REGISTRATION_PIN, settings.META_API_VERSION
            )
            logger.info("step 6/7 phone registered: %s", phone_number_id)
        except httpx.HTTPStatusError as e:
            if meta_api.is_already_registered(e.response):
                logger.info("step 6/7 phone already registered, treating as retry: %s", phone_number_id)
            else:
                detail = meta_api.meta_error_detail(e.response)
                logger.error("step 6/7 phone registration failed: %s", detail)
                raise HTTPException(status_code=502, detail=f"Meta phone register: {detail}")
    else:
        logger.info("step 6/7 skipped (coexistence)")

    _update_account_status(supabase, tenant_id, data.waba_id, phone_number_id, "meta_registered")

    # --- 7. Subscribe app to WABA webhooks ---
    try:
        await meta_api.subscribe_app_to_waba(
            http, data.waba_id, access_token, settings.META_API_VERSION
        )
        logger.info("step 7/7 app subscribed to WABA: %s", data.waba_id)
    except httpx.HTTPStatusError as e:
        if meta_api.is_already_subscribed(e.response):
            logger.info("step 7/7 app already subscribed, treating as retry: %s", data.waba_id)
        else:
            detail = meta_api.meta_error_detail(e.response)
            logger.error("step 7/7 WABA subscription failed: %s", detail)
            raise HTTPException(status_code=502, detail=f"Meta WABA subscribe: {detail}")

    # Coexistence: subscribe additional webhook fields (non-fatal)
    if data.is_coexistence:
        try:
            await meta_api.subscribe_coexistence_fields(
                http, data.waba_id, access_token, settings.META_API_VERSION
            )
        except httpx.HTTPStatusError as e:
            logger.warning(
                "coexistence webhook fields subscription failed (non-fatal): %s",
                meta_api.meta_error_detail(e.response),
            )

    # Mark as fully connected
    try:
        supabase.table("whatsapp_accounts").update({
            "status": "connected",
            "webhook_active": True,
        }).eq("tenant_id", tenant_id).eq("waba_id", data.waba_id).eq(
            "phone_number_id", phone_number_id
        ).execute()
    except Exception:
        logger.exception("final status=connected update failed (Meta is ok, DB flag lag)")
        raise HTTPException(status_code=500, detail="Onboarding OK en Meta pero falló el marcado final. Reintenta.")

    logger.info("oauth/exchange success: tenant=%s waba=%s phone=%s", tenant_id, data.waba_id, phone_number_id)

    # Coexistence: trigger smb sync in background (must complete within 24hs)
    if data.is_coexistence:
        background_tasks.add_task(_run_smb_sync, phone_number_id, access_token)

    config_result = (
        supabase.table("bot_configs")
        .select("admin_phones")
        .eq("tenant_id", tenant_id)
        .single()
        .execute()
    )
    requires_manager_setup = not bool((config_result.data or {}).get("admin_phones") or [])

    return OAuthExchangeResponse(
        success=True,
        tenant_id=tenant_id,
        message="WhatsApp conectado exitosamente",
        display_phone=display_phone,
        business_name=business_name,
        requires_manager_setup=requires_manager_setup,
    )

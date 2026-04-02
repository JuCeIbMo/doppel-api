import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

from app.config import settings
from app.dependencies import get_current_user
from app.models.schemas import OAuthExchangeRequest, OAuthExchangeResponse
from app.security import encrypt_token
from app.services import meta_api
from app.services.supabase_client import get_supabase

logger = logging.getLogger("doppel.oauth")
router = APIRouter(tags=["OAuth"])


@router.post("/oauth/exchange", response_model=OAuthExchangeResponse)
async def oauth_exchange(
    request: Request,
    data: OAuthExchangeRequest,
    current_user=Depends(get_current_user),
):
    """
    Receives the OAuth code from the frontend after Embedded Signup.
    Exchanges it for an access token and onboards the tenant.
    Supports reconnection if the user previously disconnected their WhatsApp.
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

    # 3. Register phone number for Cloud API
    try:
        await meta_api.register_phone_number(
            http, data.phone_number_id, access_token, settings.WA_REGISTRATION_PIN, settings.META_API_VERSION
        )
    except httpx.HTTPStatusError as e:
        logger.error("Phone registration failed: %s", e.response.text)
        raise HTTPException(status_code=502, detail="Meta API error registering phone number")

    # 4. Subscribe app to WABA to receive webhook events
    try:
        await meta_api.subscribe_app_to_waba(
            http, data.waba_id, access_token, settings.META_API_VERSION
        )
    except httpx.HTTPStatusError as e:
        logger.error("WABA subscription failed: %s", e.response.text)
        raise HTTPException(status_code=502, detail="Meta API error subscribing to WABA")

    # 5. Encrypt token before storing
    encrypted_token = encrypt_token(access_token, settings.ENCRYPTION_KEY)

    # 6. Save to Supabase
    try:
        if existing_tenant.data:
            # User already has a tenant — reconnect (upsert WhatsApp account)
            tenant_id = existing_tenant.data[0]["id"]

            # Check if there's already a connected account for this WABA
            connected = (
                supabase.table("whatsapp_accounts")
                .select("id")
                .eq("tenant_id", tenant_id)
                .eq("status", "connected")
                .execute()
            )
            if connected.data:
                raise HTTPException(status_code=409, detail="Ya tienes un WhatsApp activo conectado.")

            # Reactivate (upsert by waba_id + phone_number_id)
            supabase.table("whatsapp_accounts").upsert({
                "tenant_id": tenant_id,
                "waba_id": data.waba_id,
                "phone_number_id": data.phone_number_id,
                "access_token_encrypted": encrypted_token,
                "status": "connected",
                "webhook_active": True,
            }, on_conflict="waba_id,phone_number_id").execute()

            logger.info("Tenant reconnected: tenant_id=%s waba_id=%s", tenant_id, data.waba_id)

        else:
            # New user — create tenant, WhatsApp account, and default bot config
            tenant_result = supabase.table("tenants").insert({
                "business_name": business_name,
                "user_id": user_id,
                "email": current_user.email,
            }).execute()
            tenant_id = tenant_result.data[0]["id"]

            supabase.table("whatsapp_accounts").insert({
                "tenant_id": tenant_id,
                "waba_id": data.waba_id,
                "phone_number_id": data.phone_number_id,
                "access_token_encrypted": encrypted_token,
            }).execute()

            supabase.table("bot_configs").insert({
                "tenant_id": tenant_id,
            }).execute()

            logger.info("Tenant onboarded: tenant_id=%s waba_id=%s", tenant_id, data.waba_id)

    except HTTPException:
        raise
    except Exception:
        logger.exception("Database error during onboarding")
        raise HTTPException(status_code=500, detail="Database error")

    return OAuthExchangeResponse(
        success=True,
        tenant_id=tenant_id,
        message="WhatsApp conectado exitosamente",
    )

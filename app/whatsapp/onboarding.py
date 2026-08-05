"""Application service for WhatsApp Embedded Signup onboarding."""

import logging
from dataclasses import dataclass

import httpx

from app.config import settings
from app.security import encrypt_token
from app.services.supabase_client import get_supabase
from app.whatsapp import meta

logger = logging.getLogger("doppel.whatsapp.onboarding")


class OnboardingError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


@dataclass(slots=True)
class SmbSyncTask:
    phone_number_id: str
    access_token: str


@dataclass(slots=True)
class OnboardingResult:
    tenant_id: str
    business_name: str
    display_phone: str | None
    requires_manager_setup: bool
    sync_task: SmbSyncTask | None = None


async def run_smb_sync(phone_number_id: str, access_token: str) -> None:
    """Trigger the two best-effort coexistence sync jobs required by Meta."""
    async with httpx.AsyncClient() as client:
        for sync_type in ("smb_app_state_sync", "history"):
            try:
                await meta.trigger_smb_sync(
                    client,
                    phone_number_id,
                    access_token,
                    sync_type,
                    settings.META_API_VERSION,
                )
                logger.info("SMB sync triggered: phone=%s type=%s", phone_number_id, sync_type)
            except Exception:
                logger.exception("SMB sync failed: phone=%s type=%s", phone_number_id, sync_type)


async def _exchange_token(http: httpx.AsyncClient, code: str) -> str:
    try:
        return await meta.exchange_code_for_token(
            http,
            code,
            settings.META_APP_ID,
            settings.META_APP_SECRET,
            settings.META_API_VERSION,
        )
    except httpx.HTTPStatusError as exc:
        detail = meta.meta_error_detail(exc.response)
        status_code = 400 if exc.response.status_code == 400 else 502
        raise OnboardingError(status_code, f"Meta token exchange: {detail}") from exc


def _encrypt_access_token(access_token: str) -> str:
    try:
        return encrypt_token(access_token, settings.ENCRYPTION_KEY)
    except Exception as exc:
        logger.exception("WhatsApp onboarding token encryption failed")
        raise OnboardingError(
            500,
            "Error de cifrado en el servidor. Contacta soporte (ENCRYPTION_KEY).",
        ) from exc


async def _get_business_name(
    http: httpx.AsyncClient, waba_id: str, access_token: str,
) -> str:
    try:
        waba = await meta.get_waba_details(
            http, waba_id, access_token, settings.META_API_VERSION,
        )
    except httpx.HTTPStatusError as exc:
        detail = meta.meta_error_detail(exc.response)
        raise OnboardingError(502, f"Meta WABA details: {detail}") from exc
    return waba.get("name", "Negocio sin nombre")


async def _resolve_phone(
    http: httpx.AsyncClient,
    *,
    waba_id: str,
    access_token: str,
    supplied_phone_id: str | None,
    is_coexistence: bool,
) -> tuple[str, str | None]:
    if not is_coexistence:
        if not supplied_phone_id:
            raise OnboardingError(422, "phone_number_id requerido para flujo estándar")
        return supplied_phone_id, None

    try:
        phones = await meta.get_waba_phone_numbers(
            http, waba_id, access_token, settings.META_API_VERSION,
        )
    except httpx.HTTPStatusError as exc:
        detail = meta.meta_error_detail(exc.response)
        raise OnboardingError(502, f"Meta WABA phones: {detail}") from exc
    if not phones:
        raise OnboardingError(422, "No hay números de teléfono asociados a esta WABA")
    return phones[0]["id"], phones[0].get("display_phone_number")


async def _persist_pending_account(
    supabase,
    *,
    existing_tenant,
    user_id: str,
    user_email: str | None,
    business_name: str,
    waba_id: str,
    phone_number_id: str,
    display_phone: str | None,
    encrypted_token: str,
    is_coexistence: bool,
) -> str:
    try:
        if existing_tenant.data:
            tenant_id = existing_tenant.data[0]["id"]
            connected = (
                await supabase.table("whatsapp_accounts")
                .select("id, waba_id, phone_number_id")
                .eq("tenant_id", tenant_id)
                .eq("status", "connected")
                .execute()
            )
            conflicts = [
                row for row in (connected.data or [])
                if row["waba_id"] != waba_id or row["phone_number_id"] != phone_number_id
            ]
            if conflicts:
                raise OnboardingError(409, "Ya tienes un WhatsApp activo conectado.")
        else:
            tenant_result = await supabase.table("tenants").insert({
                "business_name": business_name,
                "user_id": user_id,
                "email": user_email,
            }).execute()
            tenant_id = tenant_result.data[0]["id"]
            await supabase.table("bot_configs").insert({
                "tenant_id": tenant_id,
                "bot_enabled": False,
                "admin_phones": [],
            }).execute()

        await supabase.table("whatsapp_accounts").upsert({
            "tenant_id": tenant_id,
            "waba_id": waba_id,
            "phone_number_id": phone_number_id,
            "display_phone": display_phone,
            "access_token_encrypted": encrypted_token,
            "status": "pending",
            "webhook_active": False,
            "is_coexistence": is_coexistence,
        }, on_conflict="waba_id,phone_number_id").execute()
        return tenant_id
    except OnboardingError:
        raise
    except Exception as exc:
        logger.exception("WhatsApp onboarding database upsert failed")
        raise OnboardingError(
            500, "Error de base de datos guardando el estado inicial.",
        ) from exc


async def _register_phone(
    http: httpx.AsyncClient,
    *,
    phone_number_id: str,
    access_token: str,
    is_coexistence: bool,
) -> None:
    if is_coexistence:
        return
    try:
        await meta.register_phone_number(
            http,
            phone_number_id,
            access_token,
            settings.WA_REGISTRATION_PIN,
            settings.META_API_VERSION,
        )
    except httpx.HTTPStatusError as exc:
        if not meta.is_already_registered(exc.response):
            detail = meta.meta_error_detail(exc.response)
            raise OnboardingError(502, f"Meta phone register: {detail}") from exc


async def _update_account_status(
    supabase, tenant_id: str, waba_id: str, phone_number_id: str, status: str,
) -> None:
    try:
        await supabase.table("whatsapp_accounts").update({"status": status}).eq(
            "tenant_id", tenant_id,
        ).eq("waba_id", waba_id).eq("phone_number_id", phone_number_id).execute()
    except Exception:
        logger.exception("Failed to update whatsapp_accounts.status to %s", status)


async def _subscribe_webhooks(
    http: httpx.AsyncClient,
    *,
    waba_id: str,
    access_token: str,
    is_coexistence: bool,
) -> None:
    try:
        await meta.subscribe_app_to_waba(
            http, waba_id, access_token, settings.META_API_VERSION,
        )
    except httpx.HTTPStatusError as exc:
        if not meta.is_already_subscribed(exc.response):
            detail = meta.meta_error_detail(exc.response)
            raise OnboardingError(502, f"Meta WABA subscribe: {detail}") from exc

    if is_coexistence:
        try:
            await meta.subscribe_coexistence_fields(
                http, waba_id, access_token, settings.META_API_VERSION,
            )
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "coexistence webhook fields subscription failed (non-fatal): %s",
                meta.meta_error_detail(exc.response),
            )


async def _mark_connected(
    supabase, *, tenant_id: str, waba_id: str, phone_number_id: str,
) -> None:
    try:
        await supabase.table("whatsapp_accounts").update({
            "status": "connected",
            "webhook_active": True,
        }).eq("tenant_id", tenant_id).eq("waba_id", waba_id).eq(
            "phone_number_id", phone_number_id,
        ).execute()
    except Exception as exc:
        logger.exception("final status=connected update failed (Meta is ok, DB flag lag)")
        raise OnboardingError(
            500, "Onboarding OK en Meta pero falló el marcado final. Reintenta.",
        ) from exc


async def onboard_whatsapp(
    http: httpx.AsyncClient,
    *,
    code: str,
    waba_id: str,
    supplied_phone_id: str | None,
    is_coexistence: bool,
    user_id: str,
    user_email: str | None,
) -> OnboardingResult:
    """Run the complete, retry-safe onboarding workflow."""
    supabase = get_supabase()
    existing_tenant = (
        await supabase.table("tenants").select("id").eq("user_id", user_id).execute()
    )
    access_token = await _exchange_token(http, code)
    encrypted_token = _encrypt_access_token(access_token)
    business_name = await _get_business_name(http, waba_id, access_token)
    phone_number_id, display_phone = await _resolve_phone(
        http,
        waba_id=waba_id,
        access_token=access_token,
        supplied_phone_id=supplied_phone_id,
        is_coexistence=is_coexistence,
    )
    tenant_id = await _persist_pending_account(
        supabase,
        existing_tenant=existing_tenant,
        user_id=user_id,
        user_email=user_email,
        business_name=business_name,
        waba_id=waba_id,
        phone_number_id=phone_number_id,
        display_phone=display_phone,
        encrypted_token=encrypted_token,
        is_coexistence=is_coexistence,
    )
    await _register_phone(
        http,
        phone_number_id=phone_number_id,
        access_token=access_token,
        is_coexistence=is_coexistence,
    )
    await _update_account_status(
        supabase, tenant_id, waba_id, phone_number_id, "meta_registered",
    )
    await _subscribe_webhooks(
        http,
        waba_id=waba_id,
        access_token=access_token,
        is_coexistence=is_coexistence,
    )
    await _mark_connected(
        supabase,
        tenant_id=tenant_id,
        waba_id=waba_id,
        phone_number_id=phone_number_id,
    )
    config_result = (
        await supabase.table("bot_configs")
        .select("admin_phones")
        .eq("tenant_id", tenant_id)
        .single()
        .execute()
    )
    return OnboardingResult(
        tenant_id=tenant_id,
        business_name=business_name,
        display_phone=display_phone,
        requires_manager_setup=not bool((config_result.data or {}).get("admin_phones") or []),
        sync_task=(
            SmbSyncTask(phone_number_id, access_token) if is_coexistence else None
        ),
    )

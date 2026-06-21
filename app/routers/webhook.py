import json
import logging
import tempfile
import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter, BackgroundTasks, Query, Request
from fastapi.responses import PlainTextResponse, Response

from app.config import settings
from app.security import decrypt_token, verify_webhook_signature
from app.ai import respond as ai_respond
from app.services import meta_api
from app.services.phone import normalize_phone
from app.services.supabase_client import get_supabase

logger = logging.getLogger("doppel.webhook")
router = APIRouter(tags=["Webhook"])
_MEDIA_MESSAGE_TYPES = {"image", "audio", "voice", "document"}


@router.get("/webhook/whatsapp")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """Meta calls this GET to verify the webhook URL is ours."""
    if hub_mode == "subscribe" and hub_verify_token == settings.META_VERIFY_TOKEN:
        return PlainTextResponse(content=hub_challenge)
    return Response(status_code=403)


@router.post("/webhook/whatsapp")
async def receive_webhook(request: Request, background_tasks: BackgroundTasks):
    """Receive inbound messages from Meta. Always returns 200."""
    try:
        body = await request.body()

        # Validate Meta's HMAC signature before processing anything
        signature = request.headers.get("X-Hub-Signature-256", "")
        if not verify_webhook_signature(body, signature, settings.META_APP_SECRET):
            logger.warning("Rejected webhook: invalid signature")
            return Response(status_code=200)

        payload = json.loads(body)
        supabase = get_supabase()

        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                metadata = value.get("metadata", {})
                phone_number_id = metadata.get("phone_number_id")
                messages = value.get("messages", [])
                statuses = value.get("statuses", [])

                if phone_number_id and statuses:
                    _log_whatsapp_statuses(phone_number_id, statuses)

                if not phone_number_id or not messages:
                    continue

                # Find active tenant account by phone_number_id (ignore disconnected accounts)
                result = (
                    supabase.table("whatsapp_accounts")
                    .select("id, tenant_id")
                    .eq("phone_number_id", phone_number_id)
                    .eq("status", "connected")
                    .maybe_single()
                    .execute()
                )
                account = None if result is None else result.data
                if not account:
                    logger.info(
                        "Webhook de phone_number_id no registrado, ignorando phone_number_id=%s",
                        phone_number_id,
                    )
                    continue

                config_result = (
                    supabase.table("bot_configs")
                    .select("admin_phones, bot_enabled")
                    .eq("tenant_id", account["tenant_id"])
                    .single()
                    .execute()
                )
                config = config_result.data or {}
                admin_phones = config.get("admin_phones") or []

                # Save each inbound message and schedule bot response
                for msg in messages:
                    wa_message_id = msg.get("id")
                    if wa_message_id:
                        existing_message = (
                            supabase.table("messages")
                            .select("id")
                            .eq("wa_message_id", wa_message_id)
                            .limit(1)
                            .execute()
                        )
                        if existing_message.data:
                            logger.info("Skipping duplicate webhook message_id=%s", wa_message_id)
                            continue

                    msg_type = msg.get("type", "text")
                    content, media = _extract_message_content_and_media(msg)
                    user_phone = normalize_phone(msg.get("from")) or msg.get("from")
                    mode = "manager" if user_phone in admin_phones else "client"

                    supabase.table("messages").insert({
                        "tenant_id": account["tenant_id"],
                        "wa_account_id": account["id"],
                        "user_phone": user_phone,
                        "direction": "inbound",
                        "content": content,
                        "message_type": msg_type,
                        "wa_message_id": wa_message_id,
                        "media": media,
                        "agent_mode": mode,
                    }).execute()

                    logger.info(
                        "Saved message from=%s phone_id=%s type=%s",
                        user_phone, phone_number_id, msg_type,
                    )

                    should_process = bool(settings.AI_CORE_URL and (content or media))
                    if mode == "client" and not config.get("bot_enabled", True):
                        should_process = False

                    # Schedule bot response through ai-core. Manager bypasses bot_enabled.
                    if should_process:
                        background_tasks.add_task(
                            _process_bot_response,
                            request.app.state.http_client,
                            account["tenant_id"],
                            account["id"],
                            user_phone,
                            content or "",
                            mode,
                            wa_message_id,
                            media,
                        )

    except Exception:
        logger.exception("Error processing webhook")

    # Always return 200 — Meta retries if it doesn't get 200
    return Response(status_code=200)


def _log_whatsapp_statuses(phone_number_id: str, statuses: list[dict]) -> None:
    for status_event in statuses:
        errors = status_event.get("errors") or []
        error = errors[0] if errors else {}
        logger.info(
            "WhatsApp status phone_id=%s message_id=%s recipient=%s status=%s error_code=%s error_message=%s",
            phone_number_id,
            status_event.get("id"),
            status_event.get("recipient_id"),
            status_event.get("status"),
            error.get("code"),
            error.get("message") or error.get("title"),
        )


def _extract_message_content_and_media(msg: dict) -> tuple[str | None, list[dict]]:
    msg_type = msg.get("type", "text")
    if msg_type == "text":
        return msg.get("text", {}).get("body"), []

    if msg_type not in _MEDIA_MESSAGE_TYPES:
        return None, []

    payload = msg.get(msg_type) or {}
    media_id = payload.get("id")
    media = []
    if media_id:
        media.append(
            {
                "id": media_id,
                "type": msg_type,
                "mime_type": payload.get("mime_type"),
                "sha256": payload.get("sha256"),
                "filename": payload.get("filename"),
            }
        )
    return payload.get("caption") or f"[{msg_type} message]", media


def _media_download_path(*, tenant_id: str, media_item: dict) -> Path:
    suffix = ""
    filename = media_item.get("filename")
    if filename:
        suffix = Path(str(filename)).suffix
    if not suffix:
        suffix = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "audio/ogg": ".ogg",
            "audio/mpeg": ".mp3",
            "application/pdf": ".pdf",
        }.get(str(media_item.get("mime_type") or ""), "")
    return (
        Path(tempfile.gettempdir())
        / "doppel-whatsapp-media"
        / tenant_id
        / f"{uuid.uuid4().hex}{suffix}"
    )


async def _download_media_files(
    http_client: httpx.AsyncClient,
    *,
    tenant_id: str,
    token: str,
    media: list[dict] | None,
) -> list[str]:
    paths: list[str] = []
    for item in media or []:
        media_id = item.get("id")
        if not media_id:
            continue
        downloaded = await meta_api.download_media_to_path(
            http_client,
            str(media_id),
            token,
            settings.META_API_VERSION,
            _media_download_path(tenant_id=tenant_id, media_item=item),
        )
        item.update(
            {
                "local_path": downloaded["path"],
                "downloaded_mime_type": downloaded.get("mime_type"),
                "size": downloaded.get("size"),
            }
        )
        paths.append(downloaded["path"])
    return paths


async def _process_bot_response(
    http_client: httpx.AsyncClient,
    tenant_id: str,
    wa_account_id: str,
    user_phone: str,
    inbound_text: str,
    mode: str,
    inbound_message_id: str | None,
    media: list[dict] | None = None,
) -> None:
    """Generate AI response and send it via WhatsApp. Runs as a background task."""
    logger.debug(
        "[BOT_START] tenant=%s phone=%s mode=%s msg_id=%s media_count=%d",
        tenant_id, user_phone, mode, inbound_message_id, len(media or []),
    )
    try:
        supabase = get_supabase()

        # Get bot config (incl. manager fields added in migration_v4)
        config_result = (
            supabase.table("bot_configs")
            .select("bot_enabled, admin_phones, system_prompt, manager_prompt, ai_model")
            .eq("tenant_id", tenant_id)
            .single()
            .execute()
        )
        if not config_result.data:
            logger.warning("No bot config for tenant_id=%s", tenant_id)
            return

        config = config_result.data
        is_manager = mode == "manager"

        logger.debug(
            "[BOT_CONFIG] tenant=%s bot_enabled=%s ai_model=%s is_manager=%s",
            tenant_id, config.get("bot_enabled"), config.get("ai_model"), is_manager,
        )

        # Manager bypasses bot_enabled — operator can talk even when client bot is paused.
        if not is_manager and not config.get("bot_enabled", True):
            logger.info("Bot disabled for tenant_id=%s", tenant_id)
            return

        # Get WhatsApp account (need phone_number_id and encrypted token)
        wa_result = (
            supabase.table("whatsapp_accounts")
            .select("phone_number_id, access_token_encrypted")
            .eq("id", wa_account_id)
            .eq("status", "connected")
            .single()
            .execute()
        )
        if not wa_result.data:
            logger.warning("[BOT_ABORT] wa_account no encontrado wa_account_id=%s", wa_account_id)
            return

        wa_account = wa_result.data
        access_token = decrypt_token(wa_account["access_token_encrypted"], settings.ENCRYPTION_KEY)
        logger.debug("[BOT_MEDIA] descargando %d archivos tenant=%s", len(media or []), tenant_id)
        await _download_media_files(
            http_client,
            tenant_id=tenant_id,
            token=access_token,
            media=media,
        )

        # Conversation history is owned by the ai-core (Agno) per-user session in
        # its own Postgres; the API no longer loads/sends it. Supabase `messages`
        # remains the inbound/outbound log for the dashboard.
        system_prompt = _select_system_prompt(config=config, mode=mode)

        ai_response = await ai_respond(
            mode=mode,
            tenant_id=tenant_id,
            user_phone=user_phone,
            content=inbound_text,
            system_prompt=system_prompt,
            model=str(config.get("ai_model") or "claude-sonnet-4-20250514"),
            wa_access_token=access_token,
            wa_phone_number_id=wa_account["phone_number_id"],
            media=media,
        )
        if ai_response is None:
            logger.error(
                "[BOT_CRASH] agente falló internamente tenant=%s phone=%s mode=%s",
                tenant_id, user_phone, mode,
            )
            return
        ai_text = ai_response.strip()
        if not ai_text:
            logger.warning(
                "Empty agent response tenant=%s phone=%s mode=%s",
                tenant_id, user_phone, mode,
            )
            return

        logger.debug(
            "[BOT_SEND] tenant=%s phone=%s chars=%d respuesta=%r",
            tenant_id, user_phone, len(ai_text), ai_text[:120],
        )
        wa_msg_id = await meta_api.send_whatsapp_message(
            http_client,
            wa_account["phone_number_id"],
            user_phone,
            ai_text,
            access_token,
            settings.META_API_VERSION,
        )

        # Save outbound message
        supabase.table("messages").insert({
            "tenant_id": tenant_id,
            "wa_account_id": wa_account_id,
            "user_phone": user_phone,
            "direction": "outbound",
            "content": ai_text,
            "message_type": "text",
            "wa_message_id": wa_msg_id,
            "media": [],
            "agent_mode": mode,
        }).execute()

        logger.info(
            "[BOT_OK] tenant=%s phone=%s mode=%s wa_msg_id=%s",
            tenant_id, user_phone, mode, wa_msg_id,
        )

    except Exception:
        logger.exception("Bot response failed for tenant=%s phone=%s", tenant_id, user_phone)


def _select_system_prompt(*, config: dict, mode: str) -> str:
    if mode == "manager" and config.get("manager_prompt"):
        return str(config["manager_prompt"])
    return str(config.get("system_prompt") or "")

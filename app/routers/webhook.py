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
from app.services import meta_api, nanobot_runtime
from app.services.manager_tools import normalize_phone
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

                if not phone_number_id or not messages:
                    continue

                # Find active tenant account by phone_number_id (ignore disconnected accounts)
                result = (
                    supabase.table("whatsapp_accounts")
                    .select("id, tenant_id")
                    .eq("phone_number_id", phone_number_id)
                    .eq("status", "connected")
                    .single()
                    .execute()
                )
                account = result.data
                if not account:
                    logger.warning("No active account found for phone_number_id=%s", phone_number_id)
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

                    should_process = bool(settings.NANOBOT_RUNTIME_URL and (content or media))
                    if mode == "client" and not config.get("bot_enabled", True):
                        should_process = False

                    # Schedule bot response through nanobot. Manager bypasses bot_enabled.
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
    try:
        supabase = get_supabase()

        # Get bot config (incl. manager fields added in migration_v4)
        config_result = (
            supabase.table("bot_configs")
            .select("bot_enabled, admin_phones")
            .eq("tenant_id", tenant_id)
            .single()
            .execute()
        )
        if not config_result.data:
            logger.warning("No bot config for tenant_id=%s", tenant_id)
            return

        config = config_result.data
        is_manager = mode == "manager"

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
            return

        wa_account = wa_result.data
        access_token = decrypt_token(wa_account["access_token_encrypted"], settings.ENCRYPTION_KEY)
        media_paths = await _download_media_files(
            http_client,
            tenant_id=tenant_id,
            token=access_token,
            media=media,
        )

        result = await nanobot_runtime.respond(
            http_client,
            tenant_id=tenant_id,
            mode=mode,
            sender_id=user_phone,
            chat_id=user_phone,
            message_id=inbound_message_id,
            content=inbound_text,
            media_paths=media_paths,
        )
        ai_text = str(result.get("reply") or "").strip()
        if not ai_text:
            logger.warning(
                "Empty agent response tenant=%s phone=%s mode=%s",
                tenant_id, user_phone, mode,
            )
            return

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

        logger.info("Bot responded to=%s tenant_id=%s", user_phone, tenant_id)

    except Exception:
        logger.exception("Bot response failed for tenant=%s phone=%s", tenant_id, user_phone)

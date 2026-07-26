import json
import logging
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from fastapi import APIRouter, BackgroundTasks, Query, Request
from fastapi.responses import PlainTextResponse, Response

from app.config import settings
from app.security import decrypt_token, verify_webhook_signature
from app.ai_core.bridge import respond as ai_respond
from app.ai_core.channel import courtesy
from app.ai_core.channel.actions import (
    SendButtonsAction,
    SendImageAction,
    SendListAction,
    SendTextAction,
)
from app.ai_core.channel.inbound import InteractiveReply
from app.services import meta_api
from app.services.phone import normalize_phone
from app.services.supabase_client import get_supabase
from app.services.whatsapp_delivery import plan_delivery
from app.services.whatsapp_sender import WhatsAppSender

logger = logging.getLogger("doppel.webhook")
router = APIRouter(tags=["Webhook"])
_MEDIA_MESSAGE_TYPES = {"image", "audio", "voice", "document"}


@dataclass
class InboundMessage:
    """Un mensaje entrante ya normalizado (ver `_parse_inbound`)."""

    content: str | None = None
    media: list[dict] = field(default_factory=list)
    message_type: str = "text"
    interactive: InteractiveReply | None = None


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
                    await supabase.table("whatsapp_accounts")
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
                    await supabase.table("bot_configs")
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
                            await supabase.table("messages")
                            .select("id")
                            .eq("wa_message_id", wa_message_id)
                            .limit(1)
                            .execute()
                        )
                        if existing_message.data:
                            logger.info("Skipping duplicate webhook message_id=%s", wa_message_id)
                            continue

                    inbound = _parse_inbound(msg)
                    content, media = inbound.content, inbound.media
                    msg_type = inbound.message_type
                    user_phone = normalize_phone(msg.get("from")) or msg.get("from")
                    mode = "manager" if user_phone in admin_phones else "client"

                    await supabase.table("messages").insert({
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

                    should_process = bool(settings.BOT_ENABLED and (content or media))
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
                            inbound.interactive,
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


def _parse_inbound(msg: dict) -> InboundMessage:
    """Normaliza un mensaje entrante de Meta a lo que necesita el resto del flujo.

    Devuelve un objeto y no una tupla porque ya son cuatro campos: el `type`
    crudo de Meta no alcanza (un tap de botón y uno de lista llegan los dos como
    `interactive`) y `content` es lo que se guarda para el dashboard, que no es
    lo mismo que lo que ve el agente.
    """
    msg_type = msg.get("type", "text")

    if msg_type == "text":
        return InboundMessage(content=msg.get("text", {}).get("body"), message_type=msg_type)

    if msg_type == "interactive":
        payload = msg.get("interactive") or {}
        reply = payload.get("button_reply") or payload.get("list_reply") or {}
        reply_id = reply.get("id")
        if not reply_id:
            return InboundMessage(message_type=msg_type)
        title = reply.get("title") or ""
        return InboundMessage(
            # El título es lo que el cliente vio, así que es lo legible en el
            # dashboard; el id sólo le sirve al agente.
            content=title or reply_id,
            message_type=msg_type,
            interactive=InteractiveReply(id=reply_id, title=title),
        )

    if msg_type not in _MEDIA_MESSAGE_TYPES:
        return InboundMessage(message_type=msg_type)

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
    return InboundMessage(
        content=payload.get("caption") or f"[{msg_type} message]",
        media=media,
        message_type=msg_type,
    )


def _inbound_message_type(media: list[dict] | None) -> str:
    """Tipo del mensaje entrante para elegir la reacción: el del primer adjunto."""
    for item in media or []:
        if item.get("type"):
            return item["type"]
    return "text"


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


def _cleanup_media_files(media: list[dict] | None) -> None:
    """Borrar del disco los adjuntos descargados para este mensaje.

    Sin esto cada nota de voz, foto y PDF que entra queda para siempre en
    `/tmp/doppel-whatsapp-media/`: nadie más los toca después de que el turno
    termina, así que el disco crece con cada mensaje hasta llenarse.

    Lee `local_path` de los propios items (que `_download_media_files` setea a
    medida que baja cada uno) en vez de recibir una lista de paths, para que una
    descarga que falla a mitad igual limpie lo que alcanzó a escribir. Es
    best-effort: un archivo que no se puede borrar se loguea, nunca rompe el
    turno — para cuando corre, la respuesta ya se envió.
    """
    for item in media or []:
        path = item.pop("local_path", None)
        if not path:
            continue
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            logger.warning("No se pudo borrar el media temporal path=%s", path, exc_info=True)


def _action_preview(action) -> str:
    """Texto de la acción para dimensionar la pausa de tipeo."""
    return getattr(action, "body", None) or getattr(action, "caption", None) or ""


async def _deliver_action(sender: WhatsAppSender, action) -> str:
    """Manda una acción de canal. Propaga si Meta la rechaza."""
    if isinstance(action, SendTextAction):
        return await sender.send_text(action.body)
    if isinstance(action, SendImageAction):
        return await sender.send_image(action.image_url, action.caption)
    if isinstance(action, SendButtonsAction):
        return await sender.send_buttons(action.body, action.to_meta())
    if isinstance(action, SendListAction):
        return await sender.send_list(action.body, action.button_label, action.to_meta())
    raise ValueError(f"Acción de canal no entregable: {action.kind}")


# Cómo se ve cada acción en la tabla `messages`, que alimenta el dashboard. Las
# reacciones y las tildes azules no aparecen acá a propósito: no son mensajes.
_ACTION_MESSAGE_TYPES = {
    "text": "text",
    "image": "image",
    "buttons": "interactive",
    "list": "interactive",
}


async def _record_outbound(
    supabase,
    *,
    tenant_id: str,
    wa_account_id: str,
    user_phone: str,
    mode: str,
    action,
    wa_message_id: str,
) -> None:
    """Registra una fila por acción entregada. Nunca aborta la entrega.

    El mensaje ya salió: si falla el insert, perder la fila del dashboard es
    mucho menos grave que cortar el resto del turno a mitad de camino.
    """
    try:
        await supabase.table("messages").insert({
            "tenant_id": tenant_id,
            "wa_account_id": wa_account_id,
            "user_phone": user_phone,
            "direction": "outbound",
            "content": _action_preview(action),
            "message_type": _ACTION_MESSAGE_TYPES.get(action.kind, "text"),
            "wa_message_id": wa_message_id,
            "media": [],
            "agent_mode": mode,
        }).execute()
    except Exception:
        logger.warning(
            "No se pudo registrar el saliente tenant=%s wa_msg_id=%s",
            tenant_id, wa_message_id, exc_info=True,
        )


async def _process_bot_response(
    http_client: httpx.AsyncClient,
    tenant_id: str,
    wa_account_id: str,
    user_phone: str,
    inbound_text: str,
    mode: str,
    inbound_message_id: str | None,
    media: list[dict] | None = None,
    interactive: InteractiveReply | None = None,
) -> None:
    """Generate AI response and send it via WhatsApp. Runs as a background task."""
    started = time.monotonic()
    logger.debug(
        "[BOT_START] tenant=%s phone=%s mode=%s msg_id=%s media_count=%d",
        tenant_id, user_phone, mode, inbound_message_id, len(media or []),
    )
    try:
        supabase = get_supabase()

        # Bot config: solo lo que webhook.py necesita para sus propios gates/logging.
        # system_prompt/manager_prompt/ai_model ya no aplican — app.ai_core usa
        # prompts estáticos (app/ai_core/prompts/) y DeepSeek fijo, no bot_configs.
        config_result = (
            await supabase.table("bot_configs")
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

        logger.debug(
            "[BOT_CONFIG] tenant=%s bot_enabled=%s is_manager=%s",
            tenant_id, config.get("bot_enabled"), is_manager,
        )

        # Manager bypasses bot_enabled — operator can talk even when client bot is paused.
        if not is_manager and not config.get("bot_enabled", True):
            logger.info("Bot disabled for tenant_id=%s", tenant_id)
            return

        # Get WhatsApp account (need phone_number_id and encrypted token)
        wa_result = (
            await supabase.table("whatsapp_accounts")
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

        sender = WhatsAppSender(
            http_client,
            phone_number_id=wa_account["phone_number_id"],
            token=access_token,
            api_version=settings.META_API_VERSION,
            to=user_phone,
            inbound_message_id=inbound_message_id,
        )
        # Cortesías antes de invocar al modelo, no después: el "escribiendo…"
        # tiene que estar visible mientras el LLM piensa, que es justo el hueco
        # donde el cliente hoy no ve nada. Ambas se tragan sus errores adentro.
        await sender.mark_read_and_typing()
        reaction = courtesy.choose_reaction(inbound_text, _inbound_message_type(media))
        if reaction:
            await sender.react(reaction)

        logger.debug("[BOT_MEDIA] descargando %d archivos tenant=%s", len(media or []), tenant_id)
        await _download_media_files(
            http_client,
            tenant_id=tenant_id,
            token=access_token,
            media=media,
        )

        # Conversation history is owned by app.ai_core (LangGraph checkpointer) per
        # thread in its own Postgres; the API no longer loads/sends it. Supabase
        # `messages` remains the inbound/outbound log for the dashboard.
        ai_response = await ai_respond(
            tenant_id=tenant_id,
            user_phone=user_phone,
            content=inbound_text,
            media=media,
            message_id=inbound_message_id,
            interactive_reply=interactive,
        )
        if not ai_response.ok:
            logger.error(
                "[BOT_CRASH] agente falló internamente tenant=%s phone=%s mode=%s",
                tenant_id, user_phone, mode,
            )
            return

        plan = plan_delivery(ai_response)
        if not plan:
            logger.warning(
                "Empty agent response tenant=%s phone=%s mode=%s",
                tenant_id, user_phone, mode,
            )
            return

        logger.debug(
            "[BOT_SEND] tenant=%s phone=%s acciones=%d respuesta=%r",
            tenant_id, user_phone, len(plan), ai_response.text[:120],
        )
        # Secuencial y en orden: WhatsApp no garantiza el orden de entrega de
        # envíos concurrentes, y acá el orden es semántico (la foto antes que
        # los botones que la referencian).
        for action in plan:
            await sender.human_pause(
                _action_preview(action), elapsed=time.monotonic() - started,
            )
            wa_msg_id = await _deliver_action(sender, action)
            await _record_outbound(
                supabase,
                tenant_id=tenant_id,
                wa_account_id=wa_account_id,
                user_phone=user_phone,
                mode=mode,
                action=action,
                wa_message_id=wa_msg_id,
            )

        logger.info(
            "[BOT_OK] tenant=%s phone=%s mode=%s acciones=%d",
            tenant_id, user_phone, mode, len(plan),
        )

    except Exception:
        logger.exception("Bot response failed for tenant=%s phone=%s", tenant_id, user_phone)
    finally:
        # En el `finally` y no después del envío: los adjuntos tienen que
        # borrarse también cuando el turno corta antes (bot apagado, cuenta no
        # encontrada, agente caído), que es justo cuando es fácil olvidarse.
        _cleanup_media_files(media)

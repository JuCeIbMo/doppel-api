"""Execute one AI turn and deliver its ordered WhatsApp actions."""

import logging
import time

import httpx

from app.ai_core.bridge import respond as ai_respond
from app.ai_core.channel import courtesy
from app.ai_core.channel.actions import (
    SendButtonsAction,
    SendImageAction,
    SendListAction,
    SendTextAction,
)
from app.ai_core.channel.inbound import InteractiveReply
from app.config import settings
from app.security import decrypt_token
from app.services.supabase_client import get_supabase
from app.whatsapp.delivery import plan_delivery
from app.whatsapp.inbound import cleanup_media_files, download_media_files, inbound_message_type
from app.whatsapp.sender import WhatsAppSender

logger = logging.getLogger("doppel.whatsapp.turn")
_ACTION_MESSAGE_TYPES = {
    "text": "text",
    "image": "image",
    "buttons": "interactive",
    "list": "interactive",
}


def action_preview(action) -> str:
    return getattr(action, "body", None) or getattr(action, "caption", None) or ""


async def deliver_action(sender: WhatsAppSender, action) -> str:
    if isinstance(action, SendTextAction):
        return await sender.send_text(action.body)
    if isinstance(action, SendImageAction):
        return await sender.send_image(action.image_url, action.caption)
    if isinstance(action, SendButtonsAction):
        return await sender.send_buttons(action.body, action.to_meta())
    if isinstance(action, SendListAction):
        return await sender.send_list(action.body, action.button_label, action.to_meta())
    raise ValueError(f"Acción de canal no entregable: {action.kind}")


async def record_outbound(
    supabase,
    *,
    tenant_id: str,
    wa_account_id: str,
    user_phone: str,
    mode: str,
    action,
    wa_message_id: str,
) -> None:
    """Record a successfully delivered action without interrupting later actions."""
    try:
        await supabase.table("messages").insert({
            "tenant_id": tenant_id,
            "wa_account_id": wa_account_id,
            "user_phone": user_phone,
            "direction": "outbound",
            "content": action_preview(action),
            "message_type": _ACTION_MESSAGE_TYPES.get(action.kind, "text"),
            "wa_message_id": wa_message_id,
            "media": [],
            "agent_mode": mode,
        }).execute()
    except Exception:
        logger.warning(
            "No se pudo registrar el saliente tenant=%s wa_msg_id=%s",
            tenant_id,
            wa_message_id,
            exc_info=True,
        )


async def process_bot_response(
    http_client: httpx.AsyncClient,
    tenant_id: str,
    wa_account_id: str,
    user_phone: str,
    inbound_text: str,
    mode: str,
    inbound_message_id: str | None,
    media: list[dict] | None = None,
    interactive: InteractiveReply | None = None,
    *,
    supabase_client=None,
) -> None:
    """Generate and deliver one response; suitable for a background task."""
    started = time.monotonic()
    logger.debug(
        "[BOT_START] tenant=%s phone=%s mode=%s msg_id=%s media_count=%d",
        tenant_id,
        user_phone,
        mode,
        inbound_message_id,
        len(media or []),
    )
    try:
        supabase = supabase_client or get_supabase()
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
        if not is_manager and not config.get("bot_enabled", True):
            logger.info("Bot disabled for tenant_id=%s", tenant_id)
            return

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
        await sender.mark_read_and_typing()
        reaction = courtesy.choose_reaction(inbound_text, inbound_message_type(media))
        if reaction:
            await sender.react(reaction)

        await download_media_files(
            http_client,
            tenant_id=tenant_id,
            token=access_token,
            media=media,
        )
        ai_response = await ai_respond(
            tenant_id=tenant_id,
            user_phone=user_phone,
            content=inbound_text,
            media=media,
            message_id=inbound_message_id,
            interactive_reply=interactive,
        )
        if not ai_response.ok:
            logger.error("[BOT_CRASH] agente falló internamente tenant=%s phone=%s mode=%s", tenant_id, user_phone, mode)
            return

        plan = plan_delivery(ai_response)
        if not plan:
            logger.warning("Empty agent response tenant=%s phone=%s mode=%s", tenant_id, user_phone, mode)
            return

        for action in plan:
            await sender.human_pause(action_preview(action), elapsed=time.monotonic() - started)
            wa_msg_id = await deliver_action(sender, action)
            await record_outbound(
                supabase,
                tenant_id=tenant_id,
                wa_account_id=wa_account_id,
                user_phone=user_phone,
                mode=mode,
                action=action,
                wa_message_id=wa_msg_id,
            )
        logger.info("[BOT_OK] tenant=%s phone=%s mode=%s acciones=%d", tenant_id, user_phone, mode, len(plan))
    except Exception:
        logger.exception("Bot response failed for tenant=%s phone=%s", tenant_id, user_phone)
    finally:
        cleanup_media_files(media)

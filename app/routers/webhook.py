import json
import logging

import httpx
from fastapi import APIRouter, BackgroundTasks, Query, Request
from fastapi.responses import PlainTextResponse, Response

from app.config import settings
from app.security import decrypt_token, verify_webhook_signature
from app.services import ai_bot, meta_api
from app.services.supabase_client import get_supabase

logger = logging.getLogger("doppel.webhook")
router = APIRouter(tags=["Webhook"])


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

                # Save each inbound message and schedule bot response
                for msg in messages:
                    msg_type = msg.get("type", "text")
                    content = None
                    if msg_type == "text":
                        content = msg.get("text", {}).get("body")

                    supabase.table("messages").insert({
                        "tenant_id": account["tenant_id"],
                        "wa_account_id": account["id"],
                        "user_phone": msg.get("from"),
                        "direction": "inbound",
                        "content": content,
                        "message_type": msg_type,
                        "wa_message_id": msg.get("id"),
                    }).execute()

                    logger.info(
                        "Saved message from=%s phone_id=%s type=%s",
                        msg.get("from"), phone_number_id, msg_type,
                    )

                    # Schedule bot response (only for text messages, only if AI is configured)
                    if msg_type == "text" and content and settings.ANTHROPIC_API_KEY:
                        background_tasks.add_task(
                            _process_bot_response,
                            request.app.state.http_client,
                            account["tenant_id"],
                            account["id"],
                            msg.get("from"),
                            content,
                        )

    except Exception:
        logger.exception("Error processing webhook")

    # Always return 200 — Meta retries if it doesn't get 200
    return Response(status_code=200)


async def _process_bot_response(
    http_client: httpx.AsyncClient,
    tenant_id: str,
    wa_account_id: str,
    user_phone: str,
    inbound_text: str,
) -> None:
    """Generate AI response and send it via WhatsApp. Runs as a background task."""
    try:
        supabase = get_supabase()

        # Get bot config
        config_result = (
            supabase.table("bot_configs")
            .select("system_prompt, ai_model")
            .eq("tenant_id", tenant_id)
            .single()
            .execute()
        )
        if not config_result.data:
            logger.warning("No bot config for tenant_id=%s", tenant_id)
            return

        config = config_result.data

        # Get WhatsApp account (need phone_number_id and encrypted token)
        wa_result = (
            supabase.table("whatsapp_accounts")
            .select("phone_number_id, access_token_encrypted")
            .eq("id", wa_account_id)
            .single()
            .execute()
        )
        if not wa_result.data:
            return

        wa_account = wa_result.data

        # Build conversation history (most recent N messages)
        history = (
            supabase.table("messages")
            .select("direction, content")
            .eq("tenant_id", tenant_id)
            .eq("user_phone", user_phone)
            .order("created_at", desc=True)
            .limit(settings.AI_CONTEXT_MESSAGES)
            .execute()
        )

        # Reverse to chronological order and map to Anthropic format
        conversation = []
        for m in reversed(history.data):
            if m["content"]:
                role = "user" if m["direction"] == "inbound" else "assistant"
                conversation.append({"role": role, "content": m["content"]})

        if not conversation:
            return

        # Generate AI response
        ai_text = await ai_bot.generate_response(
            system_prompt=config["system_prompt"],
            conversation=conversation,
            model=config["ai_model"],
        )

        # Decrypt token and send WhatsApp message
        access_token = decrypt_token(wa_account["access_token_encrypted"], settings.ENCRYPTION_KEY)
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
        }).execute()

        logger.info("Bot responded to=%s tenant_id=%s", user_phone, tenant_id)

    except Exception:
        logger.exception("Bot response failed for tenant=%s phone=%s", tenant_id, user_phone)

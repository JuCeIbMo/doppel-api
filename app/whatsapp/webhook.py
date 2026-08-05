"""Persist webhook events, debounce message bursts, and schedule bot turns."""

import asyncio
import logging
from collections.abc import Callable

import httpx

from app.ai_core.channel.inbound import InteractiveReply
from app.config import settings
from app.services.message_debounce import debounce_message
from app.services.phone import normalize_phone
from app.services.supabase_client import get_supabase
from app.whatsapp.inbound import parse_inbound
from app.whatsapp.turn import process_bot_response

logger = logging.getLogger("doppel.whatsapp.webhook")
ScheduledResponse = tuple[
    str,
    str,
    str,
    str,
    str,
    str | None,
    list[dict],
    InteractiveReply | None,
]


def log_whatsapp_statuses(phone_number_id: str, statuses: list[dict]) -> None:
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


async def ingest_webhook(
    payload: dict,
    *,
    http_client: httpx.AsyncClient,
    schedule_task: Callable,
) -> None:
    """Ingest all message/status changes contained in one verified Meta payload."""
    supabase = get_supabase()
    scheduled_responses: list[ScheduledResponse] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            phone_number_id = (value.get("metadata") or {}).get("phone_number_id")
            messages = value.get("messages", [])
            statuses = value.get("statuses", [])
            if phone_number_id and statuses:
                log_whatsapp_statuses(phone_number_id, statuses)
            if not phone_number_id or not messages:
                continue

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
                logger.info("Webhook de phone_number_id no registrado, ignorando phone_number_id=%s", phone_number_id)
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

            for msg in messages:
                wa_message_id = msg.get("id")
                if wa_message_id:
                    existing = (
                        await supabase.table("messages")
                        .select("id")
                        .eq("wa_message_id", wa_message_id)
                        .limit(1)
                        .execute()
                    )
                    if existing.data:
                        logger.info("Skipping duplicate webhook message_id=%s", wa_message_id)
                        continue

                inbound = parse_inbound(msg)
                user_phone = normalize_phone(msg.get("from")) or msg.get("from")
                mode = "manager" if user_phone in admin_phones else "client"
                await supabase.table("messages").insert({
                    "tenant_id": account["tenant_id"],
                    "wa_account_id": account["id"],
                    "user_phone": user_phone,
                    "direction": "inbound",
                    "content": inbound.content,
                    "message_type": inbound.message_type,
                    "wa_message_id": wa_message_id,
                    "media": inbound.media,
                    "agent_mode": mode,
                }).execute()

                should_process = bool(settings.BOT_ENABLED and (inbound.content or inbound.media))
                if mode == "client" and not config.get("bot_enabled", True):
                    should_process = False
                if should_process:
                    scheduled_responses.append(
                        (
                            account["tenant_id"],
                            account["id"],
                            user_phone,
                            inbound.content or "",
                            mode,
                            wa_message_id,
                            inbound.media,
                            inbound.interactive,
                        )
                    )

    if scheduled_responses:
        # Starlette awaits BackgroundTasks in insertion order. A single task
        # must start all waiters concurrently for messages from one Meta
        # payload to share the debounce window.
        schedule_task(
            run_scheduled_responses,
            http_client,
            scheduled_responses,
            supabase_client=supabase,
        )


async def run_scheduled_responses(
    http_client: httpx.AsyncClient,
    scheduled_responses: list[ScheduledResponse],
    *,
    supabase_client=None,
) -> None:
    """Start every debounce waiter from one Meta payload concurrently."""
    await asyncio.gather(
        *(
            debounce_bot_response(
                http_client,
                *args,
                supabase_client=supabase_client,
            )
            for args in scheduled_responses
        )
    )


async def debounce_bot_response(
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
    """Coalesce one conversation's message burst before invoking the agent."""
    message = {
        "tenant_id": tenant_id,
        "wa_account_id": wa_account_id,
        "user_phone": user_phone,
        "inbound_text": inbound_text,
        "mode": mode,
        "inbound_message_id": inbound_message_id,
        "media": media or [],
        "interactive": (
            {"id": interactive.id, "title": interactive.title}
            if interactive is not None
            else None
        ),
    }
    conversation_id = f"{tenant_id}:{mode}:{user_phone}"
    batch = await debounce_message(conversation_id, message)
    if not batch:
        return

    texts: list[str] = []
    combined_media: list[dict] = []
    last = batch[-1]
    single_interactive: InteractiveReply | None = None

    for item in batch:
        combined_media.extend(item.get("media") or [])
        reply_data = item.get("interactive")
        if reply_data:
            reply = InteractiveReply(**reply_data)
            if len(batch) == 1:
                single_interactive = reply
            else:
                texts.append(reply.as_agent_note())
        elif item.get("inbound_text"):
            texts.append(item["inbound_text"])

    logger.info(
        "Debounced inbound messages tenant=%s phone=%s count=%d",
        tenant_id,
        user_phone,
        len(batch),
    )
    await process_bot_response(
        http_client,
        tenant_id,
        last["wa_account_id"],
        user_phone,
        "\n".join(texts),
        last["mode"],
        last.get("inbound_message_id"),
        combined_media,
        single_interactive,
        supabase_client=supabase_client,
    )

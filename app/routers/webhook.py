"""HTTP boundary for the WhatsApp Cloud API webhook."""

import json
import logging

from fastapi import APIRouter, BackgroundTasks, Query, Request
from fastapi.responses import PlainTextResponse, Response

from app.config import settings
from app.security import verify_webhook_signature
from app.whatsapp.webhook import ingest_webhook

logger = logging.getLogger("doppel.webhook")
router = APIRouter(tags=["Webhook"])


@router.get("/webhook/whatsapp")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_verify_token == settings.META_VERIFY_TOKEN:
        return PlainTextResponse(content=hub_challenge)
    return Response(status_code=403)


@router.post("/webhook/whatsapp")
async def receive_webhook(request: Request, background_tasks: BackgroundTasks):
    """Verify and delegate the payload. Always return 200 so Meta does not retry."""
    try:
        body = await request.body()
        signature = request.headers.get("X-Hub-Signature-256", "")
        if not verify_webhook_signature(body, signature, settings.META_APP_SECRET):
            logger.warning("Rejected webhook: invalid signature")
            return Response(status_code=200)

        await ingest_webhook(
            json.loads(body),
            http_client=request.app.state.http_client,
            schedule_task=background_tasks.add_task,
        )
    except Exception:
        logger.exception("Error processing webhook")
    return Response(status_code=200)

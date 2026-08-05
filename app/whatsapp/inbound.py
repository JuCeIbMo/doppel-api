"""Normalize inbound Meta messages and manage their temporary media files."""

import logging
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from app.ai_core.channel.inbound import InteractiveReply
from app.config import settings
from app.whatsapp import meta

logger = logging.getLogger("doppel.whatsapp.inbound")
_MEDIA_MESSAGE_TYPES = {"image", "audio", "voice", "document"}


@dataclass
class InboundMessage:
    content: str | None = None
    media: list[dict] = field(default_factory=list)
    message_type: str = "text"
    interactive: InteractiveReply | None = None


def parse_inbound(msg: dict) -> InboundMessage:
    """Normalize Meta's channel-specific payload for persistence and the agent."""
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
        media.append({
            "id": media_id,
            "type": msg_type,
            "mime_type": payload.get("mime_type"),
            "sha256": payload.get("sha256"),
            "filename": payload.get("filename"),
        })
    return InboundMessage(
        content=payload.get("caption") or f"[{msg_type} message]",
        media=media,
        message_type=msg_type,
    )


def inbound_message_type(media: list[dict] | None) -> str:
    for item in media or []:
        if item.get("type"):
            return item["type"]
    return "text"


def _media_download_path(*, tenant_id: str, media_item: dict) -> Path:
    filename = media_item.get("filename")
    suffix = Path(str(filename)).suffix if filename else ""
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


async def download_media_files(
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
        downloaded = await meta.download_media_to_path(
            http_client,
            str(media_id),
            token,
            settings.META_API_VERSION,
            _media_download_path(tenant_id=tenant_id, media_item=item),
        )
        item.update({
            "local_path": downloaded["path"],
            "downloaded_mime_type": downloaded.get("mime_type"),
            "size": downloaded.get("size"),
        })
        paths.append(downloaded["path"])
    return paths


def cleanup_media_files(media: list[dict] | None) -> None:
    """Best-effort removal of every attachment downloaded for one turn."""
    for item in media or []:
        path = item.pop("local_path", None)
        if not path:
            continue
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            logger.warning("No se pudo borrar el media temporal path=%s", path, exc_info=True)

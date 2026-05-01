"""HTTP bridge from Doppel to the internal nanobot SaaS runtime."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import httpx

from app.config import settings

Mode = Literal["manager", "client"]


class NanobotRuntimeNotConfigured(RuntimeError):
    """Raised when Doppel is asked to call nanobot without a runtime URL."""


async def respond(
    http_client: httpx.AsyncClient,
    *,
    tenant_id: str,
    mode: Mode,
    sender_id: str,
    chat_id: str,
    message_id: str | None,
    content: str,
    model: str,
    media_paths: list[str] | None = None,
) -> dict[str, Any]:
    """Send one WhatsApp turn to nanobot and return its JSON payload."""

    base_url = settings.NANOBOT_RUNTIME_URL.rstrip("/")
    if not base_url:
        raise NanobotRuntimeNotConfigured("NANOBOT_RUNTIME_URL is not configured")

    headers = {}
    if settings.NANOBOT_RUNTIME_TOKEN:
        headers["Authorization"] = f"Bearer {settings.NANOBOT_RUNTIME_TOKEN}"

    data = {
        "tenant_id": tenant_id,
        "mode": mode,
        "sender_id": sender_id,
        "chat_id": chat_id,
        "message_id": message_id or "",
        "content": content,
        "model": model,
    }

    files = []
    handles = []
    try:
        for path in media_paths or []:
            p = Path(path)
            if not p.is_file():
                continue
            handle = p.open("rb")
            handles.append(handle)
            files.append(("files", (p.name, handle)))

        response = await http_client.post(
            f"{base_url}/internal/whatsapp/turn",
            data=data,
            files=files or None,
            headers=headers,
            timeout=settings.NANOBOT_RUNTIME_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()
    finally:
        for handle in handles:
            handle.close()

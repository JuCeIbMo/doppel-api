"""HTTP bridge from Doppel to the internal ai-core runtime."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import httpx

from app.config import settings

Mode = Literal["manager", "client"]


class AiCoreRuntimeNotConfigured(RuntimeError):
    """Raised when Doppel is asked to call ai-core without a runtime URL."""


async def respond(
    http_client: httpx.AsyncClient,
    *,
    tenant_id: str,
    mode: Mode,
    sender_id: str,
    chat_id: str,
    message_id: str | None,
    content: str,
    system_prompt: str,
    model: str,
    media_paths: list[str] | None = None,
) -> dict[str, Any]:
    """Send one WhatsApp turn to ai-core and return its JSON payload."""

    base_url = settings.AI_CORE_URL.rstrip("/")
    if not base_url:
        raise AiCoreRuntimeNotConfigured("AI_CORE_URL is not configured")

    headers = {}
    if settings.AI_CORE_TOKEN:
        headers["Authorization"] = f"Bearer {settings.AI_CORE_TOKEN}"

    data = {
        "tenant_id": tenant_id,
        "mode": mode,
        "sender_id": sender_id,
        "chat_id": chat_id,
        "message_id": message_id or "",
        "content": content,
        "system_prompt": system_prompt,
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
            f"{base_url}/internal/doppel/turn",
            data=data,
            files=files or None,
            headers=headers,
            timeout=settings.AI_CORE_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()
    finally:
        for handle in handles:
            handle.close()

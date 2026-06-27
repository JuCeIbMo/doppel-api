"""Puente entre el webhook y los agentes Pydantic AI. Entrada única por mensaje."""

from __future__ import annotations

import logging
from typing import Literal

from app.ai import history
from app.ai.agents.client import MODEL as CLIENT_MODEL
from app.ai.agents.client import client_agent
from app.ai.agents.manager import ManagerDeps, manager_agent
from app.ai.media import prepare_images
from app.ai.model import model_string
from app.ai.transcription import transcribe_audio_media
from app.services.erp.context import bot_context

logger = logging.getLogger("doppel.ai.bridge")

Mode = Literal["manager", "client"]


def _document_note(media: list[dict] | None) -> str:
    docs = [m for m in (media or []) if m.get("type") not in {"image", "audio", "voice"}]
    return "\n[documento adjunto]" if docs else ""


async def respond(
    *,
    mode: Mode,
    tenant_id: str,
    user_phone: str,
    content: str,
    system_prompt: str,
    model: str,
    wa_access_token: str = "",
    wa_phone_number_id: str = "",
    media: list[dict] | None = None,
) -> str | None:
    """Corre el agente correspondiente. None = crash, '' = vacío legítimo."""
    logger.debug(
        "[START] tenant=%s phone=%s mode=%s model=%s texto_chars=%d",
        tenant_id, user_phone, mode, model, len(content or ""),
    )
    try:
        transcript = await transcribe_audio_media(media)
        images = prepare_images(media)

        text_parts = [content] if content else []
        if transcript:
            text_parts.append(f"[Nota de voz]: {transcript}")
        text = ("\n".join(text_parts) + _document_note(media)).strip()

        prompt: list | str = [text, *images] if images else text

        session_id = history.session_id_for(tenant_id, user_phone)
        if mode == "manager":
            # El manager todavía toma su prompt y modelo del tenant.
            deps = ManagerDeps(ctx=bot_context(tenant_id, actor="admin_bot"),
                               system_prompt=system_prompt)
            result = await manager_agent.run(
                prompt, deps=deps, model=model_string(model),
                message_history=history.load(session_id),
            )
        else:
            # El vendedor es autocontenido: modelo (CLIENT_MODEL) e instrucciones
            # viven en client.py. Lo único que le pasamos es el tenant (deps).
            result = await client_agent.run(
                prompt, model=CLIENT_MODEL,
                deps=bot_context(tenant_id, actor="whatsapp_bot"),
                message_history=history.load(session_id),
            )
        history.append(session_id, result.new_messages())

        reply = (result.output or "").strip()
        logger.debug("[OUTPUT] tenant=%s mode=%s chars=%d", tenant_id, mode, len(reply))
        return reply
    except Exception:
        logger.exception("respuesta IA falló tenant=%s phone=%s mode=%s", tenant_id, user_phone, mode)
        return None

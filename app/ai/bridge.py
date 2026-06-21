"""Puente entre el webhook y los agentes Agno. Entrada única por mensaje."""

from __future__ import annotations

import logging
from typing import Literal

from supabase import Client

from app.ai.factories.client_agent import get_client_agent
from app.ai.factories.manager_agent import get_manager_agent
from app.ai.media.transcription import prepare_images, transcribe_audio_media

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
    supabase: Client,
    wa_access_token: str = "",
    wa_phone_number_id: str = "",
    media: list[dict] | None = None,
) -> str | None:
    """Ejecuta el agente correspondiente y devuelve el texto final ('' si falla)."""
    media_types = [m.get("type") for m in (media or [])]
    logger.debug(
        "[START] tenant=%s phone=%s mode=%s model=%s media=%s texto_chars=%d",
        tenant_id, user_phone, mode, model, media_types, len(content or ""),
    )
    try:
        transcript = await transcribe_audio_media(media)
        images = prepare_images(media)

        text_parts = [content] if content else []
        if transcript:
            text_parts.append(f"[Nota de voz]: {transcript}")
            logger.debug("[TRANSCRIPCION] tenant=%s chars=%d", tenant_id, len(transcript))
        text = "\n".join(text_parts) + _document_note(media)
        text = text.strip()

        logger.debug(
            "[INPUT_AGENTE] tenant=%s mode=%s imagenes=%d texto_final=%r",
            tenant_id, mode, len(images), text[:120],
        )

        factory = get_manager_agent if mode == "manager" else get_client_agent
        agent = factory(
            tenant_id=tenant_id, user_phone=user_phone,
            system_prompt=system_prompt, model_id=model, supabase=supabase,
            wa_access_token=wa_access_token, wa_phone_number_id=wa_phone_number_id,
        )
        run = await agent.arun(text, images=images or None)
        reply = (run.content or "").strip()

        logger.debug(
            "[OUTPUT_AGENTE] tenant=%s mode=%s chars=%d respuesta=%r",
            tenant_id, mode, len(reply), reply[:120],
        )
        return reply
    except Exception:
        logger.exception(
            "respuesta IA falló tenant=%s phone=%s mode=%s", tenant_id, user_phone, mode
        )
        return None

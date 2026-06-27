"""Puente del spike: misma firma que app.ai.bridge.respond, camino Pydantic AI.

Cubre solo el modo `client` (el spike). El modo `manager` se delega al bridge de
Agno para no duplicar las tools ERP completas mientras dura la comparación.
"""

from __future__ import annotations

import logging
from typing import Literal

from app.ai.transcription import transcribe_audio_media
from app.ai.pydantic_spike import history
from app.ai.pydantic_spike.agent import ClientDeps, client_agent
from app.ai.pydantic_spike.media import prepare_images
from app.ai.pydantic_spike.model import model_string
from app.services.erp.context import bot_context

logger = logging.getLogger("doppel.ai.spike.bridge")

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
    """Ejecuta el client agent Pydantic AI. None = crash, '' = vacío legítimo."""
    if mode == "manager":
        # El spike no reimplementa el manager: delegamos al camino Agno.
        from app.ai.bridge import respond as agno_respond

        return await agno_respond(
            mode=mode, tenant_id=tenant_id, user_phone=user_phone, content=content,
            system_prompt=system_prompt, model=model,
            wa_access_token=wa_access_token, wa_phone_number_id=wa_phone_number_id,
            media=media,
        )

    media_types = [m.get("type") for m in (media or [])]
    logger.debug(
        "[SPIKE START] tenant=%s phone=%s model=%s media=%s texto_chars=%d",
        tenant_id, user_phone, model, media_types, len(content or ""),
    )
    try:
        transcript = await transcribe_audio_media(media)
        images = prepare_images(media)

        text_parts = [content] if content else []
        if transcript:
            text_parts.append(f"[Nota de voz]: {transcript}")
        text = ("\n".join(text_parts) + _document_note(media)).strip()

        # El prompt de usuario es texto + imágenes (multimodal).
        prompt: list = [text, *images] if images else text

        session_id = history.session_id_for(tenant_id, user_phone)
        deps = ClientDeps(ctx=bot_context(tenant_id, actor="whatsapp_bot"), system_prompt=system_prompt)

        result = await client_agent.run(
            prompt,
            deps=deps,
            model=model_string(model),
            message_history=history.load(session_id),
        )
        history.append(session_id, result.new_messages())

        reply = (result.output or "").strip()
        logger.debug("[SPIKE OUTPUT] tenant=%s chars=%d respuesta=%r", tenant_id, len(reply), reply[:120])
        return reply
    except Exception:
        logger.exception("respuesta IA (spike) falló tenant=%s phone=%s", tenant_id, user_phone)
        return None

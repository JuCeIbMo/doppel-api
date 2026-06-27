"""Transcripción de audio (Whisper) de los mensajes de WhatsApp."""

from __future__ import annotations

import logging

from openai import AsyncOpenAI

from app.ai.config import OPENAI_API_KEY

logger = logging.getLogger("doppel.ai.transcription")

_AUDIO_TYPES = {"audio", "voice"}

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    return _client


async def transcribe_audio(path: str) -> str:
    """Transcribe un archivo de audio a texto con Whisper. Devuelve '' si falla."""
    logger.debug("[WHISPER] transcribiendo path=%s", path)
    try:
        with open(path, "rb") as fh:
            result = await _get_client().audio.transcriptions.create(
                model="whisper-1", file=fh
            )
        text = (result.text or "").strip()
        logger.debug("[WHISPER] ok chars=%d resultado=%r", len(text), text[:80])
        return text
    except Exception:
        logger.exception("transcripción de audio falló path=%s", path)
        return ""


async def transcribe_audio_media(media: list[dict] | None) -> str:
    """Concatena las transcripciones de todas las notas de voz del mensaje."""
    parts: list[str] = []
    for item in media or []:
        if item.get("type") in _AUDIO_TYPES and item.get("local_path"):
            text = await transcribe_audio(item["local_path"])
            if text:
                parts.append(text)
    return "\n".join(parts)

"""Descripción de imágenes entrantes de WhatsApp con Gemini.

Comparte proveedor y modelo con `app/services/vision.py` (análisis de fotos de
producto para el front) pero es un camino aparte: acá no catalogamos un
producto propio, describimos lo que el cliente mandó (una captura, la foto de
un producto que quiere comprar, un comprobante, etc.) para que el agente
vendedor lo lea como si fuera texto. Nunca rompe: sin `GEMINI_API_KEY` o ante
cualquier falla devuelve `""` y el turno sigue solo con el texto del cliente.
"""

from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger("doppel.ai_core.media")

_PROMPT = (
    "Un cliente le mandó esta imagen a un vendedor por WhatsApp. Describila en "
    "1-2 oraciones en español, en el tono de una nota que un vendedor humano se "
    "haría a sí mismo para saber qué le mandaron: qué objeto o escena se ve, "
    "marca o texto visible si lo hay, y cualquier detalle relevante para vender "
    "(por ejemplo si es un comprobante de pago, una captura de pantalla, o la "
    "foto de un producto). No inventes datos que no se vean."
)

_client = None


def _get_client():
    global _client
    if _client is None:
        from google import genai

        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client


async def describe_image(path: str, mime_type: str | None) -> str:
    """Describe una imagen entrante con Gemini. Devuelve '' si falla o no hay key."""
    if not settings.GEMINI_API_KEY:
        return ""

    try:
        from google.genai import types

        with open(path, "rb") as fh:
            image_bytes = fh.read()

        response = await _get_client().aio.models.generate_content(
            model=settings.GEMINI_VISION_MODEL,
            contents=[
                types.Part.from_bytes(
                    data=image_bytes, mime_type=mime_type or "image/jpeg"
                ),
                _PROMPT,
            ],
        )
        return (response.text or "").strip()
    except Exception:
        logger.exception("descripción de imagen con Gemini falló path=%s", path)
        return ""


async def describe_image_media(media: list[dict] | None) -> str:
    """Concatena las descripciones de todas las imágenes del mensaje."""
    parts: list[str] = []
    for item in media or []:
        if item.get("type") == "image" and item.get("local_path"):
            mime_type = item.get("downloaded_mime_type") or item.get("mime_type")
            text = await describe_image(item["local_path"], mime_type)
            if text:
                parts.append(text)
    return "\n".join(parts)

"""Análisis de imágenes de productos con Gemini (autodescripción/etiquetado).

Herramienta del front, AISLADA del bot (`app/ai/`). Dada la
foto de un producto, sugiere nombre comercial, descripción de venta y tags de búsqueda
pensados para que el agente vendedor matchee consultas de clientes.

Nunca rompe: si no hay API key, o Gemini falla, o la respuesta no es JSON válido, devuelve
`ai_ok=False` con sugerencias vacías para que el usuario complete a mano.
"""

from __future__ import annotations

import json
import logging

from app.config import settings

logger = logging.getLogger("doppel.vision")

_MAX_TAGS = 10
_BLANK = {"ai_ok": False, "name": None, "description": None, "tags": []}

_PROMPT = (
    "Sos un catalogador de productos para una tienda/kiosco. Mirá la imagen del producto "
    "y devolvé SOLO un JSON con estas claves:\n"
    '- "name": nombre comercial corto y claro del producto (string).\n'
    '- "description": descripción orientada a la venta, de máximo 280 caracteres (string).\n'
    '- "tags": lista de 5 a 10 palabras clave en minúsculas (sin #) para que un vendedor '
    "encuentre el producto cuando un cliente lo busca (categoría, tipo, marca, uso, etc.).\n"
    "Respondé en español. No agregues texto fuera del JSON."
)

_client = None


def _get_client():
    """Cliente genai perezoso (singleton). La API key sale del entorno/config."""
    global _client
    if _client is None:
        from google import genai

        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client


def analyze_product_image(image_bytes: bytes, content_type: str, hint: str | None = None) -> dict:
    """Devuelve {ai_ok, name, description, tags} sugeridos por Gemini para la imagen."""
    if not settings.GEMINI_API_KEY:
        return dict(_BLANK)

    try:
        from google.genai import types

        prompt = _PROMPT if not hint else f"{_PROMPT}\nContexto del vendedor: {hint}"
        response = _get_client().models.generate_content(
            model=settings.GEMINI_VISION_MODEL,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=content_type),
                prompt,
            ],
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        data = json.loads(response.text)
    except Exception:
        logger.exception("análisis de imagen con Gemini falló")
        return dict(_BLANK)

    return {
        "ai_ok": True,
        "name": _clean_str(data.get("name")),
        "description": _clean_str(data.get("description")),
        "tags": _normalize_tags(data.get("tags")),
    }


def _clean_str(value) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _normalize_tags(value) -> list[str]:
    """Minúsculas, trim, sin vacíos, sin duplicados, máximo _MAX_TAGS."""
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for tag in value:
        if not isinstance(tag, str):
            continue
        clean = tag.strip().lower()
        if clean and clean not in out:
            out.append(clean)
        if len(out) >= _MAX_TAGS:
            break
    return out

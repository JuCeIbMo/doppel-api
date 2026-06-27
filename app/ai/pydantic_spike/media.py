"""Preparación de imágenes para Pydantic AI (equivalente a prepare_images de Agno).

Agno usa `agno.media.Image`; Pydantic AI usa `BinaryContent` en el user prompt.
La transcripción de audio (Whisper) se reusa tal cual desde app.ai.media.
"""

from __future__ import annotations

import logging
import mimetypes

from pydantic_ai import BinaryContent

logger = logging.getLogger("doppel.ai.spike.media")

_IMAGE_TYPES = {"image"}


def prepare_images(media: list[dict] | None) -> list[BinaryContent]:
    items: list[BinaryContent] = []
    for item in media or []:
        if item.get("type") not in _IMAGE_TYPES:
            continue
        path = item.get("local_path")
        if not path:
            continue
        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except OSError:
            logger.exception("no pude leer imagen path=%s", path)
            continue
        media_type = mimetypes.guess_type(path)[0] or "image/jpeg"
        items.append(BinaryContent(data=data, media_type=media_type))
    return items

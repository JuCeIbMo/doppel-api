"""Tratamiento de imágenes de productos (Pillow).

Herramienta del front, aislada del bot Agno. Normaliza la foto subida a un tile de
catálogo consistente: corrige orientación EXIF, encuadra en un cuadrado con fondo
blanco y comprime a WebP. Devuelve los bytes listos para subir a Storage.
"""

from __future__ import annotations

import io

from PIL import Image, ImageOps, UnidentifiedImageError

from app.services.erp.exceptions import ValidationError

CANVAS = 1000  # lado del tile cuadrado de salida (px)
MAX_BYTES = 10 * 1024 * 1024  # 10 MB de entrada
_WEBP_QUALITY = 82
_WHITE = (255, 255, 255)


def optimize_image(raw: bytes) -> bytes:
    """Normaliza `raw` a un cuadrado WebP de CANVAS×CANVAS con fondo blanco.

    Lanza ValidationError si está vacío, excede MAX_BYTES o no es una imagen.
    """
    if not raw:
        raise ValidationError("La imagen está vacía")
    if len(raw) > MAX_BYTES:
        raise ValidationError(
            "La imagen es demasiado grande", max_bytes=MAX_BYTES, size=len(raw)
        )

    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValidationError("El archivo no es una imagen válida", reason=str(exc))

    img = ImageOps.exif_transpose(img)  # respeta la orientación de fotos de celular
    img = _flatten_to_rgb(img)
    img.thumbnail((CANVAS, CANVAS), Image.LANCZOS)  # encoge preservando proporción

    canvas = Image.new("RGB", (CANVAS, CANVAS), _WHITE)
    offset = ((CANVAS - img.width) // 2, (CANVAS - img.height) // 2)
    canvas.paste(img, offset)

    buf = io.BytesIO()
    canvas.save(buf, format="WEBP", quality=_WEBP_QUALITY, method=6)
    return buf.getvalue()


def _flatten_to_rgb(img: Image.Image) -> Image.Image:
    """Aplana transparencia sobre fondo blanco y devuelve una imagen RGB."""
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, _WHITE)
        bg.paste(rgba, mask=rgba.split()[-1])
        return bg
    return img.convert("RGB")

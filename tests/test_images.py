"""Tests del tratamiento de imágenes de productos (Pillow).

app.config se instancia al importar, así que seteamos env vars dummy antes.
"""

import io
import os

os.environ.setdefault("META_APP_ID", "test-app-id")
os.environ.setdefault("META_APP_SECRET", "test-app-secret")
os.environ.setdefault("META_VERIFY_TOKEN", "test-verify-token")
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "x.eyJyb2xlIjogInNlcnZpY2Vfcm9sZSJ9.y")
os.environ.setdefault("ENCRYPTION_KEY", "oZRrOD525wcQ0CJveupENSX1tDwKfP6e1XrDGn9P1Kw=")

import pytest
from PIL import Image

from app.services import images
from app.services.erp.exceptions import ValidationError


def _png_bytes(size=(800, 400), color=(255, 0, 0), mode="RGB"):
    img = Image.new(mode, size, color if mode == "RGB" else color + (255,))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_optimize_returns_square_webp():
    out = images.optimize_image(_png_bytes((800, 400)))
    reopened = Image.open(io.BytesIO(out))
    assert reopened.format == "WEBP"
    assert reopened.size == (images.CANVAS, images.CANVAS)


def test_optimize_pads_with_white_background():
    # Imagen apaisada: las bandas arriba/abajo deben quedar blancas tras encuadrar.
    out = images.optimize_image(_png_bytes((1000, 200), color=(0, 0, 255)))
    reopened = Image.open(io.BytesIO(out)).convert("RGB")
    assert reopened.getpixel((images.CANVAS // 2, 2)) == (255, 255, 255)


def test_optimize_flattens_transparency_onto_white():
    out = images.optimize_image(_png_bytes((400, 400), color=(0, 0, 0), mode="RGBA"))
    reopened = Image.open(io.BytesIO(out))
    assert reopened.mode == "RGB"  # WebP opaco, sin canal alfa


def test_optimize_rejects_non_image():
    with pytest.raises(ValidationError):
        images.optimize_image(b"esto no es una imagen")


def test_optimize_rejects_empty():
    with pytest.raises(ValidationError):
        images.optimize_image(b"")


def test_optimize_rejects_oversized():
    with pytest.raises(ValidationError):
        images.optimize_image(b"x" * (images.MAX_BYTES + 1))

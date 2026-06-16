"""Unit tests for media transcription/image preparation."""

import os

os.environ.setdefault("META_APP_ID", "test-app-id")
os.environ.setdefault("META_APP_SECRET", "test-app-secret")
os.environ.setdefault("META_VERIFY_TOKEN", "test-verify-token")
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "x.eyJyb2xlIjogInNlcnZpY2Vfcm9sZSJ9.y")
os.environ.setdefault("ENCRYPTION_KEY", "oZRrOD525wcQ0CJveupENSX1tDwKfP6e1XrDGn9P1Kw=")
os.environ.setdefault("AGNO_DB_URL", "postgresql+psycopg://ai:ai@localhost:5532/ai")

from agno.media import Image

from app.ai.media.transcription import prepare_images


def test_prepare_images_only_image_types(tmp_path):
    img = tmp_path / "a.jpg"
    img.write_bytes(b"x")
    media = [
        {"type": "image", "local_path": str(img)},
        {"type": "document", "local_path": str(tmp_path / "b.pdf")},
    ]
    images = prepare_images(media)
    assert len(images) == 1
    assert isinstance(images[0], Image)


def test_prepare_images_empty():
    assert prepare_images(None) == []

import os

os.environ.setdefault("META_APP_ID", "test-app-id")
os.environ.setdefault("META_APP_SECRET", "test-app-secret")
os.environ.setdefault("META_VERIFY_TOKEN", "test-verify-token")
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "x.eyJyb2xlIjogInNlcnZpY2Vfcm9sZSJ9.y")
os.environ.setdefault("ENCRYPTION_KEY", "oZRrOD525wcQ0CJveupENSX1tDwKfP6e1XrDGn9P1Kw=")

from pydantic_ai import BinaryContent

from app.ai.media import prepare_images


def test_prepare_images_reads_local_file(tmp_path):
    img = tmp_path / "test.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg")
    out = prepare_images([{"type": "image", "local_path": str(img)}])
    assert len(out) == 1
    assert isinstance(out[0], BinaryContent)
    assert out[0].media_type == "image/jpeg"


def test_prepare_images_skips_non_images():
    assert prepare_images([{"type": "audio", "local_path": "/x"}]) == []
    assert prepare_images(None) == []

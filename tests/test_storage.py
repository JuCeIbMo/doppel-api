"""Tests de subida de imágenes a Supabase Storage."""

import os

os.environ.setdefault("META_APP_ID", "test-app-id")
os.environ.setdefault("META_APP_SECRET", "test-app-secret")
os.environ.setdefault("META_VERIFY_TOKEN", "test-verify-token")
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "x.eyJyb2xlIjogInNlcnZpY2Vfcm9sZSJ9.y")
os.environ.setdefault("ENCRYPTION_KEY", "oZRrOD525wcQ0CJveupENSX1tDwKfP6e1XrDGn9P1Kw=")

from app.services import storage


class _FakeBucket:
    def __init__(self):
        self.uploaded = None
        self.public_arg = None

    def upload(self, path, file, file_options=None):
        self.uploaded = {"path": path, "file": file, "file_options": file_options}

    def get_public_url(self, path):
        self.public_arg = path
        return f"https://cdn.test/{path}"


class _FakeStorage:
    def __init__(self, bucket):
        self._bucket = bucket
        self.from_arg = None

    def from_(self, name):
        self.from_arg = name
        return self._bucket


class _FakeSupabase:
    def __init__(self, storage_obj):
        self.storage = storage_obj


def test_upload_returns_public_url(monkeypatch):
    bucket = _FakeBucket()
    monkeypatch.setattr(storage, "get_supabase", lambda: _FakeSupabase(_FakeStorage(bucket)))

    url = storage.upload_product_image("t1", b"webp-bytes")

    assert url.startswith("https://cdn.test/")
    assert bucket.uploaded["file"] == b"webp-bytes"
    assert bucket.uploaded["path"].startswith("t1/")
    assert bucket.uploaded["path"].endswith(".webp")
    assert bucket.uploaded["file_options"]["content-type"] == "image/webp"
    # La URL pública se pide sobre el mismo path que se subió.
    assert bucket.public_arg == bucket.uploaded["path"]


def test_upload_uses_configured_bucket(monkeypatch):
    fake_storage = _FakeStorage(_FakeBucket())
    monkeypatch.setattr(storage, "get_supabase", lambda: _FakeSupabase(fake_storage))
    monkeypatch.setattr(storage.settings, "PRODUCT_IMAGES_BUCKET", "mi-bucket")

    storage.upload_product_image("t9", b"x")
    assert fake_storage.from_arg == "mi-bucket"

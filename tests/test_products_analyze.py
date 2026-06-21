"""Tests del endpoint POST /erp/products/analyze-image."""

import os

os.environ.setdefault("META_APP_ID", "test-app-id")
os.environ.setdefault("META_APP_SECRET", "test-app-secret")
os.environ.setdefault("META_VERIFY_TOKEN", "test-verify-token")
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "x.eyJyb2xlIjogInNlcnZpY2Vfcm9sZSJ9.y")
os.environ.setdefault("ENCRYPTION_KEY", "oZRrOD525wcQ0CJveupENSX1tDwKfP6e1XrDGn9P1Kw=")
os.environ.setdefault("AGNO_DB_URL", "postgresql+psycopg://ai:ai@localhost:5532/ai")

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.erp.context import ERPContext, get_erp_context
from app.services.erp.exceptions import ValidationError


@pytest.fixture
def client(monkeypatch):
    app.dependency_overrides[get_erp_context] = lambda: ERPContext(
        tenant_id="t1", actor="owner", actor_label="Dueño"
    )
    monkeypatch.setattr("app.routers.erp.products.log_activity", lambda *a, **k: None)
    yield TestClient(app)
    app.dependency_overrides.clear()


def _patch_pipeline(monkeypatch, *, analysis):
    monkeypatch.setattr("app.routers.erp.products.optimize_image", lambda raw: b"webp")
    monkeypatch.setattr(
        "app.routers.erp.products.upload_product_image",
        lambda tenant_id, data: "https://cdn.test/t1/abc.webp",
    )
    monkeypatch.setattr(
        "app.routers.erp.products.analyze_product_image",
        lambda data, content_type: analysis,
    )


def test_analyze_image_returns_suggestions(client, monkeypatch):
    _patch_pipeline(monkeypatch, analysis={
        "ai_ok": True, "name": "Coca 500ml",
        "description": "Gaseosa fría", "tags": ["bebida", "gaseosa"]})

    resp = client.post(
        "/erp/products/analyze-image",
        files={"file": ("foto.jpg", b"raw-bytes", "image/jpeg")},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "image_url": "https://cdn.test/t1/abc.webp",
        "name": "Coca 500ml",
        "description": "Gaseosa fría",
        "tags": ["bebida", "gaseosa"],
        "ai_ok": True,
    }


def test_analyze_image_returns_url_even_when_ai_fails(client, monkeypatch):
    _patch_pipeline(monkeypatch, analysis={
        "ai_ok": False, "name": None, "description": None, "tags": []})

    resp = client.post(
        "/erp/products/analyze-image",
        files={"file": ("foto.jpg", b"raw-bytes", "image/jpeg")},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["image_url"] == "https://cdn.test/t1/abc.webp"
    assert body["ai_ok"] is False
    assert body["name"] is None
    assert body["tags"] == []


def test_analyze_image_rejects_invalid_image(client, monkeypatch):
    def _boom(raw):
        raise ValidationError("El archivo no es una imagen válida")

    monkeypatch.setattr("app.routers.erp.products.optimize_image", _boom)

    resp = client.post(
        "/erp/products/analyze-image",
        files={"file": ("foto.txt", b"not-an-image", "text/plain")},
    )
    assert resp.status_code == 422

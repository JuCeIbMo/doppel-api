"""Tests del análisis de imágenes con Gemini (autodescripción/etiquetado).

Sin red: se mockea el cliente genai. app.config se instancia al importar.
"""

import json
import os

os.environ.setdefault("META_APP_ID", "test-app-id")
os.environ.setdefault("META_APP_SECRET", "test-app-secret")
os.environ.setdefault("META_VERIFY_TOKEN", "test-verify-token")
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "x.eyJyb2xlIjogInNlcnZpY2Vfcm9sZSJ9.y")
os.environ.setdefault("ENCRYPTION_KEY", "oZRrOD525wcQ0CJveupENSX1tDwKfP6e1XrDGn9P1Kw=")

from app.services import vision


class _FakeResponse:
    def __init__(self, text):
        self.text = text


class _FakeModels:
    def __init__(self, text=None, exc=None):
        self._text = text
        self._exc = exc
        self.called_with = None

    def generate_content(self, **kwargs):
        self.called_with = kwargs
        if self._exc:
            raise self._exc
        return _FakeResponse(self._text)


class _FakeClient:
    def __init__(self, models):
        self.models = models


def test_analyze_happy_path(monkeypatch):
    payload = {"name": "Coca-Cola 500ml", "description": "Gaseosa cola bien fría.",
               "tags": ["bebida", "gaseosa", "cola"]}
    models = _FakeModels(text=json.dumps(payload))
    monkeypatch.setattr(vision.settings, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(vision, "_get_client", lambda: _FakeClient(models))

    result = vision.analyze_product_image(b"img", "image/webp")

    assert result["ai_ok"] is True
    assert result["name"] == "Coca-Cola 500ml"
    assert result["description"] == "Gaseosa cola bien fría."
    assert result["tags"] == ["bebida", "gaseosa", "cola"]


def test_analyze_without_key_skips_network(monkeypatch):
    monkeypatch.setattr(vision.settings, "GEMINI_API_KEY", "")

    def _boom():
        raise AssertionError("no debe construir el cliente sin API key")

    monkeypatch.setattr(vision, "_get_client", _boom)
    result = vision.analyze_product_image(b"img", "image/webp")

    assert result == {"ai_ok": False, "name": None, "description": None, "tags": []}


def test_analyze_handles_gemini_failure(monkeypatch):
    models = _FakeModels(exc=RuntimeError("gemini down"))
    monkeypatch.setattr(vision.settings, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(vision, "_get_client", lambda: _FakeClient(models))

    result = vision.analyze_product_image(b"img", "image/webp")
    assert result["ai_ok"] is False
    assert result["tags"] == []


def test_analyze_handles_malformed_json(monkeypatch):
    models = _FakeModels(text="no soy json {")
    monkeypatch.setattr(vision.settings, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(vision, "_get_client", lambda: _FakeClient(models))

    result = vision.analyze_product_image(b"img", "image/webp")
    assert result["ai_ok"] is False


def test_analyze_normalizes_tags(monkeypatch):
    payload = {"name": "X", "description": "y",
               "tags": ["  Bebida ", "BEBIDA", "", "Gaseosa", "cola", "a", "b", "c", "d", "e", "f"]}
    models = _FakeModels(text=json.dumps(payload))
    monkeypatch.setattr(vision.settings, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(vision, "_get_client", lambda: _FakeClient(models))

    tags = vision.analyze_product_image(b"img", "image/webp")["tags"]
    assert tags[:3] == ["bebida", "gaseosa", "cola"]  # minúsculas, trim, dedupe
    assert len(tags) <= 10
    assert "" not in tags

"""Tests del análisis de imágenes con Gemini (autodescripción/etiquetado).

Sin red: se mockea el cliente genai.; `tests/conftest.py` carga la configuración.
"""

import asyncio
import json

from app.services import vision

class _FakeResponse:
    def __init__(self, text):
        self.text = text

class _FakeModels:
    def __init__(self, text=None, exc=None):
        self._text = text
        self._exc = exc
        self.called_with = None

    async def generate_content(self, **kwargs):
        self.called_with = kwargs
        if self._exc:
            raise self._exc
        return _FakeResponse(self._text)

class _FakeAio:
    def __init__(self, models):
        self.models = models

class _FakeClient:
    """El código llama `client.aio.models.generate_content`, la variante async del
    SDK. `client.models` queda sin definir a propósito: si alguien vuelve al
    cliente síncrono (que bloquea el event loop), estos tests explotan."""

    def __init__(self, models):
        self.aio = _FakeAio(models)

def _analyze(*args, **kwargs):
    return asyncio.run(vision.analyze_product_image(*args, **kwargs))

def test_analyze_happy_path(monkeypatch):
    payload = {"name": "Coca-Cola 500ml", "description": "Gaseosa cola bien fría.",
               "tags": ["bebida", "gaseosa", "cola"]}
    models = _FakeModels(text=json.dumps(payload))
    monkeypatch.setattr(vision.settings, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(vision, "_get_client", lambda: _FakeClient(models))

    result = _analyze(b"img", "image/webp")

    assert result["ai_ok"] is True
    assert result["name"] == "Coca-Cola 500ml"
    assert result["description"] == "Gaseosa cola bien fría."
    assert result["tags"] == ["bebida", "gaseosa", "cola"]

def test_analyze_without_key_skips_network(monkeypatch):
    monkeypatch.setattr(vision.settings, "GEMINI_API_KEY", "")

    def _boom():
        raise AssertionError("no debe construir el cliente sin API key")

    monkeypatch.setattr(vision, "_get_client", _boom)
    result = _analyze(b"img", "image/webp")

    assert result == {"ai_ok": False, "name": None, "description": None, "tags": []}

def test_analyze_handles_gemini_failure(monkeypatch):
    models = _FakeModels(exc=RuntimeError("gemini down"))
    monkeypatch.setattr(vision.settings, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(vision, "_get_client", lambda: _FakeClient(models))

    result = _analyze(b"img", "image/webp")
    assert result["ai_ok"] is False
    assert result["tags"] == []

def test_analyze_handles_malformed_json(monkeypatch):
    models = _FakeModels(text="no soy json {")
    monkeypatch.setattr(vision.settings, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(vision, "_get_client", lambda: _FakeClient(models))

    result = _analyze(b"img", "image/webp")
    assert result["ai_ok"] is False

def test_analyze_normalizes_tags(monkeypatch):
    payload = {"name": "X", "description": "y",
               "tags": ["  Bebida ", "BEBIDA", "", "Gaseosa", "cola", "a", "b", "c", "d", "e", "f"]}
    models = _FakeModels(text=json.dumps(payload))
    monkeypatch.setattr(vision.settings, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(vision, "_get_client", lambda: _FakeClient(models))

    tags = _analyze(b"img", "image/webp")["tags"]
    assert tags[:3] == ["bebida", "gaseosa", "cola"]  # minúsculas, trim, dedupe
    assert len(tags) <= 10
    assert "" not in tags

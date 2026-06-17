"""Unit tests for the shared agent factory base helpers.

app.config instantiates Settings() at import time (transitively via
app.ai.config), requiring these env vars. Set safe test defaults before import.
"""

import os

os.environ.setdefault("META_APP_ID", "test-app-id")
os.environ.setdefault("META_APP_SECRET", "test-app-secret")
os.environ.setdefault("META_VERIFY_TOKEN", "test-verify-token")
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "x.eyJyb2xlIjogInNlcnZpY2Vfcm9sZSJ9.y")
os.environ.setdefault("ENCRYPTION_KEY", "oZRrOD525wcQ0CJveupENSX1tDwKfP6e1XrDGn9P1Kw=")

from agno.models.anthropic import Claude
from agno.models.openai import OpenAIChat

from app.ai.config import DEFAULT_MODEL
from app.ai.factories.base import build_model, session_id_for


def test_session_id_combines_tenant_and_phone():
    assert session_id_for("tenant123", "+57300") == "tenant123:+57300"


def test_build_model_routes_claude_ids_to_anthropic():
    model = build_model("claude-3-5-haiku-latest")
    assert isinstance(model, Claude)
    assert model.id == "claude-3-5-haiku-latest"


def test_build_model_routes_gpt_ids_to_openai():
    # bot_configs.ai_model = "gpt-4o-mini" debe usar OpenAI de verdad, no Anthropic.
    model = build_model("gpt-4o-mini")
    assert isinstance(model, OpenAIChat)
    assert model.id == "gpt-4o-mini"


def test_build_model_routes_o_series_to_openai():
    assert isinstance(build_model("o3-mini"), OpenAIChat)


def test_build_model_falls_back_to_default_when_id_missing():
    assert build_model(None).id == DEFAULT_MODEL
    assert build_model("").id == DEFAULT_MODEL


def test_build_model_unknown_provider_uses_default():
    # id de proveedor no soportado (p.ej. gemini) cae al modelo por defecto.
    assert build_model("gemini-2.0-flash-001").id == DEFAULT_MODEL

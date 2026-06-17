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

from app.ai.config import DEFAULT_MODEL
from app.ai.factories.base import build_model, session_id_for


def test_session_id_combines_tenant_and_phone():
    assert session_id_for("tenant123", "+57300") == "tenant123:+57300"


def test_build_model_keeps_valid_claude_id():
    assert build_model("claude-3-5-haiku-latest").id == "claude-3-5-haiku-latest"


def test_build_model_falls_back_when_id_missing():
    assert build_model(None).id == DEFAULT_MODEL
    assert build_model("").id == DEFAULT_MODEL


def test_build_model_rejects_non_claude_ids():
    # ai_model heredado de configs viejas (OpenAI/Gemini) haría que Anthropic
    # devuelva 404; debe degradar al modelo por defecto en vez de romper.
    assert build_model("gpt-4o-mini").id == DEFAULT_MODEL
    assert build_model("gemini-2.0-flash-001").id == DEFAULT_MODEL

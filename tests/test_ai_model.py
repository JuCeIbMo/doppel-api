import os

os.environ.setdefault("META_APP_ID", "test-app-id")
os.environ.setdefault("META_APP_SECRET", "test-app-secret")
os.environ.setdefault("META_VERIFY_TOKEN", "test-verify-token")
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "x.eyJyb2xlIjogInNlcnZpY2Vfcm9sZSJ9.y")
os.environ.setdefault("ENCRYPTION_KEY", "oZRrOD525wcQ0CJveupENSX1tDwKfP6e1XrDGn9P1Kw=")

from app.ai.model import model_string


def test_claude_routes_to_anthropic():
    assert model_string("claude-sonnet-4-20250514") == "anthropic:claude-sonnet-4-20250514"


def test_gpt_routes_to_openai():
    assert model_string("gpt-4o") == "openai:gpt-4o"


def test_unknown_falls_back_to_default_anthropic():
    assert model_string("desconocido").startswith("anthropic:")

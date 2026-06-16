"""Unit tests for the client agent factory.

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
os.environ.setdefault("AGNO_DB_URL", "postgresql+psycopg://ai:ai@localhost:5532/ai")

from agno.agent import Agent

from app.ai.factories.client_agent import get_client_agent


class _FakeSupabase:
    def table(self, _n):
        raise AssertionError("no se debe llamar al construir")


def test_get_client_agent_sets_identity():
    agent = get_client_agent(
        tenant_id="t1", user_phone="+57300", system_prompt="Eres un bot",
        model_id="claude-sonnet-4-20250514", supabase=_FakeSupabase(),
    )
    assert isinstance(agent, Agent)
    assert agent.user_id == "+57300"
    assert agent.session_id == "t1:+57300"

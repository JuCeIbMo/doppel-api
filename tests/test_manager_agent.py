"""Unit tests for the manager agent factory."""

import os

os.environ.setdefault("META_APP_ID", "test-app-id")
os.environ.setdefault("META_APP_SECRET", "test-app-secret")
os.environ.setdefault("META_VERIFY_TOKEN", "test-verify-token")
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "x.eyJyb2xlIjogInNlcnZpY2Vfcm9sZSJ9.y")
os.environ.setdefault("ENCRYPTION_KEY", "oZRrOD525wcQ0CJveupENSX1tDwKfP6e1XrDGn9P1Kw=")
os.environ.setdefault("AGNO_DB_URL", "postgresql+psycopg://ai:ai@localhost:5532/ai")

from agno.agent import Agent

from app.ai.factories.manager_agent import get_manager_agent


def test_get_manager_agent_sets_identity():
    agent = get_manager_agent(
        tenant_id="t1", user_phone="+57999", system_prompt="Eres el admin bot",
        model_id="claude-sonnet-4-20250514",
    )
    assert isinstance(agent, Agent)
    assert agent.user_id == "+57999"
    assert agent.session_id == "t1:+57999"

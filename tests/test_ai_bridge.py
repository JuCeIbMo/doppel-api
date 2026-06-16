"""Unit tests for the AI bridge respond() entry point."""

import os

os.environ.setdefault("META_APP_ID", "test-app-id")
os.environ.setdefault("META_APP_SECRET", "test-app-secret")
os.environ.setdefault("META_VERIFY_TOKEN", "test-verify-token")
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "x.eyJyb2xlIjogInNlcnZpY2Vfcm9sZSJ9.y")
os.environ.setdefault("ENCRYPTION_KEY", "oZRrOD525wcQ0CJveupENSX1tDwKfP6e1XrDGn9P1Kw=")
os.environ.setdefault("AGNO_DB_URL", "postgresql+psycopg://ai:ai@localhost:5532/ai")

import asyncio
from unittest.mock import AsyncMock, patch

from app.ai import bridge


class _FakeRun:
    def __init__(self, content): self.content = content


class _FakeAgent:
    def __init__(self, reply): self._reply = reply
    async def arun(self, *a, **k): return _FakeRun(self._reply)


def _run(mode, content, media=None):
    with patch.object(bridge, "get_client_agent", return_value=_FakeAgent("hola cliente")), \
         patch.object(bridge, "get_manager_agent", return_value=_FakeAgent("hola admin")), \
         patch.object(bridge, "transcribe_audio_media", new=AsyncMock(return_value="")), \
         patch.object(bridge, "prepare_images", return_value=[]):
        return asyncio.run(bridge.respond(
            mode=mode, tenant_id="t1", user_phone="+57300",
            content=content, system_prompt="p", model="m",
            supabase=object(), media=media,
        ))


def test_client_mode_uses_client_agent():
    assert _run("client", "hola") == "hola cliente"


def test_manager_mode_uses_manager_agent():
    assert _run("manager", "hola") == "hola admin"


def test_empty_reply_on_agent_error():
    with patch.object(bridge, "get_client_agent", side_effect=RuntimeError("boom")), \
         patch.object(bridge, "transcribe_audio_media", new=AsyncMock(return_value="")), \
         patch.object(bridge, "prepare_images", return_value=[]):
        out = asyncio.run(bridge.respond(
            mode="client", tenant_id="t1", user_phone="+57300",
            content="hola", system_prompt="p", model="m", supabase=object(), media=None,
        ))
    assert out == ""

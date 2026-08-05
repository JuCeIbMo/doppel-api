"""Regression tests for the Redis checkpointer and the agent cache."""

import os

os.environ.setdefault("META_APP_ID", "test-app-id")
os.environ.setdefault("META_APP_SECRET", "test-app-secret")
os.environ.setdefault("META_VERIFY_TOKEN", "test-verify-token")
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "x.eyJyb2xlIjogInNlcnZpY2Vfcm9sZSJ9.y")
os.environ.setdefault("ENCRYPTION_KEY", "oZRrOD525wcQ0CJveupENSX1tDwKfP6e1XrDGn9P1Kw=")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import asyncio
import inspect

from app.ai_core import bridge
from app.ai_core.config.tenant import AdminAgentConfig, PublicAgentConfig, TenantConfig
from app.ai_core.persistence import checkpointer as cp


def _tenant(tenant_id: str = "t1") -> TenantConfig:
    return TenantConfig(
        tenant_id=tenant_id,
        business_name="Kiosco",
        public_agent=PublicAgentConfig(),
        admin_agent=AdminAgentConfig(allowed_numbers=["59170000001"]),
    )


def test_checkpointer_uses_one_shared_redis_saver(monkeypatch):
    opened: list[str] = []
    saver = object()

    class FakeContext:
        async def __aenter__(self):
            return saver

        async def __aexit__(self, *_args):
            return None

    class FakeRedisSaver:
        @classmethod
        def from_conn_string(cls, url):
            opened.append(url)
            return FakeContext()

    monkeypatch.setattr(cp, "AsyncRedisSaver", FakeRedisSaver)
    monkeypatch.setattr(cp, "_saver", None)
    monkeypatch.setattr(cp, "_saver_context", None)
    monkeypatch.setattr(cp, "get_redis_url", lambda: "redis://test:6379/0")

    async def scenario():
        return await cp.open_checkpointer(), await cp.open_checkpointer()

    first, second = asyncio.run(scenario())
    assert first is saver and second is saver
    assert opened == ["redis://test:6379/0"]


def test_close_pool_closes_redis_and_resets_state(monkeypatch):
    closed = False

    class FakeContext:
        async def __aexit__(self, *_args):
            nonlocal closed
            closed = True

    monkeypatch.setattr(cp, "_saver", object())
    monkeypatch.setattr(cp, "_saver_context", FakeContext())
    asyncio.run(cp.close_pool())

    assert closed
    assert cp._saver is None
    assert cp._saver_context is None


def test_lifespan_closes_the_checkpointer():
    import app.main as main

    assert inspect.iscoroutinefunction(cp.close_pool)
    assert "close_pool" in inspect.getsource(main.lifespan)


def test_failed_turn_evicts_the_cached_agent(monkeypatch):
    tenant = _tenant()
    builds = 0

    async def fake_build_public_agent(_tenant):
        nonlocal builds
        builds += 1
        return object()

    async def fail(*_args, **_kwargs):
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr(bridge, "load_tenant_config", lambda _id: _async(tenant))
    monkeypatch.setattr(bridge, "build_public_agent", fake_build_public_agent)
    monkeypatch.setattr(bridge, "run_public_agent_turn", fail)
    monkeypatch.setattr(bridge, "resolve_role", lambda *_args: "public")
    monkeypatch.setattr(bridge, "_agents", {})

    async def scenario():
        return [
            await bridge.respond(tenant_id="t1", user_phone="+999", content="hola"),
            await bridge.respond(tenant_id="t1", user_phone="+999", content="hola"),
        ]

    replies = asyncio.run(scenario())
    assert [reply.ok for reply in replies] == [False, False]
    assert builds == 2


async def _async(value):
    return value


def test_agent_cache_rebuilds_when_config_changes(monkeypatch):
    builds: list[str] = []

    async def fake_build_public_agent(tenant):
        builds.append(tenant.business_name)
        return object()

    monkeypatch.setattr(bridge, "build_public_agent", fake_build_public_agent)
    monkeypatch.setattr(bridge, "_agents", {})
    renamed = _tenant()
    renamed.business_name = "Kiosco Nuevo"

    async def scenario():
        await bridge._get_or_build_agent(_tenant(), "public")
        await bridge._get_or_build_agent(renamed, "public")

    asyncio.run(scenario())
    assert builds == ["Kiosco", "Kiosco Nuevo"]


def test_successful_turn_keeps_the_agent_cached(monkeypatch):
    tenant = _tenant()
    builds = 0

    async def fake_build_public_agent(_tenant):
        nonlocal builds
        builds += 1
        return object()

    class Reply:
        content = "listo"

    monkeypatch.setattr(bridge, "load_tenant_config", lambda _id: _async(tenant))
    monkeypatch.setattr(bridge, "build_public_agent", fake_build_public_agent)
    monkeypatch.setattr(
        bridge, "run_public_agent_turn", lambda *_args, **_kwargs: _async({"messages": [Reply()]})
    )
    monkeypatch.setattr(bridge, "resolve_role", lambda *_args: "public")
    monkeypatch.setattr(bridge, "_agents", {})

    async def scenario():
        return [
            await bridge.respond(tenant_id="t1", user_phone="+999", content="hola"),
            await bridge.respond(tenant_id="t1", user_phone="+999", content="hola"),
        ]

    assert [reply.text for reply in asyncio.run(scenario())] == ["listo", "listo"]
    assert builds == 1


def test_agent_cache_is_bounded(monkeypatch):
    async def fake_build_public_agent(_tenant):
        return object()

    monkeypatch.setattr(bridge, "build_public_agent", fake_build_public_agent)
    monkeypatch.setattr(bridge, "_agents", {})
    monkeypatch.setattr(bridge, "MAX_CACHED_AGENTS", 3)

    async def scenario():
        for i in range(6):
            await bridge._get_or_build_agent(_tenant(f"t{i}"), "public")

    asyncio.run(scenario())
    assert len(bridge._agents) == 3
    assert ("t5", "public") in bridge._agents
    assert ("t0", "public") not in bridge._agents

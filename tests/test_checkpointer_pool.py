"""Regression tests for the checkpointer pool and the agent-cache eviction.

Both cover the same failure mode: the bot going permanently silent for a tenant
after one dropped Postgres connection.

1. `open_checkpointer` used to call `AsyncPostgresSaver.from_conn_string`, which
   opens a single raw `AsyncConnection`. psycopg never reconnects one, so once
   it died every later turn for that tenant failed. It must go through a shared
   `AsyncConnectionPool`, which replaces broken connections itself.
2. `bridge._agents` cached the agent — and its connection — forever, and
   `respond` swallowed the exception without evicting. That turned any failure
   into a permanent outage, invisible to the customer because `respond` returns
   `None` and the webhook then sends nothing.

app.config instantiates Settings() at import time, requiring these env vars.
Set safe test defaults before import.
"""

import os

os.environ.setdefault("META_APP_ID", "test-app-id")
os.environ.setdefault("META_APP_SECRET", "test-app-secret")
os.environ.setdefault("META_VERIFY_TOKEN", "test-verify-token")
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "x.eyJyb2xlIjogInNlcnZpY2Vfcm9sZSJ9.y")
os.environ.setdefault("ENCRYPTION_KEY", "oZRrOD525wcQ0CJveupENSX1tDwKfP6e1XrDGn9P1Kw=")
os.environ.setdefault("CHAT_DB_URL", "postgresql://ai:ai@localhost:5532/chat")

import asyncio
import inspect

import pytest
from psycopg_pool import AsyncConnectionPool

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


# --------------------------------------------------------------------------
# 1. The checkpointer must sit on a pool, not a bare connection
# --------------------------------------------------------------------------


def test_checkpointer_uses_a_shared_pool(monkeypatch):
    """A bare AsyncConnection never reconnects; only a pool self-heals."""
    opened: list[dict] = []

    class FakePool:
        closed = False

        def __init__(self, **kwargs):
            opened.append(kwargs)

        async def open(self, wait=False):
            return None

        async def close(self):
            FakePool.closed = True

    saver_conns: list[object] = []

    class FakeSaver:
        def __init__(self, conn=None):
            saver_conns.append(conn)

        async def setup(self):
            return None

    monkeypatch.setattr(cp, "AsyncConnectionPool", FakePool)
    monkeypatch.setattr(cp, "AsyncPostgresSaver", FakeSaver)
    monkeypatch.setattr(cp, "_pool", None)
    monkeypatch.setattr(cp, "_setup_done", False)

    async def scenario():
        first = await cp.open_checkpointer()
        second = await cp.open_checkpointer()
        return first, second

    asyncio.run(scenario())

    # One pool for the whole process, reused by every agent.
    assert len(opened) == 1, "each agent opened its own pool"
    assert len(saver_conns) == 2
    assert saver_conns[0] is saver_conns[1], "savers must share the same pool"
    assert isinstance(saver_conns[0], FakePool)


def test_pool_validates_connections_before_handing_them_out(monkeypatch):
    """Without `check`, a stale connection is still served once and that turn dies."""
    captured: dict = {}

    class FakePool:
        closed = False

        def __init__(self, **kwargs):
            captured.update(kwargs)

        async def open(self, wait=False):
            return None

    monkeypatch.setattr(cp, "AsyncConnectionPool", FakePool)
    monkeypatch.setattr(cp, "_pool", None)

    asyncio.run(cp.get_pool())

    assert captured["check"] is AsyncConnectionPool.check_connection
    assert cp.CHECK_CONNECTION is AsyncConnectionPool.check_connection
    # AsyncPostgresSaver runs its own transactions and needs dict rows.
    assert captured["kwargs"]["autocommit"] is True
    assert captured["kwargs"]["prepare_threshold"] == 0
    assert captured["max_size"] == cp.MAX_POOL_SIZE


def test_setup_runs_once_per_process(monkeypatch):
    """`.setup()` is idempotent but costs a round trip on every agent build."""
    setups = 0

    class FakePool:
        closed = False

        def __init__(self, **kwargs):
            pass

        async def open(self, wait=False):
            return None

    class FakeSaver:
        def __init__(self, conn=None):
            pass

        async def setup(self):
            nonlocal setups
            setups += 1

    monkeypatch.setattr(cp, "AsyncConnectionPool", FakePool)
    monkeypatch.setattr(cp, "AsyncPostgresSaver", FakeSaver)
    monkeypatch.setattr(cp, "_pool", None)
    monkeypatch.setattr(cp, "_setup_done", False)

    async def scenario():
        for _ in range(3):
            await cp.open_checkpointer()

    asyncio.run(scenario())
    assert setups == 1


def test_close_pool_is_async_and_resets_state(monkeypatch):
    """The lifespan must be able to release the pool on shutdown."""
    assert inspect.iscoroutinefunction(cp.close_pool)

    closed = False

    class FakePool:
        closed = False

        async def close(self):
            nonlocal closed
            closed = True

    monkeypatch.setattr(cp, "_pool", FakePool())
    monkeypatch.setattr(cp, "_setup_done", True)

    asyncio.run(cp.close_pool())

    assert closed
    assert cp._pool is None
    assert cp._setup_done is False


def test_lifespan_closes_the_pool():
    """A pool left open on shutdown leaks server-side Postgres connections."""
    import app.main as main

    source = inspect.getsource(main.lifespan)
    assert "close_pool" in source, "app lifespan never releases the checkpointer pool"


# --------------------------------------------------------------------------
# 2. A failed turn must not poison the cache forever
# --------------------------------------------------------------------------


def test_failed_turn_evicts_the_cached_agent(monkeypatch):
    """The whole point: a broken agent must not survive into the next message."""
    tenant = _tenant()
    builds = 0

    class BrokenAgent:
        pass

    async def fake_load_tenant_config(tenant_id):
        return tenant

    async def fake_build_public_agent(_tenant):
        nonlocal builds
        builds += 1
        return BrokenAgent()

    async def fake_run_turn(agent, tenant, thread_id, text, message_id=None):
        raise RuntimeError("the connection is closed")

    monkeypatch.setattr(bridge, "load_tenant_config", fake_load_tenant_config)
    monkeypatch.setattr(bridge, "build_public_agent", fake_build_public_agent)
    monkeypatch.setattr(bridge, "run_public_agent_turn", fake_run_turn)
    monkeypatch.setattr(bridge, "resolve_role", lambda phone, tenant: "public")
    monkeypatch.setattr(bridge, "_agents", {})

    async def scenario():
        return [
            await bridge.respond(tenant_id="t1", user_phone="+999", content="hola"),
            await bridge.respond(tenant_id="t1", user_phone="+999", content="hola"),
        ]

    replies = asyncio.run(scenario())

    # `ok=False` on both: the customer gets silence, which is exactly why a
    # permanently cached broken agent went unnoticed before.
    assert [reply.ok for reply in replies] == [False, False]
    # But the agent was rebuilt, so a transient failure stays transient.
    assert builds == 2, "the broken agent stayed cached after the failure"
    assert bridge._agents == {}


def test_successful_turn_keeps_the_agent_cached(monkeypatch):
    """Eviction must not turn the cache into a per-message rebuild."""
    tenant = _tenant()
    builds = 0

    async def fake_load_tenant_config(tenant_id):
        return tenant

    async def fake_build_public_agent(_tenant):
        nonlocal builds
        builds += 1
        return object()

    class Reply:
        content = "listo"

    async def fake_run_turn(agent, tenant, thread_id, text, message_id=None):
        return {"messages": [Reply()]}

    monkeypatch.setattr(bridge, "load_tenant_config", fake_load_tenant_config)
    monkeypatch.setattr(bridge, "build_public_agent", fake_build_public_agent)
    monkeypatch.setattr(bridge, "run_public_agent_turn", fake_run_turn)
    monkeypatch.setattr(bridge, "resolve_role", lambda phone, tenant: "public")
    monkeypatch.setattr(bridge, "_agents", {})

    async def scenario():
        return [
            await bridge.respond(tenant_id="t1", user_phone="+999", content="hola"),
            await bridge.respond(tenant_id="t1", user_phone="+999", content="hola"),
        ]

    assert [reply.text for reply in asyncio.run(scenario())] == ["listo", "listo"]
    assert builds == 1


def test_config_change_rebuilds_the_agent(monkeypatch):
    """Otherwise a bot_configs edit never reaches a running process."""
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
        await bridge._get_or_build_agent(_tenant(), "public")  # unchanged: cached
        await bridge._get_or_build_agent(renamed, "public")    # changed: rebuilt

    asyncio.run(scenario())

    assert builds == ["Kiosco", "Kiosco Nuevo"]
    assert len(bridge._agents) == 1, "the rebuild must replace, not duplicate"


def test_tool_allowlist_change_rebuilds_the_agent(monkeypatch):
    """The fingerprint must cover what is bound, not just the display name."""
    builds = 0

    async def fake_build_public_agent(_tenant):
        nonlocal builds
        builds += 1
        return object()

    monkeypatch.setattr(bridge, "build_public_agent", fake_build_public_agent)
    monkeypatch.setattr(bridge, "_agents", {})

    restricted = _tenant()
    restricted.public_agent.allowed_tools = ["search_catalog"]

    async def scenario():
        await bridge._get_or_build_agent(_tenant(), "public")
        await bridge._get_or_build_agent(restricted, "public")

    asyncio.run(scenario())
    assert builds == 2


def test_agent_cache_is_bounded(monkeypatch):
    """An unbounded cache grows one agent per tenant for the life of the process."""
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
    # Oldest entries dropped first.
    assert ("t5", "public") in bridge._agents
    assert ("t0", "public") not in bridge._agents

"""Invariants of the agent core that nothing else enforces.

Each of these was a real finding from the Agno -> LangChain port review:

- `check_stock` returned quantity 0 for a product id that does not exist, so a
  hallucinated id read to the model as "sold out" and the customer was told
  there was no stock instead of the agent searching again.
- `MAX_TOOL_CALLS_PER_RUN` and `GRAPH_RECURSION_LIMIT` are tuned against each
  other by hand in a comment. Raise the tool cap alone and the graph raises
  `GraphRecursionError` *before* the soft cap can act — the soft cap blocks
  tools and still lets the model answer, the recursion limit leaves the
  customer with nothing.
- `trace_turn` wrote whole customer messages into `activity_log`, an audit
  table with no retention policy.
- Two messages from one customer ran two turns against the same checkpoint.

Shared test environment is loaded before collection by `tests/conftest.py`.
"""

import asyncio

import pytest

from app.ai_core import bridge
from app.ai_core.config.tenant import AdminAgentConfig, PublicAgentConfig, TenantConfig
from app.ai_core.observability import tracing
from app.ai_core.observability.langfuse import GRAPH_RECURSION_LIMIT
from app.ai_core.common.middleware import (
    MAX_CATALOG_SEARCHES_PER_RUN,
    MAX_TOOL_CALLS_PER_RUN,
)
from app.ai_core.tools.context import ToolContext
from app.ai_core.tools.stock import check_stock
from app.services.erp.exceptions import NotFound

TENANT = TenantConfig(
    tenant_id="t1",
    business_name="Kiosco",
    public_agent=PublicAgentConfig(),
    admin_agent=AdminAgentConfig(allowed_numbers=["59170000001"]),
)

def _ctx(role="public"):
    return ToolContext(tenant=TENANT, role=role, thread_id=f"t1:{role}:59170000002")

# --------------------------------------------------------------------------
# check_stock must not disguise a bad id as "sold out"
# --------------------------------------------------------------------------

def test_missing_product_is_reported_as_not_found(monkeypatch):
    async def raise_not_found(self, ctx, product_id):
        raise NotFound("Producto no encontrado", product_id=product_id)

    monkeypatch.setattr("app.ai_core.tools.stock.ProductsService.get", raise_not_found)

    result = asyncio.run(
        check_stock.ainvoke({"product_id": "hallucinated", "ctx": _ctx()})
    )
    assert result.found is False
    assert result.quantity == 0

def test_real_product_with_no_stock_is_still_found(monkeypatch):
    """The whole point of `found`: zero stock and a bad id must differ."""
    async def zero_stock(self, ctx, product_id):
        return {"id": product_id, "stock": 0}

    monkeypatch.setattr("app.ai_core.tools.stock.ProductsService.get", zero_stock)

    result = asyncio.run(check_stock.ainvoke({"product_id": "real", "ctx": _ctx()}))
    assert result.found is True
    assert result.quantity == 0

def test_check_stock_tells_the_model_what_found_means():
    """The flag only helps if the tool description explains it."""
    assert "found" in (check_stock.description or "")

# --------------------------------------------------------------------------
# The two anti-loop caps are tuned against each other by hand
# --------------------------------------------------------------------------

def test_tool_cap_fits_inside_the_graph_recursion_limit():
    """A specialist run of N tool calls costs 2N+1 supersteps.

    The soft cap must bite first: it blocks further tools and lets the model
    still produce an answer, while GraphRecursionError kills the turn and the
    customer gets nothing.
    """
    supersteps = 2 * MAX_TOOL_CALLS_PER_RUN + 1
    assert supersteps <= GRAPH_RECURSION_LIMIT, (
        f"MAX_TOOL_CALLS_PER_RUN={MAX_TOOL_CALLS_PER_RUN} needs {supersteps} "
        f"supersteps but GRAPH_RECURSION_LIMIT={GRAPH_RECURSION_LIMIT}. Raise "
        f"the recursion limit to at least {supersteps} or lower the tool cap."
    )

def test_catalog_search_cap_is_tighter_than_the_general_cap():
    """The per-tool cap is only meaningful below the overall one."""
    assert MAX_CATALOG_SEARCHES_PER_RUN <= MAX_TOOL_CALLS_PER_RUN

def test_closer_worst_case_still_fits():
    """search_catalog + check_stock + create_order."""
    assert MAX_TOOL_CALLS_PER_RUN >= 3

# --------------------------------------------------------------------------
# activity_log must not accumulate whole conversations
# --------------------------------------------------------------------------

def test_traced_text_is_truncated(monkeypatch):
    logged: dict = {}

    async def fake_log_activity(ctx, **kwargs):
        logged.update(kwargs)

    monkeypatch.setattr(tracing, "log_activity", fake_log_activity)

    long_message = "x" * 5000
    asyncio.run(
        tracing.trace_turn(
            TENANT, "t1:public:+999", "public", "greeter", "m", long_message,
            long_message, 10, "", 5,
        )
    )

    detail = logged["detail"]
    assert len(detail["input_text"]) <= tracing.MAX_TRACED_TEXT + 1
    assert len(detail["output_text"]) <= tracing.MAX_TRACED_TEXT + 1
    # The length is still recorded, so the trace stays useful for debugging.
    assert detail["input_chars"] == 5000
    assert detail["output_chars"] == 5000

def test_short_text_is_left_intact(monkeypatch):
    logged: dict = {}

    async def fake_log_activity(ctx, **kwargs):
        logged.update(kwargs)

    monkeypatch.setattr(tracing, "log_activity", fake_log_activity)

    asyncio.run(
        tracing.trace_turn(
            TENANT, "t1:public:+999", "public", "greeter", "m", "hola", "buenas",
            10, "", 5,
        )
    )
    assert logged["detail"]["input_text"] == "hola"
    assert logged["detail"]["output_text"] == "buenas"

# --------------------------------------------------------------------------
# One conversation, one turn at a time
# --------------------------------------------------------------------------

def test_same_thread_turns_do_not_overlap(monkeypatch):
    """Concurrent turns on one checkpoint mean one message silently vanishes."""
    overlaps = 0
    active = 0

    async def fake_load_tenant_config(tenant_id):
        return TENANT

    async def fake_build_public_agent(_tenant):
        return object()

    async def fake_run_turn(agent, tenant, thread_id, text, message_id=None):
        nonlocal overlaps, active
        active += 1
        if active > 1:
            overlaps += 1
        await asyncio.sleep(0.01)
        active -= 1

        class Reply:
            content = "ok"

        return {"messages": [Reply()]}

    monkeypatch.setattr(bridge, "load_tenant_config", fake_load_tenant_config)
    monkeypatch.setattr(bridge, "build_public_agent", fake_build_public_agent)
    monkeypatch.setattr(bridge, "run_public_agent_turn", fake_run_turn)
    monkeypatch.setattr(bridge, "resolve_role", lambda phone, tenant: "public")
    monkeypatch.setattr(bridge, "_agents", {})
    monkeypatch.setattr(bridge, "_thread_locks", {})

    async def scenario():
        await asyncio.gather(*[
            bridge.respond(tenant_id="t1", user_phone="+999", content=f"m{i}")
            for i in range(5)
        ])

    asyncio.run(scenario())

    assert overlaps == 0, "two turns ran against the same checkpoint at once"
    assert bridge._thread_locks == {}, "lock dict leaked an entry"

def test_bot_switch_still_accepts_the_historical_env_names(monkeypatch):
    """Renaming the switch must not silently disable the bot on live deploys.

    `AI_CORE_URL` dates from when the agent was a separate HTTP service. It is
    now `BOT_ENABLED`, but a deployment still setting the old name has to keep
    working — otherwise the rename turns the bot off without any error.
    """
    from app.config import Settings

    required = {
        "META_APP_ID": "x",
        "META_APP_SECRET": "x",
        "META_VERIFY_TOKEN": "x",
        "SUPABASE_URL": "http://localhost",
        "SUPABASE_SERVICE_KEY": "x.eyJyb2xlIjogInNlcnZpY2Vfcm9sZSJ9.y",
        "ENCRYPTION_KEY": "oZRrOD525wcQ0CJveupENSX1tDwKfP6e1XrDGn9P1Kw=",
    }
    for name in ("BOT_ENABLED", "AI_CORE_URL", "NANOBOT_RUNTIME_URL"):
        monkeypatch.delenv(name, raising=False)
    for key, value in required.items():
        monkeypatch.setenv(key, value)

    # No switch set at all -> bot off.
    assert Settings(_env_file=None).BOT_ENABLED == ""

    for legacy in ("BOT_ENABLED", "AI_CORE_URL", "NANOBOT_RUNTIME_URL"):
        monkeypatch.setenv(legacy, "enabled")
        assert Settings(_env_file=None).BOT_ENABLED == "enabled", (
            f"{legacy} no longer enables the bot"
        )
        monkeypatch.delenv(legacy)

def test_different_threads_still_run_concurrently(monkeypatch):
    """The lock must be per conversation, not a global bottleneck."""
    active = 0
    peak = 0

    async def fake_load_tenant_config(tenant_id):
        return TENANT

    async def fake_build_public_agent(_tenant):
        return object()

    async def fake_run_turn(agent, tenant, thread_id, text, message_id=None):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1

        class Reply:
            content = "ok"

        return {"messages": [Reply()]}

    monkeypatch.setattr(bridge, "load_tenant_config", fake_load_tenant_config)
    monkeypatch.setattr(bridge, "build_public_agent", fake_build_public_agent)
    monkeypatch.setattr(bridge, "run_public_agent_turn", fake_run_turn)
    monkeypatch.setattr(bridge, "resolve_role", lambda phone, tenant: "public")
    monkeypatch.setattr(bridge, "_agents", {})
    monkeypatch.setattr(bridge, "_thread_locks", {})

    async def scenario():
        await asyncio.gather(*[
            bridge.respond(tenant_id="t1", user_phone=f"+{i}", content="hola")
            for i in range(4)
        ])

    asyncio.run(scenario())
    assert peak > 1, "different customers were serialized against each other"

"""Regression tests for the LangChain tool wiring in app/ai_core.

Covers the two ways the agent core can silently stop touching the ERP:

1. `contextual_tool` must register async tools as `coroutine=`, not `func=`.
   With `func=`, LangChain calls the async function synchronously and hands the
   model an un-awaited coroutine object instead of the tool's result — every
   catalog/stock/sales tool becomes a no-op without raising anything.
2. The middleware stack must expose the async hooks (`awrap_tool_call` /
   `awrap_model_call`). LangChain raises NotImplementedError rather than falling
   back to the sync hook, so a sync-only middleware breaks `ainvoke` entirely.

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
from types import SimpleNamespace

import pytest
from langchain.agents.middleware import AgentMiddleware

import app.ai_core.tools.catalog as catalog_tools
import app.ai_core.tools.sales as sales_tools
from app.ai_core.agents.context_middleware import (
    build_message_window,
    build_tool_context,
)
from app.ai_core.agents.guardrails import (
    build_tool_error_boundary,
    build_tool_guardrail,
)
from app.ai_core.config.tenant import AdminAgentConfig, PublicAgentConfig, TenantConfig
from app.ai_core.subagents._base import specialist_middleware
from app.ai_core.tools import (
    add_product,
    check_stock,
    create_order,
    get_sales_report,
    human_handoff,
    search_catalog,
    get_config,
    update_stock,
)
from app.ai_core.tools.context import ToolContext

ALL_TOOLS = [
    search_catalog, check_stock, create_order, get_sales_report,
    update_stock, add_product, human_handoff, get_config,
]

TENANT = TenantConfig(
    tenant_id="t1",
    business_name="Kiosco",
    public_agent=PublicAgentConfig(),
    admin_agent=AdminAgentConfig(allowed_numbers=["59170000001"]),
)


def _ctx(role="public"):
    return ToolContext(tenant=TENANT, role=role, thread_id=f"t1:{role}:59170000002")


@pytest.mark.parametrize("tool", ALL_TOOLS, ids=lambda t: t.name)
def test_async_tools_registered_as_coroutine(tool):
    """An async tool registered under `func=` would never be awaited."""
    assert tool.coroutine is not None, f"{tool.name} has no async implementation"
    assert tool.func is None, f"{tool.name} registered an async function as sync `func=`"


def test_tool_returns_result_not_coroutine(monkeypatch):
    """The whole point: the model must receive data, not a coroutine object."""
    rows = [{"id": "p1", "name": "Agua", "price": 10.0, "in_stock": True,
             "description": "1L", "tags": ["bebida"]}]

    async def fake_search(ctx, query=None):
        return rows

    monkeypatch.setattr(catalog_tools.storefront, "search_catalog", fake_search)

    result = asyncio.run(search_catalog.ainvoke({"query": "agua", "ctx": _ctx()}))

    assert not inspect.iscoroutine(result), "tool returned an un-awaited coroutine"
    assert [p.model_dump()["name"] for p in result] == ["Agua"]


def test_ctx_hidden_from_model_but_validated():
    """`ctx` is injected by middleware, so it must not be in the LLM's schema."""
    assert "ctx" not in search_catalog.get_input_schema().model_fields
    assert "ctx" in search_catalog.args_schema.model_fields


@pytest.mark.parametrize(
    "middleware",
    [
        build_tool_context(TENANT, "public"),
        build_tool_error_boundary(),
        build_tool_guardrail(TENANT, "public"),
    ],
    ids=lambda m: type(m).__name__,
)
def test_tool_middleware_supports_async_path(middleware):
    """Sync-only middleware makes `ainvoke` raise NotImplementedError."""
    assert type(middleware).awrap_tool_call is not AgentMiddleware.awrap_tool_call


def test_message_window_supports_async_path():
    assert type(build_message_window()).awrap_model_call is not AgentMiddleware.awrap_model_call


def _trimmed(n_turns, max_messages=40):
    """Run the real middleware trim over a system prompt + n_turns exchanges."""
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    history = [SystemMessage("Sos el vendedor de Kiosco Doppel.")]
    for i in range(n_turns):
        history += [HumanMessage(f"h{i}"), AIMessage(f"a{i}")]

    captured = {}

    class _Request:
        messages = history

        def override(self, *, messages):
            captured["messages"] = messages
            return self

    build_message_window(max_messages)._trim(_Request())
    return captured["messages"]


def test_system_prompt_survives_the_message_window():
    """The specialist must not lose its instructions in a long conversation."""
    from langchain_core.messages import SystemMessage

    trimmed = _trimmed(n_turns=30)
    assert any(isinstance(m, SystemMessage) for m in trimmed), (
        "system prompt dropped once history outgrew the window"
    )
    assert isinstance(trimmed[0], SystemMessage), "system prompt must stay first"


def test_message_window_still_bounds_the_prompt():
    """Pinning the system prompt must not let the context grow unbounded."""
    assert len(_trimmed(n_turns=30, max_messages=40)) <= 40
    assert len(_trimmed(n_turns=200, max_messages=40)) <= 40
    # A short conversation is left untouched.
    assert len(_trimmed(n_turns=3, max_messages=40)) == 7


def test_specialist_middleware_stack_is_async_capable():
    """Every middleware bound to a specialist must survive the async path."""
    for middleware in specialist_middleware(TENANT, "public"):
        cls = type(middleware)
        overrides_tool = cls.awrap_tool_call is not AgentMiddleware.awrap_tool_call
        overrides_model = cls.awrap_model_call is not AgentMiddleware.awrap_model_call
        sync_tool = cls.wrap_tool_call is not AgentMiddleware.wrap_tool_call
        sync_model = cls.wrap_model_call is not AgentMiddleware.wrap_model_call
        if sync_tool:
            assert overrides_tool, f"{cls.__name__} lacks awrap_tool_call"
        if sync_model:
            assert overrides_model, f"{cls.__name__} lacks awrap_model_call"


def test_agent_entrypoints_are_async():
    """The webhook runs on the event loop; a sync turn would block the server."""
    from app.ai_core.agents.admin_agent import build_admin_agent, run_admin_agent_turn
    from app.ai_core.agents.public_agent import build_public_agent, run_public_agent_turn
    from app.ai_core.persistence.checkpointer import open_checkpointer

    for fn in (build_admin_agent, run_admin_agent_turn,
               build_public_agent, run_public_agent_turn, open_checkpointer):
        assert inspect.iscoroutinefunction(fn), f"{fn.__name__} must be async"


def test_role_permission_still_enforced():
    """Admin-only tools must reject the public role through the async path."""
    with pytest.raises(PermissionError):
        asyncio.run(get_sales_report.ainvoke({"ctx": _ctx("public")}))


# --------------------------------------------------------------------------
# create_order: idempotencia
#
# Un reintento del modelo con los mismos ítems creaba una segunda venta —
# descontaba stock de nuevo y sumaba de nuevo a caja. La clave la deriva la
# tool y la hace cumplir el RPC (migration_v10); estos tests atan la parte que
# vive en Python: qué claves son iguales, cuáles no, y cuándo no hay clave.
# --------------------------------------------------------------------------

def _tool_call_request(tool, configurable):
    """Stub with the surface `ToolContextMiddleware._inject` actually touches."""
    return SimpleNamespace(
        tool=tool,
        tool_call={"args": {}},
        runtime=SimpleNamespace(config={"configurable": configurable}),
    )


def _order_ctx(turn_id="msg-1", thread_id="t1:public:59170000002"):
    return ToolContext(tenant=TENANT, role="public", thread_id=thread_id, turn_id=turn_id)


def _capture_register_sale(monkeypatch, calls):
    async def fake_register_sale(ctx, items, customer_phone=None,
                                 payment_method="whatsapp", idempotency_key=None):
        calls.append(idempotency_key)
        return {"ok": True, "duplicate": len(calls) > 1, "total": 2.4,
                "items": [{"product_id": "p1", "name": "Coca", "qty": 2, "subtotal": 2.4}]}

    monkeypatch.setattr(sales_tools.storefront, "register_sale", fake_register_sale)


def test_create_order_sends_an_idempotency_key(monkeypatch):
    calls = []
    _capture_register_sale(monkeypatch, calls)

    asyncio.run(create_order.ainvoke(
        {"items": [{"product_id": "p1", "quantity": 2}], "ctx": _order_ctx()}))

    assert calls[0], "create_order must send an idempotency key"


def test_retry_within_the_same_turn_reuses_the_key(monkeypatch):
    """Este es el bug: el modelo llama dos veces y se registran dos ventas."""
    calls = []
    _capture_register_sale(monkeypatch, calls)
    ctx = _order_ctx()
    items = [{"product_id": "p1", "quantity": 2}]

    first = asyncio.run(create_order.ainvoke({"items": items, "ctx": ctx}))
    second = asyncio.run(create_order.ainvoke({"items": items, "ctx": ctx}))

    assert calls[0] == calls[1], "a retry in the same turn must hit the same sale"
    assert first.duplicate is False
    assert second.duplicate is True, "the model must be told it was already placed"


def test_item_order_does_not_change_the_key(monkeypatch):
    """El modelo puede listar los ítems al revés en el reintento; sigue siendo la misma orden."""
    calls = []
    _capture_register_sale(monkeypatch, calls)
    ctx = _order_ctx()

    asyncio.run(create_order.ainvoke({"ctx": ctx, "items": [
        {"product_id": "p1", "quantity": 2}, {"product_id": "p2", "quantity": 1}]}))
    asyncio.run(create_order.ainvoke({"ctx": ctx, "items": [
        {"product_id": "p2", "quantity": 1}, {"product_id": "p1", "quantity": 2}]}))

    assert calls[0] == calls[1]


def test_a_later_turn_is_a_new_sale(monkeypatch):
    """Comprar lo mismo de nuevo más tarde es una venta nueva, no un duplicado."""
    calls = []
    _capture_register_sale(monkeypatch, calls)
    items = [{"product_id": "p1", "quantity": 2}]

    asyncio.run(create_order.ainvoke({"items": items, "ctx": _order_ctx("msg-1")}))
    asyncio.run(create_order.ainvoke({"items": items, "ctx": _order_ctx("msg-2")}))

    assert calls[0] != calls[1]


def test_different_items_are_different_keys(monkeypatch):
    calls = []
    _capture_register_sale(monkeypatch, calls)
    ctx = _order_ctx()

    asyncio.run(create_order.ainvoke(
        {"items": [{"product_id": "p1", "quantity": 2}], "ctx": ctx}))
    asyncio.run(create_order.ainvoke(
        {"items": [{"product_id": "p1", "quantity": 3}], "ctx": ctx}))

    assert calls[0] != calls[1]


def test_no_turn_id_means_no_key(monkeypatch):
    """Sin turno, una clave de thread+ítems se comería la recompra legítima del
    cliente. Perder una venta real es peor que el duplicado que esto evita."""
    calls = []
    _capture_register_sale(monkeypatch, calls)

    asyncio.run(create_order.ainvoke(
        {"items": [{"product_id": "p1", "quantity": 2}], "ctx": _order_ctx(turn_id="")}))

    assert calls == [None]


def test_middleware_injects_the_turn_id():
    """La clave sale del turn_id; si el middleware no lo inyecta, no hay idempotencia."""
    middleware = build_tool_context(TENANT, "public")
    request = _tool_call_request(
        create_order, {"thread_id": "t1:public:5917", "turn_id": "wamid.ABC"})

    injected, _ = middleware._inject(request)

    assert injected
    ctx = request.tool_call["args"]["ctx"]
    assert ctx.turn_id == "wamid.ABC"
    assert ctx.thread_id == "t1:public:5917"

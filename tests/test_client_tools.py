"""Unit tests for client_tools wrappers.

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
os.environ.setdefault("AGNO_DB_URL", "postgresql+psycopg://ai:ai@localhost:5532/ai")

import asyncio

from app.ai.tools.client_tools import build_client_tools
from app.services.erp.context import bot_context

_CTX = bot_context("t1", actor="whatsapp_bot")


def test_build_client_tools_exposes_two_tools():
    tools = build_client_tools(_CTX)
    assert all(callable(t) for t in tools)
    assert {t.__name__ for t in tools} == {"search_catalog", "register_sale"}


def test_search_catalog_tool_delegates(monkeypatch):
    async def fake_search(ctx, query=None):
        assert ctx.tenant_id == "t1"
        assert ctx.actor == "whatsapp_bot"
        assert query == "coca"
        return [{"id": "p1", "name": "Coca", "price": 1.2, "in_stock": True}]

    monkeypatch.setattr("app.ai.tools.client_tools.storefront.search_catalog", fake_search)
    tools = build_client_tools(_CTX)
    search = next(t for t in tools if t.__name__ == "search_catalog")
    assert asyncio.run(search("coca")) == [
        {"id": "p1", "name": "Coca", "price": 1.2, "in_stock": True}]


def test_register_sale_tool_delegates(monkeypatch):
    async def fake_register(ctx, items, customer_phone=None, payment_method="whatsapp"):
        assert ctx.actor == "whatsapp_bot"
        return {"ok": True, "total": 1.2, "items": []}

    monkeypatch.setattr("app.ai.tools.client_tools.storefront.register_sale", fake_register)
    tools = build_client_tools(_CTX)
    register = next(t for t in tools if t.__name__ == "register_sale")
    assert asyncio.run(register([{"product_id": "p1", "quantity": 1}]))["ok"] is True

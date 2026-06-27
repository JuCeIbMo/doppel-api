import os

os.environ.setdefault("META_APP_ID", "test-app-id")
os.environ.setdefault("META_APP_SECRET", "test-app-secret")
os.environ.setdefault("META_VERIFY_TOKEN", "test-verify-token")
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "x.eyJyb2xlIjogInNlcnZpY2Vfcm9sZSJ9.y")
os.environ.setdefault("ENCRYPTION_KEY", "oZRrOD525wcQ0CJveupENSX1tDwKfP6e1XrDGn9P1Kw=")

import asyncio

from pydantic_ai.messages import ToolCallPart
from pydantic_ai.models.test import TestModel

import app.services.storefront as storefront
from app.ai.agents.client import ClientDeps, client_agent
from app.services.erp.context import ERPContext

CTX = ERPContext(tenant_id="t1", actor="whatsapp_bot", actor_label="Bot WhatsApp")


def _tool_names(result):
    return [
        p.tool_name
        for msg in result.all_messages()
        for p in getattr(msg, "parts", [])
        if isinstance(p, ToolCallPart)
    ]


def test_client_runs_both_tools(monkeypatch):
    async def fake_business_info(ctx):
        return {"name": "Demo"}

    async def fake_search(ctx, query=None):
        return [{"id": "p1", "name": "Café", "price": 1000, "in_stock": True,
                 "description": "", "tags": []}]

    async def fake_sale(ctx, items, customer_phone=None, payment_method="whatsapp"):
        return {"ok": True, "sale_id": "s1"}

    monkeypatch.setattr(storefront, "business_info", fake_business_info)
    monkeypatch.setattr(storefront, "search_catalog", fake_search)
    monkeypatch.setattr(storefront, "register_sale", fake_sale)

    deps = ClientDeps(ctx=CTX, system_prompt="Sos un vendedor.")

    async def run():
        result = await client_agent.run("hola", model=TestModel(), deps=deps)
        return _tool_names(result)

    names = asyncio.run(run())
    assert "search_catalog" in names
    assert "register_sale" in names

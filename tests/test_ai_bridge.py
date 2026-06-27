import os

os.environ.setdefault("META_APP_ID", "test-app-id")
os.environ.setdefault("META_APP_SECRET", "test-app-secret")
os.environ.setdefault("META_VERIFY_TOKEN", "test-verify-token")
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "x.eyJyb2xlIjogInNlcnZpY2Vfcm9sZSJ9.y")
os.environ.setdefault("ENCRYPTION_KEY", "oZRrOD525wcQ0CJveupENSX1tDwKfP6e1XrDGn9P1Kw=")

import asyncio

from pydantic_ai.models.test import TestModel

import app.services.storefront as storefront
from app.ai import respond
from app.ai import history
from app.ai.agents import client as client_mod


def test_client_respond_returns_text(monkeypatch):
    async def fake_business_info(ctx):
        return {"name": "Demo"}

    async def fake_search(ctx, query=None):
        return []

    async def fake_sale(ctx, items, customer_phone=None, payment_method="whatsapp"):
        return {"ok": True}

    monkeypatch.setattr(storefront, "business_info", fake_business_info)
    monkeypatch.setattr(storefront, "search_catalog", fake_search)
    monkeypatch.setattr(storefront, "register_sale", fake_sale)

    # Forzamos TestModel como modelo del run vía override del agente.
    with client_mod.client_agent.override(model=TestModel(custom_output_text="hola!")):
        out = asyncio.run(respond(
            mode="client", tenant_id="t1", user_phone="555",
            content="buenas", system_prompt="Sos vendedor.", model="claude-sonnet-4-20250514",
        ))
    assert isinstance(out, str)
    assert out == "hola!"


def test_crash_returns_none(monkeypatch):
    def boom(_):
        raise RuntimeError("boom")
    monkeypatch.setattr(history, "load", boom)
    out = asyncio.run(respond(
        mode="client", tenant_id="t1", user_phone="555",
        content="x", system_prompt="p", model="claude-sonnet-4-20250514",
    ))
    assert out is None

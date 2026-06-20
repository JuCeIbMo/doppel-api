"""Unit tests for storefront lean reads.

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

import asyncio

import app.services.storefront as storefront
from app.services.erp.context import ERPContext

CTX = ERPContext(tenant_id="t1", actor="whatsapp_bot", actor_label="Bot WhatsApp")


class _BizQuery:
    def __init__(self, rows):
        self._rows = rows
    def select(self, *a, **k): return self
    def eq(self, field, value):
        if field == "tenant_id":
            assert value == "t1"
        return self
    def limit(self, *a, **k): return self
    def execute(self):
        rows = self._rows
        class R:
            data = rows
        return R()


class _BizSupabase:
    def __init__(self, rows):
        self._rows = rows
    def table(self, _name):
        return _BizQuery(self._rows)


def test_business_info_returns_profile(monkeypatch):
    row = {"name": "Kiosco", "description": "d", "hours": "9-18",
           "address": "calle 1", "payment_methods": "efectivo"}
    monkeypatch.setattr(storefront, "get_supabase", lambda: _BizSupabase([row]))
    assert asyncio.run(storefront.business_info(CTX)) == row


def test_business_info_empty_returns_blanks(monkeypatch):
    monkeypatch.setattr(storefront, "get_supabase", lambda: _BizSupabase([]))
    result = asyncio.run(storefront.business_info(CTX))
    assert result == {"name": "", "description": "", "hours": "",
                      "address": "", "payment_methods": ""}


def test_search_catalog_lean_and_filters_unavailable(monkeypatch):
    async def fake_list(self, ctx, *, category=None, search=None, limit=50, offset=0):
        assert ctx.tenant_id == "t1"
        return [
            {"id": "p1", "name": "Coca 500ml", "price": 1.2, "available": True, "stock": 5},
            {"id": "p2", "name": "Agua", "price": 0.8, "available": True, "stock": 0},
            {"id": "p3", "name": "Oculto", "price": 9.0, "available": False, "stock": 3},
        ]
    monkeypatch.setattr("app.services.storefront.ProductsService.list", fake_list)
    result = asyncio.run(storefront.search_catalog(CTX, query="a"))
    assert result == [
        {"id": "p1", "name": "Coca 500ml", "price": 1.2, "in_stock": True},
        {"id": "p2", "name": "Agua", "price": 0.8, "in_stock": False},
    ]


from app.services.erp.exceptions import InsufficientStock, NotFound


def test_register_sale_happy_path(monkeypatch):
    captured = {}

    async def fake_get_by_phone(self, ctx, phone):
        return {"id": "c9"}

    async def fake_create_sale(self, ctx, body):
        captured["body"] = body
        return {"id": "s1", "total": 2.4,
                "items": [{"product_name": "Coca 500ml", "quantity": 2, "subtotal": 2.4}]}

    monkeypatch.setattr("app.services.storefront.ClientsService.get_by_phone", fake_get_by_phone)
    monkeypatch.setattr("app.services.storefront.SalesService.create_sale", fake_create_sale)

    result = asyncio.run(storefront.register_sale(
        CTX, items=[{"product_id": "p1", "quantity": 2}], customer_phone="+5491100"))

    assert result == {"ok": True, "total": 2.4,
                      "items": [{"name": "Coca 500ml", "qty": 2, "subtotal": 2.4}]}
    assert captured["body"]["client_id"] == "c9"
    assert captured["body"]["payment_method"] == "whatsapp"
    assert captured["body"]["items"] == [{"product_id": "p1", "quantity": 2}]


def test_register_sale_unknown_client_keeps_none(monkeypatch):
    async def fake_get_by_phone(self, ctx, phone):
        raise NotFound("no existe")

    async def fake_create_sale(self, ctx, body):
        assert body["client_id"] is None
        return {"id": "s1", "total": 1.2, "items": []}

    monkeypatch.setattr("app.services.storefront.ClientsService.get_by_phone", fake_get_by_phone)
    monkeypatch.setattr("app.services.storefront.SalesService.create_sale", fake_create_sale)

    result = asyncio.run(storefront.register_sale(
        CTX, items=[{"product_id": "p1", "quantity": 1}], customer_phone="+5491100"))
    assert result["ok"] is True


def test_register_sale_insufficient_stock_returns_error(monkeypatch):
    async def fake_create_sale(self, ctx, body):
        raise InsufficientStock(product_id="p1", available=0, requested=2)

    monkeypatch.setattr("app.services.storefront.SalesService.create_sale", fake_create_sale)

    result = asyncio.run(storefront.register_sale(
        CTX, items=[{"product_id": "p1", "quantity": 2}]))
    assert result["error"] == "insufficient_stock"
    assert "message" in result and "detail" in result


def test_register_sale_requires_items():
    result = asyncio.run(storefront.register_sale(CTX, items=[]))
    assert result["error"] == "validation_error"

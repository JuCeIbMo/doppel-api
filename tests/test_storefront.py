"""Unit tests for storefront lean reads.

Shared test environment is loaded before collection by `tests/conftest.py`.
"""

import asyncio

import app.services.storefront as storefront
from app.services.erp.context import ERPContext
from app.services.erp.products import ProductsService

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
    async def execute(self):
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
    async def fake_search(self, ctx, query, *, limit=50, offset=0):
        assert ctx.tenant_id == "t1"
        assert query == "bebida cola"
        assert (limit, offset) == (21, 0)
        return [
            {"id": "p1", "name": "Coca 500ml", "price": 1.2, "available": True, "stock": 5,
             "description": "Gaseosa cola", "tags": ["bebida", "gaseosa"]},
            {"id": "p2", "name": "Agua", "price": 0.8, "available": True, "stock": 0},
        ]
    monkeypatch.setattr(
        "app.services.storefront.ProductsService.search_available", fake_search
    )
    result = asyncio.run(storefront.search_catalog(CTX, query="  bebida cola  "))
    # Enriquecido con description+tags para que el vendedor matchee; faltantes -> "" / [].
    assert result == {
        "items": [
            {"id": "p1", "name": "Coca 500ml", "price": 1.2, "in_stock": True,
             "has_image": False, "description": "Gaseosa cola",
             "tags": ["bebida", "gaseosa"]},
            {"id": "p2", "name": "Agua", "price": 0.8, "in_stock": False,
             "has_image": False, "description": "", "tags": []},
        ],
        "page": 0,
        "has_more": False,
    }


def test_search_catalog_without_query_keeps_alphabetical_listing(monkeypatch):
    captured = {}

    async def fake_list(
        self, ctx, *, category=None, search=None, available=None, limit=50, offset=0
    ):
        captured.update(
            search=search, available=available, limit=limit, offset=offset
        )
        return []

    async def unexpected_search(*_args, **_kwargs):
        raise AssertionError("whitespace-only query must not call the search RPC")

    monkeypatch.setattr("app.services.storefront.ProductsService.list", fake_list)
    monkeypatch.setattr(
        "app.services.storefront.ProductsService.search_available", unexpected_search
    )

    result = asyncio.run(storefront.search_catalog(CTX, query="   "))

    assert result == {"items": [], "page": 0, "has_more": False}
    assert captured == {"search": None, "available": True, "limit": 21, "offset": 0}


def test_products_search_rpc_is_tenant_scoped_and_preserves_rank_order(monkeypatch):
    captured = {}

    class InventoryQuery:
        def select(self, fields):
            assert fields == "product_id, quantity"
            return self

        def eq(self, field, value):
            assert (field, value) == ("tenant_id", "t1")
            return self

        def in_(self, field, values):
            assert (field, values) == ("product_id", ["p2", "p1"])
            return self

        async def execute(self):
            return type("Result", (), {"data": [
                {"product_id": "p1", "quantity": 3},
                {"product_id": "p2", "quantity": 0},
            ]})()

    class ProductsQuery:
        def select(self, fields):
            assert fields == "id, image_url"
            return self

        def eq(self, field, value):
            assert (field, value) == ("tenant_id", "t1")
            return self

        def in_(self, field, values):
            assert (field, values) == ("id", ["p2", "p1"])
            return self

        async def execute(self):
            return type("Result", (), {"data": [
                {"id": "p1", "image_url": "https://cdn/p1.webp"},
                {"id": "p2", "image_url": None},
            ]})()

    class RPC:
        async def execute(self):
            return type("Result", (), {"data": [
                {"id": "p2", "name": "Segundo", "search_rank": 0.9},
                {"id": "p1", "name": "Primero", "search_rank": 0.5},
            ]})()

    class Supabase:
        def rpc(self, name, params):
            captured.update(name=name, params=params)
            return RPC()

        def table(self, name):
            if name == "inventory":
                return InventoryQuery()
            assert name == "products"
            return ProductsQuery()

    monkeypatch.setattr("app.services.erp.products.get_supabase", lambda: Supabase())

    rows = asyncio.run(
        ProductsService().search_available(
            CTX, "bebida cola pequeña", limit=21, offset=40
        )
    )

    assert captured == {
        "name": "search_products_catalog",
        "params": {
            "p_tenant_id": "t1",
            "p_query": "bebida cola pequeña",
            "p_limit": 21,
            "p_offset": 40,
        },
    }
    assert [row["id"] for row in rows] == ["p2", "p1"]
    assert [row["stock"] for row in rows] == [0, 3.0]
    assert [row["has_image"] for row in rows] == [False, True]


def test_search_catalog_paginates(monkeypatch):
    all_rows = [
        {"id": f"p{i}", "name": f"Producto {i}", "price": 1.0, "available": True, "stock": 1}
        for i in range(45)
    ]

    async def fake_list(self, ctx, *, category=None, search=None, available=None, limit=50, offset=0):
        return all_rows[offset:offset + limit]

    monkeypatch.setattr("app.services.storefront.ProductsService.list", fake_list)

    page0 = asyncio.run(storefront.search_catalog(CTX, page=0))
    assert [p["id"] for p in page0["items"]] == [f"p{i}" for i in range(20)]
    assert page0["has_more"] is True

    page2 = asyncio.run(storefront.search_catalog(CTX, page=2))
    assert [p["id"] for p in page2["items"]] == [f"p{i}" for i in range(40, 45)]
    assert page2["has_more"] is False


def test_get_product_image_is_tenant_scoped_and_requires_available(monkeypatch):
    captured = []

    class Query:
        def select(self, fields):
            assert fields == "image_url"
            return self

        def eq(self, field, value):
            captured.append((field, value))
            return self

        def limit(self, value):
            assert value == 1
            return self

        async def execute(self):
            return type("Result", (), {
                "data": [{"image_url": "https://cdn.test/t1/p1.webp"}]
            })()

    class Supabase:
        def table(self, name):
            assert name == "products"
            return Query()

    monkeypatch.setattr(storefront, "get_supabase", lambda: Supabase())

    url = asyncio.run(storefront.get_product_image(CTX, "p1"))

    assert url == "https://cdn.test/t1/p1.webp"
    assert captured == [
        ("tenant_id", "t1"),
        ("id", "p1"),
        ("available", True),
    ]


from app.services.erp.exceptions import ERPError, InsufficientStock, NotFound

def test_register_sale_happy_path(monkeypatch):
    captured = {}

    async def fake_get_by_phone(self, ctx, phone):
        return {"id": "c9"}

    async def fake_create_sale(self, ctx, body):
        captured["body"] = body
        # Shape real de sale_items: el importe de línea es `total`, no `subtotal`.
        return {"id": "s1", "total": 2.4,
                "items": [{"product_id": "p1", "product_name": "Coca 500ml",
                           "quantity": 2, "total": 2.4}]}

    monkeypatch.setattr("app.services.storefront.ClientsService.get_by_phone", fake_get_by_phone)
    monkeypatch.setattr("app.services.storefront.SalesService.create_sale", fake_create_sale)

    result = asyncio.run(storefront.register_sale(
        CTX, items=[{"product_id": "p1", "quantity": 2}], customer_phone="+5491100"))

    assert result == {"ok": True, "duplicate": False, "total": 2.4,
                      "items": [{"product_id": "p1", "name": "Coca 500ml",
                                 "qty": 2, "subtotal": 2.4}]}
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

def test_register_sale_erp_error_on_client_lookup_degrades_gracefully(monkeypatch):
    """Un ERPError genérico en get_by_phone no debe abortar la venta; client_id=None."""
    captured = {}

    async def fake_get_by_phone(self, ctx, phone):
        raise ERPError("boom")

    async def fake_create_sale(self, ctx, body):
        captured["body"] = body
        return {"id": "s2", "total": 1.2,
                "items": [{"product_name": "Agua", "quantity": 1, "subtotal": 1.2}]}

    monkeypatch.setattr("app.services.storefront.ClientsService.get_by_phone", fake_get_by_phone)
    monkeypatch.setattr("app.services.storefront.SalesService.create_sale", fake_create_sale)

    result = asyncio.run(storefront.register_sale(
        CTX, items=[{"product_id": "p2", "quantity": 1}], customer_phone="+5491100"))

    assert result["ok"] is True
    assert captured["body"]["client_id"] is None

def test_register_sale_insufficient_stock_returns_error(monkeypatch):
    async def fake_create_sale(self, ctx, body):
        raise InsufficientStock(product_id="p1", available=0, requested=2)

    monkeypatch.setattr("app.services.storefront.SalesService.create_sale", fake_create_sale)

    result = asyncio.run(storefront.register_sale(
        CTX, items=[{"product_id": "p1", "quantity": 2}]))
    assert result["ok"] is False
    assert result["error"] == "insufficient_stock"
    assert "message" in result and "detail" in result

def test_register_sale_forwards_idempotency_key(monkeypatch):
    """La clave tiene que llegar al RPC: es lo único que lo hace idempotente."""
    captured = {}

    async def fake_create_sale(self, ctx, body):
        captured["body"] = body
        return {"id": "s1", "total": 1.2, "items": []}

    monkeypatch.setattr("app.services.storefront.SalesService.create_sale", fake_create_sale)

    result = asyncio.run(storefront.register_sale(
        CTX, items=[{"product_id": "p1", "quantity": 1}], idempotency_key="k-123"))

    assert captured["body"]["idempotency_key"] == "k-123"
    assert result["duplicate"] is False

def test_register_sale_marks_idempotent_replay_as_duplicate(monkeypatch):
    """El RPC devuelve la venta ya registrada; el shape lean tiene que decirlo."""

    async def fake_create_sale(self, ctx, body):
        return {"id": "s1", "total": 1.2, "idempotent_replay": True,
                "items": [{"product_id": "p1", "product_name": "Agua",
                           "quantity": 1, "total": 1.2}]}

    monkeypatch.setattr("app.services.storefront.SalesService.create_sale", fake_create_sale)

    result = asyncio.run(storefront.register_sale(
        CTX, items=[{"product_id": "p1", "quantity": 1}], idempotency_key="k-123"))

    assert result["ok"] is True
    assert result["duplicate"] is True
    assert result["total"] == 1.2

def test_register_sale_requires_items():
    result = asyncio.run(storefront.register_sale(CTX, items=[]))
    assert result["ok"] is False
    assert result["error"] == "validation_error"

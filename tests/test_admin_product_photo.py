"""`create_product_from_photo`: the WhatsApp photo alta flow.

Follows the style of `test_admin_tool_payloads.py`: monkeypatches the ERP
*services*, not the Supabase client.
"""

from __future__ import annotations

import asyncio

from app.ai_core.config.tenant import AdminAgentConfig, PublicAgentConfig, TenantConfig
from app.ai_core.tools import catalog as catalog_tools
from app.ai_core.tools.context import ToolContext
from app.services.erp.inventory import InventoryService
from app.services.erp.product_creation import ProductCreationService

TENANT = TenantConfig(
    tenant_id="tenant-1",
    business_name="Kiosco",
    public_agent=PublicAgentConfig(),
    admin_agent=AdminAgentConfig(allowed_numbers=["59170000001"]),
)


def _ctx(images=None):
    return ToolContext(
        tenant=TENANT, role="admin", thread_id="tenant-1:admin:59170000001",
        images=images or [],
    )


def test_without_photo_asks_for_one_and_never_calls_the_service(monkeypatch):
    called = False

    async def create(self, ctx, product_data, raw_image):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(ProductCreationService, "create", create)

    result = asyncio.run(catalog_tools.create_product_from_photo.ainvoke(
        {"name": "Campera de jean", "price": 45000, "ctx": _ctx(images=[])}))

    assert "foto" in result.lower()
    assert called is False


def test_with_photo_creates_the_product_once(monkeypatch, tmp_path):
    image_path = tmp_path / "photo.jpg"
    image_path.write_bytes(b"fake-jpeg-bytes")

    calls = []

    async def create(self, ctx, product_data, raw_image):
        calls.append((product_data, raw_image))
        return {"id": "p1", "name": product_data["name"], "price": product_data["price"]}

    monkeypatch.setattr(ProductCreationService, "create", create)

    ctx = _ctx(images=[{"path": str(image_path), "mime_type": "image/jpeg"}])
    result = asyncio.run(catalog_tools.create_product_from_photo.ainvoke(
        {"name": "Campera de jean", "price": 45000, "ctx": ctx}))

    assert len(calls) == 1
    product_data, raw_image = calls[0]
    assert raw_image == b"fake-jpeg-bytes"
    assert product_data["name"] == "Campera de jean"
    assert product_data["price"] == 45000
    assert "Campera de jean" in result
    assert "45000" in result


def test_with_stock_adjusts_inventory_after_creating(monkeypatch, tmp_path):
    image_path = tmp_path / "photo.jpg"
    image_path.write_bytes(b"fake-jpeg-bytes")

    async def create(self, ctx, product_data, raw_image):
        return {"id": "p1", "name": product_data["name"], "price": product_data["price"]}

    adjust_calls = []

    async def adjust(self, ctx, *, product_id, new_quantity, delta, note):
        adjust_calls.append((product_id, new_quantity, delta))
        return {"ok": True, "product_id": product_id, "quantity": new_quantity, "movement": None}

    monkeypatch.setattr(ProductCreationService, "create", create)
    monkeypatch.setattr(InventoryService, "adjust", adjust)

    ctx = _ctx(images=[{"path": str(image_path), "mime_type": "image/jpeg"}])
    result = asyncio.run(catalog_tools.create_product_from_photo.ainvoke(
        {"name": "Campera de jean", "price": 45000, "stock": 8, "ctx": ctx}))

    assert adjust_calls == [("p1", 8, None)]
    assert "8" in result

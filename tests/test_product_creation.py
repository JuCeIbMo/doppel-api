"""Product creation is one multipart operation with compensating rollback."""

import os

os.environ.setdefault("META_APP_ID", "test-app-id")
os.environ.setdefault("META_APP_SECRET", "test-app-secret")
os.environ.setdefault("META_VERIFY_TOKEN", "test-verify-token")
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "x.eyJyb2xlIjogInNlcnZpY2Vfcm9sZSJ9.y")
os.environ.setdefault("ENCRYPTION_KEY", "oZRrOD525wcQ0CJveupENSX1tDwKfP6e1XrDGn9P1Kw=")
os.environ.setdefault("CHAT_DB_URL", "postgresql://ai:ai@localhost:5532/chat")

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.erp.context import ERPContext, get_erp_context
from app.services.erp.product_creation import ProductCreationService
from app.services.storage import UploadedProductImage

CTX = ERPContext(tenant_id="t1", actor="owner", actor_label="Dueño")


class _Products:
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.payload = None

    async def create(self, ctx, payload):
        assert ctx == CTX
        self.payload = payload
        if self.error:
            raise self.error
        return {
            "id": "p1",
            **payload,
            "has_variants": False,
            "low_stock_threshold": payload.get("low_stock_threshold", 5),
            "unit": payload.get("unit", "unidad"),
            "available": payload.get("available", True),
            "cost_price": payload.get("cost_price", 0),
        }


def _patch_pipeline(monkeypatch, *, analysis=None):
    monkeypatch.setattr(
        "app.services.erp.product_creation.optimize_image", lambda raw: b"optimized-webp"
    )

    async def upload(tenant_id, data):
        assert (tenant_id, data) == ("t1", b"optimized-webp")
        return UploadedProductImage("t1/abc.webp", "https://cdn.test/t1/abc.webp")

    async def analyze(data, content_type, hint=None):
        assert (data, content_type, hint) == (b"optimized-webp", "image/webp", "Coca")
        return analysis or {
            "ai_ok": True,
            "name": "Coca sugerida",
            "description": "Descripción generada",
            "tags": ["Bebida", "cola"],
        }

    monkeypatch.setattr("app.services.erp.product_creation.upload_product_image_asset", upload)
    monkeypatch.setattr("app.services.erp.product_creation.analyze_product_image", analyze)


def test_create_enriches_and_persists_one_complete_product(monkeypatch):
    _patch_pipeline(monkeypatch)
    products = _Products()

    result = asyncio.run(ProductCreationService(products).create(
        CTX,
        {"name": "Coca", "price": 10, "description": "", "tags": ["Fría", "cola"]},
        b"raw-image",
    ))

    assert products.payload == {
        "name": "Coca",
        "price": 10,
        "description": "Descripción generada",
        "tags": ["fría", "cola", "bebida"],
        "image_url": "https://cdn.test/t1/abc.webp",
    }
    assert result["id"] == "p1"
    assert result["image_analysis_ok"] is True


def test_create_keeps_manual_description(monkeypatch):
    _patch_pipeline(monkeypatch)
    products = _Products()

    asyncio.run(ProductCreationService(products).create(
        CTX,
        {"name": "Coca", "price": 10, "description": "Texto del dueño"},
        b"raw-image",
    ))

    assert products.payload["description"] == "Texto del dueño"


def test_create_deletes_uploaded_image_when_database_fails(monkeypatch):
    _patch_pipeline(monkeypatch)
    deleted = []

    async def delete(path):
        deleted.append(path)

    monkeypatch.setattr("app.services.erp.product_creation.delete_product_image", delete)
    service = ProductCreationService(_Products(RuntimeError("database unavailable")))

    with pytest.raises(RuntimeError, match="database unavailable"):
        asyncio.run(service.create(CTX, {"name": "Coca", "price": 10}, b"raw"))

    assert deleted == ["t1/abc.webp"]


@pytest.fixture
def client(monkeypatch):
    app.dependency_overrides[get_erp_context] = lambda: CTX

    async def create(ctx, product_data, raw_image):
        assert ctx == CTX
        assert product_data["name"] == "Coca"
        assert product_data["price"] == 10
        assert raw_image == b"raw-image"
        return {
            "id": "p1", "name": "Coca", "description": "Gaseosa",
            "sku": None, "barcode": None, "category": "bebidas",
            "image_url": "https://cdn.test/t1/abc.webp", "cost_price": 0,
            "price": 10, "unit": "unidad", "available": True,
            "has_variants": False, "low_stock_threshold": 5, "tags": ["cola"],
            "image_analysis_ok": True,
        }

    monkeypatch.setattr("app.routers.erp.products.creation_service.create", create)
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_post_products_accepts_metadata_and_image_in_one_request(client):
    response = client.post(
        "/erp/products",
        data={"name": "Coca", "price": "10", "category": "bebidas"},
        files={"image": ("coca.jpg", b"raw-image", "image/jpeg")},
    )

    assert response.status_code == 200
    assert response.json()["image_url"] == "https://cdn.test/t1/abc.webp"
    assert response.json()["image_analysis_ok"] is True


def test_post_products_requires_image(client):
    response = client.post("/erp/products", data={"name": "Coca", "price": "10"})
    assert response.status_code == 422


def test_old_json_creation_is_rejected(client):
    response = client.post("/erp/products", json={"name": "Coca", "price": 10})
    assert response.status_code == 422

import os

os.environ.setdefault("META_APP_ID", "test-app-id")
os.environ.setdefault("META_APP_SECRET", "test-app-secret")
os.environ.setdefault("META_VERIFY_TOKEN", "test-verify-token")
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "x.eyJyb2xlIjogInNlcnZpY2Vfcm9sZSJ9.y")
os.environ.setdefault("ENCRYPTION_KEY", "oZRrOD525wcQ0CJveupENSX1tDwKfP6e1XrDGn9P1Kw=")

import asyncio

from pydantic_ai.messages import (
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

import app.services.storefront as storefront
from app.ai.agents.client import client_agent
from app.services.erp.context import ERPContext

CTX = ERPContext(tenant_id="t1", actor="whatsapp_bot", actor_label="Bot WhatsApp")


def _tool_calls(result):
    return [
        p.tool_name
        for msg in result.all_messages()
        for p in getattr(msg, "parts", [])
        if isinstance(p, ToolCallPart)
    ]


def test_register_sale_esta_deferida_al_inicio(monkeypatch):
    """Al arrancar, el modelo ve search_catalog y load_capability, pero NO
    register_sale: vive detrás de la capacidad deferida `cerrar-venta`."""

    async def fake_search(ctx, query=None):
        return [{"id": "p1", "name": "Café", "price": 1000, "in_stock": True,
                 "description": "", "tags": []}]

    monkeypatch.setattr(storefront, "search_catalog", fake_search)

    # call_tools=['search_catalog']: TestModel solo llama esa tool (no inventa
    # un id basura para load_capability).
    model = TestModel(call_tools=["search_catalog"])
    asyncio.run(client_agent.run("hola", model=model, deps=CTX))

    visibles = {t.name for t in model.last_model_request_parameters.function_tools}
    assert "search_catalog" in visibles
    assert "load_capability" in visibles      # la agrega el framework por la capability deferida
    assert "register_sale" not in visibles    # deferida: todavía no se ve


def test_cierre_de_venta_carga_la_capability(monkeypatch):
    """Flujo realista: el modelo carga `cerrar-venta` con load_capability y recién
    entonces puede llamar a register_sale."""

    venta = {}

    async def fake_sale(ctx, items, customer_phone=None, payment_method="whatsapp"):
        venta["items"] = items
        return {"ok": True, "sale_id": "s1"}

    monkeypatch.setattr(storefront, "register_sale", fake_sale)

    def vendedor(messages, info: AgentInfo) -> ModelResponse:
        # Mientras la capacidad esté deferida, register_sale aparece pero con
        # defer_loading=True (no se puede usar). "Disponible" = ya cargada.
        disponibles = {t.name for t in info.function_tools if not getattr(t, "defer_loading", False)}
        ya_corrieron = {
            p.tool_name
            for msg in messages
            for p in getattr(msg, "parts", [])
            if isinstance(p, ToolReturnPart)
        }
        # 1) register_sale todavía deferida → cargo la capacidad de cierre.
        if "register_sale" not in disponibles:
            return ModelResponse(parts=[ToolCallPart("load_capability", {"id": "cerrar-venta"})])
        # 2) ya disponible y todavía no la llamé → la llamo.
        if "register_sale" not in ya_corrieron:
            return ModelResponse(parts=[ToolCallPart(
                "register_sale", {"items": [{"product_id": "p1", "quantity": 1}]})])
        # 3) listo.
        return ModelResponse(parts=[TextPart("listo, registré la venta")])

    result = asyncio.run(client_agent.run("quiero 1 café", model=FunctionModel(vendedor), deps=CTX))

    llamadas = _tool_calls(result)
    assert "load_capability" in llamadas      # primero cargó la capacidad
    assert "register_sale" in llamadas        # después registró la venta
    assert venta["items"] == [{"product_id": "p1", "quantity": 1}]
    assert result.output == "listo, registré la venta"

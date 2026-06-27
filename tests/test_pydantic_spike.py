"""Tests del spike de Pydantic AI (rama spike/pydantic-ai).

Validan el client agent alternativo a Agno sin pegar a la red: usan TestModel
(que ejecuta todas las tools del agente) y mockean la capa storefront.

app.config instancia Settings() al importar; seteamos env defaults antes del import.
"""

import os

os.environ.setdefault("META_APP_ID", "test-app-id")
os.environ.setdefault("META_APP_SECRET", "test-app-secret")
os.environ.setdefault("META_VERIFY_TOKEN", "test-verify-token")
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "x.eyJyb2xlIjogInNlcnZpY2Vfcm9sZSJ9.y")
os.environ.setdefault("ENCRYPTION_KEY", "oZRrOD525wcQ0CJveupENSX1tDwKfP6e1XrDGn9P1Kw=")
os.environ.setdefault("AGNO_DB_URL", "")

import asyncio

from pydantic_ai.messages import ToolCallPart
from pydantic_ai.models.test import TestModel

import app.services.storefront as storefront
from app.ai.pydantic_spike import history
from app.ai.pydantic_spike.agent import ClientDeps, client_agent
from app.ai.pydantic_spike.model import model_string
from app.ai.pydantic_spike.skills import load_skills_text
from app.services.erp.context import ERPContext

CTX = ERPContext(tenant_id="t1", actor="whatsapp_bot", actor_label="Bot WhatsApp")


def _deps():
    return ClientDeps(ctx=CTX, system_prompt="Sos un vendedor.")


def _tool_calls(result):
    return [
        p.tool_name
        for msg in result.all_messages()
        for p in getattr(msg, "parts", [])
        if isinstance(p, ToolCallPart)
    ]


def _patch_storefront(monkeypatch):
    async def fake_business_info(ctx):
        return {"name": "Tienda Demo", "hours": "9-18"}

    async def fake_search(ctx, query=None):
        return [{"id": "p1", "name": "Café", "price": 1000, "in_stock": True,
                 "description": "", "tags": []}]

    async def fake_sale(ctx, items, customer_phone=None, payment_method="whatsapp"):
        return {"ok": True, "sale_id": "s1"}

    monkeypatch.setattr(storefront, "business_info", fake_business_info)
    monkeypatch.setattr(storefront, "search_catalog", fake_search)
    monkeypatch.setattr(storefront, "register_sale", fake_sale)


def test_model_string_routing():
    assert model_string("claude-sonnet-4-20250514") == "anthropic:claude-sonnet-4-20250514"
    assert model_string("gpt-4o") == "openai:gpt-4o"
    # id desconocido cae al DEFAULT_MODEL (claude) con prefijo anthropic
    assert model_string("desconocido").startswith("anthropic:")


def test_skills_load_strips_frontmatter():
    text = load_skills_text("catalogo-productos")
    assert text                       # no vacío
    assert not text.startswith("---")  # frontmatter removido
    assert "# Skill: catalogo-productos" in text


def test_agent_runs_tools_with_testmodel(monkeypatch):
    _patch_storefront(monkeypatch)

    async def run():
        # TestModel ejecuta cada tool registrada en el agente.
        result = await client_agent.run("hola", model=TestModel(), deps=_deps())
        return _tool_calls(result)

    calls = asyncio.run(run())
    assert "search_catalog" in calls
    assert "register_sale" in calls


def test_history_accumulates_across_runs(monkeypatch):
    _patch_storefront(monkeypatch)
    sid = history.session_id_for("t-hist", "555")

    async def run():
        r1 = await client_agent.run("hola", model=TestModel(), deps=_deps(),
                                    message_history=history.load(sid))
        history.append(sid, r1.new_messages())
        len1 = len(history.load(sid))
        r2 = await client_agent.run("dale", model=TestModel(), deps=_deps(),
                                    message_history=history.load(sid))
        history.append(sid, r2.new_messages())
        return len1, len(history.load(sid))

    len1, len2 = asyncio.run(run())
    assert len1 > 0
    assert len2 > len1   # el historial crece run a run

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

from app.ai.agents import manager as manager_mod
from app.ai.agents.manager import ManagerDeps, manager_agent
from app.services.erp.context import ERPContext

CTX = ERPContext(tenant_id="t1", actor="admin_bot", actor_label="Bot Admin")


def _tool_names(result):
    return [
        p.tool_name
        for msg in result.all_messages()
        for p in getattr(msg, "parts", [])
        if isinstance(p, ToolCallPart)
    ]


def test_manager_runs_read_tools(monkeypatch):
    class FakeReports:
        async def dashboard(self, ctx, date_from, date_to):
            return {"sales_total": 0}

    class FakeProducts:
        async def list(self, ctx, search=None, limit=50):
            return [{"id": "p1", "name": "Café", "unit": "u", "stock": 3,
                     "price": 1000, "category": None}]

    monkeypatch.setattr(manager_mod, "ReportsService", FakeReports)
    monkeypatch.setattr(manager_mod, "ProductsService", FakeProducts)

    deps = ManagerDeps(ctx=CTX, system_prompt="Sos el asistente del dueño.")

    async def run():
        result = await manager_agent.run("estado", model=TestModel(), deps=deps)
        return _tool_names(result)

    names = asyncio.run(run())
    assert "get_dashboard_summary" in names
    assert "get_stock" in names

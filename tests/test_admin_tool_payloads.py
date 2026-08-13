"""Enforcement suite: admin tools must return compact text within a declared
budget, never the raw ERP row.

The ERP services are monkeypatched to return a deliberately fat dataset —
long lists, nulls everywhere, uuids on every row, microsecond timestamps —
the same shape the real inventory_movements/sales/transactions tables return.
`app/services/admin_view.py` must trim it, `app/ai_core/tools/render.py` must
format it, and this test is what keeps a future tool from skipping that path
and dumping a service's raw output straight to the model.

Monkeypatches the ERP *services*, not the Supabase client: `tests/fakes/supabase.py`
ignores `select()` field lists and doesn't resolve nested joins, so a payload
test against the fake client would pass even if a tool leaked a field the
fake happens not to model.
"""

from __future__ import annotations

import asyncio
import re

import pytest

from app.ai_core.config.tenant import AdminAgentConfig, PublicAgentConfig, TenantConfig
from app.ai_core.tools import admin as admin_tools
from app.ai_core.tools.context import ToolContext
from app.services.erp.admin_actions import AdminActionService
from app.services.erp.clients import ClientsService
from app.services.erp.finance import FinanceService
from app.services.erp.inventory import InventoryService
from app.services.erp.products import ProductsService
from app.services.erp.reports import ReportsService
from app.services.erp.sales import SalesService

TENANT = TenantConfig(
    tenant_id="tenant-1",
    business_name="Kiosco",
    public_agent=PublicAgentConfig(),
    admin_agent=AdminAgentConfig(allowed_numbers=["59170000001"]),
)

FAT_TIMESTAMP = "2026-06-17T09:38:53.471743+00:00"
FAT_DATE = "2026-06-17"
UUID = "a1000001-0000-0000-0000-000000000001"

_FORBIDDEN_TOKENS = (
    "tenant_id", "idempotency_key", "updated_at", "created_at", "reference_id",
    "variant_id", "admin_action_id", "unit_cost", "None", "null",
)
_ISO_TIME_RE = re.compile(r"T\d{2}:\d{2}:\d{2}")

# Every list a tool can return is already capped by admin_view (see its topes
# table); with those caps, a uuid on every anchored row and realistic-length
# names, this is what the rendered text tops out at — generous enough to not
# be brittle, tight enough that a raw `select("*")` dump (10x this) still fails.
BUDGET = {
    "get_business_overview": 400,
    "get_sales_analysis": 1100,
    "get_inventory_alerts": 1900,
    "find_customers": 1300,
    "get_customer_details": 500,
    "list_recent_sales": 1600,
    "get_sale_details": 600,
    "get_cash_summary": 900,
    "propose_stock_adjustment": 200,
    "propose_product_change": 200,
    "propose_transaction": 200,
    "propose_sale_cancellation": 200,
    "execute_confirmed_action": 250,
}

# Tools shared with the public agent stay structured (JSON), by design — see
# CLAUDE.md. Every other admin tool must be in BUDGET, enforced below.
_SHARED_STRUCTURED_TOOLS = {"search_catalog", "check_stock", "get_config"}


def _ctx(outbox=None):
    return ToolContext(tenant=TENANT, role="admin", thread_id="tenant-1:admin:59170000001", outbox=outbox)


def _assert_within_budget(tool_name: str, result: str) -> None:
    assert isinstance(result, str), f"{tool_name} must return str, got {type(result)}"
    budget = BUDGET[tool_name]
    assert len(result) <= budget, f"{tool_name} returned {len(result)} chars, budget is {budget}:\n{result}"
    for token in _FORBIDDEN_TOKENS:
        assert token not in result, f"{tool_name} leaked forbidden token {token!r}:\n{result}"
    assert not _ISO_TIME_RE.search(result), f"{tool_name} leaked a raw ISO timestamp:\n{result}"


def test_every_admin_tool_has_a_declared_budget():
    """Adding a tool to ADMIN_TOOLS without a BUDGET entry must break the suite."""
    from app.ai_core.admin.tools import ADMIN_TOOLS

    names = {t.name for t in ADMIN_TOOLS} - _SHARED_STRUCTURED_TOOLS
    missing = names - set(BUDGET)
    assert not missing, f"admin tools with no declared payload budget: {sorted(missing)}"


# --------------------------------------------------------------------------
# fat fixtures
# --------------------------------------------------------------------------


def _fat_low_stock(n=30):
    return [
        {"product_id": f"{UUID[:-2]}{i:02d}", "product_name": f"Producto {i}", "quantity": 1,
         "low_stock_threshold": 5, "unit": "unidad", "category": "Bebidas",
         "tenant_id": "tenant-1"}
        for i in range(n)
    ]


def _fat_movements(n):
    return [
        {"id": f"m{i}", "product_id": "p1", "type": "sale", "quantity": 2,
         "unit_cost": None, "reference_id": None, "notes": None, "actor": "admin_bot",
         "created_at": FAT_TIMESTAMP, "product_name": "Cerveza Paceña"}
        for i in range(n)
    ]


def _fat_clients(n):
    return [
        {"id": f"{UUID[:-2]}{i:02d}", "name": f"Cliente {i}", "phone": f"5917000{i:04d}", "email": None,
         "address": None, "notes": None, "tags": [], "whatsapp_id": None, "total_purchases": 100.0,
         "purchase_count": 3, "last_purchase_at": FAT_TIMESTAMP, "created_at": FAT_TIMESTAMP,
         "tenant_id": "tenant-1"}
        for i in range(n)
    ]


def _fat_sales(n):
    return [
        {"id": f"{UUID[:-2]}{i:02d}", "tenant_id": "tenant-1", "client_id": None, "status": "completed",
         "payment_method": "efectivo", "subtotal": 200.0, "discount": 0, "total": 206.0, "notes": None,
         "actor": "admin_bot", "created_at": FAT_TIMESTAMP, "updated_at": FAT_TIMESTAMP,
         "idempotency_key": f"key-{i}"}
        for i in range(n)
    ]


def _fat_sale_items(n):
    return [
        {"id": f"si{i}", "tenant_id": "tenant-1", "sale_id": "s1", "product_id": f"p{i}",
         "product_name": f"Producto {i}", "quantity": 2, "unit_price": 10.0, "unit_cost": None, "total": 20.0}
        for i in range(n)
    ]


def _fat_transactions(n):
    return [
        {"id": f"t{i}", "tenant_id": "tenant-1", "type": "expense", "amount": 50.0, "category": "Otros",
         "description": None, "cash_account_id": None, "sale_id": None, "actor": "admin_bot",
         "date": FAT_DATE, "created_at": FAT_TIMESTAMP, "admin_action_id": None}
        for i in range(n)
    ]


def _fat_accounts(n=3):
    return [
        {"id": f"acc{i}", "name": f"Cuenta {i}", "type": "cash", "balance": 500.0,
         "is_default": i == 0, "is_active": True}
        for i in range(n)
    ]


def _fat_trend(n=30):
    return [{"period": f"2026-06-{i + 1:02d}", "total": 100.0, "count": 3} for i in range(n)]


# --------------------------------------------------------------------------
# reads
# --------------------------------------------------------------------------


def test_get_business_overview_payload(monkeypatch):
    async def dashboard(self, ctx, *, date_from, date_to):
        return {
            "period": {"from": date_from, "to": date_to}, "sales_total": 20600.0, "sales_count": 150,
            "gross_margin": 8200.0, "gross_margin_pct": 40.0, "new_clients": 30, "low_stock_count": 25,
            "top_product": {"name": "Cerveza Paceña muy larga con nombre extendido", "units_sold": 220.0},
            "cash_balances": _fat_accounts(),
        }

    monkeypatch.setattr(ReportsService, "dashboard", dashboard)
    result = asyncio.run(admin_tools.get_business_overview.ainvoke({"ctx": _ctx()}))
    _assert_within_budget("get_business_overview", result)


def test_get_sales_analysis_payload(monkeypatch):
    async def sale_items_in_period(tenant_id, date_from, date_to):
        items = []
        for i in range(50):
            items.append({
                "product_id": f"p{i}", "product_name": f"Producto con nombre largo {i}",
                "quantity": 3, "unit_price": 20.0, "unit_cost": 12.0, "total": 60.0,
                "products": {"category": f"Categoría {i % 5}"},
            })
        return items

    async def sales_by_period(self, ctx, *, date_from, date_to, group_by="day"):
        return _fat_trend()

    monkeypatch.setattr("app.services.admin_view._sale_items_in_period", sale_items_in_period)
    monkeypatch.setattr(ReportsService, "sales_by_period", sales_by_period)
    result = asyncio.run(admin_tools.get_sales_analysis.ainvoke({"ctx": _ctx()}))
    _assert_within_budget("get_sales_analysis", result)


def test_get_inventory_alerts_payload(monkeypatch):
    async def low_stock(self, ctx):
        return _fat_low_stock(30)

    async def movements(self, ctx, *, product_id=None, limit=50, offset=0):
        return _fat_movements(limit)

    monkeypatch.setattr(InventoryService, "low_stock", low_stock)
    monkeypatch.setattr(InventoryService, "movements", movements)
    result = asyncio.run(admin_tools.get_inventory_alerts.ainvoke({"ctx": _ctx()}))
    _assert_within_budget("get_inventory_alerts", result)
    assert "… +" in result, "the fat fixture must trigger the cut tail"


def test_find_customers_payload(monkeypatch):
    async def list_clients(self, ctx, *, search=None, tag=None, limit=50, offset=0):
        return _fat_clients(limit)

    monkeypatch.setattr(ClientsService, "list", list_clients)
    result = asyncio.run(admin_tools.find_customers.ainvoke({"query": "cliente", "ctx": _ctx()}))
    _assert_within_budget("find_customers", result)
    assert "… +" in result


def test_get_customer_details_payload(monkeypatch):
    async def get_client(self, ctx, client_id):
        client = _fat_clients(1)[0]
        client["recent_sales"] = [
            {"id": f"s{i}", "total": 100.0, "status": "completed", "created_at": FAT_TIMESTAMP}
            for i in range(20)
        ]
        return client

    monkeypatch.setattr(ClientsService, "get", get_client)
    result = asyncio.run(admin_tools.get_customer_details.ainvoke({"client_id": "c1", "ctx": _ctx()}))
    _assert_within_budget("get_customer_details", result)


def test_list_recent_sales_payload(monkeypatch):
    async def list_sales(self, ctx, *, client_id=None, date_from=None, date_to=None, limit=50, offset=0):
        return _fat_sales(limit)

    monkeypatch.setattr(SalesService, "list", list_sales)
    result = asyncio.run(admin_tools.list_recent_sales.ainvoke({"ctx": _ctx()}))
    _assert_within_budget("list_recent_sales", result)
    assert "… +" in result


def test_get_sale_details_payload(monkeypatch):
    async def get_sale(self, ctx, sale_id):
        sale = _fat_sales(1)[0]
        sale["items"] = _fat_sale_items(40)
        return sale

    monkeypatch.setattr(SalesService, "get", get_sale)
    result = asyncio.run(admin_tools.get_sale_details.ainvoke({"sale_id": "s1", "ctx": _ctx()}))
    _assert_within_budget("get_sale_details", result)


def test_get_cash_summary_payload(monkeypatch):
    async def list_accounts(self, ctx):
        return _fat_accounts()

    async def cashflow(self, ctx, *, date_from, date_to, group_by="day"):
        return {"from": date_from, "to": date_to, "group_by": group_by, "income": 5000.0,
                "expense": 3000.0, "net": 2000.0,
                "series": [{"period": f"2026-06-{i + 1:02d}", "income": 100.0, "expense": 50.0} for i in range(30)]}

    async def list_transactions(self, ctx, *, type=None, category=None, account_id=None,
                                date_from=None, date_to=None, limit=50, offset=0):
        return _fat_transactions(limit)

    monkeypatch.setattr(FinanceService, "list_accounts", list_accounts)
    monkeypatch.setattr(FinanceService, "cashflow", cashflow)
    monkeypatch.setattr(FinanceService, "list_transactions", list_transactions)
    result = asyncio.run(admin_tools.get_cash_summary.ainvoke({"ctx": _ctx()}))
    _assert_within_budget("get_cash_summary", result)
    assert "… +" in result


# --------------------------------------------------------------------------
# propose_* / execute_confirmed_action
# --------------------------------------------------------------------------


def test_propose_stock_adjustment_payload(monkeypatch):
    async def get_product(self, ctx, product_id):
        return {"id": product_id, "name": "Cerveza Paceña con nombre bien largo", "tenant_id": "tenant-1"}

    async def create_action(self, ctx, *, thread_id, kind, payload, summary):
        return {"id": UUID}

    monkeypatch.setattr(ProductsService, "get", get_product)
    monkeypatch.setattr(AdminActionService, "create", create_action)
    result = asyncio.run(admin_tools.propose_stock_adjustment.ainvoke(
        {"product_id": "p1", "quantity": 22, "ctx": _ctx()}))
    _assert_within_budget("propose_stock_adjustment", result)


def test_propose_transaction_payload(monkeypatch):
    async def create_action(self, ctx, *, thread_id, kind, payload, summary):
        return {"id": UUID}

    monkeypatch.setattr(AdminActionService, "create", create_action)
    result = asyncio.run(admin_tools.propose_transaction.ainvoke(
        {"type": "expense", "amount": 50, "category": "Servicios muy detallados", "ctx": _ctx()}))
    _assert_within_budget("propose_transaction", result)


def test_propose_sale_cancellation_payload(monkeypatch):
    async def get_sale(self, ctx, sale_id):
        return {"id": sale_id, "status": "completed", "total": 206.0, "tenant_id": "tenant-1"}

    async def create_action(self, ctx, *, thread_id, kind, payload, summary):
        return {"id": UUID}

    monkeypatch.setattr(SalesService, "get", get_sale)
    monkeypatch.setattr(AdminActionService, "create", create_action)
    result = asyncio.run(admin_tools.propose_sale_cancellation.ainvoke({"sale_id": UUID, "ctx": _ctx()}))
    _assert_within_budget("propose_sale_cancellation", result)


def test_execute_confirmed_action_payload(monkeypatch):
    async def claim(self, ctx, *, thread_id, action_id):
        return {"id": action_id, "status": "confirmed", "kind": "stock_adjustment",
                "payload": {"product_id": "p1", "quantity": 22, "product_name": "Cerveza Paceña"}}

    async def adjust(self, ctx, *, product_id, new_quantity, delta, note):
        return {"ok": True, "product_id": product_id, "quantity": new_quantity, "movement": None}

    async def complete(self, action_id, result):
        return {"id": action_id, "status": "executed", "result": result}

    monkeypatch.setattr(AdminActionService, "claim", claim)
    monkeypatch.setattr(InventoryService, "adjust", adjust)
    monkeypatch.setattr(AdminActionService, "complete", complete)
    ctx = ToolContext(tenant=TENANT, role="admin", thread_id="tenant-1:admin:59170000001",
                       confirmed_action_id=UUID)
    result = asyncio.run(admin_tools.execute_confirmed_action.ainvoke({"action_id": UUID, "ctx": ctx}))
    _assert_within_budget("execute_confirmed_action", result)


@pytest.mark.parametrize("tool_name", sorted(BUDGET))
def test_budgets_are_positive(tool_name):
    assert BUDGET[tool_name] > 0

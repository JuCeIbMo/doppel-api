"""Capa de lectura/consulta del agente admin de cara al dueño (WhatsApp).

Recibe siempre un ERPContext con actor="admin_bot", reusa los ERP services
existentes y devuelve shapes lean con listas ya acotadas y el sobrante
contado — mismo espíritu que `storefront.py` para el agente público. La
diferencia: acá el consumidor final es texto compacto
(`app/ai_core/tools/render.py`), no JSON estructurado, así que los shapes de
este módulo son un paso intermedio, no la respuesta final.
"""

from __future__ import annotations

from app.services.erp.clients import ClientsService
from app.services.erp.context import ERPContext
from app.services.erp.finance import FinanceService
from app.services.erp.inventory import InventoryService
from app.services.erp.products import ProductsService
from app.services.erp.reports import (
    ReportsService,
    _aggregate_margin,
    _aggregate_top_products,
    _sale_items_in_period,
    default_period,
)
from app.services.erp.sales import SalesService

LOW_STOCK_CAP = 15
MOVEMENTS_CAP = 10
CUSTOMERS_CAP = 10
SALES_CAP = 15
SALE_ITEMS_CAP = 20
TRANSACTIONS_CAP = 10
CUSTOMER_SALES_CAP = 5
TOP_N_CAP = 5
TREND_CAP = 14


def _cut(rows: list, cap: int) -> tuple[list, int]:
    """Same convention as `storefront.search_catalog`: the caller already asked
    for `cap + 1` rows, this derives the visible slice and the leftover count."""
    extra = max(0, len(rows) - cap)
    return rows[:cap], extra


async def business_overview(ctx: ERPContext, date_from: str | None = None,
                            date_to: str | None = None) -> dict:
    f, t = default_period(date_from, date_to)
    return await ReportsService().dashboard(ctx, date_from=f, date_to=t)


async def sales_analysis(ctx: ERPContext, date_from: str | None = None,
                         date_to: str | None = None) -> dict:
    f, t = default_period(date_from, date_to)
    # Un solo fetch de sale_items para top_products y margin en vez de que cada
    # uno vuelva a consultar (ver app/services/erp/reports.py).
    items = await _sale_items_in_period(ctx.tenant_id, f, t)
    top_products = _aggregate_top_products(items, TOP_N_CAP)
    margin = _aggregate_margin(items)
    margin["by_product"] = margin["by_product"][:TOP_N_CAP]
    margin["by_category"] = margin["by_category"][:TOP_N_CAP]
    trend = (await ReportsService().sales_by_period(ctx, date_from=f, date_to=t))[-TREND_CAP:]
    return {"period": {"from": f, "to": t}, "top_products": top_products, "trend": trend, "margin": margin}


async def inventory_alerts(ctx: ERPContext) -> dict:
    service = InventoryService()
    # low_stock ya trae todas las filas bajo el mínimo (filtra en Python sobre
    # hasta 1000 filas); el corte es acá, no en el fetch.
    low_stock, low_extra = _cut(await service.low_stock(ctx), LOW_STOCK_CAP)
    movements, movements_extra = _cut(
        await service.movements(ctx, limit=MOVEMENTS_CAP + 1), MOVEMENTS_CAP)
    return {
        "low_stock": [
            {"product_id": r["product_id"], "product_name": r["product_name"],
             "quantity": r["quantity"], "threshold": r["low_stock_threshold"], "unit": r["unit"]}
            for r in low_stock
        ],
        "low_stock_extra": low_extra,
        "movements": [
            {"when": m["created_at"], "type": m["type"],
             "product_name": m["product_name"], "quantity": m["quantity"]}
            for m in movements
        ],
        "movements_extra": movements_extra,
    }


async def find_customers(ctx: ERPContext, query: str) -> dict:
    rows, extra = _cut(
        await ClientsService().list(ctx, search=query, limit=CUSTOMERS_CAP + 1), CUSTOMERS_CAP)
    return {
        "items": [
            {"id": c["id"], "name": c["name"], "phone": c["phone"],
             "purchase_count": c["purchase_count"], "total_purchases": c["total_purchases"],
             "last_purchase_at": c.get("last_purchase_at")}
            for c in rows
        ],
        "extra": extra,
    }


async def customer_details(ctx: ERPContext, client_id: str) -> dict:
    client = await ClientsService().get(ctx, client_id)
    return {
        "customer": {"name": client["name"], "phone": client["phone"],
                     "purchase_count": client["purchase_count"],
                     "total_purchases": client["total_purchases"]},
        "recent_sales": client.get("recent_sales", [])[:CUSTOMER_SALES_CAP],
    }


async def recent_sales(ctx: ERPContext, date_from: str | None = None,
                       date_to: str | None = None) -> dict:
    rows, extra = _cut(
        await SalesService().list(ctx, date_from=date_from, date_to=date_to, limit=SALES_CAP + 1),
        SALES_CAP,
    )
    return {
        "items": [
            {"id": s["id"], "created_at": s["created_at"], "total": s["total"],
             "status": s["status"], "payment_method": s.get("payment_method")}
            for s in rows
        ],
        "extra": extra,
    }


async def sale_details(ctx: ERPContext, sale_id: str) -> dict:
    sale = await SalesService().get(ctx, sale_id)
    items = sale.get("items", [])[:SALE_ITEMS_CAP]
    return {
        "sale": {"created_at": sale["created_at"], "status": sale["status"],
                 "payment_method": sale.get("payment_method"), "total": sale["total"]},
        "items": [
            {"product_name": i["product_name"], "quantity": i["quantity"], "total": i["total"]}
            for i in items
        ],
    }


async def cash_summary(ctx: ERPContext, date_from: str | None = None,
                       date_to: str | None = None) -> dict:
    f, t = default_period(date_from, date_to)
    service = FinanceService()
    accounts = await service.list_accounts(ctx)
    cashflow = await service.cashflow(ctx, date_from=f, date_to=t)
    transactions, extra = _cut(
        await service.list_transactions(ctx, limit=TRANSACTIONS_CAP + 1), TRANSACTIONS_CAP)
    return {
        "period": {"from": f, "to": t},
        "accounts": [{"name": a["name"], "balance": a["balance"]} for a in accounts],
        # El día a día del flujo vive en sales_analysis; acá sólo el resumen del
        # período — la serie diaria es ruido para una respuesta de WhatsApp.
        "cashflow": {"income": cashflow["income"], "expense": cashflow["expense"], "net": cashflow["net"]},
        "transactions": [
            {"date": tr["date"], "type": tr["type"], "category": tr.get("category"), "amount": tr["amount"]}
            for tr in transactions
        ],
        "transactions_extra": extra,
    }


async def product_brief(ctx: ERPContext, product_id: str) -> dict:
    """Nombre de un producto, para el mensaje de una propuesta de stock/edición."""
    product = await ProductsService().get(ctx, product_id)
    return {"name": product["name"]}


async def sale_brief(ctx: ERPContext, sale_id: str) -> dict:
    """Estado y total de una venta, para validar y describir una cancelación."""
    sale = await SalesService().get(ctx, sale_id)
    return {"status": sale["status"], "total": sale["total"]}

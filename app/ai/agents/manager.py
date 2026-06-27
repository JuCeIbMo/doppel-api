"""Manager agent (asistente de admins) sobre Pydantic AI — versión mínima.

Solo tools de LECTURA: resumen del negocio y consulta de stock. Las de escritura
(crear venta, ajustar stock) quedan fuera de esta versión minimalista.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from pydantic_ai import Agent, RunContext

from app.services.erp.context import ERPContext
from app.services.erp.inventory import InventoryService
from app.services.erp.products import ProductsService
from app.services.erp.reports import ReportsService


@dataclass
class ManagerDeps:
    ctx: ERPContext
    system_prompt: str


def _period_dates(period: str, dfrom: str | None, dto: str | None) -> tuple[str, str]:
    today = date.today()
    if period == "today":
        return today.isoformat(), today.isoformat()
    if period == "week":
        return (today - timedelta(days=today.weekday())).isoformat(), today.isoformat()
    if period == "custom" and dfrom and dto:
        return dfrom, dto
    return today.replace(day=1).isoformat(), today.isoformat()


manager_agent = Agent(deps_type=ManagerDeps)


@manager_agent.instructions
def tenant_system_prompt(ctx: RunContext[ManagerDeps]) -> str:
    return ctx.deps.system_prompt


@manager_agent.tool
async def get_dashboard_summary(
    ctx: RunContext[ManagerDeps],
    period: str = "month",
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """Resumen del negocio en un período: ventas totales, número de ventas, margen
    bruto, clientes nuevos, productos con stock bajo y saldo de cajas.

    Args:
        period: today | week | month | custom
        date_from: YYYY-MM-DD, requerido si period=custom
        date_to: YYYY-MM-DD, requerido si period=custom
    """
    f, t = _period_dates(period, date_from, date_to)
    return await ReportsService().dashboard(ctx.deps.ctx, date_from=f, date_to=t)


@manager_agent.tool
async def get_stock(
    ctx: RunContext[ManagerDeps],
    product_name: str | None = None,
    low_stock_only: bool = False,
) -> list:
    """Consulta el stock de uno o todos los productos. Filtra por nombre o stock bajo.

    Args:
        product_name: filtra por nombre (coincidencia parcial)
        low_stock_only: solo productos por debajo de su umbral
    """
    if low_stock_only:
        return await InventoryService().low_stock(ctx.deps.ctx)
    rows = await ProductsService().list(ctx.deps.ctx, search=product_name, limit=50)
    return [
        {"product_id": r["id"], "product_name": r["name"], "category": r.get("category"),
         "unit": r["unit"], "stock": r.get("stock", 0), "price": r["price"]}
        for r in rows
    ]

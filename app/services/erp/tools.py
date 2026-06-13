"""ERP tools for the manager/admin AI assistant.

Each tool builds an ERPContext(actor="admin_bot") and calls the SAME service the HTTP
endpoints use. No business logic is reimplemented here — a sale made by the bot goes
through the exact `create_sale` RPC a dashboard sale does. Registered into the manager
registry in app/services/tool_runtime.py; ai_core discovers them via /internal/ai/tools.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from supabase import Client

from app.services.agent_core import (
    BooleanSchema,
    IntegerSchema,
    NumberSchema,
    StringSchema,
    Tool,
    ToolRegistry,
    tool_parameters,
    tool_parameters_schema,
)
from app.services.erp.clients import ClientsService
from app.services.erp.context import ERPContext, bot_context
from app.services.erp.exceptions import ERPError, NotFound
from app.services.erp.inventory import InventoryService
from app.services.erp.products import ProductsService
from app.services.erp.reports import ReportsService
from app.services.erp.sales import SalesService


def _period_dates(period: str, dfrom: str | None, dto: str | None) -> tuple[str, str]:
    today = date.today()
    if period == "today":
        return today.isoformat(), today.isoformat()
    if period == "week":
        return (today - timedelta(days=today.weekday())).isoformat(), today.isoformat()
    if period == "custom" and dfrom and dto:
        return dfrom, dto
    return today.replace(day=1).isoformat(), today.isoformat()  # month (default)


class _ERPTool(Tool):
    """Base: binds the tenant and exposes an admin-bot ERPContext."""

    def __init__(self, supabase: Client, tenant_id: str) -> None:
        self._tenant_id = tenant_id

    @property
    def ctx(self) -> ERPContext:
        return bot_context(self._tenant_id, actor="admin_bot")


@tool_parameters(
    tool_parameters_schema(
        period=StringSchema(description="today | week | month | custom"),
        date_from=StringSchema(description="YYYY-MM-DD, required if period=custom"),
        date_to=StringSchema(description="YYYY-MM-DD, required if period=custom"),
        required=[],
    )
)
class GetDashboardSummaryTool(_ERPTool):
    @property
    def name(self) -> str:
        return "get_dashboard_summary"

    @property
    def description(self) -> str:
        return ("Resumen del negocio en un período: ventas totales, número de ventas, "
                "margen bruto, clientes nuevos, productos con stock bajo y saldo de cajas.")

    @property
    def read_only(self) -> bool:
        return True

    async def execute(self, period: str = "month", date_from: str | None = None,
                      date_to: str | None = None, **_: Any) -> Any:
        f, t = _period_dates(period, date_from, date_to)
        return await ReportsService().dashboard(self.ctx, date_from=f, date_to=t)


@tool_parameters(
    tool_parameters_schema(
        product_name=StringSchema(description="Filtra por nombre (coincidencia parcial)"),
        low_stock_only=BooleanSchema(description="Solo productos por debajo de su umbral"),
        required=[],
    )
)
class GetStockTool(_ERPTool):
    @property
    def name(self) -> str:
        return "get_stock"

    @property
    def description(self) -> str:
        return "Consulta el stock de uno o todos los productos. Filtra por nombre o por stock bajo."

    @property
    def read_only(self) -> bool:
        return True

    async def execute(self, product_name: str | None = None, low_stock_only: bool = False,
                      **_: Any) -> Any:
        if low_stock_only:
            return await InventoryService().low_stock(self.ctx)
        rows = await ProductsService().list(self.ctx, search=product_name, limit=50)
        return [{"product_id": r["id"], "product_name": r["name"], "category": r.get("category"),
                 "unit": r["unit"], "stock": r.get("stock", 0), "price": r["price"]} for r in rows]


@tool_parameters(
    tool_parameters_schema(
        period=StringSchema(description="today | week | month"),
        limit=IntegerSchema(description="Cuántos productos", minimum=1, maximum=50),
        required=[],
    )
)
class GetTopProductsTool(_ERPTool):
    @property
    def name(self) -> str:
        return "get_top_products"

    @property
    def description(self) -> str:
        return "Productos más vendidos del período, por unidades e ingresos."

    @property
    def read_only(self) -> bool:
        return True

    async def execute(self, period: str = "month", limit: int = 5, **_: Any) -> Any:
        f, t = _period_dates(period, None, None)
        return await ReportsService().top_products(self.ctx, date_from=f, date_to=t, limit=limit)


@tool_parameters(
    tool_parameters_schema(
        items={
            "type": "array",
            "description": "Productos vendidos",
            "items": {
                "type": "object",
                "required": ["product_id", "quantity"],
                "properties": {
                    "product_id": {"type": "string"},
                    "quantity": {"type": "number"},
                    "unit_price": {"type": "number", "description": "Si se omite, usa el precio del catálogo"},
                },
            },
        },
        payment_method=StringSchema(description="cash | card | transfer | whatsapp | other"),
        client_phone=StringSchema(description="Teléfono para asociar la compra a un cliente"),
        required=["items", "payment_method"],
    )
)
class CreateSaleTool(_ERPTool):
    @property
    def name(self) -> str:
        return "create_sale"

    @property
    def description(self) -> str:
        return ("Registra una venta. Baja el stock y registra el ingreso automáticamente, "
                "de forma atómica. 'items' es una lista de {product_id, quantity, unit_price?}. "
                "Si unit_price se omite, usa el precio del catálogo.")

    async def execute(self, items: list[dict] | None = None, payment_method: str = "cash",
                      client_phone: str | None = None, **_: Any) -> Any:
        if not items:
            return {"error": "Se requiere al menos un ítem"}
        client_id = None
        if client_phone:
            try:
                client_id = (await ClientsService().get_by_phone(self.ctx, client_phone))["id"]
            except NotFound:
                client_id = None
        body = {
            "client_id": client_id,
            "payment_method": payment_method,
            "cash_account_id": None,
            "discount": 0,
            "notes": None,
            "items": items,
        }
        try:
            return await SalesService().create_sale(self.ctx, body)
        except ERPError as exc:
            return {"error": exc.code, "message": exc.message, "detail": exc.detail}


@tool_parameters(
    tool_parameters_schema(
        product_id=StringSchema(description="ID del producto"),
        new_quantity=NumberSchema(description="Cantidad real contada (stock objetivo)"),
        reason=StringSchema(description="Motivo del ajuste (ej: conteo físico)"),
        required=["product_id", "new_quantity", "reason"],
    )
)
class AdjustStockTool(_ERPTool):
    @property
    def name(self) -> str:
        return "adjust_stock"

    @property
    def description(self) -> str:
        return "Ajusta el stock de un producto a la cantidad real contada (corrección por conteo físico)."

    async def execute(self, product_id: str, new_quantity: float, reason: str, **_: Any) -> Any:
        try:
            return await InventoryService().adjust(
                self.ctx, product_id=product_id, variant_id=None,
                new_quantity=new_quantity, delta=None, note=reason,
            )
        except ERPError as exc:
            return {"error": exc.code, "message": exc.message, "detail": exc.detail}


def register_erp_tools(registry: ToolRegistry, supabase: Client, tenant_id: str) -> None:
    """Add the ERP toolkit to an existing registry (called from tool_runtime)."""
    registry.register(GetDashboardSummaryTool(supabase, tenant_id))
    registry.register(GetStockTool(supabase, tenant_id))
    registry.register(GetTopProductsTool(supabase, tenant_id))
    registry.register(CreateSaleTool(supabase, tenant_id))
    registry.register(AdjustStockTool(supabase, tenant_id))

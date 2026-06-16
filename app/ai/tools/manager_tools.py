"""Tools del manager/admin agent. Cada función cierra sobre tenant_id y delega en
los ERP services existentes (misma lógica que el dashboard, distinto actor)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Callable

from supabase import Client

from app.services.erp.clients import ClientsService
from app.services.erp.context import bot_context
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
    return today.replace(day=1).isoformat(), today.isoformat()


def build_manager_tools(supabase: Client, tenant_id: str) -> list[Callable]:
    ctx = bot_context(tenant_id, actor="admin_bot")

    async def get_dashboard_summary(
        period: str = "month", date_from: str | None = None, date_to: str | None = None
    ) -> dict:
        """Resumen del negocio en un período: ventas totales, número de ventas, margen
        bruto, clientes nuevos, productos con stock bajo y saldo de cajas.

        Args:
            period: today | week | month | custom
            date_from: YYYY-MM-DD, requerido si period=custom
            date_to: YYYY-MM-DD, requerido si period=custom
        """
        f, t = _period_dates(period, date_from, date_to)
        return await ReportsService().dashboard(ctx, date_from=f, date_to=t)

    async def get_stock(product_name: str | None = None, low_stock_only: bool = False) -> list:
        """Consulta el stock de uno o todos los productos. Filtra por nombre o stock bajo.

        Args:
            product_name: filtra por nombre (coincidencia parcial)
            low_stock_only: solo productos por debajo de su umbral
        """
        if low_stock_only:
            return await InventoryService().low_stock(ctx)
        rows = await ProductsService().list(ctx, search=product_name, limit=50)
        return [
            {"product_id": r["id"], "product_name": r["name"], "category": r.get("category"),
             "unit": r["unit"], "stock": r.get("stock", 0), "price": r["price"]}
            for r in rows
        ]

    async def get_top_products(period: str = "month", limit: int = 5) -> list:
        """Productos más vendidos del período, por unidades e ingresos.

        Args:
            period: today | week | month
            limit: cuántos productos (1-50)
        """
        f, t = _period_dates(period, None, None)
        return await ReportsService().top_products(ctx, date_from=f, date_to=t, limit=limit)

    async def create_sale(
        items: list[dict], payment_method: str = "cash", client_phone: str | None = None
    ) -> dict:
        """Registra una venta. Baja stock y registra el ingreso de forma atómica.

        Args:
            items: lista de {product_id, quantity, unit_price?}. Si unit_price se
                omite, usa el precio del catálogo.
            payment_method: cash | card | transfer | whatsapp | other
            client_phone: teléfono para asociar la compra a un cliente
        """
        if not items:
            return {"error": "Se requiere al menos un ítem"}
        client_id = None
        if client_phone:
            try:
                client_id = (await ClientsService().get_by_phone(ctx, client_phone))["id"]
            except NotFound:
                client_id = None
        body = {
            "client_id": client_id, "payment_method": payment_method,
            "cash_account_id": None, "discount": 0, "notes": None, "items": items,
        }
        try:
            return await SalesService().create_sale(ctx, body)
        except ERPError as exc:
            return {"error": exc.code, "message": exc.message, "detail": exc.detail}

    async def adjust_stock(product_id: str, new_quantity: float, reason: str) -> dict:
        """Ajusta el stock de un producto a la cantidad real contada (conteo físico).

        Args:
            product_id: ID del producto
            new_quantity: cantidad real contada (stock objetivo)
            reason: motivo del ajuste
        """
        try:
            return await InventoryService().adjust(
                ctx, product_id=product_id, variant_id=None,
                new_quantity=new_quantity, delta=None, note=reason,
            )
        except ERPError as exc:
            return {"error": exc.code, "message": exc.message, "detail": exc.detail}

    return [get_dashboard_summary, get_stock, get_top_products, create_sale, adjust_stock]

"""Export service: Excel (openpyxl), PDF reports (reportlab), barcode labels (python-barcode).

Heavy libs are imported lazily inside each method so importing this module stays cheap
and the rest of the app doesn't pay for them at startup.
"""

from __future__ import annotations

import csv
import io

from app.services.erp.context import ERPContext
from app.services.erp.exceptions import NotFound
from app.services.erp.finance import FinanceService
from app.services.erp.inventory import InventoryService
from app.services.erp.reports import ReportsService, default_period
from app.services.supabase_client import get_supabase


def _xlsx(title: str, headers: list[str], rows: list[list]) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = title[:31]
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _csv(title: str, headers: list[str], rows: list[list]) -> bytes:
    # utf-8-sig so Excel opens accented text (á, ñ, ó…) correctly when double-clicking the file.
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8-sig")


def serialize(table: tuple[str, list[str], list[list]], fmt: str) -> bytes:
    """Serialize a (title, headers, rows) table to the requested format."""
    title, headers, rows = table
    return _csv(title, headers, rows) if fmt == "csv" else _xlsx(title, headers, rows)


class ExportService:
    def __init__(self) -> None:
        self.inventory = InventoryService()
        self.reports = ReportsService()
        self.finance = FinanceService()

    async def sales_table(self, ctx: ERPContext, *, date_from: str | None,
                          date_to: str | None) -> tuple[str, list[str], list[list]]:
        f, t = default_period(date_from, date_to)
        rows = (
            get_supabase().table("sales")
            .select("id, status, payment_method, subtotal, discount, total, actor, created_at")
            .eq("tenant_id", ctx.tenant_id).gte("created_at", f).lte("created_at", f"{t}T23:59:59")
            .order("created_at", desc=True).execute()
        ).data or []
        return (
            "Ventas",
            ["ID", "Estado", "Pago", "Subtotal", "Descuento", "Total", "Actor", "Fecha"],
            [[r["id"], r["status"], r["payment_method"], r["subtotal"], r["discount"],
              r["total"], r["actor"], r["created_at"]] for r in rows],
        )

    async def inventory_table(self, ctx: ERPContext) -> tuple[str, list[str], list[list]]:
        rows = await self.inventory.list_stock(ctx, limit=10000)
        return (
            "Inventario",
            ["Producto", "Categoría", "Unidad", "Stock", "Umbral bajo"],
            [[r["product_name"], r.get("category") or "", r["unit"], r["quantity"],
              r["low_stock_threshold"]] for r in rows],
        )

    async def transactions_table(self, ctx: ERPContext, *, date_from: str | None,
                                 date_to: str | None) -> tuple[str, list[str], list[list]]:
        f, t = default_period(date_from, date_to)
        rows = await self.finance.list_transactions(ctx, date_from=f, date_to=t, limit=10000)
        return (
            "Transacciones",
            ["Tipo", "Monto", "Categoría", "Descripción", "Fecha", "Actor"],
            [[r["type"], r["amount"], r["category"], r.get("description") or "",
              r["date"], r["actor"]] for r in rows],
        )

    async def report_pdf(self, ctx: ERPContext, *, date_from: str | None, date_to: str | None) -> bytes:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

        f, t = default_period(date_from, date_to)
        dash = await self.reports.dashboard(ctx, date_from=f, date_to=t)
        top = await self.reports.top_products(ctx, date_from=f, date_to=t, limit=10)

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4)
        styles = getSampleStyleSheet()
        story = [
            Paragraph("Reporte de negocio", styles["Title"]),
            Paragraph(f"Período: {f} a {t}", styles["Normal"]),
            Spacer(1, 12),
        ]
        kpis = [
            ["Ventas totales", f"{dash['sales_total']:.2f}"],
            ["N° de ventas", str(dash["sales_count"])],
            ["Margen bruto", f"{dash['gross_margin']:.2f} ({dash['gross_margin_pct']}%)"],
            ["Clientes nuevos", str(dash["new_clients"])],
            ["Productos con stock bajo", str(dash["low_stock_count"])],
        ]
        kpi_table = Table([["Indicador", "Valor"], *kpis], hAlign="LEFT")
        kpi_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#222222")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        story += [kpi_table, Spacer(1, 16), Paragraph("Top productos", styles["Heading2"])]
        top_rows = [["Producto", "Unidades", "Ingresos"]] + [
            [p["product_name"], f"{p['units']:g}", f"{p['revenue']:.2f}"] for p in top
        ]
        top_table = Table(top_rows, hAlign="LEFT")
        top_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#222222")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        story.append(top_table)
        doc.build(story)
        return buf.getvalue()

    async def barcode_label_pdf(self, ctx: ERPContext, product_id: str) -> bytes:
        """Generate a printable barcode label (Code128) for a product without its own code."""
        import barcode
        from barcode.writer import ImageWriter

        rows = (
            get_supabase().table("products").select("id, name, sku, barcode, price")
            .eq("tenant_id", ctx.tenant_id).eq("id", product_id).limit(1).execute()
        ).data
        if not rows:
            raise NotFound("Producto no encontrado", product_id=product_id)
        product = rows[0]
        code_value = product.get("barcode") or product.get("sku") or product["id"][:12]
        code128 = barcode.get("code128", code_value, writer=ImageWriter())
        buf = io.BytesIO()
        code128.write(buf, options={"module_height": 12.0, "font_size": 8, "text": product["name"][:30]})
        return buf.getvalue()

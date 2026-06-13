"""Export endpoints. Return file downloads (Excel / PDF / PNG barcode)."""

from __future__ import annotations

import io

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.services.erp.context import ERPContext, get_erp_context
from app.services.erp.export import ExportService, serialize

router = APIRouter()
service = ExportService()

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_MEDIA = {"csv": "text/csv", "xlsx": _XLSX}


def _download(data: bytes, filename: str, media_type: str) -> StreamingResponse:
    return StreamingResponse(
        io.BytesIO(data),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _tabular(table, name: str, fmt: str) -> StreamingResponse:
    """Serialize a (title, headers, rows) table and stream it as csv (default) or xlsx."""
    return _download(serialize(table, fmt), f"{name}.{fmt}", _MEDIA[fmt])


@router.get("/sales")
async def export_sales(
    ctx: ERPContext = Depends(get_erp_context),
    date_from: str | None = None,
    date_to: str | None = None,
    format: str = Query("csv", pattern="^(csv|xlsx)$"),
):
    table = await service.sales_table(ctx, date_from=date_from, date_to=date_to)
    return _tabular(table, "ventas", format)


@router.get("/inventory")
async def export_inventory(
    ctx: ERPContext = Depends(get_erp_context),
    format: str = Query("csv", pattern="^(csv|xlsx)$"),
):
    table = await service.inventory_table(ctx)
    return _tabular(table, "inventario", format)


@router.get("/transactions")
async def export_transactions(
    ctx: ERPContext = Depends(get_erp_context),
    date_from: str | None = None,
    date_to: str | None = None,
    format: str = Query("csv", pattern="^(csv|xlsx)$"),
):
    table = await service.transactions_table(ctx, date_from=date_from, date_to=date_to)
    return _tabular(table, "transacciones", format)


@router.get("/report/pdf")
async def export_report_pdf(
    ctx: ERPContext = Depends(get_erp_context),
    date_from: str | None = None,
    date_to: str | None = None,
):
    data = await service.report_pdf(ctx, date_from=date_from, date_to=date_to)
    return _download(data, "reporte.pdf", "application/pdf")


@router.get("/barcode/{product_id}")
async def export_barcode(product_id: str, ctx: ERPContext = Depends(get_erp_context)):
    data = await service.barcode_label_pdf(ctx, product_id)
    return _download(data, f"etiqueta_{product_id}.png", "image/png")

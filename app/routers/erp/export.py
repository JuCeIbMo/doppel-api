"""Export endpoints. Return file downloads (Excel / PDF / PNG barcode)."""

from __future__ import annotations

import io

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.services.erp.context import ERPContext, get_erp_context
from app.services.erp.export import ExportService

router = APIRouter()
service = ExportService()

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _download(data: bytes, filename: str, media_type: str) -> StreamingResponse:
    return StreamingResponse(
        io.BytesIO(data),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/sales")
async def export_sales(
    ctx: ERPContext = Depends(get_erp_context),
    date_from: str | None = None,
    date_to: str | None = None,
):
    data = await service.sales_xlsx(ctx, date_from=date_from, date_to=date_to)
    return _download(data, "ventas.xlsx", _XLSX)


@router.get("/inventory")
async def export_inventory(ctx: ERPContext = Depends(get_erp_context)):
    data = await service.inventory_xlsx(ctx)
    return _download(data, "inventario.xlsx", _XLSX)


@router.get("/transactions")
async def export_transactions(
    ctx: ERPContext = Depends(get_erp_context),
    date_from: str | None = None,
    date_to: str | None = None,
):
    data = await service.transactions_xlsx(ctx, date_from=date_from, date_to=date_to)
    return _download(data, "transacciones.xlsx", _XLSX)


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

import logging
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.middleware import RequestIdLogFilter, install_observability
from app.routers import asistpro, auth, dashboard, health, internal, oauth, webhook
from app.routers.erp import (
    activity as erp_activity,
    clients as erp_clients,
    export as erp_export,
    finance as erp_finance,
    inventory as erp_inventory,
    products as erp_products,
    reports as erp_reports,
    sales as erp_sales,
)
from app.services.erp.exceptions import ERPError

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s",
)
for _h in logging.getLogger().handlers:
    _h.addFilter(RequestIdLogFilter())
logger = logging.getLogger("doppel")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient(timeout=30.0)
    logger.info("doppel-api started")
    yield
    await app.state.http_client.aclose()
    logger.info("doppel-api stopped")


app = FastAPI(
    title="Doppel API",
    version="1.0.0",
    description="WhatsApp Business automation API. Auth via OTP, Meta Embedded Signup, and tenant dashboard.",
    lifespan=lifespan,
)

install_observability(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(oauth.router)
app.include_router(webhook.router)
app.include_router(asistpro.router)
app.include_router(internal.router)

# --- ERP module ---------------------------------------------------------------
app.include_router(erp_products.router, prefix="/erp/products", tags=["ERP - Products"])
app.include_router(erp_inventory.router, prefix="/erp/inventory", tags=["ERP - Inventory"])
app.include_router(erp_sales.router, prefix="/erp/sales", tags=["ERP - Sales"])
app.include_router(erp_clients.router, prefix="/erp/clients", tags=["ERP - Clients"])
app.include_router(erp_finance.router, prefix="/erp/finance", tags=["ERP - Finance"])
app.include_router(erp_reports.router, prefix="/erp/reports", tags=["ERP - Reports"])
app.include_router(erp_activity.router, prefix="/erp/activity", tags=["ERP - Activity"])
app.include_router(erp_export.router, prefix="/erp/export", tags=["ERP - Export"])


@app.exception_handler(ERPError)
async def erp_error_handler(request: Request, exc: ERPError) -> JSONResponse:
    """Translate typed ERP business errors into a consistent JSON shape."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.code, "message": exc.message, "detail": exc.detail},
    )

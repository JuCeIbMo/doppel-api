import logging
import time
import uuid
from contextvars import ContextVar

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
logger = logging.getLogger("doppel.access")

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
}


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        token = request_id_var.set(rid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        response.headers["X-Request-ID"] = rid
        for k, v in _SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        if request.url.path != "/health":
            logger.info(
                "%s %s -> %s %sms",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
                extra={"request_id": rid},
            )
        return response


class RequestIdLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = request_id_var.get()
        return True


def install_observability(app: FastAPI) -> None:
    app.add_middleware(RequestContextMiddleware)

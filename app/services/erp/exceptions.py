"""Typed business errors for the ERP.

Services raise these — never `HTTPException`. A single handler registered in
`app/main.py` translates them to a consistent JSON response, so the same error
shape reaches both the frontend and the AI tools.
"""

from __future__ import annotations

from typing import Any


class ERPError(Exception):
    """Base business error. `status_code` and `code` are overridden by subclasses."""

    status_code: int = 400
    code: str = "erp_error"

    def __init__(self, message: str, **detail: Any) -> None:
        self.message = message
        self.detail = detail
        super().__init__(message)


class InsufficientStock(ERPError):
    status_code = 400
    code = "insufficient_stock"

    def __init__(self, *, product_id: str, available: float, requested: float | None = None) -> None:
        super().__init__(
            f"Stock insuficiente: quedan {available} unidades",
            product_id=product_id,
            available=available,
            requested=requested,
        )


class NotFound(ERPError):
    status_code = 404
    code = "not_found"


class ValidationError(ERPError):
    status_code = 422
    code = "validation_error"


class Conflict(ERPError):
    status_code = 409
    code = "conflict"


class Forbidden(ERPError):
    status_code = 403
    code = "forbidden"

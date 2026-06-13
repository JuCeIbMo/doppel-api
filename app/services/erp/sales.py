"""Sales service. The create/cancel paths delegate to atomic Postgres RPCs so the
whole operation (stock + finance + client rollups) either commits fully or not at all.

The same `create_sale` runs whether the actor is the owner (dashboard) or the AI bot —
only `ctx.actor` differs. That's how a WhatsApp sale and a dashboard sale provably share
one code path and one stock guarantee.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.services.erp.context import ERPContext, log_activity
from app.services.erp.exceptions import Conflict, InsufficientStock, NotFound
from app.services.supabase_client import get_supabase

logger = logging.getLogger("doppel.erp")


def _rpc_error_detail(exc: Exception) -> dict[str, Any]:
    """Postgres RAISE ... USING DETAIL=<json> surfaces through postgrest as a 'details'
    field. Parse it if present so we can rebuild a typed error."""
    raw = getattr(exc, "details", None) or getattr(exc, "detail", None)
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return {}
    return raw if isinstance(raw, dict) else {}


def _rpc_message(exc: Exception) -> str:
    return str(getattr(exc, "message", None) or exc)


class SalesService:
    async def create_sale(self, ctx: ERPContext, body: dict[str, Any]) -> dict:
        payload = {
            "client_id": body.get("client_id"),
            "payment_method": body.get("payment_method", "cash"),
            "cash_account_id": body.get("cash_account_id"),
            "discount": body.get("discount", 0),
            "notes": body.get("notes"),
            "items": body["items"],
        }
        try:
            result = get_supabase().rpc(
                "create_sale",
                {"payload": payload, "p_tenant_id": ctx.tenant_id, "p_actor": ctx.actor},
            ).execute()
        except Exception as exc:  # noqa: BLE001
            msg = _rpc_message(exc)
            if "insufficient_stock" in msg:
                d = _rpc_error_detail(exc)
                raise InsufficientStock(
                    product_id=str(d.get("product_id", "")),
                    available=float(d.get("available", 0)),
                    requested=d.get("requested"),
                ) from exc
            logger.exception("create_sale RPC failed tenant=%s", ctx.tenant_id)
            raise

        sale = result.data
        log_activity(
            ctx, action="sale.created", module="sales",
            detail={
                "sale_id": sale.get("id"),
                "total": sale.get("total"),
                "items": [{"name": it.get("product_name"), "qty": it.get("quantity")}
                          for it in sale.get("items", [])],
            },
        )
        return sale

    async def cancel_sale(self, ctx: ERPContext, sale_id: str) -> dict:
        try:
            result = get_supabase().rpc(
                "cancel_sale",
                {"p_sale_id": sale_id, "p_tenant_id": ctx.tenant_id, "p_actor": ctx.actor},
            ).execute()
        except Exception as exc:  # noqa: BLE001
            msg = _rpc_message(exc)
            if "sale_not_found" in msg:
                raise NotFound("Venta no encontrada", sale_id=sale_id) from exc
            if "sale_already_cancelled" in msg:
                raise Conflict("La venta ya estaba cancelada", sale_id=sale_id) from exc
            logger.exception("cancel_sale RPC failed tenant=%s", ctx.tenant_id)
            raise

        log_activity(ctx, action="sale.cancelled", module="sales", detail={"sale_id": sale_id})
        return result.data

    async def list(self, ctx: ERPContext, *, client_id: str | None = None,
                   date_from: str | None = None, date_to: str | None = None,
                   limit: int = 50, offset: int = 0) -> list[dict]:
        q = (
            get_supabase().table("sales").select("*")
            .eq("tenant_id", ctx.tenant_id).order("created_at", desc=True)
        )
        if client_id:
            q = q.eq("client_id", client_id)
        if date_from:
            q = q.gte("created_at", date_from)
        if date_to:
            q = q.lte("created_at", date_to)
        return (q.range(offset, offset + limit - 1).execute()).data or []

    async def get(self, ctx: ERPContext, sale_id: str) -> dict:
        rows = (
            get_supabase().table("sales").select("*, items:sale_items(*)")
            .eq("tenant_id", ctx.tenant_id).eq("id", sale_id).limit(1).execute()
        ).data
        if not rows:
            raise NotFound("Venta no encontrada", sale_id=sale_id)
        return rows[0]

"""Durable, tenant-scoped approvals for admin-agent mutations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.services.erp.context import ERPContext
from app.services.erp.exceptions import Conflict, NotFound
from app.services.supabase_client import get_supabase

_TTL = timedelta(minutes=15)
# Si un worker muere entre `claim()` y `complete()`, la fila queda en "executing"
# para siempre. Pasado este umbral se permite re-clamarla: es seguro porque las
# escrituras no idempotentes (product_create, transaction) ya están protegidas
# por el índice único `admin_action_id` de migration_v12_admin_actions.sql.
_STUCK_EXECUTING_TIMEOUT = timedelta(minutes=5)


def _parse_timestamp(value: str) -> datetime:
    """Parsea un timestamp ISO de Postgres, asumiendo UTC si viene naive."""
    parsed = datetime.fromisoformat(str(value))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


class AdminActionService:
    async def create(self, ctx: ERPContext, *, thread_id: str, kind: str,
                     payload: dict[str, Any], summary: str) -> dict:
        row = {
            "tenant_id": ctx.tenant_id, "thread_id": thread_id, "kind": kind,
            "payload": payload, "summary": summary, "status": "pending",
            "expires_at": (datetime.now(UTC) + _TTL).isoformat(),
        }
        return (await get_supabase().table("admin_pending_actions").insert(row).execute()).data[0]

    async def consume_reply(self, ctx: ERPContext, *, thread_id: str, action_id: str,
                            confirmed: bool) -> str | None:
        """Accept a raw interactive reply. Returns an executable id only on confirm."""
        rows = (await get_supabase().table("admin_pending_actions").select("*")
                .eq("tenant_id", ctx.tenant_id).eq("thread_id", thread_id)
                .eq("id", action_id).limit(1).execute()).data or []
        if not rows:
            return None
        action = rows[0]
        if action["status"] != "pending":
            return None
        if _parse_timestamp(action["expires_at"]) <= datetime.now(UTC):
            await get_supabase().table("admin_pending_actions").update({"status": "expired"}).eq("id", action_id).execute()
            return None
        if not confirmed:
            await get_supabase().table("admin_pending_actions").update({"status": "cancelled"}).eq("id", action_id).execute()
            return None
        updated = (await get_supabase().table("admin_pending_actions").update({
            "status": "confirmed", "confirmed_at": datetime.now(UTC).isoformat(),
        }).eq("id", action_id).eq("status", "pending").execute()).data or []
        return action_id if updated else None

    async def claim(self, ctx: ERPContext, *, thread_id: str, action_id: str) -> dict:
        rows = (await get_supabase().table("admin_pending_actions").select("*")
                .eq("tenant_id", ctx.tenant_id).eq("thread_id", thread_id)
                .eq("id", action_id).limit(1).execute()).data or []
        if not rows:
            raise NotFound("Acción pendiente no encontrada", action_id=action_id)
        action = rows[0]
        status = action["status"]
        if status == "executed":
            return action
        stuck = (status == "executing" and action.get("confirmed_at") is not None
                 and _parse_timestamp(action["confirmed_at"]) <= datetime.now(UTC) - _STUCK_EXECUTING_TIMEOUT)
        if status != "confirmed" and not stuck:
            if status == "executing":
                raise Conflict("La acción ya está siendo procesada", action_id=action_id)
            raise Conflict("La acción no está confirmada", action_id=action_id)
        expected_status = "executing" if stuck else "confirmed"
        updated = (await get_supabase().table("admin_pending_actions").update({"status": "executing"})
                   .eq("id", action_id).eq("status", expected_status).execute()).data or []
        if not updated:
            raise Conflict("La acción ya está siendo procesada", action_id=action_id)
        return updated[0]

    async def complete(self, action_id: str, result: dict[str, Any]) -> dict:
        rows = (await get_supabase().table("admin_pending_actions").update({
            "status": "executed", "result": result, "executed_at": datetime.now(UTC).isoformat(),
        }).eq("id", action_id).execute()).data or []
        return rows[0] if rows else result

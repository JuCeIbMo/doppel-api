"""Durable, tenant-scoped approvals for admin-agent mutations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.services.erp.context import ERPContext
from app.services.erp.exceptions import Conflict, NotFound
from app.services.supabase_client import get_supabase

_TTL = timedelta(minutes=15)


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
        if str(action["expires_at"]) <= datetime.now(UTC).isoformat():
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
        if action["status"] == "executed":
            return action
        if action["status"] != "confirmed":
            raise Conflict("La acción no está confirmada", action_id=action_id)
        updated = (await get_supabase().table("admin_pending_actions").update({"status": "executing"})
                   .eq("id", action_id).eq("status", "confirmed").execute()).data or []
        if not updated:
            raise Conflict("La acción ya está siendo procesada", action_id=action_id)
        return updated[0]

    async def complete(self, action_id: str, result: dict[str, Any]) -> dict:
        rows = (await get_supabase().table("admin_pending_actions").update({
            "status": "executed", "result": result, "executed_at": datetime.now(UTC).isoformat(),
        }).eq("id", action_id).execute()).data or []
        return rows[0] if rows else result

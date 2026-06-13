"""Activity service: read-only feed over the append-only `activity_log` table."""

from __future__ import annotations

from app.services.erp.context import ERPContext
from app.services.supabase_client import get_supabase

_BOT_ACTORS = ("whatsapp_bot", "admin_bot")


class ActivityService:
    async def feed(self, ctx: ERPContext, *, actor: str | None = None, module: str | None = None,
                   date_from: str | None = None, date_to: str | None = None,
                   limit: int = 50, offset: int = 0) -> list[dict]:
        q = (
            get_supabase().table("activity_log").select("*")
            .eq("tenant_id", ctx.tenant_id).order("created_at", desc=True)
        )
        if actor:
            q = q.eq("actor", actor)
        if module:
            q = q.eq("module", module)
        if date_from:
            q = q.gte("created_at", date_from)
        if date_to:
            q = q.lte("created_at", f"{date_to}T23:59:59")
        return (q.range(offset, offset + limit - 1).execute()).data or []

    async def ai_feed(self, ctx: ERPContext, *, limit: int = 50, offset: int = 0) -> list[dict]:
        return (
            get_supabase().table("activity_log").select("*")
            .eq("tenant_id", ctx.tenant_id).in_("actor", list(_BOT_ACTORS))
            .order("created_at", desc=True).range(offset, offset + limit - 1).execute()
        ).data or []

"""Activity service: read-only feed over the append-only `activity_log` table."""

from __future__ import annotations

from app.services.erp.context import ERPContext
from app.services.supabase_client import get_supabase

_BOT_ACTORS = ("whatsapp_bot", "admin_bot")


def _enrich(row: dict) -> dict:
    """Add deep-link fields the frontend needs. `action` is always `<entity>.<verb>` and
    `log_activity` stores the resource id under `<entity>_id` in `detail` (sale_id, product_id,
    client_id, account_id). Rows whose detail has no id (e.g. transaction.*) get entity_id=None —
    the link just won't render. `module` is already on the row; we pass it through explicitly.
    """
    entity_type = (row.get("action") or "").split(".")[0] or None
    detail = row.get("detail") or {}
    entity_id = detail.get(f"{entity_type}_id") if entity_type else None
    if entity_id is None:
        entity_id = next((v for k, v in detail.items() if k.endswith("_id")), None)
    row["entity_type"] = entity_type
    row["entity_id"] = entity_id
    row["module"] = row.get("module")
    return row


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
        rows = (q.range(offset, offset + limit - 1).execute()).data or []
        return [_enrich(r) for r in rows]

    async def ai_feed(self, ctx: ERPContext, *, limit: int = 50, offset: int = 0) -> list[dict]:
        rows = (
            get_supabase().table("activity_log").select("*")
            .eq("tenant_id", ctx.tenant_id).in_("actor", list(_BOT_ACTORS))
            .order("created_at", desc=True).range(offset, offset + limit - 1).execute()
        ).data or []
        return [_enrich(r) for r in rows]

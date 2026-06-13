"""Clients service. Quick creation during a sale (name + phone is enough). The bot
associates purchases by phone / whatsapp_id."""

from __future__ import annotations

from typing import Any

from app.services.erp.context import ERPContext, log_activity
from app.services.erp.exceptions import NotFound
from app.services.supabase_client import get_supabase

_FIELDS = (
    "id, name, phone, email, address, notes, tags, whatsapp_id, "
    "total_purchases, purchase_count, last_purchase_at, created_at"
)


class ClientsService:
    async def list(self, ctx: ERPContext, *, search: str | None = None, tag: str | None = None,
                   limit: int = 50, offset: int = 0) -> list[dict]:
        q = (
            get_supabase().table("clients").select(_FIELDS)
            .eq("tenant_id", ctx.tenant_id).order("name")
        )
        if search:
            q = q.or_(f"name.ilike.%{search}%,phone.ilike.%{search}%")
        if tag:
            q = q.contains("tags", [tag])
        return (q.range(offset, offset + limit - 1).execute()).data or []

    async def get(self, ctx: ERPContext, client_id: str) -> dict:
        rows = (
            get_supabase().table("clients").select(_FIELDS)
            .eq("tenant_id", ctx.tenant_id).eq("id", client_id).limit(1).execute()
        ).data
        if not rows:
            raise NotFound("Cliente no encontrado", client_id=client_id)
        client = rows[0]
        client["recent_sales"] = (
            get_supabase().table("sales").select("id, total, status, created_at")
            .eq("tenant_id", ctx.tenant_id).eq("client_id", client_id)
            .order("created_at", desc=True).limit(10).execute()
        ).data or []
        return client

    async def get_by_phone(self, ctx: ERPContext, phone: str) -> dict:
        rows = (
            get_supabase().table("clients").select(_FIELDS)
            .eq("tenant_id", ctx.tenant_id).eq("phone", phone).limit(1).execute()
        ).data
        if not rows:
            raise NotFound("No hay cliente con ese teléfono", phone=phone)
        return rows[0]

    async def get_by_whatsapp(self, ctx: ERPContext, wa_id: str) -> dict:
        rows = (
            get_supabase().table("clients").select(_FIELDS)
            .eq("tenant_id", ctx.tenant_id).eq("whatsapp_id", wa_id).limit(1).execute()
        ).data
        if not rows:
            raise NotFound("No hay cliente con ese WhatsApp", whatsapp_id=wa_id)
        return rows[0]

    async def create(self, ctx: ERPContext, data: dict[str, Any]) -> dict:
        payload = {**data, "tenant_id": ctx.tenant_id}
        row = (get_supabase().table("clients").insert(payload).execute()).data[0]
        log_activity(ctx, action="client.created", module="clients",
                     detail={"client_id": row["id"], "name": row["name"]})
        return row

    async def update(self, ctx: ERPContext, client_id: str, data: dict[str, Any]) -> dict:
        clean = {k: v for k, v in data.items() if v is not None}
        rows = (
            get_supabase().table("clients").update(clean)
            .eq("tenant_id", ctx.tenant_id).eq("id", client_id).execute()
        ).data
        if not rows:
            raise NotFound("Cliente no encontrado", client_id=client_id)
        log_activity(ctx, action="client.updated", module="clients",
                     detail={"client_id": client_id, "changed": list(clean.keys())})
        return rows[0]

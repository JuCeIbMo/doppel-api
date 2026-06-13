"""The shared spine of the ERP: request context, activity logging, RPC helpers.

`ERPContext` is the single object every service method receives. It carries the
`tenant_id` (so no query can forget to scope by tenant) and the `actor` (so every
mutation is attributed correctly in the audit log). The owner path builds it from
the Supabase-authenticated tenant; the AI tools build it with `actor="admin_bot"`.
Same services, same logic, different actor.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from fastapi import Depends

from app.dependencies import get_current_tenant
from app.services.supabase_client import get_supabase

logger = logging.getLogger("doppel.erp")

# Actors allowed in v1. "cashier" exists in the DB enum for the future PIN mode (v2).
Actor = str  # "owner" | "whatsapp_bot" | "admin_bot"


@dataclass(slots=True)
class ERPContext:
    tenant_id: str
    actor: Actor
    actor_label: str

    @property
    def is_owner(self) -> bool:
        return self.actor == "owner"

    @property
    def is_bot(self) -> bool:
        return self.actor in ("whatsapp_bot", "admin_bot")


async def get_erp_context(tenant: dict = Depends(get_current_tenant)) -> ERPContext:
    """Dependency for owner-facing ERP endpoints. Reuses Doppel's Supabase Auth flow."""
    return ERPContext(tenant_id=str(tenant["id"]), actor="owner", actor_label="Dueño")


def bot_context(tenant_id: str, *, actor: Actor = "admin_bot", label: str | None = None) -> ERPContext:
    """Build a context for the AI tools, which already hold the tenant_id."""
    return ERPContext(
        tenant_id=str(tenant_id),
        actor=actor,
        actor_label=label or ("Asistente Admin" if actor == "admin_bot" else "Bot WhatsApp"),
    )


def log_activity(ctx: ERPContext, *, action: str, module: str, detail: dict) -> None:
    """Append to the audit log. Best-effort and synchronous: the Supabase client is
    sync, so we do NOT wrap it in asyncio.create_task. It never raises — a failed log
    must not break the operation that triggered it.
    """
    try:
        get_supabase().table("activity_log").insert(
            {
                "tenant_id": ctx.tenant_id,
                "actor": ctx.actor,
                "actor_label": ctx.actor_label,
                "action": action,
                "module": module,
                "detail": detail,
            }
        ).execute()
    except Exception:
        logger.exception("activity_log write failed action=%s tenant=%s", action, ctx.tenant_id)

"""Piezas compartidas por las factories de agentes."""

from __future__ import annotations

from agno.db.postgres import PostgresDb
from agno.models.anthropic import Claude

from app.ai.config import AGNO_DB_URL, DEFAULT_MODEL


def session_id_for(tenant_id: str, user_phone: str) -> str:
    """Aísla cada conversación por negocio + contacto."""
    return f"{tenant_id}:{user_phone}"


def build_db() -> PostgresDb:
    return PostgresDb(db_url=AGNO_DB_URL)


def build_model(model_id: str | None) -> Claude:
    return Claude(id=model_id or DEFAULT_MODEL)

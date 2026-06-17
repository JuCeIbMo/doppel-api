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
    # El runtime es Claude-only. Un id que no sea de Claude (p.ej. "gpt-4o-mini"
    # o "gemini-*" heredado de configs viejas en bot_configs.ai_model) hace que
    # Anthropic devuelva 404 y rompe la respuesta del bot. Degradamos al modelo
    # por defecto en vez de explotar.
    if not model_id or not model_id.startswith("claude"):
        return Claude(id=DEFAULT_MODEL)
    return Claude(id=model_id)

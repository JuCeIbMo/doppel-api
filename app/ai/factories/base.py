"""Piezas compartidas por las factories de agentes."""

from __future__ import annotations

from agno.db.postgres import PostgresDb
from agno.models.anthropic import Claude
from agno.models.base import Model
from agno.models.openai import OpenAIChat

from app.ai.config import AGNO_DB_URL, DEFAULT_MODEL

# Prefijos de los ids de modelos de OpenAI (gpt-4o, gpt-4o-mini, o1/o3/o4, chatgpt-*).
_OPENAI_PREFIXES = ("gpt", "o1", "o3", "o4", "chatgpt")


def session_id_for(tenant_id: str, user_phone: str) -> str:
    """Aísla cada conversación por negocio + contacto."""
    return f"{tenant_id}:{user_phone}"


def build_db() -> PostgresDb:
    return PostgresDb(db_url=AGNO_DB_URL)


def _resolve_model(model_id: str) -> Model | None:
    """Mapea un id de modelo a su cliente Agno según el proveedor, o None si no
    se reconoce. La API key la toma Agno del entorno (ANTHROPIC_API_KEY /
    OPENAI_API_KEY) según el proveedor."""
    if model_id.startswith("claude"):
        return Claude(id=model_id)
    if model_id.startswith(_OPENAI_PREFIXES):
        return OpenAIChat(id=model_id)
    return None


def build_model(model_id: str | None) -> Model:
    """Construye el cliente del modelo enrutando por proveedor. bot_configs.ai_model
    es por-tenant, así que cada negocio puede usar Claude o GPT. Un id desconocido
    cae al DEFAULT_MODEL (AI_DEFAULT_MODEL)."""
    return (
        _resolve_model((model_id or "").strip())
        or _resolve_model(DEFAULT_MODEL)
        or Claude(id=DEFAULT_MODEL)
    )

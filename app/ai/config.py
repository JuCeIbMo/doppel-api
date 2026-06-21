"""Configuración del subsistema de IA. Re-expone los settings relevantes
para que el resto de app/ai/ no toque app.config directamente."""

from __future__ import annotations

from app.config import settings

AGNO_DB_URL: str = settings.AGNO_DB_URL
OPENAI_API_KEY: str = settings.OPENAI_API_KEY
DEFAULT_MODEL: str = settings.AI_DEFAULT_MODEL
DEBUG: bool = settings.AI_DEBUG

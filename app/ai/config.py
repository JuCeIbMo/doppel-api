"""Configuración del subsistema de IA. Re-expone los settings relevantes
para que el resto de app/ai/ no toque app.config directamente."""

from __future__ import annotations

from app.config import settings

OPENAI_API_KEY: str = settings.OPENAI_API_KEY
DEFAULT_MODEL: str = settings.AI_DEFAULT_MODEL
CHAT_DB_URL: str = settings.CHAT_DB_URL

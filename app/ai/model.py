"""Ruteo de id de modelo → string de proveedor de Pydantic AI ("provider:model").

La API key la toma Pydantic AI del entorno (ANTHROPIC_API_KEY / OPENAI_API_KEY).
"""

from __future__ import annotations

from app.ai.config import DEFAULT_MODEL

_OPENAI_PREFIXES = ("gpt", "o1", "o3", "o4", "chatgpt")


def _provider_for(model_id: str) -> str | None:
    if model_id.startswith("claude"):
        return "anthropic"
    if model_id.startswith(_OPENAI_PREFIXES):
        return "openai"
    return None


def model_string(model_id: str | None) -> str:
    """Devuelve `"provider:model"`. Un id desconocido cae al DEFAULT_MODEL."""
    mid = (model_id or "").strip()
    provider = _provider_for(mid)
    if provider:
        return f"{provider}:{mid}"
    default = DEFAULT_MODEL.strip()
    if not default:
        default = "claude-sonnet-4-20250514"
    provider = _provider_for(default) or "anthropic"
    return f"{provider}:{default}"

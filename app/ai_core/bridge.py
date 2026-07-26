"""Puente entre el webhook y el agente LangGraph. Entrada única por mensaje.

Reemplaza a `app/ai/bridge.py` (Agno). Diferencias del contrato viejo:
- No recibe `mode`/`system_prompt`/`model`: el rol (público/admin) se resuelve
  acá por `resolve_role(user_phone, tenant)` (autoridad del número, igual que
  antes), y el prompt/modelo salen de `app/ai_core` (prompts estáticos +
  DeepSeek), no de `bot_configs.system_prompt`/`ai_model`.
- No soporta imágenes todavía (ver `media/transcription.py`) — solo texto y
  transcripción de audio.

Cachea un agente compilado por `(tenant_id, role)` para no reconstruir el grafo
en cada mensaje (la conexión sale del pool compartido de `persistence`). El
caché se desaloja cuando un turno falla (así un error transitorio no queda
pegado) y cuando cambia la config del tenant, comparando un fingerprint contra
el que se usó para construirlo.
"""

from __future__ import annotations

import asyncio
import json
import logging

from app.ai_core.agents.admin_agent import build_admin_agent, run_admin_agent_turn
from app.ai_core.agents.public_agent import build_public_agent, run_public_agent_turn
from app.ai_core.config.loader import load_tenant_config
from app.ai_core.config.tenant import TenantConfig, resolve_role
from app.ai_core.media.transcription import transcribe_audio_media

logger = logging.getLogger("doppel.ai_core.bridge")

_agents: dict[tuple[str, str], tuple[str, object]] = {}
_agents_lock = asyncio.Lock()

# Cap the cache so a long tail of tenants cannot grow it without bound. Agents
# are cheap to rebuild (no I/O beyond grabbing a pooled connection), so the
# oldest entry is simply dropped.
MAX_CACHED_AGENTS = 100


def _document_note(media: list[dict] | None) -> str:
    docs = [m for m in (media or []) if m.get("type") not in {"image", "audio", "voice"}]
    return "\n[documento adjunto]" if docs else ""


def _image_note(media: list[dict] | None) -> str:
    images = [m for m in (media or []) if m.get("type") == "image"]
    return "\n[el cliente envió una imagen; hoy no puedo verla, pedile que describa lo que busca]" if images else ""


def _config_fingerprint(tenant: TenantConfig) -> str:
    """Fingerprint the tenant config that gets baked into a built agent.

    Deliberately the whole model instead of a hand-picked subset: `business_name`
    and `tone` are substituted into the prompts at build time, and
    `allowed_tools`/`allowed_subagents` decide what is bound at all. A curated
    list goes stale the moment a field is added, and the failure is silent.
    Rebuilding on an irrelevant change costs one cheap rebuild; missing a
    relevant one serves the old config until the next deploy.
    """
    return json.dumps(tenant.model_dump(), sort_keys=True, default=str)


async def _get_or_build_agent(tenant: TenantConfig, role: str):
    """Cache the compiled agent per (tenant_id, role), keyed to its config.

    `respond` reloads the tenant config on every message anyway, so comparing a
    fingerprint costs nothing and lets `bot_configs`/`business_info` edits reach
    a running process: without it the agent keeps the business name and the
    tools it was built with until the next deploy.
    """
    key = (tenant.tenant_id, role)
    fingerprint = _config_fingerprint(tenant)
    async with _agents_lock:
        cached = _agents.get(key)
        if cached is not None and cached[0] == fingerprint:
            return cached[1]
        agent = (
            await build_admin_agent(tenant)
            if role == "admin"
            else await build_public_agent(tenant)
        )
        # Only a genuinely new tenant grows the cache; replacing a stale entry
        # must not evict someone else.
        if key not in _agents:
            while len(_agents) >= MAX_CACHED_AGENTS:
                _agents.pop(next(iter(_agents)))
        _agents[key] = (fingerprint, agent)
        return agent


async def _evict_agent(key: tuple[str, str]) -> None:
    """Drop a cached agent so the next message rebuilds it from scratch.

    Without this, a failed turn is permanent rather than transient: the broken
    agent stays in `_agents`, every later message for that tenant hits the same
    object, and since `respond` returns `None` the webhook sends nothing — the
    customer just gets silence, with no error anywhere but the logs.
    """
    async with _agents_lock:
        _agents.pop(key, None)


async def respond(
    *,
    tenant_id: str,
    user_phone: str,
    content: str,
    media: list[dict] | None = None,
) -> str | None:
    """Ejecuta el agente correspondiente y devuelve el texto final ('' si falla)."""
    media_types = [m.get("type") for m in (media or [])]
    logger.debug(
        "[START] tenant=%s phone=%s media=%s texto_chars=%d",
        tenant_id, user_phone, media_types, len(content or ""),
    )
    agent_key: tuple[str, str] | None = None
    try:
        tenant = await load_tenant_config(tenant_id)
        role = resolve_role(user_phone, tenant)
        agent_key = (tenant_id, role)
        thread_id = f"{tenant_id}:{role}:{user_phone}"

        transcript = await transcribe_audio_media(media)
        text_parts = [content] if content else []
        if transcript:
            text_parts.append(f"[Nota de voz]: {transcript}")
            logger.debug("[TRANSCRIPCION] tenant=%s chars=%d", tenant_id, len(transcript))
        text = ("\n".join(text_parts) + _image_note(media) + _document_note(media)).strip()

        logger.debug(
            "[INPUT_AGENTE] tenant=%s role=%s texto_final=%r",
            tenant_id, role, text[:120],
        )

        agent = await _get_or_build_agent(tenant, role)
        run_turn = run_admin_agent_turn if role == "admin" else run_public_agent_turn
        result = await run_turn(agent, tenant, thread_id, text)

        messages = result.get("messages", [])
        last = messages[-1] if messages else None
        reply = (getattr(last, "content", "") or "").strip()

        logger.debug(
            "[OUTPUT_AGENTE] tenant=%s role=%s chars=%d respuesta=%r",
            tenant_id, role, len(reply), reply[:120],
        )
        return reply
    except Exception:
        logger.exception("respuesta IA falló tenant=%s phone=%s", tenant_id, user_phone)
        if agent_key is not None:
            await _evict_agent(agent_key)
        return None

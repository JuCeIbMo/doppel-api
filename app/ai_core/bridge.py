"""Puente entre el webhook y el agente LangGraph. Entrada única por mensaje.

Reemplaza a `app/ai/bridge.py` (Agno). Diferencias del contrato viejo:
- No recibe `mode`/`system_prompt`/`model`: el rol (público/admin) se resuelve
  acá por `resolve_role(user_phone, tenant)` (autoridad del número, igual que
  antes), y el prompt/modelo salen de `app/ai_core` (prompts estáticos +
  DeepSeek), no de `bot_configs.system_prompt`/`ai_model`.
- No soporta imágenes todavía (ver `media/transcription.py`) — solo texto y
  transcripción de audio.

Cachea un agente compilado por `(tenant_id, role)` para no abrir una conexión
de checkpointer nueva en cada mensaje. Sin invalidación por cambios de config
todavía (ver TODO abajo) — conocido, no oculto.
"""

from __future__ import annotations

import logging
import threading

from app.ai_core.agents.admin_agent import build_admin_agent, run_admin_agent_turn
from app.ai_core.agents.public_agent import build_public_agent, run_public_agent_turn
from app.ai_core.config.loader import load_tenant_config
from app.ai_core.config.tenant import TenantConfig, resolve_role
from app.ai_core.media.transcription import transcribe_audio_media

logger = logging.getLogger("doppel.ai_core.bridge")

_agents: dict[tuple[str, str], object] = {}
_agents_lock = threading.Lock()


def _document_note(media: list[dict] | None) -> str:
    docs = [m for m in (media or []) if m.get("type") not in {"image", "audio", "voice"}]
    return "\n[documento adjunto]" if docs else ""


def _image_note(media: list[dict] | None) -> str:
    images = [m for m in (media or []) if m.get("type") == "image"]
    return "\n[el cliente envió una imagen; hoy no puedo verla, pedile que describa lo que busca]" if images else ""


def _get_or_build_agent(tenant: TenantConfig, role: str):
    """Cache the compiled agent per (tenant_id, role). Built lazily on first use.

    TODO: no cache invalidation on tenant config changes yet (the ported
    project's TenantRegistry tracked a config "generation" to rebuild only
    when it changed — worth porting once bot_configs/business_info edits need
    to reach a running process without a restart).
    """
    key = (tenant.tenant_id, role)
    with _agents_lock:
        agent = _agents.get(key)
        if agent is None:
            agent = build_admin_agent(tenant) if role == "admin" else build_public_agent(tenant)
            _agents[key] = agent
        return agent


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
    try:
        tenant = load_tenant_config(tenant_id)
        role = resolve_role(user_phone, tenant)
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

        agent = _get_or_build_agent(tenant, role)
        run_turn = run_admin_agent_turn if role == "admin" else run_public_agent_turn
        result = run_turn(agent, tenant, thread_id, text)

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
        return None

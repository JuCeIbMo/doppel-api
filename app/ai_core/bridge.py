"""Puente entre el webhook y el agente LangGraph. Entrada única por mensaje.

Reemplaza a `app/ai/bridge.py` (Agno). Diferencias del contrato viejo:
- No recibe `mode`/`system_prompt`/`model`: el rol (público/admin) se resuelve
  acá por `resolve_role(user_phone, tenant)` (autoridad del número, igual que
  antes), y el prompt/modelo salen de `app/ai_core` (prompts estáticos +
  DeepSeek), no de `bot_configs.system_prompt`/`ai_model`.
- Las imágenes entrantes se describen con Gemini (`media/vision.py`) antes de
  llegar al agente: éste nunca ve la foto, sólo el texto que la describe. Sin
  `GEMINI_API_KEY` o si Gemini falla, cae a pedirle al cliente que la describa.

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
from contextlib import asynccontextmanager

from app.ai_core.admin import build_admin_agent, run_admin_agent_turn
from app.ai_core.public import build_public_agent, run_public_agent_turn
from app.ai_core.channel.actions import TurnResult
from app.ai_core.channel.inbound import InteractiveReply
from app.ai_core.config.loader import load_tenant_config
from app.ai_core.tools.channel import ADMIN_CANCEL_PREFIX, ADMIN_CONFIRM_PREFIX
from app.ai_core.config.tenant import TenantConfig, resolve_role
from app.ai_core.media.transcription import transcribe_audio_media
from app.ai_core.media.vision import describe_image_media
from app.services.erp.admin_actions import AdminActionService
from app.services.erp.context import bot_context

logger = logging.getLogger("doppel.ai_core.bridge")

_agents: dict[tuple[str, str], tuple[str, object]] = {}
_agents_lock = asyncio.Lock()

# Cap the cache so a long tail of tenants cannot grow it without bound. Agents
# are cheap to rebuild (no I/O beyond grabbing a pooled connection), so the
# oldest entry is simply dropped.
MAX_CACHED_AGENTS = 100

# One lock per live conversation, refcounted (see `_thread_lock`).
_thread_locks: dict[str, tuple[asyncio.Lock, int]] = {}
_thread_locks_guard = asyncio.Lock()


def _document_note(media: list[dict] | None) -> str:
    docs = [m for m in (media or []) if m.get("type") not in {"image", "audio", "voice"}]
    return "\n[documento adjunto]" if docs else ""


def _image_fallback_note(media: list[dict] | None) -> str:
    """Se usa sólo si hay imágenes pero Gemini no pudo describir ninguna (sin key o falla)."""
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


@asynccontextmanager
async def _thread_lock(thread_id: str):
    """Serialize turns on one conversation.

    A customer sending two messages in a row fires two background tasks that
    run the graph against the same checkpoint at once: both read the same
    state, both write, and the second write wins — so one message effectively
    never happened and its half of the conversation history is lost. Queue them
    instead.

    Refcounted so the dict does not grow one entry per conversation forever.
    """
    async with _thread_locks_guard:
        lock, waiters = _thread_locks.get(thread_id) or (asyncio.Lock(), 0)
        _thread_locks[thread_id] = (lock, waiters + 1)
    try:
        async with lock:
            yield
    finally:
        async with _thread_locks_guard:
            lock, waiters = _thread_locks[thread_id]
            if waiters <= 1:
                del _thread_locks[thread_id]
            else:
                _thread_locks[thread_id] = (lock, waiters - 1)


async def _evict_agent(key: tuple[str, str]) -> None:
    """Drop a cached agent so the next message rebuilds it from scratch.

    Without this, a failed turn is permanent rather than transient: the broken
    agent stays in `_agents`, every later message for that tenant hits the same
    object, and since `respond` returns `None` the webhook sends nothing — the
    customer just gets silence, with no error anywhere but the logs.
    """
    async with _agents_lock:
        _agents.pop(key, None)


async def _consume_admin_confirmation(tenant: TenantConfig, thread_id: str,
                                      reply: InteractiveReply | None) -> str | None:
    """Validate our confirmation buttons before the LLM sees their identifier."""
    if reply is None:
        return None
    value = reply.value
    if value.startswith(ADMIN_CONFIRM_PREFIX):
        action_id, confirmed = value.removeprefix(ADMIN_CONFIRM_PREFIX), True
    elif value.startswith(ADMIN_CANCEL_PREFIX):
        action_id, confirmed = value.removeprefix(ADMIN_CANCEL_PREFIX), False
    else:
        return None
    if not action_id:
        return None
    return await AdminActionService().consume_reply(
        bot_context(tenant.tenant_id, actor="admin_bot"), thread_id=thread_id,
        action_id=action_id, confirmed=confirmed,
    )


async def respond(
    *,
    tenant_id: str,
    user_phone: str,
    content: str,
    media: list[dict] | None = None,
    message_id: str | None = None,
    interactive_reply: InteractiveReply | None = None,
) -> TurnResult:
    """Ejecuta el agente correspondiente y devuelve su texto y sus acciones de canal.

    `message_id` es el id del mensaje entrante de WhatsApp. Identifica el turno y
    de ahí sale la clave de idempotencia de `create_order`: si Meta reentrega el
    mismo mensaje, la venta no se registra dos veces.

    Devuelve siempre un `TurnResult`, nunca `None`: `ok=False` es el agente que
    crasheó, y `text=""` con `ok=True` es una respuesta vacía legítima. El webhook
    no manda nada en ninguno de los dos casos, pero los loguea distinto.
    """
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
        image_description = await describe_image_media(media)
        # Un tap no es texto del cliente: se reemplaza por la nota, en vez de
        # mandarle al agente el título del botón como si lo hubiera escrito.
        text_parts = (
            [interactive_reply.as_agent_note()]
            if interactive_reply is not None
            else ([content] if content else [])
        )
        if transcript:
            text_parts.append(f"[Nota de voz]: {transcript}")
            logger.debug("[TRANSCRIPCION] tenant=%s chars=%d", tenant_id, len(transcript))
        if image_description:
            text_parts.append(f"[Imagen enviada]: {image_description}")
            logger.debug("[VISION] tenant=%s chars=%d", tenant_id, len(image_description))
        fallback = "" if image_description else _image_fallback_note(media)
        text = ("\n".join(text_parts) + fallback + _document_note(media)).strip()

        logger.debug(
            "[INPUT_AGENTE] tenant=%s role=%s texto_final=%r",
            tenant_id, role, text[:120],
        )

        agent = await _get_or_build_agent(tenant, role)
        run_turn = run_admin_agent_turn if role == "admin" else run_public_agent_turn
        async with _thread_lock(thread_id):
            if role == "admin":
                confirmed_action_id = await _consume_admin_confirmation(
                    tenant, thread_id, interactive_reply
                )
                # Sólo el camino admin necesita los bytes de la foto (alta de
                # producto); el público no da de alta productos, así que no
                # agrandamos su `configurable` sin motivo.
                images = [
                    {"path": m["local_path"],
                     "mime_type": m.get("downloaded_mime_type") or m.get("mime_type")}
                    for m in (media or [])
                    if m.get("type") == "image" and m.get("local_path")
                ]
                result = await run_turn(
                    agent, tenant, thread_id, text, message_id,
                    confirmed_action_id=confirmed_action_id, images=images,
                )
            else:
                result = await run_turn(agent, tenant, thread_id, text, message_id)

        messages = result.get("messages", [])
        last = messages[-1] if messages else None
        reply = (getattr(last, "content", "") or "").strip()

        actions = result.get("channel_actions") or []
        logger.debug(
            "[OUTPUT_AGENTE] tenant=%s role=%s chars=%d acciones=%d respuesta=%r",
            tenant_id, role, len(reply), len(actions), reply[:120],
        )
        return TurnResult(text=reply, actions=actions)
    except Exception:
        logger.exception("respuesta IA falló tenant=%s phone=%s", tenant_id, user_phone)
        if agent_key is not None:
            await _evict_agent(agent_key)
        return TurnResult(ok=False)

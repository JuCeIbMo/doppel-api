"""Historial de conversación por sesión, persistido en Postgres.

Pydantic AI no maneja persistencia de sesión: la app pasa `message_history` y
guarda `result.new_messages()`. Acá lo resolvemos con un Postgres dedicado
(CHAT_DB_URL) y `psycopg` directo. Si CHAT_DB_URL está vacío, el historial corre
en memoria de proceso (dev/tests).

Best-effort: cualquier fallo de Postgres se loguea y NO rompe la respuesta.
"""

from __future__ import annotations

import logging

import psycopg
from psycopg.types.json import Json
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter

from app.ai.config import CHAT_DB_URL

logger = logging.getLogger("doppel.ai.history")

# Cuántos mensajes mantener en contexto por sesión.
_MAX_MESSAGES = 40

# Fallback en memoria cuando no hay CHAT_DB_URL.
_MEM: dict[str, list[ModelMessage]] = {}

_schema_ready = False

_DDL = """
CREATE TABLE IF NOT EXISTS chat_messages (
    session_id  text        NOT NULL,
    seq         bigserial   PRIMARY KEY,
    data        jsonb       NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS chat_messages_session_idx ON chat_messages (session_id, seq);
"""


def session_id_for(tenant_id: str, user_phone: str) -> str:
    return f"{tenant_id}:{user_phone}"


def _ensure_schema(conn: psycopg.Connection) -> None:
    global _schema_ready
    if _schema_ready:
        return
    conn.execute(_DDL)
    _schema_ready = True


def load(session_id: str) -> list[ModelMessage]:
    if not CHAT_DB_URL:
        return list(_MEM.get(session_id, []))[-_MAX_MESSAGES:]
    try:
        with psycopg.connect(CHAT_DB_URL, autocommit=True) as conn:
            _ensure_schema(conn)
            rows = conn.execute(
                "SELECT data FROM chat_messages WHERE session_id = %s ORDER BY seq",
                (session_id,),
            ).fetchall()
        messages: list[ModelMessage] = []
        for (data,) in rows:
            messages.extend(ModelMessagesTypeAdapter.validate_python(data))
        return messages[-_MAX_MESSAGES:]
    except Exception:
        logger.exception("history load falló session=%s", session_id)
        return []


def append(session_id: str, new_messages: list[ModelMessage]) -> None:
    if not new_messages:
        return
    if not CHAT_DB_URL:
        _MEM.setdefault(session_id, []).extend(new_messages)
        return
    try:
        payload = ModelMessagesTypeAdapter.dump_python(new_messages, mode="json")
        with psycopg.connect(CHAT_DB_URL, autocommit=True) as conn:
            _ensure_schema(conn)
            conn.execute(
                "INSERT INTO chat_messages (session_id, data) VALUES (%s, %s)",
                (session_id, Json(payload)),
            )
    except Exception:
        logger.exception("history append falló session=%s", session_id)

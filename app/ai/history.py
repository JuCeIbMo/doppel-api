"""Historial de conversación por sesión, persistido en Postgres.

Pydantic AI no maneja persistencia de sesión: la app pasa `message_history` y
guarda `result.new_messages()`. Acá lo resolvemos con un Postgres dedicado
(CHAT_DB_URL) y `psycopg` directo. Si CHAT_DB_URL está vacío, el historial corre
en memoria de proceso (dev/tests).

Cada run de agente escribe UNA fila (data = lista de mensajes de ese run).
El historial se ventanea por RUNS (filas), no por mensajes aplanados, para no
partir pares ToolCallPart/ToolReturnPart que el LLM exige coherentes.

Best-effort: cualquier fallo de Postgres se loguea y NO rompe la respuesta.
"""

from __future__ import annotations

import dataclasses
import logging

import psycopg
from psycopg.types.json import Json
from pydantic_ai import BinaryContent
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    UserPromptPart,
)

from app.ai.config import CHAT_DB_URL

logger = logging.getLogger("doppel.ai.history")

# Cuántos runs (filas) mantener en contexto por sesión.
_MAX_RUNS = 12

# Fallback en memoria cuando no hay CHAT_DB_URL.
# Almacena una lista de runs por sesión (cada run = list[ModelMessage]).
_MEM: dict[str, list[list[ModelMessage]]] = {}

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


def _strip_binary(messages: list[ModelMessage]) -> list[ModelMessage]:
    """Devuelve copia de messages con BinaryContent reemplazado por '[imagen adjunta]'.

    Evita persistir bytes de imagen en la DB (desperdicio de espacio y ancho de banda).
    Solo toca UserPromptPart cuyo content es una lista mixta de texto/BinaryContent.
    """
    result: list[ModelMessage] = []
    for msg in messages:
        if isinstance(msg, ModelRequest):
            new_parts = []
            for part in msg.parts:
                if isinstance(part, UserPromptPart) and isinstance(part.content, list):
                    new_content = [
                        "[imagen adjunta]" if isinstance(item, BinaryContent) else item
                        for item in part.content
                    ]
                    new_parts.append(dataclasses.replace(part, content=new_content))
                else:
                    new_parts.append(part)
            result.append(dataclasses.replace(msg, parts=new_parts))
        else:
            result.append(msg)
    return result


def load(session_id: str) -> list[ModelMessage]:
    if not CHAT_DB_URL:
        runs = _MEM.get(session_id, [])[-_MAX_RUNS:]
        return [msg for run in runs for msg in run]
    try:
        with psycopg.connect(CHAT_DB_URL, autocommit=True) as conn:
            _ensure_schema(conn)
            rows = conn.execute(
                "SELECT data FROM chat_messages WHERE session_id = %s ORDER BY seq DESC LIMIT %s",
                (session_id, _MAX_RUNS),
            ).fetchall()
        # Las filas vienen en orden descendente; revertir para orden cronológico.
        messages: list[ModelMessage] = []
        for (data,) in reversed(rows):
            messages.extend(ModelMessagesTypeAdapter.validate_python(data))
        return messages
    except Exception:
        logger.exception("history load falló session=%s", session_id)
        return []


def append(session_id: str, new_messages: list[ModelMessage]) -> None:
    if not new_messages:
        return
    # Stripear imágenes antes de persistir (en ambas rutas).
    clean = _strip_binary(new_messages)
    if not CHAT_DB_URL:
        runs = _MEM.setdefault(session_id, [])
        runs.append(clean)
        # Mantener solo los últimos _MAX_RUNS runs en memoria.
        if len(runs) > _MAX_RUNS:
            _MEM[session_id] = runs[-_MAX_RUNS:]
        return
    try:
        payload = ModelMessagesTypeAdapter.dump_python(clean, mode="json")
        with psycopg.connect(CHAT_DB_URL, autocommit=True) as conn:
            _ensure_schema(conn)
            conn.execute(
                "INSERT INTO chat_messages (session_id, data) VALUES (%s, %s)",
                (session_id, Json(payload)),
            )
    except Exception:
        logger.exception("history append falló session=%s", session_id)

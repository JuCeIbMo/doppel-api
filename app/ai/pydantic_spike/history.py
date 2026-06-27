"""Historial de conversación en memoria, por sesión.

Esto es lo que Agno te da gratis con `PostgresDb` + `add_history_to_context`. En
Pydantic AI el historial es responsabilidad de la app: vos pasás `message_history`
y persistís `result.new_messages()`.

SPIKE: store en memoria de proceso (se pierde al reiniciar). El paso productivo
sería persistir estos `ModelMessage` en Postgres por session_id — ese es el
mayor costo real de migrar fuera de Agno.
"""

from __future__ import annotations

from pydantic_ai.messages import ModelMessage

# Cuántos mensajes mantener por sesión (aprox. equivale a num_history_runs de Agno).
_MAX_MESSAGES = 40

_STORE: dict[str, list[ModelMessage]] = {}


def session_id_for(tenant_id: str, user_phone: str) -> str:
    return f"{tenant_id}:{user_phone}"


def load(session_id: str) -> list[ModelMessage]:
    return list(_STORE.get(session_id, []))


def append(session_id: str, new_messages: list[ModelMessage]) -> None:
    history = _STORE.setdefault(session_id, [])
    history.extend(new_messages)
    if len(history) > _MAX_MESSAGES:
        del history[:-_MAX_MESSAGES]

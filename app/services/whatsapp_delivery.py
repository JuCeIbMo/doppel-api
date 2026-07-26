"""Del resultado de un turno al orden exacto de mensajes que sale por WhatsApp.

Función pura, sin red: recibe el `TurnResult` y devuelve la lista de acciones a
entregar. Es el análogo por reglas del "formatter" — decide *presentación*, no
negocio, así que no cuesta un solo token.

Dos reglas, y nada más:

1. **Una sola foto y el texto entra como caption → se pliegan.** WhatsApp muestra
   la foto con su texto debajo, en vez del patrón feo de foto muda seguida de un
   párrafo suelto.
2. **Todo lo demás va en orden**: primero el texto del agente, después las
   acciones tal como las encoló. El orden nunca se reordena: que la foto vaya
   antes que los botones es semántico, no estético.
"""

from __future__ import annotations

from app.ai_core.channel.actions import (
    MAX_BODY,
    MAX_TEXT,
    ChannelAction,
    SendImageAction,
    SendTextAction,
    TurnResult,
)


def plan_delivery(result: TurnResult) -> list[ChannelAction]:
    """Orden final de entrega para un turno."""
    text = (result.text or "").strip()
    actions = list(result.actions)

    images = [action for action in actions if isinstance(action, SendImageAction)]
    if (
        text
        and len(images) == 1
        and not images[0].caption
        and len(text) <= MAX_BODY
    ):
        folded = images[0].model_copy(update={"caption": text})
        return [folded if action is images[0] else action for action in actions]

    plan: list[ChannelAction] = [SendTextAction(body=chunk) for chunk in _chunk(text)]
    plan.extend(actions)
    return plan


def _chunk(text: str, limit: int = MAX_TEXT) -> list[str]:
    """Parte el texto en mensajes de a lo sumo `limit`, cortando por párrafo.

    Sin esto una respuesta larga (un catálogo entero, un reporte) se come un 400
    de Meta y el cliente no recibe absolutamente nada — falla completa en vez de
    degradada.
    """
    if not text:
        return []
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        window = remaining[:limit]
        # Cortar por el límite más "natural" que haya dentro de la ventana.
        cut = max(window.rfind("\n\n"), window.rfind("\n"), window.rfind(" "))
        if cut <= 0:
            cut = limit
        chunks.append(remaining[:cut].strip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        chunks.append(remaining)
    return [chunk for chunk in chunks if chunk]

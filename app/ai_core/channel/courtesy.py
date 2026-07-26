"""Cortesías del canal por reglas: reacción con emoji y pausa de "escribiendo…".

Sin IA y sin tokens. El LLM no decide nada de esto: elegir un emoji con una tool
cuesta un tool call entero para un gesto, y la pausa de tipeo no es una decisión
de negocio sino de presentación.

Todo acá es puro y determinístico salvo la elección dentro del pool de emojis.
"""

from __future__ import annotations

import random
import unicodedata

# Cada intención: claves a buscar en el mensaje entrante -> pool de emojis (se
# elige uno al azar para que no sea siempre el mismo).
#
# Sólo emojis de UN codepoint: Meta rechaza de forma inconsistente los que llevan
# variation selector (❤️ = U+2764 U+FE0F), y el fallo es por mensaje.
_INTENTS: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (("gracias", "genial", "buenisimo", "crack", "de diez", "barbaro"),
     ("🙏", "😊", "🤗")),
    (("me encanta", "lo quiero", "me lo llevo", "hermoso", "divino"),
     ("😍", "🔥", "🤩")),
    (("jaja", "jeje", "jiji", "lol"),
     ("😂", "😄")),
    (("dale", "listo", "perfecto", "de una", "joya"),
     ("👍", "👌", "✅")),
    (("hola", "buenas", "buen dia", "que tal"),
     ("👋", "😃")),
    (("chau", "nos vemos", "hasta luego", "adios"),
     ("👋", "🙌")),
]

# Reacción por tipo de adjunto, cuando el texto no matchea nada.
_BY_ATTACHMENT: dict[str, str] = {
    "image": "👀",
    "audio": "👂",
    "voice": "👂",
    "document": "📄",
    "location": "📍",
}

_FIRST_CONTACT = "👋"


def _normalize(text: str) -> str:
    """Minúsculas y sin acentos, para que el match no dependa de cómo escriban."""
    stripped = "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )
    return stripped.lower()


def choose_reaction(
    text: str | None,
    message_type: str = "text",
    *,
    first_contact: bool = False,
) -> str | None:
    """Emoji para reaccionar al mensaje entrante, o None si no aplica ninguno.

    `first_contact` gana sobre todo lo demás: el saludo inicial merece el mismo
    gesto siempre, sin importar qué haya escrito el cliente.
    """
    if first_contact:
        return _FIRST_CONTACT
    if text:
        normalized = _normalize(text)
        for keys, pool in _INTENTS:
            if any(key in normalized for key in keys):
                return random.choice(pool)
    return _BY_ATTACHMENT.get(message_type.lower())


# --- pausa de "escribiendo…" ------------------------------------------------
#
#   pausa = base + len(texto)/CPS   → recortada a TYPING_MAX_SECONDS
#                                   → × (1 ± jitter)
#
# Se suma a un turno de LLM que ya tarda segundos, así que el techo es bajo a
# propósito: la gracia es que el mensaje no aparezca instantáneo, no simular a
# alguien tecleando párrafos.

TYPING_CPS = 25.0
TYPING_BASE_SECONDS = 0.6
TYPING_MAX_SECONDS = 3.0
TYPING_JITTER = 0.25


def typing_pause(text: str | None, *, elapsed: float = 0.0) -> float:
    """Segundos a esperar antes de mandar `text`, descontando `elapsed`.

    `elapsed` es el tiempo que ya pasó desde que el cliente escribió (por
    ejemplo, lo que tardó el modelo). Si el turno ya tardó más que la pausa
    objetivo, no hay nada que simular y devuelve 0.
    """
    target = min(TYPING_BASE_SECONDS + len(text or "") / TYPING_CPS, TYPING_MAX_SECONDS)
    target *= random.uniform(1.0 - TYPING_JITTER, 1.0 + TYPING_JITTER)
    return max(0.0, target - elapsed)

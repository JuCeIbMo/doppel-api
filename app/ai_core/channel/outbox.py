"""Buffer de acciones de canal de UN turno.

Las tools no mandan nada por su cuenta: encolan acá, y cuando el grafo termina
el webhook las entrega en orden. Así `ai_core` no necesita el `httpx.AsyncClient`
ni las credenciales del tenant, y se puede testear entero sin red.

**Por qué esto viaja por el `context=` de LangGraph y no de otra forma.**
`ToolContextMiddleware` construye un `ToolContext` nuevo en cada tool call, y el
middleware vive dentro de un agente que `bridge` cachea *entre turnos y entre
conversaciones distintas del mismo tenant*. Un buffer colgado del middleware se
filtraría de un cliente a otro. El `context=` de LangGraph es run-scoped: se pasa
en el `ainvoke` y el runtime lo propaga a los subgrafos, así que un objeto nuevo
por invocación da aislamiento por construcción y no por convención.

Tampoco puede vivir en el estado del grafo: el `AsyncPostgresSaver` lo
serializaría al checkpoint, que es durable y acumulativo.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.ai_core.channel.actions import ChannelAction


@dataclass
class TurnOutbox:
    """Acciones encoladas por las tools durante un turno, en orden de encolado."""

    actions: list[ChannelAction] = field(default_factory=list)

    def add(self, action: ChannelAction) -> None:
        self.actions.append(action)

    def drain(self) -> list[ChannelAction]:
        """Devuelve lo encolado y vacía el buffer."""
        actions, self.actions = self.actions, []
        return actions


@dataclass
class TurnRuntime:
    """Lo que se pasa como `context=` al invocar el grafo. Uno nuevo por turno.

    ⚠️ NO le definas `__bool__` ni `__len__`. `Runtime.merge` de LangGraph hace
    ``context = other.context or self.context``: un contexto *falsy* se pierde
    en silencio al cruzar al subgrafo de un especialista, las tools encolan en
    el vacío y nadie se entera. Un dataclass sin esos métodos siempre es truthy.
    `tests/test_turn_outbox.py` lo fija.
    """

    outbox: TurnOutbox = field(default_factory=TurnOutbox)
    # Tenant de ESTE turno, resuelto por el servidor a partir del `phone_number_id`
    # verificado por Meta. Nunca sale del texto del mensaje ni del estado del grafo.
    # El `StoreBackend` del agente admin lo usa para verificar que el namespace de
    # memoria que quedó soldado al agente en build time es el del turno en curso
    # (`app/ai_core/admin/agent.py`).
    tenant_id: str = ""

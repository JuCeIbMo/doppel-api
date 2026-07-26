"""Lo que llega desde el canal y el agente tiene que poder entender.

Hoy es sólo el tap de un botón o de una fila de lista. Vive acá y no en el
router porque `bridge` es quien lo traduce a texto para el agente, y `ai_core`
no puede importar de `app.routers`.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.ai_core.tools.channel import CHOICE_PREFIX


@dataclass
class InteractiveReply:
    """Un botón o una fila de lista que el cliente tocó."""

    id: str
    title: str = ""

    @property
    def value(self) -> str:
        """El id sin nuestro namespace.

        Un id sin el prefijo `choice:` no lo generamos nosotros — una plantilla
        de Meta, un botón de un deploy anterior — así que se devuelve tal cual.
        """
        if self.id.startswith(CHOICE_PREFIX):
            return self.id[len(CHOICE_PREFIX):]
        return self.id

    def as_agent_note(self) -> str:
        """Cómo percibe el agente el tap, en el mismo formato que las otras notas."""
        label = self.title or self.value
        return f'[El cliente tocó la opción "{label}" (id: {self.value})]'

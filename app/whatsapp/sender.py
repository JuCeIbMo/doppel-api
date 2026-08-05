"""Salida hacia WhatsApp: todo lo que el número del tenant puede *hacer*.

Frontera entre "lo que el agente decidió" y "lo que efectivamente sale por
WhatsApp". Una instancia por conversación, con las credenciales del tenant ya
resueltas, para que ni el webhook ni las tools tengan que andar pasando
`phone_number_id`/token/`api_version` en cada llamada.

Dos categorías de método, con manejo de error deliberadamente distinto:

- **Cortesías** (`mark_read_and_typing`, `react`): best-effort. Si Meta las
  rechaza — un `message_id` viejo, una `META_API_VERSION` anterior a v21.0 que
  no soporta `typing_indicator` — se loguean y siguen. Un gesto fallido no
  puede dejar al cliente sin respuesta.
- **Envíos reales** (`send_*`): propagan. Si no salió, el caller tiene que
  enterarse y no registrar la fila en `messages`.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from app.ai_core.channel import courtesy
from app.whatsapp import meta

logger = logging.getLogger("doppel.whatsapp.sender")


class WhatsAppSender:
    """Acciones de canal apuntando a un cliente concreto.

    `inbound_message_id` es el id del mensaje que estamos contestando: las
    tildes azules, el "escribiendo…" y la reacción se cuelgan de un mensaje
    concreto, así que sin él esas tres son no-ops.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        phone_number_id: str,
        token: str,
        api_version: str,
        to: str,
        inbound_message_id: str | None = None,
    ):
        self._client = client
        self._phone_number_id = phone_number_id
        self._token = token
        self._api_version = api_version
        self._to = to
        self._inbound_message_id = inbound_message_id

    # --- cortesías (best-effort, cero tokens) -------------------------------

    async def mark_read_and_typing(self, *, typing: bool = True) -> None:
        """Tildes azules y "escribiendo…" sobre el mensaje entrante.

        Se llama ANTES de invocar al modelo, no después: la gracia es que el
        indicador esté visible mientras el LLM piensa, que es justo donde el
        cliente hoy ve silencio.
        """
        if not self._inbound_message_id:
            return
        try:
            await meta.mark_whatsapp_read(
                self._client,
                self._phone_number_id,
                self._inbound_message_id,
                self._token,
                self._api_version,
                typing=typing,
            )
        except Exception:
            logger.warning(
                "mark_read falló (ignorado) to=%s msg_id=%s",
                self._to, self._inbound_message_id, exc_info=True,
            )

    async def react(self, emoji: str) -> None:
        """Reacciona al mensaje entrante. `emoji` vacío quita la reacción."""
        if not self._inbound_message_id:
            return
        try:
            await meta.send_whatsapp_reaction(
                self._client,
                self._phone_number_id,
                self._to,
                self._inbound_message_id,
                emoji,
                self._token,
                self._api_version,
            )
        except Exception:
            logger.warning(
                "react falló (ignorado) to=%s emoji=%r", self._to, emoji, exc_info=True,
            )

    async def human_pause(self, text: str | None, *, elapsed: float = 0.0) -> None:
        """Espera lo que tardaría una persona en escribir `text`."""
        await asyncio.sleep(courtesy.typing_pause(text, elapsed=elapsed))

    # --- envíos reales (propagan) -------------------------------------------

    async def send_text(self, body: str) -> str:
        return await meta.send_whatsapp_message(
            self._client, self._phone_number_id, self._to, body,
            self._token, self._api_version,
        )

    async def send_image(self, image_url: str, caption: str | None = None) -> str:
        return await meta.send_whatsapp_image_message(
            self._client, self._phone_number_id, self._to, image_url, caption,
            self._token, self._api_version,
        )

    async def send_buttons(self, body: str, buttons: list[tuple[str, str]]) -> str:
        return await meta.send_whatsapp_buttons(
            self._client, self._phone_number_id, self._to, body, buttons,
            self._token, self._api_version,
        )

    async def send_list(self, body: str, button_label: str, sections: list[dict]) -> str:
        return await meta.send_whatsapp_list(
            self._client, self._phone_number_id, self._to, body, button_label, sections,
            self._token, self._api_version,
        )

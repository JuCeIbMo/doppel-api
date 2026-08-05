"""Tests del transporte de canal: WhatsAppSender y los payloads de meta_api.

Las aserciones son sobre el JSON exacto que sale hacia Meta. Un payload
interactivo mal formado no se detecta en desarrollo — Meta devuelve 400 y el
cliente simplemente no recibe el mensaje — así que la forma se fija acá.

app.config instantiates Settings() at import time, requiring these env vars.
Set safe test defaults before import.
"""

import os

os.environ.setdefault("META_APP_ID", "test-app-id")
os.environ.setdefault("META_APP_SECRET", "test-app-secret")
os.environ.setdefault("META_VERIFY_TOKEN", "test-verify-token")
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "x.eyJyb2xlIjogInNlcnZpY2Vfcm9sZSJ9.y")
os.environ.setdefault("ENCRYPTION_KEY", "oZRrOD525wcQ0CJveupENSX1tDwKfP6e1XrDGn9P1Kw=")
os.environ.setdefault("CHAT_DB_URL", "postgresql://ai:ai@localhost:5532/chat")

import asyncio

import httpx
import pytest

from app.services.whatsapp_sender import WhatsAppSender

API_VERSION = "v21.0"
PHONE_ID = "phone-1"
TO = "59170000002"
INBOUND = "wamid.IN1"


class FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload

    @property
    def status_code(self) -> int:
        return 200


class FakeClient:
    """Captura las llamadas en vez de salir a la red."""

    def __init__(self, payload: dict | None = None, error: Exception | None = None):
        self.calls: list[dict] = []
        self._payload = payload if payload is not None else {"messages": [{"id": "wamid.OUT1"}]}
        self._error = error

    async def request(self, method: str, url: str, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        if self._error is not None:
            raise self._error
        return FakeResponse(self._payload)

    @property
    def body(self) -> dict:
        return self.calls[-1]["json"]


def _sender(client, *, inbound_message_id: str | None = INBOUND) -> WhatsAppSender:
    return WhatsAppSender(
        client,
        phone_number_id=PHONE_ID,
        token="tok",
        api_version=API_VERSION,
        to=TO,
        inbound_message_id=inbound_message_id,
    )


def test_send_text_payload():
    client = FakeClient()
    result = asyncio.run(_sender(client).send_text("hola"))

    assert result == "wamid.OUT1"
    assert client.calls[0]["url"] == (
        f"https://graph.facebook.com/{API_VERSION}/{PHONE_ID}/messages"
    )
    assert client.calls[0]["headers"]["Authorization"] == "Bearer tok"
    assert client.body == {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": TO,
        "type": "text",
        "text": {"body": "hola"},
    }


def test_send_image_omits_caption_when_empty():
    client = FakeClient()
    asyncio.run(_sender(client).send_image("https://cdn/x.webp"))

    assert client.body["image"] == {"link": "https://cdn/x.webp"}


def test_send_image_includes_caption():
    client = FakeClient()
    asyncio.run(_sender(client).send_image("https://cdn/x.webp", "Remera azul"))

    assert client.body["image"] == {"link": "https://cdn/x.webp", "caption": "Remera azul"}


def test_send_buttons_payload():
    client = FakeClient()
    asyncio.run(_sender(client).send_buttons("¿Cómo pagás?", [("choice:cash", "Efectivo")]))

    assert client.body["type"] == "interactive"
    assert client.body["interactive"] == {
        "type": "button",
        "body": {"text": "¿Cómo pagás?"},
        "action": {
            "buttons": [
                {"type": "reply", "reply": {"id": "choice:cash", "title": "Efectivo"}},
            ],
        },
    }


def test_send_buttons_truncates_for_callers_that_did_not_validate():
    client = FakeClient()
    asyncio.run(_sender(client).send_buttons(
        "elegí",
        [("a", "x" * 25), ("b", "B"), ("c", "C"), ("d", "D")],
    ))

    buttons = client.body["interactive"]["action"]["buttons"]
    assert len(buttons) == 3
    assert buttons[0]["reply"]["title"] == "x" * 20


def test_send_list_payload():
    client = FakeClient()
    sections = [{"title": "Bebidas", "rows": [{"id": "p1", "title": "Café", "description": "$3"}]}]
    asyncio.run(_sender(client).send_list("Nuestro catálogo:", "Ver opciones", sections))

    assert client.body["interactive"] == {
        "type": "list",
        "body": {"text": "Nuestro catálogo:"},
        "action": {"button": "Ver opciones", "sections": sections},
    }


def test_react_payload():
    client = FakeClient()
    asyncio.run(_sender(client).react("👍"))

    assert client.body == {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": TO,
        "type": "reaction",
        "reaction": {"message_id": INBOUND, "emoji": "👍"},
    }


def test_mark_read_and_typing_payload():
    client = FakeClient(payload={"success": True})
    # Meta responde {"success": true} — sin `messages`. Si esto intentara leer
    # un message id, reventaría acá.
    asyncio.run(_sender(client).mark_read_and_typing())

    assert client.body == {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": INBOUND,
        "typing_indicator": {"type": "text"},
    }


def test_mark_read_without_typing_omits_the_indicator():
    client = FakeClient(payload={"success": True})
    asyncio.run(_sender(client).mark_read_and_typing(typing=False))

    assert "typing_indicator" not in client.body


def test_courtesies_are_noops_without_an_inbound_message_id():
    client = FakeClient()
    sender = _sender(client, inbound_message_id=None)

    asyncio.run(sender.mark_read_and_typing())
    asyncio.run(sender.react("👍"))

    assert client.calls == []


def test_courtesies_swallow_meta_errors():
    """Un gesto rechazado no puede dejar al cliente sin respuesta."""
    client = FakeClient(error=httpx.HTTPError("boom"))
    sender = _sender(client)

    asyncio.run(sender.mark_read_and_typing())
    asyncio.run(sender.react("👍"))


def test_real_sends_propagate_meta_errors():
    """Si el mensaje no salió, el caller tiene que enterarse y no registrarlo."""
    client = FakeClient(error=httpx.HTTPError("boom"))

    with pytest.raises(httpx.HTTPError):
        asyncio.run(_sender(client).send_text("hola"))

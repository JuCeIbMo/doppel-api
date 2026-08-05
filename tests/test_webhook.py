import os

import hashlib
import hmac
import json
import shutil
import tempfile
from contextlib import ExitStack
from unittest.mock import AsyncMock
from unittest.mock import patch

from app.ai_core.channel.actions import SendImageAction, TurnResult
from app.security import verify_webhook_signature
from tests.api_case import ApiTestCase
from tests.fakes import FakeSupabase

def _turn(text: str, actions=None) -> TurnResult:
    """Lo que devuelve `bridge.respond`: texto más acciones de canal."""
    return TurnResult(text=text, actions=actions or [])


class WebhookApiTests(ApiTestCase):
    def _connected_store(self, *, bot_enabled=True):
        return {
            "whatsapp_accounts": [
                {
                    "id": "wa-1",
                    "tenant_id": "tenant-1",
                    "phone_number_id": "phone-1",
                    "status": "connected",
                    "access_token_encrypted": "encrypted",
                }
            ],
            "bot_configs": [
                {
                    "tenant_id": "tenant-1",
                    "admin_phones": [],
                    "bot_enabled": bot_enabled,
                    "ai_model": "claude-test",
                }
            ],
            "messages": [],
        }

    def _post_webhook(self, payload, fake_supabase, ai_core_response, **extra_patches):
        patches = [
            patch("app.whatsapp.webhook.get_supabase", return_value=fake_supabase),
            patch("app.routers.webhook.verify_webhook_signature", return_value=True),
            patch("app.routers.webhook.settings.BOT_ENABLED", "http://ai-core"),
            patch("app.whatsapp.turn.ai_respond", ai_core_response),
            patch("app.whatsapp.turn.decrypt_token", return_value="token"),
            patch(
                "app.whatsapp.meta.send_whatsapp_message",
                AsyncMock(return_value="out-1"),
            ),
        ]
        patches += [patch(target, mock) for target, mock in extra_patches.items()]

        with ExitStack() as stack:
            for patcher in patches:
                stack.enter_context(patcher)
            return self.client.post(
                "/webhook/whatsapp",
                content=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )

    def test_webhook_signature_verification_and_deduplication(self):
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {"phone_number_id": "phone-1"},
                                "messages": [
                                    {"id": "wamid-1", "from": "59170000001", "type": "text", "text": {"body": "Hola"}},
                                    {"id": "wamid-1", "from": "59170000001", "type": "text", "text": {"body": "Hola"}},
                                ],
                            }
                        }
                    ]
                }
            ]
        }
        raw_body = json.dumps(payload).encode()
        signature = "sha256=" + hmac.new(b"secret", raw_body, hashlib.sha256).hexdigest()
        self.assertTrue(verify_webhook_signature(raw_body, signature, "secret"))

        fake_store = {
            "whatsapp_accounts": [
                {"id": "wa-1", "tenant_id": "tenant-1", "phone_number_id": "phone-1", "status": "connected"}
            ],
            "messages": [],
        }
        fake_supabase = FakeSupabase(fake_store)

        with (
            patch("app.whatsapp.webhook.get_supabase", return_value=fake_supabase),
            patch("app.routers.webhook.verify_webhook_signature", return_value=True),
        ):
            response = self.client.post(
                "/webhook/whatsapp",
                content=raw_body,
                headers={"X-Hub-Signature-256": signature, "Content-Type": "application/json"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(fake_store["messages"]), 1)

    def test_webhook_ignores_unregistered_phone_number_id(self):
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {"phone_number_id": "phone-missing"},
                                "messages": [
                                    {"id": "wamid-missing-1", "from": "59170000003", "type": "text", "text": {"body": "Hola"}}
                                ],
                            }
                        }
                    ]
                }
            ]
        }
        fake_store = {"whatsapp_accounts": [], "messages": []}
        fake_supabase = FakeSupabase(fake_store)

        with (
            patch("app.whatsapp.webhook.get_supabase", return_value=fake_supabase),
            patch("app.routers.webhook.verify_webhook_signature", return_value=True),
            self.assertLogs("doppel.whatsapp.webhook", level="INFO") as logs,
        ):
            response = self.client.post(
                "/webhook/whatsapp",
                content=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(fake_store["messages"], [])
        self.assertIn("phone_number_id no registrado", "\n".join(logs.output))

    def test_webhook_routes_admin_phone_to_nanobot_manager(self):
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {"phone_number_id": "phone-1"},
                                "messages": [
                                    {"id": "wamid-2", "from": "59170000001", "type": "text", "text": {"body": "Cambia horario"}}
                                ],
                            }
                        }
                    ]
                }
            ]
        }
        fake_store = {
            "whatsapp_accounts": [
                {
                    "id": "wa-1",
                    "tenant_id": "tenant-1",
                    "phone_number_id": "phone-1",
                    "status": "connected",
                    "access_token_encrypted": "encrypted",
                }
            ],
            "bot_configs": [
                {
                    "tenant_id": "tenant-1",
                    "admin_phones": ["59170000001"],
                    "bot_enabled": False,
                    "ai_model": "claude-test",
                }
            ],
            "messages": [],
        }
        fake_supabase = FakeSupabase(fake_store)
        ai_core_response = AsyncMock(return_value=_turn("Listo"))

        with (
            patch("app.whatsapp.webhook.get_supabase", return_value=fake_supabase),
            patch("app.routers.webhook.verify_webhook_signature", return_value=True),
            patch("app.routers.webhook.settings.BOT_ENABLED", "http://ai-core"),
            patch("app.whatsapp.turn.ai_respond", ai_core_response),
            patch("app.whatsapp.turn.decrypt_token", return_value="token"),
            patch("app.whatsapp.meta.send_whatsapp_message", AsyncMock(return_value="out-1")),
        ):
            response = self.client.post(
                "/webhook/whatsapp",
                content=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )

        self.assertEqual(response.status_code, 200)
        ai_core_response.assert_awaited_once()
        self.assertEqual(ai_core_response.await_args.kwargs["tenant_id"], "tenant-1")
        self.assertEqual(ai_core_response.await_args.kwargs["user_phone"], "59170000001")
        self.assertEqual(fake_store["messages"][0]["agent_mode"], "manager")
        self.assertEqual(fake_store["messages"][1]["content"], "Listo")

    def test_webhook_routes_regular_phone_to_ai_core_client_with_context(self):
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {"phone_number_id": "phone-1"},
                                "messages": [
                                    {"id": "wamid-3", "from": "59170000002", "type": "text", "text": {"body": "Precio?"}}
                                ],
                            }
                        }
                    ]
                }
            ]
        }
        fake_store = {
            "whatsapp_accounts": [
                {
                    "id": "wa-1",
                    "tenant_id": "tenant-1",
                    "phone_number_id": "phone-1",
                    "status": "connected",
                    "access_token_encrypted": "encrypted",
                }
            ],
            "bot_configs": [
                {
                    "tenant_id": "tenant-1",
                    "admin_phones": ["59170000001"],
                    "bot_enabled": True,
                    "system_prompt": "Eres el bot cliente",
                    "manager_prompt": "Eres el manager agent",
                    "ai_model": "claude-test",
                }
            ],
            "messages": [
                {
                    "id": "old-1",
                    "tenant_id": "tenant-1",
                    "user_phone": "59170000002",
                    "direction": "inbound",
                    "content": "Hola",
                    "created_at": "2026-06-11T07:50:00Z",
                },
                {
                    "id": "old-2",
                    "tenant_id": "tenant-1",
                    "user_phone": "59170000002",
                    "direction": "outbound",
                    "content": "Hola, en que ayudo?",
                    "created_at": "2026-06-11T07:51:00Z",
                },
            ],
        }
        fake_supabase = FakeSupabase(fake_store)
        ai_core_response = AsyncMock(return_value=_turn("Cuesta 10"))

        with (
            patch("app.whatsapp.webhook.get_supabase", return_value=fake_supabase),
            patch("app.routers.webhook.verify_webhook_signature", return_value=True),
            patch("app.routers.webhook.settings.BOT_ENABLED", "http://ai-core"),
            patch("app.whatsapp.turn.ai_respond", ai_core_response),
            patch("app.whatsapp.turn.decrypt_token", return_value="token"),
            patch("app.whatsapp.meta.send_whatsapp_message", AsyncMock(return_value="out-2")),
        ):
            response = self.client.post(
                "/webhook/whatsapp",
                content=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )

        self.assertEqual(response.status_code, 200)
        ai_core_response.assert_awaited_once()
        self.assertEqual(ai_core_response.await_args.kwargs["tenant_id"], "tenant-1")
        self.assertEqual(ai_core_response.await_args.kwargs["user_phone"], "59170000002")
        # El historial ahora lo administra app.ai_core (checkpointer LangGraph en su
        # propio Postgres) vía thread_id; el API ya no envía la conversación.
        self.assertNotIn("conversation", ai_core_response.await_args.kwargs)
        directions = [m["direction"] for m in fake_store["messages"]]
        self.assertIn("inbound", directions)
        self.assertIn("outbound", directions)
        self.assertEqual(fake_store["messages"][2]["agent_mode"], "client")

    def test_webhook_downloads_media_before_calling_ai_core(self):
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {"phone_number_id": "phone-1"},
                                "messages": [
                                    {
                                        "id": "wamid-4",
                                        "from": "59170000002",
                                        "type": "image",
                                        "image": {
                                            "id": "media-1",
                                            "mime_type": "image/jpeg",
                                            "caption": "Mira esto",
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                }
            ]
        }
        fake_store = {
            "whatsapp_accounts": [
                {
                    "id": "wa-1",
                    "tenant_id": "tenant-1",
                    "phone_number_id": "phone-1",
                    "status": "connected",
                    "access_token_encrypted": "encrypted",
                }
            ],
            "bot_configs": [
                {
                    "tenant_id": "tenant-1",
                    "admin_phones": [],
                    "bot_enabled": True,
                    "ai_model": "claude-test",
                }
            ],
            "messages": [],
        }
        fake_supabase = FakeSupabase(fake_store)

        # Archivo real en disco: así el test puede probar que el adjunto llega al
        # agente Y que después se borra. Con un path inventado, el borrado sería
        # un no-op indistinguible de no borrar nada.
        tmp_dir = tempfile.mkdtemp()
        media_path = os.path.join(tmp_dir, "media-1.jpg")
        with open(media_path, "wb") as fh:
            fh.write(b"jpeg-bytes")
        self.addCleanup(shutil.rmtree, tmp_dir, True)

        # `local_path` se lee acá y no después de la request: el turno se lleva
        # el adjunto al terminar, así que para entonces la clave ya no está.
        seen_paths = []

        async def _respond(**kwargs):
            seen_paths.extend(item.get("local_path") for item in kwargs["media"])
            return _turn("Veo la imagen")

        ai_core_response = AsyncMock(side_effect=_respond)
        download_media = AsyncMock(return_value={
            "path": media_path,
            "mime_type": "image/jpeg",
            "size": 123,
        })

        with (
            patch("app.whatsapp.webhook.get_supabase", return_value=fake_supabase),
            patch("app.routers.webhook.verify_webhook_signature", return_value=True),
            patch("app.routers.webhook.settings.BOT_ENABLED", "http://ai-core"),
            patch("app.whatsapp.turn.ai_respond", ai_core_response),
            patch("app.whatsapp.turn.decrypt_token", return_value="token"),
            patch("app.whatsapp.meta.download_media_to_path", download_media),
            patch("app.whatsapp.meta.send_whatsapp_message", AsyncMock(return_value="out-3")),
        ):
            response = self.client.post(
                "/webhook/whatsapp",
                content=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(fake_store["messages"][0]["media"][0]["id"], "media-1")
        download_media.assert_awaited_once()
        self.assertEqual(ai_core_response.await_args.kwargs["content"], "Mira esto")
        self.assertEqual(seen_paths, [media_path])
        # El adjunto se borra al terminar el turno: sin esto, cada nota de voz y
        # cada foto que entra queda en /tmp para siempre.
        self.assertFalse(os.path.exists(media_path))

    def test_webhook_feeds_a_button_tap_back_to_the_agent(self):
        """Un tap que se descarta es peor que no tener botones: el cliente toca y no pasa nada."""
        payload = {
            "entry": [{"changes": [{"value": {
                "metadata": {"phone_number_id": "phone-1"},
                "messages": [{
                    "id": "wamid-tap",
                    "from": "59170000002",
                    "type": "interactive",
                    "interactive": {
                        "type": "button_reply",
                        "button_reply": {"id": "choice:cash", "title": "Efectivo"},
                    },
                }],
            }}]}]
        }
        fake_store = self._connected_store()
        ai_core_response = AsyncMock(return_value=_turn("Perfecto, efectivo"))

        response = self._post_webhook(payload, FakeSupabase(fake_store), ai_core_response)

        self.assertEqual(response.status_code, 200)
        # El dashboard guarda lo que el cliente vio, no el id interno.
        self.assertEqual(fake_store["messages"][0]["content"], "Efectivo")
        self.assertEqual(fake_store["messages"][0]["message_type"], "interactive")
        # El agente recibe el tap como tal, con el prefijo `choice:` ya sacado.
        reply = ai_core_response.await_args.kwargs["interactive_reply"]
        self.assertEqual((reply.id, reply.value, reply.title), ("choice:cash", "cash", "Efectivo"))

    def test_webhook_delivers_a_queued_channel_action(self):
        payload = {
            "entry": [{"changes": [{"value": {
                "metadata": {"phone_number_id": "phone-1"},
                "messages": [{
                    "id": "wamid-img",
                    "from": "59170000002",
                    "type": "text",
                    "text": {"body": "cómo es la remera?"},
                }],
            }}]}]
        }
        fake_store = self._connected_store()
        ai_core_response = AsyncMock(return_value=_turn(
            "Esta es la remera azul",
            actions=[SendImageAction(image_url="https://cdn/p1.webp")],
        ))
        send_image_message = AsyncMock(return_value="out-img")

        response = self._post_webhook(
            payload,
            FakeSupabase(fake_store),
            ai_core_response,
            **{"app.whatsapp.meta.send_whatsapp_image_message": send_image_message},
        )

        self.assertEqual(response.status_code, 200)
        # Una sola foto absorbe el texto como caption: un mensaje, no dos.
        send_image_message.assert_awaited_once()
        self.assertEqual(send_image_message.await_args.args[3], "https://cdn/p1.webp")
        self.assertEqual(send_image_message.await_args.args[4], "Esta es la remera azul")
        outbound = [m for m in fake_store["messages"] if m["direction"] == "outbound"]
        self.assertEqual(len(outbound), 1)
        self.assertEqual(outbound[0]["message_type"], "image")
        self.assertEqual(outbound[0]["wa_message_id"], "out-img")

    def test_webhook_logs_whatsapp_status_updates(self):
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {"phone_number_id": "phone-asistpro"},
                                "statuses": [
                                    {
                                        "id": "wamid-out-text",
                                        "status": "failed",
                                        "recipient_id": "59170000009",
                                        "errors": [{"code": 131047, "message": "Re-engagement message"}],
                                    }
                                ],
                            }
                        }
                    ]
                }
            ]
        }

        with (
            patch("app.whatsapp.webhook.get_supabase", return_value=FakeSupabase({})),
            patch("app.routers.webhook.verify_webhook_signature", return_value=True),
            self.assertLogs("doppel.whatsapp.webhook", level="INFO") as logs,
        ):
            response = self.client.post(
                "/webhook/whatsapp",
                content=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )

        self.assertEqual(response.status_code, 200)
        log_output = "\n".join(logs.output)
        self.assertIn("WhatsApp status phone_id=phone-asistpro", log_output)
        self.assertIn("message_id=wamid-out-text", log_output)
        self.assertIn("status=failed", log_output)
        self.assertIn("error_code=131047", log_output)

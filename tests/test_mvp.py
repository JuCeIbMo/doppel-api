import os

os.environ.setdefault("META_APP_ID", "test-app-id")
os.environ.setdefault("META_APP_SECRET", "test-app-secret")
os.environ.setdefault("META_VERIFY_TOKEN", "test-verify-token")
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "x.eyJyb2xlIjogInNlcnZpY2Vfcm9sZSJ9.y")
os.environ.setdefault("ENCRYPTION_KEY", "oZRrOD525wcQ0CJveupENSX1tDwKfP6e1XrDGn9P1Kw=")
os.environ.setdefault("AGNO_DB_URL", "postgresql+psycopg://ai:ai@localhost:5532/ai")

import hashlib
import hmac
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.dependencies import get_current_tenant, get_current_user
from app.main import app
from app.security import verify_webhook_signature


class FakeResult:
    def __init__(self, data=None, count=None):
        self.data = data
        self.count = count


class FakeTableQuery:
    def __init__(self, table_name, store):
        self.table_name = table_name
        self.store = store
        self.filters = []
        self._insert_payload = None
        self._update_payload = None
        self._delete_mode = False
        self._single = False
        self._count = None
        self._range = None
        self._limit = None

    def select(self, _fields, count=None):
        self._count = count
        return self

    def eq(self, key, value):
        self.filters.append(lambda row, key=key, value=value: row.get(key) == value)
        return self

    def gte(self, key, value):
        self.filters.append(lambda row, key=key, value=value: row.get(key) >= value)
        return self

    def order(self, key, desc=False):
        self._order_key = key
        self._order_desc = desc
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def limit(self, limit):
        self._limit = limit
        return self

    def single(self):
        self._single = True
        return self

    def maybe_single(self):
        self._single = True
        return self

    def insert(self, payload):
        self._insert_payload = payload
        return self

    def upsert(self, payload, on_conflict=None):
        self._insert_payload = payload
        self._upsert = on_conflict
        return self

    def update(self, payload):
        self._update_payload = payload
        return self

    def delete(self):
        self._delete_mode = True
        return self

    def execute(self):
        table = self.store.setdefault(self.table_name, [])

        if self._insert_payload is not None:
            payload = dict(self._insert_payload)
            payload.setdefault("id", f"{self.table_name}-{len(table) + 1}")
            payload.setdefault("created_at", f"9999-12-31T23:59:{len(table) + 1:02d}Z")
            table.append(payload)
            return FakeResult([payload])

        rows = [row for row in table if all(check(row) for check in self.filters)]

        if self._update_payload is not None:
            updated = []
            for row in rows:
                row.update(self._update_payload)
                updated.append(dict(row))
            return FakeResult(updated)

        if self._delete_mode:
            self.store[self.table_name] = [row for row in table if row not in rows]
            return FakeResult(rows)

        if hasattr(self, "_order_key"):
            rows = sorted(rows, key=lambda item: item.get(self._order_key, ""), reverse=self._order_desc)

        if self._range is not None:
            start, end = self._range
            rows = rows[start : end + 1]

        if self._limit is not None:
            rows = rows[: self._limit]

        count = len(rows) if self._count == "exact" else None
        if self._single:
            return FakeResult(rows[0] if rows else None, count=count)
        return FakeResult(rows, count=count)


class FakeSupabase:
    def __init__(self, store=None):
        self.store = store or {}

    def table(self, name):
        return FakeTableQuery(name, self.store)


class StrictFilteredMutation:
    """Supabase-like filtered mutation builder: execute/eq only, no select()."""

    def __init__(self, query):
        self.query = query

    def eq(self, key, value):
        self.query.eq(key, value)
        return self

    def execute(self):
        return self.query.execute()


class StrictMutationQuery(FakeTableQuery):
    """Fake the production builder shape after update().eq(...)."""

    def update(self, payload):
        super().update(payload)
        return self

    def eq(self, key, value):
        super().eq(key, value)
        if self._update_payload is not None:
            return StrictFilteredMutation(self)
        return self


class StrictSupabase(FakeSupabase):
    def table(self, name):
        return StrictMutationQuery(name, self.store)


class MVPApiTests(unittest.TestCase):
    def setUp(self):
        app.dependency_overrides.clear()
        app.state.http_client = object()
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.client.close()

    def test_refresh_token_endpoint_returns_new_session(self):
        fake_session = SimpleNamespace(access_token="new-access", refresh_token="new-refresh", expires_in=3600)
        fake_auth = SimpleNamespace(refresh_session=lambda token: SimpleNamespace(session=fake_session))
        fake_supabase = SimpleNamespace(auth=fake_auth)

        with patch("app.routers.auth.get_supabase_auth", return_value=fake_supabase):
            response = self.client.post("/auth/token/refresh", json={"refresh_token": "refresh-token"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["access_token"], "new-access")

    def test_oauth_exchange_returns_success_payload(self):
        fake_store = {"tenants": [], "whatsapp_accounts": [], "bot_configs": []}
        fake_supabase = FakeSupabase(fake_store)
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="user-1", email="owner@doppel.lat")

        with (
            patch("app.routers.oauth.get_supabase", return_value=fake_supabase),
            patch("app.routers.oauth.meta_api.exchange_code_for_token", return_value="meta-token"),
            patch("app.routers.oauth.meta_api.get_waba_details", return_value={"name": "Cafe Doppel"}),
            patch("app.routers.oauth.meta_api.register_phone_number", return_value=None),
            patch("app.routers.oauth.meta_api.subscribe_app_to_waba", return_value=None),
            patch("app.routers.oauth.encrypt_token", return_value="encrypted"),
        ):
            response = self.client.post(
                "/oauth/exchange",
                json={
                    "code": "auth-code",
                    "waba_id": "waba-1",
                    "phone_number_id": "phone-1",
                    "is_coexistence": False,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["business_name"], "Cafe Doppel")
        self.assertTrue(payload["requires_manager_setup"])
        self.assertEqual(fake_store["bot_configs"][0]["bot_enabled"], False)

    def test_admin_phone_setup_enables_bot_when_manager_exists(self):
        fake_store = {
            "tenants": [{"id": "tenant-1"}],
            "bot_configs": [{"id": "cfg-1", "tenant_id": "tenant-1", "admin_phones": [], "bot_enabled": False}],
        }
        fake_supabase = FakeSupabase(fake_store)
        app.dependency_overrides[get_current_tenant] = lambda: fake_store["tenants"][0]

        with patch("app.routers.dashboard.get_supabase", return_value=fake_supabase):
            response = self.client.put("/me/admin-phones", json={"phones": ["+591 700-00001"]})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["phones"], ["59170000001"])
        self.assertEqual(fake_store["bot_configs"][0]["bot_enabled"], True)

    def test_admin_phone_setup_works_with_supabase_filtered_update_builder(self):
        fake_store = {
            "tenants": [{"id": "tenant-1"}],
            "bot_configs": [{"id": "cfg-1", "tenant_id": "tenant-1", "admin_phones": [], "bot_enabled": False}],
        }
        fake_supabase = StrictSupabase(fake_store)
        app.dependency_overrides[get_current_tenant] = lambda: fake_store["tenants"][0]
        client = TestClient(app, raise_server_exceptions=False)

        try:
            with patch("app.routers.dashboard.get_supabase", return_value=fake_supabase):
                response = client.put("/me/admin-phones", json={"phones": ["+591 700-00001"]})
        finally:
            client.close()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["phones"], ["59170000001"])
        self.assertEqual(fake_store["bot_configs"][0]["bot_enabled"], True)

    def test_bot_config_update_works_with_supabase_filtered_update_builder(self):
        fake_store = {
            "tenants": [{"id": "tenant-1"}],
            "bot_configs": [
                {
                    "id": "cfg-1",
                    "tenant_id": "tenant-1",
                    "system_prompt": "old",
                    "welcome_message": "hola",
                    "language": "es",
                    "ai_model": "claude-test",
                    "bot_enabled": False,
                }
            ],
        }
        fake_supabase = StrictSupabase(fake_store)
        app.dependency_overrides[get_current_tenant] = lambda: fake_store["tenants"][0]
        client = TestClient(app, raise_server_exceptions=False)

        try:
            with patch("app.routers.dashboard.get_supabase", return_value=fake_supabase):
                response = client.put(
                    "/me/bot-config",
                    json={
                        "welcome_message": "bienvenido",
                        "ai_model": "claude-sonnet-4-20250514",
                    },
                )
        finally:
            client.close()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["welcome_message"], "bienvenido")
        self.assertEqual(fake_store["bot_configs"][0]["ai_model"], "claude-test")

    def test_dashboard_messages_and_delete_account(self):
        fake_store = {
            "tenants": [{"id": "tenant-1", "business_name": "Cafe Doppel", "email": "owner@doppel.lat", "plan": "free", "status": "active"}],
            "messages": [
                {
                    "id": "msg-1",
                    "tenant_id": "tenant-1",
                    "user_phone": "59170000001",
                    "direction": "inbound",
                    "content": "Hola",
                    "message_type": "text",
                    "created_at": "2026-04-21T00:00:00Z",
                }
            ],
        }
        fake_supabase = FakeSupabase(fake_store)
        app.dependency_overrides[get_current_tenant] = lambda: fake_store["tenants"][0]

        with patch("app.routers.dashboard.get_supabase", return_value=fake_supabase):
            messages_response = self.client.get("/me/messages?limit=20&offset=0")
            delete_response = self.client.delete("/me/account")

        self.assertEqual(messages_response.status_code, 200)
        self.assertEqual(messages_response.json()["total"], 1)
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(fake_store["tenants"], [])

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
            patch("app.routers.webhook.get_supabase", return_value=fake_supabase),
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
            patch("app.routers.webhook.get_supabase", return_value=fake_supabase),
            patch("app.routers.webhook.verify_webhook_signature", return_value=True),
            self.assertLogs("doppel.webhook", level="INFO") as logs,
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
        ai_core_response = AsyncMock(return_value="Listo")

        with (
            patch("app.routers.webhook.get_supabase", return_value=fake_supabase),
            patch("app.routers.webhook.verify_webhook_signature", return_value=True),
            patch("app.routers.webhook.settings.AI_CORE_URL", "http://ai-core"),
            patch("app.routers.webhook.ai_respond", ai_core_response),
            patch("app.routers.webhook.decrypt_token", return_value="token"),
            patch("app.routers.webhook.meta_api.send_whatsapp_message", AsyncMock(return_value="out-1")),
        ):
            response = self.client.post(
                "/webhook/whatsapp",
                content=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )

        self.assertEqual(response.status_code, 200)
        ai_core_response.assert_awaited_once()
        self.assertEqual(ai_core_response.await_args.kwargs["mode"], "manager")
        self.assertEqual(ai_core_response.await_args.kwargs["model"], "claude-test")
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
        ai_core_response = AsyncMock(return_value="Cuesta 10")

        with (
            patch("app.routers.webhook.get_supabase", return_value=fake_supabase),
            patch("app.routers.webhook.verify_webhook_signature", return_value=True),
            patch("app.routers.webhook.settings.AI_CORE_URL", "http://ai-core"),
            patch("app.routers.webhook.ai_respond", ai_core_response),
            patch("app.routers.webhook.decrypt_token", return_value="token"),
            patch("app.routers.webhook.meta_api.send_whatsapp_message", AsyncMock(return_value="out-2")),
        ):
            response = self.client.post(
                "/webhook/whatsapp",
                content=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )

        self.assertEqual(response.status_code, 200)
        ai_core_response.assert_awaited_once()
        self.assertEqual(ai_core_response.await_args.kwargs["mode"], "client")
        self.assertEqual(ai_core_response.await_args.kwargs["system_prompt"], "Eres el bot cliente")
        # El historial ahora lo administra Agno (en su Postgres) vía session_id;
        # el API ya no envía la conversación. Supabase solo registra mensajes.
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
        ai_core_response = AsyncMock(return_value="Veo la imagen")
        download_media = AsyncMock(return_value={
            "path": "C:/tmp/media-1.jpg",
            "mime_type": "image/jpeg",
            "size": 123,
        })

        with (
            patch("app.routers.webhook.get_supabase", return_value=fake_supabase),
            patch("app.routers.webhook.verify_webhook_signature", return_value=True),
            patch("app.routers.webhook.settings.AI_CORE_URL", "http://ai-core"),
            patch("app.routers.webhook.ai_respond", ai_core_response),
            patch("app.routers.webhook.decrypt_token", return_value="token"),
            patch("app.routers.webhook.meta_api.download_media_to_path", download_media),
            patch("app.routers.webhook.meta_api.send_whatsapp_message", AsyncMock(return_value="out-3")),
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
        media_arg = ai_core_response.await_args.kwargs["media"]
        self.assertEqual([item["local_path"] for item in media_arg], ["C:/tmp/media-1.jpg"])

    def test_webhook_routes_configured_phone_number_to_asistpro_n8n(self):
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {"phone_number_id": "phone-asistpro"},
                                "messages": [
                                    {"id": "wamid-asistpro-1", "from": "59170000009", "type": "text", "text": {"body": "Hola Asistpro"}}
                                ],
                            }
                        }
                    ]
                }
            ]
        }
        raw_body = json.dumps(payload).encode()
        fake_store = {"messages": []}
        fake_supabase = FakeSupabase(fake_store)
        response_from_n8n = SimpleNamespace(raise_for_status=lambda: None)
        http_client = SimpleNamespace(post=AsyncMock(return_value=response_from_n8n))
        app.state.http_client = http_client

        with (
            patch("app.routers.webhook.get_supabase", return_value=fake_supabase),
            patch("app.routers.webhook.verify_webhook_signature", return_value=True),
            patch("app.routers.webhook.settings.ASISTPRO_PHONE_NUMBER_IDS", ["phone-asistpro"], create=True),
            patch("app.routers.webhook.settings.ASISTPRO_N8N_WEBHOOK_URL", "https://n8n.example/webhook", create=True),
            patch("app.routers.webhook.settings.ASISTPRO_WEBHOOK_SECRET", "shared-secret", create=True),
            patch("app.routers.webhook.ai_respond", AsyncMock(return_value="")) as ai_core_response,
        ):
            response = self.client.post(
                "/webhook/whatsapp",
                content=raw_body,
                headers={"Content-Type": "application/json"},
            )

        self.assertEqual(response.status_code, 200)
        http_client.post.assert_awaited_once()
        self.assertEqual(http_client.post.await_args.args[0], "https://n8n.example/webhook")
        forwarded = http_client.post.await_args.kwargs["json"]
        self.assertEqual(forwarded["app"], "asistpro")
        self.assertEqual(forwarded["phone_number_id"], "phone-asistpro")
        self.assertEqual(forwarded["from"], "59170000009")
        self.assertEqual(forwarded["text"], "Hola Asistpro")
        self.assertEqual(http_client.post.await_args.kwargs["headers"]["X-Asistpro-Webhook-Secret"], "shared-secret")
        self.assertEqual(fake_store["messages"], [])
        ai_core_response.assert_not_awaited()

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
            patch("app.routers.webhook.get_supabase", return_value=FakeSupabase({})),
            patch("app.routers.webhook.verify_webhook_signature", return_value=True),
            self.assertLogs("doppel.webhook", level="INFO") as logs,
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

    def test_disconnect_whatsapp_soft_deletes_and_unsubscribes_last_waba(self):
        fake_store = {
            "tenants": [{"id": "tenant-1"}],
            "whatsapp_accounts": [
                {
                    "id": "wa-1",
                    "tenant_id": "tenant-1",
                    "waba_id": "waba-1",
                    "phone_number_id": "phone-1",
                    "status": "connected",
                    "webhook_active": True,
                    "access_token_encrypted": "encrypted-1",
                }
            ],
            "bot_configs": [{"tenant_id": "tenant-1", "bot_enabled": True}],
        }
        fake_supabase = FakeSupabase(fake_store)
        app.dependency_overrides[get_current_tenant] = lambda: fake_store["tenants"][0]

        with (
            patch("app.routers.dashboard.get_supabase", return_value=fake_supabase),
            patch("app.routers.dashboard.decrypt_token", return_value="meta-token"),
            patch("app.routers.dashboard.meta_api.unsubscribe_app_from_waba", AsyncMock(return_value=None)) as unsubscribe,
        ):
            response = self.client.delete("/me/whatsapp")

        self.assertEqual(response.status_code, 200)
        unsubscribe.assert_awaited_once()
        self.assertEqual(unsubscribe.await_args.args[1], "waba-1")
        self.assertEqual(unsubscribe.await_args.args[2], "meta-token")
        account = fake_store["whatsapp_accounts"][0]
        self.assertEqual(account["status"], "disconnected")
        self.assertEqual(account["webhook_active"], False)
        self.assertEqual(account["access_token_encrypted"], "")
        self.assertIsNotNone(account.get("deleted_at"))
        datetime.fromisoformat(account["deleted_at"].replace("Z", "+00:00"))
        self.assertEqual(fake_store["bot_configs"][0]["bot_enabled"], False)

    def test_disconnect_whatsapp_skips_unsubscribe_when_waba_has_other_active_numbers(self):
        fake_store = {
            "tenants": [{"id": "tenant-1"}],
            "whatsapp_accounts": [
                {
                    "id": "wa-1",
                    "tenant_id": "tenant-1",
                    "waba_id": "waba-1",
                    "phone_number_id": "phone-1",
                    "status": "connected",
                    "webhook_active": True,
                    "access_token_encrypted": "encrypted-1",
                },
                {
                    "id": "wa-2",
                    "tenant_id": "tenant-2",
                    "waba_id": "waba-1",
                    "phone_number_id": "phone-2",
                    "status": "connected",
                    "webhook_active": True,
                    "access_token_encrypted": "encrypted-2",
                },
            ],
            "bot_configs": [{"tenant_id": "tenant-1", "bot_enabled": True}],
        }
        fake_supabase = FakeSupabase(fake_store)
        app.dependency_overrides[get_current_tenant] = lambda: fake_store["tenants"][0]

        with (
            patch("app.routers.dashboard.get_supabase", return_value=fake_supabase),
            patch("app.routers.dashboard.decrypt_token", return_value="meta-token"),
            patch("app.routers.dashboard.meta_api.unsubscribe_app_from_waba", AsyncMock(return_value=None)) as unsubscribe,
        ):
            response = self.client.delete("/me/whatsapp")

        self.assertEqual(response.status_code, 200)
        unsubscribe.assert_not_awaited()

    def test_internal_tools_list_returns_mode_specific_definitions(self):
        fake_supabase = FakeSupabase({})

        with (
            patch("app.routers.internal.get_supabase", return_value=fake_supabase),
            patch("app.dependencies.settings.DOPPEL_INTERNAL_API_TOKEN", "internal-secret"),
        ):
            response = self.client.get(
                "/internal/ai/tools",
                params={"tenant_id": "tenant-1", "mode": "client"},
                headers={"Authorization": "Bearer internal-secret"},
            )

        self.assertEqual(response.status_code, 200)
        names = {tool["name"] for tool in response.json()["tools"]}
        self.assertEqual(names, {"lookup_business_info", "list_available_products"})

    def test_internal_tools_execute_runs_requested_tool(self):
        fake_store = {
            "products": [
                {
                    "id": "prod-1",
                    "tenant_id": "tenant-1",
                    "name": "Pizza",
                    "description": "Grande",
                    "price": 50,
                    "available": True,
                }
            ]
        }
        fake_supabase = FakeSupabase(fake_store)

        with (
            patch("app.routers.internal.get_supabase", return_value=fake_supabase),
            patch("app.dependencies.settings.DOPPEL_INTERNAL_API_TOKEN", "internal-secret"),
        ):
            response = self.client.post(
                "/internal/ai/tools/execute",
                headers={"Authorization": "Bearer internal-secret"},
                json={
                    "tenant_id": "tenant-1",
                    "mode": "client",
                    "tool_name": "list_available_products",
                    "arguments": {},
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["result"][0]["name"], "Pizza")

    def test_all_tool_input_schemas_are_json_serializable(self):
        """Every tool's input_schema must be pure JSON (no leftover Schema
        objects), otherwise GET /internal/ai/tools returns 500 when ai-core
        fetches the registry. Guards against the name-collision trap in
        tool_parameters_schema (e.g. a property literally named 'description')."""
        from app.services.tool_runtime import build_tool_registry

        fake_supabase = MagicMock()
        for mode in ("client", "manager"):
            registry = build_tool_registry(
                supabase=fake_supabase, tenant_id="tenant-1", mode=mode
            )
            for tool in registry._tools.values():
                try:
                    json.dumps(tool.parameters)
                except TypeError as exc:
                    self.fail(
                        f"Tool '{tool.name}' ({mode}) input_schema not "
                        f"JSON-serializable: {exc}"
                    )

    def test_asistpro_send_text_endpoint_uses_connected_meta_account(self):
        fake_store = {
            "whatsapp_accounts": [
                {
                    "id": "wa-1",
                    "phone_number_id": "phone-asistpro",
                    "display_phone": "59170000008",
                    "status": "connected",
                    "access_token_encrypted": "encrypted",
                }
            ]
        }
        fake_supabase = FakeSupabase(fake_store)
        send_message = AsyncMock(return_value="wamid-out-text")

        with (
            patch("app.routers.asistpro.get_supabase", return_value=fake_supabase),
            patch("app.routers.asistpro.decrypt_token", return_value="meta-token"),
            patch("app.routers.asistpro.meta_api.send_whatsapp_message", send_message),
            patch("app.routers.asistpro.settings.ASISTPRO_SEND_API_KEY", "send-secret", create=True),
        ):
            response = self.client.post(
                "/integrations/asistpro/whatsapp/messages/text",
                headers={"Authorization": "Bearer send-secret"},
                json={"to": "59170000009", "text": "Respuesta"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message_id"], "wamid-out-text")
        self.assertEqual(response.json()["phone_number_id"], "phone-asistpro")
        self.assertEqual(response.json()["to"], "59170000009")
        send_message.assert_awaited_once()
        self.assertEqual(send_message.await_args.args[1], "phone-asistpro")
        self.assertEqual(send_message.await_args.args[2], "59170000009")
        self.assertEqual(send_message.await_args.args[3], "Respuesta")
        self.assertEqual(send_message.await_args.args[4], "meta-token")

    def test_asistpro_send_text_endpoint_rejects_self_send(self):
        fake_store = {
            "whatsapp_accounts": [
                {
                    "id": "wa-1",
                    "phone_number_id": "phone-asistpro",
                    "display_phone": "591720906023",
                    "status": "connected",
                    "access_token_encrypted": "encrypted",
                }
            ]
        }
        fake_supabase = FakeSupabase(fake_store)
        send_message = AsyncMock(return_value="wamid-out-text")

        with (
            patch("app.routers.asistpro.get_supabase", return_value=fake_supabase),
            patch("app.routers.asistpro.meta_api.send_whatsapp_message", send_message),
            patch("app.routers.asistpro.settings.ASISTPRO_SEND_API_KEY", "send-secret", create=True),
        ):
            response = self.client.post(
                "/integrations/asistpro/whatsapp/messages/text",
                headers={"Authorization": "Bearer send-secret"},
                json={"to": "591720906023", "text": "Respuesta"},
            )

        self.assertEqual(response.status_code, 422)
        self.assertIn("itself", response.json()["detail"])
        send_message.assert_not_awaited()

    def test_asistpro_send_image_endpoint_sends_image_link(self):
        fake_store = {
            "whatsapp_accounts": [
                {
                    "id": "wa-1",
                    "phone_number_id": "phone-asistpro",
                    "display_phone": "59170000008",
                    "status": "connected",
                    "access_token_encrypted": "encrypted",
                }
            ]
        }
        fake_supabase = FakeSupabase(fake_store)
        send_image = AsyncMock(return_value="wamid-out-image")

        with (
            patch("app.routers.asistpro.get_supabase", return_value=fake_supabase),
            patch("app.routers.asistpro.decrypt_token", return_value="meta-token"),
            patch("app.routers.asistpro.meta_api.send_whatsapp_image_message", send_image),
            patch("app.routers.asistpro.settings.ASISTPRO_SEND_API_KEY", "send-secret", create=True),
        ):
            response = self.client.post(
                "/integrations/asistpro/whatsapp/messages/image",
                headers={"Authorization": "Bearer send-secret"},
                json={
                    "to": "59170000009",
                    "image_url": "https://cdn.example/image.jpg",
                    "caption": "Imagen",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message_id"], "wamid-out-image")
        self.assertEqual(response.json()["phone_number_id"], "phone-asistpro")
        self.assertEqual(response.json()["to"], "59170000009")
        send_image.assert_awaited_once()
        self.assertEqual(send_image.await_args.args[1], "phone-asistpro")
        self.assertEqual(send_image.await_args.args[2], "59170000009")
        self.assertEqual(send_image.await_args.args[3], "https://cdn.example/image.jpg")
        self.assertEqual(send_image.await_args.args[4], "Imagen")

    def test_asistpro_send_endpoint_rejects_invalid_api_key(self):
        with patch("app.routers.asistpro.settings.ASISTPRO_SEND_API_KEY", "send-secret", create=True):
            response = self.client.post(
                "/integrations/asistpro/whatsapp/messages/text",
                headers={"Authorization": "Bearer wrong"},
                json={"to": "59170000009", "text": "Respuesta"},
            )

        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()

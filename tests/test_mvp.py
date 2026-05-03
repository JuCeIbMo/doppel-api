import hashlib
import hmac
import json
import unittest
from unittest.mock import AsyncMock
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
        nanobot_response = AsyncMock(return_value={"reply": "Listo", "mode": "manager"})

        with (
            patch("app.routers.webhook.get_supabase", return_value=fake_supabase),
            patch("app.routers.webhook.verify_webhook_signature", return_value=True),
            patch("app.routers.webhook.settings.NANOBOT_RUNTIME_URL", "http://nanobot"),
            patch("app.routers.webhook.nanobot_runtime.respond", nanobot_response),
            patch("app.routers.webhook.decrypt_token", return_value="token"),
            patch("app.routers.webhook.meta_api.send_whatsapp_message", AsyncMock(return_value="out-1")),
        ):
            response = self.client.post(
                "/webhook/whatsapp",
                content=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )

        self.assertEqual(response.status_code, 200)
        nanobot_response.assert_awaited_once()
        self.assertEqual(nanobot_response.await_args.kwargs["mode"], "manager")
        self.assertNotIn("model", nanobot_response.await_args.kwargs)
        self.assertEqual(fake_store["messages"][0]["agent_mode"], "manager")
        self.assertEqual(fake_store["messages"][1]["content"], "Listo")

    def test_webhook_routes_regular_phone_to_nanobot_client(self):
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
                    "ai_model": "claude-test",
                }
            ],
            "messages": [],
        }
        fake_supabase = FakeSupabase(fake_store)
        nanobot_response = AsyncMock(return_value={"reply": "Cuesta 10", "mode": "client"})

        with (
            patch("app.routers.webhook.get_supabase", return_value=fake_supabase),
            patch("app.routers.webhook.verify_webhook_signature", return_value=True),
            patch("app.routers.webhook.settings.NANOBOT_RUNTIME_URL", "http://nanobot"),
            patch("app.routers.webhook.nanobot_runtime.respond", nanobot_response),
            patch("app.routers.webhook.decrypt_token", return_value="token"),
            patch("app.routers.webhook.meta_api.send_whatsapp_message", AsyncMock(return_value="out-2")),
        ):
            response = self.client.post(
                "/webhook/whatsapp",
                content=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )

        self.assertEqual(response.status_code, 200)
        nanobot_response.assert_awaited_once()
        self.assertEqual(nanobot_response.await_args.kwargs["mode"], "client")
        self.assertEqual(fake_store["messages"][0]["agent_mode"], "client")

    def test_webhook_downloads_media_before_calling_nanobot(self):
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
        nanobot_response = AsyncMock(return_value={"reply": "Veo la imagen", "mode": "client"})
        download_media = AsyncMock(return_value={
            "path": "C:/tmp/media-1.jpg",
            "mime_type": "image/jpeg",
            "size": 123,
        })

        with (
            patch("app.routers.webhook.get_supabase", return_value=fake_supabase),
            patch("app.routers.webhook.verify_webhook_signature", return_value=True),
            patch("app.routers.webhook.settings.NANOBOT_RUNTIME_URL", "http://nanobot"),
            patch("app.routers.webhook.nanobot_runtime.respond", nanobot_response),
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
        self.assertEqual(nanobot_response.await_args.kwargs["content"], "Mira esto")
        self.assertEqual(nanobot_response.await_args.kwargs["media_paths"], ["C:/tmp/media-1.jpg"])


if __name__ == "__main__":
    unittest.main()

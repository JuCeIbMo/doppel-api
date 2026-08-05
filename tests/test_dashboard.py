from datetime import datetime
from unittest.mock import AsyncMock
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.dependencies import get_current_tenant
from app.main import app
from tests.api_case import ApiTestCase
from tests.fakes import FakeSupabase, StrictSupabase


class DashboardApiTests(ApiTestCase):
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
            patch("app.routers.dashboard.meta.unsubscribe_app_from_waba", AsyncMock(return_value=None)) as unsubscribe,
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
            patch("app.routers.dashboard.meta.unsubscribe_app_from_waba", AsyncMock(return_value=None)) as unsubscribe,
        ):
            response = self.client.delete("/me/whatsapp")

        self.assertEqual(response.status_code, 200)
        unsubscribe.assert_not_awaited()

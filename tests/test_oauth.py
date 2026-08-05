from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.dependencies import get_current_tenant, get_current_user
from app.main import app
from tests.api_case import ApiTestCase
from tests.fakes import FakeSupabase, StrictSupabase


class OAuthApiTests(ApiTestCase):
    def test_oauth_exchange_returns_success_payload(self):
        fake_store = {"tenants": [], "whatsapp_accounts": [], "bot_configs": []}
        fake_supabase = FakeSupabase(fake_store)
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="user-1", email="owner@doppel.lat")

        with (
            patch("app.whatsapp.onboarding.get_supabase", return_value=fake_supabase),
            patch("app.whatsapp.onboarding.meta.exchange_code_for_token", return_value="meta-token"),
            patch("app.whatsapp.onboarding.meta.get_waba_details", return_value={"name": "Cafe Doppel"}),
            patch("app.whatsapp.onboarding.meta.register_phone_number", return_value=None),
            patch("app.whatsapp.onboarding.meta.subscribe_app_to_waba", return_value=None),
            patch("app.whatsapp.onboarding.encrypt_token", return_value="encrypted"),
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

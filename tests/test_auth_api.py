from types import SimpleNamespace
from unittest.mock import patch

from tests.api_case import ApiTestCase


class AuthApiTests(ApiTestCase):
    def test_refresh_token_endpoint_returns_new_session(self):
        fake_session = SimpleNamespace(access_token="new-access", refresh_token="new-refresh", expires_in=3600)
        async def _refresh_session(token):
            return SimpleNamespace(session=fake_session)

        fake_auth = SimpleNamespace(refresh_session=_refresh_session)
        fake_supabase = SimpleNamespace(auth=fake_auth)

        with patch("app.routers.auth.get_supabase_auth", return_value=fake_supabase):
            response = self.client.post("/auth/token/refresh", json={"refresh_token": "refresh-token"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["access_token"], "new-access")

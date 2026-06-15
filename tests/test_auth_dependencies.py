"""Auth semantics for protected endpoints.

A *missing* Authorization header must yield 401 (Unauthorized), not FastAPI's
default 403 for HTTPBearer. The front-end refresh-and-retry flow only triggers on
401, so returning 403 for an absent token leaves recoverable sessions stuck.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_missing_bearer_returns_401_not_403():
    r = client.get("/erp/inventory/low-stock")
    assert r.status_code == 401


def test_malformed_authorization_scheme_returns_401():
    r = client.get(
        "/erp/inventory/low-stock",
        headers={"Authorization": "Basic abc123"},
    )
    assert r.status_code == 401

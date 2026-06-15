from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware import install_observability


def _app():
    app = FastAPI()
    install_observability(app)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    return TestClient(app)


def test_generates_request_id_header():
    r = _app().get("/ping")
    assert r.status_code == 200
    assert r.headers.get("X-Request-ID")


def test_echoes_inbound_request_id():
    r = _app().get("/ping", headers={"X-Request-ID": "abc-123"})
    assert r.headers["X-Request-ID"] == "abc-123"


def test_security_headers_present():
    h = _app().get("/ping").headers
    assert h["X-Content-Type-Options"] == "nosniff"
    assert h["X-Frame-Options"] == "DENY"
    assert h["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "max-age=" in h["Strict-Transport-Security"]

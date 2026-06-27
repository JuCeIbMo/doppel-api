import os

os.environ.setdefault("META_APP_ID", "test-app-id")
os.environ.setdefault("META_APP_SECRET", "test-app-secret")
os.environ.setdefault("META_VERIFY_TOKEN", "test-verify-token")
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "x.eyJyb2xlIjogInNlcnZpY2Vfcm9sZSJ9.y")
os.environ.setdefault("ENCRYPTION_KEY", "oZRrOD525wcQ0CJveupENSX1tDwKfP6e1XrDGn9P1Kw=")

from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from app.ai import history


def _req(text):
    return ModelRequest(parts=[UserPromptPart(content=text)])


def _resp(text):
    return ModelResponse(parts=[TextPart(content=text)])


def test_session_id_format():
    assert history.session_id_for("t1", "555") == "t1:555"


def test_load_empty_returns_empty_list():
    assert history.load("nope:000") == []


def test_append_then_load_roundtrip():
    sid = "t-roundtrip:1"
    history.append(sid, [_req("hola"), _resp("buenas")])
    loaded = history.load(sid)
    assert len(loaded) == 2
    assert isinstance(loaded[0], ModelRequest)
    assert isinstance(loaded[1], ModelResponse)


def test_append_accumulates_across_calls():
    sid = "t-accum:1"
    history.append(sid, [_req("a"), _resp("b")])
    first = len(history.load(sid))
    history.append(sid, [_req("c"), _resp("d")])
    assert len(history.load(sid)) > first

import os

os.environ.setdefault("META_APP_ID", "test-app-id")
os.environ.setdefault("META_APP_SECRET", "test-app-secret")
os.environ.setdefault("META_VERIFY_TOKEN", "test-verify-token")
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "x.eyJyb2xlIjogInNlcnZpY2Vfcm9sZSJ9.y")
os.environ.setdefault("ENCRYPTION_KEY", "oZRrOD525wcQ0CJveupENSX1tDwKfP6e1XrDGn9P1Kw=")

from pydantic_ai import BinaryContent
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from app.ai import history
from app.ai.history import _MAX_RUNS


def _req(text):
    return ModelRequest(parts=[UserPromptPart(content=text)])


def _resp(text):
    return ModelResponse(parts=[TextPart(content=text)])


def _tool_run(user_text: str, tool_name: str = "search_catalog", tool_result: str = "[]"):
    """Devuelve un run de dos mensajes: petición con tool-call + respuesta con tool-return."""
    tool_call = ModelRequest(
        parts=[
            UserPromptPart(content=user_text),
        ]
    )
    tool_response = ModelResponse(
        parts=[
            ToolCallPart(tool_name=tool_name, args="{}", tool_call_id="tc1"),
        ]
    )
    tool_return = ModelRequest(
        parts=[
            ToolReturnPart(
                tool_name=tool_name,
                content=tool_result,
                tool_call_id="tc1",
            ),
        ]
    )
    return [tool_call, tool_response, tool_return]


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
    sid = "t-accum:2"
    history.append(sid, [_req("a"), _resp("b")])
    first = len(history.load(sid))
    history.append(sid, [_req("c"), _resp("d")])
    assert len(history.load(sid)) > first


# ── FIX 3 lock-in: ventana por run, no por mensaje plano ────────────────────

def test_window_by_run_no_orphaned_tool_return():
    """Superar _MAX_RUNS nunca deja un ToolReturnPart huérfano al inicio del historial."""
    sid = "t-window:1"

    # Llenar más de _MAX_RUNS runs con pares tool-call/return.
    for i in range(_MAX_RUNS + 3):
        run = _tool_run(f"consulta {i}")
        history.append(sid, run)

    loaded = history.load(sid)

    # El primer mensaje devuelto debe ser un ModelRequest con UserPromptPart,
    # nunca un ToolReturnPart huérfano.
    assert loaded, "load no debe devolver lista vacía"
    first_msg = loaded[0]
    assert isinstance(first_msg, ModelRequest), (
        f"Primer mensaje debe ser ModelRequest, no {type(first_msg)}"
    )
    first_part = first_msg.parts[0]
    assert isinstance(first_part, UserPromptPart), (
        f"Primera parte debe ser UserPromptPart, no {type(first_part)}"
    )


def test_window_caps_at_max_runs():
    """load no devuelve más mensajes de los que caben en _MAX_RUNS runs."""
    sid = "t-cap:1"
    msgs_per_run = 2  # _req + _resp

    for i in range(_MAX_RUNS + 5):
        history.append(sid, [_req(f"q{i}"), _resp(f"r{i}")])

    loaded = history.load(sid)
    assert len(loaded) <= _MAX_RUNS * msgs_per_run


# ── FIX 2: no persistir imágenes ────────────────────────────────────────────

def test_binary_content_stripped_on_append():
    """Después de append con BinaryContent, load no devuelve ningún BinaryContent."""
    sid = "t-binary:1"

    # Construir un run con imagen en UserPromptPart
    img_part = UserPromptPart(content=["mira esta imagen", BinaryContent(data=b"\xff\xd8", media_type="image/jpeg")])
    run = [
        ModelRequest(parts=[img_part]),
        ModelResponse(parts=[TextPart(content="muy bonita")]),
    ]
    history.append(sid, run)
    loaded = history.load(sid)

    assert loaded, "load no debe devolver lista vacía"
    for msg in loaded:
        if isinstance(msg, ModelRequest):
            for part in msg.parts:
                if isinstance(part, UserPromptPart) and isinstance(part.content, list):
                    for item in part.content:
                        assert not isinstance(item, BinaryContent), (
                            "BinaryContent no debe persistirse en el historial"
                        )


def test_binary_content_replaced_by_marker():
    """El BinaryContent se sustituye por el marcador de texto '[imagen adjunta]'."""
    sid = "t-binary-marker:1"

    img_part = UserPromptPart(content=["texto previo", BinaryContent(data=b"\xff", media_type="image/png")])
    history.append(sid, [ModelRequest(parts=[img_part])])
    loaded = history.load(sid)

    assert loaded
    req = loaded[0]
    assert isinstance(req, ModelRequest)
    user_part = req.parts[0]
    assert isinstance(user_part, UserPromptPart)
    assert isinstance(user_part.content, list)
    assert "[imagen adjunta]" in user_part.content
    assert "texto previo" in user_part.content

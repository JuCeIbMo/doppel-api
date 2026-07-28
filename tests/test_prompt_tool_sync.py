"""Every tool a prompt names must actually be bound to that agent.

The port from Agno left the prompts describing a tool set that no longer
existed. The admin prompt documented five tools (`get_dashboard_summary`,
`get_stock`, `get_top_products`, `create_sale`, `adjust_stock`) — none of them
were registered anywhere. The public catalog and closer prompts named Spanish
tools from an even earlier iteration (`consultar_stock`, `registrar_pedido`,
`enviar_link_pago`, `escalar_a_humano`, `list_available_products`, ...).

Nothing catches this at runtime: the model is simply told it can do things it
cannot, and improvises. Prompts are not covered by imports or type checks, so
they drift silently — this test is the only thing tying them to reality.

app.config instantiates Settings() at import time, requiring these env vars.
Set safe test defaults before import.
"""

import os

os.environ.setdefault("META_APP_ID", "test-app-id")
os.environ.setdefault("META_APP_SECRET", "test-app-secret")
os.environ.setdefault("META_VERIFY_TOKEN", "test-verify-token")
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "x.eyJyb2xlIjogInNlcnZpY2Vfcm9sZSJ9.y")
os.environ.setdefault("ENCRYPTION_KEY", "oZRrOD525wcQ0CJveupENSX1tDwKfP6e1XrDGn9P1Kw=")
os.environ.setdefault("CHAT_DB_URL", "postgresql://ai:ai@localhost:5532/chat")

import re
from pathlib import Path

import pytest

from app.ai_core.agents.admin_agent import _ADMIN_DEFAULT_TOOLS

PROMPTS_DIR = Path("app/ai_core/prompts")

# Business tools each public specialist binds, mirroring app/ai_core/subagents/.
_PUBLIC_BUSINESS_TOOLS = {
    "greeter": set(),
    "catalog": {
        "search_catalog", "check_stock",
        "send_image", "send_reply_buttons", "send_list_message",
    },
    "objection": {"search_catalog", "check_stock", "send_image", "send_reply_buttons"},
    "closer": {
        "search_catalog", "check_stock", "create_order", "human_handoff",
        "send_image", "send_reply_buttons",
    },
}

# A prompt may legitimately mention these in backticks without calling them:
# tool arguments and response fields, not tools.
_NOT_TOOLS = {"product_id", "query", "quantity", "date_from", "date_to", "reason"}


def _tools_named_in(text: str) -> set[str]:
    """Backticked snake_case identifiers — how every prompt writes a tool name."""
    named = set(re.findall(r"`([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\(?\)?`", text))
    return {n for n in named if n not in _NOT_TOOLS}


def _available_to(agent: str) -> set[str]:
    if agent == "admin_agent":
        return {tool.name for tool in _ADMIN_DEFAULT_TOOLS}
    # Specialists bind business tools only: there is no handoff between them.
    return _PUBLIC_BUSINESS_TOOLS[agent]


def _prompt_cases():
    for path in sorted(PROMPTS_DIR.rglob("*.md")):
        yield pytest.param(path, id=f"{path.parent.name}/{path.stem}")


@pytest.mark.parametrize("path", _prompt_cases())
def test_prompt_only_names_tools_the_agent_has(path):
    """A prompt promising a tool the agent lacks makes the model improvise."""
    agent = path.stem
    available = _available_to(agent)
    named = _tools_named_in(path.read_text(encoding="utf-8"))

    ghosts = sorted(named - available)
    assert not ghosts, (
        f"{path} names tools not bound to '{agent}': {ghosts}. "
        f"Available: {sorted(available)}"
    )


def test_public_business_tool_map_matches_the_subagent_modules():
    """This test's own map must not drift from the real builders."""
    for agent, expected in _PUBLIC_BUSINESS_TOOLS.items():
        source = Path(f"app/ai_core/subagents/{agent}.py").read_text(encoding="utf-8")
        # Tolera las dos formas del import: una línea, o parentizado en varias.
        # Con un patrón de una sola línea, agregar tools hasta partir el import
        # dejaba `imported` vacío y el test fallaba con un mensaje engañoso.
        match = re.search(
            r"from app\.ai_core\.tools import (?:\(([^)]+)\)|([^\n(]+))", source
        )
        raw = (match.group(1) or match.group(2)) if match else ""
        imported = {name.strip() for name in raw.split(",") if name.strip()}
        assert imported == expected, (
            f"{agent}.py imports {sorted(imported)} but the test map expects "
            f"{sorted(expected)} — update the map."
        )


def test_every_public_tool_is_bound_somewhere():
    """A tool in the allow-list but bound to no agent is a dead code path."""
    from app.ai_core.config.tenant import ALL_PUBLIC_TOOLS

    bound = set().union(*_PUBLIC_BUSINESS_TOOLS.values())
    unbound = sorted(set(ALL_PUBLIC_TOOLS) - bound)
    assert not unbound, f"public tools reachable by no agent: {unbound}"


def test_every_admin_tool_is_bound():
    from app.ai_core.config.tenant import ALL_ADMIN_TOOLS

    bound = {tool.name for tool in _ADMIN_DEFAULT_TOOLS}
    unbound = sorted(set(ALL_ADMIN_TOOLS) - bound)
    assert not unbound, f"admin tools reachable by no agent: {unbound}"

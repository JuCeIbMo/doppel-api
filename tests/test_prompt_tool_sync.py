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

Shared test environment is loaded before collection by `tests/conftest.py`.
"""

import re
from pathlib import Path

import pytest

from app.ai_core.admin.tools import ADMIN_TOOLS
from app.ai_core.config.tenant import HARNESS_TOOLS
from app.ai_core.public.specialists import PUBLIC_SPECIALIST_TOOLS

PUBLIC_PROMPTS_DIR = Path("app/ai_core/public/prompts")
ADMIN_PROMPT = Path("app/ai_core/admin/prompt.md")

# Business tools each public specialist binds, mirroring public/specialists.py.
_PUBLIC_BUSINESS_TOOLS = {
    agent: {tool.name for tool in tools}
    for agent, tools in PUBLIC_SPECIALIST_TOOLS.items()
}

# A prompt may legitimately mention these in backticks without calling them:
# tool arguments and response fields, not tools.
_NOT_TOOLS = {
    "product_id", "query", "quantity", "date_from", "date_to", "reason", "has_more",
    "has_image",
}

def _tools_named_in(text: str) -> set[str]:
    """Backticked snake_case identifiers — how every prompt writes a tool name."""
    named = set(re.findall(r"`([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\(?\)?`", text))
    return {n for n in named if n not in _NOT_TOOLS}

def _available_to(agent: str) -> set[str]:
    if agent == "admin_agent":
        # El admin corre sobre deepagents, así que además de `ADMIN_TOOLS` tiene las
        # inyectadas por el harness (`write_todos` y las de filesystem). El prompt las
        # nombra al explicar planificación y memoria.
        # `tests/test_admin_deep_agent.py` verifica que el agente real registre
        # exactamente esta unión.
        return {tool.name for tool in ADMIN_TOOLS} | set(HARNESS_TOOLS)
    # Specialists bind business tools only: there is no handoff between them.
    return _PUBLIC_BUSINESS_TOOLS[agent]

def _prompt_cases():
    for path in sorted(PUBLIC_PROMPTS_DIR.glob("*.md")):
        yield pytest.param(path, path.stem, id=f"public/{path.stem}")
    yield pytest.param(ADMIN_PROMPT, "admin_agent", id="admin/admin_agent")

@pytest.mark.parametrize(("path", "agent"), _prompt_cases())
def test_prompt_only_names_tools_the_agent_has(path, agent):
    """A prompt promising a tool the agent lacks makes the model improvise."""
    available = _available_to(agent)
    named = _tools_named_in(path.read_text(encoding="utf-8"))

    ghosts = sorted(named - available)
    assert not ghosts, (
        f"{path} names tools not bound to '{agent}': {ghosts}. "
        f"Available: {sorted(available)}"
    )

def test_every_public_tool_is_bound_somewhere():
    """A tool in the allow-list but bound to no agent is a dead code path."""
    from app.ai_core.config.tenant import ALL_PUBLIC_TOOLS

    bound = set().union(*_PUBLIC_BUSINESS_TOOLS.values())
    unbound = sorted(set(ALL_PUBLIC_TOOLS) - bound)
    assert not unbound, f"public tools reachable by no agent: {unbound}"

def test_every_admin_tool_is_bound():
    from app.ai_core.config.tenant import ALL_ADMIN_TOOLS

    bound = {tool.name for tool in ADMIN_TOOLS}
    unbound = sorted(set(ALL_ADMIN_TOOLS) - bound)
    assert not unbound, f"admin tools reachable by no agent: {unbound}"

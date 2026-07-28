import logging
from pathlib import Path

from app.ai_core.config.tenant import TenantConfig

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def load_prompt(tenant: TenantConfig, role: str, name: str) -> str:
    """Load a subagent's prompt. Static, bundled in the repo (shared across
    tenants) — reuses doppel-api's existing sales skills content rather than
    a per-tenant file, see `app/ai_core/prompts/`."""
    path = _PROMPTS_DIR / role / f"{name}.md"
    template = path.read_text(encoding="utf-8")
    agent_config = tenant.public_agent if role == "public" else tenant.admin_agent
    result = template.replace("{{ business_name }}", tenant.business_name)
    if hasattr(agent_config, "tone"):
        result = result.replace("{{ tone }}", agent_config.tone)
    return result


def allowed_tools_for(tenant: TenantConfig, role: str, default_tools: list) -> list:
    """Intersect a specialist's default tools with the tenant's allow-list.

    The tenant config is authoritative: a tool missing from ``allowed_tools``
    is never bound to the agent, so tenants can toggle capabilities per role.
    """
    allowed = set(
        tenant.public_agent.allowed_tools
        if role == "public"
        else tenant.admin_agent.allowed_tools
    )
    selected = [t for t in default_tools if t.name in allowed]
    dropped = [t.name for t in default_tools if t.name not in allowed]
    if dropped:
        logger.warning(
            "Tenant %s (%s): tools not in allow-list, skipping: %s",
            tenant.tenant_id,
            role,
            dropped,
        )
    return selected


# Ceiling on tool calls within a single specialist invocation. Nothing else
# bounds the ReAct loop: the graph's recursion_limit only counts supersteps, so
# a model that batches parallel calls can do far more work than it suggests.
#
# A legitimate turn needs 1-3 calls, and the closer's worst case
# (search_catalog + check_stock + create_order) is 3, so 5 leaves
# room without letting a loop run. It also has to stay small enough that the
# graph's recursion limit does not run out first: a specialist alternates
# model -> tools and ends with one more model call to answer, so a run of N
# tool calls costs 2N + 1 supersteps, and 11 fits inside GRAPH_RECURSION_LIMIT.
# That ordering matters -- this cap blocks tools and lets the model still
# reply, while the recursion limit raises and leaves the customer with nothing.
MAX_TOOL_CALLS_PER_RUN = 5

# Tighter cap on the one tool that loops in practice: a model that finds no
# match rephrases the same search (bebidas, bebida, drink, refresco, ...)
# instead of concluding the catalog has none. Only this tool gets blocked;
# check_stock and create_order stay available.
MAX_CATALOG_SEARCHES_PER_RUN = 3


def specialist_middleware(tenant: TenantConfig, role: str) -> list:
    """Standard middleware stack for every specialist/admin agent.

    Order: the call limits are outermost so they bound the run regardless of
    what the inner middleware do; the error boundary then catches failures from
    the rest, and the guardrail rejects disallowed tools before the context
    injector runs.

    Both limits use ``exit_behavior="continue"``: hitting one blocks further
    tool calls but lets the model keep going, so it answers from what it
    already has instead of ending the turn without a reply. ``run_limit`` is
    per invocation -- ``thread_limit`` persists through the checkpoint and
    would eventually leave a long-running conversation permanently toolless.
    """
    from langchain.agents.middleware import ToolCallLimitMiddleware

    from app.ai_core.agents.context_middleware import (
        build_message_window,
        build_tool_context,
    )
    from app.ai_core.agents.guardrails import (
        build_tool_error_boundary,
        build_tool_guardrail,
    )

    return [
        ToolCallLimitMiddleware(
            run_limit=MAX_TOOL_CALLS_PER_RUN,
            exit_behavior="continue",
        ),
        ToolCallLimitMiddleware(
            tool_name="search_catalog",
            run_limit=MAX_CATALOG_SEARCHES_PER_RUN,
            exit_behavior="continue",
        ),
        build_tool_error_boundary(),
        build_tool_guardrail(tenant, role),
        build_tool_context(tenant, role),
        build_message_window(),
    ]

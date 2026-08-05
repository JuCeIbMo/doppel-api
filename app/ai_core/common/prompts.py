import logging
from pathlib import Path

from app.ai_core.config.tenant import TenantConfig

logger = logging.getLogger(__name__)
_AI_CORE_DIR = Path(__file__).parent.parent


def load_prompt(tenant: TenantConfig, role: str, name: str) -> str:
    """Load a static prompt owned by the corresponding agent role."""
    path = (
        _AI_CORE_DIR / "public" / "prompts" / f"{name}.md"
        if role == "public"
        else _AI_CORE_DIR / "admin" / "prompt.md"
    )
    template = path.read_text(encoding="utf-8")
    agent_config = tenant.public_agent if role == "public" else tenant.admin_agent
    result = template.replace("{{ business_name }}", tenant.business_name)
    if hasattr(agent_config, "tone"):
        result = result.replace("{{ tone }}", agent_config.tone)
    return result


def allowed_tools_for(tenant: TenantConfig, role: str, default_tools: list) -> list:
    """Intersect an agent's tools with its tenant-level allow-list."""
    allowed = set(
        tenant.public_agent.allowed_tools
        if role == "public"
        else tenant.admin_agent.allowed_tools
    )
    selected = [tool for tool in default_tools if tool.name in allowed]
    dropped = [tool.name for tool in default_tools if tool.name not in allowed]
    if dropped:
        logger.warning(
            "Tenant %s (%s): tools not in allow-list, skipping: %s",
            tenant.tenant_id,
            role,
            dropped,
        )
    return selected

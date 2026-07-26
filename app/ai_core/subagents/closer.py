from langchain.agents import create_agent
from langchain.tools import BaseTool

from app.ai_core.agents.llm import build_chat_model
from app.ai_core.config.tenant import TenantConfig
from app.ai_core.subagents._base import (
    allowed_tools_for,
    load_prompt,
    specialist_middleware,
)
from app.ai_core.tools import (
    check_stock,
    create_order,
    human_handoff,
    search_catalog,
    send_image,
    send_reply_buttons,
)


def build_closer(tenant: TenantConfig, handoff_tools: list[BaseTool] | None = None):
    handoffs = handoff_tools or []
    # `human_handoff` is the closer's escape hatch: payment problems and
    # non-standard requests surface here, at the moment of committing. It is in
    # ALL_PUBLIC_TOOLS and its prompt documents the escalation, but it was bound
    # to no agent at all, so the path was dead.
    business_tools = allowed_tools_for(
        tenant,
        "public",
        [
            search_catalog, check_stock, create_order, human_handoff,
            send_image, send_reply_buttons,
        ],
    )
    return create_agent(
        name="closer",
        model=build_chat_model("public", temperature=0.3),
        system_prompt=load_prompt(tenant, "public", "closer"),
        tools=[*business_tools, *handoffs],
        middleware=specialist_middleware(
            tenant,
            "public",
            {tool.name for tool in handoffs},
        ),
    )

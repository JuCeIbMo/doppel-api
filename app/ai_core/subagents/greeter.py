from langchain.agents import create_agent
from langchain.tools import BaseTool

from app.ai_core.agents.llm import build_chat_model
from app.ai_core.config.tenant import TenantConfig
from app.ai_core.subagents._base import load_prompt, specialist_middleware


def build_greeter(tenant: TenantConfig, handoff_tools: list[BaseTool] | None = None):
    handoffs = handoff_tools or []
    return create_agent(
        name="greeter",
        model=build_chat_model("public", temperature=0.7),
        system_prompt=load_prompt(tenant, "public", "greeter"),
        tools=handoffs,
        middleware=specialist_middleware(
            tenant,
            "public",
            {tool.name for tool in handoffs},
        ),
    )

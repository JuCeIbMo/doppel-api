from langchain.agents import create_agent

from app.ai_core.agents.llm import build_chat_model
from app.ai_core.config.tenant import TenantConfig
from app.ai_core.subagents._base import load_prompt, specialist_middleware


def build_greeter(tenant: TenantConfig):
    return create_agent(
        name="greeter",
        model=build_chat_model("public", temperature=0.7),
        system_prompt=load_prompt(tenant, "public", "greeter"),
        tools=[],
        middleware=specialist_middleware(tenant, "public"),
    )

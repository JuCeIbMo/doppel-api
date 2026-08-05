"""Builders for the four specialists selected by the public router."""

from langchain.agents import create_agent

from app.ai_core.common.llm import build_chat_model
from app.ai_core.common.middleware import specialist_middleware
from app.ai_core.common.prompts import allowed_tools_for, load_prompt
from app.ai_core.config.tenant import TenantConfig
from app.ai_core.tools import (
    check_stock,
    create_order,
    human_handoff,
    search_catalog,
    send_image,
    send_list_message,
    send_reply_buttons,
)

PUBLIC_SPECIALIST_TOOLS = {
    "greeter": [],
    "catalog": [
        search_catalog,
        check_stock,
        send_image,
        send_reply_buttons,
        send_list_message,
    ],
    "objection": [search_catalog, check_stock, send_image, send_reply_buttons],
    "closer": [
        search_catalog,
        check_stock,
        create_order,
        human_handoff,
        send_image,
        send_reply_buttons,
    ],
}

_TEMPERATURES = {"greeter": 0.7, "catalog": 0.7, "objection": 0.7, "closer": 0.3}


def _build_specialist(tenant: TenantConfig, name: str):
    tools = allowed_tools_for(tenant, "public", PUBLIC_SPECIALIST_TOOLS[name])
    return create_agent(
        name=name,
        model=build_chat_model("public", temperature=_TEMPERATURES[name]),
        system_prompt=load_prompt(tenant, "public", name),
        tools=tools,
        middleware=specialist_middleware(tenant, "public"),
    )


def build_greeter(tenant: TenantConfig):
    return _build_specialist(tenant, "greeter")


def build_catalog(tenant: TenantConfig):
    return _build_specialist(tenant, "catalog")


def build_objection(tenant: TenantConfig):
    return _build_specialist(tenant, "objection")


def build_closer(tenant: TenantConfig):
    return _build_specialist(tenant, "closer")

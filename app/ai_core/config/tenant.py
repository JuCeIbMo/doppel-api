"""Tenant config for the LangChain agent core, backed by Supabase (not YAML).

`TenantConfig` keeps the same shape the ported agent code expects
(business_name, public_agent/admin_agent with allowed_tools/allowed_subagents),
but it's built from doppel-api's real tables instead of a per-tenant YAML file:
`business_info` for the display name, `bot_configs` for admin phones + toggles.

There is no `allowed_tools`/`allowed_subagents` concept in doppel-api's schema yet,
so both default to "everything enabled" unless a tenant's `bot_configs` row
overrides them (see `config/loader.py`).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ALL_PUBLIC_SUBAGENTS = ("greeter", "catalog", "objection", "closer")
ALL_PUBLIC_TOOLS = ("search_catalog", "check_stock", "create_order", "human_handoff")
ALL_ADMIN_TOOLS = (
    "get_sales_report", "add_product", "update_stock", "update_config",
    "search_catalog", "check_stock",
)


class PublicAgentConfig(BaseModel):
    tone: str = "friendly"
    welcome_message: str = "Hi! How can I help you?"
    allowed_tools: list[str] = Field(default_factory=lambda: list(ALL_PUBLIC_TOOLS))
    allowed_subagents: list[str] = Field(default_factory=lambda: list(ALL_PUBLIC_SUBAGENTS))


class AdminAgentConfig(BaseModel):
    allowed_numbers: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=lambda: list(ALL_ADMIN_TOOLS))
    allowed_subagents: list[str] = Field(default_factory=list)


class TenantConfig(BaseModel):
    tenant_id: str
    business_name: str
    public_agent: PublicAgentConfig
    admin_agent: AdminAgentConfig


def resolve_role(sender_phone: str, tenant: TenantConfig) -> Literal["public", "admin"]:
    """Authority comes from the sender's phone number (Meta-verified), never from text."""
    return "admin" if sender_phone in tenant.admin_agent.allowed_numbers else "public"

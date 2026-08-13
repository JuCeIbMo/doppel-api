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
ALL_PUBLIC_TOOLS = (
    "search_catalog", "check_stock", "create_order", "human_handoff",
    # Tools de canal: no consultan ni escriben nada, encolan un mensaje de
    # WhatsApp (foto, botones, lista). Un tenant las puede apagar por acá si
    # prefiere que su bot hable sólo en texto.
    "send_image", "send_reply_buttons", "send_list_message",
)
ALL_ADMIN_TOOLS = (
    "get_config", "search_catalog", "check_stock",
    "get_business_overview", "get_sales_analysis", "get_inventory_alerts",
    "find_customers", "get_customer_details", "list_recent_sales", "get_sale_details",
    "get_cash_summary", "propose_stock_adjustment",
    "propose_product_change", "propose_transaction", "execute_confirmed_action",
    "propose_sale_cancellation", "create_product_from_photo",
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

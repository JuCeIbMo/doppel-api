"""Builds a TenantConfig by reading business_info + bot_configs from Supabase.

Replaces the ported project's `tenants/{id}/config.yaml` file: doppel-api already
has this data per tenant in real tables, so there's no YAML to maintain per business.
"""

from __future__ import annotations

from app.ai_core.config.tenant import AdminAgentConfig, PublicAgentConfig, TenantConfig
from app.services.supabase_client import get_supabase


def load_tenant_config(tenant_id: str) -> TenantConfig:
    supabase = get_supabase()

    biz = (
        supabase.table("business_info").select("name")
        .eq("tenant_id", tenant_id).limit(1).execute()
    ).data
    business_name = biz[0]["name"] if biz and biz[0].get("name") else "este negocio"

    cfg = (
        supabase.table("bot_configs").select("admin_phones")
        .eq("tenant_id", tenant_id).single().execute()
    ).data or {}
    admin_phones = cfg.get("admin_phones") or []

    return TenantConfig(
        tenant_id=tenant_id,
        business_name=business_name,
        public_agent=PublicAgentConfig(),
        admin_agent=AdminAgentConfig(allowed_numbers=admin_phones),
    )

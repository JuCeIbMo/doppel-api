from __future__ import annotations

from supabase import Client

from app.services.client_tools import build_client_registry
from app.services.erp.tools import register_erp_tools
from app.services.manager_tools import build_manager_registry


def build_tool_registry(*, supabase: Client, tenant_id: str, mode: str):
    if mode == "manager":
        registry = build_manager_registry(supabase, tenant_id)
        register_erp_tools(registry, supabase, tenant_id)  # owner's admin assistant operates the ERP
        return registry
    return build_client_registry(supabase, tenant_id)

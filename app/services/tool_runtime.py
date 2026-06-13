from __future__ import annotations

from supabase import Client

from app.services.client_tools import build_client_registry
from app.services.manager_tools import build_manager_registry


def build_tool_registry(*, supabase: Client, tenant_id: str, mode: str):
    if mode == "manager":
        return build_manager_registry(supabase, tenant_id)
    return build_client_registry(supabase, tenant_id)

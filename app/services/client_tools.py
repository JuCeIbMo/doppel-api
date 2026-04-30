"""Tools del client agent — read-only sobre business_info y products.

El client agent atiende a clientes finales por WhatsApp; estas tools le permiten
responder preguntas factuales sobre el negocio (horarios, direccion, formas de pago)
y listar el catalogo de productos disponibles. Sin escrituras.
"""

from __future__ import annotations

from typing import Any

from supabase import Client

from app.services.agent_core import Tool, ToolRegistry, tool_parameters, tool_parameters_schema


class _ClientTool(Tool):
    """Common base: holds the supabase client + tenant_id binding."""

    def __init__(self, supabase: Client, tenant_id: str):
        self.supabase = supabase
        self.tenant_id = tenant_id


@tool_parameters(tool_parameters_schema())
class LookupBusinessInfoTool(_ClientTool):
    @property
    def name(self) -> str:
        return "lookup_business_info"

    @property
    def description(self) -> str:
        return (
            "Look up the business profile (name, description, hours, address, "
            "payment methods). Use this to answer client questions about the business."
        )

    @property
    def read_only(self) -> bool:
        return True

    async def execute(self, **_: Any) -> Any:
        result = (
            self.supabase.table("business_info")
            .select("name, description, hours, address, payment_methods")
            .eq("tenant_id", self.tenant_id)
            .limit(1)
            .execute()
        )
        if result.data:
            return result.data[0]
        return {
            "name": "",
            "description": "",
            "hours": "",
            "address": "",
            "payment_methods": "",
        }


@tool_parameters(tool_parameters_schema())
class ListAvailableProductsTool(_ClientTool):
    @property
    def name(self) -> str:
        return "list_available_products"

    @property
    def description(self) -> str:
        return (
            "List products currently available for clients. Returns name, "
            "description and price ordered alphabetically. Unavailable products are hidden."
        )

    @property
    def read_only(self) -> bool:
        return True

    async def execute(self, **_: Any) -> Any:
        result = (
            self.supabase.table("products")
            .select("name, description, price, available")
            .eq("tenant_id", self.tenant_id)
            .eq("available", True)
            .order("name", desc=False)
            .execute()
        )
        return result.data or []


def build_client_registry(supabase: Client, tenant_id: str) -> ToolRegistry:
    """Return a ToolRegistry pre-loaded with the read-only client toolkit for this tenant."""
    registry = ToolRegistry()
    registry.register(LookupBusinessInfoTool(supabase, tenant_id))
    registry.register(ListAvailableProductsTool(supabase, tenant_id))
    return registry

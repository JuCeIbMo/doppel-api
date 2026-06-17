"""Tools read-only del client agent. Cada función cierra sobre supabase + tenant_id.
Agno genera el JSON schema desde la firma y el docstring."""

from __future__ import annotations

from typing import Callable

from supabase import Client


def build_client_tools(supabase: Client, tenant_id: str) -> list[Callable]:
    async def lookup_business_info() -> dict:
        """Consulta el perfil del negocio (nombre, descripción, horarios, dirección,
        métodos de pago). Úsalo para responder preguntas del cliente sobre el negocio."""
        result = (
            supabase.table("business_info")
            .select("name, description, hours, address, payment_methods")
            .eq("tenant_id", tenant_id)
            .limit(1)
            .execute()
        )
        if result.data:
            return result.data[0]
        return {"name": "", "description": "", "hours": "", "address": "", "payment_methods": ""}

    async def list_available_products() -> list:
        """Lista los productos disponibles para clientes (nombre, descripción, precio),
        ordenados alfabéticamente. Los no disponibles quedan ocultos."""
        result = (
            supabase.table("products")
            .select("name, description, price, available")
            .eq("tenant_id", tenant_id)
            .eq("available", True)
            .order("name", desc=False)
            .execute()
        )
        return result.data or []

    async def count_available_products() -> dict:
        """Devuelve el total de productos disponibles del negocio.
        Úsalo cuando el cliente pregunte cuántos productos hay en el catálogo."""
        result = (
            supabase.table("products")
            .select("id", count="exact")
            .eq("tenant_id", tenant_id)
            .eq("available", True)
            .execute()
        )
        return {"total": result.count or 0}

    return [lookup_business_info, list_available_products, count_available_products]

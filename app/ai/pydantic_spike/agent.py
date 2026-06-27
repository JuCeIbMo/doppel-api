"""Client agent del spike: equivalente Pydantic AI de `get_client_agent`.

Diferencias clave vs Agno:
- El agente se construye UNA vez a nivel de módulo (no una factory por request).
  Lo que varía por tenant (system prompt, modelo, ERPContext) viaja como `deps`
  o como override en `agent.run(...)`.
- Las tools son las mismas wrappers finos sobre `storefront`, pero leen el
  ERPContext desde `RunContext.deps` en vez de cerrar sobre él.
- Las "skills" se inyectan como texto en una instruction dinámica.
- WhatsApp interactivo (botones/listas) NO está en el spike: el pipeline ya envía
  el texto final. Reimplementarlo serían tools HTTP sobre el Graph API (pendiente).
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_ai import Agent, RunContext

from app.services import storefront
from app.services.erp.context import ERPContext
from app.ai.pydantic_spike.skills import load_skills_text

# Mismo set de skills que el client agent de Agno, menos whatsapp-interactivo
# (no hay tools que lo respalden en el spike).
_CLIENT_SKILLS = (
    "catalogo-productos",
    "sales-diagnostico",
    "sales-presentacion",
    "sales-objecion",
    "sales-cierre",
)

_SKILLS_TEXT = load_skills_text(*_CLIENT_SKILLS)


@dataclass
class ClientDeps:
    """Todo lo que las tools y las instructions necesitan en un run."""

    ctx: ERPContext
    system_prompt: str


# Sin modelo fijo: cada run pasa el del tenant (`agent.run(model=...)`), así no
# instanciamos el provider (ni exigimos su API key) en tiempo de import.
client_agent = Agent(deps_type=ClientDeps)


@client_agent.instructions
def tenant_system_prompt(ctx: RunContext[ClientDeps]) -> str:
    return ctx.deps.system_prompt


@client_agent.instructions
def skills_block(ctx: RunContext[ClientDeps]) -> str:
    return _SKILLS_TEXT


@client_agent.instructions
async def business_info_block(ctx: RunContext[ClientDeps]) -> str:
    """Inyecta info del negocio (equivale al `dependencies=` de Agno)."""
    info = await storefront.business_info(ctx.deps.ctx)
    return f"Información del negocio:\n{info}"


@client_agent.tool
async def search_catalog(ctx: RunContext[ClientDeps], query: str | None = None) -> list:
    """Busca productos disponibles del negocio. Sin `query` lista todo el catálogo;
    con `query` filtra por nombre. Devuelve [{id, name, price, in_stock, description,
    tags}]. Usá `description` y `tags` para elegir el producto que mejor matchea lo
    que pide el cliente, y el `id` para registrar la venta del producto exacto.

    Args:
        query: texto a buscar en el nombre del producto (opcional)
    """
    return await storefront.search_catalog(ctx.deps.ctx, query)


@client_agent.tool
async def register_sale(
    ctx: RunContext[ClientDeps],
    items: list,
    customer_phone: str | None = None,
    payment_method: str = "whatsapp",
) -> dict:
    """Registra una venta. Baja stock y registra el ingreso de forma atómica.
    Confirmá producto, cantidad y precio con el cliente antes de llamarla.

    Args:
        items: lista de {product_id, quantity}. Usá el product_id (campo `id`) que
            obtuviste de search_catalog; nunca lo inventes ni re-busques por nombre.
        customer_phone: teléfono para asociar la compra a un cliente (opcional)
        payment_method: cash | card | transfer | whatsapp | other
    """
    return await storefront.register_sale(
        ctx.deps.ctx, items, customer_phone=customer_phone, payment_method=payment_method
    )

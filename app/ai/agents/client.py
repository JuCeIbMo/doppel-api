"""Client agent (vendedor de cara al público) sobre Pydantic AI.

El agente se construye una vez; lo que varía por tenant (ERPContext, system_prompt,
modelo) viaja como deps o como override en `agent.run(...)`. Las tools son wrappers
finos sobre `storefront` que leen el ERPContext desde `RunContext.deps`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from pydantic_ai import Agent, RunContext

from app.services import storefront
from app.services.erp.context import ERPContext


@dataclass
class ClientDeps:
    ctx: ERPContext
    system_prompt: str


# Sin modelo fijo: cada run pasa el del tenant (`agent.run(model=...)`).
client_agent = Agent(deps_type=ClientDeps)


@client_agent.instructions
def tenant_system_prompt(ctx: RunContext[ClientDeps]) -> str:
    return ctx.deps.system_prompt


@client_agent.instructions
async def business_info_block(ctx: RunContext[ClientDeps]) -> str:
    info = await storefront.business_info(ctx.deps.ctx)
    return f"Información del negocio:\n{json.dumps(info, ensure_ascii=False)}"


@client_agent.tool
async def search_catalog(ctx: RunContext[ClientDeps], query: str | None = None) -> list[dict]:
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
    items: list[dict],
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

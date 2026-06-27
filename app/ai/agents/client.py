"""Agente vendedor (cara al público) sobre Pydantic AI — con progressive disclosure.

Idea central de Pydantic AI:
  - `Agent(deps_type=..., instructions=...)`  → define el agente y su prompt base
  - `@client_agent.tool` + `ctx.deps`         → tool que recibe el dato inyectado (el tenant)
  - `client_agent.run(prompt, model=MODEL, deps=ctx)`  → un turno de conversación

PROGRESSIVE DISCLOSURE (capabilities on demand)
-----------------------------------------------
No todas las tools tienen que estar visibles siempre. Una `Capability` agrupa
instrucciones + tools que viajan juntas, y con `defer_loading=True` el modelo NO
las ve al principio: solo ve su `id` y `description` en un catálogo. Cuando hacen
falta, el modelo llama a la tool `load_capability('<id>')` (la agrega el framework
solo) y recién ahí aparecen sus instrucciones y tools.

Acá lo aplicamos así:
  - `search_catalog`  → SIEMPRE visible (el vendedor busca en casi todos los turnos).
  - `cerrar-venta`    → DEFERIDA: `register_sale` + las reglas de confirmación solo
                        aparecen cuando el cliente decide comprar y el modelo la carga.

El modelo (`MODEL`) va como constante y se pasa en el `run` —no fijo en `Agent(...)`—
para no exigir `ANTHROPIC_API_KEY` al *importar* el módulo (rompería los tests).
"""

from __future__ import annotations

from pydantic_ai import Agent, RunContext
from pydantic_ai.capabilities import Capability

from app.services import storefront
from app.services.erp.context import ERPContext

# Modelo del vendedor. Único lugar donde se decide con qué LLM atiende.
MODEL = "anthropic:claude-sonnet-4-6"

INSTRUCTIONS = """\
Sos un vendedor por WhatsApp, simpático y directo. Atendés en español rioplatense.

Cómo trabajás:
- Para saber qué hay y a qué precio, usá `search_catalog`. No inventes productos
  ni precios: si no sabés, buscá.
- Cuando el cliente decida comprar, cargá la capacidad `cerrar-venta` para obtener
  la herramienta de registrar la venta y las reglas de confirmación.
- Sé breve. Una o dos frases por mensaje, como en un chat real.
"""

# --- Capacidad deferida: cerrar la venta -----------------------------------
# Sus instrucciones y su tool NO están visibles al inicio. El modelo las trae con
# load_capability('cerrar-venta') cuando el cliente confirma la compra.
cerrar_venta = Capability[ERPContext](
    id="cerrar-venta",
    description="Para cuando el cliente confirma que quiere comprar y hay que registrar la venta.",
    instructions=(
        "Antes de registrar la venta confirmá con el cliente el producto, la cantidad "
        "y el precio. Usá el `id` exacto que te dio search_catalog; nunca lo inventes."
    ),
    defer_loading=True,
)


@cerrar_venta.tool
async def register_sale(
    ctx: RunContext[ERPContext],
    items: list[dict],
    customer_phone: str | None = None,
    payment_method: str = "whatsapp",
) -> dict:
    """Registra una venta. Baja stock y registra el ingreso de forma atómica.

    Args:
        items: lista de {product_id, quantity}. Usá el `id` que te dio search_catalog.
        customer_phone: teléfono para asociar la compra a un cliente (opcional)
        payment_method: cash | card | transfer | whatsapp | other
    """
    return await storefront.register_sale(
        ctx.deps, items, customer_phone=customer_phone, payment_method=payment_method
    )


# --- Agente -----------------------------------------------------------------
# Instrucciones base fijas + la capacidad deferida. El único dato dinámico es el
# tenant (deps); el modelo (MODEL) se pasa en cada run.
client_agent = Agent(
    deps_type=ERPContext,
    instructions=INSTRUCTIONS,
    capabilities=[cerrar_venta],
)


@client_agent.tool
async def search_catalog(ctx: RunContext[ERPContext], query: str | None = None) -> list[dict]:
    """Busca productos del negocio. Sin `query` lista todo el catálogo; con `query`
    filtra por nombre. Devuelve [{id, name, price, in_stock, description, tags}].
    Usá `description` y `tags` para elegir el producto que mejor matchea, y el `id`
    para registrar la venta del producto exacto.

    Args:
        query: texto a buscar en el nombre del producto (opcional)
    """
    return await storefront.search_catalog(ctx.deps, query)

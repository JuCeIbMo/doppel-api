"""Tools del client agent (vendedor de cara al público). Wrappers finos sobre la
capa storefront: cada tool cierra sobre un ERPContext con actor whatsapp_bot."""

from __future__ import annotations

from typing import Callable

from app.services import storefront
from app.services.erp.context import ERPContext


def build_client_tools(ctx: ERPContext) -> list[Callable]:

    async def search_catalog(query: str | None = None) -> list:
        """Busca productos disponibles del negocio. Sin `query` lista todo el catálogo;
        con `query` filtra por nombre. Devuelve [{id, name, price, in_stock, description,
        tags}]. Usá `description` y `tags` para elegir el producto que mejor matchea lo
        que pide el cliente, y el `id` para registrar la venta del producto exacto.

        Args:
            query: texto a buscar en el nombre del producto (opcional)
        """
        return await storefront.search_catalog(ctx, query)

    async def register_sale(
        items: list, customer_phone: str | None = None, payment_method: str = "whatsapp"
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
            ctx, items, customer_phone=customer_phone, payment_method=payment_method)

    return [search_catalog, register_sale]

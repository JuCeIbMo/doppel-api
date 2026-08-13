"""High-value read tools and confirmed write tools for the owner agent.

Every tool here returns compact text (`app/ai_core/tools/render.py`), not JSON:
the admin agent talks to the owner over WhatsApp, and a raw ERP row (nulls,
uuids, microsecond timestamps) is both wasted tokens and something the model
tends to just repeat back verbatim. Reads go through `app/services/admin_view.py`
(the admin equivalent of `storefront.py`) instead of an ERP service directly —
a new read capability adds a lean function there, a `render_*` here in
`render.py`, and a thin tool that wires the two together. The confirmed-write
path (`_execute`, below) still calls the ERP services directly, same as before:
`admin_view` is a read layer, writes stay where the propose→confirm contract
already lives.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from app.ai_core.channel.actions import ReplyButton, SendButtonsAction
from app.ai_core.tools import render
from app.ai_core.tools.channel import ADMIN_CANCEL_PREFIX, ADMIN_CONFIRM_PREFIX, CHOICE_PREFIX
from app.ai_core.tools.context import InjectedCtx, ToolContext, contextual_tool
from app.ai_core.tools.models import ProductDraft
from app.models.erp_schemas import ProductCreate, ProductUpdate
from app.services import admin_view
from app.services.erp.admin_actions import AdminActionService
from app.services.erp.context import bot_context
from app.services.erp.finance import FinanceService
from app.services.erp.inventory import InventoryService
from app.services.erp.products import ProductsService
from app.services.erp.sales import SalesService


def _ctx(ctx: ToolContext):
    if ctx.role != "admin":
        raise PermissionError("admin tool requires admin role")
    return bot_context(ctx.tenant.tenant_id, actor="admin_bot")


@contextual_tool
async def get_business_overview(ctx: InjectedCtx, date_from: str | None = None,
                                date_to: str | None = None) -> str:
    """Estado general del negocio: ventas, margen, clientes nuevos, stock bajo
    mínimo y saldos de caja. Usala para "cómo va el negocio", "cómo estamos
    este mes". Sin fechas, cubre el mes en curso."""
    data = await admin_view.business_overview(_ctx(ctx), date_from, date_to)
    return render.business_overview(data)


@contextual_tool
async def get_sales_analysis(ctx: InjectedCtx, date_from: str | None = None,
                             date_to: str | None = None) -> str:
    """Productos líderes, tendencia de ventas y margen para un período. Usala
    para "qué se vendió más", "cómo viene la tendencia", "cuál deja más
    margen" — no para el estado general (para eso, get_business_overview)."""
    data = await admin_view.sales_analysis(_ctx(ctx), date_from, date_to)
    return render.sales_analysis(data)


@contextual_tool
async def get_inventory_alerts(ctx: InjectedCtx) -> str:
    """Productos en o bajo su mínimo de stock, y los movimientos de inventario
    más recientes. Usala para "qué me falta reponer", "qué se movió en
    stock"."""
    data = await admin_view.inventory_alerts(_ctx(ctx))
    return render.inventory_alerts(data)


@contextual_tool
async def find_customers(query: str, ctx: InjectedCtx) -> str:
    """Buscar clientes por nombre o teléfono. Usala antes de
    get_customer_details para conseguir el id real; nunca lo inventes."""
    data = await admin_view.find_customers(_ctx(ctx), query)
    return render.find_customers(data)


@contextual_tool
async def get_customer_details(client_id: str, ctx: InjectedCtx) -> str:
    """Datos de contacto, totales de compra y últimas ventas de un cliente, por
    el id devuelto por find_customers."""
    data = await admin_view.customer_details(_ctx(ctx), client_id)
    return render.customer_details(data)


@contextual_tool
async def list_recent_sales(ctx: InjectedCtx, date_from: str | None = None,
                            date_to: str | None = None) -> str:
    """Últimas ventas, opcionalmente acotadas a un rango de fechas ISO. Usala
    para ubicar una venta antes de get_sale_details o
    propose_sale_cancellation."""
    data = await admin_view.recent_sales(_ctx(ctx), date_from, date_to)
    return render.recent_sales(data)


@contextual_tool
async def get_sale_details(sale_id: str, ctx: InjectedCtx) -> str:
    """Detalle e ítems de una venta, por el id devuelto por list_recent_sales."""
    data = await admin_view.sale_details(_ctx(ctx), sale_id)
    return render.sale_details(data)


@contextual_tool
async def get_cash_summary(ctx: InjectedCtx, date_from: str | None = None,
                           date_to: str | None = None) -> str:
    """Cuentas de caja, ingresos/egresos netos y transacciones recientes para
    un período. Usala para "cuánto hay en caja", "cómo viene la plata"."""
    data = await admin_view.cash_summary(_ctx(ctx), date_from, date_to)
    return render.cash_summary(data)


async def _propose(ctx: ToolContext, kind: str, payload: dict, description: str) -> str:
    """Crea la acción pendiente, encola los botones Confirmar/Cancelar y
    devuelve la línea de confirmación que lee el dueño.

    `description` no lleva "¿Confirmás?" ni punto final: `_propose` los agrega
    para el cuerpo del botón y para render.propose respectivamente, así cada
    tool sólo describe el cambio."""
    action = await AdminActionService().create(
        _ctx(ctx), thread_id=ctx.thread_id, kind=kind, payload=payload, summary=description)
    if ctx.outbox is not None:
        ctx.outbox.add(SendButtonsAction(body=f"{description}. ¿Confirmás?", buttons=[
            ReplyButton(id=f"{CHOICE_PREFIX}{ADMIN_CONFIRM_PREFIX}{action['id']}", title="Confirmar"),
            ReplyButton(id=f"{CHOICE_PREFIX}{ADMIN_CANCEL_PREFIX}{action['id']}", title="Cancelar"),
        ]))
    return render.propose(description)


@contextual_tool
async def propose_stock_adjustment(product_id: str, quantity: Annotated[float, Field(ge=0)],
                                   ctx: InjectedCtx) -> str:
    """Proponer el stock real contado de un producto (cantidad final, no una
    diferencia). Manda botones de confirmación; no escribe nada todavía."""
    product = await admin_view.product_brief(_ctx(ctx), product_id)
    return await _propose(
        ctx, "stock_adjustment",
        {"product_id": product_id, "quantity": quantity, "product_name": product["name"]},
        f"Ajustar stock de {product['name']} a {render.qty(quantity)}",
    )


@contextual_tool
async def propose_product_change(action: Literal["create", "update", "deactivate"],
                                 ctx: InjectedCtx, product_id: str | None = None,
                                 draft: ProductDraft | None = None) -> str:
    """Proponer una edición básica o desactivación de producto (el alta con
    foto usa create_product_from_photo, no esta tool). Para editar o
    desactivar, primero buscá y verificá el producto con search_catalog.
    Requiere confirmación."""
    data = {k: v for k, v in (draft.model_dump() if draft else {}).items() if v is not None}
    if action == "create":
        data = ProductCreate.model_validate(data).model_dump()
        label = data.get("name")
    else:
        if not product_id:
            raise ValueError("product_id es obligatorio para editar o desactivar")
        product = await admin_view.product_brief(_ctx(ctx), product_id)
        label = data.get("name") or product["name"]
        if action == "update":
            data = ProductUpdate.model_validate(data).model_dump(exclude_unset=True)
            if not data:
                raise ValueError("Indicá al menos un campo para actualizar")
    return await _propose(
        ctx, f"product_{action}", {"product_id": product_id, "data": data, "label": label},
        f"{action.capitalize()} producto {label}",
    )


@contextual_tool
async def propose_transaction(type: Literal["income", "expense"], amount: Annotated[float, Field(gt=0)],
                              category: str, ctx: InjectedCtx, description: str | None = None,
                              cash_account_id: str | None = None, date: str | None = None) -> str:
    """Proponer un ingreso o gasto manual. Indicá monto, categoría, fecha y
    cuenta si se conoce antes de proponerlo. Requiere confirmación."""
    data = {"type": type, "amount": amount, "category": category, "description": description,
            "cash_account_id": cash_account_id, "date": date}
    return await _propose(
        ctx, "transaction", data, f"Registrar {render.label(type)} de {render.money(amount)} en {category}")


@contextual_tool
async def propose_sale_cancellation(sale_id: str, ctx: InjectedCtx) -> str:
    """Proponer la cancelación de una venta completada que ya localizaste con
    list_recent_sales o get_sale_details. Nunca propongas cancelar una venta
    que no consultaste. Requiere confirmación."""
    sale = await admin_view.sale_brief(_ctx(ctx), sale_id)
    if sale["status"] != "completed":
        raise ValueError("Sólo se pueden cancelar ventas completadas")
    return await _propose(
        ctx, "sale_cancellation", {"sale_id": sale_id, "total": sale["total"]},
        f"Cancelar venta {render.ref(sale_id)} por {render.money(sale['total'])}",
    )


@contextual_tool
async def execute_confirmed_action(action_id: str, ctx: InjectedCtx) -> str:
    """Ejecutar la acción que el dueño confirmó tocando su botón Confirmar.
    Pasá el identificador tal como aparece en el mensaje (el que sigue a
    "id:"), sin editarlo. No la llames por texto libre ni por un id viejo."""
    action_id = action_id.removeprefix(ADMIN_CONFIRM_PREFIX)
    if ctx.confirmed_action_id != action_id:
        raise PermissionError("Esta acción sólo puede ejecutarse desde su botón Confirmar")

    service = AdminActionService()
    action = await service.claim(_ctx(ctx), thread_id=ctx.thread_id, action_id=action_id)
    payload, kind = action["payload"], action["kind"]
    duplicate = action.get("status") == "executed"

    if not duplicate:
        erp = _ctx(ctx)
        result = await _execute(kind, payload, erp, action_id)
        await service.complete(action_id, result)

    return render.execute_confirmed_action(kind, payload, duplicate=duplicate)


async def _execute(kind: str, payload: dict, erp, action_id: str) -> dict:
    if kind == "stock_adjustment":
        return await InventoryService().adjust(
            erp, product_id=payload["product_id"],
            new_quantity=payload["quantity"], delta=None,
            note="Ajuste vía agente admin confirmado")
    if kind == "product_create":
        return await ProductsService().create(erp, {**payload["data"], "admin_action_id": action_id})
    if kind == "product_update":
        return await ProductsService().update(erp, payload["product_id"], payload["data"])
    if kind == "product_deactivate":
        return await ProductsService().soft_delete(erp, payload["product_id"])
    if kind == "transaction":
        return await FinanceService().create_transaction(erp, {**payload, "admin_action_id": action_id})
    if kind == "sale_cancellation":
        return await SalesService().cancel_sale(erp, payload["sale_id"])
    raise ValueError(f"Tipo de acción no soportado: {kind}")

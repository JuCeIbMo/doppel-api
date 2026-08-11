"""High-value read tools and confirmed write tools for the owner agent."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from app.ai_core.channel.actions import ReplyButton, SendButtonsAction
from app.ai_core.tools.context import ToolContext, contextual_tool
from app.models.erp_schemas import ProductCreate, ProductUpdate
from app.services.erp.admin_actions import AdminActionService
from app.services.erp.clients import ClientsService
from app.services.erp.context import bot_context
from app.services.erp.finance import FinanceService
from app.services.erp.inventory import InventoryService
from app.services.erp.products import ProductsService
from app.services.erp.reports import ReportsService, default_period
from app.services.erp.sales import SalesService


def _ctx(ctx: ToolContext):
    if ctx.role != "admin":
        raise PermissionError("admin tool requires admin role")
    return bot_context(ctx.tenant.tenant_id, actor="admin_bot")


@contextual_tool
async def get_business_overview(ctx: ToolContext, date_from: str | None = None,
                                date_to: str | None = None) -> dict:
    """Get sales, margin, customers, low stock and account balances for a date range."""
    f, t = default_period(date_from, date_to)
    return await ReportsService().dashboard(_ctx(ctx), date_from=f, date_to=t)


@contextual_tool
async def get_sales_analysis(ctx: ToolContext, date_from: str | None = None,
                             date_to: str | None = None) -> dict:
    """Get top products, sales trend and gross margin for a date range."""
    f, t = default_period(date_from, date_to)
    service = ReportsService()
    return {"period": {"from": f, "to": t},
            "top_products": await service.top_products(_ctx(ctx), date_from=f, date_to=t),
            "trend": await service.sales_by_period(_ctx(ctx), date_from=f, date_to=t),
            "margin": await service.margin(_ctx(ctx), date_from=f, date_to=t)}


@contextual_tool
async def get_inventory_alerts(ctx: ToolContext) -> dict:
    """List products at or below their low-stock threshold and recent movements."""
    service = InventoryService()
    erp = _ctx(ctx)
    return {"low_stock": await service.low_stock(erp), "recent_movements": await service.movements(erp, limit=20)}


@contextual_tool
async def find_customers(query: str, ctx: ToolContext) -> list[dict]:
    """Find customers by name or phone number."""
    return await ClientsService().list(_ctx(ctx), search=query, limit=20)


@contextual_tool
async def get_customer_details(client_id: str, ctx: ToolContext) -> dict:
    """Get a customer's contact data, purchase totals and recent sales."""
    return await ClientsService().get(_ctx(ctx), client_id)


@contextual_tool
async def list_recent_sales(ctx: ToolContext, date_from: str | None = None,
                            date_to: str | None = None) -> list[dict]:
    """List the most recent sales, optionally restricted to an ISO date range."""
    return await SalesService().list(_ctx(ctx), date_from=date_from, date_to=date_to, limit=20)


@contextual_tool
async def get_sale_details(sale_id: str, ctx: ToolContext) -> dict:
    """Get one sale and its line items by an id returned from list_recent_sales."""
    return await SalesService().get(_ctx(ctx), sale_id)


@contextual_tool
async def get_cash_summary(ctx: ToolContext, date_from: str | None = None,
                           date_to: str | None = None) -> dict:
    """Get cash accounts, cashflow and recent transactions for a date range."""
    from datetime import date
    today = date.today()
    f, t = default_period(date_from, date_to)
    service = FinanceService()
    erp = _ctx(ctx)
    return {"accounts": await service.list_accounts(erp),
            "cashflow": await service.cashflow(erp, date_from=f, date_to=t),
            "recent_transactions": await service.list_transactions(erp, limit=20)}


async def _propose(ctx: ToolContext, kind: str, payload: dict, summary: str) -> dict:
    action = await AdminActionService().create(_ctx(ctx), thread_id=ctx.thread_id, kind=kind, payload=payload, summary=summary)
    if ctx.outbox is not None:
        ctx.outbox.add(SendButtonsAction(body=summary, buttons=[
            ReplyButton(id=f"choice:admin-confirm:{action['id']}", title="Confirmar"),
            ReplyButton(id=f"choice:admin-cancel:{action['id']}", title="Cancelar"),
        ]))
    return {"action_id": action["id"], "status": "pending", "summary": summary}


@contextual_tool
async def propose_stock_adjustment(product_id: str, quantity: Annotated[float, Field(ge=0)],
                                   ctx: ToolContext) -> dict:
    """Propose setting a product's real counted stock. Sends confirmation buttons; does not write yet."""
    product = await ProductsService().get(_ctx(ctx), product_id)
    return await _propose(ctx, "stock_adjustment", {"product_id": product_id, "quantity": quantity},
                          f"Ajustar stock de {product['name']} a {quantity}. ¿Confirmás?")


@contextual_tool
async def propose_product_change(action: Literal["create", "update", "deactivate"],
                                 data: dict, ctx: ToolContext, product_id: str | None = None) -> dict:
    """Propose a basic product create, update, or deactivation. Confirmation is required."""
    if action == "create":
        data = ProductCreate.model_validate(data).model_dump()
    elif action == "update":
        data = ProductUpdate.model_validate(data).model_dump(exclude_unset=True)
        if not data:
            raise ValueError("Indicá al menos un campo para actualizar")
    if action != "create":
        if not product_id:
            raise ValueError("product_id es obligatorio para editar o desactivar")
        await ProductsService().get(_ctx(ctx), product_id)
    label = data.get("name") or product_id
    return await _propose(ctx, f"product_{action}", {"product_id": product_id, "data": data},
                          f"{action.capitalize()} producto {label}. ¿Confirmás?")


@contextual_tool
async def propose_transaction(type: Literal["income", "expense"], amount: Annotated[float, Field(gt=0)],
                              category: str, ctx: ToolContext, description: str | None = None,
                              cash_account_id: str | None = None, date: str | None = None) -> dict:
    """Propose a manual income or expense. Confirmation is required."""
    data = {"type": type, "amount": amount, "category": category, "description": description,
            "cash_account_id": cash_account_id, "date": date}
    return await _propose(ctx, "transaction", data, f"Registrar {type} de {amount} en {category}. ¿Confirmás?")


@contextual_tool
async def propose_sale_cancellation(sale_id: str, ctx: ToolContext) -> dict:
    """Propose cancelling an existing sale. Look it up first and require confirmation."""
    sale = await SalesService().get(_ctx(ctx), sale_id)
    if sale.get("status") != "completed":
        raise ValueError("Sólo se pueden cancelar ventas completadas")
    return await _propose(ctx, "sale_cancellation", {"sale_id": sale_id},
                          f"Cancelar venta {sale_id} por {sale.get('total')}. ¿Confirmás?")


@contextual_tool
async def execute_confirmed_action(action_id: str, ctx: ToolContext) -> dict:
    """Execute the action confirmed by the owner pressing its WhatsApp button."""
    if ctx.confirmed_action_id != action_id:
        raise PermissionError("Esta acción sólo puede ejecutarse desde su botón Confirmar")
    service = AdminActionService()
    action = await service.claim(_ctx(ctx), thread_id=ctx.thread_id, action_id=action_id)
    if action.get("status") == "executed":
        return action.get("result") or {"ok": True, "duplicate": True}
    payload, kind, erp = action["payload"], action["kind"], _ctx(ctx)
    if kind == "stock_adjustment":
        result = await InventoryService().adjust(erp, product_id=payload["product_id"], variant_id=None,
                                                  new_quantity=payload["quantity"], delta=None,
                                                  note="Ajuste vía agente admin confirmado")
    elif kind == "product_create":
        result = await ProductsService().create(erp, {**payload["data"], "admin_action_id": action_id})
    elif kind == "product_update":
        result = await ProductsService().update(erp, payload["product_id"], payload["data"])
    elif kind == "product_deactivate":
        result = await ProductsService().soft_delete(erp, payload["product_id"])
    elif kind == "transaction":
        result = await FinanceService().create_transaction(erp, {**payload, "admin_action_id": action_id})
    elif kind == "sale_cancellation":
        result = await SalesService().cancel_sale(erp, payload["sale_id"])
    else:
        raise ValueError(f"Tipo de acción no soportado: {kind}")
    return await service.complete(action_id, result)

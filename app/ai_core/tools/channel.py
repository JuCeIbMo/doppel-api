"""Tools que usan las capacidades de WhatsApp: foto, botones y listas.

Estas tools NO mandan nada: encolan una acción en el outbox del turno y el
webhook la entrega cuando el grafo termina (ver `channel/outbox.py`). Así el
agente no necesita credenciales ni cliente HTTP, y el orden de los mensajes lo
decide el canal y no el modelo.

Las tres degradan a no-op con `ok=False` si el grafo se invocó sin `TurnRuntime`
(tests, CLI): que falte el canal no puede tirar abajo un turno.
"""

from typing import Annotated

from pydantic import Field, ValidationError

from app.ai_core.channel.actions import (
    ListRow,
    ListSection,
    ReplyButton,
    SendButtonsAction,
    SendImageAction,
    SendListAction,
)
from app.ai_core.tools.context import InjectedCtx, ToolContext, contextual_tool
from app.ai_core.tools.models import ChannelActionResult, ChoiceOption, ListSectionInput
from app.services import storefront
from app.services.erp.context import bot_context

# Namespace de los ids que generamos nosotros, para distinguir el tap de un botón
# propio del de una plantilla de Meta o de un deploy anterior.
CHOICE_PREFIX = "choice:"

# Prefijos de los botones Confirmar/Cancelar del flujo admin propose→confirm.
# Compartidos entre `tools/admin.py` (los emite) y `bridge.py` (los consume) para
# que el id que se genera, el que ve el modelo y el que se compara sean el mismo.
ADMIN_CONFIRM_PREFIX = "admin-confirm:"
ADMIN_CANCEL_PREFIX = "admin-cancel:"

_NO_CHANNEL = ChannelActionResult(ok=False, reason="channel_unavailable")


def _erp_ctx(ctx: ToolContext):
    actor = "whatsapp_bot" if ctx.role == "public" else "admin_bot"
    return bot_context(ctx.tenant.tenant_id, actor=actor)


@contextual_tool
async def send_image(product_id: str, ctx: InjectedCtx) -> ChannelActionResult:
    """Show the customer the photo of a product. Use `product_id` exactly as returned by search_catalog.

    This is a CHANNEL action: WhatsApp delivers the photo as its own message.
    Never write a link, a URL or a product id in your own reply — just keep
    talking naturally and the photo arrives on its own.

    Returns `ok: false` with `reason: "no_image"` when that product has no photo
    on file. In that case simply describe it in words; do not tell the customer
    that a photo failed.
    """
    if ctx.role not in {"public", "admin"}:
        raise PermissionError("send_image requires public or admin role")
    if ctx.outbox is None:
        return _NO_CHANNEL
    if any(isinstance(action, SendImageAction) for action in ctx.outbox.actions):
        return ChannelActionResult(ok=False, reason="image_already_queued")

    image_url = await storefront.get_product_image(_erp_ctx(ctx), product_id)
    if not image_url:
        return ChannelActionResult(ok=False, reason="no_image")

    ctx.outbox.add(SendImageAction(image_url=image_url))
    return ChannelActionResult(ok=True)


@contextual_tool
async def send_reply_buttons(
    body: Annotated[str, Field(min_length=1)],
    options: Annotated[list[ChoiceOption], Field(min_length=1, max_length=3)],
    ctx: InjectedCtx,
) -> ChannelActionResult:
    """Offer the customer up to 3 tappable buttons: a payment method, confirm/cancel, a pick between two products.

    `body` is the question you are asking. Each option needs a short `label`
    (what the customer reads, max 20 characters) and a `value` (a short id you
    will recognise when they tap it).

    This is a CHANNEL action: when the customer taps a button it comes back to
    you as their next message. Do NOT repeat the options in your own reply — the
    buttons already show them. Send at most ONE interactive message per turn, and
    never combine this with send_list_message.

    Use it only when the options are genuinely few and clear; for more than 3 use
    send_list_message.
    """
    if ctx.role not in {"public", "admin"}:
        raise PermissionError("send_reply_buttons requires public or admin role")
    if ctx.outbox is None:
        return _NO_CHANNEL

    try:
        action = SendButtonsAction(
            body=body,
            buttons=[
                ReplyButton(id=f"{CHOICE_PREFIX}{option.value}", title=option.label)
                for option in options
            ],
        )
    except ValidationError as exc:
        return ChannelActionResult(ok=False, reason=str(exc))

    ctx.outbox.add(action)
    return ChannelActionResult(ok=True)


@contextual_tool
async def send_list_message(
    body: Annotated[str, Field(min_length=1)],
    button_label: Annotated[str, Field(min_length=1)],
    sections: Annotated[list[ListSectionInput], Field(min_length=1)],
    ctx: InjectedCtx,
) -> ChannelActionResult:
    """Show a scrollable menu of options grouped in sections: the catalog, categories, time slots.

    Use it when there are more than 3 options; for 3 or fewer use send_reply_buttons.
    `button_label` is the text on the button that opens the menu (max 20 chars).

    Limits: at most 10 sections and 10 rows in TOTAL across all of them. Row
    titles are cut at 24 characters and descriptions at 72, so put the name in
    the title and the price in the description.

    This is a CHANNEL action: WhatsApp renders the menu itself. Do NOT list the
    same options again in your reply — a one-line intro is enough. Send at most
    ONE interactive message per turn.
    """
    if ctx.role not in {"public", "admin"}:
        raise PermissionError("send_list_message requires public or admin role")
    if ctx.outbox is None:
        return _NO_CHANNEL

    try:
        action = SendListAction(
            body=body,
            button_label=button_label,
            sections=[
                ListSection(
                    title=section.title,
                    rows=[
                        ListRow(
                            id=f"{CHOICE_PREFIX}{row.value}",
                            title=row.title,
                            description=row.description,
                        )
                        for row in section.rows
                    ],
                )
                for section in sections
            ],
        )
    except ValidationError as exc:
        # El modelo ve el motivo en el ToolMessage y manda menos opciones, en vez
        # de que el canal recorte en silencio una que sí quería ofrecer.
        return ChannelActionResult(ok=False, reason=str(exc))

    ctx.outbox.add(action)
    return ChannelActionResult(ok=True)

"""Tests de la capa de canal pura: cortesías por reglas y modelos de acción.

Todo lo de acá es sin red y sin LLM: son las reglas que deciden qué sale por
WhatsApp y los límites que Meta impone sobre esos payloads.

Shared test environment is loaded before collection by `tests/conftest.py`.
"""

import unicodedata

import pytest
from pydantic import ValidationError

from app.ai_core.channel import courtesy
from app.ai_core.channel.actions import (
    MAX_TEXT,
    ListRow,
    ListSection,
    ReplyButton,
    SendButtonsAction,
    SendImageAction,
    SendListAction,
    SendTextAction,
    TurnResult,
)
from app.whatsapp.delivery import plan_delivery

# --- reacciones -------------------------------------------------------------

def test_reaction_matches_keywords_ignoring_accents_and_case():
    assert courtesy.choose_reaction("MUCHAS GRACIAS!") in ("🙏", "😊", "🤗")
    # "buen día" con acento tiene que matchear la clave "buen dia".
    assert courtesy.choose_reaction("buen día!") in ("👋", "😃")

def test_first_contact_always_waves():
    """Gana sobre el texto: el saludo inicial merece el mismo gesto siempre."""
    assert courtesy.choose_reaction("jajaja", first_contact=True) == "👋"

def test_reaction_falls_back_to_attachment_type():
    assert courtesy.choose_reaction(None, "image") == "👀"
    assert courtesy.choose_reaction(None, "voice") == "👂"

def test_no_reaction_when_nothing_applies():
    assert courtesy.choose_reaction("cuánto sale el número 4", "text") is None

def test_every_reaction_emoji_is_a_single_codepoint():
    """Meta rechaza de forma inconsistente los emojis con variation selector.

    ❤️ es U+2764 U+FE0F: entra al pool sin que nadie lo note y falla por mensaje.
    """
    pools = [emoji for _, pool in courtesy._INTENTS for emoji in pool]
    pools += list(courtesy._BY_ATTACHMENT.values())
    pools.append(courtesy._FIRST_CONTACT)

    for emoji in pools:
        assert len(emoji) == 1, f"{emoji!r} ({unicodedata.name(emoji[0])}) no es de un codepoint"

# --- pausa de tipeo ---------------------------------------------------------

def test_typing_pause_grows_with_length_and_is_capped():
    short = courtesy.typing_pause("hola")
    long = courtesy.typing_pause("x" * 5000)

    assert short < long
    assert long <= courtesy.TYPING_MAX_SECONDS * (1 + courtesy.TYPING_JITTER)

def test_typing_pause_is_zero_once_the_turn_already_took_longer():
    """El LLM ya tardó más que la pausa objetivo: no hay nada que simular."""
    assert courtesy.typing_pause("hola", elapsed=60.0) == 0.0

def test_typing_pause_handles_empty_text():
    assert courtesy.typing_pause(None) > 0.0

# --- límites de los modelos de acción ---------------------------------------
#
# Cantidades se rechazan (el modelo perdería una opción que quiso ofrecer y puede
# corregirse con el ToolMessage); longitudes se truncan (no pierden significado y
# rechazarlas costaría un turno de LLM entero).

def test_more_than_three_buttons_is_rejected():
    with pytest.raises(ValidationError):
        SendButtonsAction(
            body="elegí",
            buttons=[ReplyButton(id=str(i), title=f"b{i}") for i in range(4)],
        )

def test_zero_buttons_is_rejected():
    with pytest.raises(ValidationError):
        SendButtonsAction(body="elegí", buttons=[])

def test_button_title_is_truncated():
    button = ReplyButton(id="choice:x", title="Un título larguísimo que no entra")

    assert button.title == "Un título larguísimo"
    assert len(button.title) == 20

def test_list_rejects_more_than_ten_rows_across_sections():
    sections = [
        ListSection(title=f"s{i}", rows=[ListRow(id=f"r{i}{j}", title=f"f{j}") for j in range(6)])
        for i in range(2)
    ]

    with pytest.raises(ValidationError, match="10 rows in total"):
        SendListAction(body="mirá", button_label="Ver", sections=sections)

def test_list_accepts_exactly_ten_rows():
    sections = [
        ListSection(title="s", rows=[ListRow(id=f"r{j}", title=f"f{j}") for j in range(10)]),
    ]
    action = SendListAction(body="mirá", button_label="Ver", sections=sections)

    assert sum(len(section.rows) for section in action.sections) == 10

def test_list_section_meta_shape_omits_empty_descriptions():
    section = ListSection(title="Bebidas", rows=[
        ListRow(id="p1", title="Café", description="$3"),
        ListRow(id="p2", title="Té"),
    ])

    assert section.to_meta() == {
        "title": "Bebidas",
        "rows": [
            {"id": "p1", "title": "Café", "description": "$3"},
            {"id": "p2", "title": "Té"},
        ],
    }

# --- plan de entrega --------------------------------------------------------

def test_a_single_photo_absorbs_the_text_as_caption():
    """Evita el patrón feo de foto muda seguida de un párrafo suelto."""
    plan = plan_delivery(TurnResult(
        text="Esta es la remera azul",
        actions=[SendImageAction(image_url="https://cdn/x.webp")],
    ))

    assert len(plan) == 1
    assert plan[0].kind == "image"
    assert plan[0].caption == "Esta es la remera azul"

def test_two_photos_keep_the_text_as_its_own_message():
    plan = plan_delivery(TurnResult(
        text="Tengo estas dos",
        actions=[
            SendImageAction(image_url="https://cdn/a.webp"),
            SendImageAction(image_url="https://cdn/b.webp"),
        ],
    ))

    assert [action.kind for action in plan] == ["text", "image", "image"]

def test_a_photo_with_its_own_caption_is_left_alone():
    plan = plan_delivery(TurnResult(
        text="Mirá",
        actions=[SendImageAction(image_url="https://cdn/x.webp", caption="Remera")],
    ))

    assert [action.kind for action in plan] == ["text", "image"]
    assert plan[1].caption == "Remera"

def test_action_order_is_never_rearranged():
    """Que la foto vaya antes que los botones que la referencian es semántico."""
    plan = plan_delivery(TurnResult(
        text="",
        actions=[
            SendImageAction(image_url="https://cdn/x.webp"),
            SendButtonsAction(body="¿La querés?", buttons=[ReplyButton(id="c:si", title="Sí")]),
        ],
    ))

    assert [action.kind for action in plan] == ["image", "buttons"]

def test_long_text_is_split_instead_of_failing_whole():
    """Sin esto Meta devuelve 400 y el cliente no recibe absolutamente nada."""
    paragraphs = "\n\n".join(["x" * 500] * 20)  # ~10500 chars
    plan = plan_delivery(TurnResult(text=paragraphs))

    assert len(plan) > 1
    assert all(isinstance(action, SendTextAction) for action in plan)
    assert all(len(action.body) <= MAX_TEXT for action in plan)
    assert "".join(action.body.replace("\n", "") for action in plan).count("x") == 10000

def test_an_empty_turn_produces_nothing_to_send():
    assert plan_delivery(TurnResult(text="   ")) == []

"""Acciones de canal: lo que el agente decide mandar, antes de mandarlo.

Pydantic y no dataclasses a propósito: estos valores los llena el LLM, así que
validarlos no es opcional. Una `ValidationError` acá adentro la convierte
`ToolErrorMiddleware` en un `ToolMessage` de error, o sea que el modelo ve qué
hizo mal y lo corrige en el mismo turno, sin round-trip extra.

Política de límites, deliberadamente asimétrica:

- **Cantidades → se rechazan** (4 botones, 11 filas). Recortar en silencio
  descarta una opción real que el modelo quiso ofrecer; rechazar le da el
  feedback y lo arregla solo.
- **Longitudes → se truncan** (títulos, descripciones, body). Un título de 22
  caracteres no pierde significado, y rechazarlo costaría un turno de LLM entero.

Esta es la capa autoritativa de validación. `app/services/meta_api.py` vuelve a
recortar por su cuenta porque también lo llaman rutas que no pasan por el agente.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator, model_validator

# Límites de la WhatsApp Cloud API.
MAX_BUTTONS = 3
MAX_BUTTON_TITLE = 20
MAX_BUTTON_ID = 256
MAX_LIST_SECTIONS = 10
MAX_LIST_ROWS = 10
MAX_ROW_ID = 200
MAX_ROW_TITLE = 24
MAX_ROW_DESCRIPTION = 72
MAX_SECTION_TITLE = 24
MAX_LIST_BUTTON_LABEL = 20
# 1024 es el límite del body de un mensaje interactivo y del caption de una
# imagen; el texto plano admite 4096.
MAX_BODY = 1024
MAX_TEXT = 4096


def _truncate(value: str, limit: int) -> str:
    return value[:limit]


class ReplyButton(BaseModel):
    id: str
    title: str

    @field_validator("id")
    @classmethod
    def _cap_id(cls, value: str) -> str:
        return _truncate(value, MAX_BUTTON_ID)

    @field_validator("title")
    @classmethod
    def _cap_title(cls, value: str) -> str:
        return _truncate(value, MAX_BUTTON_TITLE)


class ListRow(BaseModel):
    id: str
    title: str
    description: str | None = None

    @field_validator("id")
    @classmethod
    def _cap_id(cls, value: str) -> str:
        return _truncate(value, MAX_ROW_ID)

    @field_validator("title")
    @classmethod
    def _cap_title(cls, value: str) -> str:
        return _truncate(value, MAX_ROW_TITLE)

    @field_validator("description")
    @classmethod
    def _cap_description(cls, value: str | None) -> str | None:
        return _truncate(value, MAX_ROW_DESCRIPTION) if value else value


class ListSection(BaseModel):
    title: str
    rows: list[ListRow] = Field(min_length=1)

    @field_validator("title")
    @classmethod
    def _cap_title(cls, value: str) -> str:
        return _truncate(value, MAX_SECTION_TITLE)

    def to_meta(self) -> dict:
        """Shape exacto que espera Meta para una sección de lista."""
        rows: list[dict] = []
        for row in self.rows:
            entry = {"id": row.id, "title": row.title}
            if row.description:
                entry["description"] = row.description
            rows.append(entry)
        return {"title": self.title, "rows": rows}


class SendTextAction(BaseModel):
    kind: Literal["text"] = "text"
    body: str

    @field_validator("body")
    @classmethod
    def _cap_body(cls, value: str) -> str:
        return _truncate(value, MAX_TEXT)


class SendImageAction(BaseModel):
    kind: Literal["image"] = "image"
    image_url: str
    caption: str | None = None

    @field_validator("caption")
    @classmethod
    def _cap_caption(cls, value: str | None) -> str | None:
        return _truncate(value, MAX_BODY) if value else value


class SendButtonsAction(BaseModel):
    kind: Literal["buttons"] = "buttons"
    body: str
    buttons: list[ReplyButton] = Field(min_length=1, max_length=MAX_BUTTONS)

    @field_validator("body")
    @classmethod
    def _cap_body(cls, value: str) -> str:
        return _truncate(value, MAX_BODY)

    def to_meta(self) -> list[tuple[str, str]]:
        return [(button.id, button.title) for button in self.buttons]


class SendListAction(BaseModel):
    kind: Literal["list"] = "list"
    body: str
    button_label: str
    sections: list[ListSection] = Field(min_length=1, max_length=MAX_LIST_SECTIONS)

    @field_validator("body")
    @classmethod
    def _cap_body(cls, value: str) -> str:
        return _truncate(value, MAX_BODY)

    @field_validator("button_label")
    @classmethod
    def _cap_label(cls, value: str) -> str:
        return _truncate(value, MAX_LIST_BUTTON_LABEL)

    @model_validator(mode="after")
    def _cap_total_rows(self) -> "SendListAction":
        total = sum(len(section.rows) for section in self.sections)
        if total > MAX_LIST_ROWS:
            raise ValueError(
                f"A WhatsApp list allows {MAX_LIST_ROWS} rows in total across all "
                f"sections, got {total}. Send fewer options."
            )
        return self

    def to_meta(self) -> list[dict]:
        return [section.to_meta() for section in self.sections]


class SendReactionAction(BaseModel):
    kind: Literal["reaction"] = "reaction"
    emoji: str


ChannelAction = Annotated[
    Union[
        SendTextAction,
        SendImageAction,
        SendButtonsAction,
        SendListAction,
        SendReactionAction,
    ],
    Field(discriminator="kind"),
]


class TurnResult(BaseModel):
    """Lo que un turno produce: el texto del agente más lo que encoló el canal.

    Reemplaza al `str | None` que devolvía `bridge.respond`. `ok=False` es lo que
    antes era `None` (el agente crasheó); un `text` vacío con `ok=True` sigue
    siendo una respuesta vacía legítima. La distinción importa porque el webhook
    no manda nada en ninguno de los dos casos pero los loguea distinto.
    """

    text: str = ""
    actions: list[ChannelAction] = Field(default_factory=list)
    ok: bool = True

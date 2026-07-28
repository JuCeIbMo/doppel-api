from pydantic import BaseModel, Field


class ProductResult(BaseModel):
    id: str
    name: str
    description: str | None
    price: float
    in_stock: bool
    tags: list[str] = Field(default_factory=list)


class CatalogPage(BaseModel):
    items: list[ProductResult]
    page: int
    # True = hay más productos; llamá search_catalog de nuevo con `page + 1`.
    # Sin esto el modelo no tiene forma de distinguir "esto es todo" de "corté
    # la página" y o inventa que no hay más, o repite la misma página.
    has_more: bool


class StockResult(BaseModel):
    product_id: str
    quantity: float
    # Distinguishes "this product has none left" from "no such product". Both
    # used to come back as quantity 0, so a hallucinated id read to the model as
    # a sold-out product and it told the customer there was no stock instead of
    # searching again.
    found: bool = True


class OrderItemInput(BaseModel):
    product_id: str = Field(description="Product id, as returned by search_catalog")
    quantity: float = Field(gt=0, description="Units to order; must be positive")


class OrderItemResult(BaseModel):
    product_id: str
    name: str
    quantity: float
    subtotal: float


class OrderResult(BaseModel):
    total: float
    items: list[OrderItemResult]
    # True = esta orden ya estaba registrada (mismo turno, mismos ítems) y se
    # devolvió la venta existente. El modelo no debe anunciarla como una compra
    # nueva ni volver a pedir confirmación.
    duplicate: bool = False


class HandoffResult(BaseModel):
    status: str
    reason: str


class ChannelActionResult(BaseModel):
    """Resultado de encolar una acción de canal (foto, botones, lista).

    `ok: False` con un `reason` legible en vez de una excepción: que un producto
    no tenga foto es una respuesta normal, y el modelo tiene que poder seguir la
    conversación describiéndolo en palabras.
    """

    ok: bool
    reason: str = ""


class ChoiceOption(BaseModel):
    label: str = Field(description="What the customer sees on the button; max 20 characters")
    value: str = Field(description="Short id you will recognise when the customer taps it")


class ListRowInput(BaseModel):
    title: str = Field(description="Row title; max 24 characters")
    value: str = Field(description="Short id you will recognise when the customer picks it")
    description: str | None = Field(
        default=None, description="Optional second line, e.g. the price; max 72 characters"
    )


class ListSectionInput(BaseModel):
    title: str = Field(description="Section heading; max 24 characters")
    rows: list[ListRowInput] = Field(description="Options in this section")

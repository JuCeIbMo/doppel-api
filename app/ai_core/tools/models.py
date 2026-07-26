from pydantic import BaseModel, Field


class ProductResult(BaseModel):
    id: str
    name: str
    description: str | None
    price: float
    in_stock: bool
    tags: list[str] = Field(default_factory=list)


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


class HandoffResult(BaseModel):
    status: str
    reason: str

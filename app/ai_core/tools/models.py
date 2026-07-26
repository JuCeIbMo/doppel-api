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

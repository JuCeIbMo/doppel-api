"""Pydantic request/response models for the ERP API.

This is the contract shared with the frontend (exposed via /openapi.json). Responses
are intentionally IA-friendly: they carry human-readable names next to IDs so an LLM
agent can use them directly without extra lookups.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

PaymentMethod = Literal["cash", "card", "transfer", "whatsapp", "other"]
MovementType = Literal["purchase", "sale", "adjustment_in", "adjustment_out", "return", "loss"]
TransactionType = Literal["income", "expense"]


# --- Products ----------------------------------------------------------------
class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    sku: str | None = Field(default=None, max_length=120)
    barcode: str | None = Field(default=None, max_length=120)
    category: str | None = Field(default=None, max_length=120)
    image_url: str | None = None
    cost_price: float = Field(default=0, ge=0)
    price: float = Field(default=0, ge=0)  # sale price (existing column)
    unit: str = Field(default="unidad", max_length=40)
    available: bool = True
    low_stock_threshold: int = Field(default=5, ge=0)


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    sku: str | None = Field(default=None, max_length=120)
    barcode: str | None = Field(default=None, max_length=120)
    category: str | None = Field(default=None, max_length=120)
    image_url: str | None = None
    cost_price: float | None = Field(default=None, ge=0)
    price: float | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, max_length=40)
    available: bool | None = None
    low_stock_threshold: int | None = Field(default=None, ge=0)


class ProductResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    sku: str | None = None
    barcode: str | None = None
    category: str | None = None
    image_url: str | None = None
    cost_price: float
    price: float
    unit: str
    available: bool
    has_variants: bool
    low_stock_threshold: int
    stock: float | None = None  # current quantity, joined from inventory when requested
    created_at: str | None = None


class VariantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    barcode: str | None = None
    sku: str | None = None
    cost_price: float | None = Field(default=None, ge=0)
    sale_price: float | None = Field(default=None, ge=0)
    is_active: bool = True


class VariantResponse(BaseModel):
    id: str
    product_id: str
    name: str
    barcode: str | None = None
    sku: str | None = None
    cost_price: float | None = None
    sale_price: float | None = None
    is_active: bool


class ImportResult(BaseModel):
    imported: int
    errors: list[dict] = Field(default_factory=list)


# --- Inventory ---------------------------------------------------------------
class InventoryRow(BaseModel):
    product_id: str
    product_name: str
    variant_id: str | None = None
    variant_name: str | None = None
    category: str | None = None
    unit: str
    quantity: float
    low_stock_threshold: int


class AdjustmentRequest(BaseModel):
    product_id: str
    variant_id: str | None = None
    # Either set an absolute target quantity, or a signed delta. Note (reason) required.
    new_quantity: float | None = Field(default=None, ge=0)
    delta: float | None = None
    note: str = Field(min_length=1, max_length=500)


class MovementResponse(BaseModel):
    id: str
    product_id: str
    product_name: str | None = None
    variant_id: str | None = None
    type: MovementType
    quantity: float
    unit_cost: float | None = None
    reference_id: str | None = None
    notes: str | None = None
    actor: str
    created_at: str


# --- Clients -----------------------------------------------------------------
class ClientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = None
    address: str | None = None
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)
    whatsapp_id: str | None = None


class ClientUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = None
    address: str | None = None
    notes: str | None = None
    tags: list[str] | None = None
    whatsapp_id: str | None = None


class ClientResponse(BaseModel):
    id: str
    name: str
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)
    whatsapp_id: str | None = None
    total_purchases: float
    purchase_count: int
    last_purchase_at: str | None = None
    created_at: str | None = None


# --- Sales -------------------------------------------------------------------
class SaleItemInput(BaseModel):
    product_id: str
    variant_id: str | None = None
    quantity: float = Field(gt=0)
    unit_price: float | None = Field(default=None, ge=0)  # omitted -> catalog price


class CreateSaleRequest(BaseModel):
    client_id: str | None = None
    payment_method: PaymentMethod = "cash"
    cash_account_id: str | None = None
    discount: float = Field(default=0, ge=0)
    notes: str | None = None
    items: list[SaleItemInput] = Field(min_length=1)


class SaleItemResponse(BaseModel):
    id: str
    product_id: str
    variant_id: str | None = None
    product_name: str
    quantity: float
    unit_price: float
    unit_cost: float
    total: float


class SaleResponse(BaseModel):
    id: str
    client_id: str | None = None
    status: Literal["completed", "cancelled"]
    payment_method: PaymentMethod
    subtotal: float
    discount: float
    total: float
    notes: str | None = None
    actor: str
    created_at: str
    items: list[SaleItemResponse] = Field(default_factory=list)


# --- Finance -----------------------------------------------------------------
class TransactionCreate(BaseModel):
    type: TransactionType
    amount: float = Field(ge=0)
    category: str = Field(min_length=1, max_length=120)
    description: str | None = None
    cash_account_id: str | None = None
    date: str | None = Field(default=None, description="ISO date YYYY-MM-DD; defaults to today")


class TransactionResponse(BaseModel):
    id: str
    type: TransactionType
    amount: float
    category: str
    description: str | None = None
    cash_account_id: str | None = None
    sale_id: str | None = None
    actor: str
    date: str
    created_at: str


class CashAccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: str = Field(default="cash", max_length=40)
    is_default: bool = False


class CashAccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    type: str | None = None
    is_default: bool | None = None
    is_active: bool | None = None


class CashAccountResponse(BaseModel):
    id: str
    name: str
    type: str
    balance: float
    is_default: bool
    is_active: bool


# --- Reports -----------------------------------------------------------------
class DashboardResponse(BaseModel):
    period: dict
    sales_total: float
    sales_count: int
    gross_margin: float
    gross_margin_pct: float
    new_clients: int
    low_stock_count: int
    top_product: dict | None = None
    cash_balances: list[dict] = Field(default_factory=list)

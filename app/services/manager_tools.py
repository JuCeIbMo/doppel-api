"""Tools del manager agent — leen y modifican `bot_configs` y consultan `messages`.

Convencion para escrituras: cada tool destructiva acepta `confirmed: bool`. Si
`confirmed` no es true, la tool retorna un mensaje de error pidiendo
confirmacion al operador. Esto garantiza que el manager siempre pase por un
turno de "te voy a hacer X, ¿confirmas?" antes de tocar la DB.
"""

from __future__ import annotations

import re
from typing import Any

from supabase import Client

from app.services.agent_core import (
    BooleanSchema,
    IntegerSchema,
    NumberSchema,
    ObjectSchema,
    StringSchema,
    Tool,
    ToolRegistry,
    tool_parameters,
    tool_parameters_schema,
)


_NEEDS_CONFIRMATION = (
    "Error: confirmation required. Restate the exact change to the operator "
    "in plain language and call this tool again with confirmed=true only after they approve."
)

_NON_DIGITS = re.compile(r"\D+")


def normalize_phone(raw: str) -> str:
    """Strip everything that isn't a digit. Matches the format Meta sends in webhooks
    (`from` field is digits only, no leading '+'). Empty result means invalid input.
    """
    return _NON_DIGITS.sub("", raw or "")


class _BotConfigTool(Tool):
    """Common base: holds the supabase client + tenant_id binding."""

    def __init__(self, supabase: Client, tenant_id: str):
        self.supabase = supabase
        self.tenant_id = tenant_id


# --- read-only -----------------------------------------------------------


@tool_parameters(tool_parameters_schema())
class GetBotConfigTool(_BotConfigTool):
    @property
    def name(self) -> str:
        return "get_bot_config"

    @property
    def description(self) -> str:
        return (
            "Read the current bot configuration for this tenant: system prompt, "
            "welcome message, language, AI model, enabled flag."
        )

    @property
    def read_only(self) -> bool:
        return True

    async def execute(self, **_: Any) -> Any:
        result = (
            self.supabase.table("bot_configs")
            .select(
                "system_prompt, welcome_message, language, ai_model, "
                "bot_enabled, manager_prompt, admin_phones"
            )
            .eq("tenant_id", self.tenant_id)
            .single()
            .execute()
        )
        return result.data or {}


@tool_parameters(
    tool_parameters_schema(
        limit=IntegerSchema(description="How many recent messages", minimum=1, maximum=50),
        required=[],
    )
)
class ListRecentMessagesTool(_BotConfigTool):
    @property
    def name(self) -> str:
        return "list_recent_messages"

    @property
    def description(self) -> str:
        return (
            "List the most recent inbound/outbound messages across all clients of "
            "this tenant, ordered newest first. Useful to inspect how the client "
            "agent is behaving before tweaking the prompt."
        )

    @property
    def read_only(self) -> bool:
        return True

    async def execute(self, limit: int = 10, **_: Any) -> Any:
        result = (
            self.supabase.table("messages")
            .select("user_phone, direction, content, message_type, created_at")
            .eq("tenant_id", self.tenant_id)
            .order("created_at", desc=True)
            .limit(int(limit))
            .execute()
        )
        return result.data or []


# --- writes (require confirmed=true) -------------------------------------


@tool_parameters(
    tool_parameters_schema(
        new_prompt=StringSchema(
            "Full new value for system_prompt (replaces, not appends)",
            min_length=1,
        ),
        confirmed=BooleanSchema(
            description="Must be true after operator approval. Otherwise the tool refuses.",
            default=False,
        ),
        required=["new_prompt"],
    )
)
class UpdateSystemPromptTool(_BotConfigTool):
    @property
    def name(self) -> str:
        return "update_system_prompt"

    @property
    def description(self) -> str:
        return (
            "Replace the system prompt the client-facing agent uses. "
            "Always confirm with the operator first; pass confirmed=true only after explicit approval."
        )

    async def execute(self, new_prompt: str, confirmed: bool = False, **_: Any) -> Any:
        if not confirmed:
            return _NEEDS_CONFIRMATION
        self.supabase.table("bot_configs").update(
            {"system_prompt": new_prompt}
        ).eq("tenant_id", self.tenant_id).execute()
        return {"ok": True, "field": "system_prompt", "preview": new_prompt[:120]}


@tool_parameters(
    tool_parameters_schema(
        new_message=StringSchema("Full new value for welcome_message", min_length=1),
        confirmed=BooleanSchema(default=False),
        required=["new_message"],
    )
)
class UpdateWelcomeMessageTool(_BotConfigTool):
    @property
    def name(self) -> str:
        return "update_welcome_message"

    @property
    def description(self) -> str:
        return "Replace the welcome message. Confirm before applying."

    async def execute(self, new_message: str, confirmed: bool = False, **_: Any) -> Any:
        if not confirmed:
            return _NEEDS_CONFIRMATION
        self.supabase.table("bot_configs").update(
            {"welcome_message": new_message}
        ).eq("tenant_id", self.tenant_id).execute()
        return {"ok": True, "field": "welcome_message"}


@tool_parameters(
    tool_parameters_schema(
        enabled=BooleanSchema(description="True to enable, false to pause the client agent"),
        confirmed=BooleanSchema(default=False),
        required=["enabled"],
    )
)
class SetBotEnabledTool(_BotConfigTool):
    @property
    def name(self) -> str:
        return "set_bot_enabled"

    @property
    def description(self) -> str:
        return (
            "Enable or pause the client-facing bot. When disabled, inbound messages "
            "are still stored but the bot does not respond. Confirm before applying."
        )

    async def execute(self, enabled: bool, confirmed: bool = False, **_: Any) -> Any:
        if not confirmed:
            return _NEEDS_CONFIRMATION
        self.supabase.table("bot_configs").update(
            {"bot_enabled": bool(enabled)}
        ).eq("tenant_id", self.tenant_id).execute()
        return {"ok": True, "bot_enabled": bool(enabled)}


@tool_parameters(
    tool_parameters_schema(
        phone=StringSchema(
            "Phone number to add (any format; the server will keep digits only)",
            min_length=4,
        ),
        confirmed=BooleanSchema(default=False),
        required=["phone"],
    )
)
class AddAdminPhoneTool(_BotConfigTool):
    @property
    def name(self) -> str:
        return "add_admin_phone"

    @property
    def description(self) -> str:
        return (
            "Add a phone number to the admin list. Numbers in this list can talk to "
            "the manager agent (you). Confirm with the operator before applying."
        )

    async def execute(self, phone: str, confirmed: bool = False, **_: Any) -> Any:
        digits = normalize_phone(phone)
        if not digits:
            return "Error: phone is empty after normalization. Provide a number with at least one digit."
        if not confirmed:
            return _NEEDS_CONFIRMATION

        current = (
            self.supabase.table("bot_configs")
            .select("admin_phones")
            .eq("tenant_id", self.tenant_id)
            .single()
            .execute()
        )
        phones = list((current.data or {}).get("admin_phones") or [])
        if digits in phones:
            return {"ok": True, "phones": phones, "noop": True}
        phones.append(digits)
        self.supabase.table("bot_configs").update(
            {"admin_phones": phones}
        ).eq("tenant_id", self.tenant_id).execute()
        return {"ok": True, "phones": phones, "added": digits}


@tool_parameters(
    tool_parameters_schema(
        phone=StringSchema(
            "Phone number to remove (any format; the server will keep digits only)",
            min_length=4,
        ),
        confirmed=BooleanSchema(default=False),
        required=["phone"],
    )
)
class RemoveAdminPhoneTool(_BotConfigTool):
    @property
    def name(self) -> str:
        return "remove_admin_phone"

    @property
    def description(self) -> str:
        return (
            "Remove a phone number from the admin list. Be careful: removing the "
            "last admin locks the operator out of the manager agent. Always confirm."
        )

    async def execute(self, phone: str, confirmed: bool = False, **_: Any) -> Any:
        digits = normalize_phone(phone)
        if not digits:
            return "Error: phone is empty after normalization."
        if not confirmed:
            return _NEEDS_CONFIRMATION

        current = (
            self.supabase.table("bot_configs")
            .select("admin_phones")
            .eq("tenant_id", self.tenant_id)
            .single()
            .execute()
        )
        phones = list((current.data or {}).get("admin_phones") or [])
        if digits not in phones:
            return {"ok": True, "phones": phones, "noop": True}
        phones = [p for p in phones if p != digits]
        self.supabase.table("bot_configs").update(
            {"admin_phones": phones}
        ).eq("tenant_id", self.tenant_id).execute()
        return {"ok": True, "phones": phones, "removed": digits}


# --- business info / products -------------------------------------------

_BUSINESS_FIELDS = ("name", "description", "hours", "address", "payment_methods")
_PRODUCT_FIELDS = ("name", "description", "price", "available")


def _ensure_business_row(supabase: Client, tenant_id: str) -> None:
    existing = (
        supabase.table("business_info")
        .select("id")
        .eq("tenant_id", tenant_id)
        .limit(1)
        .execute()
    )
    if not existing.data:
        supabase.table("business_info").insert({"tenant_id": tenant_id}).execute()


@tool_parameters(tool_parameters_schema())
class GetBusinessInfoTool(_BotConfigTool):
    @property
    def name(self) -> str:
        return "get_business_info"

    @property
    def description(self) -> str:
        return (
            "Read the business profile (name, description, hours, address, "
            "payment_methods) shown to clients."
        )

    @property
    def read_only(self) -> bool:
        return True

    async def execute(self, **_: Any) -> Any:
        result = (
            self.supabase.table("business_info")
            .select("name, description, hours, address, payment_methods")
            .eq("tenant_id", self.tenant_id)
            .limit(1)
            .execute()
        )
        if result.data:
            return result.data[0]
        return {f: "" for f in _BUSINESS_FIELDS}


@tool_parameters(
    tool_parameters_schema(
        field_updates=ObjectSchema(
            description=(
                "Subset of business profile fields to update. Allowed keys: "
                "name, description, hours, address, payment_methods. "
                "Only include fields you actually want to change."
            ),
            additional_properties=True,
        ),
        confirmed=BooleanSchema(default=False),
        required=["field_updates"],
    )
)
class UpdateBusinessInfoTool(_BotConfigTool):
    @property
    def name(self) -> str:
        return "update_business_info"

    @property
    def description(self) -> str:
        return (
            "Update one or more fields of the business profile. Always confirm "
            "with the operator first; pass confirmed=true only after explicit approval."
        )

    async def execute(
        self,
        field_updates: dict[str, Any] | None = None,
        confirmed: bool = False,
        **_: Any,
    ) -> Any:
        updates = {k: v for k, v in (field_updates or {}).items() if k in _BUSINESS_FIELDS}
        if not updates:
            return (
                "Error: no valid fields provided. Allowed keys: "
                + ", ".join(_BUSINESS_FIELDS)
            )
        if not confirmed:
            return _NEEDS_CONFIRMATION

        _ensure_business_row(self.supabase, self.tenant_id)
        self.supabase.table("business_info").update(updates).eq(
            "tenant_id", self.tenant_id
        ).execute()
        return {"ok": True, "updated": list(updates.keys())}


@tool_parameters(tool_parameters_schema())
class ListProductsTool(_BotConfigTool):
    @property
    def name(self) -> str:
        return "list_products"

    @property
    def description(self) -> str:
        return (
            "List all products of this tenant (including unavailable ones). "
            "Useful for the manager to review the catalog before edits."
        )

    @property
    def read_only(self) -> bool:
        return True

    async def execute(self, **_: Any) -> Any:
        result = (
            self.supabase.table("products")
            .select("id, name, description, price, available")
            .eq("tenant_id", self.tenant_id)
            .order("name", desc=False)
            .execute()
        )
        return result.data or []


@tool_parameters(
    tool_parameters_schema(
        name=StringSchema("Product name", min_length=1, max_length=200),
        description=StringSchema("Optional product description", max_length=2000),
        price=NumberSchema(description="Optional price (>= 0)", minimum=0, nullable=True),
        available=BooleanSchema(description="Whether the product is available", default=True),
        confirmed=BooleanSchema(default=False),
        required=["name"],
    )
)
class AddProductTool(_BotConfigTool):
    @property
    def name(self) -> str:
        return "add_product"

    @property
    def description(self) -> str:
        return "Create a new product in the catalog. Confirm before applying."

    async def execute(
        self,
        name: str = "",
        description: str = "",
        price: float | None = None,
        available: bool = True,
        confirmed: bool = False,
        **_: Any,
    ) -> Any:
        clean_name = (name or "").strip()
        if not clean_name:
            return "Error: name is required and cannot be empty."
        if price is not None and price < 0:
            return "Error: price must be >= 0."
        if not confirmed:
            return _NEEDS_CONFIRMATION

        payload = {
            "tenant_id": self.tenant_id,
            "name": clean_name,
            "description": description or "",
            "price": price,
            "available": bool(available),
        }
        result = self.supabase.table("products").insert(payload).execute()
        row = (result.data or [{}])[0]
        return {"ok": True, "id": row.get("id"), "name": clean_name}


@tool_parameters(
    tool_parameters_schema(
        product_id=StringSchema("UUID of the product to update", min_length=1),
        field_updates=ObjectSchema(
            description=(
                "Fields to update. Allowed keys: name, description, price, available. "
                "Include only the keys you intend to change."
            ),
            additional_properties=True,
        ),
        confirmed=BooleanSchema(default=False),
        required=["product_id", "field_updates"],
    )
)
class UpdateProductTool(_BotConfigTool):
    @property
    def name(self) -> str:
        return "update_product"

    @property
    def description(self) -> str:
        return (
            "Update one or more fields of an existing product. Confirm before applying."
        )

    async def execute(
        self,
        product_id: str = "",
        field_updates: dict[str, Any] | None = None,
        confirmed: bool = False,
        **_: Any,
    ) -> Any:
        if not product_id:
            return "Error: product_id is required."
        updates = {k: v for k, v in (field_updates or {}).items() if k in _PRODUCT_FIELDS}
        if not updates:
            return (
                "Error: no valid fields provided. Allowed keys: "
                + ", ".join(_PRODUCT_FIELDS)
            )
        if "name" in updates:
            updates["name"] = (updates["name"] or "").strip()
            if not updates["name"]:
                return "Error: name cannot be empty."
        if "price" in updates and updates["price"] is not None and updates["price"] < 0:
            return "Error: price must be >= 0."
        if not confirmed:
            return _NEEDS_CONFIRMATION

        result = (
            self.supabase.table("products")
            .update(updates)
            .eq("id", product_id)
            .eq("tenant_id", self.tenant_id)
            .execute()
        )
        if not result.data:
            return "Error: product not found for this tenant."
        return {"ok": True, "id": product_id, "updated": list(updates.keys())}


@tool_parameters(
    tool_parameters_schema(
        product_id=StringSchema("UUID of the product to delete", min_length=1),
        confirmed=BooleanSchema(default=False),
        required=["product_id"],
    )
)
class DeleteProductTool(_BotConfigTool):
    @property
    def name(self) -> str:
        return "delete_product"

    @property
    def description(self) -> str:
        return "Permanently delete a product from the catalog. Confirm before applying."

    async def execute(
        self,
        product_id: str = "",
        confirmed: bool = False,
        **_: Any,
    ) -> Any:
        if not product_id:
            return "Error: product_id is required."
        if not confirmed:
            return _NEEDS_CONFIRMATION

        result = (
            self.supabase.table("products")
            .delete()
            .eq("id", product_id)
            .eq("tenant_id", self.tenant_id)
            .execute()
        )
        if not result.data:
            return "Error: product not found for this tenant."
        return {"ok": True, "id": product_id, "deleted": True}


# --- registry factory ----------------------------------------------------


def build_manager_registry(supabase: Client, tenant_id: str) -> ToolRegistry:
    """Return a ToolRegistry pre-loaded with the manager toolkit for this tenant."""
    registry = ToolRegistry()
    registry.register(GetBotConfigTool(supabase, tenant_id))
    registry.register(ListRecentMessagesTool(supabase, tenant_id))
    registry.register(UpdateSystemPromptTool(supabase, tenant_id))
    registry.register(UpdateWelcomeMessageTool(supabase, tenant_id))
    registry.register(SetBotEnabledTool(supabase, tenant_id))
    registry.register(AddAdminPhoneTool(supabase, tenant_id))
    registry.register(RemoveAdminPhoneTool(supabase, tenant_id))
    registry.register(GetBusinessInfoTool(supabase, tenant_id))
    registry.register(UpdateBusinessInfoTool(supabase, tenant_id))
    registry.register(ListProductsTool(supabase, tenant_id))
    registry.register(AddProductTool(supabase, tenant_id))
    registry.register(UpdateProductTool(supabase, tenant_id))
    registry.register(DeleteProductTool(supabase, tenant_id))
    return registry

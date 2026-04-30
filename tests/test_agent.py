"""Unit tests for the nanobot-backed agent layer.

Covers:
- manager_tools confirmation gate (write tools refuse without confirmed=true).
- agent_runtime message construction (system prompt + history).

Does NOT make real Anthropic calls.
"""

from __future__ import annotations

import asyncio
import unittest
from copy import deepcopy
from unittest.mock import MagicMock

from app.services import agent_runtime
from app.services.agent_core import (
    AgentResponse,
    Tool,
    ToolCall,
    ToolRegistry,
    StringSchema,
    tool_parameters,
    tool_parameters_schema,
)
from app.services.client_tools import (
    ListAvailableProductsTool,
    LookupBusinessInfoTool,
    build_client_registry,
)
from app.services.manager_tools import (
    AddAdminPhoneTool,
    AddProductTool,
    DeleteProductTool,
    GetBotConfigTool,
    GetBusinessInfoTool,
    ListProductsTool,
    RemoveAdminPhoneTool,
    SetBotEnabledTool,
    UpdateBusinessInfoTool,
    UpdateProductTool,
    UpdateSystemPromptTool,
    UpdateWelcomeMessageTool,
    build_manager_registry,
    normalize_phone,
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _FakeSupabase:
    """Minimal stub: records every chained call so we can assert on writes."""

    def __init__(self, single_data=None, list_data=None):
        self._single_data = single_data or {}
        self._list_data = list_data or []
        self.updates: list[dict] = []
        self.update_filters: list[tuple[str, str]] = []
        self.inserts: list[dict] = []
        self.deletes: int = 0

    def table(self, _name):
        return self

    def select(self, _fields):
        return self

    def update(self, payload):
        self.updates.append(payload)
        return self

    def insert(self, payload):
        self.inserts.append(payload)
        return self

    def delete(self):
        self.deletes += 1
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, _n):
        return self

    def eq(self, key, value):
        self.update_filters.append((key, value))
        return self

    def single(self):
        return self

    def execute(self):
        result = MagicMock()
        if self._list_data:
            result.data = self._list_data
        else:
            result.data = self._single_data
        return result


class ManagerToolsConfirmationTests(unittest.TestCase):
    """Write tools must refuse to run without confirmed=true."""

    def test_update_system_prompt_refuses_without_confirmation(self):
        sb = _FakeSupabase()
        tool = UpdateSystemPromptTool(sb, tenant_id="t1")
        out = _run(tool.execute(new_prompt="nuevo prompt"))
        self.assertIsInstance(out, str)
        self.assertIn("confirmation required", out)
        self.assertEqual(sb.updates, [])  # no DB write happened

    def test_update_system_prompt_writes_when_confirmed(self):
        sb = _FakeSupabase()
        tool = UpdateSystemPromptTool(sb, tenant_id="t1")
        out = _run(tool.execute(new_prompt="nuevo prompt", confirmed=True))
        self.assertEqual(out["ok"], True)
        self.assertEqual(sb.updates, [{"system_prompt": "nuevo prompt"}])
        self.assertIn(("tenant_id", "t1"), sb.update_filters)

    def test_set_bot_enabled_refuses_without_confirmation(self):
        sb = _FakeSupabase()
        tool = SetBotEnabledTool(sb, tenant_id="t1")
        out = _run(tool.execute(enabled=False))
        self.assertIn("confirmation required", out)
        self.assertEqual(sb.updates, [])

    def test_update_welcome_message_writes_when_confirmed(self):
        sb = _FakeSupabase()
        tool = UpdateWelcomeMessageTool(sb, tenant_id="t1")
        out = _run(tool.execute(new_message="hola!", confirmed=True))
        self.assertEqual(out, {"ok": True, "field": "welcome_message"})
        self.assertEqual(sb.updates, [{"welcome_message": "hola!"}])

    def test_get_bot_config_does_not_write(self):
        sb = _FakeSupabase(
            single_data={"system_prompt": "x", "bot_enabled": True}
        )
        tool = GetBotConfigTool(sb, tenant_id="t1")
        out = _run(tool.execute())
        self.assertEqual(out["system_prompt"], "x")
        self.assertEqual(sb.updates, [])


class ManagerRegistryTests(unittest.TestCase):
    def test_registry_has_expected_tools(self):
        registry = build_manager_registry(_FakeSupabase(), tenant_id="t1")
        names = set(registry.tool_names)
        self.assertEqual(
            names,
            {
                "get_bot_config",
                "list_recent_messages",
                "update_system_prompt",
                "update_welcome_message",
                "set_bot_enabled",
                "add_admin_phone",
                "remove_admin_phone",
                "get_business_info",
                "update_business_info",
                "list_products",
                "add_product",
                "update_product",
                "delete_product",
            },
        )


class ClientRegistryTests(unittest.TestCase):
    def test_client_registry_has_expected_read_only_tools(self):
        registry = build_client_registry(_FakeSupabase(), tenant_id="t1")
        names = set(registry.tool_names)
        self.assertEqual(names, {"lookup_business_info", "list_available_products"})

    def test_lookup_business_info_returns_data(self):
        sb = _FakeSupabase(list_data=[{"name": "Tienda", "hours": "9-18"}])
        tool = LookupBusinessInfoTool(sb, tenant_id="t1")
        out = _run(tool.execute())
        self.assertEqual(out["name"], "Tienda")
        self.assertEqual(sb.updates, [])

    def test_lookup_business_info_returns_empty_when_no_row(self):
        sb = _FakeSupabase()
        tool = LookupBusinessInfoTool(sb, tenant_id="t1")
        out = _run(tool.execute())
        self.assertEqual(out["name"], "")
        self.assertEqual(sb.updates, [])

    def test_list_available_products_filters(self):
        sb = _FakeSupabase(list_data=[{"name": "Pizza", "price": 50, "available": True}])
        tool = ListAvailableProductsTool(sb, tenant_id="t1")
        out = _run(tool.execute())
        self.assertEqual(len(out), 1)
        self.assertIn(("available", True), sb.update_filters)
        self.assertIn(("tenant_id", "t1"), sb.update_filters)


class BusinessInfoToolsTests(unittest.TestCase):
    def test_update_business_info_refuses_without_confirmation(self):
        sb = _FakeSupabase(list_data=[{"id": "b1"}])
        tool = UpdateBusinessInfoTool(sb, tenant_id="t1")
        out = _run(tool.execute(field_updates={"name": "Mi Tienda"}))
        self.assertIn("confirmation required", out)
        self.assertEqual(sb.updates, [])

    def test_update_business_info_writes_when_confirmed(self):
        sb = _FakeSupabase(list_data=[{"id": "b1"}])
        tool = UpdateBusinessInfoTool(sb, tenant_id="t1")
        out = _run(
            tool.execute(
                field_updates={"name": "Mi Tienda", "hours": "9-18"},
                confirmed=True,
            )
        )
        self.assertEqual(out["ok"], True)
        self.assertEqual(set(out["updated"]), {"name", "hours"})
        self.assertEqual(sb.updates, [{"name": "Mi Tienda", "hours": "9-18"}])

    def test_update_business_info_rejects_empty_updates(self):
        sb = _FakeSupabase(list_data=[{"id": "b1"}])
        tool = UpdateBusinessInfoTool(sb, tenant_id="t1")
        out = _run(tool.execute(field_updates={}, confirmed=True))
        self.assertIsInstance(out, str)
        self.assertIn("Error", out)
        self.assertEqual(sb.updates, [])

    def test_update_business_info_filters_unknown_keys(self):
        sb = _FakeSupabase(list_data=[{"id": "b1"}])
        tool = UpdateBusinessInfoTool(sb, tenant_id="t1")
        out = _run(
            tool.execute(
                field_updates={"name": "X", "evil": "drop tables"},
                confirmed=True,
            )
        )
        self.assertEqual(out["ok"], True)
        self.assertEqual(sb.updates, [{"name": "X"}])

    def test_get_business_info_does_not_write(self):
        sb = _FakeSupabase(list_data=[{"name": "X"}])
        tool = GetBusinessInfoTool(sb, tenant_id="t1")
        out = _run(tool.execute())
        self.assertEqual(out["name"], "X")
        self.assertEqual(sb.updates, [])

    def test_get_business_info_returns_empty_defaults_when_missing(self):
        sb = _FakeSupabase()
        tool = GetBusinessInfoTool(sb, tenant_id="t1")
        out = _run(tool.execute())
        self.assertEqual(out["name"], "")
        self.assertEqual(out["address"], "")
        self.assertEqual(sb.updates, [])


class ProductToolsTests(unittest.TestCase):
    def test_add_product_refuses_without_confirmation(self):
        sb = _FakeSupabase(list_data=[{"id": "p1", "name": "Pizza"}])
        tool = AddProductTool(sb, tenant_id="t1")
        out = _run(tool.execute(name="Pizza"))
        self.assertIn("confirmation required", out)
        self.assertEqual(sb.inserts, [])

    def test_add_product_rejects_empty_name(self):
        sb = _FakeSupabase()
        tool = AddProductTool(sb, tenant_id="t1")
        out = _run(tool.execute(name="  ", confirmed=True))
        self.assertIn("Error", out)
        self.assertEqual(sb.inserts, [])

    def test_add_product_rejects_negative_price(self):
        sb = _FakeSupabase()
        tool = AddProductTool(sb, tenant_id="t1")
        out = _run(tool.execute(name="Pizza", price=-1, confirmed=True))
        self.assertIn("Error", out)
        self.assertIn("price", out)
        self.assertEqual(sb.inserts, [])

    def test_add_product_inserts_when_confirmed(self):
        sb = _FakeSupabase(list_data=[{"id": "p1"}])
        tool = AddProductTool(sb, tenant_id="t1")
        out = _run(
            tool.execute(
                name="Pizza",
                description="grande",
                price=50.0,
                confirmed=True,
            )
        )
        self.assertEqual(out["ok"], True)
        self.assertEqual(sb.inserts, [
            {
                "tenant_id": "t1",
                "name": "Pizza",
                "description": "grande",
                "price": 50.0,
                "available": True,
            }
        ])

    def test_update_product_refuses_without_confirmation(self):
        sb = _FakeSupabase(list_data=[{"id": "p1"}])
        tool = UpdateProductTool(sb, tenant_id="t1")
        out = _run(
            tool.execute(product_id="p1", field_updates={"name": "Nueva Pizza"})
        )
        self.assertIn("confirmation required", out)
        self.assertEqual(sb.updates, [])

    def test_update_product_rejects_empty_name_when_provided(self):
        sb = _FakeSupabase(list_data=[{"id": "p1"}])
        tool = UpdateProductTool(sb, tenant_id="t1")
        out = _run(
            tool.execute(product_id="p1", field_updates={"name": "   "}, confirmed=True)
        )
        self.assertIn("Error", out)
        self.assertEqual(sb.updates, [])

    def test_update_product_rejects_negative_price(self):
        sb = _FakeSupabase(list_data=[{"id": "p1"}])
        tool = UpdateProductTool(sb, tenant_id="t1")
        out = _run(
            tool.execute(product_id="p1", field_updates={"price": -5}, confirmed=True)
        )
        self.assertIn("Error", out)
        self.assertEqual(sb.updates, [])

    def test_update_product_writes_when_confirmed(self):
        sb = _FakeSupabase(list_data=[{"id": "p1", "name": "Pizza"}])
        tool = UpdateProductTool(sb, tenant_id="t1")
        out = _run(
            tool.execute(
                product_id="p1",
                field_updates={"available": False, "price": 60},
                confirmed=True,
            )
        )
        self.assertEqual(out["ok"], True)
        self.assertEqual(sb.updates, [{"available": False, "price": 60}])

    def test_update_product_filters_unknown_keys(self):
        sb = _FakeSupabase(list_data=[{"id": "p1"}])
        tool = UpdateProductTool(sb, tenant_id="t1")
        out = _run(
            tool.execute(
                product_id="p1",
                field_updates={"price": 10, "tenant_id": "stolen"},
                confirmed=True,
            )
        )
        self.assertEqual(out["ok"], True)
        self.assertEqual(sb.updates, [{"price": 10}])

    def test_delete_product_refuses_without_confirmation(self):
        sb = _FakeSupabase(list_data=[{"id": "p1"}])
        tool = DeleteProductTool(sb, tenant_id="t1")
        out = _run(tool.execute(product_id="p1"))
        self.assertIn("confirmation required", out)
        self.assertEqual(sb.deletes, 0)

    def test_delete_product_deletes_when_confirmed(self):
        sb = _FakeSupabase(list_data=[{"id": "p1"}])
        tool = DeleteProductTool(sb, tenant_id="t1")
        out = _run(tool.execute(product_id="p1", confirmed=True))
        self.assertEqual(out["ok"], True)
        self.assertEqual(sb.deletes, 1)

    def test_list_products_does_not_write(self):
        sb = _FakeSupabase(list_data=[{"id": "p1", "name": "Pizza"}])
        tool = ListProductsTool(sb, tenant_id="t1")
        out = _run(tool.execute())
        self.assertEqual(len(out), 1)
        self.assertEqual(sb.updates, [])


class NormalizePhoneTests(unittest.TestCase):
    def test_strips_plus_and_spaces(self):
        self.assertEqual(normalize_phone("+52 1 234-567 8900"), "5212345678900")

    def test_empty_input_returns_empty(self):
        self.assertEqual(normalize_phone(""), "")
        self.assertEqual(normalize_phone(None), "")  # type: ignore[arg-type]

    def test_no_digits_returns_empty(self):
        self.assertEqual(normalize_phone("abc"), "")


class AdminPhoneToolsTests(unittest.TestCase):
    def test_add_admin_phone_refuses_without_confirmation(self):
        sb = _FakeSupabase(single_data={"admin_phones": []})
        tool = AddAdminPhoneTool(sb, tenant_id="t1")
        out = _run(tool.execute(phone="+52 234 567 8900"))
        self.assertIn("confirmation required", out)
        self.assertEqual(sb.updates, [])

    def test_add_admin_phone_normalizes_and_appends(self):
        sb = _FakeSupabase(single_data={"admin_phones": ["111111111"]})
        tool = AddAdminPhoneTool(sb, tenant_id="t1")
        out = _run(tool.execute(phone="+52 234-567-8900", confirmed=True))
        # +52 234-567-8900 -> digits only: 522345678900
        self.assertEqual(out["added"], "522345678900")
        self.assertEqual(sb.updates, [{"admin_phones": ["111111111", "522345678900"]}])

    def test_add_admin_phone_dedupes(self):
        sb = _FakeSupabase(single_data={"admin_phones": ["5212345"]})
        tool = AddAdminPhoneTool(sb, tenant_id="t1")
        out = _run(tool.execute(phone="+52 1-2345", confirmed=True))
        self.assertEqual(out.get("noop"), True)
        self.assertEqual(sb.updates, [])  # nothing written

    def test_add_admin_phone_rejects_empty_after_normalization(self):
        sb = _FakeSupabase(single_data={"admin_phones": []})
        tool = AddAdminPhoneTool(sb, tenant_id="t1")
        out = _run(tool.execute(phone="abc", confirmed=True))
        self.assertIsInstance(out, str)
        self.assertIn("Error", out)
        self.assertEqual(sb.updates, [])

    def test_remove_admin_phone_drops_match(self):
        sb = _FakeSupabase(single_data={"admin_phones": ["5212345", "999"]})
        tool = RemoveAdminPhoneTool(sb, tenant_id="t1")
        out = _run(tool.execute(phone="+52 1-2345", confirmed=True))
        self.assertEqual(out["removed"], "5212345")
        self.assertEqual(sb.updates, [{"admin_phones": ["999"]}])

    def test_remove_admin_phone_noop_when_absent(self):
        sb = _FakeSupabase(single_data={"admin_phones": ["999"]})
        tool = RemoveAdminPhoneTool(sb, tenant_id="t1")
        out = _run(tool.execute(phone="111", confirmed=True))
        self.assertEqual(out.get("noop"), True)
        self.assertEqual(sb.updates, [])


class AgentRuntimeMessageBuildTests(unittest.TestCase):
    def test_system_prompt_first_then_conversation(self):
        msgs = agent_runtime._build_initial_messages(
            "you are helpful",
            [
                {"role": "user", "content": "hola"},
                {"role": "assistant", "content": "hola, ¿en qué te ayudo?"},
                {"role": "user", "content": "quiero info"},
            ],
        )
        self.assertEqual(msgs[0], {"role": "system", "content": "you are helpful"})
        self.assertEqual(len(msgs), 4)
        self.assertEqual(msgs[-1]["content"], "quiero info")

    def test_empty_content_messages_are_skipped(self):
        msgs = agent_runtime._build_initial_messages(
            "sys",
            [
                {"role": "user", "content": ""},
                {"role": "user", "content": "real msg"},
            ],
        )
        # system + 1 real msg
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[1]["content"], "real msg")


@tool_parameters(
    tool_parameters_schema(value=StringSchema("Value to echo"), required=["value"])
)
class _EchoTool(Tool):
    @property
    def name(self) -> str:
        return "echo"

    @property
    def description(self) -> str:
        return "Echo a value for tests."

    async def execute(self, value: str, **_):
        return {"echoed": value}


class _FakeProvider:
    def __init__(self):
        self.calls = []

    async def chat(self, *, messages, tools, model, max_tokens):
        self.calls.append(
            {
                "messages": deepcopy(messages),
                "tools": tools,
                "model": model,
                "max_tokens": max_tokens,
            }
        )
        if len(self.calls) == 1:
            return AgentResponse(
                text="",
                tool_calls=[
                    ToolCall(id="toolu_test", name="echo", input={"value": "hola"})
                ],
            )
        return AgentResponse(text="listo")


class AgentRuntimeRespondTests(unittest.TestCase):
    def test_respond_executes_tool_and_returns_final_text(self):
        provider = _FakeProvider()
        registry = ToolRegistry()
        registry.register(_EchoTool())

        original_get_provider = agent_runtime._get_provider
        agent_runtime._get_provider = lambda _model: provider
        try:
            out = _run(
                agent_runtime.respond(
                    tenant_id="t1",
                    user_phone="59170000001",
                    mode="client",
                    model="claude-test",
                    system_prompt="sys",
                    conversation=[{"role": "user", "content": "hola"}],
                    tools=registry,
                )
            )
        finally:
            agent_runtime._get_provider = original_get_provider

        self.assertEqual(out, "listo")
        self.assertEqual(len(provider.calls), 2)
        second_messages = provider.calls[1]["messages"]
        self.assertEqual(second_messages[-1]["role"], "user")
        self.assertEqual(second_messages[-1]["content"][0]["type"], "tool_result")
        self.assertIn("hola", second_messages[-1]["content"][0]["content"])


if __name__ == "__main__":
    unittest.main()

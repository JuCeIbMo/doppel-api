"""Unit tests for the isolated ai_core service (Agno + Gemini runtime).

Runs only where `agno` is installed (the ai-core venv / container). The global
test environment lacks agno, so these tests are skipped there.
"""

import os

# ai_core.config instantiates Settings() at import time and requires these.
os.environ.setdefault("DOPPEL_API_URL", "http://doppel-api:8000")
os.environ.setdefault("DOPPEL_INTERNAL_API_TOKEN", "test-internal-token")

import asyncio
import unittest
from unittest.mock import patch

import pytest

pytest.importorskip("agno")

import httpx
from agno.tools import Function

from ai_core import doppel_tools, runtime
from ai_core.contracts import TurnResponse


def _transport() -> httpx.MockTransport:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/internal/ai/tools":
            return httpx.Response(
                200,
                json={
                    "tools": [
                        {
                            "name": "list_products",
                            "description": "List products",
                            "input_schema": {
                                "type": "object",
                                "properties": {},
                                "required": [],
                            },
                            "read_only": True,
                        }
                    ]
                },
            )
        if request.url.path == "/internal/ai/tools/execute":
            return httpx.Response(200, json={"ok": True, "result": [{"sku": "A1"}]})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


class BuildRemoteToolsTest(unittest.TestCase):
    def test_builds_agno_functions_and_executes_them(self):
        async def run():
            async with httpx.AsyncClient(
                transport=_transport(), base_url="http://doppel-api:8000"
            ) as client:
                doppel_tools.settings.DOPPEL_API_URL = "http://doppel-api:8000"
                tools = await doppel_tools.build_remote_tools(
                    client, tenant_id="t1", mode="client"
                )
                self.assertEqual(len(tools), 1)
                self.assertIsInstance(tools[0], Function)
                self.assertEqual(tools[0].name, "list_products")
                self.assertEqual(tools[0].parameters["type"], "object")
                return await tools[0].entrypoint()

        result = asyncio.run(run())
        self.assertEqual(result, [{"sku": "A1"}])


class RespondTest(unittest.TestCase):
    def test_respond_builds_session_and_returns_reply(self):
        captured = {}

        class FakeRun:
            content = "Hola, soy el bot"
            tools = []
            metrics = None

        class FakeAgent:
            def __init__(self, **kwargs):
                captured["init"] = kwargs

            async def arun(self, content, **kwargs):
                captured["arun"] = {"content": content, **kwargs}
                return FakeRun()

        async def run():
            async with httpx.AsyncClient(
                transport=_transport(), base_url="http://doppel-api:8000"
            ) as client:
                runtime.settings.DOPPEL_API_URL = "http://doppel-api:8000"
                with patch.object(runtime, "Agent", FakeAgent):
                    return await runtime.respond(
                        client,
                        tenant_id="t1",
                        mode="client",
                        sender_id="591700",
                        content="hola",
                        system_prompt="Sé amable",
                        model="claude-sonnet-4",
                        images=None,
                    )

        result = asyncio.run(run())
        self.assertIsInstance(result, TurnResponse)
        self.assertEqual(result.reply, "Hola, soy el bot")
        self.assertEqual(captured["arun"]["session_id"], "tenant:t1:phone:591700")
        self.assertEqual(captured["init"]["instructions"], "Sé amable")

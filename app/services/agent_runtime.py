"""Bridge from Doppel webhook to the local tool-calling AgentRunner.

This is the single entry point that the webhook calls per inbound message.
Keeps the agent runner shielded behind a stable API so the rest of the
backend stays naive about agent internals.
"""

from __future__ import annotations

import logging
from typing import Literal

from app.config import settings
from app.services.agent_core import (
    AgentRunner,
    AgentRunResult,
    AgentRunSpec,
    AnthropicProvider,
    ToolRegistry,
)

logger = logging.getLogger("doppel.agent_runtime")

Mode = Literal["manager", "client"]

_MAX_ITERATIONS_CLIENT = 4
_MAX_ITERATIONS_MANAGER = 8
_MAX_TOKENS = 1024
_MAX_TOOL_RESULT_CHARS = 8000

_provider_cache: dict[str, AnthropicProvider] = {}


def _get_provider(model: str) -> AnthropicProvider:
    if model not in _provider_cache:
        _provider_cache[model] = AnthropicProvider(
            api_key=settings.ANTHROPIC_API_KEY,
            default_model=model,
        )
    return _provider_cache[model]


def _build_initial_messages(
    system_prompt: str,
    conversation: list[dict[str, str]],
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for msg in conversation:
        if msg.get("content"):
            messages.append({"role": msg["role"], "content": msg["content"]})
    return messages


async def respond(
    *,
    tenant_id: str,
    user_phone: str,
    mode: Mode,
    model: str,
    system_prompt: str,
    conversation: list[dict[str, str]],
    tools: ToolRegistry | None = None,
) -> str:
    """Run the agent loop once and return the final assistant text.

    `conversation` is chronological, role/content pairs (already mapped from
    Doppel's `messages` table). `system_prompt` becomes the system message.
    """
    provider = _get_provider(model)
    registry = tools if tools is not None else ToolRegistry()
    spec = AgentRunSpec(
        initial_messages=_build_initial_messages(system_prompt, conversation),
        tools=registry,
        model=model,
        max_iterations=(
            _MAX_ITERATIONS_MANAGER if mode == "manager" else _MAX_ITERATIONS_CLIENT
        ),
        max_tool_result_chars=_MAX_TOOL_RESULT_CHARS,
        max_tokens=_MAX_TOKENS,
        session_key=f"tenant:{tenant_id}:phone:{user_phone}",
    )

    result: AgentRunResult = await AgentRunner(provider).run(spec)
    if result.error:
        logger.warning(
            "agent error tenant=%s phone=%s mode=%s stop=%s err=%s",
            tenant_id, user_phone, mode, result.stop_reason, result.error,
        )
    return result.final_content or ""

from __future__ import annotations

from typing import Any

import httpx

from ai_core.config import settings
from ai_core.contracts import TurnResponse
from ai_core.doppel_tools import build_remote_registry
from app.services.agent_core import AgentRunSpec, AgentRunner, AnthropicProvider

_provider_cache: dict[str, AnthropicProvider] = {}


def _get_provider(model: str) -> AnthropicProvider:
    if model not in _provider_cache:
        _provider_cache[model] = AnthropicProvider(
            api_key=settings.ANTHROPIC_API_KEY,
            default_model=model,
        )
    return _provider_cache[model]


def _max_iterations(mode: str) -> int:
    if mode == "manager":
        return settings.AI_CORE_MANAGER_MAX_ITERATIONS
    return settings.AI_CORE_CLIENT_MAX_ITERATIONS


async def respond(
    http_client: httpx.AsyncClient,
    *,
    tenant_id: str,
    mode: str,
    sender_id: str,
    content: str,
    conversation: list[dict[str, str]],
    system_prompt: str,
    model: str,
) -> TurnResponse:
    registry = await build_remote_registry(
        http_client,
        tenant_id=tenant_id,
        mode=mode,
    )
    spec = AgentRunSpec(
        initial_messages=[{"role": "system", "content": system_prompt}, *conversation],
        tools=registry,
        model=model,
        max_iterations=_max_iterations(mode),
        max_tool_result_chars=settings.AI_CORE_MAX_TOOL_RESULT_CHARS,
        max_tokens=settings.AI_CORE_MAX_TOKENS,
        session_key=f"tenant:{tenant_id}:phone:{sender_id}",
    )
    result = await AgentRunner(_get_provider(model)).run(spec)
    return TurnResponse(
        reply=result.final_content or "",
        stop_reason=result.stop_reason,
        tools_used=result.tools_used,
        usage=result.usage,
        error=result.error,
    )

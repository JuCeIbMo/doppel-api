from __future__ import annotations

from typing import Any

import httpx
from agno.agent import Agent
from agno.db.postgres import PostgresDb
from agno.media import Image
from agno.models.google import Gemini

from ai_core.config import settings
from ai_core.contracts import TurnResponse
from ai_core.doppel_tools import build_remote_tools

_db: PostgresDb | None = (
    PostgresDb(db_url=settings.AI_CORE_DB_URL) if settings.AI_CORE_DB_URL else None
)


def _resolve_model(model: str) -> str:
    """Use the requested model only if it's a Gemini id; otherwise fall back to
    the configured default (the API may still send legacy Anthropic ids)."""

    return model if model.startswith("gemini") else settings.AI_CORE_GEMINI_MODEL


def _tools_used(run: Any) -> list[str]:
    executions = getattr(run, "tools", None) or []
    names: list[str] = []
    for item in executions:
        name = getattr(item, "tool_name", None) or getattr(item, "name", None)
        if name:
            names.append(name)
    return names


async def respond(
    http_client: httpx.AsyncClient,
    *,
    tenant_id: str,
    mode: str,
    sender_id: str,
    content: str,
    system_prompt: str,
    model: str,
    images: list[Image] | None = None,
) -> TurnResponse:
    tools = await build_remote_tools(http_client, tenant_id=tenant_id, mode=mode)
    agent = Agent(
        model=Gemini(id=_resolve_model(model), api_key=settings.GOOGLE_API_KEY or None),
        db=_db,
        tools=tools,
        instructions=system_prompt,
        add_history_to_context=True,
        num_history_runs=settings.AI_CORE_NUM_HISTORY_RUNS,
        markdown=False,
    )
    session_id = f"tenant:{tenant_id}:phone:{sender_id}"
    try:
        run = await agent.arun(content, session_id=session_id, images=images or None)
    except Exception as exc:  # noqa: BLE001 - surface runtime errors to the caller
        return TurnResponse(reply="", stop_reason="error", error=str(exc))

    return TurnResponse(
        reply=getattr(run, "content", "") or "",
        stop_reason="completed",
        tools_used=_tools_used(run),
    )

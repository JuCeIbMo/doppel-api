from __future__ import annotations

from typing import Any, Callable

import httpx
from agno.tools import Function

from ai_core.config import settings
from ai_core.contracts import ToolExecuteResponse, ToolListResponse


def _make_entrypoint(
    http_client: httpx.AsyncClient, *, tenant_id: str, mode: str, name: str
) -> Callable[..., Any]:
    async def _call(**kwargs: Any) -> Any:
        response = await http_client.post(
            f"{settings.DOPPEL_API_URL.rstrip('/')}/internal/ai/tools/execute",
            json={
                "tenant_id": tenant_id,
                "mode": mode,
                "tool_name": name,
                "arguments": kwargs,
            },
            headers={"Authorization": f"Bearer {settings.DOPPEL_INTERNAL_API_TOKEN}"},
        )
        response.raise_for_status()
        payload = ToolExecuteResponse.model_validate(response.json())
        if not payload.ok:
            return f"Error executing {name}: {payload.error or 'unknown error'}"
        return payload.result

    _call.__name__ = name
    return _call


async def build_remote_tools(
    http_client: httpx.AsyncClient, *, tenant_id: str, mode: str
) -> list[Function]:
    """Fetch the tenant/mode tool registry from Doppel and wrap each entry as an
    Agno Function whose entrypoint executes the tool back over HTTP."""

    response = await http_client.get(
        f"{settings.DOPPEL_API_URL.rstrip('/')}/internal/ai/tools",
        params={"tenant_id": tenant_id, "mode": mode},
        headers={"Authorization": f"Bearer {settings.DOPPEL_INTERNAL_API_TOKEN}"},
    )
    response.raise_for_status()
    payload = ToolListResponse.model_validate(response.json())

    tools: list[Function] = []
    for definition in payload.tools:
        tools.append(
            Function(
                name=definition.name,
                description=definition.description,
                parameters=definition.input_schema,
                entrypoint=_make_entrypoint(
                    http_client, tenant_id=tenant_id, mode=mode, name=definition.name
                ),
            )
        )
    return tools

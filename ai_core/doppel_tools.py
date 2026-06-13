from __future__ import annotations

from typing import Any

import httpx

from ai_core.config import settings
from ai_core.contracts import ToolDefinition, ToolExecuteResponse, ToolListResponse
from app.services.agent_core import Tool, ToolRegistry


class RemoteTool(Tool):
    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient,
        tenant_id: str,
        mode: str,
        definition: ToolDefinition,
    ) -> None:
        self.http_client = http_client
        self.tenant_id = tenant_id
        self.mode = mode
        self.definition = definition

    @property
    def name(self) -> str:
        return self.definition.name

    @property
    def description(self) -> str:
        return self.definition.description

    @property
    def parameters(self) -> dict[str, Any]:
        return dict(self.definition.input_schema)

    @property
    def read_only(self) -> bool:
        return self.definition.read_only

    async def execute(self, **kwargs: Any) -> Any:
        response = await self.http_client.post(
            f"{settings.DOPPEL_API_URL.rstrip('/')}/internal/ai/tools/execute",
            json={
                "tenant_id": self.tenant_id,
                "mode": self.mode,
                "tool_name": self.name,
                "arguments": kwargs,
            },
            headers={"Authorization": f"Bearer {settings.DOPPEL_INTERNAL_API_TOKEN}"},
        )
        response.raise_for_status()
        payload = ToolExecuteResponse.model_validate(response.json())
        if not payload.ok:
            return f"Error executing {self.name}: {payload.error or 'unknown error'}"
        return payload.result


async def build_remote_registry(
    http_client: httpx.AsyncClient,
    *,
    tenant_id: str,
    mode: str,
) -> ToolRegistry:
    response = await http_client.get(
        f"{settings.DOPPEL_API_URL.rstrip('/')}/internal/ai/tools",
        params={"tenant_id": tenant_id, "mode": mode},
        headers={"Authorization": f"Bearer {settings.DOPPEL_INTERNAL_API_TOKEN}"},
    )
    response.raise_for_status()
    payload = ToolListResponse.model_validate(response.json())

    registry = ToolRegistry()
    for definition in payload.tools:
        registry.register(
            RemoteTool(
                http_client=http_client,
                tenant_id=tenant_id,
                mode=mode,
                definition=definition,
            )
        )
    return registry

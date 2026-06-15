from __future__ import annotations

from typing import Any, Callable

import httpx
from agno.tools import Function

from ai_core.config import settings
from ai_core.contracts import ToolExecuteResponse, ToolListResponse

# Gemini's function-calling schema is a strict subset of JSON Schema. Keywords
# outside this set (minLength, default, additionalProperties, etc.) make Gemini
# drop the property server-side, leaving `required` dangling -> 400
# "required[0]: property is not defined". We keep only supported keywords.
_GEMINI_ALLOWED_KEYS = {
    "type",
    "format",
    "description",
    "nullable",
    "enum",
    "items",
    "properties",
    "required",
    "anyOf",
    "minItems",
    "maxItems",
}


def _sanitize_schema(node: Any) -> Any:
    """Recursively reduce a JSON schema to the subset Gemini accepts."""

    if not isinstance(node, dict):
        return node

    out: dict[str, Any] = {}
    for key, value in node.items():
        if key not in _GEMINI_ALLOWED_KEYS:
            continue
        if key == "properties" and isinstance(value, dict):
            out[key] = {k: _sanitize_schema(v) for k, v in value.items()}
        elif key == "items":
            out[key] = _sanitize_schema(value)
        elif key == "anyOf" and isinstance(value, list):
            out[key] = [_sanitize_schema(v) for v in value]
        elif key == "type" and isinstance(value, list):
            # e.g. ["number", "null"] -> "number" + nullable
            non_null = [t for t in value if t != "null"]
            out["type"] = non_null[0] if non_null else "string"
            if "null" in value:
                out["nullable"] = True
        else:
            out[key] = value

    # Drop any `required` entry that no longer maps to a property.
    if "required" in out:
        props = out.get("properties", {})
        kept = [r for r in out["required"] if r in props]
        if kept:
            out["required"] = kept
        else:
            del out["required"]

    return out


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
                parameters=_sanitize_schema(definition.input_schema),
                entrypoint=_make_entrypoint(
                    http_client, tenant_id=tenant_id, mode=mode, name=definition.name
                ),
            )
        )
    return tools

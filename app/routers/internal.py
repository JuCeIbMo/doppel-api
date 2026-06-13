import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import require_internal_api_token
from app.models.schemas import (
    InternalToolDefinition,
    InternalToolExecuteRequest,
    InternalToolExecuteResponse,
    InternalToolListResponse,
)
from app.services.supabase_client import get_supabase
from app.services.tool_runtime import build_tool_registry

logger = logging.getLogger("doppel.internal")
router = APIRouter(prefix="/internal/ai", tags=["Internal AI"])


def _get_registry(*, tenant_id: str, mode: str):
    if mode not in {"client", "manager"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported mode. Expected 'client' or 'manager'.",
        )
    return build_tool_registry(
        supabase=get_supabase(),
        tenant_id=tenant_id,
        mode=mode,
    )


@router.get("/tools", response_model=InternalToolListResponse)
async def list_tools(
    tenant_id: str = Query(..., min_length=1),
    mode: str = Query(..., min_length=1),
    _auth: dict = Depends(require_internal_api_token),
):
    registry = _get_registry(tenant_id=tenant_id, mode=mode)
    tools = [
        InternalToolDefinition(
            name=tool.name,
            description=tool.description,
            input_schema=tool.parameters,
            read_only=tool.read_only,
        )
        for tool in registry._tools.values()
    ]
    return InternalToolListResponse(tools=tools)


@router.post("/tools/execute", response_model=InternalToolExecuteResponse)
async def execute_tool(
    data: InternalToolExecuteRequest,
    _auth: dict = Depends(require_internal_api_token),
):
    registry = _get_registry(tenant_id=data.tenant_id, mode=data.mode)
    tool = registry.get(data.tool_name)
    if tool is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown tool: {data.tool_name}",
        )

    try:
        result = await tool.execute(**data.arguments)
        return InternalToolExecuteResponse(ok=True, result=result)
    except Exception as exc:
        logger.exception("Internal tool execution failed tool=%s tenant=%s", data.tool_name, data.tenant_id)
        return InternalToolExecuteResponse(ok=False, error=str(exc))

from pydantic import BaseModel, Field


class ToolDefinition(BaseModel):
    name: str
    description: str
    input_schema: dict
    read_only: bool = False


class ToolListResponse(BaseModel):
    tools: list[ToolDefinition] = Field(default_factory=list)


class ToolExecuteResponse(BaseModel):
    ok: bool
    result: dict | list | str | None = None
    error: str | None = None


class TurnResponse(BaseModel):
    reply: str = ""
    stop_reason: str = "completed"
    tools_used: list[str] = Field(default_factory=list)
    usage: dict[str, int] = Field(default_factory=dict)
    error: str | None = None

"""Small Anthropic tool-calling runtime used by Doppel's WhatsApp agents.

This keeps Doppel independent from the full nanobot app package, whose channel
dependencies currently conflict with Supabase's realtime dependency tree.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable

import anthropic

logger = logging.getLogger("doppel.agent_core")


@dataclass(slots=True)
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass(slots=True)
class AgentResponse:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True)
class AgentRunSpec:
    initial_messages: list[dict[str, Any]]
    tools: "ToolRegistry"
    model: str
    max_iterations: int
    max_tool_result_chars: int
    max_tokens: int | None = None
    session_key: str | None = None


@dataclass(slots=True)
class AgentRunResult:
    final_content: str | None
    messages: list[dict[str, Any]]
    tools_used: list[str] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    stop_reason: str = "completed"
    error: str | None = None


class Schema(ABC):
    @abstractmethod
    def to_json_schema(self) -> dict[str, Any]:
        ...

    @staticmethod
    def fragment(value: Any) -> dict[str, Any]:
        to_json_schema = getattr(value, "to_json_schema", None)
        if callable(to_json_schema):
            return to_json_schema()
        if isinstance(value, dict):
            return value
        raise TypeError(f"Expected schema object or dict, got {type(value).__name__}")


class StringSchema(Schema):
    def __init__(
        self,
        description: str = "",
        *,
        min_length: int | None = None,
        max_length: int | None = None,
    ) -> None:
        self.description = description
        self.min_length = min_length
        self.max_length = max_length

    def to_json_schema(self) -> dict[str, Any]:
        schema: dict[str, Any] = {"type": "string"}
        if self.description:
            schema["description"] = self.description
        if self.min_length is not None:
            schema["minLength"] = self.min_length
        if self.max_length is not None:
            schema["maxLength"] = self.max_length
        return schema


class IntegerSchema(Schema):
    def __init__(
        self,
        value: int = 0,
        *,
        description: str = "",
        minimum: int | None = None,
        maximum: int | None = None,
    ) -> None:
        self.value = value
        self.description = description
        self.minimum = minimum
        self.maximum = maximum

    def to_json_schema(self) -> dict[str, Any]:
        schema: dict[str, Any] = {"type": "integer"}
        if self.description:
            schema["description"] = self.description
        if self.minimum is not None:
            schema["minimum"] = self.minimum
        if self.maximum is not None:
            schema["maximum"] = self.maximum
        return schema


class NumberSchema(Schema):
    def __init__(
        self,
        value: float = 0.0,
        *,
        description: str = "",
        minimum: float | None = None,
        maximum: float | None = None,
        nullable: bool = False,
    ) -> None:
        self.value = value
        self.description = description
        self.minimum = minimum
        self.maximum = maximum
        self.nullable = nullable

    def to_json_schema(self) -> dict[str, Any]:
        schema: dict[str, Any] = {"type": ["number", "null"] if self.nullable else "number"}
        if self.description:
            schema["description"] = self.description
        if self.minimum is not None:
            schema["minimum"] = self.minimum
        if self.maximum is not None:
            schema["maximum"] = self.maximum
        return schema


class BooleanSchema(Schema):
    def __init__(self, *, description: str = "", default: bool | None = None) -> None:
        self.description = description
        self.default = default

    def to_json_schema(self) -> dict[str, Any]:
        schema: dict[str, Any] = {"type": "boolean"}
        if self.description:
            schema["description"] = self.description
        if self.default is not None:
            schema["default"] = self.default
        return schema


class ObjectSchema(Schema):
    def __init__(
        self,
        properties: dict[str, Any] | None = None,
        *,
        required: list[str] | None = None,
        description: str = "",
        additional_properties: bool | dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        self.properties = dict(properties or {}, **kwargs)
        self.required = list(required or [])
        self.description = description
        self.additional_properties = additional_properties

    def to_json_schema(self) -> dict[str, Any]:
        schema: dict[str, Any] = {
            "type": "object",
            "properties": {
                key: Schema.fragment(value) for key, value in self.properties.items()
            },
        }
        if self.required:
            schema["required"] = self.required
        if self.description:
            schema["description"] = self.description
        if self.additional_properties is not None:
            schema["additionalProperties"] = self.additional_properties
        return schema


def tool_parameters_schema(
    *,
    required: list[str] | None = None,
    description: str = "",
    **properties: Any,
) -> dict[str, Any]:
    return ObjectSchema(
        required=required,
        description=description,
        **properties,
    ).to_json_schema()


def tool_parameters(schema: dict[str, Any]) -> Callable[[type["Tool"]], type["Tool"]]:
    def decorator(cls: type[Tool]) -> type[Tool]:
        frozen = deepcopy(schema)

        @property
        def parameters(self: Tool) -> dict[str, Any]:
            return deepcopy(frozen)

        cls.parameters = parameters  # type: ignore[assignment]
        abstract = getattr(cls, "__abstractmethods__", None)
        if abstract is not None and "parameters" in abstract:
            cls.__abstractmethods__ = frozenset(abstract - {"parameters"})  # type: ignore[misc]
        return cls

    return decorator


class Tool(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        ...

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        ...

    @property
    def read_only(self) -> bool:
        return False

    @abstractmethod
    async def execute(self, **kwargs: Any) -> Any:
        ...

    def to_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def get_definitions(self) -> list[dict[str, Any]]:
        return [tool.to_schema() for tool in self._tools.values()]

    async def execute(self, name: str, params: dict[str, Any]) -> Any:
        tool = self.get(name)
        if tool is None:
            return f"Error: Tool '{name}' not found. Available: {', '.join(self.tool_names)}"
        try:
            return await tool.execute(**params)
        except Exception as exc:
            logger.exception("Tool failed name=%s", name)
            return f"Error executing {name}: {exc}"

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())


class AnthropicProvider:
    def __init__(
        self,
        *,
        api_key: str | None,
        default_model: str,
    ) -> None:
        self.default_model = default_model
        kwargs = {"api_key": api_key} if api_key else {}
        self._client = anthropic.AsyncAnthropic(**kwargs)

    async def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str,
        max_tokens: int,
    ) -> AgentResponse:
        system, anthropic_messages = _split_system(messages)
        kwargs: dict[str, Any] = {
            "model": model or self.default_model,
            "max_tokens": max_tokens,
            "messages": anthropic_messages,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        response = await self._client.messages.create(**kwargs)
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in response.content:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                text_parts.append(getattr(block, "text", "") or "")
            elif block_type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=getattr(block, "id", ""),
                        name=getattr(block, "name", ""),
                        input=dict(getattr(block, "input", {}) or {}),
                    )
                )

        usage = {}
        if getattr(response, "usage", None):
            usage = {
                "prompt_tokens": int(getattr(response.usage, "input_tokens", 0) or 0),
                "completion_tokens": int(
                    getattr(response.usage, "output_tokens", 0) or 0
                ),
            }
        return AgentResponse(text="".join(text_parts).strip(), tool_calls=tool_calls, usage=usage)


class AgentRunner:
    def __init__(self, provider: Any) -> None:
        self.provider = provider

    async def run(self, spec: AgentRunSpec) -> AgentRunResult:
        messages = list(spec.initial_messages)
        tools_used: list[str] = []
        usage = {"prompt_tokens": 0, "completion_tokens": 0}

        try:
            for _ in range(spec.max_iterations):
                response = await self.provider.chat(
                    messages=messages,
                    tools=spec.tools.get_definitions(),
                    model=spec.model,
                    max_tokens=spec.max_tokens or 1024,
                )
                usage["prompt_tokens"] += response.usage.get("prompt_tokens", 0)
                usage["completion_tokens"] += response.usage.get("completion_tokens", 0)

                if not response.tool_calls:
                    if response.text:
                        messages.append({"role": "assistant", "content": response.text})
                    return AgentRunResult(
                        final_content=response.text,
                        messages=messages,
                        tools_used=tools_used,
                        usage=usage,
                    )

                assistant_blocks: list[dict[str, Any]] = []
                if response.text:
                    assistant_blocks.append({"type": "text", "text": response.text})
                for call in response.tool_calls:
                    tools_used.append(call.name)
                    assistant_blocks.append(
                        {
                            "type": "tool_use",
                            "id": call.id,
                            "name": call.name,
                            "input": call.input,
                        }
                    )
                messages.append({"role": "assistant", "content": assistant_blocks})

                tool_results = []
                for call in response.tool_calls:
                    result = await spec.tools.execute(call.name, call.input)
                    result_text = _format_tool_result(result)
                    if len(result_text) > spec.max_tool_result_chars:
                        result_text = result_text[: spec.max_tool_result_chars]
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": call.id,
                            "content": result_text,
                        }
                    )
                messages.append({"role": "user", "content": tool_results})

            final = "No pude completar la solicitud antes del limite de iteraciones."
            messages.append({"role": "assistant", "content": final})
            return AgentRunResult(
                final_content=final,
                messages=messages,
                tools_used=tools_used,
                usage=usage,
                stop_reason="max_iterations",
            )
        except Exception as exc:
            logger.exception("Agent run failed")
            return AgentRunResult(
                final_content="",
                messages=messages,
                tools_used=tools_used,
                usage=usage,
                stop_reason="error",
                error=str(exc),
            )


def _format_tool_result(result: Any) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False, default=str)


def _split_system(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    system_parts: list[str] = []
    conversation: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        content = message.get("content")
        if role == "system":
            if content:
                system_parts.append(str(content))
            continue
        if role in {"user", "assistant"}:
            conversation.append({"role": role, "content": content or ""})

    return "\n\n".join(system_parts), _merge_consecutive_messages(conversation)


def _merge_consecutive_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for message in messages:
        if merged and merged[-1]["role"] == message["role"]:
            merged[-1]["content"] = _merge_content(merged[-1]["content"], message["content"])
        else:
            merged.append(dict(message))
    return merged


def _merge_content(left: Any, right: Any) -> Any:
    if isinstance(left, str) and isinstance(right, str):
        return f"{left}\n\n{right}" if left else right
    left_blocks = left if isinstance(left, list) else [{"type": "text", "text": str(left)}]
    right_blocks = right if isinstance(right, list) else [{"type": "text", "text": str(right)}]
    return left_blocks + right_blocks

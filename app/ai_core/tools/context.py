from dataclasses import dataclass

from langchain.tools import tool
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, create_model
from pydantic.fields import FieldInfo

from app.ai_core.config.tenant import TenantConfig


@dataclass
class ToolContext:
    tenant: TenantConfig
    role: str
    thread_id: str


_UNDEFINED = FieldInfo(annotation=str).default


def contextual_tool(func):
    """Decorate a function that needs a runtime-injected ``ToolContext``.

    The returned tool validates ``ctx`` at execution time (so the middleware can
    inject it), but ``ctx`` is omitted from the JSON schema sent to the LLM.
    This keeps the context object out of the model's tool-calling surface while
    still making it available to business logic.
    """
    base_tool = tool(func)

    class ContextualTool(StructuredTool):
        def get_input_schema(self, config=None):
            fields = {}
            for name, field_info in self.args_schema.model_fields.items():
                if name == "ctx":
                    continue
                annotation = field_info.annotation
                default = field_info.default
                fields[name] = (annotation, default if default is not _UNDEFINED else ...)
            return create_model(f"{self.name}_llm", **fields, __base__=BaseModel)

        def __call__(self, *args, **kwargs):
            """Allow the tool to be invoked like a plain function in tests."""
            tool_input = {}
            for name, value in zip(self.args_schema.model_fields.keys(), args):
                tool_input[name] = value
            tool_input.update(kwargs)
            return self.invoke(tool_input)

    return ContextualTool.from_function(
        func=func,
        name=base_tool.name,
        description=base_tool.description,
        args_schema=base_tool.args_schema,
    )

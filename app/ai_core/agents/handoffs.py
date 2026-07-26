from collections.abc import Iterable
from typing import Annotated, Any

from langchain.messages import ToolMessage
from langchain.tools import BaseTool, InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

SPECIALISTS = ("greeter", "catalog", "objection", "closer")

_SPECIALIST_CAPABILITIES = {
    "greeter": "welcoming the customer and discovering their initial need",
    "catalog": "product discovery, prices, variants, and availability",
    "objection": "resolving price, shipping, quality, trust, or policy concerns",
    "closer": "confirming a purchase and creating an order",
}


def _handoff_description(source: str, target: str) -> str:
    return (
        f"Transfer from {source} to {target} when the customer's next need is "
        f"{_SPECIALIST_CAPABILITIES[target]}."
    )


def create_handoff_tool(target: str, description: str) -> BaseTool:
    """Create a structured transfer to another node in the parent swarm graph."""
    name = f"handoff_to_{target}"

    @tool(name, description=description)
    def handoff(
        state: Annotated[Any, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        messages = state["messages"] if isinstance(state, dict) else state.messages
        acknowledgement = ToolMessage(
            content=f"Transferred to {target}.",
            name=name,
            tool_call_id=tool_call_id,
        )
        return Command(
            goto=target,
            graph=Command.PARENT,
            update={
                "messages": [*messages, acknowledgement],
                "active_agent": target,
            },
        )

    return handoff


def build_handoff_tools(source: str, available_agents: Iterable[str]) -> list[BaseTool]:
    """Build a transfer to every other enabled specialist."""
    if source not in SPECIALISTS:
        raise ValueError(f"Unknown public specialist: {source}")
    available = set(available_agents)
    return [
        create_handoff_tool(target, _handoff_description(source, target))
        for target in SPECIALISTS
        if target != source and target in available
    ]


def handoff_targets(source: str, available_agents: Iterable[str]) -> tuple[str, ...]:
    """Return every other enabled specialist as a graph destination."""
    if source not in SPECIALISTS:
        raise ValueError(f"Unknown public specialist: {source}")
    available = set(available_agents)
    return tuple(
        target for target in SPECIALISTS if target != source and target in available
    )

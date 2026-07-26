"""Lifecycle helpers for agents that hold an open checkpointer context manager."""

from typing import Any


async def _close_agent(agent: Any) -> None:
    """Exit any context manager the agent holds for its checkpointer connection."""
    checkpointer_ctx = getattr(agent, "_checkpointer_ctx", None)
    if checkpointer_ctx is not None:
        await checkpointer_ctx.__aexit__(None, None, None)
        agent._checkpointer_ctx = None


def attach_lifecycle(agent: Any) -> Any:
    """Attach an ``aclose()`` coroutine to an agent for explicit resource cleanup.

    ``create_agent`` and compiled StateGraphs need explicit checkpointer
    connection cleanup, so this helper adds a small hook that releases it
    instead of leaking the context manager. It is a coroutine because the
    checkpointer is an ``AsyncPostgresSaver``, an async context manager.
    """
    agent.aclose = lambda: _close_agent(agent)
    return agent

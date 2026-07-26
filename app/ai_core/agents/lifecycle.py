"""Lifecycle helpers for agents that hold an open checkpointer context manager."""

from typing import Any


def _close_agent(agent: Any) -> None:
    """Exit any context manager the agent holds for its checkpointer connection."""
    checkpointer_ctx = getattr(agent, "_checkpointer_ctx", None)
    if checkpointer_ctx is not None:
        checkpointer_ctx.__exit__(None, None, None)
        agent._checkpointer_ctx = None


def attach_lifecycle(agent: Any) -> Any:
    """Attach a ``close()`` method to an agent for explicit resource cleanup.

    ``create_agent`` and compiled StateGraphs need explicit checkpointer
    connection cleanup, so this helper adds a small hook that releases it
    instead of leaking the context manager.
    """
    agent.close = lambda: _close_agent(agent)
    return agent

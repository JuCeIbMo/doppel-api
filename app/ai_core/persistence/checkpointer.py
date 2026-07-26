"""LangGraph checkpointer: one shared Postgres for every tenant.

Unlike the ported project's `persistence/sqlite.py` (one SQLite file per
tenant), tenant isolation here comes from `thread_id` (`{tenant_id}:{role}:{phone}`)
scoping rows within LangGraph's own tables — the same Postgres serves every
tenant, same as any other multi-tenant table in doppel-api.
"""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.config import settings


def get_chat_db_url() -> str:
    if not settings.CHAT_DB_URL:
        raise RuntimeError(
            "CHAT_DB_URL is not set. Add it to your environment or .env file; "
            "the agent core cannot persist conversation state without it."
        )
    return settings.CHAT_DB_URL


async def open_checkpointer() -> tuple[Any, AsyncPostgresSaver]:
    """Open a checkpointer connection and run its one-time `.setup()`.

    Async on purpose: the agents drive the graph with `ainvoke` so the webhook's
    event loop is never blocked, and the synchronous `PostgresSaver` does not
    implement LangGraph's async checkpoint methods at all (`aget_tuple`/`aput`
    raise `NotImplementedError`) — only `AsyncPostgresSaver` works on that path.

    Returns `(context_manager, checkpointer)`; the caller is responsible for
    exiting the context manager (see `agents/lifecycle.py`).
    """
    checkpointer_ctx = AsyncPostgresSaver.from_conn_string(get_chat_db_url())
    checkpointer = await checkpointer_ctx.__aenter__()
    await checkpointer.setup()
    return checkpointer_ctx, checkpointer

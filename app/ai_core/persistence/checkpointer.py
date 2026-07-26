"""LangGraph checkpointer: one shared Postgres for every tenant.

Unlike the ported project's `persistence/sqlite.py` (one SQLite file per
tenant), tenant isolation here comes from `thread_id` (`{tenant_id}:{role}:{phone}`)
scoping rows within LangGraph's own tables — the same Postgres serves every
tenant, same as any other multi-tenant table in doppel-api.
"""

from __future__ import annotations

from langgraph.checkpoint.postgres import PostgresSaver

from app.config import settings


def get_chat_db_url() -> str:
    if not settings.CHAT_DB_URL:
        raise RuntimeError(
            "CHAT_DB_URL is not set. Add it to your environment or .env file; "
            "the agent core cannot persist conversation state without it."
        )
    return settings.CHAT_DB_URL


def open_checkpointer() -> PostgresSaver:
    """Open a checkpointer connection and run its one-time `.setup()`.

    Returns the checkpointer itself; the caller is responsible for exiting the
    context manager it came from (see `agents/lifecycle.py`).
    """
    checkpointer_ctx = PostgresSaver.from_conn_string(get_chat_db_url())
    checkpointer = checkpointer_ctx.__enter__()
    checkpointer.setup()
    return checkpointer_ctx, checkpointer

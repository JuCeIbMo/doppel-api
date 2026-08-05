"""LangGraph checkpointer: one shared Postgres pool for every tenant.

Unlike the ported project's `persistence/sqlite.py` (one SQLite file per
tenant), tenant isolation here comes from `thread_id` (`{tenant_id}:{role}:{phone}`)
scoping rows within LangGraph's own tables — the same Postgres serves every
tenant, same as any other multi-tenant table in doppel-api.

The pool is process-wide **on purpose**. This module used to hand out one raw
`AsyncConnection` per `(tenant, role)` (`AsyncPostgresSaver.from_conn_string`),
and `bridge._agents` cached it forever. psycopg never reconnects a dropped
connection, so one Postgres restart — or an idle reaper, or a network blip —
left that tenant's bot silent until the process restarted, with no
customer-facing error at all. An `AsyncConnectionPool` replaces broken
connections itself, and `AsyncPostgresSaver` accepts a pool directly: its
`_cursor` goes through `get_connection`, which handles both shapes.

Each agent still gets its **own** saver instance over the shared pool. The
saver serializes its own operations on an internal `asyncio.Lock`, so sharing a
single saver process-wide would funnel every tenant through one lock.
"""

from __future__ import annotations

import asyncio

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.config import settings

# `AsyncPostgresSaver` manages its own transactions and needs `dict_row`;
# `prepare_threshold=0` keeps it working behind connection poolers.
_POOL_KWARGS = {"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row}

MAX_POOL_SIZE = 10

# Bound at import so the pool class itself can be swapped in tests.
CHECK_CONNECTION = AsyncConnectionPool.check_connection

_pool: AsyncConnectionPool | None = None
_pool_lock = asyncio.Lock()
_setup_done = False


def get_chat_db_url() -> str:
    if not settings.CHAT_DB_URL:
        raise RuntimeError(
            "CHAT_DB_URL is not set. Add it to your environment or .env file; "
            "the agent core cannot persist conversation state without it."
        )
    return settings.CHAT_DB_URL


async def get_pool() -> AsyncConnectionPool:
    """Return the process-wide pool, opening it on first use.

    Opened lazily rather than at startup so a deployment with the bot disabled
    (`BOT_ENABLED` empty) never needs `CHAT_DB_URL` to boot.
    """
    global _pool
    async with _pool_lock:
        if _pool is None or _pool.closed:
            pool = AsyncConnectionPool(
                conninfo=get_chat_db_url(),
                min_size=1,
                max_size=MAX_POOL_SIZE,
                kwargs=_POOL_KWARGS,
                # Validate before handing a connection out. Without this a
                # stale connection is still served once, and that turn fails
                # before the pool notices and replaces it.
                check=CHECK_CONNECTION,
                open=False,
            )
            await pool.open(wait=True)
            _pool = pool
        return _pool


async def open_checkpointer() -> AsyncPostgresSaver:
    """Return a checkpointer over the shared pool, running `.setup()` once.

    Async on purpose: the agents drive the graph with `ainvoke` so the webhook's
    event loop is never blocked, and the synchronous `PostgresSaver` does not
    implement LangGraph's async checkpoint methods at all (`aget_tuple`/`aput`
    raise `NotImplementedError`) — only `AsyncPostgresSaver` works on that path.

    The caller owns nothing: the pool outlives every agent and is released by
    `close_pool()` at shutdown.
    """
    global _setup_done
    pool = await get_pool()
    checkpointer = AsyncPostgresSaver(conn=pool)
    if not _setup_done:
        # Idempotent (`CREATE TABLE IF NOT EXISTS` + versioned migrations), but
        # it is a round trip per agent build, so run it once per process.
        await checkpointer.setup()
        _setup_done = True
    return checkpointer


async def close_pool() -> None:
    """Release the shared pool. Called from the app lifespan on shutdown."""
    global _pool, _setup_done
    async with _pool_lock:
        if _pool is not None:
            await _pool.close()
            _pool = None
        _setup_done = False

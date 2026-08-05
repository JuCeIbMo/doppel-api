"""LangGraph checkpointer backed by Redis.

The official ``AsyncRedisSaver`` stores the checkpointed state of every
conversation.  It is process-wide because Redis itself provides the shared,
networked backing store; the saver is initialized once so its RediSearch
indices are created exactly once at startup-on-first-use.

Redis must provide RedisJSON and RediSearch (Redis 8+ includes both).
"""

from __future__ import annotations

import asyncio
from contextlib import AbstractAsyncContextManager

from langgraph.checkpoint.redis.aio import AsyncRedisSaver

from app.config import settings

_saver: AsyncRedisSaver | None = None
_saver_context: AbstractAsyncContextManager[AsyncRedisSaver] | None = None
_saver_lock = asyncio.Lock()


def get_redis_url() -> str:
    if not settings.REDIS_URL:
        raise RuntimeError(
            "REDIS_URL is not set. Add it to your environment or .env file; "
            "the agent core cannot persist conversation state without it."
        )
    return settings.REDIS_URL


async def open_checkpointer() -> AsyncRedisSaver:
    """Return the shared async Redis checkpointer, initialized once."""
    global _saver, _saver_context
    async with _saver_lock:
        if _saver is None:
            context = AsyncRedisSaver.from_conn_string(get_redis_url())
            _saver = await context.__aenter__()
            _saver_context = context
        return _saver


async def close_pool() -> None:
    """Close the Redis client at application shutdown.

    The public app lifespan already calls this function; retaining its name
    keeps that lifecycle contract small and avoids a second shutdown path.
    """
    global _saver, _saver_context
    async with _saver_lock:
        context = _saver_context
        _saver = None
        _saver_context = None
    if context is not None:
        await context.__aexit__(None, None, None)

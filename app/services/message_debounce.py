"""Redis-backed debounce for bursts of inbound WhatsApp messages.

Each webhook still persists its message immediately.  This module only delays
the bot invocation: messages for one conversation that arrive inside the
configured window are claimed as one ordered batch by the last waiter.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import uuid
from typing import Any

from redis.asyncio import Redis

from app.config import settings

logger = logging.getLogger("doppel.message_debounce")

_client: Redis | None = None
_client_lock = asyncio.Lock()

# Both keys share a Redis Cluster hash slot. Enqueueing and claiming are atomic,
# so a message cannot land between LRANGE and DEL and disappear from the batch.
_ENQUEUE = """
redis.call('RPUSH', KEYS[1], ARGV[1])
redis.call('EXPIRE', KEYS[1], ARGV[3])
redis.call('SET', KEYS[2], ARGV[2], 'EX', ARGV[3])
return ARGV[2]
"""

_CLAIM = """
if redis.call('GET', KEYS[2]) ~= ARGV[1] then
    return {}
end
local messages = redis.call('LRANGE', KEYS[1], 0, -1)
redis.call('DEL', KEYS[1], KEYS[2])
return messages
"""


def _keys(conversation_id: str) -> tuple[str, str]:
    digest = hashlib.sha256(conversation_id.encode("utf-8")).hexdigest()
    slot = f"{{{digest}}}"
    return f"doppel:debounce:{slot}:messages", f"doppel:debounce:{slot}:deadline"


async def _get_client() -> Redis:
    global _client
    async with _client_lock:
        if _client is None:
            _client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
        return _client


async def debounce_message(
    conversation_id: str,
    message: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return the complete batch to one waiter; return ``[]`` to the others.

    Redis is an optimization, not permission to drop customer messages. If it
    is disabled or unavailable, the current message is processed immediately.
    """
    delay = settings.MESSAGE_DEBOUNCE_SECONDS
    if delay <= 0 or not settings.REDIS_URL:
        return [message]

    queue_key, deadline_key = _keys(conversation_id)
    token = uuid.uuid4().hex
    encoded = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
    ttl = max(60, math.ceil(delay * 10))

    try:
        client = await _get_client()
        await client.eval(
            _ENQUEUE,
            2,
            queue_key,
            deadline_key,
            encoded,
            token,
            ttl,
        )
        await asyncio.sleep(delay)
        claimed = await client.eval(
            _CLAIM,
            2,
            queue_key,
            deadline_key,
            token,
        )
    except Exception:
        logger.warning(
            "Redis debounce unavailable; processing message immediately conversation=%s",
            conversation_id,
            exc_info=True,
        )
        return [message]

    return [json.loads(item) for item in claimed]


async def close_debounce() -> None:
    """Release the process-wide Redis connection pool at shutdown."""
    global _client
    async with _client_lock:
        client = _client
        _client = None
    if client is not None:
        await client.aclose()

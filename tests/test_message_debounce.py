"""Regression tests for the Redis message debounce."""

import os

os.environ.setdefault("META_APP_ID", "test-app-id")
os.environ.setdefault("META_APP_SECRET", "test-app-secret")
os.environ.setdefault("META_VERIFY_TOKEN", "test-verify-token")
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "x.eyJyb2xlIjogInNlcnZpY2Vfcm9sZSJ9.y")
os.environ.setdefault("ENCRYPTION_KEY", "oZRrOD525wcQ0CJveupENSX1tDwKfP6e1XrDGn9P1Kw=")
os.environ.setdefault("CHAT_DB_URL", "postgresql://ai:ai@localhost:5532/chat")

import asyncio
from unittest.mock import AsyncMock

from app.ai_core.channel.inbound import InteractiveReply
from app.routers import webhook
from app.services import message_debounce as debounce


class FakeRedis:
    def __init__(self):
        self.queues: dict[str, list[str]] = {}
        self.deadlines: dict[str, str] = {}
        self.closed = False

    async def eval(self, script, _key_count, queue_key, deadline_key, *args):
        if script == debounce._ENQUEUE:
            encoded, token, _ttl = args
            self.queues.setdefault(queue_key, []).append(encoded)
            self.deadlines[deadline_key] = token
            return token

        (token,) = args
        if self.deadlines.get(deadline_key) != token:
            return []
        messages = self.queues.pop(queue_key, [])
        self.deadlines.pop(deadline_key, None)
        return messages

    async def aclose(self):
        self.closed = True


def test_only_last_waiter_claims_the_ordered_message_burst(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(debounce, "_client", fake)
    monkeypatch.setattr(debounce.settings, "REDIS_URL", "redis://test")
    monkeypatch.setattr(debounce.settings, "MESSAGE_DEBOUNCE_SECONDS", 0.02)

    async def scenario():
        first = asyncio.create_task(debounce.debounce_message("t1:public:+1", {"text": "hola"}))
        await asyncio.sleep(0.005)
        second = asyncio.create_task(debounce.debounce_message("t1:public:+1", {"text": "precio"}))
        return await asyncio.gather(first, second)

    first_result, second_result = asyncio.run(scenario())
    assert first_result == []
    assert second_result == [{"text": "hola"}, {"text": "precio"}]


def test_redis_failure_processes_the_message_immediately(monkeypatch):
    class BrokenRedis:
        async def eval(self, *_args):
            raise ConnectionError("redis unavailable")

    message = {"text": "no me pierdas"}
    monkeypatch.setattr(debounce, "_client", BrokenRedis())
    monkeypatch.setattr(debounce.settings, "REDIS_URL", "redis://test")
    monkeypatch.setattr(debounce.settings, "MESSAGE_DEBOUNCE_SECONDS", 2)

    assert asyncio.run(debounce.debounce_message("conversation", message)) == [message]


def test_debounced_webhook_combines_text_media_and_interactive_in_order(monkeypatch):
    batch = [
        {
            "tenant_id": "t1",
            "wa_account_id": "wa1",
            "user_phone": "5911",
            "inbound_text": "quiero esto",
            "mode": "client",
            "inbound_message_id": "m1",
            "media": [{"id": "image1", "type": "image"}],
            "interactive": None,
        },
        {
            "tenant_id": "t1",
            "wa_account_id": "wa1",
            "user_phone": "5911",
            "inbound_text": "Azul",
            "mode": "client",
            "inbound_message_id": "m2",
            "media": [],
            "interactive": {"id": "choice:blue", "title": "Azul"},
        },
    ]

    async def return_batch(_conversation_id, _message):
        return batch

    process = AsyncMock()
    monkeypatch.setattr(webhook, "debounce_message", return_batch)
    monkeypatch.setattr(webhook, "_process_bot_response", process)

    asyncio.run(
        webhook._debounce_bot_response(
            AsyncMock(),
            "t1",
            "wa1",
            "5911",
            "Azul",
            "client",
            "m2",
            interactive=InteractiveReply(id="choice:blue", title="Azul"),
        )
    )

    process.assert_awaited_once()
    args = process.await_args.args
    assert args[4] == 'quiero esto\n[El cliente tocó la opción "Azul" (id: blue)]'
    assert args[6] == "m2"
    assert args[7] == [{"id": "image1", "type": "image"}]
    assert args[8] is None


def test_messages_from_one_meta_webhook_start_debounce_concurrently(monkeypatch):
    active = 0
    peak = 0

    async def track_waiter(_http_client, *_args):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0)
        active -= 1

    monkeypatch.setattr(webhook, "_debounce_bot_response", track_waiter)
    scheduled = [
        ("t1", "wa1", "5911", "uno", "client", "m1", [], None),
        ("t1", "wa1", "5911", "dos", "client", "m2", [], None),
    ]

    asyncio.run(webhook._run_scheduled_responses(AsyncMock(), scheduled))

    assert peak == 2


def test_close_debounce_releases_and_resets_client(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(debounce, "_client", fake)

    asyncio.run(debounce.close_debounce())

    assert fake.closed
    assert debounce._client is None

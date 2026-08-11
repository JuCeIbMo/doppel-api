import asyncio

from app.services.erp import admin_actions
from app.services.erp.context import bot_context
from tests.fakes import FakeSupabase


def _ctx():
    return bot_context("tenant-1", actor="admin_bot")


def test_admin_action_requires_matching_tenant_and_thread(monkeypatch):
    fake = FakeSupabase({})
    monkeypatch.setattr(admin_actions, "get_supabase", lambda: fake)

    action = asyncio.run(admin_actions.AdminActionService().create(
        _ctx(), thread_id="tenant-1:admin:59170000001", kind="stock_adjustment",
        payload={"product_id": "p1", "quantity": 7}, summary="Ajustar agua a 7",
    ))

    wrong = asyncio.run(admin_actions.AdminActionService().consume_reply(
        _ctx(), thread_id="tenant-1:admin:other", action_id=action["id"], confirmed=True,
    ))
    assert wrong is None
    assert fake.store["admin_pending_actions"][0]["status"] == "pending"


def test_confirmation_can_only_be_claimed_once(monkeypatch):
    fake = FakeSupabase({})
    monkeypatch.setattr(admin_actions, "get_supabase", lambda: fake)
    service = admin_actions.AdminActionService()
    action = asyncio.run(service.create(
        _ctx(), thread_id="thread", kind="transaction",
        payload={"type": "expense", "amount": 5}, summary="Gasto 5",
    ))

    confirmed = asyncio.run(service.consume_reply(
        _ctx(), thread_id="thread", action_id=action["id"], confirmed=True,
    ))
    assert confirmed == action["id"]
    claimed = asyncio.run(service.claim(_ctx(), thread_id="thread", action_id=action["id"]))
    assert claimed["status"] == "executing"
    completed = asyncio.run(service.complete(action["id"], {"ok": True}))
    assert completed["status"] == "executed"

    # A redelivery never returns the action to the executable state.
    assert asyncio.run(service.consume_reply(
        _ctx(), thread_id="thread", action_id=action["id"], confirmed=True,
    )) is None

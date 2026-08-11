import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.ai_core import bridge
from app.ai_core.channel.inbound import InteractiveReply
from app.ai_core.config.tenant import AdminAgentConfig, PublicAgentConfig, TenantConfig
from app.ai_core.tools import admin as admin_tools
from app.ai_core.tools.admin import execute_confirmed_action
from app.ai_core.tools.channel import ADMIN_CONFIRM_PREFIX, CHOICE_PREFIX
from app.ai_core.tools.context import ToolContext
from app.services.erp import admin_actions
from app.services.erp.context import bot_context
from app.services.erp.exceptions import Conflict
from tests.fakes import FakeSupabase


def _ctx():
    return bot_context("tenant-1", actor="admin_bot")


TENANT = TenantConfig(
    tenant_id="tenant-1",
    business_name="Kiosco",
    public_agent=PublicAgentConfig(),
    admin_agent=AdminAgentConfig(allowed_numbers=["59170000001"]),
)


def _tool_ctx(confirmed_action_id: str) -> ToolContext:
    return ToolContext(tenant=TENANT, role="admin", thread_id="thread",
                       confirmed_action_id=confirmed_action_id)


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


# --------------------------------------------------------------------------
# La cadena del id del botón, de punta a punta.
#
# El bug: `_propose` emite `choice:admin-confirm:{uuid}`, `InteractiveReply.value`
# saca el `choice:` y deja `admin-confirm:{uuid}` — eso es lo que el modelo ve en
# `as_agent_note()` y lo que se supone que pasa de vuelta a
# `execute_confirmed_action`. Antes del fix, la tool comparaba ese valor crudo
# contra el uuid pelado que guarda `ctx.confirmed_action_id` y siempre fallaba.
# --------------------------------------------------------------------------

def test_confirmation_id_chain_end_to_end(monkeypatch):
    fake = FakeSupabase({})
    monkeypatch.setattr(admin_actions, "get_supabase", lambda: fake)
    service = admin_actions.AdminActionService()
    action = asyncio.run(service.create(
        _ctx(), thread_id="thread", kind="transaction",
        payload={"type": "expense", "amount": 5}, summary="Gasto 5",
    ))
    action_id = action["id"]

    # El botón exacto que `_propose` (tools/admin.py) encola.
    reply = InteractiveReply(id=f"{CHOICE_PREFIX}{ADMIN_CONFIRM_PREFIX}{action_id}", title="Confirmar")

    confirmed_id = asyncio.run(bridge._consume_admin_confirmation(TENANT, "thread", reply))
    assert confirmed_id == action_id

    # Lo que el modelo lee literalmente en el transcript.
    note = reply.as_agent_note()
    assert f"id: {ADMIN_CONFIRM_PREFIX}{action_id}" in note

    async def _fake_claim(self, ctx, *, thread_id, action_id):
        return {"id": action_id, "status": "executed", "result": {"ok": True}}

    monkeypatch.setattr(admin_tools.AdminActionService, "claim", _fake_claim)

    # El modelo pasa el id tal cual apareció en el mensaje (con el prefijo
    # admin-confirm:) — execute_confirmed_action tiene que aceptarlo.
    result = asyncio.run(execute_confirmed_action.ainvoke({
        "action_id": reply.value, "ctx": _tool_ctx(confirmed_action_id=confirmed_id),
    }))
    assert result == {"ok": True}


def test_execute_confirmed_action_rejects_mismatched_id(monkeypatch):
    async def _fake_claim(self, ctx, *, thread_id, action_id):
        raise AssertionError("claim no debe correr si el id no coincide")

    monkeypatch.setattr(admin_tools.AdminActionService, "claim", _fake_claim)

    with pytest.raises(PermissionError):
        asyncio.run(execute_confirmed_action.ainvoke({
            "action_id": f"{ADMIN_CONFIRM_PREFIX}otro-uuid",
            "ctx": _tool_ctx(confirmed_action_id="el-uuid-real"),
        }))


def test_confirmation_past_expiry_is_rejected(monkeypatch):
    fake = FakeSupabase({})
    monkeypatch.setattr(admin_actions, "get_supabase", lambda: fake)
    service = admin_actions.AdminActionService()
    action = asyncio.run(service.create(
        _ctx(), thread_id="thread", kind="transaction",
        payload={"type": "expense", "amount": 5}, summary="Gasto 5",
    ))
    action_id = action["id"]
    # Formato estilo Postgres (sufijo Z, sin fracción de segundo) ya vencido.
    # Una comparación de strings ingenua contra datetime.now(UTC).isoformat()
    # (que siempre lleva microsegundos y "+00:00") no está garantizada a
    # ordenar bien contra este formato.
    past = (datetime.now(UTC) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    fake.store["admin_pending_actions"][0]["expires_at"] = past

    confirmed = asyncio.run(service.consume_reply(
        _ctx(), thread_id="thread", action_id=action_id, confirmed=True,
    ))
    assert confirmed is None
    assert fake.store["admin_pending_actions"][0]["status"] == "expired"


# --------------------------------------------------------------------------
# Re-claim de una acción trabada en "executing" (worker que murió a mitad de
# camino entre claim() y complete()).
# --------------------------------------------------------------------------

def test_claim_recovers_stuck_executing_action(monkeypatch):
    fake = FakeSupabase({})
    monkeypatch.setattr(admin_actions, "get_supabase", lambda: fake)
    service = admin_actions.AdminActionService()
    action = asyncio.run(service.create(
        _ctx(), thread_id="thread", kind="transaction",
        payload={"type": "expense", "amount": 5}, summary="Gasto 5",
    ))
    action_id = action["id"]
    asyncio.run(service.consume_reply(_ctx(), thread_id="thread", action_id=action_id, confirmed=True))

    old_confirmed_at = (
        datetime.now(UTC) - admin_actions._STUCK_EXECUTING_TIMEOUT - timedelta(seconds=1)
    ).isoformat()
    fake.store["admin_pending_actions"][0].update({"status": "executing", "confirmed_at": old_confirmed_at})

    reclaimed = asyncio.run(service.claim(_ctx(), thread_id="thread", action_id=action_id))
    assert reclaimed["status"] == "executing"


def test_claim_rejects_recently_stuck_executing_action(monkeypatch):
    fake = FakeSupabase({})
    monkeypatch.setattr(admin_actions, "get_supabase", lambda: fake)
    service = admin_actions.AdminActionService()
    action = asyncio.run(service.create(
        _ctx(), thread_id="thread", kind="transaction",
        payload={"type": "expense", "amount": 5}, summary="Gasto 5",
    ))
    action_id = action["id"]
    asyncio.run(service.consume_reply(_ctx(), thread_id="thread", action_id=action_id, confirmed=True))
    asyncio.run(service.claim(_ctx(), thread_id="thread", action_id=action_id))

    with pytest.raises(Conflict):
        asyncio.run(service.claim(_ctx(), thread_id="thread", action_id=action_id))

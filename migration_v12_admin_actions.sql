-- Durable approvals for mutations requested through the WhatsApp admin agent.
-- Business writes are never performed when an action is created: a separate
-- interactive reply must move it to `confirmed` first.
create table if not exists admin_pending_actions (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid not null references tenants(id) on delete cascade,
    thread_id text not null,
    kind text not null,
    payload jsonb not null,
    summary text not null,
    status text not null default 'pending'
      check (status in ('pending', 'confirmed', 'cancelled', 'executing', 'executed', 'expired')),
    expires_at timestamptz not null,
    result jsonb,
    created_at timestamptz not null default now(),
    confirmed_at timestamptz,
    executed_at timestamptz
);

create index if not exists admin_pending_actions_lookup_idx
  on admin_pending_actions (tenant_id, thread_id, status, expires_at);

-- These keys make the two non-idempotent writes safe if a worker dies after
-- the ERP write but before persisting the action result.
alter table products add column if not exists admin_action_id uuid unique;
alter table transactions add column if not exists admin_action_id uuid unique;

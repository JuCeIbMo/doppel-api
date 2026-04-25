-- migration.sql
-- Ejecutar en Supabase SQL Editor ANTES de hacer deploy del backend

-- Tenants (cada negocio conectado)
create table tenants (
  id uuid primary key default gen_random_uuid(),
  business_name text not null,
  email text,
  plan text default 'free',
  status text default 'active',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- Cuentas de WhatsApp vinculadas
create table whatsapp_accounts (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid references tenants(id) on delete cascade,
  waba_id text not null,
  phone_number_id text not null,
  display_phone text,
  access_token_encrypted text not null,
  token_type text default 'long_lived',
  token_expiry timestamptz,
  webhook_active boolean default true,
  status text default 'connected',
  is_coexistence boolean not null default false,
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  unique(waba_id, phone_number_id)
);

-- Configuración del bot por tenant
create table bot_configs (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid references tenants(id) on delete cascade,
  system_prompt text default 'Eres un asistente amable que ayuda a los clientes.',
  welcome_message text default '¡Hola! ¿En qué puedo ayudarte?',
  language text default 'es',
  ai_model text default 'claude-sonnet-4-20250514',
  tools_enabled jsonb default '[]',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- Mensajes
create table messages (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid references tenants(id) on delete cascade,
  wa_account_id uuid references whatsapp_accounts(id),
  user_phone text not null,
  direction text not null check (direction in ('inbound', 'outbound')),
  content text,
  message_type text default 'text',
  wa_message_id text,
  session_id text,
  created_at timestamptz default now()
);

-- Índices
create index idx_messages_tenant_phone on messages(tenant_id, user_phone);
create index idx_messages_session on messages(session_id);
create index idx_wa_accounts_tenant on whatsapp_accounts(tenant_id);
create index idx_wa_accounts_phone_id on whatsapp_accounts(phone_number_id);

-- Trigger para auto-actualizar updated_at
create or replace function update_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create trigger trg_tenants_updated_at
  before update on tenants
  for each row execute function update_updated_at();

create trigger trg_whatsapp_accounts_updated_at
  before update on whatsapp_accounts
  for each row execute function update_updated_at();

create trigger trg_bot_configs_updated_at
  before update on bot_configs
  for each row execute function update_updated_at();

-- RLS habilitado (service role key lo bypasea, sin políticas por ahora)
alter table tenants enable row level security;
alter table whatsapp_accounts enable row level security;
alter table bot_configs enable row level security;
alter table messages enable row level security;

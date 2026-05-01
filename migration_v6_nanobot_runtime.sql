-- migration_v6_nanobot_runtime.sql
-- Ejecutar DESPUES de migration_v5.sql.
-- Guarda metadata multimedia y el modo de agente usado por el runtime nanobot.

ALTER TABLE messages
  ADD COLUMN IF NOT EXISTS media jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS agent_mode text CHECK (agent_mode IN ('manager', 'client')),
  ADD COLUMN IF NOT EXISTS processing_error text;

CREATE INDEX IF NOT EXISTS idx_messages_tenant_agent_mode
  ON messages(tenant_id, agent_mode);

NOTIFY pgrst, 'reload schema';

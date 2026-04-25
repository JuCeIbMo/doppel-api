-- migration_v3.sql
-- Ejecutar DESPUES de migration.sql, migration_auth.sql y migration_v2.sql
-- Agrega controles para el MVP vendible

ALTER TABLE bot_configs
  ADD COLUMN IF NOT EXISTS bot_enabled boolean NOT NULL DEFAULT true;

ALTER TABLE whatsapp_accounts
  ADD COLUMN IF NOT EXISTS is_coexistence boolean NOT NULL DEFAULT false;

CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_wa_message_id_unique
  ON messages(wa_message_id)
  WHERE wa_message_id IS NOT NULL;

NOTIFY pgrst, 'reload schema';

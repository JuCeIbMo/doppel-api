-- migration_v7_whatsapp_offboarding.sql
-- Ejecutar DESPUES de migration_v6_nanobot_runtime.sql.
-- Agrega deleted_at para soft-delete de cuentas de WhatsApp desconectadas.

ALTER TABLE whatsapp_accounts
ADD COLUMN IF NOT EXISTS deleted_at timestamptz;

CREATE INDEX IF NOT EXISTS idx_wa_accounts_deleted_at
ON whatsapp_accounts(deleted_at);

NOTIFY pgrst, 'reload schema';

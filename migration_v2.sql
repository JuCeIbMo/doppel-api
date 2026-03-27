-- migration_v2.sql
-- Ejecutar DESPUÉS de migration.sql y migration_auth.sql
-- Liga cada tenant a su usuario de Supabase Auth

ALTER TABLE tenants
  ADD COLUMN user_id uuid NOT NULL UNIQUE
  REFERENCES auth.users(id) ON DELETE CASCADE;

CREATE INDEX idx_tenants_user_id ON tenants(user_id);

-- Nota: si ya tienes filas en tenants sin user_id, primero agrégala como nullable:
-- ALTER TABLE tenants ADD COLUMN user_id uuid REFERENCES auth.users(id);
-- (backfill manual)
-- ALTER TABLE tenants ALTER COLUMN user_id SET NOT NULL;
-- ALTER TABLE tenants ADD CONSTRAINT tenants_user_id_key UNIQUE (user_id);

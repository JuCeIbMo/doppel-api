-- migration_v5.sql
-- Ejecutar DESPUES de migration.sql, migration_auth.sql, migration_v2.sql, migration_v3.sql, migration_v4.sql
-- Agrega business_info (1:1 por tenant): config del negocio para el prompt del bot
-- (horarios, direccion, formas de pago, etc.).
--
-- La tabla `products` que este archivo creaba originalmente ahora vive, junto con el
-- resto del modulo ERP, en schema_erp.sql (drop-and-recreate, sin variantes).

-- business_info: una sola fila por tenant. El manager/cliente la consulta para responder
-- preguntas tipicas del negocio (horarios, direccion, formas de pago, etc.).
CREATE TABLE business_info (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL UNIQUE REFERENCES tenants(id) ON DELETE CASCADE,
  name text DEFAULT '',
  description text DEFAULT '',
  hours text DEFAULT '',
  address text DEFAULT '',
  payment_methods text DEFAULT '',
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);
CREATE TRIGGER trg_business_info_updated_at BEFORE UPDATE ON business_info
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
ALTER TABLE business_info ENABLE ROW LEVEL SECURITY;

NOTIFY pgrst, 'reload schema';

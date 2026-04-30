-- migration_v5.sql
-- Ejecutar DESPUES de migration.sql, migration_auth.sql, migration_v2.sql, migration_v3.sql, migration_v4.sql
-- Agrega un mini-dashboard de negocio: business_info (1:1 por tenant) y products (1:N por tenant).

-- 1. business_info: una sola fila por tenant. El manager/cliente la consulta para responder
--    preguntas tipicas del negocio (horarios, direccion, formas de pago, etc.).
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

-- 2. products: N filas por tenant. El client agent las lista cuando un cliente pregunta
--    "que tienen?" / "cuanto cuesta X?". El manager las administra desde el dashboard o por chat.
CREATE TABLE products (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  name text NOT NULL,
  description text DEFAULT '',
  price numeric(12,2),
  available boolean NOT NULL DEFAULT true,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);
CREATE INDEX idx_products_tenant ON products(tenant_id);
CREATE TRIGGER trg_products_updated_at BEFORE UPDATE ON products
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
ALTER TABLE products ENABLE ROW LEVEL SECURITY;

NOTIFY pgrst, 'reload schema';

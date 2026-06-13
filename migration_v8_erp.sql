-- migration_v8_erp.sql
-- Ejecutar DESPUES de migration_v7_whatsapp_offboarding.sql.
-- Agrega el modulo ERP: catalogo enriquecido, inventario con movimientos, ventas atomicas,
-- clientes, finanzas y bitacora de actividad. Todo multi-tenant via tenants(id).
--
-- Principios:
--   * El stock nunca queda negativo: create_sale valida ANTES de insertar movimientos.
--   * Operaciones compuestas (venta, cancelacion) son atomicas: viven en funciones PL/pgSQL.
--   * inventory.quantity y cash_accounts.balance son desnormalizados, mantenidos por trigger.
--   * inventory_movements y activity_log son append-only (nunca se editan ni borran).
--   * Reutiliza la tabla products existente (migration_v5) en vez de duplicarla.
--   * Reutiliza la funcion update_updated_at() existente (migration.sql:67).

-- =====================================================================================
-- 0. ENUMS
-- =====================================================================================
CREATE TYPE movement_type    AS ENUM ('purchase', 'sale', 'adjustment_in', 'adjustment_out', 'return', 'loss');
CREATE TYPE sale_status      AS ENUM ('completed', 'cancelled');
CREATE TYPE payment_method   AS ENUM ('cash', 'card', 'transfer', 'whatsapp', 'other');
CREATE TYPE transaction_type AS ENUM ('income', 'expense');
-- 'cashier' se incluye para compatibilidad futura (modo PIN, v2) aunque v1 no lo emita.
CREATE TYPE actor_type       AS ENUM ('owner', 'cashier', 'whatsapp_bot', 'admin_bot');

-- =====================================================================================
-- 1. PRODUCTS: extender la tabla existente (NO recrear). Las columnas existentes
--    name/description/price/available se mantienen para no romper el bot/dashboard actual.
--    price = precio de venta ; available = activo. Se agrega cost_price y campos de retail.
--    Todas las columnas nuevas tienen DEFAULT para que los INSERT existentes sigan validos.
-- =====================================================================================
ALTER TABLE products
  ADD COLUMN IF NOT EXISTS sku                 text,
  ADD COLUMN IF NOT EXISTS barcode             text,
  ADD COLUMN IF NOT EXISTS category            text,
  ADD COLUMN IF NOT EXISTS image_url           text,
  ADD COLUMN IF NOT EXISTS cost_price          numeric(12,2) NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS unit                text NOT NULL DEFAULT 'unidad',
  ADD COLUMN IF NOT EXISTS has_variants        boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS low_stock_threshold integer NOT NULL DEFAULT 5;

CREATE INDEX IF NOT EXISTS idx_products_barcode ON products(tenant_id, barcode);
CREATE INDEX IF NOT EXISTS idx_products_sku     ON products(tenant_id, sku);

-- =====================================================================================
-- 2. PRODUCT_VARIANTS
-- =====================================================================================
CREATE TABLE product_variants (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  product_id  uuid NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  name        text NOT NULL,                 -- "Rojo L", "500ml", "Original"
  barcode     text,
  sku         text,
  cost_price  numeric(12,2),                 -- NULL = hereda del padre
  sale_price  numeric(12,2),                 -- NULL = hereda del padre (products.price)
  is_active   boolean NOT NULL DEFAULT true,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_variants_product ON product_variants(product_id);
CREATE INDEX idx_variants_tenant  ON product_variants(tenant_id);
CREATE TRIGGER trg_variants_updated_at BEFORE UPDATE ON product_variants
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
ALTER TABLE product_variants ENABLE ROW LEVEL SECURITY;

-- =====================================================================================
-- 3. INVENTORY: stock actual. Una fila por producto/variante. Solo el trigger la toca.
--    UNIQUE con NULL no funciona en Postgres, por eso usamos dos indices parciales.
-- =====================================================================================
CREATE TABLE inventory (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  product_id  uuid NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  variant_id  uuid REFERENCES product_variants(id) ON DELETE CASCADE,
  quantity    numeric(12,3) NOT NULL DEFAULT 0,
  updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uniq_inventory_product_novariant ON inventory(product_id) WHERE variant_id IS NULL;
CREATE UNIQUE INDEX uniq_inventory_product_variant   ON inventory(product_id, variant_id) WHERE variant_id IS NOT NULL;
CREATE INDEX idx_inventory_tenant ON inventory(tenant_id);
ALTER TABLE inventory ENABLE ROW LEVEL SECURITY;

-- =====================================================================================
-- 4. INVENTORY_MOVEMENTS: registro inmutable de cada movimiento de stock.
-- =====================================================================================
CREATE TABLE inventory_movements (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  product_id    uuid NOT NULL REFERENCES products(id),
  variant_id    uuid REFERENCES product_variants(id),
  type          movement_type NOT NULL,
  quantity      numeric(12,3) NOT NULL CHECK (quantity > 0),  -- siempre positivo; el tipo da direccion
  unit_cost     numeric(12,2),
  reference_id  uuid,                                         -- sale_id o NULL para ajustes
  notes         text,
  actor         text NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_movements_product ON inventory_movements(product_id, created_at DESC);
CREATE INDEX idx_movements_tenant  ON inventory_movements(tenant_id, created_at DESC);
ALTER TABLE inventory_movements ENABLE ROW LEVEL SECURITY;

-- Trigger: cada movimiento ajusta (upsert) inventory.quantity segun la direccion del tipo.
CREATE OR REPLACE FUNCTION apply_inventory_movement() RETURNS trigger AS $$
DECLARE
  delta numeric(12,3);
BEGIN
  delta := CASE NEW.type
             WHEN 'purchase'       THEN  NEW.quantity
             WHEN 'adjustment_in'  THEN  NEW.quantity
             WHEN 'return'         THEN  NEW.quantity
             ELSE                       -NEW.quantity   -- sale, adjustment_out, loss
           END;

  IF NEW.variant_id IS NULL THEN
    UPDATE inventory SET quantity = quantity + delta, updated_at = now()
      WHERE tenant_id = NEW.tenant_id AND product_id = NEW.product_id AND variant_id IS NULL;
    IF NOT FOUND THEN
      INSERT INTO inventory (tenant_id, product_id, variant_id, quantity)
        VALUES (NEW.tenant_id, NEW.product_id, NULL, delta);
    END IF;
  ELSE
    UPDATE inventory SET quantity = quantity + delta, updated_at = now()
      WHERE tenant_id = NEW.tenant_id AND product_id = NEW.product_id AND variant_id = NEW.variant_id;
    IF NOT FOUND THEN
      INSERT INTO inventory (tenant_id, product_id, variant_id, quantity)
        VALUES (NEW.tenant_id, NEW.product_id, NEW.variant_id, delta);
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_apply_inventory_movement AFTER INSERT ON inventory_movements
  FOR EACH ROW EXECUTE FUNCTION apply_inventory_movement();

-- =====================================================================================
-- 5. CLIENTS
-- =====================================================================================
CREATE TABLE clients (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  name             text NOT NULL,
  phone            text,
  email            text,
  address          text,
  notes            text,
  tags             text[] NOT NULL DEFAULT '{}',
  whatsapp_id      text,
  total_purchases  numeric(12,2) NOT NULL DEFAULT 0,   -- desnormalizado (mantenido por create_sale)
  purchase_count   integer NOT NULL DEFAULT 0,
  last_purchase_at timestamptz,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_clients_tenant   ON clients(tenant_id);
CREATE INDEX idx_clients_phone    ON clients(tenant_id, phone);
CREATE INDEX idx_clients_whatsapp ON clients(tenant_id, whatsapp_id);
CREATE TRIGGER trg_clients_updated_at BEFORE UPDATE ON clients
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
ALTER TABLE clients ENABLE ROW LEVEL SECURITY;

-- =====================================================================================
-- 6. CASH_ACCOUNTS (cajas). balance desnormalizado, mantenido por trigger.
-- =====================================================================================
CREATE TABLE cash_accounts (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  name        text NOT NULL,
  type        text NOT NULL DEFAULT 'cash',          -- cash | bank | digital
  balance     numeric(12,2) NOT NULL DEFAULT 0,
  is_default  boolean NOT NULL DEFAULT false,
  is_active   boolean NOT NULL DEFAULT true,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_cash_accounts_tenant ON cash_accounts(tenant_id);
-- Una sola caja por defecto por tenant.
CREATE UNIQUE INDEX uniq_cash_default ON cash_accounts(tenant_id) WHERE is_default;
CREATE TRIGGER trg_cash_accounts_updated_at BEFORE UPDATE ON cash_accounts
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
ALTER TABLE cash_accounts ENABLE ROW LEVEL SECURITY;

-- =====================================================================================
-- 7. SALES + SALE_ITEMS
-- =====================================================================================
CREATE TABLE sales (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  client_id       uuid REFERENCES clients(id),         -- NULL = venta anonima
  status          sale_status NOT NULL DEFAULT 'completed',
  payment_method  payment_method NOT NULL DEFAULT 'cash',
  subtotal        numeric(12,2) NOT NULL DEFAULT 0,
  discount        numeric(12,2) NOT NULL DEFAULT 0,     -- monto absoluto, no porcentaje
  total           numeric(12,2) NOT NULL DEFAULT 0,
  notes           text,
  actor           text NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_sales_tenant ON sales(tenant_id, created_at DESC);
CREATE INDEX idx_sales_client ON sales(client_id);
CREATE TRIGGER trg_sales_updated_at BEFORE UPDATE ON sales
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
ALTER TABLE sales ENABLE ROW LEVEL SECURITY;

CREATE TABLE sale_items (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  sale_id       uuid NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
  product_id    uuid NOT NULL REFERENCES products(id),
  variant_id    uuid REFERENCES product_variants(id),
  product_name  text NOT NULL,                           -- snapshot al momento de la venta
  quantity      numeric(12,3) NOT NULL,
  unit_price    numeric(12,2) NOT NULL,
  unit_cost     numeric(12,2) NOT NULL DEFAULT 0,        -- snapshot, para calcular margen
  total         numeric(12,2) NOT NULL
);
CREATE INDEX idx_sale_items_sale    ON sale_items(sale_id);
CREATE INDEX idx_sale_items_product ON sale_items(product_id);
ALTER TABLE sale_items ENABLE ROW LEVEL SECURITY;

-- =====================================================================================
-- 8. TRANSACTIONS (movimientos de caja). Trigger mantiene cash_accounts.balance.
-- =====================================================================================
CREATE TABLE transactions (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  type            transaction_type NOT NULL,
  amount          numeric(12,2) NOT NULL CHECK (amount >= 0),
  category        text NOT NULL,
  description     text,
  cash_account_id uuid REFERENCES cash_accounts(id),
  sale_id         uuid REFERENCES sales(id),             -- NULL si no proviene de una venta
  actor           text NOT NULL,
  date            date NOT NULL DEFAULT CURRENT_DATE,
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_transactions_tenant  ON transactions(tenant_id, date DESC);
CREATE INDEX idx_transactions_account ON transactions(cash_account_id);
CREATE INDEX idx_transactions_sale    ON transactions(sale_id);
ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION apply_transaction_balance() RETURNS trigger AS $$
BEGIN
  IF NEW.cash_account_id IS NOT NULL THEN
    UPDATE cash_accounts
      SET balance = balance + CASE NEW.type WHEN 'income' THEN NEW.amount ELSE -NEW.amount END,
          updated_at = now()
      WHERE id = NEW.cash_account_id;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_apply_transaction_balance AFTER INSERT ON transactions
  FOR EACH ROW EXECUTE FUNCTION apply_transaction_balance();

-- =====================================================================================
-- 9. ACTIVITY_LOG (append-only). El service escribe aqui despues de cada mutacion.
-- =====================================================================================
CREATE TABLE activity_log (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  actor        actor_type NOT NULL,
  actor_label  text NOT NULL,
  action       text NOT NULL,                 -- "sale.created", "product.updated", "stock.adjusted"
  module       text NOT NULL,                 -- "sales", "inventory", "finance", "clients"
  detail       jsonb NOT NULL DEFAULT '{}',
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_activity_tenant ON activity_log(tenant_id, created_at DESC);
CREATE INDEX idx_activity_actor  ON activity_log(tenant_id, actor, created_at DESC);
ALTER TABLE activity_log ENABLE ROW LEVEL SECURITY;

-- =====================================================================================
-- 10. RPC: create_sale  -- venta atomica (valida stock, inserta todo o nada).
--     payload = { client_id?, payment_method?, cash_account_id?, discount?, notes?,
--                 items: [{ product_id, variant_id?, quantity, unit_price? }] }
--     Si unit_price falta, usa el precio del catalogo (products.price o variant.sale_price).
--     Lanza ERRCODE 'P0001' con DETAIL jsonb si el stock es insuficiente.
-- =====================================================================================
CREATE OR REPLACE FUNCTION create_sale(payload jsonb, p_tenant_id uuid, p_actor text)
RETURNS jsonb AS $$
DECLARE
  v_sale_id        uuid;
  v_account_id     uuid;
  v_client_id      uuid := NULLIF(payload->>'client_id', '')::uuid;
  v_discount       numeric(12,2) := COALESCE((payload->>'discount')::numeric, 0);
  v_payment        payment_method := COALESCE((payload->>'payment_method')::payment_method, 'cash');
  v_notes          text := payload->>'notes';
  v_subtotal       numeric(12,2) := 0;
  v_total          numeric(12,2);
  item             jsonb;
  v_product_id     uuid;
  v_variant_id     uuid;
  v_qty            numeric(12,3);
  v_unit_price     numeric(12,2);
  v_unit_cost      numeric(12,2);
  v_product_name   text;
  v_available      numeric(12,3);
  v_line_total     numeric(12,2);
BEGIN
  -- Resolver caja: la indicada, o la default del tenant, o la primera activa.
  v_account_id := NULLIF(payload->>'cash_account_id', '')::uuid;
  IF v_account_id IS NULL THEN
    SELECT id INTO v_account_id FROM cash_accounts
      WHERE tenant_id = p_tenant_id AND is_active ORDER BY is_default DESC, created_at ASC LIMIT 1;
  END IF;

  -- 1) Validar stock de cada item (bloqueando la fila) ANTES de tocar nada.
  FOR item IN SELECT * FROM jsonb_array_elements(payload->'items')
  LOOP
    v_product_id := (item->>'product_id')::uuid;
    v_variant_id := NULLIF(item->>'variant_id', '')::uuid;
    v_qty        := (item->>'quantity')::numeric;

    IF v_variant_id IS NULL THEN
      SELECT quantity INTO v_available FROM inventory
        WHERE tenant_id = p_tenant_id AND product_id = v_product_id AND variant_id IS NULL FOR UPDATE;
    ELSE
      SELECT quantity INTO v_available FROM inventory
        WHERE tenant_id = p_tenant_id AND product_id = v_product_id AND variant_id = v_variant_id FOR UPDATE;
    END IF;
    v_available := COALESCE(v_available, 0);

    IF v_available < v_qty THEN
      RAISE EXCEPTION 'insufficient_stock'
        USING ERRCODE = 'P0001',
              DETAIL  = jsonb_build_object('product_id', v_product_id,
                                           'requested', v_qty,
                                           'available', v_available)::text;
    END IF;
  END LOOP;

  -- 2) Crear la cabecera de la venta (subtotal/total se completan luego).
  INSERT INTO sales (tenant_id, client_id, status, payment_method, discount, actor, notes)
    VALUES (p_tenant_id, v_client_id, 'completed', v_payment, v_discount, p_actor, v_notes)
    RETURNING id INTO v_sale_id;

  -- 3) Lineas + movimientos de inventario (el trigger baja el stock).
  FOR item IN SELECT * FROM jsonb_array_elements(payload->'items')
  LOOP
    v_product_id := (item->>'product_id')::uuid;
    v_variant_id := NULLIF(item->>'variant_id', '')::uuid;
    v_qty        := (item->>'quantity')::numeric;

    -- Snapshot de nombre, costo y precio desde el catalogo.
    SELECT p.name,
           COALESCE(pv.cost_price, p.cost_price),
           COALESCE((item->>'unit_price')::numeric, pv.sale_price, p.price, 0)
      INTO v_product_name, v_unit_cost, v_unit_price
      FROM products p
      LEFT JOIN product_variants pv ON pv.id = v_variant_id
      WHERE p.id = v_product_id;

    v_line_total := ROUND(v_unit_price * v_qty, 2);
    v_subtotal   := v_subtotal + v_line_total;

    INSERT INTO sale_items (tenant_id, sale_id, product_id, variant_id, product_name,
                            quantity, unit_price, unit_cost, total)
      VALUES (p_tenant_id, v_sale_id, v_product_id, v_variant_id, v_product_name,
              v_qty, v_unit_price, COALESCE(v_unit_cost, 0), v_line_total);

    INSERT INTO inventory_movements (tenant_id, product_id, variant_id, type, quantity,
                                     unit_cost, reference_id, actor)
      VALUES (p_tenant_id, v_product_id, v_variant_id, 'sale', v_qty,
              v_unit_cost, v_sale_id, p_actor);
  END LOOP;

  -- 4) Cerrar totales.
  v_total := GREATEST(v_subtotal - v_discount, 0);
  UPDATE sales SET subtotal = v_subtotal, total = v_total WHERE id = v_sale_id;

  -- 5) Ingreso en caja (el trigger sube el balance).
  INSERT INTO transactions (tenant_id, type, amount, category, description,
                            cash_account_id, sale_id, actor)
    VALUES (p_tenant_id, 'income', v_total, 'Ventas',
            'Venta ' || v_sale_id, v_account_id, v_sale_id, p_actor);

  -- 6) Rollups del cliente.
  IF v_client_id IS NOT NULL THEN
    UPDATE clients
      SET total_purchases  = total_purchases + v_total,
          purchase_count   = purchase_count + 1,
          last_purchase_at = now()
      WHERE id = v_client_id AND tenant_id = p_tenant_id;
  END IF;

  -- Devolver la venta completa (cabecera + items) para que el service la retorne tal cual.
  RETURN (
    SELECT to_jsonb(s) || jsonb_build_object(
      'items', COALESCE((SELECT jsonb_agg(to_jsonb(si)) FROM sale_items si WHERE si.sale_id = s.id), '[]'::jsonb)
    )
    FROM sales s WHERE s.id = v_sale_id
  );
END;
$$ LANGUAGE plpgsql;

-- =====================================================================================
-- 11. RPC: cancel_sale  -- revierte stock e ingreso de forma atomica.
--     La venta original no se borra: queda con status = 'cancelled'.
-- =====================================================================================
CREATE OR REPLACE FUNCTION cancel_sale(p_sale_id uuid, p_tenant_id uuid, p_actor text)
RETURNS jsonb AS $$
DECLARE
  v_status     sale_status;
  v_total      numeric(12,2);
  v_client_id  uuid;
  v_account_id uuid;
  it           record;
BEGIN
  SELECT status, total, client_id INTO v_status, v_total, v_client_id
    FROM sales WHERE id = p_sale_id AND tenant_id = p_tenant_id FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'sale_not_found' USING ERRCODE = 'P0002';
  END IF;
  IF v_status = 'cancelled' THEN
    RAISE EXCEPTION 'sale_already_cancelled' USING ERRCODE = 'P0003';
  END IF;

  UPDATE sales SET status = 'cancelled' WHERE id = p_sale_id;

  -- Reponer stock con movimientos 'return' (el trigger sube el stock).
  FOR it IN SELECT product_id, variant_id, quantity, unit_cost FROM sale_items WHERE sale_id = p_sale_id
  LOOP
    INSERT INTO inventory_movements (tenant_id, product_id, variant_id, type, quantity,
                                     unit_cost, reference_id, actor, notes)
      VALUES (p_tenant_id, it.product_id, it.variant_id, 'return', it.quantity,
              it.unit_cost, p_sale_id, p_actor, 'Cancelacion de venta');
  END LOOP;

  -- Revertir el ingreso: egreso por el mismo monto en la misma caja del ingreso original.
  SELECT cash_account_id INTO v_account_id
    FROM transactions WHERE sale_id = p_sale_id AND type = 'income' ORDER BY created_at ASC LIMIT 1;

  INSERT INTO transactions (tenant_id, type, amount, category, description,
                            cash_account_id, sale_id, actor)
    VALUES (p_tenant_id, 'expense', v_total, 'Cancelaciones',
            'Cancelacion venta ' || p_sale_id, v_account_id, p_sale_id, p_actor);

  -- Revertir rollups del cliente.
  IF v_client_id IS NOT NULL THEN
    UPDATE clients
      SET total_purchases = GREATEST(total_purchases - v_total, 0),
          purchase_count  = GREATEST(purchase_count - 1, 0)
      WHERE id = v_client_id AND tenant_id = p_tenant_id;
  END IF;

  RETURN (SELECT to_jsonb(s) FROM sales s WHERE s.id = p_sale_id);
END;
$$ LANGUAGE plpgsql;

NOTIFY pgrst, 'reload schema';

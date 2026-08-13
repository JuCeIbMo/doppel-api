-- schema_erp.sql
-- Esquema unico del modulo ERP, drop-and-recreate. Reemplaza la cadena
-- migration_v8_erp.sql + migration_v9_product_tags.sql + migration_v10_sale_idempotency.sql +
-- migration_v11_product_search.sql + migration_v12_admin_actions.sql + la parte de `products`
-- de migration_v5.sql, ya sin `product_variants` (ningun agente las usa).
--
-- Ejecutar DESPUES de migration.sql, migration_auth.sql, migration_v2.sql, migration_v3.sql,
-- migration_v4.sql, migration_v6_nanobot_runtime.sql, migration_v7_whatsapp_offboarding.sql.
-- Esos archivos y la tabla `business_info` de migration_v5.sql NO se tocan: ahi viven las
-- credenciales de Meta y el login.
--
-- Reejecutable: dropea sus propias tablas/tipos y los vuelve a crear. Los datos de
-- catalogo/ventas/clientes son descartables; lo que no se puede perder (tenants,
-- whatsapp_accounts, bot_configs, messages, login_attempts) vive fuera de este archivo.
--
-- Principios (heredados de migration_v8_erp.sql):
--   * El stock nunca queda negativo: create_sale valida ANTES de insertar movimientos.
--   * Operaciones compuestas (venta, cancelacion) son atomicas: viven en funciones PL/pgSQL.
--   * inventory.quantity y cash_accounts.balance son desnormalizados, mantenidos por trigger.
--   * inventory_movements y activity_log son append-only (nunca se editan ni borran).
--   * Reutiliza la funcion update_updated_at() existente (migration.sql).

-- =====================================================================================
-- 0. DROP (orden de dependencia)
-- =====================================================================================
DROP TABLE IF EXISTS admin_pending_actions, activity_log, transactions, sale_items, sales,
  cash_accounts, clients, inventory_movements, inventory, products CASCADE;

DROP TYPE IF EXISTS movement_type CASCADE;
DROP TYPE IF EXISTS sale_status CASCADE;
DROP TYPE IF EXISTS payment_method CASCADE;
DROP TYPE IF EXISTS transaction_type CASCADE;
DROP TYPE IF EXISTS actor_type CASCADE;

-- =====================================================================================
-- 1. ENUMS
-- =====================================================================================
CREATE TYPE movement_type    AS ENUM ('purchase', 'sale', 'adjustment_in', 'adjustment_out', 'return', 'loss');
CREATE TYPE sale_status      AS ENUM ('completed', 'cancelled');
CREATE TYPE payment_method   AS ENUM ('cash', 'card', 'transfer', 'whatsapp', 'other');
CREATE TYPE transaction_type AS ENUM ('income', 'expense');
-- 'cashier' se incluye para compatibilidad futura (modo PIN, v2) aunque v1 no lo emita.
CREATE TYPE actor_type       AS ENUM ('owner', 'cashier', 'whatsapp_bot', 'admin_bot');

-- =====================================================================================
-- 2. BUSQUEDA FULL-TEXT: extension + funcion del documento indexado.
--    Se define antes de `products` porque la columna generada la referencia.
-- =====================================================================================
CREATE EXTENSION IF NOT EXISTS unaccent;

-- Las columnas generadas solo pueden llamar funciones IMMUTABLE. `unaccent` viene
-- marcada STABLE, asi que se encapsula junto con la configuracion fija del documento.
-- Los pesos priorizan nombre > tags > descripcion.
CREATE OR REPLACE FUNCTION public.products_search_document(
  p_name text,
  p_description text,
  p_tags text[]
)
RETURNS tsvector
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
AS $$
  SELECT
    setweight(
      to_tsvector(
        'spanish'::regconfig,
        unaccent('unaccent', coalesce(p_name, ''))
      ),
      'A'
    )
    || setweight(
      to_tsvector(
        'spanish'::regconfig,
        unaccent('unaccent', array_to_string(coalesce(p_tags, '{}'), ' '))
      ),
      'B'
    )
    || setweight(
      to_tsvector(
        'spanish'::regconfig,
        unaccent('unaccent', coalesce(p_description, ''))
      ),
      'C'
    );
$$;

-- =====================================================================================
-- 3. PRODUCTS. Sin variantes: `has_variants` no existe. `image_url` es NOT NULL porque
--    toda alta de producto pasa por la foto (ver app/ai_core/tools/catalog.py).
-- =====================================================================================
CREATE TABLE products (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  name                text NOT NULL,
  description         text DEFAULT '',
  price               numeric(12,2),
  available           boolean NOT NULL DEFAULT true,
  sku                 text,
  barcode             text,
  category            text,
  image_url           text NOT NULL,
  cost_price          numeric(12,2) NOT NULL DEFAULT 0,
  unit                text NOT NULL DEFAULT 'unidad',
  low_stock_threshold integer NOT NULL DEFAULT 5,
  tags                text[] NOT NULL DEFAULT '{}',
  admin_action_id     uuid UNIQUE,
  search_document     tsvector GENERATED ALWAYS AS (
                         public.products_search_document(name, description, tags)
                       ) STORED,
  created_at          timestamptz DEFAULT now(),
  updated_at          timestamptz DEFAULT now()
);
CREATE INDEX idx_products_tenant           ON products(tenant_id);
CREATE INDEX idx_products_barcode          ON products(tenant_id, barcode);
CREATE INDEX idx_products_sku              ON products(tenant_id, sku);
CREATE INDEX idx_products_search_document  ON products USING gin (search_document);
CREATE TRIGGER trg_products_updated_at BEFORE UPDATE ON products
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
ALTER TABLE products ENABLE ROW LEVEL SECURITY;

-- =====================================================================================
-- 4. RPC: search_products_catalog. Full-text en espanol sobre nombre + tags + descripcion,
--    con ranking ponderado; mantiene tenant_id/available dentro de la consulta para que
--    ningun caller pueda olvidarlos.
-- =====================================================================================
CREATE OR REPLACE FUNCTION public.search_products_catalog(
  p_tenant_id uuid,
  p_query text,
  p_limit integer DEFAULT 21,
  p_offset integer DEFAULT 0
)
RETURNS TABLE (
  id uuid,
  name text,
  description text,
  price numeric,
  available boolean,
  tags text[],
  search_rank real
)
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = public
AS $$
  WITH query_lexemes AS (
    SELECT unnest(
      tsvector_to_array(
        to_tsvector(
          'spanish'::regconfig,
          unaccent('unaccent', coalesce(p_query, ''))
        )
      )
    ) AS value
  ),
  query_text AS (
    -- OR mejora el recall: no exige que cada palabra del cliente este en el
    -- mismo producto. ts_rank_cd premia los productos que matchean mas terminos
    -- y respeta los pesos nombre (A), tags (B), descripcion (C).
    SELECT string_agg(quote_literal(value), ' | ') AS value
    FROM query_lexemes
  ),
  parsed_query AS (
    SELECT CASE
      WHEN value IS NULL THEN NULL
      ELSE to_tsquery('spanish'::regconfig, value)
    END AS value
    FROM query_text
  )
  SELECT
    p.id,
    p.name,
    p.description,
    p.price,
    p.available,
    p.tags,
    ts_rank_cd(p.search_document, q.value) AS search_rank
  FROM public.products AS p
  CROSS JOIN parsed_query AS q
  WHERE p.tenant_id = p_tenant_id
    AND p.available = true
    AND q.value IS NOT NULL
    AND p.search_document @@ q.value
  ORDER BY search_rank DESC, p.name ASC, p.id ASC
  LIMIT greatest(1, least(coalesce(p_limit, 21), 200))
  OFFSET greatest(coalesce(p_offset, 0), 0);
$$;

-- =====================================================================================
-- 5. INVENTORY: stock actual. Una fila por producto. Solo el trigger la toca.
-- =====================================================================================
CREATE TABLE inventory (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  product_id  uuid NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  quantity    numeric(12,3) NOT NULL DEFAULT 0,
  updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uniq_inventory_product ON inventory(tenant_id, product_id);
CREATE INDEX idx_inventory_tenant ON inventory(tenant_id);
ALTER TABLE inventory ENABLE ROW LEVEL SECURITY;

-- =====================================================================================
-- 6. INVENTORY_MOVEMENTS: registro inmutable de cada movimiento de stock.
-- =====================================================================================
CREATE TABLE inventory_movements (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  product_id    uuid NOT NULL REFERENCES products(id),
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

  UPDATE inventory SET quantity = quantity + delta, updated_at = now()
    WHERE tenant_id = NEW.tenant_id AND product_id = NEW.product_id;
  IF NOT FOUND THEN
    INSERT INTO inventory (tenant_id, product_id, quantity)
      VALUES (NEW.tenant_id, NEW.product_id, delta);
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_apply_inventory_movement AFTER INSERT ON inventory_movements
  FOR EACH ROW EXECUTE FUNCTION apply_inventory_movement();

-- =====================================================================================
-- 7. CLIENTS
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
-- 8. CASH_ACCOUNTS (cajas). balance desnormalizado, mantenido por trigger.
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
-- 9. SALES + SALE_ITEMS. sales.idempotency_key protege create_order de reintentos del LLM.
-- =====================================================================================
CREATE TABLE sales (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  client_id        uuid REFERENCES clients(id),         -- NULL = venta anonima
  status           sale_status NOT NULL DEFAULT 'completed',
  payment_method   payment_method NOT NULL DEFAULT 'cash',
  subtotal         numeric(12,2) NOT NULL DEFAULT 0,
  discount         numeric(12,2) NOT NULL DEFAULT 0,     -- monto absoluto, no porcentaje
  total            numeric(12,2) NOT NULL DEFAULT 0,
  notes            text,
  actor            text NOT NULL,
  idempotency_key  text,                                 -- NULL = venta sin clave (p.ej. dashboard)
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_sales_tenant ON sales(tenant_id, created_at DESC);
CREATE INDEX idx_sales_client ON sales(client_id);
CREATE UNIQUE INDEX idx_sales_idempotency ON sales(tenant_id, idempotency_key)
  WHERE idempotency_key IS NOT NULL;
CREATE TRIGGER trg_sales_updated_at BEFORE UPDATE ON sales
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
ALTER TABLE sales ENABLE ROW LEVEL SECURITY;

CREATE TABLE sale_items (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  sale_id       uuid NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
  product_id    uuid NOT NULL REFERENCES products(id),
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
-- 10. TRANSACTIONS (movimientos de caja). Trigger mantiene cash_accounts.balance.
--     admin_action_id: idempotencia de escrituras del agente admin (ver admin_pending_actions).
-- =====================================================================================
CREATE TABLE transactions (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  type             transaction_type NOT NULL,
  amount           numeric(12,2) NOT NULL CHECK (amount >= 0),
  category         text NOT NULL,
  description      text,
  cash_account_id  uuid REFERENCES cash_accounts(id),
  sale_id          uuid REFERENCES sales(id),             -- NULL si no proviene de una venta
  actor            text NOT NULL,
  admin_action_id  uuid UNIQUE,
  date             date NOT NULL DEFAULT CURRENT_DATE,
  created_at       timestamptz NOT NULL DEFAULT now()
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
-- 11. ACTIVITY_LOG (append-only). El service escribe aqui despues de cada mutacion.
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
-- 12. ADMIN_PENDING_ACTIONS: aprobaciones durables para mutaciones pedidas por el agente
--     admin de WhatsApp. Ninguna escritura de negocio ocurre al crear la accion: una
--     respuesta interactiva separada la mueve primero a `confirmed`.
-- =====================================================================================
CREATE TABLE admin_pending_actions (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  thread_id     text NOT NULL,
  kind          text NOT NULL,
  payload       jsonb NOT NULL,
  summary       text NOT NULL,
  status        text NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'confirmed', 'cancelled', 'executing', 'executed', 'expired')),
  expires_at    timestamptz NOT NULL,
  result        jsonb,
  created_at    timestamptz NOT NULL DEFAULT now(),
  confirmed_at  timestamptz,
  executed_at   timestamptz
);
CREATE INDEX admin_pending_actions_lookup_idx
  ON admin_pending_actions (tenant_id, thread_id, status, expires_at);
ALTER TABLE admin_pending_actions ENABLE ROW LEVEL SECURITY;

-- =====================================================================================
-- 13. RPC: create_sale  -- venta atomica (valida stock, inserta todo o nada, idempotente).
--     payload = { client_id?, payment_method?, cash_account_id?, discount?, notes?,
--                 idempotency_key?, items: [{ product_id, quantity, unit_price? }] }
--     Si unit_price falta, usa products.price. Lanza ERRCODE 'P0001' con DETAIL jsonb si
--     el stock es insuficiente. Con idempotency_key repetida devuelve la misma venta con
--     idempotent_replay: true en vez de crear otra.
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
  v_idem           text := NULLIF(payload->>'idempotency_key', '');
  v_subtotal       numeric(12,2) := 0;
  v_total          numeric(12,2);
  item             jsonb;
  v_product_id     uuid;
  v_qty            numeric(12,3);
  v_unit_price     numeric(12,2);
  v_unit_cost      numeric(12,2);
  v_product_name   text;
  v_available      numeric(12,3);
  v_line_total     numeric(12,2);
BEGIN
  -- 0) Idempotencia: si esta venta ya se registro con la misma clave, devolverla.
  --    El advisory lock (por transaccion, se suelta solo al COMMIT/ROLLBACK) evita
  --    que dos reintentos simultaneos pasen los dos el chequeo.
  IF v_idem IS NOT NULL THEN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_tenant_id::text || ':' || v_idem, 0));

    SELECT id INTO v_sale_id FROM sales
      WHERE tenant_id = p_tenant_id AND idempotency_key = v_idem;

    IF v_sale_id IS NOT NULL THEN
      RETURN (
        SELECT to_jsonb(s) || jsonb_build_object(
          'items', COALESCE((SELECT jsonb_agg(to_jsonb(si)) FROM sale_items si WHERE si.sale_id = s.id), '[]'::jsonb),
          'idempotent_replay', true
        )
        FROM sales s WHERE s.id = v_sale_id
      );
    END IF;
  END IF;

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
    v_qty        := (item->>'quantity')::numeric;

    SELECT quantity INTO v_available FROM inventory
      WHERE tenant_id = p_tenant_id AND product_id = v_product_id FOR UPDATE;
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
  INSERT INTO sales (tenant_id, client_id, status, payment_method, discount, actor, notes,
                     idempotency_key)
    VALUES (p_tenant_id, v_client_id, 'completed', v_payment, v_discount, p_actor, v_notes,
            v_idem)
    RETURNING id INTO v_sale_id;

  -- 3) Lineas + movimientos de inventario (el trigger baja el stock).
  FOR item IN SELECT * FROM jsonb_array_elements(payload->'items')
  LOOP
    v_product_id := (item->>'product_id')::uuid;
    v_qty        := (item->>'quantity')::numeric;

    -- Snapshot de nombre, costo y precio desde el catalogo.
    SELECT p.name, p.cost_price, COALESCE((item->>'unit_price')::numeric, p.price, 0)
      INTO v_product_name, v_unit_cost, v_unit_price
      FROM products p
      WHERE p.id = v_product_id;

    v_line_total := ROUND(v_unit_price * v_qty, 2);
    v_subtotal   := v_subtotal + v_line_total;

    INSERT INTO sale_items (tenant_id, sale_id, product_id, product_name,
                            quantity, unit_price, unit_cost, total)
      VALUES (p_tenant_id, v_sale_id, v_product_id, v_product_name,
              v_qty, v_unit_price, COALESCE(v_unit_cost, 0), v_line_total);

    INSERT INTO inventory_movements (tenant_id, product_id, type, quantity,
                                     unit_cost, reference_id, actor)
      VALUES (p_tenant_id, v_product_id, 'sale', v_qty,
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
      'items', COALESCE((SELECT jsonb_agg(to_jsonb(si)) FROM sale_items si WHERE si.sale_id = s.id), '[]'::jsonb),
      'idempotent_replay', false
    )
    FROM sales s WHERE s.id = v_sale_id
  );
END;
$$ LANGUAGE plpgsql;

-- =====================================================================================
-- 14. RPC: cancel_sale  -- revierte stock e ingreso de forma atomica.
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
  FOR it IN SELECT product_id, quantity, unit_cost FROM sale_items WHERE sale_id = p_sale_id
  LOOP
    INSERT INTO inventory_movements (tenant_id, product_id, type, quantity,
                                     unit_cost, reference_id, actor, notes)
      VALUES (p_tenant_id, it.product_id, 'return', it.quantity,
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

-- =====================================================================================
-- 15. STORAGE: bucket publico para imagenes de producto (idempotente).
-- =====================================================================================
INSERT INTO storage.buckets (id, name, public)
VALUES ('product-images', 'product-images', true)
ON CONFLICT (id) DO NOTHING;

-- Lectura publica de los objetos del bucket (las URLs publicas se sirven al front).
DROP POLICY IF EXISTS "product-images public read" ON storage.objects;
CREATE POLICY "product-images public read"
  ON storage.objects FOR SELECT
  USING (bucket_id = 'product-images');

-- Nota: no se crean policies de INSERT/UPDATE/DELETE porque el backend escribe con la
-- service_role key, que ignora RLS. El bucket NO es escribible publicamente.

NOTIFY pgrst, 'reload schema';

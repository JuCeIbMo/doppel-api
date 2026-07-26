-- migration_v10_sale_idempotency.sql
-- Ejecutar DESPUES de migration_v9_product_tags.sql.
-- Cierra el hueco de idempotencia de `create_order` (el bot vendedor):
--   Un reintento del LLM con los mismos items creaba una SEGUNDA venta: descontaba
--   stock de nuevo, sumaba de nuevo a caja y a los rollups del cliente. No se puede
--   tapar del lado de Python con un cache en proceso (no sobrevive un restart ni
--   sirve con varios workers): la garantia tiene que vivir en la misma transaccion
--   que la venta.
--
-- Agrega:
--   1. sales.idempotency_key (text, NULL = venta sin clave, p.ej. el dashboard).
--   2. Indice unico parcial (tenant_id, idempotency_key) — el respaldo duro.
--   3. create_sale acepta payload.idempotency_key: si ya existe una venta con esa
--      clave para el tenant, devuelve LA MISMA venta con `idempotent_replay: true`
--      en vez de crear otra. Sin clave, el comportamiento es identico al de v8.
--
-- Principios:
--   * La columna es nullable y el indice es parcial: las ventas existentes y las del
--     dashboard (sin clave) no se ven afectadas ni colisionan entre si.
--   * pg_advisory_xact_lock ANTES del SELECT: dos reintentos concurrentes con la misma
--     clave se serializan, asi el segundo ve la venta del primero en vez de pasar los
--     dos el chequeo y chocar contra el indice unico. El indice queda igual como
--     backstop (otro proceso, otra ruta, hash colisionado).
--   * Idempotente: se puede correr dos veces sin romper nada.

-- =====================================================================================
-- 1. SALES: clave de idempotencia
-- =====================================================================================
ALTER TABLE sales
  ADD COLUMN IF NOT EXISTS idempotency_key text;

CREATE UNIQUE INDEX IF NOT EXISTS idx_sales_idempotency
  ON sales(tenant_id, idempotency_key)
  WHERE idempotency_key IS NOT NULL;

-- =====================================================================================
-- 2. RPC: create_sale  -- misma funcion de migration_v8, + idempotencia.
--     payload = { client_id?, payment_method?, cash_account_id?, discount?, notes?,
--                 idempotency_key?, items: [{ product_id, variant_id?, quantity, unit_price? }] }
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
  v_idem           text := NULLIF(payload->>'idempotency_key', '');
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
  INSERT INTO sales (tenant_id, client_id, status, payment_method, discount, actor, notes,
                     idempotency_key)
    VALUES (p_tenant_id, v_client_id, 'completed', v_payment, v_discount, p_actor, v_notes,
            v_idem)
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
      'items', COALESCE((SELECT jsonb_agg(to_jsonb(si)) FROM sale_items si WHERE si.sale_id = s.id), '[]'::jsonb),
      'idempotent_replay', false
    )
    FROM sales s WHERE s.id = v_sale_id
  );
END;
$$ LANGUAGE plpgsql;

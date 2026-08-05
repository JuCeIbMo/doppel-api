-- migration_v11_product_search.sql
-- Ejecutar DESPUES de migration_v10_sale_idempotency.sql.
--
-- Mejora la búsqueda del catálogo público: en vez de comparar solamente
-- products.name con ILIKE, indexa nombre + descripción + tags con el diccionario
-- español de PostgreSQL. La RPC mantiene tenant_id y available=true dentro de
-- la consulta para que ningún caller pueda olvidarlos.

CREATE EXTENSION IF NOT EXISTS unaccent;

-- Las columnas generadas sólo pueden llamar funciones IMMUTABLE. `unaccent`
-- viene marcada STABLE, así que se encapsula junto con la configuración fija
-- del documento. Los pesos priorizan nombre > tags > descripción.
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

ALTER TABLE public.products
  ADD COLUMN IF NOT EXISTS search_document tsvector
  GENERATED ALWAYS AS (
    public.products_search_document(name, description, tags)
  ) STORED;

CREATE INDEX IF NOT EXISTS idx_products_search_document
  ON public.products USING gin (search_document);

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
    -- OR mejora el recall: no exige que cada palabra del cliente esté en el
    -- mismo producto. ts_rank_cd premia los productos que matchean más términos
    -- y respeta los pesos nombre (A), tags (B), descripción (C).
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

NOTIFY pgrst, 'reload schema';

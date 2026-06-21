-- migration_v9_product_tags.sql
-- Ejecutar DESPUES de migration_v8_erp.sql.
-- Agrega:
--   1. products.tags (text[]): keywords/etiquetas del producto. Las llena la herramienta
--      de visión (Gemini) al subir la imagen, y el agente vendedor las usa en search_catalog
--      para matchear mejor las consultas de los clientes.
--   2. Bucket de Supabase Storage `product-images` (lectura pública): aloja las imágenes
--      optimizadas (WebP) de los productos. Las escrituras van con service_role (bypassa RLS).
--
-- Principios:
--   * tags tiene DEFAULT '{}' para que los INSERT existentes sigan validos.
--   * El bucket es publico de lectura (las URLs van al front y al catalogo); subir/borrar
--     solo lo hace el backend con la service_role key.

-- =====================================================================================
-- 1. PRODUCTS: columna de etiquetas para búsqueda/IA
-- =====================================================================================
ALTER TABLE products
  ADD COLUMN IF NOT EXISTS tags text[] NOT NULL DEFAULT '{}';

-- =====================================================================================
-- 2. STORAGE: bucket público para imágenes de productos
--    (idempotente; si ya existe, no falla)
-- =====================================================================================
INSERT INTO storage.buckets (id, name, public)
VALUES ('product-images', 'product-images', true)
ON CONFLICT (id) DO NOTHING;

-- Lectura pública de los objetos del bucket (las URLs públicas se sirven al front).
DROP POLICY IF EXISTS "product-images public read" ON storage.objects;
CREATE POLICY "product-images public read"
  ON storage.objects FOR SELECT
  USING (bucket_id = 'product-images');

-- Nota: no se crean policies de INSERT/UPDATE/DELETE porque el backend escribe con la
-- service_role key, que ignora RLS. El bucket NO es escribible públicamente.

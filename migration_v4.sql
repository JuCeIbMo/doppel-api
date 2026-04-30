-- migration_v4.sql
-- Ejecutar DESPUES de migration.sql, migration_auth.sql, migration_v2.sql, migration_v3.sql
-- Habilita el split manager / client para el agente de nanobot.

-- 1. Lista de telefonos admin que reciben respuestas del manager agent
--    (numeros del operador del negocio, en formato E.164 sin '+', tal como llegan en webhook).
ALTER TABLE bot_configs
  ADD COLUMN IF NOT EXISTS admin_phones jsonb NOT NULL DEFAULT '[]'::jsonb;

-- 2. Prompt para el manager agent. El client agent sigue usando system_prompt.
ALTER TABLE bot_configs
  ADD COLUMN IF NOT EXISTS manager_prompt text NOT NULL DEFAULT
    'Eres el agente manager de un negocio que opera por WhatsApp. '
    'Hablas exclusivamente con el operador del negocio, no con clientes finales. '
    'Tu rol es leer y modificar la configuracion del bot que atiende a los clientes. '
    'Antes de aplicar cualquier cambio: 1) explica que vas a hacer, 2) pide confirmacion, '
    '3) solo entonces ejecuta la tool con confirmed=true. '
    'Si el operador pide algo fuera de tu alcance, dilo y sugiere alternativas.';

-- 3. Indice util para identificar admins rapido en el webhook (busqueda jsonb @> '"<phone>"')
CREATE INDEX IF NOT EXISTS idx_bot_configs_admin_phones
  ON bot_configs USING gin (admin_phones);

NOTIFY pgrst, 'reload schema';

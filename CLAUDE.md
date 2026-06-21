# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Correr toda la suite de tests
python3 -m pytest tests/ -q

# Correr un test individual
python3 -m pytest tests/test_storefront.py::test_register_sale_happy_path -v

# Arrancar el servidor localmente (requiere .env)
uvicorn app.main:app --reload

# Arrancar con Docker Compose (incluye Postgres para Agno)
docker compose up
```

**No hay conftest.py ni pytest.ini.** Cada archivo de test setea sus propias env vars con `os.environ.setdefault(...)` al inicio, antes del primer import de la app. El orden importa: las vars deben estar antes de `import app.*`.

## Arquitectura

**doppel-api** es una API multi-tenant para negocios con bot de WhatsApp. Cada "tenant" es un negocio con su propio catálogo, ventas, clientes y configuración de bot.

### Dos bases de datos

- **Supabase** (Postgres gestionado): datos del ERP — productos, ventas, clientes, cuentas de WhatsApp, configuración del bot. El cliente es **síncrono** (`supabase-py`). Todos los services llaman `get_supabase()` (singleton en `app/services/supabase_client.py`).
- **Agno Postgres** (container propio, `AGNO_DB_URL`): historial de conversaciones y memoria de los agentes IA. Lo gestiona Agno vía `PostgresDb` (singleton en `app/ai/factories/base.py`).

### Capa ERP

Toda operación ERP recibe un `ERPContext` (tenant_id + actor). Eso garantiza que ninguna query olvide el scope del tenant.

```
ERPContext(tenant_id, actor)  ←  construido por:
  - get_erp_context()         →  endpoints del dashboard (actor="owner")
  - bot_context()             →  agentes IA (actor="whatsapp_bot" | "admin_bot")
```

Los services nunca lanzan `HTTPException`. Lanzan subclases de `ERPError` (`NotFound`, `InsufficientStock`, `Conflict`, etc.) que el handler global de `main.py` convierte a JSON.

### Capa de IA (Agno in-process)

El bot vive dentro del proceso doppel-api (no es un microservicio separado). Flujo por mensaje:

```
POST /webhook/whatsapp
  → _process_bot_response() [background task]
    → app/ai/bridge.respond()          ← única puerta pública del subsistema AI
      → get_client_agent() / get_manager_agent()
        → agent.arun(text)
          → storefront.search_catalog / register_sale  (client)
          → ERP services directamente                  (manager)
```

**`app/services/storefront.py`** es la capa que expone el ERP al agente vendedor. Devuelve shapes "lean" (solo lo que la IA necesita) y evita que el bot toque los ERP services directamente.

**`app/ai/__init__.py`** re-exporta solo `respond` — es la única interfaz pública del módulo AI.

Los agentes se diferencian por modo:
- `client` → `get_client_agent`: tools de lectura de catálogo + `register_sale` + WhatsApp interactivo
- `manager` → `get_manager_agent`: tools ERP completas (dashboard, stock, ventas, ajustes) + WhatsApp

### Convenciones importantes

- **`ok` en respuestas de tools**: `storefront.register_sale` devuelve siempre `{"ok": bool, ...}`. Éxito = `ok: True`, error = `ok: False, "error": code, "message": ...`.
- **`bridge.respond` devuelve `str | None`**: `None` = el agente crasheó (se loguea como ERROR), `""` = respondió vacío legítimamente. El webhook no envía nada en ambos casos pero los diferencia en logs.
- **Supabase es síncrono en contexto async**: todos los `async def` de los ERP services hacen I/O síncrono. Es una limitación conocida del cliente `supabase-py`.
- **`log_activity` es best-effort**: nunca lanza excepciones — un fallo de audit log no debe romper la operación.

### Variables de entorno relevantes

| Variable | Efecto |
|----------|--------|
| `LOG_LEVEL=DEBUG` | Activa todos los `logger.debug(...)` del código doppel-api (bridge, webhook, erp) |
| `AI_DEBUG=true` | Activa `debug_mode` de Agno: loguea los prompts completos, tool calls y tokens |
| `AI_CORE_URL` | Cualquier valor no vacío activa el bot; vacío lo desactiva sin tocar código |
| `AGNO_DB_URL` | Postgres para Agno. Si está vacío, los agentes corren sin persistencia de sesión |

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

# Arrancar con Docker Compose (incluye el Postgres del checkpointer, chat-postgres)
docker compose up
```

**No hay conftest.py ni pytest.ini.** Cada archivo de test setea sus propias env vars con `os.environ.setdefault(...)` al inicio, antes del primer import de la app. El orden importa: las vars deben estar antes de `import app.*`.

## Arquitectura

**doppel-api** es una API multi-tenant para negocios con bot de WhatsApp. Cada "tenant" es un negocio con su propio catálogo, ventas, clientes y configuración de bot.

### Dos bases de datos

- **Supabase** (Postgres gestionado): datos del ERP — productos, ventas, clientes, cuentas de WhatsApp, configuración del bot. El cliente es **async** (`AsyncClient` de `supabase-py`). Todos los services llaman `get_supabase()` (singleton en `app/services/supabase_client.py`) y **awaitean** el `.execute()`.
- **Chat Postgres** (container propio, `CHAT_DB_URL`): historial de conversaciones del bot. Lo gestiona LangGraph vía `AsyncPostgresSaver` (`app/ai_core/persistence/checkpointer.py`).

### Capa ERP

Toda operación ERP recibe un `ERPContext` (tenant_id + actor). Eso garantiza que ninguna query olvide el scope del tenant.

```
ERPContext(tenant_id, actor)  ←  construido por:
  - get_erp_context()         →  endpoints del dashboard (actor="owner")
  - bot_context()             →  agentes IA (actor="whatsapp_bot" | "admin_bot")
```

Los services nunca lanzan `HTTPException`. Lanzan subclases de `ERPError` (`NotFound`, `InsufficientStock`, `Conflict`, etc.) que el handler global de `main.py` convierte a JSON.

### Capa de IA (LangChain + LangGraph in-process)

El bot vive dentro del proceso doppel-api (no es un microservicio separado). Flujo por mensaje:

```
POST /webhook/whatsapp
  → _process_bot_response() [background task]
    → app/ai_core/bridge.respond()     ← única puerta pública del subsistema AI
      → build_public_agent() / build_admin_agent()   (cacheado por tenant+rol)
        → await agent.ainvoke(...)
          → storefront.search_catalog / register_sale  (public)
          → ERP services directamente                  (admin)
```

**Todo el camino es async.** LangChain no hace fallback de async a sync: si un middleware
define sólo `wrap_tool_call` y el grafo corre con `ainvoke`, lanza `NotImplementedError`.
Cada middleware debe implementar **ambos** hooks (`wrap_*` y `awrap_*`), y el checkpointer
debe ser `AsyncPostgresSaver` (el `PostgresSaver` sync no implementa `aget_tuple`/`aput`).

**Las tools de negocio son `async def` y se registran con `coroutine=`, nunca `func=`**
(ver `app/ai_core/tools/context.py`). Con `func=`, LangChain las trata como síncronas y le
entrega al modelo un coroutine sin ejecutar, en silencio.

**`app/services/storefront.py`** es la capa que expone el ERP al agente vendedor. Devuelve shapes "lean" (solo lo que la IA necesita) y evita que el bot toque los ERP services directamente.

El rol lo resuelve `resolve_role(user_phone, tenant)` por el número del remitente (verificado por Meta), nunca por el texto del mensaje:
- `public` → swarm de especialistas (greeter/catalog/objection/closer) + `create_order`
- `admin` → tools ERP completas (reportes, stock, alta de productos, config)

### Herramienta de imagen de producto (Gemini, separada del bot)

`POST /erp/products/analyze-image` es una herramienta del front, **aislada del bot**:
recibe una imagen, la optimiza (`app/services/images.py` — WebP cuadrado con fondo blanco),
la sube a Supabase Storage (`app/services/storage.py`, bucket `product-images`) y la analiza
con **Gemini** (`app/services/vision.py`, SDK `google-genai`) para sugerir `name`, `description`
y `tags`. **No crea el producto**: devuelve sugerencias para que el front las edite y guarde con
`POST /erp/products`. `vision` nunca rompe: sin `GEMINI_API_KEY` o ante un fallo devuelve `ai_ok=false`.
Esto usa Gemini a propósito y vive fuera de `app/ai/` (que es el bot Claude/OpenAI).

`search_catalog` ahora incluye `description` y `tags` en su shape lean para que el vendedor
matchee mejor las consultas de los clientes.

### Convenciones importantes

- **`ok` en respuestas de tools**: `storefront.register_sale` devuelve siempre `{"ok": bool, ...}`. Éxito = `ok: True`, error = `ok: False, "error": code, "message": ...`.
- **`bridge.respond` devuelve `str | None`**: `None` = el agente crasheó (se loguea como ERROR), `""` = respondió vacío legítimamente. El webhook no envía nada en ambos casos pero los diferencia en logs.
- **Todo el I/O de Supabase se awaitea**: `await get_supabase().table(...)...execute()`, igual para `.auth.*` y `.storage.*`. Un `async def` NUNCA debe hacer I/O bloqueante — bloquea el event loop y con él todo el server. Si te olvidás un `await`, falla ruidoso (`.data` sobre un coroutine → `AttributeError`), no en silencio.
- **`log_activity` es best-effort**: nunca lanza excepciones — un fallo de audit log no debe romper la operación. Es `async`, hay que awaitearlo.

### Variables de entorno relevantes

| Variable | Efecto |
|----------|--------|
| `LOG_LEVEL=DEBUG` | Activa todos los `logger.debug(...)` del código doppel-api (bridge, webhook, erp) |
| `AI_CORE_URL` | Cualquier valor no vacío activa el bot; vacío lo desactiva sin tocar código |
| `CHAT_DB_URL` | Postgres del checkpointer de LangGraph. Requerido: sin él el agente no arranca |
| `DEEPSEEK_API_KEY` | Requerida por el bot; sin ella no se puede construir ningún chat model |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | Ambas presentes → tracing de Langfuse; si falta una, se desactiva sin romper |
| `GEMINI_API_KEY` | Habilita el análisis de imágenes de producto del front (`/erp/products/analyze-image`). Vacío → devuelve `ai_ok=false` sin llamar a la red |
| `PRODUCT_IMAGES_BUCKET` | Bucket de Supabase Storage para imágenes de producto (default `product-images`) |

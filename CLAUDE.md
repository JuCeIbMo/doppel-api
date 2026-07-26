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
`analyze_product_image` es `async` y usa `client.aio.models.generate_content` (el cliente sync
bloquearía el event loop unos segundos por foto); `optimize_image` es Pillow puro y el endpoint
lo corre con `asyncio.to_thread`.
Esto usa Gemini a propósito y vive fuera de `app/ai/` (que es el bot Claude/OpenAI).

`search_catalog` ahora incluye `description` y `tags` en su shape lean para que el vendedor
matchee mejor las consultas de los clientes. **No incluye `image_url` a propósito**: si el
modelo ve la URL la pega en el texto de la respuesta. La foto se manda con la tool
`send_image`, que resuelve la URL por `product_id` vía `storefront.get_product_image`.

### Capacidades de canal (foto, botones, listas)

El agente no manda mensajes: **encola acciones**. Una tool de canal
(`app/ai_core/tools/channel.py`) agrega una acción al outbox del turno, y el webhook las
entrega en orden cuando el grafo termina.

```
tool (send_image / send_reply_buttons / send_list_message)
  → ctx.outbox.add(SendImageAction(...))        app/ai_core/channel/actions.py
    → run_*_agent_turn devuelve `channel_actions`
      → bridge.respond -> TurnResult(text, actions)
        → whatsapp_delivery.plan_delivery()      ordena y pliega texto+foto
          → WhatsAppSender                        app/services/whatsapp_sender.py
            → meta_api                            payloads de la Cloud API
```

**El outbox viaja por el `context=` run-scoped de LangGraph, no por `configurable`.**
`ToolContextMiddleware` construye un `ToolContext` nuevo por tool call y vive dentro de un
agente que `bridge` cachea entre turnos y entre conversaciones: cualquier buffer colgado del
middleware se filtraría de un cliente a otro. `run_*_agent_turn` crea un `TurnRuntime` por
turno y lo pasa en el `ainvoke`; LangGraph lo propaga a los subgrafos de los especialistas y
nunca lo serializa al checkpoint. **`TurnRuntime` no puede definir `__bool__`/`__len__`**:
`Runtime.merge` hace `other.context or self.context` y un contexto falsy se pierde en
silencio al cruzar al subgrafo. `tests/test_turn_outbox.py` es el canario que lo sostiene.

Las **cortesías** (tildes azules, "escribiendo…", reacción con emoji) son por reglas, sin
LLM ni tokens: `app/ai_core/channel/courtesy.py`. El webhook las dispara **antes** de invocar
al modelo, para que el indicador esté visible mientras el LLM piensa. Son best-effort: un 400
de Meta se loguea y sigue. Los envíos reales sí propagan.

Los **taps** de botón/lista entran como `type: "interactive"`, los parsea `_parse_inbound` y
`bridge` los traduce a `[El cliente tocó la opción "..." (id: ...)]` para el agente. Los ids
que generamos nosotros llevan el prefijo `choice:` (`CHOICE_PREFIX`) para distinguirlos de
los de una plantilla de Meta.

### Convenciones importantes

- **`ok` en respuestas de tools**: `storefront.register_sale` devuelve siempre `{"ok": bool, ...}`. Éxito = `ok: True`, error = `ok: False, "error": code, "message": ...`.
- **`create_order` es idempotente por turno**: la clave sale de `thread_id + turn_id + ítems` (`app/ai_core/tools/sales.py`) y la hace cumplir el RPC `create_sale` (índice único parcial en `sales(tenant_id, idempotency_key)` + advisory lock, `migration_v10_sale_idempotency.sql`). Un reintento del modelo devuelve la misma venta con `duplicate: True`; el `turn_id` es el id del mensaje de WhatsApp, así que se propaga `webhook → bridge.respond → run_*_agent_turn → configurable["turn_id"] → ToolContext`.
- **`bridge.respond` devuelve `TurnResult`** (`app/ai_core/channel/actions.py`), nunca `None`: `ok=False` = el agente crasheó (se loguea como ERROR), `text=""` con `ok=True` = respondió vacío legítimamente. El webhook no envía nada en ambos casos pero los diferencia en logs.
- **Todo el I/O de Supabase se awaitea**: `await get_supabase().table(...)...execute()`, igual para `.auth.*` y `.storage.*`. Un `async def` NUNCA debe hacer I/O bloqueante — bloquea el event loop y con él todo el server. Si te olvidás un `await`, falla ruidoso (`.data` sobre un coroutine → `AttributeError`), no en silencio.
- **La regla anterior vale para todo I/O, no sólo Supabase**, pero `tests/test_async_discipline.py` sólo audita el AST de las llamadas a Supabase. Los SDKs de terceros (Gemini, OpenAI, httpx) hay que revisarlos a mano: usá la variante async del cliente, o `asyncio.to_thread` si no hay.
- **Los adjuntos de WhatsApp se borran al terminar el turno**: `_download_media_files` los baja a `/tmp/doppel-whatsapp-media/{tenant}/` y el `finally` de `_process_bot_response` llama a `_cleanup_media_files`, que los saca del disco por cualquier salida (incluidas las tempranas: bot apagado, cuenta no encontrada, agente caído). Nadie más los recolecta.
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

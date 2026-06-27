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

# Arrancar con Docker Compose (incluye chat-postgres para historial)
docker compose up
```

**No hay conftest.py ni pytest.ini.** Cada archivo de test setea sus propias env vars con `os.environ.setdefault(...)` al inicio, antes del primer import de la app. El orden importa: las vars deben estar antes de `import app.*`.

## Arquitectura

**doppel-api** es una API multi-tenant para negocios con bot de WhatsApp. Cada "tenant" es un negocio con su propio catálogo, ventas, clientes y configuración de bot.

### Dos bases de datos

- **Supabase** (Postgres gestionado): datos del ERP — productos, ventas, clientes, cuentas de WhatsApp, configuración del bot. El cliente es **síncrono** (`supabase-py`). Todos los services llaman `get_supabase()` (singleton en `app/services/supabase_client.py`).
- **Chat Postgres** (container propio, `CHAT_DB_URL`): historial de conversaciones de los agentes IA. Lo escribe `app/ai/history.py` con `psycopg` directo (sin ORM). Si `CHAT_DB_URL` está vacío, el historial corre en memoria de proceso (dev/tests).

### Capa ERP

Toda operación ERP recibe un `ERPContext` (tenant_id + actor). Eso garantiza que ninguna query olvide el scope del tenant.

```
ERPContext(tenant_id, actor)  ←  construido por:
  - get_erp_context()         →  endpoints del dashboard (actor="owner")
  - bot_context()             →  agentes IA (actor="whatsapp_bot" | "admin_bot")
```

Los services nunca lanzan `HTTPException`. Lanzan subclases de `ERPError` (`NotFound`, `InsufficientStock`, `Conflict`, etc.) que el handler global de `main.py` convierte a JSON.

### Capa de IA (Pydantic AI in-process)

El bot vive dentro del proceso doppel-api (no es un microservicio separado). Flujo por mensaje:

```
POST /webhook/whatsapp
  → _process_bot_response() [background task]
    → app/ai/bridge.respond()          ← única puerta pública del subsistema AI
      → client_agent / manager_agent   (app/ai/agents/)
        → agent.run(prompt, deps=..., model=model_string(...),
                    message_history=history.load(session_id))
          → storefront.search_catalog / register_sale  (client)
          → get_dashboard_summary / get_stock           (manager, solo lectura)
        → history.append(session_id, result.new_messages())
```

**`app/services/storefront.py`** es la capa que expone el ERP al agente vendedor. Devuelve shapes "lean" (solo lo que la IA necesita) y evita que el bot toque los ERP services directamente.

**`app/ai/__init__.py`** re-exporta solo `respond` — es la única interfaz pública del módulo AI.

**`app/ai/model.py`** enruta por prefijo de `model_string`: `claude-*` → Anthropic, `gpt-*/o-series` → OpenAI.

**`app/ai/media.py`** convierte adjuntos de imagen a `BinaryContent` para Pydantic AI. **`app/ai/transcription.py`** transcribe audio/voice vía Whisper antes de pasarlo al agente como texto.

**`app/ai/history.py`** carga y persiste el historial alrededor de cada `agent.run(...)` usando `ModelMessagesTypeAdapter` de Pydantic AI y `psycopg` directo contra `CHAT_DB_URL`. Best-effort: un fallo de Postgres se loguea pero no interrumpe la respuesta.

Los agentes se diferencian por modo:
- `client` (`app/ai/agents/client.py`): tools `search_catalog` + `register_sale`; deps `ClientDeps(ctx, system_prompt)`
- `manager` (`app/ai/agents/manager.py`): tools de solo lectura `get_dashboard_summary` + `get_stock`; deps `ManagerDeps(ctx, system_prompt)`

### Herramienta de imagen de producto (Gemini, separada del bot)

`POST /erp/products/analyze-image` es una herramienta del front, **aislada del bot Pydantic AI**:
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
- **Supabase es síncrono en contexto async**: todos los `async def` de los ERP services hacen I/O síncrono. Es una limitación conocida del cliente `supabase-py`.
- **`log_activity` es best-effort**: nunca lanza excepciones — un fallo de audit log no debe romper la operación.

### Variables de entorno relevantes

| Variable | Efecto |
|----------|--------|
| `LOG_LEVEL=DEBUG` | Activa todos los `logger.debug(...)` del código doppel-api (bridge, webhook, erp) |
| `AI_CORE_URL` | Cualquier valor no vacío activa el bot; vacío lo desactiva sin tocar código |
| `CHAT_DB_URL` | Postgres dedicado para historial de conversaciones. Vacío → historial en memoria de proceso (dev/tests) |
| `GEMINI_API_KEY` | Habilita el análisis de imágenes de producto del front (`/erp/products/analyze-image`). Vacío → devuelve `ai_ok=false` sin llamar a la red |
| `PRODUCT_IMAGES_BUCKET` | Bucket de Supabase Storage para imágenes de producto (default `product-images`) |

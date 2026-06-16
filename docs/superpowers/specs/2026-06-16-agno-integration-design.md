# Diseño — Integración de Agno en doppel-api

Fecha: 2026-06-16
Estado: Aprobado (diseño) — pendiente plan de implementación

## Contexto

`doppel-api` es un SaaS multitenant de bots de WhatsApp. Cada tenant (negocio)
conecta su número de WhatsApp Cloud (Meta) y atiende dos audiencias:

- **client**: clientes finales (tools read-only sobre el negocio/catálogo).
- **manager**: teléfonos admin (tools ERP: ventas, stock, reportes).

Hoy el backend tiene un **motor de agente casero** (`app/services/agent_core.py`,
~456 líneas: `AgentRunner`, `ToolRegistry`, `Tool`, `*Schema`, `AnthropicProvider`)
y un servicio `ai-core` separado al que el webhook llama por HTTP
(`ai_core_runtime.respond`, `settings.AI_CORE_URL`). Ese intento no funcionó y es
**prescindible**.

Objetivo: reemplazar el motor casero por **Agno (2.x) como librería in-process**,
conservando toda la lógica de negocio (ERP services, Supabase, webhook, modos).

## Decisiones (tomadas con el usuario)

| Tema | Decisión |
|------|----------|
| Forma de integración | Agno como **librería** dentro de doppel-api (no microservicio) |
| Versión | Agno **2.x** (tools como funciones, API `db=`) |
| BD de Agno | **Postgres separado** (nuevo `AGNO_DB_URL`), distinto del Supabase de negocio |
| Aislamiento | `user_id = user_phone`, `session_id = f"{tenant_id}:{user_phone}"` |
| Modos | **Dos factories separadas**: `get_client_agent`, `get_manager_agent` |
| Multimedia | **Imágenes** (Claude vision) + **audio** (transcripción) |
| Transcripción | **OpenAI Whisper API** (nueva dep `openai` + `OPENAI_API_KEY`) |
| Documentos | Por ahora solo se anotan como `[documento adjunto]`, sin análisis |

## Arquitectura

**Principio organizador: TODO lo de IA vive en un único paquete `app/ai/`,**
visualmente separado del backend de negocio (`app/routers/`, `app/services/`,
`app/models/`). El resto del backend solo conoce `from app.ai import respond`;
nada fuera de `app/ai/` importa Agno.

### Estructura de carpetas

```
app/
├── ai/                          ◄══ TODO LO DE IA (frontera de un solo import)
│   ├── __init__.py              # expone SOLO respond()  → única puerta de entrada
│   ├── bridge.py                # respond(): el puente que llama el webhook
│   ├── factories/
│   │   ├── base.py              # config común (Claude + PostgresDb de Agno)
│   │   ├── client_agent.py      # get_client_agent(...)
│   │   └── manager_agent.py     # get_manager_agent(...)
│   ├── tools/
│   │   ├── client_tools.py      # build_client_tools(...)  → funciones read-only
│   │   └── manager_tools.py     # build_manager_tools(...) → funciones ERP
│   ├── media/
│   │   └── transcription.py     # transcribe_audio() (Whisper) + prep de imágenes
│   ├── prompts.py               # selección system_prompt / manager_prompt
│   └── config.py                # AGNO_DB_URL, OPENAI_API_KEY, modelo por defecto
│
├── routers/        ← negocio (webhook, dashboard, erp, auth...) — SIN tocar
├── services/       ← negocio (erp/, supabase_client, meta_api, phone...) — SIN tocar
└── models/         ← schemas de negocio
```

### Flujo

```
app/routers/webhook.py (_process_bot_response)
   │  cambia 1 llamada: ai_core_runtime.respond(...) -> app.ai.respond(...)
   ▼
app/ai/bridge.py :: respond()        ← entrada única por mensaje
   │   - transcribe audio (Whisper) si hay nota de voz   (app/ai/media/)
   │   - prepara imágenes para Claude (agno Image)
   │   - elige factory según mode
   ▼
app/ai/factories/client_agent.py  /  manager_agent.py
   │   model=Claude, db=PostgresDb(AGNO_DB_URL), tools=[funciones],
   │   add_history_to_context=True, user_id=phone, session_id=tenant:phone
   ▼
app/ai/tools/                        ← tools (cáscara delgada que llama a app/services/erp/)
```

### Reglas de frontera

- **Único import público:** el backend solo usa `from app.ai import respond`.
  `app/ai/__init__.py` es el contrato; lo de adentro se puede reorganizar libre.
- **Dirección de dependencias:** `app/ai/` PUEDE importar de `app/services/`
  (las tools llaman a los ERP services). `app/services/` y `app/routers/` NO
  importan de `app/ai/` salvo el webhook, que solo importa `respond`.
- **Tools = cáscara delgada:** la lógica de negocio se queda en `app/services/erp/`.
  Nunca se reimplementa negocio dentro de `app/ai/`.

### Componentes nuevos (todos bajo `app/ai/`)

- **`app/ai/__init__.py`** — re-exporta `respond` desde `bridge`.
- **`app/ai/bridge.py`** — `respond(...)`: entrada única; orquesta media + factory.
- **`app/ai/factories/base.py`** — helper compartido (construye `PostgresDb`,
  `Claude`, defaults comunes) para no duplicar config entre las dos factories.
- **`app/ai/factories/client_agent.py`** — `get_client_agent(*, tenant_id,
  user_phone, system_prompt, model_id, supabase) -> Agent`.
- **`app/ai/factories/manager_agent.py`** — `get_manager_agent(...)` igual salvo
  `instructions=manager_prompt`, tools ERP, más iteraciones.
- **`app/ai/tools/client_tools.py`** — `build_client_tools(supabase, tenant_id)
  -> list[Callable]` (lookup_business_info, list_available_products).
- **`app/ai/tools/manager_tools.py`** — `build_manager_tools(supabase, tenant_id)
  -> list[Callable]` (get_dashboard_summary, get_stock, get_top_products,
  create_sale, adjust_stock).
- **`app/ai/media/transcription.py`** — `transcribe_audio(path) -> str` (Whisper)
  y helper de preparación de imágenes para Agno.
- **`app/ai/prompts.py`** — selección de system_prompt vs manager_prompt por mode.
- **`app/ai/config.py`** — `AGNO_DB_URL`, `OPENAI_API_KEY`, modelo por defecto.

### Mapa "dónde modifico qué"

| Quiero... | Archivo |
|-----------|---------|
| Agregar una skill/tool | `app/ai/tools/` (escribo función + la añado a la lista) |
| Cambiar personalidad del bot | `app/ai/prompts.py` o `bot_configs` (BD) |
| Cambiar modelo / memoria / historial | `app/ai/factories/base.py` |
| Tocar transcripción audio / imágenes | `app/ai/media/` |
| Tocar negocio (ERP, ventas, stock) | `app/services/erp/` (IA no se toca) |

### Componentes que se ELIMINAN

- `app/services/agent_core.py` (motor casero + `*Schema`)
- `app/services/agent_runtime.py`
- `app/services/ai_bot.py`
- `app/services/ai_core_runtime.py` y el servicio `ai-core` HTTP
- Tools viejas basadas en clases: `app/services/client_tools.py`,
  `app/services/erp/tools.py`, `app/services/manager_tools.py` (solo la parte de
  tools; `normalize_phone` y utilidades que use el webhook se preservan/migran)
- `app/services/tool_runtime.py`, `app/services/nanobot_runtime.py` (revisar uso)
- `Dockerfile.ai-core`, `compose.ai-core.yaml`, `DEPLOY_AI_CORE.md`

> **Dependencias a desenredar antes de borrar (verificado en el código):**
> - `normalize_phone` vive en `manager_tools.py` y lo usan `webhook.py`,
>   `dashboard.py` y `asistpro.py`. Se extrae a `app/services/phone.py` y se
>   actualizan los 3 imports ANTES de borrar `manager_tools.py`.
> - `app/routers/internal.py` expone `/internal/ai/tools` usando
>   `tool_runtime.build_tool_registry` (lo consultaba el ai-core HTTP). Con Agno
>   in-process ese endpoint queda obsoleto → se elimina el endpoint (y se revisa si
>   `internal.py` queda con otras rutas que conservar).
> - `manager_tools.py` también contiene la lógica de confirmación de escrituras
>   (confirmation gate) y helpers; cualquier comportamiento que se quiera conservar
>   (ej: exigir `confirmed=true` en tools de escritura) se reimplementa en las
>   nuevas tools de `manager_tools` (funciones) antes de borrar el archivo viejo.

### Componentes que se CONSERVAN intactos

- `app/routers/webhook.py` (salvo la única línea de la llamada al core)
- `app/services/erp/*` (clients, sales, inventory, products, reports, context, ...)
- `app/services/supabase_client.py`, `meta_api.py`, `security.py`
- Tabla `bot_configs` (system_prompt, manager_prompt, ai_model, admin_phones,
  bot_enabled) y `messages` (log para el dashboard)

## Flujo de datos (por mensaje entrante)

1. Meta → `POST /webhook/whatsapp` → valida firma → guarda inbound en `messages`.
2. `_process_bot_response` lee `bot_configs`, descarga media, elige `mode`.
3. Llama `app.ai.respond(mode, tenant_id, user_phone, content, system_prompt,
   model, media_paths, supabase)`.
4. El puente: transcribe audios (Whisper), arma `images=[Image(filepath=...)]`,
   añade `[documento adjunto]` para otros tipos.
5. Construye el agente con la factory del `mode` y ejecuta
   `await agent.arun(text, images=images)`.
6. Agno persiste historial/memoria en el Postgres de Agno indexado por
   `session_id = tenant:phone`.
7. El puente devuelve el texto final; el webhook lo envía por `meta_api` y guarda
   el outbound en `messages`.

## Tools: patrón de conversión

Las `Tool` classes pasan a funciones con docstring; `supabase` y `tenant_id` se
inyectan vía **closure** en el builder. Agno genera el JSON schema desde la firma.

```python
def build_manager_tools(supabase, tenant_id) -> list:
    ctx = bot_context(tenant_id, actor="admin_bot")

    async def adjust_stock(product_id: str, new_quantity: float, reason: str) -> dict:
        """Ajusta el stock de un producto a la cantidad real contada.
        Args:
            product_id: ID del producto.
            new_quantity: Cantidad real contada (stock objetivo).
            reason: Motivo del ajuste.
        """
        return await InventoryService().adjust(
            ctx, product_id=product_id, new_quantity=new_quantity, note=reason
        )

    # ... get_stock, get_top_products, create_sale, get_dashboard_summary
    return [adjust_stock, get_stock, get_top_products, create_sale, get_dashboard_summary]
```

Cada tool conserva su cuerpo actual (llama al MISMO ERP service). Agregar una skill
nueva en el futuro = escribir una función y añadirla a la lista del builder.

## Manejo de errores

- El puente captura excepciones de Agno y de Whisper y devuelve `""`.
- El webhook ya trata respuesta vacía: no envía mensaje y loguea (comportamiento
  idéntico al actual).
- Errores de tools: se devuelven como `{"error": ...}` (igual que hoy con `ERPError`)
  para que el modelo pueda reaccionar.

## Configuración nueva (settings / .env)

- `AGNO_DB_URL` — connection string del Postgres de Agno.
- `OPENAI_API_KEY` — para Whisper.
- (Se retiran) `AI_CORE_URL` y settings asociados al ai-core HTTP.

## Pruebas

- `tests/test_ai_bridge.py` (nuevo): mock del Agent y de Whisper; verifica
  `session_id == f"{tenant}:{phone}"`, `user_id == phone`, selección de factory por
  mode, manejo de respuesta vacía.
- Adaptar/retirar `tests/test_agent.py` y `tests/test_ai_core_runtime.py`.
- `tests/test_mvp.py` parchea hoy `webhook.ai_core_runtime.respond` en varios tests
  (líneas ~435, 515, 595, 642) → cambiar el target a `app.routers.webhook.respond`
  (el webhook hará `from app.ai import respond`).
- Conservar los tests de `normalize_phone` (mover a `tests/test_phone.py`).
- Test de tools: que cada builder devuelve callables y que cada función llama al ERP
  service correcto (con `bot_context` esperado).

## Migración / despliegue

- Historial arranca **limpio** en el Postgres de Agno; `messages` de Supabase sigue
  siendo el log del dashboard.
- Añadir el servicio Postgres de Agno al compose principal (o apuntar a uno gestionado).
- Quitar artefactos de ai-core del despliegue.

## Fuera de alcance (YAGNI)

- Memoria de usuario avanzada / resúmenes de sesión (se puede activar luego).
- Análisis de documentos (PDF/Excel) por el bot.
- Teams / multi-agente.
- Migrar historial viejo desde `messages` a Agno.
```


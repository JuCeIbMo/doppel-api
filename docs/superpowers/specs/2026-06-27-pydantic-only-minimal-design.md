# Versión Pydantic-only minimalista (sin Agno) — Diseño

Fecha: 2026-06-27
Rama: `spike/pydantic-ai`

## Objetivo

Eliminar Agno por completo del subsistema de IA y dejar una versión **mínima,
simple y funcional** sobre Pydantic AI, pensada para entender y modificar el
flujo de Pydantic sin ruido. No busca paridad de features con Agno: busca el
piso funcional para iterar.

Criterio de éxito: el bot responde por WhatsApp (client y manager) usando Pydantic
AI, con historial persistido en Postgres, y **no queda ninguna referencia a Agno**
en `app/ai/` ni en `requirements.txt`.

## Decisiones (acordadas)

- **Historial**: Postgres **nuevo dedicado** (`chat-postgres`), volumen propio. El
  Postgres viejo de Agno queda huérfano pero intacto (se limpia a mano aparte).
- **Manager agent**: se porta a Pydantic AI pero **mínimo** y **solo lectura**.
- **Client agent**: mantiene sus dos tools núcleo.
- **Sin skills** (los 5 markdown de ventas): el bot usa solo el `system_prompt`
  del tenant. Se re-agregan después si hacen falta.
- **Sin WhatsApp interactivo** (botones/listas): solo texto. El pipeline ya envía
  el texto final.
- **Sin flag** `AI_PYDANTIC_SPIKE`: ya no hay Agno a qué togglear.

## Arquitectura

`app/ai/` se vuelve 100% Pydantic. Se borran `app/ai/factories/` y el `bridge.py`
de Agno. Estructura final:

```
app/ai/
  __init__.py      → expone respond()
  bridge.py        → respond(): elige client/manager, arma media, carga/guarda historial
  model.py         → ruteo claude-*/gpt-* → "provider:model"
  history.py       → historial persistido en Postgres
  media.py         → imágenes (BinaryContent) + transcripción Whisper
  agents/
    client.py      → vendedor: tools search_catalog + register_sale
    manager.py     → admin: tools get_dashboard_summary + get_stock (solo lectura)
```

Las tools leen el `ERPContext` desde `RunContext.deps` (no closures). El
`system_prompt` y la info del negocio se inyectan como instructions dinámicas.

## Componentes

### model.py
Reusa el ruteo del spike: `claude-*` → `anthropic:`, `gpt/o-series` → `openai:`,
default a `AI_DEFAULT_MODEL`. La API key la toma Pydantic AI del entorno.

### agents/client.py
Agent con `deps_type=ClientDeps(ctx, system_prompt)`. Tools:
- `search_catalog(query?)` → `storefront.search_catalog`
- `register_sale(items, customer_phone?, payment_method)` → `storefront.register_sale`

Instructions dinámicas: system_prompt del tenant + info del negocio
(`storefront.business_info`).

### agents/manager.py
Agent con `deps_type=ManagerDeps(ctx, system_prompt)`. Tools **solo lectura**:
- `get_dashboard_summary(period, date_from?, date_to?)` → `ReportsService().dashboard`
- `get_stock(product_name?, low_stock_only?)` → `InventoryService`/`ProductsService`

Las de escritura (crear venta, ajustar stock) quedan fuera de esta versión.

### history.py (Postgres)
Tabla:
```sql
CREATE TABLE IF NOT EXISTS chat_messages (
  session_id  text        NOT NULL,
  seq         bigserial   PRIMARY KEY,
  data        jsonb       NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS chat_messages_session_idx ON chat_messages (session_id, seq);
```
- `session_id = f"{tenant_id}:{user_phone}"`.
- Serialización con `ModelMessagesTypeAdapter` de Pydantic AI (mensajes → JSON).
- `load(session_id, limit)`: trae los últimos N mensajes ordenados por `seq`.
- `append(session_id, new_messages)`: inserta una fila con los mensajes del run.
- Acceso con `psycopg` directo (pool simple). Sin SQLAlchemy.
- Si `CHAT_DB_URL` está vacío, el historial corre **en memoria** (fallback para
  tests y dev sin Postgres).

### bridge.py
`respond(mode, tenant_id, user_phone, content, system_prompt, model, media, ...)`:
1. Transcribe audio (Whisper) y prepara imágenes (`BinaryContent`).
2. Arma el prompt (texto + imágenes).
3. Carga historial de la sesión.
4. Corre el agente correspondiente con `model=model_string(model)`, `deps`,
   `message_history`.
5. Persiste `result.new_messages()`.
6. Devuelve `str` (`None` si crashea, `""` si vacío legítimo — igual contrato que hoy).

## Infra / Deploy

- Nuevo servicio `chat-postgres` en `compose.yaml` y `compose.ai-core.yaml`, con
  volumen propio y `CHAT_DB_URL` apuntando a él.
- Se quita el servicio `agno-postgres` y la env `AGNO_DB_URL`.
- `requirements.txt`: fuera `agno` y `sqlalchemy`; quedan `pydantic-ai-slim`,
  `openai` (Whisper), `psycopg`.
- Settings: fuera `AGNO_DB_URL`, `AI_DEBUG`, `AI_PYDANTIC_SPIKE`; entra `CHAT_DB_URL`.

## Manejo de errores

- `bridge.respond` captura todo y devuelve `None` ante crash (se loguea ERROR),
  manteniendo el contrato actual con el webhook.
- `history` nunca rompe la respuesta: si Postgres falla al cargar/guardar, se
  loguea y se sigue (best-effort, como `log_activity`).

## Testing

- `model_string` routing (claude/gpt/desconocido).
- Client: `TestModel` ejecuta las 2 tools (mock de `storefront`).
- Manager: `TestModel` ejecuta las 2 tools (mock de los ERP services).
- Historial: round-trip de serialización + acumulación por sesión (con store en
  memoria; opcionalmente Postgres si hay `CHAT_DB_URL` de test).

## Fuera de alcance (para después)

- Skills de ventas.
- WhatsApp interactivo (botones/listas/imágenes salientes).
- Tools de escritura del manager (crear venta, ajustar stock).
- Memoria de largo plazo / resúmenes de conversación.

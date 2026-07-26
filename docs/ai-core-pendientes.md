# Pendientes de `app/ai_core`

Hallazgos abiertos de la revisión del port de Agno → LangChain/LangGraph
(commit `a56948b`). Lo que ya se arregló está al final, para no volver a
diagnosticarlo.

Ordenado por riesgo real, no por esfuerzo.

---

## 🟠 `update_config` no actualiza nada

**Dónde:** `app/ai_core/tools/config.py`

El nombre y el parámetro `requested_changes` le dicen al modelo que puede
escribir; el cuerpo sólo lee. El dueño va a pedir un cambio y el admin agent va a
contestar que lo hizo.

**Fix:** renombrar a `get_config` / `suggest_config_changes`.

---

## 🟠 Sin invalidación de caché de agente por cambios de config

**Dónde:** `app/ai_core/bridge.py:_get_or_build_agent` (ya marcado con TODO)

Editar `bot_configs` / `business_info` no llega a un proceso corriendo: el agente
cacheado conserva el nombre del negocio y los `admin_phones` viejos hasta el
próximo deploy.

**Fix:** el proyecto portado trackeaba una "generación" de config para reconstruir
sólo cuando cambiaba. Vale portar eso.

---

## 🟡 El router clasifica una sola vez por conversación

**Dónde:** `app/ai_core/agents/public_agent.py:route_from_start`

`active_agent` vive en el checkpoint, así que el router LLM corre en el **primer
mensaje y nunca más**. Quien saluda con "hola" queda pegado al `greeter` de por
vida salvo que el propio modelo acierte a llamar un handoff.

La salud de todo el swarm depende de que cuatro prompts nunca se olviden de
derivar. Está documentado como intencional, pero es frágil.

**Fix posible:** re-rutear cuando el turno no produjo ni tool calls ni handoff.

---

## 🟡 PII completa en `activity_log`

**Dónde:** `app/ai_core/observability/tracing.py:36`

Se guarda `input_text` y `output_text` íntegros de cada turno de cliente en la
tabla de auditoría, sin truncar ni política de retención. Una fila por mensaje
con el contenido literal de conversaciones de WhatsApp.

**Fix:** truncar o guardar sólo hash/longitud. El detalle fino ya lo tenés en
Langfuse cuando está configurado.

---

## 🟡 `create_order` sin idempotencia

**Dónde:** `app/ai_core/tools/sales.py` (ya documentado en el módulo)

Un reintento del LLM con los mismos ítems **crea una segunda venta**. Requiere
cambio de esquema: columna `idempotency_key` única en `sales`, chequeada antes del
RPC. No se puede tapar con caché en proceso (no sobrevive restart ni sirve con
varios workers).

---

## 🔵 Menores

- **`check_stock` enmascara producto inexistente como stock 0**
  (`app/ai_core/tools/stock.py:27`). El vendedor dirá "no hay stock" ante un
  `product_id` alucinado en vez de detectar el id inválido y volver a buscar.
- **`MAX_TOOL_CALLS_PER_RUN` y `GRAPH_RECURSION_LIMIT` están acoplados a mano.**
  El comentario en `subagents/_base.py:47` razona que `2N+1` con N=5 da 11, que
  entra en 12. Si subís el tope de tool calls sin tocar el otro, el grafo revienta
  con `GraphRecursionError` **antes** de que el cap suave actúe, y el cliente se
  queda sin respuesta. Merece un test que ate los dos números.
- **`AI_CORE_URL` es el interruptor del bot** (`app/routers/webhook.py:128`)
  aunque ya no existe ningún servicio ai-core. Vestigial y confuso.
- **Sin lock por `thread_id`**: dos mensajes seguidos del mismo cliente lanzan dos
  turnos concurrentes sobre el mismo checkpoint.
- **Sin soporte de imágenes** ni de tools interactivas de WhatsApp (botones,
  ubicación). El bridge avisa al cliente que no puede ver la imagen.

---

## Ya arreglado (no re-diagnosticar)

- ✅ **`deepseek-v4-flash` es un id válido.** Descartado por observación: el bot
  responde en producción. Se overridea igual con `LLM_MODEL`,
  `LLM_MODEL_ROUTER`, `LLM_MODEL_PUBLIC`, `LLM_MODEL_ADMIN`.
- ✅ **Una conexión Postgres cruda cacheada de por vida, sin evicción al fallar.**
  Era el peor de la lista: `from_conn_string` abre una `AsyncConnection` sola,
  psycopg no reconecta, `bridge._agents` la cacheaba para siempre y el `except`
  de `respond` no desalojaba nada. Una conexión caída (restart de Postgres, idle
  reaper, corte de red) dejaba ese tenant **mudo hasta reiniciar el proceso**, y
  en silencio: `respond` devuelve `None`, el webhook no manda nada y Meta recibe
  200. Ahora hay un `AsyncConnectionPool` compartido por proceso con
  `check=check_connection`, `setup()` una sola vez, evicción de `_agents` cuando
  un turno falla, tope de `MAX_CACHED_AGENTS`, y `close_pool()` en el lifespan.
  `agents/lifecycle.py` se borró: con un pool compartido, cerrarlo por agente
  sería cerrárselo a todos. Cubierto por `tests/test_checkpointer_pool.py`.

- ✅ **Las tools no ejecutaban.** `contextual_tool` registraba funciones async como
  `func=` en vez de `coroutine=`; LangChain le entregaba al modelo un coroutine sin
  ejecutar, en silencio. Las 8 tools eran no-ops.
- ✅ **El turno bloqueaba el event loop.** `agent.invoke()` síncrono dentro de un
  background task async. Ahora todo el camino es `ainvoke`, con
  `AsyncPostgresSaver` (el `PostgresSaver` sync no implementa `aget_tuple`/`aput`)
  y los hooks `awrap_*` en todos los middlewares (LangChain no hace fallback:
  lanza `NotImplementedError`).
- ✅ **El system prompt se caía** en conversaciones largas: `trim_messages` sin
  `include_system=True`. No era un límite anti-loop — esos son
  `MAX_TOOL_CALLS_PER_RUN`, `MAX_CATALOG_SEARCHES_PER_RUN` y
  `GRAPH_RECURSION_LIMIT`.
- ✅ **Supabase era síncrono dentro de `async def`** en toda la capa ERP. Migrado a
  `AsyncClient`; `tests/test_async_discipline.py` lo hace cumplir sobre el AST.
- ✅ **Cero cobertura de `ai_core`.** Ahora hay tests de tools, middleware y
  disciplina async.

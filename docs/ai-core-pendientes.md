# Pendientes de `app/ai_core`

Hallazgos abiertos de la revisión del port de Agno → LangChain/LangGraph
(commit `a56948b`). Lo que ya se arregló está al final, para no volver a
diagnosticarlo.

Ordenado por riesgo real, no por esfuerzo.

---

## ⛔ El router clasifica una sola vez — DECIDIDO, NO TOCAR

**Dónde:** `app/ai_core/agents/public_agent.py:route_from_start`

`active_agent` vive en el checkpoint, así que el router LLM corre en el primer
mensaje y nunca más. La derivación posterior queda en manos de los handoffs que
llaman los propios especialistas.

**Esto es intencional y está decidido.** Costó trabajo llegar acá. No cambiar
`route_from_start` para que el router corra en cada turno: ya se intentó
(2026-07-26) y se revirtió. Si alguna vez se reabre, tiene que ser una decisión
explícita del dueño del proyecto, no un "arreglo" incidental durante otra tarea.

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

- ✅ **Los prompts describían tools que no existían.** Hallazgo nuevo, encontrado
  al tocar `update_config`. `admin_agent.md` documentaba cinco tools
  (`get_dashboard_summary`, `get_stock`, `get_top_products`, `create_sale`,
  `adjust_stock`) — **ninguna existía**, y su flujo estrella ("registrar una
  venta") era imposible porque el admin no tiene ninguna tool que registre
  ventas. `catalog.md` y `closer.md` nombraban tools en español de una
  iteración anterior (`consultar_stock`, `registrar_pedido`, `enviar_link_pago`,
  `escalar_a_humano`), o sea que también pegaba en clientes reales. Además
  `human_handoff` estaba en `ALL_PUBLIC_TOOLS` y documentada, pero no bindeada a
  ningún agente: la escalación a humano era un camino muerto (ahora va al
  closer). Atado por `tests/test_prompt_tool_sync.py` — los prompts no los cubre
  ningún import ni type check, se desincronizan en silencio.
- ✅ **`update_config` mentía.** Renombrada a `get_config`, sin el parámetro
  `requested_changes` que le sugería al modelo que escribía, y el payload ahora
  dice explícitamente que no se modificó nada.
- ✅ **Caché de agente sin invalidar por config.** `_get_or_build_agent` compara
  un fingerprint del `TenantConfig` completo (no un subconjunto elegido a mano,
  que se queda viejo en silencio al agregar un campo) contra el que se usó para
  construir el agente. `respond` ya recargaba la config en cada mensaje, así que
  no agrega I/O.

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

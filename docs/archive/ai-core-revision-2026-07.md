# Pendientes de `app/ai_core`

Hallazgos abiertos de la revisión del port de Agno → LangChain/LangGraph
(commit `a56948b`). Lo que ya se arregló está al final, para no volver a
diagnosticarlo.

Ordenado por riesgo real, no por esfuerzo.

---

## 🔵 Menores

- **Sin soporte de imágenes** ni de tools interactivas de WhatsApp (botones,
  ubicación). El bridge avisa al cliente que no puede ver la imagen
  (`bridge._image_note`). El audio sí se transcribe, así que el andamiaje de
  media ya está: falta el paso de visión.

---

## Ya arreglado (no re-diagnosticar)

- ✅ **El router clasificaba una sola vez, y los handoffs no tenían red de
  seguridad.** Reabierto por decisión explícita del dueño del proyecto
  (2026-07-28), reemplaza a la nota "⛔ DECIDIDO, NO TOCAR" que vivía arriba de
  este archivo. El diseño viejo era: `active_agent` en el checkpoint,
  `route_from_start` saltando desde `START` directo al especialista, y la
  derivación posterior en manos de tools `handoff_to_*` que los especialistas se
  llamaban entre sí con `Command(goto=..., graph=Command.PARENT)`. El problema
  no era el ahorro de una llamada al clasificador: era que **nada cortaba un
  ping-pong entre dos especialistas**. Los caps de `ToolCallLimitMiddleware`
  acotan el loop *dentro* de un especialista; entre ellos el único freno era
  `GRAPH_RECURSION_LIMIT`, y cuando salta `bridge.respond` devuelve `ok=False`,
  el webhook no manda nada y el cliente queda **en silencio**, con Meta
  recibiendo 200 y sin reintento.

  Ahora el grafo es un solo `START -> classify_intent -> route_dispatch ->
  <especialista> -> END`, con profundidad fija: el ping-pong es estructuralmente
  imposible porque un especialista ya no puede saltar a otro. `handoffs.py` y
  `state.py` se borraron. `active_agent` sigue en el checkpoint pero **no es
  control de flujo**: alimenta el sesgo del router y el `subagent` de
  `trace_turn`.

  **Por qué esta versión no es la que se revirtió el 2026-07-26.** Aquel intento
  hizo correr el router en cada turno *sin memoria del especialista anterior*, y
  eso perdía la continuidad: un aside en medio de un cierre ("¿y en rojo?") se
  reclasificaba como `catalog` y tiraba al cliente fuera del flujo. Acá el nodo
  del router recibe el `active_agent` previo en un `SystemMessage` aparte
  (`router._continuity_prompt`) con la instrucción de mantenerlo salvo señal
  clara de cambio. Es sesgo, no candado: un cambio real de necesidad igual mueve
  el turno.

  Además, como el clasificador ahora corre en **todos** los turnos y no sólo en
  el primero, un proveedor caído podía dejar cualquier mensaje sin respuesta. Por
  eso el retry es explícito dentro del nodo (`ROUTER_MAX_ATTEMPTS`) y, agotado,
  devuelve `intent=None`, que `route_dispatch` lee como "seguí con el
  especialista anterior". Un `RetryPolicy` de grafo no servía: sólo re-corre un
  nodo que lanza, y una excepción que escapa mata el turno entero.

  Costo asumido: el clasificador pasa de 1 llamada por conversación a 1 por
  turno (~500 tokens fijos + hasta 10 mensajes de contexto, y un round-trip
  secuencial antes de que arranque el especialista). Cubierto por
  `tests/test_public_routing.py`. **Regla que reemplaza a la vieja: no
  reintroducir handoffs entre especialistas.** Si el especialista tiene que
  cambiar, lo decide la llamada al router del turno siguiente.
- ✅ **`create_order` sin idempotencia.** Un reintento del modelo con los mismos
  ítems registraba una **segunda venta**: descontaba stock de nuevo, sumaba de
  nuevo a caja y a los rollups del cliente. `migration_v10_sale_idempotency.sql`
  agrega `sales.idempotency_key` con índice único parcial y hace que `create_sale`
  devuelva la venta ya registrada (`idempotent_replay: true`) en vez de crear otra;
  el advisory lock por `(tenant, clave)` serializa dos reintentos simultáneos, así
  que el chequeo y el insert viven en la misma transacción. La clave la deriva
  `tools/sales.py:_idempotency_key` de `thread_id + turn_id + ítems`: el turno es
  la línea entre "el modelo llamó dos veces" (una venta) y "el cliente recompró lo
  mismo más tarde" (venta nueva). El `turn_id` es el id del mensaje entrante de
  WhatsApp, así que una reentrega de Meta cae en la misma clave. Sin `turn_id` no
  se manda clave: perder una recompra real es peor que el duplicado que evita.
- ✅ **`register_sale` devolvía `subtotal: None` por línea.** Encontrado al tocar
  esto: el shape lean leía `sale_items.subtotal`, columna que no existe (es
  `total`), así que con datos reales del RPC `OrderItemResult` recibía `None` y la
  tool reventaba en la validación de pydantic. Sólo pasaba porque los tests
  fakeaban el shape. El shape lean ahora incluye también `product_id`, para no
  aparear los ítems por índice contra lo que pidió el modelo.
- ✅ **PII completa en `activity_log`.** `trace_turn` trunca `input_text` /
  `output_text` a 120 chars y guarda la longitud aparte. El detalle fino va a
  Langfuse.
- ✅ **`check_stock` enmascaraba producto inexistente como stock 0.**
  `StockResult.found` distingue "agotado" de "no existe ese id".
- ✅ **`MAX_TOOL_CALLS_PER_RUN` / `GRAPH_RECURSION_LIMIT` acoplados a mano.**
  Atados por `tests/test_ai_core_invariants.py` (`2N+1 <= limit`).
- ✅ **`AI_CORE_URL` como interruptor del bot.** Ahora es `BOT_ENABLED`, con
  `AI_CORE_URL` / `NANOBOT_RUNTIME_URL` como alias.
- ✅ **Sin lock por `thread_id`.** `bridge._thread_lock` encola los turnos de una
  misma conversación, con refcount para no dejar una entrada por thread para
  siempre.

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

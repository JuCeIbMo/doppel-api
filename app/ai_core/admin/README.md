# Agente administrativo

Este paquete es el punto reservado para desarrollar el agente admin sin mezclarlo con el
router ni con los especialistas públicos.

- `agent.py`: construcción y ejecución de un turno admin.
- `tools.py`: inventario explícito de capacidades habilitadas.
- `prompt.md`: contrato de comportamiento y herramientas visibles para el modelo.

## Corre sobre deepagents, no sobre `create_agent`

A diferencia de los especialistas públicos, este agente se construye con
`create_deep_agent`. Eso le suma dos cosas y hay que saber qué asume cada una.

**Planificación (`write_todos`).** `create_deep_agent` **no** la trae — `TodoListMiddleware`
es de langchain y `agent.py` la pasa a mano. Sirve para que un pedido abierto ("¿por qué
bajaron las ventas?") encadene varias lecturas en un turno sin que esa combinación esté
anticipada como una tool. Por eso el admin tiene `MAX_TOOL_CALLS_PER_RUN_ADMIN` (20) en vez
del límite del público (5).

**Memoria en `/memories/`.** Un filesystem virtual con dos rutas: `/memories/` va al
LangGraph Store (persistente entre conversaciones), todo lo demás al state del grafo. Las
`permissions` de `agent.py` sólo permiten escribir dentro de `/memories/`, porque el
`StateBackend` se serializa entero en cada checkpoint de un thread que no termina nunca.

El agente **lee** su memoria con `read_file`, no se le inyecta al prompt. Existe
`MemoryMiddleware` para inyectarla, pero cachea el contenido en el state del grafo
(`if "memory_contents" in state: return None`) y ese campo se checkpointea: con un
`thread_id` permanente por número de teléfono, la memoria quedaría congelada en la del
primer turno. El costo de leerla es una tool call por turno.

**Aislamiento entre tenants.** Es el `namespace` del `StoreBackend`, no la buena conducta
del modelo. La tupla `(tenant_id, "admin", "memories")` se captura en `build_admin_agent` y
el modelo sólo controla la key de adentro, así que ni un prompt injection ni un `../` pueden
cambiar de tenant. `tests/test_admin_deep_agent.py` prueba las dos fugas.

**El inventario de tools es cerrado.** `ToolGuardrailMiddleware` es fail-closed, así que las
tools del harness van declaradas en `HARNESS_TOOLS` (`config/tenant.py`). `agent.py` acota la
lista del `FilesystemMiddleware` y desactiva el subagente general-purpose vía harness profile.
Si un upgrade de deepagents cambia esos defaults, `test_admin_deep_agent.py` rompe en vez de
ampliar la superficie sola.

Las exclusiones tienen dos razones distintas y conviene no mezclarlas:

| Tool | Por qué no está |
|---|---|
| `execute` | Shell. Igual no se registraría: el backend no es un sandbox. |
| `task` | Subagente genérico con las tools ERP del dueño. |
| `glob`, `grep` | **No es aislamiento** — resuelven el namespace igual que `read`/`write`. Es que hay un solo archivo de memoria: buscar dentro de él con `read_file` alcanza, y cada tool mete su schema en cada llamada al modelo. |
| `delete` | Pérdida de datos, no fuga: el modelo podría borrar toda la memoria acumulada. `edit_file` cubre corregir un hecho viejo. |

`test_every_backend_operation_is_namespace_scoped` prueba que `ls`/`grep`/`glob`/`delete`
están namespaceadas igual que el resto, para que quede claro que su exclusión es una decisión
de costo y superficie, reversible, y no una garantía de seguridad de la que dependa nada.

Las consultas de negocio reutilizan los services ERP existentes. Las escrituras no se
exponen directamente: se proponen como una acción persistente y el dueño debe tocar
Confirmar en WhatsApp. El bridge valida ese tap y sólo ese turno puede ejecutar la
acción; así texto libre, reintentos y conversaciones ajenas no modifican el ERP.

Las tools admin devuelven texto compacto, no JSON — el dueño las lee por WhatsApp, no
un cliente HTTP. Una capacidad nueva de lectura sigue estos 5 pasos:

1. Regla en la capa ERP (`app/services/erp/`), si hace falta una nueva.
2. Shape lean y acotado en `app/services/admin_view.py` (el equivalente admin de
   `storefront.py`): trae `limit + 1` filas, recorta y devuelve el sobrante contado.
3. Un `render_*` con la gramática de `app/ai_core/tools/render.py` (`row`, `section`,
   `doc`, `money`, `qty`, `when`/`day`/`period`, `LABELS`, `ref`) que convierte ese
   shape en el texto final.
4. Una tool fina (2-3 líneas: llamar `admin_view`, pasar el resultado a `render`) +
   sumarla a `ADMIN_TOOLS` + `ALL_ADMIN_TOOLS` (`config/tenant.py`) + `prompt.md`.
5. Entrada en `BUDGET` de `tests/test_admin_tool_payloads.py` — sin eso, la suite
   rompe: es lo que impide que una tool nueva vuelva a devolver un payload gordo.

`search_catalog`, `check_stock` y `get_config` son la excepción: contrato compartido
con el agente público, siguen devolviendo shapes estructurados.

Una capacidad de escritura que necesita recibir una imagen del turno (como el alta de
producto) no pasa por el `configurable` normal: el path local de cada imagen adjunta al
mensaje de WhatsApp viaja en `ToolContext.images` (ver `app/ai_core/tools/context.py`),
poblado por `bridge.respond` → `invocation_config(images=...)` →
`ToolContextMiddleware._inject`. `create_product_from_photo`
(`app/ai_core/tools/catalog.py`) es el único consumidor hoy; ejecuta directo, sin el
contrato propose→Confirmar, porque el alta es reversible (`propose_product_change`
la desactiva) y queda en `activity_log`.

Las escrituras no se exponen directamente: se proponen como una acción persistente y
el dueño debe tocar Confirmar en WhatsApp. El bridge valida ese tap y sólo ese turno
puede ejecutar la acción; así texto libre, reintentos y conversaciones ajenas no
modifican el ERP. `execute_confirmed_action` sigue llamando a los ERP services
directamente (no a `admin_view`, que es sólo la capa de lectura).

No se registra desde `bridge.py`: el bridge sólo resuelve el rol, valida
confirmaciones y llama a este paquete.

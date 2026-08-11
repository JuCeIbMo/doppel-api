# Agente administrativo

Este paquete es el punto reservado para desarrollar el agente admin sin mezclarlo con el
router ni con los especialistas públicos.

- `agent.py`: construcción y ejecución de un turno admin.
- `tools.py`: inventario explícito de capacidades habilitadas.
- `prompt.md`: contrato de comportamiento y herramientas visibles para el modelo.

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

Las escrituras no se exponen directamente: se proponen como una acción persistente y
el dueño debe tocar Confirmar en WhatsApp. El bridge valida ese tap y sólo ese turno
puede ejecutar la acción; así texto libre, reintentos y conversaciones ajenas no
modifican el ERP. `execute_confirmed_action` sigue llamando a los ERP services
directamente (no a `admin_view`, que es sólo la capa de lectura).

No se registra desde `bridge.py`: el bridge sólo resuelve el rol, valida
confirmaciones y llama a este paquete.

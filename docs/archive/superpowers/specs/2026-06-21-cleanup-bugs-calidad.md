# Spec: Cleanup — Bugs y Calidad (Approach C)

## Objetivo

Eliminar bugs silenciosos, consistencia de errores y código redundante sin tocar la
arquitectura ni performance. Cada cambio es quirúrgico y de bajo riesgo.

---

## Cambio 1 — Consistencia del shape de error en `storefront.register_sale`

**Archivo:** `app/services/storefront.py`

**Problema:** La IA recibe dos formas distintas de respuesta:
- Éxito: `{"ok": True, "total": ..., "items": [...]}`
- Error: `{"error": "...", "message": "...", "detail": {}}` — sin clave `"ok"`

Esto obliga a la IA a usar lógica de detección diferente para éxito y error,
lo que puede generar respuestas incorrectas al usuario.

**Fix:** Agregar `"ok": False` a todas las respuestas de error en `register_sale`.
La IA puede siempre chequear `result["ok"]` independientemente del camino de ejecución.

**Impacto:** Solo `storefront.py`. Los tests de `test_storefront.py` que verifiquen
el shape de error deben actualizarse para incluir `"ok": False`.

---

## Cambio 2 — Señal de error en `bridge.respond`

**Archivo:** `app/ai/bridge.py`

**Problema:** `except Exception: logger.exception(...); return ""` hace que el webhook
no pueda distinguir entre:
- Un crash del agente (`""` por error)
- Una respuesta legítimamente vacía del bot (caso raro pero válido)

El webhook actual no puede enviar un mensaje de fallback al usuario cuando el bot falla.

**Fix:**
- Cambiar el tipo de retorno de `str` a `str | None`
- En el bloque `except`, devolver `None` en lugar de `""`
- `""` queda reservado para "bot decidió no responder"
- El webhook existente puede chequear `if reply is None` para enviar fallback

**Impacto:** `app/ai/bridge.py` + el caller en `app/routers/webhook.py` (o donde se use
`respond()`). El test de bridge debe actualizarse para asertir `None` en caso de error.

---

## Cambio 3 — ERPContext duplicado en `client_agent.py`

**Archivo:** `app/ai/factories/client_agent.py` + `app/ai/tools/client_tools.py`

**Problema:** `bot_context(tenant_id, actor="whatsapp_bot")` se construye dos veces
con idénticos parámetros:
1. Dentro de `build_client_tools(tenant_id)` al inicio de la función
2. En `get_client_agent` para pasarlo a `_business_info`

Código duplicado que puede divergir silenciosamente si uno se edita y el otro no.

**Fix:**
- `build_client_tools` cambia su firma de `(tenant_id: str)` a `(ctx: ERPContext)`
- `get_client_agent` crea `ctx` una sola vez y lo pasa a `build_client_tools(ctx)`
- La dependency `_business_info` reutiliza el mismo `ctx`

**Impacto:** `client_agent.py`, `client_tools.py`. Test `test_client_tools.py` debe
actualizar cómo construye el subject bajo test (ahora recibe `ERPContext` directamente).

---

## Cambio 4 — Docstring incorrecto en `client_agent.py`

**Archivo:** `app/ai/factories/client_agent.py`

**Problema:** El módulo dice `"solo tools read-only"` pero `register_sale` es una
operación de escritura que baja stock y registra ingresos.

**Fix:** Actualizar el docstring del módulo a `"atiende clientes finales vía WhatsApp"`.

---

## Fuera de scope (dejar para después)

- I/O síncrono en async (`_stock_map`, `log_activity`): fix sistémico que requiere
  cambiar toda la capa de acceso a Supabase (sync client → async o `to_thread`).
- Agent caching en `bridge.py`: requiere entender el modelo de concurrencia de Agno
  para compartir agentes entre requests de forma segura.
- `ProductsService` y similares como clases sin estado: refactor válido pero no urgente.

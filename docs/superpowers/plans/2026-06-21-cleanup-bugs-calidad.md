# Cleanup Bugs y Calidad — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminar bugs silenciosos, consistencia de errores y código redundante sin tocar la arquitectura.

**Architecture:** Cuatro cambios quirúrgicos e independientes sobre archivos existentes. Cada task tiene su ciclo de test propio y puede commitearse por separado.

**Tech Stack:** Python 3.12, FastAPI, Agno, Supabase-py (sync), pytest + monkeypatch.

## Global Constraints

- No introducir dependencias nuevas
- No cambiar la arquitectura ni agregar abstracciones
- Todos los tests deben pasar: `python3 -m pytest tests/ -q`
- Commits frecuentes, uno por task

---

### Task 1: Error shape consistente en `storefront.register_sale`

**Files:**
- Modify: `app/services/storefront.py` — agregar `"ok": False` a ambas respuestas de error
- Modify: `tests/test_storefront.py` — actualizar los dos tests que verifican errores

**Interfaces:**
- Produce: `register_sale` devuelve siempre un dict con clave `"ok"` (True o False)

- [ ] **Step 1: Actualizar tests de error para incluir `"ok": False`**

En `tests/test_storefront.py`, reemplazar:

```python
def test_register_sale_insufficient_stock_returns_error(monkeypatch):
    async def fake_create_sale(self, ctx, body):
        raise InsufficientStock(product_id="p1", available=0, requested=2)

    monkeypatch.setattr("app.services.storefront.SalesService.create_sale", fake_create_sale)

    result = asyncio.run(storefront.register_sale(
        CTX, items=[{"product_id": "p1", "quantity": 2}]))
    assert result["error"] == "insufficient_stock"
    assert "message" in result and "detail" in result


def test_register_sale_requires_items():
    result = asyncio.run(storefront.register_sale(CTX, items=[]))
    assert result["error"] == "validation_error"
```

Por:

```python
def test_register_sale_insufficient_stock_returns_error(monkeypatch):
    async def fake_create_sale(self, ctx, body):
        raise InsufficientStock(product_id="p1", available=0, requested=2)

    monkeypatch.setattr("app.services.storefront.SalesService.create_sale", fake_create_sale)

    result = asyncio.run(storefront.register_sale(
        CTX, items=[{"product_id": "p1", "quantity": 2}]))
    assert result["ok"] is False
    assert result["error"] == "insufficient_stock"
    assert "message" in result and "detail" in result


def test_register_sale_requires_items():
    result = asyncio.run(storefront.register_sale(CTX, items=[]))
    assert result["ok"] is False
    assert result["error"] == "validation_error"
```

- [ ] **Step 2: Verificar que los tests fallan**

```bash
python3 -m pytest tests/test_storefront.py::test_register_sale_insufficient_stock_returns_error tests/test_storefront.py::test_register_sale_requires_items -v
```

Esperado: FAIL con `KeyError: 'ok'`

- [ ] **Step 3: Agregar `"ok": False` a las respuestas de error en `storefront.py`**

En `app/services/storefront.py`, reemplazar:

```python
    if not items:
        return {"error": "validation_error",
                "message": "Se requiere al menos un ítem", "detail": {}}
```

Por:

```python
    if not items:
        return {"ok": False, "error": "validation_error",
                "message": "Se requiere al menos un ítem", "detail": {}}
```

Y reemplazar:

```python
    except ERPError as exc:
        return {"error": exc.code, "message": exc.message, "detail": exc.detail}
```

Por:

```python
    except ERPError as exc:
        return {"ok": False, "error": exc.code, "message": exc.message, "detail": exc.detail}
```

- [ ] **Step 4: Verificar que los tests pasan**

```bash
python3 -m pytest tests/test_storefront.py -v
```

Esperado: todos PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/storefront.py tests/test_storefront.py
git commit -m "fix(storefront): agregar ok=False a error shapes de register_sale"
```

---

### Task 2: Señal de error en `bridge.respond` (str | None)

**Files:**
- Modify: `app/ai/bridge.py` — cambiar return type a `str | None`, devolver `None` en excepción
- Modify: `app/routers/webhook.py` — manejar `None` antes de llamar `.strip()`
- Modify: `tests/test_ai_bridge.py` — actualizar test de error para asertir `None`

**Interfaces:**
- Produce: `bridge.respond(...)` → `str | None`; `None` = agente crasheó, `""` = respondió vacío

- [ ] **Step 1: Actualizar test de error en `test_ai_bridge.py`**

En `tests/test_ai_bridge.py`, reemplazar:

```python
def test_empty_reply_on_agent_error():
    with patch.object(bridge, "get_client_agent", side_effect=RuntimeError("boom")), \
         patch.object(bridge, "transcribe_audio_media", new=AsyncMock(return_value="")), \
         patch.object(bridge, "prepare_images", return_value=[]):
        out = asyncio.run(bridge.respond(
            mode="client", tenant_id="t1", user_phone="+57300",
            content="hola", system_prompt="p", model="m", supabase=object(), media=None,
        ))
    assert out == ""
```

Por:

```python
def test_none_reply_on_agent_error():
    with patch.object(bridge, "get_client_agent", side_effect=RuntimeError("boom")), \
         patch.object(bridge, "transcribe_audio_media", new=AsyncMock(return_value="")), \
         patch.object(bridge, "prepare_images", return_value=[]):
        out = asyncio.run(bridge.respond(
            mode="client", tenant_id="t1", user_phone="+57300",
            content="hola", system_prompt="p", model="m", supabase=object(), media=None,
        ))
    assert out is None
```

- [ ] **Step 2: Verificar que el test falla**

```bash
python3 -m pytest tests/test_ai_bridge.py::test_none_reply_on_agent_error -v
```

Esperado: FAIL con `AssertionError: assert '' is None`

- [ ] **Step 3: Actualizar `bridge.py`**

En `app/ai/bridge.py`, reemplazar la firma:

```python
async def respond(
    *,
    ...
) -> str:
```

Por:

```python
async def respond(
    *,
    ...
) -> str | None:
```

Y reemplazar el bloque `except`:

```python
    except Exception:
        logger.exception(
            "respuesta IA falló tenant=%s phone=%s mode=%s", tenant_id, user_phone, mode
        )
        return ""
```

Por:

```python
    except Exception:
        logger.exception(
            "respuesta IA falló tenant=%s phone=%s mode=%s", tenant_id, user_phone, mode
        )
        return None
```

- [ ] **Step 4: Verificar que el test de bridge pasa**

```bash
python3 -m pytest tests/test_ai_bridge.py -v
```

Esperado: todos PASS

- [ ] **Step 5: Actualizar `webhook.py` para manejar `None`**

En `app/routers/webhook.py`, en `_process_bot_response`, reemplazar las líneas:

```python
        ai_text = (await ai_respond(
            mode=mode,
            tenant_id=tenant_id,
            user_phone=user_phone,
            content=inbound_text,
            system_prompt=system_prompt,
            model=str(config.get("ai_model") or "claude-sonnet-4-20250514"),
            supabase=supabase,
            wa_access_token=access_token,
            wa_phone_number_id=wa_account["phone_number_id"],
            media=media,
        )).strip()
        if not ai_text:
            logger.warning(
                "Empty agent response tenant=%s phone=%s mode=%s",
                tenant_id, user_phone, mode,
            )
            return
```

Por:

```python
        ai_response = await ai_respond(
            mode=mode,
            tenant_id=tenant_id,
            user_phone=user_phone,
            content=inbound_text,
            system_prompt=system_prompt,
            model=str(config.get("ai_model") or "claude-sonnet-4-20250514"),
            supabase=supabase,
            wa_access_token=access_token,
            wa_phone_number_id=wa_account["phone_number_id"],
            media=media,
        )
        if ai_response is None:
            logger.error(
                "[BOT_CRASH] agente falló internamente tenant=%s phone=%s mode=%s",
                tenant_id, user_phone, mode,
            )
            return
        ai_text = ai_response.strip()
        if not ai_text:
            logger.warning(
                "Empty agent response tenant=%s phone=%s mode=%s",
                tenant_id, user_phone, mode,
            )
            return
```

- [ ] **Step 6: Verificar suite completa**

```bash
python3 -m pytest tests/ -q
```

Esperado: todos PASS

- [ ] **Step 7: Commit**

```bash
git add app/ai/bridge.py app/routers/webhook.py tests/test_ai_bridge.py
git commit -m "fix(bridge): devolver None en crash del agente (era string vacío)"
```

---

### Task 3: Eliminar ERPContext duplicado + fix docstring

**Files:**
- Modify: `app/ai/tools/client_tools.py` — firma `(ctx: ERPContext)` en lugar de `(tenant_id: str)`
- Modify: `app/ai/factories/client_agent.py` — crear ctx una vez, pasarlo a `build_client_tools`, fix docstring
- Modify: `tests/test_client_tools.py` — pasar `ERPContext` en lugar de `"t1"`

**Interfaces:**
- Consumes: `ERPContext` de `app.services.erp.context` y `bot_context` helper
- Produce: `build_client_tools(ctx: ERPContext) -> list[Callable]`

- [ ] **Step 1: Actualizar tests de `test_client_tools.py`**

En `tests/test_client_tools.py`, agregar el import de `bot_context`:

```python
from app.ai.tools.client_tools import build_client_tools
from app.services.erp.context import bot_context

_CTX = bot_context("t1", actor="whatsapp_bot")
```

Y reemplazar cada llamada `build_client_tools("t1")` por `build_client_tools(_CTX)`:

```python
def test_build_client_tools_exposes_two_tools():
    tools = build_client_tools(_CTX)
    assert all(callable(t) for t in tools)
    assert {t.__name__ for t in tools} == {"search_catalog", "register_sale"}


def test_search_catalog_tool_delegates(monkeypatch):
    async def fake_search(ctx, query=None):
        assert ctx.tenant_id == "t1"
        assert ctx.actor == "whatsapp_bot"
        assert query == "coca"
        return [{"id": "p1", "name": "Coca", "price": 1.2, "in_stock": True}]

    monkeypatch.setattr("app.ai.tools.client_tools.storefront.search_catalog", fake_search)
    tools = build_client_tools(_CTX)
    search = next(t for t in tools if t.__name__ == "search_catalog")
    assert asyncio.run(search("coca")) == [
        {"id": "p1", "name": "Coca", "price": 1.2, "in_stock": True}]


def test_register_sale_tool_delegates(monkeypatch):
    async def fake_register(ctx, items, customer_phone=None, payment_method="whatsapp"):
        assert ctx.actor == "whatsapp_bot"
        return {"ok": True, "total": 1.2, "items": []}

    monkeypatch.setattr("app.ai.tools.client_tools.storefront.register_sale", fake_register)
    tools = build_client_tools(_CTX)
    register = next(t for t in tools if t.__name__ == "register_sale")
    assert asyncio.run(register([{"product_id": "p1", "quantity": 1}]))["ok"] is True
```

- [ ] **Step 2: Verificar que los tests de client_tools fallan**

```bash
python3 -m pytest tests/test_client_tools.py -v
```

Esperado: FAIL — `build_client_tools` no acepta `ERPContext` todavía

- [ ] **Step 3: Actualizar `client_tools.py`**

Reemplazar el contenido completo de `app/ai/tools/client_tools.py`:

```python
"""Tools del client agent (vendedor de cara al público). Wrappers finos sobre la
capa storefront: cada tool cierra sobre un ERPContext con actor whatsapp_bot."""

from __future__ import annotations

from typing import Callable

from app.services import storefront
from app.services.erp.context import ERPContext


def build_client_tools(ctx: ERPContext) -> list[Callable]:

    async def search_catalog(query: str | None = None) -> list:
        """Busca productos disponibles del negocio. Sin `query` lista todo el catálogo;
        con `query` filtra por nombre. Devuelve [{id, name, price, in_stock}]. Usá el
        `id` para registrar la venta del producto exacto que mostraste.

        Args:
            query: texto a buscar en el nombre del producto (opcional)
        """
        return await storefront.search_catalog(ctx, query)

    async def register_sale(
        items: list, customer_phone: str | None = None, payment_method: str = "whatsapp"
    ) -> dict:
        """Registra una venta. Baja stock y registra el ingreso de forma atómica.
        Confirmá producto, cantidad y precio con el cliente antes de llamarla.

        Args:
            items: lista de {product_id, quantity}. Usá el product_id (campo `id`) que
                obtuviste de search_catalog; nunca lo inventes ni re-busques por nombre.
            customer_phone: teléfono para asociar la compra a un cliente (opcional)
            payment_method: cash | card | transfer | whatsapp | other
        """
        return await storefront.register_sale(
            ctx, items, customer_phone=customer_phone, payment_method=payment_method)

    return [search_catalog, register_sale]
```

- [ ] **Step 4: Actualizar `client_agent.py`**

Reemplazar el contenido completo de `app/ai/factories/client_agent.py`:

```python
"""Factory del client agent: atiende clientes finales vía WhatsApp."""

from __future__ import annotations

from agno.agent import Agent
from supabase import Client

from app.ai.factories.base import build_db, build_model, build_skills, build_whatsapp_tools, session_id_for
from app.ai.tools.client_tools import build_client_tools
from app.services import storefront
from app.services.erp.context import bot_context


def get_client_agent(
    *,
    tenant_id: str,
    user_phone: str,
    system_prompt: str,
    model_id: str | None,
    supabase: Client,
    wa_access_token: str = "",
    wa_phone_number_id: str = "",
) -> Agent:
    ctx = bot_context(tenant_id, actor="whatsapp_bot")
    tools = build_client_tools(ctx)
    wa_tools = build_whatsapp_tools(
        access_token=wa_access_token,
        phone_number_id=wa_phone_number_id,
        recipient_waid=user_phone,
        enable_send_image=True,
        enable_send_location=True,
        enable_send_reply_buttons=True,
        enable_send_list_message=True,
    )
    if wa_tools:
        tools.append(wa_tools)

    async def _business_info() -> dict:
        return await storefront.business_info(ctx)

    return Agent(
        model=build_model(model_id),
        db=build_db(),
        instructions=system_prompt,
        tools=tools,
        skills=build_skills(
            "catalogo-productos",
            "whatsapp-interactivo",
            "sales-diagnostico",
            "sales-presentacion",
            "sales-objecion",
            "sales-cierre",
        ),
        user_id=user_phone,
        session_id=session_id_for(tenant_id, user_phone),
        add_history_to_context=True,
        num_history_runs=5,
        markdown=False,
        dependencies={"business_info": _business_info},
        add_dependencies_to_context=True,
    )
```

- [ ] **Step 5: Verificar suite completa**

```bash
python3 -m pytest tests/ -q
```

Esperado: todos PASS

- [ ] **Step 6: Commit**

```bash
git add app/ai/tools/client_tools.py app/ai/factories/client_agent.py tests/test_client_tools.py
git commit -m "refactor(ai): ctx único en client_agent, build_client_tools acepta ERPContext"
```

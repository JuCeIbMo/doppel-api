# Storefront Vendedor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reemplazar las queries crudas a Supabase del `client_agent` por una capa de servicios `storefront` con shapes lean para IA, 2 tools (`search_catalog`, `register_sale`) e inyección de `business_info` al prompt vía Agno dependencies.

**Architecture:** Nuevo módulo `app/services/storefront.py` que recibe un `ERPContext(actor="whatsapp_bot")`, centraliza el tenant scoping y reusa los ERP services existentes (`ProductsService`, `SalesService`, `ClientsService`). `client_tools.py` queda como wrappers finos. El factory inyecta `business_info` con `dependencies` + `add_dependencies_to_context=True`.

**Tech Stack:** Python 3, FastAPI, Agno, Supabase (service-role), pytest (python3 global + env vars dummy, sin conftest).

## Global Constraints

- Todos los métodos de storefront reciben `ctx: ERPContext` y scopean por `ctx.tenant_id`. Nunca SQL sin tenant.
- Actor del agente vendedor: `whatsapp_bot` (ya existe en el enum).
- Shapes lean: solo los campos especificados. No filtrar inventario real (`in_stock` booleano).
- Errores de negocio se devuelven como dict `{error, message, detail}` (no se propaga la excepción a la IA).
- Tests: `python3 -m pytest`, sin conftest; mockear services/`get_supabase` con monkeypatch.
- Mensajes de error y campos de cara al usuario en español.

---

### Task 1: Storefront reads (`business_info` + `search_catalog`)

**Files:**
- Create: `app/services/storefront.py`
- Test: `tests/test_storefront.py`

**Interfaces:**
- Consumes: `app.services.erp.context.ERPContext`; `app.services.erp.products.ProductsService.list(ctx, *, category=None, search=None, limit=50, offset=0) -> list[dict]` (cada row trae `id, name, price, available, stock`); `app.services.supabase_client.get_supabase`.
- Produces:
  - `business_info(ctx: ERPContext) -> dict` → `{name, description, hours, address, payment_methods}`
  - `search_catalog(ctx: ERPContext, query: str | None = None) -> list[dict]` → `[{id, name, price, in_stock}]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_storefront.py
import asyncio

import app.services.storefront as storefront
from app.services.erp.context import ERPContext

CTX = ERPContext(tenant_id="t1", actor="whatsapp_bot", actor_label="Bot WhatsApp")


class _BizQuery:
    def __init__(self, rows):
        self._rows = rows
    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def execute(self):
        rows = self._rows
        class R:
            data = rows
        return R()


class _BizSupabase:
    def __init__(self, rows):
        self._rows = rows
    def table(self, _name):
        return _BizQuery(self._rows)


def test_business_info_returns_profile(monkeypatch):
    row = {"name": "Kiosco", "description": "d", "hours": "9-18",
           "address": "calle 1", "payment_methods": "efectivo"}
    monkeypatch.setattr(storefront, "get_supabase", lambda: _BizSupabase([row]))
    assert asyncio.run(storefront.business_info(CTX)) == row


def test_business_info_empty_returns_blanks(monkeypatch):
    monkeypatch.setattr(storefront, "get_supabase", lambda: _BizSupabase([]))
    result = asyncio.run(storefront.business_info(CTX))
    assert result == {"name": "", "description": "", "hours": "",
                      "address": "", "payment_methods": ""}


def test_search_catalog_lean_and_filters_unavailable(monkeypatch):
    async def fake_list(self, ctx, *, category=None, search=None, limit=50, offset=0):
        assert ctx.tenant_id == "t1"
        return [
            {"id": "p1", "name": "Coca 500ml", "price": 1.2, "available": True, "stock": 5},
            {"id": "p2", "name": "Agua", "price": 0.8, "available": True, "stock": 0},
            {"id": "p3", "name": "Oculto", "price": 9.0, "available": False, "stock": 3},
        ]
    monkeypatch.setattr("app.services.storefront.ProductsService.list", fake_list)
    result = asyncio.run(storefront.search_catalog(CTX, query="a"))
    assert result == [
        {"id": "p1", "name": "Coca 500ml", "price": 1.2, "in_stock": True},
        {"id": "p2", "name": "Agua", "price": 0.8, "in_stock": False},
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_storefront.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.storefront'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/services/storefront.py
"""Capa de lectura/venta del agente vendedor de cara al público (WhatsApp).

Recibe siempre un ERPContext con actor="whatsapp_bot", scopea por tenant_id en un
solo lugar y devuelve shapes lean optimizados para IA (sin la info de más del ERP).
Reusa los ERP services existentes para que la lógica viva en un solo sitio.
"""

from __future__ import annotations

from app.services.erp.context import ERPContext
from app.services.erp.products import ProductsService
from app.services.supabase_client import get_supabase

_BIZ_FIELDS = "name, description, hours, address, payment_methods"
_BIZ_BLANK = {"name": "", "description": "", "hours": "", "address": "", "payment_methods": ""}


async def business_info(ctx: ERPContext) -> dict:
    """Perfil del negocio para inyectar al prompt (no es una tool)."""
    result = (
        get_supabase().table("business_info").select(_BIZ_FIELDS)
        .eq("tenant_id", ctx.tenant_id).limit(1).execute()
    )
    return result.data[0] if result.data else dict(_BIZ_BLANK)


async def search_catalog(ctx: ERPContext, query: str | None = None) -> list[dict]:
    """Lista lean de productos disponibles. Incluye `id` como ancla para la venta."""
    rows = await ProductsService().list(ctx, search=query, limit=50)
    return [
        {"id": r["id"], "name": r["name"], "price": r["price"],
         "in_stock": float(r.get("stock", 0)) > 0}
        for r in rows
        if r.get("available")
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_storefront.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add app/services/storefront.py tests/test_storefront.py
git commit -m "feat(storefront): lecturas lean business_info y search_catalog"
```

---

### Task 2: Storefront `register_sale`

**Files:**
- Modify: `app/services/storefront.py`
- Test: `tests/test_storefront.py`

**Interfaces:**
- Consumes: `app.services.erp.sales.SalesService.create_sale(ctx, body: dict) -> dict` (devuelve `{id, total, items:[{product_name, quantity, subtotal}]}`); `app.services.erp.clients.ClientsService.get_by_phone(ctx, phone) -> dict` (lanza `NotFound`); `app.services.erp.exceptions.ERPError, NotFound`.
- Produces: `register_sale(ctx: ERPContext, items: list[dict], customer_phone: str | None = None, payment_method: str = "whatsapp") -> dict` → éxito `{ok: True, total, items:[{name, qty, subtotal}]}`; error `{error, message, detail}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_storefront.py  (append)
from app.services.erp.exceptions import InsufficientStock, NotFound


def test_register_sale_happy_path(monkeypatch):
    captured = {}

    async def fake_get_by_phone(self, ctx, phone):
        return {"id": "c9"}

    async def fake_create_sale(self, ctx, body):
        captured["body"] = body
        return {"id": "s1", "total": 2.4,
                "items": [{"product_name": "Coca 500ml", "quantity": 2, "subtotal": 2.4}]}

    monkeypatch.setattr("app.services.storefront.ClientsService.get_by_phone", fake_get_by_phone)
    monkeypatch.setattr("app.services.storefront.SalesService.create_sale", fake_create_sale)

    result = asyncio.run(storefront.register_sale(
        CTX, items=[{"product_id": "p1", "quantity": 2}], customer_phone="+5491100"))

    assert result == {"ok": True, "total": 2.4,
                      "items": [{"name": "Coca 500ml", "qty": 2, "subtotal": 2.4}]}
    assert captured["body"]["client_id"] == "c9"
    assert captured["body"]["payment_method"] == "whatsapp"
    assert captured["body"]["items"] == [{"product_id": "p1", "quantity": 2}]


def test_register_sale_unknown_client_keeps_none(monkeypatch):
    async def fake_get_by_phone(self, ctx, phone):
        raise NotFound("no existe")

    async def fake_create_sale(self, ctx, body):
        assert body["client_id"] is None
        return {"id": "s1", "total": 1.2, "items": []}

    monkeypatch.setattr("app.services.storefront.ClientsService.get_by_phone", fake_get_by_phone)
    monkeypatch.setattr("app.services.storefront.SalesService.create_sale", fake_create_sale)

    result = asyncio.run(storefront.register_sale(
        CTX, items=[{"product_id": "p1", "quantity": 1}], customer_phone="+5491100"))
    assert result["ok"] is True


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

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_storefront.py -k register_sale -v`
Expected: FAIL with `AttributeError: module 'app.services.storefront' has no attribute 'register_sale'`

- [ ] **Step 3: Write minimal implementation**

Add imports at the top of `app/services/storefront.py` (junto a los existentes):

```python
from app.services.erp.clients import ClientsService
from app.services.erp.exceptions import ERPError, NotFound
from app.services.erp.sales import SalesService
```

Append the function:

```python
async def register_sale(
    ctx: ERPContext,
    items: list[dict],
    customer_phone: str | None = None,
    payment_method: str = "whatsapp",
) -> dict:
    """Registra una venta del vendedor público. `items` = [{product_id, quantity}]
    usando el id que la IA ya obtuvo de search_catalog (no re-resuelve por nombre).
    Delega en SalesService.create_sale (atómico). Devuelve confirmación lean."""
    if not items:
        return {"error": "validation_error",
                "message": "Se requiere al menos un ítem", "detail": {}}

    client_id = None
    if customer_phone:
        try:
            client_id = (await ClientsService().get_by_phone(ctx, customer_phone))["id"]
        except NotFound:
            client_id = None

    body = {
        "client_id": client_id,
        "payment_method": payment_method,
        "cash_account_id": None,
        "discount": 0,
        "notes": None,
        "items": items,
    }
    try:
        sale = await SalesService().create_sale(ctx, body)
    except ERPError as exc:
        return {"error": exc.code, "message": exc.message, "detail": exc.detail}

    return {
        "ok": True,
        "total": sale.get("total"),
        "items": [
            {"name": it.get("product_name"), "qty": it.get("quantity"),
             "subtotal": it.get("subtotal")}
            for it in sale.get("items", [])
        ],
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_storefront.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add app/services/storefront.py tests/test_storefront.py
git commit -m "feat(storefront): register_sale lean delegando en SalesService"
```

---

### Task 3: Reescribir `client_tools.py` a 2 wrappers

**Files:**
- Modify: `app/ai/tools/client_tools.py` (reescritura completa)
- Test: `tests/test_client_tools.py` (reescritura completa)

**Interfaces:**
- Consumes: `app.services.erp.context.bot_context`; `app.services.storefront.search_catalog`, `app.services.storefront.register_sale`.
- Produces: `build_client_tools(tenant_id: str) -> list[Callable]` con tools `search_catalog(query=None)` y `register_sale(items, customer_phone=None, payment_method="whatsapp")`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_client_tools.py  (replace whole file)
import asyncio

from app.ai.tools.client_tools import build_client_tools


def test_build_client_tools_exposes_two_tools():
    tools = build_client_tools("t1")
    assert all(callable(t) for t in tools)
    assert {t.__name__ for t in tools} == {"search_catalog", "register_sale"}


def test_search_catalog_tool_delegates(monkeypatch):
    async def fake_search(ctx, query=None):
        assert ctx.tenant_id == "t1"
        assert ctx.actor == "whatsapp_bot"
        assert query == "coca"
        return [{"id": "p1", "name": "Coca", "price": 1.2, "in_stock": True}]

    monkeypatch.setattr("app.ai.tools.client_tools.storefront.search_catalog", fake_search)
    tools = build_client_tools("t1")
    search = next(t for t in tools if t.__name__ == "search_catalog")
    assert asyncio.run(search("coca")) == [
        {"id": "p1", "name": "Coca", "price": 1.2, "in_stock": True}]


def test_register_sale_tool_delegates(monkeypatch):
    async def fake_register(ctx, items, customer_phone=None, payment_method="whatsapp"):
        assert ctx.actor == "whatsapp_bot"
        return {"ok": True, "total": 1.2, "items": []}

    monkeypatch.setattr("app.ai.tools.client_tools.storefront.register_sale", fake_register)
    tools = build_client_tools("t1")
    register = next(t for t in tools if t.__name__ == "register_sale")
    assert asyncio.run(register([{"product_id": "p1", "quantity": 1}]))["ok"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_client_tools.py -v`
Expected: FAIL (old `build_client_tools(supabase, tenant_id)` signature / old tool names)

- [ ] **Step 3: Write minimal implementation**

```python
# app/ai/tools/client_tools.py  (replace whole file)
"""Tools del client agent (vendedor de cara al público). Wrappers finos sobre la
capa storefront: cada tool cierra sobre un ERPContext con actor whatsapp_bot."""

from __future__ import annotations

from typing import Callable

from app.services import storefront
from app.services.erp.context import bot_context


def build_client_tools(tenant_id: str) -> list[Callable]:
    ctx = bot_context(tenant_id, actor="whatsapp_bot")

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

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_client_tools.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add app/ai/tools/client_tools.py tests/test_client_tools.py
git commit -m "refactor(ai): client_tools como wrappers de storefront (2 tools)"
```

---

### Task 4: Inyectar `business_info` al prompt en el factory

**Files:**
- Modify: `app/ai/factories/client_agent.py`
- Test: `tests/test_client_agent.py`

**Interfaces:**
- Consumes: `build_client_tools(tenant_id)` (Task 3); `app.services.storefront.business_info`; `app.services.erp.context.bot_context`.
- Produces: `get_client_agent(...)` ahora arma el `Agent` con `dependencies={"business_info": <callable>}` y `add_dependencies_to_context=True`; sigue llamando `build_client_tools` con la firma nueva `(tenant_id)`.

- [ ] **Step 1: Write the failing test**

Primero leé `tests/test_client_agent.py` para reusar su forma de mockear (`build_model`/`build_db`/`build_skills`). Agregá este test que verifica el cableado de dependencies:

```python
# tests/test_client_agent.py  (append)
def test_client_agent_injects_business_info_dependency(monkeypatch):
    import app.ai.factories.client_agent as mod

    captured = {}

    class _FakeAgent:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(mod, "Agent", _FakeAgent)
    monkeypatch.setattr(mod, "build_model", lambda *a, **k: object())
    monkeypatch.setattr(mod, "build_db", lambda *a, **k: object())
    monkeypatch.setattr(mod, "build_skills", lambda *a, **k: object())
    monkeypatch.setattr(mod, "build_whatsapp_tools", lambda *a, **k: None)

    mod.get_client_agent(
        tenant_id="t1", user_phone="+549110", system_prompt="hola",
        model_id=None, supabase=object())

    assert captured["add_dependencies_to_context"] is True
    assert "business_info" in captured["dependencies"]
    assert callable(captured["dependencies"]["business_info"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_client_agent.py -k business_info -v`
Expected: FAIL with `KeyError: 'dependencies'`

- [ ] **Step 3: Write minimal implementation**

Editar `app/ai/factories/client_agent.py`:

1. Añadir imports:

```python
from app.services import storefront
from app.services.erp.context import bot_context
```

2. Cambiar la construcción de tools (la firma de `build_client_tools` ya no recibe `supabase`):

```python
    tools = build_client_tools(tenant_id)
```

3. Construir un ctx y el callable de la dependency antes del `return`:

```python
    ctx = bot_context(tenant_id, actor="whatsapp_bot")

    async def _business_info() -> dict:
        return await storefront.business_info(ctx)
```

4. En la llamada `Agent(...)`, agregar los dos parámetros:

```python
        dependencies={"business_info": _business_info},
        add_dependencies_to_context=True,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_client_agent.py -v`
Expected: PASS

- [ ] **Step 5: Run full suite**

Run: `python3 -m pytest tests/test_storefront.py tests/test_client_tools.py tests/test_client_agent.py -v`
Expected: PASS (todo verde)

- [ ] **Step 6: Commit**

```bash
git add app/ai/factories/client_agent.py tests/test_client_agent.py
git commit -m "feat(ai): inyectar business_info al prompt del vendedor via Agno dependencies"
```

---

## Notas de verificación final

- Confirmá que `business_info` resuelve callables async en tu versión de Agno. Si Agno
  solo resuelve callables síncronos en `dependencies`, cambiá `_business_info` a una
  función síncrona que ejecute la corutina (p. ej. con un wrapper), o pre-resolvé el
  dict antes de crear el agente. Verificalo contra `docs.agno.com/dependencies`.
- `supabase` sigue siendo parámetro de `get_client_agent` (lo usa `build_whatsapp_tools`
  vía otros caminos del factory); solo dejó de pasarse a `build_client_tools`.

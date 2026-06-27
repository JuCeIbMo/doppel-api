# Versión Pydantic-only minimalista (sin Agno) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reemplazar Agno por una capa de IA mínima sobre Pydantic AI (client + manager), con historial persistido en un Postgres dedicado, sin dejar rastro de Agno en `app/ai/` ni en `requirements.txt`.

**Architecture:** `app/ai/` se vuelve 100% Pydantic AI. Dos agentes (`client`, `manager`) construidos una vez a nivel de módulo, con `deps` por run (ERPContext + system_prompt) y tools que delegan en `storefront` y en los ERP services. Un `bridge.respond()` único arma media, carga/guarda historial en Postgres (con fallback en memoria) y corre el agente. Se borran `app/ai/factories/`, el bridge de Agno y el paquete `pydantic_spike`.

**Tech Stack:** Pydantic AI (`pydantic-ai-slim[anthropic,openai]`), `psycopg` (historial Postgres directo, sin SQLAlchemy), `openai` (Whisper), FastAPI.

## Global Constraints

- Python 3.10+ (Dockerfile usa `python:3.12-slim`).
- `pydantic-ai-slim[anthropic,openai]>=2.0.0,<3.0.0`; `openai>=1.50.0,<3.0.0`; `psycopg[binary]>=3.1.0`.
- **Prohibido** importar `agno` en cualquier archivo de `app/`.
- Model strings Pydantic AI: `"<provider>:<model>"` (p. ej. `"anthropic:claude-sonnet-4-20250514"`).
- `bridge.respond` devuelve `str | None`: `None` = crash (log ERROR), `""` = vacío legítimo. Mismo contrato que hoy.
- El historial nunca rompe la respuesta: fallo de Postgres se loguea y se sigue (best-effort).
- Tests: cada archivo setea sus env vars con `os.environ.setdefault(...)` antes del primer `import app.*`. No hay conftest. Suite: `python3 -m pytest tests/ -q`.
- Tests corren con `CHAT_DB_URL` vacío → historial en memoria (no requieren Postgres).

---

### Task 1: Config plumbing + model routing

**Files:**
- Modify: `app/config.py` (agregar `CHAT_DB_URL`)
- Modify: `app/ai/config.py` (re-exponer `CHAT_DB_URL`)
- Create: `app/ai/model.py`
- Test: `tests/test_ai_model.py`

**Interfaces:**
- Produces: `app.ai.model.model_string(model_id: str | None) -> str`
- Produces: `app.ai.config.CHAT_DB_URL: str`, `app.ai.config.DEFAULT_MODEL: str`, `app.ai.config.OPENAI_API_KEY: str`

- [ ] **Step 1: Write the failing test**

Create `tests/test_ai_model.py`:

```python
import os

os.environ.setdefault("META_APP_ID", "test-app-id")
os.environ.setdefault("META_APP_SECRET", "test-app-secret")
os.environ.setdefault("META_VERIFY_TOKEN", "test-verify-token")
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "x.eyJyb2xlIjogInNlcnZpY2Vfcm9sZSJ9.y")
os.environ.setdefault("ENCRYPTION_KEY", "oZRrOD525wcQ0CJveupENSX1tDwKfP6e1XrDGn9P1Kw=")

from app.ai.model import model_string


def test_claude_routes_to_anthropic():
    assert model_string("claude-sonnet-4-20250514") == "anthropic:claude-sonnet-4-20250514"


def test_gpt_routes_to_openai():
    assert model_string("gpt-4o") == "openai:gpt-4o"


def test_unknown_falls_back_to_default_anthropic():
    assert model_string("desconocido").startswith("anthropic:")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_ai_model.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.ai.model'`

- [ ] **Step 3: Add `CHAT_DB_URL` to settings**

In `app/config.py`, after the `AI_DEBUG` line, add:

```python
    # Postgres dedicado para el historial de conversaciones del bot (Pydantic AI).
    # Vacío → el historial corre en memoria (dev/tests sin Postgres).
    CHAT_DB_URL: str = ""
```

- [ ] **Step 4: Re-expose it in `app/ai/config.py`**

In `app/ai/config.py`, add after the `DEFAULT_MODEL` line:

```python
CHAT_DB_URL: str = settings.CHAT_DB_URL
```

(Dejar `AGNO_DB_URL`, `DEBUG`, `PYDANTIC_SPIKE` por ahora; se borran en Task 7.)

- [ ] **Step 5: Create `app/ai/model.py`**

```python
"""Ruteo de id de modelo → string de proveedor de Pydantic AI ("provider:model").

La API key la toma Pydantic AI del entorno (ANTHROPIC_API_KEY / OPENAI_API_KEY).
"""

from __future__ import annotations

from app.ai.config import DEFAULT_MODEL

_OPENAI_PREFIXES = ("gpt", "o1", "o3", "o4", "chatgpt")


def _provider_for(model_id: str) -> str | None:
    if model_id.startswith("claude"):
        return "anthropic"
    if model_id.startswith(_OPENAI_PREFIXES):
        return "openai"
    return None


def model_string(model_id: str | None) -> str:
    """Devuelve `"provider:model"`. Un id desconocido cae al DEFAULT_MODEL."""
    mid = (model_id or "").strip()
    provider = _provider_for(mid)
    if provider:
        return f"{provider}:{mid}"
    default = DEFAULT_MODEL.strip()
    provider = _provider_for(default) or "anthropic"
    return f"{provider}:{default}"
```

- [ ] **Step 6: Run test to verify it passes**

Run: `python3 -m pytest tests/test_ai_model.py -v`
Expected: PASS (3 passed)

- [ ] **Step 7: Commit**

```bash
git add app/config.py app/ai/config.py app/ai/model.py tests/test_ai_model.py
git commit -m "feat(ai): config CHAT_DB_URL + model_string routing (Pydantic AI)"
```

---

### Task 2: Historial persistido (Postgres + fallback en memoria)

**Files:**
- Create: `app/ai/history.py`
- Test: `tests/test_ai_history.py`

**Interfaces:**
- Consumes: `app.ai.config.CHAT_DB_URL`
- Produces:
  - `app.ai.history.session_id_for(tenant_id: str, user_phone: str) -> str`
  - `app.ai.history.load(session_id: str) -> list[ModelMessage]`
  - `app.ai.history.append(session_id: str, new_messages: list[ModelMessage]) -> None`

- [ ] **Step 1: Write the failing test**

Create `tests/test_ai_history.py` (no setea `CHAT_DB_URL` → modo memoria):

```python
import os

os.environ.setdefault("META_APP_ID", "test-app-id")
os.environ.setdefault("META_APP_SECRET", "test-app-secret")
os.environ.setdefault("META_VERIFY_TOKEN", "test-verify-token")
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "x.eyJyb2xlIjogInNlcnZpY2Vfcm9sZSJ9.y")
os.environ.setdefault("ENCRYPTION_KEY", "oZRrOD525wcQ0CJveupENSX1tDwKfP6e1XrDGn9P1Kw=")

from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from app.ai import history


def _req(text):
    return ModelRequest(parts=[UserPromptPart(content=text)])


def _resp(text):
    return ModelResponse(parts=[TextPart(content=text)])


def test_session_id_format():
    assert history.session_id_for("t1", "555") == "t1:555"


def test_load_empty_returns_empty_list():
    assert history.load("nope:000") == []


def test_append_then_load_roundtrip():
    sid = "t-roundtrip:1"
    history.append(sid, [_req("hola"), _resp("buenas")])
    loaded = history.load(sid)
    assert len(loaded) == 2
    assert isinstance(loaded[0], ModelRequest)
    assert isinstance(loaded[1], ModelResponse)


def test_append_accumulates_across_calls():
    sid = "t-accum:1"
    history.append(sid, [_req("a"), _resp("b")])
    first = len(history.load(sid))
    history.append(sid, [_req("c"), _resp("d")])
    assert len(history.load(sid)) > first
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_ai_history.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.ai.history'`

- [ ] **Step 3: Create `app/ai/history.py`**

```python
"""Historial de conversación por sesión, persistido en Postgres.

Pydantic AI no maneja persistencia de sesión: la app pasa `message_history` y
guarda `result.new_messages()`. Acá lo resolvemos con un Postgres dedicado
(CHAT_DB_URL) y `psycopg` directo. Si CHAT_DB_URL está vacío, el historial corre
en memoria de proceso (dev/tests).

Best-effort: cualquier fallo de Postgres se loguea y NO rompe la respuesta.
"""

from __future__ import annotations

import logging

import psycopg
from psycopg.types.json import Json
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter

from app.ai.config import CHAT_DB_URL

logger = logging.getLogger("doppel.ai.history")

# Cuántos mensajes mantener en contexto por sesión.
_MAX_MESSAGES = 40

# Fallback en memoria cuando no hay CHAT_DB_URL.
_MEM: dict[str, list[ModelMessage]] = {}

_schema_ready = False

_DDL = """
CREATE TABLE IF NOT EXISTS chat_messages (
    session_id  text        NOT NULL,
    seq         bigserial   PRIMARY KEY,
    data        jsonb       NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS chat_messages_session_idx ON chat_messages (session_id, seq);
"""


def session_id_for(tenant_id: str, user_phone: str) -> str:
    return f"{tenant_id}:{user_phone}"


def _ensure_schema(conn: psycopg.Connection) -> None:
    global _schema_ready
    if _schema_ready:
        return
    conn.execute(_DDL)
    _schema_ready = True


def load(session_id: str) -> list[ModelMessage]:
    if not CHAT_DB_URL:
        return list(_MEM.get(session_id, []))[-_MAX_MESSAGES:]
    try:
        with psycopg.connect(CHAT_DB_URL, autocommit=True) as conn:
            _ensure_schema(conn)
            rows = conn.execute(
                "SELECT data FROM chat_messages WHERE session_id = %s ORDER BY seq",
                (session_id,),
            ).fetchall()
        messages: list[ModelMessage] = []
        for (data,) in rows:
            messages.extend(ModelMessagesTypeAdapter.validate_python(data))
        return messages[-_MAX_MESSAGES:]
    except Exception:
        logger.exception("history load falló session=%s", session_id)
        return []


def append(session_id: str, new_messages: list[ModelMessage]) -> None:
    if not new_messages:
        return
    if not CHAT_DB_URL:
        _MEM.setdefault(session_id, []).extend(new_messages)
        return
    try:
        payload = ModelMessagesTypeAdapter.dump_python(new_messages, mode="json")
        with psycopg.connect(CHAT_DB_URL, autocommit=True) as conn:
            _ensure_schema(conn)
            conn.execute(
                "INSERT INTO chat_messages (session_id, data) VALUES (%s, %s)",
                (session_id, Json(payload)),
            )
    except Exception:
        logger.exception("history append falló session=%s", session_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_ai_history.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add app/ai/history.py tests/test_ai_history.py
git commit -m "feat(ai): historial Postgres con fallback en memoria"
```

---

### Task 3: Client agent (vendedor)

**Files:**
- Create: `app/ai/agents/__init__.py` (vacío)
- Create: `app/ai/agents/client.py`
- Test: `tests/test_ai_client_agent.py`

**Interfaces:**
- Consumes: `app.services.storefront`, `app.services.erp.context.ERPContext`
- Produces:
  - `app.ai.agents.client.ClientDeps(ctx: ERPContext, system_prompt: str)`
  - `app.ai.agents.client.client_agent` (Pydantic AI `Agent` con tools `search_catalog`, `register_sale`)

- [ ] **Step 1: Write the failing test**

Create `tests/test_ai_client_agent.py`:

```python
import os

os.environ.setdefault("META_APP_ID", "test-app-id")
os.environ.setdefault("META_APP_SECRET", "test-app-secret")
os.environ.setdefault("META_VERIFY_TOKEN", "test-verify-token")
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "x.eyJyb2xlIjogInNlcnZpY2Vfcm9sZSJ9.y")
os.environ.setdefault("ENCRYPTION_KEY", "oZRrOD525wcQ0CJveupENSX1tDwKfP6e1XrDGn9P1Kw=")

import asyncio

from pydantic_ai.messages import ToolCallPart
from pydantic_ai.models.test import TestModel

import app.services.storefront as storefront
from app.ai.agents.client import ClientDeps, client_agent
from app.services.erp.context import ERPContext

CTX = ERPContext(tenant_id="t1", actor="whatsapp_bot", actor_label="Bot WhatsApp")


def _tool_names(result):
    return [
        p.tool_name
        for msg in result.all_messages()
        for p in getattr(msg, "parts", [])
        if isinstance(p, ToolCallPart)
    ]


def test_client_runs_both_tools(monkeypatch):
    async def fake_business_info(ctx):
        return {"name": "Demo"}

    async def fake_search(ctx, query=None):
        return [{"id": "p1", "name": "Café", "price": 1000, "in_stock": True,
                 "description": "", "tags": []}]

    async def fake_sale(ctx, items, customer_phone=None, payment_method="whatsapp"):
        return {"ok": True, "sale_id": "s1"}

    monkeypatch.setattr(storefront, "business_info", fake_business_info)
    monkeypatch.setattr(storefront, "search_catalog", fake_search)
    monkeypatch.setattr(storefront, "register_sale", fake_sale)

    deps = ClientDeps(ctx=CTX, system_prompt="Sos un vendedor.")

    async def run():
        result = await client_agent.run("hola", model=TestModel(), deps=deps)
        return _tool_names(result)

    names = asyncio.run(run())
    assert "search_catalog" in names
    assert "register_sale" in names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_ai_client_agent.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.ai.agents'`

- [ ] **Step 3: Create `app/ai/agents/__init__.py`**

```python
```

(Archivo vacío.)

- [ ] **Step 4: Create `app/ai/agents/client.py`**

```python
"""Client agent (vendedor de cara al público) sobre Pydantic AI.

El agente se construye una vez; lo que varía por tenant (ERPContext, system_prompt,
modelo) viaja como deps o como override en `agent.run(...)`. Las tools son wrappers
finos sobre `storefront` que leen el ERPContext desde `RunContext.deps`.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_ai import Agent, RunContext

from app.services import storefront
from app.services.erp.context import ERPContext


@dataclass
class ClientDeps:
    ctx: ERPContext
    system_prompt: str


# Sin modelo fijo: cada run pasa el del tenant (`agent.run(model=...)`).
client_agent = Agent(deps_type=ClientDeps)


@client_agent.instructions
def tenant_system_prompt(ctx: RunContext[ClientDeps]) -> str:
    return ctx.deps.system_prompt


@client_agent.instructions
async def business_info_block(ctx: RunContext[ClientDeps]) -> str:
    info = await storefront.business_info(ctx.deps.ctx)
    return f"Información del negocio:\n{info}"


@client_agent.tool
async def search_catalog(ctx: RunContext[ClientDeps], query: str | None = None) -> list:
    """Busca productos disponibles del negocio. Sin `query` lista todo el catálogo;
    con `query` filtra por nombre. Devuelve [{id, name, price, in_stock, description,
    tags}]. Usá `description` y `tags` para elegir el producto que mejor matchea lo
    que pide el cliente, y el `id` para registrar la venta del producto exacto.

    Args:
        query: texto a buscar en el nombre del producto (opcional)
    """
    return await storefront.search_catalog(ctx.deps.ctx, query)


@client_agent.tool
async def register_sale(
    ctx: RunContext[ClientDeps],
    items: list,
    customer_phone: str | None = None,
    payment_method: str = "whatsapp",
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
        ctx.deps.ctx, items, customer_phone=customer_phone, payment_method=payment_method
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/test_ai_client_agent.py -v`
Expected: PASS (1 passed)

- [ ] **Step 6: Commit**

```bash
git add app/ai/agents/__init__.py app/ai/agents/client.py tests/test_ai_client_agent.py
git commit -m "feat(ai): client agent en Pydantic AI (search_catalog + register_sale)"
```

---

### Task 4: Manager agent (admin, solo lectura)

**Files:**
- Create: `app/ai/agents/manager.py`
- Test: `tests/test_ai_manager_agent.py`

**Interfaces:**
- Consumes: `app.services.erp.reports.ReportsService`, `app.services.erp.inventory.InventoryService`, `app.services.erp.products.ProductsService`, `app.services.erp.context.ERPContext`
- Produces:
  - `app.ai.agents.manager.ManagerDeps(ctx: ERPContext, system_prompt: str)`
  - `app.ai.agents.manager.manager_agent` (tools `get_dashboard_summary`, `get_stock`)

- [ ] **Step 1: Write the failing test**

Create `tests/test_ai_manager_agent.py`:

```python
import os

os.environ.setdefault("META_APP_ID", "test-app-id")
os.environ.setdefault("META_APP_SECRET", "test-app-secret")
os.environ.setdefault("META_VERIFY_TOKEN", "test-verify-token")
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "x.eyJyb2xlIjogInNlcnZpY2Vfcm9sZSJ9.y")
os.environ.setdefault("ENCRYPTION_KEY", "oZRrOD525wcQ0CJveupENSX1tDwKfP6e1XrDGn9P1Kw=")

import asyncio

from pydantic_ai.messages import ToolCallPart
from pydantic_ai.models.test import TestModel

from app.ai.agents import manager as manager_mod
from app.ai.agents.manager import ManagerDeps, manager_agent
from app.services.erp.context import ERPContext

CTX = ERPContext(tenant_id="t1", actor="admin_bot", actor_label="Bot Admin")


def _tool_names(result):
    return [
        p.tool_name
        for msg in result.all_messages()
        for p in getattr(msg, "parts", [])
        if isinstance(p, ToolCallPart)
    ]


def test_manager_runs_read_tools(monkeypatch):
    class FakeReports:
        async def dashboard(self, ctx, date_from, date_to):
            return {"sales_total": 0}

    class FakeProducts:
        async def list(self, ctx, search=None, limit=50):
            return [{"id": "p1", "name": "Café", "unit": "u", "stock": 3,
                     "price": 1000, "category": None}]

    monkeypatch.setattr(manager_mod, "ReportsService", FakeReports)
    monkeypatch.setattr(manager_mod, "ProductsService", FakeProducts)

    deps = ManagerDeps(ctx=CTX, system_prompt="Sos el asistente del dueño.")

    async def run():
        result = await manager_agent.run("estado", model=TestModel(), deps=deps)
        return _tool_names(result)

    names = asyncio.run(run())
    assert "get_dashboard_summary" in names
    assert "get_stock" in names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_ai_manager_agent.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.ai.agents.manager'`

- [ ] **Step 3: Create `app/ai/agents/manager.py`**

```python
"""Manager agent (asistente de admins) sobre Pydantic AI — versión mínima.

Solo tools de LECTURA: resumen del negocio y consulta de stock. Las de escritura
(crear venta, ajustar stock) quedan fuera de esta versión minimalista.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from pydantic_ai import Agent, RunContext

from app.services.erp.context import ERPContext
from app.services.erp.inventory import InventoryService
from app.services.erp.products import ProductsService
from app.services.erp.reports import ReportsService


@dataclass
class ManagerDeps:
    ctx: ERPContext
    system_prompt: str


def _period_dates(period: str, dfrom: str | None, dto: str | None) -> tuple[str, str]:
    today = date.today()
    if period == "today":
        return today.isoformat(), today.isoformat()
    if period == "week":
        return (today - timedelta(days=today.weekday())).isoformat(), today.isoformat()
    if period == "custom" and dfrom and dto:
        return dfrom, dto
    return today.replace(day=1).isoformat(), today.isoformat()


manager_agent = Agent(deps_type=ManagerDeps)


@manager_agent.instructions
def tenant_system_prompt(ctx: RunContext[ManagerDeps]) -> str:
    return ctx.deps.system_prompt


@manager_agent.tool
async def get_dashboard_summary(
    ctx: RunContext[ManagerDeps],
    period: str = "month",
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """Resumen del negocio en un período: ventas totales, número de ventas, margen
    bruto, clientes nuevos, productos con stock bajo y saldo de cajas.

    Args:
        period: today | week | month | custom
        date_from: YYYY-MM-DD, requerido si period=custom
        date_to: YYYY-MM-DD, requerido si period=custom
    """
    f, t = _period_dates(period, date_from, date_to)
    return await ReportsService().dashboard(ctx.deps.ctx, date_from=f, date_to=t)


@manager_agent.tool
async def get_stock(
    ctx: RunContext[ManagerDeps],
    product_name: str | None = None,
    low_stock_only: bool = False,
) -> list:
    """Consulta el stock de uno o todos los productos. Filtra por nombre o stock bajo.

    Args:
        product_name: filtra por nombre (coincidencia parcial)
        low_stock_only: solo productos por debajo de su umbral
    """
    if low_stock_only:
        return await InventoryService().low_stock(ctx.deps.ctx)
    rows = await ProductsService().list(ctx.deps.ctx, search=product_name, limit=50)
    return [
        {"product_id": r["id"], "product_name": r["name"], "category": r.get("category"),
         "unit": r["unit"], "stock": r.get("stock", 0), "price": r["price"]}
        for r in rows
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_ai_manager_agent.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add app/ai/agents/manager.py tests/test_ai_manager_agent.py
git commit -m "feat(ai): manager agent mínimo en Pydantic AI (solo lectura)"
```

---

### Task 5: Media (imágenes Pydantic + fix transcripción)

**Files:**
- Create: `app/ai/media.py`
- Modify: `app/ai/media/transcription.py` (quitar `agno.media.Image` y `prepare_images`)
- Test: `tests/test_ai_media.py`

**Nota:** `app/ai/media/` es un paquete (dir) y queremos crear `app/ai/media.py` (módulo). No pueden coexistir. Por eso esta task **mueve** la transcripción a `app/ai/transcription.py` y crea `app/ai/media.py` nuevo, y borra el dir `app/ai/media/`.

**Interfaces:**
- Produces:
  - `app.ai.media.prepare_images(media: list[dict] | None) -> list[BinaryContent]`
  - `app.ai.transcription.transcribe_audio_media(media: list[dict] | None) -> str` (movido, misma firma)

- [ ] **Step 1: Write the failing test**

Create `tests/test_ai_media.py`:

```python
import os
import tempfile

os.environ.setdefault("META_APP_ID", "test-app-id")
os.environ.setdefault("META_APP_SECRET", "test-app-secret")
os.environ.setdefault("META_VERIFY_TOKEN", "test-verify-token")
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "x.eyJyb2xlIjogInNlcnZpY2Vfcm9sZSJ9.y")
os.environ.setdefault("ENCRYPTION_KEY", "oZRrOD525wcQ0CJveupENSX1tDwKfP6e1XrDGn9P1Kw=")

from pydantic_ai import BinaryContent

from app.ai.media import prepare_images


def test_prepare_images_reads_local_file():
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        f.write(b"\xff\xd8\xff\xe0fake-jpeg")
        path = f.name
    out = prepare_images([{"type": "image", "local_path": path}])
    assert len(out) == 1
    assert isinstance(out[0], BinaryContent)
    assert out[0].media_type == "image/jpeg"


def test_prepare_images_skips_non_images():
    assert prepare_images([{"type": "audio", "local_path": "/x"}]) == []
    assert prepare_images(None) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_ai_media.py -v`
Expected: FAIL (import de `app.ai.media` resuelve hoy al paquete `app/ai/media/`, que no tiene `prepare_images` con esa firma → `ImportError`)

- [ ] **Step 3: Create `app/ai/transcription.py` (movido desde media/transcription.py, sin Agno)**

```python
"""Transcripción de audio (Whisper) de los mensajes de WhatsApp."""

from __future__ import annotations

import logging

from openai import AsyncOpenAI

from app.ai.config import OPENAI_API_KEY

logger = logging.getLogger("doppel.ai.media")

_AUDIO_TYPES = {"audio", "voice"}

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    return _client


async def transcribe_audio(path: str) -> str:
    """Transcribe un archivo de audio a texto con Whisper. Devuelve '' si falla."""
    logger.debug("[WHISPER] transcribiendo path=%s", path)
    try:
        with open(path, "rb") as fh:
            result = await _get_client().audio.transcriptions.create(
                model="whisper-1", file=fh
            )
        text = (result.text or "").strip()
        logger.debug("[WHISPER] ok chars=%d resultado=%r", len(text), text[:80])
        return text
    except Exception:
        logger.exception("transcripción de audio falló path=%s", path)
        return ""


async def transcribe_audio_media(media: list[dict] | None) -> str:
    """Concatena las transcripciones de todas las notas de voz del mensaje."""
    parts: list[str] = []
    for item in media or []:
        if item.get("type") in _AUDIO_TYPES and item.get("local_path"):
            text = await transcribe_audio(item["local_path"])
            if text:
                parts.append(text)
    return "\n".join(parts)
```

- [ ] **Step 4: Delete the old media package**

```bash
git rm app/ai/media/__init__.py app/ai/media/transcription.py
```

- [ ] **Step 5: Create `app/ai/media.py`**

```python
"""Preparación de imágenes entrantes para Pydantic AI (BinaryContent)."""

from __future__ import annotations

import logging
import mimetypes

from pydantic_ai import BinaryContent

logger = logging.getLogger("doppel.ai.media")

_IMAGE_TYPES = {"image"}


def prepare_images(media: list[dict] | None) -> list[BinaryContent]:
    items: list[BinaryContent] = []
    for item in media or []:
        if item.get("type") not in _IMAGE_TYPES:
            continue
        path = item.get("local_path")
        if not path:
            continue
        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except OSError:
            logger.exception("no pude leer imagen path=%s", path)
            continue
        media_type = mimetypes.guess_type(path)[0] or "image/jpeg"
        items.append(BinaryContent(data=data, media_type=media_type))
    return items
```

- [ ] **Step 6: Run test to verify it passes**

Run: `python3 -m pytest tests/test_ai_media.py -v`
Expected: PASS (2 passed)

- [ ] **Step 7: Commit**

```bash
git add app/ai/media.py app/ai/transcription.py tests/test_ai_media.py
git rm app/ai/media/__init__.py app/ai/media/transcription.py
git commit -m "refactor(ai): media.py (BinaryContent) + transcripción sin Agno"
```

---

### Task 6: Bridge único (routing + media + historial) y `__init__`

**Files:**
- Create: `app/ai/bridge.py` (sobrescribe el de Agno)
- Modify: `app/ai/__init__.py`
- Test: `tests/test_ai_bridge.py`

**Interfaces:**
- Consumes: `app.ai.agents.client`, `app.ai.agents.manager`, `app.ai.history`, `app.ai.media`, `app.ai.transcription`, `app.ai.model`, `app.services.erp.context.bot_context`
- Produces: `app.ai.respond(*, mode, tenant_id, user_phone, content, system_prompt, model, wa_access_token="", wa_phone_number_id="", media=None) -> str | None`

- [ ] **Step 1: Write the failing test**

Create `tests/test_ai_bridge.py`:

```python
import os

os.environ.setdefault("META_APP_ID", "test-app-id")
os.environ.setdefault("META_APP_SECRET", "test-app-secret")
os.environ.setdefault("META_VERIFY_TOKEN", "test-verify-token")
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "x.eyJyb2xlIjogInNlcnZpY2Vfcm9sZSJ9.y")
os.environ.setdefault("ENCRYPTION_KEY", "oZRrOD525wcQ0CJveupENSX1tDwKfP6e1XrDGn9P1Kw=")

import asyncio

from pydantic_ai.models.test import TestModel

import app.services.storefront as storefront
from app.ai import respond
from app.ai.agents import client as client_mod


def test_client_respond_returns_text(monkeypatch):
    async def fake_business_info(ctx):
        return {"name": "Demo"}

    async def fake_search(ctx, query=None):
        return []

    async def fake_sale(ctx, items, customer_phone=None, payment_method="whatsapp"):
        return {"ok": True}

    monkeypatch.setattr(storefront, "business_info", fake_business_info)
    monkeypatch.setattr(storefront, "search_catalog", fake_search)
    monkeypatch.setattr(storefront, "register_sale", fake_sale)

    # Forzamos TestModel como modelo del run vía override del agente.
    with client_mod.client_agent.override(model=TestModel(custom_output_text="hola!")):
        out = asyncio.run(respond(
            mode="client", tenant_id="t1", user_phone="555",
            content="buenas", system_prompt="Sos vendedor.", model="claude-sonnet-4-20250514",
        ))
    assert isinstance(out, str)
    assert out == "hola!"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_ai_bridge.py -v`
Expected: FAIL — hoy `app.ai.respond` enruta al bridge de Agno / spike; el assert de salida `"hola!"` o el import fallan.

- [ ] **Step 3: Overwrite `app/ai/bridge.py`**

```python
"""Puente entre el webhook y los agentes Pydantic AI. Entrada única por mensaje."""

from __future__ import annotations

import logging
from typing import Literal

from app.ai import history
from app.ai.agents.client import ClientDeps, client_agent
from app.ai.agents.manager import ManagerDeps, manager_agent
from app.ai.media import prepare_images
from app.ai.model import model_string
from app.ai.transcription import transcribe_audio_media
from app.services.erp.context import bot_context

logger = logging.getLogger("doppel.ai.bridge")

Mode = Literal["manager", "client"]


def _document_note(media: list[dict] | None) -> str:
    docs = [m for m in (media or []) if m.get("type") not in {"image", "audio", "voice"}]
    return "\n[documento adjunto]" if docs else ""


async def respond(
    *,
    mode: Mode,
    tenant_id: str,
    user_phone: str,
    content: str,
    system_prompt: str,
    model: str,
    wa_access_token: str = "",
    wa_phone_number_id: str = "",
    media: list[dict] | None = None,
) -> str | None:
    """Corre el agente correspondiente. None = crash, '' = vacío legítimo."""
    logger.debug(
        "[START] tenant=%s phone=%s mode=%s model=%s texto_chars=%d",
        tenant_id, user_phone, mode, model, len(content or ""),
    )
    try:
        transcript = await transcribe_audio_media(media)
        images = prepare_images(media)

        text_parts = [content] if content else []
        if transcript:
            text_parts.append(f"[Nota de voz]: {transcript}")
        text = ("\n".join(text_parts) + _document_note(media)).strip()

        prompt: list | str = [text, *images] if images else text

        session_id = history.session_id_for(tenant_id, user_phone)
        if mode == "manager":
            agent = manager_agent
            deps = ManagerDeps(ctx=bot_context(tenant_id, actor="admin_bot"),
                               system_prompt=system_prompt)
        else:
            agent = client_agent
            deps = ClientDeps(ctx=bot_context(tenant_id, actor="whatsapp_bot"),
                              system_prompt=system_prompt)

        result = await agent.run(
            prompt, deps=deps, model=model_string(model),
            message_history=history.load(session_id),
        )
        history.append(session_id, result.new_messages())

        reply = (result.output or "").strip()
        logger.debug("[OUTPUT] tenant=%s mode=%s chars=%d", tenant_id, mode, len(reply))
        return reply
    except Exception:
        logger.exception("respuesta IA falló tenant=%s phone=%s mode=%s", tenant_id, user_phone, mode)
        return None
```

- [ ] **Step 4: Overwrite `app/ai/__init__.py`**

```python
"""Subsistema de IA (Pydantic AI). Única puerta de entrada para el backend."""

from app.ai.bridge import respond

__all__ = ["respond"]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/test_ai_bridge.py -v`
Expected: PASS (1 passed)

- [ ] **Step 6: Commit**

```bash
git add app/ai/bridge.py app/ai/__init__.py tests/test_ai_bridge.py
git commit -m "feat(ai): bridge único Pydantic AI (routing client/manager + historial)"
```

---

### Task 7: Eliminar Agno (código, deps, compose, config muerta)

**Files:**
- Delete: `app/ai/factories/` (todo el dir), `app/ai/pydantic_spike/` (todo el dir), `tests/test_pydantic_spike.py`
- Modify: `app/ai/config.py` (quitar `AGNO_DB_URL`, `DEBUG`, `PYDANTIC_SPIKE`)
- Modify: `app/config.py` (quitar `AGNO_DB_URL`, `AI_DEBUG`, `AI_PYDANTIC_SPIKE`)
- Modify: `requirements.txt` (quitar `agno`, `sqlalchemy`)
- Modify: `compose.yaml` y `compose.ai-core.yaml` (cambiar `agno-postgres` → `chat-postgres`, `AGNO_DB_URL` → `CHAT_DB_URL`, quitar `AI_PYDANTIC_SPIKE`)

**Interfaces:**
- Consumes: todo lo de Tasks 1-6.
- Produces: árbol `app/ai/` sin Agno; `grep -rn agno app/` devuelve vacío.

- [ ] **Step 1: Delete Agno + spike code and obsolete test**

```bash
git rm -r app/ai/factories app/ai/pydantic_spike tests/test_pydantic_spike.py
```

- [ ] **Step 2: Clean `app/ai/config.py`**

Reemplazar el contenido completo por:

```python
"""Configuración del subsistema de IA. Re-expone los settings relevantes
para que el resto de app/ai/ no toque app.config directamente."""

from __future__ import annotations

from app.config import settings

OPENAI_API_KEY: str = settings.OPENAI_API_KEY
DEFAULT_MODEL: str = settings.AI_DEFAULT_MODEL
CHAT_DB_URL: str = settings.CHAT_DB_URL
```

- [ ] **Step 3: Clean `app/config.py`**

Quitar las tres líneas de settings de Agno/spike/debug. Borrar:

```python
    # Agno (Postgres separado para historial/memoria de los agentes)
    AGNO_DB_URL: str = ""
```
```python
    # Agno debug: activa logs detallados de mensajes, tools y tokens
    AI_DEBUG: bool = False
    # Spike: enruta el client agent por Pydantic AI en vez de Agno (comparación).
    AI_PYDANTIC_SPIKE: bool = False
```

(Dejar `OPENAI_API_KEY` y `AI_DEFAULT_MODEL`: siguen en uso. `CHAT_DB_URL` ya se agregó en Task 1.)

- [ ] **Step 4: Clean `requirements.txt`**

Reemplazar el bloque de IA por:

```
# AI bot in-process sobre Pydantic AI + Whisper para transcripción de audio.
pydantic-ai-slim[anthropic,openai]>=2.0.0,<3.0.0
openai>=1.50.0,<3.0.0
# Historial de conversaciones en Postgres dedicado (psycopg directo, sin ORM).
psycopg[binary]>=3.1.0
```

(Eliminar las líneas `agno>=2.0.0,<3.0.0` y `sqlalchemy>=2.0.0,<3.0.0`.)

- [ ] **Step 5: Update `compose.yaml`**

En el servicio `doppel-api`, reemplazar el bloque `environment` por:

```yaml
    environment:
      # Postgres dedicado para el historial de conversaciones del bot (Pydantic AI).
      CHAT_DB_URL: postgresql://ai:ai@chat-postgres:5432/chat
      # Flag de "bot activado": cualquier valor no vacío activa el bot.
      AI_CORE_URL: enabled
```

Reemplazar `depends_on` para apuntar a `chat-postgres`:

```yaml
    depends_on:
      chat-postgres:
        condition: service_healthy
```

Reemplazar el servicio `agno-postgres` y su volumen por:

```yaml
  chat-postgres:
    image: postgres:17
    container_name: chat-postgres
    environment:
      POSTGRES_DB: chat
      POSTGRES_USER: ai
      POSTGRES_PASSWORD: ai
    volumes:
      - chat-postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ai -d chat"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

volumes:
  chat-postgres-data:
```

- [ ] **Step 6: Mirror the same changes into `compose.ai-core.yaml`**

Aplicar exactamente los mismos cambios del Step 5 en `compose.ai-core.yaml` (mantener su cabecera de comentario "ALIAS DE COMPATIBILIDAD" intacta).

- [ ] **Step 7: Verify no Agno references remain**

Run: `grep -rn "agno\|Agno\|AGNO\|PYDANTIC_SPIKE\|AI_DEBUG" app/ requirements.txt compose.yaml compose.ai-core.yaml`
Expected: sin resultados (exit code 1).

- [ ] **Step 8: Run the full suite**

Run: `python3 -m pytest tests/ -q`
Expected: todo verde (los tests de Agno/spike fueron eliminados; los nuevos pasan).

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "refactor(ai): eliminar Agno por completo (deps, compose, config)"
```

---

### Task 8: Actualizar CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update the AI architecture section**

Reemplazar las menciones a Agno (sección "Capa de IA (Agno in-process)", "Dos bases de datos", tabla de env vars con `AGNO_DB_URL`/`AI_DEBUG`) por la realidad nueva:
- El bot corre sobre **Pydantic AI** in-process.
- Historial en **Postgres dedicado** vía `CHAT_DB_URL` (no Agno).
- Agentes: `app/ai/agents/client.py` (vendedor) y `app/ai/agents/manager.py` (admin, solo lectura).
- `app/ai/bridge.respond` sigue siendo la única puerta pública; mismo contrato `str | None`.
- Tabla de env vars: quitar `AGNO_DB_URL`, `AI_DEBUG`; agregar `CHAT_DB_URL` (vacío → historial en memoria).

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: CLAUDE.md refleja la capa de IA Pydantic (sin Agno)"
```

---

## Self-Review

**Spec coverage:**
- Estructura `app/ai/` plana sin Agno → Tasks 3-7 ✓
- Postgres nuevo dedicado para historial → Task 2 (código) + Task 7 (compose) ✓
- Manager portado mínimo solo lectura → Task 4 ✓
- Client con 2 tools → Task 3 ✓
- Sin skills, sin WhatsApp interactivo, sin flag → reflejado (no se portan; `respond` ignora `wa_*`) ✓
- Serialización con `ModelMessagesTypeAdapter` → Task 2 ✓
- Quitar `agno` y `sqlalchemy` de requirements → Task 7 ✓
- Settings: fuera `AGNO_DB_URL`/`AI_DEBUG`/`AI_PYDANTIC_SPIKE`, entra `CHAT_DB_URL` → Tasks 1 y 7 ✓
- Error handling best-effort historial + contrato `None`/`""` → Tasks 2 y 6 ✓
- Tests client/manager/model/historial → Tasks 1-6 ✓

**Placeholder scan:** sin TBD/TODO; todo el código está completo.

**Type consistency:** `ClientDeps(ctx, system_prompt)` y `ManagerDeps(ctx, system_prompt)` usados igual en agents y bridge; `model_string`, `prepare_images`, `transcribe_audio_media`, `history.load/append/session_id_for` con firmas consistentes entre tasks.

**Nota de orden:** Tasks 1-6 dejan código Agno (`factories/`, settings viejos) presente pero **sin usar** — la suite queda verde en cada límite de task. Task 7 hace la limpieza atómica. El `compose` con `chat-postgres` recién aplica en Task 7; hasta entonces dev/tests usan historial en memoria (`CHAT_DB_URL` vacío).

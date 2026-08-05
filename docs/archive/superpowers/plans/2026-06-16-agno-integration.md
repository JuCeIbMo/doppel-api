# Integración de Agno en doppel-api — Plan de Implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reemplazar el motor de agente casero y el servicio ai-core HTTP por Agno 2.x como librería in-process, con todo el código de IA aislado en `app/ai/`.

**Architecture:** El webhook llama a una única función `app.ai.respond()`. Ese puente transcribe audio (Whisper), prepara imágenes, elige una de dos factories (client/manager) que construyen un `Agent` de Agno con tools-función que envuelven los ERP services existentes. Historial/memoria en un Postgres separado, aislado por `session_id = tenant:phone`.

**Tech Stack:** Python 3.11+, FastAPI, Agno 2.x, Anthropic Claude, OpenAI Whisper, Supabase (negocio), Postgres (Agno).

---

## Estructura de archivos final

```
app/ai/
├── __init__.py                 # expone respond()
├── config.py                   # ai_settings: AGNO_DB_URL, OPENAI_API_KEY, modelo
├── bridge.py                   # respond()
├── prompts.py                  # select_prompt(config, mode)
├── factories/
│   ├── __init__.py
│   ├── base.py                 # build_db(), DEFAULT_MODEL
│   ├── client_agent.py         # get_client_agent(...)
│   └── manager_agent.py        # get_manager_agent(...)
├── tools/
│   ├── __init__.py
│   ├── client_tools.py         # build_client_tools(...)
│   └── manager_tools.py        # build_manager_tools(...)
└── media/
    ├── __init__.py
    └── transcription.py        # transcribe_audio(), prepare_images()
app/services/phone.py           # normalize_phone (extraído de manager_tools)
```

---

## Task 1: Añadir dependencias (Agno + OpenAI)

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Añadir las dependencias**

En `requirements.txt`, añadir al final:

```
# AI core (Agno como librería in-process + Whisper para transcripción de audio)
agno>=2.0.0,<3.0.0
openai>=1.50.0,<2.0.0
psycopg[binary]>=3.1.0
```

- [ ] **Step 2: Instalar**

Run: `pip install -r requirements.txt`
Expected: instala agno, openai, psycopg sin errores.

- [ ] **Step 3: Verificar import de Agno**

Run: `python -c "from agno.agent import Agent; from agno.models.anthropic import Claude; from agno.db.postgres import PostgresDb; from agno.media import Image; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "build: añadir agno y openai (whisper) como dependencias"
```

---

## Task 2: Extraer `normalize_phone` a `app/services/phone.py`

`normalize_phone` vive hoy en `manager_tools.py` (que vamos a borrar) y lo usan webhook, dashboard y asistpro. Lo movemos primero para desacoplar.

**Files:**
- Create: `app/services/phone.py`
- Create: `tests/test_phone.py`
- Modify: `app/routers/webhook.py:14`, `app/routers/dashboard.py:26`, `app/routers/asistpro.py:11`

- [ ] **Step 1: Ver la implementación actual**

Run: `grep -n "def normalize_phone" -A 20 app/services/manager_tools.py`
Expected: muestra el cuerpo de `normalize_phone`.

- [ ] **Step 2: Crear `app/services/phone.py` copiando ese cuerpo EXACTO**

```python
"""Normalización de números de teléfono (extraído de manager_tools)."""

from __future__ import annotations


def normalize_phone(raw: str | None) -> str:
    # PEGAR AQUÍ el cuerpo EXACTO de normalize_phone visto en el Step 1.
    ...
```

- [ ] **Step 3: Escribir el test (basado en los asserts ya existentes en test_agent.py)**

`tests/test_phone.py`:

```python
from app.services.phone import normalize_phone


def test_normalize_strips_symbols():
    assert normalize_phone("+52 1 234-567 8900") == "5212345678900"


def test_normalize_empty():
    assert normalize_phone("") == ""


def test_normalize_non_numeric():
    assert normalize_phone("abc") == ""
```

- [ ] **Step 4: Run test**

Run: `pytest tests/test_phone.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Actualizar los 3 imports**

En `app/routers/webhook.py`, `app/routers/dashboard.py`, `app/routers/asistpro.py` cambiar:
`from app.services.manager_tools import normalize_phone`
→ `from app.services.phone import normalize_phone`

- [ ] **Step 6: Verificar que nada más importa normalize_phone del módulo viejo (salvo manager_tools internamente)**

Run: `grep -rn "from app.services.manager_tools import" app/ tests/`
Expected: solo `tests/test_agent.py` (lo retiraremos en Task 14) sigue apuntando al viejo.

- [ ] **Step 7: Commit**

```bash
git add app/services/phone.py tests/test_phone.py app/routers/webhook.py app/routers/dashboard.py app/routers/asistpro.py
git commit -m "refactor: extraer normalize_phone a app/services/phone.py"
```

---

## Task 3: Config de IA (`app/ai/config.py`) + settings

**Files:**
- Create: `app/ai/__init__.py` (vacío por ahora)
- Create: `app/ai/config.py`
- Modify: `app/config.py` (añadir AGNO_DB_URL, OPENAI_API_KEY)
- Modify: `.env.example`

- [ ] **Step 1: Añadir settings nuevos en `app/config.py`**

Dentro de la clase `Settings`, junto a las claves de Anthropic, añadir:

```python
    # Agno (Postgres separado para historial/memoria de los agentes)
    AGNO_DB_URL: str = ""
    # OpenAI Whisper para transcribir notas de voz de WhatsApp
    OPENAI_API_KEY: str = ""
    AI_DEFAULT_MODEL: str = "claude-sonnet-4-20250514"
```

- [ ] **Step 2: Documentar en `.env.example`**

Añadir:

```
# Agno: Postgres separado para historial/memoria de los agentes
AGNO_DB_URL=postgresql+psycopg://ai:ai@localhost:5532/ai
# OpenAI (solo Whisper para transcribir audios)
OPENAI_API_KEY=
AI_DEFAULT_MODEL=claude-sonnet-4-20250514
```

- [ ] **Step 3: Crear `app/ai/__init__.py` vacío y `app/ai/config.py`**

`app/ai/config.py`:

```python
"""Configuración del subsistema de IA. Re-expone los settings relevantes
para que el resto de app/ai/ no toque app.config directamente."""

from __future__ import annotations

from app.config import settings

AGNO_DB_URL: str = settings.AGNO_DB_URL
OPENAI_API_KEY: str = settings.OPENAI_API_KEY
DEFAULT_MODEL: str = settings.AI_DEFAULT_MODEL
```

- [ ] **Step 4: Verificar**

Run: `python -c "from app.ai.config import AGNO_DB_URL, DEFAULT_MODEL; print(DEFAULT_MODEL)"`
Expected: `claude-sonnet-4-20250514`

- [ ] **Step 5: Commit**

```bash
git add app/ai/__init__.py app/ai/config.py app/config.py .env.example
git commit -m "feat(ai): config base del subsistema de IA"
```

---

## Task 4: Factory base (`app/ai/factories/base.py`)

**Files:**
- Create: `app/ai/factories/__init__.py` (vacío)
- Create: `app/ai/factories/base.py`
- Create: `tests/test_ai_factory_base.py`

- [ ] **Step 1: Escribir el test**

`tests/test_ai_factory_base.py`:

```python
from app.ai.factories.base import session_id_for


def test_session_id_combines_tenant_and_phone():
    assert session_id_for("tenant123", "+57300") == "tenant123:+57300"
```

- [ ] **Step 2: Run test (debe fallar)**

Run: `pytest tests/test_ai_factory_base.py -v`
Expected: FAIL (`ModuleNotFoundError` / `cannot import name`).

- [ ] **Step 3: Implementar `app/ai/factories/base.py`**

```python
"""Piezas compartidas por las factories de agentes."""

from __future__ import annotations

from agno.db.postgres import PostgresDb
from agno.models.anthropic import Claude

from app.ai.config import AGNO_DB_URL, DEFAULT_MODEL


def session_id_for(tenant_id: str, user_phone: str) -> str:
    """Aísla cada conversación por negocio + contacto."""
    return f"{tenant_id}:{user_phone}"


def build_db() -> PostgresDb:
    return PostgresDb(db_url=AGNO_DB_URL)


def build_model(model_id: str | None) -> Claude:
    return Claude(id=model_id or DEFAULT_MODEL)
```

- [ ] **Step 4: Run test**

Run: `pytest tests/test_ai_factory_base.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/ai/factories/__init__.py app/ai/factories/base.py tests/test_ai_factory_base.py
git commit -m "feat(ai): factory base (db, modelo, session_id)"
```

---

## Task 5: Client tools (`app/ai/tools/client_tools.py`)

Convierte `LookupBusinessInfoTool` y `ListAvailableProductsTool` a funciones con closure.

**Files:**
- Create: `app/ai/tools/__init__.py` (vacío)
- Create: `app/ai/tools/client_tools.py`
- Create: `tests/test_client_tools.py`

- [ ] **Step 1: Escribir el test (con supabase fake)**

`tests/test_client_tools.py`:

```python
import asyncio

from app.ai.tools.client_tools import build_client_tools


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows
    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def order(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def execute(self):
        class R: data = self._rows
        return R()


class _FakeSupabase:
    def __init__(self, rows):
        self._rows = rows
    def table(self, _name):
        return _FakeQuery(self._rows)


def test_build_client_tools_returns_callables():
    tools = build_client_tools(_FakeSupabase([]), "t1")
    assert all(callable(t) for t in tools)
    assert {t.__name__ for t in tools} == {"lookup_business_info", "list_available_products"}


def test_list_available_products_returns_rows():
    rows = [{"name": "Pizza", "price": 10, "available": True}]
    tools = build_client_tools(_FakeSupabase(rows), "t1")
    list_products = next(t for t in tools if t.__name__ == "list_available_products")
    assert asyncio.run(list_products()) == rows
```

- [ ] **Step 2: Run test (debe fallar)**

Run: `pytest tests/test_client_tools.py -v`
Expected: FAIL (módulo no existe).

- [ ] **Step 3: Implementar `app/ai/tools/client_tools.py`**

```python
"""Tools read-only del client agent. Cada función cierra sobre supabase + tenant_id.
Agno genera el JSON schema desde la firma y el docstring."""

from __future__ import annotations

from typing import Callable

from supabase import Client


def build_client_tools(supabase: Client, tenant_id: str) -> list[Callable]:
    async def lookup_business_info() -> dict:
        """Consulta el perfil del negocio (nombre, descripción, horarios, dirección,
        métodos de pago). Úsalo para responder preguntas del cliente sobre el negocio."""
        result = (
            supabase.table("business_info")
            .select("name, description, hours, address, payment_methods")
            .eq("tenant_id", tenant_id)
            .limit(1)
            .execute()
        )
        if result.data:
            return result.data[0]
        return {"name": "", "description": "", "hours": "", "address": "", "payment_methods": ""}

    async def list_available_products() -> list:
        """Lista los productos disponibles para clientes (nombre, descripción, precio),
        ordenados alfabéticamente. Los no disponibles quedan ocultos."""
        result = (
            supabase.table("products")
            .select("name, description, price, available")
            .eq("tenant_id", tenant_id)
            .eq("available", True)
            .order("name", desc=False)
            .execute()
        )
        return result.data or []

    return [lookup_business_info, list_available_products]
```

- [ ] **Step 4: Run test**

Run: `pytest tests/test_client_tools.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add app/ai/tools/__init__.py app/ai/tools/client_tools.py tests/test_client_tools.py
git commit -m "feat(ai): client tools como funciones"
```

---

## Task 6: Client agent factory (`app/ai/factories/client_agent.py`)

**Files:**
- Create: `app/ai/factories/client_agent.py`
- Create: `tests/test_client_agent.py`

- [ ] **Step 1: Escribir el test (verifica identidad y tipo)**

`tests/test_client_agent.py`:

```python
from agno.agent import Agent

from app.ai.factories.client_agent import get_client_agent


class _FakeSupabase:
    def table(self, _n): raise AssertionError("no se debe llamar al construir")


def test_get_client_agent_sets_identity():
    agent = get_client_agent(
        tenant_id="t1", user_phone="+57300", system_prompt="Eres un bot",
        model_id="claude-sonnet-4-20250514", supabase=_FakeSupabase(),
    )
    assert isinstance(agent, Agent)
    assert agent.user_id == "+57300"
    assert agent.session_id == "t1:+57300"
```

- [ ] **Step 2: Run test (debe fallar)**

Run: `pytest tests/test_client_agent.py -v`
Expected: FAIL (módulo no existe).

- [ ] **Step 3: Implementar `app/ai/factories/client_agent.py`**

```python
"""Factory del client agent: atiende clientes finales, solo tools read-only."""

from __future__ import annotations

from agno.agent import Agent
from supabase import Client

from app.ai.factories.base import build_db, build_model, session_id_for
from app.ai.tools.client_tools import build_client_tools


def get_client_agent(
    *,
    tenant_id: str,
    user_phone: str,
    system_prompt: str,
    model_id: str | None,
    supabase: Client,
) -> Agent:
    return Agent(
        model=build_model(model_id),
        db=build_db(),
        instructions=system_prompt,
        tools=build_client_tools(supabase, tenant_id),
        user_id=user_phone,
        session_id=session_id_for(tenant_id, user_phone),
        add_history_to_context=True,
        num_history_runs=5,
        markdown=False,
    )
```

- [ ] **Step 4: Run test**

Run: `pytest tests/test_client_agent.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/ai/factories/client_agent.py tests/test_client_agent.py
git commit -m "feat(ai): client agent factory"
```

---

## Task 7: Manager tools (`app/ai/tools/manager_tools.py`)

Convierte las 5 ERP tools a funciones. Cada una construye un `ERPContext` con `bot_context` y llama al MISMO ERP service.

**Files:**
- Create: `app/ai/tools/manager_tools.py`
- Create: `tests/test_manager_tools.py`

- [ ] **Step 1: Escribir el test**

`tests/test_manager_tools.py`:

```python
from app.ai.tools.manager_tools import build_manager_tools


class _FakeSupabase:
    def table(self, _n): raise AssertionError("las tools llaman a ERP services, no supabase directo")


def test_build_manager_tools_names():
    tools = build_manager_tools(_FakeSupabase(), "t1")
    assert {t.__name__ for t in tools} == {
        "get_dashboard_summary", "get_stock", "get_top_products",
        "create_sale", "adjust_stock",
    }
    assert all(callable(t) for t in tools)
```

- [ ] **Step 2: Run test (debe fallar)**

Run: `pytest tests/test_manager_tools.py -v`
Expected: FAIL.

- [ ] **Step 3: Implementar `app/ai/tools/manager_tools.py`**

```python
"""Tools del manager/admin agent. Cada función cierra sobre tenant_id y delega en
los ERP services existentes (misma lógica que el dashboard, distinto actor)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Callable

from supabase import Client

from app.services.erp.clients import ClientsService
from app.services.erp.context import bot_context
from app.services.erp.exceptions import ERPError, NotFound
from app.services.erp.inventory import InventoryService
from app.services.erp.products import ProductsService
from app.services.erp.reports import ReportsService
from app.services.erp.sales import SalesService


def _period_dates(period: str, dfrom: str | None, dto: str | None) -> tuple[str, str]:
    today = date.today()
    if period == "today":
        return today.isoformat(), today.isoformat()
    if period == "week":
        return (today - timedelta(days=today.weekday())).isoformat(), today.isoformat()
    if period == "custom" and dfrom and dto:
        return dfrom, dto
    return today.replace(day=1).isoformat(), today.isoformat()


def build_manager_tools(supabase: Client, tenant_id: str) -> list[Callable]:
    ctx = bot_context(tenant_id, actor="admin_bot")

    async def get_dashboard_summary(
        period: str = "month", date_from: str | None = None, date_to: str | None = None
    ) -> dict:
        """Resumen del negocio en un período: ventas totales, número de ventas, margen
        bruto, clientes nuevos, productos con stock bajo y saldo de cajas.

        Args:
            period: today | week | month | custom
            date_from: YYYY-MM-DD, requerido si period=custom
            date_to: YYYY-MM-DD, requerido si period=custom
        """
        f, t = _period_dates(period, date_from, date_to)
        return await ReportsService().dashboard(ctx, date_from=f, date_to=t)

    async def get_stock(product_name: str | None = None, low_stock_only: bool = False) -> list:
        """Consulta el stock de uno o todos los productos. Filtra por nombre o stock bajo.

        Args:
            product_name: filtra por nombre (coincidencia parcial)
            low_stock_only: solo productos por debajo de su umbral
        """
        if low_stock_only:
            return await InventoryService().low_stock(ctx)
        rows = await ProductsService().list(ctx, search=product_name, limit=50)
        return [
            {"product_id": r["id"], "product_name": r["name"], "category": r.get("category"),
             "unit": r["unit"], "stock": r.get("stock", 0), "price": r["price"]}
            for r in rows
        ]

    async def get_top_products(period: str = "month", limit: int = 5) -> list:
        """Productos más vendidos del período, por unidades e ingresos.

        Args:
            period: today | week | month
            limit: cuántos productos (1-50)
        """
        f, t = _period_dates(period, None, None)
        return await ReportsService().top_products(ctx, date_from=f, date_to=t, limit=limit)

    async def create_sale(
        items: list[dict], payment_method: str = "cash", client_phone: str | None = None
    ) -> dict:
        """Registra una venta. Baja stock y registra el ingreso de forma atómica.

        Args:
            items: lista de {product_id, quantity, unit_price?}. Si unit_price se
                omite, usa el precio del catálogo.
            payment_method: cash | card | transfer | whatsapp | other
            client_phone: teléfono para asociar la compra a un cliente
        """
        if not items:
            return {"error": "Se requiere al menos un ítem"}
        client_id = None
        if client_phone:
            try:
                client_id = (await ClientsService().get_by_phone(ctx, client_phone))["id"]
            except NotFound:
                client_id = None
        body = {
            "client_id": client_id, "payment_method": payment_method,
            "cash_account_id": None, "discount": 0, "notes": None, "items": items,
        }
        try:
            return await SalesService().create_sale(ctx, body)
        except ERPError as exc:
            return {"error": exc.code, "message": exc.message, "detail": exc.detail}

    async def adjust_stock(product_id: str, new_quantity: float, reason: str) -> dict:
        """Ajusta el stock de un producto a la cantidad real contada (conteo físico).

        Args:
            product_id: ID del producto
            new_quantity: cantidad real contada (stock objetivo)
            reason: motivo del ajuste
        """
        try:
            return await InventoryService().adjust(
                ctx, product_id=product_id, variant_id=None,
                new_quantity=new_quantity, delta=None, note=reason,
            )
        except ERPError as exc:
            return {"error": exc.code, "message": exc.message, "detail": exc.detail}

    return [get_dashboard_summary, get_stock, get_top_products, create_sale, adjust_stock]
```

- [ ] **Step 4: Run test**

Run: `pytest tests/test_manager_tools.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/ai/tools/manager_tools.py tests/test_manager_tools.py
git commit -m "feat(ai): manager (ERP) tools como funciones"
```

---

## Task 8: Manager agent factory (`app/ai/factories/manager_agent.py`)

**Files:**
- Create: `app/ai/factories/manager_agent.py`
- Create: `tests/test_manager_agent.py`

- [ ] **Step 1: Escribir el test**

`tests/test_manager_agent.py`:

```python
from agno.agent import Agent

from app.ai.factories.manager_agent import get_manager_agent


class _FakeSupabase:
    def table(self, _n): raise AssertionError("no se debe llamar al construir")


def test_get_manager_agent_sets_identity():
    agent = get_manager_agent(
        tenant_id="t1", user_phone="+57999", system_prompt="Eres el admin bot",
        model_id="claude-sonnet-4-20250514", supabase=_FakeSupabase(),
    )
    assert isinstance(agent, Agent)
    assert agent.user_id == "+57999"
    assert agent.session_id == "t1:+57999"
```

- [ ] **Step 2: Run test (debe fallar)**

Run: `pytest tests/test_manager_agent.py -v`
Expected: FAIL.

- [ ] **Step 3: Implementar `app/ai/factories/manager_agent.py`**

```python
"""Factory del manager agent: atiende admins, con tools ERP de escritura/lectura."""

from __future__ import annotations

from agno.agent import Agent
from supabase import Client

from app.ai.factories.base import build_db, build_model, session_id_for
from app.ai.tools.manager_tools import build_manager_tools


def get_manager_agent(
    *,
    tenant_id: str,
    user_phone: str,
    system_prompt: str,
    model_id: str | None,
    supabase: Client,
) -> Agent:
    return Agent(
        model=build_model(model_id),
        db=build_db(),
        instructions=system_prompt,
        tools=build_manager_tools(supabase, tenant_id),
        user_id=user_phone,
        session_id=session_id_for(tenant_id, user_phone),
        add_history_to_context=True,
        num_history_runs=8,
        markdown=False,
    )
```

- [ ] **Step 4: Run test**

Run: `pytest tests/test_manager_agent.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/ai/factories/manager_agent.py tests/test_manager_agent.py
git commit -m "feat(ai): manager agent factory"
```

---

## Task 9: Selección de prompt (`app/ai/prompts.py`)

Replica la lógica de `webhook._select_system_prompt`, ahora dentro de `app/ai/`.

**Files:**
- Create: `app/ai/prompts.py`
- Create: `tests/test_ai_prompts.py`

- [ ] **Step 1: Escribir el test**

`tests/test_ai_prompts.py`:

```python
from app.ai.prompts import select_prompt


def test_manager_uses_manager_prompt():
    config = {"system_prompt": "cliente", "manager_prompt": "admin"}
    assert select_prompt(config, "manager") == "admin"


def test_manager_falls_back_to_system_when_no_manager_prompt():
    config = {"system_prompt": "cliente", "manager_prompt": ""}
    assert select_prompt(config, "manager") == "cliente"


def test_client_uses_system_prompt():
    config = {"system_prompt": "cliente", "manager_prompt": "admin"}
    assert select_prompt(config, "client") == "cliente"
```

- [ ] **Step 2: Run test (debe fallar)**

Run: `pytest tests/test_ai_prompts.py -v`
Expected: FAIL.

- [ ] **Step 3: Implementar `app/ai/prompts.py`**

```python
"""Selección del prompt según el modo (client vs manager)."""

from __future__ import annotations


def select_prompt(config: dict, mode: str) -> str:
    if mode == "manager" and config.get("manager_prompt"):
        return str(config["manager_prompt"])
    return str(config.get("system_prompt") or "")
```

- [ ] **Step 4: Run test**

Run: `pytest tests/test_ai_prompts.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add app/ai/prompts.py tests/test_ai_prompts.py
git commit -m "feat(ai): selección de prompt por modo"
```

---

## Task 10: Media — transcripción e imágenes (`app/ai/media/transcription.py`)

**Files:**
- Create: `app/ai/media/__init__.py` (vacío)
- Create: `app/ai/media/transcription.py`
- Create: `tests/test_ai_media.py`

- [ ] **Step 1: Escribir el test**

`tests/test_ai_media.py`:

```python
from agno.media import Image

from app.ai.media.transcription import prepare_images


def test_prepare_images_only_image_types(tmp_path):
    img = tmp_path / "a.jpg"
    img.write_bytes(b"x")
    media = [
        {"type": "image", "local_path": str(img)},
        {"type": "document", "local_path": str(tmp_path / "b.pdf")},
    ]
    images = prepare_images(media)
    assert len(images) == 1
    assert isinstance(images[0], Image)


def test_prepare_images_empty():
    assert prepare_images(None) == []
```

- [ ] **Step 2: Run test (debe fallar)**

Run: `pytest tests/test_ai_media.py -v`
Expected: FAIL.

- [ ] **Step 3: Implementar `app/ai/media/transcription.py`**

```python
"""Transcripción de audio (Whisper) y preparación de imágenes para Agno."""

from __future__ import annotations

import logging

from agno.media import Image
from openai import AsyncOpenAI

from app.ai.config import OPENAI_API_KEY

logger = logging.getLogger("doppel.ai.media")

_AUDIO_TYPES = {"audio", "voice"}
_IMAGE_TYPES = {"image"}

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    return _client


def prepare_images(media: list[dict] | None) -> list[Image]:
    images: list[Image] = []
    for item in media or []:
        if item.get("type") in _IMAGE_TYPES and item.get("local_path"):
            images.append(Image(filepath=item["local_path"]))
    return images


async def transcribe_audio(path: str) -> str:
    """Transcribe un archivo de audio a texto con Whisper. Devuelve '' si falla."""
    try:
        with open(path, "rb") as fh:
            result = await _get_client().audio.transcriptions.create(
                model="whisper-1", file=fh
            )
        return (result.text or "").strip()
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

- [ ] **Step 4: Run test**

Run: `pytest tests/test_ai_media.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add app/ai/media/__init__.py app/ai/media/transcription.py tests/test_ai_media.py
git commit -m "feat(ai): transcripción de audio (whisper) y preparación de imágenes"
```

---

## Task 11: El puente (`app/ai/bridge.py`) + `app/ai/__init__.py`

**Files:**
- Create: `app/ai/bridge.py`
- Modify: `app/ai/__init__.py` (re-exporta respond)
- Create: `tests/test_ai_bridge.py`

- [ ] **Step 1: Escribir el test (con agentes y whisper mockeados)**

`tests/test_ai_bridge.py`:

```python
import asyncio
from unittest.mock import AsyncMock, patch

from app.ai import bridge


class _FakeRun:
    def __init__(self, content): self.content = content


class _FakeAgent:
    def __init__(self, reply): self._reply = reply
    async def arun(self, *a, **k): return _FakeRun(self._reply)


def _run(mode, content, media=None):
    with patch.object(bridge, "get_client_agent", return_value=_FakeAgent("hola cliente")), \
         patch.object(bridge, "get_manager_agent", return_value=_FakeAgent("hola admin")), \
         patch.object(bridge, "transcribe_audio_media", new=AsyncMock(return_value="")), \
         patch.object(bridge, "prepare_images", return_value=[]):
        return asyncio.run(bridge.respond(
            mode=mode, tenant_id="t1", user_phone="+57300",
            content=content, system_prompt="p", model="m",
            supabase=object(), media=media,
        ))


def test_client_mode_uses_client_agent():
    assert _run("client", "hola") == "hola cliente"


def test_manager_mode_uses_manager_agent():
    assert _run("manager", "hola") == "hola admin"


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

- [ ] **Step 2: Run test (debe fallar)**

Run: `pytest tests/test_ai_bridge.py -v`
Expected: FAIL.

- [ ] **Step 3: Implementar `app/ai/bridge.py`**

```python
"""Puente entre el webhook y los agentes Agno. Entrada única por mensaje."""

from __future__ import annotations

import logging
from typing import Literal

from supabase import Client

from app.ai.factories.client_agent import get_client_agent
from app.ai.factories.manager_agent import get_manager_agent
from app.ai.media.transcription import prepare_images, transcribe_audio_media

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
    supabase: Client,
    media: list[dict] | None = None,
) -> str:
    """Ejecuta el agente correspondiente y devuelve el texto final ('' si falla)."""
    try:
        transcript = await transcribe_audio_media(media)
        images = prepare_images(media)

        text_parts = [content] if content else []
        if transcript:
            text_parts.append(f"[Nota de voz]: {transcript}")
        text = "\n".join(text_parts) + _document_note(media)
        text = text.strip()

        factory = get_manager_agent if mode == "manager" else get_client_agent
        agent = factory(
            tenant_id=tenant_id, user_phone=user_phone,
            system_prompt=system_prompt, model_id=model, supabase=supabase,
        )
        run = await agent.arun(text, images=images or None)
        return (run.content or "").strip()
    except Exception:
        logger.exception(
            "respuesta IA falló tenant=%s phone=%s mode=%s", tenant_id, user_phone, mode
        )
        return ""
```

- [ ] **Step 4: Re-exportar en `app/ai/__init__.py`**

```python
"""Subsistema de IA. Única puerta de entrada para el resto del backend."""

from app.ai.bridge import respond

__all__ = ["respond"]
```

- [ ] **Step 5: Run test**

Run: `pytest tests/test_ai_bridge.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add app/ai/bridge.py app/ai/__init__.py tests/test_ai_bridge.py
git commit -m "feat(ai): puente respond() — entrada única del webhook"
```

---

## Task 12: Conectar el webhook a `app.ai.respond`

**Files:**
- Modify: `app/routers/webhook.py` (imports + `_process_bot_response`)

- [ ] **Step 1: Cambiar el import**

En `app/routers/webhook.py:13` cambiar:
`from app.services import ai_core_runtime, meta_api`
→
```python
from app.ai import respond as ai_respond
from app.services import meta_api
```

- [ ] **Step 2: Reemplazar la llamada al core**

En `_process_bot_response`, sustituir el bloque que llama a `ai_core_runtime.respond(...)`
(actualmente líneas ~350-362, que produce `result` y `ai_text`) por:

```python
        system_prompt = _select_system_prompt(config=config, mode=mode)

        ai_text = (await ai_respond(
            mode=mode,
            tenant_id=tenant_id,
            user_phone=user_phone,
            content=inbound_text,
            system_prompt=system_prompt,
            model=str(config.get("ai_model") or "claude-sonnet-4-20250514"),
            supabase=supabase,
            media=media,
        )).strip()
```

> Nota: `media` ya trae `local_path` tras `_download_media_files` (línea ~338).
> Se elimina el uso de `media_paths` para la llamada (Agno recibe `media` con paths).

- [ ] **Step 3: Verificar que no quedan referencias a ai_core_runtime en el webhook**

Run: `grep -n "ai_core_runtime\|media_paths" app/routers/webhook.py`
Expected: sin resultados (o solo la línea de `_download_media_files` si aún se usa para otra cosa; si `media_paths` queda huérfano, eliminar esa asignación).

- [ ] **Step 4: Verificar que la app importa sin error**

Run: `python -c "import app.main"`
Expected: sin excepción.

- [ ] **Step 5: Commit**

```bash
git add app/routers/webhook.py
git commit -m "feat(webhook): usar app.ai.respond (Agno in-process)"
```

---

## Task 13: Actualizar `tests/test_mvp.py`

**Files:**
- Modify: `tests/test_mvp.py` (parches de `ai_core_runtime.respond`)

- [ ] **Step 1: Ver los parches actuales**

Run: `grep -n "ai_core_runtime" tests/test_mvp.py`
Expected: ~4 ocurrencias (líneas ~435, 515, 595, 642).

- [ ] **Step 2: Cambiar el target de los parches**

En cada `patch("app.routers.webhook.ai_core_runtime.respond", ...)` cambiar el
target a `patch("app.routers.webhook.ai_respond", ...)`. Como `ai_respond` es
`async`, el mock debe devolver el texto via `AsyncMock(return_value="<texto>")`
(antes devolvía un dict `{"reply": ...}`; ahora devuelve el string directo).

Ajustar cada side-effect/return: donde antes el fake devolvía `{"reply": "X"}`,
ahora debe devolver `"X"` (string).

- [ ] **Step 3: Run tests del webhook**

Run: `pytest tests/test_mvp.py -v -k "webhook or bot or response"`
Expected: PASS (ajustar returns hasta que pasen).

- [ ] **Step 4: Commit**

```bash
git add tests/test_mvp.py
git commit -m "test: apuntar mocks del webhook a ai_respond (string)"
```

---

## Task 14: Borrar el motor casero y artefactos de ai-core

**Files:**
- Delete: `app/services/agent_core.py`, `app/services/agent_runtime.py`,
  `app/services/ai_bot.py`, `app/services/ai_core_runtime.py`,
  `app/services/tool_runtime.py`, `app/services/client_tools.py`,
  `app/services/erp/tools.py`, `app/services/manager_tools.py`
- Modify: `app/routers/internal.py` (quitar endpoint `/internal/ai/tools`)
- Delete: `tests/test_agent.py`, `tests/test_ai_core_runtime.py`
- Delete: `Dockerfile.ai-core`, `compose.ai-core.yaml`, `DEPLOY_AI_CORE.md`, `ai_core/`

- [ ] **Step 1: Confirmar que nada vivo importa los módulos a borrar**

Run:
```bash
grep -rn "agent_core\|agent_runtime\|ai_bot\|ai_core_runtime\|tool_runtime\|services.client_tools\|erp.tools\|services.manager_tools" app/ --include="*.py"
```
Expected: solo `app/routers/internal.py` (endpoint a quitar). Si aparece algo más, resolver antes de borrar.

- [ ] **Step 2: Quitar el endpoint de tools en `internal.py`**

Eliminar el import `from app.services.tool_runtime import build_tool_registry` y la
ruta que expone `/internal/ai/tools`. Si `internal.py` queda vacío de rutas, quitar
su `include_router` en `app/main.py`; si conserva otras rutas, dejarlo.

- [ ] **Step 3: Borrar los módulos del motor casero**

```bash
git rm app/services/agent_core.py app/services/agent_runtime.py \
       app/services/ai_bot.py app/services/ai_core_runtime.py \
       app/services/tool_runtime.py app/services/client_tools.py \
       app/services/erp/tools.py app/services/manager_tools.py \
       tests/test_agent.py tests/test_ai_core_runtime.py
git rm Dockerfile.ai-core compose.ai-core.yaml DEPLOY_AI_CORE.md
git rm -r ai_core
```

- [ ] **Step 4: Verificar que la app arranca y la suite pasa**

Run: `python -c "import app.main" && pytest -q`
Expected: import OK; tests en verde (los que dependían del motor viejo ya no existen).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: eliminar motor de agente casero y artefactos de ai-core"
```

---

## Task 15: Limpieza de settings obsoletos

**Files:**
- Modify: `app/config.py` (quitar AI_CORE_*/NANOBOT_* si ya nadie los usa)

- [ ] **Step 1: Buscar usos restantes**

Run: `grep -rn "AI_CORE_URL\|AI_CORE_TOKEN\|NANOBOT_RUNTIME\|AI_CORE_TIMEOUT\|DOPPEL_INTERNAL_API_TOKEN" app/ tests/`
Expected: idealmente sin usos en código vivo.

- [ ] **Step 2: Eliminar de `Settings` lo que quedó huérfano**

Quitar de `app/config.py` los campos `AI_CORE_URL`, `AI_CORE_TOKEN`,
`AI_CORE_TIMEOUT_SECONDS` y las properties `NANOBOT_RUNTIME_*` si el Step 1 confirma
que nadie los usa. Conservar lo que siga referenciado.

- [ ] **Step 3: Verificar**

Run: `python -c "import app.main" && pytest -q`
Expected: OK.

- [ ] **Step 4: Commit**

```bash
git add app/config.py .env.example
git commit -m "chore: retirar settings obsoletos del ai-core HTTP"
```

---

## Verificación final

- [ ] `pytest -q` en verde.
- [ ] `python -c "import app.main"` sin error.
- [ ] `grep -rn "import agno" app/` solo dentro de `app/ai/` (frontera respetada).
- [ ] El webhook responde end-to-end con un mensaje de prueba (texto, imagen y nota de voz) contra un tenant real con `AGNO_DB_URL` y `OPENAI_API_KEY` configurados.
```


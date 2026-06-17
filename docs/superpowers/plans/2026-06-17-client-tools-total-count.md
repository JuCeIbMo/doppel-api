# Client Tools: Tool de Conteo Total Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir una tercera tool al client agent que devuelva el total de productos disponibles del tenant.

**Architecture:** Una nueva función `count_available_products` se agrega a `build_client_tools`. Sigue el mismo patrón de closure que las otras dos tools: cierra sobre `supabase` y `tenant_id`, hace una query con `.select(..., count="exact")` y devuelve un entero.

**Tech Stack:** Python 3.11+, Supabase Python SDK (`count="exact"` en `.select()`), Agno (genera el schema desde docstring).

## Global Constraints

- Solo lectura (read-only) — el client agent no puede mutar datos
- El docstring es la descripción que Agno expone al LLM: debe ser clara y en español
- Las tools se registran como closures dentro de `build_client_tools`; no son métodos de clase
- Test runner: `python3 -m pytest tests/test_client_tools.py -q`

---

### Task 1: Implementar `count_available_products`

**Files:**
- Modify: `app/ai/tools/client_tools.py`
- Test: `tests/test_client_tools.py`

**Interfaces:**
- Produces: `count_available_products() -> dict` — devuelve `{"total": int}`

- [ ] **Step 1: Escribir el test que falla**

En `tests/test_client_tools.py`, agregar al final:

```python
def test_count_available_products_returns_total():
    rows = [
        {"name": "Pizza", "price": 10, "available": True},
        {"name": "Pasta", "price": 8, "available": True},
    ]
    tools = build_client_tools(_FakeSupabase(rows), "t1")
    count_tool = next(t for t in tools if t.__name__ == "count_available_products")
    result = asyncio.run(count_tool())
    assert result == {"total": 2}


def test_count_available_products_empty():
    tools = build_client_tools(_FakeSupabase([]), "t1")
    count_tool = next(t for t in tools if t.__name__ == "count_available_products")
    result = asyncio.run(count_tool())
    assert result == {"total": 0}
```

También actualizar el test de nombres:

```python
def test_build_client_tools_returns_callables():
    tools = build_client_tools(_FakeSupabase([]), "t1")
    assert all(callable(t) for t in tools)
    assert {t.__name__ for t in tools} == {
        "lookup_business_info",
        "list_available_products",
        "count_available_products",
    }
```

- [ ] **Step 2: Correr tests para verificar que fallan**

```bash
ANTHROPIC_API_KEY=x OPENAI_API_KEY=x META_APP_ID=x META_APP_SECRET=x META_VERIFY_TOKEN=x \
SUPABASE_URL=https://x.supabase.co \
SUPABASE_SERVICE_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.M2cT4L9pHJcHDhEqOaLbFe5GChKLoVB7UXPB-WlhPIA" \
ENCRYPTION_KEY="$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')" \
AGNO_DB_URL=postgresql://x \
python3 -m pytest tests/test_client_tools.py -q
```

Esperado: FAIL en los dos tests nuevos ("count_available_products not in tools").

- [ ] **Step 3: Implementar la tool en `client_tools.py`**

Dentro de `build_client_tools`, antes del `return`, agregar:

```python
    async def count_available_products() -> dict:
        """Devuelve el total de productos disponibles del negocio.
        Úsalo cuando el cliente pregunte cuántos productos hay en el catálogo."""
        result = (
            supabase.table("products")
            .select("id", count="exact")
            .eq("tenant_id", tenant_id)
            .eq("available", True)
            .execute()
        )
        return {"total": result.count or 0}
```

Y añadir `count_available_products` al `return`:

```python
    return [lookup_business_info, list_available_products, count_available_products]
```

- [ ] **Step 4: Correr tests para verificar que pasan**

```bash
ANTHROPIC_API_KEY=x OPENAI_API_KEY=x META_APP_ID=x META_APP_SECRET=x META_VERIFY_TOKEN=x \
SUPABASE_URL=https://x.supabase.co \
SUPABASE_SERVICE_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.M2cT4L9pHJcHDhEqOaLbFe5GChKLoVB7UXPB-WlhPIA" \
ENCRYPTION_KEY="$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')" \
AGNO_DB_URL=postgresql://x \
python3 -m pytest tests/test_client_tools.py -q
```

Esperado: 4 passed.

- [ ] **Step 5: Commit y push**

```bash
git add app/ai/tools/client_tools.py tests/test_client_tools.py
git commit -m "feat(ai): añadir tool count_available_products al client agent"
git push origin master
```

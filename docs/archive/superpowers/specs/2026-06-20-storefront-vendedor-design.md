# Storefront: capa del agente vendedor de cara al público

**Fecha:** 2026-06-20
**Estado:** Aprobado para planificación

## Problema

El `client_agent` (vendedor de cara al público, WhatsApp) usa `client_tools.py`, que
arma queries crudas a Supabase inline. Problemas:

1. **Scoping disperso:** el `.eq("tenant_id", ...)` se repite a mano en cada query;
   cualquier tool nueva puede olvidarlo.
2. **Sin capa de servicios:** inconsistente con `manager_tools.py`, que delega en los
   ERP services vía `bot_context`.
3. **Sin camino para mutaciones:** se vienen acciones acotadas del cliente (marcar
   ventas) y no hay un lugar limpio y auditable donde vivan.

> Nota: toda la app usa el **service-role key** y bypassa RLS por diseño
> (`supabase_client.py`). La frontera real de seguridad NO es RLS, es el scoping por
> `tenant_id` que centraliza `ERPContext`. Por eso la solución no son endpoints HTTP
> nuevos, sino centralizar en la capa de servicios in-process.

## Objetivos

- Centralizar el tenant scoping en una sola capa.
- Aislar lo que el agente público puede ver/hacer (read-only + una mutación acotada).
- Devolver shapes **lean, optimizados para IA**, sin la info de más que arrastra el
  ERP API (pensado para el dashboard del dueño).
- Minimizar la cantidad de tools y hacerlas a prueba de errores (sin encadenar
  lookups, sin que la IA invente UUIDs).

## No-objetivos (YAGNI)

- No se crean endpoints HTTP. El bot corre in-process en doppel-api.
- No se agregan tools de cotización, historial, categorías ni recomendaciones (se
  evaluarán más adelante).
- No se toca el `manager_agent` ni `manager_tools.py`.

## Diseño

### 1. Nuevo módulo `app/services/storefront.py`

Capa read-only + una mutación acotada para el agente vendedor. Cada método recibe un
`ERPContext` construido con `actor="whatsapp_bot"` (ya existe en el enum), scopea por
`tenant_id` en un solo lugar y devuelve dicts **lean**. Reusa la infraestructura
existente: `SalesService.create_sale` (venta atómica stock+ingreso), `ProductsService`
para resolver productos, `ClientsService.get_by_phone`, y `log_activity` para auditar.

Métodos:

- `business_info(ctx) -> dict`
  → `{name, description, hours, address, payment_methods}`.
  Lectura del perfil del negocio. NO es una tool: se inyecta al prompt (ver §4).

- `search_catalog(ctx, query: str | None = None) -> list[dict]`
  → `[{id, name, price, in_stock}]`.
  - Solo productos `available=True`, ordenados por nombre.
  - Sin `query` lista todo lo disponible; con `query` filtra por nombre (`ilike`).
  - `in_stock` es **booleano** (stock > 0), no expone la cantidad real → contexto más
    chico y no filtra inventario.
  - Incluye `id` como **ancla estable** (ver §3).

- `register_sale(ctx, items: list[dict], customer_phone: str | None = None, payment_method: str = "whatsapp") -> dict`
  - `items` = `[{product_id, quantity}]`. Usa el `id` que el agente ya obtuvo de
    `search_catalog` (no re-resuelve por nombre).
  - Resuelve `customer_phone` → `client_id` vía `ClientsService.get_by_phone`
    (si no existe, queda en `None`, igual que `manager_tools.create_sale`).
  - Delega en `SalesService.create_sale` con el body que ese service ya espera.
  - Devuelve confirmación lean: `{ok: true, total, items: [{name, qty, subtotal}]}`.
  - Errores devueltos como dict claro (no excepción que rompe el flujo IA):
    - producto inexistente / sin stock → `{error, message, detail}` reusando `ERPError`.

### 2. `app/ai/tools/client_tools.py` → wrappers finos

`build_client_tools(supabase, tenant_id)` construye un `ctx = bot_context(tenant_id,
actor="whatsapp_bot")` y expone **2 tools** que delegan en `storefront.py`:

- `search_catalog(query: str | None = None)` → `storefront.search_catalog(ctx, query)`
- `register_sale(items, customer_phone=None, payment_method="whatsapp")`
  → `storefront.register_sale(...)`

Se elimina el acceso directo a Supabase y las queries inline. Se quitan las viejas
`lookup_business_info`, `list_available_products`, `count_available_products`.

### 3. Conservación del producto entre mensajes (id como ancla)

Flujo objetivo: cliente menciona un producto → `search_catalog` → confirma → en
mensajes siguientes se marca la venta de **ese producto exacto**, no uno re-resuelto.

Resolución **sin infraestructura nueva**: Agno ya persiste el historial de
conversación en Postgres (es dueño del historial). Ese historial es la memoria.

1. `search_catalog` devuelve el `id` de cada producto.
2. El turno donde la IA mostró `{id, name, price, in_stock}` queda en el historial.
3. `register_sale` recibe `product_id` = el `id` que la IA ya vio. La IA **copia** un
   valor que está en su propio contexto (confiable), no lo inventa. La búsqueda por
   nombre nunca vuelve a ocurrir en el momento de vender → imposible re-resolver a
   otro producto.
4. Disciplina por instrucción del prompt (no código): "Antes de marcar una venta,
   confirmá producto, cantidad y precio. Usá el `id` que obtuviste de `search_catalog`;
   nunca adivines ni re-busques por nombre."

### 4. Inyección de `business_info` al prompt (mecanismo Agno)

`business_info` es data estática del negocio → no merece una tool. Se inyecta vía
**dependencies** de Agno (`docs.agno.com/dependencies`). En `get_client_agent`:

```python
ctx = bot_context(tenant_id, actor="whatsapp_bot")
agent = Agent(
    ...,
    dependencies={"business_info": lambda: storefront.business_info(ctx)},
    add_dependencies_to_context=True,
    ...,
)
```

Se usa `add_dependencies_to_context=True` (no template `{business_info}`) porque el
`system_prompt` lo escribe el tenant y puede contener llaves sueltas que romperían la
sustitución de template. Agno resuelve el callable en runtime e inyecta el resultado
bajo `<additional context>` en el mensaje.

## Seguridad y aislamiento

- Actor `whatsapp_bot` ≠ `admin_bot` → la auditoría distingue las ventas del vendedor
  público de las del asistente admin.
- La mutación pasa por `SalesService.create_sale` (atómica, ya probada), nunca por SQL
  crudo.
- Catálogo solo `available=True`; `in_stock` booleano, sin exponer inventario real ni
  datos de otros clientes/tenants.
- Todo scopeado por `ctx.tenant_id` en la capa storefront.

## Tests

Siguiendo el patrón actual (python3 global + env vars dummy, sin conftest):

- `storefront.search_catalog`: scoping por tenant; con/sin query; solo `available`;
  `in_stock` booleano correcto.
- `storefront.register_sale`: venta feliz (devuelve total + items lean); product_id
  inexistente → error dict; stock insuficiente → error dict; `customer_phone`
  resuelto vs. no encontrado.
- `client_tools`: las 2 tools delegan y exponen las firmas esperadas para Agno.

## Archivos afectados

- `app/services/storefront.py` (nuevo)
- `app/ai/tools/client_tools.py` (reescrito a wrappers)
- `app/ai/factories/client_agent.py` (agrega dependencies + ctx)
- `tests/` (nuevos tests de storefront + client_tools)

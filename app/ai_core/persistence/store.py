"""LangGraph Store: memoria de largo plazo del agente admin, sobre el mismo Postgres de chat.

El checkpointer guarda la *conversación* (scoped por `thread_id`); el store guarda lo que
tiene que sobrevivir a la conversación: lo que el agente aprendió del dueño y de su negocio.
Van al mismo Postgres (`CHAT_DB_URL`) y **reusan el pool** de `checkpointer.get_pool()`, así
que esto no agrega infraestructura, sólo tablas.

En un LangSmith Deployment el store viene provisionado; acá el bot corre dentro del proceso de
doppel-api, así que lo cableamos nosotros. Es el mismo trato que `checkpointer.py`.

El aislamiento entre tenants NO vive acá: vive en el `namespace` que
`app/ai_core/admin/agent.py` le pasa al `StoreBackend`. Este módulo sólo provee la conexión.

**Singleton de proceso, no uno por tenant.** `AsyncPostgresStore` hereda de
`AsyncBatchedBaseStore`, que captura el event loop en `__init__` y levanta una task de fondo
para batchear las operaciones. Uno por agente serían N tasks colgadas del loop, una por tenant
cacheado en `bridge._agents`.
"""

from __future__ import annotations

import asyncio

from langgraph.store.postgres import AsyncPostgresStore

from app.ai_core.persistence.checkpointer import get_pool

_store: AsyncPostgresStore | None = None
_store_lock = asyncio.Lock()
_setup_done = False


async def open_store() -> AsyncPostgresStore:
    """Return the process-wide store, creating it on first use.

    Async on purpose, like `open_checkpointer`: the store has to be constructed from inside
    the running loop (see the module docstring), and `setup()` is a round trip.
    """
    global _store, _setup_done
    async with _store_lock:
        if _store is None:
            pool = await get_pool()
            _store = AsyncPostgresStore(conn=pool)
        if not _setup_done:
            # Idempotent (`CREATE TABLE IF NOT EXISTS` + versioned migrations), but it is a
            # round trip, so run it once per process instead of once per agent build.
            await _store.setup()
            _setup_done = True
        return _store


async def close_store() -> None:
    """Release the store. Called from the app lifespan, BEFORE `close_pool()`.

    Order matters: the store borrows connections from the checkpointer's pool, so closing the
    pool first would leave its background batching task writing into a closed pool.
    """
    global _store, _setup_done
    async with _store_lock:
        if _store is not None:
            # `__aexit__` only stops the TTL sweeper (we configure no TTL, so it is a no-op
            # today) and deliberately does not touch the pool — releasing the connections is
            # `close_pool()`'s job. The batching task is cancelled by `AsyncBatchedBaseStore.
            # __del__` once the last reference is dropped below.
            await _store.__aexit__(None, None, None)
            _store = None
        _setup_done = False

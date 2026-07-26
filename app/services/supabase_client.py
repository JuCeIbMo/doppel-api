"""Supabase clients. Async on purpose — see the note below before changing this.

Both clients are `AsyncClient`, so every terminal call is awaited:
`await supabase.table(...).select(...).execute()`, `await ...auth.get_user(...)`,
`await ...storage.from_(...).upload(...)`.

This is what makes the `async def` signatures across the ERP layer honest. With
the synchronous client, every `async def` service was doing blocking network I/O
inside the event loop: FastAPI, the WhatsApp webhook and the LangGraph agent all
stalled for the duration of each Supabase round-trip while pretending not to.

Forgetting an `await` now fails loudly (`.data` on a coroutine raises
AttributeError) instead of silently blocking the loop.

`AsyncClient(...)` is constructed directly rather than through
`create_async_client()`: that helper is only async because it probes for an
existing user session, which is meaningless for a service-role key. Direct
construction sets the same `apiKey`/`Authorization` headers, so the clients stay
lazily created from sync code and no startup hook is needed.
"""

from supabase import AsyncClient

from app.config import settings

_client: AsyncClient | None = None
_auth_client: AsyncClient | None = None


def get_supabase() -> AsyncClient:
    """Return the service-role database client.

    Keep this client away from Supabase Auth session calls so its Authorization
    header stays on the service role and continues to bypass RLS.
    """
    global _client
    if _client is None:
        _client = AsyncClient(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
    return _client


def get_supabase_auth() -> AsyncClient:
    """Return a separate client for Supabase Auth operations."""
    global _auth_client
    if _auth_client is None:
        _auth_client = AsyncClient(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
    return _auth_client

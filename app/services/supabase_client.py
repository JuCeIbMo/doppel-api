from supabase import Client, create_client

from app.config import settings

_client: Client | None = None
_auth_client: Client | None = None


def get_supabase() -> Client:
    """Return the service-role database client.

    Keep this client away from Supabase Auth session calls so its Authorization
    header stays on the service role and continues to bypass RLS.
    """
    global _client
    if _client is None:
        _client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
    return _client


def get_supabase_auth() -> Client:
    """Return a separate client for Supabase Auth operations."""
    global _auth_client
    if _auth_client is None:
        _auth_client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
    return _auth_client

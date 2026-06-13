from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.services.supabase_client import get_supabase, get_supabase_auth

security = HTTPBearer()
internal_security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Verify Bearer JWT token from Supabase Auth and return the user."""
    token = credentials.credentials
    try:
        supabase = get_supabase_auth()
        response = supabase.auth.get_user(token)
        return response.user
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_tenant(current_user=Depends(get_current_user)):
    """Resolve the tenant for the authenticated user. Raises 404 if not onboarded."""
    result = get_supabase().table("tenants").select("*").eq("user_id", str(current_user.id)).execute()
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No tienes un negocio conectado. Conecta tu WhatsApp primero.",
        )
    return result.data[0]


async def require_internal_api_token(
    credentials: HTTPAuthorizationCredentials = Depends(internal_security),
):
    """Authenticate service-to-service calls into Doppel internal endpoints."""
    expected = settings.DOPPEL_INTERNAL_API_TOKEN
    if not expected or credentials.credentials != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal API token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {"service": "internal"}

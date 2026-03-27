from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.services.supabase_client import get_supabase

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Verify Bearer JWT token from Supabase Auth and return the user."""
    token = credentials.credentials
    try:
        supabase = get_supabase()
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

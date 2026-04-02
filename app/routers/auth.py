import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.dependencies import get_current_user
from app.models.schemas import (
    LoginResponse,
    OTPSendRequest,
    OTPVerifyRequest,
    TokenRefreshRequest,
    UserResponse,
)
from app.services.supabase_client import get_supabase

logger = logging.getLogger("doppel.auth")
router = APIRouter(prefix="/auth", tags=["Auth"])


# OTP rate limits
_OTP_EMAIL_MAX = 3
_OTP_EMAIL_WINDOW_MINUTES = 5
_OTP_IP_MAX = 10
_OTP_IP_WINDOW_MINUTES = 5


def _check_otp_rate_limits(email: str, ip: str) -> None:
    supabase = get_supabase()
    now = datetime.now(timezone.utc)

    email_cutoff = (now - timedelta(minutes=_OTP_EMAIL_WINDOW_MINUTES)).isoformat()
    email_count = (
        supabase.table("login_attempts")
        .select("id", count="exact")
        .eq("email", email)
        .eq("ip_address", f"otp:{ip}")
        .gte("attempted_at", email_cutoff)
        .execute()
        .count
    )
    if email_count >= _OTP_EMAIL_MAX:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Demasiados códigos enviados. Espera {_OTP_EMAIL_WINDOW_MINUTES} minutos.",
        )

    ip_cutoff = (now - timedelta(minutes=_OTP_IP_WINDOW_MINUTES)).isoformat()
    ip_count = (
        supabase.table("login_attempts")
        .select("id", count="exact")
        .eq("ip_address", f"otp:{ip}")
        .gte("attempted_at", ip_cutoff)
        .execute()
        .count
    )
    if ip_count >= _OTP_IP_MAX:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Demasiados intentos desde tu red. Espera {_OTP_IP_WINDOW_MINUTES} minutos.",
        )


@router.post("/otp/send", status_code=status.HTTP_202_ACCEPTED)
async def send_otp(request: Request, data: OTPSendRequest):
    """Send a 6-digit OTP to the email. Creates the user if they don't exist."""
    ip = request.client.host
    _check_otp_rate_limits(data.email, ip)

    try:
        get_supabase().auth.sign_in_with_otp({
            "email": data.email,
            "options": {"should_create_user": True},
        })
    except Exception:
        logger.exception("OTP send failed for %s", data.email)

    # Record attempt for rate limiting (prefix ip with "otp:" to separate from login attempts)
    try:
        get_supabase().table("login_attempts").insert({
            "email": data.email,
            "ip_address": f"otp:{ip}",
        }).execute()
    except Exception:
        pass

    # Always 202 to prevent email enumeration
    return {"message": "Si el email es válido, recibirás un código de verificación."}


@router.post("/otp/verify", response_model=LoginResponse)
async def verify_otp(data: OTPVerifyRequest):
    """Verify the OTP code and return a session JWT."""
    try:
        response = get_supabase().auth.verify_otp({
            "email": data.email,
            "token": data.token,
            "type": "email",
        })
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código inválido o expirado.",
        )

    if not response.session:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código inválido o expirado.",
        )

    logger.info("OTP verified for %s", data.email)
    return LoginResponse(
        access_token=response.session.access_token,
        refresh_token=response.session.refresh_token,
        expires_in=response.session.expires_in,
    )


@router.post("/token/refresh", response_model=LoginResponse)
async def refresh_token(data: TokenRefreshRequest):
    """Exchange a refresh_token for a new access_token."""
    try:
        response = get_supabase().auth.refresh_session(data.refresh_token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token invalido o expirado.",
        )
    if not response.session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token invalido o expirado.",
        )
    return LoginResponse(
        access_token=response.session.access_token,
        refresh_token=response.session.refresh_token,
        expires_in=response.session.expires_in,
    )


@router.get("/me", response_model=UserResponse)
async def me(current_user=Depends(get_current_user)):
    return UserResponse(
        user_id=str(current_user.id),
        email=current_user.email,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(current_user=Depends(get_current_user)):
    try:
        get_supabase().auth.admin.sign_out(str(current_user.id))
    except Exception:
        pass  # Best-effort: invalidate refresh token server-side
    return None

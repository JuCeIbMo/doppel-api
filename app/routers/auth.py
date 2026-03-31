import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.dependencies import get_current_user
from app.models.schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    LoginResponse,
    OTPSendRequest,
    OTPVerifyRequest,
    RegisterRequest,
    RegisterResponse,
    ResetPasswordRequest,
    UserResponse,
)
from app.services.supabase_client import get_supabase

logger = logging.getLogger("doppel.auth")
router = APIRouter(prefix="/auth")

# Rate limit thresholds
_EMAIL_MAX_ATTEMPTS = 5
_EMAIL_WINDOW_MINUTES = 15
_IP_MAX_ATTEMPTS = 20
_IP_WINDOW_MINUTES = 1


def _check_rate_limits(email: str, ip: str) -> None:
    """Raise 429 if email or IP exceeds failed-attempt thresholds."""
    supabase = get_supabase()
    now = datetime.now(timezone.utc)

    email_cutoff = (now - timedelta(minutes=_EMAIL_WINDOW_MINUTES)).isoformat()
    email_count = (
        supabase.table("login_attempts")
        .select("id", count="exact")
        .eq("email", email)
        .gte("attempted_at", email_cutoff)
        .execute()
        .count
    )
    if email_count >= _EMAIL_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Cuenta bloqueada temporalmente. Espera {_EMAIL_WINDOW_MINUTES} minutos e intenta de nuevo.",
        )

    ip_cutoff = (now - timedelta(minutes=_IP_WINDOW_MINUTES)).isoformat()
    ip_count = (
        supabase.table("login_attempts")
        .select("id", count="exact")
        .eq("ip_address", ip)
        .gte("attempted_at", ip_cutoff)
        .execute()
        .count
    )
    if ip_count >= _IP_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Demasiados intentos desde tu red. Espera {_IP_WINDOW_MINUTES} minuto.",
        )


def _record_failed_attempt(email: str, ip: str) -> None:
    try:
        get_supabase().table("login_attempts").insert({
            "email": email,
            "ip_address": ip,
        }).execute()
    except Exception:
        logger.exception("Failed to record login attempt")


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
        expires_in=response.session.expires_in,
    )


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(data: RegisterRequest):
    supabase = get_supabase()
    try:
        response = supabase.auth.sign_up({"email": data.email, "password": data.password})
    except Exception as e:
        msg = getattr(e, "message", str(e))
        logger.warning("Register failed for %s: %s", data.email, msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    if not response.user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No se pudo crear la cuenta.")

    logger.info("New user registered: %s", data.email)
    return RegisterResponse(
        success=True,
        user_id=str(response.user.id),
        message="Cuenta creada. Revisa tu email para confirmar tu dirección.",
    )


@router.post("/login", response_model=LoginResponse)
async def login(request: Request, data: LoginRequest):
    ip = request.client.host

    _check_rate_limits(data.email, ip)

    supabase = get_supabase()
    try:
        response = supabase.auth.sign_in_with_password({"email": data.email, "password": data.password})
    except Exception:
        _record_failed_attempt(data.email, ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos.",
        )

    logger.info("User logged in: %s", data.email)
    return LoginResponse(
        access_token=response.session.access_token,
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
    # El JWT expira solo (1h por defecto en Supabase).
    # El cliente debe descartar el token al recibir este 204.
    return None


@router.post("/forgot-password", status_code=status.HTTP_204_NO_CONTENT)
async def forgot_password(data: ForgotPasswordRequest):
    """Send a password reset email. Always returns 204 — no email enumeration."""
    try:
        get_supabase().auth.reset_password_email(data.email)
    except Exception:
        pass  # Never reveal whether the email exists
    return None


@router.post("/reset-password")
async def reset_password(data: ResetPasswordRequest):
    """
    Reset password using the access_token from the recovery link.
    Frontend captures the token from: https://doppel.lat/auth/reset#access_token=...
    """
    supabase = get_supabase()
    try:
        user_response = supabase.auth.get_user(data.access_token)
        user_id = str(user_response.user.id)
        supabase.auth.admin.update_user_by_id(user_id, {"password": data.new_password})
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token inválido o expirado.",
        )
    return {"message": "Contraseña actualizada exitosamente."}

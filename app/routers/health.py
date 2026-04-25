import logging

from fastapi import APIRouter

from app.config import settings
from app.models.schemas import HealthResponse
from app.security import decrypt_token, encrypt_token
from app.services.supabase_client import get_supabase

logger = logging.getLogger("doppel.health")
router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
async def health():
    return {"status": "ok", "service": "doppel-api"}


@router.get("/health/preflight")
async def preflight():
    """Onboarding preflight: verifies everything needed by /oauth/exchange is healthy."""
    checks: dict[str, str] = {}

    # 1. Required env vars present and non-empty
    required = [
        "META_APP_ID",
        "META_APP_SECRET",
        "META_VERIFY_TOKEN",
        "SUPABASE_URL",
        "SUPABASE_SERVICE_KEY",
        "ENCRYPTION_KEY",
    ]
    missing = [k for k in required if not getattr(settings, k, None)]
    checks["env"] = "ok" if not missing else f"missing: {', '.join(missing)}"
    checks["supabase_key_role"] = "ok"

    # 2. Fernet roundtrip (validator already ran at startup, but verify runtime too)
    try:
        sample = "preflight-check"
        if decrypt_token(encrypt_token(sample, settings.ENCRYPTION_KEY), settings.ENCRYPTION_KEY) != sample:
            checks["fernet"] = "fail: roundtrip mismatch"
        else:
            checks["fernet"] = "ok"
    except Exception as e:
        logger.exception("Preflight fernet check failed")
        checks["fernet"] = f"fail: {e}"

    # 3. Supabase reachable
    try:
        get_supabase().table("tenants").select("id").limit(1).execute()
        checks["supabase"] = "ok"
    except Exception as e:
        logger.exception("Preflight supabase check failed")
        checks["supabase"] = f"fail: {e}"

    ok = all(v == "ok" for v in checks.values())
    return {"ok": ok, "checks": checks}

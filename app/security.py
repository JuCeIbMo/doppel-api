import hashlib
import hmac
from functools import lru_cache

from cryptography.fernet import Fernet


def verify_webhook_signature(payload: bytes, signature_header: str, app_secret: str) -> bool:
    """Verify Meta's X-Hub-Signature-256 header on webhook POST requests."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), payload, hashlib.sha256).hexdigest()
    received = signature_header[7:]  # strip "sha256="
    return hmac.compare_digest(expected, received)


def validate_fernet_key(key: str) -> None:
    """Raise ValueError if key is not a valid Fernet key. Call at startup."""
    if not key:
        raise ValueError("ENCRYPTION_KEY is empty")
    try:
        Fernet(key.encode())
    except Exception as e:
        raise ValueError(
            "ENCRYPTION_KEY is not a valid Fernet key (must be 32 url-safe base64-encoded bytes). "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\". "
            f"Underlying error: {e}"
        ) from e


@lru_cache(maxsize=1)
def _fernet(key: str) -> Fernet:
    return Fernet(key.encode())


def encrypt_token(token: str, key: str) -> str:
    return _fernet(key).encrypt(token.encode()).decode()


def decrypt_token(encrypted: str, key: str) -> str:
    return _fernet(key).decrypt(encrypted.encode()).decode()

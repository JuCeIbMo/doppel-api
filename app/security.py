import hashlib
import hmac

from cryptography.fernet import Fernet


def verify_webhook_signature(payload: bytes, signature_header: str, app_secret: str) -> bool:
    """Verify Meta's X-Hub-Signature-256 header on webhook POST requests."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), payload, hashlib.sha256).hexdigest()
    received = signature_header[7:]  # strip "sha256="
    return hmac.compare_digest(expected, received)


def _fernet(key: str) -> Fernet:
    return Fernet(key.encode())


def encrypt_token(token: str, key: str) -> str:
    return _fernet(key).encrypt(token.encode()).decode()


def decrypt_token(encrypted: str, key: str) -> str:
    return _fernet(key).decrypt(encrypted.encode()).decode()

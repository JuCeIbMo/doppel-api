from pydantic import field_validator
from pydantic_settings import BaseSettings

from app.security import validate_fernet_key


class Settings(BaseSettings):
    # Meta
    META_APP_ID: str
    META_APP_SECRET: str
    META_VERIFY_TOKEN: str
    META_API_VERSION: str = "v21.0"

    # Supabase
    SUPABASE_URL: str
    SUPABASE_SERVICE_KEY: str

    # Encryption (Fernet key: run `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`)
    ENCRYPTION_KEY: str

    # WhatsApp registration PIN sent to Meta when registering a phone number
    WA_REGISTRATION_PIN: str = "000000"

    # CORS — comma-separated origins or JSON list in env
    ALLOWED_ORIGINS: list[str] = ["https://doppel.lat"]

    # Anthropic — leave empty to disable AI bot responses
    ANTHROPIC_API_KEY: str = ""
    AI_CONTEXT_MESSAGES: int = 20
    META_API_RETRIES: int = 3
    META_API_RETRY_DELAY_MS: int = 300
    ANTHROPIC_API_RETRIES: int = 2

    @field_validator("ENCRYPTION_KEY")
    @classmethod
    def _validate_encryption_key(cls, v: str) -> str:
        validate_fernet_key(v)
        return v

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

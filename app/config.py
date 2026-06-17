import base64
import json

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.security import validate_fernet_key


class Settings(BaseSettings):
    # Meta
    META_APP_ID: str
    META_APP_SECRET: str
    META_VERIFY_TOKEN: str
    META_API_VERSION: str = "v21.0"

    # Supabase
    SUPABASE_URL: str
    SUPABASE_SERVICE_KEY: str = Field(
        validation_alias=AliasChoices("SUPABASE_SERVICE_KEY", "SUPABASE_SERVICE_ROLE_KEY")
    )

    # Encryption (Fernet key: run `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`)
    ENCRYPTION_KEY: str

    # WhatsApp registration PIN sent to Meta when registering a phone number
    WA_REGISTRATION_PIN: str = "000000"

    # CORS — comma-separated origins or JSON list in env
    ALLOWED_ORIGINS: list[str] = ["https://doppel.lat"]

    # Anthropic — leave empty to disable AI bot responses
    ANTHROPIC_API_KEY: str = ""
    META_API_RETRIES: int = 3
    META_API_RETRY_DELAY_MS: int = 300
    ANTHROPIC_API_RETRIES: int = 2

    # Agno (Postgres separado para historial/memoria de los agentes)
    AGNO_DB_URL: str = ""
    # OpenAI Whisper para transcribir notas de voz de WhatsApp
    OPENAI_API_KEY: str = ""
    AI_DEFAULT_MODEL: str = "claude-sonnet-4-20250514"

    # Empty value disables agent responses; any non-empty value enables the bot.
    AI_CORE_URL: str = Field(
        default="",
        validation_alias=AliasChoices("AI_CORE_URL", "NANOBOT_RUNTIME_URL"),
    )

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def _parse_list_setting(cls, v):
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            raw = v.strip()
            if not raw:
                return []
            if raw.startswith("["):
                try:
                    return json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise ValueError("Invalid JSON list value") from exc
            return [item.strip() for item in raw.split(",") if item.strip()]
        return v

    @field_validator("ENCRYPTION_KEY")
    @classmethod
    def _validate_encryption_key(cls, v: str) -> str:
        validate_fernet_key(v)
        return v

    @field_validator("SUPABASE_SERVICE_KEY")
    @classmethod
    def _validate_supabase_service_key(cls, v: str) -> str:
        try:
            payload = v.split(".")[1]
            padding = "=" * (-len(payload) % 4)
            decoded = base64.urlsafe_b64decode(payload + padding)
            claims = json.loads(decoded)
        except Exception as exc:
            raise ValueError("SUPABASE_SERVICE_KEY must be a valid Supabase JWT") from exc

        if claims.get("role") != "service_role":
            raise ValueError(
                "SUPABASE_SERVICE_KEY/SUPABASE_SERVICE_ROLE_KEY must be the Supabase service_role key, not anon/public"
            )
        return v

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        enable_decoding=False,
        extra="ignore",
    )


settings = Settings()

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DOPPEL_API_URL: str
    DOPPEL_INTERNAL_API_TOKEN: str
    AI_CORE_API_TOKEN: str = ""
    AI_CORE_DB_URL: str = ""
    GOOGLE_API_KEY: str = ""
    AI_CORE_GEMINI_MODEL: str = "gemini-2.0-flash-001"
    AI_CORE_NUM_HISTORY_RUNS: int = 10
    # Echo mode: bypass the model and reply with tenant/user. For wiring tests.
    AI_CORE_ECHO: bool = False
    ANTHROPIC_API_KEY: str = ""
    AI_CORE_MAX_TOOL_RESULT_CHARS: int = 8000
    AI_CORE_MAX_TOKENS: int = 1024
    AI_CORE_CLIENT_MAX_ITERATIONS: int = 4
    AI_CORE_MANAGER_MAX_ITERATIONS: int = 8

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

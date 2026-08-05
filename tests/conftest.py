"""Configuración común cargada antes de importar la aplicación en los tests."""

import os

TEST_ENV = {
    "META_APP_ID": "test-app-id",
    "META_APP_SECRET": "test-app-secret",
    "META_VERIFY_TOKEN": "test-verify-token",
    "SUPABASE_URL": "http://localhost",
    "SUPABASE_SERVICE_KEY": "x.eyJyb2xlIjogInNlcnZpY2Vfcm9sZSJ9.y",
    "ENCRYPTION_KEY": "oZRrOD525wcQ0CJveupENSX1tDwKfP6e1XrDGn9P1Kw=",
    "CHAT_DB_URL": "postgresql://ai:ai@localhost:5532/chat",
}

for name, value in TEST_ENV.items():
    os.environ.setdefault(name, value)

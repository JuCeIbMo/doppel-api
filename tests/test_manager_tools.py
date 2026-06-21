"""Unit tests for the manager tools factory.

app.config instantiates Settings() at import time (transitively via
app.services.erp.*), requiring these env vars. Set safe test defaults before import.
"""

import os

os.environ.setdefault("META_APP_ID", "test-app-id")
os.environ.setdefault("META_APP_SECRET", "test-app-secret")
os.environ.setdefault("META_VERIFY_TOKEN", "test-verify-token")
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "x.eyJyb2xlIjogInNlcnZpY2Vfcm9sZSJ9.y")
os.environ.setdefault("ENCRYPTION_KEY", "oZRrOD525wcQ0CJveupENSX1tDwKfP6e1XrDGn9P1Kw=")
os.environ.setdefault("AGNO_DB_URL", "postgresql+psycopg://ai:ai@localhost:5532/ai")

from app.ai.tools.manager_tools import build_manager_tools


def test_build_manager_tools_names():
    tools = build_manager_tools("t1")
    assert {t.__name__ for t in tools} == {
        "get_dashboard_summary", "get_stock", "get_top_products",
        "create_sale", "adjust_stock",
    }
    assert all(callable(t) for t in tools)

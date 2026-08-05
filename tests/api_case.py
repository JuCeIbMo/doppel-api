"""Base común para probar los routers FastAPI con dependencias aisladas."""

import unittest

from fastapi.testclient import TestClient

from app.main import app

class ApiTestCase(unittest.TestCase):
    def setUp(self):
        app.dependency_overrides.clear()
        app.state.http_client = object()
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.client.close()

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from opsdevcode_specmint.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)

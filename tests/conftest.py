import sys
import os

# Make backend importable from the tests directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from fastapi.testclient import TestClient
from main import app

DEMO_KEY = "demo-key-123"
ADMIN_KEY = "admin-key-456"
TEST_KEY = "test-key-789"
HEADERS = {"X-API-Key": DEMO_KEY}
ADMIN_HEADERS = {"X-API-Key": ADMIN_KEY}
TEST_HEADERS = {"X-API-Key": TEST_KEY}


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def launched_job(client):
    res = client.post("/jobs", json={}, headers=HEADERS)
    assert res.status_code == 201
    return res.json()

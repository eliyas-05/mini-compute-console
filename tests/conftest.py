import sys
import os

# Make backend importable from the tests directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from fastapi.testclient import TestClient
from main import app

DEMO_KEY   = "demo-key-123"
ADMIN_KEY  = "admin-key-456"
TEST_KEY   = "test-key-789"
TENANT_KEY = "tenant-key-000"
HEADERS        = {"X-API-Key": DEMO_KEY}
ADMIN_HEADERS  = {"X-API-Key": ADMIN_KEY}
TEST_HEADERS   = {"X-API-Key": TEST_KEY}
TENANT_HEADERS = {"X-API-Key": TENANT_KEY}


@pytest.fixture(autouse=True)
def reset_jobs():
    import job_engine
    job_engine._jobs.clear()
    yield
    job_engine._jobs.clear()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def launched_job(client):
    res = client.post("/jobs", json={}, headers=HEADERS)
    assert res.status_code == 201
    return res.json()

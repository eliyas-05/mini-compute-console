import sys
import os

# Make backend importable from the tests directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# Point the database at a throwaway temp file so tests never touch console.db
import tempfile
_test_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_test_db.close()
os.environ["DB_PATH"] = _test_db.name

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
def reset_state():
    import job_engine, audit_log, webhooks, auth, alerts
    job_engine._jobs.clear()
    audit_log._audit_entries.clear()
    webhooks._webhooks.clear()
    alerts._alerts.clear()
    auth._rate_counters.clear()
    yield
    job_engine._jobs.clear()
    audit_log._audit_entries.clear()
    webhooks._webhooks.clear()
    alerts._alerts.clear()
    auth._rate_counters.clear()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def launched_job(client):
    res = client.post("/jobs", json={}, headers=HEADERS)
    assert res.status_code == 201
    return res.json()

"""Integration tests for the Mini Compute Console API."""
import pytest
from conftest import HEADERS, ADMIN_HEADERS


# ── Auth ──────────────────────────────────────────────────────────────────────

def test_no_key_returns_401(client):
    assert client.get("/providers").status_code == 401


def test_invalid_key_returns_401(client):
    assert client.get("/providers", headers={"X-API-Key": "bad-key"}).status_code == 401


def test_valid_key_accepted(client):
    assert client.get("/providers", headers=HEADERS).status_code == 200


# ── Providers ─────────────────────────────────────────────────────────────────

def test_providers_returns_list(client):
    data = client.get("/providers", headers=HEADERS).json()
    assert isinstance(data, list)
    assert len(data) == 8


def test_provider_has_required_fields(client):
    provider = client.get("/providers", headers=HEADERS).json()[0]
    for field in ("id", "name", "region", "gpu_type", "price_per_hour", "uptime_pct", "status"):
        assert field in provider, f"Missing field: {field}"


def test_get_single_provider(client):
    providers = client.get("/providers", headers=HEADERS).json()
    pid = providers[0]["id"]
    res = client.get(f"/providers/{pid}", headers=HEADERS)
    assert res.status_code == 200
    assert res.json()["id"] == pid


def test_unknown_provider_returns_404(client):
    assert client.get("/providers/does-not-exist", headers=HEADERS).status_code == 404


# ── Jobs ──────────────────────────────────────────────────────────────────────

def test_launch_job_auto_pick(client, launched_job):
    for field in ("job_id", "provider_id", "provider_name", "gpu_type", "status", "cost_so_far"):
        assert field in launched_job, f"Missing field: {field}"
    assert launched_job["status"] == "queued"
    assert launched_job["cost_so_far"] == 0.0


def test_launch_job_specific_provider(client):
    # pick an available provider
    providers = client.get("/providers", headers=HEADERS).json()
    available = next(p for p in providers if p["status"] == "available")
    res = client.post("/jobs", json={"provider_id": available["id"]}, headers=HEADERS)
    assert res.status_code == 201
    assert res.json()["provider_id"] == available["id"]


def test_launch_job_unknown_provider(client):
    res = client.post("/jobs", json={"provider_id": "fake-provider"}, headers=HEADERS)
    assert res.status_code == 400


def test_launch_job_busy_provider(client):
    providers = client.get("/providers", headers=HEADERS).json()
    busy = next((p for p in providers if p["status"] == "busy"), None)
    if busy:
        res = client.post("/jobs", json={"provider_id": busy["id"]}, headers=HEADERS)
        assert res.status_code == 400


def test_get_job_status(client, launched_job):
    job_id = launched_job["job_id"]
    res = client.get(f"/jobs/{job_id}", headers=HEADERS)
    assert res.status_code == 200
    assert res.json()["job_id"] == job_id


def test_get_unknown_job_returns_404(client):
    assert client.get("/jobs/nope", headers=HEADERS).status_code == 404


def test_list_jobs(client, launched_job):
    res = client.get("/jobs", headers=HEADERS)
    assert res.status_code == 200
    ids = [j["job_id"] for j in res.json()]
    assert launched_job["job_id"] in ids


def test_cancel_job(client, launched_job):
    job_id = launched_job["job_id"]
    res = client.delete(f"/jobs/{job_id}", headers=HEADERS)
    assert res.status_code == 200
    assert res.json()["status"] == "cancelled"


def test_cancel_unknown_job_returns_404(client):
    assert client.delete("/jobs/ghost", headers=HEADERS).status_code == 404


def test_get_logs(client, launched_job):
    job_id = launched_job["job_id"]
    res = client.get(f"/jobs/{job_id}/logs", headers=HEADERS)
    assert res.status_code == 200
    assert "logs" in res.json()
    assert isinstance(res.json()["logs"], list)


# ── Analytics ─────────────────────────────────────────────────────────────────

def test_analytics_shape(client, launched_job):
    res = client.get("/analytics", headers=HEADERS)
    assert res.status_code == 200
    data = res.json()
    for field in ("total_jobs", "completed_jobs", "total_spend", "provider_breakdown"):
        assert field in data


def test_analytics_counts_jobs(client):
    before = client.get("/analytics", headers=HEADERS).json()["total_jobs"]
    client.post("/jobs", json={}, headers=HEADERS)
    after = client.get("/analytics", headers=HEADERS).json()["total_jobs"]
    assert after == before + 1


# ── Admin ─────────────────────────────────────────────────────────────────────

def test_audit_log_requires_admin(client, launched_job):
    assert client.get("/admin/audit", headers=HEADERS).status_code == 403


def test_audit_log_accessible_to_admin(client, launched_job):
    res = client.get("/admin/audit", headers=ADMIN_HEADERS)
    assert res.status_code == 200
    assert isinstance(res.json(), list)
    assert len(res.json()) >= 1


# ── Brand ─────────────────────────────────────────────────────────────────────

def test_brand_voltgrid(client):
    res = client.get("/brand/voltgrid")
    assert res.status_code == 200
    assert "primary_color" in res.json()


def test_brand_unknown_returns_404(client):
    assert client.get("/brand/nonexistent").status_code == 404


# ── Health ────────────────────────────────────────────────────────────────────

def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}

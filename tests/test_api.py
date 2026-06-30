"""Integration tests for the Mini Compute Console API."""
import pytest
from tests.conftest import HEADERS, ADMIN_HEADERS, TEST_HEADERS, TENANT_HEADERS


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


# ── Templates ─────────────────────────────────────────────────────────────────

def test_create_template(client):
    res = client.post("/templates", json={"name": "A100 fast", "priority": "high", "budget_limit": 1.0}, headers=TEST_HEADERS)
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "A100 fast"
    assert data["budget_limit"] == 1.0
    assert "id" in data


def test_list_templates(client):
    client.post("/templates", json={"name": "tpl-list"}, headers=TEST_HEADERS)
    res = client.get("/templates", headers=TEST_HEADERS)
    assert res.status_code == 200
    assert any(t["name"] == "tpl-list" for t in res.json())


def test_get_template(client):
    r = client.post("/templates", json={"name": "tpl-get"}, headers=TEST_HEADERS)
    tid = r.json()["id"]
    res = client.get(f"/templates/{tid}", headers=TEST_HEADERS)
    assert res.status_code == 200
    assert res.json()["id"] == tid


def test_get_template_not_found(client):
    assert client.get("/templates/nope", headers=TEST_HEADERS).status_code == 404


def test_delete_template(client):
    r = client.post("/templates", json={"name": "tpl-del"}, headers=TEST_HEADERS)
    tid = r.json()["id"]
    assert client.delete(f"/templates/{tid}", headers=TEST_HEADERS).status_code == 204
    assert client.get(f"/templates/{tid}", headers=TEST_HEADERS).status_code == 404


# ── Budget ────────────────────────────────────────────────────────────────────

def test_launch_with_budget_limit(client):
    res = client.post("/jobs", json={"priority": "normal", "budget_limit": 99.0}, headers=TEST_HEADERS)
    assert res.status_code == 201
    data = res.json()
    assert data["budget_limit"] == 99.0


def test_launch_from_template(client):
    r = client.post("/templates", json={"name": "tpl-launch", "priority": "high", "budget_limit": 5.0}, headers=TEST_HEADERS)
    tid = r.json()["id"]
    res = client.post("/jobs", json={"template_id": tid}, headers=TEST_HEADERS)
    assert res.status_code == 201


def test_launch_from_missing_template(client):
    res = client.post("/jobs", json={"template_id": "ghost"}, headers=TEST_HEADERS)
    assert res.status_code == 404


# ── Multi-tenant isolation ────────────────────────────────────────────────────

def test_jobs_scoped_to_api_key(client):
    r = client.post("/jobs", json={}, headers=TENANT_HEADERS)
    assert r.status_code == 201
    job_id = r.json()["job_id"]
    # admin-user cannot see tenant-user's job
    jobs = client.get("/jobs", headers=ADMIN_HEADERS).json()
    assert not any(j["job_id"] == job_id for j in jobs)


def test_job_not_accessible_cross_tenant(client):
    r = client.post("/jobs", json={}, headers=TENANT_HEADERS)
    assert r.status_code == 201
    job_id = r.json()["job_id"]
    assert client.get(f"/jobs/{job_id}", headers=ADMIN_HEADERS).status_code == 404


def test_job_owner_field(client):
    r = client.post("/jobs", json={}, headers=TENANT_HEADERS)
    assert r.status_code == 201
    assert r.json()["owner"] == "tenant-user"


# ── Forecast ──────────────────────────────────────────────────────────────────

def test_forecast_endpoint(client):
    r = client.post("/jobs", json={}, headers=TENANT_HEADERS)
    assert r.status_code == 201
    job_id = r.json()["job_id"]
    res = client.get(f"/jobs/{job_id}/forecast", headers=TENANT_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert "estimated_final_cost" in data
    assert "eta_seconds" in data
    assert "burn_rate_per_hour" in data
    assert "budget_breach_prob" in data


def test_forecast_cross_tenant_404(client):
    r = client.post("/jobs", json={}, headers=TENANT_HEADERS)
    assert r.status_code == 201
    job_id = r.json()["job_id"]
    assert client.get(f"/jobs/{job_id}/forecast", headers=ADMIN_HEADERS).status_code == 404


# ── SLA tracker ───────────────────────────────────────────────────────────────

def test_sla_all_providers(client):
    client.get("/providers", headers=TENANT_HEADERS)
    res = client.get("/providers/sla", headers=TENANT_HEADERS)
    assert res.status_code == 200
    assert isinstance(res.json(), dict)


def test_sla_single_provider(client):
    client.get("/providers", headers=TENANT_HEADERS)
    res = client.get("/providers/runpod-a100-us-east/sla", headers=TENANT_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert "sla_pct" in data
    assert "grade" in data
    assert "incidents" in data


def test_sla_unknown_provider(client):
    assert client.get("/providers/ghost/sla", headers=TENANT_HEADERS).status_code == 404


# ── Job report ────────────────────────────────────────────────────────────────

def test_job_report(client):
    r = client.post("/jobs", json={}, headers=TENANT_HEADERS)
    assert r.status_code == 201
    res = client.get(f"/jobs/{r.json()['job_id']}/report", headers=TENANT_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert "efficiency_score" in data
    assert "efficiency_grade" in data
    assert "gpu_util" in data
    assert "recommendation" in data


def test_job_report_cross_tenant_404(client):
    r = client.post("/jobs", json={}, headers=TENANT_HEADERS)
    assert client.get(f"/jobs/{r.json()['job_id']}/report", headers=ADMIN_HEADERS).status_code == 404


# ── Job clone ─────────────────────────────────────────────────────────────────

def test_clone_job(client):
    r = client.post("/jobs", json={"priority": "high"}, headers=TENANT_HEADERS)
    assert r.status_code == 201
    jid = r.json()["job_id"]
    clone = client.post(f"/jobs/{jid}/clone", headers=TENANT_HEADERS)
    assert clone.status_code == 201
    assert clone.json()["job_id"] != jid
    assert clone.json()["priority"] == "high"


def test_clone_cross_tenant_404(client):
    r = client.post("/jobs", json={}, headers=TENANT_HEADERS)
    assert client.post(f"/jobs/{r.json()['job_id']}/clone", headers=ADMIN_HEADERS).status_code == 404


# ── Pagination ────────────────────────────────────────────────────────────────

def test_jobs_pagination_headers(client):
    for _ in range(3):
        client.post("/jobs", json={}, headers=TENANT_HEADERS)
    res = client.get("/jobs?page=1&limit=2", headers=TENANT_HEADERS)
    assert res.status_code == 200
    assert len(res.json()) == 2
    assert res.headers["x-total-count"] == "3"
    assert res.headers["x-total-pages"] == "2"


def test_jobs_pagination_page2(client):
    for _ in range(3):
        client.post("/jobs", json={}, headers=TENANT_HEADERS)
    res = client.get("/jobs?page=2&limit=2", headers=TENANT_HEADERS)
    assert res.status_code == 200
    assert len(res.json()) == 1


# ── Prometheus metrics ────────────────────────────────────────────────────────

def test_metrics_endpoint(client):
    res = client.get("/metrics")
    assert res.status_code == 200
    assert "voltgrid_jobs_total" in res.text
    assert "voltgrid_spend_dollars_total" in res.text
    assert "voltgrid_providers_total" in res.text


# ── System info ───────────────────────────────────────────────────────────────

def test_system_info(client):
    res = client.get("/system/info", headers=TENANT_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert "version" in data
    assert "ws_subscribers" in data
    assert "providers_total" in data


# ── Health ────────────────────────────────────────────────────────────────────

def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}

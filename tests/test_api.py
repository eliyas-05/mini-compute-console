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


# ── Webhooks ──────────────────────────────────────────────────────────────────

def test_register_webhook(client):
    res = client.post("/webhooks", json={
        "url": "https://example.com/hook",
        "events": ["job_complete", "job_cancelled"],
    }, headers=HEADERS)
    assert res.status_code == 201
    data = res.json()
    assert "id" in data
    assert data["url"] == "https://example.com/hook"
    assert "job_complete" in data["events"]
    assert "secret" not in data  # never returned


def test_register_webhook_invalid_event(client):
    res = client.post("/webhooks", json={
        "url": "https://example.com/hook",
        "events": ["job_teleported"],
    }, headers=HEADERS)
    assert res.status_code == 422


def test_register_webhook_missing_url(client):
    res = client.post("/webhooks", json={"events": ["job_complete"]}, headers=HEADERS)
    assert res.status_code == 422


def test_list_webhooks(client):
    client.post("/webhooks", json={"url": "https://a.com", "events": ["job_complete"]}, headers=HEADERS)
    client.post("/webhooks", json={"url": "https://b.com", "events": ["job_cancelled"]}, headers=HEADERS)
    res = client.get("/webhooks", headers=HEADERS)
    assert res.status_code == 200
    assert len(res.json()) == 2


def test_list_webhooks_scoped_to_owner(client):
    client.post("/webhooks", json={"url": "https://demo.com", "events": ["job_complete"]}, headers=HEADERS)
    client.post("/webhooks", json={"url": "https://tenant.com", "events": ["job_complete"]}, headers=TENANT_HEADERS)
    demo_hooks   = client.get("/webhooks", headers=HEADERS).json()
    tenant_hooks = client.get("/webhooks", headers=TENANT_HEADERS).json()
    assert all(h["url"] == "https://demo.com" for h in demo_hooks)
    assert all(h["url"] == "https://tenant.com" for h in tenant_hooks)


def test_get_webhook(client):
    wid = client.post("/webhooks", json={"url": "https://x.com", "events": ["job_complete"]}, headers=HEADERS).json()["id"]
    res = client.get(f"/webhooks/{wid}", headers=HEADERS)
    assert res.status_code == 200
    assert res.json()["id"] == wid


def test_get_webhook_cross_tenant_returns_404(client):
    wid = client.post("/webhooks", json={"url": "https://x.com", "events": ["job_complete"]}, headers=HEADERS).json()["id"]
    assert client.get(f"/webhooks/{wid}", headers=TENANT_HEADERS).status_code == 404


def test_delete_webhook(client):
    wid = client.post("/webhooks", json={"url": "https://x.com", "events": ["job_complete"]}, headers=HEADERS).json()["id"]
    assert client.delete(f"/webhooks/{wid}", headers=HEADERS).status_code == 204
    assert client.get(f"/webhooks/{wid}", headers=HEADERS).status_code == 404


def test_delete_webhook_cross_tenant_returns_404(client):
    wid = client.post("/webhooks", json={"url": "https://x.com", "events": ["job_complete"]}, headers=HEADERS).json()["id"]
    assert client.delete(f"/webhooks/{wid}", headers=TENANT_HEADERS).status_code == 404


# ── X-Request-ID header ───────────────────────────────────────────────────────

def test_response_has_request_id(client):
    res = client.get("/health")
    assert "x-request-id" in res.headers


def test_client_request_id_echoed(client):
    res = client.get("/health", headers={"X-Request-ID": "my-trace-123"})
    assert res.headers["x-request-id"] == "my-trace-123"


# ── Job scheduling ────────────────────────────────────────────────────────────

def test_scheduled_job_starts_in_scheduled_status(client):
    import time
    future_ts = time.time() + 3600  # 1 hour from now
    res = client.post("/jobs", json={"scheduled_at": future_ts}, headers=HEADERS)
    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "scheduled"
    assert data["scheduled_at"] == future_ts


def test_scheduled_job_past_ts_starts_queued(client):
    import time
    past_ts = time.time() - 1
    res = client.post("/jobs", json={"scheduled_at": past_ts}, headers=HEADERS)
    assert res.status_code == 201
    assert res.json()["status"] == "queued"


def test_job_tags_stored_and_returned(client):
    res = client.post("/jobs", json={"tags": {"env": "prod", "team": "ml"}}, headers=HEADERS)
    assert res.status_code == 201
    data = res.json()
    assert data["tags"]["env"] == "prod"
    assert data["tags"]["team"] == "ml"


# ── Job filtering ─────────────────────────────────────────────────────────────

def test_filter_jobs_by_status(client):
    import time
    client.post("/jobs", json={"scheduled_at": time.time() + 3600}, headers=HEADERS)
    client.post("/jobs", json={}, headers=HEADERS)
    scheduled = client.get("/jobs?status=scheduled", headers=HEADERS).json()
    queued    = client.get("/jobs?status=queued",    headers=HEADERS).json()
    assert all(j["status"] == "scheduled" for j in scheduled)
    assert all(j["status"] == "queued"    for j in queued)


def test_filter_jobs_by_tag(client):
    client.post("/jobs", json={"tags": {"env": "prod"}}, headers=HEADERS)
    client.post("/jobs", json={"tags": {"env": "staging"}}, headers=HEADERS)
    prod = client.get("/jobs?tag=env=prod", headers=HEADERS).json()
    assert len(prod) == 1
    assert prod[0]["tags"]["env"] == "prod"


def test_filter_jobs_by_priority(client):
    client.post("/jobs", json={"priority": "high"}, headers=HEADERS)
    client.post("/jobs", json={"priority": "low"},  headers=HEADERS)
    high_jobs = client.get("/jobs?priority=high", headers=HEADERS).json()
    assert all(j["priority"] == "high" for j in high_jobs)


# ── Bulk launch ───────────────────────────────────────────────────────────────

def test_bulk_launch_returns_array(client):
    res = client.post("/jobs/bulk", json={"jobs": [{}, {}]}, headers=HEADERS)
    assert res.status_code == 201
    data = res.json()
    assert len(data) == 2
    assert all(r["ok"] for r in data)


def test_bulk_launch_partial_failure(client):
    res = client.post("/jobs/bulk", json={
        "jobs": [
            {},
            {"provider_id": "nonexistent-provider-xyz"},
        ]
    }, headers=HEADERS)
    assert res.status_code == 201
    data = res.json()
    assert data[0]["ok"] is True
    assert data[1]["ok"] is False
    assert "error" in data[1]


def test_bulk_launch_max_5(client):
    res = client.post("/jobs/bulk", json={"jobs": [{}, {}, {}, {}, {}, {}]}, headers=HEADERS)
    assert res.status_code == 422  # validation error — too many


# ── Preemption ────────────────────────────────────────────────────────────────

def test_preempt_queued_job(client):
    original = client.post("/jobs", json={}, headers=HEADERS).json()
    res = client.post(f"/jobs/{original['job_id']}/preempt", headers=HEADERS)
    assert res.status_code == 201
    new_job = res.json()
    assert new_job["job_id"] != original["job_id"]
    original_status = client.get(f"/jobs/{original['job_id']}", headers=HEADERS).json()["status"]
    assert original_status == "cancelled"


def test_preempt_completed_job_returns_400(client):
    import time, job_engine
    job = client.post("/jobs", json={}, headers=HEADERS).json()
    jid = job["job_id"]
    job_engine._jobs[jid]["status"] = "complete"
    res = client.post(f"/jobs/{jid}/preempt", headers=HEADERS)
    assert res.status_code == 400


# ── Provider recommendation ───────────────────────────────────────────────────

def test_recommend_returns_ranked_list(client):
    res = client.get("/providers/recommend", headers=HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert "recommendations" in data
    assert len(data["recommendations"]) > 0
    assert data["recommendations"][0]["fit"] == "best"


def test_recommend_high_priority_sorted_by_uptime(client):
    res = client.get("/providers/recommend?priority=high", headers=HEADERS).json()
    uptimes = [r["uptime_pct"] for r in res["recommendations"]]
    assert uptimes == sorted(uptimes, reverse=True)


def test_recommend_normal_priority_sorted_by_spot(client):
    res = client.get("/providers/recommend?priority=normal", headers=HEADERS).json()
    prices = [r["spot_price"] for r in res["recommendations"]]
    assert prices == sorted(prices)


def test_recommend_filters_by_budget(client):
    res = client.get("/providers/recommend?priority=normal&budget_limit=0.0001", headers=HEADERS).json()
    # Budget too small for any 90s job — no providers should qualify
    assert res["providers_available"] == 0


# ── Admin bulk cancel ─────────────────────────────────────────────────────────

def test_admin_bulk_cancel_queued(client):
    client.post("/jobs", json={}, headers=HEADERS)
    client.post("/jobs", json={}, headers=HEADERS)
    res = client.delete("/admin/jobs/bulk?status=queued", headers=ADMIN_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert data["cancelled"] >= 2


def test_admin_bulk_cancel_non_admin_returns_403(client):
    res = client.delete("/admin/jobs/bulk?status=queued", headers=HEADERS)
    assert res.status_code == 403


def test_admin_bulk_cancel_invalid_status(client):
    res = client.delete("/admin/jobs/bulk?status=complete", headers=ADMIN_HEADERS)
    assert res.status_code == 400


# ── Job dependencies ──────────────────────────────────────────────────────────

def test_job_with_dependency_starts_waiting(client):
    parent = client.post("/jobs", json={}, headers=HEADERS).json()
    child  = client.post("/jobs", json={"depends_on": parent["job_id"]}, headers=HEADERS).json()
    assert child["status"] == "waiting"
    assert child["depends_on"] == parent["job_id"]


def test_job_dependency_cross_tenant_rejected(client):
    parent = client.post("/jobs", json={}, headers=TENANT_HEADERS).json()
    res    = client.post("/jobs", json={"depends_on": parent["job_id"]}, headers=HEADERS)
    assert res.status_code == 400  # can't depend on another tenant's job


def test_job_dependency_nonexistent_rejected(client):
    res = client.post("/jobs", json={"depends_on": "notreal1"}, headers=HEADERS)
    assert res.status_code == 400


def test_waiting_job_released_when_parent_completes(client):
    import job_engine
    parent = client.post("/jobs", json={}, headers=HEADERS).json()
    child  = client.post("/jobs", json={"depends_on": parent["job_id"]}, headers=HEADERS).json()
    assert child["status"] == "waiting"
    # Mark parent complete
    job_engine._jobs[parent["job_id"]]["status"] = "complete"
    # Poll child — should transition to queued
    updated = client.get(f"/jobs/{child['job_id']}", headers=HEADERS).json()
    assert updated["status"] == "queued"


# ── Spend alerts ──────────────────────────────────────────────────────────────

def test_create_alert(client):
    res = client.post("/alerts", json={"threshold_usd": 1.0, "label": "Test cap"}, headers=HEADERS)
    assert res.status_code == 201
    data = res.json()
    assert data["threshold_usd"] == 1.0
    assert data["fired"] is False


def test_create_alert_requires_threshold(client):
    res = client.post("/alerts", json={"label": "no threshold"}, headers=HEADERS)
    assert res.status_code == 422


def test_create_alert_threshold_must_be_positive(client):
    res = client.post("/alerts", json={"threshold_usd": -1.0}, headers=HEADERS)
    assert res.status_code == 422


def test_list_alerts(client):
    client.post("/alerts", json={"threshold_usd": 1.0}, headers=HEADERS)
    client.post("/alerts", json={"threshold_usd": 2.0}, headers=HEADERS)
    res = client.get("/alerts", headers=HEADERS)
    assert res.status_code == 200
    assert len(res.json()) == 2


def test_alerts_scoped_to_owner(client):
    client.post("/alerts", json={"threshold_usd": 1.0}, headers=HEADERS)
    client.post("/alerts", json={"threshold_usd": 1.0}, headers=TENANT_HEADERS)
    demo_alerts   = client.get("/alerts", headers=HEADERS).json()
    tenant_alerts = client.get("/alerts", headers=TENANT_HEADERS).json()
    assert len(demo_alerts) == 1
    assert len(tenant_alerts) == 1


def test_delete_alert(client):
    aid = client.post("/alerts", json={"threshold_usd": 1.0}, headers=HEADERS).json()["id"]
    assert client.delete(f"/alerts/{aid}", headers=HEADERS).status_code == 204
    assert client.get(f"/alerts/{aid}", headers=HEADERS).status_code == 404


def test_reset_alert(client):
    import alerts as _alerts_module
    aid = client.post("/alerts", json={"threshold_usd": 0.0001}, headers=HEADERS).json()["id"]
    _alerts_module._alerts[aid]["fired"] = True
    res = client.patch(f"/alerts/{aid}/reset", headers=HEADERS)
    assert res.status_code == 200
    assert res.json()["fired"] is False


def test_alert_cross_tenant_returns_404(client):
    aid = client.post("/alerts", json={"threshold_usd": 1.0}, headers=HEADERS).json()["id"]
    assert client.get(f"/alerts/{aid}", headers=TENANT_HEADERS).status_code == 404


# ── Timeseries analytics ──────────────────────────────────────────────────────

def test_timeseries_returns_structure(client):
    client.post("/jobs", json={}, headers=HEADERS)
    res = client.get("/analytics/timeseries", headers=HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert "granularity" in data
    assert "buckets" in data
    assert "total_spend" in data


def test_timeseries_hourly_granularity(client):
    client.post("/jobs", json={}, headers=HEADERS)
    res = client.get("/analytics/timeseries?granularity=hour", headers=HEADERS).json()
    assert res["granularity"] == "hour"
    if res["buckets"]:
        assert "T" in res["buckets"][0]["bucket"]  # ISO hour format


def test_timeseries_daily_granularity(client):
    client.post("/jobs", json={}, headers=HEADERS)
    res = client.get("/analytics/timeseries?granularity=day", headers=HEADERS).json()
    assert res["granularity"] == "day"


def test_timeseries_invalid_granularity(client):
    res = client.get("/analytics/timeseries?granularity=minute", headers=HEADERS)
    assert res.status_code == 422


def test_timeseries_job_count_matches_launched(client):
    client.post("/jobs", json={}, headers=HEADERS)
    client.post("/jobs", json={}, headers=HEADERS)
    res = client.get("/analytics/timeseries", headers=HEADERS).json()
    assert res["total_jobs"] == 2


# ── Job timeline ──────────────────────────────────────────────────────────────

def test_job_timeline(client):
    job = client.post("/jobs", json={}, headers=HEADERS).json()
    res = client.get(f"/jobs/{job['job_id']}/timeline", headers=HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert data["job_id"] == job["job_id"]
    assert "current_status" in data
    assert "events" in data
    assert isinstance(data["events"], list)


def test_job_timeline_cross_tenant_returns_404(client):
    job = client.post("/jobs", json={}, headers=HEADERS).json()
    assert client.get(f"/jobs/{job['job_id']}/timeline", headers=TENANT_HEADERS).status_code == 404

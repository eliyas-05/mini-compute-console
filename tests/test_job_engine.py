"""Unit tests for job_engine state machine logic."""
import time
import pytest
from job_engine import launch_job, get_job, cancel_job, list_jobs, _jobs, PROVIDERS


@pytest.fixture(autouse=True)
def clear_jobs():
    _jobs.clear()
    yield
    _jobs.clear()


def test_launch_returns_queued_job():
    job = launch_job()
    assert job["status"] == "queued"
    assert job["cost_so_far"] == 0.0
    assert "id" in job


def test_auto_pick_selects_available_provider():
    job = launch_job()
    provider = next(p for p in PROVIDERS if p["id"] == job["provider_id"])
    assert provider["status"] == "available"
    assert provider["uptime_pct"] >= 98.0


def test_auto_pick_normal_selects_available_provider():
    # normal priority picks cheapest spot price, which varies; just assert a valid pick
    job = launch_job(priority="normal")
    candidates = [p for p in PROVIDERS if p["status"] == "available" and p["uptime_pct"] >= 98.0]
    assert any(job["provider_id"] == p["id"] for p in candidates)


def test_auto_pick_low_selects_cheapest_base():
    job = launch_job(priority="low")
    candidates = [p for p in PROVIDERS if p["status"] == "available" and p["uptime_pct"] >= 98.0]
    cheapest = min(candidates, key=lambda p: p["price_per_hour"])
    assert job["provider_id"] == cheapest["id"]


def test_auto_pick_high_selects_best_uptime():
    job = launch_job(priority="high")
    candidates = [p for p in PROVIDERS if p["status"] == "available" and p["uptime_pct"] >= 98.0]
    best_uptime = max(candidates, key=lambda p: p["uptime_pct"])
    assert job["provider_id"] == best_uptime["id"]


def test_launch_specific_provider():
    available = next(p for p in PROVIDERS if p["status"] == "available")
    job = launch_job(available["id"])
    assert job["provider_id"] == available["id"]


def test_launch_unknown_provider_raises():
    with pytest.raises(ValueError, match="not found"):
        launch_job("fake-id")


def test_launch_busy_provider_raises():
    busy = next((p for p in PROVIDERS if p["status"] == "busy"), None)
    if busy:
        with pytest.raises(ValueError, match="not available"):
            launch_job(busy["id"])


def test_get_job_returns_none_for_unknown():
    assert get_job("nonexistent") is None


def test_cost_increases_over_time():
    job = launch_job()
    job_id = job["id"]
    # Manually backdate started_at to simulate elapsed time
    _jobs[job_id]["started_at"] -= 60  # 60 seconds ago
    updated = get_job(job_id)
    assert updated["cost_so_far"] > 0


def test_status_transitions_to_running():
    job = launch_job()
    _jobs[job["id"]]["started_at"] -= 3  # skip past queued window
    updated = get_job(job["id"])
    assert updated["status"] == "running"


def test_status_transitions_to_complete():
    job = launch_job()
    _jobs[job["id"]]["started_at"] -= 120  # past the 90s completion threshold
    updated = get_job(job["id"])
    assert updated["status"] == "complete"


def test_cancel_job():
    job = launch_job()
    cancelled = cancel_job(job["id"])
    assert cancelled["status"] == "cancelled"
    assert any("cancelled" in l.lower() for l in cancelled["_logs"])


def test_cancelled_job_does_not_transition():
    job = launch_job()
    cancel_job(job["id"])
    _jobs[job["id"]]["started_at"] -= 120
    updated = get_job(job["id"])
    assert updated["status"] == "cancelled"


def test_list_jobs():
    launch_job()
    launch_job()
    assert len(list_jobs()) == 2


def test_complete_job_appends_final_log():
    job = launch_job()
    _jobs[job["id"]]["started_at"] -= 120
    updated = get_job(job["id"])
    assert any("complete" in l.lower() for l in updated["_logs"])

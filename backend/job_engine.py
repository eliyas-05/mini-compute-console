import random
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from budget import check_budget, budget_remaining, budget_pct_used
from database import upsert_job, append_log, load_all_jobs, init_db
from logger import info, warn
from mock_data import PROVIDERS
from pubsub import broadcast_sync
from spot_prices import get_spot_price, get_spot_prices
from webhooks import fire_webhooks

_jobs: dict[str, dict] = {}

def _boot():
    init_db()
    for job in load_all_jobs():
        # Mark stale running/queued jobs as complete on restart
        if job["status"] in ("queued", "running"):
            job["status"] = "complete"
        _jobs[job["id"]] = job

_boot()

_JOB_DURATION_SECONDS = 90

_LOG_TEMPLATES = [
    "Initializing CUDA context...",
    "Loading model weights ({step}/{total})...",
    "Allocating GPU memory: {mem}GB",
    "Starting training loop",
    "Training step {step}/{total} — loss: {loss:.4f}",
    "Checkpoint saved to /output/ckpt-{step}.pt",
    "GPU utilization: {util}%",
    "ETA: {eta}s remaining",
    "Validating epoch {epoch}...",
    "Val loss: {loss:.4f} | Val acc: {acc:.2f}%",
    "Gradient norm: {gnorm:.3f}",
    "Learning rate: {lr:.6f}",
    "Batch {step}/{total} complete",
    "Memory allocated: {mem}GB / 80GB",
]


_log_counter = 0

def _make_log_line(elapsed: float) -> str:
    global _log_counter
    _log_counter += 1
    progress = min(elapsed / _JOB_DURATION_SECONDS, 1.0)
    step = int(progress * 500)
    template = _LOG_TEMPLATES[_log_counter % len(_LOG_TEMPLATES)]
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = template.format(
        step=step,
        total=500,
        loss=max(0.01, 2.5 * (1 - progress) + random.uniform(-0.05, 0.05)),
        mem=round(random.uniform(40, 75), 1),
        util=random.randint(92, 99),
        eta=max(0, int(_JOB_DURATION_SECONDS - elapsed)),
        epoch=max(1, int(progress * 10)),
        acc=min(99.9, 60 + progress * 38 + random.uniform(-1, 1)),
        gnorm=random.uniform(0.8, 2.5),
        lr=1e-4 * (0.95 ** int(progress * 20)),
    )
    return f"[{ts}] {line}"


def _get_provider(provider_id: str) -> Optional[dict]:
    return next((p for p in PROVIDERS if p["id"] == provider_id), None)


def _auto_pick_provider(priority: str = "normal") -> Optional[dict]:
    candidates = [
        p for p in PROVIDERS
        if p["status"] == "available" and p["uptime_pct"] >= 98.0
    ]
    if not candidates:
        return None
    # High priority: pick best uptime. Normal/low: pick cheapest spot price.
    if priority == "high":
        return max(candidates, key=lambda p: p["uptime_pct"])
    spot = get_spot_prices() if priority == "normal" else None
    if spot:
        return min(candidates, key=lambda p: spot.get(p["id"], p["price_per_hour"]))
    return min(candidates, key=lambda p: p["price_per_hour"])


_PRIORITY_RANK = {"high": 0, "normal": 1, "low": 2}


_PREEMPTION_THRESHOLD = 1.25  # auto-preempt when spot spikes >25% above launch price


def launch_job(
    provider_id: Optional[str] = None,
    priority: str = "normal",
    budget_limit: Optional[float] = None,
    template_id: Optional[str] = None,
    owner: str = "demo-user",
    scheduled_at: Optional[float] = None,
    tags: Optional[dict] = None,
) -> dict:
    if priority not in _PRIORITY_RANK:
        raise ValueError(f"Invalid priority '{priority}'. Must be high, normal, or low.")

    # For scheduled jobs we defer provider selection until start time
    if scheduled_at and scheduled_at > time.time():
        provider = None
        initial_status = "scheduled"
    else:
        scheduled_at = None
        if provider_id:
            provider = _get_provider(provider_id)
            if not provider:
                raise ValueError(f"Provider '{provider_id}' not found")
            if provider["status"] != "available":
                raise ValueError(f"Provider '{provider_id}' is not available")
        else:
            provider = _auto_pick_provider(priority)
            if not provider:
                raise ValueError("No available providers meet reliability criteria (available + uptime >= 98%)")
        initial_status = "queued"

    now = time.time()
    spot = get_spot_price(provider["id"]) if provider else 0.0
    job = {
        "id": str(uuid.uuid4())[:8],
        "provider_id": provider["id"] if provider else provider_id or None,
        "provider_name": provider["name"] if provider else None,
        "gpu_type": provider["gpu_type"] if provider else None,
        "region": provider["region"] if provider else None,
        "price_per_hour": spot,
        "base_price_per_hour": provider["price_per_hour"] if provider else 0.0,
        "launch_price_per_hour": spot,  # used to detect spot spikes for preemption
        "priority": priority,
        "status": initial_status,
        "started_at": now,
        "scheduled_at": scheduled_at,
        "cost_so_far": 0.0,
        "projected_cost": None,
        "budget_limit": budget_limit,
        "template_id": template_id,
        "tags": tags or {},
        "owner": owner,
        "created_at": now,
        "gpu_util": 0,
        "_gpu_samples": [],
        "_logs": [],
        "_last_log_tick": now,
        "_retry_count": 0,
        "_rerouted_from": None,
        "_preempted": False,
    }
    _jobs[job["id"]] = job
    upsert_job(job)
    info("job.launched", job_id=job["id"], provider=job["provider_id"],
         priority=priority, budget_limit=budget_limit, owner=owner,
         scheduled_at=scheduled_at)
    broadcast_sync({"type": "job_launched", "job_id": job["id"],
                    "provider": job["provider_id"], "owner": owner, "status": initial_status})
    return job


def get_job(job_id: str) -> Optional[dict]:
    job = _jobs.get(job_id)
    if not job:
        return None

    now = time.time()
    elapsed = now - job["started_at"]

    if job["status"] in ("cancelled", "complete"):
        if job["status"] == "cancelled":
            job["cost_so_far"] = round(elapsed / 3600 * job["price_per_hour"], 6)
        return job

    # Scheduled → queued when the window opens
    if job["status"] == "scheduled" and now >= (job.get("scheduled_at") or 0):
        provider = _auto_pick_provider(job.get("priority", "normal"))
        if provider:
            spot = get_spot_price(provider["id"])
            job["provider_id"]         = provider["id"]
            job["provider_name"]       = provider["name"]
            job["gpu_type"]            = provider["gpu_type"]
            job["region"]              = provider["region"]
            job["price_per_hour"]      = spot
            job["base_price_per_hour"] = provider["price_per_hour"]
            job["launch_price_per_hour"] = spot
            job["started_at"]          = now
        job["status"] = "queued"
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        job["_logs"].append(f"[{ts}] Scheduled window reached — entering queue on {job['provider_name']}.")
        broadcast_sync({"type": "job_queued", "job_id": job_id,
                        "provider": job["provider_id"], "owner": job.get("owner")})

    if job["status"] == "queued" and elapsed >= 2:
        job["status"] = "running"
        broadcast_sync({"type": "job_running", "job_id": job_id,
                        "provider": job["provider_id"], "owner": job.get("owner")})

    if job["status"] == "running" and elapsed >= _JOB_DURATION_SECONDS:
        job["status"] = "complete"
        broadcast_sync({"type": "job_complete", "job_id": job_id,
                        "cost": job["cost_so_far"], "owner": job.get("owner")})
        fire_webhooks("job_complete", job.get("owner", ""), {
            "job_id": job_id, "provider": job["provider_id"],
            "cost": job["cost_so_far"], "gpu_type": job["gpu_type"],
        })

    job["cost_so_far"] = round(elapsed / 3600 * job["price_per_hour"], 6)

    # Cost projection: estimated total at completion
    if job["status"] in ("queued", "running"):
        job["projected_cost"] = round(_JOB_DURATION_SECONDS / 3600 * job["price_per_hour"], 6)
    elif job["status"] == "complete":
        job["projected_cost"] = job["cost_so_far"]

    # Retry: if still queued and provider went busy, re-route to next best
    if job["status"] == "queued" and job["_retry_count"] < 3:
        provider = _get_provider(job["provider_id"])
        if provider and provider["status"] == "busy":
            next_provider = _auto_pick_provider(job.get("priority", "normal"))
            if next_provider and next_provider["id"] != job["provider_id"]:
                ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
                job["_logs"].append(
                    f"[{ts}] Provider busy — re-routing to {next_provider['name']}"
                )
                job["_rerouted_from"] = job["provider_id"]
                job["provider_id"]    = next_provider["id"]
                job["provider_name"]  = next_provider["name"]
                job["gpu_type"]       = next_provider["gpu_type"]
                job["region"]         = next_provider["region"]
                job["price_per_hour"] = get_spot_price(next_provider["id"])
                job["base_price_per_hour"] = next_provider["price_per_hour"]
                job["_retry_count"] += 1

    # Spot preemption — if spot price spiked >25% above launch price, cancel and re-queue
    if job["status"] == "running" and not job.get("_preempted"):
        current_spot = get_spot_price(job["provider_id"])
        launch_price = job.get("launch_price_per_hour", job["price_per_hour"])
        if launch_price > 0 and current_spot > launch_price * _PREEMPTION_THRESHOLD:
            job["_preempted"] = True
            ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
            spike_pct = round((current_spot / launch_price - 1) * 100, 1)
            line = (f"[{ts}] Spot price spiked +{spike_pct}% (${current_spot:.4f}/hr vs "
                    f"${launch_price:.4f}/hr at launch) — job preempted.")
            job["_logs"].append(line)
            append_log(job["id"], line)
            job["status"] = "cancelled"
            job["preemption_spike_pct"] = spike_pct
            upsert_job(job)
            broadcast_sync({"type": "job_preempted", "job_id": job_id,
                            "reason": "spot_spike", "spike_pct": spike_pct,
                            "owner": job.get("owner")})
            fire_webhooks("job_cancelled", job.get("owner", ""), {
                "job_id": job_id, "reason": "spot_preemption",
                "spike_pct": spike_pct, "cost": job["cost_so_far"],
            })
            return job

    # GPU utilization sampling while running
    if job["status"] == "running":
        util = random.randint(88, 99)
        job["gpu_util"] = util
        samples = job["_gpu_samples"]
        samples.append(util)
        if len(samples) > 20:
            samples.pop(0)

    # Append one fake log line per poll while running (max once per 3 s)
    if job["status"] == "running" and now - job["_last_log_tick"] >= 3:
        line = _make_log_line(elapsed)
        job["_logs"].append(line)
        append_log(job["id"], line)
        job["_last_log_tick"] = now
        upsert_job(job)

    # Budget guardrail — auto-cancel if cost exceeds limit
    if check_budget(job):
        job["status"] = "cancelled"
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        line = f"[{ts}] Budget limit ${job['budget_limit']:.4f} reached — job auto-cancelled."
        job["_logs"].append(line)
        append_log(job["id"], line)
        upsert_job(job)
        broadcast_sync({"type": "job_cancelled", "job_id": job_id,
                        "reason": "budget", "owner": job.get("owner")})
        fire_webhooks("job_cancelled", job.get("owner", ""), {
            "job_id": job_id, "reason": "budget",
            "cost": job["cost_so_far"], "budget_limit": job["budget_limit"],
        })

    if job["status"] == "complete" and not any("complete" in l for l in job["_logs"]):
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        line = f"[{ts}] Job complete. Final cost: ${job['cost_so_far']:.4f}"
        job["_logs"].append(line)
        append_log(job["id"], line)
        upsert_job(job)

    # Add budget metadata to job for API consumers
    job["budget_remaining"] = budget_remaining(job)
    job["budget_pct_used"]  = budget_pct_used(job)

    return job


def cancel_job(job_id: str) -> Optional[dict]:
    job = _jobs.get(job_id)
    if not job:
        return None
    if job["status"] in ("complete", "cancelled"):
        return job
    job["status"] = "cancelled"
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    job["_logs"].append(f"[{ts}] Job cancelled by user.")
    return get_job(job_id)


def get_logs(job_id: str, owner: Optional[str] = None) -> Optional[list[str]]:
    job = get_job(job_id)
    if not job:
        return None
    if owner and job.get("owner") != owner:
        return None
    return list(job["_logs"])


def list_jobs(owner: Optional[str] = None) -> list[dict]:
    jobs = [get_job(jid) for jid in list(_jobs.keys())]
    if owner:
        jobs = [j for j in jobs if j and j.get("owner") == owner]
    return [j for j in jobs if j]


def get_job_for_owner(job_id: str, owner: str) -> Optional[dict]:
    job = get_job(job_id)
    if not job:
        return None
    if job.get("owner") != owner:
        return None
    return job

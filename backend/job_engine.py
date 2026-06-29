import random
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from mock_data import PROVIDERS

_jobs: dict[str, dict] = {}

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


def _make_log_line(elapsed: float) -> str:
    progress = min(elapsed / _JOB_DURATION_SECONDS, 1.0)
    step = int(progress * 500)
    template = _LOG_TEMPLATES[int(elapsed * 7) % len(_LOG_TEMPLATES)]
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


def _auto_pick_provider() -> Optional[dict]:
    candidates = [
        p for p in PROVIDERS
        if p["status"] == "available" and p["uptime_pct"] >= 98.0
    ]
    return min(candidates, key=lambda p: p["price_per_hour"]) if candidates else None


def launch_job(provider_id: Optional[str] = None) -> dict:
    if provider_id:
        provider = _get_provider(provider_id)
        if not provider:
            raise ValueError(f"Provider '{provider_id}' not found")
        if provider["status"] != "available":
            raise ValueError(f"Provider '{provider_id}' is not available")
    else:
        provider = _auto_pick_provider()
        if not provider:
            raise ValueError("No available providers meet reliability criteria (available + uptime >= 98%)")

    now = time.time()
    job = {
        "id": str(uuid.uuid4())[:8],
        "provider_id": provider["id"],
        "status": "queued",
        "started_at": now,
        "cost_so_far": 0.0,
        # internal fields, stripped before API responses
        "_price_per_hour": provider["price_per_hour"],
        "_logs": [],
        "_last_log_tick": now,
    }
    _jobs[job["id"]] = job
    return job


def get_job(job_id: str) -> Optional[dict]:
    job = _jobs.get(job_id)
    if not job:
        return None

    now = time.time()
    elapsed = now - job["started_at"]

    if job["status"] == "queued" and elapsed >= 2:
        job["status"] = "running"

    if job["status"] == "running" and elapsed >= _JOB_DURATION_SECONDS:
        job["status"] = "complete"

    job["cost_so_far"] = round(elapsed / 3600 * job["_price_per_hour"], 6)

    # Append one fake log line per poll while running (max once per 3 s)
    if job["status"] == "running" and now - job["_last_log_tick"] >= 3:
        job["_logs"].append(_make_log_line(elapsed))
        job["_last_log_tick"] = now

    if job["status"] == "complete" and not any("complete" in l for l in job["_logs"]):
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        job["_logs"].append(f"[{ts}] Job complete. Final cost: ${job['cost_so_far']:.4f}")

    return job


def get_logs(job_id: str) -> Optional[list[str]]:
    job = get_job(job_id)
    return list(job["_logs"]) if job else None

import asyncio
import json
import os

from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from auth import verify_api_key
from audit_log import log_action, get_audit_log
from analytics import compute_analytics
from job_engine import get_job, get_logs, launch_job, cancel_job, list_jobs
from mock_data import PROVIDERS
from models import LaunchRequest, JobResponse, LogsResponse, AnalyticsResponse

app = FastAPI(
    title="Mini Compute Console",
    version="0.2.0",
    description="Scaled-down GPU compute marketplace API with job routing, live streaming, and cost analytics.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_BRANDS_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend", "brands")


# ── Providers ─────────────────────────────────────────────────────────────────

@app.get("/providers", summary="List all GPU providers")
def list_providers(user: str = Depends(verify_api_key)):
    return PROVIDERS


@app.get("/providers/{provider_id}", summary="Get a single provider")
def get_provider(provider_id: str, user: str = Depends(verify_api_key)):
    provider = next((p for p in PROVIDERS if p["id"] == provider_id), None)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return provider


# ── Jobs ──────────────────────────────────────────────────────────────────────

@app.get("/jobs", summary="List all jobs")
def get_jobs(user: str = Depends(verify_api_key)):
    return [_job_view(j) for j in list_jobs()]


@app.post("/jobs", status_code=201, response_model=JobResponse, summary="Launch a job")
def create_job(body: LaunchRequest, user: str = Depends(verify_api_key)):
    try:
        job = launch_job(body.provider_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    log_action(user, job["provider_id"], job["id"], action="launch")
    return _job_view(job)


@app.get("/jobs/{job_id}", response_model=JobResponse, summary="Get job status and running cost")
def job_status(job_id: str, user: str = Depends(verify_api_key)):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_view(job)


@app.delete("/jobs/{job_id}", summary="Cancel a running job")
def cancel(job_id: str, user: str = Depends(verify_api_key)):
    job = cancel_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    log_action(user, job["provider_id"], job_id, action="cancel")
    return _job_view(job)


@app.get("/jobs/{job_id}/logs", response_model=LogsResponse, summary="Get job log lines")
def job_logs(job_id: str, user: str = Depends(verify_api_key)):
    logs = get_logs(job_id)
    if logs is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job_id": job_id, "logs": logs}


# ── WebSocket: live log stream ─────────────────────────────────────────────────

@app.websocket("/ws/jobs/{job_id}/logs")
async def ws_job_logs(websocket: WebSocket, job_id: str):
    """
    Stream log lines in real time. Sends each new line as a JSON string.
    Closes automatically when the job reaches complete or cancelled.
    """
    await websocket.accept()
    sent = 0
    try:
        while True:
            job = get_job(job_id)
            if not job:
                await websocket.send_json({"error": "Job not found"})
                break

            logs = job["_logs"]
            for line in logs[sent:]:
                await websocket.send_json({"line": line})
            sent = len(logs)

            if job["status"] in ("complete", "cancelled"):
                await websocket.send_json({"status": job["status"], "cost": job["cost_so_far"]})
                break

            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass


# ── Analytics ─────────────────────────────────────────────────────────────────

@app.get("/analytics", summary="Aggregate cost and usage stats")
def analytics(user: str = Depends(verify_api_key)):
    return compute_analytics()


# ── Brand ─────────────────────────────────────────────────────────────────────

@app.get("/brand/{brand_name}", summary="Get brand theme config")
def get_brand(brand_name: str):
    safe_name = os.path.basename(brand_name)
    path = os.path.join(_BRANDS_DIR, f"{safe_name}.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Brand '{brand_name}' not found")
    with open(path) as f:
        return json.load(f)


# ── Admin ─────────────────────────────────────────────────────────────────────

@app.get("/admin/audit", summary="Audit log (admin only)")
def audit_log(user: str = Depends(verify_api_key)):
    if user != "admin-user":
        raise HTTPException(status_code=403, detail="Admin only")
    return get_audit_log()


@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _job_view(job: dict) -> dict:
    return {
        "job_id": job["id"],
        "provider_id": job["provider_id"],
        "provider_name": job["provider_name"],
        "gpu_type": job["gpu_type"],
        "region": job["region"],
        "price_per_hour": job["price_per_hour"],
        "status": job["status"],
        "started_at": job["started_at"],
        "cost_so_far": job["cost_so_far"],
    }

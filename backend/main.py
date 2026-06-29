import json
import os
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from auth import verify_api_key
from audit_log import log_job_launch, get_audit_log
from job_engine import get_job, get_logs, launch_job
from mock_data import PROVIDERS

app = FastAPI(title="Mini Compute Console", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_BRANDS_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend", "brands")


class LaunchRequest(BaseModel):
    provider_id: Optional[str] = None


@app.get("/providers")
def list_providers(user: str = Depends(verify_api_key)):
    return PROVIDERS


@app.post("/jobs", status_code=201)
def create_job(body: LaunchRequest, user: str = Depends(verify_api_key)):
    try:
        job = launch_job(body.provider_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    log_job_launch(user, job["provider_id"], job["id"])
    return _job_view(job)


@app.get("/jobs/{job_id}")
def job_status(job_id: str, user: str = Depends(verify_api_key)):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_view(job)


@app.get("/jobs/{job_id}/logs")
def job_logs(job_id: str, user: str = Depends(verify_api_key)):
    logs = get_logs(job_id)
    if logs is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job_id": job_id, "logs": logs}


@app.get("/brand/{brand_name}")
def get_brand(brand_name: str):
    safe_name = os.path.basename(brand_name)
    path = os.path.join(_BRANDS_DIR, f"{safe_name}.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Brand '{brand_name}' not found")
    with open(path) as f:
        return json.load(f)


@app.get("/admin/audit")
def audit_log(user: str = Depends(verify_api_key)):
    if user != "admin-user":
        raise HTTPException(status_code=403, detail="Admin only")
    return get_audit_log()


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

from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from job_engine import get_job, get_logs, launch_job
from mock_data import PROVIDERS

app = FastAPI(title="Mini Compute Console", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class LaunchRequest(BaseModel):
    provider_id: Optional[str] = None


@app.get("/providers")
def list_providers():
    return PROVIDERS


@app.post("/jobs", status_code=201)
def create_job(body: LaunchRequest):
    try:
        job = launch_job(body.provider_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _job_view(job)


@app.get("/jobs/{job_id}")
def job_status(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_view(job)


@app.get("/jobs/{job_id}/logs")
def job_logs(job_id: str):
    logs = get_logs(job_id)
    if logs is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job_id": job_id, "logs": logs}


def _job_view(job: dict) -> dict:
    return {
        "job_id": job["id"],
        "provider_id": job["provider_id"],
        "status": job["status"],
        "started_at": job["started_at"],
        "cost_so_far": job["cost_so_far"],
    }

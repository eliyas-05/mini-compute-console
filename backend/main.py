import asyncio
import json
import os

from fastapi import FastAPI, Depends, HTTPException, Header, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from auth import verify_api_key, get_rate_info
from audit_log import log_action, get_audit_log
from analytics import compute_analytics
from health_score import score_provider, score_all_providers
from job_engine import get_job, get_logs, launch_job, cancel_job, list_jobs
import logger as L
from mock_data import PROVIDERS
from models import LaunchRequest, JobResponse, LogsResponse, AnalyticsResponse, TemplateRequest, TemplateResponse
from spot_prices import get_spot_prices, price_trend
from templates import create_template, get_all_templates, get_one_template, remove_template

app = FastAPI(
    title="Mini Compute Console",
    version="0.4.0",
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


@app.get("/providers/health", summary="Health scores for all providers")
def all_health_scores(user: str = Depends(verify_api_key)):
    return score_all_providers()


@app.get("/providers/{provider_id}/health", summary="Health score for a single provider")
def provider_health(provider_id: str, user: str = Depends(verify_api_key)):
    provider = next((p for p in PROVIDERS if p["id"] == provider_id), None)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return {"provider_id": provider_id, **score_provider(provider)}


@app.get("/spot-prices", summary="Live spot prices for all providers")
def spot_prices(user: str = Depends(verify_api_key)):
    from mock_data import PROVIDERS as _P
    prices = get_spot_prices()
    return [
        {
            "provider_id": p["id"],
            "name": p["name"],
            "base_price": p["price_per_hour"],
            "spot_price": prices.get(p["id"], p["price_per_hour"]),
            "trend": price_trend(p["id"]),
        }
        for p in _P
    ]


# ── Jobs ──────────────────────────────────────────────────────────────────────

@app.get("/jobs", summary="List all jobs")
def get_jobs(user: str = Depends(verify_api_key)):
    return [_job_view(j) for j in list_jobs()]


@app.post("/jobs", status_code=201, response_model=JobResponse, summary="Launch a job")
def create_job(body: LaunchRequest, user: str = Depends(verify_api_key)):
    kwargs = {
        "provider_id": body.provider_id,
        "priority": body.priority,
        "budget_limit": body.budget_limit,
        "template_id": body.template_id,
    }
    # If a template is given, fill in missing fields from it
    if body.template_id:
        tmpl = get_one_template(body.template_id)
        if not tmpl:
            raise HTTPException(status_code=404, detail="Template not found")
        if not body.provider_id:
            kwargs["provider_id"] = tmpl.get("provider_id")
        if body.budget_limit is None:
            kwargs["budget_limit"] = tmpl.get("budget_limit")
    try:
        job = launch_job(**kwargs)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    log_action(user, job["provider_id"], job["id"], action="launch")
    L.info("api.job_launched", user=user, job_id=job["id"],
           provider=job["provider_id"], budget_limit=body.budget_limit)
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
    L.info("api.job_cancelled", user=user, job_id=job_id)
    return _job_view(job)


# ── Templates ─────────────────────────────────────────────────────────────────

@app.get("/templates", response_model=list[TemplateResponse], summary="List job templates")
def list_templates_route(user: str = Depends(verify_api_key)):
    return get_all_templates()


@app.post("/templates", status_code=201, response_model=TemplateResponse, summary="Save a job template")
def create_template_route(body: TemplateRequest, user: str = Depends(verify_api_key)):
    tmpl = create_template(
        name=body.name,
        description=body.description,
        provider_id=body.provider_id,
        priority=body.priority,
        budget_limit=body.budget_limit,
    )
    L.info("api.template_created", user=user, template_id=tmpl["id"], name=tmpl["name"])
    return tmpl


@app.get("/templates/{template_id}", response_model=TemplateResponse, summary="Get a template")
def get_template_route(template_id: str, user: str = Depends(verify_api_key)):
    tmpl = get_one_template(template_id)
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")
    return tmpl


@app.delete("/templates/{template_id}", status_code=204, summary="Delete a template")
def delete_template_route(template_id: str, user: str = Depends(verify_api_key)):
    if not get_one_template(template_id):
        raise HTTPException(status_code=404, detail="Template not found")
    remove_template(template_id)
    L.info("api.template_deleted", user=user, template_id=template_id)


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

            # Stream live GPU utilization and cost
            if job["status"] == "running":
                await websocket.send_json({
                    "util": job.get("gpu_util", 0),
                    "gpu_samples": job.get("_gpu_samples", []),
                    "cost": job["cost_so_far"],
                    "rerouted_from": job.get("_rerouted_from"),
                })

            if job["status"] in ("complete", "cancelled"):
                await websocket.send_json({
                    "status": job["status"],
                    "cost": job["cost_so_far"],
                    "retry_count": job.get("_retry_count", 0),
                })
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


@app.get("/rate-limit", summary="Current rate limit status for your API key")
def rate_limit_status(user: str = Depends(verify_api_key), x_api_key: str = Header(default=None)):
    return get_rate_info(x_api_key)


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
        "base_price_per_hour": job.get("base_price_per_hour", job["price_per_hour"]),
        "priority": job.get("priority", "normal"),
        "status": job["status"],
        "started_at": job["started_at"],
        "cost_so_far": job["cost_so_far"],
        "projected_cost": job.get("projected_cost"),
        "budget_limit": job.get("budget_limit"),
        "budget_remaining": job.get("budget_remaining"),
        "budget_pct_used": job.get("budget_pct_used"),
        "gpu_util": job.get("gpu_util", 0),
        "rerouted_from": job.get("_rerouted_from"),
        "retry_count": job.get("_retry_count", 0),
    }

from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field


class Provider(BaseModel):
    id: str
    name: str
    region: str
    gpu_type: str
    price_per_hour: float
    uptime_pct: float
    status: Literal["available", "busy"]


class LaunchRequest(BaseModel):
    provider_id: Optional[str] = Field(
        default=None,
        description="Leave blank to auto-select based on priority.",
    )
    priority: Literal["high", "normal", "low"] = Field(
        default="normal",
        description="high=best uptime, normal=cheapest spot, low=cheapest spot.",
    )


class SpotPrice(BaseModel):
    provider_id: str
    spot_price: float
    base_price: float
    trend: Literal["up", "down", "flat"]


class JobResponse(BaseModel):
    job_id: str
    provider_id: str
    provider_name: str
    gpu_type: str
    region: str
    price_per_hour: float
    base_price_per_hour: float
    priority: Literal["high", "normal", "low"]
    status: Literal["queued", "running", "complete", "cancelled"]
    started_at: float
    cost_so_far: float
    projected_cost: Optional[float]


class LogsResponse(BaseModel):
    job_id: str
    logs: list[str]


class AnalyticsResponse(BaseModel):
    total_jobs: int
    completed_jobs: int
    cancelled_jobs: int
    running_jobs: int
    total_spend: float
    avg_cost_per_job: float
    cheapest_provider: Optional[str]
    most_used_provider: Optional[str]
    provider_breakdown: dict[str, ProviderStats]


class ProviderStats(BaseModel):
    jobs: int
    total_spend: float


AnalyticsResponse.model_rebuild()


class AuditEntry(BaseModel):
    timestamp: str
    user: str
    provider_id: str
    job_id: str
    action: Literal["launch", "cancel"] = "launch"

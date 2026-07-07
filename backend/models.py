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
    budget_limit: Optional[float] = Field(
        default=None,
        description="Auto-cancel when cost_so_far reaches this USD amount.",
        gt=0,
    )
    template_id: Optional[str] = Field(
        default=None,
        description="Pre-fill settings from a saved template (overridden by explicit fields).",
    )
    scheduled_at: Optional[float] = Field(
        default=None,
        description="Unix timestamp (seconds). Job stays in 'scheduled' status until this time.",
    )
    tags: Optional[dict] = Field(
        default=None,
        description="Arbitrary key-value metadata attached to the job.",
    )
    depends_on: Optional[str] = Field(
        default=None,
        description="Job ID that must complete before this job starts. Creates a 'waiting' status until the dependency finishes.",
    )
    max_retries: int = Field(
        default=0,
        ge=0,
        le=5,
        description="Max number of automatic relaunches if the job is spot-preempted. 0 = no auto-retry.",
    )


class BulkLaunchRequest(BaseModel):
    jobs: list[LaunchRequest] = Field(
        ...,
        description="List of job launch configs. Max 5.",
        min_length=1,
        max_length=5,
    )


class TemplateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    description: str = Field(default="")
    provider_id: Optional[str] = None
    priority: Literal["high", "normal", "low"] = "normal"
    budget_limit: Optional[float] = Field(default=None, gt=0)


class TemplateResponse(BaseModel):
    id: str
    name: str
    description: str
    provider_id: Optional[str]
    priority: Literal["high", "normal", "low"]
    budget_limit: Optional[float]
    created_at: float


class SpotPrice(BaseModel):
    provider_id: str
    spot_price: float
    base_price: float
    trend: Literal["up", "down", "flat"]


class JobResponse(BaseModel):
    job_id: str
    provider_id: Optional[str] = None
    provider_name: Optional[str] = None
    gpu_type: Optional[str] = None
    region: Optional[str] = None
    price_per_hour: float
    base_price_per_hour: float
    priority: Literal["high", "normal", "low"]
    status: Literal["queued", "running", "complete", "cancelled", "scheduled", "waiting"]
    started_at: float
    cost_so_far: float
    projected_cost: Optional[float]
    budget_limit: Optional[float] = None
    budget_remaining: Optional[float] = None
    budget_pct_used: Optional[float] = None
    gpu_util: int = 0
    rerouted_from: Optional[str] = None
    retry_count: int = 0
    preempted: bool = False
    preemption_spike_pct: Optional[float] = None
    scheduled_at: Optional[float] = None
    tags: dict = {}
    depends_on: Optional[str] = None
    max_retries: int = 0
    retry_generation: int = 0
    parent_job_id: Optional[str] = None
    owner: str = "demo-user"


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

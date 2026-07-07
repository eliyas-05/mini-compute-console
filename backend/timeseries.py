"""
Timeseries analytics.

Groups completed and running jobs into time buckets (hour or day) and
returns per-bucket spend, job count, and avg GPU utilisation. The frontend
can feed this directly into a chart without any client-side aggregation.
"""

import time
from typing import Literal


def _bucket_key(ts: float, granularity: str) -> str:
    import datetime
    dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
    if granularity == "hour":
        return dt.strftime("%Y-%m-%dT%H:00Z")
    else:  # day
        return dt.strftime("%Y-%m-%dZ")


def compute_timeseries(
    jobs: list[dict],
    granularity: Literal["hour", "day"] = "hour",
    from_ts: float = 0,
    to_ts: float = 0,
) -> dict:
    now = time.time()
    if not to_ts:
        to_ts = now
    if not from_ts:
        # Default: last 24 hours for hourly, last 30 days for daily
        from_ts = now - (86400 if granularity == "hour" else 86400 * 30)

    # Only include jobs created in window
    window_jobs = [j for j in jobs if from_ts <= j.get("created_at", j["started_at"]) <= to_ts]

    buckets: dict[str, dict] = {}

    for job in window_jobs:
        key = _bucket_key(job.get("created_at", job["started_at"]), granularity)
        if key not in buckets:
            buckets[key] = {
                "bucket": key,
                "jobs": 0,
                "spend": 0.0,
                "completed": 0,
                "cancelled": 0,
                "gpu_util_sum": 0,
                "gpu_util_count": 0,
            }
        b = buckets[key]
        b["jobs"] += 1
        b["spend"] = round(b["spend"] + job.get("cost_so_far", 0.0), 6)
        if job["status"] == "complete":
            b["completed"] += 1
        elif job["status"] == "cancelled":
            b["cancelled"] += 1
        util = job.get("gpu_util", 0)
        if util:
            b["gpu_util_sum"] += util
            b["gpu_util_count"] += 1

    result = []
    for b in sorted(buckets.values(), key=lambda x: x["bucket"]):
        avg_util = round(b["gpu_util_sum"] / b["gpu_util_count"], 1) if b["gpu_util_count"] else None
        result.append({
            "bucket": b["bucket"],
            "jobs": b["jobs"],
            "spend": b["spend"],
            "completed": b["completed"],
            "cancelled": b["cancelled"],
            "avg_gpu_util": avg_util,
        })

    return {
        "granularity": granularity,
        "from_ts": from_ts,
        "to_ts": to_ts,
        "total_jobs": sum(b["jobs"] for b in result),
        "total_spend": round(sum(b["spend"] for b in result), 6),
        "buckets": result,
    }

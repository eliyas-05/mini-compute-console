"""
Budget guardrails.

Each job can have an optional budget_limit (USD). The engine checks
cost_so_far on every poll and auto-cancels the job if the limit is
breached, appending a log line explaining why.
"""

from logger import warn


def check_budget(job: dict) -> bool:
    """
    Returns True if the job should be cancelled due to budget breach.
    Mutates job status and logs to the job log — caller must persist.
    """
    limit = job.get("budget_limit")
    if not limit:
        return False
    if job["status"] != "running":
        return False
    if job["cost_so_far"] >= limit:
        warn(
            "budget.exceeded",
            job_id=job["id"],
            cost=job["cost_so_far"],
            limit=limit,
        )
        return True
    return False


def budget_remaining(job: dict) -> float | None:
    limit = job.get("budget_limit")
    if limit is None:
        return None
    return max(0.0, round(limit - job["cost_so_far"], 6))


def budget_pct_used(job: dict) -> float | None:
    limit = job.get("budget_limit")
    if not limit:
        return None
    return round(min(100.0, job["cost_so_far"] / limit * 100), 1)

from collections import Counter
from job_engine import _jobs, get_job


def compute_analytics() -> dict:
    jobs = [get_job(jid) for jid in list(_jobs.keys())]

    total = len(jobs)
    completed = sum(1 for j in jobs if j["status"] == "complete")
    cancelled = sum(1 for j in jobs if j["status"] == "cancelled")
    running = sum(1 for j in jobs if j["status"] == "running")
    total_spend = round(sum(j["cost_so_far"] for j in jobs), 6)
    avg_cost = round(total_spend / total, 6) if total else 0.0

    provider_counts: Counter = Counter()
    provider_spend: dict[str, float] = {}
    for j in jobs:
        pid = j["provider_id"]
        provider_counts[pid] += 1
        provider_spend[pid] = round(provider_spend.get(pid, 0) + j["cost_so_far"], 6)

    most_used = provider_counts.most_common(1)[0][0] if provider_counts else None
    cheapest = (
        min(provider_spend, key=lambda p: provider_spend[p] / provider_counts[p])
        if provider_spend else None
    )

    breakdown = {
        pid: {"jobs": provider_counts[pid], "total_spend": provider_spend[pid]}
        for pid in provider_counts
    }

    return {
        "total_jobs": total,
        "completed_jobs": completed,
        "cancelled_jobs": cancelled,
        "running_jobs": running,
        "total_spend": total_spend,
        "avg_cost_per_job": avg_cost,
        "cheapest_provider": cheapest,
        "most_used_provider": most_used,
        "provider_breakdown": breakdown,
    }

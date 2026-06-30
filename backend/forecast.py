"""
Cost forecasting for running jobs.

Given a job's current burn rate, projects:
  - estimated_final_cost   : cost if job runs to natural completion
  - eta_seconds            : seconds until natural completion
  - burn_rate_per_hour     : current $/hr (spot price)
  - budget_breach_prob     : 0-1 probability budget will be exceeded
  - over_budget_by         : how much over budget (None if no limit)
  - savings_vs_base        : $ saved vs base price so far
"""

from job_engine import _JOB_DURATION_SECONDS


def forecast_job(job: dict) -> dict:
    import time
    now = time.time()
    elapsed = now - job["started_at"]
    price = job["price_per_hour"]
    base  = job.get("base_price_per_hour", price)

    remaining_seconds = max(0.0, _JOB_DURATION_SECONDS - elapsed)
    estimated_final   = round(_JOB_DURATION_SECONDS / 3600 * price, 6)
    burn_rate         = price  # $/hr — spot price is the instantaneous burn rate

    savings_vs_base = round((_JOB_DURATION_SECONDS / 3600) * (base - price), 6)

    budget_limit = job.get("budget_limit")
    if budget_limit:
        cost_at_completion = estimated_final
        # Simple probability: if projected cost > limit, p=1; if <80% of limit, p=0;
        # linearly interpolate in between.
        ratio = cost_at_completion / budget_limit
        if ratio >= 1.0:
            breach_prob = 1.0
        elif ratio <= 0.8:
            breach_prob = 0.0
        else:
            breach_prob = round((ratio - 0.8) / 0.2, 3)
        over_budget_by = round(max(0.0, cost_at_completion - budget_limit), 6) or None
    else:
        breach_prob    = 0.0
        over_budget_by = None

    return {
        "job_id":               job["id"],
        "status":               job["status"],
        "elapsed_seconds":      round(elapsed, 1),
        "eta_seconds":          round(remaining_seconds, 1),
        "burn_rate_per_hour":   round(burn_rate, 4),
        "cost_so_far":          job["cost_so_far"],
        "estimated_final_cost": estimated_final,
        "savings_vs_base":      savings_vs_base,
        "budget_limit":         budget_limit,
        "budget_breach_prob":   breach_prob,
        "over_budget_by":       over_budget_by,
    }

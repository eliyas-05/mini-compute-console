"""
Per-job performance report.

Produces a structured efficiency analysis for any completed or running job:
  - GPU utilisation stats (avg, peak, min, stddev)
  - Cost efficiency score (0-100): how close was spot price to the cheapest
    available provider at launch time?
  - Wasted capacity estimate: GPU headroom above 100% ideal
  - Savings vs base price
  - A plain-English recommendation

The score is designed to reward both good provider selection AND high GPU
utilisation — two levers an operator actually controls.
"""

import math
from mock_data import PROVIDERS


def job_report(job: dict) -> dict:
    samples  = job.get("_gpu_samples", [])
    gpu_util = job.get("gpu_util", 0)

    # ── GPU stats ─────────────────────────────────────────────────────────────
    all_samples = samples if samples else ([gpu_util] if gpu_util else [])
    if all_samples:
        avg_util  = round(sum(all_samples) / len(all_samples), 1)
        peak_util = max(all_samples)
        min_util  = min(all_samples)
        variance  = sum((x - avg_util) ** 2 for x in all_samples) / len(all_samples)
        stddev    = round(math.sqrt(variance), 2)
    else:
        avg_util = peak_util = min_util = stddev = 0

    # Wasted capacity: % of GPU time not used
    wasted_pct = round(max(0.0, 100 - avg_util), 1) if avg_util else None

    # ── Cost efficiency ───────────────────────────────────────────────────────
    price    = job["price_per_hour"]
    base     = job.get("base_price_per_hour", price)
    cheapest = min((p["price_per_hour"] for p in PROVIDERS if p["status"] == "available"),
                   default=price)

    # Score = how close we are to cheapest (100 = got the cheapest, 0 = 2x+ over)
    if cheapest > 0:
        ratio         = min(price / cheapest, 2.0)
        price_score   = round(max(0.0, (2.0 - ratio) / 1.0 * 50), 1)
    else:
        price_score   = 50.0

    util_score     = round((avg_util / 100) * 50, 1) if avg_util else 0
    efficiency     = round(price_score + util_score, 1)

    savings_vs_base = round((base - price) / base * 100, 2) if base else 0

    # ── Recommendation ────────────────────────────────────────────────────────
    tips = []
    if avg_util < 85:
        tips.append("GPU utilisation is below 85% — consider batching more work per job.")
    if price > cheapest * 1.15:
        tips.append("A cheaper provider was available — try 'normal' priority for cost routing.")
    if stddev > 8:
        tips.append("High GPU util variance suggests workload is bursty; pipeline stages could smooth it.")
    if not tips:
        tips.append("Excellent efficiency — high utilisation on a competitively priced provider.")

    grade = "A" if efficiency >= 80 else "B" if efficiency >= 65 else "C" if efficiency >= 50 else "D"

    return {
        "job_id":            job["id"],
        "status":            job["status"],
        "efficiency_score":  efficiency,
        "efficiency_grade":  grade,
        "gpu_util": {
            "avg":    avg_util,
            "peak":   peak_util,
            "min":    min_util,
            "stddev": stddev,
            "samples": len(all_samples),
        },
        "wasted_capacity_pct":   wasted_pct,
        "cost": {
            "total":             job["cost_so_far"],
            "spot_per_hour":     round(price, 4),
            "base_per_hour":     round(base, 4),
            "cheapest_available": round(cheapest, 4),
            "savings_vs_base_pct": savings_vs_base,
        },
        "recommendation": " ".join(tips),
    }

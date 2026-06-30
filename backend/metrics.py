"""
Prometheus-compatible metrics endpoint.

Exposes scrape-ready text/plain metrics at GET /metrics so any Prometheus
instance (or Grafana Agent) can collect them without additional config.

Metric families:
  voltgrid_jobs_total          gauge   by status label
  voltgrid_spend_dollars_total gauge   cumulative spend across all jobs
  voltgrid_gpu_util_avg        gauge   mean GPU utilisation across running jobs
  voltgrid_providers_total     gauge   total provider count
  voltgrid_providers_available gauge   available provider count
  voltgrid_spot_price_dollars  gauge   by provider_id label
  voltgrid_provider_sla_pct    gauge   by provider_id label (5-min window)
  voltgrid_rate_limit_used     gauge   by api_key label
"""

from job_engine import list_jobs
from mock_data import PROVIDERS
from spot_prices import get_spot_prices
from sla_tracker import get_sla
from auth import _rate_counters, RATE_LIMIT, RATE_WINDOW
import time


def _g(name: str, help_: str, value, labels: dict | None = None) -> str:
    lbl = ""
    if labels:
        pairs = ",".join(f'{k}="{v}"' for k, v in labels.items())
        lbl   = f"{{{pairs}}}"
    return f"# HELP {name} {help_}\n# TYPE {name} gauge\n{name}{lbl} {value}\n"


def generate_metrics() -> str:
    lines = []
    jobs  = list_jobs()

    # ── Job counts by status ───────────────────────────────────────────────────
    counts = {"queued": 0, "running": 0, "complete": 0, "cancelled": 0}
    for j in jobs:
        counts[j["status"]] = counts.get(j["status"], 0) + 1

    lines.append("# HELP voltgrid_jobs_total Number of jobs by status")
    lines.append("# TYPE voltgrid_jobs_total gauge")
    for status, n in counts.items():
        lines.append(f'voltgrid_jobs_total{{status="{status}"}} {n}')
    lines.append("")

    # ── Total spend ───────────────────────────────────────────────────────────
    total_spend = sum(j["cost_so_far"] for j in jobs)
    lines.append(_g("voltgrid_spend_dollars_total",
                    "Cumulative spend in USD across all jobs", round(total_spend, 6)))

    # ── Avg GPU utilisation ───────────────────────────────────────────────────
    running_utils = [j["gpu_util"] for j in jobs if j["status"] == "running" and j.get("gpu_util")]
    avg_util = round(sum(running_utils) / len(running_utils), 2) if running_utils else 0
    lines.append(_g("voltgrid_gpu_util_avg",
                    "Mean GPU utilisation % across running jobs", avg_util))

    # ── Provider availability ─────────────────────────────────────────────────
    lines.append(_g("voltgrid_providers_total",    "Total provider count",     len(PROVIDERS)))
    lines.append(_g("voltgrid_providers_available","Available provider count",
                    sum(1 for p in PROVIDERS if p["status"] == "available")))

    # ── Spot prices per provider ──────────────────────────────────────────────
    spots = get_spot_prices()
    lines.append("# HELP voltgrid_spot_price_dollars Current spot price in USD/hr")
    lines.append("# TYPE voltgrid_spot_price_dollars gauge")
    for p in PROVIDERS:
        price = spots.get(p["id"], p["price_per_hour"])
        lines.append(f'voltgrid_spot_price_dollars{{provider_id="{p["id"]}"}} {round(price, 4)}')
    lines.append("")

    # ── SLA per provider ──────────────────────────────────────────────────────
    lines.append("# HELP voltgrid_provider_sla_pct 5-minute rolling SLA percentage")
    lines.append("# TYPE voltgrid_provider_sla_pct gauge")
    for p in PROVIDERS:
        sla = get_sla(p["id"])
        pct = sla["sla_pct"] if sla["sla_pct"] is not None else -1
        lines.append(f'voltgrid_provider_sla_pct{{provider_id="{p["id"]}"}} {pct}')
    lines.append("")

    # ── Rate limit usage per key ──────────────────────────────────────────────
    now          = time.time()
    window_start = now - RATE_WINDOW
    lines.append("# HELP voltgrid_rate_limit_used Requests used in current window")
    lines.append("# TYPE voltgrid_rate_limit_used gauge")
    for key, timestamps in _rate_counters.items():
        used = sum(1 for t in timestamps if t > window_start)
        lines.append(f'voltgrid_rate_limit_used{{api_key="{key[:8]}…"}} {used}')
    lines.append("")

    return "\n".join(lines)

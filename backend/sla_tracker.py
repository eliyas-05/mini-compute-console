"""
Provider SLA tracker.

Keeps a rolling 5-minute window of availability samples per provider.
Each time a provider is observed (available or busy), we record it.
SLA = fraction of samples where status == "available".

Exposed via:
  record_sample(provider_id, status)   — called on every /providers poll
  get_sla(provider_id) -> dict         — current SLA stats
  get_all_slas() -> dict[str, dict]
"""

import time
from collections import defaultdict, deque

_WINDOW_SECONDS = 300  # 5-minute rolling window
_samples: dict[str, deque] = defaultdict(lambda: deque())


def record_sample(provider_id: str, status: str):
    now = time.time()
    dq  = _samples[provider_id]
    dq.append((now, status))
    cutoff = now - _WINDOW_SECONDS
    while dq and dq[0][0] < cutoff:
        dq.popleft()


def get_sla(provider_id: str) -> dict:
    now    = time.time()
    cutoff = now - _WINDOW_SECONDS
    dq     = _samples.get(provider_id, deque())
    recent = [(t, s) for t, s in dq if t >= cutoff]

    total     = len(recent)
    available = sum(1 for _, s in recent if s == "available")
    sla_pct   = round(available / total * 100, 2) if total else None

    # Incident = any contiguous run of "busy" samples
    incidents = 0
    prev = None
    for _, s in recent:
        if s == "busy" and prev != "busy":
            incidents += 1
        prev = s

    return {
        "provider_id":    provider_id,
        "window_seconds": _WINDOW_SECONDS,
        "total_samples":  total,
        "sla_pct":        sla_pct,
        "incidents":      incidents,
        "grade": (
            "A" if sla_pct is None or sla_pct >= 99 else
            "B" if sla_pct >= 95 else
            "C" if sla_pct >= 90 else "D"
        ),
    }


def get_all_slas() -> dict:
    from mock_data import PROVIDERS
    return {p["id"]: get_sla(p["id"]) for p in PROVIDERS}

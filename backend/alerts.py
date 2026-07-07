"""
Spend alert system.

Owners register thresholds; when total account spend crosses the limit the
engine fires the registered webhooks. Distinct from per-job budget_limit —
alerts are account-level and trigger notifications rather than cancellations.

Each alert fires once: after triggering it is marked fired=True and ignored
on subsequent checks. The owner can reset it with PATCH /alerts/{id}/reset.
"""

import time
import uuid
from typing import Optional


_alerts: dict[str, dict] = {}  # alert_id → alert record


def create_alert(
    owner: str,
    threshold_usd: float,
    webhook_id: Optional[str] = None,
    label: Optional[str] = None,
) -> dict:
    if threshold_usd <= 0:
        raise ValueError("threshold_usd must be > 0")

    aid = str(uuid.uuid4())[:8]
    record = {
        "id": aid,
        "owner": owner,
        "threshold_usd": threshold_usd,
        "webhook_id": webhook_id,
        "label": label or f"Spend alert at ${threshold_usd:.2f}",
        "fired": False,
        "fired_at": None,
        "spend_at_trigger": None,
        "created_at": time.time(),
    }
    _alerts[aid] = record
    return record


def list_alerts(owner: str) -> list[dict]:
    return [a for a in _alerts.values() if a["owner"] == owner]


def get_alert(aid: str, owner: str) -> Optional[dict]:
    a = _alerts.get(aid)
    return a if a and a["owner"] == owner else None


def delete_alert(aid: str, owner: str) -> bool:
    a = _alerts.get(aid)
    if not a or a["owner"] != owner:
        return False
    del _alerts[aid]
    return True


def reset_alert(aid: str, owner: str) -> Optional[dict]:
    """Re-arm a fired alert so it can fire again on the next crossing."""
    a = _alerts.get(aid)
    if not a or a["owner"] != owner:
        return None
    a["fired"] = False
    a["fired_at"] = None
    a["spend_at_trigger"] = None
    return a


def check_alerts(owner: str, total_spend: float, fire_fn) -> list[str]:
    """
    Called after every job state change. Checks all unfired alerts for this
    owner and calls fire_fn(alert, total_spend) for each that crossed its threshold.

    fire_fn is injected by the caller to avoid circular imports with webhooks.
    Returns list of alert IDs that were triggered.
    """
    triggered = []
    for a in _alerts.values():
        if a["owner"] == owner and not a["fired"] and total_spend >= a["threshold_usd"]:
            a["fired"] = True
            a["fired_at"] = time.time()
            a["spend_at_trigger"] = round(total_spend, 6)
            fire_fn(a, total_spend)
            triggered.append(a["id"])
    return triggered

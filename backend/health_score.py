"""
Provider health scoring.

Composite score (0–100) weighted across three dimensions:
  - Uptime reliability   (50%) — normalized uptime_pct
  - Price competitiveness(30%) — how cheap vs. peers of same GPU class
  - Spot stability       (20%) — inverse of spot price deviation from base

Grade bands: A (90-100), B (75-89), C (60-74), D (<60)
"""

from mock_data import PROVIDERS
from spot_prices import get_spot_prices, _BASE


def _uptime_score(uptime_pct: float) -> float:
    """Map uptime 95-100 → 0-100."""
    return max(0.0, min(100.0, (uptime_pct - 95.0) / 5.0 * 100.0))


def _price_score(provider: dict, all_providers: list) -> float:
    """Compare price against peers with the same GPU class (lower is better)."""
    gpu = provider["gpu_type"]
    peers = [p["price_per_hour"] for p in all_providers if p["gpu_type"] == gpu]
    if len(peers) <= 1:
        return 75.0  # no competition data
    min_p, max_p = min(peers), max(peers)
    if max_p == min_p:
        return 75.0
    # cheapest peer → 100, most expensive → 0
    rank = (max_p - provider["price_per_hour"]) / (max_p - min_p)
    return round(rank * 100.0, 2)


def _stability_score(provider_id: str) -> float:
    """Inverse of spot price deviation from base (smaller drift → higher score)."""
    base = _BASE.get(provider_id, 1.0)
    spot = get_spot_prices().get(provider_id, base)
    deviation = abs(spot - base) / base  # 0 = perfect, 0.2 = max allowed
    stability = max(0.0, 1.0 - deviation / 0.20)
    return round(stability * 100.0, 2)


def _grade(score: float) -> str:
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    return "D"


def score_provider(provider: dict) -> dict:
    uptime  = _uptime_score(provider["uptime_pct"])
    price   = _price_score(provider, PROVIDERS)
    stability = _stability_score(provider["id"])

    composite = round(0.50 * uptime + 0.30 * price + 0.20 * stability, 1)
    return {
        "composite": composite,
        "grade": _grade(composite),
        "breakdown": {
            "uptime_score":    round(uptime, 1),
            "price_score":     round(price, 1),
            "stability_score": round(stability, 1),
        },
    }


def score_all_providers() -> dict[str, dict]:
    return {p["id"]: score_provider(p) for p in PROVIDERS}

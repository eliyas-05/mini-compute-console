"""
Spot price simulation.

Each provider's price drifts ±20% from its base using a mean-reverting
random walk (Ornstein-Uhlenbeck). Prices update every 30 seconds.
"""

import random
import time
from mock_data import PROVIDERS

_BASE: dict[str, float] = {p["id"]: p["price_per_hour"] for p in PROVIDERS}
_spot: dict[str, float] = dict(_BASE)
_last_tick: float = 0.0

_TICK_INTERVAL = 30
_DRIFT_SPEED   = 0.15   # mean-reversion strength
_VOLATILITY    = 0.04   # shock size as fraction of base


def _tick():
    global _last_tick
    now = time.time()
    if now - _last_tick < _TICK_INTERVAL:
        return
    _last_tick = now
    for pid, base in _BASE.items():
        current = _spot[pid]
        new = current + _DRIFT_SPEED * (base - current) + random.gauss(0, _VOLATILITY * base)
        _spot[pid] = round(max(base * 0.80, min(base * 1.20, new)), 4)


def get_spot_prices() -> dict[str, float]:
    _tick()
    return dict(_spot)


def get_spot_price(provider_id: str) -> float:
    _tick()
    return _spot.get(provider_id, _BASE.get(provider_id, 0.0))


def price_trend(provider_id: str) -> str:
    base = _BASE.get(provider_id, 0)
    spot = _spot.get(provider_id, base)
    delta = (spot - base) / base if base else 0
    if delta > 0.02:
        return "up"
    if delta < -0.02:
        return "down"
    return "flat"
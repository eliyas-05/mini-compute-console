import time
from fastapi import HTTPException, Header, Response
from typing import Optional

API_KEYS = {
    "demo-key-123":  "demo-user",
    "admin-key-456": "admin-user",
    "test-key-789":  "test-user",
    "tenant-key-000": "tenant-user",
}

# Per-key rate limits: keys not listed here get the default
_RATE_LIMITS: dict[str, int] = {
    "admin-key-456": 100,  # admin tier — higher limit for bulk ops
}
_DEFAULT_RATE_LIMIT = 30
RATE_WINDOW = 60

_rate_counters: dict[str, list[float]] = {}


def _limit_for(key: str) -> int:
    return _RATE_LIMITS.get(key, _DEFAULT_RATE_LIMIT)


def _get_usage(key: str) -> tuple[int, int]:
    """Return (used, remaining) for the current window."""
    now = time.time()
    window_start = now - RATE_WINDOW
    timestamps = [t for t in _rate_counters.get(key, []) if t > window_start]
    used = len(timestamps)
    limit = _limit_for(key)
    return used, max(0, limit - used)


def get_rate_info(key: str) -> dict:
    used, remaining = _get_usage(key)
    limit = _limit_for(key)
    return {"limit": limit, "used": used, "remaining": remaining, "window_seconds": RATE_WINDOW}


def verify_api_key(
    x_api_key: Optional[str] = Header(default=None),
    response: Response = None,
) -> str:
    if not x_api_key or x_api_key not in API_KEYS:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    limit = _limit_for(x_api_key)
    now = time.time()
    window_start = now - RATE_WINDOW
    timestamps = _rate_counters.get(x_api_key, [])
    timestamps = [t for t in timestamps if t > window_start]

    if len(timestamps) >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded ({limit} req/min)",
            headers={"X-RateLimit-Limit": str(limit), "X-RateLimit-Remaining": "0"},
        )

    timestamps.append(now)
    _rate_counters[x_api_key] = timestamps

    remaining = limit - len(timestamps)
    if response is not None:
        response.headers["X-RateLimit-Limit"]     = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Window"]    = str(RATE_WINDOW)

    return API_KEYS[x_api_key]

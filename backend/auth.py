import time
from fastapi import HTTPException, Header, Response
from typing import Optional

API_KEYS = {
    "demo-key-123": "demo-user",
    "admin-key-456": "admin-user",
    "test-key-789": "test-user",
}

RATE_LIMIT = 30
RATE_WINDOW = 60

_rate_counters: dict[str, list[float]] = {}


def _get_usage(key: str) -> tuple[int, int]:
    """Return (used, remaining) for the current window."""
    now = time.time()
    window_start = now - RATE_WINDOW
    timestamps = [t for t in _rate_counters.get(key, []) if t > window_start]
    used = len(timestamps)
    return used, max(0, RATE_LIMIT - used)


def get_rate_info(key: str) -> dict:
    used, remaining = _get_usage(key)
    return {"limit": RATE_LIMIT, "used": used, "remaining": remaining, "window_seconds": RATE_WINDOW}


def verify_api_key(
    x_api_key: Optional[str] = Header(default=None),
    response: Response = None,
) -> str:
    if not x_api_key or x_api_key not in API_KEYS:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    now = time.time()
    window_start = now - RATE_WINDOW
    timestamps = _rate_counters.get(x_api_key, [])
    timestamps = [t for t in timestamps if t > window_start]

    if len(timestamps) >= RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded (30 req/min)",
            headers={"X-RateLimit-Limit": str(RATE_LIMIT), "X-RateLimit-Remaining": "0"},
        )

    timestamps.append(now)
    _rate_counters[x_api_key] = timestamps

    remaining = RATE_LIMIT - len(timestamps)
    if response is not None:
        response.headers["X-RateLimit-Limit"]     = str(RATE_LIMIT)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Window"]    = str(RATE_WINDOW)

    return API_KEYS[x_api_key]

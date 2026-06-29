import time
from fastapi import HTTPException, Header
from typing import Optional

API_KEYS = {
    "demo-key-123": "demo-user",
    "admin-key-456": "admin-user",
    "test-key-789": "test-user",
}

# Rate limiting: max 30 requests per minute per key
RATE_LIMIT = 30
RATE_WINDOW = 60  # seconds

_rate_counters: dict[str, list[float]] = {}


def verify_api_key(x_api_key: Optional[str] = Header(default=None)) -> str:
    if not x_api_key or x_api_key not in API_KEYS:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    now = time.time()
    window_start = now - RATE_WINDOW
    timestamps = _rate_counters.get(x_api_key, [])
    # Prune old timestamps
    timestamps = [t for t in timestamps if t > window_start]

    if len(timestamps) >= RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Rate limit exceeded (30 req/min)")

    timestamps.append(now)
    _rate_counters[x_api_key] = timestamps

    return API_KEYS[x_api_key]

"""
Webhook delivery system.

Owners register callback URLs for specific event types. When a matching event
fires (job_complete, job_cancelled, job_launched), the engine calls
fire_webhooks() which dispatches background HTTP POSTs to every registered URL
for that owner+event combination.

Delivery attempts are logged in-memory (last 50 per webhook). Failed deliveries
are not retried in this demo — a production implementation would use exponential
backoff with a dead-letter queue.
"""

import asyncio
import time
import uuid
from typing import Optional

import httpx

_webhooks: dict[str, dict] = {}  # webhook_id -> webhook record

VALID_EVENTS = {"job_launched", "job_complete", "job_cancelled", "job_running"}


def register_webhook(owner: str, url: str, events: list[str], secret: Optional[str] = None) -> dict:
    for e in events:
        if e not in VALID_EVENTS:
            raise ValueError(f"Unknown event type '{e}'. Valid: {sorted(VALID_EVENTS)}")

    wid = str(uuid.uuid4())[:8]
    record = {
        "id": wid,
        "owner": owner,
        "url": url,
        "events": list(events),
        "secret": secret,
        "active": True,
        "created_at": time.time(),
        "delivery_attempts": [],
        "success_count": 0,
        "failure_count": 0,
    }
    _webhooks[wid] = record
    return _public(record)


def list_webhooks(owner: str) -> list[dict]:
    return [_public(w) for w in _webhooks.values() if w["owner"] == owner]


def get_webhook(wid: str, owner: str) -> Optional[dict]:
    w = _webhooks.get(wid)
    if not w or w["owner"] != owner:
        return None
    return _public(w)


def delete_webhook(wid: str, owner: str) -> bool:
    w = _webhooks.get(wid)
    if not w or w["owner"] != owner:
        return False
    del _webhooks[wid]
    return True


def _public(w: dict) -> dict:
    """Return webhook record without the secret."""
    return {k: v for k, v in w.items() if k != "secret"}


async def _deliver(webhook: dict, payload: dict):
    """Fire one HTTP POST to the webhook URL. Log the attempt."""
    attempt = {
        "ts": time.time(),
        "event": payload.get("type"),
        "status_code": None,
        "error": None,
    }
    try:
        headers = {"Content-Type": "application/json", "X-Hook-Event": payload.get("type", "")}
        if webhook.get("secret"):
            headers["X-Hook-Secret"] = webhook["secret"]

        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(webhook["url"], json=payload, headers=headers)
            attempt["status_code"] = resp.status_code
            if resp.status_code < 300:
                webhook["success_count"] += 1
            else:
                webhook["failure_count"] += 1
    except Exception as exc:
        attempt["error"] = str(exc)[:120]
        webhook["failure_count"] += 1

    attempts = webhook["delivery_attempts"]
    attempts.append(attempt)
    if len(attempts) > 50:
        attempts.pop(0)


def fire_webhooks(event_type: str, owner: str, payload: dict):
    """
    Called from the synchronous job engine. Finds matching webhooks for this
    owner+event and schedules async delivery without blocking.
    """
    targets = [
        w for w in _webhooks.values()
        if w["owner"] == owner and w["active"] and event_type in w["events"]
    ]
    if not targets:
        return

    full_payload = {"type": event_type, **payload}

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return  # no event loop in test context

    for w in targets:
        loop.create_task(_deliver(w, full_payload))

"""
WebSocket pub-sub broadcast.

Any number of clients can subscribe to the global event stream at
WS /ws/events. When a job transitions state (launched, running,
complete, cancelled, rerouted) job_engine calls broadcast() and
every connected client receives the update instantly — no polling needed.

This is a fan-out hub: one publisher (the job engine), N subscribers
(browser tabs). Demonstrates real-time architecture beyond point-to-point
WebSocket streams.
"""

import asyncio
from fastapi import WebSocket

_subscribers: set[WebSocket] = set()


def subscribe(ws: WebSocket):
    _subscribers.add(ws)


def unsubscribe(ws: WebSocket):
    _subscribers.discard(ws)


async def broadcast(event: dict):
    """Fan out an event to all connected subscribers."""
    dead = set()
    for ws in list(_subscribers):
        try:
            await ws.send_json(event)
        except Exception:
            dead.add(ws)
    _subscribers -= dead


def broadcast_sync(event: dict):
    """Fire-and-forget from synchronous code (job_engine)."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(broadcast(event))
    except RuntimeError:
        pass  # no running event loop in test / sync context


def subscriber_count() -> int:
    return len(_subscribers)

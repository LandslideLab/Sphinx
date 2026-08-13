"""In-process event bus. The WebSocket manager subscribes to broadcast live updates.

The REST handlers, MCP tools and the SLA policy engine run in different threads,
so mutation sites call `publish_sync(...)` which schedules a coroutine on the
FastAPI event loop captured at startup.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)

    async def subscribe(self, topics: list[str]) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        for t in topics:
            self._subscribers[t].append(q)
        return q

    def unsubscribe(self, topics: list[str], q: asyncio.Queue) -> None:
        for t in topics:
            if q in self._subscribers[t]:
                self._subscribers[t].remove(q)

    async def publish(self, topic: str, payload: dict) -> None:
        for q in list(self._subscribers.get(topic, [])):
            try:
                q.put_nowait({"topic": topic, "data": payload})
            except asyncio.QueueFull:
                pass


bus = EventBus()

TOPIC_REQUESTS = "requests"
TOPIC_DECISIONS = "decisions"
TOPIC_POLICIES = "policies"
TOPIC_CAPTURE = "capture"

_loop: asyncio.AbstractEventLoop | None = None


def set_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Capture the running FastAPI event loop so sync threads can publish."""
    global _loop
    _loop = loop


def publish_sync(topic: str, payload: dict[str, Any]) -> None:
    """Publish an event from a synchronous context (REST/MCP/policy engine).

    No-op when the event loop is unavailable (e.g. during unit tests without a
    running server) so callers never block on the notification path.
    """
    loop = _loop
    if loop is None or loop.is_closed():
        return
    try:
        asyncio.run_coroutine_threadsafe(bus.publish(topic, payload), loop)
    except (RuntimeError, ValueError):
        pass

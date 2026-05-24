"""Job progress events + in-memory pub/sub for SSE consumers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Literal

EventType = Literal["progress", "paused", "reauth_required", "completed", "failed", "cancelled"]


@dataclass(slots=True)
class ProgressEvent:
    job_id: str
    type: EventType
    processed: int = 0
    total: int | None = None
    detail: dict[str, object] = field(default_factory=dict)


class ProgressSink:
    """Pub/sub fanout. One sink per process; subscribers get an ``asyncio.Queue``."""

    def __init__(self) -> None:
        self._subs: dict[str, list[asyncio.Queue[ProgressEvent]]] = {}

    def subscribe(self, job_id: str) -> asyncio.Queue[ProgressEvent]:
        q: asyncio.Queue[ProgressEvent] = asyncio.Queue()
        self._subs.setdefault(job_id, []).append(q)
        return q

    def unsubscribe(self, job_id: str, q: asyncio.Queue[ProgressEvent]) -> None:
        if job_id in self._subs and q in self._subs[job_id]:
            self._subs[job_id].remove(q)

    async def publish(self, event: ProgressEvent) -> None:
        for q in list(self._subs.get(event.job_id, [])):
            await q.put(event)


# Default in-process singleton (tests instantiate their own).
default_sink = ProgressSink()

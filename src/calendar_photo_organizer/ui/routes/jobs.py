"""Job status + SSE progress stream."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from calendar_photo_organizer.jobs.progress import default_sink

router = APIRouter(prefix="/jobs")


@router.get("/{job_id}")
def job_status(request: Request, job_id: str) -> dict[str, object]:
    conn = request.app.state.open_conn()
    try:
        row = conn.execute("SELECT * FROM scan_jobs WHERE id=?", (job_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        return {"error": "not-found"}
    return {k: row[k] for k in row}


@router.get("/{job_id}/stream")
async def job_stream(request: Request, job_id: str) -> EventSourceResponse:
    queue = default_sink.subscribe(job_id)

    async def event_gen() -> object:
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=10.0)
                except TimeoutError:
                    yield {"event": "ping", "data": ""}
                    continue
                yield {
                    "event": ev.type,
                    "data": json.dumps(
                        {"job_id": ev.job_id, "processed": ev.processed, "type": ev.type}
                    ),
                }
                if ev.type in {"completed", "cancelled", "failed"}:
                    break
        finally:
            default_sink.unsubscribe(job_id, queue)

    return EventSourceResponse(event_gen())  # type: ignore[arg-type]

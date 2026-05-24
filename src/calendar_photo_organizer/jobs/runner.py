"""Cancellable, checkpointed asyncio JobRunner.

Workers are coroutines that accept a :class:`JobContext`. They call
``await ctx.report_progress(n)`` after each item; the runner persists a
checkpoint every ``checkpoint_every`` items (or every ``heartbeat_seconds``,
whichever comes first) and emits a ``ProgressEvent`` on the bound :class:`~calendar_photo_organizer.jobs.progress.ProgressSink`.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from calendar_photo_organizer.db.repositories.errors import ErrorsRepository
from calendar_photo_organizer.db.repositories.jobs import JobsRepository
from calendar_photo_organizer.jobs.progress import ProgressEvent, ProgressSink, default_sink
from calendar_photo_organizer.logging_setup import bind_job_id

WorkerFn = Callable[["JobContext"], Awaitable[None]]


@dataclass(slots=True)
class JobContext:
    job_id: str
    checkpoint: int  # number of items already processed before this run
    _runner: JobRunner

    async def report_progress(self, processed: int) -> None:
        await self._runner._tick(self.job_id, processed)


class JobRunner:
    def __init__(
        self,
        *,
        jobs_repo: JobsRepository,
        errors_repo: ErrorsRepository,
        sink: ProgressSink | None = None,
    ) -> None:
        self.jobs = jobs_repo
        self.errors = errors_repo
        self.sink = sink or default_sink
        self._state: dict[str, _JobState] = {}

    async def run(
        self,
        job_type: str,
        worker: WorkerFn,
        *,
        checkpoint_every: int = 200,
        heartbeat_seconds: float = 5.0,
        resume_job_id: str | None = None,
        total_count: int | None = None,
    ) -> str:
        if resume_job_id:
            job_id = resume_job_id
            existing = self.jobs.get(job_id)
            checkpoint = existing.last_checkpoint if existing else 0
            self.jobs.set_status(job_id, "running", pause_reason=None)
        else:
            job_id = self.jobs.create(job_type, total_count=total_count)
            checkpoint = 0

        bind_job_id(job_id)
        self._state[job_id] = _JobState(
            checkpoint_every=checkpoint_every,
            heartbeat_seconds=heartbeat_seconds,
            last_persisted=checkpoint,
            last_persisted_at=time.monotonic(),
        )
        ctx = JobContext(job_id=job_id, checkpoint=checkpoint, _runner=self)

        try:
            await worker(ctx)
        except asyncio.CancelledError:
            self.jobs.set_status(job_id, "cancelled", finished=True)
            await self.sink.publish(
                ProgressEvent(
                    job_id=job_id, type="cancelled", processed=self._state[job_id].last_persisted
                )
            )
            raise
        except Exception as exc:
            self.errors.record(
                job_id=job_id,
                phase=job_type,
                subject_kind="other",
                subject=job_type,
                reason=type(exc).__name__,
                detail=str(exc),
            )
            self.jobs.set_status(job_id, "failed", finished=True)
            await self.sink.publish(
                ProgressEvent(
                    job_id=job_id, type="failed", processed=self._state[job_id].last_persisted
                )
            )
            raise

        # Flush a final checkpoint
        state = self._state[job_id]
        self.jobs.update_checkpoint(
            job_id, processed=state.last_persisted, checkpoint=state.last_persisted
        )
        self.jobs.set_status(job_id, "completed", finished=True)
        await self.sink.publish(
            ProgressEvent(job_id=job_id, type="completed", processed=state.last_persisted)
        )
        return job_id

    async def _tick(self, job_id: str, processed: int) -> None:
        st = self._state[job_id]
        st.last_persisted = processed
        now = time.monotonic()
        delta = processed - st.last_checkpoint_value
        if delta >= st.checkpoint_every or (now - st.last_persisted_at) >= st.heartbeat_seconds:
            self.jobs.update_checkpoint(job_id, processed=processed, checkpoint=processed)
            await self.sink.publish(
                ProgressEvent(job_id=job_id, type="progress", processed=processed)
            )
            st.last_checkpoint_value = processed
            st.last_persisted_at = now


@dataclass(slots=True)
class _JobState:
    checkpoint_every: int
    heartbeat_seconds: float
    last_persisted: int
    last_persisted_at: float
    last_checkpoint_value: int = 0

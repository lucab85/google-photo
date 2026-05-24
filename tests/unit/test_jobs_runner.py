"""T016 — JobRunner: checkpointing, cooperative cancellation, resume."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from calendar_photo_organizer.db import migrate
from calendar_photo_organizer.db.connection import connect
from calendar_photo_organizer.db.repositories.errors import ErrorsRepository
from calendar_photo_organizer.db.repositories.jobs import JobsRepository
from calendar_photo_organizer.jobs.runner import JobRunner


@pytest.fixture
def job_runner(tmp_path: Path) -> tuple[JobRunner, JobsRepository]:
    conn = connect(tmp_path)
    migrate.apply(conn, data_dir=tmp_path)
    jobs = JobsRepository(conn)
    errors = ErrorsRepository(conn)
    return JobRunner(jobs_repo=jobs, errors_repo=errors), jobs


async def test_checkpoint_every_200_items(job_runner) -> None:
    runner, jobs = job_runner
    processed: list[int] = []

    async def work(ctx) -> None:
        for i in range(500):
            processed.append(i)
            await ctx.report_progress(i + 1)

    await runner.run("scan", work, checkpoint_every=200)
    job = jobs.latest_of_type("scan")
    assert job is not None
    assert job.status == "completed"
    assert job.processed_count == 500
    assert job.last_checkpoint >= 400  # 200, 400 checkpoints written


async def test_cancellation_marks_job_cancelled(job_runner) -> None:
    runner, jobs = job_runner

    async def slow(ctx) -> None:
        for i in range(100_000):
            await asyncio.sleep(0.001)
            await ctx.report_progress(i + 1)

    task = asyncio.create_task(runner.run("scan", slow, checkpoint_every=50))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    job = jobs.latest_of_type("scan")
    assert job is not None
    assert job.status == "cancelled"


async def test_resume_skips_already_done(job_runner) -> None:
    runner, jobs = job_runner
    seen: list[int] = []

    async def work(ctx) -> None:
        start = ctx.checkpoint  # resume marker
        for i in range(start, 600):
            seen.append(i)
            await ctx.report_progress(i + 1)

    # First run completes
    await runner.run("scan", work, checkpoint_every=100)
    job_id = jobs.latest_of_type("scan").id
    # Simulate "resume" of the same job: mark it paused and re-run from checkpoint
    jobs.set_status(job_id, "paused", pause_reason="manual")
    seen.clear()
    await runner.run("scan", work, checkpoint_every=100, resume_job_id=job_id)
    # No items < last_checkpoint should be re-processed
    assert all(i >= 600 for i in seen) or seen == []

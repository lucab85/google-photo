"""T043 — calendar OAuth pause/resume on RefreshError (FR-042a)."""

from __future__ import annotations

import pytest

from calendar_photo_organizer.calendar_client import (
    CalendarAuthError,
    run_calendar_import_with_reauth,
)
from calendar_photo_organizer.db import migrate
from calendar_photo_organizer.db.connection import connect
from calendar_photo_organizer.db.repositories.errors import ErrorsRepository
from calendar_photo_organizer.db.repositories.events import EventsRepository
from calendar_photo_organizer.db.repositories.jobs import JobsRepository
from calendar_photo_organizer.jobs.runner import JobRunner


class FakeRefreshError(Exception):
    pass


async def test_pause_then_resume(tmp_path) -> None:
    conn = connect(tmp_path)
    migrate.apply(conn, data_dir=tmp_path)
    events = EventsRepository(conn)
    runner = JobRunner(jobs_repo=JobsRepository(conn), errors_repo=ErrorsRepository(conn))

    # First attempt: raise RefreshError after 2 events
    call = {"n": 0}

    async def fetcher_failing(start, end):
        for i in range(5):
            call["n"] += 1
            if i == 2:
                raise FakeRefreshError("token expired")
            yield {
                "google_event_id": f"e{i}",
                "summary": f"E{i}",
                "start_utc": "2024-07-04T17:00:00Z",
                "end_utc": "2024-07-04T18:00:00Z",
                "is_all_day": False,
            }

    with pytest.raises(CalendarAuthError):
        await run_calendar_import_with_reauth(
            runner,
            events_repo=events,
            fetcher=fetcher_failing,
            start_iso="2024-07-01",
            end_iso="2024-07-31",
            refresh_error_types=(FakeRefreshError,),
        )
    job = runner.jobs.latest_of_type("calendar_import")
    assert job is not None
    assert job.status.value == "paused"
    assert job.pause_reason == "reauth_required"

    # Resume: this time fetcher succeeds
    async def fetcher_ok(start, end):
        for i in range(5):
            yield {
                "google_event_id": f"e{i}",
                "summary": f"E{i}",
                "start_utc": "2024-07-04T17:00:00Z",
                "end_utc": "2024-07-04T18:00:00Z",
                "is_all_day": False,
            }

    await run_calendar_import_with_reauth(
        runner,
        events_repo=events,
        fetcher=fetcher_ok,
        start_iso="2024-07-01",
        end_iso="2024-07-31",
        refresh_error_types=(FakeRefreshError,),
        resume_job_id=job.id,
    )
    job2 = runner.jobs.latest_of_type("calendar_import")
    assert job2 is not None
    assert job2.status.value == "completed"
    assert events.count() == 5

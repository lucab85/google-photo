"""Calendar import (fixture-friendly).

The OAuth + Google API client path is wrapped behind the abstract ``fetcher``
callable so the test suite can drive imports from a static JSON payload. The
real OAuth flow lives in :func:`build_google_calendar_fetcher` and is exercised
only by the live ``cpo auth google-calendar`` command, not by the test suite.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping
from datetime import datetime
from typing import Any

from calendar_photo_organizer.db.repositories.events import EventsRepository
from calendar_photo_organizer.jobs.runner import JobRunner
from calendar_photo_organizer.models import CalendarEvent


class CalendarAuthError(Exception):
    """Raised when re-authentication is required (token expired / revoked)."""


Fetcher = Callable[[str, str], AsyncIterator[Mapping[str, Any]]]


def _event_from_payload(p: Mapping[str, Any], *, calendar_id: str = "primary") -> CalendarEvent:
    return CalendarEvent(
        id=None,
        google_event_id=str(p["google_event_id"]),
        calendar_id=calendar_id,
        title=str(p.get("summary") or p.get("title") or "(untitled)"),
        description=p.get("description"),
        location=p.get("location"),
        start_utc=datetime.fromisoformat(p["start_utc"].replace("Z", "+00:00")),
        end_utc=datetime.fromisoformat(p["end_utc"].replace("Z", "+00:00")),
        is_all_day=bool(p.get("is_all_day", False)),
        etag=p.get("etag"),
    )


def import_events_from_json(
    payload: Mapping[str, Any], events_repo: EventsRepository
) -> int:
    """Bulk-import events from a JSON document like ``tests/fixtures/calendar_sample.json``."""
    calendar_id = str(payload.get("calendar_id", "primary"))
    n = 0
    for raw in payload.get("events", []):
        events_repo.upsert(_event_from_payload(raw, calendar_id=calendar_id))
        n += 1
    events_repo.conn.commit()
    return n


async def run_calendar_import_with_reauth(
    runner: JobRunner,
    *,
    events_repo: EventsRepository,
    fetcher: Fetcher,
    start_iso: str,
    end_iso: str,
    refresh_error_types: tuple[type[BaseException], ...] = (),
    resume_job_id: str | None = None,
    calendar_id: str = "primary",
) -> str:
    """Run a calendar-import job, pausing if a refresh error is raised.

    On any ``refresh_error_types`` exception the job is marked
    ``paused`` with ``pause_reason='reauth_required'`` and
    :class:`CalendarAuthError` is re-raised so the caller can prompt for
    re-auth (FR-042a).
    """

    async def worker(ctx: object) -> None:
        seen = 0
        try:
            async for raw in fetcher(start_iso, end_iso):
                events_repo.upsert(_event_from_payload(raw, calendar_id=calendar_id))
                seen += 1
                await ctx.report_progress(seen)  # type: ignore[attr-defined]
        except refresh_error_types as exc:
            raise CalendarAuthError(str(exc)) from exc

    try:
        return await runner.run(
            "calendar_import", worker, resume_job_id=resume_job_id
        )
    except CalendarAuthError:
        # Runner marked the job 'failed' before re-raising; promote to 'paused'.
        latest = runner.jobs.latest_of_type("calendar_import")
        if latest is not None:
            runner.jobs.set_status(latest.id, "paused", pause_reason="reauth_required")
        raise


def build_google_calendar_fetcher(
    credentials: Any, *, calendar_id: str = "primary"
) -> Fetcher:  # pragma: no cover - exercised only by live CLI
    """Build a fetcher that talks to the real Google Calendar API.

    Kept thin and isolated so the test suite never imports googleapiclient.
    """
    from googleapiclient.discovery import build

    service = build("calendar", "v3", credentials=credentials, cache_discovery=False)

    async def fetch(start_iso: str, end_iso: str) -> AsyncIterator[Mapping[str, Any]]:
        page_token: str | None = None
        while True:
            req = service.events().list(
                calendarId=calendar_id,
                timeMin=start_iso, timeMax=end_iso,
                singleEvents=True, orderBy="startTime",
                maxResults=2500, pageToken=page_token,
            )
            resp = req.execute()
            for ev in resp.get("items", []):
                yield {
                    "google_event_id": ev["id"],
                    "summary": ev.get("summary", ""),
                    "description": ev.get("description"),
                    "location": ev.get("location"),
                    "start_utc": ev["start"].get("dateTime") or ev["start"].get("date") + "T00:00:00Z",
                    "end_utc": ev["end"].get("dateTime") or ev["end"].get("date") + "T00:00:00Z",
                    "is_all_day": "date" in ev["start"],
                    "etag": ev.get("etag"),
                }
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

    return fetch

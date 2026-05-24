"""Calendar events repository."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import datetime

from calendar_photo_organizer.models import CalendarEvent


def _row_to_event(row: sqlite3.Row) -> CalendarEvent:
    return CalendarEvent(
        id=row["id"],
        google_event_id=row["google_event_id"],
        calendar_id=row["calendar_id"],
        title=row["title"],
        description=row["description"],
        location=row["location"],
        start_utc=datetime.fromisoformat(row["start_utc"]),
        end_utc=datetime.fromisoformat(row["end_utc"]),
        is_all_day=bool(row["is_all_day"]),
        etag=row["etag"],
    )


class EventsRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def upsert(self, event: CalendarEvent) -> int:
        cur = self.conn.execute(
            "SELECT id FROM calendar_events WHERE google_event_id = ? AND calendar_id = ?",
            (event.google_event_id, event.calendar_id),
        ).fetchone()
        if cur is not None:
            self.conn.execute(
                """UPDATE calendar_events
                       SET title=?, description=?, location=?,
                           start_utc=?, end_utc=?, is_all_day=?, etag=?
                     WHERE id=?""",
                (
                    event.title,
                    event.description,
                    event.location,
                    event.start_utc.isoformat(),
                    event.end_utc.isoformat(),
                    int(event.is_all_day),
                    event.etag,
                    cur["id"],
                ),
            )
            return int(cur["id"])
        ins = self.conn.execute(
            """INSERT INTO calendar_events
                 (google_event_id, calendar_id, title, description, location,
                  start_utc, end_utc, is_all_day, etag)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event.google_event_id,
                event.calendar_id,
                event.title,
                event.description,
                event.location,
                event.start_utc.isoformat(),
                event.end_utc.isoformat(),
                int(event.is_all_day),
                event.etag,
            ),
        )
        return int(ins.lastrowid or 0)

    def find_in_window(self, start_utc: datetime, end_utc: datetime) -> Iterator[CalendarEvent]:
        q = """SELECT * FROM calendar_events
                 WHERE start_utc < ? AND end_utc > ?
              ORDER BY start_utc"""
        for row in self.conn.execute(q, (end_utc.isoformat(), start_utc.isoformat())):
            yield _row_to_event(row)

    def get(self, event_id: int) -> CalendarEvent | None:
        row = self.conn.execute("SELECT * FROM calendar_events WHERE id=?", (event_id,)).fetchone()
        return _row_to_event(row) if row else None

    def iter_all(self) -> Iterator[CalendarEvent]:
        for row in self.conn.execute("SELECT * FROM calendar_events ORDER BY start_utc"):
            yield _row_to_event(row)

    def count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) AS c FROM calendar_events").fetchone()["c"])

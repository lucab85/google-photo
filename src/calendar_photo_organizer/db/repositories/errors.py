"""errors repository — never raises."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import datetime

from calendar_photo_organizer.models import ErrorRecord


def _row(row: sqlite3.Row) -> ErrorRecord:
    return ErrorRecord(
        id=row["id"],
        job_id=row["job_id"],
        phase=row["phase"],
        subject_kind=row["subject_kind"],
        subject=row["subject"],
        reason=row["reason"],
        detail=row["detail"],
        occurred_at_utc=datetime.fromisoformat(row["occurred_at_utc"]),
    )


class ErrorsRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def record(
        self,
        *,
        job_id: str | None,
        phase: str,
        subject_kind: str,
        subject: str,
        reason: str,
        detail: str | None = None,
    ) -> None:
        try:
            self.conn.execute(
                """INSERT INTO errors
                     (job_id, phase, subject_kind, subject, reason, detail)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (job_id, phase, subject_kind, subject, reason, detail),
            )
            self.conn.commit()
        except sqlite3.Error:
            # Best-effort only — never raise from the error sink.
            pass

    def count(self, *, job_id: str | None = None) -> int:
        if job_id is None:
            r = self.conn.execute("SELECT COUNT(*) AS c FROM errors").fetchone()
        else:
            r = self.conn.execute(
                "SELECT COUNT(*) AS c FROM errors WHERE job_id=?", (job_id,)
            ).fetchone()
        return int(r["c"])

    def list(self, *, limit: int = 100) -> Iterator[ErrorRecord]:
        for row in self.conn.execute(
            "SELECT * FROM errors ORDER BY id DESC LIMIT ?", (int(limit),)
        ):
            yield _row(row)

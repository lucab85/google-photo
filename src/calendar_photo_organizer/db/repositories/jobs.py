"""scan_jobs repository."""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime

from calendar_photo_organizer.models import JobStatus, ScanJob


def _row(row: sqlite3.Row) -> ScanJob:
    return ScanJob(
        id=row["id"],
        job_type=row["job_type"],
        status=JobStatus(row["status"]),
        pause_reason=row["pause_reason"],
        started_at_utc=(
            datetime.fromisoformat(row["started_at_utc"]) if row["started_at_utc"] else None
        ),
        finished_at_utc=(
            datetime.fromisoformat(row["finished_at_utc"]) if row["finished_at_utc"] else None
        ),
        processed_count=row["processed_count"],
        total_count=row["total_count"],
        last_checkpoint=row["last_checkpoint"],
        detail_json=row["detail_json"],
    )


class JobsRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create(self, job_type: str, *, total_count: int | None = None) -> str:
        jid = str(uuid.uuid4())
        self.conn.execute(
            """INSERT INTO scan_jobs (id, job_type, status, started_at_utc, total_count)
               VALUES (?, ?, 'running', ?, ?)""",
            (jid, job_type, datetime.now(UTC).isoformat(), total_count),
        )
        self.conn.commit()
        return jid

    def get(self, job_id: str) -> ScanJob | None:
        row = self.conn.execute("SELECT * FROM scan_jobs WHERE id=?", (job_id,)).fetchone()
        return _row(row) if row else None

    def latest_of_type(self, job_type: str) -> ScanJob | None:
        row = self.conn.execute(
            "SELECT * FROM scan_jobs WHERE job_type=? ORDER BY started_at_utc DESC LIMIT 1",
            (job_type,),
        ).fetchone()
        return _row(row) if row else None

    def set_status(
        self,
        job_id: str,
        status: JobStatus | str,
        *,
        pause_reason: str | None = None,
        finished: bool = False,
    ) -> None:
        params: list[object] = [str(status), pause_reason]
        cols = "status=?, pause_reason=?"
        if finished:
            cols += ", finished_at_utc=?"
            params.append(datetime.now(UTC).isoformat())
        params.append(job_id)
        self.conn.execute(f"UPDATE scan_jobs SET {cols} WHERE id=?", params)
        self.conn.commit()

    def update_checkpoint(
        self,
        job_id: str,
        *,
        processed: int,
        checkpoint: int,
        detail: Mapping[str, object] | None = None,
    ) -> None:
        self.conn.execute(
            """UPDATE scan_jobs SET processed_count=?, last_checkpoint=?, detail_json=?
                 WHERE id=?""",
            (processed, checkpoint, json.dumps(dict(detail)) if detail else None, job_id),
        )
        self.conn.commit()

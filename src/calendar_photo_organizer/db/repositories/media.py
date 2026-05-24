"""Media + media_paths repository."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from calendar_photo_organizer.models import (
    CaptureSourceTier,
    MediaItem,
    MediaPath,
    Provenance,
)


def _row_to_media(row: sqlite3.Row) -> MediaItem:
    raw_ts = row["captured_at_utc"]
    ts: datetime | None = datetime.fromisoformat(raw_ts) if raw_ts else None
    return MediaItem(
        id=row["id"],
        content_hash=row["content_hash"],
        captured_at_utc=ts,
        captured_at_tz=row["captured_at_tz"],
        capture_source_tier=(
            CaptureSourceTier(row["capture_source_tier"]) if row["capture_source_tier"] else None
        ),
        mime_type=row["mime_type"],
        width=row["width"],
        height=row["height"],
        duration_seconds=row["duration_seconds"],
        provenance=Provenance(row["provenance"]),
        google_photo_id=row["google_photo_id"],
    )


class MediaRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    # ---- Media items ------------------------------------------------------

    def upsert_by_content_hash(self, media: MediaItem) -> int:
        cur = self.conn.execute(
            "SELECT id FROM media_items WHERE content_hash = ?",
            (media.content_hash,),
        )
        row = cur.fetchone()
        if row is not None:
            return int(row["id"])

        cur = self.conn.execute(
            """
            INSERT INTO media_items
                (content_hash, captured_at_utc, captured_at_tz, capture_source_tier,
                 mime_type, width, height, duration_seconds, provenance, google_photo_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                media.content_hash,
                media.captured_at_utc.isoformat() if media.captured_at_utc else None,
                media.captured_at_tz,
                str(media.capture_source_tier) if media.capture_source_tier else None,
                media.mime_type,
                media.width,
                media.height,
                media.duration_seconds,
                str(media.provenance),
                media.google_photo_id,
            ),
        )
        return int(cur.lastrowid or 0)

    def get(self, media_id: int) -> MediaItem | None:
        row = self.conn.execute("SELECT * FROM media_items WHERE id = ?", (media_id,)).fetchone()
        return _row_to_media(row) if row is not None else None

    def iter_all(self) -> Iterator[MediaItem]:
        for row in self.conn.execute("SELECT * FROM media_items"):
            yield _row_to_media(row)

    def find_unmatched(self) -> Iterator[MediaItem]:
        q = """
            SELECT m.* FROM media_items m
            LEFT JOIN media_event_matches x ON x.media_id = m.id
            WHERE x.id IS NULL
        """
        for row in self.conn.execute(q):
            yield _row_to_media(row)

    # ---- Media paths ------------------------------------------------------

    def add_path(self, path: MediaPath) -> None:
        self.conn.execute(
            """
            INSERT OR IGNORE INTO media_paths
                (media_id, path, size_bytes, mtime_ns, is_primary)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                path.media_id,
                str(path.path),
                path.size_bytes,
                path.mtime_ns,
                int(path.is_primary),
            ),
        )

    def find_by_path_size_mtime(self, path: Path, size: int, mtime_ns: int) -> int | None:
        row = self.conn.execute(
            "SELECT media_id FROM media_paths WHERE path = ? AND size_bytes = ? AND mtime_ns = ?",
            (str(path), size, mtime_ns),
        ).fetchone()
        return int(row["media_id"]) if row is not None else None

    def paths_for(self, media_id: int) -> list[Path]:
        return [
            Path(row["path"])
            for row in self.conn.execute(
                "SELECT path FROM media_paths WHERE media_id = ? ORDER BY is_primary DESC, id ASC",
                (media_id,),
            )
        ]

    def count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) AS c FROM media_items").fetchone()["c"])

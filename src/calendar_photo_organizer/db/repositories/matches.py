"""media_event_matches repository."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator

from calendar_photo_organizer.models import (
    ConfidenceBand,
    MatchRule,
    MediaEventMatch,
)


def _row_to_match(row: sqlite3.Row) -> MediaEventMatch:
    return MediaEventMatch(
        id=row["id"],
        media_id=row["media_id"],
        event_id=row["event_id"],
        rule=MatchRule(row["rule"]),
        confidence=row["confidence"],
        band=ConfidenceBand(row["band"]),
        is_recommended=bool(row["is_recommended"]),
    )


class MatchesRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def replace_for_media(self, media_id: int, matches: Iterable[MediaEventMatch]) -> None:
        self.conn.execute("DELETE FROM media_event_matches WHERE media_id = ?", (media_id,))
        ml = list(matches)
        if not ml:
            return
        # Ensure at most one recommended (Invariant I-1)
        rec_seen = False
        rows: list[tuple[int, int, str, float, str, int]] = []
        for m in ml:
            is_rec = bool(m.is_recommended) and not rec_seen
            if is_rec:
                rec_seen = True
            rows.append(
                (
                    media_id,
                    m.event_id,
                    str(m.rule),
                    float(m.confidence),
                    str(m.band),
                    int(is_rec),
                )
            )
        self.conn.executemany(
            """INSERT INTO media_event_matches
                 (media_id, event_id, rule, confidence, band, is_recommended)
               VALUES (?, ?, ?, ?, ?, ?)""",
            rows,
        )

    def for_media(self, media_id: int) -> list[MediaEventMatch]:
        return [
            _row_to_match(r)
            for r in self.conn.execute(
                "SELECT * FROM media_event_matches WHERE media_id = ?", (media_id,)
            )
        ]

    def recommended_for_event(self, event_id: int) -> list[MediaEventMatch]:
        return [
            _row_to_match(r)
            for r in self.conn.execute(
                "SELECT * FROM media_event_matches WHERE event_id = ? AND is_recommended = 1",
                (event_id,),
            )
        ]

    def count_by_band(self) -> dict[str, int]:
        out = {"high": 0, "medium": 0, "low": 0}
        for r in self.conn.execute(
            "SELECT band, COUNT(*) AS c FROM media_event_matches "
            "WHERE is_recommended = 1 GROUP BY band"
        ):
            out[r["band"]] = int(r["c"])
        return out

    def iter_recommended_grouped_by_event(self) -> Iterator[tuple[int, list[int]]]:
        q = """SELECT event_id, media_id FROM media_event_matches
                 WHERE is_recommended = 1 ORDER BY event_id"""
        current: int | None = None
        bucket: list[int] = []
        for r in self.conn.execute(q):
            ev = int(r["event_id"])
            if current is None:
                current = ev
            if ev != current:
                yield current, bucket
                current = ev
                bucket = []
            bucket.append(int(r["media_id"]))
        if current is not None:
            yield current, bucket

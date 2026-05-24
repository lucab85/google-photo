"""Proposed albums + album_items repository."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator

from calendar_photo_organizer.models import AlbumStatus, ProposedAlbum


def _row(row: sqlite3.Row) -> ProposedAlbum:
    return ProposedAlbum(
        id=row["id"],
        display_name=row["display_name"],
        folder_name=row["folder_name"],
        status=AlbumStatus(row["status"]),
        event_id=row["event_id"],
        user_renamed=bool(row["user_renamed"]),
        merged_from_json=row["merged_from_json"],
        split_from_id=row["split_from_id"],
    )


class AlbumsRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    # -------- CRUD --------

    def create(self, album: ProposedAlbum) -> int:
        cur = self.conn.execute(
            """INSERT INTO proposed_albums
                 (display_name, folder_name, status, event_id,
                  user_renamed, merged_from_json, split_from_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                album.display_name,
                album.folder_name,
                str(album.status),
                album.event_id,
                int(album.user_renamed),
                album.merged_from_json,
                album.split_from_id,
            ),
        )
        return int(cur.lastrowid or 0)

    def get(self, album_id: int) -> ProposedAlbum | None:
        row = self.conn.execute("SELECT * FROM proposed_albums WHERE id=?", (album_id,)).fetchone()
        return _row(row) if row else None

    def find_by_event(self, event_id: int) -> ProposedAlbum | None:
        row = self.conn.execute(
            "SELECT * FROM proposed_albums WHERE event_id=? AND split_from_id IS NULL",
            (event_id,),
        ).fetchone()
        return _row(row) if row else None

    def list_page(
        self,
        *,
        band: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> list[ProposedAlbum]:
        clauses: list[str] = []
        params: list[object] = []
        if status:
            clauses.append("a.status = ?")
            params.append(status)
        if band:
            # band filter requires joining matches → events → albums
            clauses.append(
                """a.event_id IN (
                    SELECT event_id FROM media_event_matches
                     WHERE is_recommended = 1 AND band = ?
                )"""
            )
            params.append(band)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        page_size = max(1, min(int(page_size), 200))
        offset = (max(int(page), 1) - 1) * page_size
        q = f"SELECT a.* FROM proposed_albums a {where} ORDER BY a.id LIMIT ? OFFSET ?"
        params.extend([page_size, offset])
        return [_row(r) for r in self.conn.execute(q, params)]

    def iter_all(self) -> Iterator[ProposedAlbum]:
        for row in self.conn.execute("SELECT * FROM proposed_albums ORDER BY id"):
            yield _row(row)

    def count(self, *, status: str | None = None) -> int:
        if status:
            r = self.conn.execute(
                "SELECT COUNT(*) AS c FROM proposed_albums WHERE status=?", (status,)
            ).fetchone()
        else:
            r = self.conn.execute("SELECT COUNT(*) AS c FROM proposed_albums").fetchone()
        return int(r["c"])

    def set_status(self, album_id: int, status: AlbumStatus | str) -> None:
        self.conn.execute(
            "UPDATE proposed_albums SET status=?, updated_at_utc=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",
            (str(status), album_id),
        )

    def rename(self, album_id: int, display_name: str, folder_name: str) -> None:
        self.conn.execute(
            """UPDATE proposed_albums
                  SET display_name=?, folder_name=?, user_renamed=1,
                      updated_at_utc=strftime('%Y-%m-%dT%H:%M:%fZ','now')
                WHERE id=?""",
            (display_name, folder_name, album_id),
        )

    def folder_name_exists(self, folder_name: str, *, exclude_id: int | None = None) -> bool:
        if exclude_id is None:
            row = self.conn.execute(
                "SELECT 1 FROM proposed_albums WHERE folder_name=? LIMIT 1",
                (folder_name,),
            ).fetchone()
        else:
            row = self.conn.execute(
                "SELECT 1 FROM proposed_albums WHERE folder_name=? AND id!=? LIMIT 1",
                (folder_name, exclude_id),
            ).fetchone()
        return row is not None

    # -------- Album items --------

    def add_items(self, album_id: int, media_ids: Iterable[int]) -> int:
        rows = [(album_id, mid) for mid in media_ids]
        if not rows:
            return 0
        self.conn.executemany(
            "INSERT OR IGNORE INTO album_items (album_id, media_id) VALUES (?, ?)",
            rows,
        )
        return len(rows)

    def remove_items(self, album_id: int, media_ids: Iterable[int]) -> None:
        rows = [(album_id, mid) for mid in media_ids]
        if not rows:
            return
        self.conn.executemany("DELETE FROM album_items WHERE album_id=? AND media_id=?", rows)

    def items(self, album_id: int) -> list[int]:
        return [
            int(r["media_id"])
            for r in self.conn.execute(
                "SELECT media_id FROM album_items WHERE album_id=? ORDER BY media_id",
                (album_id,),
            )
        ]

    def media_album_ids(self, media_id: int) -> list[int]:
        return [
            int(r["album_id"])
            for r in self.conn.execute(
                "SELECT album_id FROM album_items WHERE media_id=?", (media_id,)
            )
        ]

    def set_merged_from(self, album_id: int, source_ids: list[int]) -> None:
        self.conn.execute(
            "UPDATE proposed_albums SET merged_from_json=? WHERE id=?",
            (json.dumps(source_ids), album_id),
        )

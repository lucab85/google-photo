"""T012 — db.connection.connect()."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from calendar_photo_organizer.db.connection import connect


def test_connect_sets_pragmas_and_row_factory(tmp_path: Path) -> None:
    conn = connect(tmp_path)
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.row_factory is sqlite3.Row
        row = conn.execute("SELECT 1 AS one").fetchone()
        assert row["one"] == 1
    finally:
        conn.close()

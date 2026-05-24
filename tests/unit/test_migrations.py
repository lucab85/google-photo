"""T011 — migrator applies 0001_initial cleanly."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from calendar_photo_organizer.db import migrate
from calendar_photo_organizer.db.connection import connect

REQUIRED_TABLES = {
    "schema_meta",
    "media_items",
    "media_paths",
    "calendar_events",
    "media_event_matches",
    "proposed_albums",
    "album_items",
    "scan_jobs",
    "errors",
    "export_targets",
    "exported_albums",
}


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def _indexes(conn: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
        )
    }


def test_apply_initial_migration(tmp_path: Path) -> None:
    conn = connect(tmp_path)
    migrate.apply(conn, data_dir=tmp_path)
    assert migrate.current_version(conn) == 1
    tables = _tables(conn)
    assert REQUIRED_TABLES.issubset(tables), f"missing tables: {REQUIRED_TABLES - tables}"
    idx = _indexes(conn)
    # Spot-check critical indexes
    assert any("media_items" in i for i in idx)
    assert any("media_event_matches" in i for i in idx)
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_migration_is_idempotent(tmp_path: Path) -> None:
    conn = connect(tmp_path)
    migrate.apply(conn, data_dir=tmp_path)
    migrate.apply(conn, data_dir=tmp_path)  # second apply does nothing
    assert migrate.current_version(conn) == 1

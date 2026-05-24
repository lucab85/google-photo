"""Linear SQL migrator.

Migrations live in ``db/migrations/NNNN_*.sql`` and are applied in lexicographic
order. The current schema version is tracked in the ``schema_meta`` table so
re-applying is a no-op.
"""

from __future__ import annotations

import re
import sqlite3
from importlib import resources
from pathlib import Path

_MIGRATION_RE = re.compile(r"^(\d{4})_.+\.sql$")


def _migration_files() -> list[tuple[int, str]]:
    pkg = resources.files("calendar_photo_organizer.db.migrations")
    out: list[tuple[int, str]] = []
    for entry in pkg.iterdir():
        m = _MIGRATION_RE.match(entry.name)
        if m:
            out.append((int(m.group(1)), entry.name))
    out.sort()
    return out


def _read(name: str) -> str:
    return (
        resources.files("calendar_photo_organizer.db.migrations")
        .joinpath(name)
        .read_text(encoding="utf-8")
    )


def current_version(conn: sqlite3.Connection) -> int:
    """Return the highest applied schema version, or 0 if none."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_meta'"
    ).fetchone()
    if row is None:
        return 0
    v = conn.execute("SELECT COALESCE(MAX(version), 0) AS v FROM schema_meta").fetchone()
    return int(v["v"] if isinstance(v, sqlite3.Row) else v[0])


def pending_migrations(conn: sqlite3.Connection) -> list[tuple[int, str]]:
    have = current_version(conn)
    return [(v, n) for v, n in _migration_files() if v > have]


def apply(conn: sqlite3.Connection, data_dir: Path | None = None) -> int:
    """Apply all pending migrations. Returns the count applied."""
    applied = 0
    for _version, name in pending_migrations(conn):
        sql = _read(name)
        conn.executescript(sql)
        conn.commit()
        applied += 1
    return applied

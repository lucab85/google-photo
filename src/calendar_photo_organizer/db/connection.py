"""SQLite connection factory.

Applies the project-wide pragmas (WAL, foreign keys ON) and installs the
``sqlite3.Row`` row factory so repository code can index columns by name.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

DB_FILENAME = "calendar_photo_organizer.sqlite3"
_RETRY_DELAYS = (0.05, 0.1, 0.25, 0.5)


def db_path(data_dir: Path) -> Path:
    return data_dir / DB_FILENAME


def connect(data_dir: Path) -> sqlite3.Connection:
    """Open (or create) the project database under *data_dir*."""
    data_dir.mkdir(parents=True, exist_ok=True)
    path = db_path(data_dir)

    last_exc: sqlite3.OperationalError | None = None
    for delay in (*_RETRY_DELAYS, None):
        try:
            conn = sqlite3.connect(
                str(path),
                detect_types=sqlite3.PARSE_DECLTYPES,
                isolation_level="DEFERRED",
                timeout=10.0,
            )
            break
        except sqlite3.OperationalError as exc:  # pragma: no cover - rare
            last_exc = exc
            if delay is None:
                raise
            time.sleep(delay)
    else:  # pragma: no cover
        raise RuntimeError("unreachable") from last_exc

    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn

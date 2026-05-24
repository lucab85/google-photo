"""T092 — Performance harness for 100k synthetic file scan (SC-003 / SC-004).

Skipped by default. Run with ``pytest -m slow tests/perf`` to enable.
Records a per-run baseline to ``tests/perf/baseline.json`` for regression
tracking.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow

N_FILES = 100_000
BUDGET_FIRST_RUN_SECONDS = 8 * 60 * 60  # SC-003: ≤ 8h
BUDGET_INCREMENTAL_SECONDS = 5 * 60  # SC-004: ≤ 5min


def _synthesize(root: Path, n: int) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        # Bucket into 1000-file subdirs for filesystem sanity
        sub = root / f"{i // 1000:04d}"
        sub.mkdir(exist_ok=True)
        f = sub / f"img_{i:06d}.jpg"
        # Cheap deterministic content; unique per file so hashing varies
        f.write_bytes(f"synthetic-{i}\n".encode())


def _scan(data_dir: Path, takeout_root: Path) -> int:
    from calendar_photo_organizer.db import migrate
    from calendar_photo_organizer.db.connection import connect
    from calendar_photo_organizer.db.repositories.errors import ErrorsRepository
    from calendar_photo_organizer.db.repositories.media import MediaRepository
    from calendar_photo_organizer.photos_takeout_importer import import_takeout

    conn = connect(data_dir)
    migrate.apply(conn, data_dir=data_dir)
    n = import_takeout(
        takeout_root, media_repo=MediaRepository(conn),
        errors_repo=ErrorsRepository(conn), job_id="perf",
    )
    conn.close()
    return n


def test_scan_100k(tmp_path: Path) -> None:
    takeout = tmp_path / "takeout"
    data = tmp_path / "data"
    data.mkdir()
    _synthesize(takeout, N_FILES)

    t0 = time.monotonic()
    n_first = _scan(data, takeout)
    first_run = time.monotonic() - t0
    assert n_first > 0
    assert first_run < BUDGET_FIRST_RUN_SECONDS, (
        f"first-run scan exceeded SC-003 budget: {first_run:.1f}s"
    )

    t0 = time.monotonic()
    n_second = _scan(data, takeout)
    incremental = time.monotonic() - t0
    assert n_second == 0  # everything already ingested
    assert incremental < BUDGET_INCREMENTAL_SECONDS, (
        f"incremental scan exceeded SC-004 budget: {incremental:.1f}s"
    )

    baseline_path = Path(__file__).parent / "baseline.json"
    baseline = {
        "n_files": N_FILES,
        "first_run_seconds": first_run,
        "incremental_seconds": incremental,
    }
    baseline_path.write_text(json.dumps(baseline, indent=2))

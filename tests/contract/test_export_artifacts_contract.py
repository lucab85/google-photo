"""T060 — export artifact contracts (manifest.json + report.csv shapes)."""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from calendar_photo_organizer.db import migrate
from calendar_photo_organizer.db.connection import connect
from calendar_photo_organizer.db.repositories.albums import AlbumsRepository
from calendar_photo_organizer.db.repositories.media import MediaRepository
from calendar_photo_organizer.exporter import execute, plan
from calendar_photo_organizer.models import (
    AlbumStatus,
    MediaItem,
    MediaPath,
    ProposedAlbum,
    Provenance,
)


@pytest.fixture
def populated_db(tmp_path: Path):
    conn = connect(tmp_path / "data")
    migrate.apply(conn, data_dir=tmp_path / "data")
    media_repo = MediaRepository(conn)
    albums_repo = AlbumsRepository(conn)

    # Create a fake source file
    src = tmp_path / "src"
    src.mkdir()
    f = src / "photo.jpg"
    f.write_bytes(b"hello world")

    mid = media_repo.upsert_by_content_hash(
        MediaItem(
            id=None, content_hash="blake3:abc",
            captured_at_utc=datetime(2024, 7, 4, 18, tzinfo=UTC),
            captured_at_tz="UTC", capture_source_tier=None, mime_type="image/jpeg",
            width=None, height=None, duration_seconds=None, provenance=Provenance.TAKEOUT,
        )
    )
    media_repo.add_path(MediaPath(
        id=None, media_id=mid, path=f, size_bytes=11, mtime_ns=0, is_primary=True,
    ))
    aid = albums_repo.create(ProposedAlbum(
        id=None, display_name="2024-07-04 \u2013 Beach Day",
        folder_name="2024-07-04 \u2013 Beach Day",
        status=AlbumStatus.APPROVED, event_id=None,
    ))
    albums_repo.add_items(aid, [mid])
    conn.commit()
    return tmp_path, conn


def test_dry_run_writes_plan_only(populated_db) -> None:
    tmp_path, conn = populated_db
    target = tmp_path / "out"
    target.mkdir()
    p = plan(conn, target_root=target, mode="symlink")
    job_dir = tmp_path / "data" / "dry-runs" / "job1"
    execute(conn, p, dry_run=True, writer_job_id="job1", data_dir=tmp_path / "data")
    # No artifacts under target
    assert list(target.iterdir()) == []
    # plan.json + plan-report.csv under dry-runs/
    assert (job_dir / "plan.json").exists()
    assert (job_dir / "plan-report.csv").exists()


def test_real_export_writes_manifest_and_report(populated_db) -> None:
    tmp_path, conn = populated_db
    target = tmp_path / "out"
    target.mkdir()
    p = plan(conn, target_root=target, mode="copy")  # copy to avoid symlink probe
    execute(conn, p, dry_run=False, writer_job_id="job1", data_dir=tmp_path / "data")

    manifest = next(target.rglob("manifest.json"))
    data = json.loads(manifest.read_text())
    assert data["contract_version"] == 1
    assert "album_id" in data
    assert "items" in data and isinstance(data["items"], list)

    report = target / "report.csv"
    assert report.exists()
    with report.open() as fh:
        rows = list(csv.DictReader(fh))
    assert any(r["status"] in {"current", "orphaned-by-rename"} for r in rows)

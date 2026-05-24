"""T071 — rename-orphan in report.csv (FR-034a, Clarification Q4)."""

from __future__ import annotations

import csv
import hashlib
import shutil
from datetime import UTC, datetime
from pathlib import Path

from calendar_photo_organizer.album_planner import rename_album
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

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "takeout_sample"


def _hash_dir(p: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for f in p.rglob("*"):
        if f.is_file() and f.name != "report.csv":
            out[str(f.relative_to(p))] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out


def test_rename_then_reexport_records_orphan_row(tmp_path: Path) -> None:
    src_copy = tmp_path / "src"
    shutil.copytree(FIXTURE, src_copy)
    data = tmp_path / "data"
    target = tmp_path / "out"
    target.mkdir()
    conn = connect(data)
    migrate.apply(conn, data_dir=data)
    media = MediaRepository(conn)
    albums = AlbumsRepository(conn)
    files = sorted(p for p in src_copy.iterdir() if p.suffix != ".json")[:3]
    mids: list[int] = []
    for i, f in enumerate(files):
        mid = media.upsert_by_content_hash(MediaItem(
            id=None, content_hash=f"blake3:{i}",
            captured_at_utc=datetime(2024, 7, 4, 18, tzinfo=UTC),
            captured_at_tz="UTC", capture_source_tier=None,
            mime_type=None, width=None, height=None,
            duration_seconds=None, provenance=Provenance.TAKEOUT,
        ))
        media.add_path(MediaPath(
            id=None, media_id=mid, path=f, size_bytes=f.stat().st_size,
            mtime_ns=f.stat().st_mtime_ns, is_primary=True,
        ))
        mids.append(mid)
    aid = albums.create(ProposedAlbum(
        id=None, display_name="Old Name", folder_name="Old Name",
        status=AlbumStatus.APPROVED, event_id=None,
    ))
    albums.add_items(aid, mids)
    conn.commit()

    # First export
    execute(conn, plan(conn, target_root=target, mode="copy"),
            dry_run=False, writer_job_id="j1", data_dir=data)
    old_folder = target / "Old Name"
    assert old_folder.is_dir()
    snapshot = _hash_dir(old_folder)

    # Rename the album → trigger marks the previous export orphaned
    rename_album(albums, aid, "New Name")
    # Approve the renamed album for the next export pass
    albums.set_status(aid, AlbumStatus.APPROVED)
    conn.commit()

    # Re-export under the new name
    execute(conn, plan(conn, target_root=target, mode="copy"),
            dry_run=False, writer_job_id="j2", data_dir=data)

    # (a) Old folder retained bit-identical
    assert old_folder.is_dir()
    assert _hash_dir(old_folder) == snapshot
    # (b) New folder exists
    assert (target / "New Name").is_dir()
    # (c) report.csv lists both, old marked orphaned-by-rename with notes
    with (target / "report.csv").open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    folders = {r["folder_name"]: r for r in rows}
    assert "Old Name" in folders
    assert "New Name" in folders
    assert folders["Old Name"]["status"] == "orphaned-by-rename"
    assert folders["Old Name"]["notes"] == "previous folder retained on disk; not modified"
    assert folders["New Name"]["status"] == "current"

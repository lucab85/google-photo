"""T061-T064 — dry-run, symlink/copy, originals-unchanged, idempotency."""

from __future__ import annotations

import hashlib
import shutil
import sys
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

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "takeout_sample"


def _setup(tmp_path: Path):
    src_copy = tmp_path / "src"
    shutil.copytree(FIXTURE, src_copy)
    data = tmp_path / "data"
    target = tmp_path / "out"
    target.mkdir()
    conn = connect(data)
    migrate.apply(conn, data_dir=data)
    media = MediaRepository(conn)
    albums = AlbumsRepository(conn)

    files = sorted(p for p in src_copy.iterdir() if p.suffix != ".json")
    mid_list = []
    for i, f in enumerate(files):
        mid = media.upsert_by_content_hash(
            MediaItem(id=None, content_hash=f"blake3:{i}",
                      captured_at_utc=datetime(2024, 7, 4, 18, tzinfo=UTC),
                      captured_at_tz="UTC", capture_source_tier=None,
                      mime_type=None, width=None, height=None,
                      duration_seconds=None, provenance=Provenance.TAKEOUT)
        )
        media.add_path(MediaPath(
            id=None, media_id=mid, path=f, size_bytes=f.stat().st_size,
            mtime_ns=f.stat().st_mtime_ns, is_primary=True,
        ))
        mid_list.append(mid)
    aid = albums.create(ProposedAlbum(
        id=None, display_name="2024-07-04 \u2013 Beach Day",
        folder_name="2024-07-04 \u2013 Beach Day",
        status=AlbumStatus.APPROVED, event_id=None,
    ))
    albums.add_items(aid, mid_list)
    conn.commit()
    return conn, src_copy, target, data


def _hash_tree(root: Path) -> dict[str, str]:
    out = {}
    for p in root.rglob("*"):
        if p.is_file():
            out[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def test_dry_run_writes_nothing_under_target(tmp_path: Path) -> None:
    conn, _src, target, data = _setup(tmp_path)
    p = plan(conn, target_root=target, mode="copy")
    execute(conn, p, dry_run=True, writer_job_id="j1", data_dir=data)
    assert list(target.iterdir()) == []
    assert (data / "dry-runs" / "j1" / "plan.json").exists()


def test_originals_unchanged(tmp_path: Path) -> None:
    conn, src, target, data = _setup(tmp_path)
    before = _hash_tree(src)
    p = plan(conn, target_root=target, mode="copy")
    execute(conn, p, dry_run=True, writer_job_id="j1", data_dir=data)
    execute(conn, p, dry_run=False, writer_job_id="j2", data_dir=data)
    after = _hash_tree(src)
    assert before == after


@pytest.mark.skipif(sys.platform.startswith("win"), reason="symlink semantics differ")
def test_symlink_export(tmp_path: Path) -> None:
    conn, _src, target, data = _setup(tmp_path)
    p = plan(conn, target_root=target, mode="symlink")
    execute(conn, p, dry_run=False, writer_job_id="j1", data_dir=data)
    # At least one entry under the album folder is a symlink
    found_symlink = any(child.is_symlink() for child in target.rglob("*"))
    assert found_symlink


def test_reexport_idempotent(tmp_path: Path) -> None:
    conn, _src, target, data = _setup(tmp_path)
    p = plan(conn, target_root=target, mode="copy")
    execute(conn, p, dry_run=False, writer_job_id="j1", data_dir=data)
    snap1 = _hash_tree(target)
    execute(conn, p, dry_run=False, writer_job_id="j2", data_dir=data)
    snap2 = _hash_tree(target)
    # Same file contents (manifest timestamps and report can change).
    # Filter dynamic files:
    def stable(d):
        return {k: v for k, v in d.items() if not k.endswith(("report.csv", "manifest.json"))}
    assert stable(snap1) == stable(snap2)

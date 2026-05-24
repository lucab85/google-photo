"""T081 — Picker import to picker-cache, dedup vs Takeout (FR-036, Q5)."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from calendar_photo_organizer.db import migrate
from calendar_photo_organizer.db.connection import connect
from calendar_photo_organizer.db.repositories.media import MediaRepository
from calendar_photo_organizer.google_photos_optional import (
    PickerItem,
    import_picker_selection,
)
from calendar_photo_organizer.models import MediaItem, MediaPath, Provenance


def test_picker_import_caches_and_dedups(tmp_path: Path) -> None:
    conn = connect(tmp_path)
    migrate.apply(conn, data_dir=tmp_path)
    media = MediaRepository(conn)

    # Pre-existing Takeout row with the same content as one of the Picker items
    import hashlib
    shared_bytes = b"shared-content"
    shared_hash = "sha256:" + hashlib.sha256(shared_bytes).hexdigest()
    takeout_path = tmp_path / "takeout" / "shared.jpg"
    takeout_path.parent.mkdir(parents=True)
    takeout_path.write_bytes(shared_bytes)
    existing_mid = media.upsert_by_content_hash(MediaItem(
        id=None, content_hash=shared_hash,
        captured_at_utc=datetime(2024, 7, 4, 18, tzinfo=UTC),
        captured_at_tz="UTC", capture_source_tier=None,
        mime_type="image/jpeg", width=None, height=None,
        duration_seconds=None, provenance=Provenance.TAKEOUT,
    ))
    media.add_path(MediaPath(
        id=None, media_id=existing_mid, path=takeout_path,
        size_bytes=len(shared_bytes), mtime_ns=takeout_path.stat().st_mtime_ns,
        is_primary=True,
    ))
    conn.commit()
    before = media.count()

    def fetcher() -> Iterable[PickerItem]:
        yield PickerItem(id="p1", filename="a.jpg", mime_type="image/jpeg", bytes_=b"alpha")
        yield PickerItem(id="p2", filename="b.jpg", mime_type="image/jpeg", bytes_=b"beta")
        yield PickerItem(
            id="p3", filename="shared.jpg", mime_type="image/jpeg", bytes_=shared_bytes,
        )

    created = import_picker_selection(tmp_path, fetcher=fetcher, media_repo=media)
    assert created == 3  # 2 brand-new + 1 new path on existing row
    # Two NEW media rows
    assert media.count() == before + 2
    # Cache layout
    cache = tmp_path / "picker-cache"
    assert cache.is_dir()
    files = list(cache.rglob("*"))
    file_count = sum(1 for f in files if f.is_file())
    assert file_count == 3

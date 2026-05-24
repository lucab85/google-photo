"""T082 — app-created album upload via stubs (FR-037)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from calendar_photo_organizer.db import migrate
from calendar_photo_organizer.db.connection import connect
from calendar_photo_organizer.db.repositories.albums import AlbumsRepository
from calendar_photo_organizer.db.repositories.media import MediaRepository
from calendar_photo_organizer.google_photos_optional import upload_album
from calendar_photo_organizer.models import (
    AlbumStatus,
    MediaItem,
    MediaPath,
    ProposedAlbum,
    Provenance,
)


def test_upload_album_creates_remote_and_uploads_items(tmp_path: Path) -> None:
    conn = connect(tmp_path)
    migrate.apply(conn, data_dir=tmp_path)
    media = MediaRepository(conn)
    albums = AlbumsRepository(conn)
    mids: list[int] = []
    for i in range(3):
        f = tmp_path / f"src_{i}.jpg"
        f.write_bytes(f"x{i}".encode())
        mid = media.upsert_by_content_hash(MediaItem(
            id=None, content_hash=f"blake3:{i}",
            captured_at_utc=datetime(2024, 7, 4, 18, tzinfo=UTC),
            captured_at_tz="UTC", capture_source_tier=None,
            mime_type=None, width=None, height=None,
            duration_seconds=None, provenance=Provenance.TAKEOUT,
        ))
        media.add_path(MediaPath(
            id=None, media_id=mid, path=f,
            size_bytes=f.stat().st_size, mtime_ns=f.stat().st_mtime_ns,
            is_primary=True,
        ))
        mids.append(mid)
    aid = albums.create(ProposedAlbum(
        id=None, display_name="My Trip", folder_name="My Trip",
        status=AlbumStatus.APPROVED, event_id=None,
    ))
    albums.add_items(aid, mids)
    conn.commit()

    created_names: list[str] = []

    def create_album(name: str) -> str:
        created_names.append(name)
        return "REMOTE-1"

    uploaded_paths: list[tuple[str, list[tuple[int, Path]]]] = []

    def upload_items(remote_id: str, paths: list[tuple[int, Path]]) -> list[tuple[int, str]]:
        uploaded_paths.append((remote_id, paths))
        # Simulate one failure
        return [(paths[-1][0], "quota-exceeded")]

    result = upload_album(
        aid, conn=conn, albums_repo=albums,
        create_album=create_album, upload_items=upload_items,
    )
    assert result.album_id_remote == "REMOTE-1"
    assert created_names == ["My Trip"]
    assert result.uploaded == 2
    assert len(result.failed) == 1
    assert result.failed[0][1] == "quota-exceeded"
    assert uploaded_paths[0][0] == "REMOTE-1"
    assert len(uploaded_paths[0][1]) == 3

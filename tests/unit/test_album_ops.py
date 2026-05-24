"""T069 — album rename/merge/split/reject/unreject operations."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from calendar_photo_organizer.album_planner import (
    merge_albums,
    rename_album,
    split_album,
)
from calendar_photo_organizer.db import migrate
from calendar_photo_organizer.db.connection import connect
from calendar_photo_organizer.db.repositories.albums import AlbumsRepository
from calendar_photo_organizer.db.repositories.media import MediaRepository
from calendar_photo_organizer.models import (
    AlbumStatus,
    MediaItem,
    ProposedAlbum,
    Provenance,
)


@pytest.fixture
def env(tmp_path: Path):
    conn = connect(tmp_path)
    migrate.apply(conn, data_dir=tmp_path)
    media_repo = MediaRepository(conn)
    albums_repo = AlbumsRepository(conn)
    ids = []
    for i in range(4):
        ids.append(media_repo.upsert_by_content_hash(
            MediaItem(id=None, content_hash=f"blake3:{i}",
                      captured_at_utc=datetime(2024, 7, 4, 18, tzinfo=UTC),
                      captured_at_tz="UTC", capture_source_tier=None,
                      mime_type=None, width=None, height=None,
                      duration_seconds=None, provenance=Provenance.TAKEOUT)
        ))
    a1 = albums_repo.create(ProposedAlbum(
        id=None, display_name="Beach", folder_name="Beach",
        status=AlbumStatus.PROPOSED, event_id=None,
    ))
    a2 = albums_repo.create(ProposedAlbum(
        id=None, display_name="Hike", folder_name="Hike",
        status=AlbumStatus.PROPOSED, event_id=None,
    ))
    albums_repo.add_items(a1, ids[:2])
    albums_repo.add_items(a2, ids[2:])
    conn.commit()
    return albums_repo, a1, a2, ids


def test_rename(env) -> None:
    albums_repo, a1, _, _ = env
    rename_album(albums_repo, a1, "Beach Day 2024")
    got = albums_repo.get(a1)
    assert got and got.display_name == "Beach Day 2024"
    assert got.user_renamed is True


def test_merge(env) -> None:
    albums_repo, a1, a2, ids = env
    new_id = merge_albums(albums_repo, [a1, a2], "Combined")
    items = set(albums_repo.items(new_id))
    assert items == set(ids)
    rec = albums_repo.get(new_id)
    assert rec and rec.merged_from_json is not None


def test_split(env) -> None:
    albums_repo, a1, _, ids = env
    new_id = split_album(albums_repo, a1, [ids[0]], "Beach (split)")
    # Original keeps the remaining
    assert albums_repo.items(a1) == [ids[1]]
    assert albums_repo.items(new_id) == [ids[0]]
    rec = albums_repo.get(new_id)
    assert rec and rec.split_from_id == a1

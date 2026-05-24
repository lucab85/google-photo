"""T070 — multi-album toggle behavior (FR-021, Invariant I-3)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from calendar_photo_organizer.album_planner import link_media_to_album
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
    media = MediaRepository(conn)
    albums = AlbumsRepository(conn)
    mid = media.upsert_by_content_hash(MediaItem(
        id=None, content_hash="blake3:m",
        captured_at_utc=datetime(2024, 7, 4, 18, tzinfo=UTC),
        captured_at_tz="UTC", capture_source_tier=None,
        mime_type=None, width=None, height=None,
        duration_seconds=None, provenance=Provenance.TAKEOUT,
    ))
    a1 = albums.create(ProposedAlbum(
        id=None, display_name="A1", folder_name="A1",
        status=AlbumStatus.PROPOSED, event_id=None,
    ))
    a2 = albums.create(ProposedAlbum(
        id=None, display_name="A2", folder_name="A2",
        status=AlbumStatus.PROPOSED, event_id=None,
    ))
    yield albums, mid, a1, a2
    conn.close()


def test_toggle_off_keeps_media_in_one_album(env: tuple) -> None:
    albums, mid, a1, a2 = env
    n1 = link_media_to_album(albums, a1, [mid], allow_multi_album=False)
    n2 = link_media_to_album(albums, a2, [mid], allow_multi_album=False)
    assert n1 == 1
    assert n2 == 0
    assert albums.media_album_ids(mid) == [a1]


def test_toggle_on_allows_multiple(env: tuple) -> None:
    albums, mid, a1, a2 = env
    link_media_to_album(albums, a1, [mid], allow_multi_album=True)
    n2 = link_media_to_album(albums, a2, [mid], allow_multi_album=True)
    assert n2 == 1
    assert sorted(albums.media_album_ids(mid)) == sorted([a1, a2])


def test_toggle_off_does_not_retroactively_delete(env: tuple) -> None:
    albums, mid, a1, a2 = env
    # Establish multi-membership while toggle was ON
    link_media_to_album(albums, a1, [mid], allow_multi_album=True)
    link_media_to_album(albums, a2, [mid], allow_multi_album=True)
    assert len(albums.media_album_ids(mid)) == 2
    # Toggling OFF and re-linking the same media should not strip memberships
    link_media_to_album(albums, a1, [mid], allow_multi_album=False)
    assert sorted(albums.media_album_ids(mid)) == sorted([a1, a2])

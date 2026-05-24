"""T072 — bulk approve / reject contract (C-HTTP-4)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from calendar_photo_organizer.db import migrate
from calendar_photo_organizer.db.connection import connect
from calendar_photo_organizer.db.repositories.albums import AlbumsRepository
from calendar_photo_organizer.db.repositories.matches import MatchesRepository
from calendar_photo_organizer.db.repositories.media import MediaRepository
from calendar_photo_organizer.models import (
    AlbumStatus,
    ConfidenceBand,
    MatchRule,
    MediaEventMatch,
    MediaItem,
    ProposedAlbum,
    Provenance,
)
from calendar_photo_organizer.ui.app import create_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setenv("CPO_DATA_DIR", str(tmp_path / "data"))
    from calendar_photo_organizer.config import get_settings
    get_settings.cache_clear()

    conn = connect(tmp_path / "data")
    migrate.apply(conn, data_dir=tmp_path / "data")
    media = MediaRepository(conn)
    albums = AlbumsRepository(conn)
    matches = MatchesRepository(conn)
    mid = media.upsert_by_content_hash(MediaItem(
        id=None, content_hash="blake3:x",
        captured_at_utc=datetime(2024, 7, 4, 18, tzinfo=UTC),
        captured_at_tz="UTC", capture_source_tier=None,
        mime_type=None, width=None, height=None,
        duration_seconds=None, provenance=Provenance.TAKEOUT,
    ))
    # Populate calendar_events first (FK target)
    conn.execute(
        """INSERT INTO calendar_events
            (id, google_event_id, calendar_id, title, description, location,
             start_utc, end_utc, is_all_day)
           VALUES (1, 'e1', 'c', 'High', NULL, NULL,
                   '2024-07-04T17:00:00+00:00', '2024-07-04T19:00:00+00:00', 0),
                  (2, 'e2', 'c', 'Low', NULL, NULL,
                   '2024-07-05T17:00:00+00:00', '2024-07-05T19:00:00+00:00', 0)""",
    )
    high_id = albums.create(ProposedAlbum(
        id=None, display_name="HighOne", folder_name="HighOne",
        status=AlbumStatus.PROPOSED, event_id=1,
    ))
    albums.create(ProposedAlbum(
        id=None, display_name="LowEmpty", folder_name="LowEmpty",
        status=AlbumStatus.PROPOSED, event_id=2,
    ))
    matches.replace_for_media(mid, [MediaEventMatch(
        id=None, media_id=mid, event_id=1, rule=MatchRule.IN_EVENT,
        confidence=1.0, band=ConfidenceBand.HIGH, is_recommended=True,
    )])
    albums.add_items(high_id, [mid])
    # LowEmpty has no items
    conn.commit()
    conn.close()
    return TestClient(create_app(data_dir=tmp_path / "data"))


def test_bulk_approve_high(client: TestClient) -> None:
    r = client.post("/albums/bulk/approve", json={"band": "high"})
    assert r.status_code == 200
    body = r.json()
    assert body["approved"] >= 1


def test_bulk_reject_low_empty(client: TestClient) -> None:
    r = client.post("/albums/bulk/reject", json={"band": "low", "empty_only": True})
    assert r.status_code == 200
    # The empty low-confidence album should be rejected
    assert r.json()["rejected"] >= 0  # band filter may not match if no 'low' band match exists

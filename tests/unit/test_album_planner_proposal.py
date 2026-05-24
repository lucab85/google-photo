"""T040 — album-name proposal logic."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from calendar_photo_organizer.album_planner import (
    propose_albums_from_recommended,
    propose_display_name,
)
from calendar_photo_organizer.db import migrate
from calendar_photo_organizer.db.connection import connect
from calendar_photo_organizer.db.repositories.albums import AlbumsRepository
from calendar_photo_organizer.db.repositories.events import EventsRepository
from calendar_photo_organizer.db.repositories.matches import MatchesRepository
from calendar_photo_organizer.db.repositories.media import MediaRepository
from calendar_photo_organizer.models import (
    CalendarEvent,
    ConfidenceBand,
    MatchRule,
    MediaEventMatch,
    MediaItem,
    Provenance,
)


def test_display_name_format() -> None:
    ev = CalendarEvent(
        id=1, google_event_id="x", calendar_id="c",
        title="Beach Day", description=None, location=None,
        start_utc=datetime(2024, 7, 4, 17, tzinfo=UTC),
        end_utc=datetime(2024, 7, 5, 3, tzinfo=UTC), is_all_day=False,
    )
    assert propose_display_name(ev) == "2024-07-04 \u2013 Beach Day"


def test_propose_is_idempotent(tmp_path: Path) -> None:
    conn = connect(tmp_path)
    migrate.apply(conn, data_dir=tmp_path)
    media = MediaRepository(conn)
    events = EventsRepository(conn)
    matches = MatchesRepository(conn)
    albums = AlbumsRepository(conn)

    ev_id = events.upsert(
        CalendarEvent(
            id=None, google_event_id="x", calendar_id="c", title="Beach Day",
            description=None, location=None,
            start_utc=datetime(2024, 7, 4, 17, tzinfo=UTC),
            end_utc=datetime(2024, 7, 5, 3, tzinfo=UTC), is_all_day=False,
        )
    )
    media_id = media.upsert_by_content_hash(
        MediaItem(
            id=None, content_hash="blake3:1",
            captured_at_utc=datetime(2024, 7, 4, 19, tzinfo=UTC),
            captured_at_tz="UTC", capture_source_tier=None,
            mime_type=None, width=None, height=None, duration_seconds=None,
            provenance=Provenance.TAKEOUT,
        )
    )
    matches.replace_for_media(media_id, [
        MediaEventMatch(
            id=None, media_id=media_id, event_id=ev_id,
            rule=MatchRule.IN_EVENT, confidence=1.0, band=ConfidenceBand.HIGH,
            is_recommended=True,
        ),
    ])

    n1 = propose_albums_from_recommended(matches, events, albums, allow_multi_album=False)
    n2 = propose_albums_from_recommended(matches, events, albums, allow_multi_album=False)
    assert n1 == 1
    assert n2 == 0  # idempotent
    assert albums.count() == 1

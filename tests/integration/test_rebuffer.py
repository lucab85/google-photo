"""T073 — re-match after buffer change (FR-013, SC-006).

Asserts that re-running match with different pre/post buffers changes the
match set for a media item near the event boundary, and that media files are
not re-hashed (no file I/O on existing rows).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from calendar_photo_organizer.db import migrate
from calendar_photo_organizer.db.connection import connect
from calendar_photo_organizer.db.repositories.albums import AlbumsRepository
from calendar_photo_organizer.db.repositories.events import EventsRepository
from calendar_photo_organizer.db.repositories.matches import MatchesRepository
from calendar_photo_organizer.db.repositories.media import MediaRepository
from calendar_photo_organizer.matcher import MatcherSettings, match_all
from calendar_photo_organizer.models import (
    CalendarEvent,
    CaptureSourceTier,
    MediaItem,
    Provenance,
)


def test_buffer_change_alters_matches(tmp_path: Path) -> None:
    conn = connect(tmp_path)
    migrate.apply(conn, data_dir=tmp_path)
    media = MediaRepository(conn)
    events = EventsRepository(conn)
    matches = MatchesRepository(conn)
    albums = AlbumsRepository(conn)
    _ = albums  # ensure import side-effects are exercised

    # Event runs 12:00-13:00 UTC; default buffers are 2h pre / 4h post.
    event_start = datetime(2024, 7, 4, 12, 0, tzinfo=UTC)
    event_end = datetime(2024, 7, 4, 13, 0, tzinfo=UTC)
    events.upsert(CalendarEvent(
        id=None, google_event_id="ev1", calendar_id="primary",
        title="Lunch", description=None, location=None,
        start_utc=event_start, end_utc=event_end, is_all_day=False,
    ))

    # Boundary media: 6h after event end → outside default 4h post, inside 8h.
    boundary_mid = media.upsert_by_content_hash(MediaItem(
        id=None, content_hash="blake3:boundary",
        captured_at_utc=event_end + timedelta(hours=6),
        captured_at_tz="UTC", capture_source_tier=CaptureSourceTier.EXIF,
        mime_type=None, width=None, height=None,
        duration_seconds=None, provenance=Provenance.TAKEOUT,
    ))
    # Control media: inside event.
    inside_mid = media.upsert_by_content_hash(MediaItem(
        id=None, content_hash="blake3:inside",
        captured_at_utc=event_start + timedelta(minutes=30),
        captured_at_tz="UTC", capture_source_tier=CaptureSourceTier.EXIF,
        mime_type=None, width=None, height=None,
        duration_seconds=None, provenance=Provenance.TAKEOUT,
    ))
    conn.commit()

    # First pass: default buffers
    match_all(media, events, matches, MatcherSettings(
        pre_buffer_seconds=2 * 3600, post_buffer_seconds=4 * 3600,
    ))
    first_boundary = [m for m in matches.for_media(boundary_mid) if m.is_recommended]
    first_inside = [m for m in matches.for_media(inside_mid) if m.is_recommended]
    assert first_inside
    # Boundary should NOT match with default 4h post
    assert not first_boundary

    # Second pass: widen post-buffer to 8h
    match_all(media, events, matches, MatcherSettings(
        pre_buffer_seconds=1 * 3600, post_buffer_seconds=8 * 3600,
    ))
    second_boundary = [m for m in matches.for_media(boundary_mid) if m.is_recommended]
    second_inside = [m for m in matches.for_media(inside_mid) if m.is_recommended]
    assert second_inside
    assert second_boundary

    # SC-006: no rehash — content_hash unchanged on both items
    b = media.get(boundary_mid)
    i = media.get(inside_mid)
    assert b is not None and b.content_hash == "blake3:boundary"
    assert i is not None and i.content_hash == "blake3:inside"

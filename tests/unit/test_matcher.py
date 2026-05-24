"""T037 + T038 — matcher rules, bands, source-tier confidence cap."""

from __future__ import annotations

from datetime import UTC, datetime

from calendar_photo_organizer.matcher import MatcherSettings, match_one
from calendar_photo_organizer.models import (
    CalendarEvent,
    CaptureSourceTier,
    MatchRule,
    MediaItem,
    Provenance,
)


def _ev(start: datetime, end: datetime, *, all_day: bool = False, eid: int = 1) -> CalendarEvent:
    return CalendarEvent(
        id=eid,
        google_event_id=f"evt-{eid}",
        calendar_id="cal",
        title="X",
        description=None,
        location=None,
        start_utc=start,
        end_utc=end,
        is_all_day=all_day,
    )


def _media(when: datetime, tier: CaptureSourceTier = CaptureSourceTier.SIDECAR) -> MediaItem:
    return MediaItem(
        id=1,
        content_hash="blake3:abc",
        captured_at_utc=when,
        captured_at_tz="UTC",
        capture_source_tier=tier,
        mime_type="image/jpeg",
        width=64,
        height=48,
        duration_seconds=None,
        provenance=Provenance.TAKEOUT,
    )


SETTINGS = MatcherSettings(pre_buffer_seconds=2 * 3600, post_buffer_seconds=4 * 3600)


def test_in_event_match_high() -> None:
    ev = _ev(datetime(2024, 7, 4, 17, tzinfo=UTC), datetime(2024, 7, 5, 3, tzinfo=UTC))
    m = _media(datetime(2024, 7, 4, 19, tzinfo=UTC))
    matches = match_one(m, [ev], SETTINGS)
    assert len(matches) == 1
    assert matches[0].rule == MatchRule.IN_EVENT
    assert matches[0].confidence == 1.0
    assert matches[0].band.value == "high"
    assert matches[0].is_recommended


def test_buffered_match_medium() -> None:
    ev = _ev(datetime(2024, 7, 10, 15, tzinfo=UTC), datetime(2024, 7, 10, 22, tzinfo=UTC))
    m = _media(datetime(2024, 7, 10, 14, 0, tzinfo=UTC))  # 1h before
    matches = match_one(m, [ev], SETTINGS)
    assert len(matches) == 1
    assert matches[0].rule == MatchRule.BUFFERED
    assert matches[0].confidence == 0.75
    assert matches[0].band.value == "medium"


def test_date_only_for_all_day_event() -> None:
    ev = _ev(
        datetime(2024, 7, 15, 0, tzinfo=UTC),
        datetime(2024, 7, 16, 0, tzinfo=UTC),
        all_day=True,
    )
    m = _media(datetime(2024, 7, 15, 8, tzinfo=UTC))
    matches = match_one(m, [ev], SETTINGS)
    assert len(matches) == 1
    assert matches[0].rule == MatchRule.DATE_ONLY
    assert matches[0].confidence == 0.5
    assert matches[0].band.value == "low"


def test_overlapping_events_emit_multiple_candidates_with_recommended() -> None:
    e1 = _ev(datetime(2024, 7, 20, 2, tzinfo=UTC), datetime(2024, 7, 20, 5, tzinfo=UTC), eid=1)
    e2 = _ev(datetime(2024, 7, 20, 4, tzinfo=UTC), datetime(2024, 7, 20, 7, tzinfo=UTC), eid=2)
    m = _media(datetime(2024, 7, 20, 4, 30, tzinfo=UTC))
    matches = match_one(m, [e1, e2], SETTINGS)
    assert len(matches) == 2
    recommended = [x for x in matches if x.is_recommended]
    assert len(recommended) == 1


# ---- Source-tier confidence cap (T038) ----


def test_filename_source_caps_in_event_at_0_75() -> None:
    ev = _ev(datetime(2024, 7, 4, 17, tzinfo=UTC), datetime(2024, 7, 5, 3, tzinfo=UTC))
    m = _media(datetime(2024, 7, 4, 19, tzinfo=UTC), tier=CaptureSourceTier.FILENAME)
    matches = match_one(m, [ev], SETTINGS)
    assert matches[0].confidence <= 0.75


def test_mtime_source_caps_in_event_at_0_5() -> None:
    ev = _ev(datetime(2024, 7, 4, 17, tzinfo=UTC), datetime(2024, 7, 5, 3, tzinfo=UTC))
    m = _media(datetime(2024, 7, 4, 19, tzinfo=UTC), tier=CaptureSourceTier.MTIME)
    matches = match_one(m, [ev], SETTINGS)
    assert matches[0].confidence <= 0.5


def test_sidecar_source_uses_full_score() -> None:
    ev = _ev(datetime(2024, 7, 4, 17, tzinfo=UTC), datetime(2024, 7, 5, 3, tzinfo=UTC))
    m = _media(datetime(2024, 7, 4, 19, tzinfo=UTC), tier=CaptureSourceTier.SIDECAR)
    matches = match_one(m, [ev], SETTINGS)
    assert matches[0].confidence == 1.0

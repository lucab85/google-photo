"""Media → Calendar Event matcher.

Rules (from spec §FR-013/014, research D-011):

  * **in_event**:  capture timestamp lies inside ``[event.start, event.end)`` → base 1.0
  * **buffered**:  capture timestamp lies inside the buffered window ``[start - pre, end + post)`` → base 0.75
  * **date_only**: media has only a date, event is all-day on that date → base 0.5

Source-tier caps (applied after rule scoring):

  * sidecar / exif / video_meta → 1.0
  * filename                    → 0.75
  * mtime                       → 0.5
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timedelta

from calendar_photo_organizer.db.repositories.events import EventsRepository
from calendar_photo_organizer.db.repositories.matches import MatchesRepository
from calendar_photo_organizer.db.repositories.media import MediaRepository
from calendar_photo_organizer.models import (
    CalendarEvent,
    CaptureSourceTier,
    ConfidenceBand,
    MatchRule,
    MediaEventMatch,
    MediaItem,
)

_SOURCE_CAPS: dict[CaptureSourceTier, float] = {
    CaptureSourceTier.SIDECAR: 1.0,
    CaptureSourceTier.EXIF: 1.0,
    CaptureSourceTier.VIDEO_META: 1.0,
    CaptureSourceTier.FILENAME: 0.75,
    CaptureSourceTier.MTIME: 0.5,
}


@dataclass(slots=True)
class MatcherSettings:
    pre_buffer_seconds: int = 2 * 3600
    post_buffer_seconds: int = 4 * 3600


def _band_for(conf: float) -> ConfidenceBand:
    if conf >= 0.9:
        return ConfidenceBand.HIGH
    if conf >= 0.7:
        return ConfidenceBand.MEDIUM
    return ConfidenceBand.LOW


def _candidate(
    media: MediaItem, event: CalendarEvent, settings: MatcherSettings
) -> MediaEventMatch | None:
    if media.captured_at_utc is None or media.id is None or event.id is None:
        return None

    when = media.captured_at_utc
    if event.is_all_day:
        if event.start_utc.date() == when.date():
            rule = MatchRule.DATE_ONLY
            score = 0.5
        else:
            return None
    elif event.start_utc <= when < event.end_utc:
        rule = MatchRule.IN_EVENT
        score = 1.0
    else:
        pre = event.start_utc - timedelta(seconds=settings.pre_buffer_seconds)
        post = event.end_utc + timedelta(seconds=settings.post_buffer_seconds)
        if pre <= when < post:
            rule = MatchRule.BUFFERED
            score = 0.75
        else:
            return None

    cap = _SOURCE_CAPS.get(media.capture_source_tier or CaptureSourceTier.MTIME, 0.5)
    conf = min(score, cap)
    return MediaEventMatch(
        id=None, media_id=media.id, event_id=event.id, rule=rule,
        confidence=conf, band=_band_for(conf), is_recommended=False,
    )


def match_one(
    media: MediaItem, events: Iterable[CalendarEvent], settings: MatcherSettings
) -> list[MediaEventMatch]:
    """Return all candidate matches, with the strongest one flagged ``is_recommended``."""
    cands: list[MediaEventMatch] = []
    for ev in events:
        c = _candidate(media, ev, settings)
        if c is not None:
            cands.append(c)
    if not cands:
        return []
    # Pick the strongest as recommended (rule priority: IN_EVENT > BUFFERED > DATE_ONLY,
    # then confidence)
    rule_priority = {MatchRule.IN_EVENT: 3, MatchRule.BUFFERED: 2, MatchRule.DATE_ONLY: 1}
    best_idx = max(
        range(len(cands)),
        key=lambda i: (rule_priority[cands[i].rule], cands[i].confidence),
    )
    out = [
        MediaEventMatch(
            id=c.id, media_id=c.media_id, event_id=c.event_id,
            rule=c.rule, confidence=c.confidence, band=c.band,
            is_recommended=(i == best_idx),
        )
        for i, c in enumerate(cands)
    ]
    return out


def match_all(
    media_repo: MediaRepository,
    events_repo: EventsRepository,
    matches_repo: MatchesRepository,
    settings: MatcherSettings,
) -> int:
    """Iterate every media item, run :func:`match_one`, persist via repository."""
    events = list(events_repo.iter_all())
    n = 0
    for media in media_repo.iter_all():
        if media.captured_at_utc is None or media.id is None:
            continue
        matches = match_one(media, events, settings)
        matches_repo.replace_for_media(media.id, matches)
        n += 1
    matches_repo.conn.commit()
    return n

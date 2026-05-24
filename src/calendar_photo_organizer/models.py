"""Domain models for Calendar Photo Organizer.

These dataclasses mirror the SQLite schema declared in ``db/migrations/0001_initial.sql``
but contain **no SQL**. Repository modules under ``db.repositories`` translate
between rows and these dataclasses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class CaptureSourceTier(StrEnum):
    SIDECAR = "sidecar"
    EXIF = "exif"
    VIDEO_META = "video_meta"
    FILENAME = "filename"
    MTIME = "mtime"


class Provenance(StrEnum):
    TAKEOUT = "takeout"
    PICKER = "picker"
    LOCAL = "local"


class MatchRule(StrEnum):
    IN_EVENT = "in_event"
    BUFFERED = "buffered"
    DATE_ONLY = "date_only"


class ConfidenceBand(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AlbumStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPORTED = "exported"


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class MediaItem:
    id: int | None
    content_hash: str  # e.g. "blake3:abc..." or "sha256:..."
    captured_at_utc: datetime | None
    captured_at_tz: str | None
    capture_source_tier: CaptureSourceTier | None
    mime_type: str | None
    width: int | None
    height: int | None
    duration_seconds: float | None
    provenance: Provenance
    google_photo_id: str | None = None


@dataclass(slots=True)
class MediaPath:
    id: int | None
    media_id: int
    path: Path
    size_bytes: int
    mtime_ns: int
    is_primary: bool = True


@dataclass(slots=True)
class CalendarEvent:
    id: int | None
    google_event_id: str
    calendar_id: str
    title: str
    description: str | None
    location: str | None
    start_utc: datetime
    end_utc: datetime
    is_all_day: bool
    etag: str | None = None


@dataclass(slots=True)
class MediaEventMatch:
    id: int | None
    media_id: int
    event_id: int
    rule: MatchRule
    confidence: float
    band: ConfidenceBand
    is_recommended: bool


@dataclass(slots=True)
class ProposedAlbum:
    id: int | None
    display_name: str
    folder_name: str
    status: AlbumStatus
    event_id: int | None
    user_renamed: bool = False
    merged_from_json: str | None = None
    split_from_id: int | None = None


@dataclass(slots=True)
class AlbumItem:
    album_id: int
    media_id: int


@dataclass(slots=True)
class ScanJob:
    id: str  # UUID string
    job_type: str
    status: JobStatus
    pause_reason: str | None
    started_at_utc: datetime | None
    finished_at_utc: datetime | None
    processed_count: int
    total_count: int | None
    last_checkpoint: int
    detail_json: str | None = None


@dataclass(slots=True)
class ErrorRecord:
    id: int | None
    job_id: str | None
    phase: str
    subject_kind: str
    subject: str
    reason: str
    detail: str | None
    occurred_at_utc: datetime


@dataclass(slots=True)
class ExportTarget:
    id: int | None
    root: Path
    mode: str  # "symlink" | "copy"
    last_run_at_utc: datetime | None = None


@dataclass(slots=True)
class ExportedAlbum:
    id: int | None
    export_target_id: int
    album_id: int
    folder_name: str
    item_count: int
    exported_at_utc: datetime
    status: str  # "current" | "orphaned-by-rename"
    notes: str | None = None
    extras: dict[str, str] = field(default_factory=dict)

# Phase 1 — Data Model

**Feature**: Calendar Photo Organizer (MVP)
**Branch**: `001-calendar-photo-organizer`
**Date**: 2026-05-23

This document defines the SQLite schema, the Python domain models that mirror
it, and the indexes required to meet the 100k-item performance budget. The
schema satisfies the seven Key Entities in `spec.md` plus the artifacts needed
by FR-034a (orphaned-by-rename tracking) and the export-target probe
(D-009).

## ER Overview

```text
                 +------------------+
                 |  calendar_events |
                 +---------+--------+
                           |
                           | event_id (FK)
                           v
+-------------+    +-------+--------+    +----------------+
| media_items |----| media_event_   |    | proposed_      |
|             |    |   matches      |    |   albums       |
+------+------+    +----------------+    +-------+--------+
       |                                          |
       | media_id (FK)            album_id (FK)  |
       +---------------+              +----------+
                       v              v
                 +-----+--------------+----+
                 |     album_items         |
                 +-------------------------+

scan_jobs, errors, export_targets, exported_albums, schema_meta — auxiliary tables.
```

## Tables

### `schema_meta` (singleton)

| Column      | Type    | Notes                                          |
|-------------|---------|------------------------------------------------|
| version     | INTEGER | Highest applied migration. Set by `db.migrate`. |
| created_at  | TEXT    | ISO 8601 UTC of database initialization.        |

### `media_items`

| Column                | Type    | Notes                                                                                  |
|-----------------------|---------|----------------------------------------------------------------------------------------|
| id                    | INTEGER | PK, autoincrement.                                                                     |
| content_hash          | TEXT    | NOT NULL. Algorithm prefix included, e.g., `blake3:abc…` or `sha256:abc…`.             |
| hash_algorithm        | TEXT    | NOT NULL. `blake3` or `sha256` (denormalised from `content_hash` for fast filtering).  |
| primary_path          | TEXT    | NOT NULL. The first-discovered source path; UTF-8 normalised.                          |
| size_bytes            | INTEGER | NOT NULL.                                                                              |
| mtime_unix            | REAL    | NOT NULL. Used together with `primary_path` and `size_bytes` for incremental skip.     |
| mime_type             | TEXT    | NULLABLE. Guessed at scan time.                                                        |
| capture_ts_utc        | TEXT    | NULLABLE ISO 8601. NULL ⇒ item is Unmatched (no parseable timestamp).                  |
| capture_tz            | TEXT    | NULLABLE IANA tz name when known; otherwise NULL (system-local assumed).               |
| capture_source_tier   | TEXT    | NULLABLE. One of `sidecar`, `exif`, `video`, `filename`, `mtime`.                      |
| google_photos_id      | TEXT    | NULLABLE. From sidecar or Picker.                                                      |
| provenance            | TEXT    | NOT NULL. `takeout` \| `picker`.                                                       |
| picker_cache_path     | TEXT    | NULLABLE. Set when `provenance='picker'`.                                              |
| created_at            | TEXT    | NOT NULL ISO 8601 UTC of ingest.                                                       |
| updated_at            | TEXT    | NOT NULL ISO 8601 UTC of last metadata refresh.                                        |

**Indexes**:

- `UNIQUE (content_hash)` — dedup invariant.
- `INDEX media_items_capture_ts_idx ON media_items(capture_ts_utc)` — matcher range scans.
- `INDEX media_items_primary_path_idx ON media_items(primary_path)` — incremental scan.
- `INDEX media_items_google_id_idx ON media_items(google_photos_id) WHERE google_photos_id IS NOT NULL`.
- `INDEX media_items_provenance_idx ON media_items(provenance)`.

### `media_paths` (one-to-many alternate paths for duplicates)

| Column         | Type    | Notes                                              |
|----------------|---------|----------------------------------------------------|
| id             | INTEGER | PK.                                                |
| media_id       | INTEGER | NOT NULL FK → `media_items.id` ON DELETE CASCADE.  |
| path           | TEXT    | NOT NULL.                                          |
| size_bytes     | INTEGER | NOT NULL.                                          |
| mtime_unix     | REAL    | NOT NULL.                                          |
| discovered_at  | TEXT    | NOT NULL.                                          |

**Indexes**: `UNIQUE (path)`, `INDEX media_paths_media_id_idx ON media_paths(media_id)`.

### `calendar_events`

| Column           | Type    | Notes                                                                          |
|------------------|---------|--------------------------------------------------------------------------------|
| id               | INTEGER | PK.                                                                            |
| google_event_id  | TEXT    | NOT NULL. Recurring-instance id (`<eventId>_<originalStartTime>`) when applicable. |
| calendar_id      | TEXT    | NOT NULL. Source calendar id.                                                  |
| title            | TEXT    | NOT NULL (may be empty string).                                                |
| start_utc        | TEXT    | NOT NULL ISO 8601.                                                             |
| end_utc          | TEXT    | NOT NULL ISO 8601. For all-day events: 00:00 next day in the event's tz.       |
| timezone         | TEXT    | NULLABLE IANA tz.                                                              |
| is_all_day       | INTEGER | NOT NULL 0|1.                                                                  |
| location         | TEXT    | NULLABLE.                                                                      |
| description      | TEXT    | NULLABLE.                                                                      |
| attendees_json   | TEXT    | NULLABLE JSON array of `{email, displayName?}` (may be redacted in exports).   |
| imported_at      | TEXT    | NOT NULL ISO 8601 UTC.                                                         |
| etag             | TEXT    | NULLABLE. Used for incremental re-import.                                      |

**Indexes**:

- `UNIQUE (google_event_id, calendar_id)`.
- `INDEX calendar_events_window_idx ON calendar_events(start_utc, end_utc)` — matcher range scans.
- `INDEX calendar_events_calendar_id_idx ON calendar_events(calendar_id)`.

### `media_event_matches`

| Column          | Type    | Notes                                                                  |
|-----------------|---------|------------------------------------------------------------------------|
| id              | INTEGER | PK.                                                                    |
| media_id        | INTEGER | NOT NULL FK → `media_items.id` ON DELETE CASCADE.                      |
| event_id        | INTEGER | NOT NULL FK → `calendar_events.id` ON DELETE CASCADE.                  |
| rule_category   | TEXT    | NOT NULL. `in_event` \| `buffered` \| `date_only`.                     |
| source_cap      | REAL    | NOT NULL. Per-item source-tier cap applied (1.0 / 0.75 / 0.5).         |
| rule_score      | REAL    | NOT NULL. 1.0 / 0.75 / 0.5.                                            |
| bonus           | REAL    | NOT NULL ≥ 0.0. Location/keyword bonus.                                |
| confidence      | REAL    | NOT NULL. `min(rule_score + bonus, source_cap)`.                       |
| band            | TEXT    | NOT NULL. `high` \| `medium` \| `low` (banded for UI filters).         |
| is_recommended  | INTEGER | NOT NULL 0|1.                                                          |
| computed_at     | TEXT    | NOT NULL ISO 8601 UTC of last matcher run.                             |

**Indexes**:

- `UNIQUE (media_id, event_id)`.
- `INDEX matches_media_idx ON media_event_matches(media_id)`.
- `INDEX matches_event_idx ON media_event_matches(event_id)`.
- `INDEX matches_band_idx ON media_event_matches(band, is_recommended)` — bulk-approve queries.

### `proposed_albums`

| Column            | Type    | Notes                                                                              |
|-------------------|---------|------------------------------------------------------------------------------------|
| id                | INTEGER | PK.                                                                                |
| anchor_event_id   | INTEGER | NULLABLE FK → `calendar_events.id`. NULL after merge across days.                  |
| display_name      | TEXT    | NOT NULL. User-facing name; default `YYYY-MM-DD – <event title>`.                  |
| folder_name       | TEXT    | NOT NULL. Sanitised version of `display_name`. Unique per export target via      |
|                   |         | the `exported_albums.target_id` join — DB-driven disambiguation (D-010).           |
| status            | TEXT    | NOT NULL. `proposed` \| `approved` \| `rejected` \| `exported`.                    |
| approved_at       | TEXT    | NULLABLE ISO 8601 UTC.                                                             |
| rejected_at       | TEXT    | NULLABLE ISO 8601 UTC.                                                             |
| merged_from_json  | TEXT    | NULLABLE JSON array of prior album ids (for audit of merge operations).            |
| split_from_id     | INTEGER | NULLABLE FK → `proposed_albums.id` (parent before split).                          |
| user_renamed      | INTEGER | NOT NULL 0|1. Set after the first user rename.                                     |
| created_at        | TEXT    | NOT NULL.                                                                          |
| updated_at        | TEXT    | NOT NULL.                                                                          |

**Indexes**:

- `INDEX albums_status_idx ON proposed_albums(status)`.
- `INDEX albums_anchor_idx ON proposed_albums(anchor_event_id)`.

### `album_items`

| Column         | Type    | Notes                                                                                  |
|----------------|---------|----------------------------------------------------------------------------------------|
| id             | INTEGER | PK.                                                                                    |
| album_id       | INTEGER | NOT NULL FK → `proposed_albums.id` ON DELETE CASCADE.                                  |
| media_id       | INTEGER | NOT NULL FK → `media_items.id` ON DELETE CASCADE.                                      |
| via_match_id   | INTEGER | NULLABLE FK → `media_event_matches.id`. NULL when user manually added.                 |
| added_at       | TEXT    | NOT NULL.                                                                              |

**Indexes**:

- `UNIQUE (album_id, media_id)`.
- `INDEX album_items_media_idx ON album_items(media_id)` — for the
  "single-album-membership" enforcement query (FR-021).

### `scan_jobs`

| Column           | Type    | Notes                                                                                |
|------------------|---------|--------------------------------------------------------------------------------------|
| id               | INTEGER | PK.                                                                                  |
| job_type         | TEXT    | NOT NULL. `scan` \| `calendar_import` \| `match` \| `export` \| `picker_import` \| `gp_upload`. |
| status           | TEXT    | NOT NULL. `queued` \| `running` \| `paused` \| `cancelled` \| `failed` \| `completed`. |
| pause_reason     | TEXT    | NULLABLE. e.g., `reauth_required` (FR-042a).                                         |
| checkpoint_json  | TEXT    | NULLABLE JSON. Cursor (last directory + last file index, last event etag, etc.).     |
| total_items      | INTEGER | NULLABLE. Best-known total (may grow during scan).                                   |
| processed_items  | INTEGER | NOT NULL DEFAULT 0.                                                                  |
| started_at       | TEXT    | NULLABLE.                                                                            |
| finished_at      | TEXT    | NULLABLE.                                                                            |
| created_at       | TEXT    | NOT NULL.                                                                            |

**Indexes**: `INDEX jobs_status_idx ON scan_jobs(status, job_type)`.

### `errors`

| Column       | Type    | Notes                                                                          |
|--------------|---------|--------------------------------------------------------------------------------|
| id           | INTEGER | PK.                                                                            |
| job_id       | INTEGER | NULLABLE FK → `scan_jobs.id`.                                                  |
| phase        | TEXT    | NOT NULL. `scan` \| `extract` \| `match` \| `export` \| `upload` \| `auth`.    |
| subject_kind | TEXT    | NOT NULL. `path` \| `event` \| `album` \| `media_id`.                          |
| subject      | TEXT    | NOT NULL. The file path / event id / album id.                                 |
| reason       | TEXT    | NOT NULL. Short machine code (e.g., `EXIF_PARSE`, `FFPROBE_TIMEOUT`).          |
| detail       | TEXT    | NULLABLE. Human-readable detail (no secrets).                                  |
| occurred_at  | TEXT    | NOT NULL.                                                                      |

**Indexes**: `INDEX errors_job_idx ON errors(job_id)`,
`INDEX errors_phase_idx ON errors(phase)`.

### `export_targets`

| Column                  | Type    | Notes                                                              |
|-------------------------|---------|--------------------------------------------------------------------|
| id                      | INTEGER | PK.                                                                |
| root_path               | TEXT    | NOT NULL UNIQUE. Absolute export-root path chosen by the user.     |
| symlink_supported       | INTEGER | NOT NULL 0|1. Result of probe (D-009).                             |
| user_confirmed_copy     | INTEGER | NOT NULL 0|1. Set after the user confirms copy-mode for this root. |
| probed_at               | TEXT    | NOT NULL.                                                          |

### `exported_albums`

Records every materialisation event of a `proposed_album` into a folder under an
`export_target`. Used to detect re-exports and surface
`orphaned-by-rename` rows (FR-034a).

| Column            | Type    | Notes                                                                |
|-------------------|---------|----------------------------------------------------------------------|
| id                | INTEGER | PK.                                                                  |
| album_id          | INTEGER | NOT NULL FK → `proposed_albums.id`.                                  |
| target_id         | INTEGER | NOT NULL FK → `export_targets.id`.                                   |
| folder_name       | TEXT    | NOT NULL. The sanitised folder name at the time of this export.      |
| mode              | TEXT    | NOT NULL. `symlink` \| `copy`.                                       |
| item_count        | INTEGER | NOT NULL.                                                            |
| photo_count       | INTEGER | NOT NULL.                                                            |
| video_count       | INTEGER | NOT NULL.                                                            |
| status            | TEXT    | NOT NULL. `current` \| `orphaned-by-rename`.                         |
| manifest_path     | TEXT    | NOT NULL. Relative to `target.root_path`.                            |
| exported_at       | TEXT    | NOT NULL.                                                            |

**Indexes**: `UNIQUE (target_id, folder_name)`,
`INDEX exported_albums_album_idx ON exported_albums(album_id)`.

## Domain Models (Python)

`models.py` exports `dataclass`-based mirrors of these tables (snake_case
fields, `datetime` instead of ISO strings, `enum.StrEnum` for status columns).
Each repository maps between SQL rows and dataclasses; no auto-magic ORM.

```python
class CaptureSourceTier(StrEnum):
    SIDECAR = "sidecar"
    EXIF = "exif"
    VIDEO = "video"
    FILENAME = "filename"
    MTIME = "mtime"

class Provenance(StrEnum):
    TAKEOUT = "takeout"
    PICKER = "picker"

class MatchRule(StrEnum):
    IN_EVENT = "in_event"
    BUFFERED = "buffered"
    DATE_ONLY = "date_only"

class ConfidenceBand(StrEnum):
    HIGH = "high"     # >= 0.85
    MEDIUM = "medium" # >= 0.60
    LOW = "low"

class AlbumStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPORTED = "exported"

class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    FAILED = "failed"
    COMPLETED = "completed"
```

## Invariants

- **I-1 (Dedup)**: `media_items.content_hash` is unique. Inserts on a duplicate
  hash route to `media_paths` instead.
- **I-2 (Recommended uniqueness)**: at most one row in
  `media_event_matches` per `media_id` has `is_recommended = 1`. Enforced by
  partial unique index on `(media_id) WHERE is_recommended = 1`.
- **I-3 (Single-album membership default)**: when
  `config.multi_album_membership = false`, the application layer ensures any
  given `media_id` appears in at most one `album_items` row whose album has
  status ∈ {`proposed`, `approved`}. Toggling the flag does not retroactively
  duplicate or remove rows.
- **I-4 (No orphan exports lost)**: when `proposed_albums.folder_name` changes
  after an `exported_albums.status = 'current'` row exists, the existing row
  flips to `orphaned-by-rename` (DB trigger).
- **I-5 (No destructive paths)**: there are no `DELETE` statements against
  `media_items` or `media_paths` outside of `db/migrations/*` and an explicit
  `--reset` admin path (out of scope for v1 UI). `proposed_albums` rows are
  `status='rejected'`, not deleted.

## Initial Migration (`0001_initial.sql`)

Creates every table above with the indexes listed, enables WAL
(`PRAGMA journal_mode=WAL`), foreign keys (`PRAGMA foreign_keys=ON`), and
sets `schema_meta.version = 1`. Subsequent schema changes ship as
`0002_*.sql`, … each tested by `tests/unit/test_migrations.py` (constitution
Engineering Standard).

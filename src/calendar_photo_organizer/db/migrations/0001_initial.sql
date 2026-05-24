-- 0001_initial.sql — Calendar Photo Organizer baseline schema.
-- See specs/001-calendar-photo-organizer/data-model.md for narrative.

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- Schema bookkeeping
-- ---------------------------------------------------------------------------
CREATE TABLE schema_meta (
    version    INTEGER NOT NULL PRIMARY KEY,
    applied_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- ---------------------------------------------------------------------------
-- Media: one row per unique content_hash
-- ---------------------------------------------------------------------------
CREATE TABLE media_items (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    content_hash          TEXT    NOT NULL UNIQUE,           -- "algo:hex"
    captured_at_utc       TEXT,                              -- ISO-8601 UTC
    captured_at_tz        TEXT,                              -- IANA tz name
    capture_source_tier   TEXT,                              -- sidecar|exif|video_meta|filename|mtime
    mime_type             TEXT,
    width                 INTEGER,
    height                INTEGER,
    duration_seconds      REAL,
    provenance            TEXT    NOT NULL DEFAULT 'takeout',-- takeout|picker|local
    google_photo_id       TEXT    UNIQUE,
    created_at_utc        TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at_utc        TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX idx_media_items_captured_at ON media_items(captured_at_utc);
CREATE INDEX idx_media_items_provenance  ON media_items(provenance);

-- ---------------------------------------------------------------------------
-- Media paths: one row per (path, size, mtime); supports dedup of alt paths
-- ---------------------------------------------------------------------------
CREATE TABLE media_paths (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    media_id    INTEGER NOT NULL REFERENCES media_items(id) ON DELETE CASCADE,
    path        TEXT    NOT NULL,
    size_bytes  INTEGER NOT NULL,
    mtime_ns    INTEGER NOT NULL,
    is_primary  INTEGER NOT NULL DEFAULT 1 CHECK (is_primary IN (0, 1)),
    UNIQUE (path)
);
CREATE INDEX idx_media_paths_media_id ON media_paths(media_id);
CREATE INDEX idx_media_paths_lookup   ON media_paths(path, size_bytes, mtime_ns);

-- ---------------------------------------------------------------------------
-- Calendar events (FR-003 instances are flattened by client)
-- ---------------------------------------------------------------------------
CREATE TABLE calendar_events (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    google_event_id   TEXT    NOT NULL,
    calendar_id       TEXT    NOT NULL,
    title             TEXT    NOT NULL,
    description       TEXT,
    location          TEXT,
    start_utc         TEXT    NOT NULL,
    end_utc           TEXT    NOT NULL,
    is_all_day        INTEGER NOT NULL DEFAULT 0 CHECK (is_all_day IN (0, 1)),
    etag              TEXT,
    UNIQUE (google_event_id, calendar_id)
);
CREATE INDEX idx_calendar_events_range ON calendar_events(start_utc, end_utc);

-- ---------------------------------------------------------------------------
-- Matches: media x event (many-to-many with confidence)
-- ---------------------------------------------------------------------------
CREATE TABLE media_event_matches (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    media_id        INTEGER NOT NULL REFERENCES media_items(id) ON DELETE CASCADE,
    event_id        INTEGER NOT NULL REFERENCES calendar_events(id) ON DELETE CASCADE,
    rule            TEXT    NOT NULL,    -- in_event|buffered|date_only
    confidence      REAL    NOT NULL,    -- 0.0..1.0
    band            TEXT    NOT NULL,    -- high|medium|low
    is_recommended  INTEGER NOT NULL DEFAULT 0 CHECK (is_recommended IN (0, 1)),
    UNIQUE (media_id, event_id)
);
CREATE INDEX idx_media_event_matches_media ON media_event_matches(media_id);
CREATE INDEX idx_media_event_matches_event ON media_event_matches(event_id);
-- Invariant I-1: at most one recommended match per media item
CREATE UNIQUE INDEX idx_media_event_matches_recommended
    ON media_event_matches(media_id) WHERE is_recommended = 1;

-- ---------------------------------------------------------------------------
-- Proposed albums + album_items
-- ---------------------------------------------------------------------------
CREATE TABLE proposed_albums (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    display_name        TEXT    NOT NULL,
    folder_name         TEXT    NOT NULL,
    status              TEXT    NOT NULL DEFAULT 'proposed',
    event_id            INTEGER REFERENCES calendar_events(id) ON DELETE SET NULL,
    user_renamed        INTEGER NOT NULL DEFAULT 0 CHECK (user_renamed IN (0, 1)),
    merged_from_json    TEXT,
    split_from_id       INTEGER REFERENCES proposed_albums(id) ON DELETE SET NULL,
    created_at_utc      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at_utc      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX idx_proposed_albums_status ON proposed_albums(status);
CREATE INDEX idx_proposed_albums_event  ON proposed_albums(event_id);

CREATE TABLE album_items (
    album_id  INTEGER NOT NULL REFERENCES proposed_albums(id) ON DELETE CASCADE,
    media_id  INTEGER NOT NULL REFERENCES media_items(id) ON DELETE CASCADE,
    PRIMARY KEY (album_id, media_id)
);
CREATE INDEX idx_album_items_media ON album_items(media_id);

-- ---------------------------------------------------------------------------
-- Jobs & errors
-- ---------------------------------------------------------------------------
CREATE TABLE scan_jobs (
    id                  TEXT PRIMARY KEY,            -- UUID
    job_type            TEXT NOT NULL,               -- scan|calendar_import|match|propose|export
    status              TEXT NOT NULL DEFAULT 'pending',
    pause_reason        TEXT,                        -- reauth_required|manual|other
    started_at_utc      TEXT,
    finished_at_utc     TEXT,
    processed_count     INTEGER NOT NULL DEFAULT 0,
    total_count         INTEGER,
    last_checkpoint     INTEGER NOT NULL DEFAULT 0,
    detail_json         TEXT
);
CREATE INDEX idx_jobs_type_status ON scan_jobs(job_type, status);

CREATE TABLE errors (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          TEXT REFERENCES scan_jobs(id) ON DELETE CASCADE,
    phase           TEXT NOT NULL,
    subject_kind    TEXT NOT NULL,                   -- media|event|album|export|other
    subject         TEXT NOT NULL,
    reason          TEXT NOT NULL,
    detail          TEXT,
    occurred_at_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX idx_errors_job ON errors(job_id);

-- ---------------------------------------------------------------------------
-- Export bookkeeping
-- ---------------------------------------------------------------------------
CREATE TABLE export_targets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    root            TEXT    NOT NULL UNIQUE,
    mode            TEXT    NOT NULL,                -- symlink|copy
    last_run_at_utc TEXT
);

CREATE TABLE exported_albums (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    export_target_id    INTEGER NOT NULL REFERENCES export_targets(id) ON DELETE CASCADE,
    album_id            INTEGER REFERENCES proposed_albums(id) ON DELETE SET NULL,
    folder_name         TEXT    NOT NULL,            -- as-written on disk
    item_count          INTEGER NOT NULL,
    exported_at_utc     TEXT    NOT NULL,
    status              TEXT    NOT NULL DEFAULT 'current', -- current|orphaned-by-rename
    notes               TEXT,
    UNIQUE (export_target_id, folder_name, exported_at_utc)
);
CREATE INDEX idx_exported_albums_album  ON exported_albums(album_id);
CREATE INDEX idx_exported_albums_status ON exported_albums(status);

-- Invariant I-4: on rename, the previously-exported folder for this album
-- is marked orphaned-by-rename (FR-034a, Clarification Q4).
CREATE TRIGGER trg_rename_marks_export_orphan
AFTER UPDATE OF folder_name ON proposed_albums
WHEN OLD.folder_name <> NEW.folder_name
BEGIN
    UPDATE exported_albums
       SET status = 'orphaned-by-rename',
           notes  = 'previous folder retained on disk; not modified'
     WHERE album_id = NEW.id
       AND folder_name = OLD.folder_name
       AND status = 'current';
END;

-- ---------------------------------------------------------------------------
-- Seed
-- ---------------------------------------------------------------------------
INSERT INTO schema_meta (version) VALUES (1);

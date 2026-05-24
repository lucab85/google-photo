# Feature Specification: Calendar Photo Organizer (MVP)

**Feature Branch**: `001-calendar-photo-organizer`

**Created**: 2026-05-23

**Status**: Draft

**Input**: User description: Build a simple but scalable Python desktop/web app that organizes a ~100,000-item Google Photos archive into event-based albums using the user's Google Calendar history, primarily by importing a local Google Takeout export plus calendar events for a chosen date range, matching media timestamps to events with configurable buffers, proposing albums the user can review/rename/merge/split/reject, and exporting approved albums as local folders (symlinks by default) with manifests and a CSV report. Optional Google Photos Picker/upload integration is behind a feature flag. Local-first, non-destructive, resumable, cross-platform (macOS/Windows/Linux), Python 3.12+.

## Clarifications

### Session 2026-05-23

- Q: Should the user have to approve every proposed album individually, or are bulk-approval actions also offered? → A: Both — per-album approve/reject controls **and** scoped bulk actions (e.g., "approve all high-confidence albums", "reject all empty/low-confidence"). Albums never auto-approve; every export still requires an explicit user act, but that act can be batched.
- Q: Which timestamp sources are eligible for matching against calendar events, and how does source quality affect confidence? → A: All sources participate in matching, but per-item confidence is **capped by source**: sidecar `photoTakenTime` / EXIF / video container `creation_time` can reach the highest confidence; filename-derived timestamps are capped at medium; filesystem-mtime-only items are capped at low. Items with no parseable timestamp from any source remain Unmatched.
- Q: What should happen when Google Calendar OAuth fails (token revoked / refresh expired / persistent 401) during a long-running job? → A: **Pause & re-auth**. The job is paused with its checkpoint persisted; the UI shows a clear "re-authorize Google Calendar to continue" prompt; on successful re-auth the job resumes from the checkpoint. Transient errors (HTTP 429 rate-limit, 5xx) are retried with exponential backoff before pausing. The job is never silently failed or silently completed against partial calendar data.
- Q: What happens when a user re-exports an album whose name has changed since the last export and the previous folder still exists on disk under the old name? → A: **Leave + report**. The old folder is left untouched on disk; the new folder is created under the new sanitized name; both are listed in `report.csv` with a status column, with the old one flagged as `orphaned-by-rename`. The app never moves, renames, or deletes previously exported folders — cleanup is the user's choice (consistent with the non-destructive principle).
- Q: When the optional Google Photos Picker integration is enabled, how are selected items stored locally? → A: **Download to app cache**. Picker-selected bytes are fetched into a dedicated `picker-cache/` directory under the app's working data directory, content-hashed on arrival, and treated identically to Takeout items thereafter (ingestion, matching, export). Re-running a Picker selection that includes already-cached items reuses the cached bytes (no re-download). The cache is app-owned storage; the user's Google Photos cloud copies are never modified.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Bulk-organize a Takeout archive into reviewable event albums (Priority: P1)

A non-technical user with a Google Takeout export of ~100,000 photos and videos and a connected Google Calendar wants the app to automatically group their media into albums named after calendar events (e.g., "2024-07-18 – Luca Birthday"). They want to see proposed albums on screen and approve or reject each one before anything is written to disk.

**Why this priority**: This is the entire reason the product exists. Without this slice the product delivers no value. Everything else (export, refinement, cloud upload) is an enhancement of this slice.

**Independent Test**: Point the app at a fixture Takeout folder of 100 media items and a fixture set of calendar events covering the same date range. Verify the app ingests both, produces a list of proposed albums in the review UI with item counts and confidence levels, and that the user can open an album to see which media were matched. No export step is required for this test.

**Acceptance Scenarios**:

1. **Given** a local Takeout folder containing photos, videos, and Google sidecar JSON files, and a connected Google account with calendar events covering the same dates, **When** the user starts an ingest + match job, **Then** the app scans the folder, imports calendar events for the chosen date range, persists everything to a local database, and presents a list of proposed albums each labeled "YYYY-MM-DD – Event Title" with a count of matched photos and videos and a confidence indicator.
2. **Given** an in-progress ingest job that is interrupted (process killed, machine restarted), **When** the user reopens the app and resumes the job, **Then** scanning continues from where it left off without re-hashing or re-extracting metadata for files that were already processed and whose path/size/mtime have not changed.
3. **Given** the proposed albums list, **When** the user opens a proposed album, **Then** they see the matched media with capture timestamps and the matching event details (title, start, end, location if available).
4. **Given** matched media, **When** the user filters by confidence (high / medium / low), **Then** only albums or items at that confidence level are shown.
5. **Given** media with no matching event, **When** the user opens the "Unmatched" view, **Then** they see the unmatched media grouped by date with the option to manually assign them to an existing or new album later.

---

### User Story 2 — Export approved albums to local folders with manifests (Priority: P2)

After reviewing proposed albums, the user wants to materialize their approved organization on disk as folders containing the media (via symlinks by default) plus a per-album manifest and a global CSV report — without touching, moving, or deleting any original files.

**Why this priority**: The review in US1 is useless without a way to produce a durable result. Export is the second-most-valuable slice and the one that crosses the "trust" threshold: it must be safe.

**Independent Test**: Given a small set of approved albums from US1, run the export. Verify (a) a dry-run mode lists every file that *would* be created, (b) a real run creates the album folders with symlinks (or copies on filesystems that disallow symlinks), (c) each album folder contains `manifest.json`, (d) a top-level `report.csv` is written, (e) all original files in the Takeout folder remain bit-identical and at their original paths.

**Acceptance Scenarios**:

1. **Given** one or more approved albums, **When** the user runs export in dry-run mode, **Then** the app produces a textual/structured plan of every folder, symlink/copy, and manifest it would create, and writes nothing to the export target.
2. **Given** an approved export plan, **When** the user runs the real export on a filesystem that supports symlinks, **Then** each album becomes a folder of symlinks pointing to the original Takeout media, each folder contains `manifest.json` listing source paths, hashes, capture timestamps, matched event, and confidence, and a top-level `report.csv` summarizes all exported albums and items.
3. **Given** an approved export plan on a filesystem that does not support symlinks (e.g., FAT32, restricted Windows account), **When** the user runs export, **Then** the app falls back to copy mode and clearly indicates this in the UI/log before proceeding.
4. **Given** a previously exported album, **When** the user re-runs export for the same album, **Then** the app detects existing items and does not duplicate them; new items are added and removed items are reported, but no original file is ever modified or deleted.
5. **Given** an export of any kind, **Verify** that every original media file under the Takeout source directory is byte-identical and at the same path it had before the export started.

---

### User Story 3 — Refine the proposal: rename, merge, split, reject albums, and tune match windows (Priority: P3)

The user wants to correct the automated proposals: rename an album, merge two same-day events into one album, split an over-broad album into two, reject albums that don't make sense, and adjust the pre/post-event time buffers to re-run matching.

**Why this priority**: Improves quality of results but the product is still useful without it (US1 + US2 = a viable MVP). Refinement is what makes the tool feel "smart" rather than rigid.

**Independent Test**: Take the proposed-albums list from US1, perform each refinement (rename, merge, split, reject) in the UI, change the pre-buffer to 1 h and post-buffer to 8 h, re-run matching, and verify the changes persist and that subsequent export (US2) reflects them.

**Acceptance Scenarios**:

1. **Given** a proposed album, **When** the user renames it, **Then** the new name is persisted and used in the export folder name (after folder-name sanitization).
2. **Given** two proposed albums on the same day, **When** the user merges them, **Then** the resulting album contains the union of media and the user is asked to pick or supply the merged name.
3. **Given** a proposed album with media from clearly different sub-events, **When** the user splits it by selecting items and choosing "split into new album", **Then** two albums exist and every media item is in exactly one of them (unless the user has enabled multi-album membership).
4. **Given** any proposed album, **When** the user rejects it, **Then** the album disappears from the proposal list and its media return to the "Unmatched" view; no media file is deleted.
5. **Given** updated pre-buffer and post-buffer settings, **When** the user re-runs the matcher, **Then** matches are recomputed and the proposal list reflects the new windows without requiring a re-scan of media files.
6. **Given** the multi-album-membership toggle is OFF (default), **When** matching runs, **Then** each media item appears in at most one proposed album (the highest-confidence candidate); **When** the toggle is ON, **Then** items may appear in multiple candidate albums and the UI shows that fact clearly.

---

### User Story 4 — Optional Google Photos integration (Priority: P4)

A more adventurous user wants to (a) import a smaller batch of media from their cloud library via the Google Photos Picker, and/or (b) upload the contents of an approved album back to Google Photos as a new app-created album.

**Why this priority**: Nice-to-have, explicitly optional, and bounded by Google API restrictions. Off by default. Last to build.

**Independent Test**: With the Google Photos feature flag enabled, (a) sign in, use the Picker to select a small batch, and verify those items are ingested and visible in the review UI alongside Takeout items; (b) approve one album and trigger upload, then verify a new album appears in the user's Google Photos account containing only the uploaded items.

**Acceptance Scenarios**:

1. **Given** the Google Photos feature flag is OFF (default), **When** the user uses the app, **Then** no Google Photos UI controls are visible and no Google Photos network calls are made.
2. **Given** the feature flag is ON and the user has authorized the relevant OAuth scopes, **When** the user invokes the Picker, **Then** they select items in Google's Picker UI and those items are downloaded/registered in the local database with provenance "picker" and become reviewable alongside Takeout items.
3. **Given** an approved album, **When** the user requests upload to Google Photos, **Then** the app creates a new app-created Google Photos album, uploads the album's media (where API permission allows), and reports any items that could not be uploaded with a clear reason.
4. **Given** any Google Photos operation, **When** it fails or is partially restricted by API permissions, **Then** the app surfaces a clear, non-technical explanation referencing the documented Google Photos API limitations and does not silently drop data.

---

### Edge Cases

- **Missing capture timestamp**: a media file has no EXIF/video-metadata timestamp, no sidecar JSON, and no parseable filename date. The app records it as "unmatched – no reliable timestamp" and the user can review it manually.
- **EXIF vs Takeout sidecar disagreement**: when EXIF says one timestamp and the Google JSON sidecar says another, the app uses the sidecar's `photoTakenTime` as authoritative (Google's recorded capture time), records the discrepancy, and exposes it in the per-item details.
- **Wrong/unknown timezone**: media timestamp lacks timezone info. The app assumes the timestamp is in the user's configured local timezone and flags the item with a low-confidence indicator if the matched event's timezone differs.
- **All-day events**: events without a specific time match any media whose capture timestamp falls within the event's full local calendar day; these matches receive the "date-only" confidence (lower than in-event matches).
- **Overlapping events**: when two or more events overlap and a media item could belong to several, the app keeps all candidate matches in the database, marks the highest-confidence one as "recommended", and lets the user adjust in the review UI.
- **Travel across timezones**: capture timestamps are converted using the per-item timezone when available (EXIF GPS-derived or sidecar) and otherwise the user's local timezone is assumed; users can see the assumed timezone in item details.
- **Burst photos**: multiple shots taken within seconds are treated as independent media; they will naturally co-cluster into the same event album.
- **Duplicates**: same content reaching the database via different paths or via Takeout + Picker is detected by content hash (and/or Google Photos id when available) and counted once in reports and once in any album; the duplicate paths are preserved in the per-item record.
- **Screenshots / downloaded images**: ingested like any other media; they will either match an event or sit in the Unmatched view. No special exclusion in v1.
- **Recurring calendar events**: each instance is imported as a separate event row keyed by the instance's effective start/end, so each occurrence can anchor its own album.
- **Very large albums in the UI**: any view of items must paginate or lazy-load; opening an album with 5,000 items must not freeze the UI.
- **Filesystem without symlink support**: export falls back to copy mode with a clear warning before proceeding.
- **Interrupted scan/match/export**: state is persisted incrementally; a resume restarts from the last committed checkpoint without redoing completed work.
- **Per-item ingestion error** (corrupt file, unreadable metadata): logged to the errors table with file path and reason; the job continues.
- **No internet during ingest**: Calendar import requires internet; if offline, calendar import fails gracefully and the user is told to retry later. Media ingestion from Takeout works fully offline.
- **Multiple events on the same date**: each becomes its own proposed album; album names disambiguate by including the event title (and a numeric suffix only if titles collide).
- **Calendar event title contains characters illegal in filesystem names**: folder names are sanitized (illegal characters replaced or stripped, length capped), but the in-app display name preserves the original.

## Requirements *(mandatory)*

### Functional Requirements

**Authentication & Calendar Import**

- **FR-001**: System MUST allow the user to sign in to Google for read-only access to their Google Calendar.
- **FR-002**: System MUST let the user choose which calendars to import from (primary plus any selectable calendars) and a date range (start, end).
- **FR-003**: System MUST import all event instances of recurring events within the chosen date range (one row per instance).
- **FR-004**: System MUST persist for each event: stable id, title, start, end, timezone, location (if present), description (if present), attendees (if present), and source calendar id.
- **FR-005**: System MUST store OAuth tokens locally using the OS keychain when available, otherwise a user-readable file with restrictive permissions, and MUST NOT include tokens or secrets in any log.

**Media Ingestion**

- **FR-006**: System MUST scan a user-chosen local directory (Google Takeout export) recursively for media.
- **FR-007**: System MUST recognize at minimum the file types JPG, JPEG, PNG, HEIC, WEBP, MP4, MOV, M4V, AVI, and the Google Photos JSON sidecar files associated with them.
- **FR-008**: System MUST extract a capture timestamp per media item using, in this priority order: Google sidecar `photoTakenTime`, EXIF DateTimeOriginal/CreateDate, video container `creation_time`, filename date patterns (e.g., `IMG_YYYYMMDD_HHMMSS`), and the filesystem mtime as a last resort. System MUST record per item which source produced the chosen timestamp (the "timestamp source tier").
- **FR-009**: System MUST extract and persist per item: source path, file size, content hash, capture timestamp, capture timezone (when known), MIME/type, and any Google Photos id present in the sidecar.
- **FR-010**: System MUST detect duplicates by content hash, by (filename + size), and by Google Photos id when available, and MUST count each duplicate set as one logical item across reports and album membership while preserving every source path.
- **FR-011**: System MUST be incremental: a file whose path, size, and mtime are unchanged since the last scan MUST NOT be re-hashed or have its metadata re-extracted.
- **FR-012**: System MUST record per-item ingestion errors to an errors store with file path and reason and MUST NOT abort the enclosing job on a per-item error.

**Matching**

- **FR-013**: System MUST match every media item that has any extracted capture timestamp (regardless of source tier) against the imported calendar events using configurable pre-event and post-event time buffers (defaults: 2 h before, 4 h after). Items with no parseable timestamp from any source MUST go straight to the Unmatched view.
- **FR-014**: System MUST assign each match a confidence determined by combining (a) the **matching rule** — highest when the capture timestamp falls inside the event's start/end, medium when it falls inside the buffered window, low when only the calendar date matches (all-day or date-only fallback) — with (b) a **source-tier cap**: sidecar `photoTakenTime` / EXIF / video `creation_time` may reach the highest confidence; filename-derived timestamps are capped at medium; filesystem-mtime-only timestamps are capped at low. The final confidence is the lower of the two. The keyword/location bonus from FR-015 is applied after the cap and MUST NOT raise an item above its source-tier cap.
- **FR-015**: System MUST add a bonus to confidence when the event's location or title contains tokens that also appear in the media's filename, folder path, sidecar location, or EXIF GPS-derived place name.
- **FR-016**: System MUST keep all candidate matches when a media item could belong to multiple events, and MUST mark exactly one as "recommended" (the highest-confidence one; ties broken by smallest time distance to event center, then by earliest event start).
- **FR-017**: System MUST place low-confidence and ambiguous matches into a dedicated review queue surfaced in the UI.

**Album Proposal & Review**

- **FR-018**: System MUST generate one proposed album per event with at least one matched media item, named in the format "YYYY-MM-DD – Event Title".
- **FR-019**: System MUST sanitize names used for filesystem folders (strip/replace illegal characters, cap length) while preserving the original display name in the database and UI.
- **FR-020**: System MUST allow the user to rename, merge (same day or across days), split (by selecting items), and reject any proposed album, with all changes persisted.
- **FR-021**: System MUST enforce single-album-membership by default (each media item belongs to at most one proposed album, its recommended match), with a user-toggleable mode that allows membership in multiple candidate albums.
- **FR-022**: System MUST provide a dashboard showing totals: media scanned, media matched, media unmatched, duplicates collapsed, and errors.
- **FR-023**: System MUST provide a per-album view listing matched media with thumbnails where the file type permits, capture timestamp, confidence, and the matched event details.
- **FR-024**: System MUST provide an "Unmatched" view grouped by date.
- **FR-025**: System MUST allow the user to filter albums and items by confidence level.
- **FR-026**: System MUST allow the user to approve or reject proposed albums and MUST persist that approval state. Both per-album approve/reject controls AND scoped bulk actions (at minimum: "approve all high-confidence albums", "reject all empty/low-confidence albums") MUST be available. The system MUST NOT auto-approve any album; only approved albums are eligible for export (FR-029).
- **FR-027**: System MUST paginate or lazy-load any view of items so that opening a view with thousands of items does not freeze the UI.

**Export**

- **FR-028**: System MUST offer a dry-run export mode that produces the full planned output description (which folders, which symlinks/copies, which manifests) without writing any file to the export target.
- **FR-029**: System MUST create one folder per approved album under a user-chosen export root.
- **FR-030**: System MUST materialize each album's media as symlinks pointing to the original Takeout files by default, and MUST fall back to file copies on filesystems where symlinks are unsupported or not permitted, informing the user before proceeding.
- **FR-031**: System MUST write a `manifest.json` in each exported album folder listing for each item: source path, exported entry name, content hash, capture timestamp, matched event id and title, and confidence.
- **FR-032**: System MUST write a top-level `report.csv` summarizing all exported albums (album name, event date, item count, photo count, video count, mode used: symlink|copy) and a per-item CSV (or a section) covering at least item path, album, event, confidence.
- **FR-033**: System MUST NOT modify, move, overwrite, or delete any original media file or original Google Takeout file during any operation.
- **FR-034**: System MUST be safely re-runnable: re-exporting the same album does not duplicate existing entries and does not modify original files.
- **FR-034a**: When an approved album has been renamed since its last export, the system MUST NOT move, rename, or delete the previously written folder on disk. The new export MUST create a fresh folder under the new sanitized name, and `report.csv` MUST list both the new folder and the previously exported folder, with a status column marking the previous folder as `orphaned-by-rename`. Cleanup of orphaned folders is left to the user (no destructive path in the app).

**Optional Google Photos Integration (feature-flagged, OFF by default)**

- **FR-035**: System MUST gate all Google Photos cloud features (Picker import, app-created album upload) behind a feature flag that is OFF by default; no Google Photos network calls occur while the flag is OFF.
- **FR-036**: System MUST, when enabled, support importing a user-selected batch of media via the Google Photos Picker. Selected items MUST be downloaded into a dedicated `picker-cache/` directory under the app's working data directory, content-hashed on arrival, and registered in the local database with provenance `picker` and the originating Google Photos id; thereafter they are treated identically to Takeout items for ingestion, matching, and export. A Picker selection that includes an already-cached item (same content hash or same Google Photos id) MUST reuse the cached bytes and MUST NOT re-download.
- **FR-037**: System MUST, when enabled, support creating a new app-created Google Photos album and uploading the media of an approved local album into it, and MUST surface clear errors for items the API will not accept.
- **FR-038**: System MUST disclose, before requesting OAuth consent for cloud features, what data leaves the device and what scopes are requested, and MUST request the minimum scopes needed for the chosen action.
- **FR-039**: System MUST NOT advertise, attempt, or imply automatic reorganization of the user's existing (non-app-created) Google Photos library.

**Jobs, Resume, Cancellation**

- **FR-040**: System MUST run long operations (scan, calendar import, match, export, upload) as background jobs with persisted state.
- **FR-041**: System MUST show live progress (items processed / total, current phase) and MUST allow the user to cancel any running job; cancellation MUST leave the database in a consistent state.
- **FR-042**: System MUST resume an interrupted job from the last committed checkpoint without redoing completed work.
- **FR-042a**: When a Google Calendar OAuth call fails with an authorization error (revoked token, refresh-token expired, persistent 401) during a running job, the system MUST pause the job with its checkpoint persisted and surface a clear in-UI "re-authorize Google Calendar to continue" prompt; on successful re-authorization the job MUST resume from the checkpoint without re-doing completed work. Transient errors (HTTP 429 rate-limit, 5xx) MUST be retried with exponential backoff before the job is paused. The system MUST NOT silently fail the job and MUST NOT silently complete a match against partial calendar data; a paused job that is cancelled MUST clearly record which events were and were not imported.

**Privacy, Logging, Platform**

- **FR-043**: System MUST keep all media, derived metadata, calendar data, and export output on the local machine by default; no telemetry or analytics.
- **FR-044**: System MUST produce structured logs for ingest, match, and export operations including a job id, and MUST NOT include OAuth secrets, media bytes, or full file contents in logs.
- **FR-045**: System MUST run on macOS, Windows, and Linux with Python 3.12+.

### Key Entities

- **Media Item**: a unique piece of media identified by content hash, with one or more source paths (originals and Picker copies), a chosen capture timestamp + timezone, file size, type, optional Google Photos id, ingestion provenance (takeout|picker), and an error/status indicator.
- **Calendar Event**: one instance (including each occurrence of a recurring event) with stable id, title, start, end, timezone, optional location/description/attendees, and source calendar id.
- **Media-Event Match**: a candidate link between one Media Item and one Calendar Event with a confidence score, a category (in-event | buffered | date-only), an optional location/keyword bonus, and a "recommended" flag.
- **Proposed Album**: a user-facing grouping anchored on a Calendar Event with a display name, a sanitized folder name, a status (proposed | approved | rejected | exported), membership of Media Items, and any user-applied rename/merge/split history.
- **Album Item**: the membership row linking a Proposed Album to a Media Item (so an item can theoretically live in multiple albums when the multi-membership mode is on).
- **Scan/Match/Export Job**: a row tracking a long-running operation with type, status (queued | running | paused | cancelled | failed | completed), progress counters, started/finished timestamps, and a checkpoint cursor used for resume.
- **Error Record**: a per-item failure with file path (or event id), phase (scan | extract | match | export | upload), reason, and timestamp.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Given a fixture Takeout folder of 100 media items and a fixture set of calendar events covering the same date range, the user can complete the journey "ingest → review proposed albums → approve → export to local folders" in under 10 minutes on a typical consumer laptop, with no manual intervention beyond clicking approve.
- **SC-002**: At least 90% of media items in the fixture that (a) fall inside a calendar event's time span (no buffer) AND (b) have a sidecar / EXIF / video-container timestamp source are matched to that event with the highest confidence level. Items whose only timestamp source is filename or filesystem mtime are excluded from this 90% target by design (they are capped at medium/low confidence).
- **SC-003**: First-time ingest + match of a 100,000-item Takeout archive completes within a single overnight run (≤ 8 hours) on a typical consumer laptop, and a subsequent re-run with no file changes completes in under 5 minutes (incremental).
- **SC-004**: Memory use during ingest of 100,000 items stays at or below ~1 GB steady-state on a typical consumer laptop.
- **SC-005**: After any export — dry-run or real — every original media file under the Takeout source directory is byte-identical and at the same path it had before the export started (verified by re-hashing).
- **SC-006**: When a scan or match job is killed at any point and restarted, no media file is re-hashed or re-metadata-extracted if its path, size, and mtime are unchanged; the resumed job reaches the same final state as an uninterrupted run.
- **SC-007**: Opening any review view (album list, single album with 5,000 items, unmatched-by-date) renders the first page in under 2 seconds on a typical consumer laptop.
- **SC-008**: A media file present at multiple Takeout paths or via both Takeout and Picker appears exactly once in `report.csv` and exactly once per album it belongs to.
- **SC-009**: With the Google Photos feature flag OFF, the app makes zero network calls to Google Photos endpoints during a complete ingest → review → export cycle.
- **SC-010**: The README explains, in language a non-technical reader can follow, that full automatic reorganization of an existing Google Photos library is not supported via the current Google Photos API, and that Google Takeout is the recommended bulk-processing path.
- **SC-011**: When export is requested on a filesystem that does not support symlinks, the app informs the user before writing anything and proceeds in copy mode only after the user confirms (or has pre-configured copy mode).
- **SC-012**: For each proposed album, the user can rename, merge with another album, split, or reject it and see the change reflected in the next export (no schema or file-system corruption across these operations, verified by re-running export and checking manifests and `report.csv`).

## Assumptions

- **Single local user per installation**: one Google account configured per app data directory in v1; multi-account support is out of scope.
- **Typical consumer laptop** (used in SC-001/003/004/007) is interpreted as: 4+ physical CPU cores, 8+ GB RAM, an internal SSD, and an external/internal disk with the Takeout export on a non-removable medium.
- **Storage layout**: app data (SQLite database, logs, OAuth tokens) lives under the OS-standard per-user application data directory; the user picks the Takeout source path and the export root path explicitly.
- **Timezones**: when a media item lacks per-item timezone metadata, the user's configured system local timezone is assumed; the assumption is visible in the per-item details.
- **HEIC handling**: HEIC files are ingested and exported as-is (symlinked or copied); on-the-fly conversion to JPEG for previews is out of scope for v1 — thumbnails for HEIC may be unavailable on platforms without a HEIC decoder, and that is acceptable.
- **Multi-album membership**: OFF by default; each media item belongs to at most one proposed album (its recommended match). The user can toggle the mode globally to allow multi-membership.
- **Calendar sidecar source of truth**: when EXIF and Google sidecar timestamps disagree, the sidecar `photoTakenTime` wins because it reflects Google's recorded capture moment; the disagreement is logged and surfaced.
- **No cloud infrastructure**: v1 has no server component; everything runs on the user's machine. Network is only used to talk to Google APIs the user has authorized.
- **No automatic deletion**: nothing in v1 (or any future version) deletes user media. Reject means "remove from this album proposal", never "delete from disk".
- **UI framework choice deferred**: the spec is technology-agnostic. The plan phase will choose between FastAPI+HTMX and Streamlit (or another lightweight local web/desktop UI) based on simplicity, while honoring the UX requirements stated above.
- **Fixture data**: a small bundled sample (~10–20 media files spread across a few synthetic calendar events) ships with the repository so acceptance scenarios can be reproduced without a real Takeout export or Google account.

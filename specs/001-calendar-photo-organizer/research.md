# Phase 0 — Research & Technology Decisions

**Feature**: Calendar Photo Organizer (MVP)
**Branch**: `001-calendar-photo-organizer`
**Date**: 2026-05-23

The spec and clarifications resolve nearly every product decision. This phase
records the **technical** choices behind the Technical Context in `plan.md` and
the rationale that prevented each NEEDS-CLARIFICATION-equivalent from re-opening.

## Decisions

### D-001 — UI framework: FastAPI + Jinja2 + HTMX

- **Decision**: Embed a FastAPI application bound to `127.0.0.1`, render HTML
  via Jinja2 templates, and use HTMX for partial swaps (pagination,
  approve/reject buttons, progress streaming). No JS build step; ship
  `htmx.min.js` as a static file.
- **Rationale**:
  - Pagination/lazy-load for 100k items (FR-027) maps naturally to HTMX
    `hx-get` partial swaps; Streamlit's whole-page rerun model fights this.
  - Background-job UX (live progress, cancel) is straightforward with FastAPI
    + Server-Sent Events; Streamlit requires `st.empty()` polling loops that
    do not survive page reloads.
  - Testability: HTTP endpoints are trivially contract-testable with
    `httpx.AsyncClient`; Streamlit requires `streamlit.testing.v1` and
    couples test code to UI internals.
  - Constitution Engineering Standard "one UI framework per major version"
    requires a single choice; this is it.
- **Alternatives considered**:
  - **Streamlit**: faster to a first screen, but the rerun-on-every-interaction
    model and lack of native cancellation + SSE made every long-job feature
    awkward. Rejected.
  - **Tkinter / native desktop**: cross-platform UI is harder to test and to
    style consistently; HTMX requires zero install on the user's side beyond
    a browser. Rejected.
  - **Electron/Tauri**: violates the "no npm build pipeline" simplicity goal
    and significantly grows the install footprint. Rejected.

### D-002 — Database access: stdlib `sqlite3` + thin repository layer (no ORM)

- **Decision**: Use Python's stdlib `sqlite3` driver directly, with one
  `Repository` class per entity exposing typed methods. WAL mode enabled on
  every connection. All queries parameterised.
- **Rationale**:
  - Schema is small (≤ 10 tables) and stable; the constitution requires
    explicit migrations with tests anyway, so an ORM's auto-migration feature
    would be ignored.
  - 100k-scale operations rely on hand-tuned queries with composite indexes
    (see `data-model.md`); raw SQL is the most direct expression.
  - Zero added dependency surface.
- **Alternatives considered**:
  - **SQLAlchemy Core**: nice query builder but adds 5 MB of deps for marginal
    benefit at our schema size. Rejected.
  - **SQLAlchemy ORM**: hides query shape; risky at 100k-row scans. Rejected.
  - **`sqlmodel`**: same downsides as SQLAlchemy ORM plus extra magic.
    Rejected.

### D-003 — Schema migrations: hand-rolled linear `0001_initial.sql`, `0002_*.sql`, …

- **Decision**: `db/migrations/NNNN_<name>.sql` files; a `_schema_version`
  table tracks the highest applied integer; `db.migrate.apply()` runs all
  files with version > current inside one transaction each.
- **Rationale**: Aligns with constitution's "every schema change ships with a
  migration and a test". Trivial to test, trivial to read. No DSL.
- **Alternatives considered**:
  - **`alembic`** (requires SQLAlchemy): rejected for the same reason as
    SQLAlchemy itself.
  - **`yoyo-migrations`**: works, but is an extra dep for a problem the
    constitution already constrains. Rejected.

### D-004 — Background jobs: in-process `asyncio` + `JobRunner`

- **Decision**: One `JobRunner` class per running job, using `asyncio.Task`
  with cooperative cancellation. Checkpoints (cursor, counters) are persisted
  to the `scan_jobs` row every N items (default N=200) or every M seconds
  (default M=5), whichever comes first. The UI gets progress via SSE.
- **Rationale**:
  - Single-user, single-machine. External brokers (Celery, RQ) would require
    Redis/RabbitMQ, violating Engineering Standard "no cloud infra for v1".
  - `asyncio` integrates with FastAPI naturally and supports clean
    cancellation via `Task.cancel()`.
  - Constitution Principle IV requires resumable, cancellable, checkpointed
    jobs — satisfied directly.
- **Alternatives considered**:
  - **`multiprocessing`**: useful for CPU-bound hashing, but the orchestration
    layer should still be `asyncio`. We use `asyncio.to_thread` to offload
    hashing/EXIF to a thread pool — keeps API uniform.
  - **`concurrent.futures.ProcessPoolExecutor`** for hashing: kept as an
    optional optimization (configurable worker count); default thread-pool is
    sufficient given I/O dominance.
  - **External queue (RQ/Celery)**: rejected, see above.

### D-005 — Timestamp extraction stack

- **Decision**: A single `MetadataExtractor` function takes a `Path` and
  returns a `CaptureTimestamp(value: datetime, tz: tzinfo | None, source_tier:
  Literal["sidecar","exif","video","filename","mtime"])`.
  Implementation order matches FR-008:
  1. `*.json` Google sidecar (`photoTakenTime.timestamp`) — authoritative on
     conflict (per spec Edge Cases).
  2. EXIF via `Pillow` (`PIL.Image.getexif()` → tags `DateTimeOriginal`,
     `OffsetTimeOriginal`); HEIC via `pillow-heif` when installed (graceful
     skip otherwise — Pillow can still read EXIF for HEIC on some platforms).
  3. Video container `creation_time` via **hachoir** (pure-Python). If
     `ffprobe` is on `PATH`, prefer it (faster on large MP4s); detected at
     startup and cached.
  4. Filename regex list (`IMG_YYYYMMDD_HHMMSS`, `VID_…`, `PXL_…`, `Screenshot_YYYY-MM-DD-HH-MM-SS`,
     bare `YYYY-MM-DD-HH-MM-SS`, bare `YYYYMMDD_HHMMSS`).
  5. Filesystem `stat().st_mtime`.
- **Rationale**: One pure function with explicit source tier feeds the
  source-tier cap in `matcher.py` (FR-014 per Clarification Q2). Easy to
  unit-test each path.
- **Alternatives considered**:
  - **`exifread`**: less robust than Pillow for malformed EXIF. Rejected.
  - **`pymediainfo`**: requires system libmediainfo; cross-platform install
    pain. Rejected as primary; users may install separately and we
    auto-detect.

### D-006 — Hashing: blake3 with sha256 fallback

- **Decision**: Use `blake3` (~5x faster than sha256 on typical media files);
  fall back to `hashlib.sha256` if `blake3` cannot be imported. The hash
  algorithm name is stored alongside the digest in `media_items.content_hash`
  so future re-hashes can verify.
- **Rationale**: At 100k items × ~2 MB average, hashing dominates first-run
  cost. blake3 saves hours. Fallback ensures the app installs on minimal
  systems.
- **Alternatives considered**:
  - **xxh3**: faster than blake3 but not cryptographic; collision risk for
    dedup at 100k+ is acceptable but blake3 is fast *and* collision-resistant.
  - **sha256 only**: 5× slower; rejected as default.

### D-007 — OAuth + Calendar API

- **Decision**: `google-auth-oauthlib` for installed-app OAuth flow (loopback
  redirect, port chosen at runtime), `google-api-python-client` for the
  Calendar v3 client. Scope: `https://www.googleapis.com/auth/calendar.readonly`.
  Tokens stored via `keyring` (OS keychain) with a file-fallback at
  `<user_data_dir>/auth/tokens.json` chmodded `0600`. Refresh handled by the
  google-auth `Credentials.refresh()` API; on `RefreshError`/persistent 401 a
  `CalendarAuthError` is raised from `calendar_client` and the `JobRunner`
  catches it, persists the job in `paused` state, and emits a
  `reauth_required` progress event (FR-042a, Clarification Q3).
- **Rationale**: Standard Google client stack; minimum scope; pause+re-auth
  matches the clarified failure mode.

### D-008 — Optional Google Photos integration (Picker + app-album upload)

- **Decision**: `google_photos_optional.py` is the **only** module that
  imports the Photos Library SDK or makes Picker HTTP calls. It is guarded by
  `config.feature_flags.google_photos_enabled` (default `false`); when the
  flag is `false`, the module is not even imported (lazy import inside the
  feature-flag check), so the SDK dependency can also be marked an extra
  (`pip install calendar-photo-organizer[google-photos]`).
  - **Picker**: HTTPS calls per the documented Picker REST flow (create
    session → poll → list media items → download bytes). Downloaded bytes
    land in `<user_data_dir>/picker-cache/<content-hash[:2]>/<content-hash>`
    (Clarification Q5).
  - **Upload to app-created album**: Photos Library
    `mediaItems:batchCreate` + album creation per the post-March-2025 scope
    `https://www.googleapis.com/auth/photoslibrary.appendonly` (only items
    uploaded by the app are visible to the app — explicitly disclosed in the
    UI before consent).
- **Rationale**: Single-file isolation (Principle V), removable extra.
- **Alternatives considered**:
  - **Library-API "everything"**: forbidden by Principle V and infeasible
    post-March-2025; rejected.

### D-009 — Symlink-vs-copy policy

- **Decision**: A `paths.probe_symlink_support(target_dir: Path) -> bool`
  utility creates and immediately removes a probe symlink in the target
  directory the first time export is requested for that path. If
  `OSError` / `WinError 1314` / `EPERM` is raised, symlink support is `False`
  for that target. The UI surfaces the result and asks the user to confirm
  copy mode before the first non-dry-run export to that target. The decision
  is cached per target path in the `export_targets` table.
- **Rationale**: Implements FR-030 and SC-011 (copy-mode requires explicit
  confirmation before disk writes). Probes are cheap and a one-time cost.
- **Alternatives considered**:
  - **Assume symlinks always work on Unix**: false on FAT32 / SMB shares.
    Rejected.
  - **Default to copy mode**: doubles disk for the common case. Rejected.

### D-010 — Folder-name sanitisation

- **Decision**: A pure function `sanitize_folder_name(display: str, *,
  max_len: int = 120) -> str` that:
  1. Trims whitespace and collapses runs of whitespace to single spaces.
  2. Replaces each character in `<>:"/\|?*` and ASCII control chars (`< 0x20`)
     with `_`.
  3. Strips trailing `.` and trailing spaces (Windows restriction).
  4. Rejects reserved Windows device names (`CON`, `PRN`, `AUX`, `NUL`,
     `COM1`–`COM9`, `LPT1`–`LPT9`) by prefixing `_`.
  5. Truncates to `max_len` characters preserving any leading `YYYY-MM-DD – `
     prefix.
  6. Disambiguates name collisions within the same export root by appending
     ` (2)`, ` (3)`, … (collision detected via DB lookup, not filesystem
     scan).
- **Rationale**: Tested via Hypothesis property tests covering all platforms.
  Database-driven disambiguation avoids races and is deterministic.

### D-011 — Confidence scoring + source-tier cap

- **Decision**: A confidence score `c ∈ {0.0..1.0}` is computed per match as
  `final = min(rule_score + bonus, source_cap)`, where:
  - `rule_score` ∈ {1.0 (in-event), 0.75 (in buffer), 0.5 (date-only/all-day)}.
  - `bonus` ∈ {0.0, 0.1} where the bonus is added when the event's location
    or title contains a token also present in the media's filename, folder
    path, sidecar location, or EXIF GPS-derived place name (when available).
  - `source_cap` ∈ {1.0 (sidecar/EXIF/video), 0.75 (filename), 0.5 (mtime)}
    per Clarification Q2.
  - Banding for UI/bulk-approve (Clarification Q1): high ≥ 0.85,
    medium ≥ 0.6, else low.
- **Rationale**: Single formula, easy to unit-test, easy to reason about.

### D-012 — Picker-cache layout & dedup

- **Decision**: Picker downloads are content-hashed in a streaming manner
  during fetch and stored at
  `<user_data_dir>/picker-cache/<hash[:2]>/<hash>` with the original filename
  preserved as a `.json` sidecar (`<hash>.json`) capturing the Google Photos
  id, original filename, mime, and download timestamp. On selection that
  includes an item whose content hash is already in `media_items`, the
  download is short-circuited (HEAD request to learn size, then compare with
  the cached file; if unsure, hash on the fly and reuse). This satisfies
  FR-036 ("MUST NOT re-download").

## Open questions

None. All clarifications from Phase /speckit.clarify are integrated, and every
spec assumption is mapped to a concrete decision above.

## Cross-references

- Spec functional requirements: `spec.md` §Requirements.
- Spec clarifications: `spec.md` §Clarifications (Session 2026-05-23).
- Constitution: `.specify/memory/constitution.md` v1.0.0.
- Schema: `data-model.md`.
- External-facing contracts: `contracts/`.

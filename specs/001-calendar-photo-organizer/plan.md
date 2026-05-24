# Implementation Plan: Calendar Photo Organizer (MVP)

**Branch**: `001-calendar-photo-organizer` | **Date**: 2026-05-23 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-calendar-photo-organizer/spec.md`

## Summary

Local-first Python application that ingests a Google Takeout export and the user's Google Calendar history, matches media to events using configurable time-buffer windows with source-tier-capped confidence scoring, lets the user review/refine/approve proposed albums in a small embedded web UI, and exports approved albums as folders of symlinks (with manifests and a CSV report) — all without ever modifying or deleting original media. An optional, feature-flagged Google Photos module supports Picker-based import (downloaded to a local cache) and app-created-album upload.

**Technical approach**: single-process Python 3.12+ application that serves a FastAPI + Jinja2 + HTMX UI on `127.0.0.1`, persists everything to a single SQLite database with versioned SQL migrations and indexes on every query path required for 100k-item scale, runs scan / match / export as cancellable, checkpointed `asyncio` jobs (no external task queue), and isolates the Google Photos cloud integration behind a single removable module gated by a feature flag that is OFF by default.

## Technical Context

**Language/Version**: Python 3.12+ (user-mandated; uses TaskGroup, native `Self`, PEP 695 generics where useful).

**Primary Dependencies**:

- Web/UI: `fastapi`, `uvicorn` (loopback only), `jinja2`, HTMX served from `static/` (no npm).
- CLI entry: `typer` (built on click; type-hint-native).
- Data: stdlib `sqlite3` (no ORM); thin repository layer over raw parameterised SQL; hand-rolled linear-version migrator.
- OAuth + Calendar: `google-auth`, `google-auth-oauthlib`, `google-api-python-client` (Calendar v3, read-only scope).
- Google Photos (optional, behind feature flag): `google-api-python-client` (Photos Library API for app-created-album upload) + Picker API HTTP calls via `httpx`.
- Image metadata + thumbnails: `Pillow`; HEIC via optional `pillow-heif` (degrade gracefully when missing).
- Video metadata: `hachoir` (pure-Python, cross-platform) primary; `ffprobe` used opportunistically when on `PATH` (faster, optional).
- Hashing: `blake3` (fast); fall back to `hashlib.sha256` if `blake3` unavailable on platform.
- Secrets storage: `keyring` (OS keychain) with restrictive-permission file fallback.
- OS-standard data directories: `platformdirs`.
- Structured logging: `structlog` with stdlib `logging` underneath.
- HTTP client (Picker, retries): `httpx` with `tenacity` for backoff.

**Storage**: a single SQLite database file (`cpo.sqlite3`) under the OS-standard per-user application data directory (`platformdirs.user_data_dir("calendar-photo-organizer")`). WAL mode. Every query path used in 100k-scale operations has a covering index (see `data-model.md`).

**Testing**: `pytest`, `pytest-asyncio`, `hypothesis` (property tests for sanitization and confidence scoring). Test matrix on macOS, Windows, and Linux runners via GitHub Actions. Per-OS markers (`@pytest.mark.symlink`, `@pytest.mark.windows`).

**Target Platform**: macOS 13+, Windows 10+, Linux (glibc ≥ 2.31). Single binary not required; `pipx install` and `python -m calendar_photo_organizer` are the supported install routes for v1.

**Project Type**: single project (desktop-style local web app — FastAPI process serves HTMX UI on loopback; no separate frontend build).

**Performance Goals**:

- First-time ingest + match of 100,000 items: ≤ 8 h on a typical consumer laptop (≈ 3.5 items/sec end-to-end, single host).
- Incremental rescan with no file changes: ≤ 5 min.
- Steady-state memory during ingest: ≤ 1 GB.
- UI: first paint of any review page ≤ 2 s; paginated views render ≤ 200 items per HTMX swap.

**Constraints**:

- Non-destructive on user media (constitution Principle I).
- All data local by default; zero network calls to Google Photos endpoints when the feature flag is OFF.
- Cross-platform symlinks: must detect support and fall back to copy with explicit user notice.
- 100k+ items requires streaming I/O (no full-list materialization).
- Resume from arbitrary kill point without re-hashing unchanged files.

**Scale/Scope**: 100,000+ media items, up to ~10,000 calendar event instances over a multi-year range, hundreds of proposed albums per archive. Single user, single account, single machine.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Constitution v1.0.0 — [.specify/memory/constitution.md](../../.specify/memory/constitution.md). Each principle and Engineering Standard evaluated against the planned design:

| Principle / Standard | Compliance | Mechanism in Plan |
|---|---|---|
| I. Data Safety & Non-Destructive (NON-NEGOTIABLE) | PASS | Dry-run is the default `export` mode (FR-028, contracted); writer module exposes only additive verbs (`create_album_folder`, `link_or_copy_item`, `write_manifest`); FR-033/034/034a forbid moving/deleting; integration test `test_originals_unchanged_after_export` re-hashes every Takeout source after export. |
| II. Privacy-First & Local-First | PASS | UI binds to `127.0.0.1` only; cloud features sit behind `config.feature_flags.google_photos_enabled` (default `false`); tokens stored via `keyring` with file fallback at `0600`; contract test `test_no_network_when_flag_off` asserts zero `httpx` calls during full ingest→export cycle with flag OFF. |
| III. Test-First Discipline (NON-NEGOTIABLE) | PASS | Tasks phase will order tests-first per module: timestamp extraction, matcher, dedup, sanitization, confidence cap, manifest/CSV. Cross-OS CI matrix mandated for symlink behaviour. |
| IV. Scalability by Streaming & Indexed Persistence | PASS | All scan and match routines are generator-based (`os.scandir`); SQLite WAL + composite indexes on (capture_ts), (content_hash), (event_id, start_utc, end_utc), (job_id, status); incremental scan keyed on `(path, size, mtime)`; `JobRunner` checkpoints every N rows and exposes `cancel()`. |
| V. API Honesty & Modular Optional Integrations | PASS | `google_photos_optional.py` is the only file importing Photos/Picker SDKs; removable by deleting that file + clearing the feature flag; README quickstart explicitly documents the post-March-2025 Library-API restrictions and recommends Takeout. |
| Engineering Standards — Python 3.12+, type hints | PASS | `pyproject.toml` pins `requires-python = ">=3.12"`; CI runs ruff + mypy `strict` on new modules; `from __future__ import annotations` allowed. |
| Engineering Standards — Logging | PASS | `structlog` configured in `logging_setup.py`; every job log line carries `job_id`; no `print()` outside `cli.py`. |
| Engineering Standards — Platform support | PASS | All filesystem paths via `pathlib.Path`; symlink probe utility; CI runs on macOS, Windows, Linux. |
| Engineering Standards — Single UI framework | PASS | FastAPI + Jinja2 + HTMX chosen; Streamlit explicitly rejected (see Phase 0 research). |
| Engineering Standards — Performance budget | PASS | Targets above match Engineering Standards: ≤ 1 GB memory, incremental near-instant. |
| Engineering Standards — Schema migrations | PASS | `db/migrations/NNNN_*.sql` files applied in order by hand-rolled `apply()`; `tests/unit/test_migrations.py` exercises each migration on a populated fixture DB. |

**Result**: PASS. No deviations. **Complexity Tracking section is empty.**

## Project Structure

### Documentation (this feature)

```text
specs/001-calendar-photo-organizer/
├── plan.md              # This file
├── research.md          # Phase 0 — technology decisions + rationale
├── data-model.md        # Phase 1 — SQLite schema, entities, indexes
├── quickstart.md        # Phase 1 — developer + end-user setup
├── contracts/           # Phase 1 — CLI, HTTP, and on-disk artifact contracts
│   ├── cli.md
│   ├── http-api.md
│   └── export-artifacts.md
├── checklists/
│   └── requirements.md  # From /speckit.specify
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

Single Python project. Layout follows the structure suggested by the user, adapted to a `src/` package and an idiomatic Python project skeleton.

```text
pyproject.toml
README.md
.github/workflows/ci.yml          # ruff + mypy + pytest matrix (macOS/Windows/Linux)

src/calendar_photo_organizer/
├── __init__.py
├── __main__.py                   # python -m calendar_photo_organizer
├── cli.py                        # typer CLI: scan, import-calendar, match, propose, export, demo
├── config.py                     # pydantic-settings; feature flags; paths; buffers
├── logging_setup.py              # structlog config; job_id contextvar
├── db/
│   ├── __init__.py
│   ├── connection.py             # sqlite3 connection factory; WAL pragma
│   ├── migrate.py                # hand-rolled linear migrator
│   ├── migrations/
│   │   └── 0001_initial.sql
│   └── repositories/
│       ├── media.py
│       ├── events.py
│       ├── matches.py
│       ├── albums.py
│       ├── jobs.py
│       └── errors.py
├── models.py                     # dataclasses for the seven Key Entities
├── hashing.py                    # blake3 / sha256 fallback
├── metadata_extractor.py         # sidecar → EXIF → video → filename → mtime, with source tier
├── photos_takeout_importer.py    # os.scandir-driven streaming scanner + sidecar pairing
├── calendar_client.py            # OAuth + Calendar v3; pause-on-401 hook
├── matcher.py                    # buffered + date-only matching with source-tier cap
├── album_planner.py              # proposal naming, sanitisation, merge/split/rename ops
├── exporter.py                   # dry-run + symlink/copy + manifest.json + report.csv
├── google_photos_optional.py     # Picker download to picker-cache/, app-created-album upload
├── jobs/
│   ├── __init__.py
│   ├── runner.py                 # JobRunner: asyncio + checkpoints + cancellation
│   └── progress.py               # progress events streamed to UI
└── ui/
    ├── __init__.py
    ├── app.py                    # FastAPI app, loopback bind, htmx routes
    ├── deps.py                   # request-scoped repository wiring
    ├── routes/
    │   ├── dashboard.py
    │   ├── albums.py             # list, detail, rename/merge/split/reject, approve
    │   ├── unmatched.py
    │   ├── jobs.py               # progress stream, cancel
    │   ├── export.py             # dry-run preview, run
    │   └── auth.py               # Google Calendar OAuth start/callback
    ├── templates/                # Jinja2 + HTMX partials
    └── static/                   # htmx.min.js, css

tests/
├── conftest.py                   # tmp data dir, fixture DB factory
├── fixtures/
│   ├── takeout_sample/           # ~15 media files spanning ~5 synthetic events
│   ├── takeout_sample/sidecars/
│   └── calendar_sample.json      # canned Google Calendar API response
├── unit/
│   ├── test_metadata_extractor.py     # all five source tiers + conflicts
│   ├── test_matcher.py                 # in-event, buffered, date-only, overlap, all-day, TZ shift
│   ├── test_confidence_cap.py          # source-tier cap semantics
│   ├── test_hashing.py
│   ├── test_album_planner.py           # sanitisation, dedup names, merge/split
│   ├── test_dedup.py                   # hash, filename+size, Google Photos id
│   ├── test_migrations.py              # each migration on populated DB
│   └── test_jobs_runner.py             # checkpoint, cancel, resume
├── integration/
│   ├── test_takeout_ingest_end_to_end.py
│   ├── test_calendar_oauth_pause_resume.py  # FR-042a
│   ├── test_dry_run_export.py
│   ├── test_real_export_symlink_then_copy_fallback.py
│   ├── test_resume_after_interruption.py
│   ├── test_originals_unchanged_after_export.py    # SC-005
│   ├── test_rename_orphan_in_report.py             # FR-034a
│   └── test_no_network_when_flag_off.py            # SC-009
└── contract/
    ├── test_cli_contract.py
    ├── test_http_api_contract.py
    └── test_export_artifacts_contract.py            # manifest.json + report.csv schemas
```

**Structure Decision**: single Python project under `src/calendar_photo_organizer/`. Justification: the application is one process (FastAPI + background job runner + CLI), all running locally; the user-suggested `app/` layout maps cleanly into this `src/` package without artificial frontend/backend separation. The optional Google Photos integration lives in **one** file (`google_photos_optional.py`) as required by Principle V, and the UI lives in `ui/` so the constitution-mandated "one UI framework per major version" boundary is structurally enforced.

## Complexity Tracking

> Fill ONLY if Constitution Check has violations that must be justified.

*No violations. Section intentionally empty.*

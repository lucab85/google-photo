---
description: "Task list for Calendar Photo Organizer (MVP)"
---

# Tasks: Calendar Photo Organizer (MVP)

**Input**: Design documents from `/specs/001-calendar-photo-organizer/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: REQUIRED. Constitution Principle III (Test-First Discipline, NON-NEGOTIABLE) mandates unit + integration + contract tests for every non-trivial module.

**Organization**: Tasks are grouped by user story. Phase 1 (Setup) and Phase 2 (Foundational) must complete before any user-story phase begins. After Phase 2, user stories may proceed in priority order (P1 → P2 → P3 → P4) or in parallel where staffed.

## Format

`- [ ] TaskID [P?] [Story?] Description with file path`

- **[P]** — task is parallelizable (different files, no live dependency on another in-flight task)
- **[USn]** — required label for tasks inside a user-story phase; Setup / Foundational / Polish carry no story label

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Initialize the Python project skeleton, tooling, and CI matrix that every later phase relies on. Outputs no runtime code.

- [X] T001 Create the package skeleton: `src/calendar_photo_organizer/__init__.py`, `src/calendar_photo_organizer/__main__.py`, empty `src/calendar_photo_organizer/{db,jobs,ui,ui/routes,ui/templates,ui/static,db/repositories,db/migrations}/__init__.py` (plus the `db/migrations/` directory without `__init__.py`), and `tests/{unit,integration,contract,fixtures}/__init__.py` per [plan.md](./plan.md) §Project Structure.
- [X] T002 Author `pyproject.toml` at the repo root with `requires-python=">=3.12"`, the runtime deps from [research.md](./research.md) (`fastapi`, `uvicorn`, `jinja2`, `typer`, `pydantic-settings`, `google-auth`, `google-auth-oauthlib`, `google-api-python-client`, `Pillow`, `hachoir`, `blake3`, `keyring`, `platformdirs`, `structlog`, `httpx`, `tenacity`), and the extras `[dev]` (`pytest`, `pytest-asyncio`, `hypothesis`, `ruff`, `mypy`, `pre-commit`), `[heic]` (`pillow-heif`), `[google-photos]` (Google Photos SDK + Picker deps). Configure the `cpo` script entrypoint pointing at `calendar_photo_organizer.cli:app`. Use Hatchling.
- [X] T003 [P] Add `ruff.toml` (or `[tool.ruff]` section in `pyproject.toml`) configured for Python 3.12, line-length 100, enable `E,F,I,B,UP,SIM,N,RUF`.
- [X] T004 [P] Add `[tool.mypy]` section in `pyproject.toml` with `strict = true` scoped to `src/calendar_photo_organizer/**`, `python_version = "3.12"`, and `disallow_any_generics`.
- [X] T005 [P] Add `.pre-commit-config.yaml` running `ruff`, `ruff-format`, `mypy`, and a `no-print-outside-cli` custom hook (regex grep for `\bprint\(` excluding `cli.py`).
- [X] T006 [P] Add `.github/workflows/ci.yml` matrix on `{ubuntu-latest, macos-latest, windows-latest}` × Python `3.12` running `ruff check`, `mypy`, then `pytest -q`. Mark `tests/integration/test_real_export_symlink_then_copy_fallback.py` to require admin/Developer-Mode on Windows or skip with reason.
- [X] T007 [P] Add repo-level `.gitignore` entries for `.venv/`, `__pycache__/`, `*.egg-info/`, `dist/`, `build/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `.tmp/`, `dry-runs/`.
- [X] T008 [P] Add `README.md` stub at the repo root that links to [specs/001-calendar-photo-organizer/quickstart.md](./quickstart.md) and includes the Principle V honesty disclosure (no full Google Photos library reorganization; Takeout is the supported bulk path). Fuller content is finalized in T086.

**Checkpoint**: `pipx install -e .` succeeds, `pytest -q` finds zero tests, `ruff check` and `mypy --strict` pass on the empty package.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Build the cross-cutting infrastructure every user story depends on — config, logging, SQLite schema + migrator, repositories, domain models, path/symlink utilities, hashing, and the cancellable checkpointed `JobRunner`. NO user-story work begins until this phase is green.

**⚠️ CRITICAL**: This phase blocks every US1/US2/US3/US4 task below.

### Foundational tests (write first, MUST FAIL before implementation)

- [X] T009 [P] Unit test for config + feature-flag defaults in `tests/unit/test_config.py` — verify `feature_flags.google_photos_enabled` defaults to `False`, default pre-buffer `2h`, post-buffer `4h`, `multi_album_membership=False`, data dir resolves via `platformdirs`.
- [X] T010 [P] Unit test for structured logging setup in `tests/unit/test_logging_setup.py` — assert `job_id` contextvar appears in JSON output, no secrets in formatter, no `print()` calls anywhere under `src/calendar_photo_organizer/` (regex sweep).
- [X] T011 [P] Unit test for the migrator in `tests/unit/test_migrations.py` — applies `0001_initial.sql` to an in-memory DB, asserts `schema_meta.version=1`, every table from [data-model.md](./data-model.md) exists, every required index exists (query `sqlite_master`), `PRAGMA journal_mode` returns `wal`, `PRAGMA foreign_keys` returns `1`.
- [X] T012 [P] Unit test for `db.connection.connect()` in `tests/unit/test_db_connection.py` — returns a connection with WAL + foreign keys ON, row-factory yields `sqlite3.Row`.
- [X] T013 [P] Unit test for `hashing.hash_file()` in `tests/unit/test_hashing.py` — produces deterministic blake3 digest with `blake3:` prefix; falls back to `sha256:` prefix when `blake3` is monkeypatched to `ImportError`; streaming hashing handles a 100 MB fixture in chunks (memory bound asserted via `tracemalloc`).
- [X] T014 [P] Unit test for symlink probe in `tests/unit/test_paths.py` — `probe_symlink_support(tmp_path)` returns `True` on POSIX in tmp; returns `False` when `Path.symlink_to` is monkeypatched to raise `OSError(EPERM)`; result is cached for the same target.
- [X] T015 [P] Unit test for folder-name sanitization in `tests/unit/test_album_planner_sanitize.py` — Hypothesis property test asserting (a) only `[\w \-–_.()]` and accented chars remain, (b) no trailing `.` or space, (c) reserved Windows names get `_` prefix, (d) length ≤ 120, (e) `YYYY-MM-DD – ` prefix preserved across truncation.
- [X] T016 [P] Unit test for `JobRunner` in `tests/unit/test_jobs_runner.py` — drives a fake job to checkpoint every 200 items, cancels via `Task.cancel()` at item 350, restarts, verifies items 0–199 are *not* re-executed (resume from checkpoint 1), terminal state `cancelled`/`completed` written to `scan_jobs`.

### Foundational implementation

- [X] T017 Implement `src/calendar_photo_organizer/config.py` — `pydantic-settings` model `Settings` with fields from [research.md](./research.md) D-001..D-012 (data_dir resolved via `platformdirs.user_data_dir("calendar-photo-organizer")`, env prefix `CPO_`, feature flags struct, buffers, hashing.algorithm preference, multi_album_membership). Provides `get_settings()` singleton.
- [X] T018 Implement `src/calendar_photo_organizer/logging_setup.py` — `structlog` config; `job_id` contextvar bound by `JobRunner`; JSON formatter for `--log-format=json`, key=value for default. Forbid `print()` (enforced by T005 pre-commit hook).
- [X] T019 Implement `src/calendar_photo_organizer/models.py` — `StrEnum`s and `dataclass`es mirroring [data-model.md](./data-model.md) §Domain Models. Public types: `CaptureSourceTier`, `Provenance`, `MatchRule`, `ConfidenceBand`, `AlbumStatus`, `JobStatus`, `MediaItem`, `MediaPath`, `CalendarEvent`, `MediaEventMatch`, `ProposedAlbum`, `AlbumItem`, `ScanJob`, `ErrorRecord`, `ExportTarget`, `ExportedAlbum`. No SQL here.
- [X] T020 Author the initial SQL migration `src/calendar_photo_organizer/db/migrations/0001_initial.sql` — every table and index from [data-model.md](./data-model.md), partial unique index on `media_event_matches(media_id) WHERE is_recommended=1`, the orphan-by-rename trigger (Invariant I-4), `PRAGMA journal_mode=WAL`, `PRAGMA foreign_keys=ON`, set `schema_meta.version=1`.
- [X] T021 Implement `src/calendar_photo_organizer/db/connection.py` — `connect(data_dir: Path) -> sqlite3.Connection` factory, WAL + foreign keys, row factory, retry on `OperationalError("database is locked")` with short backoff.
- [X] T022 Implement `src/calendar_photo_organizer/db/migrate.py` — `current_version(conn)`, `pending_migrations(data_dir)`, `apply(conn, data_dir)` (one transaction per file, ordered by filename, updates `schema_meta.version`).
- [X] T023 [P] Implement `src/calendar_photo_organizer/db/repositories/media.py` — repository with `upsert_by_content_hash`, `add_alternate_path`, `find_by_path_size_mtime` (incremental-skip query), `find_unmatched`, `get_with_paths`, all parameterised.
- [X] T024 [P] Implement `src/calendar_photo_organizer/db/repositories/events.py` — `upsert_event` keyed on `(google_event_id, calendar_id)`, `find_in_window`, `find_by_date`.
- [X] T025 [P] Implement `src/calendar_photo_organizer/db/repositories/matches.py` — `replace_matches_for_media`, `set_recommended`, `count_by_band`, `iter_for_album_proposal`.
- [X] T026 [P] Implement `src/calendar_photo_organizer/db/repositories/albums.py` — CRUD for `proposed_albums` and `album_items`; respects Invariant I-3 (single-album membership default), supports merge/split via `merged_from_json`/`split_from_id`.
- [X] T027 [P] Implement `src/calendar_photo_organizer/db/repositories/jobs.py` — `create`, `set_status`, `set_pause_reason`, `update_checkpoint`, `incr_processed`, `latest_of_type`.
- [X] T028 [P] Implement `src/calendar_photo_organizer/db/repositories/errors.py` — `record(job_id, phase, subject_kind, subject, reason, detail)`; never raises.
- [X] T029 [P] Implement `src/calendar_photo_organizer/hashing.py` — `hash_file(path: Path) -> str` returning `algo:hexdigest`; chunked read (1 MiB); blake3 with sha256 fallback (lazy import + fall-back constant).
- [X] T030 [P] Implement `src/calendar_photo_organizer/paths.py` — `probe_symlink_support(target_dir: Path) -> bool` (creates and removes a probe symlink, catches `OSError/PermissionError/NotImplementedError`); `link_or_copy(src, dst, mode)` honoring `mode ∈ {"symlink","copy"}`. Cross-platform via `pathlib`.
- [X] T031 Implement `src/calendar_photo_organizer/album_planner.py` — pure `sanitize_folder_name(display, max_len=120)` matching D-010; DB-driven collision disambiguation `disambiguate_folder_name(albums_repo, target_id, base)`.
- [X] T032 Implement `src/calendar_photo_organizer/jobs/runner.py` — `JobRunner(jobs_repo, errors_repo)` exposing `await runner.run(job_type, coro_factory, *, checkpoint_every=200, heartbeat_seconds=5)`, cooperative cancellation via `asyncio.CancelledError`, persisted checkpoint via `jobs_repo.update_checkpoint`, emits progress events to an injectable `ProgressSink`.
- [X] T033 Implement `src/calendar_photo_organizer/jobs/progress.py` — `ProgressSink` interface, in-memory pub/sub for SSE consumers, `progress | paused | reauth_required | completed | failed | cancelled` event types.
- [X] T034 Author a tiny `cpo init` command in `src/calendar_photo_organizer/cli.py` that wires `Settings` + `connect` + `migrate.apply` (other CLI commands are added in later phases).
- [X] T035 Build the shared fixture under `tests/fixtures/takeout_sample/` (~15 small media files: 6 JPEGs with EXIF, 2 PNG screenshots, 2 HEIC stubs, 3 MP4s, 2 files without any metadata) plus matching `*.json` sidecars and `tests/fixtures/calendar_sample.json` (5 events covering the same date range, one all-day, two overlapping, one with location). Used by every later integration test.

**Checkpoint**: All Phase-2 tests (T009–T016) pass. `cpo init` creates a working DB. No user-story task may start before this checkpoint.

---

## Phase 3: User Story 1 — Bulk-organize Takeout into reviewable event albums (Priority: P1) 🎯 MVP

**Story goal** ([spec.md](./spec.md) §US1): import a Google Takeout folder + Google Calendar events for a chosen date range into the local DB, run the matcher with source-tier-capped confidence, generate proposed albums, and let the user review them in the UI.

**Independent Test**: run `cpo calendar-import --from 2024-07-01 --to 2024-07-31` + `cpo scan tests/fixtures/takeout_sample` + `cpo match` + `cpo propose`, then `cpo review serve` and verify the dashboard counters, album list with bands, album detail view, and Unmatched-by-date view all render against the fixture.

### Tests for User Story 1 (write first, MUST FAIL before implementation)

- [X] T036 [P] [US1] Unit test for metadata extraction in `tests/unit/test_metadata_extractor.py` — for each of the 5 source tiers, assert the correct `(timestamp, tz, source_tier)` tuple; assert sidecar wins on EXIF/sidecar conflict; assert filename regex covers `IMG_`, `VID_`, `PXL_`, `Screenshot_`, bare `YYYYMMDD_HHMMSS`; assert items with no parseable timestamp return `None` (FR-008, Clarification Q2).
- [X] T037 [P] [US1] Unit test for the matcher in `tests/unit/test_matcher.py` — in-event match → confidence 1.0; buffered match → 0.75; date-only (all-day) → 0.5; overlapping events keep all candidates and recommend the highest-confidence; timezone-shifted timestamp uses event's local day (FR-013/014).
- [X] T038 [P] [US1] Unit test for source-tier cap in `tests/unit/test_confidence_cap.py` — `min(rule_score + bonus, source_cap)` enforced; filename-sourced in-event match capped at 0.75; mtime-sourced in-event match capped at 0.5; bonus never raises above cap (Clarification Q2, D-011).
- [X] T039 [P] [US1] Unit test for dedup in `tests/unit/test_dedup.py` — same content hash from two paths registers one `media_items` row and two `media_paths` rows; Google Photos id collision dedups; report counts collapsed (FR-010, SC-008).
- [X] T040 [P] [US1] Unit test for album-name proposal in `tests/unit/test_album_planner_proposal.py` — given an event and matched media, `propose_album_for(event, items)` produces `display_name = f"{YYYY-MM-DD} – {event.title}"`, `folder_name = sanitize(display_name)`; multiple events same day → distinct names; collision suffix `(2)` only when titles collide (FR-018/019).
- [X] T041 [P] [US1] Integration test for end-to-end ingest in `tests/integration/test_takeout_ingest_end_to_end.py` — run scan + calendar-import + match + propose over the fixture; assert dashboard counters match expected (scanned, matched, unmatched, duplicates, errors); assert ≥ 90 % of fixture items inside an event window with sidecar/EXIF tier are matched at `high` band (SC-002).
- [X] T042 [P] [US1] Integration test for resume in `tests/integration/test_resume_after_interruption.py` — start `scan`, kill the runner after first checkpoint, restart; assert no file is re-hashed (count `hash_calls` via a test double); assert the resumed job reaches the same final state as an uninterrupted run (SC-006).
- [X] T043 [P] [US1] Integration test for calendar OAuth pause/resume in `tests/integration/test_calendar_oauth_pause_resume.py` — inject a fake `Credentials` that raises `RefreshError` mid-import; assert the job moves to `paused` with `pause_reason='reauth_required'`; after a fake re-auth, the job resumes from its checkpoint without re-importing already-stored events (FR-042a, Clarification Q3).
- [X] T044 [P] [US1] Contract test for the HTTP dashboard / album / unmatched routes in `tests/contract/test_http_api_contract.py` — server binds only to `127.0.0.1` (asserts `0.0.0.0` not used), `GET /` returns 200 + counters, `GET /albums?page=1&page_size=50` returns ≤ 50 rows, `GET /albums/{id}` paginates items, `GET /unmatched?date=YYYY-MM-DD` paginates by date, `GET /healthz` returns `ok`. Maps to C-HTTP-1, C-HTTP-3.
- [X] T045 [P] [US1] Contract test for the CLI in `tests/contract/test_cli_contract.py` — covers C-CLI-3 (uninitialised DB → exit 2 with `db-not-initialised`) and C-CLI-4 (final JSON log line); `cpo scan` re-run on an unchanged dir does not call `hash_file` (C-CLI-5).

### Implementation for User Story 1

- [X] T046 [US1] Implement `src/calendar_photo_organizer/metadata_extractor.py` — `extract(path: Path) -> CaptureTimestamp | None` running the 5-tier pipeline (sidecar → EXIF via Pillow → video via hachoir, opportunistic `ffprobe` if on `PATH` → filename regex chain → mtime); records source tier and tz. HEIC handled via `pillow-heif` when available, degrades gracefully otherwise. Errors routed to `errors_repo` and return `None` for the item (FR-012).
- [X] T047 [US1] Implement `src/calendar_photo_organizer/photos_takeout_importer.py` — streaming `os.scandir`-based recursive walk; pairs media files with `*.json` sidecars by filename rules; calls `hashing.hash_file` only when `(path, size, mtime)` differs from any existing `media_paths` row (FR-011); upserts via `media_repo.upsert_by_content_hash`; appends alternate paths for dedups; routes per-item errors to `errors_repo`; checkpoints via the `JobRunner` callback.
- [X] T048 [US1] Implement `src/calendar_photo_organizer/calendar_client.py` — installed-app OAuth flow (loopback redirect, random port), token storage via `keyring` with `0600` file fallback, Calendar v3 `events.list` with `singleEvents=True` (FR-003, recurring instances), incremental `etag`/`syncToken` reuse, `CalendarAuthError` raised on persistent 401/`RefreshError`, `httpx`+`tenacity` exponential backoff on 429/5xx (FR-042a).
- [X] T049 [US1] Implement `src/calendar_photo_organizer/matcher.py` — `match_one(media, events)` produces all candidate matches per FR-013, computes `confidence = min(rule_score + bonus, source_cap)` per D-011, bands per D-011, marks the highest-confidence candidate `is_recommended=1`, persists via `matches_repo.replace_matches_for_media`. Operates as a streaming generator over `media_repo` for 100k scale (Principle IV).
- [X] T050 [US1] Extend `src/calendar_photo_organizer/album_planner.py` with `propose_albums_from_recommended(matches_repo, events_repo, albums_repo, *, allow_multi_album: bool)` — iterates recommended matches grouped by event, generates proposed albums idempotently (re-running does not duplicate), enforces Invariant I-3 when `allow_multi_album=False`. Sanitization reuses T031.
- [X] T051 [US1] Build the FastAPI application shell in `src/calendar_photo_organizer/ui/app.py` — `create_app(settings)`; binds via `uvicorn.run(host="127.0.0.1", port=settings.ui_port)` (C-HTTP-1); Jinja2 templates rooted at `ui/templates/`; HTMX served from `ui/static/htmx.min.js`; mounts `routes/dashboard.py`, `routes/albums.py`, `routes/unmatched.py`, `routes/jobs.py`, `routes/auth.py` (Google Photos routes added in US4 only when flag is ON, C-HTTP-2).
- [X] T052 [US1] Implement `src/calendar_photo_organizer/ui/routes/dashboard.py` — `GET /` renders counters from `media_repo`, `matches_repo.count_by_band`, `errors_repo`; `GET /healthz` returns `ok`.
- [X] T053 [US1] Implement `src/calendar_photo_organizer/ui/routes/albums.py` — `GET /albums` paginated (default 50, max 200; C-HTTP-3) filtered by `band` and `status`; `GET /albums/{id}` paginated item list with thumbnails (Pillow-generated, cached under `<data_dir>/thumbs/`, fallback placeholder for HEIC without decoder; FR-023/027).
- [X] T054 [US1] Implement `src/calendar_photo_organizer/ui/routes/unmatched.py` — `GET /unmatched?date=YYYY-MM-DD&page=N`, grouped by date, paginated (FR-024).
- [X] T055 [US1] Implement `src/calendar_photo_organizer/ui/routes/jobs.py` — `GET /jobs/{id}` status page; SSE `GET /jobs/{id}/stream` subscribed to `progress.ProgressSink`, emits `progress` event at least every 10 s (C-HTTP-6); `POST /scan/run`, `POST /calendar/import`, `POST /match/run` schedule via `JobRunner`; `POST /jobs/{id}/cancel` honours cooperative cancellation.
- [X] T056 [US1] Implement `src/calendar_photo_organizer/ui/routes/auth.py` — `GET /auth/google/start`, `GET /auth/google/callback`, `POST /auth/google/reauth` (unpauses a `reauth_required` job and resumes it; FR-042a).
- [X] T057 [P] [US1] Author Jinja2 templates under `src/calendar_photo_organizer/ui/templates/`: `base.html` (HTMX include + layout), `dashboard.html`, `albums/list.html`, `albums/_row.html` (HTMX partial), `albums/detail.html`, `albums/_item.html`, `unmatched.html`, `jobs/detail.html`, `jobs/_progress.html`, `auth/reauth_required.html`. Use only server-rendered HTML; no client JS beyond bundled HTMX.
- [X] T058 [P] [US1] Vendor `htmx.min.js` under `src/calendar_photo_organizer/ui/static/htmx.min.js` and add minimal CSS `ui/static/app.css`.
- [X] T059 [US1] Extend `cli.py` with `cpo auth google-calendar`, `cpo calendar-import --from --to --calendar`, `cpo scan <TAKEOUT_DIR> [--workers N] [--include-ext …] [--restart]`, `cpo match [--pre-buffer 2h] [--post-buffer 4h] [--allow-multi-album]`, `cpo propose`, `cpo review serve [--port N] [--open]`, `cpo doctor`. All exit codes per [contracts/cli.md](./contracts/cli.md) (0/1/2/3/4); paused-pending-reauth jobs use exit 3.

**Checkpoint**: US1 fully demoable via the [quickstart.md](./quickstart.md) walkthrough steps 1–8. Tests T036–T045 pass. The MVP increment is shippable here even without US2.

---

## Phase 4: User Story 2 — Export approved albums to local folders with manifests (Priority: P2)

**Story goal** ([spec.md](./spec.md) §US2): materialize approved albums as folders of symlinks (or copies on filesystems that disallow symlinks), with a per-album `manifest.json` and a top-level `report.csv`, never touching originals, with a default dry-run mode.

**Independent Test**: from US1's approved fixture albums, run `cpo export <tmp>` (dry-run) and confirm `plan.json` is produced under `<data_dir>/dry-runs/`; run `cpo export <tmp> --write` and confirm folders + `manifest.json` + `report.csv` are written; re-hash every Takeout source and confirm they are byte-identical (SC-005).

### Tests for User Story 2 (write first, MUST FAIL before implementation)

- [X] T060 [P] [US2] Contract test for `manifest.json` and `report.csv` shapes in `tests/contract/test_export_artifacts_contract.py` — validates against the schemas in [contracts/export-artifacts.md](./contracts/export-artifacts.md), including `contract_version=1`, every required field, `status ∈ {current, orphaned-by-rename}` (C-EXP-1, C-EXP-4).
- [X] T061 [P] [US2] Integration test for dry-run mode in `tests/integration/test_dry_run_export.py` — assert nothing is written under `target_root` (filesystem snapshot before/after); `plan.json` and `plan-report.csv` appear only under `<data_dir>/dry-runs/<job_id>/` (C-EXP-3).
- [X] T062 [P] [US2] Integration test for real export with symlinks in `tests/integration/test_real_export_symlink_then_copy_fallback.py` — case A: target supports symlinks → folder entries are symlinks; case B: monkeypatch `paths.probe_symlink_support` to `False` and assert export returns the copy-mode-required error (C-CLI-2, C-HTTP-5); case C: with `--confirm-copy`, export succeeds in copy mode and each entry is a true file copy.
- [X] T063 [P] [US2] Integration test for originals-unchanged in `tests/integration/test_originals_unchanged_after_export.py` — record sha256 of every file under `tests/fixtures/takeout_sample/` before export; run dry-run *and* real export; re-hash; assert every original is byte-identical and at the same path (SC-005, C-EXP-2).
- [X] T064 [P] [US2] Integration test for re-export idempotency in `tests/integration/test_reexport_idempotent.py` — run export twice with no album changes; assert no symlink/file is recreated, `report.csv` gets a new run row but no duplicate item entries (FR-034).

### Implementation for User Story 2

- [X] T065 [US2] Implement `src/calendar_photo_organizer/exporter.py` — `plan(approved_albums, target, mode) -> ExportPlan` (pure, no FS writes); `execute(plan, *, dry_run: bool, writer)` driving `paths.link_or_copy`; writes `manifest.json` per album and `report.csv` at the target root; dry-run writes `plan.json` and `plan-report.csv` under `<data_dir>/dry-runs/<job_id>/` (C-EXP-3). Streams the album-items query (Principle IV) to avoid loading 100k items.
- [X] T066 [P] [US2] Implement `src/calendar_photo_organizer/ui/routes/export.py` — `GET /export/preview?target=PATH` renders the plan; `POST /export/run` creates a `scan_jobs` row of type `export`, dispatches to `JobRunner`; rejects symlink-mode against unsupported targets with 409 + copy-mode explainer (C-HTTP-5).
- [X] T067 [US2] Extend `cli.py` with `cpo export <TARGET_DIR> [--dry-run|--write] [--mode auto|symlink|copy] [--confirm-copy]`; default `--dry-run` (C-CLI-1); maps copy-mode-not-confirmed to exit 2 (C-CLI-2). Wires into `exporter.plan` + `exporter.execute`.
- [X] T068 [P] [US2] Author Jinja2 templates `src/calendar_photo_organizer/ui/templates/export/preview.html` and `export/_summary.html` showing the action plan and the copy-mode confirmation dialog when symlinks are unsupported.

**Checkpoint**: US2 complete. Tests T060–T064 pass. End-user can ingest, review, approve, and export the fixture archive. The MVP is feature-complete for the "Takeout-only" promise.

---

## Phase 5: User Story 3 — Refine: rename, merge, split, reject, re-tune buffers (Priority: P3)

**Story goal** ([spec.md](./spec.md) §US3): give the user direct control to rename/merge/split/reject albums, re-run matching with tweaked buffers, and toggle multi-album membership. Per Clarification Q1, also expose scoped bulk actions; per Clarification Q4, never move/delete previously exported folders on rename.

**Independent Test**: from US1's proposed albums, rename / merge / split / reject in the UI; change buffers and re-run match; toggle multi-album-membership; then re-export and verify `report.csv` includes a row marked `orphaned-by-rename` for the prior folder (FR-034a).

### Tests for User Story 3 (write first, MUST FAIL before implementation)

- [X] T069 [P] [US3] Unit test for album operations in `tests/unit/test_album_ops.py` — `rename(album_id, new_name)` updates `display_name` + `folder_name` + sets `user_renamed=1`; `merge(a,b,new_name)` produces union and writes `merged_from_json`; `split(album_id, media_ids, new_name)` produces two albums with disjoint membership when `allow_multi_album=False`; `reject(album_id)` sets `status='rejected'` and returns items to Unmatched (FR-020).
- [X] T070 [P] [US3] Unit test for the multi-album toggle in `tests/unit/test_multi_album_toggle.py` — with toggle OFF a media item exists in ≤ 1 active album; with toggle ON the same item may be linked from multiple albums; toggling OFF does NOT retroactively delete existing memberships (FR-021, Invariant I-3).
- [X] T071 [P] [US3] Integration test for rename-orphan reporting in `tests/integration/test_rename_orphan_in_report.py` — export, rename, re-export; assert (a) old folder is bit-identical to its post-first-export state, (b) new folder exists, (c) `report.csv` lists both, the old marked `orphaned-by-rename` with `notes="previous folder retained on disk; not modified"` (FR-034a, Clarification Q4).
- [X] T072 [P] [US3] Contract test for bulk-approve / bulk-reject in `tests/contract/test_bulk_actions_contract.py` — `POST /albums/bulk/approve` with `{band:"high"}` marks every `high` album approved; `POST /albums/bulk/reject` with `{band:"low", empty_only:true}` rejects only empty low-confidence albums; no album auto-approves at any other moment (FR-026, C-HTTP-4 still applies: cannot approve a rejected album without un-reject).
- [X] T073 [P] [US3] Integration test for re-match after buffer change in `tests/integration/test_rebuffer.py` — first match with default buffers, change to `pre=1h post=8h`, re-run `cpo match`, assert match-set differs as expected for fixture items at the buffer boundary; no media file re-hashed (FR-013, SC-006).

### Implementation for User Story 3

- [X] T074 [US3] Extend `src/calendar_photo_organizer/album_planner.py` with `rename`, `merge`, `split`, `reject`, `unreject` operations; trigger the orphan-by-rename DB trigger from T020 by updating `proposed_albums.folder_name` (Invariant I-4).
- [X] T075 [US3] Extend `src/calendar_photo_organizer/ui/routes/albums.py` with `POST /albums/{id}/rename`, `/merge`, `/split`, `/approve`, `/reject`, `/bulk/approve`, `/bulk/reject` per [contracts/http-api.md](./contracts/http-api.md). `409 Conflict` on approve-of-rejected (C-HTTP-4).
- [X] T076 [US3] Implement `src/calendar_photo_organizer/ui/routes/config.py` — `GET /config` shows buffers, multi-album toggle, feature flags; `POST /config` persists via `Settings` writer. Buffer change emits a one-shot "re-run match" HTMX banner.
- [X] T077 [P] [US3] Add Jinja2 templates `ui/templates/albums/_rename.html`, `_merge.html`, `_split.html`, `_bulk_actions.html`, and `ui/templates/config.html`.
- [X] T078 [US3] Extend `cli.py` with `cpo approve [--band high] [--album-id ID] [--all] [--reject]` (Clarification Q1) covering the same bulk semantics as the HTTP endpoints.

**Checkpoint**: US3 complete. Tests T069–T073 pass. Refinement journey is end-to-end; users can shape the output without ever risking the originals.

---

## Phase 6: User Story 4 — Optional Google Photos integration (Priority: P4)

**Story goal** ([spec.md](./spec.md) §US4): when the user explicitly enables the feature flag, support (a) Picker-based import into a local cache and (b) app-created-album upload to Google Photos. Per Principle V the integration lives in one removable module; per Clarification Q5 Picker bytes are downloaded into `<data_dir>/picker-cache/`.

**Independent Test**: with the feature flag OFF, no Google Photos routes exist and no Photos network calls are made (SC-009). Flip the flag ON, complete consent, invoke Picker against a stubbed Google Photos service, confirm items appear in the review UI; approve an album and upload via the stub, confirm an app-created album is created and items uploaded.

### Tests for User Story 4 (write first, MUST FAIL before implementation)

- [X] T079 [P] [US4] Integration test for "no network when flag OFF" in `tests/integration/test_no_network_when_flag_off.py` — monkeypatch `httpx` and `googleapiclient` to raise on any call; run the full ingest → review → export cycle; assert zero invocations (SC-009, C-HTTP-2).
- [X] T080 [P] [US4] Contract test for Google Photos route registration in `tests/contract/test_google_photos_routes_contract.py` — with flag OFF: `GET /picker/start` and `GET /gp/upload/{album_id}` return 404; with flag ON: same routes return 200/302 (C-HTTP-2).
- [X] T081 [P] [US4] Integration test for Picker import in `tests/integration/test_picker_import.py` — using a stubbed Picker service, drive a selection of 3 items; assert bytes are downloaded to `<data_dir>/picker-cache/<hash[:2]>/<hash>`, `provenance='picker'` is set, dedup against an identical Takeout item collapses to one `media_items` row (FR-036, Clarification Q5).
- [X] T082 [P] [US4] Integration test for app-created-album upload in `tests/integration/test_gp_upload.py` — approve a fixture album; stub the Photos `albums.create` + `mediaItems.batchCreate`; assert one album is created with the sanitized name and the items are uploaded; failed items are surfaced via `errors_repo` and the UI displays a clear, non-technical reason (FR-037).

### Implementation for User Story 4

- [X] T083 [US4] Implement `src/calendar_photo_organizer/google_photos_optional.py` — single module containing: feature-flag check at import; Picker REST flow (create session → poll → list media items → stream-download to picker-cache with on-the-fly hashing per D-012); `upload_album(album_id)` using Photos Library `mediaItems:batchCreate` with the `photoslibrary.appendonly` scope; clear, redacted log lines (no tokens, no bytes). The SDK and Picker deps are imported lazily inside the flag-on branch so the module can be removed without breaking the rest of the app.
- [X] T084 [US4] Add Google-Photos UI routes under `src/calendar_photo_organizer/ui/routes/google_photos.py` (`/picker/start`, `/picker/poll`, `/gp/upload/{album_id}`) — registered into the FastAPI app **only** when `feature_flags.google_photos_enabled=True` at startup (C-HTTP-2). Pre-consent scope disclosure rendered via `ui/templates/auth/gp_consent.html`.
- [X] T085 [US4] Extend `cli.py` with `cpo picker import` and `cpo gp upload <ALBUM_ID>`; both no-ops with a clear message when the flag is OFF.

**Checkpoint**: US4 complete. Tests T079–T082 pass. The optional integration is wholly contained in two files (`google_photos_optional.py` + `ui/routes/google_photos.py`) and the lazy-imported `[google-photos]` extra — removable without affecting the Takeout pipeline (Principle V).

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, performance hardening, the bundled demo, the doctor command, and the release pre-flight checklist.

- [X] T086 [P] Author the full `README.md` at the repo root: end-user pitch, install steps, link to [quickstart.md](./quickstart.md), explicit explanation of Google Photos Library-API restrictions post-March-2025 with the recommendation to use Google Takeout for bulk processing (Principle V, SC-010); link to constitution and contributing guide.
- [X] T087 [P] Author `docs/oauth-setup.md` walking a non-technical user through creating a Google Cloud project, enabling Calendar API, configuring an OAuth consent screen, and downloading installed-app credentials. Reference only Calendar scopes for the default install (Principle II).
- [X] T088 [P] Author `docs/google-photos-api.md` documenting the post-March-2025 Library-API restrictions, what the optional integration can and cannot do (Picker = bring-your-own-batch, upload = app-created-only), and explicit non-promises (no full-library reorganization; SC-010, Principle V).
- [X] T089 [P] Author `docs/takeout.md` — how to order a Google Takeout export, recommended settings, expected folder layout, sidecar JSON behaviour.
- [X] T090 Implement `cpo demo` in `cli.py` to drive the full pipeline against the bundled fixture in a temp data dir and print the final dry-run plan path — the deliverable-7 demo command.
- [X] T091 Implement `cpo doctor` in `cli.py` reporting: Python version, OS, blake3 availability, pillow-heif availability, `ffprobe` on PATH, keyring backend, symlink-supported on the current cwd, current data dir, feature-flag state. Useful for support and CI debugging.
- [X] T092 [P] Performance harness `tests/perf/test_scan_100k.py` (marked `slow`, off by default) generating 100,000 synthetic small files and timing first-time scan + incremental rescan against the SC-003 / SC-004 budgets (≤ 8 h first run, ≤ 5 min incremental, ≤ 1 GB RSS). Records a numerical regression baseline.
- [X] T093 [P] Add a contributor checklist `.github/PULL_REQUEST_TEMPLATE.md` mirroring the five-point Constitution review (Principle I–V) per [.specify/memory/constitution.md](../../.specify/memory/constitution.md) §Development Workflow.
- [X] T094 Run the full [quickstart.md](./quickstart.md) §Acceptance walkthrough (steps 1–12) on macOS, Windows, and Linux runners (via the CI matrix from T006); fix any cross-platform issue surfaced. Sign off Phase 7 by attaching the green CI run to the release PR.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)** — no dependencies; T003–T008 are all [P].
- **Phase 2 (Foundational)** — depends on Phase 1; **blocks every later phase**. Foundational tests T009–T016 are [P]; implementation T017–T035 is mostly sequential per module but `[P]` repositories T023–T030 can land in parallel after T017–T022.
- **Phase 3 (US1)** — depends on Phase 2 checkpoint. Tests T036–T045 are all [P]; impl T046–T059 is partially sequential (T046 → T047 ; T049 depends on T046; routes T052–T056 depend on T051; CLI T059 depends on all). Templates T057–T058 are [P].
- **Phase 4 (US2)** — depends on Phase 2; can begin in parallel with US1 once the matcher / album_planner is stubbed, but the integration tests require US1 to be functional. Tests T060–T064 [P]; impl T065 → T066 → T067; T068 [P].
- **Phase 5 (US3)** — depends on US1 (operates on its proposals); independent of US2 for unit tests, but T071 depends on US2's exporter.
- **Phase 6 (US4)** — depends on Phase 2 only; entirely behind the feature flag so it can be staffed independently. T079 requires the rest of the pipeline (US1 + US2) to be runnable.
- **Phase 7 (Polish)** — depends on US1 + US2 being done at minimum. T086–T091 are documentation/CLI and all [P]; T094 is the final integrating sign-off.

### Within Each User Story

- All tests for the story MUST be written and FAIL before any implementation task in that story is started (Constitution Principle III).
- Models / migrations / repositories before services; services before routes; routes before CLI wiring; CLI wiring before templates polish.
- A story is "done" when its checkpoint is reached and its independent test passes.

### Parallel Opportunities

- All Phase 1 tasks except T001 and T002 are [P].
- All Phase 2 tests T009–T016 are [P]; repositories T023–T028 are [P]; `hashing` + `paths` (T029–T030) are [P].
- All US1 tests T036–T045 are [P].
- All US2 tests T060–T064 are [P].
- All US3 tests T069–T073 are [P].
- All US4 tests T079–T082 are [P].
- Polish T086–T091 + T092–T093 are all [P].

---

## Parallel Example: User Story 1

After Phase 2 checkpoint, a team can pick up these strictly-parallel test tasks in one round:

```text
T036 [P] [US1] tests/unit/test_metadata_extractor.py
T037 [P] [US1] tests/unit/test_matcher.py
T038 [P] [US1] tests/unit/test_confidence_cap.py
T039 [P] [US1] tests/unit/test_dedup.py
T040 [P] [US1] tests/unit/test_album_planner_proposal.py
T041 [P] [US1] tests/integration/test_takeout_ingest_end_to_end.py
T042 [P] [US1] tests/integration/test_resume_after_interruption.py
T043 [P] [US1] tests/integration/test_calendar_oauth_pause_resume.py
T044 [P] [US1] tests/contract/test_http_api_contract.py
T045 [P] [US1] tests/contract/test_cli_contract.py
```

Then implementation tasks T046 (metadata_extractor) and T047 (importer) are sequential, while T048 (calendar_client), T049 (matcher), T051 (FastAPI shell), and T057+T058 (templates+static) can be picked up in parallel by other team members.

---

## Implementation Strategy

- **Suggested MVP scope**: Phase 1 + Phase 2 + Phase 3 (US1). At this point the user can ingest a Takeout archive, see proposed albums in the UI, and review them — the entire reason the product exists. The MVP is releasable as `0.1.0`.
- **Incremental delivery**:
  - `0.2.0` adds US2 (export to local folders) — the first version most end-users would actually run.
  - `0.3.0` adds US3 (rename/merge/split/reject + bulk approve + buffer re-tune) — the "feels smart" release.
  - `0.4.0` adds US4 (optional Google Photos integration) behind the feature flag — the power-user release.
- **Test ordering**: every phase writes its tests first and ensures they FAIL on a clean tree before any implementation task in that phase is opened for review. The constitution makes this non-negotiable.
- **Cross-OS CI on every PR** (T006) catches symlink-vs-copy and HEIC-availability regressions before they reach a release branch.

## Format validation

All 94 tasks in this file follow the required strict format:

`- [ ] TaskID [P?] [Story?] Description with file path`

- Every Setup/Foundational/Polish task: `- [ ] TXXX [P?] Description …` (no story label).
- Every User-Story task: `- [ ] TXXX [P?] [USn] Description …` (story label present).
- Every task names at least one concrete file path (`src/.../*.py`, `tests/.../*.py`, `docs/*.md`, `.github/.../*.yml`, or a configuration file).

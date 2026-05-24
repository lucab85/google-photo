# Quickstart — Calendar Photo Organizer

Two audiences: **end-users** running the app, and **developers** working on
this repository.

## End-user quickstart

### Prerequisites

- macOS 13+, Windows 10+, or Linux (glibc ≥ 2.31).
- Python 3.12 or newer (`python3 --version`).
- A Google Takeout export of your Google Photos library, unzipped to a
  directory. (See `docs/takeout.md` once written — order it from
  `takeout.google.com` selecting **Google Photos** only.)
- A Google account whose Calendar covers the dates your photos were taken on.

### Install

```bash
pipx install calendar-photo-organizer
# or
python3.12 -m pip install --user calendar-photo-organizer
```

Optional extras:

- `pip install 'calendar-photo-organizer[heic]'` — HEIC thumbnail decoding.
- `pip install 'calendar-photo-organizer[google-photos]'` — enables the
  optional Google Photos integration (Picker import + app-created-album
  upload). **OFF by default even after install** — must be enabled in
  Settings.

### One-shot demo (uses bundled fixture, no Google account required)

```bash
cpo demo
```

This runs the full pipeline against `tests/fixtures/takeout_sample/` and a
canned calendar response, producing a dry-run export plan under a temp dir.

### Real usage

```bash
cpo init                                    # creates the local database
cpo auth google-calendar                    # OAuth in your browser (read-only)
cpo calendar-import --from 2018-01-01 --to today
cpo scan /path/to/Takeout                   # streaming + resumable
cpo match
cpo propose
cpo review serve --open                     # opens 127.0.0.1:<port>
#   Review albums in the browser. Approve per album or use bulk actions.
cpo export /Volumes/Photos/Organized        # dry-run by default
cpo export /Volumes/Photos/Organized --write
```

### What this app does NOT do

The Google Photos Library API (post-March-2025) does not let third-party
apps reorganize your existing photos in the cloud. This app therefore
**reads your archive from Google Takeout** and **writes a new organized copy
locally** (as folders of symlinks by default). Nothing under your Takeout
folder is ever modified or deleted, and nothing is uploaded to Google Photos
unless you explicitly enable the optional integration in Settings. See
`docs/google-photos-api.md` once written.

## Developer quickstart

### Repository layout

See `plan.md` § "Project Structure (repository root)".

### Bootstrap

```bash
git clone <repo>
cd google-photo
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,heic,google-photos]'
pre-commit install
```

### Run the test suite

```bash
pytest                            # all tests
pytest tests/unit                 # fast inner loop
pytest tests/integration -m "not network"
ruff check src tests
mypy --strict src/calendar_photo_organizer
```

### Run the app locally against the fixture

```bash
CPO_DATA_DIR=$(mktemp -d) cpo init
CPO_DATA_DIR=$PWD/.tmp cpo demo
```

### Acceptance walkthrough (covers all P1/P2 acceptance scenarios)

Each step maps to a spec acceptance scenario.

1. `cpo init` — creates DB, runs migration `0001`. (Constitution Eng. Std.)
2. `cpo calendar-import --from 2024-07-01 --to 2024-07-31` — US1 AS-1.
3. `cpo scan tests/fixtures/takeout_sample` — US1 AS-1.
4. Kill the process mid-scan; rerun the same command. — US1 AS-2 (resume).
5. `cpo match && cpo propose` — US1 AS-1.
6. `cpo review serve --open` and open an album. — US1 AS-3.
7. Filter by confidence band `high`. — US1 AS-4.
8. Open `/unmatched`. — US1 AS-5.
9. Rename, merge, split, reject albums in the UI. — US3 AS-1..4.
10. `cpo export <tmp>` (dry-run) — US2 AS-1.
11. `cpo export <tmp> --write` — US2 AS-2.
12. Verify every original under `tests/fixtures/takeout_sample/` is
    byte-identical (`sha256sum` before/after). — SC-005.

### Constitution checkpoints during development

Before opening a PR:

- [ ] No `print()` outside `cli.py` (Eng. Std. logging).
- [ ] No `0.0.0.0` bind in `ui/app.py` (Privacy-First).
- [ ] No new `pip` dep that's pulled in without a feature flag if it touches
      Google Photos (Principle V).
- [ ] Any change to `db/migrations/` is paired with a test in
      `tests/unit/test_migrations.py` (Eng. Std. schema changes).
- [ ] Any new long-running operation goes through `jobs/runner.py` and
      checkpoints to `scan_jobs` (Principle IV).

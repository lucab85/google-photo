# Calendar Photo Organizer

A local-first tool that organizes a Google Photos / Google Takeout archive into
event-based albums using your Google Calendar history. All processing happens on
your machine; nothing is uploaded unless you explicitly opt in.

> **Honesty disclosure (Constitution Principle V).** After Google's March 2025
> Photos Library API changes, third-party apps **cannot** read or reorganize
> your existing Google Photos library. This tool therefore organizes a **Google
> Takeout export** locally. The optional Google Photos integration is limited to
> the Picker API (you choose individual items) and uploads to **app-created
> albums only**. Full-library reorganization in Google Photos is not supported
> and is not a goal of this project.

## Features

- **Calendar-driven grouping** — Photos and videos are matched to your Google
  Calendar events (with configurable pre/post buffer windows) to form proposed
  albums.
- **Takeout-first** — Ingests a Google Takeout archive (directory or zip),
  preserves EXIF/sidecar metadata, and never modifies your source files.
- **Local SQLite catalog** — All state lives in `<data_dir>/cpo.db` (WAL mode,
  foreign keys enforced). Easy to inspect, back up, and delete.
- **Review UI** — Local-only FastAPI/HTMX web app bound to `127.0.0.1` for
  approving, renaming, merging, splitting, and rejecting album proposals.
- **Deterministic exports** — Plans, manifests, and CSV reports for every
  export; supports symlink or copy mode and dry-run by default.
- **Rename safety** — An export-time trigger (Invariant I-4) marks previously
  exported folders as orphaned on rename so you never silently lose data.
- **Optional Google Photos integration** — Feature-flagged Picker import and
  app-created album upload. Off by default; no network calls are made when the
  flag is disabled.
- **Doctor diagnostics** — `cpo doctor` reports environment capabilities
  (blake3, pillow-heif, ffprobe, keyring, symlink support).

## Requirements

- Python **3.12+**
- macOS, Linux, or Windows
- Optional: `ffmpeg`/`ffprobe` on PATH for video metadata
- Optional: `pillow-heif` for HEIC support (`pip install pillow-heif`)

## Install

```bash
git clone https://github.com/<you>/google-photo.git
cd google-photo
python3 -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Verify:

```bash
cpo --help
cpo doctor
```

## Quick start (offline demo)

Runs the full pipeline against the bundled fixture in an isolated temp dir:

```bash
cpo demo
```

Output ends with a `demo-complete` JSON record pointing at the generated
`plan.json`.

## End-to-end workflow

```bash
# 1. Point at a writable data directory (defaults to platformdirs user data dir)
export CPO_DATA_DIR="$HOME/.local/share/calendar-photo-organizer"

# 2. Initialise the catalog
cpo init

# 3. Authenticate with Google Calendar (OAuth, token stored in OS keyring)
cpo auth google-calendar

# 4. Import calendar events for a date range
cpo calendar-import --from 2024-01-01 --to 2024-12-31

# 5. Scan your Takeout export (directory or .zip)
cpo scan /path/to/Takeout

# 6. Match media to events and propose albums
cpo match
cpo propose

# 7. Review and edit proposals in the local UI
cpo review serve --open      # http://127.0.0.1:8765

# 8. Approve individual or bulk proposals from the CLI (optional)
cpo approve --all
cpo approve --album-id 42 --reject

# 9. Export — always dry-run first
cpo export ~/Pictures/Organized --dry-run
cpo export ~/Pictures/Organized --write
```

Each export produces:

- `<target>/<Year>/<Album>/` — symlinked or copied media
- `<target>/manifest.json` — deterministic record of what was written
- `<target>/report.csv` — per-file outcome, including orphan-by-rename rows

## CLI reference

| Command | Purpose |
|---|---|
| `cpo version` | Print package version. |
| `cpo init` | Create the data dir and run migrations. |
| `cpo doctor` | Report environment capabilities (JSON). |
| `cpo demo` | Run the full pipeline against the bundled fixture. |
| `cpo auth google-calendar` | OAuth flow for read-only calendar scope. |
| `cpo calendar-import` | Fetch events for `--from` / `--to`. |
| `cpo scan PATH` | Ingest a Takeout directory or zip. |
| `cpo match` | Match media to calendar events using buffer windows. |
| `cpo propose` | Generate album proposals from recommended matches. |
| `cpo approve` | Approve/reject by `--band`, `--album-id`, or `--all`. |
| `cpo export TARGET` | Plan or write an export (`--dry-run` default). |
| `cpo review serve` | Launch the local-only review UI. |
| `cpo picker import` | (Feature-flagged) Import selections via Google Photos Picker. |
| `cpo gp upload ALBUM_ID` | (Feature-flagged) Upload an app-created album. |

Run `cpo <command> --help` for full flags.

## Configuration

Settings come from environment variables (prefix `CPO_`, nested delimiter `__`)
and a runtime overrides file at `<data_dir>/config.json` (written by the UI's
settings page).

Common knobs:

| Variable | Default | Description |
|---|---|---|
| `CPO_DATA_DIR` | platform user-data dir | Where the catalog, cache, and exports metadata live. |
| `CPO_MATCH__PRE_BUFFER_HOURS` | `2` | Hours before an event to consider photos part of it. |
| `CPO_MATCH__POST_BUFFER_HOURS` | `2` | Hours after an event. |
| `CPO_MATCH__ALLOW_MULTI_ALBUM` | `false` | Allow a single media item in multiple albums (Invariant I-3). |
| `CPO_FEATURE_FLAGS__GOOGLE_PHOTOS_ENABLED` | `false` | Gate Picker/upload commands and routes. |

Changing buffer hours from the UI triggers a recommended re-run of `cpo match`.

## Google Photos integration (optional)

Disabled by default. When enabled, only two operations are supported, per
Google's current API surface:

1. **Picker import** — you pick items in Google's hosted UI; the tool downloads
   them to `<data_dir>/picker-cache/` and dedups by SHA-256.
2. **App-created album upload** — uploads media into albums the tool itself
   created. Cannot modify pre-existing Google Photos albums.

Setup walkthrough: [docs/oauth-setup.md](./docs/oauth-setup.md),
[docs/google-photos-api.md](./docs/google-photos-api.md).

## Architecture

- **CLI** — Typer (`src/calendar_photo_organizer/cli.py`)
- **Storage** — SQLite (WAL, FK on) via thin repositories
- **Matching** — Calendar-window join with configurable buffers
- **Planner** — `album_planner.py` for proposal, rename, merge, split
- **Exporter** — Deterministic plan/manifest/report; symlink or copy
- **UI** — FastAPI + Jinja2 + HTMX, bound to `127.0.0.1` only
- **Optional GP** — `google_photos_optional.py`, gated by feature flag

Full design: [specs/001-calendar-photo-organizer/plan.md](./specs/001-calendar-photo-organizer/plan.md).

## Development

```bash
source .venv/bin/activate
pytest -q                       # unit + integration (slow tests deselected)
pytest -m slow tests/perf       # perf harness (writes baseline.json)
ruff check .
ruff format --check .
mypy
```

All four must remain green. Strict typing is enforced on
`src/calendar_photo_organizer`.

## Documentation

- Spec: [specs/001-calendar-photo-organizer/spec.md](./specs/001-calendar-photo-organizer/spec.md)
- Plan: [specs/001-calendar-photo-organizer/plan.md](./specs/001-calendar-photo-organizer/plan.md)
- Quickstart: [specs/001-calendar-photo-organizer/quickstart.md](./specs/001-calendar-photo-organizer/quickstart.md)
- Data model: [specs/001-calendar-photo-organizer/data-model.md](./specs/001-calendar-photo-organizer/data-model.md)
- Contracts: [specs/001-calendar-photo-organizer/contracts/](./specs/001-calendar-photo-organizer/contracts/)
- Constitution: [.specify/memory/constitution.md](./.specify/memory/constitution.md)
- OAuth setup: [docs/oauth-setup.md](./docs/oauth-setup.md)
- Takeout tips: [docs/takeout.md](./docs/takeout.md)

## Privacy

- All processing is local. The review UI binds only to `127.0.0.1`.
- OAuth tokens are stored in the OS keyring (Keychain / Secret Service / DPAPI).
- No telemetry. No outbound network calls when the Google Photos flag is off
  (covered by [test_no_network_when_flag_off.py](./tests/integration/test_no_network_when_flag_off.py)).

## License

See [LICENSE](./LICENSE) if present; otherwise all rights reserved by the
repository owner pending a formal license decision.

# Contract — Command-Line Interface

Implemented in `src/calendar_photo_organizer/cli.py` using **typer**. Entrypoint
`cpo` (also `python -m calendar_photo_organizer`). All commands print
structured logs to stderr (`structlog` JSON when `--log-format=json`, otherwise
human-readable). Exit codes: `0` success, `2` user error, `3` paused
(re-auth required), `4` cancelled, `1` unexpected failure.

| Command | Purpose | Key flags |
|---|---|---|
| `cpo init` | Create the SQLite DB + run migrations under the OS user data dir. | `--data-dir PATH` |
| `cpo auth google-calendar` | Run OAuth installed-app flow, store token via `keyring`. | `--scopes calendar.readonly` (default) |
| `cpo calendar-import` | Import calendar events for a date range. Resumable. | `--from YYYY-MM-DD`, `--to YYYY-MM-DD`, `--calendar primary,…` |
| `cpo scan <TAKEOUT_DIR>` | Streaming scan + metadata extraction + hashing. Resumable, incremental on `(path,size,mtime)`. | `--workers N`, `--include-ext …`, `--resume` (default), `--restart` |
| `cpo match` | Compute matches with confidence cap + bands. | `--pre-buffer 2h`, `--post-buffer 4h`, `--allow-multi-album` |
| `cpo propose` | Generate `proposed_albums` from matches. Idempotent. | (none) |
| `cpo review serve` | Launch the FastAPI UI on `127.0.0.1:<port>`. | `--port N` (default: random), `--open` |
| `cpo approve --band high \| --album-id ID \| --all` | Apply approval (per Q1 clarification). | `--reject` inverse |
| `cpo export <TARGET_DIR>` | Materialise approved albums. **Defaults to `--dry-run`.** | `--dry-run` (default), `--write`, `--mode auto\|symlink\|copy`, `--confirm-copy` |
| `cpo demo` | One-shot dry-run demo over the bundled fixture (deliverable 7). | `--data-dir <tmp>` |
| `cpo doctor` | Probe environment: blake3, pillow-heif, ffprobe, symlink support, keyring backend. | (none) |

**Contract guarantees** (testable in `tests/contract/test_cli_contract.py`):

- C-CLI-1: `cpo export` without `--write` MUST NOT write any file under the
  target directory; only a plan is printed and `report.csv`-style preview is
  written to a temp file under `<data_dir>/dry-runs/`.
- C-CLI-2: `cpo export --write` against a non-symlink-supporting target MUST
  exit `2` with a `copy-mode-not-confirmed` error unless `--confirm-copy` or
  `--mode copy` is given.
- C-CLI-3: Any command other than `cpo demo` and `cpo doctor` against an
  uninitialised data dir MUST exit `2` with `db-not-initialised`.
- C-CLI-4: All commands log a single JSON object with `event`, `job_id?`,
  `phase`, and `outcome` at completion.
- C-CLI-5: `cpo scan` re-run on an unchanged directory MUST NOT re-hash any
  file (verified by counting `hash_calls` in a test fake).

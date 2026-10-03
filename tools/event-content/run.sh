#!/usr/bin/env bash
# One-shot runner. Usage:
#   ./run.sh setup                 # venv + Pillow/pytest + build the Vision binary
#   ./run.sh test                  # unit tests
#   ./run.sh all                   # index → select → extract → vision → sessions → calendar → dossiers
#   ./run.sh videos                # frames OCR + whisper transcripts for event-like sessions, then rebuilds dossiers
#   ./run.sh list                  # the writing worklist (event-like sessions)
#   ./run.sh sheet SESSION [pub|all] [N]     # contact sheet
#   ./run.sh export SLUG TITLE=name ... [--thumb TITLE]   # web images into the blog repo
#   ./run.sh <step>                # any single step: index select extract vision sessions calendar dossiers
# Config: ./config.toml, or set EC_CONFIG=/path/to/other.toml (e.g. one per archive).
# Every step is resumable; re-running skips work already done.
set -euo pipefail
cd "$(dirname "$0")"
PY=.venv/bin/python
cmd="${1:-help}"; cfg="${EC_CONFIG:-config.toml}"

case "$cmd" in
  setup)
    [ -d .venv ] || python3 -m venv .venv
    .venv/bin/pip -q install -r requirements.txt
    ./vision/build.sh
    command -v ffmpeg >/dev/null || echo "warning: ffmpeg not found (needed for videos: brew install ffmpeg)"
    command -v whisper-cli >/dev/null || echo "warning: whisper-cli not found (videos are OCR-only: brew install whisper-cpp)"
    [ -f config.toml ] || { cp config.example.toml config.toml; echo "created config.toml: review it"; }
    ;;
  test) $PY -m pytest -q ;;
  videos)
    $PY -m event_content --config "$cfg" videos
    $PY -m event_content --config "$cfg" dossiers
    ;;
  help|-h|--help) sed -n '2,12p' "$0" ;;
  *) $PY -m event_content --config "$cfg" "$@" ;;
esac

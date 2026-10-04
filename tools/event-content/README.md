# event-content: from a Google Photos Takeout to event blog posts

This toolkit turns a Google Photos Takeout archive (one or more zip parts) into **event dossiers**. For each event you get the text from the slides, decoded QR links, matching calendar entries, text from video frames and talk transcripts, and a ranked list of photos that are safe to publish. Writing agents (Claude Code) then turn the dossiers into blog posts and galleries, and an export step produces web-ready photos.

It follows the calendar-photo-organizer constitution:

- **Read-only on the Takeout.** It reads the zips in place and never modifies, moves or deletes them.
- **Local-first.** OCR, QR decoding, scene labels, faces and aesthetics use Apple Vision. Speech-to-text uses whisper.cpp. Nothing leaves the machine.
- **Privacy by default.** Only your own camera photos are used, and family albums and people tags are excluded. Photos showing badges, secrets, contact details, QR-only screens or third parties in close-up are never offered for publishing. Exported images have their EXIF/GPS data stripped.

> Platform: **macOS** (Apple Vision). The Python steps run anywhere, but the `vision` step needs the Swift
> `vanalyze` binary. Requirements: Python 3.12+, Xcode command line tools; optional `ffmpeg` and `whisper-cpp`
> (`brew install ffmpeg whisper-cpp`) with a ggml model, e.g. `~/.cache/whisper-cpp/ggml-large-v3.bin`.

## Quick start

```bash
cd tools/event-content
./run.sh setup            # venv, Pillow + pytest, builds vision/vanalyze, creates config.toml
$EDITOR config.toml       # takeout_glob, work_dir, filters (owner name, family albums/people), blog repo
./run.sh test             # unit tests
./run.sh all              # index → select → extract → vision → sessions → calendar → dossiers
./run.sh videos           # optional: video frames OCR + transcripts for event sessions, rebuilds dossiers
./run.sh list             # the worklist: event-like sessions with calendar hints
```

Then open Claude Code in the blog repo and paste `prompts/ORCHESTRATOR.md`, with the paths filled in. It reads the worklist and fans out writing agents using the templates in `prompts/`. Every draft is reviewed before it is committed.

Calendar hints come from the calendar-photo-organizer catalog. Run `cpo auth google-calendar` and then `cpo calendar-import --from … --to …`, and set `[calendar] cpo_db`. Alternatively, point `events_json` at a JSON list of events. Without either, dossiers simply have no calendar hints.

## Steps and outputs (all under `work_dir`)

| Step | What it does | Output |
|---|---|---|
| `index` | Reads every JSON sidecar in all zips and maps each media file to the zip that contains it (parts are often split). | `index.csv` |
| `select` | Privacy filter: own-camera prefixes, no received or screenshot files, no private albums or people, optional date range. Also separates images from videos. | `candidates.csv`, `videos.csv` |
| `extract` | Analysis copies, ~2100 px, EXIF dropped. | `img/` |
| `preserve` | Saves analysis copies of own-camera photos whose sidecar is in a part you haven't downloaded yet, so you can delete this part. When the sidecar arrives, `select` keeps them and the privacy filters run as usual. Skips Motion Photo clip halves (`PXL_….MP`). | `img/` |
| `vision` | Apple Vision OCR, QR codes, labels, faces and aesthetics. Runs in chunks and resumes. | `vision.jsonl` |
| `sessions` | Groups photos into bursts separated by more than `gap_minutes`, in local time (configured zone, or derived from longitude abroad). | `sessions.json` |
| `calendar` | Attaches overlapping calendar events. Private keywords are filtered out. | `calendar-matches.json` |
| `dossiers` | One markdown + JSON file per session: text timeline, QR links, calendar hints, video text, transcripts, publishable photos. | `dossiers/` |
| `videos` | For event-like sessions: frames every N seconds (near-duplicates removed) through Vision, plus audio through whisper.cpp with VAD. | `vframes/`, `transcripts/` |
| `sheet SID` | Contact sheet of a session (`pub` = publishable only, or `all`). | `sheets/` |
| `export SLUG TITLE=name … [--thumb TITLE]` | Writes web images (≤1280 px, ≤300 KB, no EXIF) and a 1200×630 thumbnail into the blog repo. Falls back to the analysis copies if the zip is gone. | `static/blog/events/SLUG/` |

**Before deleting a part**, run `./run.sh preserve`: a photo and its sidecar are often in different parts.

Every step is idempotent, so re-running only processes what is new. To process **another archive**, give it its own config with a different `work_dir` (`EC_CONFIG=other.toml ./run.sh all`). If you're processing **one Takeout part at a time** because of disk space, process a part, keep `work_dir`, then point `takeout_glob` at the next part. Exports keep working from the analysis copies.

## Photo classification (dossiers)

- **kind**: `scene` (no prominent faces), `selfie` (only `owner_people` tagged), `crowd` (many small faces), or `people` (a third party may be in focus; **not publishable**).
- **flags**: `badge`, `secret` (passwords or WiFi details), `contact` (email, LinkedIn, "connect with me"), `internal` (work screens: internal hostnames, image digests, shell prompts, network output), `qr-only`, `utility`. Any flag makes a photo **not publishable**, and flagged text is kept out of the timeline.
- **event share**: the fraction of photos showing stage, screen, crowd or slide signals. Sessions below `event_share_min` are treated as personal and left out of the worklist.

Automation doesn't catch everything. Reviewers must still zoom in for graffiti, laptop screens, other people's tweets or slides, and loosely related photos. See `prompts/WRITER_BRIEF.md` for the full rules.

## Lessons baked in

- **Trust photos over the calendar.** Calendar entries are RSVPs. In one case the calendar said "Databricks meetup", but the slides showed a Java User Group hosted by IKEA.
- **Long Vision runs can silently drop output.** The runner works in chunks and resumes from what is missing.
- **macOS `unzip` fails on some non-ASCII filenames.** Everything reads through Python `zipfile` instead.
- **Media and its sidecar can live in different Takeout parts.** `index` resolves media across all zips.
- **Deep dives need photos from the start.** Put slide photos inside the sections they illustrate, not just one image at the top.

## Development

```bash
./run.sh test   # tests/test_pipeline.py: indexing across parts, privacy filters, sessions/time zones,
                # calendar matching, photo classification, EXIF-free export
```

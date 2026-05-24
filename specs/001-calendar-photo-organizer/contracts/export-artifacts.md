# Contract — On-Disk Export Artifacts

Every export run — dry or real — produces a stable, machine-parseable layout.
These artifacts are the user's durable record and must not change shape
without a contract version bump.

## Layout

```text
<target_root>/
├── 2024-07-18 – Luca Birthday/
│   ├── IMG_20240718_141233.jpg          # symlink or copy
│   ├── …
│   └── manifest.json
├── 2025-04-12 – Amsterdam Trip/
│   └── …
└── report.csv                            # written at the end of every run
<data_dir>/dry-runs/<job_id>/
├── plan.json                             # dry-run only
└── plan-report.csv                       # dry-run only
```

## `manifest.json` (one per exported album)

```json
{
  "contract_version": 1,
  "album": {
    "id": 42,
    "display_name": "2024-07-18 – Luca Birthday",
    "folder_name": "2024-07-18 – Luca Birthday",
    "anchor_event": {
      "google_event_id": "…",
      "calendar_id": "primary",
      "title": "Luca Birthday",
      "start_utc": "2024-07-18T14:00:00Z",
      "end_utc":   "2024-07-18T20:00:00Z",
      "is_all_day": false
    },
    "status": "exported",
    "exported_at": "2026-05-23T18:04:11Z",
    "mode": "symlink"
  },
  "items": [
    {
      "filename_in_album": "IMG_20240718_141233.jpg",
      "source_path": "/Users/…/Takeout/Google Photos/2024/IMG_20240718_141233.jpg",
      "content_hash": "blake3:5b1d…",
      "size_bytes": 4321987,
      "mime_type": "image/jpeg",
      "capture_ts_utc": "2024-07-18T14:12:33Z",
      "capture_tz": "Europe/Rome",
      "capture_source_tier": "exif",
      "match": {
        "rule_category": "in_event",
        "rule_score": 1.0,
        "source_cap": 1.0,
        "bonus": 0.0,
        "confidence": 1.0,
        "band": "high",
        "is_recommended": true
      },
      "google_photos_id": null,
      "provenance": "takeout"
    }
  ]
}
```

## `report.csv` (one per export run, top-level under `<target_root>`)

Columns (header row required):

```
run_id,started_at,finished_at,target_root,mode,album_id,folder_name,display_name,status,
event_id,event_title,event_start_utc,event_end_utc,item_count,photo_count,video_count,
notes
```

- `status ∈ {current, orphaned-by-rename}` (FR-034a).
- Orphaned rows have `item_count=0` and `notes="previous folder retained on disk; not modified"`.
- Re-running export appends a new run; rows from prior runs are not modified.

## `plan.json` (dry-run only)

```json
{
  "contract_version": 1,
  "job_id": 123,
  "target_root": "/Volumes/Photos/Organized",
  "mode": "symlink",
  "symlink_supported": true,
  "albums": [
    {
      "album_id": 42,
      "folder_name": "2024-07-18 – Luca Birthday",
      "actions": [
        { "kind": "create_dir", "path": "2024-07-18 – Luca Birthday" },
        { "kind": "symlink", "src": "/.../IMG_20240718_141233.jpg",
          "dst": "2024-07-18 – Luca Birthday/IMG_20240718_141233.jpg" }
      ],
      "skipped": [
        { "kind": "exists", "path": "2024-07-18 – Luca Birthday/IMG_20240718_141234.jpg" }
      ]
    }
  ]
}
```

## Contract guarantees

- C-EXP-1: `manifest.json` and `report.csv` MUST validate against the JSON
  Schema / CSV header above; tested in
  `tests/contract/test_export_artifacts_contract.py`.
- C-EXP-2: every `source_path` listed in any artifact MUST resolve to a file
  that is byte-identical to its `content_hash` after export completes
  (verified by SC-005 integration test).
- C-EXP-3: dry-run MUST write nothing under `target_root`; the only side
  effects allowed are under `<data_dir>/dry-runs/<job_id>/`.
- C-EXP-4: the `contract_version` field MUST be present and equal to `1` for
  v1; any future incompatible change MUST bump it and ship a migration.

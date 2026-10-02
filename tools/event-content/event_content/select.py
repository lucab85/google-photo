"""Privacy filter: decide which indexed items may be analysed at all."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

from .takeout_index import FIELDS


def classify(row: dict, f: dict, processed: set[str] | None = None) -> str:
    """Return 'image', 'video' or the reason the item is excluded.

    `processed` holds stems already analysed from an earlier part: they stay candidates
    even when their zip has been deleted (derived data lives on in work_dir).
    """
    title = row["title"]
    low = title.lower()
    stem = title.rsplit(".", 1)[0]
    if not row.get("media_path") and stem not in (processed or set()):
        return "media not in available zips"
    day = row["utc"][:10]
    if (f.get("since") and day < f["since"]) or (f.get("until") and day > f["until"]):
        return "outside date range"
    if any(s in title for s in f.get("exclude_title_substrings", [])):
        return "not own camera (received/screenshot)"
    if not any(title.startswith(p) for p in f.get("own_camera_prefixes", ["PXL_"])):
        return "not own camera"
    if row.get("album") in f.get("exclude_albums", []):
        return "private album"
    people = row.get("people", "").lower()
    if any(s in people for s in f.get("exclude_people_substrings", [])):
        return "private people tag"
    if low.endswith(tuple(f.get("image_extensions", [".jpg", ".jpeg"]))):
        return "image"
    if low.endswith(tuple(f.get("video_extensions", [".mp4", ".mov"]))):
        return "video"
    return "unsupported type"


def select(
    rows: list[dict],
    filters: dict,
    images_csv: Path,
    videos_csv: Path,
    processed: set[str] | None = None,
) -> Counter:
    stats: Counter = Counter()
    imgs, vids = [], []
    for r in rows:
        c = classify(r, filters, processed)
        stats[c] += 1
        (imgs if c == "image" else vids if c == "video" else []).append(r)
    for path, data in ((images_csv, imgs), (videos_csv, vids)):
        with open(path, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(data)
    return stats

"""Index Google Photos Takeout JSON sidecars across one or more zip parts.

Reads zips in place with `zipfile` (no extraction, so it is robust to non-ASCII names
that macOS `unzip` cannot write) and records which zip holds each media file, because
a sidecar and its media are often in different parts.
"""

from __future__ import annotations

import csv
import json
import os
import zipfile
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path

FIELDS = ["utc", "lat", "lon", "album", "title", "zip", "media_path", "people", "desc"]
SKIP_JSON = ("metadata.json",)
SKIP_PREFIXES = ("print-subscriptions", "shared_album_comments", "user-generated-memory-titles")


def parse_sidecar(name: str, data: dict) -> dict | None:
    """Turn one sidecar into an index row (without zip/media location). None if not a media sidecar."""
    ts = (data.get("photoTakenTime") or {}).get("timestamp")
    title = data.get("title")
    if not ts or not title:
        return None
    geo = data.get("geoData") or {}
    geo_exif = data.get("geoDataExif") or {}
    lat = geo.get("latitude") or geo_exif.get("latitude") or 0
    lon = geo.get("longitude") or geo_exif.get("longitude") or 0
    parts = name.split("/")
    album = parts[2] if len(parts) > 3 else ""
    return {
        "utc": datetime.fromtimestamp(int(ts), UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lat": round(lat, 5) if lat else "",
        "lon": round(lon, 5) if lon else "",
        "album": album,
        "title": title,
        "people": ";".join(p.get("name", "") for p in data.get("people", []) if p.get("name")),
        "desc": (data.get("description") or "").replace("\n", " ")[:200],
        "_dir": name.rsplit("/", 1)[0],
    }


def is_sidecar(name: str) -> bool:
    base = os.path.basename(name)
    return (
        name.endswith(".json")
        and "/Google Photos/" in name
        and base not in SKIP_JSON
        and not base.startswith(SKIP_PREFIXES)
    )


def iter_rows(zips: Iterable[Path]) -> Iterator[dict]:
    zips = list(zips)
    media_loc: dict[str, str] = {}
    for zp in zips:
        with zipfile.ZipFile(zp) as z:
            for n in z.namelist():
                if not n.endswith(".json") and not n.endswith("/"):
                    media_loc.setdefault(n, str(zp))
    for zp in zips:
        with zipfile.ZipFile(zp) as z:
            for n in z.namelist():
                if not is_sidecar(n):
                    continue
                try:
                    row = parse_sidecar(n, json.loads(z.read(n)))
                except (ValueError, KeyError):
                    continue
                if not row:
                    continue
                media = f"{row.pop('_dir')}/{row['title']}"
                row["media_path"] = media if media in media_loc else ""
                row["zip"] = media_loc.get(media, "")
                yield row


def build_index(zips: Iterable[Path], out_csv: Path) -> dict:
    """Write index.csv (sorted by time, de-duplicated by media path or title+time)."""
    seen, rows = set(), []
    for r in iter_rows(zips):
        key = r["media_path"] or (r["title"], r["utc"])
        if key in seen:
            continue
        seen.add(key)
        rows.append(r)
    rows.sort(key=lambda r: r["utc"])
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    return {
        "items": len(rows),
        "with_gps": sum(1 for r in rows if r["lat"]),
        "media_present": sum(1 for r in rows if r["media_path"]),
    }


def read_index(path: Path) -> list[dict]:
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))

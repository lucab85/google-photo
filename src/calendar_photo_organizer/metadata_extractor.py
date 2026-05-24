"""Capture-timestamp extraction (5-tier waterfall).

Order of attempts:
  1. Google Takeout JSON sidecar (``photoTakenTime.timestamp``)
  2. EXIF DateTimeOriginal / DateTime (Pillow, with optional pillow-heif for HEIC)
  3. Video metadata via hachoir
  4. Filename regex (IMG_/VID_/PXL_/Screenshot_ + ``YYYYMMDD_HHMMSS``)
  5. Filesystem mtime (last resort)

The first tier to yield a usable timestamp wins. Returns ``None`` only when
*every* tier fails (e.g., binary blob with no parseable name and mtime is
unavailable — extremely rare in practice).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from calendar_photo_organizer.models import CaptureSourceTier

try:  # Optional HEIC support
    import pillow_heif

    pillow_heif.register_heif_opener()
except Exception:
    pass

from PIL import Image, UnidentifiedImageError

_FILENAME_RES = (
    re.compile(r"(\d{4})(\d{2})(\d{2})[_-](\d{2})(\d{2})(\d{2})"),
    re.compile(r"(\d{4})-(\d{2})-(\d{2})[T_ ](\d{2})[:-](\d{2})[:-](\d{2})"),
)


@dataclass(slots=True)
class CaptureTimestamp:
    timestamp_utc: datetime
    tz: str | None
    tier: CaptureSourceTier


def _from_sidecar(path: Path) -> CaptureTimestamp | None:
    sidecar = path.with_suffix(path.suffix + ".json")
    if not sidecar.exists():
        return None
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        ts_raw = data.get("photoTakenTime", {}).get("timestamp")
        if not ts_raw:
            return None
        dt = datetime.fromtimestamp(int(ts_raw), UTC)
        return CaptureTimestamp(dt, "UTC", CaptureSourceTier.SIDECAR)
    except (ValueError, OSError, KeyError):
        return None


def _from_exif(path: Path) -> CaptureTimestamp | None:
    try:
        with Image.open(path) as img:
            exif = img.getexif()
            if not exif:
                return None
            for tag in (36867, 306):  # DateTimeOriginal, DateTime
                raw = exif.get(tag)
                if not raw:
                    continue
                try:
                    dt = datetime.strptime(str(raw), "%Y:%m:%d %H:%M:%S")
                except ValueError:
                    continue
                offset = exif.get(36881)  # OffsetTimeOriginal
                tz_name = None
                if offset:
                    tz_name = str(offset)
                dt = dt.replace(tzinfo=UTC)
                return CaptureTimestamp(dt, tz_name or "UTC", CaptureSourceTier.EXIF)
    except (UnidentifiedImageError, OSError, ValueError):
        return None
    return None


def _from_video_metadata(path: Path) -> CaptureTimestamp | None:
    try:
        from hachoir.metadata import extractMetadata
        from hachoir.parser import createParser

        parser = createParser(str(path))
        if not parser:
            return None
        with parser:
            md = extractMetadata(parser)
        if md is None:
            return None
        creation = md.get("creation_date")
        if isinstance(creation, datetime):
            dt = creation if creation.tzinfo else creation.replace(tzinfo=UTC)
            return CaptureTimestamp(dt, "UTC", CaptureSourceTier.VIDEO_META)
    except Exception:
        return None
    return None


def _from_filename(path: Path) -> CaptureTimestamp | None:
    name = path.name
    for r in _FILENAME_RES:
        m = r.search(name)
        if m:
            try:
                y, mo, d, h, mi, s = (int(g) for g in m.groups())
                dt = datetime(y, mo, d, h, mi, s, tzinfo=UTC)
                return CaptureTimestamp(dt, "UTC", CaptureSourceTier.FILENAME)
            except ValueError:
                continue
    return None


def _from_mtime(path: Path) -> CaptureTimestamp | None:
    try:
        st = path.stat()
        dt = datetime.fromtimestamp(st.st_mtime, UTC)
        return CaptureTimestamp(dt, "UTC", CaptureSourceTier.MTIME)
    except OSError:
        return None


_EXTRACTORS = (_from_sidecar, _from_exif, _from_video_metadata, _from_filename, _from_mtime)


def extract(path: Path) -> CaptureTimestamp | None:
    """Return the highest-tier capture timestamp for *path*, or ``None``."""
    for fn in _EXTRACTORS:
        ts = fn(path)
        if ts is not None:
            return ts
    return None


def file_stat(path: Path) -> tuple[int, int]:
    """Return (size_bytes, mtime_ns) suitable for the incremental-skip cache."""
    st = os.stat(path)
    return st.st_size, st.st_mtime_ns

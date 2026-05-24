"""Generate the takeout_sample fixture (small, real media files with EXIF / sidecars).

Run once via ``python tests/fixtures/generate_takeout_sample.py``. Re-runnable:
deletes the existing ``takeout_sample/`` before regenerating.

The fixture is committed to the repo so tests don't have to regenerate it.
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image
from PIL.ExifTags import Base

ROOT = Path(__file__).parent / "takeout_sample"


def _datetime_exif(dt: datetime) -> str:
    return dt.strftime("%Y:%m:%d %H:%M:%S")


def _write_jpeg_with_exif(path: Path, color: tuple[int, int, int], dt_utc: datetime) -> None:
    img = Image.new("RGB", (64, 48), color)
    exif = img.getexif()
    local = dt_utc.astimezone(UTC)
    exif[Base.DateTimeOriginal.value] = _datetime_exif(local)
    exif[Base.DateTime.value] = _datetime_exif(local)
    exif[Base.OffsetTimeOriginal.value] = "+00:00"
    img.save(path, "JPEG", exif=exif.tobytes(), quality=70)


def _write_png(path: Path, color: tuple[int, int, int, int]) -> None:
    img = Image.new("RGBA", (32, 32), color)
    img.save(path, "PNG")


def _write_minimal_mp4(path: Path) -> None:
    # Very minimal MP4 "ftyp" box so hachoir / file-detection has something to chew on.
    ftyp = b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2avc1mp41"
    mdat = b"\x00\x00\x00\x08mdat"
    path.write_bytes(ftyp + mdat)


def _write_sidecar(path: Path, taken_at_utc: datetime, *, title: str | None = None) -> None:
    sidecar = path.with_suffix(path.suffix + ".json")
    payload = {
        "title": title or path.name,
        "photoTakenTime": {
            "timestamp": str(int(taken_at_utc.timestamp())),
            "formatted": taken_at_utc.strftime("%b %d, %Y, %I:%M:%S %p UTC"),
        },
    }
    sidecar.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def generate() -> None:
    if ROOT.exists():
        shutil.rmtree(ROOT)
    ROOT.mkdir(parents=True)

    # 1-6: JPEGs with EXIF + sidecars (during evt-001 Beach Day)
    base = datetime(2024, 7, 4, 18, 0, tzinfo=UTC)
    for i in range(6):
        dt = base.replace(minute=i * 5)
        p = ROOT / f"IMG_2024070{4}_{180000 + i * 500:06d}.jpg"
        _write_jpeg_with_exif(p, (200 - i * 10, 100 + i * 10, 50), dt)
        _write_sidecar(p, dt)

    # 7-8: PNG screenshots (filename-only timestamps, evt-002 Hike day)
    for i in range(2):
        dt = datetime(2024, 7, 10, 16, i * 15, tzinfo=UTC)
        p = ROOT / f"Screenshot_20240710_{160000 + i * 1500:06d}.png"
        _write_png(p, (i * 100, 200, 200, 255))

    # 9-10: "HEIC" stubs (use PNG body but .heic ext — extractor should fall back to filename)
    for i in range(2):
        dt = datetime(2024, 7, 15, 12, i * 10, tzinfo=UTC)
        p = ROOT / f"IMG_20240715_120{i}00.heic"
        _write_png(p, (50, 50, 50, 255))
        p.rename(p.with_suffix(".HEIC"))

    # 11-13: minimal MP4 videos (evt-004 Concert)
    for i in range(3):
        dt = datetime(2024, 7, 20, 3, i * 15, tzinfo=UTC)
        p = ROOT / f"VID_20240720_030{i}00.mp4"
        _write_minimal_mp4(p)
        _write_sidecar(p, dt)

    # 14-15: media files with NO metadata at all (no sidecar, no parseable name)
    for i in range(2):
        p = ROOT / f"unknown_blob_{i}.bin"
        p.write_bytes(b"opaque-data-" + bytes([i] * 16))


if __name__ == "__main__":
    generate()

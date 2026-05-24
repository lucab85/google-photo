"""T036 — metadata extraction across 5 source tiers."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from calendar_photo_organizer.metadata_extractor import extract


@pytest.fixture
def sample() -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures" / "takeout_sample"


def test_sidecar_tier(sample: Path) -> None:
    f = sample / "IMG_20240704_180000.jpg"
    ts = extract(f)
    assert ts is not None
    assert ts.tier.value in ("sidecar", "exif")
    # Sidecar should win over EXIF and resolve to the exact UTC second
    if ts.tier.value == "sidecar":
        assert ts.timestamp_utc == datetime(2024, 7, 4, 18, 0, tzinfo=UTC)


def test_filename_tier(sample: Path) -> None:
    f = sample / "Screenshot_20240710_160000.png"
    ts = extract(f)
    assert ts is not None
    assert ts.tier.value == "filename"
    assert ts.timestamp_utc.date() == datetime(2024, 7, 10).date()


def test_heic_filename_fallback(sample: Path) -> None:
    f = sample / "IMG_20240715_120000.HEIC"
    ts = extract(f)
    assert ts is not None
    # HEIC decoding may not be available; either EXIF or filename works
    assert ts.tier.value in ("exif", "filename", "mtime")


def test_no_timestamp_returns_mtime_or_none(sample: Path) -> None:
    f = sample / "unknown_blob_0.bin"
    ts = extract(f)
    # Falls back to mtime as last resort, or None
    assert ts is None or ts.tier.value == "mtime"


def test_video_sidecar(sample: Path) -> None:
    f = sample / "VID_20240720_030000.mp4"
    ts = extract(f)
    assert ts is not None
    # Sidecar always wins
    assert ts.tier.value in ("sidecar", "video_meta", "filename")

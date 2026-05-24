"""Generate a tiny fixture Takeout-shaped tree on demand.

The unit tests check pure logic against synthetic in-memory data, but the
integration tests in Phase 3 need real files on disk. To keep the repo small,
we generate ~15 small files (PNGs, fake HEIC, fake MP4s, screenshots, sidecars)
the first time a test imports :func:`make_takeout_tree`.
"""

from __future__ import annotations

import json
import struct
import zlib
from datetime import UTC, datetime
from pathlib import Path

# Minimal valid 1x1 PNG bytes (transparent pixel)
_PNG_1X1 = bytes.fromhex(
    "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C4"
    "890000000A49444154789C6300010000000500010D0A2DB40000000049454E44"
    "AE426082"
)


def _png(color_seed: int) -> bytes:
    """Return a 1x1 PNG whose IDAT depends on *color_seed* so files differ."""
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    ihdr = _chunk(b"IHDR", ihdr_data)
    raw = bytes([0, color_seed & 0xFF, color_seed & 0xFF, color_seed & 0xFF, 0xFF])
    idat = _chunk(b"IDAT", zlib.compress(raw))
    iend = _chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


def _chunk(tag: bytes, data: bytes) -> bytes:
    length = struct.pack(">I", len(data))
    crc = struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return length + tag + data + crc


def _sidecar(ts_utc: str) -> dict[str, object]:
    return {
        "photoTakenTime": {
            "timestamp": str(int(datetime.fromisoformat(ts_utc.replace("Z", "+00:00")).timestamp()))
        },
        "creationTime": {
            "timestamp": str(int(datetime.fromisoformat(ts_utc.replace("Z", "+00:00")).timestamp()))
        },
    }


SAMPLE_ITEMS: list[tuple[str, str, bool]] = [
    # (relative path, capture timestamp UTC, write sidecar?)
    ("Photos from 2024/IMG_20240704_180501.jpg", "2024-07-04T18:05:01Z", True),
    ("Photos from 2024/IMG_20240704_190233.jpg", "2024-07-04T19:02:33Z", True),
    ("Photos from 2024/IMG_20240704_201500.jpg", "2024-07-04T20:15:00Z", True),
    ("Photos from 2024/IMG_20240710_153000.jpg", "2024-07-10T15:30:00Z", True),
    ("Photos from 2024/IMG_20240710_180000.jpg", "2024-07-10T18:00:00Z", True),
    ("Photos from 2024/IMG_20240710_212211.jpg", "2024-07-10T21:22:11Z", True),
    ("Photos from 2024/Screenshot_20240715-090000.png", "2024-07-15T09:00:00Z", False),
    ("Photos from 2024/Screenshot_20240715-141533.png", "2024-07-15T14:15:33Z", False),
    ("Photos from 2024/IMG_20240720_030200.heic", "2024-07-20T03:02:00Z", True),
    ("Photos from 2024/IMG_20240720_034522.heic", "2024-07-20T03:45:22Z", True),
    ("Photos from 2024/VID_20240704_201000.mp4", "2024-07-04T20:10:00Z", True),
    ("Photos from 2024/VID_20240710_170000.mp4", "2024-07-10T17:00:00Z", True),
    ("Photos from 2024/PXL_20240720_040000.mp4", "2024-07-20T04:00:00Z", True),
    # Two items lacking parseable metadata (no sidecar, no timestamp in name)
    ("Photos from 2024/random_image.jpg", "2024-07-04T19:30:00Z", False),
    ("Photos from 2024/unknown.bin", "2024-07-04T19:31:00Z", False),
]


def make_takeout_tree(root: Path) -> Path:
    """Create the fixture tree under *root* and return *root*."""
    root.mkdir(parents=True, exist_ok=True)
    for idx, (rel, ts, sidecar) in enumerate(SAMPLE_ITEMS):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        # Vary content per file so content hashes differ
        path.write_bytes(_png(idx + 1))
        # Set mtime so the mtime-tier matches our expectation
        epoch = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
        import os

        os.utime(path, (epoch, epoch))
        if sidecar:
            (path.with_suffix(path.suffix + ".json")).write_text(
                json.dumps(_sidecar(ts)), encoding="utf-8"
            )
    return root


__all__ = ["SAMPLE_ITEMS", "make_takeout_tree"]
_ = UTC  # silence "unused import" - kept for downstream use

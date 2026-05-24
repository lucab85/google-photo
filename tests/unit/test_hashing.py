"""T013 — hashing.hash_file (blake3 + sha256 fallback, streaming)."""

from __future__ import annotations

import builtins
import importlib
import sys
import tracemalloc
from pathlib import Path

import pytest

from calendar_photo_organizer import hashing


def test_blake3_hash_is_deterministic(tmp_path: Path) -> None:
    p = tmp_path / "a.bin"
    p.write_bytes(b"hello world")
    h1 = hashing.hash_file(p)
    h2 = hashing.hash_file(p)
    assert h1 == h2
    assert h1.startswith("blake3:") or h1.startswith("sha256:")


def test_sha256_fallback_when_blake3_missing(tmp_path: Path, monkeypatch) -> None:
    real_import = builtins.__import__

    def raise_blake3(name, *a, **kw):
        if name == "blake3":
            raise ImportError("simulated")
        return real_import(name, *a, **kw)

    # Ensure subsequent imports see the patched __import__
    sys.modules.pop("blake3", None)
    monkeypatch.setattr(builtins, "__import__", raise_blake3)
    importlib.reload(hashing)

    p = tmp_path / "b.bin"
    p.write_bytes(b"abc")
    h = hashing.hash_file(p)
    assert h.startswith("sha256:")

    monkeypatch.setattr(builtins, "__import__", real_import)
    importlib.reload(hashing)


@pytest.mark.slow
def test_streams_large_file_in_bounded_memory(tmp_path: Path) -> None:
    big = tmp_path / "big.bin"
    chunk = b"\x55" * (1024 * 1024)
    with big.open("wb") as f:
        for _ in range(100):  # 100 MiB
            f.write(chunk)
    tracemalloc.start()
    hashing.hash_file(big)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert peak < 8 * 1024 * 1024, f"peak memory {peak} bytes exceeded 8 MiB"

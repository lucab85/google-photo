"""T014 — symlink probe + link_or_copy."""

from __future__ import annotations

from pathlib import Path

import pytest

from calendar_photo_organizer import paths


def test_probe_returns_true_on_posix_tmp(tmp_path: Path) -> None:
    # POSIX always allows symlinks under user-writable tmp dirs.
    assert paths.probe_symlink_support(tmp_path) is True


def test_probe_returns_false_when_symlink_errors(tmp_path: Path, monkeypatch) -> None:
    paths._probe_cache.clear()
    original_symlink_to = Path.symlink_to

    def fail(self, *a, **kw):
        raise OSError(1, "EPERM")

    monkeypatch.setattr(Path, "symlink_to", fail)
    assert paths.probe_symlink_support(tmp_path) is False
    monkeypatch.setattr(Path, "symlink_to", original_symlink_to)


def test_probe_result_is_cached(tmp_path: Path) -> None:
    paths._probe_cache.clear()
    paths.probe_symlink_support(tmp_path)
    # Second call should hit cache (sentinel: monkey-patched Path.symlink_to would
    # otherwise raise; we just confirm idempotent return value)
    assert paths.probe_symlink_support(tmp_path) is True


def test_link_or_copy_symlink(tmp_path: Path) -> None:
    src = tmp_path / "src.bin"
    src.write_bytes(b"hi")
    dst = tmp_path / "dst.bin"
    paths.link_or_copy(src, dst, mode="symlink")
    assert dst.is_symlink()
    assert dst.read_bytes() == b"hi"


def test_link_or_copy_copy(tmp_path: Path) -> None:
    src = tmp_path / "src.bin"
    src.write_bytes(b"hi")
    dst = tmp_path / "dst.bin"
    paths.link_or_copy(src, dst, mode="copy")
    assert not dst.is_symlink()
    assert dst.read_bytes() == b"hi"


def test_link_or_copy_invalid_mode(tmp_path: Path) -> None:
    src = tmp_path / "src.bin"
    src.write_bytes(b"")
    with pytest.raises(ValueError):
        paths.link_or_copy(src, tmp_path / "x", mode="weird")  # type: ignore[arg-type]

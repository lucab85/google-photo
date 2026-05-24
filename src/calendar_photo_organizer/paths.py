"""Path / filesystem helpers — symlink probing and link-or-copy."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Literal

_probe_cache: dict[str, bool] = {}

Mode = Literal["symlink", "copy"]


def probe_symlink_support(target_dir: Path) -> bool:
    """Return True iff *target_dir* supports symlinks.

    The result is cached per-target. Caller is expected to pass the **same**
    directory it will later write into.
    """
    key = str(target_dir.resolve())
    cached = _probe_cache.get(key)
    if cached is not None:
        return cached

    target_dir.mkdir(parents=True, exist_ok=True)
    probe = target_dir / f".cpo-symlink-probe-{uuid.uuid4().hex}"
    src = target_dir / f".cpo-symlink-src-{uuid.uuid4().hex}"
    src.write_bytes(b"")
    ok = False
    try:
        probe.symlink_to(src)
        ok = probe.is_symlink()
    except (OSError, NotImplementedError):
        ok = False
    finally:
        for p in (probe, src):
            try:
                if p.is_symlink() or p.exists():
                    p.unlink()
            except OSError:
                pass
    _probe_cache[key] = ok
    return ok


def link_or_copy(src: Path, dst: Path, *, mode: Mode) -> None:
    """Materialize *src* at *dst* using either a symlink or a true copy."""
    if mode not in ("symlink", "copy"):
        raise ValueError(f"unknown mode: {mode!r}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    if mode == "symlink":
        dst.symlink_to(src)
    else:
        shutil.copy2(src, dst)

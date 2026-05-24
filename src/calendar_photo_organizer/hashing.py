"""Content hashing.

Default algorithm: ``blake3`` (fast, parallel). If blake3 fails to import for
any reason (missing wheel on a platform) we transparently fall back to ``sha256``.
The returned digest is prefixed with the algorithm name (e.g. ``blake3:abcd...``)
so downstream code can detect heterogeneous archives.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

_CHUNK = 1024 * 1024  # 1 MiB

try:  # pragma: no cover - covered indirectly by tests
    import blake3 as _blake3_mod

    _blake3: Any = _blake3_mod
    _USE_BLAKE3 = True
except Exception:
    _blake3 = None
    _USE_BLAKE3 = False


def hash_file(path: Path, *, chunk_size: int = _CHUNK) -> str:
    """Hash a file in fixed-size chunks. Returns ``"<algo>:<hexdigest>"``."""
    h: Any
    if _USE_BLAKE3 and _blake3 is not None:
        h = _blake3.blake3()
        algo = "blake3"
    else:
        h = hashlib.sha256()
        algo = "sha256"

    with path.open("rb") as f:
        while True:
            buf = f.read(chunk_size)
            if not buf:
                break
            h.update(buf)
    return f"{algo}:{h.hexdigest()}"

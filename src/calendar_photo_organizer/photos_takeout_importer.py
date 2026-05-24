"""Streaming Takeout importer (recursive, dedup by content hash).

Skips files whose ``(path, size, mtime)`` is already in ``media_paths`` so a
re-scan of an unchanged directory does not re-hash anything (FR-011, SC-006).
"""

from __future__ import annotations

import mimetypes
import os
from collections.abc import Callable, Iterator
from pathlib import Path

from calendar_photo_organizer.db.repositories.errors import ErrorsRepository
from calendar_photo_organizer.db.repositories.media import MediaRepository
from calendar_photo_organizer.hashing import hash_file
from calendar_photo_organizer.metadata_extractor import extract, file_stat
from calendar_photo_organizer.models import MediaItem, MediaPath, Provenance

_SKIP_SUFFIXES = {".json"}
_IGNORE_NAMES = {".DS_Store", "Thumbs.db"}


def _iter_files(root: Path) -> Iterator[Path]:
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            if name in _IGNORE_NAMES:
                continue
            p = Path(dirpath) / name
            if p.suffix.lower() in _SKIP_SUFFIXES:
                continue
            yield p


def import_takeout(
    root: Path,
    *,
    media_repo: MediaRepository,
    errors_repo: ErrorsRepository | None = None,
    job_id: str | None = None,
    progress_cb: Callable[[int], None] | None = None,
) -> int:
    """Walk *root* and ingest every media file. Returns the number processed."""
    processed = 0
    for path in _iter_files(root):
        try:
            size, mtime_ns = file_stat(path)
            existing_media_id = media_repo.find_by_path_size_mtime(path, size, mtime_ns)
            if existing_media_id is not None:
                processed += 1
                if progress_cb:
                    progress_cb(processed)
                continue

            digest = hash_file(path)
            ts = extract(path)
            mime, _ = mimetypes.guess_type(str(path))

            media = MediaItem(
                id=None,
                content_hash=digest,
                captured_at_utc=ts.timestamp_utc if ts else None,
                captured_at_tz=ts.tz if ts else None,
                capture_source_tier=ts.tier if ts else None,
                mime_type=mime,
                width=None,
                height=None,
                duration_seconds=None,
                provenance=Provenance.TAKEOUT,
            )
            media_id = media_repo.upsert_by_content_hash(media)
            media_repo.add_path(
                MediaPath(
                    id=None,
                    media_id=media_id,
                    path=path,
                    size_bytes=size,
                    mtime_ns=mtime_ns,
                    is_primary=True,
                )
            )
            processed += 1
            if progress_cb:
                progress_cb(processed)
        except OSError as exc:
            if errors_repo is not None:
                errors_repo.record(
                    job_id=job_id, phase="scan", subject_kind="media",
                    subject=str(path), reason="oserror", detail=str(exc),
                )
            continue
    # Commit any pending writes
    import contextlib
    with contextlib.suppress(Exception):
        media_repo.conn.commit()
    return processed

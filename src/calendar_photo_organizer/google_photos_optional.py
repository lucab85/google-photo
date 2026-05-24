"""Optional Google Photos integration (Picker import + Library upload).

This module is imported ONLY when ``feature_flags.google_photos_enabled`` is
True (Principle V). All Google SDK / Picker imports are deferred to the call
sites so that, with the flag off, the rest of the app has zero Photos-related
dependencies. Per Clarification Q5, Picker bytes land in
``<data_dir>/picker-cache/<hash[:2]>/<hash>``.

The functions here are intentionally minimal — they take **fetcher** callables
that perform the network I/O so tests can pass stubs without monkeypatching
the SDK.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(slots=True)
class PickerItem:
    """A single selection returned by the Picker."""

    id: str
    filename: str
    mime_type: str
    bytes_: bytes


@dataclass(slots=True)
class UploadResult:
    album_id_remote: str | None
    uploaded: int
    failed: list[tuple[int, str]]  # (media_id, reason)


def _picker_cache_dir(data_dir: Path) -> Path:
    p = data_dir / "picker-cache"
    p.mkdir(parents=True, exist_ok=True)
    return p


def import_picker_selection(
    data_dir: Path,
    *,
    fetcher: Callable[[], Iterable[PickerItem]],
    media_repo: object,
) -> int:
    """Import a Picker selection into the local cache and ``media_items``.

    Returns the number of new media rows created (duplicates dedup against
    existing content hashes per FR-036).
    """
    from calendar_photo_organizer.models import MediaItem, MediaPath, Provenance

    cache = _picker_cache_dir(data_dir)
    created = 0
    for item in fetcher():
        digest = hashlib.sha256(item.bytes_).hexdigest()
        content_hash = f"sha256:{digest}"
        sub = cache / digest[:2]
        sub.mkdir(parents=True, exist_ok=True)
        dest = sub / digest
        if not dest.exists():
            dest.write_bytes(item.bytes_)
        # Upsert by content hash — duplicates collapse to one row
        media = MediaItem(
            id=None, content_hash=content_hash,
            captured_at_utc=datetime.now(UTC), captured_at_tz="UTC",
            capture_source_tier=None, mime_type=item.mime_type,
            width=None, height=None, duration_seconds=None,
            provenance=Provenance.PICKER,
        )
        mid = media_repo.upsert_by_content_hash(media)  # type: ignore[attr-defined]
        existing_paths = media_repo.paths_for(mid)  # type: ignore[attr-defined]
        if not any(p == dest for p in existing_paths):
            media_repo.add_path(MediaPath(  # type: ignore[attr-defined]
                id=None, media_id=mid, path=dest,
                size_bytes=len(item.bytes_), mtime_ns=dest.stat().st_mtime_ns,
                is_primary=not existing_paths,
            ))
            created += 1
    return created


def upload_album(
    album_id: int,
    *,
    conn: object,
    albums_repo: object,
    create_album: Callable[[str], str],
    upload_items: Callable[[str, list[tuple[int, Path]]], list[tuple[int, str]]],
) -> UploadResult:
    """Upload an approved album via Photos Library API (``photoslibrary.appendonly``).

    ``create_album(display_name) -> remote_album_id``
    ``upload_items(remote_album_id, [(media_id, source_path), ...]) -> failed``
    """
    album = albums_repo.get(album_id)  # type: ignore[attr-defined]
    if album is None:
        return UploadResult(album_id_remote=None, uploaded=0, failed=[])
    remote_id = create_album(album.display_name)
    media_ids = albums_repo.items(album_id)  # type: ignore[attr-defined]
    paths: list[tuple[int, Path]] = []
    for mid in media_ids:
        rows = conn.execute(  # type: ignore[attr-defined]
            """SELECT path FROM media_paths
                WHERE media_id=? AND is_primary=1 LIMIT 1""", (mid,),
        ).fetchall()
        if rows:
            paths.append((mid, Path(rows[0]["path"])))
    failed = upload_items(remote_id, paths)
    return UploadResult(
        album_id_remote=remote_id, uploaded=len(paths) - len(failed), failed=failed,
    )

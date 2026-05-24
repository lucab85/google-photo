"""Album planner — sanitization + (later) proposal logic.

Phase 2 covers only ``sanitize_folder_name`` (T031); proposal/merge/split helpers
are added incrementally in Phase 3 (T050) and Phase 5 (T074).
"""

from __future__ import annotations

import re
import unicodedata

# Reserved Windows device names (case-insensitive)
_RESERVED = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
)

# Allowed characters: word chars, space, ASCII hyphen, EN-DASH, underscore,
# dot, parentheses, and the Latin-1 / Latin-Extended-A accented range.
_ALLOWED = re.compile(r"[^\w \-\u2013_.()\u00C0-\u017F]", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")

DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:\s+\u2013\s+|\s+-\s+|\s+)")


def sanitize_folder_name(name: str, *, max_len: int = 120) -> str:
    """Sanitize *name* for safe use as a folder name on macOS, Linux, and Windows.

    Rules (matches the property tests in T015):
      * Strip / replace any character outside the allowed set.
      * Collapse internal whitespace runs to a single space.
      * Remove trailing dots and spaces.
      * Prefix Windows reserved names (CON, PRN, ...) with ``_``.
      * Truncate to ``max_len`` characters preserving any ``YYYY-MM-DD`` date prefix.  # noqa: RUF002
      * Empty or whitespace-only input returns ``"Untitled"``.
    """
    if not name or not name.strip():
        return "Untitled"

    # Normalize accents (preserve them rather than stripping)
    s = unicodedata.normalize("NFC", name)

    # Detect optional date prefix so we can preserve it across truncation
    m = DATE_PREFIX_RE.match(s)
    if m:
        date = m.group(1)
        rest = s[m.end() :]
        prefix = f"{date} \u2013 "
    else:
        prefix = ""
        rest = s

    # Strip disallowed characters from the body
    cleaned = _ALLOWED.sub(" ", rest)
    cleaned = _WHITESPACE.sub(" ", cleaned).strip(" .")

    out = (prefix + cleaned).rstrip(" .")
    if not out:
        out = "Untitled"

    # Windows reserved name handling
    head = out.split(".", 1)[0].upper()
    if head in _RESERVED:
        out = "_" + out

    # Truncate while preserving the date prefix
    if len(out) > max_len:
        if prefix:
            remaining = max_len - len(prefix)
            out = prefix + cleaned[: max(remaining, 0)]
        else:
            out = out[:max_len]
        out = out.rstrip(" .")
        if not out:
            out = "Untitled"
    return out


# ---------------------------------------------------------------------------
# Display-name + proposal logic (T050)
# ---------------------------------------------------------------------------

from calendar_photo_organizer.db.repositories.albums import AlbumsRepository  # noqa: E402
from calendar_photo_organizer.db.repositories.events import EventsRepository  # noqa: E402
from calendar_photo_organizer.db.repositories.matches import MatchesRepository  # noqa: E402
from calendar_photo_organizer.models import AlbumStatus, CalendarEvent, ProposedAlbum  # noqa: E402


def propose_display_name(event: CalendarEvent) -> str:
    """Return ``"YYYY-MM-DD \u2013 Title"`` for *event* (local date in UTC)."""
    date = event.start_utc.date().isoformat()
    title = event.title.strip() or "Untitled"
    return f"{date} \u2013 {title}"


def _unique_folder_name(albums: AlbumsRepository, base: str, *, exclude_id: int | None = None) -> str:
    candidate = base
    n = 2
    while albums.folder_name_exists(candidate, exclude_id=exclude_id):
        candidate = f"{base} ({n})"
        n += 1
    return candidate


def propose_albums_from_recommended(
    matches_repo: MatchesRepository,
    events_repo: EventsRepository,
    albums_repo: AlbumsRepository,
    *,
    allow_multi_album: bool,
) -> int:
    """Create one ProposedAlbum per event with recommended matches (idempotent).

    Re-running with no new matches is a no-op (FR-018). Existing user-renamed
    albums are preserved. Returns the number of albums that exist after the call.
    """

    # decisions are handled by add_items() — recommended matches are 1:1 in this
    # path (matcher picks one event per media) so the flag mainly affects later
    # split/merge operations (T074).
    _ = allow_multi_album

    created = 0
    for event_id, media_ids in matches_repo.iter_recommended_grouped_by_event():
        event = events_repo.get(event_id)
        if event is None:
            continue
        existing = albums_repo.find_by_event(event_id)
        if existing is None:
            display = propose_display_name(event)
            folder = _unique_folder_name(albums_repo, sanitize_folder_name(display))
            album_id = albums_repo.create(
                ProposedAlbum(
                    id=None,
                    display_name=display,
                    folder_name=folder,
                    status=AlbumStatus.PROPOSED,
                    event_id=event_id,
                )
            )
            created += 1
        else:
            album_id = existing.id or 0
        if album_id:
            albums_repo.add_items(album_id, media_ids)
    albums_repo.conn.commit()
    return created


# ---------------------------------------------------------------------------
# Album operations (T074)
# ---------------------------------------------------------------------------



def rename_album(
    albums_repo: AlbumsRepository, album_id: int, new_display_name: str
) -> None:
    """Rename an album. Triggers ``trg_rename_marks_export_orphan`` (Invariant I-4)."""
    folder = _unique_folder_name(
        albums_repo, sanitize_folder_name(new_display_name), exclude_id=album_id
    )
    albums_repo.rename(album_id, new_display_name, folder)
    albums_repo.conn.commit()


def merge_albums(
    albums_repo: AlbumsRepository, source_ids: list[int], new_display_name: str
) -> int:
    """Merge ``source_ids`` into a new album; sources are marked ``rejected``."""
    folder = _unique_folder_name(albums_repo, sanitize_folder_name(new_display_name))
    new_id = albums_repo.create(
        ProposedAlbum(
            id=None, display_name=new_display_name, folder_name=folder,
            status=AlbumStatus.PROPOSED, event_id=None,
        )
    )
    all_items: list[int] = []
    for sid in source_ids:
        all_items.extend(albums_repo.items(sid))
        albums_repo.set_status(sid, AlbumStatus.REJECTED)
    # Deduplicate while preserving order
    seen: set[int] = set()
    unique_items: list[int] = []
    for mid in all_items:
        if mid in seen:
            continue
        seen.add(mid)
        unique_items.append(mid)
    albums_repo.add_items(new_id, unique_items)
    albums_repo.set_merged_from(new_id, source_ids)
    albums_repo.conn.commit()
    return new_id


def split_album(
    albums_repo: AlbumsRepository, source_id: int, media_ids: list[int], new_display_name: str
) -> int:
    """Move ``media_ids`` out of ``source_id`` into a new album."""
    folder = _unique_folder_name(albums_repo, sanitize_folder_name(new_display_name))
    new_id = albums_repo.conn.execute(
        """INSERT INTO proposed_albums
             (display_name, folder_name, status, event_id,
              user_renamed, merged_from_json, split_from_id)
           VALUES (?, ?, 'proposed', NULL, 0, NULL, ?)""",
        (new_display_name, folder, source_id),
    ).lastrowid
    albums_repo.add_items(int(new_id or 0), media_ids)
    albums_repo.remove_items(source_id, media_ids)
    albums_repo.conn.commit()
    return int(new_id or 0)


def reject_album(albums_repo: AlbumsRepository, album_id: int) -> None:
    """Mark an album rejected (items return to Unmatched)."""
    albums_repo.set_status(album_id, AlbumStatus.REJECTED)
    albums_repo.conn.commit()


def unreject_album(albums_repo: AlbumsRepository, album_id: int) -> None:
    """Reverse ``reject_album``."""
    albums_repo.set_status(album_id, AlbumStatus.PROPOSED)
    albums_repo.conn.commit()


def link_media_to_album(
    albums_repo: AlbumsRepository,
    album_id: int,
    media_ids: list[int],
    *,
    allow_multi_album: bool,
) -> int:
    """Link media items to an album, honoring the multi-album toggle (Invariant I-3).

    When ``allow_multi_album=False``, items already in an active (non-rejected)
    album other than ``album_id`` are skipped. Toggling OFF later never deletes
    pre-existing memberships (FR-021) — this helper only gates *new* additions.
    Returns the count of media items actually added.
    """
    eligible: list[int] = []
    for mid in media_ids:
        if not allow_multi_album:
            other_active = [
                aid for aid in albums_repo.media_album_ids(mid)
                if aid != album_id and (a := albums_repo.get(aid)) is not None
                and a.status != AlbumStatus.REJECTED
            ]
            if other_active:
                continue
        eligible.append(mid)
    added = albums_repo.add_items(album_id, eligible)
    albums_repo.conn.commit()
    return added

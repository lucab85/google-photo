"""T041 — end-to-end ingest (scan → calendar-import → match → propose)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from calendar_photo_organizer.album_planner import propose_albums_from_recommended
from calendar_photo_organizer.calendar_client import import_events_from_json
from calendar_photo_organizer.db import migrate
from calendar_photo_organizer.db.connection import connect
from calendar_photo_organizer.db.repositories.albums import AlbumsRepository
from calendar_photo_organizer.db.repositories.errors import ErrorsRepository
from calendar_photo_organizer.db.repositories.events import EventsRepository
from calendar_photo_organizer.db.repositories.matches import MatchesRepository
from calendar_photo_organizer.db.repositories.media import MediaRepository
from calendar_photo_organizer.matcher import MatcherSettings, match_all
from calendar_photo_organizer.photos_takeout_importer import import_takeout

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture
def env(tmp_path: Path):
    conn = connect(tmp_path)
    migrate.apply(conn, data_dir=tmp_path)
    return {
        "conn": conn,
        "media": MediaRepository(conn),
        "events": EventsRepository(conn),
        "matches": MatchesRepository(conn),
        "albums": AlbumsRepository(conn),
        "errors": ErrorsRepository(conn),
    }


def test_end_to_end(env) -> None:
    payload = json.loads((FIXTURE_DIR / "calendar_sample.json").read_text())
    import_events_from_json(payload, env["events"])
    assert env["events"].count() == 5

    import_takeout(FIXTURE_DIR / "takeout_sample", media_repo=env["media"], job_id=None)
    assert env["media"].count() >= 10  # 15 files; some dedupe by content hash

    settings = MatcherSettings(pre_buffer_seconds=2 * 3600, post_buffer_seconds=4 * 3600)
    match_all(env["media"], env["events"], env["matches"], settings)

    n = propose_albums_from_recommended(
        env["matches"], env["events"], env["albums"], allow_multi_album=False
    )
    assert n >= 3  # at least Beach Day, Hike-or-screenshot day, Concert

    # SC-002: high-confidence matches dominate for fixture items with sidecar+EXIF
    bands = env["matches"].count_by_band()
    assert bands["high"] >= 5

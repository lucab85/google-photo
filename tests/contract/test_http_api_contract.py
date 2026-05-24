"""T044 — HTTP API contract (C-HTTP-1, C-HTTP-3)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from calendar_photo_organizer.album_planner import propose_albums_from_recommended
from calendar_photo_organizer.calendar_client import import_events_from_json
from calendar_photo_organizer.db import migrate
from calendar_photo_organizer.db.connection import connect
from calendar_photo_organizer.db.repositories.albums import AlbumsRepository
from calendar_photo_organizer.db.repositories.events import EventsRepository
from calendar_photo_organizer.db.repositories.matches import MatchesRepository
from calendar_photo_organizer.db.repositories.media import MediaRepository
from calendar_photo_organizer.matcher import MatcherSettings, match_all
from calendar_photo_organizer.photos_takeout_importer import import_takeout
from calendar_photo_organizer.ui.app import create_app

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture
def client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setenv("CPO_DATA_DIR", str(tmp_path))
    from calendar_photo_organizer.config import get_settings
    get_settings.cache_clear()

    conn = connect(tmp_path)
    migrate.apply(conn, data_dir=tmp_path)

    # Populate DB
    payload = json.loads((FIXTURE_DIR / "calendar_sample.json").read_text())
    events = EventsRepository(conn)
    media = MediaRepository(conn)
    matches = MatchesRepository(conn)
    albums = AlbumsRepository(conn)
    import_events_from_json(payload, events)
    import_takeout(FIXTURE_DIR / "takeout_sample", media_repo=media, job_id=None)
    match_all(media, events, matches, MatcherSettings())
    propose_albums_from_recommended(matches, events, albums, allow_multi_album=False)
    conn.close()

    app = create_app(data_dir=tmp_path)
    return TestClient(app)


def test_dashboard_returns_counters(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    body = r.text
    assert "media" in body.lower() or "scanned" in body.lower()


def test_healthz(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.text.strip().strip('"') == "ok"


def test_albums_list_pagination(client: TestClient) -> None:
    r = client.get("/albums?page=1&page_size=50")
    assert r.status_code == 200


def test_albums_page_size_cap(client: TestClient) -> None:
    r = client.get("/albums?page=1&page_size=9999")
    assert r.status_code == 200  # silently capped to 200, no error


def test_unmatched_by_date(client: TestClient) -> None:
    r = client.get("/unmatched")
    assert r.status_code == 200


def test_server_binds_loopback_only() -> None:
    # Indirect verification: create_app exposes intended host
    from calendar_photo_organizer.ui.app import default_host
    assert default_host() == "127.0.0.1"

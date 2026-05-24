"""T080 — Google Photos route registration is gated by the feature flag (C-HTTP-2)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from calendar_photo_organizer.config import get_settings


def _make_client(tmp_path: Path, enabled: bool, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("CPO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(
        "CPO_FEATURE_FLAGS__GOOGLE_PHOTOS_ENABLED", "true" if enabled else "false"
    )
    get_settings.cache_clear()
    # Reload the app module so any module-level flag checks re-evaluate
    sys.modules.pop("calendar_photo_organizer.google_photos_optional", None)
    sys.modules.pop("calendar_photo_organizer.ui.routes.google_photos", None)
    from calendar_photo_organizer.db import migrate
    from calendar_photo_organizer.db.connection import connect
    from calendar_photo_organizer.ui.app import create_app

    conn = connect(tmp_path)
    migrate.apply(conn, data_dir=tmp_path)
    conn.close()
    return TestClient(create_app(data_dir=tmp_path))


def test_routes_404_when_flag_off(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    c = _make_client(tmp_path, enabled=False, monkeypatch=monkeypatch)
    assert c.get("/picker/start").status_code == 404
    assert c.get("/gp/upload/1").status_code == 404


def test_routes_present_when_flag_on(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    c = _make_client(tmp_path, enabled=True, monkeypatch=monkeypatch)
    # Endpoint may need auth/data; we only assert it is NOT 404 (i.e., registered).
    r = c.get("/picker/start")
    assert r.status_code != 404
    r2 = c.get("/gp/upload/1", follow_redirects=False)
    assert r2.status_code != 404

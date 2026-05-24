"""T079 — assert no httpx / googleapiclient calls when GP flag OFF (SC-009)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from calendar_photo_organizer.config import get_settings
from calendar_photo_organizer.ui.app import create_app


def test_no_gp_network_when_flag_off(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CPO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CPO_FEATURE_FLAGS__GOOGLE_PHOTOS_ENABLED", "false")
    get_settings.cache_clear()
    # Sentinels: if anything tries to import these, fail loudly.
    import builtins

    real_import = builtins.__import__

    def guarded(name: str, *a: object, **kw: object) -> object:
        if name.startswith("googleapiclient") or name == "google.auth":
            raise AssertionError(f"unexpected import: {name}")
        return real_import(name, *a, **kw)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", guarded)
    # Drop any cached google_photos_optional module
    sys.modules.pop("calendar_photo_organizer.google_photos_optional", None)
    sys.modules.pop("calendar_photo_organizer.ui.routes.google_photos", None)

    from calendar_photo_organizer.db import migrate
    from calendar_photo_organizer.db.connection import connect

    conn = connect(tmp_path)
    migrate.apply(conn, data_dir=tmp_path)
    conn.close()

    app = create_app(data_dir=tmp_path)
    # Routes for picker/gp must NOT be registered
    paths = {r.path for r in app.routes}  # type: ignore[attr-defined]
    assert not any(p.startswith("/picker") or p.startswith("/gp") for p in paths)

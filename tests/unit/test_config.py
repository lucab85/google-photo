"""T009 — config + feature-flag defaults."""

from __future__ import annotations

from pathlib import Path

from calendar_photo_organizer.config import Settings, get_settings


def test_defaults(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CPO_DATA_DIR", str(tmp_path))
    # Clear cached singleton between tests
    get_settings.cache_clear()  # type: ignore[attr-defined]
    s = get_settings()
    assert s.feature_flags.google_photos_enabled is False
    assert s.matching.pre_buffer_seconds == 2 * 3600
    assert s.matching.post_buffer_seconds == 4 * 3600
    assert s.matching.multi_album_membership is False
    assert s.data_dir == tmp_path
    assert s.hashing.algorithm == "blake3"


def test_data_dir_falls_back_to_platformdirs(monkeypatch) -> None:
    monkeypatch.delenv("CPO_DATA_DIR", raising=False)
    get_settings.cache_clear()  # type: ignore[attr-defined]
    s = get_settings()
    assert s.data_dir.parts[-1] == "calendar-photo-organizer"


def test_env_override(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CPO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CPO_FEATURE_FLAGS__GOOGLE_PHOTOS_ENABLED", "true")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    s = Settings()
    assert s.feature_flags.google_photos_enabled is True

"""Application settings — loaded from environment + defaults.

Uses ``pydantic-settings`` with the ``CPO_`` env prefix. Nested settings are
addressed with double-underscore separators (e.g. ``CPO_FEATURE_FLAGS__GOOGLE_PHOTOS_ENABLED``).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

import platformdirs
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class FeatureFlags(BaseModel):
    google_photos_enabled: bool = False


class MatchingSettings(BaseModel):
    pre_buffer_seconds: int = 2 * 3600
    post_buffer_seconds: int = 4 * 3600
    multi_album_membership: bool = False


class HashingSettings(BaseModel):
    algorithm: Literal["blake3", "sha256"] = "blake3"
    chunk_size: int = 1024 * 1024


class UISettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8765


class Settings(BaseSettings):
    """Top-level settings object.

    Environment variables override defaults; nested fields use ``__`` as the
    separator (pydantic-settings convention).
    """

    model_config = SettingsConfigDict(
        env_prefix="CPO_",
        env_nested_delimiter="__",
        env_file=None,
        extra="ignore",
    )

    data_dir: Path = Field(
        default_factory=lambda: Path(platformdirs.user_data_dir("calendar-photo-organizer"))
    )
    log_format: Literal["json", "kv"] = "kv"

    feature_flags: FeatureFlags = Field(default_factory=FeatureFlags)
    matching: MatchingSettings = Field(default_factory=MatchingSettings)
    hashing: HashingSettings = Field(default_factory=HashingSettings)
    ui: UISettings = Field(default_factory=UISettings)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton accessor — call ``get_settings.cache_clear()`` in tests."""
    s = Settings()
    # Apply persisted user overrides (config.json) on top of env defaults.
    overrides_path = s.data_dir / "config.json"
    if overrides_path.is_file():
        import contextlib
        import json as _json

        try:
            raw = _json.loads(overrides_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return s
        if isinstance(raw, dict):
            merged = s.model_dump()
            for key, val in raw.items():
                if key in merged and isinstance(merged[key], dict) and isinstance(val, dict):
                    merged[key].update(val)
                else:
                    merged[key] = val
            with contextlib.suppress(Exception):
                s = Settings(**merged)
    return s


def write_overrides(data_dir: Path, overrides: dict[str, object]) -> None:
    """Persist *overrides* to ``<data_dir>/config.json`` (used by /config UI)."""
    import json as _json

    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / "config.json"
    existing: dict[str, object] = {}
    if path.is_file():
        try:
            loaded = _json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        except (OSError, ValueError):
            existing = {}
    for k, v in overrides.items():
        if isinstance(v, dict) and isinstance(existing.get(k), dict):
            cur = existing[k]
            assert isinstance(cur, dict)
            cur.update(v)
        else:
            existing[k] = v
    path.write_text(_json.dumps(existing, indent=2), encoding="utf-8")
    get_settings.cache_clear()

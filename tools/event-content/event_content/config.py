"""Configuration loading and the working-directory layout."""

from __future__ import annotations

import glob
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config.toml"


def _expand(p: str) -> Path:
    return Path(os.path.expanduser(p)).resolve() if p else Path()


@dataclass(frozen=True)
class Layout:
    """All derived files live under work_dir; nothing is written next to the Takeout."""

    root: Path

    @property
    def index_csv(self) -> Path:
        return self.root / "index.csv"

    @property
    def sidecars_jsonl(self) -> Path:
        return self.root / "sidecars.jsonl"

    @property
    def candidates_csv(self) -> Path:
        return self.root / "candidates.csv"

    @property
    def videos_csv(self) -> Path:
        return self.root / "videos.csv"

    @property
    def img_dir(self) -> Path:
        return self.root / "img"

    @property
    def vision_jsonl(self) -> Path:
        return self.root / "vision.jsonl"

    @property
    def sessions_json(self) -> Path:
        return self.root / "sessions.json"

    @property
    def calendar_json(self) -> Path:
        return self.root / "calendar-matches.json"

    @property
    def dossier_dir(self) -> Path:
        return self.root / "dossiers"

    @property
    def sheet_dir(self) -> Path:
        return self.root / "sheets"

    @property
    def video_dir(self) -> Path:
        return self.root / "videos"

    @property
    def frames_dir(self) -> Path:
        return self.root / "vframes"

    @property
    def frames_vision_jsonl(self) -> Path:
        return self.root / "vision-vframes.jsonl"

    @property
    def transcripts_dir(self) -> Path:
        return self.root / "transcripts"

    def ensure(self) -> Layout:
        for d in (
            self.root,
            self.img_dir,
            self.dossier_dir,
            self.sheet_dir,
            self.video_dir,
            self.frames_dir,
            self.transcripts_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)
        return self


@dataclass(frozen=True)
class Config:
    raw: dict[str, Any]

    def get(self, section: str, key: str, default: Any = None) -> Any:
        return self.raw.get(section, {}).get(key, default)

    def path(self, section: str, key: str) -> Path:
        return _expand(self.get(section, key, ""))

    @property
    def layout(self) -> Layout:
        return Layout(self.path("paths", "work_dir")).ensure()

    def takeout_zips(self) -> list[Path]:
        """Zips matching `takeout_glob`: one pattern, or a list (e.g. Downloads + an external disk)."""
        patterns = self.get("paths", "takeout_glob", "")
        if isinstance(patterns, str):
            patterns = [patterns]
        found = {Path(p) for pat in patterns for p in glob.glob(os.path.expanduser(pat))}
        return sorted(found, key=lambda p: p.name)


def load(path: str | Path | None = None) -> Config:
    p = Path(path) if path else DEFAULT_CONFIG
    if not p.exists():
        raise SystemExit(f"config not found: {p} (copy config.example.toml to config.toml)")
    with open(p, "rb") as fh:
        return Config(tomllib.load(fh))

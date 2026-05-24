"""T042 — resume after interruption skips already-hashed files."""

from __future__ import annotations

from pathlib import Path

from calendar_photo_organizer.db import migrate
from calendar_photo_organizer.db.connection import connect
from calendar_photo_organizer.db.repositories.media import MediaRepository
from calendar_photo_organizer.photos_takeout_importer import import_takeout

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "takeout_sample"


def test_rescan_does_not_rehash(tmp_path: Path, monkeypatch) -> None:
    conn = connect(tmp_path)
    migrate.apply(conn, data_dir=tmp_path)
    media = MediaRepository(conn)

    import_takeout(FIXTURE_DIR, media_repo=media, job_id=None)
    first_count = media.count()

    # Patch hash_file to count invocations
    import calendar_photo_organizer.photos_takeout_importer as imp

    calls = {"n": 0}
    orig = imp.hash_file

    def counting(p, **kw):
        calls["n"] += 1
        return orig(p, **kw)

    monkeypatch.setattr(imp, "hash_file", counting)

    # Re-run: identical (path, size, mtime) — must NOT rehash
    import_takeout(FIXTURE_DIR, media_repo=media, job_id=None)
    assert calls["n"] == 0
    assert media.count() == first_count

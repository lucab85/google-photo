"""T039 — content-hash deduplication during scan."""

from __future__ import annotations

from pathlib import Path

from calendar_photo_organizer.db import migrate
from calendar_photo_organizer.db.connection import connect
from calendar_photo_organizer.db.repositories.media import MediaRepository
from calendar_photo_organizer.photos_takeout_importer import import_takeout


def test_duplicate_content_collapses_to_one_media_row(tmp_path: Path) -> None:
    # Two distinct paths, identical bytes
    data = tmp_path / "src"
    data.mkdir()
    (data / "a.jpg").write_bytes(b"hello-bytes-1234567890")
    (data / "b.jpg").write_bytes(b"hello-bytes-1234567890")  # same content

    db_dir = tmp_path / "db"
    conn = connect(db_dir)
    migrate.apply(conn, data_dir=db_dir)
    media = MediaRepository(conn)

    import_takeout(data, media_repo=media, job_id=None)

    assert media.count() == 1
    media_id = next(media.iter_all()).id
    assert media_id is not None
    paths = media.paths_for(media_id)
    assert len(paths) == 2

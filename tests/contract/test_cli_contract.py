"""T045 — CLI contract (C-CLI-3, C-CLI-4, C-CLI-5)."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from calendar_photo_organizer.cli import app

runner = CliRunner()


def test_uninitialized_db_yields_exit_2(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CPO_DATA_DIR", str(tmp_path / "no-such"))
    from calendar_photo_organizer.config import get_settings
    get_settings.cache_clear()

    # Running scan against an uninitialized data dir
    result = runner.invoke(app, ["scan", str(tmp_path)])
    assert result.exit_code == 2
    assert "db-not-initialised" in result.output or "init" in result.output.lower()


def test_rescan_does_not_rehash(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CPO_DATA_DIR", str(tmp_path / "data"))
    from calendar_photo_organizer.config import get_settings
    get_settings.cache_clear()

    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_bytes(b"hi")

    assert runner.invoke(app, ["init"]).exit_code == 0
    r1 = runner.invoke(app, ["scan", str(src)])
    assert r1.exit_code == 0

    # Patch hash_file to count second-scan invocations
    import calendar_photo_organizer.photos_takeout_importer as imp
    calls = {"n": 0}
    orig = imp.hash_file
    def counting(p, **kw):
        calls["n"] += 1
        return orig(p, **kw)
    monkeypatch.setattr(imp, "hash_file", counting)

    r2 = runner.invoke(app, ["scan", str(src)])
    assert r2.exit_code == 0
    assert calls["n"] == 0


def test_version_command() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output

"""Calendar Photo Organizer CLI.

This module is the **only** place in the codebase allowed to call ``print()``.
Every other module must use ``structlog`` via ``logging_setup`` (Principle II).

Exit codes (C-CLI-3):
  * 0 — success
  * 1 — generic failure
  * 2 — operator configuration error (e.g., uninitialised DB)
  * 3 — re-authentication required (paused)
  * 4 — input/data error (e.g., missing path)
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import typer

from calendar_photo_organizer.config import get_settings
from calendar_photo_organizer.db import migrate
from calendar_photo_organizer.db.connection import connect, db_path

app = typer.Typer(
    name="cpo",
    help="Calendar Photo Organizer — organize a Google Takeout archive into event-based albums.",
    no_args_is_help=True,
)

auth_app = typer.Typer(help="Authentication helpers.")
app.add_typer(auth_app, name="auth")

review_app = typer.Typer(help="Local review UI.")
app.add_typer(review_app, name="review")

picker_app = typer.Typer(help="Google Photos Picker (feature-flag gated).")
app.add_typer(picker_app, name="picker")

gp_app = typer.Typer(help="Google Photos upload (feature-flag gated).")
app.add_typer(gp_app, name="gp")


@app.callback()
def _root() -> None:
    """Root callback so subcommands are exposed in multi-command mode."""


def _require_initialized_db() -> Path:
    """Return data_dir if DB exists; otherwise emit db-not-initialised and exit(2)."""
    settings = get_settings()
    if not db_path(settings.data_dir).exists():
        print("db-not-initialised: run `cpo init` first", file=sys.stderr)
        raise typer.Exit(code=2)
    return settings.data_dir


def _emit(payload: dict[str, object]) -> None:
    print(json.dumps(payload))


@app.command()
def version() -> None:
    """Print the installed package version."""
    from calendar_photo_organizer import __version__

    print(__version__)


@app.command()
def init() -> None:
    """Initialize the data directory and apply pending DB migrations."""
    get_settings.cache_clear()
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    conn = connect(settings.data_dir)
    try:
        applied = migrate.apply(conn, data_dir=settings.data_dir)
    finally:
        conn.close()
    print(f"Initialized data dir at {settings.data_dir}; migrations applied: {applied}")


@app.command()
def scan(
    path: Path = typer.Argument(..., exists=False, help="Takeout root to ingest."),
) -> None:
    """Scan a Google Takeout directory and record media items."""
    if not path.exists():
        print(f"path-not-found: {path}", file=sys.stderr)
        raise typer.Exit(code=4)
    data_dir = _require_initialized_db()

    from calendar_photo_organizer.db.repositories.errors import ErrorsRepository
    from calendar_photo_organizer.db.repositories.media import MediaRepository
    from calendar_photo_organizer.photos_takeout_importer import import_takeout

    conn = connect(data_dir)
    try:
        n = import_takeout(
            path,
            media_repo=MediaRepository(conn),
            errors_repo=ErrorsRepository(conn),
            job_id=None,
        )
    finally:
        conn.close()
    _emit({"event": "scan-complete", "processed": n})


@app.command()
def match() -> None:
    """Run the matcher over all media + events."""
    data_dir = _require_initialized_db()
    from calendar_photo_organizer.db.repositories.events import EventsRepository
    from calendar_photo_organizer.db.repositories.matches import MatchesRepository
    from calendar_photo_organizer.db.repositories.media import MediaRepository
    from calendar_photo_organizer.matcher import MatcherSettings, match_all

    settings = get_settings()
    conn = connect(data_dir)
    try:
        n = match_all(
            MediaRepository(conn),
            EventsRepository(conn),
            MatchesRepository(conn),
            MatcherSettings(
                pre_buffer_seconds=settings.matching.pre_buffer_seconds,
                post_buffer_seconds=settings.matching.post_buffer_seconds,
            ),
        )
    finally:
        conn.close()
    _emit({"event": "match-complete", "media_processed": n})


@app.command()
def propose() -> None:
    """Propose albums from recommended matches."""
    data_dir = _require_initialized_db()
    from calendar_photo_organizer.album_planner import propose_albums_from_recommended
    from calendar_photo_organizer.db.repositories.albums import AlbumsRepository
    from calendar_photo_organizer.db.repositories.events import EventsRepository
    from calendar_photo_organizer.db.repositories.matches import MatchesRepository

    settings = get_settings()
    conn = connect(data_dir)
    try:
        n = propose_albums_from_recommended(
            MatchesRepository(conn),
            EventsRepository(conn),
            AlbumsRepository(conn),
            allow_multi_album=settings.matching.multi_album_membership,
        )
    finally:
        conn.close()
    _emit({"event": "propose-complete", "albums": n})


@app.command("calendar-import")
def calendar_import(
    from_: str = typer.Option(..., "--from", help="ISO start date/time (UTC)."),
    to: str = typer.Option(..., "--to", help="ISO end date/time (UTC)."),
    calendar: str = typer.Option("primary", "--calendar"),
    from_json: Path | None = typer.Option(
        None, "--from-json", help="Import from a local JSON file instead of Google."
    ),
) -> None:
    """Import calendar events (live or from a local JSON dump)."""
    data_dir = _require_initialized_db()
    from calendar_photo_organizer.calendar_client import import_events_from_json
    from calendar_photo_organizer.db.repositories.events import EventsRepository

    conn = connect(data_dir)
    try:
        if from_json is not None:
            payload = json.loads(from_json.read_text())
            n = import_events_from_json(payload, EventsRepository(conn))
            _emit({"event": "calendar-import-complete", "events": n})
            return
        from calendar_photo_organizer.calendar_client import (
            CalendarAuthError,
            build_google_calendar_fetcher,
            run_calendar_import_with_reauth,
        )
        from calendar_photo_organizer.db.repositories.errors import ErrorsRepository
        from calendar_photo_organizer.db.repositories.jobs import JobsRepository
        from calendar_photo_organizer.jobs.runner import JobRunner

        try:
            creds = _load_google_credentials()
            fetcher = build_google_calendar_fetcher(creds, calendar_id=calendar)
        except ImportError:
            print("google-auth not installed; pass --from-json instead", file=sys.stderr)
            raise typer.Exit(code=2) from None

        runner = JobRunner(jobs_repo=JobsRepository(conn), errors_repo=ErrorsRepository(conn))
        try:
            asyncio.run(
                run_calendar_import_with_reauth(
                    runner,
                    events_repo=EventsRepository(conn),
                    fetcher=fetcher,
                    start_iso=from_,
                    end_iso=to,
                    calendar_id=calendar,
                )
            )
        except CalendarAuthError:
            print("reauth-required: run `cpo auth google-calendar`", file=sys.stderr)
            raise typer.Exit(code=3) from None
    finally:
        conn.close()
    _emit({"event": "calendar-import-complete"})


def _load_google_credentials() -> object:  # pragma: no cover
    raise NotImplementedError("Google credentials loader not configured in this build.")


@auth_app.command("google-calendar")
def auth_google_calendar() -> None:  # pragma: no cover
    """Run the OAuth installed-app flow for Google Calendar."""
    print("auth flow not implemented in this build", file=sys.stderr)
    raise typer.Exit(code=2)


@review_app.command("serve")
def review_serve(
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8765),
) -> None:  # pragma: no cover
    """Serve the local review UI on the loopback interface."""
    data_dir = _require_initialized_db()
    import uvicorn

    from calendar_photo_organizer.ui.app import create_app

    app_obj = create_app(data_dir=data_dir)
    uvicorn.run(app_obj, host=host, port=port, log_level="info")


@app.command()
def export(
    target_dir: Path = typer.Argument(..., help="Destination root for album folders."),
    dry_run: bool = typer.Option(True, "--dry-run/--write", help="Default is dry-run (C-CLI-1)."),
    mode: str = typer.Option("auto", "--mode", help="auto | symlink | copy"),
    confirm_copy: bool = typer.Option(False, "--confirm-copy"),
) -> None:
    """Export approved albums to *target_dir* (dry-run by default)."""
    data_dir = _require_initialized_db()
    from calendar_photo_organizer.exporter import execute, plan
    from calendar_photo_organizer.paths import probe_symlink_support

    target_dir.mkdir(parents=True, exist_ok=True)
    if mode == "auto":
        resolved = "symlink" if probe_symlink_support(target_dir) else "copy"
    else:
        resolved = mode

    if resolved == "copy" and not confirm_copy and not dry_run:
        print("copy-mode-required: pass --confirm-copy to proceed", file=sys.stderr)
        raise typer.Exit(code=2)

    import uuid

    conn = connect(data_dir)
    try:
        p = plan(conn, target_root=target_dir, mode=resolved)  # type: ignore[arg-type]
        execute(conn, p, dry_run=dry_run, writer_job_id=str(uuid.uuid4()), data_dir=data_dir)
    finally:
        conn.close()
    _emit({"event": "export-complete", "dry_run": dry_run, "albums": len(p.albums)})


@app.command()
def approve(
    band: str | None = typer.Option(None, "--band", help="high|medium|low"),
    album_id: int | None = typer.Option(None, "--album-id"),
    all_: bool = typer.Option(False, "--all", help="Apply to all matching albums"),
    reject: bool = typer.Option(False, "--reject", help="Reject instead of approve"),
) -> None:
    """Bulk approve / reject proposed albums (Clarification Q1)."""
    data_dir = _require_initialized_db()
    from calendar_photo_organizer.db.repositories.albums import AlbumsRepository
    from calendar_photo_organizer.models import AlbumStatus

    target_status = AlbumStatus.REJECTED if reject else AlbumStatus.APPROVED
    conn = connect(data_dir)
    try:
        repo = AlbumsRepository(conn)
        if album_id is not None:
            cur = repo.get(album_id)
            if cur is None:
                print(f"album-not-found: {album_id}", file=sys.stderr)
                raise typer.Exit(code=4)
            if not reject and cur.status == AlbumStatus.REJECTED:
                print("cannot-approve-rejected (C-HTTP-4)", file=sys.stderr)
                raise typer.Exit(code=4)
            repo.set_status(album_id, target_status)
            conn.commit()
            _emit({"event": "approve", "album_id": album_id, "status": str(target_status)})
            return
        if not (band or all_):
            print("specify --album-id, --band, or --all", file=sys.stderr)
            raise typer.Exit(code=4)
        rows = repo.list_page(band=band, page=1, page_size=10000)
        n = 0
        for a in rows:
            if a.id is None:
                continue
            if not reject and a.status == AlbumStatus.REJECTED:
                continue
            repo.set_status(a.id, target_status)
            n += 1
        conn.commit()
        _emit({"event": "approve", "band": band, "all": all_, "count": n,
               "status": str(target_status)})
    finally:
        conn.close()


@app.command()
def doctor() -> None:
    """Print environment + capability checks."""
    import platform
    import shutil

    from calendar_photo_organizer import __version__
    from calendar_photo_organizer.paths import probe_symlink_support

    settings = get_settings()
    blake3_ok = True
    try:
        import blake3 as _blake3  # noqa: F401
    except ImportError:
        blake3_ok = False
    pillow_heif_ok = True
    try:
        import pillow_heif as _heif  # noqa: F401
    except ImportError:
        pillow_heif_ok = False
    keyring_backend = ""
    try:
        import keyring

        keyring_backend = keyring.get_keyring().__class__.__name__
    except (ImportError, Exception):
        keyring_backend = "unavailable"
    info = {
        "version": __version__,
        "python": platform.python_version(),
        "os": f"{platform.system()} {platform.release()}",
        "data_dir": str(settings.data_dir),
        "db_initialized": db_path(settings.data_dir).exists(),
        "blake3_available": blake3_ok,
        "pillow_heif_available": pillow_heif_ok,
        "ffprobe_on_path": shutil.which("ffprobe") is not None,
        "keyring_backend": keyring_backend,
        "symlink_support_cwd": probe_symlink_support(Path.cwd()),
        "symlink_support_data_dir": probe_symlink_support(settings.data_dir)
            if settings.data_dir.exists() else False,
        "google_photos_enabled": settings.feature_flags.google_photos_enabled,
    }
    _emit({"event": "doctor", **info})


@app.command()
def demo() -> None:
    """Run the full pipeline against the bundled fixture in a temp data dir."""
    import tempfile
    from pathlib import Path as _Path

    fixture = (
        _Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "takeout_sample"
    )
    if not fixture.is_dir():
        print("demo-fixture-missing", file=sys.stderr)
        raise typer.Exit(code=1)
    tmp = _Path(tempfile.mkdtemp(prefix="cpo-demo-"))
    data = tmp / "data"
    target = tmp / "out"
    data.mkdir()
    target.mkdir()
    # Initialise DB
    from calendar_photo_organizer.db import migrate as _mig

    conn = connect(data)
    _mig.apply(conn, data_dir=data)
    conn.close()
    # Scan
    from calendar_photo_organizer.db.repositories.errors import ErrorsRepository
    from calendar_photo_organizer.db.repositories.media import MediaRepository
    from calendar_photo_organizer.photos_takeout_importer import import_takeout

    conn = connect(data)
    n = import_takeout(
        fixture, media_repo=MediaRepository(conn),
        errors_repo=ErrorsRepository(conn), job_id="demo",
    )
    conn.close()
    # Dry-run export with no albums (informational)
    from calendar_photo_organizer.exporter import execute as _exec
    from calendar_photo_organizer.exporter import plan as _plan

    conn = connect(data)
    p = _plan(conn, target_root=target, mode="symlink")
    _exec(conn, p, dry_run=True, writer_job_id="demo", data_dir=data)
    conn.close()
    plan_path = data / "dry-runs" / "demo" / "plan.json"
    _emit({
        "event": "demo-complete", "data_dir": str(data), "imported_media": n,
        "plan_path": str(plan_path) if plan_path.exists() else None,
    })


@picker_app.command("import")
def picker_import() -> None:
    """Picker import (requires --feature-flag google_photos_enabled)."""
    settings = get_settings()
    if not settings.feature_flags.google_photos_enabled:
        print(
            "google-photos-disabled: set CPO_FEATURE_FLAGS__GOOGLE_PHOTOS_ENABLED=true",
            file=sys.stderr,
        )
        raise typer.Exit(code=2)
    print("picker-import: no interactive flow available in this build", file=sys.stderr)
    raise typer.Exit(code=1)


@gp_app.command("upload")
def gp_upload(album_id: int = typer.Argument(...)) -> None:
    """Upload an approved album to Google Photos (feature-flag gated)."""
    settings = get_settings()
    if not settings.feature_flags.google_photos_enabled:
        print(
            "google-photos-disabled: set CPO_FEATURE_FLAGS__GOOGLE_PHOTOS_ENABLED=true",
            file=sys.stderr,
        )
        raise typer.Exit(code=2)
    _ = album_id
    print("gp-upload: no interactive flow available in this build", file=sys.stderr)
    raise typer.Exit(code=1)


if __name__ == "__main__":
    app()

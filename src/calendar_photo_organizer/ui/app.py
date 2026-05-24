"""FastAPI app factory for the local review UI.

Binds 127.0.0.1 by default (C-HTTP-1). Google Photos routes are mounted only
when ``feature_flags.google_photos_enabled`` is true (FR-007/008).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from calendar_photo_organizer.config import get_settings
from calendar_photo_organizer.db.connection import connect

_STATIC = Path(__file__).parent / "static"
_TEMPLATES = Path(__file__).parent / "templates"


def default_host() -> str:
    return "127.0.0.1"


def default_port() -> int:
    return 8765


def create_app(*, data_dir: Path | None = None) -> FastAPI:
    settings = get_settings()
    resolved_data_dir = data_dir or settings.data_dir

    app = FastAPI(title="Calendar Photo Organizer", docs_url=None, redoc_url=None)
    app.state.data_dir = resolved_data_dir
    app.state.templates = Jinja2Templates(directory=str(_TEMPLATES))

    if _STATIC.exists():
        app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")

    def open_conn() -> object:
        return connect(resolved_data_dir)

    app.state.open_conn = open_conn

    # Register routes
    from calendar_photo_organizer.ui.routes import (
        albums as albums_routes,
    )
    from calendar_photo_organizer.ui.routes import (
        auth as auth_routes,
    )
    from calendar_photo_organizer.ui.routes import (
        config as config_routes,
    )
    from calendar_photo_organizer.ui.routes import (
        dashboard as dashboard_routes,
    )
    from calendar_photo_organizer.ui.routes import (
        export as export_routes,
    )
    from calendar_photo_organizer.ui.routes import (
        jobs as jobs_routes,
    )
    from calendar_photo_organizer.ui.routes import (
        unmatched as unmatched_routes,
    )

    app.include_router(dashboard_routes.router)
    app.include_router(albums_routes.router)
    app.include_router(unmatched_routes.router)
    app.include_router(jobs_routes.router)
    app.include_router(export_routes.router)
    app.include_router(config_routes.router)

    if settings.feature_flags.google_photos_enabled:
        try:
            import importlib

            gp_mod = importlib.import_module(
                "calendar_photo_organizer.ui.routes.google_photos"
            )
            app.include_router(gp_mod.router)
        except ImportError:
            pass

    app.include_router(auth_routes.router)

    @app.get("/healthz")
    def healthz() -> str:
        return "ok"

    return app

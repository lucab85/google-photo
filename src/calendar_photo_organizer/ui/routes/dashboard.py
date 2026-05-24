"""Dashboard route — counters + recent jobs."""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    conn = request.app.state.open_conn()
    try:
        media_count = int(conn.execute("SELECT COUNT(*) AS c FROM media_items").fetchone()["c"])
        event_count = int(conn.execute("SELECT COUNT(*) AS c FROM calendar_events").fetchone()["c"])
        album_count = int(conn.execute("SELECT COUNT(*) AS c FROM proposed_albums").fetchone()["c"])
        match_bands = {"high": 0, "medium": 0, "low": 0}
        for row in conn.execute(
            "SELECT band, COUNT(*) AS c FROM media_event_matches "
            "WHERE is_recommended = 1 GROUP BY band"
        ):
            match_bands[row["band"]] = int(row["c"])
        unmatched = int(
            conn.execute(
                "SELECT COUNT(*) AS c FROM media_items m "
                "LEFT JOIN media_event_matches x ON x.media_id = m.id "
                "WHERE x.id IS NULL"
            ).fetchone()["c"]
        )
    finally:
        conn.close()

    templates = request.app.state.templates
    return cast(HTMLResponse, templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "media_count": media_count,
            "event_count": event_count,
            "album_count": album_count,
            "match_bands": match_bands,
            "unmatched_count": unmatched,
        },
    ))

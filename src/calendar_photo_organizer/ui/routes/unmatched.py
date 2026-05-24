"""Unmatched media browser — grouped by date."""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/unmatched")


@router.get("", response_class=HTMLResponse)
def unmatched(
    request: Request, date: str | None = None, page: int = 1, page_size: int = 50
) -> HTMLResponse:
    conn = request.app.state.open_conn()
    try:
        page_size = max(1, min(int(page_size), 200))
        offset = (max(int(page), 1) - 1) * page_size
        if date:
            q = """SELECT m.id, m.captured_at_utc FROM media_items m
                    LEFT JOIN media_event_matches x ON x.media_id = m.id
                    WHERE x.id IS NULL AND substr(m.captured_at_utc, 1, 10) = ?
                    ORDER BY m.captured_at_utc LIMIT ? OFFSET ?"""
            rows = list(conn.execute(q, (date, page_size, offset)))
        else:
            q = """SELECT m.id, m.captured_at_utc FROM media_items m
                    LEFT JOIN media_event_matches x ON x.media_id = m.id
                    WHERE x.id IS NULL
                    ORDER BY m.captured_at_utc LIMIT ? OFFSET ?"""
            rows = list(conn.execute(q, (page_size, offset)))
        media = [{"id": r["id"], "captured_at_utc": r["captured_at_utc"]} for r in rows]
    finally:
        conn.close()
    return cast(HTMLResponse, request.app.state.templates.TemplateResponse(
        request,
        "unmatched.html",
        {"media": media, "date": date, "page": page, "page_size": page_size},
    ))

"""Albums browsing + mutation routes (paginated, ≤200/page)."""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import HTMLResponse

from calendar_photo_organizer.album_planner import (
    merge_albums,
    rename_album,
    split_album,
)
from calendar_photo_organizer.db.repositories.albums import AlbumsRepository
from calendar_photo_organizer.models import AlbumStatus

router = APIRouter(prefix="/albums")


@router.get("", response_class=HTMLResponse)
def list_albums(
    request: Request, band: str | None = None, page: int = 1, page_size: int = 50
) -> HTMLResponse:
    conn = request.app.state.open_conn()
    try:
        albums_repo = AlbumsRepository(conn)
        rows = albums_repo.list_page(band=band, page=page, page_size=page_size)
        total = albums_repo.count()
    finally:
        conn.close()
    return cast(HTMLResponse, request.app.state.templates.TemplateResponse(
        request,
        "albums_list.html",
        {
            "albums": rows, "page": page,
            "page_size": page_size, "band": band, "total": total,
        },
    ))


@router.get("/{album_id}", response_class=HTMLResponse)
def album_detail(
    request: Request, album_id: int, page: int = 1, page_size: int = 50
) -> HTMLResponse:
    conn = request.app.state.open_conn()
    try:
        albums_repo = AlbumsRepository(conn)
        album = albums_repo.get(album_id)
        items = albums_repo.items(album_id)
        page_size = max(1, min(int(page_size), 200))
        start = (max(int(page), 1) - 1) * page_size
        slice_ = items[start : start + page_size]
    finally:
        conn.close()
    return cast(HTMLResponse, request.app.state.templates.TemplateResponse(
        request,
        "album_detail.html",
        {
            "album": album, "media_ids": slice_,
            "page": page, "page_size": page_size, "total": len(items),
        },
    ))


# ---- Mutations -----------------------------------------------------------


@router.post("/bulk/approve")
def bulk_approve(request: Request, body: dict[str, object] = Body(...)) -> dict[str, object]:
    band_raw = body.get("band")
    band = str(band_raw) if isinstance(band_raw, str) else None
    conn = request.app.state.open_conn()
    try:
        repo = AlbumsRepository(conn)
        rows = repo.list_page(band=band, page=1, page_size=200)
        n = 0
        for a in rows:
            if a.status == AlbumStatus.REJECTED or a.id is None:
                continue
            repo.set_status(a.id, AlbumStatus.APPROVED)
            n += 1
        conn.commit()
    finally:
        conn.close()
    return {"approved": n}


@router.post("/bulk/reject")
def bulk_reject(request: Request, body: dict[str, object] = Body(...)) -> dict[str, object]:
    band_raw = body.get("band")
    band = str(band_raw) if isinstance(band_raw, str) else None
    empty_only = bool(body.get("empty_only", False))
    conn = request.app.state.open_conn()
    try:
        repo = AlbumsRepository(conn)
        rows = repo.list_page(band=band, page=1, page_size=200)
        n = 0
        for a in rows:
            if a.id is None:
                continue
            if empty_only and repo.items(a.id):
                continue
            repo.set_status(a.id, AlbumStatus.REJECTED)
            n += 1
        conn.commit()
    finally:
        conn.close()
    return {"rejected": n}


@router.post("/merge")
def merge_route(request: Request, body: dict[str, object] = Body(...)) -> dict[str, object]:
    raw = body.get("source_ids", [])
    source_ids = [int(x) for x in (raw if isinstance(raw, list) else [])]
    new_name = str(body.get("display_name", "")).strip()
    if not source_ids or not new_name:
        raise HTTPException(status_code=400, detail="source_ids and display_name required")
    conn = request.app.state.open_conn()
    try:
        new_id = merge_albums(AlbumsRepository(conn), source_ids, new_name)
    finally:
        conn.close()
    return {"status": "ok", "new_album_id": new_id}


@router.post("/{album_id}/rename")
def rename_route(
    request: Request, album_id: int, body: dict[str, object] = Body(...)
) -> dict[str, object]:
    new_name = str(body.get("display_name", "")).strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="display_name required")
    conn = request.app.state.open_conn()
    try:
        rename_album(AlbumsRepository(conn), album_id, new_name)
    finally:
        conn.close()
    return {"status": "ok"}


@router.post("/{album_id}/split")
def split_route(
    request: Request, album_id: int, body: dict[str, object] = Body(...)
) -> dict[str, object]:
    raw = body.get("media_ids", [])
    media_ids = [int(x) for x in (raw if isinstance(raw, list) else [])]
    new_name = str(body.get("display_name", "")).strip()
    if not media_ids or not new_name:
        raise HTTPException(status_code=400, detail="media_ids and display_name required")
    conn = request.app.state.open_conn()
    try:
        new_id = split_album(AlbumsRepository(conn), album_id, media_ids, new_name)
    finally:
        conn.close()
    return {"status": "ok", "new_album_id": new_id}


@router.post("/{album_id}/approve")
def approve_route(request: Request, album_id: int) -> dict[str, object]:
    conn = request.app.state.open_conn()
    try:
        repo = AlbumsRepository(conn)
        cur = repo.get(album_id)
        if cur is None:
            raise HTTPException(status_code=404, detail="not-found")
        if cur.status == AlbumStatus.REJECTED:
            raise HTTPException(status_code=409, detail="cannot-approve-rejected (C-HTTP-4)")
        repo.set_status(album_id, AlbumStatus.APPROVED)
        conn.commit()
    finally:
        conn.close()
    return {"status": "ok"}


@router.post("/{album_id}/reject")
def reject_route(request: Request, album_id: int) -> dict[str, object]:
    conn = request.app.state.open_conn()
    try:
        AlbumsRepository(conn).set_status(album_id, AlbumStatus.REJECTED)
        conn.commit()
    finally:
        conn.close()
    return {"status": "ok"}

"""Google Photos UI routes (registered only when feature flag is ON, C-HTTP-2)."""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/picker/start", response_class=HTMLResponse)
def picker_start(request: Request) -> HTMLResponse:
    return cast(HTMLResponse, request.app.state.templates.TemplateResponse(
        request, "auth/gp_consent.html", {"action": "/picker/poll"},
    ))


@router.post("/picker/poll")
def picker_poll(request: Request, body: dict[str, object] = Body(default={})) -> dict[str, object]:
    """Driver-injected fetcher endpoint — tests/CLI provide a callable."""
    fetcher = getattr(request.app.state, "picker_fetcher", None)
    if fetcher is None:
        raise HTTPException(status_code=503, detail="picker-not-configured")
    from calendar_photo_organizer.db.repositories.media import MediaRepository
    from calendar_photo_organizer.google_photos_optional import import_picker_selection

    conn = request.app.state.open_conn()
    try:
        created = import_picker_selection(
            request.app.state.data_dir, fetcher=fetcher, media_repo=MediaRepository(conn),
        )
        conn.commit()
    finally:
        conn.close()
    return {"created": created}


@router.post("/gp/upload/{album_id}")
def gp_upload(request: Request, album_id: int) -> dict[str, object]:
    create_album = getattr(request.app.state, "gp_create_album", None)
    upload_items = getattr(request.app.state, "gp_upload_items", None)
    if create_album is None or upload_items is None:
        raise HTTPException(status_code=503, detail="gp-uploader-not-configured")
    from calendar_photo_organizer.db.repositories.albums import AlbumsRepository
    from calendar_photo_organizer.google_photos_optional import upload_album

    conn = request.app.state.open_conn()
    try:
        result = upload_album(
            album_id, conn=conn, albums_repo=AlbumsRepository(conn),
            create_album=create_album, upload_items=upload_items,
        )
    finally:
        conn.close()
    return {
        "remote_album_id": result.album_id_remote,
        "uploaded": result.uploaded,
        "failed": result.failed,
    }


# GET form for tests that probe registration with GET
@router.get("/gp/upload/{album_id}")
def gp_upload_get(request: Request, album_id: int) -> dict[str, object]:
    return {"album_id": album_id, "method": "POST required"}

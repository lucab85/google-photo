"""Config route (T076) — show & edit buffers, multi-album toggle, feature flags."""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse

from calendar_photo_organizer.config import get_settings, write_overrides

router = APIRouter(prefix="/config")


@router.get("", response_class=HTMLResponse)
def show(request: Request) -> HTMLResponse:
    s = get_settings()
    ctx = {
        "pre_buffer_hours": s.matching.pre_buffer_seconds / 3600,
        "post_buffer_hours": s.matching.post_buffer_seconds / 3600,
        "multi_album": s.matching.multi_album_membership,
        "google_photos_enabled": s.feature_flags.google_photos_enabled,
    }
    return cast(HTMLResponse, request.app.state.templates.TemplateResponse(
        request, "config.html", ctx,
    ))


@router.post("")
def update(request: Request, body: dict[str, object] = Body(...)) -> dict[str, object]:
    matching: dict[str, object] = {}
    feature_flags: dict[str, object] = {}
    buffer_changed = False
    if "pre_buffer_hours" in body:
        matching["pre_buffer_seconds"] = int(float(cast(float, body["pre_buffer_hours"])) * 3600)
        buffer_changed = True
    if "post_buffer_hours" in body:
        matching["post_buffer_seconds"] = int(float(cast(float, body["post_buffer_hours"])) * 3600)
        buffer_changed = True
    if "multi_album_membership" in body:
        matching["multi_album_membership"] = bool(body["multi_album_membership"])
    if "google_photos_enabled" in body:
        feature_flags["google_photos_enabled"] = bool(body["google_photos_enabled"])
    overrides: dict[str, object] = {}
    if matching:
        overrides["matching"] = matching
    if feature_flags:
        overrides["feature_flags"] = feature_flags
    if overrides:
        write_overrides(request.app.state.data_dir, overrides)
    return {"status": "ok", "rerun_match_recommended": buffer_changed}

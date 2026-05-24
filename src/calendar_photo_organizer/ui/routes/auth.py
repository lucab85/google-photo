"""Auth helper routes (Google Calendar re-auth landing page)."""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/auth")


@router.get("/calendar/reauth", response_class=HTMLResponse)
def calendar_reauth(request: Request) -> HTMLResponse:
    return cast(HTMLResponse, request.app.state.templates.TemplateResponse(
        request,
        "auth_reauth.html",
        {"provider": "Google Calendar"},
    ))

"""T066 — export preview + run routes."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from calendar_photo_organizer.exporter import execute, plan
from calendar_photo_organizer.paths import probe_symlink_support

router = APIRouter(prefix="/export")


@router.get("/preview")
def export_preview(request: Request, target: str, mode: str = "auto") -> dict[str, object]:
    target_root = Path(target)
    target_root.mkdir(parents=True, exist_ok=True)
    resolved = mode
    if mode == "auto":
        resolved = "symlink" if probe_symlink_support(target_root) else "copy"

    conn = request.app.state.open_conn()
    try:
        p = plan(conn, target_root=target_root, mode=resolved)  # type: ignore[arg-type]
        return {
            "target_root": str(p.target_root),
            "mode": p.mode,
            "album_count": len(p.albums),
            "item_count": sum(len(a.items) for a in p.albums),
        }
    finally:
        conn.close()


@router.post("/run")
def export_run(
    request: Request, target: str, mode: str = "auto", confirm_copy: bool = False
) -> dict[str, object]:
    target_root = Path(target)
    target_root.mkdir(parents=True, exist_ok=True)
    resolved = mode
    if mode == "auto":
        resolved = "symlink" if probe_symlink_support(target_root) else "copy"
    if resolved == "copy" and not confirm_copy:
        raise HTTPException(
            status_code=409,
            detail="copy-mode-required: pass confirm_copy=true (C-HTTP-5)",
        )
    conn = request.app.state.open_conn()
    try:
        p = plan(conn, target_root=target_root, mode=resolved)  # type: ignore[arg-type]
        execute(
            conn, p, dry_run=False, writer_job_id=str(uuid.uuid4()),
            data_dir=request.app.state.data_dir,
        )
        return {"status": "ok", "albums_exported": len(p.albums)}
    finally:
        conn.close()

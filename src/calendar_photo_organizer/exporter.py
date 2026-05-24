"""Export pipeline (T065).

``plan()`` reads the DB and produces an :class:`ExportPlan` (pure, no FS writes).
``execute()`` drives :func:`paths.link_or_copy`, writes per-album ``manifest.json``
plus a top-level ``report.csv`` (C-EXP-1, C-EXP-4). In dry-run mode (default), no
file is created under ``target_root``; instead ``plan.json`` and ``plan-report.csv``
are written under ``<data_dir>/dry-runs/<job_id>/`` (C-EXP-3).
"""

from __future__ import annotations

import csv
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from calendar_photo_organizer.album_planner import sanitize_folder_name
from calendar_photo_organizer.paths import link_or_copy

Mode = Literal["symlink", "copy", "auto"]

CONTRACT_VERSION = 1


@dataclass(slots=True)
class PlannedItem:
    media_id: int
    source_path: Path
    dest_name: str


@dataclass(slots=True)
class PlannedAlbum:
    album_id: int
    folder_name: str
    display_name: str
    items: list[PlannedItem] = field(default_factory=list)


@dataclass(slots=True)
class ExportPlan:
    target_root: Path
    mode: Literal["symlink", "copy"]
    albums: list[PlannedAlbum] = field(default_factory=list)


def plan(
    conn: sqlite3.Connection, *, target_root: Path, mode: Mode = "symlink"
) -> ExportPlan:
    """Build an :class:`ExportPlan` from the approved albums in *conn*."""
    resolved: Literal["symlink", "copy"]
    if mode == "auto":
        from calendar_photo_organizer.paths import probe_symlink_support

        resolved = "symlink" if probe_symlink_support(target_root) else "copy"
    else:
        resolved = mode

    out = ExportPlan(target_root=target_root, mode=resolved)
    rows = conn.execute(
        """SELECT a.id, a.folder_name, a.display_name
             FROM proposed_albums a
            WHERE a.status IN ('approved', 'exported')
            ORDER BY a.id"""
    ).fetchall()
    for row in rows:
        pa = PlannedAlbum(
            album_id=int(row["id"]),
            folder_name=sanitize_folder_name(row["folder_name"]),
            display_name=row["display_name"],
        )
        items = conn.execute(
            """SELECT ai.media_id, mp.path
                 FROM album_items ai
                 JOIN media_paths mp ON mp.media_id = ai.media_id AND mp.is_primary = 1
                WHERE ai.album_id = ?
                ORDER BY ai.media_id""",
            (pa.album_id,),
        )
        for item in items:
            src = Path(item["path"])
            pa.items.append(
                PlannedItem(media_id=int(item["media_id"]), source_path=src, dest_name=src.name)
            )
        out.albums.append(pa)
    return out


def _write_manifest(album_dir: Path, pa: PlannedAlbum) -> None:
    manifest = {
        "contract_version": CONTRACT_VERSION,
        "album_id": pa.album_id,
        "display_name": pa.display_name,
        "folder_name": pa.folder_name,
        "items": [
            {
                "media_id": it.media_id,
                "source_path": str(it.source_path),
                "dest_name": it.dest_name,
            }
            for it in pa.items
        ],
        "exported_at_utc": datetime.now(UTC).isoformat(),
    }
    (album_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))


def _write_report(target_root: Path, plan_obj: ExportPlan, *, status: str = "current") -> None:
    """Append per-album rows to ``report.csv`` (C-EXP-4)."""
    report = target_root / "report.csv"
    fieldnames = [
        "album_id", "folder_name", "display_name", "item_count",
        "status", "exported_at_utc", "notes",
    ]
    exists = report.exists()
    with report.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        for pa in plan_obj.albums:
            writer.writerow({
                "album_id": pa.album_id,
                "folder_name": pa.folder_name,
                "display_name": pa.display_name,
                "item_count": len(pa.items),
                "status": status,
                "exported_at_utc": datetime.now(UTC).isoformat(),
                "notes": "",
            })


def _append_orphan_rows(
    target_root: Path, conn: sqlite3.Connection, export_target_id: int
) -> None:
    """Append rows for any orphaned-by-rename exports (FR-034a)."""
    rows = conn.execute(
        """SELECT album_id, folder_name, item_count, status, exported_at_utc, notes
             FROM exported_albums
            WHERE export_target_id = ? AND status = 'orphaned-by-rename'""",
        (export_target_id,),
    ).fetchall()
    if not rows:
        return
    report = target_root / "report.csv"
    fieldnames = [
        "album_id", "folder_name", "display_name", "item_count",
        "status", "exported_at_utc", "notes",
    ]
    exists = report.exists()
    with report.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        if not exists:
            w.writeheader()
        for r in rows:
            w.writerow({
                "album_id": r["album_id"], "folder_name": r["folder_name"],
                "display_name": "", "item_count": r["item_count"],
                "status": r["status"], "exported_at_utc": r["exported_at_utc"],
                "notes": r["notes"] or "",
            })


def _register_export_target(
    conn: sqlite3.Connection, root: Path, mode: str
) -> int:
    cur = conn.execute("SELECT id FROM export_targets WHERE root=?", (str(root),)).fetchone()
    if cur is not None:
        conn.execute(
            "UPDATE export_targets SET mode=?, last_run_at_utc=? WHERE id=?",
            (mode, datetime.now(UTC).isoformat(), int(cur["id"])),
        )
        return int(cur["id"])
    new_id = conn.execute(
        "INSERT INTO export_targets (root, mode, last_run_at_utc) VALUES (?, ?, ?)",
        (str(root), mode, datetime.now(UTC).isoformat()),
    ).lastrowid
    return int(new_id or 0)


def execute(
    conn: sqlite3.Connection,
    plan_obj: ExportPlan,
    *,
    dry_run: bool,
    writer_job_id: str,
    data_dir: Path,
) -> None:
    """Materialize *plan_obj* on disk (or in dry-run, write the plan only)."""
    if dry_run:
        dry_dir = data_dir / "dry-runs" / writer_job_id
        dry_dir.mkdir(parents=True, exist_ok=True)
        (dry_dir / "plan.json").write_text(
            json.dumps(
                {
                    "contract_version": CONTRACT_VERSION,
                    "target_root": str(plan_obj.target_root),
                    "mode": plan_obj.mode,
                    "albums": [
                        {
                            "album_id": pa.album_id,
                            "folder_name": pa.folder_name,
                            "item_count": len(pa.items),
                        }
                        for pa in plan_obj.albums
                    ],
                },
                indent=2,
            )
        )
        with (dry_dir / "plan-report.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["album_id", "folder_name", "item_count"])
            for pa in plan_obj.albums:
                w.writerow([pa.album_id, pa.folder_name, len(pa.items)])
        return

    # Real export
    plan_obj.target_root.mkdir(parents=True, exist_ok=True)
    export_target_id = _register_export_target(conn, plan_obj.target_root, plan_obj.mode)
    for pa in plan_obj.albums:
        album_dir = plan_obj.target_root / pa.folder_name
        album_dir.mkdir(parents=True, exist_ok=True)
        for it in pa.items:
            dest = album_dir / it.dest_name
            if dest.exists() or dest.is_symlink():
                continue  # idempotency
            link_or_copy(it.source_path, dest, mode=plan_obj.mode)
        _write_manifest(album_dir, pa)
        conn.execute(
            "UPDATE proposed_albums SET status='exported' WHERE id=?", (pa.album_id,)
        )
        # Register this folder as a current export so the rename trigger can
        # later mark it orphaned-by-rename (Invariant I-4).
        conn.execute(
            """INSERT OR IGNORE INTO exported_albums
                 (export_target_id, album_id, folder_name, item_count,
                  exported_at_utc, status, notes)
               VALUES (?, ?, ?, ?, ?, 'current', NULL)""",
            (
                export_target_id, pa.album_id, pa.folder_name, len(pa.items),
                datetime.now(UTC).isoformat(),
            ),
        )
    _write_report(plan_obj.target_root, plan_obj)
    _append_orphan_rows(plan_obj.target_root, conn, export_target_id)
    conn.commit()

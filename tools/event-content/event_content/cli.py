"""Command line: python -m event_content [--config config.toml] <step> [...]

Steps (each is resumable and idempotent; run `all` for index→dossiers, then `videos`):
  index       index JSON sidecars across all Takeout zips          -> index.csv
  select      privacy filter (own camera, no family/private)        -> candidates.csv, videos.csv
  extract     analysis-sized copies of candidate photos             -> img/
  vision      Apple Vision OCR / QR / labels / faces / aesthetics   -> vision.jsonl
  sessions    group photos into time/GPS sessions                   -> sessions.json
  calendar    attach overlapping calendar events (cpo.db or JSON)   -> calendar-matches.json
  dossiers    one dossier per session (md + json)                   -> dossiers/
  videos      frames OCR + whisper transcripts for event sessions   -> vframes/, transcripts/
  list        print event-like sessions (the writing worklist)
  sheet SID   contact sheet for a session                           -> sheets/
  export SLUG TITLE=name ... [--thumb TITLE]   web images into the blog repo
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from . import (
    calendar_match,
    dossiers,
    export_images,
    extract,
    select,
    sessions,
    sheet,
    takeout_index,
    videos,
    vision,
)
from . import config as cfgmod


def _index_by_stem(rows: list[dict]) -> dict[str, dict]:
    return {r["title"].rsplit(".", 1)[0]: r for r in rows}


def cmd_index(c, a):
    zips = c.takeout_zips()
    if not zips:
        sys.exit(f"no zips match {c.get('paths', 'takeout_glob')}")
    print(
        json.dumps(
            {"zips": [z.name for z in zips], **takeout_index.build_index(zips, c.layout.index_csv)}
        )
    )


def cmd_select(c, a):
    rows = takeout_index.read_index(c.layout.index_csv)
    stats = select.select(
        rows, c.raw.get("filters", {}), c.layout.candidates_csv, c.layout.videos_csv
    )
    print(json.dumps(dict(stats.most_common())))


def cmd_extract(c, a):
    rows = takeout_index.read_index(c.layout.candidates_csv)
    n, errs = extract.extract(
        rows, c.layout.img_dir, c.get("vision", "max_edge", 2100), c.get("vision", "workers", 8)
    )
    print(json.dumps({"extracted_now": n, "errors": len(errs)}))
    for e in errs[:20]:
        print("  ", e)


def cmd_vision(c, a):
    rows = takeout_index.read_index(c.layout.candidates_csv)
    imgs = [c.layout.img_dir / f"{r['title'].rsplit('.', 1)[0]}.jpg" for r in rows]
    imgs = [p for p in imgs if p.exists()]
    print(
        json.dumps(
            vision.run(
                imgs,
                c.layout.vision_jsonl,
                c.get("vision", "chunk", 150),
                c.get("vision", "languages", "en-US"),
            )
        )
    )


def cmd_sessions(c, a):
    rows = takeout_index.read_index(c.layout.candidates_csv)
    s = sessions.build(
        rows,
        c.get("sessions", "gap_minutes", 90),
        c.get("sessions", "min_photos", 6),
        c.get("sessions", "timezone", "Europe/Amsterdam"),
    )
    c.layout.sessions_json.write_text(json.dumps(s))
    print(json.dumps({"sessions": len(s)}))


def cmd_calendar(c, a):
    evs = calendar_match.load_events(
        c.path("calendar", "cpo_db"), c.path("calendar", "events_json")
    )
    s = json.loads(c.layout.sessions_json.read_text())
    m = calendar_match.match(
        s, evs, c.get("calendar", "private_keywords", []), c.get("calendar", "padding_minutes", 60)
    )
    c.layout.calendar_json.write_text(json.dumps(m, indent=1))
    print(
        json.dumps(
            {"events_loaded": len(evs), "sessions_with_hints": sum(1 for v in m.values() if v)}
        )
    )


def _video_context(c) -> tuple[dict, dict]:
    """Per-session video frame text and transcripts, if the videos step has run."""
    vt: dict[str, list[str]] = defaultdict(list)
    tr: dict[str, list[tuple[str, str]]] = defaultdict(list)
    man = videos.load_manifest(c.layout.root)
    by_frame_dir: dict[str, list[dict]] = defaultdict(list)
    if c.layout.frames_vision_jsonl.exists():
        with open(c.layout.frames_vision_jsonl) as fh:
            lines = fh.readlines()
        for line in lines:
            try:
                v = json.loads(line)
            except ValueError:
                continue
            by_frame_dir[Path(v["path"]).parent.name].append(v)
    for m in man:
        stem = m["title"].rsplit(".", 1)[0]
        seen = set()
        for v in sorted(by_frame_dir.get(stem, []), key=lambda v: v["path"]):
            flags, _, _ = dossiers.classify(v)
            if set(flags) & {"badge", "secret", "contact"}:
                continue
            new = [b for b in dossiers.big_lines(v) if b.lower() not in seen]
            seen.update(b.lower() for b in new)
            if new:
                vt[m["session"]].append(f"- [{stem} {Path(v['path']).stem}] " + " | ".join(new))
        t = c.layout.transcripts_dir / f"{stem}.txt"
        if t.exists() and t.read_text().strip():
            tr[m["session"]].append((stem, " ".join(t.read_text().split())))
    return vt, tr


def cmd_dossiers(c, a):
    lay = c.layout
    vis = vision.load(lay.vision_jsonl)
    idx = _index_by_stem(takeout_index.read_index(lay.candidates_csv))
    s = json.loads(lay.sessions_json.read_text())
    cal = json.loads(lay.calendar_json.read_text()) if lay.calendar_json.exists() else {}
    vt, tr = _video_context(c)
    owners = tuple(c.get("filters", "owner_people", []))
    n_event = 0
    for sess in s:
        md, data = dossiers.build(
            sess,
            vis,
            idx,
            cal.get(sess["id"]),
            vt.get(sess["id"]),
            tr.get(sess["id"]),
            c.get("dossiers", "max_timeline_lines", 150),
            owners,
        )
        dossiers.write(lay.dossier_dir, sess["id"], md, data)
        n_event += data["event_share"] >= c.get("dossiers", "event_share_min", 0.15)
    print(json.dumps({"dossiers": len(s), "event_like": n_event}))


def _event_ids(c) -> set[str]:
    thr = c.get("dossiers", "event_share_min", 0.15)
    out = set()
    for p in c.layout.dossier_dir.glob("*.json"):
        if json.loads(p.read_text()).get("event_share", 0) >= thr:
            out.add(p.stem)
    return out


def cmd_videos(c, a):
    lay = c.layout
    vids = takeout_index.read_index(lay.videos_csv)
    s = json.loads(lay.sessions_json.read_text())
    picked = videos.pick(vids, s, _event_ids(c))
    model, vad = c.path("video", "whisper_model"), c.path("video", "vad_model")
    all_frames = []
    for v in picked:
        path = videos.extract_video(v, lay.video_dir)
        v["duration"] = round(videos.duration(path))
        all_frames += videos.frames(
            path,
            lay.frames_dir,
            c.get("video", "frame_interval_s", 5),
            c.get("video", "dedupe_threshold", 6.0),
        )
        if v["duration"] >= c.get("video", "min_transcribe_s", 20):
            videos.transcribe(path, lay.transcripts_dir, model, vad)
    videos.save_manifest(lay.root, picked)
    res = vision.run(
        all_frames,
        lay.frames_vision_jsonl,
        c.get("vision", "chunk", 150),
        c.get("vision", "languages", "en-US"),
    )
    print(
        json.dumps(
            {
                "videos": len(picked),
                "frames": len(all_frames),
                **res,
                "transcripts": len(list(lay.transcripts_dir.glob("*.txt"))),
            }
        )
    )


def cmd_list(c, a):
    thr = c.get("dossiers", "event_share_min", 0.15)
    cal = json.loads(c.layout.calendar_json.read_text()) if c.layout.calendar_json.exists() else {}
    for p in sorted(c.layout.dossier_dir.glob("*.json")):
        d = json.loads(p.read_text())
        if d.get("event_share", 0) < thr:
            continue
        s = d["session"]
        hint = "; ".join(e["title"] for e in cal.get(s["id"], [])[:3])
        print(
            f"{s['id']}  {s['start']}→{s['end'][11:]}  n={s['n']:4d}  event={d['event_share']:.0%}  "
            f"pub={len(d['publishable']):3d}  {hint}"
        )


def cmd_sheet(c, a):
    print(
        sheet.make(
            c.layout.dossier_dir / f"{a.session}.json",
            c.layout.img_dir,
            c.layout.sheet_dir,
            a.mode,
            a.limit,
        )
    )


def cmd_export(c, a):
    lay = c.layout
    idx = _index_by_stem(takeout_index.read_index(lay.candidates_csv))
    repo = c.path("paths", "blog_repo")
    own = tuple(c.get("filters", "own_camera_prefixes", ["PXL_"]))
    ev_dir = repo / c.get("paths", "events_subdir", "static/blog/events") / a.slug
    for spec in a.items:
        title, name = spec.split("=", 1)
        size, kb = export_images.save(
            export_images.load(idx[title], lay.img_dir, own),
            ev_dir / f"{name}.jpg",
            c.get("export", "max_edge", 1280),
            c.get("export", "max_kb", 300),
        )
        print(f"{ev_dir / (name + '.jpg')} {size} {kb}KB")
    if a.thumb:
        im = export_images.thumbnail(
            export_images.load(idx[a.thumb], lay.img_dir, own),
            c.get("export", "thumb_width", 1200),
            c.get("export", "thumb_height", 630),
        )
        out = repo / c.get("paths", "thumbs_subdir", "static/blog/thumbnails") / f"{a.slug}.jpg"
        size, kb = export_images.save(im, out, max(im.size), c.get("export", "thumb_max_kb", 200))
        print(f"{out} {size} {kb}KB")


STEPS = {
    "index": cmd_index,
    "select": cmd_select,
    "extract": cmd_extract,
    "vision": cmd_vision,
    "sessions": cmd_sessions,
    "calendar": cmd_calendar,
    "dossiers": cmd_dossiers,
}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        prog="event_content",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--config", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in [*STEPS, "videos", "list", "all"]:
        sub.add_parser(name)
    sp = sub.add_parser("sheet")
    sp.add_argument("session")
    sp.add_argument("mode", nargs="?", default="pub", choices=["pub", "all"])
    sp.add_argument("limit", nargs="?", type=int, default=36)
    ep = sub.add_parser("export")
    ep.add_argument("slug")
    ep.add_argument("items", nargs="*", help="TITLE=name")
    ep.add_argument("--thumb")
    a = ap.parse_args(argv)
    c = cfgmod.load(a.config)
    if a.cmd == "all":
        for name, fn in STEPS.items():
            print(f"== {name}", flush=True)
            fn(c, a)
        return
    {**STEPS, "videos": cmd_videos, "list": cmd_list, "sheet": cmd_sheet, "export": cmd_export}[
        a.cmd
    ](c, a)


if __name__ == "__main__":
    main()

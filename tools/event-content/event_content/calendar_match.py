"""Attach calendar events that overlap each session (read-only on the calendar source).

Sources: the calendar-photo-organizer SQLite catalog (`calendar_events` table, filled by
`cpo calendar-import`) or a JSON list of events. Private/family items are filtered out by
keyword before anything is written. Calendar entries are RSVPs, not proof of attendance:
dossiers present them as hints to be confirmed by the photos.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path


def _ts(s: str) -> datetime:
    s = s.replace("Z", "+00:00")
    if len(s) == 10:  # all-day date
        s += "T00:00:00+00:00"
    return datetime.fromisoformat(s)


def load_events(cpo_db: Path | None, events_json: Path | None) -> list[dict]:
    events: list[dict] = []
    if cpo_db and cpo_db.is_file():
        con = sqlite3.connect(f"file:{cpo_db}?mode=ro", uri=True)  # read-only
        for title, desc, loc, s, e, allday in con.execute(
            "SELECT title, description, location, start_utc, end_utc, is_all_day FROM calendar_events"
        ):
            events.append(
                {
                    "title": title,
                    "description": desc or "",
                    "location": loc or "",
                    "start_utc": s,
                    "end_utc": e,
                    "all_day": bool(allday),
                }
            )
        con.close()
    if events_json and events_json.is_file():
        events += json.loads(events_json.read_text())
    return events


def is_private(ev: dict, keywords: list[str]) -> bool:
    text = f"{ev.get('title', '')} {ev.get('description', '')}".lower()
    return any(k.lower() in text for k in keywords)


def match(
    sessions: list[dict], events: list[dict], keywords: list[str], padding_minutes: int = 60
) -> dict:
    pad = timedelta(minutes=padding_minutes)
    clean = [e for e in events if not is_private(e, keywords)]
    out = {}
    for s in sessions:
        a, b = _ts(s["start_utc"]) - pad, _ts(s["end_utc"]) + pad
        hits = []
        for e in clean:
            es, ee = _ts(e["start_utc"]), _ts(e["end_utc"])
            if es <= b and ee >= a:
                desc = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", e.get("description", "")))
                hits.append(
                    {
                        "title": e["title"],
                        "start_utc": e["start_utc"],
                        "end_utc": e["end_utc"],
                        "location": e.get("location", "")[:120],
                        "all_day": e.get("all_day", False),
                        "description": desc[:300],
                    }
                )
        # Prefer timed events over multi-day all-day blocks, dedupe by title.
        seen, uniq = set(), []
        for h in sorted(hits, key=lambda h: (h["all_day"], h["start_utc"])):
            if h["title"].lower() not in seen:
                seen.add(h["title"].lower())
                uniq.append(h)
        out[s["id"]] = uniq
    return out

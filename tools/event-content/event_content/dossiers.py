"""Build one dossier per session: what the photos say, with privacy classification.

The dossier is the single source for writers: slide/sign text (largest text first,
chronological), decoded QR links, calendar hints, video-frame text, transcript snippets,
and the ranked list of publishable photos.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

BADGE = re.compile(
    r"\b(ATTENDEE|SPEAKER|SPONSOR|EXHIBITOR|STAFF|VOLUNTEER|PRESS|MEDIA|ORGANI[SZ]ER|CO-LOCATED)\b",
    re.I,
)
SECRET = re.compile(r"(pass ?word|wachtwoord|wifi|wi-fi|ssid|login|\bpin\b|iban)", re.I)
CONTACT = re.compile(
    r"(linkedin\.com/in/|[\w.+-]+@[\w-]+\.[\w.]+|connect with me|let'?s connect)", re.I
)
EVENT_LABELS = {
    "crowd",
    "conference",
    "presentation",
    "stage",
    "auditorium",
    "classroom",
    "theater",
    "screen",
    "projector",
    "display",
    "monitor",
    "sign",
    "banner",
    "poster",
    "microphone",
    "lectern",
    "podium",
}


def big_lines(v: dict, k: int = 6) -> list[str]:
    """Largest text first: slide titles, banners, signs."""
    ls = [ln for ln in v.get("lines", []) if ln["c"] >= 0.5 and len(ln["t"].strip()) >= 3]
    ls.sort(key=lambda ln: -ln["h"])
    seen, out = set(), []
    for ln in ls:
        t = ln["t"].strip()
        if t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
        if len(out) >= k:
            break
    return out


def classify(v: dict, people: str = "", owners: tuple[str, ...] = ()) -> tuple[list[str], str, int]:
    """Return (flags, kind, eventness). kind=people means a third party may be in focus."""
    text = " ".join(ln["t"] for ln in v.get("lines", []))
    n_lines = len(v.get("lines", []))
    flags = []
    if BADGE.search(text) and n_lines < 25:
        flags.append("badge")
    if SECRET.search(text):
        flags.append("secret")
    if CONTACT.search(text):
        flags.append("contact")
    if v.get("codes") and n_lines <= 4:
        flags.append("qr-only")
    if v.get("utility"):
        flags.append("utility")
    tagged = [p for p in people.split(";") if p]
    owner_only = bool(tagged) and all(p in owners for p in tagged)
    faces, mf = v.get("faces", 0), v.get("maxFace", 0)
    if mf < 0.012:
        kind = "scene"
    elif owner_only and faces <= 2:
        kind = "selfie"
    elif faces >= 4 and mf < 0.03:
        kind = "crowd"
    else:
        kind = "people"
    eventness = sum(1 for k in v.get("labels", {}) if k in EVENT_LABELS) + (
        1 if n_lines >= 6 else 0
    )
    return flags, kind, eventness


def build(
    session: dict,
    vision: dict[str, dict],
    index: dict[str, dict],
    calendar: list[dict] | None = None,
    video_text: list[str] | None = None,
    transcripts: list[tuple[str, str]] | None = None,
    max_timeline: int = 150,
    owners: tuple[str, ...] = (),
) -> tuple[str, dict]:
    photos = []
    for t in session["titles"]:
        v, r = vision.get(t), index.get(t)
        if not v or not r:
            continue
        flags, kind, ev = classify(v, r.get("people", ""), owners)
        photos.append(
            {
                "title": t,
                "utc": r["utc"],
                "kind": kind,
                "flags": flags,
                "event": ev,
                "aes": round(v.get("aesthetic") or 0, 3),
                "faces": v.get("faces", 0),
                "big": big_lines(v),
                "codes": v.get("codes", []),
                "labels": sorted(v.get("labels", {}), key=lambda k: -v["labels"][k])[:5],
            }
        )
    pub = sorted(
        (p for p in photos if p["kind"] != "people" and not p["flags"]),
        key=lambda p: -(p["aes"] + 0.15 * min(p["event"], 3)),
    )
    share = (sum(1 for p in photos if p["event"] >= 2) / len(photos)) if photos else 0.0
    codes = sorted(
        {c for p in photos for c in p["codes"] if not set(p["flags"]) & {"badge", "contact"}}
    )
    timeline, seen = [], set()
    for p in sorted(photos, key=lambda p: p["utc"]):
        if set(p["flags"]) & {"badge", "secret", "contact"}:
            continue
        new = [b for b in p["big"] if b.lower() not in seen]
        seen.update(b.lower() for b in new)
        if new:
            timeline.append(f"- {p['utc'][11:16]}Z [{p['title']}] " + " | ".join(new))
    md = [
        f"# Session {session['id']}: {session['start']} → {session['end'][11:]} local, {len(photos)} analysed photos",
        f"GPS centroid (internal, NEVER publish): {session['lat']},{session['lon']}",
        f"Event-likeness: {share:.0%} | publishable: {len(pub)} | excluded: "
        f"{sum(p['kind'] == 'people' for p in photos)} people-in-focus, "
        + ", ".join(
            f"{sum(f in p['flags'] for p in photos)} {f}"
            for f in ("badge", "secret", "contact", "qr-only", "utility")
        ),
        "",
        "## Calendar hints (RSVPs — confirm with the photos)",
    ]
    md += [
        f"- {e['start_utc'][:16]}-{e['end_utc'][11:16]} | {e['title']} | {e['location']} | {e['description'][:200]}"
        for e in (calendar or [])
    ] or ["- none"]
    md += [
        "",
        "## QR / links decoded (verify before linking; never personal profiles)",
        *(f"- {c}" for c in codes[:30]),
        "",
        "## Text seen in photos (largest first, chronological, UTC)",
        *timeline[:max_timeline],
    ]
    if video_text:
        md += ["", "## Text seen in video frames", *video_text[:80]]
    if transcripts:
        md += [
            "",
            "## Transcript excerpts (use ONLY if clearly a stage talk; never private conversations)",
        ]
        md += [f"- [{name}] {text[:600]}" for name, text in transcripts[:20]]
    md += [
        "",
        "## Top publishable photos (aesthetic + event score)",
        *(
            f"- {p['title']} {p['utc'][11:16]}Z {p['kind']} aes={p['aes']} labels={','.join(p['labels'])} "
            f"text={' | '.join(p['big'][:2])}"
            for p in pub[:25]
        ),
    ]
    data = {"session": session, "event_share": share, "publishable": pub, "all": photos}
    return "\n".join(md) + "\n", data


def write(out_dir: Path, sid: str, md: str, data: dict) -> None:
    (out_dir / f"{sid}.md").write_text(md)
    (out_dir / f"{sid}.json").write_text(json.dumps(data))

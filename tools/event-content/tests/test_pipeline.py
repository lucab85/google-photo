"""Unit tests for the non-trivial logic: indexing, privacy filters, sessions, calendar, classification, export."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from event_content import calendar_match, dossiers, export_images, select, sessions, takeout_index
from PIL import Image

FILTERS = {
    "own_camera_prefixes": ["PXL_"],
    "exclude_title_substrings": ["-WA", "Screenshot"],
    "exclude_albums": ["Family"],
    "exclude_people_substrings": ["grandma"],
    "image_extensions": [".jpg"],
    "video_extensions": [".mp4"],
}


def _jpeg(exif_gps: bool = False) -> bytes:
    im = Image.new("RGB", (3000, 2000), (120, 30, 200))
    buf = io.BytesIO()
    if exif_gps:
        ex = Image.Exif()
        ex[0x010F] = "TestCam"  # Make
        im.save(buf, "JPEG", exif=ex.tobytes())
    else:
        im.save(buf, "JPEG")
    return buf.getvalue()


def _sidecar(
    title: str, ts: int, lat: float = 52.37, lon: float = 4.89, people: list[str] | None = None
) -> bytes:
    return json.dumps(
        {
            "title": title,
            "photoTakenTime": {"timestamp": str(ts)},
            "geoData": {"latitude": lat, "longitude": lon},
            "people": [{"name": p} for p in (people or [])],
        }
    ).encode()


def _takeout(tmp: Path) -> list[Path]:
    """Two parts: the sidecar for one photo lives in part 1, its media in part 2."""
    base = "Takeout/Google Photos/Photos from 2026/"
    p1, p2 = tmp / "takeout-001.zip", tmp / "takeout-002.zip"
    with zipfile.ZipFile(p1, "w") as z:
        z.writestr(
            base + "PXL_20260323_120000000.jpg.supplemental-metadata.json",
            _sidecar("PXL_20260323_120000000.jpg", 1774267200),
        )
        z.writestr(
            base + "PXL_20260323_120500000.jpg.supplemental-metadata.json",
            _sidecar("PXL_20260323_120500000.jpg", 1774267500),
        )
        z.writestr(base + "PXL_20260323_120000000.jpg", _jpeg(exif_gps=True))
        z.writestr(base + "metadata.json", b"{}")
    with zipfile.ZipFile(p2, "w") as z:
        z.writestr(base + "PXL_20260323_120500000.jpg", _jpeg())
        z.writestr(
            "Takeout/Google Photos/Photos from 2026/IMG-20260323-WA0001.jpg.supplemental-metadata.json",
            _sidecar("IMG-20260323-WA0001.jpg", 1774267600),
        )
        z.writestr("Takeout/Google Photos/Photos from 2026/IMG-20260323-WA0001.jpg", _jpeg())
    return [p1, p2]


def test_index_resolves_media_across_parts(tmp_path):
    zips = _takeout(tmp_path)
    stats = takeout_index.build_index(zips, tmp_path / "index.csv")
    rows = takeout_index.read_index(tmp_path / "index.csv")
    assert stats["items"] == 3 and stats["media_present"] == 3
    second = next(r for r in rows if r["title"] == "PXL_20260323_120500000.jpg")
    assert second["zip"].endswith("takeout-002.zip")
    assert rows == sorted(rows, key=lambda r: r["utc"])


def test_select_privacy_rules():
    base = {
        "utc": "2026-03-23T12:00:00Z",
        "media_path": "x",
        "album": "Photos from 2026",
        "people": "",
    }
    assert select.classify({**base, "title": "PXL_1.jpg"}, FILTERS) == "image"
    assert select.classify({**base, "title": "PXL_1.mp4"}, FILTERS) == "video"
    assert select.classify({**base, "title": "IMG-20260323-WA0001.jpg"}, FILTERS).startswith(
        "not own camera"
    )
    assert (
        select.classify({**base, "title": "PXL_1.jpg", "album": "Family"}, FILTERS)
        == "private album"
    )
    assert (
        select.classify({**base, "title": "PXL_1.jpg", "people": "Grandma"}, FILTERS)
        == "private people tag"
    )
    assert (
        select.classify({**base, "title": "PXL_1.jpg", "media_path": ""}, FILTERS)
        == "media not in available zips"
    )
    assert (
        select.classify({**base, "title": "PXL_1.jpg"}, {**FILTERS, "since": "2026-04-01"})
        == "outside date range"
    )


def test_sessions_split_on_gap_and_local_time():
    rows = [
        {
            "utc": f"2026-03-23T{h:02d}:{m:02d}:00Z",
            "lat": "52.3",
            "lon": "4.9",
            "title": f"PXL_{h}{m}.jpg",
        }
        for h, m in [(12, 0), (12, 10), (12, 20), (15, 0), (15, 5), (15, 10)]
    ]
    s = sessions.build(rows, gap_minutes=90, min_photos=3)
    assert [x["n"] for x in s] == [3, 3]
    assert s[0]["start"] == "2026-03-23 13:00"  # CET (UTC+1) before the 29 Mar DST switch


def test_local_time_uses_longitude_outside_europe():
    lt = sessions.to_local("2026-01-01T12:00:00Z", lon="102.3")  # ~UTC+7
    assert lt.hour == 19


def test_calendar_match_filters_private_and_overlaps():
    s = [{"id": "S1", "start_utc": "2026-03-23T12:00:00Z", "end_utc": "2026-03-23T14:00:00Z"}]
    evs = [
        {
            "title": "KubeCon EU",
            "start_utc": "2026-03-23T08:00:00Z",
            "end_utc": "2026-03-23T17:00:00Z",
            "location": "RAI",
        },
        {
            "title": "Family call",
            "start_utc": "2026-03-23T12:30:00Z",
            "end_utc": "2026-03-23T13:00:00Z",
        },
        {
            "title": "Other day",
            "start_utc": "2026-03-25T12:00:00Z",
            "end_utc": "2026-03-25T13:00:00Z",
        },
    ]
    m = calendar_match.match(s, evs, ["family call"], padding_minutes=30)
    assert [e["title"] for e in m["S1"]] == ["KubeCon EU"]


def _v(lines=(), faces=0, max_face=0.0, codes=(), labels=None, utility=False):
    return {
        "lines": [{"t": t, "c": 0.9, "x": 0, "y": 0, "w": 0.5, "h": h} for t, h in lines],
        "faces": faces,
        "maxFace": max_face,
        "codes": list(codes),
        "labels": labels or {},
        "utility": utility,
    }


def test_classify_flags_and_kinds():
    assert "badge" in dossiers.classify(_v([("JANE DOE", 0.1), ("ATTENDEE", 0.05)]))[0]
    assert "secret" in dossiers.classify(_v([("WiFi password: hunter2", 0.1)]))[0]
    assert (
        "contact"
        in dossiers.classify(_v([("connect with me", 0.1), ("jane@example.com", 0.05)]))[0]
    )
    assert "qr-only" in dossiers.classify(_v(codes=["https://x"]))[0]
    assert dossiers.classify(_v(faces=0))[1] == "scene"
    assert (
        dossiers.classify(_v(faces=1, max_face=0.05), "Luca Berton", ("Luca Berton",))[1]
        == "selfie"
    )
    assert (
        dossiers.classify(_v(faces=1, max_face=0.05), "Someone Else", ("Luca Berton",))[1]
        == "people"
    )
    assert dossiers.classify(_v(faces=8, max_face=0.02))[1] == "crowd"


def test_dossier_hides_badge_text_and_keeps_slide_text():
    sess = {
        "id": "S1",
        "start": "2026-03-23 13:00",
        "end": "2026-03-23 14:00",
        "lat": 1,
        "lon": 2,
        "titles": ["PXL_a", "PXL_b"],
    }
    vis = {
        "PXL_a": _v([("Scaling Argo CD", 0.2)], labels={"screen": 0.9, "crowd": 0.8}),
        "PXL_b": _v([("JANE DOE", 0.1), ("SPEAKER", 0.05)]),
    }
    idx = {
        "PXL_a": {"utc": "2026-03-23T12:00:00Z", "people": ""},
        "PXL_b": {"utc": "2026-03-23T12:05:00Z", "people": ""},
    }
    md, data = dossiers.build(sess, vis, idx)
    assert "Scaling Argo CD" in md and "JANE DOE" not in md
    assert [p["title"] for p in data["publishable"]] == ["PXL_a"]


def test_export_strips_exif_and_caps_size(tmp_path):
    im = Image.open(io.BytesIO(_jpeg(exif_gps=True)))
    assert im.info.get("exif")
    _size, kb = export_images.save(im, tmp_path / "out.jpg", max_edge=1280, max_kb=300)
    out = Image.open(tmp_path / "out.jpg")
    assert max(out.size) == 1280 and kb <= 300 and not out.info.get("exif")
    th = export_images.thumbnail(im, 1200, 630)
    assert th.size == (1200, 630)


def test_export_rejects_non_own_camera(tmp_path):
    try:
        export_images.load(
            {"title": "IMG-20260323-WA0001.jpg", "zip": "", "media_path": ""}, tmp_path, ("PXL_",)
        )
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_export_falls_back_to_analysis_copy_when_zip_is_gone(tmp_path):
    Image.new("RGB", (2100, 1400), (10, 20, 30)).save(tmp_path / "PXL_20260323_120000000.jpg")
    row = {
        "title": "PXL_20260323_120000000.jpg",
        "zip": str(tmp_path / "gone.zip"),
        "media_path": "x",
    }
    im = export_images.load(row, tmp_path, ("PXL_",))
    assert im.size == (2100, 1400)

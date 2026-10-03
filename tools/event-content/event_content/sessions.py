"""Group photos into sessions: bursts in local time separated by long gaps."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo


def to_local(utc: str, lon: str | float | None, tz: str = "Europe/Amsterdam") -> datetime:
    """Local wall-clock time. Uses the configured zone near it, else a longitude-based offset."""
    t = datetime.strptime(utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    if lon not in (None, "") and not (-10 < float(lon) < 30):
        return (t + timedelta(hours=round(float(lon) / 15))).replace(tzinfo=None)
    return t.astimezone(ZoneInfo(tz)).replace(tzinfo=None)


def build(
    rows: list[dict], gap_minutes: int = 90, min_photos: int = 6, tz: str = "Europe/Amsterdam"
) -> list[dict]:
    items = sorted(((to_local(r["utc"], r.get("lon"), tz), r) for r in rows), key=lambda x: x[0])
    groups: list[list[tuple[datetime, dict]]] = []
    for lt, r in items:
        if groups and lt - groups[-1][-1][0] <= timedelta(minutes=gap_minutes):
            groups[-1].append((lt, r))
        else:
            groups.append([(lt, r)])
    out = []
    for g in groups:
        if len(g) < min_photos:
            continue
        gps = [(float(r["lat"]), float(r["lon"])) for _, r in g if r.get("lat")]
        start, end = g[0][0], g[-1][0]
        out.append(
            {
                "id": f"S{start:%Y%m%d%H%M}",
                "start": f"{start:%Y-%m-%d %H:%M}",
                "end": f"{end:%Y-%m-%d %H:%M}",
                "start_utc": g[0][1]["utc"],
                "end_utc": g[-1][1]["utc"],
                "n": len(g),
                "lat": round(sum(a for a, _ in gps) / len(gps), 4) if gps else None,
                "lon": round(sum(b for _, b in gps) / len(gps), 4) if gps else None,
                "titles": [r["title"].rsplit(".", 1)[0] for _, r in g],
            }
        )
    return out

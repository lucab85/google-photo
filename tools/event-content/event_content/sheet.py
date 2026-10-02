"""Contact sheets so a human (or an agent) can review a session at a glance."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw


def make(
    dossier_json: Path, img_dir: Path, out_dir: Path, mode: str = "pub", limit: int = 36
) -> Path:
    d = json.loads(dossier_json.read_text())
    ps = d["publishable"] if mode == "pub" else sorted(d["all"], key=lambda p: p["utc"])
    ps = ps[:limit]
    w, h, cols = 330, 350, 6
    sheet = Image.new("RGB", (cols * w, max(1, (len(ps) + cols - 1) // cols) * h), "white")
    rows = []
    for i, p in enumerate(ps):
        src = img_dir / f"{p['title']}.jpg"
        if not src.exists():
            continue
        im = Image.open(src)
        im.thumbnail((w, w - 20))
        tile = Image.new("RGB", (w, h), "white")
        tile.paste(im, ((w - im.width) // 2, 0))
        ImageDraw.Draw(tile).text(
            (3, h - 18), f"{i:02d} {p['utc'][11:16]}Z {p['kind']} {p['aes']}", fill="black"
        )
        sheet.paste(tile, ((i % cols) * w, (i // cols) * h))
        rows.append(f"{i:02d}\t{p['title']}\t{p['utc']}\t{p['kind']}\t{' | '.join(p['big'][:3])}")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{dossier_json.stem}-{mode}.jpg"
    sheet.save(out, quality=78)
    out.with_suffix(".tsv").write_text("\n".join(rows) + "\n")
    return out

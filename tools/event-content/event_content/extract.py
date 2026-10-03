"""Write analysis-sized JPEG copies of candidate photos (originals are never modified)."""

from __future__ import annotations

import io
import os
import zipfile
from collections import defaultdict
from multiprocessing import Pool
from pathlib import Path

from PIL import Image, ImageOps


def stem(title: str) -> str:
    return title.rsplit(".", 1)[0]


def _job(args: tuple[str, list[tuple[str, str]], str, int]) -> tuple[int, list[str]]:
    zp, items, out_dir, max_edge = args
    n, errors = 0, []
    with zipfile.ZipFile(zp) as z:
        for media_path, title in items:
            out = os.path.join(out_dir, stem(title) + ".jpg")
            if os.path.exists(out):
                continue
            try:
                im = Image.open(io.BytesIO(z.read(media_path)))
                im.draft("RGB", (max_edge, max_edge))
                im = ImageOps.exif_transpose(im).convert("RGB")
                im.thumbnail((max_edge, max_edge))
                im.save(out, "JPEG", quality=88)  # no exif= argument: metadata is dropped
                n += 1
            except Exception as e:  # corrupt or unsupported file: record and move on
                errors.append(f"{title}: {e}")
    return n, errors


def extract(
    rows: list[dict], out_dir: Path, max_edge: int = 2100, workers: int = 8
) -> tuple[int, list[str]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    by_zip: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for r in rows:
        by_zip[r["zip"]].append((r["media_path"], r["title"]))
    jobs = []
    for zp, items in by_zip.items():
        k = max(1, min(workers, len(items) // 50 or 1))
        jobs += [(zp, items[i::k], str(out_dir), max_edge) for i in range(k)]
    total, errs = 0, []
    with Pool(min(workers, len(jobs)) or 1) as p:
        for n, e in p.map(_job, jobs):
            total += n
            errs += e
    return total, errs

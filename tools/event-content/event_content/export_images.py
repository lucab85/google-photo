"""Export chosen photos as web images for the blog: resized, size-capped, EXIF/GPS stripped.

Reads the original from its zip when available, otherwise falls back to the analysis copy
(so exports keep working after a processed Takeout part has been removed from disk).
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from PIL import Image, ImageOps


def load(row: dict, img_dir: Path, own_prefixes: tuple[str, ...]) -> Image.Image:
    if not row["title"].startswith(own_prefixes):
        raise ValueError(f"{row['title']}: only own-camera photos may be exported")
    zp = Path(row.get("zip") or "")
    if zp.is_file():
        with zipfile.ZipFile(zp) as z:
            return ImageOps.exif_transpose(
                Image.open(io.BytesIO(z.read(row["media_path"])))
            ).convert("RGB")
    return Image.open(img_dir / f"{row['title'].rsplit('.', 1)[0]}.jpg").convert("RGB")


def save(im: Image.Image, path: Path, max_edge: int, max_kb: int) -> tuple[tuple[int, int], int]:
    im = im.copy()
    im.thumbnail((max_edge, max_edge), Image.LANCZOS)
    data = b""
    for q in range(85, 40, -5):
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=q, optimize=True, progressive=True)  # no exif => stripped
        data = buf.getvalue()
        if len(data) <= max_kb * 1024:
            break
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return im.size, len(data) // 1024


def thumbnail(im: Image.Image, w: int, h: int) -> Image.Image:
    iw, ih = im.size
    ch = int(iw * h / w)
    if ch > ih:
        cw = int(ih * w / h)
        x = (iw - cw) // 2
        im = im.crop((x, 0, x + cw, ih))
    else:
        y = (ih - ch) // 2
        im = im.crop((0, y, iw, y + ch))
    return im.resize((w, h), Image.LANCZOS)

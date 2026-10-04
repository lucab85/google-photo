"""Video pass for event sessions: frame text via Vision OCR, speech via whisper.cpp (all local).

Only own-camera videos recorded during event-like sessions are processed. Transcripts are
inputs for writers, never published verbatim; dossiers mark them as "stage talks only".
"""

from __future__ import annotations

import json
import shutil
import subprocess
import zipfile
from pathlib import Path

from PIL import Image, ImageChops, ImageStat


def pick(
    videos: list[dict], sessions: list[dict], event_ids: set[str], pad_s: int = 1800
) -> list[dict]:
    """Videos whose capture time falls inside (or within pad of) an event-like session."""
    from datetime import timedelta

    from .calendar_match import _ts

    wins = [
        (
            _ts(s["start_utc"]) - timedelta(seconds=pad_s),
            _ts(s["end_utc"]) + timedelta(seconds=pad_s),
            s["id"],
        )
        for s in sessions
        if s["id"] in event_ids
    ]
    out = []
    for v in videos:
        t = _ts(v["utc"])
        sid = next((i for a, b, i in wins if a <= t <= b), None)
        if sid:
            out.append({**v, "session": sid})
    return out


def duration(path: Path) -> float:
    r = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def extract_video(v: dict, video_dir: Path) -> Path:
    out = video_dir / v["title"]
    if not out.exists():
        with zipfile.ZipFile(v["zip"]) as z, z.open(v["media_path"]) as src, open(out, "wb") as dst:
            shutil.copyfileobj(src, dst)
    return out


def frames(
    video: Path, frames_dir: Path, interval_s: int = 5, threshold: float = 6.0
) -> list[Path]:
    od = frames_dir / video.stem
    if not od.is_dir():
        od.mkdir(parents=True)
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                str(video),
                "-vf",
                f"fps=1/{interval_s},scale=1920:-2",
                "-q:v",
                "3",
                str(od / "f%04d.jpg"),
            ],
            check=False,
            stderr=subprocess.DEVNULL,
        )
        prev = None
        for f in sorted(od.glob("f*.jpg")):  # drop near-identical consecutive frames
            im = Image.open(f).convert("L").resize((64, 36))
            if (
                prev is not None
                and ImageStat.Stat(ImageChops.difference(im, prev)).mean[0] < threshold
            ):
                f.unlink()
                continue
            prev = im
    return sorted(od.glob("f*.jpg"))


def detected_language(base: Path) -> str | None:
    """Language whisper-cli reported in its JSON output (result.language), if any."""
    try:
        data = json.loads(Path(f"{base}.json").read_text())
    except (OSError, ValueError):
        return None
    return (data.get("result") or {}).get("language")


def transcribe(
    video: Path,
    out_dir: Path,
    model: Path,
    vad: Path | None,
    languages: tuple[str, ...] = ("en", "it", "nl"),
    force: str | None = None,
) -> Path | None:
    """Transcribe with language auto-detection. On noisy audio whisper often "detects" Latin,
    Welsh or Slovenian and returns gibberish, so if the detected language is not one of
    `languages`, run again forced to the first of them. `force` skips detection (re-runs)."""
    # Pixel names carry a second suffix (PXL_….TS.mp4); with_suffix() would drop ".TS".
    base = out_dir / video.stem
    txt, wav = Path(f"{base}.txt"), Path(f"{base}.wav")
    if txt.exists() and not force:
        return txt
    if not shutil.which("whisper-cli") or not model.is_file():
        return None
    audio = subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(video), "-ac", "1", "-ar", "16000", str(wav)],
        check=False,
    )
    if audio.returncode != 0 or not wav.is_file():
        # No usable audio track (e.g. Google Photos "RESTORED" clips): mark as done with an
        # empty transcript so later runs don't extract the video again.
        wav.unlink(missing_ok=True)
        txt.write_text("")
        return txt
    def run(lang: str) -> None:
        cmd = ["whisper-cli", "-m", str(model), "-l", lang, "-oj", "-otxt", "-of", str(base), "-f", str(wav)]
        if vad and vad.is_file():
            cmd[1:1] = ["--vad", "--vad-model", str(vad)]
        with open(out_dir / "whisper.err", "a") as err:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=err, check=False)

    run(force or "auto")
    if not force and languages and detected_language(base) not in languages:
        run(languages[0])
    wav.unlink(missing_ok=True)
    return txt if txt.exists() else None


def manifest_path(work: Path) -> Path:
    return work / "videos.json"


def save_manifest(work: Path, items: list[dict]) -> None:
    manifest_path(work).write_text(json.dumps(items, indent=1))


def load_manifest(work: Path) -> list[dict]:
    p = manifest_path(work)
    return json.loads(p.read_text()) if p.exists() else []

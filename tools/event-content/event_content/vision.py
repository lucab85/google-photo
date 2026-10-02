"""Run the Swift `vanalyze` binary over images, in chunks, with resume.

Long single runs of DispatchQueue.concurrentPerform were observed to silently drop part of
their output, so we feed fixed-size chunks and skip anything already present in the JSONL.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

VANALYZE = Path(__file__).resolve().parent.parent / "vision" / "vanalyze"


def done_paths(jsonl: Path) -> set[str]:
    if not jsonl.exists():
        return set()
    out = set()
    with open(jsonl) as fh:
        for line in fh:
            try:
                out.add(json.loads(line)["path"])
            except (ValueError, KeyError):
                continue
    return out


def run(images: list[Path], jsonl: Path, chunk: int = 150, languages: str = "en-US") -> dict:
    if not VANALYZE.exists():
        raise SystemExit(f"{VANALYZE} missing: run vision/build.sh first")
    todo = [str(p) for p in images if str(p) not in done_paths(jsonl)]
    env = {**os.environ, "VANALYZE_LANGS": languages}
    for i in range(0, len(todo), chunk):
        batch = "\n".join(todo[i : i + chunk]) + "\n"
        with open(jsonl, "a") as out:
            subprocess.run([str(VANALYZE)], input=batch, text=True, stdout=out, env=env, check=True)
    missing = [p for p in todo if p not in done_paths(jsonl)]
    if missing:  # one retry for anything still missing
        with open(jsonl, "a") as out:
            subprocess.run(
                [str(VANALYZE)],
                input="\n".join(missing) + "\n",
                text=True,
                stdout=out,
                env=env,
                check=True,
            )
    final = done_paths(jsonl)
    return {
        "requested": len(images),
        "analysed_now": len(todo),
        "still_missing": sum(1 for p in images if str(p) not in final),
    }


def load(jsonl: Path) -> dict[str, dict]:
    """Map image stem -> vision result."""
    res = {}
    if jsonl.exists():
        with open(jsonl) as fh:
            for line in fh:
                try:
                    v = json.loads(line)
                except ValueError:
                    continue
                res[Path(v["path"]).stem] = v
    return res

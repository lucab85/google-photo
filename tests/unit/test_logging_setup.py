"""T010 — structlog setup + 'no print() outside cli.py' sweep."""

from __future__ import annotations

import io
import json
import re
from pathlib import Path

import structlog

from calendar_photo_organizer.logging_setup import bind_job_id, configure_logging


def test_job_id_appears_in_json_output() -> None:
    buf = io.StringIO()
    configure_logging(json_output=True, stream=buf)
    bind_job_id("job-123")
    structlog.get_logger("test").info("hello", k="v")
    line = buf.getvalue().strip().splitlines()[-1]
    rec = json.loads(line)
    assert rec["job_id"] == "job-123"
    assert rec["event"] == "hello"
    assert rec["k"] == "v"


def test_no_print_outside_cli() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "calendar_photo_organizer"
    offenders: list[str] = []
    pattern = re.compile(r"\bprint\s*\(")
    for path in root.rglob("*.py"):
        if path.name == "cli.py":
            continue
        text = path.read_text(encoding="utf-8")
        # Strip line comments to allow `# print(` in docs
        stripped = "\n".join(line.split("#", 1)[0] for line in text.splitlines())
        if pattern.search(stripped):
            offenders.append(str(path.relative_to(root)))
    assert offenders == [], f"print() found outside cli.py: {offenders}"

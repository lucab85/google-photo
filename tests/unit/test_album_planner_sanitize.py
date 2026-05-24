"""T015 — sanitize_folder_name property tests."""

from __future__ import annotations

import re

from hypothesis import given, settings
from hypothesis import strategies as st

from calendar_photo_organizer.album_planner import sanitize_folder_name

ALLOWED = re.compile(r"^[\w \-\u2013_.()\u00C0-\u017F]+$", re.UNICODE)
RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


@given(st.text(min_size=1, max_size=300))
@settings(max_examples=200, deadline=None)
def test_only_allowed_chars(s: str) -> None:
    out = sanitize_folder_name(s)
    if out:
        assert ALLOWED.fullmatch(out), f"disallowed chars in: {out!r}"


@given(st.text(min_size=1, max_size=300))
@settings(max_examples=200, deadline=None)
def test_no_trailing_dot_or_space(s: str) -> None:
    out = sanitize_folder_name(s)
    if out:
        assert not out.endswith((".", " "))


@given(st.text(min_size=1, max_size=400))
@settings(max_examples=200, deadline=None)
def test_max_length(s: str) -> None:
    assert len(sanitize_folder_name(s, max_len=120)) <= 120


def test_reserved_windows_names_prefixed() -> None:
    for name in ("CON", "PRN", "COM1", "LPT3"):
        assert sanitize_folder_name(name).startswith("_")


def test_date_prefix_preserved_on_truncation() -> None:
    name = "2024-07-04 \u2013 " + "x" * 500
    out = sanitize_folder_name(name, max_len=40)
    assert out.startswith("2024-07-04 \u2013 ")
    assert len(out) <= 40


def test_empty_falls_back_to_untitled() -> None:
    assert sanitize_folder_name("") == "Untitled"
    assert sanitize_folder_name("    ") == "Untitled"

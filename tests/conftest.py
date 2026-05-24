"""Shared pytest fixtures."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """A throwaway data directory laid out like the real one."""
    (tmp_path / "auth").mkdir()
    (tmp_path / "thumbs").mkdir()
    (tmp_path / "picker-cache").mkdir()
    (tmp_path / "dry-runs").mkdir()
    return tmp_path


@pytest.fixture
def mem_conn() -> Iterator[sqlite3.Connection]:
    """In-memory SQLite connection with the project's pragmas applied."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def fixture_root() -> Path:
    return Path(__file__).parent / "fixtures"

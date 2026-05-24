"""Structured logging setup using ``structlog``.

Every long-running operation binds a ``job_id`` via :func:`bind_job_id` so the
identifier appears on every emitted line. The ``print`` builtin is forbidden everywhere
except :mod:`calendar_photo_organizer.cli` (enforced by the ``no-print-outside-cli``
pre-commit hook and by ``tests/unit/test_logging_setup.py``).
"""

from __future__ import annotations

import logging
import sys
from collections.abc import MutableMapping
from contextvars import ContextVar
from typing import Any, TextIO

import structlog

_job_id_var: ContextVar[str | None] = ContextVar("job_id", default=None)


def _add_job_id(_: Any, __: str, event_dict: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    jid = _job_id_var.get()
    if jid is not None:
        event_dict.setdefault("job_id", jid)
    return event_dict


def bind_job_id(job_id: str | None) -> None:
    """Bind a job identifier visible to every subsequent log line in this context."""
    _job_id_var.set(job_id)


def configure_logging(*, json_output: bool = False, stream: TextIO | None = None) -> None:
    """Idempotent global configuration of the logging pipeline.

    Parameters
    ----------
    json_output:
        ``True`` produces one JSON object per line; ``False`` produces a
        compact key=value rendering.
    stream:
        Override the destination stream (used in tests).
    """
    target: TextIO = stream if stream is not None else sys.stderr

    renderer: Any = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer(colors=False)
    )

    structlog.configure(
        cache_logger_on_first_use=False,
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _add_job_id,
            renderer,
        ],
        logger_factory=structlog.PrintLoggerFactory(file=target),
    )

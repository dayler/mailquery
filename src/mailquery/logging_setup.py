"""Logging setup: plain text, daily rotation, never in ``stdout``.

``stdout`` is reserved for the JSON contract; every diagnostic goes to
``~/.mailquery/logs/mailquery.log`` (PRD 14). The format is log4j-like and
includes the ``run=`` correlation id so a harness call can be traced.
"""

from __future__ import annotations

import logging
import os
import uuid
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

LOG_FORMAT = "%(asctime)s.%(msecs)03d %(levelname)-5s %(name)s run=%(run_id)s %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

LEVELS: dict[str, int] = {
    "error": logging.ERROR,
    "warning": logging.WARNING,
    "info": logging.INFO,
    "debug": logging.DEBUG,
}

_current_run_id: str = "-"

# A NullHandler keeps library-style usage (and the test suite) from leaking
# warnings to ``stderr`` through logging's last-resort handler. The CLI replaces
# it with the rotating file handler via ``setup_logging``.
logging.getLogger("mailquery").addHandler(logging.NullHandler())


def _close_handlers(logger: logging.Logger) -> None:
    """Remove and close every handler so repeated runs do not leak fds."""
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        try:
            handler.close()
        except (OSError, ValueError):  # pragma: no cover - best effort cleanup
            pass


def setup_logging(home: Path, level: str = "info", retention_days: int = 7) -> str:
    """Configure the ``mailquery`` logger and return the run id.

    The log directory is created with mode 0700 and the log file with mode
    0600. Rotation happens at local midnight and keeps ``retention_days``
    backups.
    """
    global _current_run_id

    log_dir = Path(home) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    _chmod_dir(log_dir)
    log_path = log_dir / "mailquery.log"

    logger = logging.getLogger("mailquery")
    _close_handlers(logger)
    logger.setLevel(LEVELS.get(level, logging.INFO))
    logger.propagate = False

    handler = TimedRotatingFileHandler(
        log_path,
        when="midnight",
        backupCount=int(retention_days),
        encoding="utf-8",
        delay=False,
        utc=False,
    )
    handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    logger.addHandler(handler)

    try:
        os.chmod(log_path, 0o600)
    except OSError:  # pragma: no cover - best effort on foreign filesystems
        pass

    _current_run_id = uuid.uuid4().hex[:12]
    logger.debug("logging initialized level=%s retention_days=%s", level, retention_days)
    return _current_run_id


def current_run_id() -> str:
    return _current_run_id


def get_logger(name: str = "mailquery") -> logging.LoggerAdapter:
    """Return a logger adapter carrying the current run correlation id."""
    return logging.LoggerAdapter(logging.getLogger(name), {"run_id": _current_run_id})


def _chmod_dir(path: Path) -> None:
    try:
        os.chmod(path, 0o700)
    except OSError:  # pragma: no cover - best effort on foreign filesystems
        pass

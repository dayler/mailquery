"""Logging setup: plain text, rotation by size, never in ``stdout``.

``stdout`` is reserved for the JSON contract; every diagnostic goes to
``~/.mailquery/logs/mailquery.log``. The format is log4j-like and
includes the ``run=`` correlation id so a harness call can be traced.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

# ``asctime`` without a date format renders ``YYYY-MM-DD HH:MM:SS,mmm``.
LOG_FORMAT = "%(asctime)s %(levelname)-5s %(name)s run=%(run_id)s %(message)s"

BACKUP_COUNT = 5  # rotated files kept (fixed)
DEFAULT_MAX_SIZE_MB = 10

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


class _PrivateRotatingFileHandler(RotatingFileHandler):
    """Rotating handler whose current and rotated files are 0600 on POSIX."""

    def _open(self):  # noqa: D401 - logging.FileHandler hook
        stream = super()._open()
        try:
            os.chmod(self.baseFilename, 0o600)
        except OSError:  # pragma: no cover - best effort on foreign filesystems
            pass
        return stream


def setup_logging(home: Path, level: str = "info", max_size_mb: int = DEFAULT_MAX_SIZE_MB) -> str:
    """Configure the ``mailquery`` logger and return the run id.

    The log directory is created with mode 0700 and the log files with mode
    0600. The file rotates when it exceeds ``max_size_mb`` and keeps
    ``BACKUP_COUNT`` rotated files.
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

    handler = _PrivateRotatingFileHandler(
        log_path,
        maxBytes=int(max_size_mb) * 1024 * 1024,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
        delay=False,
    )
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logger.addHandler(handler)

    import uuid  # lazy: only needed once per run

    _current_run_id = uuid.uuid4().hex[:12]
    logger.debug("logging initialized level=%s max_size_mb=%s", level, max_size_mb)
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

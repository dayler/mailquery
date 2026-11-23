"""Logging setup: plain text or JSON Lines, rotation by size, never in ``stdout``.

``stdout`` is reserved for the JSON contract; every diagnostic goes to
``~/.mailquery/logs/mailquery.log`` or, when JSON Lines is enabled,
``~/.mailquery/logs/mailquery.jsonl``. The text format is log4j-like and
includes the ``run=`` correlation id so a harness call can be traced.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Sequence

# ``asctime`` without a date format renders ``YYYY-MM-DD HH:MM:SS,mmm``.
LOG_FORMAT = "%(asctime)s %(levelname)-5s %(name)s run=%(run_id)s %(message)s"

TEXT_LOG_FILENAME = "mailquery.log"
JSON_LOG_FILENAME = "mailquery.jsonl"

_DECIMAL_INTEGER = re.compile(r"-?\d+")
_KEY_VALUE_TEXT = re.compile(r"^([A-Za-z_][\w.-]*)=(.*)$", re.DOTALL)

BACKUP_COUNT = 5  # rotated files kept (fixed)
DEFAULT_MAX_SIZE_MB = 10

LEVELS: dict[str, int] = {
    "error": logging.ERROR,
    "warning": logging.WARNING,
    "info": logging.INFO,
    "debug": logging.DEBUG,
}

_current_run_id: str = "-"

#: Name of the log file the last applied configuration writes to.
_active_log_filename: str = TEXT_LOG_FILENAME

#: Record attribute that carries the structured event to formatters.
_EVENT_EXTRA_KEY = "mailquery_event"

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


def active_log_filename() -> str:
    """Name of the log file the current configuration writes to.

    It is ``mailquery.jsonl`` when JSON Lines is enabled and ``mailquery.log``
    otherwise; before the first configuration it is ``mailquery.log``.
    """
    return _active_log_filename


def setup_logging(
    home: Path,
    level: str = "info",
    max_size_mb: int = DEFAULT_MAX_SIZE_MB,
    json: bool = False,
) -> str:
    """Configure the ``mailquery`` logger and return the run id.

    ``json`` selects ``mailquery.jsonl`` with one JSON object per line instead
    of the text ``mailquery.log``; the other file is never opened, rotated or
    removed. The log directory is created with mode 0700 and the log files with
    mode 0600. The active file rotates when it exceeds ``max_size_mb`` and
    keeps ``BACKUP_COUNT`` rotated files.
    """
    global _current_run_id, _active_log_filename

    log_dir = Path(home) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    _chmod_dir(log_dir)
    log_path = log_dir / (JSON_LOG_FILENAME if json else TEXT_LOG_FILENAME)

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
    handler.setFormatter(JsonFormatter() if json else logging.Formatter(LOG_FORMAT))
    logger.addHandler(handler)
    _active_log_filename = log_path.name

    import uuid  # lazy: only needed once per run

    _current_run_id = uuid.uuid4().hex[:12]
    log_event(
        get_logger("mailquery"),
        logging.DEBUG,
        (("level", level), ("max_size_mb", max_size_mb)),
        text="logging initialized",
    )
    return _current_run_id


def current_run_id() -> str:
    return _current_run_id


def _json_value(value: object) -> object:
    """JSON type of one event value: integer, boolean, ``null`` or text.

    A decimal integer, as an ``int`` or as text, becomes a number; ``true`` and
    ``false`` in any case become booleans; ``-`` becomes ``null``; every other
    value becomes text.
    """
    if isinstance(value, bool) or isinstance(value, int):
        return value
    if value is None:
        return None
    text = value if isinstance(value, str) else str(value)
    if text == "-":
        return None
    lowered = text.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    if _DECIMAL_INTEGER.fullmatch(text):
        return int(text)
    return text


def _field_value(key: str, value: object) -> object:
    """JSON value of one event field; ``message`` is always text."""
    if key == "message":
        return "" if value is None else str(value)
    return _json_value(value)


def _iso_local_timestamp(created: float) -> str:
    """Local ISO 8601 timestamp with milliseconds and offset."""
    return datetime.fromtimestamp(created).astimezone().isoformat(timespec="milliseconds")


class JsonFormatter(logging.Formatter):
    """One JSON object per line with the structured event of each record.

    ``fields`` keeps the ``key=value`` pairs of the event in its order; the
    free text goes to ``text`` when it is not itself a ``key=value`` pair, which
    then joins ``fields`` (the text line puts it before the other fields). A
    record without a structured event carries its formatted message in ``text``
    and leaves ``fields`` empty.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": _iso_local_timestamp(record.created),
            "level": record.levelname,
            "logger": record.name,
            "run": getattr(record, "run_id", _current_run_id),
        }
        event = getattr(record, _EVENT_EXTRA_KEY, None)
        fields: dict[str, object] = {}
        text: str | None = None
        traceback_text: str | None = None
        if isinstance(event, dict):
            raw_text = event.get("text")
            if raw_text is not None:
                match = _KEY_VALUE_TEXT.match(str(raw_text))
                if match:
                    fields[match.group(1)] = _field_value(match.group(1), match.group(2))
                else:
                    text = str(raw_text)
            for key, value in event.get("fields") or ():
                fields[str(key)] = _field_value(str(key), value)
            traceback_text = event.get("traceback")
        else:
            text = record.getMessage()
        if record.exc_info and not traceback_text:
            traceback_text = self.formatException(record.exc_info)
        payload["fields"] = fields
        if text is not None:
            payload["text"] = text
        if traceback_text:
            payload["traceback"] = str(traceback_text)
        return json.dumps(payload, ensure_ascii=False)


def get_logger(name: str = "mailquery") -> logging.LoggerAdapter:
    """Return a logger adapter carrying the current run correlation id."""
    return logging.LoggerAdapter(logging.getLogger(name), {"run_id": _current_run_id})


def log_event(
    logger: logging.Logger | logging.LoggerAdapter,
    level: int,
    fields: Sequence[tuple[str, object]] = (),
    *,
    text: str | None = None,
    traceback: str | None = None,
    exc_info: bool = False,
) -> None:
    """Log one structured event without changing its rendered text line.

    ``fields`` keeps every ``key=value`` pair in order; ``text`` is the free
    text that precedes them. Both travel to the formatter as record data, so
    the JSON formatter can read the event without parsing the text line. A
    logger adapter keeps its own extra values (the run id) and gains the event
    data; calling the adapter directly would replace one map with the other on
    the supported Python versions.
    """
    items = tuple((str(key), value) for key, value in fields)
    parts = [text] if text else []
    parts.extend(f"{key}={value}" for key, value in items)
    message = " ".join(parts)
    if traceback:
        message = f"{message}\n{traceback}" if message else traceback
    event = {"fields": items, "text": text, "traceback": traceback}
    if isinstance(logger, logging.LoggerAdapter):
        merged = dict(logger.extra or {})
        merged[_EVENT_EXTRA_KEY] = event
        logger.logger.log(level, message, extra=merged, exc_info=exc_info)
        return
    logger.log(level, message, extra={_EVENT_EXTRA_KEY: event}, exc_info=exc_info)


def _chmod_dir(path: Path) -> None:
    try:
        os.chmod(path, 0o700)
    except OSError:  # pragma: no cover - best effort on foreign filesystems
        pass

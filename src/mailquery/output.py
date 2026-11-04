"""Stable JSON output helpers.

All commands emit exactly one formatted JSON object on ``stdout``. These helpers
keep serialization deterministic, strip control characters from untrusted
message content (prompt-injection hygiene, PRD 16.3) and build 200-character
snippets.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone

# Fixed product values (PRD 15.6).
SNIPPET_CHARS = 200
SHOW_BODY_MAX_CHARS = 20_000

_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MULTI_SPACE = re.compile(r"[ \t\f\v]+")


def sanitize_text(text: str, *, max_chars: int | None = None) -> str:
    """Remove ANSI escapes and control characters from untrusted text.

    Newlines and tabs are preserved (they are meaningful in bodies); everything
    else in the C0/C1 control range is dropped. Optionally truncates to
    ``max_chars`` without adding an ellipsis.
    """
    if not text:
        return ""
    cleaned = _ANSI_ESCAPE.sub("", text)
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = _CONTROL_CHARS.sub("", cleaned)
    if max_chars is not None and len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars]
    return cleaned


def make_snippet(body_text: str, max_chars: int = SNIPPET_CHARS) -> str:
    """Return a single-line preview of a body, at most ``max_chars`` long.

    The truncation marker counts towards the limit (the snippet never exceeds
    the documented 200 characters).
    """
    text = sanitize_text(body_text)
    text = _MULTI_SPACE.sub(" ", text)
    text = " ".join(line.strip() for line in text.split("\n"))
    text = text.strip()
    if len(text) <= max_chars:
        return text
    if max_chars <= 1:
        return text[:max_chars]
    return text[: max_chars - 1].rstrip() + "\u2026"


def iso_timestamp(epoch_seconds: float | int | None) -> str | None:
    """Convert Unix seconds to local ISO 8601 (``2026-11-01T22:54:09-04:00``).

    ``None``, values <= 0 and values the platform cannot represent give ``None``.
    """
    if epoch_seconds is None:
        return None
    try:
        value = float(epoch_seconds)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    try:
        # Through an aware UTC value: a naive local conversion fails on Windows
        # for dates whose local time falls before 1970 (epoch 1 with UTC-4).
        moment = datetime.fromtimestamp(value, tz=timezone.utc).astimezone()
        return moment.isoformat(timespec="seconds")
    except (OverflowError, OSError, ValueError):
        # Unrepresentable on this platform (for example 1e20): null (PRD 17).
        return None


def now_iso() -> str:
    """Current local time as ISO 8601 with offset."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def dumps_json(payload: dict) -> str:
    """Serialize a payload as JSON: 2-space indent, one field per line, no ASCII escaping."""
    return json.dumps(payload, ensure_ascii=False, indent=2, separators=(",", ": "), sort_keys=False)


def configure_streams() -> None:
    """Force UTF-8 and LF on ``stdout``/``stderr`` (RF-32), also when piped on Windows."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", newline="\n")


def write_json(payload: dict) -> None:
    """Write one formatted JSON object to ``stdout`` followed by a single LF."""
    sys.stdout.write(dumps_json(payload))
    sys.stdout.write("\n")
    sys.stdout.flush()

"""Stable JSON output helpers.

All commands emit exactly one formatted JSON object on ``stdout``. These helpers
keep serialization deterministic, strip control characters from untrusted
message content (prompt-injection hygiene) and build 200-character
snippets. ``html_to_text`` is the common HTML to plain text conversion.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone, tzinfo
from html.parser import HTMLParser

# Fixed product values.
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


#: Tags whose text content is not part of the visible body.
_SKIP_TAGS = frozenset(
    {"head", "title", "script", "style", "noscript", "template", "svg", "math"}
)

#: Tags that visually separate text; they become whitespace before collapsing.
_BLOCK_TAGS = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "caption",
        "dd",
        "div",
        "dl",
        "dt",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
        "ul",
    }
)


def html_to_text(html: str) -> str:
    """Convert HTML to plain text using ``html.parser``.

    Script/style/head content is dropped, character references are decoded,
    block-level elements become whitespace and runs of whitespace collapse to a
    single space. The result is used for snippets and for ``--text`` search.
    """
    if not isinstance(html, str) or not html:
        return ""
    extractor = _HtmlTextExtractor()
    try:
        extractor.feed(html)
        extractor.close()
    except Exception:  # pragma: no cover - HTMLParser is tolerant; never crash
        pass
    return extractor.text()


class _HtmlTextExtractor(HTMLParser):
    """Collect visible text while dropping non-content elements."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag in _BLOCK_TAGS:
            self._chunks.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            if self._skip_depth:
                self._skip_depth -= 1
        elif tag in _BLOCK_TAGS:
            self._chunks.append(" ")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self._chunks.append(data)

    def text(self) -> str:
        return " ".join("".join(self._chunks).split())


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


#: Zone of :func:`iso_timestamp`; ``None`` is the system zone. Test seam only: on
#: Windows there is no ``TZ``/``tzset`` to change it.
LOCAL_ZONE: tzinfo | None = None


def iso_timestamp(epoch_seconds: float | int | None) -> str | None:
    """Convert Unix seconds to local ISO 8601 (``2026-11-01T22:54:09-04:00``).

    ``None``, values <= 0 and values the platform cannot represent give ``None``.
    The local zone is :data:`LOCAL_ZONE` (the system zone by default).
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
        moment = datetime.fromtimestamp(value, tz=timezone.utc).astimezone(LOCAL_ZONE)
        return moment.isoformat(timespec="seconds")
    except (OverflowError, OSError, ValueError):
        # Unrepresentable on this platform (for example 1e20): null.
        return None


def now_iso() -> str:
    """Current local time as ISO 8601 with offset."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def dumps_json(payload: dict) -> str:
    """Serialize a payload as JSON: 2-space indent, one field per line, no ASCII escaping."""
    return json.dumps(payload, ensure_ascii=False, indent=2, separators=(",", ": "), sort_keys=False)


def configure_streams() -> None:
    """Force UTF-8 and LF on ``stdout``/``stderr``, also when piped on Windows."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", newline="\n")


def write_json(payload: dict) -> None:
    """Write one formatted JSON object to ``stdout`` followed by a single LF."""
    sys.stdout.write(dumps_json(payload))
    sys.stdout.write("\n")
    sys.stdout.flush()

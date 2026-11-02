"""``.emlx`` path resolution and MIME parsing (PRD 9.5, 17).

Resolves ``uid -> path`` with an O(1) formula (version uuid + decimal shards),
falls back to a recursive search only when the formula misses, and parses the
``.emlx`` container: length line, RFC 5322/MIME payload and plist trailer.

Never writes anything and never triggers an attachment download.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mailquery.store import EnvelopeStore, Mailbox


@dataclass(frozen=True)
class EmlxMessage:
    """Parsed representation of one ``.emlx`` file."""

    path: Path
    partial: bool
    headers: dict[str, str]
    body_text: str
    attachments: tuple[str, ...]
    available: bool
    readable: bool
    warnings: tuple[str, ...] = ()


def resolve_path(store: "EnvelopeStore", mailbox: "Mailbox", uid: int) -> Path | None:
    """Return the ``.emlx``/``.partial.emlx`` path for ``uid`` or ``None``."""
    raise NotImplementedError


def parse_emlx(path: Path) -> EmlxMessage:
    """Parse an ``.emlx`` file without modifying it."""
    raise NotImplementedError


def html_to_text(html: str) -> str:
    """Convert HTML to plain text using ``html.parser``."""
    raise NotImplementedError

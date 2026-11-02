"""Search, new-mail, show and mailboxes queries (PRD 9.3, 9.4, 12).

Builds the SQL filters, applies the configured scope (declared accounts only,
INBOX always included), deduplicates by ``global_message_id`` with INBOX
priority, bounds content scans (``--text``) and assembles the JSON message
objects. This module renders no JSON: it returns plain dictionaries that the
CLI wraps with ``ok``/``command``/``generated_at``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mailquery.accounts import AccountLabels
    from mailquery.config import Config
    from mailquery.state import StateStore
    from mailquery.store import EnvelopeStore


@dataclass(frozen=True)
class Filters:
    """Validated CLI filters for ``search``."""

    subject: tuple[str, ...] = ()
    text: tuple[str, ...] = ()
    from_: tuple[str, ...] = ()
    to: tuple[str, ...] = ()
    cc: tuple[str, ...] = ()
    since: float | None = None
    until: float | None = None
    unread: bool = False
    flagged: bool = False
    has_attachments: bool = False
    include_mailboxes: tuple[str, ...] = ()
    limit: int | None = None


@dataclass(frozen=True)
class ScanStats:
    mode: str
    candidates: int
    messages_read: int
    duration_ms: int


def parse_relative_time(value: str, now: datetime | None = None) -> float:
    """Parse an ISO date or relative value into Unix seconds (E_BAD_TIME)."""
    raise NotImplementedError


def wildcard_to_regex(pattern: str) -> str:
    """Translate ``*``/``?`` wildcards into a case-insensitive regex string."""
    raise NotImplementedError


def matches(pattern: str, text: str) -> bool:
    """Case-insensitive wildcard/substring match against untrusted text."""
    raise NotImplementedError


def run_search(
    store: "EnvelopeStore",
    config: "Config",
    labels: "AccountLabels",
    filters: Filters,
) -> dict:
    """Return ``{"messages", "truncated", "warnings", "scan"}``."""
    raise NotImplementedError


def run_new(
    store: "EnvelopeStore",
    config: "Config",
    labels: "AccountLabels",
    state_store: "StateStore",
    *,
    peek: bool = False,
    limit: int | None = None,
) -> dict:
    """Return ``{"messages", "truncated", "warnings", "scan", "cursor"}``."""
    raise NotImplementedError


def run_show(store: "EnvelopeStore", labels: "AccountLabels", uid: int) -> dict:
    """Return ``{"message", "warnings"}`` for one uid."""
    raise NotImplementedError


def run_mailboxes(store: "EnvelopeStore", config: "Config", labels: "AccountLabels") -> dict:
    """Return ``{"accounts", "mailboxes", "warnings"}``."""
    raise NotImplementedError

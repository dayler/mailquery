"""Read-only access to the Apple Mail store (PRD 9.5, 9.6, 11.1).

Locates ``~/Library/Mail/V*`` from ``PersistenceInfo.plist``, validates the
``Envelope Index`` schema by feature detection, opens it read-only (URI
``mode=ro`` + ``PRAGMA query_only=ON``) or through a temporary copy when the
``-shm`` file is absent, and maps mailbox URLs to on-disk directories.

This module must never write inside ``~/Library/Mail``.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

SUPPORTED_VERSIONS = ("V9", "V10", "V11")

# Minimum column fingerprint required from each table (PRD 11.1). Keys are
# table names, values the columns that must exist for the schema to be usable.
REQUIRED_COLUMNS: dict[str, tuple[str, ...]] = {
    "messages": (
        "ROWID",
        "message_id",
        "global_message_id",
        "sender",
        "subject",
        "date_sent",
        "date_received",
        "mailbox",
        "flags",
        "read",
        "flagged",
        "deleted",
        "size",
    ),
    "subjects": ("ROWID", "subject"),
    "addresses": ("ROWID", "address", "comment"),
    "recipients": ("message", "address", "type", "position"),
    "mailboxes": ("ROWID", "url"),
    "labels": ("message_id", "mailbox_id"),
    "attachments": ("message", "name"),
    "message_global_data": ("ROWID", "message_id_header"),
}


@dataclass(frozen=True)
class StoreVersion:
    """Detected Mail store version and the paths derived from it."""

    mail_root: Path
    version: str
    version_uuid: str
    data_dir: Path
    envelope_index: Path


@dataclass(frozen=True)
class Mailbox:
    """One row of the ``mailboxes`` table plus recalculated counters."""

    rowid: int
    url: str
    name: str
    path: str
    account_uuid: str
    account_kind: str  # "imap" | "local"
    is_inbox: bool
    is_aggregate: bool
    message_count: int
    unread_count: int


class EnvelopeStore:
    """Open read-only connection plus mailbox metadata."""

    def __init__(
        self,
        version: StoreVersion,
        connection: sqlite3.Connection,
        strategy: str,
        tmp_dir: Path | None = None,
    ) -> None:
        raise NotImplementedError

    @property
    def mailboxes(self) -> tuple[Mailbox, ...]:
        raise NotImplementedError

    def mailbox(self, rowid: int) -> Mailbox:
        raise NotImplementedError

    def mailbox_dir(self, mailbox: Mailbox) -> Path:
        """Return the on-disk ``.mbox`` directory for a mailbox (read-only)."""
        raise NotImplementedError

    def resolve_mailbox(self, account_uuid: str, ref: str) -> Mailbox | None:
        """Resolve a mailbox name/path/URL inside one account, case-insensitively."""
        raise NotImplementedError

    def fingerprint(self) -> dict[str, bool]:
        """Feature-detect the required schema; False marks a missing piece."""
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


def open_store(mail_root: Path | None = None, tmp_root: Path | None = None) -> EnvelopeStore:
    """Open the Mail store read-only, choosing the live or copied strategy."""
    raise NotImplementedError


def detect_version(mail_root: Path | None = None) -> StoreVersion:
    """Detect the Mail store version from ``PersistenceInfo.plist``."""
    raise NotImplementedError

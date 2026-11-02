"""Read-only resolution of visible account labels (PRD 11.3).

Reads ``~/Library/Accounts/Accounts4.sqlite`` in SQLite read-only mode to map a
Mail account UUID to a human label such as ``iCloud (you@gmail.com)``,
``Gmail (you@gmail.com)`` or ``On My Device``. Never reads credentials and
never writes to the database.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AccountLabel:
    """Display metadata for one Mail account."""

    uuid: str
    label: str
    email: str | None = None
    provider: str | None = None
    local: bool = False


class AccountLabels:
    """Lazy, read-only label resolver backed by ``Accounts4.sqlite``."""

    def __init__(self, db_path: Path | None = None, tmp_dir: Path | None = None) -> None:
        raise NotImplementedError

    @property
    def available(self) -> bool:
        """True when the accounts database could be opened and read."""
        raise NotImplementedError

    def all(self) -> list[AccountLabel]:
        raise NotImplementedError

    def get(self, uuid: str) -> AccountLabel | None:
        raise NotImplementedError

    def label_for(self, uuid: str) -> str:
        """Return the readable label, or the UUID when labels are unavailable."""
        raise NotImplementedError


def default_accounts_db_path() -> Path:
    """Return ``~/Library/Accounts/Accounts4.sqlite``."""
    raise NotImplementedError

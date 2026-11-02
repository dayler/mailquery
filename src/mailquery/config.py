"""Configuration loading, validation and scope resolution (PRD 15).

Owns the optional ``~/.mailquery/config.toml``: parsing with ``tomllib``,
strict validation (unknown keys are errors), defaults and the declaration of
observed accounts (``[scope.<account-id>]``).

This module never writes the configuration and never opens the Mail store by
itself: scope resolution receives the store and the account labels as
arguments to avoid import cycles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from mailquery.errors import MailqueryError

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mailquery.accounts import AccountLabels
    from mailquery.store import Mailbox, EnvelopeStore

LOG_LEVELS = ("error", "warning", "info", "debug")


@dataclass(frozen=True)
class LoggingConfig:
    level: str = "info"
    retention_days: int = 7


@dataclass(frozen=True)
class SearchConfig:
    default_limit: int = 20
    max_scan: int = 5000


@dataclass(frozen=True)
class NewConfig:
    default_limit: int = 100
    lookback: str = "10min"
    lookback_seconds: int = 600


@dataclass(frozen=True)
class ScopeEntry:
    """One ``[scope.<account-id>]`` block exactly as written by the user."""

    key: str
    mailbox_list: tuple[str, ...] = ()


@dataclass(frozen=True)
class Config:
    home: Path
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
    new: NewConfig = field(default_factory=NewConfig)
    scopes: tuple[ScopeEntry, ...] = ()

    @property
    def has_scopes(self) -> bool:
        return bool(self.scopes)


@dataclass(frozen=True)
class ResolvedScope:
    """A declared account and the mailboxes observed for it (INBOX included)."""

    account_uuid: str
    account_label: str
    account_email: str | None
    mailboxes: tuple["Mailbox", ...]


def app_home() -> Path:
    """Return ``~/.mailquery`` (fixed product value, PRD 15.6)."""
    raise NotImplementedError


def ensure_app_home(home: Path) -> None:
    """Create ``home`` and its runtime subdirectories with mode 0700."""
    raise NotImplementedError


def parse_duration(value: str) -> int:
    """Parse a duration such as ``10min``/``2h``/``1d`` into seconds.

    Raises :class:`MailqueryError` (E_CONFIG_INVALID) for invalid values.
    """
    raise NotImplementedError


def load_config(home: Path | None = None) -> Config:
    """Load and strictly validate ``config.toml`` (absent file means defaults)."""
    raise NotImplementedError


def resolve_scope(
    config: Config,
    store: "EnvelopeStore",
    labels: "AccountLabels",
) -> list[ResolvedScope]:
    """Resolve declared accounts and their mailbox list against the store.

    INBOX is always included first; ``mailbox_list`` entries are additive.
    Raises E_CONFIG_ACCOUNT_UNKNOWN, E_ACCOUNT_AMBIGUOUS,
    E_ACCOUNT_LABELS_UNAVAILABLE or E_MAILBOX_NOT_FOUND.
    """
    raise NotImplementedError

"""Configuration loading, validation and scope resolution (PRD 15).

Owns the optional ``~/.mailquery/config.toml``: parsing with ``tomllib``,
strict validation (unknown keys are errors), defaults and the declaration of
observed accounts (``[scope.<account-id>]``).

This module never writes the configuration and never opens a mail client by
itself: scope resolution receives the backend (``MailBackend``, PRD 9.3) as an
argument and only uses its interface.
"""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Sequence

from mailquery.errors import MailqueryError, config_error

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mailquery.backends.base import AccountRow, MailBackend, MailboxRow

LOG_LEVELS = ("error", "warning", "info", "debug")

CONFIG_FILENAME = "config.toml"
APP_HOME_SUBDIRS = ("logs", "locks", "tmp")
DEFAULT_APP_HOME_DIRNAME = ".mailquery"

DEFAULT_LOG_LEVEL = "info"
DEFAULT_MAX_SIZE_MB = 10
DEFAULT_SEARCH_LIMIT = 20
DEFAULT_SEARCH_MAX_SCAN = 5000
DEFAULT_NEW_LIMIT = 100
DEFAULT_LOOKBACK = "10min"

MIN_MAX_SIZE_MB = 1
MAX_MAX_SIZE_MB = 1024
MIN_SEARCH_LIMIT = 1
MAX_SEARCH_LIMIT = 200
MIN_SEARCH_MAX_SCAN = 100
MAX_SEARCH_MAX_SCAN = 50000
MIN_NEW_LIMIT = 1
MAX_NEW_LIMIT = 500

MIN_LOOKBACK_SECONDS = 60  # 1 min
MAX_LOOKBACK_SECONDS = 86400  # 1 day
MIN_UUID_PREFIX = 8

# Fixed order used for top-level validation and error hints.
_TOP_LEVEL_KEYS = ("logging", "search", "new", "scope")

_DURATION_RE = re.compile(r"^(\d+)(min|h|d)$")
_UNIT_SECONDS = {"min": 60, "h": 3600, "d": 86400}
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_UUIDISH_PREFIX_RE = re.compile(r"^[0-9a-fA-F-]{8,}$")

_CONSERVATIVE_LABELS_HINT = (
    "the accounts database (Accounts4.sqlite) could not be read; use the full "
    "account UUID (visible in `mailquery mailboxes`) in config.toml, or grant "
    "Full Disk Access"
)


@dataclass(frozen=True)
class LoggingConfig:
    level: str = DEFAULT_LOG_LEVEL
    max_size_mb: int = DEFAULT_MAX_SIZE_MB


@dataclass(frozen=True)
class SearchConfig:
    default_limit: int = DEFAULT_SEARCH_LIMIT
    max_scan: int = DEFAULT_SEARCH_MAX_SCAN


@dataclass(frozen=True)
class NewConfig:
    default_limit: int = DEFAULT_NEW_LIMIT
    lookback: str = DEFAULT_LOOKBACK
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
    mailboxes: tuple["MailboxRow", ...]


# --------------------------------------------------------------------------- #
# Application home
# --------------------------------------------------------------------------- #


def app_home() -> Path:
    """Return ``~/.mailquery`` (fixed product value, PRD 15.6)."""
    return Path.home() / DEFAULT_APP_HOME_DIRNAME


def ensure_app_home(home: Path) -> None:
    """Create ``home`` and its runtime subdirectories with mode 0700."""
    home_path = Path(home)
    directories = [home_path] + [home_path / name for name in APP_HOME_SUBDIRS]
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(directory, 0o700)
        except OSError:  # pragma: no cover - best effort on foreign filesystems
            pass


def parse_duration(value: str) -> int:
    """Parse a duration such as ``10min``/``2h``/``1d`` into seconds.

    Raises :class:`MailqueryError` (E_CONFIG_INVALID) for invalid values.
    """
    invalid = config_error(
        f"invalid duration: {value!r}",
        'use a number followed by a unit: "min", "h" or "d" '
        '(valid range 1min..1d, e.g. "10min", "2h", "1d")',
    )
    if not isinstance(value, str):
        raise invalid
    match = _DURATION_RE.match(value.strip())
    if match is None:
        raise invalid
    amount = int(match.group(1))
    seconds = amount * _UNIT_SECONDS[match.group(2)]
    if not MIN_LOOKBACK_SECONDS <= seconds <= MAX_LOOKBACK_SECONDS:
        raise config_error(
            f"duration out of range: {value!r}",
            'valid range: 1min..1d (e.g. "10min", "2h", "1d")',
        )
    return seconds


# --------------------------------------------------------------------------- #
# Loading and strict validation
# --------------------------------------------------------------------------- #


def load_config(home: Path | None = None) -> Config:
    """Load and strictly validate ``config.toml`` (absent file means defaults)."""
    home_path = Path(home) if home is not None else app_home()
    path = home_path / CONFIG_FILENAME
    try:
        with path.open("rb") as handle:
            data: Any = tomllib.load(handle)
    except FileNotFoundError:
        return Config(home=home_path)
    except tomllib.TOMLDecodeError as exc:
        raise config_error(
            f"invalid TOML in {path}: {exc}",
            "fix the TOML syntax; quoted keys with spaces, dots or parentheses, "
            'e.g. [scope."iCloud (user@example.com)"]',
            "invalid TOML in config.toml",
        ) from exc
    except OSError as exc:
        raise config_error(
            f"cannot read {path}: {exc.strerror or exc}",
            f"check that {path} is a readable file with mode 0600",
            "cannot read config.toml",
        ) from exc

    if not isinstance(data, dict):  # pragma: no cover - tomllib always returns a dict
        raise config_error("config.toml must contain a TOML table", "check the file syntax")

    return _parse_config(home_path, data)


def _parse_config(home: Path, data: dict[str, Any]) -> Config:
    for key in data:
        if key not in _TOP_LEVEL_KEYS:
            raise _unknown_top_level(key, data[key])

    logging_cfg = _parse_logging(data.get("logging"))
    search_cfg = _parse_search(data.get("search"))
    new_cfg = _parse_new(data.get("new"))
    scopes = _parse_scopes(data.get("scope"))
    return Config(
        home=home,
        logging=logging_cfg,
        search=search_cfg,
        new=new_cfg,
        scopes=scopes,
    )


def _unknown_top_level(key: str, value: Any) -> MailqueryError:
    if isinstance(value, dict):
        return config_error(
            f"unknown top-level section [{key}]",
            'account blocks must be declared as [scope."<account-id>"], not as '
            "top-level tables; only [logging], [search], [new] and [scope.*] are allowed",
            "unknown top-level section in config.toml",
        )
    return config_error(
        f"unknown top-level key {key!r}",
        "only the [logging], [search], [new] and [scope.*] sections are allowed; "
        "see the configuration reference in docs/PRD.md §15",
        "unknown top-level key in config.toml",
    )


def _as_table(value: Any, display: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise config_error(
            f"{display} must be a TOML table",
            f"write it as a table, e.g. [{display}] with its keys indented below",
        )
    return value


def _unknown_key(display: str, allowed: Sequence[str], key: str) -> MailqueryError:
    allowed_text = ", ".join(allowed) if allowed else "none"
    return config_error(
        f"unknown key {display}.{key}",
        f"remove it; allowed keys in this table: {allowed_text}",
    )


def _parse_int(
    table: dict[str, Any],
    *,
    display: str,
    key: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    value = table.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise config_error(
            f"{display}.{key} must be an integer",
            f"set {key} to an integer between {minimum} and {maximum}",
        )
    if not minimum <= value <= maximum:
        raise config_error(
            f"{display}.{key} out of range: {value}",
            f"valid range: {minimum}..{maximum}",
        )
    return value


def _parse_logging(value: Any) -> LoggingConfig:
    if value is None:
        return LoggingConfig()
    table = _as_table(value, "logging")
    for key in table:
        if key == "retention_days":
            raise config_error(
                "unknown key [logging].retention_days",
                "retention_days was replaced by max_size_mb",
            )
        if key not in ("level", "max_size_mb"):
            raise _unknown_key("[logging]", ("level", "max_size_mb"), key)
    level = table.get("level", DEFAULT_LOG_LEVEL)
    if not isinstance(level, str) or level not in LOG_LEVELS:
        raise config_error(
            f"invalid [logging].level: {level!r}",
            f"valid values: {', '.join(LOG_LEVELS)}",
        )
    max_size_mb = _parse_int(
        table,
        display="[logging]",
        key="max_size_mb",
        default=DEFAULT_MAX_SIZE_MB,
        minimum=MIN_MAX_SIZE_MB,
        maximum=MAX_MAX_SIZE_MB,
    )
    return LoggingConfig(level=level, max_size_mb=max_size_mb)


def _parse_search(value: Any) -> SearchConfig:
    if value is None:
        return SearchConfig()
    table = _as_table(value, "search")
    for key in table:
        if key not in ("default_limit", "max_scan"):
            raise _unknown_key("[search]", ("default_limit", "max_scan"), key)
    default_limit = _parse_int(
        table,
        display="[search]",
        key="default_limit",
        default=DEFAULT_SEARCH_LIMIT,
        minimum=MIN_SEARCH_LIMIT,
        maximum=MAX_SEARCH_LIMIT,
    )
    max_scan = _parse_int(
        table,
        display="[search]",
        key="max_scan",
        default=DEFAULT_SEARCH_MAX_SCAN,
        minimum=MIN_SEARCH_MAX_SCAN,
        maximum=MAX_SEARCH_MAX_SCAN,
    )
    return SearchConfig(default_limit=default_limit, max_scan=max_scan)


def _parse_new(value: Any) -> NewConfig:
    if value is None:
        return NewConfig()
    table = _as_table(value, "new")
    for key in table:
        if key not in ("default_limit", "lookback"):
            raise _unknown_key("[new]", ("default_limit", "lookback"), key)
    default_limit = _parse_int(
        table,
        display="[new]",
        key="default_limit",
        default=DEFAULT_NEW_LIMIT,
        minimum=MIN_NEW_LIMIT,
        maximum=MAX_NEW_LIMIT,
    )
    lookback = table.get("lookback", DEFAULT_LOOKBACK)
    if not isinstance(lookback, str):
        raise config_error(
            "[new].lookback must be a duration string",
            'e.g. lookback = "10min" (valid range 1min..1d)',
        )
    lookback_seconds = parse_duration(lookback)
    return NewConfig(
        default_limit=default_limit,
        lookback=lookback,
        lookback_seconds=lookback_seconds,
    )


def _parse_scopes(value: Any) -> tuple[ScopeEntry, ...]:
    if value is None:
        return ()
    table = _as_table(value, "scope")
    entries: list[ScopeEntry] = []
    for account_key, block in table.items():
        display = f'[scope."{account_key}"]'
        if not isinstance(account_key, str) or not account_key.strip():
            raise config_error(
                "empty account identifier in [scope]",
                'use a label, a unique email or a UUID, e.g. [scope."iCloud (user@example.com)"]',
                "invalid account block in config.toml",
            )
        if not isinstance(block, dict):
            raise config_error(
                f"{display} must be a TOML table",
                'declare each account as its own table, e.g. [scope."iCloud (user@example.com)"]',
                "invalid account block in config.toml",
            )
        for inner_key in block:
            if inner_key != "mailbox_list":
                raise config_error(
                    f"unknown key {display}.{inner_key}",
                    'the only allowed key inside an account block is "mailbox_list"',
                    "unknown key in an account block of config.toml",
                )
        raw_refs = block.get("mailbox_list", [])
        if not isinstance(raw_refs, list):
            raise config_error(
                f"{display}.mailbox_list must be an array of strings",
                'write it as a TOML array, e.g. mailbox_list = ["Facturas", "Archivo"]',
                "invalid mailbox_list in config.toml",
            )
        refs: list[str] = []
        for index, ref in enumerate(raw_refs):
            if not isinstance(ref, str):
                raise config_error(
                    f"{display}.mailbox_list[{index}] must be a string",
                    "each mailbox reference must be a string (name, path or URL)",
                    "invalid mailbox_list in config.toml",
                )
            if not ref.strip():
                raise config_error(
                    f"{display}.mailbox_list[{index}] must not be empty",
                    "use a mailbox name, path or URL as shown by `mailquery mailboxes`",
                    "invalid mailbox_list in config.toml",
                )
            refs.append(ref)
        entries.append(ScopeEntry(key=account_key, mailbox_list=tuple(refs)))
    return tuple(entries)


# --------------------------------------------------------------------------- #
# Scope resolution
# --------------------------------------------------------------------------- #


def listed_mailboxes(backend: "MailBackend") -> list["MailboxRow"]:
    """The backend's folders when only their identity matters (scope, display, hints).

    A backend whose ``total``/``unread`` cost a table scan per folder (Outlook)
    offers ``mailboxes_without_counters()``: the same rows without counting.
    Only the ``mailboxes`` command needs the counters (PRD 19, annex B.9);
    other backends answer with ``mailboxes()``.
    """
    without_counters = getattr(backend, "mailboxes_without_counters", None)
    if callable(without_counters):
        return list(without_counters())
    return list(backend.mailboxes())


def resolve_scope(
    config: Config,
    backend: "MailBackend",
    excluded: list[dict[str, Any]] | None = None,
) -> list[ResolvedScope]:
    """Resolve declared accounts and their mailbox list against the backend.

    INBOX is always included first; ``mailbox_list`` entries are additive.
    A key that resolves to an excluded store (Outlook account row with an
    ``excluded`` entry, PRD 15.3) is not read and is left out of the result;
    its ``{label, path, reason}`` entry is appended once to ``excluded`` when
    the caller passes a list (for ``W_STORE_EXCLUDED``).
    Raises E_CONFIG_ACCOUNT_UNKNOWN, E_ACCOUNT_AMBIGUOUS,
    E_ACCOUNT_LABELS_UNAVAILABLE or E_MAILBOX_NOT_FOUND.
    """
    if not config.scopes:
        return []

    accounts = list(backend.accounts())
    labels_available = bool(backend.labels_available)
    backend_mailboxes = listed_mailboxes(backend)

    declared_order: list[str] = []
    declared_refs: dict[str, list[str]] = {}
    for entry in config.scopes:
        account = _resolve_account(entry.key, accounts, labels_available)
        excluded_store = account.get("excluded")
        if excluded_store is not None:
            if excluded is not None and excluded_store not in excluded:
                excluded.append(excluded_store)
            continue
        account_uuid = account["uuid"]
        if account_uuid not in declared_refs:
            declared_order.append(account_uuid)
            declared_refs[account_uuid] = []
        merged_refs = declared_refs[account_uuid]
        for ref in entry.mailbox_list:
            if ref not in merged_refs:
                merged_refs.append(ref)

    by_uuid = {account["uuid"]: account for account in accounts}
    resolved: list[ResolvedScope] = []
    for account_uuid in declared_order:
        account_mailboxes = [
            mailbox for mailbox in backend_mailboxes if mailbox["account_uuid"] == account_uuid
        ]
        chosen: list["MailboxRow"] = []
        seen_ids: set[Any] = set()
        for mailbox in account_mailboxes:
            if mailbox["is_inbox"] and mailbox["id"] not in seen_ids:
                chosen.append(mailbox)
                seen_ids.add(mailbox["id"])
        for ref in declared_refs[account_uuid]:
            mailbox = _find_mailbox(backend, account_uuid, ref)
            if mailbox is None:
                raise _mailbox_not_found(ref, account_uuid, account_mailboxes, by_uuid)
            if mailbox["id"] not in seen_ids:
                chosen.append(mailbox)
                seen_ids.add(mailbox["id"])
        account_label, account_email = _account_identity(by_uuid, account_uuid)
        resolved.append(
            ResolvedScope(
                account_uuid=account_uuid,
                account_label=account_label,
                account_email=account_email,
                mailboxes=tuple(chosen),
            )
        )
    return resolved


def _resolve_account(
    key: str,
    accounts: Sequence["AccountRow"],
    labels_available: bool,
) -> "AccountRow":
    """Resolve one config key: label -> unique email -> UUID/prefix (PRD 15.2).

    Returns the matched account row; it may be an excluded store (Outlook row
    with ``excluded``, PRD 15.3), which the caller reports instead of reading.
    """
    key_folded = key.casefold()
    # UUID matching uses the accounts that have folders; label and email
    # matching and the "known accounts" lists use every label entry. An
    # unreadable excluded store has no uuid and resolves by label only.
    in_store = [
        account
        for account in accounts
        if account.get("store_index", 0) is not None and account["uuid"]
    ]
    in_store.sort(key=lambda account: account.get("store_index", 0) or 0)
    account_uuids = [account["uuid"] for account in in_store]
    by_uuid: dict[str, "AccountRow"] = {}
    for account in in_store:
        by_uuid.setdefault(account["uuid"], account)
    entries: list["AccountRow"] = (
        [account for account in accounts if account.get("labelled", True)]
        if labels_available
        else []
    )

    label_matches = [
        entry for entry in entries if entry["label"] and entry["label"].casefold() == key_folded
    ]
    email_matches: list["AccountRow"] = []
    if not label_matches:
        email_matches = [
            entry
            for entry in entries
            if entry["email"] and entry["email"].casefold() == key_folded
        ]

    candidates = label_matches or email_matches
    if len(candidates) > 1:
        raise _ambiguous_account(key, [(entry["label"], entry["uuid"]) for entry in candidates])
    if candidates:
        account = candidates[0]
        if account.get("excluded") is not None or account["uuid"] in account_uuids:
            return account
        raise _unknown_account(key, entries)

    if _UUID_RE.match(key):
        for account_uuid in account_uuids:
            if account_uuid.casefold() == key_folded:
                return by_uuid[account_uuid]

    if len(key) >= MIN_UUID_PREFIX:
        prefixed = [
            account_uuid
            for account_uuid in account_uuids
            if account_uuid.casefold().startswith(key_folded)
        ]
        if len(prefixed) == 1:
            return by_uuid[prefixed[0]]
        if len(prefixed) > 1:
            labels = {account["uuid"]: account["label"] for account in accounts}
            raise _ambiguous_account(
                key,
                [(labels[uuid] if labels_available else None, uuid) for uuid in prefixed],
            )

    if not labels_available:
        # A UUID (full or prefix-like) is resolvable without account labels,
        # so a miss means the account is unknown, not unresolvable.
        if _UUID_RE.match(key) or _UUIDISH_PREFIX_RE.match(key):
            raise _unknown_account(key, entries)
        raise MailqueryError(
            "E_ACCOUNT_LABELS_UNAVAILABLE",
            f"cannot resolve account {key!r}: account labels are unavailable",
            _CONSERVATIVE_LABELS_HINT,
            "cannot resolve an account: account labels are unavailable",
        )
    raise _unknown_account(key, entries)


def _ambiguous_account(
    key: str,
    candidates: Sequence[tuple[str | None, str]],
) -> MailqueryError:
    pairs = ", ".join(_format_account(label, uuid) for label, uuid in candidates)
    return MailqueryError(
        "E_ACCOUNT_AMBIGUOUS",
        f"account reference {key!r} matches more than one account",
        f"use a more specific identifier; matching accounts: {pairs}",
        "an account reference matches more than one account",
    )


def _unknown_account(key: str, entries: Sequence["AccountRow"]) -> MailqueryError:
    # Excluded stores (Outlook) are never offered as accounts to declare.
    entries = [entry for entry in entries if entry.get("excluded") is None]
    if entries:
        known = ", ".join(_format_account(entry["label"], entry["uuid"]) for entry in entries)
        hint = f"declare an existing account; known accounts: {known}"
    else:
        hint = (
            "declare an existing account with its label, unique email or UUID; "
            "remove the [scope.*] block and run `mailquery mailboxes` to list accounts"
        )
    return MailqueryError(
        "E_CONFIG_ACCOUNT_UNKNOWN",
        f"unknown account in config.toml: {key!r}",
        hint,
        "unknown account in config.toml",
    )


def _format_account(label: str | None, account_uuid: str | None) -> str:
    if account_uuid is None:  # an unreadable excluded store (Outlook)
        return label or ""
    if label and label != account_uuid:
        return f"{label} ({account_uuid})"
    return account_uuid


def _account_identity(
    accounts: dict[str, "AccountRow"], account_uuid: str
) -> tuple[str, str | None]:
    """``(label, email)`` of an account; the UUID stands in for a missing label."""
    entry = accounts.get(account_uuid)
    if entry is None:
        return account_uuid, None
    return (entry["label"] or account_uuid), entry["email"]


def _find_mailbox(
    backend: "MailBackend", account_uuid: str, ref: str
) -> "MailboxRow | None":
    # PRD 15.3: INBOX is always the account inbox, an exact path or URL beats a
    # name match and the first name match wins; all of that lives in the backend.
    mailbox = backend.resolve_mailbox(account_uuid, ref)
    if mailbox is not None and mailbox["account_uuid"] == account_uuid:
        return mailbox
    return None


def _valid_folders(account_mailboxes: Sequence["MailboxRow"]) -> str:
    valid = sorted({mailbox["path"] or mailbox["name"] for mailbox in account_mailboxes})
    return ", ".join(valid) if valid else "(no folders)"


def include_mailbox_not_found(
    ref: str,
    account_uuids: Sequence[str],
    backend: "MailBackend",
) -> MailqueryError:
    """``E_MAILBOX_NOT_FOUND`` for an ``--include-mailbox`` reference (PRD 15.3).

    The hint lists the folders of every declared account.
    """
    accounts = {account["uuid"]: account for account in backend.accounts()}
    backend_mailboxes = listed_mailboxes(backend)
    parts: list[str] = []
    for account_uuid in account_uuids:
        account_mailboxes = [
            mailbox for mailbox in backend_mailboxes if mailbox["account_uuid"] == account_uuid
        ]
        label = _account_identity(accounts, account_uuid)[0]
        parts.append(f"{_format_account(label, account_uuid)}: {_valid_folders(account_mailboxes)}")
    valid_text = "; ".join(parts) if parts else "(no declared accounts)"
    return MailqueryError(
        "E_MAILBOX_NOT_FOUND",
        f"mailbox {ref!r} was not found in the declared accounts",
        f"valid folders: {valid_text}; run `mailquery mailboxes` to list names, paths and URLs",
        "an included mailbox was not found in the declared accounts",
    )


def _mailbox_not_found(
    ref: str,
    account_uuid: str,
    account_mailboxes: Sequence["MailboxRow"],
    accounts: dict[str, "AccountRow"],
) -> MailqueryError:
    account_label, _ = _account_identity(accounts, account_uuid)
    valid_text = _valid_folders(account_mailboxes)
    return MailqueryError(
        "E_MAILBOX_NOT_FOUND",
        f"mailbox {ref!r} not found in account {_format_account(account_label, account_uuid)}",
        f"valid folders: {valid_text}; run `mailquery mailboxes` to list names, paths and URLs",
        "mailbox not found in an account",
    )

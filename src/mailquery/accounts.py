"""Read-only resolution of visible account labels (PRD 11.3).

Reads ``~/Library/Accounts/Accounts4.sqlite`` in SQLite read-only mode to map a
Mail account UUID to a human label such as ``iCloud (you@gmail.com)``,
``Gmail (you@gmail.com)`` or ``On My Device``. Never reads credentials and
never writes to the database.
"""

from __future__ import annotations

import shutil
import sqlite3
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from mailquery.logging_setup import get_logger

# Column fingerprint required from the Core Data accounts schema (PRD 11.3).
REQUIRED_COLUMNS: dict[str, tuple[str, ...]] = {
    "ZACCOUNT": (
        "Z_PK",
        "ZACCOUNTTYPE",
        "ZPARENTACCOUNT",
        "ZACCOUNTDESCRIPTION",
        "ZIDENTIFIER",
        "ZUSERNAME",
    ),
    "ZACCOUNTTYPE": ("Z_PK", "ZACCOUNTTYPEDESCRIPTION", "ZIDENTIFIER"),
}

# Only identifiers and visible names are selected: no credential, token,
# password or data-class column is ever queried (PRD 11.3 / invariant I-1).
_LABEL_QUERY = """
    SELECT
        c.ZIDENTIFIER AS uuid,
        c.ZUSERNAME AS username,
        c.ZACCOUNTDESCRIPTION AS account_description,
        ct.ZACCOUNTTYPEDESCRIPTION AS account_type,
        ct.ZIDENTIFIER AS type_identifier,
        p.ZUSERNAME AS parent_email,
        p.ZACCOUNTDESCRIPTION AS parent_description,
        pt.ZACCOUNTTYPEDESCRIPTION AS parent_provider
    FROM ZACCOUNT AS c
    LEFT JOIN ZACCOUNTTYPE AS ct ON ct.Z_PK = c.ZACCOUNTTYPE
    LEFT JOIN ZACCOUNT AS p ON p.Z_PK = c.ZPARENTACCOUNT
    LEFT JOIN ZACCOUNTTYPE AS pt ON pt.Z_PK = p.ZACCOUNTTYPE
    WHERE c.ZIDENTIFIER IS NOT NULL AND c.ZIDENTIFIER <> ''
    ORDER BY c.Z_PK
"""

# Account types that appear as Mail store URLs: IMAP/Exchange children and the
# local "On My Device" account. Other Core Data accounts (iCloud/Google/Apple
# ID parents and authentication helpers) are not Mail accounts.
_MAIL_TYPE_MARKERS = ("imap", "exchange", "ews", "onmydevice")

_RETRY_DELAY_SECONDS = 0.1
_ACCOUNTS_DB_NAME = "Accounts4.sqlite"


def _log():
    """Return a logger that carries the current ``run_id``."""
    return get_logger("mailquery.accounts")


@dataclass(frozen=True)
class AccountLabel:
    """Display metadata for one Mail account."""

    uuid: str
    label: str
    email: str | None = None
    provider: str | None = None
    local: bool = False


def default_accounts_db_path() -> Path:
    """Return ``~/Library/Accounts/Accounts4.sqlite``."""
    return Path.home() / "Library" / "Accounts" / _ACCOUNTS_DB_NAME


def _default_tmp_dir() -> Path:
    return Path.home() / ".mailquery" / "tmp"


def _sidecar(path: Path, suffix: str) -> Path:
    return path.with_name(path.name + suffix)


def _is_within(path: Path, parent: Path) -> bool:
    try:
        Path(path).expanduser().resolve().relative_to(Path(parent).expanduser().resolve())
    except (OSError, ValueError):
        return False
    return True


def _make_private(path: Path) -> None:
    """Restrict a temporary copy to its owner (0600, RNF-05); best effort."""
    try:
        path.chmod(0o600)
    except OSError:  # pragma: no cover - best effort on foreign filesystems
        pass


def _connect_readonly(path: Path) -> sqlite3.Connection:
    uri = Path(path).expanduser().resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
    except sqlite3.Error:
        connection.close()
        raise
    return connection


def _connect_with_retry(path: Path) -> sqlite3.Connection | None:
    """Open read-only, retrying once when the database is briefly locked."""
    for attempt in (1, 2):
        try:
            return _connect_readonly(path)
        except sqlite3.OperationalError as exc:
            text = str(exc).lower()
            if ("locked" in text or "busy" in text) and attempt == 1:
                time.sleep(_RETRY_DELAY_SECONDS)
                continue
            return None
        except sqlite3.Error:
            return None
    return None


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    quoted = table.replace('"', '""')
    try:
        rows = connection.execute(f'PRAGMA table_info("{quoted}")').fetchall()
    except sqlite3.Error:
        return set()
    return {str(row[1]) for row in rows}


def _missing_columns(connection: sqlite3.Connection) -> list[str]:
    missing: list[str] = []
    for table, required in REQUIRED_COLUMNS.items():
        columns = _table_columns(connection, table)
        missing.extend(f"{table}.{column}" for column in required if column not in columns)
    return missing


def _is_mail_account(type_identifier: str | None, type_description: str | None) -> bool:
    identifier = (type_identifier or "").casefold()
    description = (type_description or "").casefold()
    return any(marker in identifier for marker in _MAIL_TYPE_MARKERS) or any(
        marker in description for marker in _MAIL_TYPE_MARKERS
    )


def _format_label(provider: str | None, email: str | None) -> str:
    provider = (provider or "").strip()
    email = (email or "").strip()
    if provider and email:
        return f"{provider} ({email})"
    return provider or email


def _build_label(row: sqlite3.Row) -> AccountLabel | None:
    uuid = str(row["uuid"] or "").strip()
    if not uuid:
        return None
    account_type = (row["account_type"] or "").strip() or None
    type_identifier = (row["type_identifier"] or "").strip() or None
    account_description = (row["account_description"] or "").strip() or None
    username = (row["username"] or "").strip() or None
    parent_email = (row["parent_email"] or "").strip() or None
    parent_description = (row["parent_description"] or "").strip() or None
    parent_provider = (row["parent_provider"] or "").strip() or None

    if not _is_mail_account(type_identifier, account_type):
        return None

    if (type_identifier or "").casefold().endswith(".onmydevice") or (
        account_type or ""
    ).casefold() == "on my device":
        return AccountLabel(
            uuid=uuid,
            label="On My Device",
            email=None,
            provider=account_type or "On My Device",
            local=True,
        )

    # IMAP/Exchange child: the parent account supplies provider + email.
    provider = parent_provider or parent_description or account_type
    email = parent_email if parent_email is not None else username
    label = _format_label(provider, email)
    if not label:
        label = account_description or uuid
    return AccountLabel(
        uuid=uuid,
        label=label,
        email=email,
        provider=provider,
        local=False,
    )


class AccountLabels:
    """Lazy, read-only label resolver backed by ``Accounts4.sqlite``."""

    def __init__(self, db_path: Path | None = None, tmp_dir: Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else default_accounts_db_path()
        self.tmp_dir = Path(tmp_dir) if tmp_dir is not None else None
        self._loaded = False
        self._available = False
        self._labels: dict[str, AccountLabel] = {}
        self._folded: dict[str, AccountLabel] = {}
        self._order: list[str] = []
        self._warning: str | None = None

    # -- lazy loading ------------------------------------------------------- #

    @property
    def available(self) -> bool:
        """True when the accounts database could be opened and read."""
        self._ensure_loaded()
        return self._available

    @property
    def warning(self) -> str | None:
        """Human-readable reason when labels are unavailable (None if ready)."""
        self._ensure_loaded()
        return self._warning

    def all(self) -> list[AccountLabel]:
        self._ensure_loaded()
        return [self._labels[uuid] for uuid in self._order]

    def get(self, uuid: str) -> AccountLabel | None:
        self._ensure_loaded()
        if uuid is None:
            return None
        key = str(uuid).strip()
        if not key:
            return None
        label = self._labels.get(key)
        if label is not None:
            return label
        return self._folded.get(key.casefold())

    def label_for(self, uuid: str) -> str:
        """Return the readable label, or the UUID when labels are unavailable."""
        label = self.get(uuid)
        if label is not None:
            return label.label
        if not self.available:
            _log().warning("account labels unavailable; using uuid")
        else:
            _log().warning("no visible label for an account; using uuid")
        return str(uuid)

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        rows = self._read_rows()
        if rows is None:
            return
        for row in rows:
            account = _build_label(row)
            if account is None:
                continue
            if account.uuid in self._labels:
                continue  # duplicate ZIDENTIFIER rows: keep the first one
            self._labels[account.uuid] = account
            self._folded[account.uuid.casefold()] = account
            self._order.append(account.uuid)
        self._available = True
        self._warning = None

    # -- source database ---------------------------------------------------- #

    def _read_rows(self) -> list[sqlite3.Row] | None:
        source, work_dir = self._source_database()
        if source is None:
            return None
        connection: sqlite3.Connection | None = None
        try:
            connection = _connect_with_retry(source)
            if connection is None:
                self._warning = f"accounts database is locked: {source}"
                return None
            missing = _missing_columns(connection)
            if missing:
                detail = ", ".join(missing[:6])
                self._warning = f"unsupported accounts schema; missing {detail}"
                return None
            return connection.execute(_LABEL_QUERY).fetchall()
        except (sqlite3.Error, OSError) as exc:
            self._warning = f"cannot read accounts database: {exc}"
            return None
        finally:
            if connection is not None:
                connection.close()
            if work_dir is not None:
                shutil.rmtree(work_dir, ignore_errors=True)

    def _source_database(self) -> tuple[Path | None, Path | None]:
        """Return ``(database_to_open, temporary_copy_dir_or_None)``."""
        try:
            exists = self.db_path.is_file()
        except OSError:
            exists = False
        if not exists:
            self._warning = f"accounts database not found: {self.db_path}"
            return None, None

        shm = _sidecar(self.db_path, "-shm")
        try:
            if shm.exists():
                return self.db_path, None
        except OSError:
            pass

        tmp_dir = self.tmp_dir if self.tmp_dir is not None else _default_tmp_dir()
        if _is_within(tmp_dir, self.db_path.parent):
            self._warning = (
                f"refusing to use {tmp_dir} as temporary directory: it is inside "
                "the accounts database directory"
            )
            return None, None
        try:
            tmp_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            work_dir = Path(tempfile.mkdtemp(prefix="mailquery-accounts-", dir=tmp_dir))
        except OSError as exc:
            self._warning = f"cannot create temporary directory under {tmp_dir}: {exc}"
            return None, None

        target = work_dir / self.db_path.name
        try:
            shutil.copy2(self.db_path, target)
            _make_private(target)
            wal = _sidecar(self.db_path, "-wal")
            if wal.is_file():
                shutil.copy2(wal, work_dir / wal.name)
                _make_private(work_dir / wal.name)
        except OSError as exc:
            shutil.rmtree(work_dir, ignore_errors=True)
            self._warning = f"cannot copy accounts database: {exc}"
            return None, None
        return target, work_dir

"""Read-only access to the Apple Mail store (PRD 9.5, 9.6, 11.1).

Locates ``~/Library/Mail/V*`` from ``PersistenceInfo.plist``, validates the
``Envelope Index`` schema by feature detection, opens it read-only (URI
``mode=ro`` + ``PRAGMA query_only=ON``) or through a temporary copy when the
``-shm`` file is absent, and maps mailbox URLs to on-disk directories.

This module must never write inside ``~/Library/Mail``.
"""

from __future__ import annotations

import plistlib
import shutil
import sqlite3
import tempfile
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import unquote, urlsplit

from mailquery.errors import MailqueryError
from mailquery.logging_setup import get_logger

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

# Connection strategies (PRD 9.6).
STRATEGY_LIVE = "live_ro"
STRATEGY_COPY = "copy_ro"

_RETRY_DELAY_SECONDS = 0.1
_ENVELOPE_INDEX_NAME = "Envelope Index"


def _log():
    """Return a logger that carries the current ``run_id``."""
    return get_logger("mailquery.store")


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #


def _permission_error(path: Path, action: str, detail: str = "") -> MailqueryError:
    reason = detail or "permission denied"
    return MailqueryError(
        "E_PERMISSION",
        f"cannot {action} {path}: {reason}",
        "grant Full Disk Access to the app running mailquery "
        "(System Settings -> Privacy & Security -> Full Disk Access) and retry",
        log_message=f"cannot {action} a store path: permission denied",
    )


def _store_not_found(message: str, hint: str, log_message: str | None = None) -> MailqueryError:
    return MailqueryError("E_STORE_NOT_FOUND", message, hint, log_message)


def _schema_unsupported(message: str, hint: str) -> MailqueryError:
    return MailqueryError("E_SCHEMA_UNSUPPORTED", message, hint)


def _internal_error(message: str, hint: str = "", log_message: str | None = None) -> MailqueryError:
    return MailqueryError("E_INTERNAL", message, hint, log_message)


# --------------------------------------------------------------------------- #
# Paths and version detection
# --------------------------------------------------------------------------- #


def _default_mail_root() -> Path:
    return Path.home() / "Library" / "Mail"


def _default_tmp_root() -> Path:
    return Path.home() / ".mailquery" / "tmp"


def _sidecar(path: Path, suffix: str) -> Path:
    """Return the SQLite sidecar (``-wal``/``-shm``) for ``path``."""
    return path.with_name(path.name + suffix)


def _read_persistence_payload(mail_root: Path) -> dict:
    """Read ``PersistenceInfo.plist``; missing/invalid payload means empty."""
    path = mail_root / "PersistenceInfo.plist"
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return {}
    except PermissionError as exc:
        raise _permission_error(path, "read") from exc
    except OSError:
        return {}
    try:
        payload = plistlib.loads(raw)
    except Exception:  # plistlib raises several unrelated exception types
        return {}
    return payload if isinstance(payload, dict) else {}


def _fallback_version_dir(mail_root: Path) -> str | None:
    """Detect the version directory when the plist is missing or stale."""
    try:
        entries = list(mail_root.iterdir())
    except FileNotFoundError:
        return None
    except PermissionError as exc:
        raise _permission_error(mail_root, "inspect") from exc
    candidates: list[tuple[int, str]] = []
    for entry in entries:
        if entry.name not in SUPPORTED_VERSIONS:
            continue
        try:
            if not entry.is_dir():
                continue
            has_index = (entry / "MailData" / _ENVELOPE_INDEX_NAME).is_file()
        except OSError:
            continue
        if has_index:
            candidates.append((int(entry.name[1:]), entry.name))
    if not candidates:
        return None
    return max(candidates)[1]


def _find_version_uuid(version_dir: Path) -> str:
    """Find the version uuid directory (``<mailbox>.mbox/<uuid>/Data``)."""
    try:
        account_dirs = sorted(version_dir.iterdir())
    except OSError:
        return ""
    for account_dir in account_dirs:
        try:
            if not account_dir.is_dir():
                continue
            mailbox_dirs = sorted(account_dir.iterdir())
        except OSError:
            continue
        for mailbox_dir in mailbox_dirs:
            if not mailbox_dir.name.endswith(".mbox"):
                continue
            try:
                children = sorted(mailbox_dir.iterdir())
            except OSError:
                continue
            for child in children:
                try:
                    if (child / "Data").is_dir():
                        return child.name
                except OSError:
                    continue
    return ""


def detect_version(mail_root: Path | None = None) -> StoreVersion:
    """Detect the Mail store version from ``PersistenceInfo.plist``."""
    root = Path(mail_root) if mail_root is not None else _default_mail_root()
    try:
        root_exists = root.is_dir()
    except PermissionError as exc:
        raise _permission_error(root, "inspect") from exc
    if not root_exists:
        raise _store_not_found(
            f"Apple Mail store not found at {root}",
            "open Apple Mail at least once, check the path and make sure only "
            "read access is needed (Full Disk Access if the app is sandboxed)",
            "Apple Mail store not found",
        )

    payload = _read_persistence_payload(root)
    plist_version = payload.get("LastUsedVersionDirectoryName")
    plist_version = plist_version if isinstance(plist_version, str) else ""
    identifiers = payload.get("VersionDirectoryIdentifiers")
    identifiers = identifiers if isinstance(identifiers, dict) else {}

    if plist_version and plist_version not in SUPPORTED_VERSIONS:
        raise _schema_unsupported(
            f"Apple Mail store version {plist_version!r} is not supported",
            f"mailquery supports version directories {', '.join(SUPPORTED_VERSIONS)}; "
            "update mailquery or use a supported macOS/Apple Mail release",
        )

    version = plist_version
    version_dir = root / version if version else None
    try:
        version_exists = version_dir is not None and version_dir.is_dir()
    except PermissionError as exc:
        raise _permission_error(version_dir, "inspect") from exc
    if not version_exists:
        version = _fallback_version_dir(root) or ""
    if not version:
        if plist_version:
            raise _store_not_found(
                f"Apple Mail store version directory {root / plist_version} is missing",
                "open Apple Mail once so it rebuilds its store, or check the path",
                "Apple Mail store version directory is missing",
            )
        raise _store_not_found(
            f"no supported Apple Mail store version ({', '.join(SUPPORTED_VERSIONS)}) "
            f"found under {root}",
            "open Apple Mail once and retry; if this Mac is new, Apple Mail "
            "may not have been used yet",
        )

    version_dir = root / version
    data_dir = version_dir / "MailData"
    envelope_index = data_dir / _ENVELOPE_INDEX_NAME

    version_uuid = identifiers.get(version)
    version_uuid = version_uuid if isinstance(version_uuid, str) else ""
    if not version_uuid:
        version_uuid = _find_version_uuid(version_dir)
        if version_uuid:
            _log().debug("recovered version uuid from disk")

    return StoreVersion(
        mail_root=root,
        version=version,
        version_uuid=version_uuid,
        data_dir=data_dir,
        envelope_index=envelope_index,
    )


# --------------------------------------------------------------------------- #
# Read-only SQLite connection helpers
# --------------------------------------------------------------------------- #


def _connect_readonly(path: Path) -> sqlite3.Connection:
    """Open ``path`` in SQLite read-only URI mode with ``query_only`` set."""
    uri = Path(path).expanduser().resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
    except (sqlite3.Error, OSError):
        connection.close()
        raise
    return connection


def _is_busy(exc: sqlite3.Error) -> bool:
    """Return True when ``exc`` says the database is locked or busy."""
    text = str(exc).lower()
    return "locked" in text or "busy" in text


def run_query(
    connection: sqlite3.Connection,
    sql: str,
    params: Sequence[Any] = (),
    *,
    first: bool = False,
) -> Any:
    """Run a read query; a locked database is retried once after 100 ms (PRD A.4).

    Returns ``fetchall()`` (or ``fetchone()`` with ``first``). A lock that
    persists raises ``E_DB_BUSY``; any other ``sqlite3`` error propagates.
    """
    for attempt in (1, 2):
        try:
            cursor = connection.execute(sql, params)
            return cursor.fetchone() if first else cursor.fetchall()
        except sqlite3.OperationalError as exc:
            if not _is_busy(exc):
                raise
            if attempt == 1:
                time.sleep(_RETRY_DELAY_SECONDS)
                continue
            raise MailqueryError(
                "E_DB_BUSY",
                "the Envelope Index is locked by another process",
                "close Apple Mail or wait a moment and retry; mailquery "
                "never forces a lock on the live database",
                "the Envelope Index is locked",
            ) from exc
    raise _internal_error(  # pragma: no cover - the loop always returns/raises
        "the Envelope Index query failed", "retry the command"
    )


def _connect_with_retry(path: Path) -> sqlite3.Connection:
    """Open the database, retrying once after a short delay when locked."""
    for attempt in (1, 2):
        try:
            return _connect_readonly(path)
        except sqlite3.OperationalError as exc:
            locked = _is_busy(exc)
            if locked and attempt == 1:
                time.sleep(_RETRY_DELAY_SECONDS)
                continue
            if locked:
                raise MailqueryError(
                    "E_DB_BUSY",
                    f"the Envelope Index is locked: {path} ({exc})",
                    "close Apple Mail or wait a moment and retry; mailquery "
                    "never forces a lock on the live database",
                    "the Envelope Index is locked",
                ) from exc
            raise _store_not_found(
                f"cannot open the Envelope Index at {path}: {exc}",
                "check that the file is a readable SQLite database and that the "
                "app running mailquery has Full Disk Access",
                "cannot open the Envelope Index",
            ) from exc
        except sqlite3.Error as exc:
            raise _internal_error(
                f"cannot open Envelope Index at {path}: {exc}",
                "verify the file is a readable SQLite database",
                "cannot open the Envelope Index",
            ) from exc
        except OSError as exc:
            # macOS TCC (/Full Disk Access) can surface as a raw PermissionError
            # or OSError from sqlite3.connect(), not only as sqlite3.Error.
            raise _permission_error(path, "open", str(exc)) from exc
    raise _internal_error(  # pragma: no cover - the loop always returns/raises
        f"cannot open Envelope Index at {path}",
        "restart mailquery and retry",
        "cannot open the Envelope Index",
    )


def _is_within(path: Path, parent: Path) -> bool:
    """Return True when ``path`` is ``parent`` or lives below it."""
    try:
        path = Path(path).expanduser().resolve()
        parent = Path(parent).expanduser().resolve()
    except OSError:  # pragma: no cover - defensive
        return False
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _ensure_tmp_dir(tmp_root: Path | None, mail_root: Path) -> Path:
    """Validate/create the temporary directory used by the copy strategy."""
    tmp_dir = Path(tmp_root) if tmp_root is not None else _default_tmp_root()
    if _is_within(tmp_dir, mail_root):
        raise MailqueryError(
            "E_PERMISSION",
            f"refusing to use {tmp_dir} as a temporary directory: "
            "it is inside the Apple Mail store",
            "point the temporary directory to the app home (~/.mailquery/tmp)",
            "refusing to use a temporary directory inside the Apple Mail store",
        )
    try:
        tmp_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    except PermissionError as exc:
        raise _permission_error(tmp_dir, "create") from exc
    except OSError as exc:
        raise _internal_error(
            f"cannot create temporary directory {tmp_dir}: {exc}",
            "check free space and permissions under the app home",
            "cannot create the temporary directory",
        ) from exc
    try:
        tmp_dir.chmod(0o700)
    except OSError:  # pragma: no cover - best effort on foreign filesystems
        pass
    return tmp_dir


def _make_private(path: Path) -> None:
    """Restrict a temporary copy to its owner (0600, RNF-05); best effort."""
    try:
        path.chmod(0o600)
    except OSError:  # pragma: no cover - best effort on foreign filesystems
        pass


def _copy_for_readonly(version: StoreVersion, tmp_root: Path | None) -> tuple[Path, Path]:
    """Copy ``Envelope Index`` (+ ``-wal``) to the app temp dir (PRD 9.6)."""
    tmp_dir = _ensure_tmp_dir(tmp_root, version.mail_root)
    try:
        work_dir = Path(tempfile.mkdtemp(prefix="mailquery-envelope-", dir=tmp_dir))
    except OSError as exc:
        raise _internal_error(
            f"cannot create a temporary copy directory under {tmp_dir}: {exc}",
            "check free space and permissions under the app home",
            "cannot create a temporary copy directory",
        ) from exc
    source = version.envelope_index
    copied = work_dir / source.name
    try:
        shutil.copy2(source, copied)
        _make_private(copied)
        wal = _sidecar(source, "-wal")
        if wal.is_file():
            shutil.copy2(wal, work_dir / wal.name)
            _make_private(work_dir / wal.name)
    except OSError as exc:
        # TCC denial can surface here as a raw PermissionError/OSError.
        shutil.rmtree(work_dir, ignore_errors=True)
        raise _permission_error(source, "copy", str(exc)) from exc
    return copied, work_dir


# --------------------------------------------------------------------------- #
# Mailbox URL parsing
# --------------------------------------------------------------------------- #


def _parse_mailbox_url(url: str) -> tuple[str, str, tuple[str, ...]]:
    """Split a mailbox URL into ``(account_uuid, account_kind, segments)``."""
    try:
        parts = urlsplit(url or "")
    except ValueError:
        return "", "unknown", ()
    account_uuid = unquote(parts.netloc or "")
    segments = tuple(unquote(segment) for segment in (parts.path or "").split("/") if segment)
    if parts.scheme == "local":
        kind = "local"
    elif parts.scheme in ("imap", "imaps"):
        kind = "imap"
    else:
        kind = parts.scheme or "unknown"
    return account_uuid, kind, segments


def _mailbox_variants(mailbox: Mailbox) -> list[tuple[str, ...]]:
    """Return literal/NFC/NFD path segment variants for on-disk lookup."""
    _, _, segments = _parse_mailbox_url(mailbox.url)
    if not segments:
        return [()]
    variants: list[tuple[str, ...]] = [segments]
    for form in ("NFC", "NFD"):
        normalized = tuple(unicodedata.normalize(form, segment) for segment in segments)
        if normalized not in variants:
            variants.append(normalized)
    return variants


def _mailbox_directory(version: StoreVersion, mailbox: Mailbox, segments: tuple[str, ...]) -> Path:
    path = version.mail_root / version.version / mailbox.account_uuid
    for segment in segments:
        path = path / f"{segment}.mbox"
    return path


# --------------------------------------------------------------------------- #
# Schema fingerprint
# --------------------------------------------------------------------------- #


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    quoted = table.replace('"', '""')
    try:
        rows = connection.execute(f'PRAGMA table_info("{quoted}")').fetchall()
    except sqlite3.Error:
        return set()
    return {str(row[1]) for row in rows}  # column name is field 1


def _schema_fingerprint(connection: sqlite3.Connection) -> dict[str, bool]:
    result: dict[str, bool] = {}
    for table, required in REQUIRED_COLUMNS.items():
        columns = _table_columns(connection, table)
        result[table] = all(column in columns for column in required)
    return result


def _missing_columns(connection: sqlite3.Connection) -> list[str]:
    missing: list[str] = []
    for table, required in REQUIRED_COLUMNS.items():
        columns = _table_columns(connection, table)
        missing.extend(f"{table}.{column}" for column in required if column not in columns)
    return missing


# --------------------------------------------------------------------------- #
# Public data model
# --------------------------------------------------------------------------- #


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


def _mailbox_from_row(
    row: sqlite3.Row, counters: dict[int, tuple[int, int]]
) -> Mailbox:
    rowid = int(row["rowid"])
    url = str(row["url"] or "")
    account_uuid, account_kind, segments = _parse_mailbox_url(url)
    path = "/".join(segments)
    name = segments[-1] if segments else ""
    folded_path = path.casefold()
    total, unread = counters.get(rowid, (0, 0))
    return Mailbox(
        rowid=rowid,
        url=url,
        name=name,
        path=path,
        account_uuid=account_uuid,
        account_kind=account_kind,
        is_inbox=len(segments) == 1 and segments[0].casefold() == "inbox",
        is_aggregate="all mail" in folded_path,
        message_count=total,
        unread_count=unread,
    )


def _mailbox_counters(connection: sqlite3.Connection) -> dict[int, tuple[int, int]]:
    """Recalculate counts from ``messages`` + ``labels`` (PRD 11.1).

    Membership is ``messages.mailbox = X`` OR a ``labels`` row pointing at X,
    so a Gmail message physically stored in ``[Gmail]/All Mail`` still counts
    for INBOX/label mailboxes. The counters stored in ``mailboxes`` are
    ignored on purpose: Apple Mail reports unreliable values for virtual
    folders.
    """
    query = """
        WITH memberships AS (
            SELECT m.mailbox AS mailbox_id, m.ROWID AS message_rowid
            FROM messages AS m
            WHERE COALESCE(m.deleted, 0) = 0
            UNION
            SELECT l.mailbox_id AS mailbox_id, l.message_id AS message_rowid
            FROM labels AS l
            JOIN messages AS m ON m.ROWID = l.message_id
            WHERE COALESCE(m.deleted, 0) = 0
        )
        SELECT mb.ROWID AS rowid,
               COUNT(mem.message_rowid) AS message_count,
               COALESCE(
                   SUM(
                       CASE
                           WHEN mem.message_rowid IS NOT NULL
                                AND COALESCE(msg.read, 0) = 0
                           THEN 1 ELSE 0
                       END
                   ), 0
               ) AS unread_count
        FROM mailboxes AS mb
        LEFT JOIN memberships AS mem ON mem.mailbox_id = mb.ROWID
        LEFT JOIN messages AS msg ON msg.ROWID = mem.message_rowid
        GROUP BY mb.ROWID
    """
    rows = run_query(connection, query)
    return {
        int(row["rowid"]): (int(row["message_count"] or 0), int(row["unread_count"] or 0))
        for row in rows
    }


# --------------------------------------------------------------------------- #
# Store
# --------------------------------------------------------------------------- #


class EnvelopeStore:
    """Open read-only connection plus mailbox metadata."""

    def __init__(
        self,
        version: StoreVersion,
        connection: sqlite3.Connection,
        strategy: str,
        tmp_dir: Path | None = None,
    ) -> None:
        if strategy not in (STRATEGY_LIVE, STRATEGY_COPY):
            raise ValueError(f"unknown connection strategy: {strategy!r}")
        self.version = version
        self.connection = connection
        self.strategy = strategy
        self.tmp_dir = Path(tmp_dir) if tmp_dir is not None else None
        self._owns_tmp_dir = strategy == STRATEGY_COPY and self.tmp_dir is not None
        self._mailboxes: tuple[Mailbox, ...] | None = None
        self._by_rowid: dict[int, Mailbox] = {}
        self._closed = False

    # -- mailbox catalog ---------------------------------------------------- #

    def _load_mailboxes(self) -> tuple[Mailbox, ...]:
        rows = run_query(
            self.connection, "SELECT ROWID AS rowid, url FROM mailboxes ORDER BY ROWID"
        )
        counters = _mailbox_counters(self.connection)
        mailboxes = tuple(_mailbox_from_row(row, counters) for row in rows)
        self._mailboxes = mailboxes
        self._by_rowid = {mailbox.rowid: mailbox for mailbox in mailboxes}
        return mailboxes

    @property
    def mailboxes(self) -> tuple[Mailbox, ...]:
        if self._mailboxes is None:
            self._load_mailboxes()
        return self._mailboxes

    def mailbox(self, rowid: int) -> Mailbox:
        if self._mailboxes is None:
            self._load_mailboxes()
        try:
            return self._by_rowid[int(rowid)]
        except KeyError:
            raise KeyError(f"mailbox ROWID {rowid} does not exist") from None

    def resolve_mailbox(self, account_uuid: str, ref: str) -> Mailbox | None:
        """Resolve a mailbox name/path/URL inside one account (PRD 15.3).

        Case-insensitive. ``INBOX`` is always the account inbox; otherwise an
        exact path or URL beats a name match, and among several name matches
        the first one in catalog order wins.
        """
        if not ref:
            return None
        needle = str(ref).strip()
        if not needle:
            return None
        folded = needle.casefold()
        account = str(account_uuid or "").casefold()
        candidates = [
            mailbox
            for mailbox in self.mailboxes
            if mailbox.account_uuid.casefold() == account
        ]
        if folded == "inbox":
            return next((mailbox for mailbox in candidates if mailbox.is_inbox), None)
        for mailbox in candidates:
            if folded in (
                mailbox.path.casefold(),
                mailbox.url.casefold(),
                unquote(mailbox.url).casefold(),
            ):
                return mailbox
        for mailbox in candidates:
            if folded == mailbox.name.casefold():
                return mailbox
        return None

    def mailbox_dir(self, mailbox: Mailbox) -> Path:
        """Return the on-disk ``.mbox`` directory for a mailbox (read-only).

        Each decoded path segment maps to ``<segment>.mbox``; literal bracketed
        names are used without globbing. When accents differ by Unicode
        normalization the literal, NFC and NFD variants are tried in order.
        """
        variants = _mailbox_variants(mailbox)
        first: Path | None = None
        for segments in variants:
            candidate = _mailbox_directory(self.version, mailbox, segments)
            if first is None:
                first = candidate
            try:
                if candidate.is_dir():
                    return candidate
            except OSError:
                continue
        return first if first is not None else (
            self.version.mail_root / self.version.version / mailbox.account_uuid
        )

    # -- schema ------------------------------------------------------------- #

    def fingerprint(self) -> dict[str, bool]:
        """Feature-detect the required schema; False marks a missing piece."""
        return _schema_fingerprint(self.connection)

    def missing_columns(self) -> list[str]:
        """Return the ``table.column`` entries the current schema lacks."""
        return _missing_columns(self.connection)

    # -- lifecycle ---------------------------------------------------------- #

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.connection.close()
        finally:
            if self._owns_tmp_dir and self.tmp_dir is not None:
                shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def __enter__(self) -> "EnvelopeStore":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def probe_envelope_index(version: StoreVersion, tmp_root: Path | None = None) -> str:
    """Open the Envelope Index with the PRD A.4 strategy, read it and close it.

    Returns ``live_ro`` (``-shm`` present) or ``copy_ro``. The schema is not
    checked: that is the ``schema`` check of ``doctor``.
    """
    index = version.envelope_index
    try:
        if not index.is_file():
            raise _store_not_found(
                f"missing Envelope Index: {index}",
                "open Apple Mail once so the store is created",
                "Envelope Index not found",
            )
        strategy = STRATEGY_LIVE if _sidecar(index, "-shm").exists() else STRATEGY_COPY
    except PermissionError as exc:
        raise _permission_error(index, "read") from exc
    work_dir: Path | None = None
    db_path = index
    try:
        if strategy == STRATEGY_COPY:
            db_path, work_dir = _copy_for_readonly(version, tmp_root)
        connection = _connect_with_retry(db_path)
        try:
            connection.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchall()
        except sqlite3.Error as exc:
            raise _store_not_found(
                f"cannot read the Envelope Index at {index}: {exc}",
                "check that the file is a readable SQLite database",
                "cannot read the Envelope Index",
            ) from exc
        finally:
            connection.close()
    finally:
        if work_dir is not None:
            shutil.rmtree(work_dir, ignore_errors=True)
    return strategy


def open_store(mail_root: Path | None = None, tmp_root: Path | None = None) -> EnvelopeStore:
    """Open the Mail store read-only, choosing the live or copied strategy."""
    version = detect_version(mail_root)
    index = version.envelope_index
    try:
        index_exists = index.is_file()
    except PermissionError as exc:
        raise _permission_error(index, "read") from exc
    if not index_exists:
        raise _store_not_found(
            f"Envelope Index not found at {index}",
            "open Apple Mail once so it rebuilds its index; if the file exists, "
            "the app may need Full Disk Access",
            "Envelope Index not found",
        )

    shm = _sidecar(index, "-shm")
    try:
        has_shm = shm.exists()
    except PermissionError as exc:
        raise _permission_error(shm, "inspect") from exc

    work_dir: Path | None = None
    db_path = index
    strategy = STRATEGY_LIVE if has_shm else STRATEGY_COPY
    try:
        if strategy == STRATEGY_COPY:
            db_path, work_dir = _copy_for_readonly(version, tmp_root)
        connection = _connect_with_retry(db_path)
        store = EnvelopeStore(version, connection, strategy, tmp_dir=work_dir)
        missing = store.missing_columns()
        if missing:
            store.close()
            detail = ", ".join(missing[:8])
            if len(missing) > 8:
                detail += f", ... ({len(missing)} missing)"
            raise _schema_unsupported(
                f"Envelope Index schema is not supported; missing {detail}",
                "the Apple Mail index drifted from the supported layout "
                "(V9/V10/V11); update mailquery or check `mailquery doctor`",
            )
        _log().debug("opened Envelope Index strategy=%s", strategy)
        return store
    except Exception:
        if work_dir is not None:
            shutil.rmtree(work_dir, ignore_errors=True)
        raise

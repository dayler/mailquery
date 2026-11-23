"""Short ids and the cache that maps uid parts to native ids.

:func:`short_id` derives a deterministic short id from any text. :class:`NativeIdCache`
stores one row per native id and driver: the short id without suffix, the ``seq``
that keeps a uid part unique, and the native id itself. A new ``seq`` is the one
after the highest ``seq`` stored for its driver and short id, so deleting a row
lets that ``seq`` be used again.

:class:`PluginNativeIds` wraps a cache for the driver of a plugin: it opens the
database on its first operation and translates the cache failures to the plugin
error protocol.

The module is inert at import time. It opens the cache only when an operation
runs, writes only under ``<home>/db/cache.db`` and never touches the mail store.
"""

from __future__ import annotations

import os
import re
import sqlite3
import threading
from pathlib import Path
from typing import Final, Sequence

from mailquery.errors import MailqueryError
from mailquery.uid import is_valid_driver

ALPHABET: Final[str] = "0123456789abcdefghjkmnpqrstvwxyz"
FORMAT_VERSION: Final[int] = 1
BUSY_TIMEOUT_SECONDS: Final[float] = 5.0

SHORT_ID_MAX_LENGTH: Final[int] = 51
DEFAULT_SHORT_ID_LENGTH: Final[int] = 10
_GROUPS: Final[int] = 52

CACHE_DIRECTORY_NAME: Final[str] = "db"
CACHE_FILE_NAME: Final[str] = "cache.db"

_IDS_TABLE: Final[str] = "cache_native_ids"

_LOCKED_MESSAGE: Final[str] = "the native id cache is locked by another process"
_LOCKED_HINT: Final[str] = (
    "close the process that holds ~/.mailquery/db/cache.db and run the command again"
)
_PERMISSION_MESSAGE: Final[str] = "no permission to read or write the native id cache"
_PERMISSION_HINT: Final[str] = (
    "check the permissions of ~/.mailquery/db/ and ~/.mailquery/db/cache.db"
)
_IO_HINT: Final[str] = (
    "if you delete ~/.mailquery/db/cache.db, mailquery creates an empty one; uids "
    "already printed do not resolve until you repeat the search"
)
_CONFLICT_DETAIL: Final[str] = "conflicting uid part"
_INVALID_DETAIL: Final[str] = "not a valid native id cache"

_PART_PATTERN: Final[re.Pattern[str]] = re.compile(r"([0-9a-z]+)(?:-([1-9][0-9]*))?\Z")

_CREATE_IDS: Final[str] = f"""
CREATE TABLE {_IDS_TABLE} (
    driver TEXT NOT NULL,
    short_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    native_id TEXT NOT NULL,
    PRIMARY KEY (driver, short_id, seq),
    UNIQUE (driver, native_id)
)
"""


def short_id(text: str, length: int) -> str:
    """Return the first ``length`` characters of the base32 encoding of ``SHA-256(text)``.

    The text is encoded as UTF-8. Bits are read in groups of five from the most
    significant one, the last group is padded with zeros and the result uses
    :data:`ALPHABET` without any filler. ``length`` must be an integer from 1 to
    :data:`SHORT_ID_MAX_LENGTH` and ``text`` must be a ``str``; anything else
    raises :class:`ValueError`.
    """
    if not isinstance(text, str):
        raise ValueError("text must be a string")
    if not isinstance(length, int) or isinstance(length, bool):
        raise ValueError("length must be an integer")
    if not 1 <= length <= SHORT_ID_MAX_LENGTH:
        raise ValueError(
            f"length must be between 1 and {SHORT_ID_MAX_LENGTH}, got {length}"
        )
    import hashlib

    digest = hashlib.sha256(text.encode("utf-8")).digest()
    # 52 groups of 5 bits cover the 256-bit digest with four trailing zero bits.
    value = int.from_bytes(digest, "big") << (_GROUPS * 5 - 256)
    encoded = "".join(
        ALPHABET[(value >> (5 * (_GROUPS - 1 - index))) & 0x1F]
        for index in range(_GROUPS)
    )
    return encoded[:length]


def cache_path(home: Path) -> Path:
    """Return ``home / "db" / "cache.db"``."""
    return Path(home) / CACHE_DIRECTORY_NAME / CACHE_FILE_NAME


def _locked() -> MailqueryError:
    return MailqueryError(
        "E_LOCKED",
        _LOCKED_MESSAGE,
        _LOCKED_HINT,
        "native id cache is locked",
    )


def _permission_denied() -> MailqueryError:
    return MailqueryError(
        "E_PERMISSION",
        _PERMISSION_MESSAGE,
        _PERMISSION_HINT,
        "no permission for the native id cache",
    )


def _io(detail: str) -> MailqueryError:
    return MailqueryError(
        "E_IO",
        f"cannot use the native id cache: {detail}",
        _IO_HINT,
        "cannot use the native id cache",
    )


def _invalid_cache() -> MailqueryError:
    return _io(_INVALID_DETAIL)


def _access_denied(path: Path | None) -> bool:
    if path is None:
        return False
    if path.exists() and not os.access(path, os.R_OK | os.W_OK):
        return True
    return not os.access(path.parent, os.R_OK | os.W_OK | os.X_OK)


def _classify_sqlite_error(exc: sqlite3.Error, path: Path | None) -> MailqueryError:
    """Map a SQLite failure to ``E_LOCKED``, ``E_PERMISSION`` or ``E_IO``."""
    if _is_busy(exc):
        return _locked()
    code = getattr(exc, "sqlite_errorcode", -1)
    base = code & 0xFF if isinstance(code, int) else -1
    if base in (
        sqlite3.SQLITE_PERM,
        sqlite3.SQLITE_READONLY,
        sqlite3.SQLITE_CANTOPEN,
    ) and _access_denied(path):
        return _permission_denied()
    return _io(f"cannot use {CACHE_FILE_NAME}")


def _connect(path: Path | None) -> sqlite3.Connection:
    """Open one SQLite connection; ``None`` opens an in-memory database."""
    if path is None:
        connection = sqlite3.connect(
            ":memory:", isolation_level=None, check_same_thread=False
        )
    else:
        connection = sqlite3.connect(
            str(path),
            timeout=BUSY_TIMEOUT_SECONDS,
            isolation_level=None,
            check_same_thread=False,
        )
    timeout_ms = int(max(0.0, BUSY_TIMEOUT_SECONDS) * 1000)
    connection.execute(f"PRAGMA busy_timeout = {timeout_ms}")
    return connection


def _ensure_directory(directory: Path) -> None:
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except PermissionError as exc:
        raise _permission_denied() from exc
    except OSError as exc:
        raise _io("cannot create the native id cache directory") from exc


def _check_access(directory: Path, file_path: Path) -> None:
    if not os.access(directory, os.R_OK | os.W_OK | os.X_OK):
        raise _permission_denied()
    if file_path.exists() and not (
        os.access(file_path, os.R_OK) and os.access(file_path, os.W_OK)
    ):
        raise _permission_denied()


def _apply_permissions(directory: Path, file_path: Path) -> None:
    try:
        os.chmod(directory, 0o700)
    except PermissionError as exc:
        raise _permission_denied() from exc
    except OSError as exc:
        raise _io("cannot set the native id cache directory permissions") from exc
    try:
        os.chmod(file_path, 0o600)
    except PermissionError as exc:
        raise _permission_denied() from exc
    except OSError as exc:
        raise _io("cannot set the native id cache file permissions") from exc


def _user_tables(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {row[0] for row in rows}


def _is_busy(exc: sqlite3.Error) -> bool:
    code = getattr(exc, "sqlite_errorcode", -1)
    base = code & 0xFF if isinstance(code, int) else -1
    return base in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)


def _read_format(connection: sqlite3.Connection) -> tuple[int, set[str]]:
    """Return the format version and the user tables of the database.

    A database that another process keeps locked past the busy timeout fails
    with ``E_LOCKED``; any other read failure means the file is not a cache.
    """
    try:
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        tables = _user_tables(connection)
    except sqlite3.Error as exc:
        if _is_busy(exc):
            raise _locked() from exc
        raise _invalid_cache() from exc
    return version, tables


def _create_schema(connection: sqlite3.Connection, *, recheck: bool = False) -> None:
    """Create the table and store the format version in one transaction.

    With ``recheck`` the format is read again once the write lock is held: a
    database that another connection initialized in the meantime is left as it
    is, and one that holds anything else is rejected.
    """
    try:
        connection.execute("BEGIN IMMEDIATE")
        if recheck:
            version, tables = _read_format(connection)
            if version == FORMAT_VERSION and _IDS_TABLE in tables:
                connection.execute("COMMIT")
                return
            if version != 0 or tables:
                raise _invalid_cache()
        connection.execute(_CREATE_IDS)
        connection.execute(f"PRAGMA user_version = {FORMAT_VERSION}")
        connection.execute("COMMIT")
    except BaseException:
        _rollback_quietly(connection)
        raise


def _prepare_file_cache(connection: sqlite3.Connection) -> None:
    version, tables = _read_format(connection)
    if version == 0:
        _create_schema(connection, recheck=True)
    elif version == FORMAT_VERSION:
        if _IDS_TABLE not in tables:
            raise _invalid_cache()
    else:
        raise _invalid_cache()
    connection.execute("PRAGMA journal_mode = WAL")


def _prepare_memory_cache(connection: sqlite3.Connection) -> None:
    _create_schema(connection)


def _rollback_quietly(connection: sqlite3.Connection) -> None:
    try:
        connection.execute("ROLLBACK")
    except sqlite3.Error:
        pass


def _format_part(short: str, seq: int) -> str:
    return short if seq == 1 else f"{short}-{seq}"


def _split_part(part: object) -> tuple[str, int] | None:
    """Parse ``<short_id>`` or ``<short_id>-<seq>``; ``None`` when it is not a part."""
    if not isinstance(part, str):
        return None
    match = _PART_PATTERN.fullmatch(part)
    if match is None:
        return None
    short = match.group(1)
    if any(character not in ALPHABET for character in short):
        return None
    seq_text = match.group(2)
    if seq_text is None:
        return short, 1
    seq = int(seq_text)
    if seq <= 1:
        return None
    return short, seq


class NativeIdCache:
    """SQLite cache of ``driver``/``short_id``/``seq`` rows for one driver.

    Every method reads or writes only the rows of the driver given to
    :meth:`open`. :meth:`assign` is read-only; :meth:`register` writes all the
    pending rows in one transaction; :meth:`discard` deletes one row.
    """

    def __init__(
        self,
        connection: sqlite3.Connection,
        driver: str,
        *,
        path: Path | None = None,
    ) -> None:
        self._connection = connection
        self._driver = driver
        self._path = path
        self._lock = threading.RLock()
        self._assigned: dict[str, tuple[str, int]] = {}
        self._execution_max: dict[str, int] = {}
        self._closed = False

    @classmethod
    def open(cls, driver: str, *, home: Path) -> "NativeIdCache":
        """Open ``<home>/db/cache.db`` for ``driver``, creating the folder and file.

        A missing or empty database is initialized with its table and
        :data:`FORMAT_VERSION`; a database with another format is rejected.
        """
        if not is_valid_driver(driver):
            raise ValueError(f"invalid driver name: {driver!r}")
        home_path = Path(home)
        path = cache_path(home_path)
        directory = path.parent
        _ensure_directory(directory)
        _check_access(directory, path)
        try:
            connection = _connect(path)
        except PermissionError as exc:
            raise _permission_denied() from exc
        except sqlite3.Error as exc:
            raise _classify_sqlite_error(exc, path) from exc
        except OSError as exc:
            raise _io("cannot open the native id cache file") from exc
        try:
            _prepare_file_cache(connection)
            _apply_permissions(directory, path)
        except MailqueryError:
            connection.close()
            raise
        except sqlite3.Error as exc:
            connection.close()
            raise _classify_sqlite_error(exc, path) from exc
        except BaseException:
            connection.close()
            raise
        return cls(connection, driver, path=path)

    @classmethod
    def open_in_memory(cls, driver: str) -> "NativeIdCache":
        """Open an empty in-memory cache for ``driver``; no file is created."""
        if not is_valid_driver(driver):
            raise ValueError(f"invalid driver name: {driver!r}")
        try:
            connection = _connect(None)
        except sqlite3.Error as exc:
            raise _classify_sqlite_error(exc, None) from exc
        try:
            _prepare_memory_cache(connection)
        except sqlite3.Error as exc:
            connection.close()
            raise _classify_sqlite_error(exc, None) from exc
        except BaseException:
            connection.close()
            raise
        return cls(connection, driver, path=None)

    @property
    def driver(self) -> str:
        """Driver whose rows this cache exposes."""
        return self._driver

    @property
    def path(self) -> Path | None:
        """File behind this cache, or ``None`` for an in-memory cache."""
        return self._path

    def assign(
        self, native_ids: Sequence[str], *, length: int = DEFAULT_SHORT_ID_LENGTH
    ) -> dict[str, str]:
        """Return the uid part of each native id, without writing.

        A native id already registered or assigned earlier in this execution
        keeps its part. A new one receives the short id plus the next ``seq`` of
        its driver and short id; new native ids that share a short id take their
        ``seq`` in the order of their native id, whatever order the sequence
        arrives in.
        """
        with self._lock:
            self._ensure_open()
            values = list(native_ids)
            for native_id in values:
                if not isinstance(native_id, str) or not native_id:
                    raise ValueError(f"invalid native id: {native_id!r}")
            parts: dict[str, str] = {}
            for native_id in sorted(set(values)):
                parts[native_id] = _format_part(*self._assign_one(native_id, length))
            return parts

    def register(self, native_ids: Sequence[str]) -> None:
        """Store every pending native id of ``native_ids`` in one transaction.

        An id that already has its row with the same part is left untouched. A
        part already owned by another native id, an id with a different part or
        an id without a part in this execution fails with ``E_IO`` and stores
        nothing.
        """
        with self._lock:
            self._ensure_open()
            try:
                self._connection.execute("BEGIN IMMEDIATE")
            except sqlite3.Error as exc:
                raise _classify_sqlite_error(exc, self._path) from exc
            try:
                for native_id in native_ids:
                    if not isinstance(native_id, str) or not native_id:
                        raise ValueError(f"invalid native id: {native_id!r}")
                    self._register_one(native_id)
                self._connection.execute("COMMIT")
            except sqlite3.Error as exc:
                _rollback_quietly(self._connection)
                raise _classify_sqlite_error(exc, self._path) from exc
            except BaseException:
                _rollback_quietly(self._connection)
                raise

    def resolve(self, uid_part: str) -> str | None:
        """Return the native id registered for ``uid_part``, or ``None``."""
        with self._lock:
            self._ensure_open()
            parsed = _split_part(uid_part)
            if parsed is None:
                return None
            short, seq = parsed
            row = self._fetch_one(
                f"SELECT native_id FROM {_IDS_TABLE} "
                "WHERE driver = ? AND short_id = ? AND seq = ?",
                (self._driver, short, seq),
            )
            return None if row is None else str(row[0])

    def discard(self, native_id: str) -> None:
        """Delete the row of ``native_id``; the highest ``seq`` of a pair becomes free."""
        with self._lock:
            self._ensure_open()
            try:
                self._connection.execute(
                    f"DELETE FROM {_IDS_TABLE} WHERE driver = ? AND native_id = ?",
                    (self._driver, native_id),
                )
            except sqlite3.Error as exc:
                raise _classify_sqlite_error(exc, self._path) from exc

    def close(self) -> None:
        """Close the connection; calling it more than once is harmless."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            try:
                self._connection.close()
            except sqlite3.Error as exc:
                raise _classify_sqlite_error(exc, self._path) from exc

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("the native id cache is closed")

    def _fetch_one(
        self, sql: str, parameters: tuple[object, ...]
    ) -> tuple[object, ...] | None:
        try:
            return self._connection.execute(sql, parameters).fetchone()
        except sqlite3.Error as exc:
            raise _classify_sqlite_error(exc, self._path) from exc

    def _row_part(self, native_id: str) -> tuple[str, int] | None:
        row = self._fetch_one(
            f"SELECT short_id, seq FROM {_IDS_TABLE} "
            "WHERE driver = ? AND native_id = ?",
            (self._driver, native_id),
        )
        if row is None:
            return None
        return str(row[0]), int(row[1])

    def _max_registered_seq(self, short: str) -> int:
        row = self._fetch_one(
            f"SELECT MAX(seq) FROM {_IDS_TABLE} WHERE driver = ? AND short_id = ?",
            (self._driver, short),
        )
        return 0 if row is None or row[0] is None else int(row[0])

    def _assign_one(self, native_id: str, length: int) -> tuple[str, int]:
        known = self._assigned.get(native_id)
        if known is not None:
            return known
        row_part = self._row_part(native_id)
        if row_part is not None:
            self._assigned[native_id] = row_part
            self._note_execution_seq(*row_part)
            return row_part
        short = short_id(native_id, length)
        seq = (
            max(self._max_registered_seq(short), self._execution_max.get(short, 0)) + 1
        )
        part = (short, seq)
        self._assigned[native_id] = part
        self._note_execution_seq(short, seq)
        return part

    def _note_execution_seq(self, short: str, seq: int) -> None:
        current = self._execution_max.get(short, 0)
        if seq > current:
            self._execution_max[short] = seq

    def _register_one(self, native_id: str) -> None:
        assigned = self._assigned.get(native_id)
        if assigned is None:
            raise _io(_CONFLICT_DETAIL)
        short, seq = assigned
        row_part = self._row_part(native_id)
        if row_part is not None:
            if row_part != assigned:
                raise _io(_CONFLICT_DETAIL)
            return
        owner = self._fetch_one(
            f"SELECT native_id FROM {_IDS_TABLE} "
            "WHERE driver = ? AND short_id = ? AND seq = ?",
            (self._driver, short, seq),
        )
        if owner is not None:
            raise _io(_CONFLICT_DETAIL)
        self._connection.execute(
            f"INSERT INTO {_IDS_TABLE} (driver, short_id, seq, native_id) "
            "VALUES (?, ?, ?, ?)",
            (self._driver, short, seq, native_id),
        )


def _plugin_error_from(exc: MailqueryError) -> Exception:
    """Translate a cache failure to the plugin protocol, importing it lazily."""
    from mailquery.plugins.api import PluginError, Reason

    if exc.code == "E_LOCKED":
        return PluginError(
            Reason.BUSY,
            hint=_LOCKED_HINT,
            log_message="native id cache is locked",
        )
    if exc.code == "E_PERMISSION":
        return PluginError(
            Reason.PERMISSION,
            hint=_PERMISSION_HINT,
            log_message="no permission for the native id cache",
        )
    return exc


class PluginNativeIds:
    """Plugin access to the cache of its own driver.

    The database is opened on the first operation, not in the constructor. Every
    failure is translated to the plugin error protocol: a locked cache becomes
    ``busy``, a permission failure becomes ``permission`` and any other failure
    stays an exception that the core reports as a plugin failure.
    """

    def __init__(self, home: Path, driver: str) -> None:
        self._home = Path(home)
        self._driver = driver
        self._lock = threading.Lock()
        self._cache: NativeIdCache | None = None

    @property
    def driver(self) -> str:
        """Driver whose rows this access exposes."""
        return self._driver

    def assign(self, native_ids: Sequence[str]) -> dict[str, str]:
        """Return the uid part of each native id, without writing."""
        return self._run(lambda cache: cache.assign(native_ids))

    def register(self, native_ids: Sequence[str]) -> None:
        """Store every pending native id of ``native_ids`` in one transaction."""
        self._run(lambda cache: cache.register(native_ids))

    def resolve(self, uid_part: str) -> str | None:
        """Return the native id registered for ``uid_part``, or ``None``."""
        return self._run(lambda cache: cache.resolve(uid_part))

    def discard(self, native_id: str) -> None:
        """Delete the row of ``native_id``."""
        self._run(lambda cache: cache.discard(native_id))

    def close(self) -> None:
        """Close the connection; the next operation opens the database again."""
        with self._lock:
            cache, self._cache = self._cache, None
            if cache is None:
                return
            try:
                cache.close()
            except MailqueryError as exc:
                raise _plugin_error_from(exc) from exc

    def _run(self, operation):
        with self._lock:
            try:
                cache = self._cache
                if cache is None:
                    cache = NativeIdCache.open(self._driver, home=self._home)
                    self._cache = cache
                return operation(cache)
            except MailqueryError as exc:
                raise _plugin_error_from(exc) from exc


__all__ = [
    "ALPHABET",
    "BUSY_TIMEOUT_SECONDS",
    "CACHE_DIRECTORY_NAME",
    "CACHE_FILE_NAME",
    "DEFAULT_SHORT_ID_LENGTH",
    "FORMAT_VERSION",
    "NativeIdCache",
    "PluginNativeIds",
    "SHORT_ID_MAX_LENGTH",
    "cache_path",
    "short_id",
]

"""Persistent cursor state and run lock.

State lives in ``~/.mailquery/state.json`` only, schema 2: the
``new`` cursor ``(last_date_received, last_uid)``, the ring of the last 1.000
emitted uids and the last run metadata. Uids are opaque prefixed strings
``"<driver>:<native_id>"``; a schema-1 file (integer Apple Mail uids or
upper-case hexadecimal Outlook ``EntryID``) is migrated in memory by value type
and persisted as schema 2 by the next non-``--peek`` ``new`` run. Writes are
atomic (temporary + fsync + ``os.replace``) with mode 0600, and the file never
contains subjects, bodies or addresses.
"""

from __future__ import annotations

import errno
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

from mailquery import uid as uid_module
from mailquery.errors import MailqueryError
from mailquery.output import now_iso

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

MAX_EMITTED_UIDS = 1000
STATE_SCHEMA = 2
"""Current ``state.json`` schema."""

SUPPORTED_SCHEMAS = (1, 2)

STATE_FILENAME = "state.json"
LOCK_DIRNAME = "locks"
LOCK_FILENAME = "mailquery.lock"
DEFAULT_LOOKBACK_SECONDS = 600

#: Shape of a legacy Outlook ``EntryID`` (upper-case hexadecimal).
_LEGACY_HEX_UID = re.compile(r"[0-9A-F]+")

_RENAME_HINT = (
    "rename ~/.mailquery/state.json (for example to state.json.bak): the "
    "next 'mailquery new' is a first run that emits the messages of the "
    "lookback window"
)
_MISSING_DRIVER_HINT = (
    "reinstall the plugin that provides the driver, or rename "
    "~/.mailquery/state.json (for example to state.json.bak): the next "
    "'mailquery new' is a first run that emits the messages of the lookback window"
)

#: ``state.json`` uid validator: whether a driver name is installed (registry).
UidInstalled = Callable[[str], bool]


@dataclass(frozen=True)
class Cursor:
    """Watermark for ``mailquery new``; ``last_uid`` is a prefixed uid string."""

    last_date_received: int
    last_uid: str
    lookback_seconds: int = DEFAULT_LOOKBACK_SECONDS


@dataclass(frozen=True)
class LastRun:
    command: str
    at: str


@dataclass(frozen=True)
class AppState:
    """In-memory view of ``state.json`` (always schema 2 after :meth:`StateStore.load`)."""

    schema: int = STATE_SCHEMA
    updated_at: str = ""
    last_run: LastRun | None = None
    cursor: Cursor | None = None
    emitted_uids: tuple[str, ...] = ()


@dataclass(frozen=True)
class EmittedUid:
    """One uid a ``new`` run emits, with the keys of the total order.

    ``native_order_key`` is the backend row's key already typed by the core: an
    ``int`` for a ``numeric`` driver (Apple Mail) and a ``str`` for a ``text``
    driver (Outlook and plugins). ``driver`` is part of the sort key so a future
    multi-driver cursor advances with ``(date_received, driver, native_order_key)``
    and never compares the uid as text.
    """

    date_received: int
    driver: str
    native_order_key: int | str
    uid: str


@dataclass(frozen=True)
class StateLoadInfo:
    """What :meth:`StateStore.load` found on disk (for the ``state`` check of ``doctor``)."""

    exists: bool = False
    persisted_schema: int | None = None
    migrated: bool = False
    pruned_emitted_uids: int = 0
    pruned_drivers: tuple[str, ...] = field(default=())

    @property
    def migration_pending(self) -> bool:
        """A schema-1 file was read and migrated in memory but not persisted yet."""
        return self.exists and self.persisted_schema == 1


class _MissingFile(Exception):
    """Internal marker raised when ``state.json`` does not exist yet."""


class StateStore:
    """Load/save ``state.json`` atomically.

    ``load`` is tolerant with missing keys (they take defaults) and
    with unknown keys (they are ignored), but it is strict about the file being
    a JSON object with a known ``schema`` and about the types of the known
    fields: a damaged state must fail loudly with ``E_STATE_CORRUPT``
    instead of silently re-baselining and re-emitting a window of mail.

    A ``schema: 1`` file is migrated **in memory** to schema 2: integer uids
    ``>= 1`` become ``apple_mail:<n>`` and upper-case hexadecimal strings become
    ``outlook:<HEX>``, independent of the platform. The
    resulting uids are then validated like any schema-2 uid, with
    ``is_installed`` (the registry) for the driver part: a ``cursor.last_uid``
    whose driver is not installed is ``E_STATE_CORRUPT``, while ring items of
    drivers that are not installed are pruned in silence and reported by
    :attr:`load_info`.
    """

    def __init__(self, home: Path, is_installed: UidInstalled) -> None:
        self._home = Path(home)
        self._is_installed = is_installed
        self._load_info = StateLoadInfo()

    @property
    def home(self) -> Path:
        return self._home

    @property
    def path(self) -> Path:
        return self._home / STATE_FILENAME

    @property
    def load_info(self) -> StateLoadInfo:
        """Result metadata of the last :meth:`load` (``exists``/schema/pruning)."""
        return self._load_info

    def load(self) -> AppState:
        """Load state; raises E_STATE_CORRUPT when the file is unreadable."""
        path = self.path
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            self._load_info = StateLoadInfo()
            return AppState()
        except (UnicodeDecodeError, UnicodeError) as exc:
            raise _corrupt(f"the file is not valid UTF-8 ({exc})") from exc
        except PermissionError as exc:
            raise MailqueryError(
                "E_PERMISSION",
                f"cannot read state file: {path}",
                "check that ~/.mailquery is readable by the current user "
                "(it must be mode 0700 and owned by the invoking account)",
                "cannot read the state file",
            ) from exc
        except OSError as exc:
            raise _corrupt(f"cannot read {path} ({exc.strerror or exc})") from exc

        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise _corrupt(f"invalid JSON ({exc})") from exc

        if not isinstance(payload, dict):
            raise _corrupt("the top-level value must be a JSON object")
        state, info = _state_from_payload(payload, self._is_installed)
        self._load_info = info
        return state

    def save(self, state: AppState) -> None:
        """Atomically persist ``state`` as schema-2 ``0600`` JSON."""
        path = self.path
        directory = path.parent
        try:
            directory.mkdir(parents=True, exist_ok=True)
            _chmod(directory, 0o700)
        except OSError as exc:
            raise MailqueryError(
                "E_PERMISSION",
                f"cannot create the application home: {directory}",
                "check the permissions of the parent directory",
                "cannot create the application home",
            ) from exc

        data = json.dumps(_state_to_payload(state), ensure_ascii=False, indent=2) + "\n"
        tmp_path = self._write_temp(directory, data)
        try:
            os.replace(tmp_path, path)
        except OSError as exc:
            _unlink_quietly(tmp_path)
            mapped = _write_error(exc, directory)
            if mapped is None:
                raise
            raise mapped from exc
        _fsync_dir(directory)

    @staticmethod
    def _write_temp(directory: Path, data: str) -> Path:
        """Write ``data`` to a 0600 temporary file in ``directory`` and fsync it."""
        try:
            fd, tmp_name = tempfile.mkstemp(prefix=".state-", suffix=".tmp", dir=directory)
        except OSError as exc:
            if exc.errno == errno.ENOSPC:
                raise _write_error(exc, directory) from exc
            raise MailqueryError(
                "E_PERMISSION",
                f"cannot create a temporary state file in {directory}",
                "check that ~/.mailquery is writable by the current user",
                "cannot create a temporary state file",
            ) from exc
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(tmp_path, 0o600)
        except OSError as exc:
            _unlink_quietly(tmp_path)
            mapped = _write_error(exc, directory)
            if mapped is None:
                raise
            raise mapped from exc
        except BaseException:
            _unlink_quietly(tmp_path)
            raise
        return tmp_path

    def record_new(
        self,
        state: AppState,
        emitted: Sequence[EmittedUid],
        lookback_seconds: int,
        command: str = "new",
    ) -> AppState:
        """Advance the cursor and the emitted-uid ring, returning the new state.

        ``emitted`` holds the uids this run emits, each with its
        ``(date_received, driver, native_order_key)`` total-order key. The cursor
        only ever moves forward (a Mail index rebuild may change uids but never the
        dates); ``lookback_seconds``
        is the lookback of the current config and is the one stored in
        the cursor, and the emitted uids are appended to the ring in total order
        (newest last) capped at 1.000 entries.

        This method does **not** persist the new state: the caller
        (``search.run_new``) saves it only when the run is not ``--peek``, so a
        peek can never advance the cursor.
        """
        entries = list(emitted)
        previous = state.cursor
        lookback = int(lookback_seconds)

        cursor = previous
        if previous is not None and previous.lookback_seconds != lookback:
            cursor = Cursor(
                last_date_received=previous.last_date_received,
                last_uid=previous.last_uid,
                lookback_seconds=lookback,
            )
        if entries:
            newest = max(entries, key=_emitted_order_key)
            if previous is None or _advances(newest, previous):
                cursor = Cursor(
                    last_date_received=newest.date_received,
                    last_uid=newest.uid,
                    lookback_seconds=lookback,
                )

        ring = _advance_ring(state.emitted_uids, entries)
        timestamp = now_iso()
        return AppState(
            schema=STATE_SCHEMA,
            updated_at=timestamp,
            last_run=LastRun(command=command, at=timestamp),
            cursor=cursor,
            emitted_uids=ring,
        )


def migrate_uid(value: object) -> str:
    """Pure schema-1 -> schema-2 uid conversion.

    Deterministic by the value type and independent of the platform: an integer
    ``>= 1`` becomes ``apple_mail:<n>`` and an upper-case hexadecimal string
    becomes ``outlook:<HEX>``; anything else (``0``, negatives, ``bool``,
    ``None``, lists, lower-case or non-hex formats) is ``E_STATE_CORRUPT``.
    """
    return _migrate_legacy_uid(value, "uid")


def _write_error(exc: OSError, directory: Path) -> MailqueryError | None:
    """Map a failed state write: ENOSPC is internal, EACCES/EPERM a permission error.

    Returns ``None`` for any other I/O error, which keeps its current handling.
    The previous ``state.json`` is never touched by a failed write.
    """
    if exc.errno == errno.ENOSPC:
        return MailqueryError(
            "E_INTERNAL",
            f"no space left on the device to write the state file in {directory}",
            "free disk space and retry; the previous cursor was not changed",
            "no space left on the device to write the state file",
        )
    if exc.errno in (errno.EACCES, errno.EPERM):
        return MailqueryError(
            "E_PERMISSION",
            f"cannot write the state file in {directory}: {exc.strerror or exc}",
            "check that ~/.mailquery is writable by the current user",
            "cannot write the state file",
        )
    return None


def _lock_fd(fd: int) -> None:
    """Take a non-blocking exclusive lock on ``fd``; raise ``OSError`` if held."""
    if sys.platform == "win32":
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_fd(fd: int) -> None:
    if sys.platform == "win32":
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)


class RunLock:
    """Non-blocking lock under ``~/.mailquery/locks``.

    Uses ``fcntl.flock`` on POSIX and ``msvcrt.locking`` on Windows.

    Every invocation takes the lock before touching the store so two harness
    calls cannot overlap. A contended lock raises ``E_LOCKED``
    (exit 5) immediately; the harness may retry.
    """

    def __init__(self, home: Path) -> None:
        self._home = Path(home)
        self._fd: int | None = None

    @property
    def path(self) -> Path:
        return self._home / LOCK_DIRNAME / LOCK_FILENAME

    def acquire(self) -> None:
        """Acquire the lock or raise E_LOCKED (exit 5)."""
        if self._fd is not None:
            return
        path = self.path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            _chmod(path.parent, 0o700)
            fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        except OSError as exc:
            raise MailqueryError(
                "E_PERMISSION",
                f"cannot open the run lock: {path}",
                "check that ~/.mailquery is writable by the current user",
                "cannot open the run lock",
            ) from exc
        try:
            os.chmod(path, 0o600)
        except OSError:  # pragma: no cover - best effort on foreign filesystems
            pass
        try:
            _lock_fd(fd)
        except OSError as exc:
            os.close(fd)
            raise MailqueryError(
                "E_LOCKED",
                "another mailquery run is already in progress",
                "wait for the running invocation to finish and retry "
                "(the harness should only retry exit code 5)",
            ) from exc
        self._fd = fd

    def release(self) -> None:
        fd = self._fd
        if fd is None:
            return
        self._fd = None
        try:
            _unlock_fd(fd)
        finally:
            os.close(fd)

    def __enter__(self) -> "RunLock":
        self.acquire()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.release()


# --------------------------------------------------------------------------- #
# Serialization helpers
# --------------------------------------------------------------------------- #


def _state_to_payload(state: AppState) -> dict:
    """Render ``AppState`` as the stable schema-2 ``state.json`` object (no PII)."""
    return {
        "schema": STATE_SCHEMA,
        "updated_at": state.updated_at,
        "last_run": (
            None
            if state.last_run is None
            else {"command": state.last_run.command, "at": state.last_run.at}
        ),
        "cursor": (
            None
            if state.cursor is None
            else {
                "last_date_received": state.cursor.last_date_received,
                "last_uid": state.cursor.last_uid,
                "lookback_seconds": state.cursor.lookback_seconds,
            }
        ),
        "emitted_uids": list(state.emitted_uids),
    }


def _state_from_payload(
    payload: dict, is_installed: UidInstalled
) -> tuple[AppState, StateLoadInfo]:
    """Build ``(AppState, StateLoadInfo)`` from raw JSON, raising E_STATE_CORRUPT."""
    schema = _schema_from_payload(payload)
    legacy = schema == 1

    updated_at = payload.get("updated_at", "")
    if updated_at is None:
        updated_at = ""
    if not isinstance(updated_at, str):
        raise _corrupt("'updated_at' must be a string")

    last_run = _last_run_from_payload(payload.get("last_run"))
    cursor = _cursor_from_payload(payload.get("cursor"), legacy=legacy, is_installed=is_installed)
    emitted_uids, pruned, pruned_drivers = _ring_from_payload(
        payload.get("emitted_uids", []), legacy=legacy, is_installed=is_installed
    )

    state = AppState(
        schema=STATE_SCHEMA,
        updated_at=updated_at,
        last_run=last_run,
        cursor=cursor,
        emitted_uids=emitted_uids,
    )
    info = StateLoadInfo(
        exists=True,
        persisted_schema=schema,
        migrated=legacy,
        pruned_emitted_uids=pruned,
        pruned_drivers=pruned_drivers,
    )
    return state, info


def _schema_from_payload(payload: dict) -> int:
    """Required ``schema`` key: 1 (migrated in memory) or 2; anything else is corrupt."""
    if "schema" not in payload:
        raise _corrupt("'schema' is required (expected 1 or 2)")
    schema = payload["schema"]
    if isinstance(schema, bool) or not isinstance(schema, int) or schema not in SUPPORTED_SCHEMAS:
        raise _corrupt(f"unsupported schema {schema!r} (expected 1 or 2)")
    return schema


def _last_run_from_payload(value: object) -> LastRun | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise _corrupt("'last_run' must be an object")
    command = value.get("command")
    at = value.get("at")
    if not isinstance(command, str) or not isinstance(at, str):
        raise _corrupt("'last_run' must contain string 'command' and 'at'")
    return LastRun(command=command, at=at)


def _cursor_from_payload(
    value: object, *, legacy: bool, is_installed: UidInstalled
) -> Cursor | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise _corrupt("'cursor' must be an object")
    date = value.get("last_date_received")
    lookback = value.get("lookback_seconds", DEFAULT_LOOKBACK_SECONDS)
    if not _is_int(date) or not _is_int(lookback):
        raise _corrupt(
            "'cursor' must hold integer 'last_date_received' and 'last_uid'"
        )
    if date < 0:
        raise _corrupt("'cursor.last_date_received' must not be negative")
    uid = _state_uid(value.get("last_uid"), "'cursor.last_uid'", legacy=legacy)
    _require_installed(uid.driver, "'cursor.last_uid'", is_installed)
    if lookback < 1:
        raise _corrupt("'cursor.lookback_seconds' must be positive")
    return Cursor(
        last_date_received=date,
        last_uid=uid.uid,
        lookback_seconds=lookback,
    )


def _ring_from_payload(
    value: object, *, legacy: bool, is_installed: UidInstalled
) -> tuple[tuple[str, ...], int, tuple[str, ...]]:
    """Validate the ring and drop the uids of drivers that are not installed."""
    if value is None:
        return (), 0, ()
    if not isinstance(value, list):
        raise _corrupt("'emitted_uids' must be a list of prefixed uids")
    uids: list[str] = []
    pruned = 0
    pruned_drivers: set[str] = set()
    for index, item in enumerate(value):
        uid = _state_uid(item, f"'emitted_uids[{index}]'", legacy=legacy)
        if not is_installed(uid.driver):
            pruned += 1
            pruned_drivers.add(uid.driver)
            continue
        uids.append(uid.uid)
    return tuple(uids[-MAX_EMITTED_UIDS:]), pruned, tuple(sorted(pruned_drivers))


def _state_uid(value: object, field: str, *, legacy: bool) -> uid_module.ParsedUid:
    """Migrate (schema 1) or validate (schema 2) one ``state.json`` uid."""
    if legacy:
        prefixed = _migrate_legacy_uid(value, field)
    else:
        if not isinstance(value, str) or not value:
            raise _corrupt(
                f"{field} must be a prefixed uid string '<driver>:<native_id>'"
            )
        if ":" not in value:
            raise _corrupt(
                f"{field} is not a prefixed uid ('<driver>:<native_id>'): the "
                "legacy unprefixed form is only accepted in command arguments"
            )
        prefixed = value
    try:
        return uid_module.parse_uid(prefixed)
    except MailqueryError as exc:
        raise _corrupt(f"{field} is not a valid prefixed uid ({exc.message})") from exc


def _migrate_legacy_uid(value: object, field: str) -> str:
    """Deterministic schema-1 uid conversion by value type."""
    if isinstance(value, int) and not isinstance(value, bool) and value >= 1:
        return f"apple_mail:{value}"
    if isinstance(value, str) and _LEGACY_HEX_UID.fullmatch(value) is not None:
        return f"outlook:{value}"
    raise _corrupt(
        f"{field} is not a schema-1 uid: expected an integer >= 1 (Apple Mail) "
        "or an upper-case hexadecimal EntryID string (Outlook)"
    )


def _require_installed(driver: str, field: str, is_installed: UidInstalled) -> None:
    if not is_installed(driver):
        raise _corrupt(
            f"{field} uses driver {driver!r}, which is not installed",
            hint=_MISSING_DRIVER_HINT,
        )


def _advance_ring(
    current: Sequence[str],
    entries: Sequence[EmittedUid],
) -> tuple[str, ...]:
    """Append emitted uids in total order, caps the ring at 1.000."""
    ring = list(current)
    for entry in sorted(entries, key=_emitted_order_key):
        if entry.uid in ring:
            ring.remove(entry.uid)
        ring.append(entry.uid)
    if len(ring) > MAX_EMITTED_UIDS:
        ring = ring[-MAX_EMITTED_UIDS:]
    return tuple(ring)


def _emitted_order_key(entry: EmittedUid) -> tuple[int, str, int | str]:
    """Total order key of one emitted uid."""
    return (entry.date_received, entry.driver, entry.native_order_key)


def _advances(newest: EmittedUid, previous: Cursor) -> bool:
    """Whether the cursor may advance to ``newest`` (it only ever moves forward).

    Dates are the watermark; at the same date the cursor advances when the uid
    changes (the emitted uids of one run are already in total order, so the
    candidate is the newest of that run). The uid is never compared as text.
    """
    if newest.date_received > previous.last_date_received:
        return True
    if newest.date_received < previous.last_date_received:
        return False
    return newest.uid != previous.last_uid


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _corrupt(detail: str, *, hint: str | None = None) -> MailqueryError:
    return MailqueryError(
        "E_STATE_CORRUPT",
        f"state.json is corrupt: {detail}",
        hint or _RENAME_HINT,
        "state.json is corrupt",
    )


def _chmod(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError:  # pragma: no cover - best effort on foreign filesystems
        pass


def _unlink_quietly(path: Path) -> None:
    try:
        path.unlink()
    except OSError:  # pragma: no cover - the temporary file may already be gone
        pass


def _fsync_dir(directory: Path) -> None:
    """Best-effort fsync of the directory so the rename survives a crash."""
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:  # pragma: no cover - platform dependent
        return
    try:
        os.fsync(fd)
    except OSError:  # pragma: no cover - not supported everywhere
        pass
    finally:
        os.close(fd)

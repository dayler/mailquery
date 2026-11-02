"""Persistent cursor state and run lock (PRD 11.2, 18, 21.3).

State lives in ``~/.mailquery/state.json`` only: the ``new`` cursor
``(last_date_received, last_uid)``, the ring of the last 1.000 emitted uids and
the last run metadata. Writes are atomic (temporary + fsync + ``os.replace``)
with mode 0600, and the file never contains subjects, bodies or addresses.
"""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from mailquery.errors import MailqueryError
from mailquery.output import now_iso

MAX_EMITTED_UIDS = 1000
STATE_SCHEMA = 1

STATE_FILENAME = "state.json"
LOCK_DIRNAME = "locks"
LOCK_FILENAME = "mailquery.lock"
DEFAULT_LOOKBACK_SECONDS = 600


@dataclass(frozen=True)
class Cursor:
    """Watermark for ``mailquery new``."""

    last_date_received: int
    last_uid: int
    lookback_seconds: int = DEFAULT_LOOKBACK_SECONDS


@dataclass(frozen=True)
class LastRun:
    command: str
    at: str


@dataclass(frozen=True)
class AppState:
    schema: int = STATE_SCHEMA
    updated_at: str = ""
    last_run: LastRun | None = None
    cursor: Cursor | None = None
    emitted_uids: tuple[int, ...] = ()


class _MissingFile(Exception):
    """Internal marker raised when ``state.json`` does not exist yet."""


class StateStore:
    """Load/save ``state.json`` atomically.

    ``load`` is tolerant with missing keys (they take documented defaults) and
    with unknown keys (they are ignored), but it is strict about the file being
    a JSON object with schema ``1`` and about the types of the known fields: a
    damaged state must fail loudly with ``E_STATE_CORRUPT`` (PRD 11.2) instead
    of silently re-baselining and re-emitting a window of mail.
    """

    def __init__(self, home: Path) -> None:
        self._home = Path(home)

    @property
    def home(self) -> Path:
        return self._home

    @property
    def path(self) -> Path:
        return self._home / STATE_FILENAME

    def load(self) -> AppState:
        """Load state; raises E_STATE_CORRUPT when the file is unreadable."""
        path = self.path
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return AppState()
        except (UnicodeDecodeError, UnicodeError) as exc:
            raise _corrupt(f"the file is not valid UTF-8 ({exc})") from exc
        except PermissionError as exc:
            raise MailqueryError(
                "E_PERMISSION",
                f"cannot read state file: {path}",
                "check that ~/.mailquery is readable by the current user "
                "(it must be mode 0700 and owned by the invoking account)",
            ) from exc
        except OSError as exc:
            raise _corrupt(f"cannot read {path} ({exc.strerror or exc})") from exc

        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise _corrupt(f"invalid JSON ({exc})") from exc

        if not isinstance(payload, dict):
            raise _corrupt("the top-level value must be a JSON object")
        return _state_from_payload(payload)

    def save(self, state: AppState) -> None:
        """Atomically persist ``state`` as 0600 JSON."""
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
            ) from exc

        data = json.dumps(_state_to_payload(state), ensure_ascii=False, indent=2) + "\n"
        tmp_path = self._write_temp(directory, data)
        try:
            os.replace(tmp_path, path)
        except OSError:
            _unlink_quietly(tmp_path)
            raise
        _fsync_dir(directory)

    @staticmethod
    def _write_temp(directory: Path, data: str) -> Path:
        """Write ``data`` to a 0600 temporary file in ``directory`` and fsync it."""
        try:
            fd, tmp_name = tempfile.mkstemp(prefix=".state-", suffix=".tmp", dir=directory)
        except OSError as exc:
            raise MailqueryError(
                "E_PERMISSION",
                f"cannot create a temporary state file in {directory}",
                "check that ~/.mailquery is writable by the current user",
            ) from exc
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(tmp_path, 0o600)
        except BaseException:
            _unlink_quietly(tmp_path)
            raise
        return tmp_path

    def record_new(
        self,
        state: AppState,
        emitted: Sequence[tuple[int, int]],
        command: str = "new",
    ) -> AppState:
        """Advance the cursor and the emitted-uid ring, returning the new state.

        ``emitted`` holds ``(date_received, uid)`` pairs for the messages this
        run emits. The cursor only ever moves forward (a Mail index rebuild may
        change uids but never the dates, PRD 18); the previous
        ``lookback_seconds`` is preserved, and the emitted uids are appended to
        the ring in chronological order (newest last) capped at 1.000 entries.

        This method does **not** persist the new state: the caller
        (``search.run_new``) saves it only when the run is not ``--peek``, so a
        peek can never advance the cursor (PRD 12.3, 18).
        """
        pairs = [(int(date), int(uid)) for date, uid in emitted]
        previous = state.cursor
        previous_lookback = previous.lookback_seconds if previous is not None else DEFAULT_LOOKBACK_SECONDS

        cursor = previous
        if pairs:
            newest = max(pairs, key=lambda pair: (pair[0], pair[1]))
            if previous is None or newest > (previous.last_date_received, previous.last_uid):
                cursor = Cursor(
                    last_date_received=newest[0],
                    last_uid=newest[1],
                    lookback_seconds=previous_lookback,
                )

        ring = _advance_ring(state.emitted_uids, pairs)
        timestamp = now_iso()
        return AppState(
            schema=STATE_SCHEMA,
            updated_at=timestamp,
            last_run=LastRun(command=command, at=timestamp),
            cursor=cursor,
            emitted_uids=ring,
        )


class RunLock:
    """Non-blocking ``fcntl.flock`` lock under ``~/.mailquery/locks``.

    Every invocation takes the lock before touching the store so two harness
    calls cannot overlap (PRD 21.3). A contended lock raises ``E_LOCKED``
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
            ) from exc
        try:
            os.chmod(path, 0o600)
        except OSError:  # pragma: no cover - best effort on foreign filesystems
            pass
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
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
            fcntl.flock(fd, fcntl.LOCK_UN)
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
    """Render ``AppState`` as the stable ``state.json`` object (no PII)."""
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


def _state_from_payload(payload: dict) -> AppState:
    """Build ``AppState`` from raw JSON, raising E_STATE_CORRUPT on bad types."""
    schema = payload.get("schema", STATE_SCHEMA)
    if schema != STATE_SCHEMA or isinstance(schema, bool):
        raise _corrupt(f"unsupported schema {schema!r} (expected {STATE_SCHEMA})")

    updated_at = payload.get("updated_at", "")
    if updated_at is None:
        updated_at = ""
    if not isinstance(updated_at, str):
        raise _corrupt("'updated_at' must be a string")

    last_run = _last_run_from_payload(payload.get("last_run"))
    cursor = _cursor_from_payload(payload.get("cursor"))
    emitted_uids = _ring_from_payload(payload.get("emitted_uids", []))

    return AppState(
        schema=STATE_SCHEMA,
        updated_at=updated_at,
        last_run=last_run,
        cursor=cursor,
        emitted_uids=emitted_uids,
    )


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


def _cursor_from_payload(value: object) -> Cursor | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise _corrupt("'cursor' must be an object")
    date = value.get("last_date_received", 0)
    uid = value.get("last_uid", 0)
    lookback = value.get("lookback_seconds", DEFAULT_LOOKBACK_SECONDS)
    if not _is_int(date) or not _is_int(uid) or not _is_int(lookback):
        raise _corrupt("'cursor' fields must be integers")
    if date < 0 or uid < 0:
        raise _corrupt("'cursor' fields must not be negative")
    if lookback < 1:
        raise _corrupt("'cursor.lookback_seconds' must be positive")
    return Cursor(
        last_date_received=date,
        last_uid=uid,
        lookback_seconds=lookback,
    )


def _ring_from_payload(value: object) -> tuple[int, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise _corrupt("'emitted_uids' must be a list of integers")
    uids: list[int] = []
    for item in value:
        if not _is_int(item) or item < 0:
            raise _corrupt("'emitted_uids' must be a list of non-negative integers")
        uids.append(item)
    return tuple(uids[-MAX_EMITTED_UIDS:])


def _advance_ring(
    current: Sequence[int],
    pairs: Sequence[tuple[int, int]],
) -> tuple[int, ...]:
    """Append emitted uids in chronological order, caps the ring at 1.000."""
    ring = [int(uid) for uid in current]
    for _, uid in sorted(pairs, key=lambda pair: (pair[0], pair[1])):
        uid = int(uid)
        if uid in ring:
            ring.remove(uid)
        ring.append(uid)
    if len(ring) > MAX_EMITTED_UIDS:
        ring = ring[-MAX_EMITTED_UIDS:]
    return tuple(ring)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _corrupt(detail: str) -> MailqueryError:
    return MailqueryError(
        "E_STATE_CORRUPT",
        f"state.json is corrupt: {detail}",
        "rename ~/.mailquery/state.json (for example to state.json.bak) to "
        "re-baseline: the next 'mailquery new' creates a fresh state and, on "
        "its first run, emits nothing",
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

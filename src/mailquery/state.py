"""Persistent cursor state and run lock (PRD 11.2, 18, 21.3).

State lives in ``~/.mailquery/state.json`` only: the ``new`` cursor
``(last_date_received, last_uid)``, the ring of the last 1.000 emitted uids and
the last run metadata. Writes are atomic (temporary + fsync + ``os.replace``)
with mode 0600, and the file never contains subjects, bodies or addresses.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

MAX_EMITTED_UIDS = 1000
STATE_SCHEMA = 1


@dataclass(frozen=True)
class Cursor:
    """Watermark for ``mailquery new``."""

    last_date_received: int
    last_uid: int
    lookback_seconds: int = 600


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


class StateStore:
    """Load/save ``state.json`` atomically."""

    def __init__(self, home: Path) -> None:
        raise NotImplementedError

    @property
    def path(self) -> Path:
        raise NotImplementedError

    def load(self) -> AppState:
        """Load state; raises E_STATE_CORRUPT when the file is unreadable."""
        raise NotImplementedError

    def save(self, state: AppState) -> None:
        raise NotImplementedError

    def record_new(
        self,
        state: AppState,
        emitted: Sequence[tuple[int, int]],
        command: str = "new",
    ) -> AppState:
        """Advance the cursor and the emitted-uid ring, returning the new state."""
        raise NotImplementedError


class RunLock:
    """Non-blocking ``fcntl.flock`` lock under ``~/.mailquery/locks``."""

    def __init__(self, home: Path) -> None:
        raise NotImplementedError

    def acquire(self) -> None:
        """Acquire the lock or raise E_LOCKED (exit 5)."""
        raise NotImplementedError

    def release(self) -> None:
        raise NotImplementedError

    def __enter__(self) -> "RunLock":
        raise NotImplementedError

    def __exit__(self, *exc_info: object) -> None:
        raise NotImplementedError

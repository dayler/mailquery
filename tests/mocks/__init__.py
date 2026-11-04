"""``unittest.mock`` helpers that simulate Apple Mail / TCC failure modes.

The synthetic store in ``tests/fixtures`` covers the happy path. These helpers
put the suite in the situations the PRD lists under "Mocks de Apple Mail"
(PRD 20):

* **TCC denied** — reading ``~/Library/Mail`` raises ``Operation not
  permitted``; commands must fail with ``E_PERMISSION`` (exit 3) and ``doctor``
  must still diagnose (exit 0 with a failed check).
* **DB busy** — the ``Envelope Index`` is locked; after the single documented
  retry the command must return ``E_DB_BUSY`` (exit 5).
* **Unexpected schema** — a required table/column is gone; the fingerprint must
  fail with ``E_SCHEMA_UNSUPPORTED`` (exit 3). ``drop_required_table`` mutates
  a *fixture* store, so it must only be used on a fixture built for that test.
* **Accounts DB unavailable** — ``~/Library/Accounts/Accounts4.sqlite`` is
  missing; labels fall back to the UUID and account labels are unresolvable.

Everything here is stdlib-only and never touches the real user directories.
"""

from __future__ import annotations

import contextlib
import errno
import sqlite3
import tempfile
from pathlib import Path
from typing import Iterator
from unittest import mock

from mailquery.store import REQUIRED_COLUMNS

__all__ = [
    "db_busy_error",
    "drop_required_table",
    "accounts_db_unavailable",
    "db_busy",
    "permission_denied",
    "tcc_denied",
]


# --------------------------------------------------------------------------- #
# Error factories
# --------------------------------------------------------------------------- #


def permission_denied() -> PermissionError:
    """Return the error macOS raises when TCC denies access to ``~/Library``."""
    return PermissionError(errno.EPERM, "Operation not permitted")


def db_busy_error() -> sqlite3.OperationalError:
    """Return the error SQLite raises for a locked database."""
    return sqlite3.OperationalError("database is locked")


# --------------------------------------------------------------------------- #
# Monkeypatch context managers
# --------------------------------------------------------------------------- #


@contextlib.contextmanager
def _sqlite_connect_raising(error: BaseException) -> Iterator[mock.MagicMock]:
    """Patch ``sqlite3.connect`` everywhere so opening any DB raises ``error``."""
    with mock.patch("sqlite3.connect", side_effect=error) as patched:
        yield patched


@contextlib.contextmanager
def tcc_denied() -> Iterator[mock.MagicMock]:
    """Simulate TCC denying access: every SQLite open raises PermissionError."""
    with _sqlite_connect_raising(permission_denied()) as patched:
        yield patched


@contextlib.contextmanager
def db_busy() -> Iterator[mock.MagicMock]:
    """Simulate a locked ``Envelope Index``: every SQLite open says "busy"."""
    with _sqlite_connect_raising(db_busy_error()) as patched:
        yield patched


@contextlib.contextmanager
def accounts_db_unavailable() -> Iterator[Path]:
    """Point the default accounts database at a path that does not exist."""
    with tempfile.TemporaryDirectory(prefix="mailquery-noaccounts-") as tmp:
        missing = Path(tmp) / "Accounts4.sqlite"
        targets = (
            "mailquery.accounts.default_accounts_db_path",
            "mailquery.cli.default_accounts_db_path",
        )
        with contextlib.ExitStack() as stack:
            for target in targets:
                try:
                    stack.enter_context(mock.patch(target, return_value=missing))
                except AttributeError:  # pragma: no cover - module layout dependent
                    continue
            yield missing


# --------------------------------------------------------------------------- #
# Fixture mutation helpers
# --------------------------------------------------------------------------- #


def drop_required_table(envelope_index: Path, table: str = "message_global_data") -> None:
    """Drop one required table from a *fixture* ``Envelope Index``.

    Raises :class:`ValueError` for names outside ``store.REQUIRED_COLUMNS`` so
    the call can never be used to execute arbitrary SQL.
    """
    if table not in REQUIRED_COLUMNS:
        raise ValueError(f"not a required table: {table!r}")
    connection = sqlite3.connect(str(envelope_index))
    try:
        connection.execute(f'DROP TABLE "{table}"')
        connection.commit()
    finally:
        connection.close()

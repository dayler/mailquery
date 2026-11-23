"""Tests for :mod:`mailquery.native_ids` (RF-80, RNF-05, AC-64, AC-69, AC-70).

Covers the short id calculation (UT-NID-01), opening and format of the cache
(UT-NID-02), assign/register/resolve/discard (UT-NID-03) and the plugin access
that translates cache failures to the plugin error protocol (UT-NID-04).
"""

from __future__ import annotations

import hashlib
import inspect
import os
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from mailquery import native_ids
from mailquery.errors import MailqueryError
from mailquery.native_ids import (
    ALPHABET,
    FORMAT_VERSION,
    NativeIdCache,
    PluginNativeIds,
    cache_path,
    short_id,
)
from mailquery.plugins.api import call_driver

_IO_HINT = (
    "if you delete ~/.mailquery/db/cache.db, mailquery creates an empty one; uids "
    "already printed do not resolve until you repeat the search"
)
_LOCKED_MESSAGE = "the native id cache is locked by another process"
_LOCKED_HINT = (
    "close the process that holds ~/.mailquery/db/cache.db and run the command again"
)
_PERMISSION_MESSAGE = "no permission to read or write the native id cache"
_PERMISSION_HINT = "check the permissions of ~/.mailquery/db/ and ~/.mailquery/db/cache.db"


def reference_encoding(text: str) -> str:
    """Base32 reference: five bits from the most significant one, no filler."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    bits = "".join(f"{byte:08b}" for byte in digest)
    groups = (
        int(bits[start : start + 5].ljust(5, "0"), 2) for start in range(0, len(bits), 5)
    )
    return "".join(ALPHABET[index] for index in groups)


class _NativeIdsTestCase(unittest.TestCase):
    """Temporary home and helpers shared by the four case groups."""

    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.root = Path(self._temporary.name)
        self.home = self.root / "home"
        environment = mock.patch.dict(
            os.environ,
            {"HOME": str(self.root), "USERPROFILE": str(self.root)},
        )
        environment.start()
        self.addCleanup(environment.stop)

    @property
    def cache_file(self) -> Path:
        return cache_path(self.home)

    def open_cache(self, driver: str = "outlook") -> NativeIdCache:
        cache = NativeIdCache.open(driver, home=self.home)
        self.addCleanup(cache.close)
        return cache

    def query(self, sql: str, parameters: tuple = (), *, path: Path | None = None):
        connection = sqlite3.connect(str(path or self.cache_file))
        try:
            return connection.execute(sql, parameters).fetchall()
        finally:
            connection.close()

    def execute(
        self, sql: str, parameters: tuple = (), *, path: Path | None = None
    ) -> None:
        connection = sqlite3.connect(str(path or self.cache_file))
        try:
            connection.execute(sql, parameters)
            connection.commit()
        finally:
            connection.close()

    def patch_short_id(self, value: str):
        return mock.patch(
            "mailquery.native_ids.short_id",
            side_effect=lambda text, length: value,
        )

    def set_user_version(self, version: int) -> None:
        connection = sqlite3.connect(str(self.cache_file))
        try:
            connection.execute(f"PRAGMA user_version = {version}")
            connection.commit()
        finally:
            connection.close()

    def assert_invalid_cache_is_untouched(self) -> None:
        before = self.cache_file.read_bytes()
        with self.assertRaises(MailqueryError) as context:
            NativeIdCache.open("outlook", home=self.home)
        self.assert_io_error(context.exception, "not a valid native id cache")
        self.assertEqual(self.cache_file.read_bytes(), before)

    def assert_io_error(self, error: MailqueryError, detail: str) -> None:
        self.assertEqual(error.code, "E_IO")
        self.assertEqual(error.exit_code, 3)
        self.assertEqual(error.message, f"cannot use the native id cache: {detail}")
        self.assertEqual(error.hint, _IO_HINT)

    def assert_permission_error(self, error: MailqueryError) -> None:
        self.assertEqual(error.code, "E_PERMISSION")
        self.assertEqual(error.exit_code, 3)
        self.assertEqual(error.message, _PERMISSION_MESSAGE)
        self.assertEqual(error.hint, _PERMISSION_HINT)

    def assert_locked_error(self, error: MailqueryError) -> None:
        self.assertEqual(error.code, "E_LOCKED")
        self.assertEqual(error.exit_code, 5)
        self.assertEqual(error.message, _LOCKED_MESSAGE)
        self.assertEqual(error.hint, _LOCKED_HINT)


class ShortIdTests(_NativeIdsTestCase):
    """UT-NID-01: short id calculation."""

    def test_ut_nid_01_01_mailquery_with_ten_characters(self) -> None:
        """UT-NID-01.01: short_id("mailquery", 10) is pmw3w06f5e."""
        self.assertEqual(short_id("mailquery", 10), "pmw3w06f5e")

    def test_ut_nid_01_02_length_bounds_and_invalid_arguments(self) -> None:
        """UT-NID-01.02: lengths 1..51 are accepted; invalid lengths and texts raise."""
        self.assertEqual(len(short_id("mailquery", 1)), 1)
        self.assertEqual(len(short_id("mailquery", 51)), 51)
        for length in (0, 52, -1, 3.5, "10", None, True):
            with self.subTest(length=length):
                with self.assertRaises(ValueError):
                    short_id("mailquery", length)  # type: ignore[arg-type]
        for text in (123, None, b"mailquery", ["mailquery"]):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    short_id(text, 10)  # type: ignore[arg-type]

    def test_ut_nid_01_03_alphabet_prefix_determinism_and_reference(self) -> None:
        """UT-NID-01.03: alphabet, determinism, prefix property and reference encoding."""
        texts = ("", "mailquery", "cafe", "a longer text with spaces and 123")
        for text in texts:
            with self.subTest(text=text):
                encoding = reference_encoding(text)
                self.assertEqual(short_id(text, 51), encoding[:51])
                for length in (1, 5, 10, 51):
                    value = short_id(text, length)
                    self.assertEqual(value, encoding[:length])
                    self.assertTrue(set(value) <= set(ALPHABET))
                    self.assertEqual(value, short_id(text, length))
        self.assertEqual(short_id("mailquery", 10), short_id("mailquery", 51)[:10])

    def test_ut_nid_01_04_non_ascii_text_is_hashed_as_utf8(self) -> None:
        """UT-NID-01.04: a non-ASCII text is encoded as UTF-8 before SHA-256."""
        text = "correo-ñandú-✓-日本"
        self.assertEqual(short_id(text, 10), reference_encoding(text)[:10])
        latin_1_lookalike = text.encode("utf-8").decode("latin-1")
        self.assertNotEqual(short_id(text, 10), short_id(latin_1_lookalike, 10))


class CacheOpenTests(_NativeIdsTestCase):
    """UT-NID-02: opening, creation and format of the cache file."""

    def test_ut_nid_02_01_open_creates_directory_file_table_and_version(self) -> None:
        """UT-NID-02.01: a missing db/ and cache.db are created, empty, format 1."""
        self.assertFalse(self.home.exists())
        cache = self.open_cache()
        self.assertEqual(cache.driver, "outlook")
        self.assertTrue(self.cache_file.parent.is_dir())
        self.assertTrue(self.cache_file.is_file())
        self.assertEqual(self.query("PRAGMA user_version")[0][0], FORMAT_VERSION)
        tables = {
            row[0]
            for row in self.query(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        self.assertEqual(tables, {"cache_native_ids"})
        self.assertEqual(
            self.query("SELECT COUNT(*) FROM cache_native_ids")[0][0], 0
        )
        invalid_home = self.root / "invalid-driver"
        with self.assertRaises(ValueError):
            NativeIdCache.open("Not A Driver", home=invalid_home)
        self.assertFalse(invalid_home.exists())
        unusable = self.root / "unusable"
        unusable.write_text("not a directory")
        with self.assertRaises(MailqueryError) as context:
            NativeIdCache.open("outlook", home=unusable)
        self.assertEqual(context.exception.code, "E_IO")
        self.assertEqual(context.exception.exit_code, 3)
        self.assertTrue(
            context.exception.message.startswith("cannot use the native id cache: ")
        )

    def test_ut_nid_02_02_empty_file_is_initialized(self) -> None:
        """UT-NID-02.02: a 0-byte cache.db is initialized as a new one."""
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self.cache_file.write_bytes(b"")
        cache = self.open_cache()
        self.assertEqual(cache.driver, "outlook")
        self.assertEqual(self.query("PRAGMA user_version")[0][0], FORMAT_VERSION)
        self.assertEqual(
            self.query("SELECT COUNT(*) FROM cache_native_ids")[0][0], 0
        )
        self.assertGreater(self.cache_file.stat().st_size, 0)

    def test_ut_nid_02_03_table_has_only_the_documented_columns(self) -> None:
        """UT-NID-02.03: columns, types, NOT NULL, primary key and unique constraint."""
        self.open_cache()
        ids_columns = [
            (row[1], row[2], row[3], row[5])
            for row in self.query("PRAGMA table_info(cache_native_ids)")
        ]
        self.assertEqual(
            ids_columns,
            [
                ("driver", "TEXT", 1, 1),
                ("short_id", "TEXT", 1, 2),
                ("seq", "INTEGER", 1, 3),
                ("native_id", "TEXT", 1, 0),
            ],
        )
        unique_indexes = [
            row
            for row in self.query("PRAGMA index_list(cache_native_ids)")
            if row[2] == 1 and row[3] == "u"
        ]
        self.assertEqual(len(unique_indexes), 1)
        indexed = [
            row[2]
            for row in self.query(f"PRAGMA index_info({unique_indexes[0][1]})")
        ]
        self.assertEqual(indexed, ["driver", "native_id"])
        tables = {
            row[0]
            for row in self.query(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        self.assertEqual(tables, {"cache_native_ids"})

    def test_ut_nid_02_04_directory_and_file_permissions(self) -> None:
        """UT-NID-02.04: on POSIX the folder is 0700 and the file and auxiliaries 0600."""
        cache = self.open_cache()
        cache.assign(["alpha"])
        cache.register(["alpha"])
        if sys.platform == "win32":
            self.assertTrue(self.cache_file.is_file())
            return
        self.assertEqual(self.cache_file.parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.cache_file.stat().st_mode & 0o777, 0o600)
        auxiliary = list(self.cache_file.parent.glob("cache.db-*"))
        self.assertTrue(auxiliary, "a write must leave an auxiliary file")
        for path in auxiliary:
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_ut_nid_02_05_other_format_version_is_io_error(self) -> None:
        """UT-NID-02.05: a different format version is E_IO and the file is untouched."""
        cache = self.open_cache()
        cache.close()
        self.set_user_version(2)
        self.assert_invalid_cache_is_untouched()
        self.set_user_version(0)
        self.assert_invalid_cache_is_untouched()
        self.execute("DROP TABLE cache_native_ids")
        self.set_user_version(1)
        self.assert_invalid_cache_is_untouched()

    def test_ut_nid_02_06_file_that_is_not_sqlite_is_io_error(self) -> None:
        """UT-NID-02.06: a file that is not SQLite is E_IO and the file is untouched."""
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self.cache_file.write_bytes(b"not a sqlite database\n" * 64)
        before = self.cache_file.read_bytes()
        with self.assertRaises(MailqueryError) as context:
            NativeIdCache.open("outlook", home=self.home)
        self.assert_io_error(context.exception, "not a valid native id cache")
        self.assertEqual(self.cache_file.read_bytes(), before)
        with mock.patch(
            "mailquery.native_ids._connect",
            side_effect=OSError("input/output error"),
        ):
            with self.assertRaises(MailqueryError) as context:
                NativeIdCache.open("outlook", home=self.home)
        self.assert_io_error(
            context.exception, "cannot open the native id cache file"
        )

    def test_ut_nid_02_07_missing_permission_is_permission_error(self) -> None:
        """UT-NID-02.07: denied access is E_PERMISSION, with real chmod and injected denial."""
        cache = self.open_cache()
        cache.close()
        if sys.platform != "win32" and os.geteuid() != 0:
            directory = self.cache_file.parent
            directory.chmod(0o500)
            try:
                with self.assertRaises(MailqueryError) as context:
                    NativeIdCache.open("outlook", home=self.home)
            finally:
                directory.chmod(0o700)
            self.assert_permission_error(context.exception)

            self.cache_file.chmod(0o000)
            try:
                with self.assertRaises(MailqueryError) as context:
                    NativeIdCache.open("outlook", home=self.home)
            finally:
                self.cache_file.chmod(0o600)
            self.assert_permission_error(context.exception)

        with mock.patch("mailquery.native_ids.os.access", return_value=False):
            with self.assertRaises(MailqueryError) as context:
                NativeIdCache.open("outlook", home=self.home)
        self.assert_permission_error(context.exception)

        with mock.patch(
            "mailquery.native_ids._connect",
            side_effect=PermissionError("denied"),
        ):
            with self.assertRaises(MailqueryError) as context:
                NativeIdCache.open("outlook", home=self.home)
        self.assert_permission_error(context.exception)

        injected = (
            (mock.patch.object(Path, "mkdir", side_effect=PermissionError("no")), "E_PERMISSION"),
            (mock.patch.object(Path, "mkdir", side_effect=OSError("no")), "E_IO"),
            (mock.patch("mailquery.native_ids.os.chmod", side_effect=PermissionError("no")), "E_PERMISSION"),
            (mock.patch("mailquery.native_ids.os.chmod", side_effect=OSError("no")), "E_IO"),
            (mock.patch("mailquery.native_ids.os.chmod", side_effect=[None, PermissionError("no")]), "E_PERMISSION"),
            (mock.patch("mailquery.native_ids.os.chmod", side_effect=[None, OSError("no")]), "E_IO"),
        )
        for index, (patcher, code) in enumerate(injected):
            with self.subTest(case=index, code=code):
                home = self.root / f"injected-{index}"
                with patcher:
                    with self.assertRaises(MailqueryError) as context:
                        NativeIdCache.open("outlook", home=home)
                self.assertEqual(context.exception.code, code)
                self.assertEqual(context.exception.exit_code, 3)

    def test_ut_nid_02_08_locked_database_is_locked_error(self) -> None:
        """UT-NID-02.08: a write or an open blocked beyond BUSY_TIMEOUT_SECONDS is E_LOCKED."""
        self.assertEqual(native_ids.BUSY_TIMEOUT_SECONDS, 5.0)
        with mock.patch("mailquery.native_ids.BUSY_TIMEOUT_SECONDS", 0.2):
            cache = self.open_cache()
            cache.assign(["alpha"])
            blocker = sqlite3.connect(
                str(self.cache_file), isolation_level=None, timeout=5
            )
            try:
                blocker.execute("BEGIN IMMEDIATE")
                with self.assertRaises(MailqueryError) as context:
                    cache.register(["alpha"])
            finally:
                try:
                    blocker.execute("ROLLBACK")
                finally:
                    blocker.close()
        self.assert_locked_error(context.exception)
        cache.close()
        with mock.patch("mailquery.native_ids.BUSY_TIMEOUT_SECONDS", 0.2):
            blocker = sqlite3.connect(
                str(self.cache_file), isolation_level=None, timeout=5
            )
            try:
                blocker.execute("PRAGMA locking_mode = EXCLUSIVE")
                blocker.execute("BEGIN EXCLUSIVE")
                with self.assertRaises(MailqueryError) as context:
                    NativeIdCache.open("outlook", home=self.home)
            finally:
                try:
                    blocker.execute("ROLLBACK")
                finally:
                    blocker.close()
        self.assert_locked_error(context.exception)
        busy = sqlite3.OperationalError("database is locked")
        busy.sqlite_errorcode = sqlite3.SQLITE_BUSY
        with mock.patch("mailquery.native_ids._connect", side_effect=busy):
            with self.assertRaises(MailqueryError) as context:
                NativeIdCache.open("outlook", home=self.root / "busy-home")
        self.assert_locked_error(context.exception)

    def test_ut_nid_02_09_reopen_keeps_rows_and_version(self) -> None:
        """UT-NID-02.09: reopening a cache keeps its rows and its format version."""
        cache = self.open_cache()
        parts = cache.assign(["alpha", "bravo"])
        cache.register(["alpha", "bravo"])
        cache.close()
        reopened = NativeIdCache.open("outlook", home=self.home)
        self.addCleanup(reopened.close)
        self.assertEqual(self.query("PRAGMA user_version")[0][0], FORMAT_VERSION)
        self.assertEqual(
            self.query("SELECT COUNT(*) FROM cache_native_ids")[0][0], 2
        )
        self.assertEqual(reopened.resolve(parts["alpha"]), "alpha")
        self.assertEqual(reopened.resolve(parts["bravo"]), "bravo")
        self.assertEqual(reopened.assign(["alpha", "bravo"]), parts)

    def test_ut_nid_02_10_database_initialized_by_another_open_is_kept(self) -> None:
        """UT-NID-02.10: an open that read the file before another open initialized it keeps the schema."""
        cache = self.open_cache()
        parts = cache.assign(["alpha"])
        cache.register(["alpha"])
        cache.close()
        real_read_format = native_ids._read_format
        for first_read in ((0, set()), (0, {"cache_native_ids"})):
            with self.subTest(first_read=first_read):
                calls: list[int] = []

                def read_format(connection: sqlite3.Connection):
                    calls.append(1)
                    if len(calls) == 1:
                        return first_read
                    return real_read_format(connection)

                with mock.patch(
                    "mailquery.native_ids._read_format", side_effect=read_format
                ):
                    reopened = NativeIdCache.open("outlook", home=self.home)
                try:
                    self.assertEqual(len(calls), 2)
                    self.assertEqual(
                        self.query("PRAGMA user_version")[0][0], FORMAT_VERSION
                    )
                    self.assertEqual(reopened.resolve(parts["alpha"]), "alpha")
                finally:
                    reopened.close()
        foreign_home = self.root / "foreign-home"
        foreign_file = native_ids.cache_path(foreign_home)
        foreign_file.parent.mkdir(parents=True)
        foreign = sqlite3.connect(str(foreign_file))
        try:
            foreign.execute("CREATE TABLE other (value TEXT)")
            foreign.commit()
        finally:
            foreign.close()
        calls = []

        def read_empty_first(connection: sqlite3.Connection):
            calls.append(1)
            if len(calls) == 1:
                return 0, set()
            return real_read_format(connection)

        with mock.patch(
            "mailquery.native_ids._read_format", side_effect=read_empty_first
        ):
            with self.assertRaises(MailqueryError) as context:
                NativeIdCache.open("outlook", home=foreign_home)
        self.assertEqual(context.exception.code, "E_IO")
        check = sqlite3.connect(str(foreign_file))
        try:
            tables = {
                row[0]
                for row in check.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
        finally:
            check.close()
        self.assertEqual(tables, {"other"})


class CacheOperationsTests(_NativeIdsTestCase):
    """UT-NID-03: assign, register, resolve and discard."""

    def test_ut_nid_03_01_assign_unregistered_and_registered(self) -> None:
        """UT-NID-03.01: assign gives the short id, keeps the row part and never writes."""
        cache = self.open_cache()
        expected = short_id("alpha", 10)
        before = self.cache_file.read_bytes()
        self.assertEqual(cache.assign(["alpha"]), {"alpha": expected})
        self.assertEqual(self.cache_file.read_bytes(), before)
        self.assertEqual(self.query("SELECT COUNT(*) FROM cache_native_ids")[0][0], 0)
        cache.register(["alpha"])
        self.assertEqual(cache.assign(["alpha"]), {"alpha": expected})
        self.assertEqual(cache.resolve(expected), "alpha")
        for value in (b"bytes", "", 7):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    cache.assign([value])  # type: ignore[list-item]

    def test_ut_nid_03_02_two_native_ids_with_the_same_short_id(self) -> None:
        """UT-NID-03.02: a shared short id yields seq 1 and 2 in the native id order."""
        cache = self.open_cache()
        with self.patch_short_id("abc"):
            parts = cache.assign(["bravo", "alpha"])
        self.assertEqual(parts, {"alpha": "abc", "bravo": "abc-2"})

    def test_ut_nid_03_03_one_part_per_native_id_across_calls(self) -> None:
        """UT-NID-03.03: a part sticks to its native id and two ids never share a part."""
        cache = self.open_cache()
        with self.patch_short_id("abc"):
            first = cache.assign(["n1"])
            second = cache.assign(["n1", "n2"])
            third = cache.assign(["n3"])
            again = cache.assign(["n2"])
        self.assertEqual(first, {"n1": "abc"})
        self.assertEqual(second, {"n1": "abc", "n2": "abc-2"})
        self.assertEqual(third, {"n3": "abc-3"})
        self.assertEqual(again, {"n2": "abc-2"})
        self.assertEqual(len({"abc", "abc-2", "abc-3"}), 3)

    def test_ut_nid_03_04_register_saves_all_pending_rows_once(self) -> None:
        """UT-NID-03.04: register stores all pending rows in one transaction."""
        cache = self.open_cache()
        parts = cache.assign(["alpha", "bravo"])
        cache.register(["alpha", "bravo"])
        rows = self.query(
            "SELECT driver, short_id, seq, native_id FROM cache_native_ids"
        )
        self.assertEqual(len(rows), 2)
        for driver, short, seq, native in rows:
            self.assertEqual(driver, "outlook")
            part = short if seq == 1 else f"{short}-{seq}"
            self.assertEqual(cache.resolve(part), native)
        self.assertEqual(cache.assign(["alpha", "bravo"]), parts)
        cache.register(["alpha", "bravo"])
        self.assertEqual(
            self.query("SELECT COUNT(*) FROM cache_native_ids")[0][0], 2
        )
        with self.assertRaises(ValueError):
            cache.register([123])  # type: ignore[list-item]
        self.assertEqual(
            self.query("SELECT COUNT(*) FROM cache_native_ids")[0][0], 2
        )

    def test_ut_nid_03_05_conflicts_save_nothing(self) -> None:
        """UT-NID-03.05: three conflict shapes are E_IO and store no row."""
        first = self.open_cache()
        with self.patch_short_id("abc"):
            first.assign(["n1"])
        first.register(["n1"])

        shared = NativeIdCache.open("outlook", home=self.home)
        self.addCleanup(shared.close)
        other = NativeIdCache.open("outlook", home=self.home)
        self.addCleanup(other.close)
        with self.patch_short_id("abc"):
            self.assertEqual(shared.assign(["n2"]), {"n2": "abc-2"})
            self.assertEqual(other.assign(["n3"]), {"n3": "abc-2"})
            other.register(["n3"])
            with self.assertRaises(MailqueryError) as context:
                shared.register(["n2"])
        self.assert_io_error(context.exception, "conflicting uid part")

        stale = NativeIdCache.open("outlook", home=self.home)
        self.addCleanup(stale.close)
        with self.patch_short_id("abc"):
            self.assertEqual(stale.assign(["n4"]), {"n4": "abc-3"})
        with self.patch_short_id("xyz"):
            moved = NativeIdCache.open("outlook", home=self.home)
            self.addCleanup(moved.close)
            moved.assign(["n4"])
            moved.register(["n4"])
        with self.patch_short_id("abc"):
            with self.assertRaises(MailqueryError) as context:
                stale.register(["n4"])
        self.assert_io_error(context.exception, "conflicting uid part")
        self.assertEqual(
            {row for row in self.query("SELECT short_id, seq, native_id FROM cache_native_ids")},
            {("abc", 1, "n1"), ("abc", 2, "n3"), ("xyz", 1, "n4")},
        )

        pending = NativeIdCache.open("outlook", home=self.home)
        self.addCleanup(pending.close)
        pending.assign(["ok"])
        before = set(self.query("SELECT short_id, seq, native_id FROM cache_native_ids"))
        with self.assertRaises(MailqueryError) as context:
            pending.register(["ok", "missing"])
        self.assert_io_error(context.exception, "conflicting uid part")
        self.assertEqual(
            set(self.query("SELECT short_id, seq, native_id FROM cache_native_ids")),
            before,
        )

    def test_ut_nid_03_06_resolve_registered_and_missing_parts(self) -> None:
        """UT-NID-03.06: resolve returns the native id or None and never writes."""
        cache = self.open_cache()
        parts = cache.assign(["alpha"])
        cache.register(["alpha"])
        before = self.query("SELECT * FROM cache_native_ids")
        self.assertEqual(cache.resolve(parts["alpha"]), "alpha")
        self.assertEqual(self.query("SELECT * FROM cache_native_ids"), before)
        for part in ("zzzzzzzzzz", "", "ABC", "abc-01", "abc-1", "abc-0"):
            with self.subTest(part=part):
                self.assertIsNone(cache.resolve(part))

    def test_ut_nid_03_07_discard_frees_the_highest_seq(self) -> None:
        """UT-NID-03.07: discard deletes the row and its seq can be assigned again."""
        cache = self.open_cache()
        with self.patch_short_id("abc"):
            parts = cache.assign(["alpha", "bravo"])
        cache.register(["alpha", "bravo"])
        self.assertEqual(parts, {"alpha": "abc", "bravo": "abc-2"})
        cache.discard("bravo")
        self.assertIsNone(cache.resolve("abc-2"))
        reopened = NativeIdCache.open("outlook", home=self.home)
        self.addCleanup(reopened.close)
        with self.patch_short_id("abc"):
            self.assertEqual(reopened.assign(["charlie"]), {"charlie": "abc-2"})
        reopened.register(["charlie"])
        self.assertEqual(
            self.query("SELECT seq FROM cache_native_ids ORDER BY seq"), [(1,), (2,)]
        )
        cache.discard("not-there")

    def test_ut_nid_03_08_drivers_are_isolated(self) -> None:
        """UT-NID-03.08: a driver neither reads, resolves nor discards another driver's rows."""
        outlook = self.open_cache("outlook")
        other = self.open_cache("other_driver")
        parts = outlook.assign(["alpha"])
        outlook.register(["alpha"])
        self.assertIsNone(other.resolve(parts["alpha"]))
        self.assertEqual(other.assign(["alpha"]), {"alpha": parts["alpha"]})
        other.discard("alpha")
        self.assertEqual(outlook.resolve(parts["alpha"]), "alpha")
        other.register(["alpha"])
        self.assertEqual(other.resolve(parts["alpha"]), "alpha")
        self.assertEqual(outlook.resolve(parts["alpha"]), "alpha")
        self.assertEqual(
            self.query(
                "SELECT driver, native_id FROM cache_native_ids ORDER BY driver"
            ),
            [("other_driver", "alpha"), ("outlook", "alpha")],
        )

    def test_ut_nid_03_09_suffix_is_decimal_without_leading_zeros(self) -> None:
        """UT-NID-03.09: seq 10 is <id>-10 and seq 1 never carries -1."""
        cache = self.open_cache()
        with self.patch_short_id("abc"):
            native_ids_list = [f"item-{index}" for index in range(10)]
            parts = cache.assign(native_ids_list)
            expected = ["abc"] + [f"abc-{seq}" for seq in range(2, 11)]
            self.assertEqual([parts[value] for value in native_ids_list], expected)
            self.assertEqual(parts["item-9"], "abc-10")
            self.assertEqual(len(set(parts.values())), 10)
            cache.register(native_ids_list)
            self.assertEqual(cache.resolve("abc-10"), "item-9")

    def test_ut_nid_03_10_only_the_documented_values_are_stored(self) -> None:
        """UT-NID-03.10: after register the table holds only the documented values."""
        cache = self.open_cache()
        with self.patch_short_id("abc"):
            cache.assign(["alpha", "bravo", "charlie"])
            cache.register(["alpha", "bravo", "charlie"])
        self.assertEqual(
            [row[1] for row in self.query("PRAGMA table_info(cache_native_ids)")],
            ["driver", "short_id", "seq", "native_id"],
        )
        rows = self.query(
            "SELECT driver, short_id, seq, native_id FROM cache_native_ids ORDER BY seq"
        )
        self.assertEqual(
            [(row[0], row[1], row[2]) for row in rows],
            [("outlook", "abc", 1), ("outlook", "abc", 2), ("outlook", "abc", 3)],
        )
        self.assertEqual([row[3] for row in rows], ["alpha", "bravo", "charlie"])
        tables = {
            row[0]
            for row in self.query(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        self.assertEqual(tables, {"cache_native_ids"})

    def test_ut_nid_03_11_in_memory_cache_creates_no_file(self) -> None:
        """UT-NID-03.11: open_in_memory assigns, registers and resolves without a file."""
        cache = NativeIdCache.open_in_memory("outlook")
        self.addCleanup(cache.close)
        self.assertIsNone(cache.path)
        parts = cache.assign(["alpha", "bravo"])
        cache.register(["alpha", "bravo"])
        self.assertEqual(cache.resolve(parts["alpha"]), "alpha")
        self.assertEqual(cache.resolve(parts["bravo"]), "bravo")
        self.assertFalse(self.home.exists())
        self.assertFalse(self.cache_file.exists())
        with self.assertRaises(ValueError):
            NativeIdCache.open_in_memory("Not A Driver")
        busy = sqlite3.OperationalError("database is locked")
        busy.sqlite_errorcode = sqlite3.SQLITE_BUSY
        with mock.patch("mailquery.native_ids._connect", side_effect=busy):
            with self.assertRaises(MailqueryError) as context:
                NativeIdCache.open_in_memory("outlook")
        self.assert_locked_error(context.exception)
        with mock.patch(
            "mailquery.native_ids._create_schema",
            side_effect=sqlite3.OperationalError("disk I/O error"),
        ):
            with self.assertRaises(MailqueryError) as context:
                NativeIdCache.open_in_memory("outlook")
        self.assertEqual(context.exception.code, "E_IO")
        self.assertEqual(context.exception.exit_code, 3)
        cache.close()
        with self.assertRaises(RuntimeError):
            cache.assign(["alpha"])
        self.assertFalse(self.home.exists())


class PluginAccessTests(_NativeIdsTestCase):
    """UT-NID-04: plugin access and RF-50 error translation."""

    def call_plugin(
        self,
        call,
        *,
        driver: str = "outlook_ext",
        timeout: float | None = None,
    ):
        options: dict = {"internal": False}
        if timeout is not None:
            options["timeout"] = timeout
        return call_driver("cache_probe", call, driver=driver, **options)

    def test_ut_nid_04_01_failures_reach_the_core_as_plugin_errors(self) -> None:
        """UT-NID-04.01: locked, denied, invalid and conflicting caches fail as RF-50 says."""
        with mock.patch("mailquery.native_ids.BUSY_TIMEOUT_SECONDS", 0.2):
            access = PluginNativeIds(self.home, "outlook_ext")
            self.addCleanup(access.close)
            self.call_plugin(lambda: access.assign(["alpha"]))
            blocker = sqlite3.connect(
                str(self.cache_file), isolation_level=None, timeout=5
            )
            try:
                blocker.execute("BEGIN IMMEDIATE")
                with self.assertRaises(MailqueryError) as context:
                    self.call_plugin(lambda: access.register(["alpha"]))
            finally:
                try:
                    blocker.execute("ROLLBACK")
                finally:
                    blocker.close()
        self.assertEqual(context.exception.code, "E_CLIENT_BUSY")
        self.assertEqual(context.exception.exit_code, 5)

        denied = PluginNativeIds(self.root / "denied", "outlook_ext")
        with mock.patch("mailquery.native_ids.os.access", return_value=False):
            with self.assertRaises(MailqueryError) as context:
                self.call_plugin(lambda: denied.assign(["alpha"]))
        self.assertEqual(context.exception.code, "E_PERMISSION")
        self.assertEqual(context.exception.exit_code, 3)

        invalid_home = self.root / "invalid"
        invalid_file = cache_path(invalid_home)
        invalid_file.parent.mkdir(parents=True, exist_ok=True)
        invalid_file.write_bytes(b"not a sqlite database\n" * 64)
        invalid = PluginNativeIds(invalid_home, "outlook_ext")
        with self.assertRaises(MailqueryError) as context:
            self.call_plugin(lambda: invalid.assign(["alpha"]))
        self.assertEqual(context.exception.code, "E_PLUGIN_FAILED")
        self.assertEqual(context.exception.exit_code, 3)

        conflict_home = self.root / "conflict"
        first = PluginNativeIds(conflict_home, "outlook_ext")
        self.addCleanup(first.close)
        with self.patch_short_id("abc"):
            self.call_plugin(lambda: first.assign(["alpha"]))
            self.call_plugin(lambda: first.register(["alpha"]))
        second = PluginNativeIds(conflict_home, "outlook_ext")
        self.addCleanup(second.close)
        third = PluginNativeIds(conflict_home, "outlook_ext")
        self.addCleanup(third.close)
        with self.patch_short_id("abc"):
            self.call_plugin(lambda: second.assign(["bravo"]))
            self.call_plugin(lambda: third.assign(["charlie"]))
            self.call_plugin(lambda: third.register(["charlie"]))
            with self.assertRaises(MailqueryError) as context:
                self.call_plugin(lambda: second.register(["bravo"]))
        self.assertEqual(context.exception.code, "E_PLUGIN_FAILED")
        self.assertEqual(context.exception.exit_code, 3)

    def test_ut_nid_04_02_operations_run_in_worker_threads_and_under_a_deadline(self) -> None:
        """UT-NID-04.02: operations work from successive worker threads and under the cap."""
        access = PluginNativeIds(self.home, "outlook_ext")
        self.addCleanup(access.close)
        threads: list[tuple[int, str]] = []

        def assign():
            threads.append(
                (threading.get_ident(), threading.current_thread().name)
            )
            return access.assign(["alpha"])

        parts = self.call_plugin(assign, timeout=2.0)
        self.assertEqual(parts, {"alpha": short_id("alpha", 10)})

        def register():
            threads.append(
                (threading.get_ident(), threading.current_thread().name)
            )
            access.register(["alpha"])
            return None

        self.call_plugin(register, timeout=2.0)

        def resolve():
            threads.append(
                (threading.get_ident(), threading.current_thread().name)
            )
            return access.resolve(parts["alpha"])

        self.assertEqual(self.call_plugin(resolve, timeout=2.0), "alpha")
        self.assertEqual(len(threads), 3)
        self.assertTrue(all(ident != threading.get_ident() for ident, _ in threads))
        self.assertEqual(
            [name for _, name in threads], ["mailquery-driver-call"] * 3
        )

    def test_ut_nid_04_03_construction_creates_nothing(self) -> None:
        """UT-NID-04.03: constructing the access creates nothing; the first operation does."""
        access = PluginNativeIds(self.home, "outlook_ext")
        self.addCleanup(access.close)
        self.assertFalse(self.home.exists())
        self.assertFalse(self.cache_file.exists())
        parts = self.call_plugin(lambda: access.assign(["alpha"]))
        self.assertEqual(parts, {"alpha": short_id("alpha", 10)})
        self.assertTrue(self.cache_file.parent.is_dir())
        self.assertTrue(self.cache_file.is_file())

    def test_ut_nid_04_04_operations_are_bound_to_the_plugin_driver(self) -> None:
        """UT-NID-04.04: no operation picks another driver; rows belong to the plugin driver."""
        for name in ("assign", "register", "resolve", "discard", "close"):
            parameters = inspect.signature(getattr(PluginNativeIds, name)).parameters
            self.assertNotIn("driver", parameters)
        first = PluginNativeIds(self.home, "driver_a")
        self.addCleanup(first.close)
        second = PluginNativeIds(self.home, "driver_b")
        self.addCleanup(second.close)
        parts = self.call_plugin(lambda: first.assign(["alpha"]), driver="driver_a")
        self.call_plugin(lambda: first.register(["alpha"]), driver="driver_a")
        self.assertIsNone(
            self.call_plugin(
                lambda: second.resolve(parts["alpha"]), driver="driver_b"
            )
        )
        self.call_plugin(lambda: second.discard("alpha"), driver="driver_b")
        self.assertEqual(
            self.call_plugin(
                lambda: first.resolve(parts["alpha"]), driver="driver_a"
            ),
            "alpha",
        )
        self.call_plugin(lambda: second.assign(["alpha"]), driver="driver_b")
        self.call_plugin(lambda: second.register(["alpha"]), driver="driver_b")
        self.assertEqual(
            self.call_plugin(
                lambda: second.resolve(parts["alpha"]), driver="driver_b"
            ),
            "alpha",
        )
        self.assertEqual(
            self.query(
                "SELECT driver, native_id FROM cache_native_ids ORDER BY driver"
            ),
            [("driver_a", "alpha"), ("driver_b", "alpha")],
        )

    def test_ut_nid_04_05_close_releases_the_connection_and_reopens(self) -> None:
        """UT-NID-04.05: after close the file can be deleted and the next operation reopens."""
        access = PluginNativeIds(self.home, "outlook_ext")
        self.addCleanup(access.close)
        parts = self.call_plugin(lambda: access.assign(["alpha"]))
        self.call_plugin(lambda: access.register(["alpha"]))
        access.close()
        access.close()
        self.cache_file.unlink()
        self.assertFalse(self.cache_file.exists())
        reopened = self.call_plugin(lambda: access.assign(["alpha"]))
        self.assertTrue(self.cache_file.is_file())
        self.assertEqual(reopened, parts)
        self.call_plugin(lambda: access.register(["alpha"]))
        self.assertEqual(
            self.call_plugin(lambda: access.resolve(reopened["alpha"])), "alpha"
        )


if __name__ == "__main__":
    unittest.main()

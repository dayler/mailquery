"""Tests for :mod:`mailquery.state` (PRD.md 11.2, 18, 21.3; PRD §11.2).

Covers the atomic ``state.json`` lifecycle (defaults, roundtrip, 0600 mode,
corruption), the schema-1 to schema-2 uid migration (UT-ST-06/07), the ``new``
cursor and emitted-uid ring semantics with prefixed uids, the non-blocking run
lock and the ``--peek`` guarantee end to end through ``search.run_new``.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

from mailquery.errors import MailqueryError
from mailquery.state import (
    MAX_EMITTED_UIDS,
    STATE_SCHEMA,
    AppState,
    Cursor,
    EmittedUid,
    LastRun,
    RunLock,
    StateLoadInfo,
    StateStore,
    migrate_uid,
)

_LEGACY_INT = 83143
_PREFIXED = "apple_mail:83143"
_HEX = "00000000D70DBCF61C2A4B6E9A51E0C3B2A49F1007000000"


def _all_installed(driver: str) -> bool:
    return bool(driver)


def _apple_only(driver: str) -> bool:
    return driver == "apple_mail"


def _store(home: Path, is_installed=_all_installed) -> StateStore:
    return StateStore(home, is_installed)


def _apple(date: int, native: int) -> EmittedUid:
    return EmittedUid(
        date_received=date,
        driver="apple_mail",
        native_order_key=native,
        uid=f"apple_mail:{native}",
    )


def _outlook(date: int, native: str) -> EmittedUid:
    return EmittedUid(
        date_received=date,
        driver="outlook",
        native_order_key=native,
        uid=f"outlook:{native}",
    )


class StateStoreTest(unittest.TestCase):
    """Atomic persistence and corruption handling."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="mailquery-state-")
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name) / "home"
        self.store = _store(self.home)

    def test_path_is_state_json_under_home(self) -> None:
        self.assertEqual(self.store.path, self.home / "state.json")
        self.assertEqual(self.store.home, self.home)

    def test_missing_file_returns_defaults_without_creating_anything(self) -> None:
        state = self.store.load()
        self.assertEqual(state, AppState())
        self.assertEqual(state.schema, STATE_SCHEMA)
        self.assertEqual(STATE_SCHEMA, 2)
        self.assertEqual(state.updated_at, "")
        self.assertIsNone(state.last_run)
        self.assertIsNone(state.cursor)
        self.assertEqual(state.emitted_uids, ())
        self.assertFalse(self.home.exists())
        self.assertFalse(self.store.load_info.exists)
        self.assertIsNone(self.store.load_info.persisted_schema)
        self.assertFalse(self.store.load_info.migrated)

    def test_roundtrip_preserves_every_field(self) -> None:
        state = AppState(
            schema=STATE_SCHEMA,
            updated_at="2026-11-02T02:15:00-04:00",
            last_run=LastRun(command="new", at="2026-11-02T02:15:00-04:00"),
            cursor=Cursor(
                last_date_received=1793573649,
                last_uid="apple_mail:83143",
                lookback_seconds=900,
            ),
            emitted_uids=("apple_mail:83135", "apple_mail:83138", "apple_mail:83143"),
        )
        self.store.save(state)
        self.assertEqual(self.store.load(), state)

        payload = json.loads(self.store.path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema"], 2)
        self.assertEqual(payload["cursor"]["last_uid"], "apple_mail:83143")
        self.assertEqual(
            payload["emitted_uids"],
            ["apple_mail:83135", "apple_mail:83138", "apple_mail:83143"],
        )
        self.assertEqual(self.store.load_info.persisted_schema, 2)
        self.assertFalse(self.store.load_info.migrated)

    def test_state_file_is_0600_and_home_is_0700(self) -> None:
        self.store.save(AppState())
        self.assertTrue(self.store.path.is_file())
        if os.name == "posix":
            self.assertEqual(self.store.path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(self.home.stat().st_mode & 0o777, 0o700)

    def test_creating_state_in_nested_missing_home(self) -> None:
        nested = Path(self._tmp.name) / "a" / "b" / "home"
        _store(nested).save(AppState())
        self.assertTrue((nested / "state.json").is_file())

    def test_save_overwrites_previous_content(self) -> None:
        self.store.save(AppState(updated_at="first"))
        self.store.save(AppState(updated_at="second"))
        self.assertEqual(self.store.load().updated_at, "second")

    def assert_failed_save_keeps_previous_cursor(
        self, phase: str, code: int, expected: str, exit_code: int
    ) -> None:
        previous = AppState(
            updated_at="previous",
            cursor=Cursor(
                last_date_received=1793573649,
                last_uid="apple_mail:83143",
                lookback_seconds=600,
            ),
            emitted_uids=("apple_mail:83143",),
        )
        self.store.save(previous)
        error = OSError(code, os.strerror(code))
        targets = {
            "mkstemp": "mailquery.state.tempfile.mkstemp",
            "write": "mailquery.state.os.fsync",
            "replace": "mailquery.state.os.replace",
        }
        with mock.patch(targets[phase], side_effect=error):
            with self.assertRaises(MailqueryError) as caught:
                self.store.save(AppState(updated_at="next", cursor=None))
        self.assertEqual(caught.exception.code, expected)
        self.assertEqual(caught.exception.exit_code, exit_code)
        self.assertTrue(caught.exception.hint)
        self.assertEqual(self.store.load(), previous)
        self.assertEqual(sorted(self.home.glob(".state-*.tmp")), [])

    def test_ut_st_05_01_disk_full_is_internal_error_and_keeps_the_cursor(self) -> None:
        """UT-ST-05.01: ENOSPC while writing => E_INTERNAL (exit 1), previous cursor intact."""
        import errno

        for phase in ("mkstemp", "write", "replace"):
            with self.subTest(phase=phase):
                self.assert_failed_save_keeps_previous_cursor(
                    phase, errno.ENOSPC, "E_INTERNAL", 1
                )

    def test_ut_st_05_02_access_denied_is_permission_error_and_keeps_the_cursor(self) -> None:
        """UT-ST-05.02: EACCES/EPERM while writing => E_PERMISSION, previous cursor intact."""
        import errno

        for phase in ("mkstemp", "write", "replace"):
            for code in (errno.EACCES, errno.EPERM):
                with self.subTest(phase=phase, errno=code):
                    self.assert_failed_save_keeps_previous_cursor(
                        phase, code, "E_PERMISSION", 3
                    )

    def test_other_write_errors_keep_their_current_code(self) -> None:
        """Errors other than ENOSPC/EACCES/EPERM are not remapped."""
        import errno

        self.store.save(AppState(updated_at="previous"))
        with mock.patch(
            "mailquery.state.tempfile.mkstemp", side_effect=OSError(errno.EIO, "I/O error")
        ):
            with self.assertRaises(MailqueryError) as caught:
                self.store.save(AppState(updated_at="next"))
        self.assertEqual(caught.exception.code, "E_PERMISSION")
        with mock.patch("mailquery.state.os.fsync", side_effect=OSError(errno.EIO, "I/O error")):
            with self.assertRaises(OSError) as raw:
                self.store.save(AppState(updated_at="next"))
        self.assertNotIsInstance(raw.exception, MailqueryError)
        self.assertEqual(self.store.load().updated_at, "previous")

    def test_corrupt_json_raises_state_corrupt(self) -> None:
        self.home.mkdir(parents=True)
        self.store.path.write_text("{not json", encoding="utf-8")
        with self.assertRaises(MailqueryError) as caught:
            self.store.load()
        error = caught.exception
        self.assertEqual(error.code, "E_STATE_CORRUPT")
        self.assertEqual(error.exit_code, 3)
        self.assertIn("rename", error.hint.lower())

    def test_corrupt_utf8_raises_state_corrupt(self) -> None:
        self.home.mkdir(parents=True)
        self.store.path.write_bytes(b"\xff\xfe\x00state")
        with self.assertRaises(MailqueryError) as caught:
            self.store.load()
        self.assertEqual(caught.exception.code, "E_STATE_CORRUPT")

    def test_non_object_json_raises_state_corrupt(self) -> None:
        self.home.mkdir(parents=True)
        self.store.path.write_text("[1, 2, 3]", encoding="utf-8")
        with self.assertRaises(MailqueryError) as caught:
            self.store.load()
        self.assertEqual(caught.exception.code, "E_STATE_CORRUPT")

    def test_schema_2_is_valid(self) -> None:
        self.home.mkdir(parents=True)
        self.store.path.write_text(
            json.dumps(
                {
                    "schema": 2,
                    "cursor": {
                        "last_date_received": 100,
                        "last_uid": _PREFIXED,
                        "lookback_seconds": 600,
                    },
                    "emitted_uids": [_PREFIXED],
                }
            ),
            encoding="utf-8",
        )
        state = self.store.load()
        self.assertEqual(state.schema, 2)
        assert state.cursor is not None
        self.assertEqual(state.cursor.last_uid, _PREFIXED)
        self.assertEqual(state.emitted_uids, (_PREFIXED,))
        self.assertEqual(self.store.load_info.persisted_schema, 2)
        self.assertFalse(self.store.load_info.migrated)

    def test_malformed_known_fields_raise_state_corrupt(self) -> None:
        bad_payloads = (
            {"schema": 2, "cursor": []},
            {"schema": 2, "cursor": {"last_date_received": "x"}},
            {"schema": 2, "cursor": {"last_uid": _PREFIXED, "lookback_seconds": 0}},
            {"schema": 2, "last_run": {"command": "new"}},
            {"schema": 2, "last_run": "new"},
            {"schema": 2, "emitted_uids": "83143"},
            {"schema": 2, "emitted_uids": ["83143"]},
            {"schema": 2, "updated_at": 42},
        )
        self.home.mkdir(parents=True, exist_ok=True)
        for payload in bad_payloads:
            with self.subTest(payload=payload):
                self.store.path.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaises(MailqueryError) as caught:
                    self.store.load()
                self.assertEqual(caught.exception.code, "E_STATE_CORRUPT")

    def _load_cursor_payload(self, cursor: object, schema: int = 2) -> AppState:
        self.home.mkdir(parents=True, exist_ok=True)
        payload = {"schema": schema, "cursor": cursor, "emitted_uids": []}
        self.store.path.write_text(json.dumps(payload), encoding="utf-8")
        return self.store.load()

    def _assert_state_corrupt(self, payload: dict) -> MailqueryError:
        self.home.mkdir(parents=True, exist_ok=True)
        self.store.path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(MailqueryError) as caught:
            self.store.load()
        self.assertEqual(caught.exception.code, "E_STATE_CORRUPT")
        self.assertEqual(caught.exception.exit_code, 3)
        return caught.exception

    def test_ut_st_02_01_empty_cursor_object_is_corrupt(self) -> None:
        """UT-ST-02.01: ``cursor: {}`` is E_STATE_CORRUPT (no ``last_uid``)."""
        self._assert_state_corrupt({"schema": 2, "cursor": {}})

    def test_ut_st_02_02_negative_last_date_received_is_corrupt(self) -> None:
        """UT-ST-02.02: a negative ``last_date_received`` is E_STATE_CORRUPT."""
        self._assert_state_corrupt(
            {
                "schema": 2,
                "cursor": {"last_date_received": -1, "last_uid": _PREFIXED},
            }
        )

    def test_ut_st_02_06_null_cursor_means_no_cursor(self) -> None:
        """UT-ST-02.06: ``cursor: null`` means no stored cursor."""
        self.assertIsNone(self._load_cursor_payload(None).cursor)

    def test_ut_st_04_01_hint_says_the_next_run_is_a_first_run_that_emits_the_window(self) -> None:
        """UT-ST-04.01: the hint renames the file; the next run is a first run that emits the window."""
        self.home.mkdir(parents=True)
        self.store.path.write_text("{not json", encoding="utf-8")
        with self.assertRaises(MailqueryError) as caught:
            self.store.load()
        hint = caught.exception.hint.lower()
        self.assertIn("rename", hint)
        self.assertIn("first run", hint)
        self.assertIn("emits the messages of the lookback window", hint)
        self.assertNotIn("baseline", hint)
        self.assertNotIn("emits nothing", hint)

    def test_unknown_keys_are_ignored(self) -> None:
        self.home.mkdir(parents=True)
        payload = {
            "schema": 2,
            "server": "future-field",
            "cursor": {
                "last_date_received": 10,
                "last_uid": _PREFIXED,
                "future": True,
            },
            "emitted_uids": [_PREFIXED],
        }
        self.store.path.write_text(json.dumps(payload), encoding="utf-8")
        state = self.store.load()
        self.assertEqual(
            state.cursor,
            Cursor(last_date_received=10, last_uid=_PREFIXED),
        )
        self.assertEqual(state.emitted_uids, (_PREFIXED,))

    def test_state_never_contains_pii(self) -> None:
        self.store.save(self.store.record_new(AppState(), [_apple(1793573649, 83143)], 600))
        raw = self.store.path.read_text(encoding="utf-8")
        payload = json.loads(raw)
        self.assertEqual(
            set(payload),
            {"schema", "updated_at", "last_run", "cursor", "emitted_uids"},
        )
        self.assertNotIn("@", raw)

    def test_permission_error_reading_state_is_e_permission(self) -> None:
        with mock.patch.object(
            Path, "read_text", side_effect=PermissionError(1, "Operation not permitted")
        ):
            with self.assertRaises(MailqueryError) as caught:
                self.store.load()
        self.assertEqual(caught.exception.code, "E_PERMISSION")
        self.assertEqual(caught.exception.exit_code, 3)

    def test_failed_write_keeps_previous_state_and_no_temp_file(self) -> None:
        original = AppState(
            updated_at="original",
            cursor=Cursor(last_date_received=100, last_uid="apple_mail:1"),
        )
        self.store.save(original)
        original_text = self.store.path.read_text(encoding="utf-8")

        replacement = AppState(updated_at="replacement")
        with mock.patch(
            "mailquery.state.os.replace",
            side_effect=OSError(5, "Input/output error"),
        ):
            with self.assertRaises(OSError):
                self.store.save(replacement)

        self.assertEqual(self.store.path.read_text(encoding="utf-8"), original_text)
        self.assertEqual(self.store.load(), original)
        leftovers = [p.name for p in self.home.iterdir() if p.name.startswith(".state-")]
        self.assertEqual(leftovers, [])


class MigrationTest(unittest.TestCase):
    """UT-ST-06.01-.03: schema-1 uid migration by value type (PRD §11.2)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="mailquery-state-")
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name) / "home"
        self.home.mkdir(parents=True)
        self.store = _store(self.home)

    def _write(self, payload: dict) -> None:
        self.store.path.write_text(json.dumps(payload), encoding="utf-8")

    def _write_legacy(self, last_uid: object, emitted: list) -> None:
        self._write(
            {
                "schema": 1,
                "updated_at": "",
                "last_run": None,
                "cursor": {
                    "last_date_received": 100,
                    "last_uid": last_uid,
                    "lookback_seconds": 600,
                },
                "emitted_uids": emitted,
            }
        )

    def test_ut_st_06_01_integers_migrate_to_apple_mail_regardless_of_platform(self) -> None:
        """UT-ST-06.01: integer uids >= 1 in cursor and ring => apple_mail:<n>, OS-independent."""
        for platform in ("darwin", "win32", "linux"):
            with self.subTest(platform=platform), mock.patch.object(sys, "platform", platform):
                self.assertEqual(migrate_uid(83143), "apple_mail:83143")
                self.assertEqual(migrate_uid(1), "apple_mail:1")
                self._write_legacy(83143, [83135, 83138, 83143])
                state = self.store.load()
                assert state.cursor is not None
                self.assertEqual(state.cursor.last_uid, "apple_mail:83143")
                self.assertEqual(
                    state.emitted_uids,
                    ("apple_mail:83135", "apple_mail:83138", "apple_mail:83143"),
                )
                self.assertEqual(self.store.load_info.persisted_schema, 1)
                self.assertTrue(self.store.load_info.migrated)

    def test_ut_st_06_02_uppercase_hex_migrates_to_outlook(self) -> None:
        """UT-ST-06.02: upper-case hexadecimal strings => outlook:<HEX>; digits-only hex is accepted."""
        self.assertEqual(migrate_uid(_HEX), f"outlook:{_HEX}")
        # A string of digits is valid upper-case hexadecimal (Outlook's own shape), so it
        # migrates by type and must not be reinterpreted as an Apple Mail uid.
        self.assertEqual(migrate_uid("83143"), "outlook:83143")
        self._write_legacy(_HEX, ["0000000000000001", _HEX])
        state = self.store.load()
        assert state.cursor is not None
        self.assertEqual(state.cursor.last_uid, f"outlook:{_HEX}")
        self.assertEqual(
            state.emitted_uids,
            ("outlook:0000000000000001", f"outlook:{_HEX}"),
        )

    def test_ut_st_06_02_mixed_types_migrate_independently(self) -> None:
        """UT-ST-06.02: the cursor and each ring item migrate by their own value type."""
        self._write_legacy(83143, [_HEX])
        state = self.store.load()
        assert state.cursor is not None
        self.assertEqual(state.cursor.last_uid, "apple_mail:83143")
        self.assertEqual(state.emitted_uids, (f"outlook:{_HEX}",))

    def test_ut_st_06_03_invalid_legacy_values_are_state_corrupt(self) -> None:
        """UT-ST-06.03: 0, negatives, bool, None, lists and non-hex formats => E_STATE_CORRUPT."""
        invalid = (0, -1, -83143, True, False, None, [], {}, 1.5, "00ab", "abc", "0x10", "1 2", "")
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(MailqueryError) as caught:
                    migrate_uid(value)
                self.assertEqual(caught.exception.code, "E_STATE_CORRUPT")
                self.assertEqual(caught.exception.exit_code, 3)
                self.assertIn("rename", caught.exception.hint.lower())

        for value in (0, -1, True, None, [], "00ab"):
            with self.subTest(cursor=value):
                self._write_legacy(value, [_LEGACY_INT])
                with self.assertRaises(MailqueryError) as caught:
                    self.store.load()
                self.assertEqual(caught.exception.code, "E_STATE_CORRUPT")
                self.assertIn("rename", caught.exception.hint.lower())

        for value in (0, -1, True, None, [], "00ab"):
            with self.subTest(ring=value):
                self._write_legacy(_LEGACY_INT, [value])
                with self.assertRaises(MailqueryError) as caught:
                    self.store.load()
                self.assertEqual(caught.exception.code, "E_STATE_CORRUPT")

    def test_ut_st_06_03_lowercase_hex_is_not_reinterpreted(self) -> None:
        """UT-ST-06.03: lower-case hex is a different (invalid) format, never upper-cased."""
        for value in ("d70dbcf6", "00ab", "AbC123"):
            with self.subTest(value=value):
                with self.assertRaises(MailqueryError):
                    migrate_uid(value)


class Schema2ValidationTest(unittest.TestCase):
    """UT-ST-07: schema-2 validation and ring pruning (PRD §11.2)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="mailquery-state-")
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name) / "home"
        self.home.mkdir(parents=True)
        self.store = _store(self.home)

    def _write(self, payload: dict) -> None:
        self.store.path.write_text(json.dumps(payload), encoding="utf-8")

    def _write_schema_2(self, last_uid: object, emitted: list | None = None) -> None:
        self._write(
            {
                "schema": 2,
                "updated_at": "",
                "last_run": None,
                "cursor": {
                    "last_date_received": 100,
                    "last_uid": last_uid,
                    "lookback_seconds": 600,
                },
                "emitted_uids": [] if emitted is None else emitted,
            }
        )

    def _assert_corrupt(self, payload: dict) -> MailqueryError:
        self._write(payload)
        with self.assertRaises(MailqueryError) as caught:
            self.store.load()
        self.assertEqual(caught.exception.code, "E_STATE_CORRUPT")
        self.assertEqual(caught.exception.exit_code, 3)
        return caught.exception

    def test_ut_st_07_01_cursor_uid_shape_and_length_are_corrupt(self) -> None:
        """UT-ST-07.01: a non-prefixed, malformed or > 1024 uid in ``last_uid`` => E_STATE_CORRUPT."""
        invalid = (
            83143,
            "83143",
            "",
            "Apple_Mail:1",
            "apple_mail:",
            "apple_mail:a/b",
            "apple_mail:.hidden",
            "apple_mail:a..b",
            "apple_mail:" + "1" * 1025,
            "outlook:" + "A" * 1025,
            None,
            [],
        )
        for value in invalid:
            with self.subTest(value=str(value)[:40]):
                error = self._assert_corrupt(
                    {
                        "schema": 2,
                        "cursor": {"last_date_received": 100, "last_uid": value},
                    }
                )
                self.assertIn("cursor.last_uid", error.message)

    def test_ut_st_07_01_ring_item_shape_is_corrupt(self) -> None:
        """UT-ST-07.01: a malformed ``emitted_uids`` item => E_STATE_CORRUPT."""
        for value in (83143, "83143", "", "apple_mail:a b", "outlook:" + "a" * 1025):
            with self.subTest(value=str(value)[:40]):
                self._assert_corrupt({"schema": 2, "emitted_uids": [_PREFIXED, value]})

    def test_ut_st_07_02_cursor_driver_not_installed_is_corrupt_with_hint(self) -> None:
        """UT-ST-07.02: a cursor uid of a driver that is not installed => E_STATE_CORRUPT."""
        self.store = _store(self.home, _apple_only)
        error = self._assert_corrupt(
            {
                "schema": 2,
                "cursor": {"last_date_received": 100, "last_uid": "graph:1"},
            }
        )
        self.assertIn("graph", error.message)
        self.assertIn("reinstall", error.hint.lower())
        self.assertIn("rename", error.hint.lower())

    def test_ut_st_07_03_uninstalled_ring_items_are_pruned_in_silence(self) -> None:
        """UT-ST-07.03: ring items of uninstalled drivers are dropped and reported."""
        self.store = _store(self.home, _apple_only)
        self._write_schema_2(
            "apple_mail:1",
            ["apple_mail:1", "graph:1", "graph:2", "outlook:" + _HEX],
        )
        state = self.store.load()
        self.assertEqual(state.emitted_uids, ("apple_mail:1",))
        info = self.store.load_info
        self.assertEqual(info.pruned_emitted_uids, 3)
        self.assertEqual(info.pruned_drivers, ("graph", "outlook"))

    def test_ut_st_07_03_pruning_keeps_the_installed_ring_order(self) -> None:
        """UT-ST-07.03: pruning keeps the remaining uids in their stored order."""
        self.store = _store(self.home, _apple_only)
        self._write_schema_2(
            "apple_mail:3",
            ["graph:1", "apple_mail:1", "graph:2", "apple_mail:2"],
        )
        state = self.store.load()
        self.assertEqual(
            state.emitted_uids, ("apple_mail:1", "apple_mail:2")
        )
        self.assertEqual(self.store.load_info.pruned_emitted_uids, 2)

    def test_ut_st_07_04_migrated_uid_longer_than_1024_is_corrupt(self) -> None:
        """UT-ST-07.04: a migrated uid above the 1024 limit => E_STATE_CORRUPT."""
        huge_int = int("9" * 1025)
        self._write(
            {
                "schema": 1,
                "cursor": {"last_date_received": 100, "last_uid": huge_int},
            }
        )
        with self.assertRaises(MailqueryError) as caught:
            self.store.load()
        self.assertEqual(caught.exception.code, "E_STATE_CORRUPT")

        self._write(
            {
                "schema": 1,
                "cursor": {"last_date_received": 100, "last_uid": "A" * 1025},
            }
        )
        with self.assertRaises(MailqueryError) as caught:
            self.store.load()
        self.assertEqual(caught.exception.code, "E_STATE_CORRUPT")

    def test_ut_st_07_05_schema_absent_bool_or_unknown_is_corrupt(self) -> None:
        """UT-ST-07.05: a missing, boolean or out-of-range ``schema`` => E_STATE_CORRUPT."""
        payloads = (
            {},
            {"cursor": None},
            {"schema": True},
            {"schema": False},
            {"schema": 0},
            {"schema": 3},
            {"schema": "1"},
            {"schema": None},
            {"schema": 1.0},
        )
        for payload in payloads:
            with self.subTest(payload=payload):
                self._assert_corrupt(payload)


class RecordNewTest(unittest.TestCase):
    """Cursor advancement, ring cap and ordering semantics (PRD §11.3)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="mailquery-state-")
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name) / "home"
        self.store = _store(self.home)

    def test_record_new_does_not_persist_by_itself(self) -> None:
        # The caller (search.run_new) owns persistence so --peek can skip it.
        new_state = self.store.record_new(AppState(), [_apple(100, 10)], 600)
        self.assertFalse(self.store.path.exists())
        self.store.save(new_state)
        self.assertEqual(self.store.load(), new_state)

    def test_first_record_advances_cursor_and_ring(self) -> None:
        new_state = self.store.record_new(
            AppState(), [_apple(100, 10), _apple(200, 20)], 600
        )
        self.assertEqual(
            new_state.cursor,
            Cursor(last_date_received=200, last_uid="apple_mail:20"),
        )
        self.assertEqual(new_state.emitted_uids, ("apple_mail:10", "apple_mail:20"))
        self.assertEqual(new_state.last_run.command, "new")
        self.assertTrue(new_state.last_run.at)
        self.assertTrue(new_state.updated_at)
        self.assertEqual(new_state.schema, STATE_SCHEMA)
        self.store.save(new_state)
        self.assertEqual(self.store.load(), new_state)

    def test_ring_is_chronological_even_for_descending_input(self) -> None:
        new_state = self.store.record_new(
            AppState(), [_apple(300, 30), _apple(100, 10), _apple(200, 20)], 600
        )
        self.assertEqual(
            new_state.emitted_uids,
            ("apple_mail:10", "apple_mail:20", "apple_mail:30"),
        )
        assert new_state.cursor is not None
        self.assertEqual(new_state.cursor.last_uid, "apple_mail:30")

    def test_ring_uses_native_order_key_not_uid_text(self) -> None:
        # "apple_mail:10" sorts before "apple_mail:2" as text; numeric order is 2 then 10.
        new_state = self.store.record_new(
            AppState(),
            [_apple(500, 10), _apple(500, 2)],
            600,
        )
        self.assertEqual(new_state.emitted_uids, ("apple_mail:2", "apple_mail:10"))
        assert new_state.cursor is not None
        self.assertEqual(new_state.cursor.last_uid, "apple_mail:10")

    def test_ring_orders_same_date_by_driver_then_native_key(self) -> None:
        # Total order at the same date: driver ASC, then the driver's native key ASC.
        new_state = self.store.record_new(
            AppState(),
            [_outlook(500, "B"), _apple(500, 5), _outlook(500, "A")],
            600,
        )
        self.assertEqual(
            new_state.emitted_uids,
            ("apple_mail:5", "outlook:A", "outlook:B"),
        )

    def test_record_new_without_emitted_keeps_missing_cursor(self) -> None:
        new_state = self.store.record_new(AppState(), [], 600)
        self.assertIsNone(new_state.cursor)
        self.assertEqual(new_state.emitted_uids, ())
        self.assertEqual(new_state.last_run.command, "new")

    def test_record_new_without_emitted_preserves_existing_cursor(self) -> None:
        state = AppState(
            cursor=Cursor(
                last_date_received=500, last_uid="apple_mail:900", lookback_seconds=300
            )
        )
        new_state = self.store.record_new(state, [], 300)
        self.assertEqual(new_state.cursor, state.cursor)

    def test_cursor_never_regresses(self) -> None:
        state = AppState(
            cursor=Cursor(
                last_date_received=500, last_uid="apple_mail:900", lookback_seconds=900
            )
        )
        new_state = self.store.record_new(state, [_apple(100, 5)], 900)
        self.assertEqual(new_state.cursor, state.cursor)
        self.assertEqual(new_state.emitted_uids, ("apple_mail:5",))

    def test_cursor_advances_on_newer_date_and_stores_the_given_lookback(self) -> None:
        # The lookback comes from the current config, not from the state.
        state = AppState(
            cursor=Cursor(
                last_date_received=500, last_uid="apple_mail:900", lookback_seconds=900
            )
        )
        new_state = self.store.record_new(state, [_apple(600, 5)], 300)
        self.assertEqual(
            new_state.cursor,
            Cursor(last_date_received=600, last_uid="apple_mail:5", lookback_seconds=300),
        )

    def test_cursor_advances_on_same_date_with_a_different_uid(self) -> None:
        state = AppState(
            cursor=Cursor(last_date_received=500, last_uid="apple_mail:900")
        )
        new_state = self.store.record_new(state, [_apple(500, 950)], 600)
        self.assertEqual(
            new_state.cursor,
            Cursor(last_date_received=500, last_uid="apple_mail:950"),
        )

    def test_custom_command_is_recorded(self) -> None:
        new_state = self.store.record_new(AppState(), [], 600, command="doctor")
        self.assertEqual(new_state.last_run.command, "doctor")

    def test_ring_caps_at_max_and_drops_oldest(self) -> None:
        state = AppState(
            emitted_uids=tuple(f"apple_mail:{index}" for index in range(MAX_EMITTED_UIDS))
        )
        new_state = self.store.record_new(state, [_apple(9999, 9999)], 600)
        self.assertEqual(len(new_state.emitted_uids), MAX_EMITTED_UIDS)
        self.assertNotIn("apple_mail:0", new_state.emitted_uids)
        self.assertIn(
            f"apple_mail:{MAX_EMITTED_UIDS - 1}", new_state.emitted_uids
        )
        self.assertEqual(new_state.emitted_uids[-1], "apple_mail:9999")

    def test_ring_does_not_duplicate_an_emitted_uid(self) -> None:
        state = AppState(
            emitted_uids=("apple_mail:1", "apple_mail:2", "apple_mail:3")
        )
        new_state = self.store.record_new(state, [_apple(400, 2)], 600)
        self.assertEqual(
            new_state.emitted_uids,
            ("apple_mail:1", "apple_mail:3", "apple_mail:2"),
        )

    def test_ring_longer_than_max_is_trimmed_on_load(self) -> None:
        self.home.mkdir(parents=True)
        uids = [f"apple_mail:{index}" for index in range(1, MAX_EMITTED_UIDS + 6)]
        payload = {"schema": 2, "emitted_uids": uids}
        self.store.path.write_text(json.dumps(payload), encoding="utf-8")
        self.assertEqual(
            self.store.load().emitted_uids,
            tuple(uids[-MAX_EMITTED_UIDS:]),
        )

    def test_boolean_uid_is_corrupt_on_macos(self) -> None:
        # PRD 11.2: bool is not an integer uid (and schema 1 migrates by value type).
        self.home.mkdir(parents=True)
        self.store.path.write_text(
            json.dumps({"schema": 1, "emitted_uids": [True]}), encoding="utf-8"
        )
        with self.assertRaises(MailqueryError) as caught:
            self.store.load()
        self.assertEqual(caught.exception.code, "E_STATE_CORRUPT")


class RunLockTest(unittest.TestCase):
    """Non-blocking flock behaviour (PRD 21.3)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="mailquery-lock-")
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name) / "home"

    def test_ut_st_01_01_lock_path_and_modes(self) -> None:
        """UT-ST-01.01: Lock file is created under locks/; POSIX modes are 0600/0700."""
        self.assertEqual(RunLock(self.home).path, self.home / "locks" / "mailquery.lock")
        lock = RunLock(self.home)
        lock.acquire()
        try:
            self.assertTrue(lock.path.is_file())
            if os.name == "posix":
                self.assertEqual(lock.path.stat().st_mode & 0o777, 0o600)
                self.assertEqual(lock.path.parent.stat().st_mode & 0o777, 0o700)
        finally:
            lock.release()

    def test_ut_st_01_02_second_acquisition_raises_e_locked(self) -> None:
        """UT-ST-01.02: A second acquisition fails with E_LOCKED (exit 5) and a hint."""
        first = RunLock(self.home)
        first.acquire()
        self.addCleanup(first.release)
        second = RunLock(self.home)
        with self.assertRaises(MailqueryError) as caught:
            second.acquire()
        self.assertEqual(caught.exception.code, "E_LOCKED")
        self.assertEqual(caught.exception.exit_code, 5)
        self.assertTrue(caught.exception.hint)

    def test_ut_st_01_03_lock_can_be_taken_again_after_release(self) -> None:
        """UT-ST-01.03: The lock can be acquired again after release."""
        first = RunLock(self.home)
        first.acquire()
        first.release()
        second = RunLock(self.home)
        second.acquire()
        second.release()

    def test_ut_st_01_04_context_manager_releases_on_exit(self) -> None:
        """UT-ST-01.04: Leaving the context manager releases the lock."""
        with RunLock(self.home):
            pass
        with RunLock(self.home):
            pass

    def test_ut_st_01_05_context_manager_releases_on_exception(self) -> None:
        """UT-ST-01.05: An exception inside the context manager still releases the lock."""
        with self.assertRaises(RuntimeError):
            with RunLock(self.home):
                raise RuntimeError("boom")
        with RunLock(self.home):
            pass

    def test_ut_st_01_06_acquire_is_idempotent_per_instance(self) -> None:
        """UT-ST-01.06: Acquiring twice on one instance is a no-op."""
        lock = RunLock(self.home)
        lock.acquire()
        lock.acquire()
        lock.release()
        lock.release()

    def test_ut_st_01_07_release_without_acquire_is_safe(self) -> None:
        """UT-ST-01.07: Releasing a lock that was never acquired is safe."""
        RunLock(self.home).release()


class PeekThroughRunNewTest(unittest.TestCase):
    """``--peek`` must not persist the cursor (PRD 18, 12.3; UT-ST-06.04/.05)."""

    _PREFIXED_WINDOW = {
        "apple_mail:83143",
        "apple_mail:83150",
        "apple_mail:83160",
        "apple_mail:83170",
    }

    def _pipeline(self, *, schema: int = 1):
        from tests.fixtures.make_fixtures import build_store, write_config, write_state

        fx = build_store()
        self.addCleanup(fx.cleanup)
        write_config(fx.home)
        legacy_uid = 1 if schema == 1 else "apple_mail:1"
        seed = {
            "schema": schema,
            "updated_at": "",
            "last_run": None,
            "cursor": {
                "last_date_received": int((fx.now - timedelta(hours=2)).timestamp()),
                "last_uid": legacy_uid,
                "lookback_seconds": 600,
            },
            "emitted_uids": [],
        }
        write_state(fx.home, seed)
        from mailquery.accounts import AccountLabels
        from mailquery.backends.apple_mail import AppleMailBackend
        from mailquery.config import load_config
        from mailquery.store import open_store

        store = open_store(mail_root=fx.mail_root, tmp_root=fx.home / "tmp")
        labels = AccountLabels(db_path=fx.accounts_db, tmp_dir=fx.home / "tmp")
        config = load_config(fx.home)
        self.addCleanup(store.close)
        return fx, store, config, labels, _store(fx.home)

    def _backend(self, store, labels):
        from mailquery.backends.apple_mail import AppleMailBackend

        return AppleMailBackend(store, labels)

    def test_peek_does_not_advance_then_normal_run_does(self) -> None:
        from mailquery.search import run_new

        fx, store, config, labels, state_store = self._pipeline()

        peeked = run_new(self._backend(store, labels), config, state_store, peek=True)

        self.assertEqual(
            {message["uid"] for message in peeked["messages"]},
            self._PREFIXED_WINDOW,
        )
        after_peek = _store(fx.home).load()
        assert after_peek.cursor is not None
        self.assertEqual(after_peek.cursor.last_uid, "apple_mail:1")

        emitted = run_new(self._backend(store, labels), config, state_store)
        again = run_new(self._backend(store, labels), config, state_store)
        self.assertEqual(
            {message["uid"] for message in emitted["messages"]},
            self._PREFIXED_WINDOW,
        )
        after_run = _store(fx.home).load()
        assert after_run.cursor is not None
        self.assertEqual(after_run.cursor.last_uid, "apple_mail:83170")
        self.assertEqual(set(after_run.emitted_uids), self._PREFIXED_WINDOW)

        self.assertEqual(again["count"], 0)

    def test_ut_st_06_04_peek_migrates_schema_1_in_memory_and_does_not_write(self) -> None:
        """UT-ST-06.04: ``new --peek`` migrates in memory, writes nothing and returns the cursor."""
        from mailquery.search import run_new

        fx, store, config, labels, state_store = self._pipeline(schema=1)
        before = (fx.home / "state.json").read_bytes()

        peeked = run_new(self._backend(store, labels), config, state_store, peek=True)

        self.assertEqual((fx.home / "state.json").read_bytes(), before)
        cursor = peeked["cursor"]
        self.assertEqual(cursor["previous"]["last_uid"], "apple_mail:1")
        # A peek never advances the cursor: the migrated previous cursor is returned.
        self.assertEqual(cursor["current"]["last_uid"], "apple_mail:1")
        self.assertEqual(
            {message["uid"] for message in peeked["messages"]},
            self._PREFIXED_WINDOW,
        )
        self.assertEqual(state_store.load_info.migrated, True)

    def test_ut_st_06_05_next_new_run_persists_schema_2_atomically(self) -> None:
        """UT-ST-06.05: the next non-peek ``new`` persists schema 2 with the atomic write."""
        from mailquery.search import run_new

        fx, store, config, labels, state_store = self._pipeline(schema=1)

        emitted = run_new(self._backend(store, labels), config, state_store)

        self.assertEqual(emitted["cursor"]["previous"]["last_uid"], "apple_mail:1")
        self.assertEqual(emitted["cursor"]["current"]["last_uid"], "apple_mail:83170")
        payload = json.loads((fx.home / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["schema"], 2)
        self.assertEqual(payload["cursor"]["last_uid"], "apple_mail:83170")
        self.assertEqual(
            set(payload["emitted_uids"]), self._PREFIXED_WINDOW
        )
        self.assertEqual(
            [path.name for path in fx.home.glob(".state-*.tmp")], []
        )
        reloaded = _store(fx.home)
        reloaded.load()
        self.assertEqual(reloaded.load_info.persisted_schema, 2)
        self.assertFalse(reloaded.load_info.migrated)

    def test_ut_st_06_07_uninstalled_ring_items_do_not_break_new(self) -> None:
        """UT-ST-06.07: ring uids of an uninstalled driver are pruned and ``new`` still runs."""
        from mailquery.search import run_new

        fx, store, config, labels, state_store = self._pipeline(schema=2)
        from tests.fixtures.make_fixtures import write_state

        write_state(
            fx.home,
            {
                "schema": 2,
                "updated_at": "",
                "last_run": None,
                "cursor": {
                    "last_date_received": int((fx.now - timedelta(hours=2)).timestamp()),
                    "last_uid": "apple_mail:1",
                    "lookback_seconds": 600,
                },
                "emitted_uids": ["graph:1", "graph:2"],
            },
        )
        result = run_new(
            self._backend(store, labels), config, _store(fx.home), peek=True
        )
        self.assertEqual(
            {message["uid"] for message in result["messages"]},
            self._PREFIXED_WINDOW,
        )
        loaded = _store(fx.home, _apple_only)
        loaded.load()
        self.assertEqual(loaded.load_info.pruned_emitted_uids, 2)
        self.assertEqual(loaded.load_info.pruned_drivers, ("graph",))


if __name__ == "__main__":  # pragma: no cover - manual runs
    unittest.main()

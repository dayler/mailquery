"""Tests for :mod:`mailquery.state` (PRD 11.2, 18, 21.3).

Covers the atomic ``state.json`` lifecycle (defaults, roundtrip, 0600 mode,
corruption), the ``new`` cursor and emitted-uid ring semantics, the
non-blocking run lock and the ``--peek`` guarantee end to end through
``search.run_new`` when that module is implemented.
"""

from __future__ import annotations

import json
import os
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
    LastRun,
    RunLock,
    StateStore,
)


class StateStoreTest(unittest.TestCase):
    """Atomic persistence and corruption handling."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="mailquery-state-")
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name) / "home"
        self.store = StateStore(self.home)

    def test_path_is_state_json_under_home(self) -> None:
        self.assertEqual(self.store.path, self.home / "state.json")
        self.assertEqual(self.store.home, self.home)

    def test_missing_file_returns_defaults_without_creating_anything(self) -> None:
        state = self.store.load()
        self.assertEqual(state, AppState())
        self.assertEqual(state.schema, STATE_SCHEMA)
        self.assertEqual(state.updated_at, "")
        self.assertIsNone(state.last_run)
        self.assertIsNone(state.cursor)
        self.assertEqual(state.emitted_uids, ())
        self.assertFalse(self.home.exists())

    def test_roundtrip_preserves_every_field(self) -> None:
        state = AppState(
            schema=STATE_SCHEMA,
            updated_at="2026-11-02T02:15:00-04:00",
            last_run=LastRun(command="new", at="2026-11-02T02:15:00-04:00"),
            cursor=Cursor(last_date_received=1793573649, last_uid=83143, lookback_seconds=900),
            emitted_uids=(83135, 83138, 83143),
        )
        self.store.save(state)
        self.assertEqual(self.store.load(), state)

        payload = json.loads(self.store.path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema"], 1)
        self.assertEqual(payload["cursor"]["last_uid"], 83143)
        self.assertEqual(payload["emitted_uids"], [83135, 83138, 83143])

    def test_state_file_is_0600_and_home_is_0700(self) -> None:
        self.store.save(AppState())
        self.assertTrue(self.store.path.is_file())
        if os.name == "posix":
            self.assertEqual(self.store.path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(self.home.stat().st_mode & 0o777, 0o700)

    def test_creating_state_in_nested_missing_home(self) -> None:
        nested = Path(self._tmp.name) / "a" / "b" / "home"
        StateStore(nested).save(AppState())
        self.assertTrue((nested / "state.json").is_file())

    def test_save_overwrites_previous_content(self) -> None:
        self.store.save(AppState(updated_at="first"))
        self.store.save(AppState(updated_at="second"))
        self.assertEqual(self.store.load().updated_at, "second")

    def assert_failed_save_keeps_previous_cursor(self, phase: str, code: int, expected: str, exit_code: int) -> None:
        previous = AppState(
            updated_at="previous",
            cursor=Cursor(last_date_received=1793573649, last_uid=83143, lookback_seconds=600),
            emitted_uids=(83143,),
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
        """B-24: errors other than ENOSPC/EACCES/EPERM are not remapped."""
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

    def test_unsupported_schema_raises_state_corrupt(self) -> None:
        for schema in (0, 2, "1", True, None):
            with self.subTest(schema=schema):
                self.home.mkdir(parents=True, exist_ok=True)
                self.store.path.write_text(json.dumps({"schema": schema}), encoding="utf-8")
                with self.assertRaises(MailqueryError) as caught:
                    self.store.load()
                self.assertEqual(caught.exception.code, "E_STATE_CORRUPT")

    def test_malformed_known_fields_raise_state_corrupt(self) -> None:
        bad_payloads = (
            {"schema": 1, "cursor": []},
            {"schema": 1, "cursor": {"last_date_received": "x"}},
            {"schema": 1, "cursor": {"last_uid": -1}},
            {"schema": 1, "cursor": {"lookback_seconds": 0}},
            {"schema": 1, "last_run": {"command": "new"}},
            {"schema": 1, "last_run": "new"},
            {"schema": 1, "emitted_uids": "83143"},
            {"schema": 1, "emitted_uids": ["83143"]},
            {"schema": 1, "updated_at": 42},
        )
        self.home.mkdir(parents=True, exist_ok=True)
        for payload in bad_payloads:
            with self.subTest(payload=payload):
                self.store.path.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaises(MailqueryError) as caught:
                    self.store.load()
                self.assertEqual(caught.exception.code, "E_STATE_CORRUPT")

    def _load_cursor_payload(self, cursor: object) -> AppState:
        self.home.mkdir(parents=True, exist_ok=True)
        payload = {"schema": 1, "cursor": cursor, "emitted_uids": []}
        self.store.path.write_text(json.dumps(payload), encoding="utf-8")
        return self.store.load()

    def _assert_state_corrupt(self, payload: dict) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        self.store.path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(MailqueryError) as caught:
            self.store.load()
        self.assertEqual(caught.exception.code, "E_STATE_CORRUPT")
        self.assertEqual(caught.exception.exit_code, 3)

    def test_ut_st_02_01_empty_cursor_object_is_corrupt(self) -> None:
        """UT-ST-02.01: ``cursor: {}`` is E_STATE_CORRUPT."""
        self._assert_state_corrupt({"schema": 1, "cursor": {}})

    def test_ut_st_02_02_negative_last_date_received_is_corrupt(self) -> None:
        """UT-ST-02.02: a negative ``last_date_received`` is E_STATE_CORRUPT."""
        self._assert_state_corrupt(
            {"schema": 1, "cursor": {"last_date_received": -1, "last_uid": 5}}
        )

    def test_ut_st_02_03_last_uid_zero_is_corrupt(self) -> None:
        """UT-ST-02.03: ``last_uid: 0`` is E_STATE_CORRUPT (uids are >= 1)."""
        self._assert_state_corrupt(
            {"schema": 1, "cursor": {"last_date_received": 100, "last_uid": 0}}
        )

    def test_ut_st_02_04_string_last_uid_is_corrupt(self) -> None:
        """UT-ST-02.04: ``last_uid: "83143"`` (the other backend's uid) is E_STATE_CORRUPT."""
        self._assert_state_corrupt(
            {"schema": 1, "cursor": {"last_date_received": 100, "last_uid": "83143"}}
        )

    def test_ut_st_02_05_emitted_uids_with_zero_is_corrupt(self) -> None:
        """UT-ST-02.05: ``emitted_uids`` containing 0 is E_STATE_CORRUPT."""
        self._assert_state_corrupt({"schema": 1, "emitted_uids": [5, 0]})

    def test_ut_st_02_06_null_cursor_means_no_cursor(self) -> None:
        """UT-ST-02.06: ``cursor: null`` means no stored cursor."""
        self.assertIsNone(self._load_cursor_payload(None).cursor)

    def test_ut_st_02_07_missing_known_keys_take_defaults(self) -> None:
        """UT-ST-02.07: the file ``{}`` (cursor absent) loads with no cursor."""
        self.home.mkdir(parents=True)
        self.store.path.write_text("{}", encoding="utf-8")
        self.assertEqual(self.store.load(), AppState())

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
            "schema": 1,
            "server": "future-field",
            "cursor": {"last_date_received": 10, "last_uid": 20, "future": True},
            "emitted_uids": [20],
        }
        self.store.path.write_text(json.dumps(payload), encoding="utf-8")
        state = self.store.load()
        self.assertEqual(state.cursor, Cursor(last_date_received=10, last_uid=20))
        self.assertEqual(state.emitted_uids, (20,))

    def test_state_never_contains_pii(self) -> None:
        self.store.save(self.store.record_new(AppState(), [(1793573649, 83143)], 600))
        raw = self.store.path.read_text(encoding="utf-8")
        payload = json.loads(raw)
        self.assertEqual(
            set(payload),
            {"schema", "updated_at", "last_run", "cursor", "emitted_uids"},
        )
        self.assertNotIn("@", raw)

    def test_permission_error_reading_state_is_e_permission(self) -> None:
        with mock.patch.object(Path, "read_text", side_effect=PermissionError(1, "Operation not permitted")):
            with self.assertRaises(MailqueryError) as caught:
                self.store.load()
        self.assertEqual(caught.exception.code, "E_PERMISSION")
        self.assertEqual(caught.exception.exit_code, 3)

    def test_failed_write_keeps_previous_state_and_no_temp_file(self) -> None:
        original = AppState(
            updated_at="original",
            cursor=Cursor(last_date_received=100, last_uid=1),
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


class RecordNewTest(unittest.TestCase):
    """Cursor advancement, ring cap and no-regression semantics."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="mailquery-state-")
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name) / "home"
        self.store = StateStore(self.home)

    def test_record_new_does_not_persist_by_itself(self) -> None:
        # The caller (search.run_new) owns persistence so --peek can skip it.
        new_state = self.store.record_new(AppState(), [(100, 10)], 600)
        self.assertFalse(self.store.path.exists())
        self.store.save(new_state)
        self.assertEqual(self.store.load(), new_state)

    def test_first_record_advances_cursor_and_ring(self) -> None:
        new_state = self.store.record_new(AppState(), [(100, 10), (200, 20)], 600)
        self.assertEqual(new_state.cursor, Cursor(last_date_received=200, last_uid=20))
        self.assertEqual(new_state.emitted_uids, (10, 20))
        self.assertEqual(new_state.last_run.command, "new")
        self.assertTrue(new_state.last_run.at)
        self.assertTrue(new_state.updated_at)
        self.assertEqual(new_state.schema, STATE_SCHEMA)
        self.store.save(new_state)
        self.assertEqual(self.store.load(), new_state)

    def test_ring_is_chronological_even_for_descending_input(self) -> None:
        new_state = self.store.record_new(AppState(), [(300, 30), (100, 10), (200, 20)], 600)
        self.assertEqual(new_state.emitted_uids, (10, 20, 30))
        self.assertEqual(new_state.cursor.last_uid, 30)

    def test_record_new_without_emitted_keeps_missing_cursor(self) -> None:
        new_state = self.store.record_new(AppState(), [], 600)
        self.assertIsNone(new_state.cursor)
        self.assertEqual(new_state.emitted_uids, ())
        self.assertEqual(new_state.last_run.command, "new")

    def test_record_new_without_emitted_preserves_existing_cursor(self) -> None:
        state = AppState(cursor=Cursor(last_date_received=500, last_uid=900, lookback_seconds=300))
        new_state = self.store.record_new(state, [], 300)
        self.assertEqual(new_state.cursor, state.cursor)

    def test_cursor_never_regresses(self) -> None:
        state = AppState(cursor=Cursor(last_date_received=500, last_uid=900, lookback_seconds=900))
        new_state = self.store.record_new(state, [(100, 5)], 900)
        self.assertEqual(new_state.cursor, state.cursor)
        self.assertEqual(new_state.emitted_uids, (5,))

    def test_cursor_advances_on_newer_date_and_stores_the_given_lookback(self) -> None:
        # B-03: the lookback comes from the current config, not from the state.
        state = AppState(cursor=Cursor(last_date_received=500, last_uid=900, lookback_seconds=900))
        new_state = self.store.record_new(state, [(600, 5)], 300)
        self.assertEqual(new_state.cursor, Cursor(last_date_received=600, last_uid=5, lookback_seconds=300))

    def test_cursor_uses_uid_as_tiebreaker(self) -> None:
        state = AppState(cursor=Cursor(last_date_received=500, last_uid=900))
        new_state = self.store.record_new(state, [(500, 950)], 600)
        self.assertEqual(new_state.cursor, Cursor(last_date_received=500, last_uid=950))

    def test_custom_command_is_recorded(self) -> None:
        new_state = self.store.record_new(AppState(), [], 600, command="doctor")
        self.assertEqual(new_state.last_run.command, "doctor")

    def test_ring_caps_at_max_and_drops_oldest(self) -> None:
        state = AppState(emitted_uids=tuple(range(MAX_EMITTED_UIDS)))
        new_state = self.store.record_new(state, [(9999, 9999)], 600)
        self.assertEqual(len(new_state.emitted_uids), MAX_EMITTED_UIDS)
        self.assertNotIn(0, new_state.emitted_uids)
        self.assertIn(MAX_EMITTED_UIDS - 1, new_state.emitted_uids)
        self.assertEqual(new_state.emitted_uids[-1], 9999)

    def test_ring_does_not_duplicate_an_emitted_uid(self) -> None:
        state = AppState(emitted_uids=(1, 2, 3))
        new_state = self.store.record_new(state, [(400, 2)], 600)
        self.assertEqual(new_state.emitted_uids, (1, 3, 2))

    def test_ring_longer_than_max_is_trimmed_on_load(self) -> None:
        self.home.mkdir(parents=True)
        payload = {"schema": 1, "emitted_uids": list(range(1, MAX_EMITTED_UIDS + 6))}
        self.store.path.write_text(json.dumps(payload), encoding="utf-8")
        self.assertEqual(self.store.load().emitted_uids, tuple(range(6, MAX_EMITTED_UIDS + 6)))


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
    """``--peek`` must not persist the cursor (PRD 18, 12.3).

    This is the state-level view of the end-to-end integration test.
    """

    def _pipeline(self):
        from tests.fixtures.make_fixtures import build_store, write_config, write_state

        fx = build_store()
        self.addCleanup(fx.cleanup)
        write_config(fx.home)
        seed = {
            "schema": 1,
            "updated_at": "",
            "last_run": None,
            "cursor": {
                "last_date_received": int((fx.now - timedelta(hours=2)).timestamp()),
                "last_uid": 1,
                "lookback_seconds": 600,
            },
            "emitted_uids": [],
        }
        write_state(fx.home, seed)
        from mailquery.accounts import AccountLabels
        from mailquery.config import load_config
        from mailquery.store import open_store

        store = open_store(mail_root=fx.mail_root, tmp_root=fx.home / "tmp")
        labels = AccountLabels(db_path=fx.accounts_db, tmp_dir=fx.home / "tmp")
        config = load_config(fx.home)
        self.addCleanup(store.close)
        return fx, store, config, labels, StateStore(fx.home)

    def test_peek_does_not_advance_then_normal_run_does(self) -> None:
        from mailquery.search import run_new

        fx, store, config, labels, state_store = self._pipeline()

        peeked = run_new(store, config, labels, state_store, peek=True)

        self.assertEqual(
            {message["uid"] for message in peeked["messages"]},
            {83143, 83150, 83160, 83170},
        )
        after_peek = StateStore(fx.home).load()
        self.assertEqual(after_peek.cursor.last_uid, 1)

        emitted = run_new(store, config, labels, state_store)
        again = run_new(store, config, labels, state_store)
        self.assertEqual(
            {message["uid"] for message in emitted["messages"]},
            {83143, 83150, 83160, 83170},
        )
        after_run = StateStore(fx.home).load()
        self.assertEqual(after_run.cursor.last_uid, 83170)
        self.assertEqual(set(after_run.emitted_uids), {83143, 83150, 83160, 83170})

        self.assertEqual(again["count"], 0)


if __name__ == "__main__":  # pragma: no cover - manual runs
    unittest.main()

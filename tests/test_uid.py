"""UT-UID-01: prefixed uid format, parsing and stable path identifier (M01, AC-05/RF-40).

Pure module tests: ``mailquery.uid`` must validate before any home/config/store
work (PRD §6.5 RF-40, §12.11 row 2, §20 AC-05).
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import timedelta
from pathlib import Path
from unittest import mock

from mailquery import cli as cli_mod
from mailquery import uid as uid_mod
from mailquery.errors import MailqueryError
from mailquery.uid import (
    DRIVER_PATTERN,
    NATIVE_ID_PATTERN,
    ParsedUid,
    format_uid,
    is_valid_driver,
    is_valid_native_id,
    parse_uid,
    split_uid,
    stable_identifier,
)


def _assert_error(testcase: unittest.TestCase, expected_code: str, call) -> MailqueryError:
    with testcase.assertRaises(MailqueryError) as context:
        call()
    testcase.assertEqual(context.exception.code, expected_code)
    return context.exception


class UidFormatTests(unittest.TestCase):
    def test_ut_uid_01_01_prefixed_uid_splits_driver_and_native_id(self) -> None:
        """UT-UID-01.01: apple_mail:83143 and outlook:ABC123 split at the first colon."""
        apple = parse_uid("apple_mail:83143", native_driver="apple_mail")
        self.assertIsInstance(apple, ParsedUid)
        self.assertEqual(apple.driver, "apple_mail")
        self.assertEqual(apple.native_id, "83143")
        self.assertEqual(apple.uid, "apple_mail:83143")
        self.assertIsInstance(apple.uid, str)
        outlook = parse_uid("outlook:ABC123", native_driver="apple_mail")
        self.assertEqual((outlook.driver, outlook.native_id), ("outlook", "ABC123"))
        self.assertEqual(outlook.uid, "outlook:ABC123")
        self.assertEqual(format_uid("apple_mail", "83143"), "apple_mail:83143")
        self.assertEqual(format_uid("outlook", "ABC123"), "outlook:ABC123")

    def test_ut_uid_01_02_native_id_charset_and_first_colon_split(self) -> None:
        """UT-UID-01.02: ``[A-Za-z0-9._=-]``; dot interior ok, leading dot and ``..`` rejected."""
        accepted = [
            "a.b",
            "ABC123",
            "a_b-c=d.e",
            "0",
            "x" * 1024,
        ]
        for value in accepted:
            with self.subTest(value=value):
                self.assertTrue(is_valid_native_id(value), value)
                self.assertIsNotNone(NATIVE_ID_PATTERN.fullmatch(value))
        for value in (".a", "a..b", "a:b", "a/b", "a b", ""):
            with self.subTest(value=value):
                self.assertFalse(is_valid_native_id(value), value)
        # Split at the first ':' only: "a:b:c" hands "b:c" to the plugin, invalid by charset.
        self.assertEqual(split_uid("a:b:c"), ("a", "b:c"))
        self.assertEqual(split_uid("apple_mail:83143"), ("apple_mail", "83143"))
        _assert_error(self, "E_USAGE", lambda: parse_uid("a:b:c", native_driver="apple_mail"))

    def test_ut_uid_01_03_invalid_driver_is_usage_and_unknown_driver_is_driver_unknown(self) -> None:
        """UT-UID-01.03: bad driver syntax ⇒ E_USAGE; valid but not installed ⇒ E_DRIVER_UNKNOWN."""
        self.assertTrue(is_valid_driver("apple_mail"))
        self.assertIsNotNone(DRIVER_PATTERN.fullmatch("a" * 64))
        for driver in ("", "Apple_Mail", "apple-mail", "a" * 65, "apple mail"):
            with self.subTest(driver=driver):
                _assert_error(self, "E_USAGE", lambda: parse_uid(f"{driver}:1"))
                _assert_error(self, "E_USAGE", lambda: format_uid(driver, "1"))
        error = _assert_error(
            self,
            "E_DRIVER_UNKNOWN",
            lambda: parse_uid("graph:1", is_installed=lambda name: name != "graph"),
        )
        self.assertIn("graph", error.message)
        self.assertEqual(parse_uid("graph:1", is_installed=lambda name: True).driver, "graph")

    def test_ut_uid_01_04_invalid_native_id_is_usage(self) -> None:
        """UT-UID-01.04: ``/``, space, ``:``, >1024, leading dot, ``..`` or empty ⇒ E_USAGE."""
        for native in ("a/b", "a b", "a:b", "x" * 1025, ".a", "a..b", "", "."):
            with self.subTest(native=native):
                _assert_error(self, "E_USAGE", lambda: parse_uid(f"apple_mail:{native}"))

    def test_ut_uid_01_05_legacy_uid_uses_the_platform_native_driver(self) -> None:
        """UT-UID-01.05: unprefixed integer on macOS ⇒ apple_mail; uppercase hex on Windows ⇒ outlook."""
        with mock.patch.object(sys, "platform", "darwin"):
            parsed = parse_uid("83143")
        self.assertEqual((parsed.driver, parsed.native_id), ("apple_mail", "83143"))
        self.assertEqual(parsed.uid, "apple_mail:83143")
        with mock.patch.object(sys, "platform", "win32"):
            parsed = parse_uid("ABC123")
        self.assertEqual((parsed.driver, parsed.native_id), ("outlook", "ABC123"))
        self.assertEqual(parsed.uid, "outlook:ABC123")
        # The native driver can be given explicitly (tests and non-standard hosts).
        parsed = parse_uid("83143", native_driver="apple_mail")
        self.assertEqual(parsed.uid, "apple_mail:83143")

    def test_ut_uid_01_06_invalid_uid_is_validated_before_home_config_and_store(self) -> None:
        """UT-UID-01.06: no home creation, config read, store open, state or cache write."""
        with tempfile.TemporaryDirectory(prefix="mailquery-uid-") as tmp:
            fake_home = Path(tmp) / ".mailquery"
            stdout = io.StringIO()
            with (
                mock.patch.object(cli_mod, "ensure_app_home", side_effect=AssertionError),
                mock.patch.object(cli_mod, "load_config", side_effect=AssertionError),
                mock.patch.object(cli_mod, "get_backend", side_effect=AssertionError),
                mock.patch.dict(os.environ, {"HOME": tmp, "USERPROFILE": tmp}),
                redirect_stdout(stdout),
                redirect_stderr(io.StringIO()),
            ):
                code = cli_mod.main(["show", "bad uid"], home=fake_home)
            self.assertEqual(code, 2)
            self.assertFalse(fake_home.exists())
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["error"]["code"], "E_USAGE")
            _assert_error(
                self, "E_USAGE", lambda: parse_uid("apple_mail:.a", native_driver="apple_mail")
            )
            self.assertFalse(fake_home.exists())
            self.assertFalse((Path(tmp) / ".mailquery").exists())

    def test_ut_uid_01_07_stable_identifier_is_sha256_prefix(self) -> None:
        """UT-UID-01.07: 32 lowercase hex = first 32 chars of SHA-256(uid UTF-8), deterministic."""
        value = "apple_mail:83143"
        expected = hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]
        self.assertEqual(stable_identifier(value), expected)
        self.assertEqual(len(stable_identifier(value)), 32)
        self.assertIsNotNone(re.fullmatch(r"[0-9a-f]{32}", stable_identifier(value)))
        self.assertEqual(stable_identifier(value), stable_identifier(value))
        self.assertNotEqual(stable_identifier(value), stable_identifier("apple_mail:83144"))
        self.assertEqual(uid_mod.stable_identifier("outlook:ABC123"), stable_identifier("outlook:ABC123"))
        with self.assertRaises(MailqueryError):
            stable_identifier("")


# --------------------------------------------------------------------------- #
# UT-UID-02: prefixed uid in commands (M03, AC-05)
# --------------------------------------------------------------------------- #


def _run_cli(argv, *, home, mail_root=None, accounts_db=None, backend=None):
    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = cli_mod.main(
            list(argv),
            home=home,
            mail_root=mail_root,
            accounts_db=accounts_db,
            backend=backend,
        )
    text = stdout.getvalue()
    return code, (json.loads(text) if text else None), stderr.getvalue()


class CommandUidTests(unittest.TestCase):
    """UT-UID-02: commands emit prefixed uids and accept the legacy native uid."""

    def _fixture(self):
        from tests.fixtures.make_fixtures import build_store, write_config

        fx = build_store()
        self.addCleanup(fx.cleanup)
        write_config(fx.home)
        return fx

    def _legacy_state(self, fx):
        from tests.fixtures.make_fixtures import write_state

        write_state(
            fx.home,
            {
                "schema": 1,
                "updated_at": "",
                "last_run": None,
                "cursor": {
                    "last_date_received": int((fx.now - timedelta(hours=2)).timestamp()),
                    "last_uid": 1,
                    "lookback_seconds": 600,
                },
                "emitted_uids": [],
            },
        )

    def test_ut_uid_02_01_commands_emit_prefixed_uids_and_cursor(self) -> None:
        """UT-UID-02.01: search/new/show emit uid strings with the native driver prefix."""
        from tests.fixtures.make_fixtures import prefixed_uid

        fx = self._fixture()
        code, payload, _ = _run_cli(
            ["search"], home=fx.home, mail_root=fx.mail_root, accounts_db=fx.accounts_db
        )
        self.assertEqual(code, 0)
        self.assertTrue(payload["messages"])
        for message in payload["messages"]:
            self.assertIsInstance(message["uid"], str)
            self.assertTrue(message["uid"].startswith("apple_mail:"))
        self.assertIn(prefixed_uid(2714), [m["uid"] for m in payload["messages"]])

        code, payload, _ = _run_cli(
            ["show", "2714"], home=fx.home, mail_root=fx.mail_root, accounts_db=fx.accounts_db
        )
        self.assertEqual(code, 0)
        self.assertEqual(payload["message"]["uid"], prefixed_uid(2714))

        # First run: no previous cursor, current prefixed.
        code, payload, _ = _run_cli(
            ["new"], home=fx.home, mail_root=fx.mail_root, accounts_db=fx.accounts_db
        )
        self.assertEqual(code, 0)
        self.assertIsNone(payload["cursor"]["previous"])
        self.assertTrue(payload["cursor"]["current"]["last_uid"].startswith("apple_mail:"))
        for message in payload["messages"]:
            self.assertTrue(message["uid"].startswith("apple_mail:"))

        # A migrated schema-1 cursor is reported prefixed in previous/current.
        fx2 = self._fixture()
        self._legacy_state(fx2)
        code, payload, _ = _run_cli(
            ["new", "--peek"], home=fx2.home, mail_root=fx2.mail_root, accounts_db=fx2.accounts_db
        )
        self.assertEqual(code, 0)
        self.assertEqual(payload["cursor"]["previous"]["last_uid"], prefixed_uid(1))
        self.assertEqual(payload["cursor"]["current"]["last_uid"], prefixed_uid(1))

    def test_ut_uid_02_02_order_uses_native_order_key(self) -> None:
        """UT-UID-02.02: the total order uses the driver's native_order_key, not the uid text."""
        from mailquery import search

        class _Numeric:
            driver = "apple_mail"
            native_order = "numeric"

        class _Text:
            driver = "outlook"
            native_order = "text"

        rows = [
            {"date_received": 100, "native_order_key": "10", "uid": "apple_mail:2"},
            {"date_received": 100, "native_order_key": "2", "uid": "apple_mail:10"},
        ]
        self.assertEqual(search._native_order_key(_Numeric(), rows[0]), 10)
        self.assertEqual(search._native_order_key(_Text(), rows[0]), "10")
        self.assertEqual(
            [row["native_order_key"] for row in search._ordered(rows, _Numeric(), descending=True)],
            ["10", "2"],
        )
        self.assertEqual(
            [row["native_order_key"] for row in search._ordered(rows, _Text(), descending=True)],
            ["2", "10"],
        )

        # With the real fixture the numeric order is the 2.0.1 order.
        from tests.fixtures.make_fixtures import prefixed_uid

        fx = self._fixture()
        code, payload, _ = _run_cli(
            ["search", "--limit", "4"],
            home=fx.home,
            mail_root=fx.mail_root,
            accounts_db=fx.accounts_db,
        )
        self.assertEqual(code, 0)
        self.assertEqual(
            [message["uid"] for message in payload["messages"]],
            [prefixed_uid(83170), prefixed_uid(83160), prefixed_uid(83150), prefixed_uid(83143)],
        )

    def test_ut_uid_02_03_legacy_input_is_resolved_with_the_native_driver(self) -> None:
        """UT-UID-02.03: ``show 83143`` / ``show <EntryID>`` return the prefixed uid."""
        from tests.fixtures.make_fixtures import prefixed_uid

        fx = self._fixture()
        code, payload, _ = _run_cli(
            ["show", "83143"], home=fx.home, mail_root=fx.mail_root, accounts_db=fx.accounts_db
        )
        self.assertEqual(code, 0)
        self.assertEqual(payload["message"]["uid"], prefixed_uid(83143))

        from mailquery.backends import get_backend
        from tests.fakes import outlook as fake_outlook
        from tests.fixtures.make_fixtures import write_config

        fake = fake_outlook.FakeOutlook.default()
        with tempfile.TemporaryDirectory(prefix="mailquery-uid-ol-") as tmp:
            home = Path(tmp) / "home"
            write_config(home, '[scope."ana.perez@example.com"]\n')
            backend = get_backend(
                platform="win32",
                outlook_app=fake,
                registry=fake.registry,
                security_center=fake.security_center,
                tmp_root=home / "tmp",
            )
            self.addCleanup(backend.close)
            entry_id = fake.item("normal").entry_id
            code, payload, _ = _run_cli(["show", entry_id], home=home, backend=backend)
        self.assertEqual(code, 0)
        self.assertEqual(payload["message"]["uid"], prefixed_uid(entry_id, "outlook"))

    def test_ut_uid_02_04_malformed_and_unknown_uid_fail_before_home(self) -> None:
        """UT-UID-02.04: malformed ⇒ E_USAGE; unknown driver ⇒ E_DRIVER_UNKNOWN; no home."""
        with tempfile.TemporaryDirectory(prefix="mailquery-uid-") as tmp:
            missing_home = Path(tmp) / "home"
            for uid in ("apple_mail:a/b", "outlook:" + "A" * 1025, "apple_mail:.hidden"):
                with self.subTest(uid=uid[:30]):
                    code, payload, _ = _run_cli(["show", uid], home=missing_home)
                    self.assertEqual(code, 2)
                    self.assertEqual(payload["error"]["code"], "E_USAGE")
                    self.assertFalse(missing_home.exists())
            code, payload, _ = _run_cli(["show", "graph:1"], home=missing_home)
            self.assertEqual(code, 2)
            self.assertEqual(payload["error"]["code"], "E_DRIVER_UNKNOWN")
            self.assertFalse(missing_home.exists())

    def test_ut_uid_02_05_installed_driver_not_declared_is_out_of_scope(self) -> None:
        """UT-UID-02.05: an installed but undeclared driver ⇒ E_ACCOUNT_NOT_IN_SCOPE, not loaded."""
        from tests.fixtures.make_fixtures import DEFAULT_CONFIG, write_config

        with tempfile.TemporaryDirectory(prefix="mailquery-uid-") as tmp:
            home = Path(tmp) / "home"
            write_config(home, DEFAULT_CONFIG)
            with mock.patch.object(
                cli_mod, "get_backend", side_effect=AssertionError("driver loaded")
            ):
                code, payload, _ = _run_cli(
                    ["show", "outlook:ABC123"],
                    home=home,
                    mail_root=Path(tmp) / "Mail",  # force Apple Mail (native driver)
                )
            self.assertEqual(code, 2)
            self.assertEqual(payload["error"]["code"], "E_ACCOUNT_NOT_IN_SCOPE")
            self.assertIn("config.toml", payload["error"]["hint"])

    def test_ut_uid_02_06_read_only_commands_do_not_rewrite_a_legacy_state(self) -> None:
        """UT-UID-02.06: search/show/mailboxes/doctor leave a schema-1 state.json untouched."""
        from tests.fixtures.make_fixtures import write_config

        fx = self._fixture()
        write_config(fx.home)
        self._legacy_state(fx)
        path = fx.home / "state.json"
        before = path.read_bytes()
        for argv in (("search",), ("show", "2714"), ("mailboxes",), ("doctor", "--json")):
            with self.subTest(argv=argv):
                code, payload, stderr = _run_cli(
                    argv,
                    home=fx.home,
                    mail_root=fx.mail_root,
                    accounts_db=fx.accounts_db,
                )
                self.assertEqual(code, 0, stderr)
                self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":  # pragma: no cover - manual runs
    unittest.main()

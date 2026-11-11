"""UT-UID-01: prefixed uid format, parsing and stable path identifier (M01, AC-05/RF-40).

Pure module tests: ``mailquery.uid`` must validate before any home/config/store
work (PRD-v2.1 §6.1 RF-40, §11.3 row 2, §14 AC-05).
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


if __name__ == "__main__":
    unittest.main()

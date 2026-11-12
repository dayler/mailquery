"""Tests for ``mailquery.cli``: argparse contract, JSON output and exit codes.

The command functions of ``search.py`` and the store/accounts/state modules are
replaced by fakes so the CLI contract can be verified while those modules are
still being implemented in parallel. ``doctor`` is exercised end-to-end because
its contract is "never raises, always exit 0".
"""

from __future__ import annotations

import io
import json
import os
import platform
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from mailquery import cli as cli_mod
from mailquery import errors
from mailquery.backends import apple_mail as apple_mail_mod
from mailquery.backends.apple_mail import AppleMailBackend
from mailquery.backends.registry import BackendRegistry, package_version
from mailquery.errors import MailqueryError
from mailquery.search import Filters

from tests.fakes.plugin import (
    DRIVER as PLUGIN_DRIVER,
    VERSION as PLUGIN_VERSION,
    FakeEntryPoint,
    FakePluginBackend,
    internal_entry_points,
    plugin_class,
)
from tests.fixtures.make_fixtures import (
    DEFAULT_CONFIG,
    ICLOUD_LABEL,
    PREFIXED_CONFIG,
    build_store,
    prefixed_uid,
    write_config,
    write_state,
)

_DEFAULT = object()
FORBIDDEN_FLAGS = (
    "--format",
    "--config",
    "--home",
    "--quiet",
    "--verbose",
    "--no-color",
    "--timeout",
    "--backend",
)


class _FakeBackend:
    """Minimal stand-in for a ``MailBackend``: only what ``cli`` itself touches."""

    driver = "apple_mail"
    plugin_api = 1
    capabilities = {
        "network": False,
        "readonly": "structural",
        "body_local": True,
        "attachments": "local",
        "native_order": "numeric",
    }

    def __init__(self) -> None:
        self.closed = False

    @staticmethod
    def parse_native_id(native_id: str) -> int:
        """Apple Mail native ids are integers (pure, offline)."""
        if not native_id.lstrip("-").isdigit():
            raise MailqueryError(
                "E_USAGE", f"invalid uid part {native_id!r}: expected an integer"
            )
        return int(native_id)

    def describe(self) -> dict:
        return {}

    def close(self) -> None:
        self.closed = True


class _FakeLock:
    def __init__(self, home: Path) -> None:
        self.home = home
        self.acquired = False
        self.released = False

    def acquire(self) -> None:
        self.acquired = True

    def release(self) -> None:
        self.released = True

    def __enter__(self) -> "_FakeLock":
        self.acquire()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.release()


class _BusyLock(_FakeLock):
    def acquire(self) -> None:
        raise MailqueryError(
            "E_LOCKED",
            "another mailquery run holds the lock",
            "retry after the other run finishes (exit 5 is retryable)",
        )


class _CliTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = build_store()
        self.addCleanup(self.fx.cleanup)

    def run_cli(
        self,
        argv,
        *,
        home=_DEFAULT,
        mail_root=_DEFAULT,
        accounts_db=_DEFAULT,
    ):
        if home is _DEFAULT:
            home = self.fx.home
        if mail_root is _DEFAULT:
            mail_root = self.fx.mail_root
        if accounts_db is _DEFAULT:
            accounts_db = self.fx.accounts_db
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli_mod.main(
                argv,
                home=home,
                mail_root=mail_root,
                accounts_db=accounts_db,
            )
        return code, stdout.getvalue(), stderr.getvalue()

    def json_object(self, stdout: str) -> dict:
        self.assertTrue(stdout.endswith("}\n"), f"expected one JSON object + LF: {stdout!r}")
        parsed = json.loads(stdout)
        self.assertEqual(
            stdout,
            json.dumps(parsed, ensure_ascii=False, indent=2) + "\n",
            "JSON object must be formatted (2-space indent)",
        )
        return parsed

    def assert_error(
        self,
        code: int,
        command_result,
        expected_error: str,
        expected_command: str | None = None,
    ) -> dict:
        exit_code, stdout, stderr = command_result
        self.assertEqual(exit_code, code)
        payload = self.json_object(stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], expected_error)
        self.assertNotIn("generated_at", payload)
        if expected_command is not None:
            self.assertEqual(payload["command"], expected_command)
        self.assertIn(expected_error, stderr)
        return payload

    def success_payload(self, payload: dict | None = None) -> dict:
        if payload is None:
            payload = {
                "messages": [],
                "truncated": False,
                "hint": None,
                "scan": {
                    "mode": "metadata",
                    "candidates": 0,
                    "messages_read": 0,
                    "duration_ms": 1,
                },
                "warnings": [],
            }
        return payload


# --------------------------------------------------------------------------- #
# Help and usage errors
# --------------------------------------------------------------------------- #


class HelpContractTests(_CliTestCase):
    HELP_MAX_WIDTH = 100

    def assert_human_readable(self, stdout: str) -> None:
        self.assertFalse(stdout.lstrip().startswith("{"), "help must be plain text")
        self.assertNotIn("\x1b[", stdout, "help must not use ANSI colors")
        for line in stdout.splitlines():
            self.assertLessEqual(
                len(line), self.HELP_MAX_WIDTH, f"help line is too long: {line!r}"
            )

    def test_ut_cli_06_01_global_help_is_formatted_text_and_exits_zero(self) -> None:
        """UT-CLI-06.01: root --help has the PRD 12.7 sections, both clients, <= 100 columns, no ANSI."""
        unused_home = self.fx.root / "unused-home"
        code, stdout, stderr = self.run_cli(["--help"], home=unused_home)
        self.assertEqual(code, 0)
        self.assertIn("usage: mailquery", stdout)
        self.assertIn("Apple Mail", stdout)
        self.assertIn("Outlook", stdout)
        for section in (
            "Commands:",
            "Global options:",
            "Examples:",
            "Configuration:",
            "Output:",
            "Exit codes:",
        ):
            self.assertIn(section, stdout)
        for command in ("doctor", "mailboxes", "search", "new", "show"):
            self.assertIn(command, stdout)
        self.assertIn("--log-level LEVEL", stdout)
        self.assertIn("mailquery search --since 1w", stdout)
        self.assertIn("mailquery show 83143", stdout)
        self.assert_human_readable(stdout)
        self.assertEqual(stderr, "")
        self.assertFalse(unused_home.exists(), "--help must not touch the filesystem")

    def test_ut_cli_06_02_subcommand_help_is_formatted_for_every_command(self) -> None:
        """UT-CLI-06.02: <command> --help for the 5 commands has Options, Examples and Notes."""
        expected_flags = {
            "doctor": ("--json",),
            "mailboxes": (),
            "search": (
                "--subject",
                "--text",
                "--from",
                "--to",
                "--cc",
                "--since",
                "--until",
                "--unread",
                "--flagged",
                "--has-attachments",
                "--include-mailbox",
                "--limit",
            ),
            "new": ("--peek", "--limit"),
            "show": ("uid",),
        }
        for command, flags in expected_flags.items():
            with self.subTest(command=command):
                code, stdout, stderr = self.run_cli([command, "--help"])
                self.assertEqual(code, 0)
                self.assertIn(f"usage: mailquery {command}", stdout)
                self.assertIn("Options:", stdout)
                self.assertIn("Examples:", stdout)
                self.assertIn("Notes:", stdout)
                for flag in flags:
                    self.assertIn(flag, stdout)
                self.assert_human_readable(stdout)
                self.assertEqual(stderr, "")

    def help_text(self, command: str | None) -> str:
        argv = ["--help"] if command is None else [command, "--help"]
        code, stdout, stderr = self.run_cli(argv)
        self.assertEqual((code, stderr), (0, ""))
        return stdout

    def test_ut_cli_06_03_root_help_lists_the_exit_codes_including_6(self) -> None:
        """UT-CLI-06.03: the root help lists exit codes 0, 2, 3, 4, 5 and 6."""
        stdout = self.help_text(None)
        exit_codes = stdout[stdout.index("Exit codes:") :]
        for fragment in (
            "0 ok",
            "2 usage or config error",
            "3 environment error",
            "4 rejected query",
            "5 busy or transient error",
            "6 mail client not running",
        ):
            self.assertIn(fragment, exit_codes)
        self.assertIn("this help,", stdout)
        self.assertIn("UTF-8", stdout)

    def test_ut_cli_06_04_new_help_describes_the_first_run(self) -> None:
        """UT-CLI-06.04: the help of ``new`` describes the first run of PRD 12.3 (no "baseline")."""
        stdout = self.help_text("new")
        flat = " ".join(stdout.split())
        for fragment in (
            "first run",
            "W_FIRST_RUN",
            "[new].lookback",
            "newest message",
            "oldest first",
            "--limit",
            "--peek",
        ):
            self.assertIn(fragment, flat)
        for command in (None, "doctor", "mailboxes", "search", "new", "show"):
            with self.subTest(command=command):
                self.assertNotIn("baseline", self.help_text(command).lower())

    def test_ut_cli_06_05_search_help_describes_terms_and_text_narrowing(self) -> None:
        """UT-CLI-06.05: the help of ``search`` describes PRD 12.2 terms and the RF-17 narrowing."""
        stdout = self.help_text("search")
        flat = " ".join(stdout.split())
        for fragment in (
            "--subject: words separated by spaces are AND",
            "--text, --from, --to and --cc: the whole value is one pattern",
            "Repeating a flag is AND",
            "--text needs a narrowing filter",
            "E_UNBOUNDED_SCAN",
            "E_SCAN_TOO_LARGE",
            "does not narrow",
            "--to and --cc narrow on macOS but not on Windows",
        ):
            self.assertIn(fragment, flat)
        self.assertNotIn("split on spaces into AND terms", flat)

    def test_ut_cli_06_06_every_help_example_parses(self) -> None:
        """UT-CLI-06.06: each example of the 6 helps passes ``parse_args``."""
        import re
        import shlex

        parser = cli_mod.build_parser()
        seen = 0
        for command in (None, "doctor", "mailboxes", "search", "new", "show"):
            stdout = self.help_text(command)
            in_examples = False
            for line in stdout.splitlines():
                if line.rstrip() == "Examples:":
                    in_examples = True
                    continue
                if not in_examples:
                    continue
                if not line.strip():
                    in_examples = False
                    continue
                example = re.split(r"\s{2,}", line.strip())[0]
                with self.subTest(command=command, example=example):
                    argv = shlex.split(example)
                    self.assertEqual(argv[0], "mailquery")
                    parser.parse_args(argv[1:])
                    seen += 1
        self.assertGreaterEqual(seen, 15)

    def test_subcommand_help_has_specific_examples(self) -> None:
        examples = {
            "doctor": "mailquery doctor --json",
            "mailboxes": "mailquery mailboxes",
            "search": 'mailquery search --text "*invoice*" --since 1mo',
            "new": "mailquery new --peek",
            "show": "mailquery show 83143",
        }
        for command, example in examples.items():
            with self.subTest(command=command):
                _, stdout, _ = self.run_cli([command, "--help"])
                self.assertIn(example, stdout)

    def test_help_has_no_undeclared_flags(self) -> None:
        _, stdout, _ = self.run_cli(["--help"])
        for flag in FORBIDDEN_FLAGS:
            self.assertNotIn(flag, stdout)

    def test_help_survives_broken_config(self) -> None:
        write_config(self.fx.home, "this is = = not toml\n")
        code, stdout, stderr = self.run_cli(["--help"])
        self.assertEqual(code, 0)
        self.assertIn("usage: mailquery", stdout)
        self.assertEqual(stderr, "")

    def test_unknown_flag_returns_usage_json(self) -> None:
        payload = self.assert_error(
            2,
            self.run_cli(["search", "--format", "json"]),
            "E_USAGE",
            "search",
        )
        self.assertIn("--format", payload["error"]["message"])
        self.assertTrue(payload["error"]["hint"])

    def test_missing_command_returns_usage_json(self) -> None:
        self.assert_error(2, self.run_cli([]), "E_USAGE")

    def test_ut_cli_04_01_all_forbidden_flags_are_rejected(self) -> None:
        """UT-CLI-04.01: each nonexistent option is E_USAGE, exit 2."""
        for flag in FORBIDDEN_FLAGS:
            with self.subTest(flag=flag):
                exit_code, stdout, stderr = self.run_cli(["search", flag, "value"])
                self.assertEqual(exit_code, 2)
                payload = self.json_object(stdout)
                self.assertEqual(payload["error"]["code"], "E_USAGE")
                self.assertIn("E_USAGE", stderr)

    def test_ut_cli_07_01_show_requires_an_integer_uid(self) -> None:
        """UT-CLI-07.01: ``show abc`` is E_USAGE "invalid uid ...: expected an integer"."""
        self.assert_error(2, self.run_cli(["show"]), "E_USAGE")
        payload = self.assert_error(
            2, self.run_cli(["show", "abc"]), "E_USAGE", "show"
        )
        self.assertIn("invalid uid", payload["error"]["message"])
        self.assertIn("expected an integer", payload["error"]["message"])
        self.assertIn("'abc'", payload["error"]["message"])

    def test_ut_cli_07_02_invalid_uid_is_rejected_before_home_config_and_store(self) -> None:
        """UT-CLI-07.02: a bad uid creates no home, reads no config and opens no store."""
        with tempfile.TemporaryDirectory(prefix="mailquery-uid-") as tmp:
            missing_home = Path(tmp) / "home"
            missing_root = Path(tmp) / "Mail"
            self.assert_error(
                2,
                self.run_cli(
                    ["show", "abc"], home=missing_home, mail_root=missing_root
                ),
                "E_USAGE",
                "show",
            )
            self.assertFalse(missing_home.exists())

            # An existing home with a broken config: still E_USAGE, nothing created.
            broken_home = Path(tmp) / "broken-home"
            write_config(broken_home, "[search]\nnot_a_key = 1\n")
            self.assert_error(
                2,
                self.run_cli(["show", "abc"], home=broken_home, mail_root=missing_root),
                "E_USAGE",
                "show",
            )
            self.assertEqual(
                sorted(path.name for path in broken_home.iterdir()), ["config.toml"]
            )

    def test_ut_cli_07_03_uid_zero_is_an_integer_that_is_not_found(self) -> None:
        """UT-CLI-07.03: ``show 0`` is an integer: E_USAGE "was not found"."""
        write_config(self.fx.home, DEFAULT_CONFIG)
        payload = self.assert_error(2, self.run_cli(["show", "0"]), "E_USAGE", "show")
        self.assertIn("was not found", payload["error"]["message"])
        self.assertNotIn("invalid uid", payload["error"]["message"])

    def test_invalid_log_level_returns_usage_json(self) -> None:
        payload = self.assert_error(
            2,
            self.run_cli(["--log-level", "loud", "search"]),
            "E_USAGE",
        )
        self.assertIn("invalid choice", payload["error"]["message"])


# --------------------------------------------------------------------------- #
# Limit validation (fails before touching the store)
# --------------------------------------------------------------------------- #


class LimitValidationTests(_CliTestCase):
    def test_search_limit_out_of_range(self) -> None:
        for value in ("0", "201", "-3"):
            with self.subTest(value=value):
                payload = self.assert_error(
                    2,
                    self.run_cli(["search", "--limit", value]),
                    "E_USAGE",
                    "search",
                )
                self.assertIn("--limit", payload["error"]["message"])
                self.assertIn("1..200", payload["error"]["hint"])

    def test_new_limit_out_of_range(self) -> None:
        payload = self.assert_error(
            2,
            self.run_cli(["new", "--limit", "501"]),
            "E_USAGE",
            "new",
        )
        self.assertIn("1..500", payload["error"]["hint"])

    def test_empty_include_mailbox_is_usage_error(self) -> None:
        self.assert_error(
            2,
            self.run_cli(["search", "--include-mailbox", ","]),
            "E_USAGE",
            "search",
        )


# --------------------------------------------------------------------------- #
# Config errors
# --------------------------------------------------------------------------- #


class ConfigErrorTests(_CliTestCase):
    def test_broken_config_returns_json_config_error(self) -> None:
        write_config(self.fx.home, "verbose = true\n")
        payload = self.assert_error(
            2,
            self.run_cli(["mailboxes"]),
            "E_CONFIG_INVALID",
            "mailboxes",
        )
        self.assertIn("verbose", payload["error"]["message"])
        self.assertTrue(payload["error"]["hint"])

    def test_command_not_executed_with_broken_config(self) -> None:
        write_config(self.fx.home, "[logging]\nlevel = \"loud\"\n")
        with mock.patch.object(cli_mod, "_execute") as execute:
            exit_code, stdout, _ = self.run_cli(["search"])
        self.assertEqual(exit_code, 2)
        execute.assert_not_called()
        self.assertEqual(self.json_object(stdout)["error"]["code"], "E_CONFIG_INVALID")


# --------------------------------------------------------------------------- #
# Success rendering
# --------------------------------------------------------------------------- #


class SuccessContractTests(_CliTestCase):
    def test_search_success_json(self) -> None:
        payload = {
            "count": 1,
            "truncated": False,
            "hint": None,
            "messages": [{"uid": 83143}],
            "scan": {"mode": "metadata", "candidates": 1, "messages_read": 1, "duration_ms": 2},
            "warnings": [],
        }
        with mock.patch.object(cli_mod, "_execute", return_value=payload):
            exit_code, stdout, stderr = self.run_cli(["search", "--subject", "invoice"])
        self.assertEqual(exit_code, 0)
        rendered = self.json_object(stdout)
        self.assertTrue(rendered["ok"])
        self.assertEqual(rendered["command"], "search")
        self.assertIsInstance(rendered["generated_at"], str)
        self.assertEqual(rendered["count"], 1)
        self.assertEqual(rendered["messages"], [{"uid": 83143}])
        self.assertEqual(rendered["warnings"], [])
        self.assertIsNone(rendered["hint"])
        self.assertEqual(stderr, "")

    def test_count_is_derived_when_missing(self) -> None:
        payload = {
            "messages": [{"uid": 1}, {"uid": 2}],
            "truncated": True,
            "hint": "narrow the query with --since",
            "warnings": [],
        }
        with mock.patch.object(cli_mod, "_execute", return_value=payload):
            exit_code, stdout, _ = self.run_cli(["search"])
        self.assertEqual(exit_code, 0)
        rendered = self.json_object(stdout)
        self.assertEqual(rendered["count"], 2)
        self.assertEqual(rendered["hint"], "narrow the query with --since")
        self.assertTrue(rendered["truncated"])

    def test_reserved_keys_from_payload_cannot_override_the_envelope(self) -> None:
        payload = {
            "ok": False,
            "command": "evil",
            "generated_at": "1999-01-01T00:00:00+00:00",
            "messages": [],
            "warnings": [],
        }
        with mock.patch.object(cli_mod, "_execute", return_value=payload):
            exit_code, stdout, _ = self.run_cli(["search"])
        self.assertEqual(exit_code, 0)
        rendered = self.json_object(stdout)
        self.assertTrue(rendered["ok"])
        self.assertEqual(rendered["command"], "search")
        self.assertNotEqual(rendered["generated_at"], "1999-01-01T00:00:00+00:00")

    def test_output_is_one_compact_json_object(self) -> None:
        payload = self.success_payload()
        with mock.patch.object(cli_mod, "_execute", return_value=payload):
            exit_code, stdout, stderr = self.run_cli(["mailboxes"])
        self.assertEqual(exit_code, 0)
        parsed = json.loads(stdout)
        self.assertEqual(
            stdout,
            json.dumps(parsed, ensure_ascii=False, indent=2) + "\n",
        )
        self.assertGreater(stdout.count("\n"), 1)
        self.assertFalse(stdout.endswith("\n\n"))
        self.assertEqual(stderr, "")

    def test_warnings_are_preserved(self) -> None:
        payload = {
            "accounts": [],
            "mailboxes": [],
            "warnings": ["W_NO_ACCOUNTS: no accounts declared in config.toml"],
        }
        with mock.patch.object(cli_mod, "_execute", return_value=payload):
            exit_code, stdout, _ = self.run_cli(["mailboxes"])
        self.assertEqual(exit_code, 0)
        rendered = self.json_object(stdout)
        self.assertEqual(rendered["warnings"], ["W_NO_ACCOUNTS: no accounts declared in config.toml"])

    def test_ut_log_03_04_debug_log_goes_to_file_not_stdout_with_end_event(self) -> None:
        """UT-LOG-03.04: event=end with exit_code and counts; the log never reaches stdout."""
        payload = self.success_payload()
        with mock.patch.object(cli_mod, "_execute", return_value=payload):
            exit_code, stdout, stderr = self.run_cli(["--log-level", "debug", "search"])
        self.assertEqual(exit_code, 0)
        self.json_object(stdout)
        self.assertNotIn("event=start", stdout)
        self.assertNotIn("event=start", stderr)
        log_path = self.fx.home / "logs" / "mailquery.log"
        self.assertTrue(log_path.is_file())
        log_text = log_path.read_text(encoding="utf-8")
        self.assertIn("event=start command=search", log_text)
        self.assertIn("event=end command=search exit_code=0 count=0 truncated=False", log_text)


# --------------------------------------------------------------------------- #
# Error rendering and exit codes
# --------------------------------------------------------------------------- #


class ErrorContractTests(_CliTestCase):
    def test_ut_cli_09_01_error_codes_map_to_documented_exit_codes(self) -> None:
        """UT-CLI-09.01: each of the 32 E_* codes of PRD-v2.1 §11.7 maps to its exit code."""
        cases = (
            ("E_USAGE", 2),
            ("E_CONFIG_INVALID", 2),
            ("E_CONFIG_ACCOUNT_UNKNOWN", 2),
            ("E_ACCOUNT_AMBIGUOUS", 2),
            ("E_ACCOUNT_LABELS_UNAVAILABLE", 2),
            ("E_ACCOUNT_NOT_IN_SCOPE", 2),
            ("E_MAILBOX_NOT_FOUND", 2),
            ("E_BAD_TIME", 2),
            ("E_BAD_FILTER", 2),
            ("E_STORE_NOT_FOUND", 3),
            ("E_SCHEMA_UNSUPPORTED", 3),
            ("E_PERMISSION", 3),
            ("E_STATE_CORRUPT", 3),
            ("E_CLIENT_UNSUPPORTED", 3),
            ("E_DEPENDENCY_MISSING", 3),
            ("E_CLIENT_TIMEOUT", 3),
            ("E_UNBOUNDED_SCAN", 4),
            ("E_SCAN_TOO_LARGE", 4),
            ("E_LOCKED", 5),
            ("E_DB_BUSY", 5),
            ("E_CLIENT_BUSY", 5),
            ("E_OUTLOOK_NOT_RUNNING", 6),
            ("E_INTERNAL", 1),
            # PRD-v2.1 §11.7 new codes (M01).
            ("E_DRIVER_UNKNOWN", 2),
            ("E_ATTACHMENTS_DISABLED", 2),
            ("E_PLUGIN_INCOMPATIBLE", 3),
            ("E_PLUGIN_FAILED", 3),
            ("E_ATTACHMENT_UNAVAILABLE", 3),
            ("E_ATTACHMENT_UNREADABLE", 3),
            ("E_ATTACHMENT_BLOCKED", 4),
            ("E_ATTACHMENT_TOO_LARGE", 4),
            ("E_IO", 3),
        )
        self.assertEqual(len(cases), 32)
        # The full catalogue matches the table exactly, not only the sampled codes.
        catalogue = {
            code: exit_code
            for exit_code, codes in errors._EXIT_ERRORS.items()
            for code in codes
        }
        self.assertEqual(catalogue, dict(cases))
        for code, expected_exit in cases:
            with self.subTest(code=code):
                error = MailqueryError(code, f"failure {code}", "do something useful")
                with mock.patch.object(cli_mod, "_execute", side_effect=error):
                    exit_code, stdout, stderr = self.run_cli(["search"])
                self.assertEqual(exit_code, expected_exit)
                payload = self.json_object(stdout)
                self.assertFalse(payload["ok"])
                self.assertEqual(payload["command"], "search")
                self.assertEqual(payload["error"]["code"], code)
                self.assertEqual(payload["error"]["message"], f"failure {code}")
                self.assertEqual(payload["error"]["hint"], "do something useful")
                self.assertIn(code, stderr)
                self.assertTrue(stdout.endswith("}\n"))

    def test_unexpected_exception_becomes_internal_error_with_traceback_in_log(self) -> None:
        with mock.patch.object(cli_mod, "_execute", side_effect=RuntimeError("boom")):
            exit_code, stdout, stderr = self.run_cli(["search"])
        self.assertEqual(exit_code, 1)
        payload = self.json_object(stdout)
        self.assertEqual(payload["error"]["code"], "E_INTERNAL")
        self.assertIn("RuntimeError", payload["error"]["message"])
        self.assertTrue(payload["error"]["hint"])
        self.assertIn("E_INTERNAL", stderr)
        log_text = (self.fx.home / "logs" / "mailquery.log").read_text(encoding="utf-8")
        self.assertIn("event=internal_error", log_text)
        self.assertIn("Traceback", log_text)

    def test_store_is_closed_when_the_command_fails(self) -> None:
        backend = _FakeBackend()
        with (
            mock.patch.object(cli_mod, "RunLock", _FakeLock),
            mock.patch.object(cli_mod, "get_backend", return_value=backend),
            mock.patch.object(
                cli_mod,
                "run_search",
                side_effect=MailqueryError("E_BAD_FILTER", "bad filter", "fix it"),
            ),
        ):
            exit_code, stdout, _ = self.run_cli(["search"])
        self.assertEqual(exit_code, 2)
        self.assertEqual(self.json_object(stdout)["error"]["code"], "E_BAD_FILTER")
        self.assertTrue(backend.closed)

    def test_lock_busy_maps_to_exit_5(self) -> None:
        with mock.patch.object(cli_mod, "RunLock", _BusyLock):
            exit_code, stdout, stderr = self.run_cli(["search"])
        self.assertEqual(exit_code, 5)
        self.assertEqual(self.json_object(stdout)["error"]["code"], "E_LOCKED")
        self.assertIn("E_LOCKED", stderr)

    def test_lock_busy_against_a_real_flock_exits_5(self) -> None:
        from mailquery.state import RunLock as RealRunLock

        holder = RealRunLock(self.fx.home)
        holder.acquire()
        self.addCleanup(holder.release)
        exit_code, stdout, _ = self.run_cli(["search"])
        self.assertEqual(exit_code, 5)
        self.assertEqual(self.json_object(stdout)["error"]["code"], "E_LOCKED")


# --------------------------------------------------------------------------- #
# Dispatch
# --------------------------------------------------------------------------- #


class DispatchTests(_CliTestCase):
    def test_get_backend_receives_test_paths_and_home_tmp(self) -> None:
        backend = _FakeBackend()
        with (
            mock.patch.object(cli_mod, "RunLock", _FakeLock),
            mock.patch.object(cli_mod, "get_backend", return_value=backend) as backend_mock,
            mock.patch.object(
                cli_mod,
                "run_mailboxes",
                return_value={"accounts": [], "mailboxes": [], "warnings": []},
            ),
        ):
            exit_code, stdout, _ = self.run_cli(["mailboxes"])
        self.assertEqual(exit_code, 0)
        backend_mock.assert_called_once_with(
            platform="darwin",
            mail_root=self.fx.mail_root,
            accounts_db=self.fx.accounts_db,
            tmp_root=self.fx.home / "tmp",
        )
        self.assertTrue(backend.closed)
        self.assertTrue(self.json_object(stdout)["ok"])

    def test_search_dispatch_builds_filters(self) -> None:
        backend = _FakeBackend()
        config = cli_mod.load_config(self.fx.home)
        with (
            mock.patch.object(cli_mod, "RunLock", _FakeLock),
            mock.patch.object(cli_mod, "get_backend", return_value=backend),
            mock.patch.object(
                cli_mod,
                "run_search",
                return_value={"messages": [], "truncated": False, "hint": None, "warnings": []},
            ) as run_mock,
        ):
            exit_code, stdout, _ = self.run_cli(
                [
                    "search",
                    "--subject",
                    "a",
                    "--subject",
                    "b",
                    "--text",
                    "hello world",
                    "--from",
                    "sender@example.com",
                    "--to",
                    "me@example.com",
                    "--cc",
                    "cc@example.com",
                    "--unread",
                    "--flagged",
                    "--has-attachments",
                    "--include-mailbox",
                    "Facturas,Archivo",
                    "--include-mailbox",
                    "INBOX",
                    "--limit",
                    "5",
                ]
            )
        self.assertEqual(exit_code, 0)
        rendered = self.json_object(stdout)
        self.assertEqual(rendered["count"], 0)
        run_mock.assert_called_once()
        _, call_config, filters = run_mock.call_args.args
        self.assertEqual(call_config.home, config.home)
        self.assertIsInstance(filters, Filters)
        self.assertEqual(filters.subject, ("a", "b"))
        self.assertEqual(filters.text, ("hello world",))
        self.assertEqual(filters.from_, ("sender@example.com",))
        self.assertEqual(filters.to, ("me@example.com",))
        self.assertEqual(filters.cc, ("cc@example.com",))
        self.assertTrue(filters.unread)
        self.assertTrue(filters.flagged)
        self.assertTrue(filters.has_attachments)
        self.assertEqual(filters.include_mailboxes, ("Facturas", "Archivo", "INBOX"))
        self.assertEqual(filters.limit, 5)
        self.assertIsNone(filters.since)
        self.assertIsNone(filters.until)

    def test_show_dispatch(self) -> None:
        write_config(self.fx.home, DEFAULT_CONFIG)
        backend = _FakeBackend()
        with (
            mock.patch.object(cli_mod, "RunLock", _FakeLock),
            mock.patch.object(cli_mod, "get_backend", return_value=backend),
            mock.patch.object(
                cli_mod,
                "run_show",
                return_value={
                    "message": {"uid": prefixed_uid(83143)},
                    "warnings": [],
                },
            ) as run_mock,
        ):
            exit_code, stdout, _ = self.run_cli(["show", "83143"])
        self.assertEqual(exit_code, 0)
        run_mock.assert_called_once()
        # run_show(backend, config, uid): B-01 gives it the config.
        _, call_config, call_uid = run_mock.call_args.args
        self.assertEqual(call_config.home, self.fx.home)
        self.assertEqual(call_uid, 83143)
        self.assertEqual(
            self.json_object(stdout)["message"], {"uid": prefixed_uid(83143)}
        )

    def test_new_dispatch_peek_and_limit(self) -> None:
        backend = _FakeBackend()
        state_store = object()
        payload = {
            "messages": [],
            "truncated": False,
            "hint": None,
            "cursor": {"previous": None, "current": None},
            "warnings": [],
        }
        with (
            mock.patch.object(cli_mod, "RunLock", _FakeLock),
            mock.patch.object(cli_mod, "get_backend", return_value=backend),
            mock.patch.object(cli_mod, "StateStore", return_value=state_store) as state_mock,
            mock.patch.object(cli_mod, "run_new", return_value=payload) as run_mock,
        ):
            exit_code, stdout, _ = self.run_cli(["new", "--peek", "--limit", "7"])
        self.assertEqual(exit_code, 0)
        state_mock.assert_called_once()
        store_args, _store_kwargs = state_mock.call_args
        self.assertEqual(store_args[0], self.fx.home)
        self.assertTrue(callable(store_args[1]))
        self.assertEqual(run_mock.call_args.args[2], state_store)
        self.assertEqual(run_mock.call_args.kwargs, {"peek": True, "limit": 7})
        rendered = self.json_object(stdout)
        self.assertEqual(rendered["cursor"], {"previous": None, "current": None})
        self.assertEqual(rendered["count"], 0)


class _InjectedBackend(_FakeBackend):
    """Backend instance passed to ``main(backend=...)`` (the Outlook fake later)."""

    driver = "injected"

    def __init__(self) -> None:
        super().__init__()
        self.parsed: list = []

    def parse_native_id(self, native_id: str) -> str:
        self.parsed.append(native_id)
        if not str(native_id).isalnum():
            raise MailqueryError("E_USAGE", f"invalid uid {native_id!r}", "use a hex uid")
        return str(native_id).upper()

    def doctor_checks(self) -> list[dict]:
        return [{"name": "fake_check", "ok": True, "detail": "from the backend"}]


class BackendInjectionTests(_CliTestCase):
    """``main(..., backend=...)``: the CLI obtains, uses and closes the backend (plan 4.2)."""

    def run_injected(self, argv, backend, **kwargs):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli_mod.main(argv, home=self.fx.home, backend=backend, **kwargs)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_injected_backend_is_used_logged_and_closed(self) -> None:
        backend = _InjectedBackend()
        with (
            mock.patch.object(cli_mod, "get_backend") as get_mock,
            mock.patch.object(
                cli_mod,
                "run_mailboxes",
                return_value={"accounts": [], "mailboxes": [], "warnings": []},
            ) as run_mock,
        ):
            exit_code, stdout, _ = self.run_injected(["mailboxes"], backend)
        self.assertEqual(exit_code, 0)
        get_mock.assert_not_called()
        self.assertIs(run_mock.call_args.args[0], backend)
        self.assertTrue(backend.closed)
        log_text = (self.fx.home / "logs" / "mailquery.log").read_text(encoding="utf-8")
        self.assertIn("backend=injected", log_text)

    def test_without_injection_the_platform_backend_is_requested(self) -> None:
        backend = _FakeBackend()
        with (
            mock.patch.object(cli_mod, "get_backend", return_value=backend) as get_mock,
            mock.patch.object(
                cli_mod,
                "run_mailboxes",
                return_value={"accounts": [], "mailboxes": [], "warnings": []},
            ),
        ):
            exit_code, _, _ = self.run_cli(
                ["mailboxes"], mail_root=None, accounts_db=None
            )
        self.assertEqual(exit_code, 0)
        get_mock.assert_called_once_with(
            platform=None,
            mail_root=None,
            accounts_db=None,
            tmp_root=self.fx.home / "tmp",
        )
        self.assertTrue(backend.closed)

    def test_injected_backend_is_closed_when_the_command_fails(self) -> None:
        backend = _InjectedBackend()
        with mock.patch.object(
            cli_mod,
            "run_search",
            side_effect=MailqueryError("E_BAD_FILTER", "bad filter", "fix it"),
        ):
            exit_code, stdout, _ = self.run_injected(["search"], backend)
        self.assertEqual(exit_code, 2)
        self.assertEqual(self.json_object(stdout)["error"]["code"], "E_BAD_FILTER")
        self.assertTrue(backend.closed)

    def test_show_uid_is_validated_by_the_backend_before_the_home_exists(self) -> None:
        backend = _InjectedBackend()
        with tempfile.TemporaryDirectory() as tmp:
            missing_home = Path(tmp) / "no-home"
            stdout = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(io.StringIO()):
                code = cli_mod.main(
                    ["show", "not-hex"], home=missing_home, backend=backend
                )
            self.assertEqual(code, 2)
            self.assertEqual(self.json_object(stdout.getvalue())["error"]["code"], "E_USAGE")
            self.assertEqual(backend.parsed, ["not-hex"])
            self.assertFalse(missing_home.exists())
            self.assertFalse(backend.closed)  # never obtained, never opened

    def test_show_passes_the_backend_uid_to_run_show(self) -> None:
        write_config(self.fx.home, DEFAULT_CONFIG)
        backend = _InjectedBackend()
        with mock.patch.object(
            cli_mod, "run_show", return_value={"message": {}, "warnings": []}
        ) as run_mock:
            exit_code, _, _ = self.run_injected(["show", "ab12"], backend)
        self.assertEqual(exit_code, 0)
        self.assertEqual(run_mock.call_args.args[2], "AB12")

    def test_doctor_is_common_checks_plus_the_backend_checks(self) -> None:
        backend = _InjectedBackend()
        exit_code, stdout, _ = self.run_injected(["doctor", "--json"], backend)
        self.assertEqual(exit_code, 0)
        names = [check["name"] for check in self.json_object(stdout)["checks"]]
        self.assertEqual(
            names, ["python", "home", "driver", "fake_check", "config", "state", "lock"]
        )
        self.assertTrue(backend.closed)


# --------------------------------------------------------------------------- #
# Logging setup / precedence
# --------------------------------------------------------------------------- #


class LoggingConfigTests(_CliTestCase):
    def test_ut_cli_05_01_log_level_flag_overrides_config(self) -> None:
        """UT-CLI-05.01: --log-level debug overrides [logging].level."""
        write_config(
            self.fx.home,
            '[logging]\nlevel = "debug"\nmax_size_mb = 14\n',
        )
        payload = self.success_payload()
        with (
            mock.patch.object(cli_mod, "setup_logging", return_value="run-1") as setup_mock,
            mock.patch.object(cli_mod, "_execute", return_value=payload),
        ):
            exit_code, _, _ = self.run_cli(["search"])
            self.assertEqual(exit_code, 0)
            self.assertEqual(
                setup_mock.call_args.args,
                (self.fx.home, "debug", 14),
            )
            setup_mock.reset_mock()
            exit_code, _, _ = self.run_cli(["--log-level", "error", "search"])
            self.assertEqual(exit_code, 0)
            self.assertEqual(
                setup_mock.call_args.args,
                (self.fx.home, "error", 14),
            )

    def test_ut_cli_05_02_log_level_after_the_subcommand_is_a_usage_error(self) -> None:
        """UT-CLI-05.02: --log-level after the subcommand => E_USAGE (global option only)."""
        for argv in (
            ["search", "--log-level", "debug"],
            ["mailboxes", "--log-level", "debug"],
            ["new", "--log-level=debug"],
        ):
            with self.subTest(argv=argv):
                self.assert_error(2, self.run_cli(argv), "E_USAGE")
        self.assertFalse((self.fx.home / "logs" / "mailquery.log").exists())

    def test_defaults_when_no_config_and_no_flag(self) -> None:
        payload = self.success_payload()
        with (
            mock.patch.object(cli_mod, "setup_logging", return_value="run-1") as setup_mock,
            mock.patch.object(cli_mod, "_execute", return_value=payload),
        ):
            exit_code, _, _ = self.run_cli(["search"])
        self.assertEqual(exit_code, 0)
        self.assertEqual(setup_mock.call_args.args, (self.fx.home, "info", 10))


# --------------------------------------------------------------------------- #
# doctor
# --------------------------------------------------------------------------- #


class DoctorTests(_CliTestCase):
    def _doctor(self, **kwargs) -> dict:
        exit_code, stdout, stderr = self.run_cli(["doctor", "--json"], **kwargs)
        self.assertEqual(exit_code, 0, "doctor must always exit 0")
        self.assertEqual(stderr, "")
        payload = self.json_object(stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["command"], "doctor")
        self.assertIn("generated_at", payload)
        self.assertIsInstance(payload["checks"], list)
        return payload

    def test_doctor_default_output_is_human_readable(self) -> None:
        exit_code, stdout, stderr = self.run_cli(["doctor"])
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertFalse(
            stdout.lstrip().startswith("{"), "default doctor output must be text"
        )
        self.assertIn("mailquery doctor - environment and read-only preflight", stdout)
        self.assertIn("Checks:", stdout)
        self.assertIn("[ok]", stdout)
        self.assertIn("Result: 11/11 checks passed", stdout)
        self.assertIn("Notes:", stdout)
        self.assertIn("mailquery doctor --json", stdout)
        self.assertNotIn('"checks"', stdout)
        for line in stdout.splitlines():
            self.assertLessEqual(len(line), 100, f"doctor line too long: {line!r}")

    def test_doctor_human_report_shows_failures(self) -> None:
        exit_code, stdout, stderr = self.run_cli(
            ["doctor"], mail_root=self.fx.root / "missing-mail"
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("[FAIL]", stdout)
        self.assertIn("Result: ", stdout)
        self.assertIn("failed)", stdout)
        self.assertIn("E_STORE_NOT_FOUND", stdout)
        self.assertNotIn('"checks"', stdout)

    def test_doctor_validates_account_resolution(self) -> None:
        write_config(self.fx.home, '[scope."No Such Account"]\n')
        payload = self._doctor()
        config = next(check for check in payload["checks"] if check["name"] == "config")
        self.assertFalse(config["ok"])
        self.assertIn("E_CONFIG_ACCOUNT_UNKNOWN", config["detail"])

    def test_doctor_validates_mailbox_resolution(self) -> None:
        content = f'[scope."{ICLOUD_LABEL}"]\nmailbox_list = ["No Such Folder"]\n'
        write_config(self.fx.home, content)
        payload = self._doctor()
        config = next(check for check in payload["checks"] if check["name"] == "config")
        self.assertFalse(config["ok"])
        self.assertIn("E_MAILBOX_NOT_FOUND", config["detail"])

    def test_doctor_distinguishes_missing_and_empty_config(self) -> None:
        payload = self._doctor()
        config = next(check for check in payload["checks"] if check["name"] == "config")
        self.assertTrue(config["ok"])
        self.assertIn("no config.toml (optional)", config["detail"])

        write_config(self.fx.home, "# template only\n")
        payload = self._doctor()
        config = next(check for check in payload["checks"] if check["name"] == "config")
        self.assertTrue(config["ok"])
        self.assertIn("exists but declares no [scope.*] blocks", config["detail"])

    def test_doctor_lists_available_accounts_when_none_declared(self) -> None:
        payload = self._doctor()
        config = next(check for check in payload["checks"] if check["name"] == "config")
        self.assertTrue(config["ok"])
        self.assertIn("0 account block(s) declared", config["detail"])
        self.assertIn("available: iCloud (fixture@icloud.com)", config["detail"])
        self.assertIn("Gmail (fixture@gmail.com)", config["detail"])

        write_config(self.fx.home, '# template\n[scope."No Such Account"]\n')
        payload = self._doctor()
        config = next(check for check in payload["checks"] if check["name"] == "config")
        self.assertFalse(config["ok"])
        self.assertIn("E_CONFIG_ACCOUNT_UNKNOWN", config["detail"])

    def test_doctor_reports_all_required_checks(self) -> None:
        payload = self._doctor()
        names = [check["name"] for check in payload["checks"]]
        self.assertEqual(
            names,
            [
                "python",
                "home",
                "driver",
                "store",
                "envelope_index",
                "schema",
                "readonly_strategy",
                "accounts_db",
                "config",
                "state",
                "lock",
            ],
        )
        for check in payload["checks"]:
            self.assertEqual(set(check), {"name", "ok", "detail"})
            self.assertIsInstance(check["ok"], bool)
            self.assertIsInstance(check["detail"], str)
        by_name = {check["name"]: check for check in payload["checks"]}
        self.assertTrue(by_name["python"]["ok"])
        self.assertTrue(by_name["home"]["ok"])
        self.assertTrue(by_name["config"]["ok"])

    def test_ut_cli_10_01_broken_store_marks_dependants_not_evaluated(self) -> None:
        """UT-CLI-10.01: store fails => envelope_index/schema/readonly_strategy/config not evaluated."""
        write_config(self.fx.home)
        payload = self._doctor(mail_root=self.fx.root / "missing-mail")
        by_name = {check["name"]: check for check in payload["checks"]}
        self.assertFalse(by_name["store"]["ok"])
        self.assertIn("E_STORE_NOT_FOUND", by_name["store"]["detail"])
        self.assertFalse(by_name["envelope_index"]["ok"])
        self.assertEqual(by_name["envelope_index"]["detail"], "not evaluated: store failed")
        for name in ("schema", "readonly_strategy"):
            self.assertFalse(by_name[name]["ok"])
            self.assertEqual(by_name[name]["detail"], "not evaluated: envelope_index failed")
        self.assertFalse(by_name["config"]["ok"])
        self.assertEqual(by_name["config"]["detail"], "not evaluated: schema failed")
        for name in ("python", "home", "accounts_db", "state", "lock"):
            self.assertTrue(by_name[name]["ok"], by_name[name])
            self.assertFalse(by_name[name]["detail"].startswith("not evaluated"))

    def test_ut_cli_10_02_broken_store_without_blocks_config_is_ok_and_unknown(self) -> None:
        """UT-CLI-10.02: store fails, no blocks => config ok=true, accounts unknown (schema failed)."""
        payload = self._doctor(mail_root=self.fx.root / "missing-mail")
        config = next(check for check in payload["checks"] if check["name"] == "config")
        self.assertTrue(config["ok"])
        self.assertIn(
            "0 account block(s) declared; available accounts: unknown (schema failed)",
            config["detail"],
        )

    def test_ut_cli_10_03_envelope_index_failure_blocks_schema_and_strategy(self) -> None:
        """UT-CLI-10.03: envelope_index fails with store ok => schema/readonly_strategy not evaluated."""
        error = MailqueryError("E_PERMISSION", "Envelope Index is not readable", "grant access")
        with mock.patch.object(apple_mail_mod, "probe_envelope_index", side_effect=error):
            payload = self._doctor()
        by_name = {check["name"]: check for check in payload["checks"]}
        self.assertTrue(by_name["store"]["ok"])
        self.assertFalse(by_name["envelope_index"]["ok"])
        self.assertIn("E_PERMISSION", by_name["envelope_index"]["detail"])
        for name in ("schema", "readonly_strategy"):
            self.assertFalse(by_name[name]["ok"])
            self.assertEqual(by_name[name]["detail"], "not evaluated: envelope_index failed")

    def test_ut_cli_10_04_schema_failure_blocks_resolution_but_not_syntax(self) -> None:
        """UT-CLI-10.04: schema fails => block resolution not evaluated; invalid syntax still reported."""
        write_config(self.fx.home)
        with mock.patch.object(apple_mail_mod, "open_store", side_effect=RuntimeError("kaboom")):
            payload = self._doctor()
            by_name = {check["name"]: check for check in payload["checks"]}
            self.assertTrue(by_name["envelope_index"]["ok"])
            self.assertFalse(by_name["schema"]["ok"])
            self.assertFalse(by_name["config"]["ok"])
            self.assertEqual(by_name["config"]["detail"], "not evaluated: schema failed")

            write_config(self.fx.home, "unknown_key = 1\n")
            payload = self._doctor()
        by_name = {check["name"]: check for check in payload["checks"]}
        self.assertFalse(by_name["config"]["ok"])
        self.assertIn("E_CONFIG_INVALID", by_name["config"]["detail"])

    def test_ut_cli_10_05_no_blocks_and_accounts_db_down_reports_unavailable(self) -> None:
        """UT-CLI-10.05: no blocks, dependency ok, accounts_db down => Accounts4.sqlite unavailable."""
        payload = self._doctor(accounts_db=self.fx.root / "missing-accounts.sqlite")
        by_name = {check["name"]: check for check in payload["checks"]}
        self.assertTrue(by_name["schema"]["ok"])
        self.assertFalse(by_name["accounts_db"]["ok"])
        self.assertTrue(by_name["config"]["ok"])
        self.assertIn(
            "available accounts: unknown (Accounts4.sqlite unavailable)",
            by_name["config"]["detail"],
        )

    def test_ut_cli_11_01_state_without_cursor_explains_first_run(self) -> None:
        """UT-CLI-11.01: lookback = "15min" and no state.json => the section 12.8 detail."""
        write_config(self.fx.home, '[new]\nlookback = "15min"\n')
        payload = self._doctor()
        state = next(check for check in payload["checks"] if check["name"] == "state")
        self.assertTrue(state["ok"])
        self.assertEqual(
            state["detail"],
            "no state yet; the next new run is a first run and emits the messages "
            "received in the last 15min before the newest message",
        )

    def test_ut_cli_11_02_state_with_cursor_reports_it(self) -> None:
        """UT-CLI-11.02: with a cursor => cursor last_date_received=<n> last_uid=<n>."""
        write_state(
            self.fx.home,
            {
                "schema": 1,
                "updated_at": "",
                "last_run": None,
                "cursor": {
                    "last_date_received": 1700000000,
                    "last_uid": 42,
                    "lookback_seconds": 600,
                },
                "emitted_uids": [],
            },
        )
        payload = self._doctor()
        state = next(check for check in payload["checks"] if check["name"] == "state")
        self.assertTrue(state["ok"])
        self.assertEqual(
            state["detail"],
            "schema: 1 (migration pending); cursor last_date_received=1700000000 "
            "last_uid=apple_mail:42",
        )

    def test_ut_st_06_06_doctor_reports_migration_pending_then_schema_2(self) -> None:
        """UT-ST-06.06: ``doctor`` reports ``schema: 1 (migration pending)`` until it is persisted."""
        write_config(self.fx.home, DEFAULT_CONFIG)
        write_state(
            self.fx.home,
            {
                "schema": 1,
                "updated_at": "",
                "last_run": None,
                "cursor": {
                    "last_date_received": 1700000000,
                    "last_uid": 42,
                    "lookback_seconds": 600,
                },
                "emitted_uids": [42],
            },
        )
        payload = self._doctor()
        state = next(check for check in payload["checks"] if check["name"] == "state")
        self.assertTrue(state["ok"])
        self.assertEqual(
            state["detail"],
            "schema: 1 (migration pending); cursor last_date_received=1700000000 "
            "last_uid=apple_mail:42",
        )

        exit_code, _stdout, stderr = self.run_cli(["new"])
        self.assertEqual(exit_code, 0, stderr)
        payload = self._doctor()
        state = next(check for check in payload["checks"] if check["name"] == "state")
        self.assertTrue(state["ok"])
        self.assertTrue(state["detail"].startswith("schema: 2; cursor last_date_received="))
        self.assertTrue(state["detail"].endswith("last_uid=apple_mail:83170"))

    def test_ut_st_06_07_doctor_reports_pruned_ring_and_invalid_cursor_driver(self) -> None:
        """UT-ST-06.07: ``doctor`` reports the ring pruning and the uninstalled cursor driver."""
        write_config(self.fx.home, DEFAULT_CONFIG)
        write_state(
            self.fx.home,
            {
                "schema": 2,
                "updated_at": "",
                "last_run": None,
                "cursor": {
                    "last_date_received": 1700000000,
                    "last_uid": "apple_mail:1",
                    "lookback_seconds": 600,
                },
                "emitted_uids": ["graph:1", "graph:2"],
            },
        )
        payload = self._doctor()
        state = next(check for check in payload["checks"] if check["name"] == "state")
        self.assertTrue(state["ok"])
        self.assertIn(
            "pruned 2 emitted uid(s) of uninstalled drivers: graph", state["detail"]
        )

        # A cursor of an uninstalled driver is E_STATE_CORRUPT (DP-03 lifecycle).
        write_state(
            self.fx.home,
            {
                "schema": 2,
                "updated_at": "",
                "last_run": None,
                "cursor": {
                    "last_date_received": 1700000000,
                    "last_uid": "graph:1",
                    "lookback_seconds": 600,
                },
                "emitted_uids": [],
            },
        )
        payload = self._doctor()
        state = next(check for check in payload["checks"] if check["name"] == "state")
        self.assertFalse(state["ok"])
        self.assertIn("E_STATE_CORRUPT", state["detail"])
        self.assertIn("graph", state["detail"])

    def test_ut_cli_12_01_envelope_index_with_shm_opens_live_ro(self) -> None:
        """UT-CLI-12.01: -shm present => the live database is opened; strategy live_ro."""
        fx = build_store(extended=True)
        self.addCleanup(fx.cleanup)
        payload = self._doctor(home=fx.home, mail_root=fx.mail_root, accounts_db=fx.accounts_db)
        by_name = {check["name"]: check for check in payload["checks"]}
        self.assertTrue(by_name["envelope_index"]["ok"], by_name["envelope_index"])
        self.assertTrue(by_name["readonly_strategy"]["ok"])
        self.assertTrue(by_name["readonly_strategy"]["detail"].startswith("live_ro:"))

    def test_ut_cli_12_02_unreadable_envelope_index_fails(self) -> None:
        """UT-CLI-12.02: base unreadable (permission, mocked on every OS) => ok=false."""
        # File modes/ACLs are not reliable across OSes and users (D-07): make the
        # open of the base itself fail with a permission error, on every OS.
        with mock.patch("mailquery.store.shutil.copy2", side_effect=PermissionError("denied")):
            payload = self._doctor()
        by_name = {check["name"]: check for check in payload["checks"]}
        self.assertFalse(by_name["envelope_index"]["ok"])
        self.assertIn("E_PERMISSION", by_name["envelope_index"]["detail"])
        self.assertFalse(by_name["schema"]["ok"])

    def test_doctor_tolerates_unexpected_store_errors(self) -> None:
        with (
            mock.patch.object(apple_mail_mod, "detect_version", side_effect=RuntimeError("kaboom")),
            mock.patch.object(apple_mail_mod, "open_store", side_effect=RuntimeError("kaboom")),
        ):
            payload = self._doctor()
        by_name = {check["name"]: check for check in payload["checks"]}
        self.assertFalse(by_name["store"]["ok"])
        self.assertIn("RuntimeError", by_name["store"]["detail"])
        self.assertFalse(by_name["schema"]["ok"])

    def test_doctor_envelope_index_preserves_detection_error(self) -> None:
        error = MailqueryError(
            "E_PERMISSION",
            "cannot read ~/Library/Mail/PersistenceInfo.plist: permission denied",
            "grant Full Disk Access to the application running mailquery",
        )
        with (
            mock.patch.object(apple_mail_mod, "detect_version", side_effect=error),
            mock.patch.object(apple_mail_mod, "open_store", side_effect=error),
        ):
            payload = self._doctor()
        by_name = {check["name"]: check for check in payload["checks"]}
        # The cause stays in the first failing check; dependants are not evaluated.
        self.assertIn("E_PERMISSION", by_name["store"]["detail"])
        self.assertFalse(by_name["envelope_index"]["ok"])
        self.assertEqual(by_name["envelope_index"]["detail"], "not evaluated: store failed")

    def test_doctor_without_blocks_lists_every_account_label(self) -> None:
        # Labels of accounts that have no folders in the store are still listed.
        from tests.test_config import MISSING_LABEL, _fake_labels

        backend = AppleMailBackend(
            mail_root=self.fx.mail_root,
            labels=_fake_labels(),
            tmp_root=self.fx.home / "tmp",
        )
        exit_code, stdout, _ = self._run_with_backend(["doctor", "--json"], backend)
        self.assertEqual(exit_code, 0)
        config = next(c for c in json.loads(stdout)["checks"] if c["name"] == "config")
        self.assertTrue(config["ok"])
        self.assertIn("available:", config["detail"])
        self.assertIn(MISSING_LABEL, config["detail"])

    def _run_with_backend(self, argv, backend):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli_mod.main(argv, home=self.fx.home, backend=backend)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_doctor_reports_invalid_config_but_exits_zero(self) -> None:
        write_config(self.fx.home, "unknown_key = 1\n")
        payload = self._doctor()
        by_name = {check["name"]: check for check in payload["checks"]}
        self.assertFalse(by_name["config"]["ok"])
        self.assertIn("E_CONFIG_INVALID", by_name["config"]["detail"])

    def test_doctor_tolerates_a_broken_home(self) -> None:
        broken_home = self.fx.root / "broken-home"
        broken_home.write_text("not a directory", encoding="utf-8")
        payload = self._doctor(home=broken_home)
        by_name = {check["name"]: check for check in payload["checks"]}
        self.assertFalse(by_name["home"]["ok"])
        if sys.platform != "win32":
            # On Windows reading "<file>/config.toml" is "not found", so the
            # config check legitimately passes there (D-07).
            self.assertFalse(by_name["config"]["ok"])

    def _home_check(self, home: Path) -> dict:
        backend = AppleMailBackend(
            mail_root=self.fx.mail_root,
            accounts_db=self.fx.accounts_db,
            tmp_root=home / "tmp",
        )
        self.addCleanup(backend.close)
        checks = cli_mod._collect_doctor_checks(home, backend)
        return next(check for check in checks if check["name"] == "home")

    def test_ut_cli_13_01_home_with_mode_0755_fails(self) -> None:
        """UT-CLI-13.01: POSIX home 0755 => home ok=false (Windows: writable => ok)."""
        home = self.fx.root / "home-0755"
        home.mkdir()
        if sys.platform != "win32":
            home.chmod(0o755)
        # Skip the self-repairing chmod so the doctor sees the real mode.
        with mock.patch.object(cli_mod, "ensure_app_home"):
            for name in cli_mod.APP_HOME_SUBDIRS:
                (home / name).mkdir(mode=0o700, exist_ok=True)
            check = self._home_check(home)
        if sys.platform != "win32":
            self.assertFalse(check["ok"])
            self.assertIn("mode=0o755", check["detail"])
        else:
            self.assertTrue(check["ok"], check["detail"])

    def test_ut_cli_13_02_win32_probe_file_permission_error_fails(self) -> None:
        """UT-CLI-13.02: win32 patched, probe file creation raises PermissionError => ok=false."""
        home = self.fx.root / "home-win32"
        with (
            mock.patch.object(sys, "platform", "win32"),
            mock.patch.object(Path, "write_bytes", side_effect=PermissionError("denied")),
        ):
            check = self._home_check(home)
        self.assertFalse(check["ok"])
        self.assertIn("not writable", check["detail"])

    def test_doctor_reports_lock_contention_but_exits_zero(self) -> None:
        from mailquery.state import RunLock as RealRunLock

        holder = RealRunLock(self.fx.home)
        holder.acquire()
        self.addCleanup(holder.release)
        payload = self._doctor()
        by_name = {check["name"]: check for check in payload["checks"]}
        self.assertFalse(by_name["lock"]["ok"])
        self.assertIn("another", by_name["lock"]["detail"])


# --------------------------------------------------------------------------- #
# UT-DRV-05 — doctor `driver` check (AC-02, AC-18, PRD-v2.1 §11.6)
# --------------------------------------------------------------------------- #

MACOS_DRIVER_ORDER = [
    "python", "home", "driver", "store", "envelope_index", "schema",
    "readonly_strategy", "accounts_db", "config", "state", "lock",
]
WINDOWS_DRIVER_ORDER = [
    "python", "home", "driver", "pywin32", "outlook", "stores",
    "readonly_strategy", "object_model_guard", "config", "state", "lock",
]


class DriverDoctorTests(_CliTestCase):
    """UT-DRV-05 — the ``driver`` check of ``doctor`` (AC-02, AC-18)."""

    def _registry(self, *entry_points) -> BackendRegistry:
        return BackendRegistry(
            platform=sys.platform,
            entry_points=[*internal_entry_points(), *entry_points],
        )

    def _run_doctor(self, registry: BackendRegistry, *, argv=("doctor", "--json"), **kwargs):
        with mock.patch.object(cli_mod, "BackendRegistry", lambda: registry):
            return self.run_cli(list(argv), **kwargs)

    def _doctor(self, registry: BackendRegistry | None = None, **kwargs) -> dict:
        registry = registry if registry is not None else self._registry()
        exit_code, stdout, stderr = self._run_doctor(registry, **kwargs)
        self.assertEqual(exit_code, 0, "doctor must always exit 0")
        self.assertEqual(stderr, "")
        return self.json_object(stdout)

    @staticmethod
    def _by_name(payload: dict) -> dict[str, dict]:
        return {check["name"]: check for check in payload["checks"]}

    @staticmethod
    def _windows_ordered() -> list[str]:
        """``_DoctorRun.ordered()`` with the Windows backend checks (platform-independent)."""
        run = cli_mod._DoctorRun(Path(tempfile.gettempdir()))
        for name in ("python", "home", "driver"):
            run.record(name, True, "detail")
        run.backend_checks = [
            {"name": name, "ok": True, "detail": "detail"}
            for name in ("pywin32", "outlook", "stores", "readonly_strategy", "object_model_guard")
        ]
        for name in ("config", "state", "lock"):
            run.record(name, True, "detail")
        return [check["name"] for check in run.ordered()]

    def _native_detail(self, version: str | None = None) -> str:
        version = package_version() if version is None else version
        return (
            f"apple_mail (api=1; pkg {version}; network=false; readonly=structural; "
            "body_local=true; attachments=local; native_order=numeric)"
        )

    def test_ut_drv_05_01_check_order_is_macos_and_windows_with_driver_after_home(self) -> None:
        """UT-DRV-05.01: `driver` sits after `home` in the macOS and Windows orders."""
        payload = self._doctor()
        self.assertEqual([check["name"] for check in payload["checks"]], MACOS_DRIVER_ORDER)
        self.assertEqual(self._windows_ordered(), WINDOWS_DRIVER_ORDER)

    def test_ut_drv_05_02_detail_lists_api_package_and_capabilities(self) -> None:
        """UT-DRV-05.02: the detail has api, pkg, network, readonly, body_local, attachments, native_order."""
        payload = self._doctor()
        driver = self._by_name(payload)["driver"]
        self.assertTrue(driver["ok"], driver)
        self.assertEqual(driver["detail"], self._native_detail() + "; no declared drivers")
        for token in (
            "api=1",
            "pkg ",
            "network=false",
            "readonly=structural",
            "body_local=true",
            "attachments=local",
            "native_order=numeric",
        ):
            self.assertIn(token, driver["detail"])

        # A prefixed native block keeps the native entry and drops the suffix.
        write_config(self.fx.home, PREFIXED_CONFIG)
        driver = self._by_name(self._doctor())["driver"]
        self.assertTrue(driver["ok"], driver)
        self.assertEqual(driver["detail"], self._native_detail())
        self.assertNotIn("no declared drivers", driver["detail"])

    def test_ut_drv_05_03_incompatible_declared_driver_fails_and_blocks_config(self) -> None:
        """UT-DRV-05.03: an incompatible declared driver ⇒ ok=false with reason/hint; config not evaluated."""
        registry = self._registry(
            FakeEntryPoint(PLUGIN_DRIVER, plugin=plugin_class(plugin_api=2))
        )
        write_config(self.fx.home, f'[scope."{PLUGIN_DRIVER}:work"]\n')
        payload = self._doctor(registry)
        checks = self._by_name(payload)
        driver = checks["driver"]
        self.assertFalse(driver["ok"])
        self.assertIn("E_PLUGIN_INCOMPATIBLE", driver["detail"])
        self.assertIn("expected 1, found 2", driver["detail"])
        self.assertIn("(hint: ", driver["detail"])
        self.assertFalse(checks["config"]["ok"])
        self.assertEqual(checks["config"]["detail"], "not evaluated: driver failed")

    def test_ut_drv_05_04_invalid_config_validates_only_the_native_driver(self) -> None:
        """UT-DRV-05.04: invalid config.toml ⇒ native only plus `declared drivers: unknown (config failed)`."""
        write_config(self.fx.home, "unknown_key = 1\n")
        payload = self._doctor()
        checks = self._by_name(payload)
        self.assertTrue(checks["driver"]["ok"], checks["driver"])
        self.assertEqual(
            checks["driver"]["detail"],
            self._native_detail() + "; declared drivers: unknown (config failed)",
        )
        self.assertFalse(checks["config"]["ok"])
        self.assertIn("E_CONFIG_INVALID", checks["config"]["detail"])

    def test_ut_drv_05_05_no_config_or_no_blocks_lists_no_declared_drivers(self) -> None:
        """UT-DRV-05.05: no config.toml or no blocks ⇒ native + `no declared drivers`."""
        expected = self._native_detail() + "; no declared drivers"
        self.assertEqual(self._by_name(self._doctor())["driver"]["detail"], expected)
        write_config(self.fx.home, "# template only\n")
        self.assertEqual(self._by_name(self._doctor())["driver"]["detail"], expected)

    def test_ut_drv_05_06_several_drivers_are_all_listed(self) -> None:
        """UT-DRV-05.06: native + plugin are listed; a failing one fails the check."""
        write_config(
            self.fx.home,
            f'[scope."{PLUGIN_DRIVER}:work"]\n\n[scope."{ICLOUD_LABEL}"]\n',
        )
        registry = self._registry(FakeEntryPoint(PLUGIN_DRIVER, plugin=FakePluginBackend()))
        checks = self._by_name(self._doctor(registry))
        self.assertTrue(checks["driver"]["ok"], checks["driver"])
        self.assertEqual(
            checks["driver"]["detail"],
            self._native_detail()
            + f"; {PLUGIN_DRIVER} (api=1; pkg {PLUGIN_VERSION}; network=true; "
            "readonly=promise; body_local=false; attachments=remote; native_order=text)",
        )
        self.assertTrue(checks["config"]["ok"], checks["config"])

        broken = self._registry(
            FakeEntryPoint(PLUGIN_DRIVER, plugin=plugin_class(plugin_api=2))
        )
        checks = self._by_name(self._doctor(broken))
        self.assertFalse(checks["driver"]["ok"])
        self.assertIn("apple_mail (api=1;", checks["driver"]["detail"])
        self.assertIn("E_PLUGIN_INCOMPATIBLE", checks["driver"]["detail"])
        self.assertEqual(checks["config"]["detail"], "not evaluated: driver failed")

    def test_ut_drv_05_07_driver_failure_wins_over_the_backend_dependency(self) -> None:
        """UT-DRV-05.07: driver and schema fail together ⇒ config reports `not evaluated: driver failed`."""
        write_config(self.fx.home, f'[scope."{PLUGIN_DRIVER}:work"]\n')
        registry = self._registry(
            FakeEntryPoint(PLUGIN_DRIVER, plugin=plugin_class(plugin_api=2))
        )
        with mock.patch.object(apple_mail_mod, "open_store", side_effect=RuntimeError("kaboom")):
            payload = self._doctor(registry)
        checks = self._by_name(payload)
        self.assertFalse(checks["driver"]["ok"])
        self.assertFalse(checks["schema"]["ok"])
        self.assertFalse(checks["config"]["ok"])
        self.assertEqual(checks["config"]["detail"], "not evaluated: driver failed")

    def test_ut_drv_05_08_driver_is_third_in_both_platform_orders(self) -> None:
        """UT-DRV-05.08: `driver` is exactly at position 3 on macOS and on Windows."""
        payload = self._doctor()
        names = [check["name"] for check in payload["checks"]]
        self.assertEqual(names.index("driver"), 2)
        self.assertEqual(MACOS_DRIVER_ORDER.index("driver"), 2)
        self.assertEqual(WINDOWS_DRIVER_ORDER.index("driver"), 2)
        self.assertEqual(self._windows_ordered().index("driver"), 2)


# --------------------------------------------------------------------------- #
# End-to-end contract against the synthetic fixture store
# --------------------------------------------------------------------------- #


class EndToEndContractTests(_CliTestCase):
    """Runs the real command functions against the synthetic fixture store."""

    def _require_store(self) -> None:
        from mailquery.store import open_store

        store = open_store(self.fx.mail_root, tmp_root=self.fx.root / "tmp")
        try:
            store.close()
        except Exception:  # noqa: BLE001 - best effort cleanup
            pass

    def _require_time_parser(self) -> None:
        from mailquery.search import parse_relative_time

        parse_relative_time("7d")

    def test_no_declared_accounts_returns_warning_and_zero(self) -> None:
        self._require_store()
        exit_code, stdout, stderr = self.run_cli(["search"])
        self.assertEqual(exit_code, 0)
        payload = self.json_object(stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["count"], 0)
        self.assertEqual(payload["messages"], [])
        self.assertTrue(
            any(warning.startswith("W_NO_ACCOUNTS") for warning in payload["warnings"]),
            payload["warnings"],
        )
        self.assertEqual(stderr, "")

        exit_code, stdout, _ = self.run_cli(["mailboxes"])
        self.assertEqual(exit_code, 0)
        payload = self.json_object(stdout)
        self.assertTrue(
            any(warning.startswith("W_NO_ACCOUNTS") for warning in payload["warnings"]),
            payload["warnings"],
        )

    def test_text_scan_without_narrowing_filter_exits_4(self) -> None:
        self._require_store()
        write_config(self.fx.home, f'[scope."{ICLOUD_LABEL}"]\n')
        payload = self.assert_error(
            4,
            self.run_cli(["search", "--text", "invoice"]),
            "E_UNBOUNDED_SCAN",
            "search",
        )
        self.assertIn("--since", payload["error"]["hint"])

    def test_text_scan_bounded_by_configured_folder_succeeds(self) -> None:
        self._require_store()
        write_config(self.fx.home, DEFAULT_CONFIG)
        exit_code, stdout, _ = self.run_cli(["search", "--text", "invoice"])
        self.assertEqual(exit_code, 0)
        payload = self.json_object(stdout)
        self.assertTrue(payload["ok"])
        self.assertGreaterEqual(payload["count"], 1)
        self.assertIn(
            prefixed_uid(2714), [message["uid"] for message in payload["messages"]]
        )

    def test_invalid_since_is_a_bad_time_error(self) -> None:
        self._require_time_parser()
        payload = self.assert_error(
            2,
            self.run_cli(["search", "--since", "nonsense"]),
            "E_BAD_TIME",
            "search",
        )
        self.assertIn("ISO 8601", payload["error"]["hint"])

    def test_show_returns_the_message_payload(self) -> None:
        self._require_store()
        write_config(self.fx.home, DEFAULT_CONFIG)
        exit_code, stdout, stderr = self.run_cli(["show", "83143"])
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        payload = self.json_object(stdout)
        self.assertTrue(payload["ok"])
        message = payload["message"]
        self.assertEqual(message["uid"], prefixed_uid(83143))
        self.assertIn("headers", message)
        self.assertIn("source", message)
        self.assertIn("emlx_path", message["source"])

    def test_unknown_uid_show_is_a_usage_error(self) -> None:
        self._require_store()
        write_config(self.fx.home, DEFAULT_CONFIG)
        self.assert_error(2, self.run_cli(["show", "123"]), "E_USAGE", "show")


if __name__ == "__main__":
    unittest.main()


# --------------------------------------------------------------------------- #
# UTF-8 and LF on stdout/stderr (RF-32, PRD 20), through a real pipe
# --------------------------------------------------------------------------- #

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Runs ``cli.main`` inside the subprocess pointed at the synthetic store; the
# modes that need non-ASCII output replace ``_execute`` (the store is ASCII-only).
_LAUNCHER = r"""
import sys
from pathlib import Path
from unittest import mock
from mailquery import cli
from mailquery.errors import MailqueryError

mode, root = sys.argv[1], Path(sys.argv[2])
kwargs = dict(home=root / "home", mail_root=root / "Mail",
              accounts_db=root / "Library" / "Accounts" / "Accounts4.sqlite")
argv = sys.argv[3:]
if mode == "ok":
    payload = {"messages": [{"subject": "Año á \U0001f600"}], "warnings": []}
    with mock.patch.object(cli, "_execute", return_value=payload):
        code = cli.main(argv, **kwargs)
elif mode == "error":
    error = MailqueryError("E_USAGE", "carpeta ñandú \U0001f600", "pista á")
    with mock.patch.object(cli, "_execute", side_effect=error):
        code = cli.main(argv, **kwargs)
else:
    code = cli.main(argv, **kwargs)
sys.exit(code)
"""

_SUBJECT = "Año á \U0001f600"
_ERROR_MESSAGE = "carpeta ñandú \U0001f600"


class PipeEncodingTests(unittest.TestCase):
    """Subprocess with pipes, cp1252 and ``PYTHONUTF8=0`` (plan 7.1 isolation)."""

    def setUp(self) -> None:
        self.fx = build_store()
        self.addCleanup(self.fx.cleanup)

    def run_launcher(self, mode: str, *argv: str) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env["HOME"] = env["USERPROFILE"] = str(self.fx.home)
        env["PYTHONPATH"] = os.pathsep.join([str(_REPO_ROOT / "src"), str(_REPO_ROOT)])
        env["PYTHONUTF8"] = "0"
        env["PYTHONIOENCODING"] = "cp1252"
        return subprocess.run(
            [sys.executable, "-B", "-c", _LAUNCHER, mode, str(self.fx.root), *argv],
            capture_output=True,
            env=env,
            cwd=str(_REPO_ROOT),
            timeout=120,
        )

    def test_ut_cli_08_01_non_ascii_json_is_utf8_bytes_on_stdout(self) -> None:
        """UT-CLI-08.01: JSON with non-ASCII text is written as UTF-8 bytes."""
        result = self.run_launcher("ok", "search")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(_SUBJECT.encode("utf-8"), result.stdout)
        payload = json.loads(result.stdout.decode("utf-8"))
        self.assertEqual(payload["messages"][0]["subject"], _SUBJECT)

    def test_ut_cli_08_02_error_json_and_stderr_summary_are_utf8(self) -> None:
        """UT-CLI-08.02: error JSON on stdout and the stderr summary are UTF-8."""
        result = self.run_launcher("error", "search")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn(_ERROR_MESSAGE.encode("utf-8"), result.stdout)
        self.assertIn(
            f"mailquery: E_USAGE: {_ERROR_MESSAGE}\n".encode("utf-8"), result.stderr
        )
        self.assertIn("mailquery: hint: pista á\n".encode("utf-8"), result.stderr)

    def test_ut_cli_08_03_no_crlf_in_stdout_or_stderr(self) -> None:
        """UT-CLI-08.03: no CR LF in stdout or stderr (data, errors, help, doctor)."""
        runs = (
            ("ok", "search"),
            ("error", "search"),
            ("plain", "--help"),
            ("plain", "search", "--help"),
            ("plain", "doctor"),
            ("plain", "doctor", "--json"),
            ("plain", "--version"),
            ("plain", "-v"),
        )
        for run in runs:
            with self.subTest(run=run):
                result = self.run_launcher(*run)
                self.assertTrue(result.stdout, result.stderr)
                self.assertNotIn(b"\r", result.stdout)
                self.assertNotIn(b"\r", result.stderr)

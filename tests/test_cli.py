"""Tests for ``mailquery.cli``: argparse contract, JSON output and exit codes.

The command functions of ``search.py`` and the store/accounts/state modules are
replaced by fakes so the CLI contract can be verified while those modules are
still being implemented in parallel. ``doctor`` is exercised end-to-end because
its contract is "never raises, always exit 0".
"""

from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from mailquery import cli as cli_mod
from mailquery.errors import MailqueryError
from mailquery.search import Filters

from tests.fixtures.make_fixtures import (
    DEFAULT_CONFIG,
    ICLOUD_LABEL,
    build_store,
    write_config,
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
)


class _FakeStore:
    def __init__(self) -> None:
        self.closed = False

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
        lines = stdout.splitlines()
        self.assertEqual(len(lines), 1, f"expected one stdout line, got {lines!r}")
        self.assertFalse(lines[0].startswith(" "), "JSON object must be compact")
        return json.loads(lines[0])

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

    def test_global_help_is_formatted_text_and_exits_zero(self) -> None:
        unused_home = self.fx.root / "unused-home"
        code, stdout, stderr = self.run_cli(["--help"], home=unused_home)
        self.assertEqual(code, 0)
        self.assertIn("usage: mailquery", stdout)
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

    def test_subcommand_help_is_formatted_for_every_command(self) -> None:
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
                for flag in flags:
                    self.assertIn(flag, stdout)
                self.assert_human_readable(stdout)
                self.assertEqual(stderr, "")

    def test_subcommand_help_has_specific_examples(self) -> None:
        examples = {
            "doctor": "mailquery doctor --json",
            "mailboxes": "mailquery mailboxes",
            "search": 'mailquery search --text "*factura*" --since 1mo',
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

    def test_all_forbidden_flags_are_rejected(self) -> None:
        for flag in FORBIDDEN_FLAGS:
            with self.subTest(flag=flag):
                exit_code, stdout, stderr = self.run_cli(["search", flag, "value"])
                self.assertEqual(exit_code, 2)
                payload = self.json_object(stdout)
                self.assertEqual(payload["error"]["code"], "E_USAGE")
                self.assertIn("E_USAGE", stderr)

    def test_show_requires_integer_uid(self) -> None:
        self.assert_error(2, self.run_cli(["show"]), "E_USAGE")
        self.assert_error(2, self.run_cli(["show", "not-a-uid"]), "E_USAGE")

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
        line = stdout.strip()
        parsed = json.loads(line)
        self.assertEqual(
            line,
            json.dumps(parsed, ensure_ascii=False, separators=(",", ":")),
        )
        self.assertEqual(stdout.count("\n"), 1)
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

    def test_debug_log_goes_to_file_not_stdout(self) -> None:
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
        self.assertIn("event=end command=search exit_code=0", log_text)


# --------------------------------------------------------------------------- #
# Error rendering and exit codes
# --------------------------------------------------------------------------- #


class ErrorContractTests(_CliTestCase):
    def test_error_codes_map_to_documented_exit_codes(self) -> None:
        cases = (
            ("E_USAGE", 2),
            ("E_CONFIG_INVALID", 2),
            ("E_CONFIG_ACCOUNT_UNKNOWN", 2),
            ("E_ACCOUNT_AMBIGUOUS", 2),
            ("E_MAILBOX_NOT_FOUND", 2),
            ("E_BAD_TIME", 2),
            ("E_BAD_FILTER", 2),
            ("E_STORE_NOT_FOUND", 3),
            ("E_SCHEMA_UNSUPPORTED", 3),
            ("E_PERMISSION", 3),
            ("E_STATE_CORRUPT", 3),
            ("E_UNBOUNDED_SCAN", 4),
            ("E_SCAN_TOO_LARGE", 4),
            ("E_LOCKED", 5),
            ("E_DB_BUSY", 5),
            ("E_INTERNAL", 1),
        )
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
                self.assertEqual(stdout.count("\n"), 1)

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
        store = _FakeStore()
        with (
            mock.patch.object(cli_mod, "RunLock", _FakeLock),
            mock.patch.object(cli_mod, "open_store", return_value=store),
            mock.patch.object(cli_mod, "AccountLabels", return_value=object()),
            mock.patch.object(
                cli_mod,
                "run_search",
                side_effect=MailqueryError("E_BAD_FILTER", "bad filter", "fix it"),
            ),
        ):
            exit_code, stdout, _ = self.run_cli(["search"])
        self.assertEqual(exit_code, 2)
        self.assertEqual(self.json_object(stdout)["error"]["code"], "E_BAD_FILTER")
        self.assertTrue(store.closed)

    def test_lock_busy_maps_to_exit_5(self) -> None:
        with mock.patch.object(cli_mod, "RunLock", _BusyLock):
            exit_code, stdout, stderr = self.run_cli(["search"])
        self.assertEqual(exit_code, 5)
        self.assertEqual(self.json_object(stdout)["error"]["code"], "E_LOCKED")
        self.assertIn("E_LOCKED", stderr)

    def test_lock_busy_against_a_real_flock_exits_5(self) -> None:
        from mailquery.state import RunLock as RealRunLock

        try:
            holder = RealRunLock(self.fx.home)
            holder.acquire()
        except NotImplementedError:
            self.skipTest("state.RunLock is not implemented yet")
        self.addCleanup(holder.release)
        exit_code, stdout, _ = self.run_cli(["search"])
        self.assertEqual(exit_code, 5)
        self.assertEqual(self.json_object(stdout)["error"]["code"], "E_LOCKED")


# --------------------------------------------------------------------------- #
# Dispatch
# --------------------------------------------------------------------------- #


class DispatchTests(_CliTestCase):
    def test_open_store_receives_test_paths_and_home_tmp(self) -> None:
        store = _FakeStore()
        with (
            mock.patch.object(cli_mod, "RunLock", _FakeLock),
            mock.patch.object(cli_mod, "open_store", return_value=store) as open_mock,
            mock.patch.object(cli_mod, "AccountLabels", return_value=object()) as labels_mock,
            mock.patch.object(
                cli_mod,
                "run_mailboxes",
                return_value={"accounts": [], "mailboxes": [], "warnings": []},
            ),
        ):
            exit_code, stdout, _ = self.run_cli(["mailboxes"])
        self.assertEqual(exit_code, 0)
        open_mock.assert_called_once_with(
            mail_root=self.fx.mail_root,
            tmp_root=self.fx.home / "tmp",
        )
        labels_mock.assert_called_once_with(
            self.fx.accounts_db,
            tmp_dir=self.fx.home / "tmp",
        )
        self.assertTrue(store.closed)
        self.assertTrue(self.json_object(stdout)["ok"])

    def test_search_dispatch_builds_filters(self) -> None:
        store = _FakeStore()
        config = cli_mod.load_config(self.fx.home)
        with (
            mock.patch.object(cli_mod, "RunLock", _FakeLock),
            mock.patch.object(cli_mod, "open_store", return_value=store),
            mock.patch.object(cli_mod, "AccountLabels", return_value=object()),
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
        _, call_config, _, filters = run_mock.call_args.args
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
        store = _FakeStore()
        with (
            mock.patch.object(cli_mod, "RunLock", _FakeLock),
            mock.patch.object(cli_mod, "open_store", return_value=store),
            mock.patch.object(cli_mod, "AccountLabels", return_value=object()),
            mock.patch.object(
                cli_mod,
                "run_show",
                return_value={"message": {"uid": 83143}, "warnings": []},
            ) as run_mock,
        ):
            exit_code, stdout, _ = self.run_cli(["show", "83143"])
        self.assertEqual(exit_code, 0)
        run_mock.assert_called_once()
        self.assertEqual(run_mock.call_args.args[2], 83143)
        self.assertEqual(self.json_object(stdout)["message"], {"uid": 83143})

    def test_new_dispatch_peek_and_limit(self) -> None:
        store = _FakeStore()
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
            mock.patch.object(cli_mod, "open_store", return_value=store),
            mock.patch.object(cli_mod, "AccountLabels", return_value=object()),
            mock.patch.object(cli_mod, "StateStore", return_value=state_store) as state_mock,
            mock.patch.object(cli_mod, "run_new", return_value=payload) as run_mock,
        ):
            exit_code, stdout, _ = self.run_cli(["new", "--peek", "--limit", "7"])
        self.assertEqual(exit_code, 0)
        state_mock.assert_called_once_with(self.fx.home)
        self.assertEqual(run_mock.call_args.args[3], state_store)
        self.assertEqual(run_mock.call_args.kwargs, {"peek": True, "limit": 7})
        rendered = self.json_object(stdout)
        self.assertEqual(rendered["cursor"], {"previous": None, "current": None})
        self.assertEqual(rendered["count"], 0)


# --------------------------------------------------------------------------- #
# Logging setup / precedence
# --------------------------------------------------------------------------- #


class LoggingConfigTests(_CliTestCase):
    def test_log_level_flag_overrides_config(self) -> None:
        write_config(
            self.fx.home,
            '[logging]\nlevel = "debug"\nretention_days = 14\n',
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

    def test_defaults_when_no_config_and_no_flag(self) -> None:
        payload = self.success_payload()
        with (
            mock.patch.object(cli_mod, "setup_logging", return_value="run-1") as setup_mock,
            mock.patch.object(cli_mod, "_execute", return_value=payload),
        ):
            exit_code, _, _ = self.run_cli(["search"])
        self.assertEqual(exit_code, 0)
        self.assertEqual(setup_mock.call_args.args, (self.fx.home, "info", 7))


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
        self.assertIn("Result: 10/10 checks passed", stdout)
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

    def test_doctor_reports_all_required_checks(self) -> None:
        payload = self._doctor()
        names = [check["name"] for check in payload["checks"]]
        self.assertEqual(
            names,
            [
                "python",
                "home",
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

    def test_doctor_tolerates_a_broken_store(self) -> None:
        payload = self._doctor(mail_root=self.fx.root / "missing-mail")
        by_name = {check["name"]: check for check in payload["checks"]}
        self.assertFalse(by_name["store"]["ok"])
        self.assertFalse(by_name["envelope_index"]["ok"])
        self.assertFalse(by_name["schema"]["ok"])
        self.assertFalse(by_name["readonly_strategy"]["ok"])

    def test_doctor_tolerates_unexpected_store_errors(self) -> None:
        with (
            mock.patch.object(cli_mod, "detect_version", side_effect=RuntimeError("kaboom")),
            mock.patch.object(cli_mod, "open_store", side_effect=RuntimeError("kaboom")),
        ):
            payload = self._doctor()
        by_name = {check["name"]: check for check in payload["checks"]}
        self.assertFalse(by_name["store"]["ok"])
        self.assertIn("RuntimeError", by_name["store"]["detail"])
        self.assertFalse(by_name["schema"]["ok"])

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
        self.assertFalse(by_name["config"]["ok"])

    def test_doctor_reports_lock_contention_but_exits_zero(self) -> None:
        from mailquery.state import RunLock as RealRunLock

        try:
            holder = RealRunLock(self.fx.home)
            holder.acquire()
        except NotImplementedError:
            self.skipTest("state.RunLock is not implemented yet")
        self.addCleanup(holder.release)
        payload = self._doctor()
        by_name = {check["name"]: check for check in payload["checks"]}
        self.assertFalse(by_name["lock"]["ok"])
        self.assertIn("another", by_name["lock"]["detail"])


# --------------------------------------------------------------------------- #
# End-to-end contract against the synthetic fixture store
# --------------------------------------------------------------------------- #


class EndToEndContractTests(_CliTestCase):
    """Runs the real command functions against the synthetic fixture store."""

    def _require_store(self) -> None:
        from mailquery.store import open_store

        try:
            store = open_store(self.fx.mail_root, tmp_root=self.fx.root / "tmp")
        except NotImplementedError as exc:
            self.skipTest(f"store.py dependency not implemented yet: {exc}")
        try:
            store.close()
        except Exception:  # noqa: BLE001 - best effort cleanup
            pass

    def _require_time_parser(self) -> None:
        from mailquery.search import parse_relative_time

        try:
            parse_relative_time("7d")
        except NotImplementedError as exc:
            self.skipTest(f"search.py dependency not implemented yet: {exc}")

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
        self.assertIn(2714, [message["uid"] for message in payload["messages"]])

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
        self.assertEqual(message["uid"], 83143)
        self.assertIn("headers", message)
        self.assertIn("source", message)
        self.assertIn("emlx_path", message["source"])

    def test_unknown_uid_show_is_a_usage_error(self) -> None:
        self._require_store()
        write_config(self.fx.home, DEFAULT_CONFIG)
        self.assert_error(2, self.run_cli(["show", "123"]), "E_USAGE", "show")


if __name__ == "__main__":
    unittest.main()

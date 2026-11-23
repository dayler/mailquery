"""Tests for the log file: rotation, permissions, format and content.

Covers UT-LOG-01 (rotation), UT-LOG-02 (permissions), UT-LOG-03 (format) and
UT-LOG-04 (content), PRD RF-18 and section 14. UT-LOG-03.04 lives in
``tests/test_cli.py`` (renamed test).
"""

from __future__ import annotations

import io
import logging
import os
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from mailquery import cli as cli_mod
from mailquery.errors import MailqueryError
from mailquery.logging_setup import get_logger, setup_logging

from tests.fixtures.make_fixtures import (
    ACCOUNT_GMAIL,
    ACCOUNT_ICLOUD,
    ACCOUNT_LOCAL,
    ICLOUD_LABEL,
    build_store,
)

_MESSAGE_BYTES = 600_000  # with max_size_mb = 1, every message forces a rotation


def _close_log_handlers() -> None:
    """Release the log file so Windows can delete the temp dir."""
    logger = logging.getLogger("mailquery")
    for handler in list(logger.handlers):
        if isinstance(handler, logging.FileHandler):
            logger.removeHandler(handler)
            handler.close()


class _LogHomeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="mailquery-log-")
        self.addCleanup(tmp.cleanup)
        self.addCleanup(_close_log_handlers)
        self.home = Path(tmp.name)
        self.logs = self.home / "logs"
        self.log_path = self.logs / "mailquery.log"

    def rotate(self, count: int, max_size_mb: int = 1) -> None:
        """Write ``count`` oversized records; each one rotates the file."""
        setup_logging(self.home, "info", max_size_mb)
        logger = get_logger("mailquery.test")
        for index in range(count):
            logger.info("record=%d %s", index, "x" * _MESSAGE_BYTES)


class RotationTests(_LogHomeTestCase):
    def test_ut_log_01_01_exceeding_max_size_creates_first_rotated_file(self) -> None:
        """UT-LOG-01.01: with max_size_mb = 1, exceeding 1 MB creates mailquery.log.1."""
        setup_logging(self.home, "info", 1)
        logger = get_logger("mailquery.test")
        logger.info("small record")
        self.assertFalse((self.logs / "mailquery.log.1").exists())
        for index in range(3):
            logger.info("record=%d %s", index, "x" * _MESSAGE_BYTES)
        self.assertTrue((self.logs / "mailquery.log.1").is_file())
        self.assertTrue(self.log_path.is_file())

    def test_ut_log_01_02_seven_rotations_keep_only_five_rotated_files(self) -> None:
        """UT-LOG-01.02: 7 rotations leave only .1-.5; the oldest is deleted."""
        self.rotate(8)  # 8 records, 1 per file => 7 rotations
        names = sorted(path.name for path in self.logs.iterdir())
        self.assertEqual(
            names,
            [
                "mailquery.log",
                "mailquery.log.1",
                "mailquery.log.2",
                "mailquery.log.3",
                "mailquery.log.4",
                "mailquery.log.5",
            ],
        )
        self.assertIn("record=7 ", self.log_path.read_text(encoding="utf-8"))
        self.assertIn("record=6 ", (self.logs / "mailquery.log.1").read_text(encoding="utf-8"))
        # record=0 and record=1 were the oldest files and are gone.
        self.assertIn("record=2 ", (self.logs / "mailquery.log.5").read_text(encoding="utf-8"))


class PermissionTests(_LogHomeTestCase):
    def test_ut_log_02_01_log_file_is_0600(self) -> None:
        """UT-LOG-02.01: POSIX: mailquery.log is 0600."""
        setup_logging(self.home, "info", 1)
        get_logger("mailquery.test").info("hello")
        if os.name == "posix":
            self.assertEqual(self.log_path.stat().st_mode & 0o777, 0o600)
        self.assertTrue(self.log_path.is_file())

    def test_ut_log_02_02_rotated_files_are_0600(self) -> None:
        """UT-LOG-02.02: POSIX: rotated files (and the new current log) are 0600."""
        self.rotate(3)
        rotated = sorted(self.logs.glob("mailquery.log.*"))
        self.assertTrue(rotated)
        if os.name == "posix":
            for path in [self.log_path, *rotated]:
                self.assertEqual(path.stat().st_mode & 0o777, 0o600, path.name)


    def test_ut_log_02_03_log_handle_is_released_after_a_run(self) -> None:
        """UT-LOG-02.03: a finished run leaves no open log file (Windows-safe cleanup)."""
        fx = build_store()
        self.addCleanup(fx.cleanup)
        code = cli_mod.main(["search"], home=fx.home, mail_root=fx.mail_root)
        self.assertEqual(code, 0)
        handlers = [
            handler
            for handler in logging.getLogger("mailquery").handlers
            if isinstance(handler, logging.FileHandler)
        ]
        self.assertEqual(handlers, [])
        self.assertTrue((fx.home / "logs" / "mailquery.log").is_file())


class FormatTests(_LogHomeTestCase):
    def test_ut_log_03_01_line_has_comma_milliseconds_level_logger_and_run(self) -> None:
        """UT-LOG-03.01: YYYY-MM-DD HH:MM:SS,mmm LEVEL logger run=..."""
        run_id = setup_logging(self.home, "info", 10)
        get_logger("mailquery.cli").info("event=probe")
        get_logger("mailquery.cli").warning("event=probe")
        lines = self.log_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        pattern = (
            r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} "
            r"(INFO |WARNING) mailquery\.cli run=" + re.escape(run_id) + r" event=probe$"
        )
        for line in lines:
            self.assertRegex(line, pattern)
        self.assertTrue(lines[0].split(" ")[2] == "INFO")

    def test_ut_log_03_02_start_line_names_command_and_backend(self) -> None:
        """UT-LOG-03.02: event=start command=... backend=... drivers=..."""
        fx = build_store()
        self.addCleanup(fx.cleanup)
        self.addCleanup(_close_log_handlers)
        with mock.patch.object(cli_mod, "_execute", return_value={"messages": []}):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code = cli_mod.main(["search"], home=fx.home, mail_root=fx.mail_root)
        self.assertEqual(code, 0)
        text = (fx.home / "logs" / "mailquery.log").read_text(encoding="utf-8")
        self.assertRegex(
            text,
            r"(?m) INFO  mailquery\.cli run=[0-9a-f]{12} "
            r"event=start command=search backend=apple_mail drivers=apple_mail$",
        )

    def test_ut_log_03_03_store_line_has_strategy_and_version(self) -> None:
        """UT-LOG-03.03: store line with the connection strategy and the store version."""
        fx = build_store()
        self.addCleanup(fx.cleanup)
        self.addCleanup(_close_log_handlers)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            code = cli_mod.main(
                ["mailboxes"],
                home=fx.home,
                mail_root=fx.mail_root,
                accounts_db=fx.accounts_db,
            )
        self.assertEqual(code, 0)
        text = (fx.home / "logs" / "mailquery.log").read_text(encoding="utf-8")
        self.assertRegex(
            text,
            r"(?m) INFO  mailquery\.store run=[0-9a-f]{12} "
            r"strategy=(live_ro|copy_ro) version=V10 schema_ok=true$",
        )


class ContentTests(unittest.TestCase):
    SUBJECT = "Factura mayo Contoso"
    ADDRESS = "ana.garcia@contoso.example"
    PERSON = "Ana Garcia"
    FOLDER = "Facturas"
    TERM = "zebra-unico"
    UID = "424242"
    BODY = "cuerpo-secreto-del-mensaje"

    def setUp(self) -> None:
        self.fx = build_store()
        self.addCleanup(self.fx.cleanup)
        self.addCleanup(_close_log_handlers)

    def run_cli(self, argv, **kwargs) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        kwargs.setdefault("accounts_db", self.fx.accounts_db)
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli_mod.main(
                argv, home=self.fx.home, mail_root=self.fx.mail_root, **kwargs
            )
        return code, stdout.getvalue(), stderr.getvalue()

    def log_text(self) -> str:
        return (self.fx.home / "logs" / "mailquery.log").read_text(encoding="utf-8")

    def test_ut_log_04_01_error_logs_code_and_message(self) -> None:
        """UT-LOG-04.01: an error logs its code and log_message (or message without one)."""
        sanitized = MailqueryError(
            "E_BAD_FILTER", "secret filter detail", "fix it", log_message="invalid filter"
        )
        with mock.patch.object(cli_mod, "_execute", side_effect=sanitized):
            code, _, _ = self.run_cli(["search"])
        self.assertEqual(code, 2)
        text = self.log_text()
        self.assertRegex(text, r"(?m) ERROR mailquery\.cli run=\S+ event=error command=search "
                         r"code=E_BAD_FILTER message=invalid filter$")
        self.assertNotIn("secret filter detail", text)

        plain = MailqueryError("E_LOCKED", "another run holds the lock", "retry")
        with mock.patch.object(cli_mod, "_execute", side_effect=plain):
            code, _, _ = self.run_cli(["search"])
        self.assertEqual(code, 5)
        self.assertRegex(
            self.log_text(),
            r"(?m) code=E_LOCKED message=another run holds the lock$",
        )

    def test_ut_log_04_02_error_log_has_no_private_data_with_labels_unavailable(self) -> None:
        """UT-LOG-04.02: debug log, labels unavailable, search --text error: no private data."""
        message = (
            f"cannot search {self.SUBJECT!r} from {self.ADDRESS} ({self.PERSON}) in "
            f"{self.FOLDER} of {ICLOUD_LABEL} at {self.fx.mail_root}: term {self.TERM} "
            f"uid {self.UID} snippet {self.BODY}"
        )

        def failing_search(backend, config, filters, **kwargs):
            # Labels are unavailable: resolving a label logs a warning.
            backend.labels.label_for(ACCOUNT_ICLOUD)
            backend.labels.label_for(ACCOUNT_GMAIL)
            raise MailqueryError(
                "E_SCAN_TOO_LARGE", message, f"hint {self.TERM}", log_message="the scan was too large"
            )

        missing_db = self.fx.root / "no-such-dir" / "Accounts4.sqlite"
        with mock.patch.object(cli_mod, "run_search", side_effect=failing_search):
            code, stdout, _ = self.run_cli(
                ["--log-level", "debug", "search", "--text", self.TERM],
                accounts_db=missing_db,
            )
        self.assertEqual(code, 4)
        self.assertIn(self.TERM, stdout)  # the JSON error keeps the full message
        text = self.log_text()
        self.assertIn("code=E_SCAN_TOO_LARGE message=the scan was too large", text)
        self.assertIn("DEBUG", text)  # the debug level was really active
        forbidden = {
            "subject": self.SUBJECT,
            "address": self.ADDRESS,
            "person": self.PERSON,
            "folder": self.FOLDER,
            "account label": ICLOUD_LABEL,
            "term": self.TERM,
            "uid": self.UID,
            "body": self.BODY,
            "snippet": "snippet",
            "root path": str(self.fx.root),
            "home path": str(self.fx.home),
            "mail path": str(self.fx.mail_root),
            "accounts db path": str(missing_db),
            "missing dir": "no-such-dir",
        }
        for uuid_value in (ACCOUNT_ICLOUD, ACCOUNT_GMAIL, ACCOUNT_LOCAL):
            forbidden[f"uuid {uuid_value}"] = uuid_value
        lowered = text.lower()
        for name, value in forbidden.items():
            self.assertNotIn(value.lower(), lowered, f"log leaks the {name}")

    def test_ut_log_04_03_warnings_log_number_and_codes_without_detail(self) -> None:
        """UT-LOG-04.03: warnings log their number and W_* codes, not the detail."""
        payload = {
            "messages": [],
            "warnings": [
                "W_ACCOUNT_LABELS_UNAVAILABLE: account labels are unavailable at /secret/path",
                "W_NO_ACCOUNTS: nothing declared for ana.garcia@contoso.example",
            ],
        }
        with mock.patch.object(cli_mod, "_execute", return_value=payload):
            code, _, _ = self.run_cli(["search"])
        self.assertEqual(code, 0)
        text = self.log_text()
        self.assertRegex(
            text,
            r"(?m)event=end command=search exit_code=0 .*warnings=2 "
            r"warning_codes=W_ACCOUNT_LABELS_UNAVAILABLE,W_NO_ACCOUNTS ",
        )
        self.assertNotIn("/secret/path", text)
        self.assertNotIn("ana.garcia", text)
        self.assertNotIn("nothing declared", text)

    def test_ut_log_04_04_non_internal_error_has_no_traceback(self) -> None:
        """UT-LOG-04.04: an error that is not E_INTERNAL logs no traceback."""
        error = MailqueryError("E_BAD_FILTER", "bad filter", "fix it")
        with mock.patch.object(cli_mod, "_execute", side_effect=error):
            code, _, _ = self.run_cli(["search"])
        self.assertEqual(code, 2)
        text = self.log_text()
        self.assertIn("code=E_BAD_FILTER", text)
        self.assertNotIn("Traceback", text)
        self.assertNotIn("event=internal_error", text)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


# --------------------------------------------------------------------------- #
# Structured log events: the text line of every migrated core event
# --------------------------------------------------------------------------- #

import plistlib
import threading
import time

from mailquery import store as store_mod
from mailquery.accounts import AccountLabels
from mailquery.backends import outlook_com
from tests.fakes.attachment_backend import FakeAttachmentBackend
from tests.fixtures.make_fixtures import write_config

_LOG_PREFIX = re.compile(
    r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} \S+\s+\S+ run=[0-9a-f]{12} "
)


def _event_lines(text: str) -> list[str]:
    """Return the log text without the fixed prefix of each formatted line."""
    return [_LOG_PREFIX.sub("", line) for line in text.splitlines()]


class CoreEventTextTests(unittest.TestCase):
    """Fixes the text line of every core event that goes through ``log_event``."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="mailquery-event-")
        self.addCleanup(tmp.cleanup)
        self.addCleanup(_close_log_handlers)
        self.home = Path(tmp.name)
        self.log_path = self.home / "logs" / "mailquery.log"

    def start(self, level: str = "debug") -> None:
        setup_logging(self.home, level, 10)

    def lines(self) -> list[str]:
        return _event_lines(self.log_path.read_text(encoding="utf-8"))

    def wait_for(self, fragment: str, timeout: float = 3.0) -> str:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            text = self.log_path.read_text(encoding="utf-8")
            if fragment in text:
                return text
            time.sleep(0.02)
        self.fail(f"the log never received {fragment!r}")

    def fixture(self):
        fx = build_store()
        self.addCleanup(fx.cleanup)
        return fx

    def test_core_event_store_recovered_uuid_keeps_text_line(self) -> None:
        """The store event for a version uuid recovered from disk keeps its text line."""
        fx = self.fixture()
        plist = fx.mail_root / "PersistenceInfo.plist"
        data = plistlib.loads(plist.read_bytes())
        data.pop("VersionDirectoryIdentifiers", None)
        plist.write_bytes(plistlib.dumps(data))
        self.start()
        store_mod.detect_version(fx.mail_root)
        self.assertEqual(self.lines()[-1], "recovered version uuid from disk")

    def test_core_event_store_opened_index_keeps_text_line(self) -> None:
        """The store event for an opened Envelope Index keeps its text line."""
        fx = self.fixture()
        self.start()
        store = store_mod.open_store(fx.mail_root, tmp_root=self.home / "tmp")
        store.close()
        self.assertRegex(
            self.lines()[-1], r"^opened Envelope Index strategy=(?:live_ro|copy_ro)$"
        )

    def test_core_event_account_labels_unavailable_keeps_text_line(self) -> None:
        """The accounts warning for unavailable labels keeps its text line."""
        self.start()
        AccountLabels(self.home / "absent" / "Accounts4.sqlite").label_for("X")
        self.assertEqual(self.lines()[-1], "account labels unavailable; using uuid")

    def test_core_event_account_label_missing_keeps_text_line(self) -> None:
        """The accounts warning for a visible account without label keeps its text line."""
        fx = self.fixture()
        self.start()
        AccountLabels(fx.accounts_db).label_for("00000000-0000-0000-0000-000000000000")
        self.assertEqual(self.lines()[-1], "no visible label for an account; using uuid")

    def test_core_event_outlook_watchdog_keeps_text_line_and_traceback(self) -> None:
        """The Outlook watchdog failure keeps its event line and traceback."""
        self.start()

        def failing(self, seconds):
            raise RuntimeError("watchdog failed")

        watchdog = outlook_com.Watchdog(timeout=0.01, on_expire=failing)
        watchdog.arm()
        try:
            text = self.wait_for("event=watchdog_error")
        finally:
            watchdog.disarm()
        self.assertIn("ERROR mailquery.outlook", text)
        self.assertIn("event=watchdog_error\nTraceback (most recent call last):", text)

    def test_core_event_cli_start_keeps_text_line(self) -> None:
        """The CLI ``event=start`` line keeps its fields and order."""
        fx = self.fixture()
        with mock.patch.object(cli_mod, "_execute", return_value={"messages": []}):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                cli_mod.main(["search"], home=fx.home, mail_root=fx.mail_root)
        log = _event_lines(
            (fx.home / "logs" / "mailquery.log").read_text(encoding="utf-8")
        )
        self.assertIn(
            "event=start command=search backend=apple_mail drivers=apple_mail", log
        )

    def test_core_event_cli_end_keeps_text_line(self) -> None:
        """The CLI ``event=end`` line keeps its fields and order."""
        fx = self.fixture()
        with mock.patch.object(cli_mod, "_execute", return_value={"messages": []}):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                cli_mod.main(["search"], home=fx.home, mail_root=fx.mail_root)
        line = next(
            line
            for line in _event_lines(
                (fx.home / "logs" / "mailquery.log").read_text(encoding="utf-8")
            )
            if line.startswith("event=end command=search")
        )
        self.assertRegex(
            line,
            r"^event=end command=search exit_code=0 count=0 truncated=False "
            r"warnings=0 warning_codes=- mode=- candidates=- messages_read=- "
            r"duration_ms=\d+$",
        )

    def test_core_event_cli_store_connection_keeps_text_line(self) -> None:
        """The store connection line keeps its fields and order."""
        fx = self.fixture()
        with mock.patch.object(cli_mod, "_execute", return_value={"messages": []}):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                cli_mod.main(["search"], home=fx.home, mail_root=fx.mail_root)
        line = next(
            line
            for line in _event_lines(
                (fx.home / "logs" / "mailquery.log").read_text(encoding="utf-8")
            )
            if line.startswith("strategy=")
        )
        self.assertRegex(
            line, r"^strategy=(?:live_ro|copy_ro) version=V10 schema_ok=true$"
        )

    def test_core_event_cli_internal_error_keeps_text_line_and_traceback(self) -> None:
        """An unexpected exception keeps its ``event=internal_error`` line and traceback."""
        fx = self.fixture()
        with mock.patch.object(cli_mod, "_execute", side_effect=RuntimeError("boom")):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                cli_mod.main(["search"], home=fx.home, mail_root=fx.mail_root)
        text = (fx.home / "logs" / "mailquery.log").read_text(encoding="utf-8")
        self.assertIn(
            "event=internal_error command=search\nTraceback (most recent call last):",
            text,
        )

    def test_core_event_cli_error_keeps_text_line(self) -> None:
        """A handled error keeps its ``event=error`` line without a traceback."""
        self.start()
        error = MailqueryError("E_BAD_FILTER", "bad filter detail", "fix it")
        cli_mod._log_error(get_logger("mailquery.cli"), "search", error)
        self.assertEqual(
            self.lines()[-1],
            "event=error command=search code=E_BAD_FILTER message=bad filter detail",
        )

    def test_core_event_cli_internal_error_traceback_keeps_text(self) -> None:
        """An ``E_INTERNAL`` carries its traceback block on the text line."""
        self.start()
        try:
            raise MailqueryError("E_INTERNAL", "boom message", "hint")
        except MailqueryError as exc:
            cli_mod._log_error(get_logger("mailquery.cli"), "search", exc)
        text = self.log_path.read_text(encoding="utf-8")
        self.assertIn(
            "event=error command=search code=E_INTERNAL message=boom message\n"
            "Traceback (most recent call last):",
            text,
        )
        self.assertIn("mailquery.errors.MailqueryError", text)

    def test_core_event_cli_doctor_end_keeps_text_line(self) -> None:
        """The doctor ``event=end`` line keeps ``checks=<passed>/<total>``."""
        self.start()
        cli_mod._emit_doctor_report(
            [], [], True, get_logger("mailquery.cli"), "Apple Mail"
        )
        self.assertEqual(
            self.lines()[-1], "event=end command=doctor exit_code=0 checks=0/0"
        )

    def test_core_event_cli_attachment_end_keeps_text_line(self) -> None:
        """The attachment ``event=end`` line keeps its counters."""
        fx = self.fixture()
        write_config(fx.home, '[scope."apple_mail:iCloud (attachment@fixture.example)"]\n')
        backend = FakeAttachmentBackend()
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            code = cli_mod.main(
                ["attachment", str(backend.native_uid), "--index", "1"],
                home=fx.home,
                backend=backend,
            )
        self.assertEqual(code, 0)
        line = next(
            line
            for line in _event_lines(
                (fx.home / "logs" / "mailquery.log").read_text(encoding="utf-8")
            )
            if line.startswith("event=end command=attachment")
        )
        self.assertRegex(
            line,
            r"^event=end command=attachment exit_code=0 count=1 cached=0 "
            r"bytes=\d+ duration_ms=\d+$",
        )


class StructuredSetupEventTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="mailquery-setup-event-")
        self.addCleanup(tmp.cleanup)
        self.addCleanup(_close_log_handlers)
        self.home = Path(tmp.name)

    def test_setup_logging_debug_event_keeps_its_text_line(self) -> None:
        """The debug ``logging initialized`` event keeps its text line and run id."""
        setup_logging(self.home, "debug", 10)
        text = (self.home / "logs" / "mailquery.log").read_text(encoding="utf-8")
        self.assertRegex(
            text,
            r"(?m)^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} DEBUG "
            r"mailquery run=[0-9a-f]{12} logging initialized level=debug "
            r"max_size_mb=10$",
        )

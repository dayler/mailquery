"""End-to-end integration tests for the JSON contract (PRD §12, §17, §18, §20).

Every test drives the real CLI (``mailquery.cli.main``) against the synthetic
Apple Mail store built by ``tests/fixtures/make_fixtures.py`` with the documented
``home``/``mail_root``/``accounts_db`` injection points. The assertions pin the
contract from ``docs/INTERFACES.md`` §4-§6: command payload shapes, dedupe with
``duplicate_count`` and INBOX priority, snippets, recalculated mailbox counters,
the ``new`` cursor (first-run baseline, seeded run, ``--peek``), ``show`` for
text/partial/missing/corrupt ``.emlx`` and the error JSON / exit-code dictionary.

Stable normalized payloads are compared against goldens in
``tests/fixtures/expected/`` (``MAILQUERY_UPDATE_GOLDENS=1`` regenerates them).
"""

from __future__ import annotations

import contextlib
import io
import json
import logging
import os
import re
import sqlite3
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

from mailquery import cli
from mailquery.backends.apple_mail import AppleMailBackend
from mailquery.state import StateStore
from tests.fixtures.make_fixtures import (
    ACCOUNT_GMAIL,
    ACCOUNT_ICLOUD,
    ACCOUNT_LOCAL,
    DEFAULT_CONFIG,
    GMAIL_LABEL,
    ICLOUD_LABEL,
    LOCAL_LABEL,
    MAILBOX_ICLOUD_INBOX,
    build_store,
    write_config,
    write_state,
)

EXPECTED_DIR = Path(__file__).resolve().parent / "fixtures" / "expected"

ISO_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}")
EMAIL_DATE_RE = re.compile(
    r"[A-Z][a-z]{2}, \d{1,2} [A-Z][a-z]{2} \d{4} \d{2}:\d{2}:\d{2} [+-]\d{4}"
)
ISO_EXACT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$")

# Default config scope (iCloud INBOX + Facturas + Archivo, Gmail INBOX, local
# account with no folders): 12 distinct global messages ordered by
# (date_received DESC, ROWID DESC).
DEFAULT_UID_ORDER = [
    83170,
    83160,
    83150,
    83143,
    83210,
    2714,
    83220,
    83200,
    79658,
    83180,
    830,
    83190,
]

MESSAGE_FIELDS = {
    "uid",
    "message_id",
    "duplicate_count",
    "subject",
    "from",
    "to",
    "cc",
    "date_sent",
    "date_received",
    "mailbox",
    "is_read",
    "is_flagged",
    "has_attachments",
    "size_bytes",
    "snippet",
    "body",
}
BODY_FIELDS = {"available", "readable", "partial", "truncated"}
MAILBOX_FIELDS = {"account", "name", "path", "url"}
ACCOUNT_FIELDS = {"uuid", "label", "email"}

ICLOUD_ONLY_CONFIG = f'[scope."{ICLOUD_LABEL}"]\n'
ICLOUD_FACTURAS_CONFIG = f'[scope."{ICLOUD_LABEL}"]\nmailbox_list = ["Facturas"]\n'
ALL_MAIL_CONFIG = (
    f'[scope."{ICLOUD_LABEL}"]\nmailbox_list = ["Facturas", "Archivo"]\n\n'
    f'[scope."{GMAIL_LABEL}"]\nmailbox_list = ["[Gmail]/All Mail"]\n\n'
    f'[scope."{LOCAL_LABEL}"]\n'
)
TOO_LARGE_CONFIG = (
    "[search]\nmax_scan = 100\n\n"
    f'[scope."{ICLOUD_LABEL}"]\nmailbox_list = ["Facturas"]\n'
)
NO_ACCOUNTS_CONFIG = "[logging]\nlevel = \"warning\"\n"
BROKEN_CONFIG = "[search]\nnot_a_key = 1\n"


def _normalize(value: object, root: Path) -> object:
    """Replace run-dependent values so payloads can be compared to goldens."""
    if isinstance(value, dict):
        if value.get("name") == "python" and "detail" in value:
            value = {**value, "detail": "<PYTHON>"}
        if value.get("name") == "home" and "detail" in value:
            value = {**value, "detail": "<HOME>"}
        return {
            key: _normalize(item, root)
            for key, item in value.items()
            if key not in ("generated_at", "duration_ms")
        }
    if isinstance(value, list):
        return [_normalize(item, root) for item in value]
    if isinstance(value, str):
        text = ISO_RE.sub("<ISO>", value)
        text = EMAIL_DATE_RE.sub("<EMAIL_DATE>", text)
        text = text.replace(str(root), "<ROOT>")
        # Goldens use "/" on every OS: normalize separators after the root swap.
        return text.replace("\\", "/")
    if isinstance(value, int) and not isinstance(value, bool) and abs(value) >= 1_000_000_000:
        return "<EPOCH>"
    return value


def _assert_golden(case: unittest.TestCase, name: str, payload: dict, root: Path) -> None:
    """Compare a normalized payload with ``EXPECTED_DIR / name`` (or rewrite it)."""
    normalized = _normalize(payload, root)
    path = EXPECTED_DIR / name
    if os.environ.get("MAILQUERY_UPDATE_GOLDENS") == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(normalized, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return
    case.assertTrue(
        path.is_file(),
        f"missing golden {path}; run with MAILQUERY_UPDATE_GOLDENS=1",
    )
    expected = json.loads(path.read_text(encoding="utf-8"))
    case.assertEqual(normalized, expected, f"golden mismatch: {path.name}")


def _close_log_handlers() -> None:
    """Release the log file ``cli.main`` leaves open (Windows cannot delete it)."""
    logger = logging.getLogger("mailquery")
    for handler in list(logger.handlers):
        if isinstance(handler, logging.FileHandler):
            logger.removeHandler(handler)
            handler.close()


@contextlib.contextmanager
def _closing_log_handlers():
    try:
        yield
    finally:
        _close_log_handlers()


def _insert_candidate_messages(fx, count: int = 130) -> None:
    """Add ``count`` recent INBOX rows to the fixture (enough to exceed max_scan)."""
    connection = sqlite3.connect(fx.envelope_index)
    try:
        subject_id = connection.execute(
            "INSERT INTO subjects (subject) VALUES ('Bulk candidate')"
        ).lastrowid
        sender_id = connection.execute(
            "INSERT INTO addresses (address, comment) VALUES ('bulk@fixture.example', 'Bulk')"
        ).lastrowid
        base = int(fx.now.timestamp())
        for index in range(count):
            uid = 90_000 + index
            global_id = 50_000 + index
            message_id = 300_000 + index
            received = base - index
            connection.execute(
                "INSERT INTO message_global_data (ROWID, message_id, message_id_header) "
                "VALUES (?, ?, NULL)",
                (global_id, message_id),
            )
            connection.execute(
                "INSERT INTO messages (ROWID, message_id, global_message_id, sender, "
                "subject, date_sent, date_received, mailbox, flags, read, flagged, "
                "deleted, size) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, 512)",
                (
                    uid,
                    message_id,
                    global_id,
                    sender_id,
                    subject_id,
                    received - 30,
                    received,
                    MAILBOX_ICLOUD_INBOX,
                ),
            )
        connection.commit()
    finally:
        connection.close()


class IntegrationBase(unittest.TestCase):
    """Build one fixture store per test and drive ``cli.main`` with its paths."""

    config_text = DEFAULT_CONFIG

    def setUp(self) -> None:
        self.fx = build_store()
        self.addCleanup(self.fx.cleanup)
        self.addCleanup(_close_log_handlers)
        if self.config_text is not None:
            write_config(self.fx.home, self.config_text)

    # -- CLI helpers ------------------------------------------------------ #

    def configure(self, content: str) -> None:
        write_config(self.fx.home, content)

    def run_cli(
        self,
        *args: str,
        home: Path | None = None,
        mail_root: Path | None = None,
        accounts_db: Path | None = None,
    ) -> tuple[int, dict | None, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = cli.main(
                list(args),
                home=self.fx.home if home is None else home,
                mail_root=self.fx.mail_root if mail_root is None else mail_root,
                accounts_db=self.fx.accounts_db if accounts_db is None else accounts_db,
            )
        raw = stdout.getvalue()
        payload = json.loads(raw) if raw.strip() else None
        return code, payload, stderr.getvalue()

    def run_ok(self, *args: str, **kwargs) -> dict:
        code, payload, stderr = self.run_cli(*args, **kwargs)
        self.assertEqual(code, 0, f"command {args} failed: stdout={payload} stderr={stderr}")
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertIs(payload.get("ok"), True, payload)
        self.assertIsInstance(payload.get("generated_at"), str)
        self.assertRegex(payload["generated_at"], ISO_EXACT_RE)
        self.assertIsInstance(payload.get("warnings"), list)
        return payload

    def run_error(
        self,
        *args: str,
        expected_exit: int,
        expected_code: str | None = None,
        **kwargs,
    ) -> dict:
        code, payload, stderr = self.run_cli(*args, **kwargs)
        self.assertEqual(code, expected_exit, f"unexpected exit for {args}: {payload} {stderr}")
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(set(payload), {"ok", "command", "error"}, payload)
        self.assertIs(payload["ok"], False)
        # Error contract: no generated_at (PRD 12.5).
        self.assertNotIn("generated_at", payload)
        error = payload["error"]
        self.assertEqual(set(error), {"code", "message", "hint"})
        self.assertIsInstance(error["code"], str)
        self.assertTrue(error["code"].startswith("E_"))
        self.assertIsInstance(error["message"], str)
        self.assertIsInstance(error["hint"], str)
        self.assertTrue(error["hint"], f"error {error['code']} must carry an actionable hint")
        self.assertTrue(stderr.strip(), "errors also print a human summary on stderr")
        if expected_code is not None:
            self.assertEqual(error["code"], expected_code)
        return payload

    # -- contract helpers ------------------------------------------------- #

    def message_by_uid(self, payload: dict, uid: int) -> dict:
        for message in payload["messages"]:
            if message["uid"] == uid:
                return message
        self.fail(f"uid {uid} not present in {payload['count']} results")

    def assert_message_shape(self, message: dict) -> None:
        self.assertTrue(MESSAGE_FIELDS <= set(message), MESSAGE_FIELDS - set(message))
        self.assertIsInstance(message["uid"], int)
        self.assertIsInstance(message["message_id"], str)
        self.assertIsInstance(message["duplicate_count"], int)
        self.assertGreaterEqual(message["duplicate_count"], 1)
        self.assertIsInstance(message["subject"], str)
        for field in ("from", "to", "cc"):
            self.assertIsInstance(message[field], list if field != "from" else dict)
        self.assertIsInstance(message["from"].get("name"), str)
        self.assertIsInstance(message["from"].get("address"), str)
        for recipient in message["to"] + message["cc"]:
            self.assertEqual(set(recipient), {"name", "address"})
        for field in ("date_sent", "date_received"):
            if message[field] is not None:
                self.assertRegex(message[field], ISO_EXACT_RE)
        self.assertTrue(MAILBOX_FIELDS <= set(message["mailbox"]))
        self.assertEqual(set(message["mailbox"]["account"]), ACCOUNT_FIELDS)
        self.assertIsInstance(message["mailbox"]["account"]["uuid"], str)
        self.assertIsInstance(message["mailbox"]["account"]["label"], str)
        for field in ("is_read", "is_flagged", "has_attachments"):
            self.assertIsInstance(message[field], bool)
        self.assertIsInstance(message["size_bytes"], int)
        self.assertIsInstance(message["snippet"], str)
        self.assertLessEqual(len(message["snippet"]), 200)
        self.assertNotIn("\n", message["snippet"])
        self.assertTrue(BODY_FIELDS <= set(message["body"]))
        for field in BODY_FIELDS:
            self.assertIsInstance(message["body"][field], bool)

    def assert_warning(self, payload: dict, prefix: str) -> str:
        for warning in payload["warnings"]:
            if warning.startswith(prefix):
                return warning
        self.fail(f"warning {prefix} not found in {payload['warnings']}")

    # -- goldens ---------------------------------------------------------- #

    def assert_golden(self, name: str, payload: dict) -> None:
        _assert_golden(self, name, payload, self.fx.root)


# --------------------------------------------------------------------------- #
# doctor / mailboxes
# --------------------------------------------------------------------------- #


class DoctorTest(IntegrationBase):
    def test_tc_01_01_doctor_reports_all_documented_checks(self) -> None:
        """TC-01.01: doctor reports every documented check (golden)."""
        payload = self.run_ok("doctor", "--json")
        self.assertEqual(payload["command"], "doctor")
        checks = payload["checks"]
        self.assertIsInstance(checks, list)
        self.assertTrue(checks)
        names = [check["name"] for check in checks]
        for required in (
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
        ):
            self.assertIn(required, names)
        for check in checks:
            self.assertTrue({"name", "ok", "detail"} <= set(check))
            self.assertIsInstance(check["ok"], bool)
            self.assertIsInstance(check["detail"], str)
        by_name = {check["name"]: check for check in checks}
        for name in names:
            self.assertTrue(by_name[name]["ok"], f"healthy fixture check failed: {by_name[name]}")
        self.assert_golden("doctor.json", payload)

    def test_doctor_default_output_is_human_readable(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = cli.main(
                ["doctor"],
                home=self.fx.home,
                mail_root=self.fx.mail_root,
                accounts_db=self.fx.accounts_db,
            )
        text = stdout.getvalue()
        self.assertEqual(code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertFalse(text.lstrip().startswith("{"), "doctor must print text by default")
        self.assertIn("mailquery doctor - environment and read-only preflight", text)
        self.assertIn("Checks:", text)
        self.assertIn("[ok]", text)
        self.assertIn("Result: 11/11 checks passed", text)
        self.assertIn("mailquery doctor --json", text)
        self.assertNotIn('"checks"', text)


class MailboxesTest(IntegrationBase):
    def test_tc_01_02_mailboxes_accounts_counters_and_included_flags(self) -> None:
        """TC-01.02: mailboxes, accounts, counters and included flags (golden)."""
        payload = self.run_ok("mailboxes")
        self.assertEqual(payload["command"], "mailboxes")
        self.assertTrue({"accounts", "mailboxes"} <= set(payload))

        accounts = {account["uuid"]: account for account in payload["accounts"]}
        self.assertEqual(set(accounts), {ACCOUNT_ICLOUD, ACCOUNT_GMAIL, ACCOUNT_LOCAL})
        self.assertEqual(accounts[ACCOUNT_ICLOUD]["label"], ICLOUD_LABEL)
        self.assertEqual(accounts[ACCOUNT_ICLOUD]["email"], "fixture@icloud.com")
        self.assertEqual(accounts[ACCOUNT_GMAIL]["label"], GMAIL_LABEL)
        self.assertEqual(accounts[ACCOUNT_GMAIL]["email"], "fixture@gmail.com")
        self.assertEqual(accounts[ACCOUNT_LOCAL]["label"], LOCAL_LABEL)
        for account in accounts.values():
            self.assertTrue(ACCOUNT_FIELDS | {"declared"} <= set(account))
            self.assertIs(account["declared"], True)

        mailboxes = payload["mailboxes"]
        self.assertTrue(mailboxes)
        by_key = {(entry["account"]["uuid"], entry["path"]): entry for entry in mailboxes}
        for entry in mailboxes:
            self.assertTrue(MAILBOX_FIELDS | {"total", "unread", "included"} <= set(entry))
            self.assertIsInstance(entry["total"], int)
            self.assertIsInstance(entry["unread"], int)
            self.assertIsInstance(entry["included"], bool)

        icloud_inbox = by_key[(ACCOUNT_ICLOUD, "INBOX")]
        self.assertEqual(icloud_inbox["name"], "INBOX")
        self.assertEqual((icloud_inbox["total"], icloud_inbox["unread"]), (8, 3))
        self.assertIs(icloud_inbox["included"], True)

        gmail_inbox = by_key[(ACCOUNT_GMAIL, "INBOX")]
        self.assertEqual((gmail_inbox["total"], gmail_inbox["unread"]), (2, 1))
        self.assertIs(gmail_inbox["included"], True)

        self.assertEqual(by_key[(ACCOUNT_GMAIL, "[Gmail]/All Mail")]["total"], 3)
        self.assertIs(by_key[(ACCOUNT_GMAIL, "[Gmail]/All Mail")]["included"], False)
        self.assertIs(by_key[(ACCOUNT_GMAIL, "[Gmail]/Important")]["included"], False)
        self.assertIs(by_key[(ACCOUNT_ICLOUD, "Facturas")]["included"], True)
        self.assertIs(by_key[(ACCOUNT_ICLOUD, "Archivo")]["included"], True)
        self.assertIs(by_key[(ACCOUNT_LOCAL, "Recovered Messages")]["included"], False)
        self.assert_golden("mailboxes.json", payload)


# --------------------------------------------------------------------------- #
# search
# --------------------------------------------------------------------------- #


class SearchTest(IntegrationBase):
    def test_tc_01_03_search_default_returns_all_distinct_messages(self) -> None:
        """TC-01.03: default search returns all distinct messages (golden)."""
        payload = self.run_ok("search")
        self.assertEqual(payload["command"], "search")
        self.assertTrue({"count", "truncated", "messages", "scan"} <= set(payload))
        self.assertEqual(payload["count"], 12)
        self.assertIs(payload["truncated"], False)
        self.assertEqual([message["uid"] for message in payload["messages"]], DEFAULT_UID_ORDER)
        for message in payload["messages"]:
            self.assert_message_shape(message)
        # Dates are non-increasing in the output.
        received = [message["date_received"] for message in payload["messages"]]
        self.assertEqual(received, sorted(received, reverse=True))

        invoice = self.message_by_uid(payload, 2714)
        self.assertEqual(invoice["subject"], "Invoice 2026-10")
        self.assertEqual(invoice["from"], {"name": "Billing Team", "address": "billing@fixture.example"})
        self.assertEqual(invoice["to"], [{"name": "Fixture User", "address": "me@fixture.example"}])
        self.assertEqual(invoice["cc"], [{"name": "Finance", "address": "finance@fixture.example"}])
        self.assertEqual(invoice["mailbox"]["account"]["uuid"], ACCOUNT_ICLOUD)
        self.assertEqual(invoice["mailbox"]["account"]["label"], ICLOUD_LABEL)
        self.assertEqual(invoice["mailbox"]["account"]["email"], "fixture@icloud.com")
        self.assertEqual(invoice["mailbox"]["name"], "INBOX")
        self.assertEqual(invoice["mailbox"]["path"], "INBOX")
        self.assertEqual(invoice["mailbox"]["url"], f"imap://{ACCOUNT_ICLOUD}/INBOX")
        self.assertIs(invoice["is_read"], False)
        self.assertIs(invoice["is_flagged"], False)
        self.assertIs(invoice["has_attachments"], True)
        self.assertEqual(invoice["size_bytes"], 123456)
        self.assertEqual(invoice["snippet"], "Please find the invoice attached.")
        self.assertEqual(
            invoice["body"],
            {"available": True, "readable": True, "partial": False, "truncated": False},
        )
        self.assertEqual(invoice["duplicate_count"], 1)
        self.assertEqual(invoice["message_id"], "<invoice-2714@fixture.example>")

        partial = self.message_by_uid(payload, 79658)
        self.assertIs(partial["body"]["partial"], True)
        self.assertEqual(partial["mailbox"]["path"], "Facturas")
        self.assertEqual(partial["snippet"], "Adjuntamos la factura de septiembre.")
        self.assertIs(partial["has_attachments"], True)

        flagged = self.message_by_uid(payload, 83150)
        self.assertIs(flagged["is_flagged"], True)
        self.assertIs(flagged["is_read"], False)
        self.assertEqual(flagged["snippet"], "Remember this.")

        gmail = self.message_by_uid(payload, 83210)
        self.assertIs(gmail["is_read"], False)
        self.assertIs(gmail["has_attachments"], True)
        self.assertEqual(gmail["mailbox"]["account"]["uuid"], ACCOUNT_GMAIL)
        self.assertEqual(gmail["mailbox"]["path"], "INBOX")
        self.assertEqual(gmail["snippet"], "Photo attached.")

        missing = self.message_by_uid(payload, 83170)
        self.assertIs(missing["body"]["available"], False)
        self.assertEqual(missing["snippet"], "")
        self.assert_warning(payload, "W_EMLX_MISSING")

        corrupt = self.message_by_uid(payload, 83180)
        self.assertEqual(corrupt["snippet"], "")
        self.assert_warning(payload, "W_EMLX_")

        html_only = self.message_by_uid(payload, 83200)
        self.assertIn("HTML only", html_only["snippet"])
        self.assertIn("no plain text part", html_only["snippet"])

        no_header = self.message_by_uid(payload, 83220)
        self.assertEqual(no_header["message_id"], "")

        scan = payload["scan"]
        self.assertEqual(scan["mode"], "metadata")
        self.assertIsInstance(scan["candidates"], int)
        self.assertEqual(scan["candidates"], 12)
        self.assertIsInstance(scan["messages_read"], int)
        self.assertIsInstance(scan["duration_ms"], int)
        self.assert_golden("search_default.json", payload)

    def test_tc_01_04_search_with_all_mail_dedupes_to_inbox_canonical(self) -> None:
        """TC-01.04: All Mail search dedupes to the INBOX canonical (golden)."""
        self.configure(ALL_MAIL_CONFIG)
        payload = self.run_ok("search")
        self.assertEqual(payload["count"], 12)
        self.assertEqual([message["uid"] for message in payload["messages"]], DEFAULT_UID_ORDER)
        self.assertNotIn(83142, [message["uid"] for message in payload["messages"]])

        duplicate = self.message_by_uid(payload, 83143)
        self.assertEqual(duplicate["duplicate_count"], 2)
        self.assertEqual(duplicate["subject"], "Shared duplicate")
        self.assertEqual(duplicate["message_id"], "<duplicate-4@fixture.example>")
        self.assertEqual(duplicate["mailbox"]["path"], "INBOX")
        self.assertEqual(duplicate["snippet"], "Duplicate body from the inbox.")
        for message in payload["messages"]:
            if message["uid"] != 83143:
                self.assertEqual(message["duplicate_count"], 1, message["uid"])
        self.assert_golden("search_all_mail.json", payload)

    def test_search_text_bounded_by_since(self) -> None:
        self.configure(ICLOUD_ONLY_CONFIG)
        payload = self.run_ok("search", "--text", "invoice", "--since", "30d")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["messages"][0]["uid"], 2714)
        self.assertEqual(payload["messages"][0]["snippet"], "Please find the invoice attached.")
        self.assertEqual(payload["scan"]["mode"], "text")
        self.assertEqual(payload["scan"]["candidates"], 6)

    def test_search_text_bounded_by_config_extra_mailbox(self) -> None:
        payload = self.run_ok("search", "--text", "factura")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["messages"][0]["uid"], 79658)
        self.assertEqual(payload["messages"][0]["snippet"], "Adjuntamos la factura de septiembre.")

    def test_search_text_bounded_by_include_mailbox(self) -> None:
        self.configure(ICLOUD_ONLY_CONFIG)
        payload = self.run_ok("search", "--text", "factura", "--include-mailbox", "Facturas")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["messages"][0]["uid"], 79658)

    def test_search_text_unbounded_is_rejected(self) -> None:
        self.configure(ICLOUD_ONLY_CONFIG)
        error = self.run_error(
            "search", "--text", "invoice", expected_exit=4, expected_code="E_UNBOUNDED_SCAN"
        )
        self.assertEqual(error["command"], "search")
        self.run_ok("search", "--text", "invoice", "--since", "1d")

    def test_search_text_scan_too_large_is_rejected(self) -> None:
        _insert_candidate_messages(self.fx, count=130)
        self.configure(TOO_LARGE_CONFIG)
        self.run_error("search", "--text", "anything", expected_exit=4, expected_code="E_SCAN_TOO_LARGE")

    def test_search_limit_truncates(self) -> None:
        payload = self.run_ok("search", "--limit", "3")
        self.assertEqual(payload["count"], 3)
        self.assertIs(payload["truncated"], True)
        self.assertEqual([message["uid"] for message in payload["messages"]], DEFAULT_UID_ORDER[:3])
        self.assertIn("hint", payload)

    def test_search_without_declared_accounts_warns(self) -> None:
        self.configure(NO_ACCOUNTS_CONFIG)
        payload = self.run_ok("search")
        self.assertEqual(payload["count"], 0)
        self.assertEqual(payload["messages"], [])
        self.assert_warning(payload, "W_NO_ACCOUNTS")


# --------------------------------------------------------------------------- #
# new (cursor)
# --------------------------------------------------------------------------- #


class NewTest(IntegrationBase):
    def _seed_cursor(self, hours: int = 2) -> dict:
        cursor = {
            "last_date_received": int((self.fx.now - timedelta(hours=hours)).timestamp()),
            "last_uid": 1,
            "lookback_seconds": 600,
        }
        write_state(
            self.fx.home,
            {
                "schema": 1,
                "updated_at": "",
                "last_run": None,
                "cursor": cursor,
                "emitted_uids": [],
            },
        )
        return cursor

    def test_tc_01_05_first_run_emits_the_lookback_window(self) -> None:
        """TC-01.05: first run of ``new`` emits the [D - lookback, D] window (golden)."""
        self.assertFalse(StateStore(self.fx.home, AppleMailBackend.check_state_uid).path.exists())
        payload = self.run_ok("new")
        self.assertEqual(payload["command"], "new")
        self.assertEqual(payload["count"], 2)
        self.assertEqual(
            [message["uid"] for message in payload["messages"]], [83160, 83170]
        )
        for message in payload["messages"]:
            self.assert_message_shape(message)
        self.assertEqual(
            payload["warnings"][-1],
            "W_FIRST_RUN: first run: emitted the messages received in the last "
            "10min before the newest message",
        )

        expected_date = int((self.fx.now - timedelta(minutes=15)).timestamp())
        cursor = payload["cursor"]
        self.assertIsNone(cursor["previous"])
        self.assertEqual(cursor["current"]["last_uid"], 83170)
        self.assertEqual(cursor["current"]["last_date_received"], expected_date)
        self.assertEqual(cursor["current"]["lookback_seconds"], 600)

        state = StateStore(self.fx.home, AppleMailBackend.check_state_uid).load()
        self.assertIsNotNone(state.cursor)
        assert state.cursor is not None
        self.assertEqual(state.cursor.last_uid, 83170)
        self.assertEqual(state.cursor.last_date_received, expected_date)
        self.assertEqual(state.emitted_uids, (83160, 83170))
        self.assertEqual(state.last_run.command, "new")
        self.assert_golden("new_first_run.json", payload)

        # The window was emitted once: the next run has nothing new.
        self.assertEqual(self.run_ok("new")["count"], 0)

    def test_tc_01_06_seeded_run_emits_new_messages_and_advances_cursor(self) -> None:
        """TC-01.06: a seeded run emits the new messages (golden)."""
        seeded = self._seed_cursor()
        payload = self.run_ok("new")
        self.assertEqual(payload["count"], 4)
        self.assertEqual(
            [message["uid"] for message in payload["messages"]],
            [83143, 83150, 83160, 83170],
        )
        self.assertIs(payload["truncated"], False)
        for message in payload["messages"]:
            self.assert_message_shape(message)
        cursor = payload["cursor"]
        self.assertEqual(cursor["previous"], seeded)
        self.assertEqual(cursor["current"]["last_uid"], 83170)
        self.assertEqual(
            cursor["current"]["last_date_received"],
            int((self.fx.now - timedelta(minutes=15)).timestamp()),
        )
        self.assertEqual(cursor["current"]["lookback_seconds"], 600)

        state = StateStore(self.fx.home, AppleMailBackend.check_state_uid).load()
        assert state.cursor is not None
        self.assertEqual(state.cursor.last_uid, 83170)
        self.assertEqual(set(state.emitted_uids), {83143, 83150, 83160, 83170})
        self.assertEqual(state.last_run.command, "new")

        again = self.run_ok("new")
        self.assertEqual(again["count"], 0)
        self.assertEqual(again["messages"], [])
        self.assert_golden("new_seeded.json", payload)

    def test_peek_does_not_advance_the_cursor(self) -> None:
        self._seed_cursor()
        peeked = self.run_ok("new", "--peek")
        self.assertEqual(peeked["count"], 4)
        self.assertEqual(
            [message["uid"] for message in peeked["messages"]],
            [83143, 83150, 83160, 83170],
        )
        state = StateStore(self.fx.home, AppleMailBackend.check_state_uid).load()
        assert state.cursor is not None
        self.assertEqual(state.cursor.last_uid, 1)
        self.assertEqual(state.emitted_uids, ())

        # A real run after the peek still emits the same window.
        emitted = self.run_ok("new")
        self.assertEqual({message["uid"] for message in emitted["messages"]}, {83143, 83150, 83160, 83170})
        # And then there is nothing left.
        self.assertEqual(self.run_ok("new")["count"], 0)
        self.assertEqual(self.run_ok("new", "--peek")["count"], 0)


# --------------------------------------------------------------------------- #
# show
# --------------------------------------------------------------------------- #


class ShowTest(IntegrationBase):
    def test_tc_01_07_show_text_message_with_attachment(self) -> None:
        """TC-01.07: show of a text message with attachment (golden)."""
        payload = self.run_ok("show", "2714")
        self.assertEqual(payload["command"], "show")
        message = payload["message"]
        self.assertEqual(message["uid"], 2714)
        self.assertEqual(message["message_id"], "<invoice-2714@fixture.example>")
        self.assertEqual(message["subject"], "Invoice 2026-10")
        self.assertEqual(message["from"], {"name": "Billing Team", "address": "billing@fixture.example"})
        self.assertEqual(message["to"], [{"name": "Fixture User", "address": "me@fixture.example"}])
        self.assertEqual(message["cc"], [{"name": "Finance", "address": "finance@fixture.example"}])
        self.assertRegex(message["date_sent"], ISO_EXACT_RE)
        self.assertRegex(message["date_received"], ISO_EXACT_RE)
        self.assertEqual(message["mailbox"]["path"], "INBOX")
        self.assertIs(message["is_read"], False)
        self.assertIs(message["is_flagged"], False)
        self.assertIs(message["has_attachments"], True)
        self.assertEqual(message["size_bytes"], 123456)
        self.assertTrue({"From", "To", "Cc", "Subject", "Date", "Message-ID"} <= set(message["headers"]))
        self.assertEqual(message["headers"]["Subject"], "Invoice 2026-10")
        self.assertIn("billing@fixture.example", message["headers"]["From"])
        self.assertEqual(message["body_text"], "Please find the invoice attached.")
        self.assertIs(message["body_truncated"], False)
        self.assertEqual(message["attachments"], [{"name": "invoice-2026-10.pdf"}])
        self.assertIs(message["partial"], False)
        self.assertIs(message["readable"], True)
        self.assertIs(message["source"]["partial"], False)
        self.assertEqual(Path(message["source"]["emlx_path"]).name, "2714.emlx")
        self.assert_golden("show_2714.json", payload)

    def test_tc_01_08_show_missing_emlx(self) -> None:
        """TC-01.08: show with a missing .emlx (golden)."""
        payload = self.run_ok("show", "83170")
        message = payload["message"]
        self.assertEqual(message["uid"], 83170)
        self.assertIs(message["body_text"], "")
        self.assertIs(message["body_truncated"], False)
        self.assertEqual(message["attachments"], [])
        self.assertIs(message["readable"], False)
        self.assertIs(message["partial"], False)
        self.assertIn(message["source"]["emlx_path"], (None, ""))
        self.assert_warning(payload, "W_EMLX_MISSING")
        self.assert_golden("show_83170.json", payload)

    def test_tc_01_09_show_corrupt_emlx(self) -> None:
        """TC-01.09: show with a corrupt .emlx (golden)."""
        payload = self.run_ok("show", "83180")
        message = payload["message"]
        self.assertEqual(message["uid"], 83180)
        self.assertIs(message["body_text"], "")
        self.assertIs(message["readable"], False)
        self.assert_warning(payload, "W_EMLX_")
        self.assert_golden("show_83180.json", payload)

    def test_show_partial_emlx(self) -> None:
        payload = self.run_ok("show", "79658")
        message = payload["message"]
        self.assertEqual(message["uid"], 79658)
        self.assertIs(message["partial"], True)
        self.assertIs(message["source"]["partial"], True)
        self.assertIs(message["readable"], True)
        self.assertIn("Adjuntamos la factura de septiembre.", message["body_text"])
        self.assertEqual([attachment["name"] for attachment in message["attachments"]], ["factura-79658.pdf"])


class ExtendedGoldenTest(IntegrationBase):
    """Goldens that need the extended fixture store (only ``setUp`` differs)."""

    def setUp(self) -> None:
        self.fx = build_store(extended=True)
        self.addCleanup(self.fx.cleanup)
        self.addCleanup(_close_log_handlers)
        write_config(self.fx.home, self.config_text)

    def test_tc_01_10_show_smime_encrypted(self) -> None:
        """TC-01.10: show of the encrypted S/MIME message with attachment rows (golden)."""
        payload = self.run_ok("show", "90110")
        message = payload["message"]
        self.assertEqual(message["uid"], 90110)
        self.assertIs(message["has_attachments"], True)
        self.assert_golden("show_smime_encrypted.json", payload)

    def test_tc_01_11_show_not_in_scope_error(self) -> None:
        """TC-01.11: show of a uid in an undeclared account (golden)."""
        self.configure(ICLOUD_ONLY_CONFIG)
        payload = self.run_error(
            "show", "83160", expected_exit=2, expected_code="E_ACCOUNT_NOT_IN_SCOPE"
        )
        self.assert_golden("show_not_in_scope_error.json", payload)


# --------------------------------------------------------------------------- #
# TC-02 — Outlook goldens (RF-30, PRD 12.5) over the in-memory fake
# --------------------------------------------------------------------------- #

#: Golden profile config: the cached Exchange account and the excluded shared
#: mailbox, both declared (the latter reports W_STORE_EXCLUDED, PRD 15.3).
OUTLOOK_GOLDEN_CONFIG = (
    '[scope."ana.perez@example.com"]\n'
    '[scope."Exchange shared (Soporte)"]\n'
)
OUTLOOK_STORE_EXCLUDED = "W_STORE_EXCLUDED: Exchange shared (Soporte) is excluded: shared_mailbox"


class OutlookGoldenTest(unittest.TestCase):
    """``cli.main`` with the Outlook backend over ``FakeOutlook.default()`` (TC-02 profile).

    The local zone is injected (fixed UTC-04:00) so the converted dates do not
    depend on the host zone.
    """

    def setUp(self) -> None:
        from mailquery import output
        from tests.fakes import outlook as fake_outlook

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.addCleanup(_close_log_handlers)
        self.root = Path(tmp.name)
        self.home = self.root / ".mailquery"
        self.home.mkdir()
        (self.home / "config.toml").write_text(OUTLOOK_GOLDEN_CONFIG, encoding="utf-8")
        self.fake = fake_outlook.FakeOutlook.default()
        zone = fake_outlook.FakeZone.fixed(-4)
        patcher = mock.patch.object(output, "LOCAL_ZONE", zone)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_ok(self, *args: str) -> dict:
        from mailquery.backends import get_backend

        backend = get_backend(
            platform="win32",
            outlook_app=self.fake,
            registry=self.fake.registry,
            security_center=self.fake.security_center,
            tmp_root=self.home / "tmp",
        )
        self.addCleanup(backend.close)
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = cli.main(list(args), home=self.home, backend=backend)
        self.assertEqual(code, 0, stdout.getvalue() + stderr.getvalue())
        payload = json.loads(stdout.getvalue())
        self.assertIs(payload["ok"], True)
        self.assertRegex(payload["generated_at"], ISO_EXACT_RE)
        self.assertEqual(self.fake.mutations.total, 0)
        return payload

    def show(self, key: str) -> dict:
        payload = self.run_ok("show", self.fake.item(key).entry_id)
        self.assertEqual(payload["message"]["uid"], self.fake.item(key).entry_id)
        return payload

    def test_tc_02_01_mailboxes(self) -> None:
        """TC-02.01: mailboxes of the golden profile (golden)."""
        payload = self.run_ok("mailboxes")
        self.assertEqual(
            payload["excluded_stores"],
            [{"label": "Exchange shared (Soporte)", "path": None, "reason": "shared_mailbox"}],
        )
        self.assertEqual(payload["warnings"], [OUTLOOK_STORE_EXCLUDED])
        inbox = payload["mailboxes"][0]
        self.assertEqual(
            (inbox["path"], inbox["total"], inbox["unread"], inbox["included"]),
            ("INBOX", 3, 2, True),
        )
        _assert_golden(self, "outlook/mailboxes.json", payload, self.root)

    def test_tc_02_02_search(self) -> None:
        """TC-02.02: search of the golden profile (golden)."""
        payload = self.run_ok("search")
        self.assertEqual(
            [message["uid"] for message in payload["messages"]],
            [self.fake.item(key).entry_id for key in ("normal", "header_only", "smime_encrypted")],
        )
        normal = payload["messages"][0]
        self.assertEqual(normal["date_received"], "2026-11-02T09:54:09-04:00")
        self.assertEqual(normal["date_sent"], "2026-11-02T09:54:03-04:00")
        self.assertEqual(payload["warnings"][0], OUTLOOK_STORE_EXCLUDED)
        _assert_golden(self, "outlook/search.json", payload, self.root)

    def test_tc_02_03_show(self) -> None:
        """TC-02.03: show of the normal message with an attachment (golden)."""
        payload = self.show("normal")
        message = payload["message"]
        self.assertEqual(message["attachments"], [{"name": "factura-2026-10.pdf"}])
        self.assertEqual(message["date_received"], "2026-11-02T09:54:09-04:00")
        self.assertIs(message["readable"], True)
        _assert_golden(self, "outlook/show.json", payload, self.root)

    def test_tc_02_04_show_header_only(self) -> None:
        """TC-02.04: show of a header-only item: no body, W_BODY_NOT_LOCAL (golden)."""
        payload = self.show("header_only")
        message = payload["message"]
        self.assertEqual((message["readable"], message["body_text"]), (False, ""))
        self.assertTrue(payload["warnings"][1].startswith("W_BODY_NOT_LOCAL: "))
        _assert_golden(self, "outlook/show_header_only.json", payload, self.root)

    def test_tc_02_05_show_smime(self) -> None:
        """TC-02.05: show of an S/MIME encrypted item: unreadable, no attachments (golden)."""
        payload = self.show("smime_encrypted")
        message = payload["message"]
        self.assertEqual((message["readable"], message["attachments"]), (False, []))
        self.assertIn(
            "W_BODY_UNREADABLE: S/MIME encrypted content is not supported", payload["warnings"]
        )
        _assert_golden(self, "outlook/show_smime.json", payload, self.root)

    def test_tc_02_06_new_first_run(self) -> None:
        """TC-02.06: first run of ``new``: the [D - lookback, D] window, hex uids (golden)."""
        from mailquery.backends.outlook import OutlookBackend

        normal = self.fake.item("normal").entry_id
        payload = self.run_ok("new")
        self.assertEqual([message["uid"] for message in payload["messages"]], [normal])
        self.assertEqual(
            payload["warnings"],
            [
                OUTLOOK_STORE_EXCLUDED,
                "W_FIRST_RUN: first run: emitted the messages received in the last "
                "10min before the newest message",
            ],
        )
        self.assertIsNone(payload["cursor"]["previous"])
        self.assertEqual(payload["cursor"]["current"]["last_uid"], normal)
        state = StateStore(self.home, OutlookBackend.check_state_uid).load()
        self.assertEqual(state.emitted_uids, (normal,))
        _assert_golden(self, "outlook/new_first_run.json", payload, self.root)

    def test_tc_02_07_doctor(self) -> None:
        """TC-02.07: ``doctor --json`` of the golden profile: every check passes (golden)."""
        payload = self.run_ok("doctor", "--json")
        checks = payload["checks"]
        self.assertEqual(
            [check["name"] for check in checks],
            [
                "python", "home", "driver", "pywin32", "outlook", "stores",
                "readonly_strategy", "object_model_guard", "config", "state", "lock",
            ],
        )
        for check in checks:
            self.assertIs(check["ok"], True, check)
        by_name = {check["name"]: check for check in checks}
        self.assertIn(OUTLOOK_STORE_EXCLUDED, by_name["config"]["detail"])
        self.assertIn(str(self.home / "tmp" / "gen_py"), by_name["readonly_strategy"]["detail"])
        _assert_golden(self, "outlook/doctor.json", payload, self.root)


# --------------------------------------------------------------------------- #
# TC-04 / TC-05 — recipes and JSON shape on both backends (PRD 21.2, RF-30)
# --------------------------------------------------------------------------- #

RECIPES_DIR = Path(__file__).resolve().parents[1] / "docs" / "recipes"
#: Outlook config of TC-04/TC-05 over ``FakeOutlook.item_matrix()``: the Exchange
#: account with ``INBOX/Facturas``, which holds a message of the last month.
OUTLOOK_ITEMS_CONFIG = '[scope."ana@example.com"]\nmailbox_list = ["INBOX/Facturas"]\n'


def _recipe_commands(name: str) -> list[list[str]]:
    """Each line that starts with ``mailquery`` inside a code block of the recipe (plan 7.4).

    Fenced blocks may be indented (inside a list). The shell comment that
    follows a command is dropped and the quotes are resolved as a shell would.
    """
    import shlex

    commands: list[list[str]] = []
    inside = False
    for line in (RECIPES_DIR / name).read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            inside = not inside
            continue
        if inside and (stripped == "mailquery" or stripped.startswith("mailquery ")):
            commands.append(shlex.split(stripped, comments=True)[1:])
    return commands


def _key_paths(value: object, prefix: str = "") -> set[str]:
    """Recursive set of JSON keys (``a.b``, list elements as ``a[]``), values ignored."""
    paths: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}"
            paths.add(path)
            paths |= _key_paths(item, path)
    elif isinstance(value, list):
        for item in value:
            paths |= _key_paths(item, f"{prefix}[]")
    return paths


class _BothBackendsCase(unittest.TestCase):
    """``cli.main`` on Apple Mail (fixture store) and on Outlook (in-memory fake).

    Apple Mail runs over ``build_store()`` with ``DEFAULT_CONFIG``; Outlook over
    ``outlook_fake()`` (``FakeOutlook.item_matrix()`` by default) with
    ``OUTLOOK_ITEMS_CONFIG``, each in its own temporary home.
    """

    def setUp(self) -> None:
        from mailquery.backends import outlook_com

        self.fx = build_store()
        self.addCleanup(self.fx.cleanup)
        write_config(self.fx.home, DEFAULT_CONFIG)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.addCleanup(_close_log_handlers)  # before the cleanups above (Windows)
        self.outlook_home = Path(tmp.name) / ".mailquery"
        self.outlook_home.mkdir()
        (self.outlook_home / "config.toml").write_text(OUTLOOK_ITEMS_CONFIG, encoding="utf-8")
        self.fake = self.outlook_fake()
        patcher = mock.patch.object(outlook_com, "get_drive_type", self.fake.drive_type)
        patcher.start()
        self.addCleanup(patcher.stop)

    def outlook_fake(self):
        from tests.fakes import outlook as fake_outlook

        return fake_outlook.FakeOutlook.item_matrix()

    @staticmethod
    def _capture(call) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = call()
        return code, stdout.getvalue(), stderr.getvalue()

    def run_backend(self, backend: str, *args: str) -> tuple[int, dict, str]:
        """Run ``mailquery <args>`` on ``"apple_mail"`` or ``"outlook"``: (exit, JSON, stderr)."""
        if backend == "apple_mail":
            code, stdout, stderr = self._capture(
                lambda: cli.main(
                    list(args),
                    home=self.fx.home,
                    mail_root=self.fx.mail_root,
                    accounts_db=self.fx.accounts_db,
                )
            )
        else:
            from mailquery.backends import get_backend

            instance = get_backend(
                platform="win32",
                outlook_app=self.fake,
                registry=self.fake.registry,
                security_center=self.fake.security_center,
                tmp_root=self.outlook_home / "tmp",
            )
            self.addCleanup(instance.close)
            code, stdout, stderr = self._capture(
                lambda: cli.main(list(args), home=self.outlook_home, backend=instance)
            )
        self.assertTrue(stdout.strip(), f"{backend} {args}: no JSON on stdout; stderr={stderr}")
        return code, json.loads(stdout), stderr

    def run_both_ok(self, *args: str) -> dict[str, dict]:
        """``args`` on both backends, each with exit 0: ``{backend: payload}``."""
        payloads = {}
        for backend in ("apple_mail", "outlook"):
            code, payload, stderr = self.run_backend(backend, *args)
            self.assertEqual(code, 0, f"{backend} {args}: {payload} {stderr}")
            payloads[backend] = payload
        return payloads


class RecipeCommandTest(_BothBackendsCase):
    """TC-04 (PRD 21.2): every recipe command runs with exit 0 on both backends."""

    def assert_recipe(self, name: str, uid_command: tuple[str, ...]) -> None:
        commands = _recipe_commands(name)
        self.assertTrue(commands, f"no mailquery command in {name}")
        for backend in ("apple_mail", "outlook"):
            code, payload, stderr = self.run_backend(backend, *uid_command)
            self.assertEqual(code, 0, f"{backend} {uid_command}: {payload} {stderr}")
            self.assertTrue(payload["messages"], f"{backend} {uid_command}: no message for <uid>")
            uid = str(payload["messages"][0]["uid"])
            for command in commands:
                argv = [uid if arg == "<uid>" else arg for arg in command]
                with self.subTest(backend=backend, command=" ".join(command)):
                    code, payload, stderr = self.run_backend(backend, *argv)
                    self.assertEqual(code, 0, f"{payload} {stderr}")
                    self.assertIs(payload["ok"], True)

    def test_tc_04_01_new_mail_digest_commands_exit_0_on_both_backends(self) -> None:
        """TC-04.01: each command of 01-new-mail-digest.md exits 0 (<uid> from `new --peek`)."""
        self.assert_recipe("01-new-mail-digest.md", ("new", "--peek"))

    def test_tc_04_02_search_invoices_commands_exit_0_on_both_backends(self) -> None:
        """TC-04.02: each command of 02-search-invoices.md exits 0 (<uid> from `search --since 1mo`)."""
        self.assert_recipe("02-search-invoices.md", ("search", "--since", "1mo"))


class JsonShapeParityTest(_BothBackendsCase):
    """TC-05 (RF-30): the same recursive set of JSON keys on both backends.

    The Outlook profile adds to ``item_matrix`` a message with To, Cc and a
    visible attachment (the counterpart of Apple Mail's uid 2714), so that the
    lists of both payloads have elements whose keys can be compared.
    """

    def outlook_fake(self):
        from tests.fakes import outlook as fake_outlook

        fake = fake_outlook.FakeOutlook.item_matrix()
        inbox = fake.store("exchange").inbox
        assert inbox is not None
        inbox.add_message(
            "complete",
            subject="Factura completa",
            sender=("Proveedor", "ventas@proveedor.example"),
            to=[("Ana", "ana@example.com")],
            cc=[("Copia", "copia@example.com")],
            body="Adjuntamos la factura.\r\n",
            attachments=[fake_outlook.AttachmentSpec("factura.pdf")],
        )
        return fake

    def assert_same_keys(self, payloads: dict[str, dict]) -> None:
        apple, outlook = (_key_paths(payloads[name]) for name in ("apple_mail", "outlook"))
        self.assertTrue(apple)
        self.assertEqual(
            (sorted(apple - outlook), sorted(outlook - apple)),
            ([], []),
            "keys only on Apple Mail / only on Outlook",
        )

    def test_tc_05_01_search(self) -> None:
        """TC-05.01: `search` has the same recursive keys on both backends."""
        payloads = self.run_both_ok("search", "--limit", "200")
        for payload in payloads.values():
            self.assertTrue(any(message["cc"] for message in payload["messages"]))
        self.assert_same_keys(payloads)

    def test_tc_05_02_new(self) -> None:
        """TC-05.02: `new` (first run) has the same recursive keys on both backends."""
        payloads = self.run_both_ok("new")
        for payload in payloads.values():
            self.assertTrue(payload["messages"])
        self.assert_same_keys(payloads)

    def test_tc_05_03_show(self) -> None:
        """TC-05.03: `show` (message with To, Cc and an attachment) has the same keys."""
        payloads = {}
        for backend, uid in (
            ("apple_mail", "2714"),
            ("outlook", self.fake.item("complete").entry_id),
        ):
            code, payload, stderr = self.run_backend(backend, "show", uid)
            self.assertEqual(code, 0, f"{backend}: {payload} {stderr}")
            self.assertTrue(payload["message"]["cc"] and payload["message"]["attachments"])
            payloads[backend] = payload
        self.assert_same_keys(payloads)

    def test_tc_05_04_mailboxes(self) -> None:
        """TC-05.04: `mailboxes` has the same recursive keys on both backends."""
        self.assert_same_keys(self.run_both_ok("mailboxes"))

    def test_tc_05_05_error(self) -> None:
        """TC-05.05: an error has the same recursive keys on both backends."""
        payloads = {}
        for backend in ("apple_mail", "outlook"):
            code, payload, _stderr = self.run_backend(backend, "search", "--since", "banana")
            self.assertEqual((code, payload["error"]["code"]), (2, "E_BAD_TIME"))
            payloads[backend] = payload
        self.assert_same_keys(payloads)

    def test_tc_05_06_doctor_json(self) -> None:
        """TC-05.06: `doctor --json` has the same recursive keys on both backends."""
        self.assert_same_keys(self.run_both_ok("doctor", "--json"))


# --------------------------------------------------------------------------- #
# error JSON, exit codes and failure modes
# --------------------------------------------------------------------------- #


class ErrorContractTest(IntegrationBase):
    def test_bad_time_is_exit_2(self) -> None:
        self.run_error("search", "--since", "banana", expected_exit=2, expected_code="E_BAD_TIME")

    def test_invalid_limit_is_exit_2(self) -> None:
        self.run_error("search", "--limit", "0", expected_exit=2, expected_code="E_USAGE")
        self.run_error("show", "not-a-uid", expected_exit=2, expected_code="E_USAGE")

    def test_unknown_command_is_exit_2(self) -> None:
        code, payload, stderr = self.run_cli("frobnicate")
        self.assertEqual(code, 2)
        assert payload is not None
        self.assertIs(payload["ok"], False)
        self.assertEqual(payload["error"]["code"], "E_USAGE")
        self.assertTrue(stderr.strip())

    def test_invalid_config_is_exit_2(self) -> None:
        self.configure(BROKEN_CONFIG)
        self.run_error("search", expected_exit=2, expected_code="E_CONFIG_INVALID")

    def test_missing_store_is_exit_3(self) -> None:
        with tempfile.TemporaryDirectory(prefix="mailquery-nostore-") as tmp, _closing_log_handlers():
            empty_root = Path(tmp) / "Mail"
            empty_root.mkdir()
            empty_home = Path(tmp) / "home"
            empty_home.mkdir()
            missing_accounts = Path(tmp) / "Accounts4.sqlite"
            self.run_error(
                "mailboxes",
                home=empty_home,
                mail_root=empty_root,
                accounts_db=missing_accounts,
                expected_exit=3,
                expected_code="E_STORE_NOT_FOUND",
            )
            # doctor still diagnoses and exits 0 (PRD decision 8).
            code, payload, _stderr = self.run_cli(
                "doctor",
                "--json",
                home=empty_home,
                mail_root=empty_root,
                accounts_db=missing_accounts,
            )
            self.assertEqual(code, 0)
            assert payload is not None
            self.assertIs(payload["ok"], True)
            checks = {check["name"]: check for check in payload["checks"]}
            self.assertIs(checks["store"]["ok"], False)
            self.assertIs(checks["schema"]["ok"], False)

    def test_ut_st_04_02_corrupt_state_blocks_new_but_not_the_other_commands(self) -> None:
        """UT-ST-04.02: with a corrupt state ``new`` fails; search, show and mailboxes work."""
        (self.fx.home / "state.json").write_text("{this is not json", encoding="utf-8")
        error = self.run_error("new", expected_exit=3, expected_code="E_STATE_CORRUPT")
        self.assertIn("first run", error["error"]["hint"])
        # search/show/mailboxes/doctor are unaffected by a damaged state file.
        self.run_ok("search")
        self.run_ok("show", "2714")
        self.run_ok("mailboxes")
        code, payload, _stderr = self.run_cli("doctor", "--json")
        self.assertEqual(code, 0)
        assert payload is not None
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertIs(checks["state"]["ok"], False)

    def test_lock_contention_is_exit_5(self) -> None:
        from mailquery.state import RunLock

        lock = RunLock(self.fx.home)
        lock.acquire()
        try:
            self.run_error("mailboxes", expected_exit=5, expected_code="E_LOCKED")
        finally:
            lock.release()
        # Released: the next invocation succeeds.
        self.run_ok("mailboxes")

    def test_account_labels_unavailable_is_exit_2(self) -> None:
        missing = self.fx.root / "missing-accounts.sqlite"
        self.run_error(
            "search",
            accounts_db=missing,
            expected_exit=2,
            expected_code="E_ACCOUNT_LABELS_UNAVAILABLE",
        )

    def test_include_mailbox_on_undeclared_account_is_exit_2(self) -> None:
        self.configure(ICLOUD_ONLY_CONFIG)
        self.run_error(
            "search",
            "--include-mailbox",
            "All Mail",
            expected_exit=2,
            expected_code="E_ACCOUNT_NOT_IN_SCOPE",
        )

    def test_mailbox_not_found_is_exit_2(self) -> None:
        self.configure(f'[scope."{ICLOUD_LABEL}"]\nmailbox_list = ["Does not exist"]\n')
        self.run_error("search", expected_exit=2, expected_code="E_MAILBOX_NOT_FOUND")

    def test_permission_denied_on_store_is_exit_3(self) -> None:
        from tests.mocks import tcc_denied

        with tcc_denied():
            self.run_error("mailboxes", expected_exit=3, expected_code="E_PERMISSION")
            # doctor never fails: it reports the denied store and exits 0.
            code, payload, _stderr = self.run_cli("doctor", "--json")
        self.assertEqual(code, 0)
        assert payload is not None
        checks = {check["name"]: check for check in payload["checks"]}
        # The store *directory* is visible; opening the index is what TCC denies.
        self.assertIs(checks["schema"]["ok"], False)
        self.assertIs(checks["readonly_strategy"]["ok"], False)

    def test_unexpected_schema_is_exit_3(self) -> None:
        from tests.mocks import drop_required_table

        drop_required_table(self.fx.envelope_index, "message_global_data")
        self.run_error("mailboxes", expected_exit=3, expected_code="E_SCHEMA_UNSUPPORTED")
        code, payload, _stderr = self.run_cli("doctor", "--json")
        self.assertEqual(code, 0)
        assert payload is not None
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertIs(checks["schema"]["ok"], False)


# --------------------------------------------------------------------------- #
# TC-07 — user documentation (PRD 21.2, 23.3)
# --------------------------------------------------------------------------- #

DOCS_ROOT = Path(__file__).resolve().parents[1]
#: Terms the 1.x documentation used and the 2.0.0 contract retired (TC-07.01-.04).
_FORBIDDEN_DOC_TERMS = (
    re.compile(r"baseline", re.IGNORECASE),
    re.compile(r"retention_days(?! was replaced by max_size_mb)"),
    re.compile(r"W_EMLX_UNREADABLE"),
    re.compile(r"only runs on macOS", re.IGNORECASE),
    re.compile(r"solo macOS", re.IGNORECASE),
)


class UserDocumentationTest(unittest.TestCase):
    """TC-07: the user documentation has no 1.x leftovers and the recipes cover exits 3, 5, 6."""

    def assert_clean(self, label: str, text: str) -> None:
        for pattern in _FORBIDDEN_DOC_TERMS:
            match = pattern.search(text)
            self.assertIsNone(match, f"{label} contains {match.group(0)!r}" if match else "")

    def test_tc_07_01_readme_has_no_retired_terms(self) -> None:
        """TC-07.01: README.md without baseline, retention_days (but the hint), W_EMLX_UNREADABLE, macOS-only."""
        self.assert_clean("README.md", (DOCS_ROOT / "README.md").read_text(encoding="utf-8"))

    def test_tc_07_02_recipes_have_no_retired_terms(self) -> None:
        """TC-07.02: the recipes without the retired terms."""
        recipes = sorted(RECIPES_DIR.glob("*.md"))
        self.assertEqual(len(recipes), 2)
        for recipe in recipes:
            self.assert_clean(recipe.name, recipe.read_text(encoding="utf-8"))

    def test_tc_07_03_config_example_has_no_retired_terms(self) -> None:
        """TC-07.03: docs/config.example.toml without the retired terms."""
        path = DOCS_ROOT / "docs" / "config.example.toml"
        self.assert_clean(path.name, path.read_text(encoding="utf-8"))

    def test_tc_07_04_help_has_no_retired_terms(self) -> None:
        """TC-07.04: the --help output of the root and of the 5 commands without the retired terms."""
        for argv in (["--help"], *([command, "--help"] for command in ("doctor", "mailboxes", "search", "new", "show"))):
            with self.subTest(argv=argv):
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
                    code = cli.main(argv)
                self.assertEqual(code, 0)
                self.assertTrue(stdout.getvalue().strip())
                self.assert_clean(" ".join(argv), stdout.getvalue())

    def test_tc_07_05_each_recipe_mentions_exits_3_5_and_6(self) -> None:
        """TC-07.05: every recipe handles the exit codes 3, 5 and 6."""
        for recipe in sorted(RECIPES_DIR.glob("*.md")):
            text = recipe.read_text(encoding="utf-8")
            for code in ("3", "5", "6"):
                with self.subTest(recipe=recipe.name, exit=code):
                    self.assertIsNotNone(re.search(rf"exit {code}(?!\d)|`{code}`", text), f"no mention of exit {code}")


if __name__ == "__main__":  # pragma: no cover - manual runs
    unittest.main()

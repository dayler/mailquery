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
import hashlib
import io
import json
import logging
import os
import re
import sqlite3
import sys
import tempfile
import tomllib
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

from mailquery import __version__, cli
from mailquery.backends.apple_mail import AppleMailBackend
from mailquery.backends.registry import BackendRegistry
from mailquery.config import load_config
from mailquery.search import DEFAULT_ROW_FIELDS, SEARCH_ROW_FIELDS
from mailquery.state import StateStore
from tests.fakes.plugin import (
    ACCOUNT_LABEL as PLUGIN_ACCOUNT_LABEL,
    DRIVER as PLUGIN_DRIVER,
    FakeEntryPoint,
    internal_entry_points,
    plugin_factory,
)
from tests.fixtures.make_fixtures import (
    ACCOUNT_GMAIL,
    ACCOUNT_ICLOUD,
    ACCOUNT_LOCAL,
    DEFAULT_CONFIG,
    GMAIL_LABEL,
    ICLOUD_LABEL,
    LIMIT_1MB_CONFIG,
    LOCAL_LABEL,
    MAILBOX_ICLOUD_INBOX,
    PAYLOAD_PDF_OCTUBRE,
    UID_ATTACH_BIG,
    UID_ATTACH_CORRUPT,
    UID_ATTACH_EMPTY,
    UID_ATTACH_EXECUTABLE,
    UID_ATTACH_HOSTILE_RESERVED,
    UID_ATTACH_MISSING_EMLX,
    UID_ATTACH_MULTI,
    UID_ATTACH_PARTIAL,
    UID_ATTACH_SMIME,
    build_store,
    write_config,
    write_state,
    prefixed_uid,
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
    prefixed_uid(83170),
    prefixed_uid(83160),
    prefixed_uid(83150),
    prefixed_uid(83143),
    prefixed_uid(83210),
    prefixed_uid(2714),
    prefixed_uid(83220),
    prefixed_uid(83200),
    prefixed_uid(79658),
    prefixed_uid(83180),
    prefixed_uid(830),
    prefixed_uid(83190),
]

MESSAGE_FIELDS = set(SEARCH_ROW_FIELDS)
DEFAULT_FIELDS = set(DEFAULT_ROW_FIELDS)
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


def _all_installed(driver: str) -> bool:
    """``state.json`` driver check for the fixture commands (both built-ins installed)."""
    return bool(driver)


MESSAGE_DIR_RE = re.compile(r"(/attachments/[a-z0-9_]+/)([^/]+)")


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
        text = text.replace("\\", "/")
        # Windows uses the stable 32-hex directory when the real cache path
        # exceeds its conservative budget; the message directory is not
        # platform-independent, so goldens keep it as a placeholder.
        return MESSAGE_DIR_RE.sub(r"\1<MESSAGE_DIR>", text)
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
        wanted = prefixed_uid(uid)
        for message in payload["messages"]:
            if message["uid"] == wanted:
                return message
        self.fail(f"uid {wanted} not present in {payload['count']} results")

    def assert_message_shape(self, message: dict) -> None:
        """The six-field default row of ``search``/``new``, in canonical order."""
        self.assertEqual(list(message), list(DEFAULT_ROW_FIELDS))
        self.assertIsInstance(message["uid"], str)
        self.assertTrue(message["uid"].startswith("apple_mail:"))
        self.assertIsInstance(message["subject"], str)
        self.assertIsInstance(message["from"], dict)
        self.assertIsInstance(message["from"].get("name"), str)
        self.assertIsInstance(message["from"].get("address"), str)
        if message["date_received"] is not None:
            self.assertRegex(message["date_received"], ISO_EXACT_RE)
        for field in ("is_read", "has_attachments"):
            self.assertIsInstance(message[field], bool)

    def assert_full_message_shape(self, message: dict) -> None:
        """The full ``--fields all`` row with the nested objects of the contract."""
        self.assertTrue(MESSAGE_FIELDS <= set(message), MESSAGE_FIELDS - set(message))
        self.assertIsInstance(message["uid"], str)
        self.assertTrue(message["uid"].startswith("apple_mail:"))
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
        self.assertIn("mailquery doctor - environment and read-only diagnosis", text)
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
        self.assertEqual(
            set(payload),
            {
                "ok",
                "command",
                "generated_at",
                "accounts",
                "excluded_stores",
                "warnings",
            },
        )

        accounts = {account["uuid"]: account for account in payload["accounts"]}
        self.assertEqual(set(accounts), {ACCOUNT_ICLOUD, ACCOUNT_GMAIL, ACCOUNT_LOCAL})
        self.assertEqual(accounts[ACCOUNT_ICLOUD]["label"], ICLOUD_LABEL)
        self.assertEqual(accounts[ACCOUNT_ICLOUD]["email"], "fixture@icloud.com")
        self.assertEqual(accounts[ACCOUNT_GMAIL]["label"], GMAIL_LABEL)
        self.assertEqual(accounts[ACCOUNT_GMAIL]["email"], "fixture@gmail.com")
        self.assertEqual(accounts[ACCOUNT_LOCAL]["label"], LOCAL_LABEL)
        for account in accounts.values():
            self.assertTrue(ACCOUNT_FIELDS | {"declared", "mailboxes"} <= set(account))
            self.assertIs(account["declared"], True)
        for account in accounts.values():
            for entry in account["mailboxes"]:
                self.assertEqual(set(entry), {"path", "included"})
                self.assertIsInstance(entry["included"], bool)

        full = self.run_ok("mailboxes", "--fields", "name,url,total,unread")
        by_key = {
            (account["uuid"], entry["path"]): entry
            for account in full["accounts"]
            for entry in account["mailboxes"]
        }
        self.assertEqual(len(by_key), 7)
        for entry in by_key.values():
            self.assertTrue(
                {"name", "path", "url", "total", "unread", "included"} <= set(entry)
            )
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

        # The fields outside the default row and the body warnings are checked
        # on the full row of the same query.
        full = self.run_ok("search", "--fields", "all")
        self.assertEqual([message["uid"] for message in full["messages"]], DEFAULT_UID_ORDER)
        for message in full["messages"]:
            self.assert_full_message_shape(message)

        invoice = self.message_by_uid(full, 2714)
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

        partial = self.message_by_uid(full, 79658)
        self.assertIs(partial["body"]["partial"], True)
        self.assertEqual(partial["mailbox"]["path"], "Facturas")
        self.assertEqual(partial["snippet"], "Adjuntamos la factura de septiembre.")
        self.assertIs(partial["has_attachments"], True)

        flagged = self.message_by_uid(full, 83150)
        self.assertIs(flagged["is_flagged"], True)
        self.assertIs(flagged["is_read"], False)
        self.assertEqual(flagged["snippet"], "Remember this.")

        gmail = self.message_by_uid(full, 83210)
        self.assertIs(gmail["is_read"], False)
        self.assertIs(gmail["has_attachments"], True)
        self.assertEqual(gmail["mailbox"]["account"]["uuid"], ACCOUNT_GMAIL)
        self.assertEqual(gmail["mailbox"]["path"], "INBOX")
        self.assertEqual(gmail["snippet"], "Photo attached.")

        missing = self.message_by_uid(full, 83170)
        self.assertIs(missing["body"]["available"], False)
        self.assertEqual(missing["snippet"], "")
        self.assert_warning(full, "W_EMLX_MISSING")

        corrupt = self.message_by_uid(full, 83180)
        self.assertEqual(corrupt["snippet"], "")
        self.assert_warning(full, "W_EMLX_")

        html_only = self.message_by_uid(full, 83200)
        self.assertIn("HTML only", html_only["snippet"])
        self.assertIn("no plain text part", html_only["snippet"])

        no_header = self.message_by_uid(full, 83220)
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
        self.assertNotIn(prefixed_uid(83142), [message["uid"] for message in payload["messages"]])
        for message in payload["messages"]:
            self.assert_message_shape(message)

        full = self.run_ok("search", "--fields", "all")
        duplicate = self.message_by_uid(full, 83143)
        self.assertEqual(duplicate["duplicate_count"], 2)
        self.assertEqual(duplicate["subject"], "Shared duplicate")
        self.assertEqual(duplicate["message_id"], "<duplicate-4@fixture.example>")
        self.assertEqual(duplicate["mailbox"]["path"], "INBOX")
        self.assertEqual(duplicate["snippet"], "Duplicate body from the inbox.")
        for message in full["messages"]:
            if message["uid"] != prefixed_uid(83143):
                self.assertEqual(message["duplicate_count"], 1, message["uid"])
        self.assert_golden("search_all_mail.json", payload)

    def test_search_text_bounded_by_since(self) -> None:
        self.configure(ICLOUD_ONLY_CONFIG)
        payload = self.run_ok("search", "--text", "invoice", "--since", "30d", "--fields", "snippet")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["messages"][0]["uid"], prefixed_uid(2714))
        self.assertEqual(payload["messages"][0]["snippet"], "Please find the invoice attached.")
        self.assertEqual(payload["scan"]["mode"], "text")
        self.assertEqual(payload["scan"]["candidates"], 6)

    def test_search_text_bounded_by_config_extra_mailbox(self) -> None:
        payload = self.run_ok("search", "--text", "factura", "--fields", "snippet")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["messages"][0]["uid"], prefixed_uid(79658))
        self.assertEqual(payload["messages"][0]["snippet"], "Adjuntamos la factura de septiembre.")

    def test_search_text_bounded_by_include_mailbox(self) -> None:
        self.configure(ICLOUD_ONLY_CONFIG)
        payload = self.run_ok("search", "--text", "factura", "--include-mailbox", "Facturas")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["messages"][0]["uid"], prefixed_uid(79658))

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
            "last_uid": prefixed_uid(1),
            "lookback_seconds": 600,
        }
        write_state(
            self.fx.home,
            {
                "schema": 2,
                "updated_at": "",
                "last_run": None,
                "cursor": cursor,
                "emitted_uids": [],
            },
        )
        return cursor

    def test_tc_01_05_first_run_emits_the_lookback_window(self) -> None:
        """TC-01.05: first run of ``new`` emits the [D - lookback, D] window (golden)."""
        self.assertFalse(StateStore(self.fx.home, _all_installed).path.exists())
        payload = self.run_ok("new")
        self.assertEqual(payload["command"], "new")
        self.assertEqual(payload["count"], 2)
        self.assertEqual(
            [message["uid"] for message in payload["messages"]], [prefixed_uid(83160), prefixed_uid(83170)]
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
        self.assertEqual(cursor["current"]["last_uid"], prefixed_uid(83170))
        self.assertEqual(cursor["current"]["last_date_received"], expected_date)
        self.assertEqual(cursor["current"]["lookback_seconds"], 600)

        state = StateStore(self.fx.home, _all_installed).load()
        self.assertIsNotNone(state.cursor)
        assert state.cursor is not None
        self.assertEqual(state.cursor.last_uid, prefixed_uid(83170))
        self.assertEqual(state.cursor.last_date_received, expected_date)
        self.assertEqual(state.emitted_uids, (prefixed_uid(83160), prefixed_uid(83170)))
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
            [prefixed_uid(83143), prefixed_uid(83150), prefixed_uid(83160), prefixed_uid(83170)],
        )
        self.assertIs(payload["truncated"], False)
        for message in payload["messages"]:
            self.assert_message_shape(message)
        cursor = payload["cursor"]
        self.assertEqual(cursor["previous"], seeded)
        self.assertEqual(cursor["current"]["last_uid"], prefixed_uid(83170))
        self.assertEqual(
            cursor["current"]["last_date_received"],
            int((self.fx.now - timedelta(minutes=15)).timestamp()),
        )
        self.assertEqual(cursor["current"]["lookback_seconds"], 600)

        state = StateStore(self.fx.home, _all_installed).load()
        assert state.cursor is not None
        self.assertEqual(state.cursor.last_uid, prefixed_uid(83170))
        self.assertEqual(set(state.emitted_uids), {prefixed_uid(83143), prefixed_uid(83150), prefixed_uid(83160), prefixed_uid(83170)})
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
            [prefixed_uid(83143), prefixed_uid(83150), prefixed_uid(83160), prefixed_uid(83170)],
        )
        state = StateStore(self.fx.home, _all_installed).load()
        assert state.cursor is not None
        self.assertEqual(state.cursor.last_uid, prefixed_uid(1))
        self.assertEqual(state.emitted_uids, ())

        # A real run after the peek still emits the same window.
        emitted = self.run_ok("new")
        self.assertEqual({message["uid"] for message in emitted["messages"]}, {prefixed_uid(83143), prefixed_uid(83150), prefixed_uid(83160), prefixed_uid(83170)})
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
        self.assertEqual(message["uid"], prefixed_uid(2714))
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
        self.assertEqual(
            message["attachments"],
            [{"index": 1, "name": "invoice-2026-10.pdf", "cached_path": None}],
        )
        self.assertIs(message["partial"], False)
        self.assertIs(message["readable"], True)
        self.assertIs(message["source"]["partial"], False)
        self.assertEqual(Path(message["source"]["emlx_path"]).name, "2714.emlx")
        self.assert_golden("show_2714.json", payload)

    def test_tc_01_08_show_missing_emlx(self) -> None:
        """TC-01.08: show with a missing .emlx (golden)."""
        payload = self.run_ok("show", "83170")
        message = payload["message"]
        self.assertEqual(message["uid"], prefixed_uid(83170))
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
        self.assertEqual(message["uid"], prefixed_uid(83180))
        self.assertIs(message["body_text"], "")
        self.assertIs(message["readable"], False)
        self.assert_warning(payload, "W_EMLX_")
        self.assert_golden("show_83180.json", payload)

    def test_show_partial_emlx(self) -> None:
        payload = self.run_ok("show", "79658")
        message = payload["message"]
        self.assertEqual(message["uid"], prefixed_uid(79658))
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
        self.assertEqual(message["uid"], prefixed_uid(90110))
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
# Apple Mail attachments: UT-AM-03/04 and the TC-08 goldens
# --------------------------------------------------------------------------- #

EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


class _AttachmentFixtureCase(IntegrationBase):
    """Integration base over ``build_store(attachments=True)`` (attachment fixtures)."""

    def setUp(self) -> None:
        self.fx = build_store(attachments=True)
        self.addCleanup(self.fx.cleanup)
        self.addCleanup(_close_log_handlers)
        write_config(self.fx.home, DEFAULT_CONFIG)

    def cache_files(self) -> list[Path]:
        base = self.fx.home / "attachments"
        return sorted(path for path in base.rglob("*") if path.is_file())

    def backend(self) -> AppleMailBackend:
        instance = AppleMailBackend(
            mail_root=self.fx.mail_root,
            accounts_db=self.fx.accounts_db,
            tmp_root=self.fx.home / "tmp",
        )
        self.addCleanup(instance.close)
        return instance

    def assert_reason(self, uid: int, index: int, reason: str) -> None:
        rows = self.backend().attachments(uid)
        self.assertEqual(rows[index - 1]["unavailable_reason"], reason, rows)


class AppleMailAttachmentTest(_AttachmentFixtureCase):
    """UT-AM-03/04: extraction, availability, read-only and integration."""

    # -- UT-AM-03 ---------------------------------------------------------- #

    def test_ut_am_03_01_first_extraction_then_cache_hit_then_force(self) -> None:
        """UT-AM-03.01: cached false → true → --force false, same size and sha256."""
        uid = prefixed_uid(UID_ATTACH_MULTI)
        first = self.run_ok("attachment", uid, "--index", "2")
        self.assertIs(first["attachments"][0]["cached"], False)
        second = self.run_ok("attachment", uid, "--index", "2")
        self.assertIs(second["attachments"][0]["cached"], True)
        self.assertEqual(second["attachments"][0]["sha256"], first["attachments"][0]["sha256"])
        forced = self.run_ok("attachment", uid, "--index", "2", "--force")
        self.assertIs(forced["attachments"][0]["cached"], False)
        self.assertEqual(forced["attachments"][0]["sha256"], first["attachments"][0]["sha256"])

    def test_ut_am_03_02_missing_emlx_is_not_local(self) -> None:
        """UT-AM-03.02: a missing .emlx with a DB attachment row ⇒ unavailable (not_local)."""
        payload = self.run_error(
            "attachment",
            prefixed_uid(UID_ATTACH_MISSING_EMLX),
            "--index",
            "1",
            expected_exit=3,
            expected_code="E_ATTACHMENT_UNAVAILABLE",
        )
        self.assertIn("is not available in the local store", payload["error"]["message"])
        self.assert_reason(UID_ATTACH_MISSING_EMLX, 1, "not_local")
        self.assertEqual(self.cache_files(), [])

    def test_ut_am_03_03_unverifiable_externalized_attachment_is_unsupported(self) -> None:
        """UT-AM-03.03: a .partial.emlx externalized part without file ⇒ unsupported."""
        payload = self.run_error(
            "attachment",
            prefixed_uid(UID_ATTACH_PARTIAL),
            "--index",
            "2",
            expected_exit=3,
            expected_code="E_ATTACHMENT_UNAVAILABLE",
        )
        self.assertIn("cannot be recovered by driver 'apple_mail'", payload["error"]["message"])
        self.assert_reason(UID_ATTACH_PARTIAL, 2, "unsupported")
        self.assertEqual(self.cache_files(), [])

    def test_ut_am_03_04_partial_message_mixed_availability(self) -> None:
        """UT-AM-03.04: --all fails on the unsupported part without partial files; --index 1 works."""
        uid = prefixed_uid(UID_ATTACH_PARTIAL)
        self.run_error(
            "attachment",
            uid,
            "--all",
            expected_exit=3,
            expected_code="E_ATTACHMENT_UNAVAILABLE",
        )
        self.assertEqual(self.cache_files(), [])
        payload = self.run_ok("attachment", uid, "--index", "1")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["attachments"][0]["index"], 1)
        self.assertEqual(
            Path(payload["attachments"][0]["path"]).read_bytes(), b"%PDF-1.4\nexternalized fixture attachment\n"
        )

    def test_ut_am_03_05_smime_is_unreadable_never_no_attachments(self) -> None:
        """UT-AM-03.05: S/MIME ⇒ E_ATTACHMENT_UNREADABLE and show returns []."""
        payload = self.run_error(
            "attachment",
            prefixed_uid(UID_ATTACH_SMIME),
            "--index",
            "1",
            expected_exit=3,
            expected_code="E_ATTACHMENT_UNREADABLE",
        )
        self.assertIn("S/MIME protected", payload["error"]["message"])
        shown = self.run_ok("show", prefixed_uid(UID_ATTACH_SMIME))
        self.assertEqual(shown["message"]["attachments"], [])
        self.assert_warning(shown, "W_BODY_UNREADABLE")

    def test_ut_am_03_06_corrupt_mime_payload_is_corrupt(self) -> None:
        """UT-AM-03.06: an undecodable base64 attachment ⇒ E_ATTACHMENT_UNREADABLE (corrupt)."""
        payload = self.run_error(
            "attachment",
            prefixed_uid(UID_ATTACH_CORRUPT),
            "--index",
            "1",
            expected_exit=3,
            expected_code="E_ATTACHMENT_UNREADABLE",
        )
        self.assertIn("is corrupt or unreadable", payload["error"]["message"])
        self.assert_reason(UID_ATTACH_CORRUPT, 1, "corrupt")

    def test_ut_am_03_07_empty_attachment_is_saved_with_zero_size(self) -> None:
        """UT-AM-03.07: a 0-byte attachment is valid (size 0, sha256 of the empty file)."""
        payload = self.run_ok("attachment", prefixed_uid(UID_ATTACH_EMPTY), "--index", "1")
        entry = payload["attachments"][0]
        self.assertEqual(entry["size_bytes"], 0)
        self.assertEqual(entry["sha256"], EMPTY_SHA256)
        self.assertEqual(Path(entry["path"]).read_bytes(), b"")

    def test_ut_am_03_08_deleted_cache_file_is_re_extracted_once(self) -> None:
        """UT-AM-03.08: a cache file deleted before attachment is re-extracted once (AC-20)."""
        uid = prefixed_uid(UID_ATTACH_MULTI)
        first = self.run_ok("attachment", uid, "--index", "1")
        cached = Path(first["attachments"][0]["path"])
        cached.unlink()
        again = self.run_ok("attachment", uid, "--index", "1")
        self.assertIs(again["attachments"][0]["cached"], False)
        self.assertEqual(again["attachments"][0]["sha256"], first["attachments"][0]["sha256"])
        self.assertTrue(cached.is_file())

    def test_ut_am_03_09_all_failure_leaves_no_partial_files(self) -> None:
        """UT-AM-03.09: a failing --all leaves no partial cache file and cleans staging."""
        payload = self.run_error(
            "attachment",
            prefixed_uid(UID_ATTACH_EXECUTABLE),
            "--all",
            expected_exit=4,
            expected_code="E_ATTACHMENT_BLOCKED",
        )
        self.assertIn("executable content", payload["error"]["message"])
        self.assertEqual(self.cache_files(), [])
        staging = self.fx.home / "tmp" / "staging"
        self.assertEqual([path for path in staging.rglob("*") if path.is_file()], [])

    # -- UT-AM-04 ---------------------------------------------------------- #

    def test_ut_am_04_01_store_hashes_and_mtimes_do_not_change(self) -> None:
        """UT-AM-04.01: success, cache, blocked and limit flows leave the store untouched."""
        before = _store_snapshot(self.fx.mail_root)
        self.run_ok("attachment", prefixed_uid(UID_ATTACH_MULTI), "--index", "1")
        self.run_ok("attachment", prefixed_uid(UID_ATTACH_MULTI), "--index", "1")
        self.run_error(
            "attachment", prefixed_uid(UID_ATTACH_HOSTILE_RESERVED), "--all",
            expected_exit=4, expected_code="E_ATTACHMENT_BLOCKED",
        )
        self.run_ok("attachment", prefixed_uid(UID_ATTACH_EMPTY), "--index", "1")
        self.run_error(
            "attachment", prefixed_uid(UID_ATTACH_SMIME), "--index", "1",
            expected_exit=3, expected_code="E_ATTACHMENT_UNREADABLE",
        )
        self.configure(LIMIT_1MB_CONFIG)
        self.run_error(
            "attachment", prefixed_uid(UID_ATTACH_BIG), "--index", "1",
            expected_exit=4, expected_code="E_ATTACHMENT_TOO_LARGE",
        )
        self.assertEqual(_store_snapshot(self.fx.mail_root), before)

    def test_ut_am_04_02_every_write_stays_under_the_app_home(self) -> None:
        """UT-AM-04.02: only ~/.mailquery is written; the staging area is left clean."""
        before = set(_snapshot_paths(self.fx.root))
        self.run_ok("attachment", prefixed_uid(UID_ATTACH_MULTI), "--all")
        self.run_error(
            "attachment", prefixed_uid(UID_ATTACH_EXECUTABLE), "--all",
            expected_exit=4, expected_code="E_ATTACHMENT_BLOCKED",
        )
        new_paths = set(_snapshot_paths(self.fx.root)) - before
        home_prefix = self.fx.home.relative_to(self.fx.root).as_posix()
        for relative in new_paths:
            self.assertTrue(
                relative == home_prefix or relative.startswith(home_prefix + "/"),
                f"write outside the app home: {relative}",
            )
        self.assertTrue(
            any(path.startswith(f"{home_prefix}/attachments/") for path in new_paths),
            new_paths,
        )
        staging = self.fx.home / "tmp" / "staging"
        self.assertEqual([path for path in staging.rglob("*") if path.is_file()], [])

    @unittest.skipUnless(os.name == "posix", "POSIX permissions only")
    def test_ut_am_04_03_cache_permissions_are_private_and_not_executable(self) -> None:
        """UT-AM-04.03: directories 0700 and files 0600 without the executable bit."""
        payload = self.run_ok("attachment", prefixed_uid(UID_ATTACH_MULTI), "--all")
        for entry in payload["attachments"]:
            path = Path(entry["path"])
            file_mode = path.stat().st_mode & 0o777
            self.assertEqual(file_mode, 0o600, path)
            directory = path.parent
            self.assertEqual(directory.stat().st_mode & 0o777, 0o700, directory)
            self.assertEqual(directory.parent.stat().st_mode & 0o777, 0o700, directory.parent)

    def test_ut_am_04_04_capabilities_are_declared_and_shown_by_doctor(self) -> None:
        """UT-AM-04.04: driver capabilities (attachments: local) shown by the doctor `driver` check."""
        backend = self.backend()
        self.assertEqual(backend.driver, "apple_mail")
        self.assertEqual(backend.plugin_api, 1)
        self.assertEqual(
            dict(backend.capabilities),
            {
                "network": False,
                "readonly": "structural",
                "body_local": True,
                "attachments": "local",
                "native_order": "numeric",
            },
        )
        payload = self.run_ok("doctor", "--json")
        driver = next(check for check in payload["checks"] if check["name"] == "driver")
        self.assertIs(driver["ok"], True, driver)
        self.assertIn("attachments=local", driver["detail"])
        self.assertIn("native_order=numeric", driver["detail"])


class AttachmentGoldenTest(_AttachmentFixtureCase):
    """TC-08: the six attachment goldens over the real Apple Mail fixtures.

    Golden seeds: TC-08.01 runs on a fresh store (``cached: false``); TC-08.02
    runs the same extraction once to seed the cache and compares the second run
    (``cached: true``); TC-08.06 seeds ``attachment 2714 --index 1`` before the
    ``show``. Every fixture payload is a fixed byte string, so sizes and sha256
    values are stable.
    """

    def test_tc_08_01_attachment_saved(self) -> None:
        """TC-08.01: attachment --index 2 of the three-attachment message (golden)."""
        payload = self.run_ok(
            "attachment", prefixed_uid(UID_ATTACH_MULTI), "--index", "2"
        )
        entry = payload["attachments"][0]
        self.assertEqual(entry["original_name"], "Factura Octubre 2026.pdf")
        self.assertEqual(entry["sanitized_name"], "02_Factura_Octubre_2026.pdf")
        self.assertIs(entry["cached"], False)
        self.assertEqual(entry["size_bytes"], len(PAYLOAD_PDF_OCTUBRE))
        self.assertEqual(entry["sha256"], hashlib.sha256(PAYLOAD_PDF_OCTUBRE).hexdigest())
        self.assert_golden("attachment_saved.json", payload)

    def test_tc_08_02_attachment_cached(self) -> None:
        """TC-08.02: first run seeds the cache; the second run is the cached golden."""
        uid = prefixed_uid(UID_ATTACH_MULTI)
        seeded = self.run_ok("attachment", uid, "--index", "2")
        self.assertIs(seeded["attachments"][0]["cached"], False)
        payload = self.run_ok("attachment", uid, "--index", "2")
        self.assertIs(payload["attachments"][0]["cached"], True)
        self.assertEqual(
            payload["attachments"][0]["sha256"], seeded["attachments"][0]["sha256"]
        )
        self.assert_golden("attachment_cached.json", payload)

    def test_tc_08_03_attachment_blocked_name(self) -> None:
        """TC-08.03: --all on a message with a reserved filename (golden error, exit 4)."""
        payload = self.run_error(
            "attachment",
            prefixed_uid(UID_ATTACH_HOSTILE_RESERVED),
            "--all",
            expected_exit=4,
            expected_code="E_ATTACHMENT_BLOCKED",
        )
        self.assertIn("CON.fdp.exe", payload["error"]["message"])
        self.assertEqual(self.cache_files(), [])
        self.assert_golden("attachment_blocked_name.json", payload)

    def test_tc_08_04_attachment_blocked_content(self) -> None:
        """TC-08.04: --index 2 of the MZ message (golden error, exit 4)."""
        payload = self.run_error(
            "attachment",
            prefixed_uid(UID_ATTACH_EXECUTABLE),
            "--index",
            "2",
            expected_exit=4,
            expected_code="E_ATTACHMENT_BLOCKED",
        )
        self.assertIn("has executable content", payload["error"]["message"])
        self.assertEqual(self.cache_files(), [])
        self.assert_golden("attachment_blocked_content.json", payload)

    def test_tc_08_05_attachment_too_large(self) -> None:
        """TC-08.05: max_file_size_mb=1 with a known 1.5 MiB attachment (golden, exit 4)."""
        self.configure(LIMIT_1MB_CONFIG)
        payload = self.run_error(
            "attachment",
            prefixed_uid(UID_ATTACH_BIG),
            "--index",
            "1",
            expected_exit=4,
            expected_code="E_ATTACHMENT_TOO_LARGE",
        )
        self.assertIn("max_file_size_mb=1", payload["error"]["message"])
        self.assertEqual(self.cache_files(), [])
        self.assert_golden("attachment_too_large.json", payload)

    def test_tc_08_06_show_with_previous_cache(self) -> None:
        """TC-08.06: attachment 2714 seeds the cache, then show returns its cached_path (golden)."""
        seed = self.run_ok("attachment", "apple_mail:2714", "--index", "1")
        published = Path(seed["attachments"][0]["path"])
        payload = self.run_ok("show", "apple_mail:2714")
        cached_path = payload["message"]["attachments"][0]["cached_path"]
        self.assertEqual(cached_path, str(published))
        self.assertTrue(Path(cached_path).is_file())
        self.assert_golden("show_2714_with_cache.json", payload)


def _store_snapshot(mail_root: Path) -> dict[str, tuple[int, int, str]]:
    """``{relative path: (size, mtime_ns, sha256)}`` of every file of the Mail store."""
    snapshot: dict[str, tuple[int, int, str]] = {}
    for path in sorted(mail_root.rglob("*")):
        if not path.is_file():
            continue
        stat = path.stat()
        snapshot[path.relative_to(mail_root).as_posix()] = (
            stat.st_size,
            stat.st_mtime_ns,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
    return snapshot


def _snapshot_paths(root: Path) -> list[str]:
    """Relative POSIX paths of every file and directory under ``root``."""
    return [
        path.relative_to(root).as_posix()
        for path in sorted(root.rglob("*"))
        if path.is_file() or path.is_dir()
    ]


# --------------------------------------------------------------------------- #
# TC-10 — multi-driver goldens: apple_mail + the API 1 plugin double
# --------------------------------------------------------------------------- #

#: Default fixture config plus the plugin account: apple_mail + graph.
MULTI_DRIVER_CONFIG = (
    f'{DEFAULT_CONFIG}\n[scope."{PLUGIN_DRIVER}:{PLUGIN_ACCOUNT_LABEL}"]\n'
)


def _plugin_row(now, native_id: str, *, minutes_ago: float) -> dict:
    """One common-model row of the plugin double, relative to the fixture clock.

    The golden seed is deterministic: the fixture clock plus fixed offsets
    (-18 min P2 and -16 min P1) puts both plugin messages inside the first-run
    lookback window of ``new`` (``D`` = the newest Apple Mail message, -15 min).
    """
    date = int((now - timedelta(minutes=minutes_ago)).timestamp())
    return {
        "uid": native_id,
        "native_order_key": native_id,
        "global_message_id": 0,
        "subject": f"Plugin {native_id}",
        "sender_name": "Plugin Sender",
        "sender_address": "plugin@example.com",
        "date_sent": date,
        "date_received": date,
        "mailbox_id": "graph-inbox",
        "read": 0,
        "flagged": 0,
        "size": 10,
        "message_id": f"<{native_id}@plugin.example>",
        "has_attachments": False,
    }


class MultiDriverGoldenTest(IntegrationBase):
    """TC-10: ``search``/``new`` over ``apple_mail`` plus the plugin double.

    The registry seam is patched with an in-memory ``BackendRegistry`` holding the
    built-in entry points plus the plugin entry point, so the CLI loads the
    declared plugin without installing it.
    """

    def setUp(self) -> None:
        super().setUp()
        self.configure(MULTI_DRIVER_CONFIG)
        rows = [
            _plugin_row(self.fx.now, "P1", minutes_ago=16),
            _plugin_row(self.fx.now, "P2", minutes_ago=18),
        ]
        self.entry = FakeEntryPoint(PLUGIN_DRIVER, plugin=plugin_factory(rows=rows))
        self.registry = BackendRegistry(
            platform=sys.platform,
            entry_points=[*internal_entry_points(), self.entry],
        )

    @contextlib.contextmanager
    def plugin_registry(self):
        with mock.patch.object(cli, "BackendRegistry", lambda *a, **k: self.registry):
            yield

    def test_tc_10_01_search_merges_both_drivers(self) -> None:
        """TC-10.01: search golden with the two declared drivers (golden)."""
        with self.plugin_registry():
            payload = self.run_ok("search")
        uids = [message["uid"] for message in payload["messages"]]
        self.assertEqual(payload["count"], 14)
        self.assertEqual(
            uids[:4],
            [
                prefixed_uid(83170),
                prefixed_uid("P1", PLUGIN_DRIVER),
                prefixed_uid("P2", PLUGIN_DRIVER),
                prefixed_uid(83160),
            ],
        )
        self.assertEqual(self.entry.load_calls, 1, "the declared plugin is loaded once")
        self.assert_golden("search_multidriver.json", payload)

    def test_tc_10_02_new_merges_both_drivers(self) -> None:
        """TC-10.02: new golden over the merged first-run window (golden)."""
        with self.plugin_registry():
            payload = self.run_ok("new")
        self.assertEqual(
            [message["uid"] for message in payload["messages"]],
            [
                prefixed_uid(83160),
                prefixed_uid("P2", PLUGIN_DRIVER),
                prefixed_uid("P1", PLUGIN_DRIVER),
                prefixed_uid(83170),
            ],
        )
        self.assertEqual(
            payload["cursor"]["current"]["last_uid"], prefixed_uid(83170)
        )
        self.assert_golden("new_multidriver.json", payload)


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
        payload = self.run_ok("show", prefixed_uid(self.fake.item(key).entry_id, "outlook"))
        self.assertEqual(payload["message"]["uid"], prefixed_uid(self.fake.item(key).entry_id, "outlook"))
        return payload

    def test_tc_02_01_mailboxes(self) -> None:
        """TC-02.01: mailboxes of the golden profile (golden)."""
        payload = self.run_ok("mailboxes")
        self.assertEqual(
            payload["excluded_stores"],
            [{"label": "Exchange shared (Soporte)", "path": None, "reason": "shared_mailbox"}],
        )
        self.assertEqual(payload["warnings"], [OUTLOOK_STORE_EXCLUDED])
        (account,) = payload["accounts"]
        self.assertEqual(account["label"], "Exchange (ana.perez@example.com)")
        self.assertEqual(
            [entry["path"] for entry in account["mailboxes"]],
            ["INBOX", "Deleted Items", "Sent Items"],
        )
        self.assertTrue(all(set(entry) == {"path", "included"} for entry in account["mailboxes"]))
        full = self.run_ok("mailboxes", "--fields", "name,url,total,unread")
        inbox = full["accounts"][0]["mailboxes"][0]
        self.assertEqual(
            (inbox["path"], inbox["total"], inbox["unread"], inbox["included"]),
            ("INBOX", 3, 2, True),
        )
        self.assertEqual(inbox["name"], "INBOX")
        self.assertTrue(inbox["url"].startswith("outlook://"))
        _assert_golden(self, "outlook/mailboxes.json", payload, self.root)

    def test_tc_02_02_search(self) -> None:
        """TC-02.02: search of the golden profile (golden)."""
        payload = self.run_ok("search")
        self.assertEqual(
            [message["uid"] for message in payload["messages"]],
            [prefixed_uid(self.fake.item(key).entry_id, "outlook") for key in ("normal", "header_only", "smime_encrypted")],
        )
        for message in payload["messages"]:
            self.assertEqual(list(message), list(DEFAULT_ROW_FIELDS))
        self.assertEqual(payload["warnings"][0], OUTLOOK_STORE_EXCLUDED)
        full = self.run_ok("search", "--fields", "all")
        normal = full["messages"][0]
        self.assertEqual(normal["date_received"], "2026-11-02T09:54:09-04:00")
        self.assertEqual(normal["date_sent"], "2026-11-02T09:54:03-04:00")
        _assert_golden(self, "outlook/search.json", payload, self.root)

    def test_tc_02_03_show(self) -> None:
        """TC-02.03: show of the normal message with an attachment (golden)."""
        payload = self.show("normal")
        message = payload["message"]
        self.assertEqual(
            message["attachments"],
            [{"index": 1, "name": "factura-2026-10.pdf", "cached_path": None}],
        )
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
        self.assertEqual([message["uid"] for message in payload["messages"]], [prefixed_uid(normal, "outlook")])
        self.assertEqual(
            payload["warnings"],
            [
                OUTLOOK_STORE_EXCLUDED,
                "W_FIRST_RUN: first run: emitted the messages received in the last "
                "10min before the newest message",
            ],
        )
        self.assertIsNone(payload["cursor"]["previous"])
        self.assertEqual(payload["cursor"]["current"]["last_uid"], prefixed_uid(normal, "outlook"))
        state = StateStore(self.home, _all_installed).load()
        self.assertEqual(state.emitted_uids, (prefixed_uid(normal, "outlook"),))
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
    """Each line that starts with ``mailquery`` inside a code block of the recipe.

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


def _fake_with_attachment_message(fake):
    """Add the Outlook counterpart of Apple Mail 2714: To, Cc and a local attachment."""
    from tests.fakes import outlook as fake_outlook

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


class _AttachmentUidMixin:
    """Resolve a message with a known attachment on both backends (TC-04/TC-05/TC-08)."""

    def attachment_uid(self, backend: str) -> str:
        if backend == "outlook":
            return self.fake.item("complete").entry_id
        code, payload, stderr = self.run_backend(backend, "show", "2714")
        self.assertEqual(code, 0, f"{backend} show 2714: {payload} {stderr}")
        attachments = payload["message"]["attachments"]
        self.assertTrue(attachments, "the Apple Mail fixture message 2714 has no attachment")
        return str(payload["message"]["uid"])


class RecipeCommandTest(_AttachmentUidMixin, _BothBackendsCase):
    """TC-04 (PRD 21.2): every recipe command runs with exit 0 on both backends."""

    def outlook_fake(self):
        return _fake_with_attachment_message(super().outlook_fake())

    def assert_recipe(
        self, name: str, uid_command: tuple[str, ...], *, requires_attachment: bool = False
    ) -> None:
        commands = _recipe_commands(name)
        self.assertTrue(commands, f"no mailquery command in {name}")
        if requires_attachment:
            self.assertTrue(
                any(command and command[0] == "attachment" for command in commands),
                f"{name} must show at least one `mailquery attachment` command",
            )
        for backend in ("apple_mail", "outlook"):
            code, payload, stderr = self.run_backend(backend, *uid_command)
            self.assertEqual(code, 0, f"{backend} {uid_command}: {payload} {stderr}")
            self.assertTrue(payload["messages"], f"{backend} {uid_command}: no message for <uid>")
            uid = str(payload["messages"][0]["uid"])
            attachment_uid = None
            for command in commands:
                argv = list(command)
                if argv and argv[0] == "attachment":
                    if attachment_uid is None:
                        attachment_uid = self.attachment_uid(backend)
                    argv = [attachment_uid if arg == "<uid>" else arg for arg in argv]
                else:
                    argv = [uid if arg == "<uid>" else arg for arg in argv]
                with self.subTest(backend=backend, command=" ".join(command)):
                    code, payload, stderr = self.run_backend(backend, *argv)
                    self.assertEqual(code, 0, f"{payload} {stderr}")
                    self.assertIs(payload["ok"], True)

    def test_tc_04_01_new_mail_digest_commands_exit_0_on_both_backends(self) -> None:
        """TC-04.01: each command of 01-new-mail-digest.md exits 0 (<uid> from `new --peek`)."""
        self.assert_recipe("01-new-mail-digest.md", ("new", "--peek"))

    def test_tc_04_02_search_invoices_commands_exit_0_on_both_backends(self) -> None:
        """TC-04.02: each command of 02-search-invoices.md exits 0; `<uid>` has an attachment."""
        self.assert_recipe(
            "02-search-invoices.md", ("search", "--since", "1mo", "--has-attachments"),
            requires_attachment=True,
        )

    def test_tc_04_03_recipes_do_not_promise_remote_extraction_or_execution(self) -> None:
        """TC-04.03: recipes promise no remote extraction, no `--out` and no file execution."""
        for recipe in sorted(RECIPES_DIR.glob("*.md")):
            text = recipe.read_text(encoding="utf-8")
            with self.subTest(recipe=recipe.name):
                self.assertNotIn("--out", text)
                for promise in ("extracción remota", "extraccion remota", "remote extraction"):
                    self.assertNotIn(promise, text.lower())
                self.assertRegex(text, r"(?i)(nunca|no) (?:abrir|ejecutar|descargar)|never (?:open|execute|download)")


class JsonShapeParityTest(_AttachmentUidMixin, _BothBackendsCase):
    """TC-05 (RF-30): the same recursive set of JSON keys on both backends.

    The Outlook profile adds to ``item_matrix`` a message with To, Cc and a
    visible attachment (the counterpart of Apple Mail's uid 2714), so that the
    lists of both payloads have elements whose keys can be compared.
    """

    def outlook_fake(self):
        return _fake_with_attachment_message(super().outlook_fake())

    def assert_same_keys(self, payloads: dict[str, dict]) -> None:
        apple, outlook = (_key_paths(payloads[name]) for name in ("apple_mail", "outlook"))
        self.assertTrue(apple)
        self.assertEqual(
            (sorted(apple - outlook), sorted(outlook - apple)),
            ([], []),
            "keys only on Apple Mail / only on Outlook",
        )

    def test_tc_05_01_list_commands_have_the_same_keys(self) -> None:
        """TC-05.01: search/new/show/mailboxes share the recursive key set on both backends."""
        for label, argv in (
            ("search", ("search", "--limit", "200", "--fields", "all")),
            ("new", ("new",)),
            ("mailboxes", ("mailboxes",)),
            ("doctor", ("doctor", "--json")),
        ):
            with self.subTest(command=label):
                payloads = self.run_both_ok(*argv)
                if label == "search":
                    for payload in payloads.values():
                        self.assertTrue(any(message["cc"] for message in payload["messages"]))
                if label == "new":
                    for payload in payloads.values():
                        self.assertTrue(payload["messages"])
                self.assert_same_keys(payloads)
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

    def test_tc_05_02_attachment_success_and_error_have_the_same_keys(self) -> None:
        """TC-05.02: `attachment` success and error payloads share the key set on both backends."""
        successes = {}
        for backend in ("apple_mail", "outlook"):
            uid = self.attachment_uid(backend)
            code, payload, stderr = self.run_backend(backend, "attachment", uid, "--index", "1")
            self.assertEqual(code, 0, f"{backend} attachment: {payload} {stderr}")
            self.assertTrue(payload["attachments"], f"{backend}: no attachment extracted")
            self.assertIs(payload["attachments"][0]["saved"], True)
            successes[backend] = payload
        self.assert_same_keys(successes)
        errors = {}
        for backend in ("apple_mail", "outlook"):
            uid = self.attachment_uid(backend)
            code, payload, _stderr = self.run_backend(
                backend, "attachment", uid, "--index", "99"
            )
            self.assertEqual((code, payload["error"]["code"]), (2, "E_USAGE"))
            errors[backend] = payload
        self.assert_same_keys(errors)

    def test_tc_05_03_error_object_keeps_the_closed_shape(self) -> None:
        """TC-05.03: the error object is `{code, message, hint}` with no extra fields."""
        for backend in ("apple_mail", "outlook"):
            with self.subTest(backend=backend):
                code, payload, _stderr = self.run_backend(backend, "search", "--since", "banana")
                self.assertEqual((code, payload["error"]["code"]), (2, "E_BAD_TIME"))
                self.assertEqual(set(payload), {"ok", "command", "error"})
                self.assertEqual(set(payload["error"]), {"code", "message", "hint"})

# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# TC-07 — user documentation (PRD 21.2, 23.3)
# --------------------------------------------------------------------------- #

DOCS_ROOT = Path(__file__).resolve().parents[1]
README_EN = DOCS_ROOT / "README.md"
README_ES = DOCS_ROOT / "README.es.md"
SKILL_FILE = DOCS_ROOT / "skills" / "mailquery" / "SKILL.md"
SKILLS_README = DOCS_ROOT / "skills" / "README.md"
CONFIG_EXAMPLE = DOCS_ROOT / "docs" / "config.example.toml"
INSTALL_SH = DOCS_ROOT / "scripts" / "install.sh"
INSTALL_PS1 = DOCS_ROOT / "scripts" / "install.ps1"

COMMANDS = tuple(cli.COMMANDS)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _help_text(argv: list[str]) -> str:
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
        code = cli.main(list(argv))
    assert code == 0, f"{argv} exited {code}"
    return stdout.getvalue()


def _all_help_texts() -> dict[str, str]:
    texts = {"mailquery": _help_text(["--help"])}
    for command in COMMANDS:
        texts[command] = _help_text([command, "--help"])
    return texts


def _normalized(text: str) -> str:
    return " ".join(text.split())


#: A ``major.minor.patch`` version with an optional PEP 440 pre-release (``3.0.0a0``).
_VERSION = r"\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?"
#: ``mailquery 3.0.0`` presented as the final release (a pre-release such as
#: ``3.0.0a0`` is not the published 3.0.0).
_FINAL_3_0_0 = r"mailquery 3\.0\.0(?!(?:a|b|rc)\d)"

#: Stale patterns the 2.1 documentation retires.
_STALE_TEXT_PATTERNS: dict[str, re.Pattern[str]] = {
    "five commands": re.compile(r"five commands", re.IGNORECASE),
    "cinco comandos": re.compile(r"cinco comandos", re.IGNORECASE),
    "integer uid": re.compile(
        r"(?i)\buid\b[^\n.]{0,80}\b(?:integer|entero)\b|"
        r"\b(?:integer|entero)\b[^\n.]{0,40}\buid\b"
    ),
    "attachments name-only": re.compile(r'"attachments"\s*:\s*\[\{\s*"name"'),
    "published 3.0.0": re.compile(_FINAL_3_0_0),
    "baseline": re.compile(r"\bbaseline\b", re.IGNORECASE),
    "retention_days": re.compile(r"retention_days(?! was replaced by max_size_mb)"),
    "--out": re.compile(r"--out\b"),
    "list accounts, folders, counters": re.compile(
        r"list accounts, folders, counters", re.IGNORECASE
    ),
    "standard library only": re.compile(r"standard library\s+only", re.IGNORECASE),
    "solo biblioteca estándar": re.compile(
        r"solo biblioteca\s+estándar", re.IGNORECASE
    ),
    "preflight": re.compile(r"\bpreflight\b", re.IGNORECASE),
}

#: Text the README must document (DOC-01.03/05, AC-21).
_README_CONTRACT_FEATURES = (
    '[scope."<driver>',
    "[attachments]",
    "mailquery attachment",
    "--index",
    "--all",
    "--force",
    "cached_path",
    "index",
    "drivers:",
    "E_ATTACHMENT_BLOCKED",
    "E_ATTACHMENTS_DISABLED",
    "E_ATTACHMENT_UNAVAILABLE",
    "E_ATTACHMENT_UNREADABLE",
    "E_PLUGIN_INCOMPATIBLE",
    "E_PLUGIN_FAILED",
    "E_DRIVER_UNKNOWN",
    "E_IO",
    "~/.mailquery/attachments/",
    "pipx inject mailquery",
)

_EXPECTED_EXIT_LINE = (
    "Exit codes: 0 ok | 2 usage or config error | 3 environment error "
    "| 4 rejected query or blocked attachments | 5 busy or transient error "
    "| 6 mail client not running"
)


class _DocumentationCase(unittest.TestCase):
    def assert_no_stale_terms(self, label: str, text: str) -> None:
        for name, pattern in _STALE_TEXT_PATTERNS.items():
            match = pattern.search(text)
            self.assertIsNone(match, f"{label} contains the stale marker {name!r}: {match.group(0)!r}" if match else "")


# --------------------------------------------------------------------------- #
# DOC-01 — README.md (AC-21)
# --------------------------------------------------------------------------- #


class ReadmeDocumentationTest(_DocumentationCase):
    def test_doc_01_01_six_commands_without_five_commands(self) -> None:
        """DOC-01.01: README lists the six commands and no five-command wording."""
        text = _read(README_EN)
        for command in COMMANDS:
            with self.subTest(command=command):
                self.assertRegex(text, rf"`mailquery {command}\b|mailquery {command} ")
        self.assertIsNone(re.search(r"five commands", text, re.IGNORECASE))
        self.assertIsNone(re.search(r"cinco comandos", text, re.IGNORECASE))

    def test_doc_01_02_uid_is_a_prefixed_string_with_legacy_input(self) -> None:
        """DOC-01.02: README documents the prefixed string uid and the legacy input."""
        text = _read(README_EN)
        self.assertIn("<driver>:<native_id>", text)
        self.assertRegex(text, r"(?i)legacy")
        self.assertRegex(text, r"(?i)unprefixed")
        self.assertRegex(text, r'"uid":\s*"apple_mail:')
        for pattern in ("integer uid",):
            match = _STALE_TEXT_PATTERNS[pattern].search(text)
            self.assertIsNone(match, match.group(0) if match else "")

    def test_doc_01_03_documents_scope_attachments_doctor_and_version(self) -> None:
        """DOC-01.03: README covers [scope] with driver, [attachments], attachment and doctor/version."""
        text = _read(README_EN)
        for feature in _README_CONTRACT_FEATURES:
            with self.subTest(feature=feature):
                self.assertIn(feature, text)
        doctor_section = text[text.index("### `mailquery doctor") : text.index("### `mailquery mailboxes")]
        self.assertIn("`driver`", doctor_section)
        self.assertRegex(text, r"drivers: ")

    def test_doc_01_04_no_stale_marks(self) -> None:
        """DOC-01.04: README has no retired marks (five commands, baseline, integer uid, 3.0.0)."""
        self.assert_no_stale_terms("README.md", _read(README_EN))

    def test_doc_01_05_examples_match_the_contract(self) -> None:
        """DOC-01.05: README JSON/command examples match the implemented contract."""
        text = _read(README_EN)
        self.assertRegex(text, r'"uid":\s*"apple_mail:')
        self.assertRegex(text, r'"attachments":\s*\[\s*\{\s*"index"')
        self.assertIn('"cached_path"', text)
        self.assertRegex(text, r'"sanitized_name"')
        self.assertRegex(text, r"drivers: [^)\n]*(?:apple_mail|outlook) \d+\.\d+\.\d+")
        self.assertIn("mailquery attachment apple_mail:", text)


# --------------------------------------------------------------------------- #
# DOC-02 — README.es.md (AC-21)
# --------------------------------------------------------------------------- #


def _flags(text: str) -> set[str]:
    return set(re.findall(r"--[a-z][a-z0-9-]*", text))


def _home_paths(text: str) -> set[str]:
    return set(re.findall(r"~/\.mailquery/[A-Za-z0-9_./<>%-]+", text))


class ReadmeEsDocumentationTest(_DocumentationCase):
    def test_doc_02_01_parity_with_readme(self) -> None:
        """DOC-02.01: README.es.md has the same commands, flags, paths and exit codes."""
        english, spanish = _read(README_EN), _read(README_ES)
        for command in COMMANDS:
            with self.subTest(command=command):
                self.assertIn(command, spanish)
        self.assertEqual(_flags(english), _flags(spanish))
        self.assertEqual(_home_paths(english), _home_paths(spanish))
        for code in ("E_ATTACHMENT_BLOCKED", "E_ATTACHMENTS_DISABLED", "E_IO"):
            with self.subTest(code=code):
                self.assertIn(code, spanish)

    def test_doc_02_02_no_stale_marks(self) -> None:
        """DOC-02.02: README.es.md has no retired marks."""
        self.assert_no_stale_terms("README.es.md", _read(README_ES))

    def test_doc_02_03_prefixed_uid_and_attachment_examples(self) -> None:
        """DOC-02.03: Spanish examples use the prefixed uid and `attachment`."""
        text = _read(README_ES)
        self.assertRegex(text, r'"uid":\s*"apple_mail:')
        self.assertIn("mailquery attachment apple_mail:", text)
        self.assertIn("<driver>:<native_id>", text)


# --------------------------------------------------------------------------- #
# DOC-03 — cross-document coherence (AC-21)
# --------------------------------------------------------------------------- #


class DocumentationCoherenceTest(_DocumentationCase):
    def test_doc_03_01_documents_and_help_agree(self) -> None:
        """DOC-03.01: READMEs, recipes, SKILL, config example and helps agree."""
        readme, spanish = _read(README_EN), _read(README_ES)
        skill = _read(SKILL_FILE)
        config = _read(CONFIG_EXAMPLE)
        recipes = _read(RECIPES_DIR / "02-search-invoices.md")
        helps = _all_help_texts()
        for document, label in ((readme, "README.md"), (spanish, "README.es.md"), (skill, "SKILL.md")):
            for command in COMMANDS:
                with self.subTest(document=label, command=command):
                    self.assertIn(command, document)
        exit_line = _normalized(helps["mailquery"])
        self.assertIn(_EXPECTED_EXIT_LINE, exit_line)
        self.assertIn("blocked attachments", exit_line)
        self.assertIn("blocked attachments", readme)
        self.assertIn("adjuntos bloqueados", spanish)
        for document, label in (
            (readme, "README.md"),
            (spanish, "README.es.md"),
            (skill, "SKILL.md"),
        ):
            with self.subTest(document=label):
                self.assertIn("<driver>:<native_id>", document)
                self.assertIn("~/.mailquery/attachments/", document)
        self.assertIn('[scope."<driver>:', config)
        self.assertIn("~/.mailquery/attachments/", config)
        for document, label in ((readme, "README.md"), (spanish, "README.es.md"), (skill, "SKILL.md")):
            with self.subTest(document=label):
                self.assertIn("<driver>:<native_id>", document)
        self.assertIn("~/.mailquery/attachments/", recipes)
        self.assertIn("~/.mailquery/attachments/", helps["attachment"])

    def test_doc_03_02_no_document_promises_write_outside_home_or_core_network(self) -> None:
        """DOC-03.02: no document promises writes outside ~/.mailquery or core network."""
        readme, spanish = _read(README_EN), _read(README_ES)
        skill = _read(SKILL_FILE)
        config = _read(CONFIG_EXAMPLE)
        for document, label in (
            (readme, "README.md"),
            (spanish, "README.es.md"),
            (skill, "SKILL.md"),
            (config, "config.example.toml"),
            *((_read(path), path.name) for path in sorted(RECIPES_DIR.glob("*.md"))),
        ):
            with self.subTest(document=label):
                self.assertNotIn("--out", document)
                self.assertIn("~/.mailquery", document)
        for text, label in ((readme, "README.md"), (spanish, "README.es.md")):
            with self.subTest(document=label):
                self.assertRegex(text, r"(?i)no network|sin red|never (?:opens?|uses?) (?:the )?network")
                self.assertRegex(text, r"(?is)only\s+writes\s+(?:inside|under)\s+`?~/\.mailquery|solo\s+escribe\s+dentro\s+de\s+`?~/\.mailquery")
        self.assertRegex(skill, r"(?i)read-only|solo lectura")

    def test_doc_03_03_version_examples_use_the_current_version(self) -> None:
        """DOC-03.03: version examples use `__version__` with `drivers:` and never 3.0.0 as current."""
        for path in (README_EN, README_ES):
            text = _read(path)
            lines = re.findall(rf"mailquery {_VERSION} \([^\n]*\)", text)
            with self.subTest(document=path.name):
                self.assertTrue(lines, f"{path.name} shows no version example")
                for line in lines:
                    self.assertIn("drivers:", line)
                    self.assertIn(__version__, line)
                self.assertNotRegex(text, _FINAL_3_0_0)
                if "3.0.0" in text:
                    self.assertRegex(
                        text,
                        r"(?is)(?:future|futuro)[^.]{0,80}3\.0\.0|"
                        r"3\.0\.0[^.]{0,80}(?:not (?:yet )?released|no publicado)",
                    )


# --------------------------------------------------------------------------- #
# DOC-04 — skills/mailquery/SKILL.md (AC-21)
# --------------------------------------------------------------------------- #


class SkillDocumentationTest(_DocumentationCase):
    def test_doc_04_01_skill_documents_the_new_contract(self) -> None:
        """DOC-04.01: SKILL has six commands, string uid, show.attachments and the new errors."""
        text = _read(SKILL_FILE)
        for command in COMMANDS:
            with self.subTest(command=command):
                self.assertIn(command, text)
        for feature in (
            "<driver>:<native_id>",
            "cached_path",
            "E_ATTACHMENT_BLOCKED",
            "E_ATTACHMENT_UNAVAILABLE",
            "E_ATTACHMENT_UNREADABLE",
            "E_DRIVER_UNKNOWN",
            "E_PLUGIN_FAILED",
        ):
            with self.subTest(feature=feature):
                self.assertIn(feature, text)

    def test_doc_04_02_skill_forbids_opening_or_executing_recovered_files(self) -> None:
        """DOC-04.02: the harness must not open/execute recovered files and blocking is whole-message."""
        text = _read(SKILL_FILE)
        self.assertRegex(text, r"(?i)never (?:open|execute)|do not (?:open|execute)|nunca (?:abrir|ejecutar)")
        self.assertRegex(text, r"(?i)whole message|message is blocked|mensaje completo")

    def test_doc_04_03_skill_does_not_describe_an_integer_uid_or_omit_attachment(self) -> None:
        """DOC-04.03: SKILL does not present an integer uid and does not omit `attachment`."""
        text = _read(SKILL_FILE)
        self.assertIn("attachment", text)
        match = _STALE_TEXT_PATTERNS["integer uid"].search(text)
        self.assertIsNone(match, match.group(0) if match else "")


# --------------------------------------------------------------------------- #
# DOC-05 — CLI help (AC-21)
# --------------------------------------------------------------------------- #


class HelpDocumentationTest(_DocumentationCase):
    def test_doc_05_01_root_help_lists_six_commands_and_the_exit_line(self) -> None:
        """DOC-05.01: the root help lists the six commands and the PRD §12.7 exit line."""
        text = _all_help_texts()["mailquery"]
        self.assertIn("Commands:", text)
        for command in COMMANDS:
            with self.subTest(command=command):
                self.assertRegex(text, rf"(?m)^  {command}\s")
        self.assertIn(_EXPECTED_EXIT_LINE, _normalized(text))

    def test_doc_05_02_attachment_help_matches_the_prd(self) -> None:
        """DOC-05.02: `attachment --help` matches PRD §12.7."""
        text = _all_help_texts()["attachment"]
        normalized = _normalized(text)
        self.assertIn(
            "usage: mailquery attachment [-h] (--index N | --all) [--force] <uid>",
            normalized,
        )
        self.assertIn("Recover local attachments of one message into ~/.mailquery/attachments/", normalized)
        for section in ("Positional arguments:", "Options:", "Examples:", "Notes:"):
            with self.subTest(section=section):
                self.assertIn(section, text)
        for option in ("--index N", "--all", "--force"):
            with self.subTest(option=option):
                self.assertIn(option, text)
        for note in (
            "E_ATTACHMENT_BLOCKED (exit 4)",
            "E_ATTACHMENT_UNAVAILABLE (exit 3)",
            "E_ATTACHMENT_UNREADABLE (exit 3)",
            "0600",
        ):
            with self.subTest(note=note):
                self.assertIn(note, normalized)

    def test_doc_05_03_seven_help_invocations_parse(self) -> None:
        """DOC-05.03: the root help and the six subcommand helps (7 invocations) parse."""
        for argv in (["--help"], *([command, "--help"] for command in COMMANDS)):
            with self.subTest(argv=argv):
                text = _help_text(argv)
                self.assertTrue(text.strip())
        self.assertEqual(len(COMMANDS), 6)

    def test_doc_05_04_help_has_no_stale_terms(self) -> None:
        """DOC-05.04: no help mentions five commands or an integer uid (module docstring included)."""
        for label, text in _all_help_texts().items():
            self.assert_no_stale_terms(f"{label} --help", text)
        self.assert_no_stale_terms("cli.py docstring", cli.__doc__ or "")


# --------------------------------------------------------------------------- #
# DOC-06 — docs/config.example.toml (AC-21)
# --------------------------------------------------------------------------- #


class ConfigExampleTest(_DocumentationCase):
    def _load(self, text: str):
        with tempfile.TemporaryDirectory(prefix="mailquery-config-example-") as tmp:
            home = Path(tmp) / ".mailquery"
            home.mkdir()
            (home / "config.toml").write_text(text, encoding="utf-8")
            return load_config(home)

    def test_doc_06_01_parses_with_the_real_loader_and_documents_attachments(self) -> None:
        """DOC-06.01: the example parses with the real loader and documents [attachments] defaults."""
        template = _read(CONFIG_EXAMPLE)
        self.assertIn("# [attachments]", template)
        for default in ("enabled = true", "max_file_size_mb = 100", "max_total_size_mb = 200", "max_count = 50"):
            with self.subTest(default=default):
                self.assertIn(default, template)
        parsed = self._load(template)
        self.assertEqual(parsed.attachments.enabled, True)
        self.assertEqual(parsed.attachments.max_file_size_mb, 100)
        self.assertEqual(parsed.attachments.max_total_size_mb, 200)
        self.assertEqual(parsed.attachments.max_count, 50)
        explicit = (
            "[attachments]\nenabled = true\nmax_file_size_mb = 100\n"
            "max_total_size_mb = 200\nmax_count = 50\n"
        )
        parsed = self._load(explicit)
        self.assertEqual(parsed.attachments.max_total_size_mb, 200)

    def test_doc_06_02_scope_examples_with_and_without_driver_prefix(self) -> None:
        """DOC-06.02: the example shows one prefixed [scope] block and one unprefixed block."""
        template = _read(CONFIG_EXAMPLE)
        self.assertRegex(template, r'\[scope\."(?:<driver>|apple_mail|outlook|graph):')
        self.assertRegex(template, r'\[scope\."(?!<driver>|apple_mail:|outlook:|graph:)[^"]+"\]')
        self.assertEqual(tomllib.loads(template), {}, "the template must keep all sections commented")
        documented = set(re.findall(r"(?m)^#\s*\[([a-z][a-z0-9_-]*)", template))
        self.assertTrue(
            documented <= {"logging", "search", "new", "attachments", "content", "scope"}
        )

    def test_doc_06_04_example_documents_content_url_display(self) -> None:
        """DOC-06.04: the example carries the commented [content] block and it loads as neutralize."""
        template = _read(CONFIG_EXAMPLE)
        self.assertIn("# [content]", template)
        self.assertIn('# url_display = "neutralize"', template)
        explicit = (
            "[content]\n"
            'url_display = "neutralize"   # neutralize | keep | strip (--strip-links forces strip)\n'
        )
        parsed = self._load(explicit)
        self.assertEqual(parsed.content.url_display, "neutralize")

    def test_doc_06_05_example_documents_the_attachment_timeout(self) -> None:
        """DOC-06.05: the [attachments] block documents timeout_seconds and it loads as 60."""
        template = _read(CONFIG_EXAMPLE)
        self.assertRegex(template, r"(?m)^#\s*timeout_seconds = 60\b")
        self.assertIn('# timeout_seconds = 60', template)
        explicit = (
            "[attachments]\nenabled = true\nmax_file_size_mb = 100\n"
            "max_total_size_mb = 200\nmax_count = 50\ntimeout_seconds = 60\n"
        )
        parsed = self._load(explicit)
        self.assertEqual(parsed.attachments.timeout_seconds, 60)
        self.assertEqual(tomllib.loads(template), {}, "the template must keep all sections commented")

    def test_doc_06_03_no_previous_version_keys(self) -> None:
        """DOC-06.03: the example keeps no keys retired by previous versions."""
        template = _read(CONFIG_EXAMPLE)
        for stale in ("retention_days", "[backend.", "[driver.", "--out"):
            with self.subTest(stale=stale):
                self.assertNotIn(stale, template)
        self.assertIsNone(re.search(r"(?m)^\s*backend\s*=", template))


# --------------------------------------------------------------------------- #
# TC-07 — user documentation (PRD 21.2, 23.3)
# --------------------------------------------------------------------------- #


class UserDocumentationTest(_DocumentationCase):
    """TC-07: documentation and helps are coherent with the 2.1 contract."""

    def test_tc_07_01_root_and_six_helps_parse(self) -> None:
        """TC-07.01: the root help and the six subcommand helps (7 invocations) parse."""
        self.assertEqual(len(COMMANDS), 6)
        for argv in (["--help"], *([command, "--help"] for command in COMMANDS)):
            with self.subTest(argv=argv):
                self.assertTrue(_help_text(argv).strip())

    def test_tc_07_02_attachment_help_matches_the_prd(self) -> None:
        """TC-07.02: `attachment --help` matches PRD §12.7."""
        normalized = _normalized(_all_help_texts()["attachment"])
        self.assertIn("usage: mailquery attachment [-h] (--index N | --all) [--force] <uid>", normalized)
        self.assertIn("E_ATTACHMENT_BLOCKED (exit 4)", normalized)

    def test_tc_07_03_documents_have_no_retired_terms_and_recipes_cover_exits(self) -> None:
        """TC-07.03: docs/helps have no retired terms; recipes cover exits 3, 5 and 6."""
        for path in (README_EN, README_ES, SKILL_FILE, SKILLS_README, CONFIG_EXAMPLE):
            with self.subTest(document=path.name):
                self.assert_no_stale_terms(path.name, _read(path))
        for path in sorted(RECIPES_DIR.glob("*.md")):
            with self.subTest(document=path.name):
                self.assert_no_stale_terms(path.name, _read(path))
        for label, text in _all_help_texts().items():
            self.assert_no_stale_terms(f"{label} --help", text)
        self.assert_no_stale_terms("cli.py docstring", cli.__doc__ or "")
        self.assertEqual(len(sorted(RECIPES_DIR.glob("*.md"))), 2)
        for recipe in sorted(RECIPES_DIR.glob("*.md")):
            text = _read(recipe)
            for code in ("3", "5", "6"):
                with self.subTest(recipe=recipe.name, exit=code):
                    self.assertIsNotNone(
                        re.search(rf"exit {code}(?!\d)|`{code}`", text),
                        f"no mention of exit {code}",
                    )

    def test_tc_07_04_no_document_or_help_promises_integer_uid_or_outside_writes(self) -> None:
        """TC-07.04: no help/document shows an integer uid or promises writes outside ~/.mailquery."""
        text = _read(README_EN) + _read(README_ES) + _read(SKILL_FILE)
        text += "".join(_all_help_texts().values())
        match = _STALE_TEXT_PATTERNS["integer uid"].search(text)
        self.assertIsNone(match, match.group(0) if match else "")
        for document, label in ((_read(README_EN), "README.md"), (_read(README_ES), "README.es.md")):
            self.assertNotIn("--out", document)
            self.assertIsNone(
                re.search(
                    r"(?is)(?:writes?|escribe)\b[^.]{0,40}?\b(?:outside|fuera de)\b"
                    r"(?!\s*`?~/\.mailquery)",
                    document,
                )
            )


if __name__ == "__main__":  # pragma: no cover - manual runs
    unittest.main()

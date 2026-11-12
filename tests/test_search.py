"""Unit tests for :mod:`mailquery.search` (PRD 9.3, 9.4, 12, 18).

Two layers are covered:

* the pure helpers (``parse_relative_time``, ``wildcard_to_regex``,
  ``matches``) that do not need a store at all;
* the four commands (``search``/``new``/``show``/``mailboxes``) against the
  synthetic Apple Mail fixture, including wildcard/substring semantics,
  relative dates, state filters, dedupe with ``duplicate_count``, pagination
  and truncation, bounded ``--text`` scans, the ``new`` cursor/ring semantics,
  message detail and the mailbox catalog.

Every path is a fixture path: the tests never read ``~/Library/Mail``,
``~/Library/Accounts`` or the real ``~/.mailquery``.
"""

from __future__ import annotations

import dataclasses
import sqlite3
import unittest
from datetime import datetime, timedelta
from unittest import mock

from mailquery import emlx, output, search
from mailquery.accounts import AccountLabels
from mailquery.backends.apple_mail import AppleMailBackend
from mailquery.config import (
    Config,
    LoggingConfig,
    NewConfig,
    ScopeEntry,
    SearchConfig,
    load_config,
)
from mailquery.errors import MailqueryError
from mailquery.state import StateStore
from mailquery.store import open_store
from tests.fixtures import make_fixtures
from tests.fixtures.make_fixtures import (
    ACCOUNT_GMAIL,
    ACCOUNT_ICLOUD,
    ACCOUNT_LOCAL,
    DEFAULT_CONFIG,
    GMAIL_LABEL,
    ICLOUD_LABEL,
    LOCAL_LABEL,
    MAILBOX_URLS,
    UID_DATE_FUTURE,
    UID_DATE_HUGE,
    UID_DATE_NULL,
    UID_DATE_ZERO,
    UID_DELETED,
    UID_MISSING_EMLX_ATTACH,
    UID_SMIME_ENCRYPTED,
    UID_SMIME_SIGNED,
    FixturePaths,
    prefixed_uid,
    build_store,
    write_config,
    write_state,
)
from tests.fakes.plugin import (
    ACCOUNT_LABEL as PLUGIN_ACCOUNT_LABEL,
    ACCOUNT_UUID as PLUGIN_ACCOUNT_UUID,
    DEFAULT_MAILBOXES as PLUGIN_MAILBOXES,
    DRIVER as PLUGIN_DRIVER,
    FakePluginBackend,
)
from tests.mocks import accounts_db_unavailable

ICLOUD_ONLY = f'[scope."{ICLOUD_LABEL}"]\n'

ICLOUD_FACTURAS_ARCHIVO = (
    f'[scope."{ICLOUD_LABEL}"]\nmailbox_list = ["Facturas", "Archivo"]\n'
)

ICLOUD_WITH_ARCHIVO = f'[scope."{ICLOUD_LABEL}"]\nmailbox_list = ["Archivo"]\n'

ICLOUD_WITH_FACTURAS = f'[scope."{ICLOUD_LABEL}"]\nmailbox_list = ["Facturas"]\n'

DEDUPE_CONFIG = (
    ICLOUD_FACTURAS_ARCHIVO
    + "\n"
    + f'[scope."{GMAIL_LABEL}"]\nmailbox_list = ["[Gmail]/All Mail"]\n'
)

DEFAULT_UIDS = [
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

MESSAGE_KEYS = {
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


def _all_installed(driver: str) -> bool:
    return True


def warning_codes(warnings: list[str]) -> list[str]:
    return [str(warning).split(":", 1)[0] for warning in warnings]


# --------------------------------------------------------------------------- #
# Pure helpers (no store needed)
# --------------------------------------------------------------------------- #


class PureHelpersTest(unittest.TestCase):
    """Wildcard, substring and relative-time helpers."""

    def setUp(self) -> None:
        self.now = datetime(2026, 11, 2, 12, 0, 0)

    def test_parse_relative_time_iso_date_is_local_midnight(self) -> None:
        parsed = search.parse_relative_time("2026-11-01", self.now)
        self.assertEqual(parsed, datetime(2026, 11, 1).timestamp())

    def test_parse_relative_time_iso_datetime_with_offset(self) -> None:
        expected = datetime.fromisoformat("2026-11-01T22:54:03+00:00").timestamp()
        self.assertEqual(
            search.parse_relative_time("2026-11-01T22:54:03Z", self.now), expected
        )
        self.assertEqual(
            search.parse_relative_time("2026-11-01T22:54:03+00:00", self.now),
            expected,
        )

    def test_parse_relative_time_offsets(self) -> None:
        offsets = {
            "30min": 30 * 60,
            "24h": 24 * 60 * 60,
            "7d": 7 * 24 * 60 * 60,
            "1w": 7 * 24 * 60 * 60,
            "2w": 14 * 24 * 60 * 60,
            "1mo": 30 * 24 * 60 * 60,
            "2mo": 60 * 24 * 60 * 60,
            "6mo": 180 * 24 * 60 * 60,
            "1y": 365 * 24 * 60 * 60,
        }
        for value, seconds in offsets.items():
            with self.subTest(value=value):
                self.assertEqual(
                    search.parse_relative_time(value, self.now),
                    self.now.timestamp() - seconds,
                )

    def test_parse_relative_time_today_yesterday_now(self) -> None:
        self.assertEqual(
            search.parse_relative_time("now", self.now), self.now.timestamp()
        )
        self.assertEqual(
            search.parse_relative_time("today", self.now),
            datetime(2026, 11, 2).timestamp(),
        )
        self.assertEqual(
            search.parse_relative_time("yesterday", self.now),
            datetime(2026, 11, 1).timestamp(),
        )

    def test_parse_relative_time_is_case_insensitive(self) -> None:
        self.assertEqual(
            search.parse_relative_time("TODAY", self.now),
            datetime(2026, 11, 2).timestamp(),
        )

    def test_parse_relative_time_rejects_invalid_values(self) -> None:
        for value in ("", "banana", "7", "1.5h", "-3d", "2026-13-01", "1 fortnight"):
            with self.subTest(value=value):
                with self.assertRaises(MailqueryError) as context:
                    search.parse_relative_time(value, self.now)
                self.assertEqual(context.exception.code, "E_BAD_TIME")
                self.assertEqual(context.exception.exit_code, 2)

    def test_wildcard_to_regex_translates_and_escapes(self) -> None:
        self.assertEqual(search.wildcard_to_regex("*factura*"), ".*factura.*")
        self.assertEqual(search.wildcard_to_regex("?nvoice"), ".nvoice")
        self.assertEqual(search.wildcard_to_regex("a.b+c"), r"a\.b\+c")
        self.assertEqual(search.wildcard_to_regex("plain"), "plain")
        self.assertEqual(search.wildcard_to_regex(""), "")

    def test_ut_sr_01_01_substring_without_wildcards(self) -> None:
        """UT-SR-01.01: a value without wildcards is matched as a substring."""
        self.assertTrue(search.matches("invoice", "Invoice 2026-10"))
        self.assertFalse(search.matches("invoice", "Factura septiembre"))
        self.assertTrue(search.matches("", "anything"))

    def test_ut_sr_01_02_star_wildcard_matches_any_sequence(self) -> None:
        """UT-SR-01.02: ``*factura*`` matches any sequence around the word."""
        self.assertTrue(search.matches("*factura*", "La Factura de septiembre"))
        self.assertTrue(search.matches("*2026-10*", "Invoice 2026-10"))
        self.assertFalse(search.matches("*2026-11*", "Invoice 2026-10"))

    def test_ut_sr_01_03_pattern_is_not_anchored(self) -> None:
        """UT-SR-01.03: ``factura*`` matches anywhere in the text (no anchor)."""
        self.assertTrue(search.matches("factura*", "La factura de septiembre"))
        self.assertTrue(search.matches("factura*", "Adjuntamos la factura"))
        self.assertTrue(search.matches("*factura", "factura de septiembre"))

    def test_ut_sr_01_04_question_mark_matches_one_character(self) -> None:
        """UT-SR-01.04: ``?actura`` matches exactly one character."""
        self.assertTrue(search.matches("?actura", "Factura"))
        self.assertTrue(search.matches("f?ctura", "factura"))
        self.assertFalse(search.matches("f?ctura", "fctura"))

    def test_ut_sr_01_05_match_is_case_insensitive(self) -> None:
        """UT-SR-01.05: ``FACTURA`` matches ``factura``."""
        self.assertTrue(search.matches("FACTURA", "la factura"))
        self.assertTrue(search.matches("INVOICE", "invoice 2026-10"))
        self.assertTrue(search.matches("septiembre", "Septiembre"))

    def test_ut_sr_01_06_match_is_accent_insensitive(self) -> None:
        """UT-SR-01.06: ``fáctura`` matches ``factura`` (and the other way round)."""
        self.assertTrue(search.matches("fáctura", "factura"))
        self.assertTrue(search.matches("informacion", "Información mensual"))
        self.assertTrue(search.matches("INFORMACIÓN", "informacion mensual"))

    def test_ut_sr_01_07_regex_characters_are_literals(self) -> None:
        """UT-SR-01.07: ``[``, ``.`` and ``(`` are literal characters."""
        self.assertTrue(search.matches("a.b", "a.b"))
        self.assertFalse(search.matches("a.b", "axb"))
        self.assertTrue(search.matches("invoice (2026)", "invoice (2026)"))
        self.assertFalse(search.matches("invoice (2026)", "invoice 2026"))
        self.assertTrue(search.matches("a[b", "xa[by"))
        self.assertFalse(search.matches("a[b", "ab"))

    def test_filter_terms_follow_the_two_rules_of_the_prd(self) -> None:
        # --subject: terms split on spaces, with or without wildcards (PRD 12.2).
        self.assertEqual(
            search._filter_terms(("invoice 2026",), split=True), ("invoice", "2026")
        )
        self.assertEqual(
            search._filter_terms(("*invoice 2026*",), split=True),
            ("*invoice", "2026*"),
        )
        self.assertEqual(
            search._filter_terms(("  a  b ", "*x*"), split=True), ("a", "b", "*x*")
        )
        # --text/--from/--to/--cc: the whole value is one pattern.
        self.assertEqual(
            search._filter_terms(("invoice 2026",)), ("invoice 2026",)
        )
        self.assertEqual(
            search._filter_terms(("*invoice 2026*", " a  b ")),
            ("*invoice 2026*", "a  b"),
        )
        # Empty values never narrow anything.
        self.assertEqual(search._filter_terms(("", "   ")), ())
        self.assertEqual(search._filter_terms(("", "   "), split=True), ())


# --------------------------------------------------------------------------- #
# Fixture-backed base class
# --------------------------------------------------------------------------- #


class SearchFixtureTest(unittest.TestCase):
    """Base class that opens the synthetic store, labels and config."""

    fx: FixturePaths

    @classmethod
    def setUpClass(cls) -> None:
        cls.fx = build_store()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.fx.cleanup()

    def setUp(self) -> None:
        write_config(self.fx.home, DEFAULT_CONFIG)
        self.store = open_store(
            mail_root=self.fx.mail_root, tmp_root=self.fx.home / "tmp"
        )
        self.addCleanup(self.store.close)
        self.labels = AccountLabels(
            self.fx.accounts_db, tmp_dir=self.fx.home / "tmp"
        )
        self.backend = AppleMailBackend(self.store, self.labels)
        self.config = load_config(self.fx.home)

    # -- helpers ----------------------------------------------------------- #

    def use_config(self, content: str) -> Config:
        write_config(self.fx.home, content)
        self.config = load_config(self.fx.home)
        return self.config

    def fresh_state(self) -> StateStore:
        path = self.fx.home / "state.json"
        path.unlink(missing_ok=True)
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        return StateStore(self.fx.home, _all_installed)

    def seed_state(
        self,
        *,
        age: timedelta = timedelta(hours=2),
        last_uid: int = 1,
        lookback_seconds: int = 600,
        emitted_uids: tuple[int, ...] = (),
        last_date_received: int | None = None,
    ) -> StateStore:
        """Seed a schema-2 ``state.json`` from fixture-native Apple Mail uids."""
        state = self.fresh_state()
        if last_date_received is None:
            last_date_received = int((self.fx.now - age).timestamp())
        write_state(
            self.fx.home,
            {
                "schema": 2,
                "updated_at": "",
                "last_run": None,
                "cursor": {
                    "last_date_received": last_date_received,
                    "last_uid": prefixed_uid(last_uid),
                    "lookback_seconds": lookback_seconds,
                },
                "emitted_uids": [prefixed_uid(uid) for uid in emitted_uids],
            },
        )
        return state

    def use_lookback(self, text: str, seconds: int) -> Config:
        """Replace ``[new].lookback`` of the loaded config (no file involved)."""
        self.config = dataclasses.replace(
            self.config,
            new=dataclasses.replace(
                self.config.new, lookback=text, lookback_seconds=seconds
            ),
        )
        return self.config

    def run_search(self, **filters: object) -> dict:
        return search.run_search(
            self.backend, self.config, search.Filters(**filters)
        )

    def multi_driver_config(self, *, mailbox_list: tuple[str, ...] = ()) -> Config:
        """The loaded config plus the plugin account (no config.toml roundtrip)."""
        scopes = self.config.scopes + (
            ScopeEntry(
                key=f"{PLUGIN_DRIVER}:{PLUGIN_ACCOUNT_LABEL}",
                driver=PLUGIN_DRIVER,
                account=PLUGIN_ACCOUNT_LABEL,
                mailbox_list=mailbox_list,
            ),
        )
        return dataclasses.replace(self.config, scopes=scopes)

    def plugin_row(self, native_id: str, *, minutes_ago: float, mailbox_id: str = "graph-inbox"):
        date = int((self.fx.now - timedelta(minutes=minutes_ago)).timestamp())
        return {
            "uid": native_id,
            "native_order_key": native_id,
            "global_message_id": 0,
            "subject": f"Plugin {native_id}",
            "sender_name": "Plugin Sender",
            "sender_address": "plugin@example.com",
            "date_sent": date,
            "date_received": date,
            "mailbox_id": mailbox_id,
            "read": 0,
            "flagged": 0,
            "size": 10,
            "message_id": f"<{native_id}@plugin.example>",
            "has_attachments": False,
        }

    @staticmethod
    def uids(result: dict) -> list[str]:
        return [message["uid"] for message in result["messages"]]

    def message_by_uid(self, result: dict, uid: int) -> dict:
        """Return the message whose emitted prefixed uid matches ``uid``."""
        wanted = prefixed_uid(uid)
        for message in result["messages"]:
            if message["uid"] == wanted:
                return message
        raise AssertionError(f"uid {wanted} not in result: {self.uids(result)}")


class ExtendedSearchFixtureTest(SearchFixtureTest):
    """Same base, over ``build_store(extended=True)`` (only ``setUpClass`` changes)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.fx = build_store(extended=True)


# --------------------------------------------------------------------------- #
# search (metadata)
# --------------------------------------------------------------------------- #


class SearchMetadataTest(SearchFixtureTest):
    """Metadata search: scope, filters, ordering, snippets, dedupe, limits."""

    def test_result_shape_and_default_scope(self) -> None:
        result = self.run_search()
        self.assertEqual(
            set(result),
            {"count", "truncated", "hint", "messages", "scan", "warnings"},
        )
        for forbidden in ("ok", "command", "generated_at"):
            self.assertNotIn(forbidden, result)
        self.assertEqual(result["count"], 12)
        self.assertEqual(result["count"], len(result["messages"]))
        self.assertFalse(result["truncated"])
        self.assertIsNone(result["hint"])
        # The returned page includes the missing and the corrupt .emlx message.
        self.assertEqual(
            warning_codes(result["warnings"]),
            ["W_EMLX_MISSING", "W_EMLX_CORRUPT"],
        )
        self.assertEqual(set(result["scan"]), {"mode", "candidates", "messages_read", "duration_ms"})
        self.assertEqual(result["scan"]["mode"], "metadata")
        self.assertEqual(result["scan"]["candidates"], 12)
        self.assertEqual(result["scan"]["messages_read"], 11)
        self.assertIsInstance(result["scan"]["duration_ms"], int)
        self.assertGreaterEqual(result["scan"]["duration_ms"], 0)
        for message in result["messages"]:
            self.assertEqual(set(message), MESSAGE_KEYS)

    def test_total_order_by_date_received_desc_then_rowid_desc(self) -> None:
        result = self.run_search()
        self.assertEqual(self.uids(result), DEFAULT_UIDS)
        received = [message["date_received"] for message in result["messages"]]
        self.assertEqual(received, sorted(received, reverse=True))

    def test_gmail_inbox_membership_via_labels(self) -> None:
        result = self.run_search(subject=("Gmail labelled",))
        self.assertEqual(self.uids(result), [prefixed_uid(83160)])
        message = result["messages"][0]
        self.assertEqual(message["mailbox"]["name"], "INBOX")
        self.assertEqual(message["mailbox"]["path"], "INBOX")
        self.assertEqual(message["mailbox"]["account"]["uuid"], ACCOUNT_GMAIL)
        self.assertEqual(
            message["mailbox"]["account"]["label"], GMAIL_LABEL
        )
        self.assertTrue(message["body"]["available"])
        self.assertIn("labels table", message["snippet"])

        result = self.run_search(subject=("Gmail unread",))
        self.assertEqual(self.uids(result), [prefixed_uid(83210)])
        self.assertEqual(result["messages"][0]["mailbox"]["name"], "INBOX")

    def test_subject_substring_and_wildcards(self) -> None:
        cases = {
            ("invoice",): [prefixed_uid(2714)],
            ("INVOICE",): [prefixed_uid(2714)],
            ("*factura*",): [prefixed_uid(79658)],
            ("?nvoice",): [prefixed_uid(2714)],
            ("*2026-10*",): [prefixed_uid(2714)],
            ("zzz-no-match",): [],
        }
        for patterns, expected in cases.items():
            with self.subTest(patterns=patterns):
                self.assertEqual(self.uids(self.run_search(subject=patterns)), expected)

    def test_subject_terms_are_and(self) -> None:
        self.assertEqual(
            self.uids(self.run_search(subject=("invoice 2026",))), [prefixed_uid(2714)]
        )
        self.assertEqual(self.uids(self.run_search(subject=("invoice 2025",))), [])
        # A wildcard value is one pattern, so the phrase is matched literally.
        self.assertEqual(
            self.uids(self.run_search(subject=("*invoice 2026*",))), [prefixed_uid(2714)]
        )
        # Repeating the flag is AND too.
        self.assertEqual(
            self.uids(self.run_search(subject=("invoice", "2026"))), [prefixed_uid(2714)]
        )

    def test_ut_sr_02_01_subject_terms_with_wildcards_are_and(self) -> None:
        """UT-SR-02.01: --subject "*a* *b*" => a AND b, in any order."""
        self.assertEqual(self.uids(self.run_search(subject=("*inv* *2026*",))), [prefixed_uid(2714)])
        self.assertEqual(self.uids(self.run_search(subject=("*2026* *inv*",))), [prefixed_uid(2714)])
        self.assertEqual(self.uids(self.run_search(subject=("*inv* *2025*",))), [])
        self.assertEqual(self.uids(self.run_search(subject=("2026 invoice",))), [prefixed_uid(2714)])

    def test_ut_sr_02_03_from_to_cc_value_is_one_pattern(self) -> None:
        """UT-SR-02.03: --from/--to/--cc "Team Billing" does not match "Billing Team"."""
        # Words in the same order as the display value match as one pattern.
        self.assertEqual(self.uids(self.run_search(from_=("Billing Team",))), [prefixed_uid(2714)])
        self.assertEqual(self.uids(self.run_search(cc=("Finance <finance",))), [prefixed_uid(2714)])
        # Words in another order do not (they used to be split into AND terms).
        self.assertEqual(self.uids(self.run_search(from_=("Team Billing",))), [])
        self.assertEqual(self.uids(self.run_search(to=("User Fixture",))), [])
        self.assertEqual(self.uids(self.run_search(cc=("fixture finance",))), [])

    def test_from_to_cc_filters(self) -> None:
        self.assertEqual(
            self.uids(self.run_search(from_=("billing@fixture.example",))), [prefixed_uid(2714)]
        )
        self.assertEqual(
            self.uids(self.run_search(from_=("Billing Team",))), [prefixed_uid(2714)]
        )
        self.assertEqual(
            self.uids(self.run_search(from_=("*@fixture.example",))), DEFAULT_UIDS
        )
        self.assertEqual(
            self.uids(self.run_search(from_=("*@banco.example",))), []
        )
        self.assertEqual(
            self.uids(self.run_search(to=("me@fixture.example",))), DEFAULT_UIDS
        )
        self.assertEqual(self.uids(self.run_search(cc=("finance",))), [prefixed_uid(2714)])
        self.assertEqual(self.uids(self.run_search(cc=("nobody",))), [])

    def test_relative_since_and_until(self) -> None:
        since_week = self.run_search(since=search.parse_relative_time("7d"))
        self.assertEqual(
            self.uids(since_week),
            [prefixed_uid(83170), prefixed_uid(83160), prefixed_uid(83150), prefixed_uid(83143), prefixed_uid(83210), prefixed_uid(2714), prefixed_uid(83220), prefixed_uid(83200)],
        )
        until_week = self.run_search(until=search.parse_relative_time("7d"))
        self.assertEqual(self.uids(until_week), [prefixed_uid(79658), prefixed_uid(83180), prefixed_uid(830), prefixed_uid(83190)])
        minute_window = self.run_search(since=search.parse_relative_time("45min"))
        self.assertEqual(self.uids(minute_window), [prefixed_uid(83170), prefixed_uid(83160), prefixed_uid(83150)])

    def test_state_filters(self) -> None:
        self.assertEqual(
            self.uids(self.run_search(unread=True)), [prefixed_uid(83150), prefixed_uid(83143), prefixed_uid(83210), prefixed_uid(2714)]
        )
        self.assertEqual(self.uids(self.run_search(flagged=True)), [prefixed_uid(83150)])
        self.assertEqual(
            self.uids(self.run_search(has_attachments=True)),
            [prefixed_uid(83210), prefixed_uid(2714), prefixed_uid(79658)],
        )
        self.assertEqual(
            self.uids(self.run_search(flagged=True, unread=True)), [prefixed_uid(83150)]
        )
        self.assertEqual(
            self.uids(
                self.run_search(
                    unread=True,
                    flagged=True,
                    since=search.parse_relative_time("7d"),
                )
            ),
            [prefixed_uid(83150)],
        )

    def test_combined_filters_are_and(self) -> None:
        result = self.run_search(
            unread=True,
            since=search.parse_relative_time("7d"),
            has_attachments=True,
        )
        self.assertEqual(self.uids(result), [prefixed_uid(83210), prefixed_uid(2714)])

    def test_limit_and_truncated_hint(self) -> None:
        limited = self.run_search(limit=5)
        self.assertEqual(limited["count"], 5)
        self.assertEqual(self.uids(limited), DEFAULT_UIDS[:5])
        self.assertTrue(limited["truncated"])
        self.assertIsNotNone(limited["hint"])
        self.assertIn("200", limited["hint"])
        self.assertIn("W_RESULTS_TRUNCATED", warning_codes(limited["warnings"]))
        self.assertIn(
            "7 more messages match", " ".join(limited["warnings"])
        )

        complete = self.run_search(limit=20)
        self.assertFalse(complete["truncated"])
        self.assertIsNone(complete["hint"])
        self.assertNotIn("W_RESULTS_TRUNCATED", warning_codes(complete["warnings"]))

    def test_limit_is_capped_at_200(self) -> None:
        result = self.run_search(limit=500)
        self.assertEqual(result["count"], 12)
        self.assertFalse(result["truncated"])

    def test_snippets_and_body_availability(self) -> None:
        shared = self.message_by_uid(
            self.run_search(subject=("Shared duplicate",)), 83143
        )
        self.assertIn("Duplicate body from the inbox.", shared["snippet"])
        self.assertEqual(
            shared["body"],
            {"available": True, "readable": True, "partial": False, "truncated": False},
        )

        partial = self.message_by_uid(
            self.run_search(subject=("Factura septiembre",)), 79658
        )
        self.assertIn("Adjuntamos la factura", partial["snippet"])
        self.assertTrue(partial["body"]["partial"])
        self.assertTrue(partial["body"]["available"])

        html_only = self.message_by_uid(
            self.run_search(subject=("HTML only",)), 83200
        )
        self.assertIn("There is no plain text part", html_only["snippet"])

        missing = self.run_search(subject=("Missing body",))
        missing_message = missing["messages"][0]
        self.assertEqual(missing_message["uid"], prefixed_uid(83170))
        self.assertEqual(missing_message["snippet"], "")
        self.assertFalse(missing_message["body"]["available"])
        self.assertIn("W_EMLX_MISSING", warning_codes(missing["warnings"]))

        corrupt = self.run_search(subject=("Corrupt body",))
        self.assertEqual(corrupt["messages"][0]["uid"], prefixed_uid(83180))
        self.assertEqual(corrupt["messages"][0]["snippet"], "")
        self.assertIn("W_EMLX_CORRUPT", warning_codes(corrupt["warnings"]))

    def test_include_mailbox_adds_folder_and_keeps_inbox_priority(self) -> None:
        result = self.run_search(
            subject=("Shared duplicate",),
            include_mailboxes=("[Gmail]/All Mail",),
        )
        self.assertEqual(self.uids(result), [prefixed_uid(83143)])
        self.assertEqual(result["messages"][0]["duplicate_count"], 2)
        self.assertEqual(result["messages"][0]["mailbox"]["name"], "INBOX")

        # With the extra folder in scope only one canonical copy is returned.
        everything = self.run_search(include_mailboxes=("[Gmail]/All Mail",))
        self.assertEqual(everything["count"], 12)
        self.assertEqual(self.uids(everything), DEFAULT_UIDS)

    def test_include_mailbox_accepts_name_path_and_url(self) -> None:
        for reference in ("All Mail", "[Gmail]/All Mail", MAILBOX_URLS[6]):
            with self.subTest(reference=reference):
                result = self.run_search(include_mailboxes=(reference,))
                self.assertEqual(result["count"], 12)
                self.assertEqual(
                    self.message_by_uid(result, 83143)["duplicate_count"], 2
                )

    def test_ut_sr_04_01_unknown_include_mailbox_lists_the_folders_of_declared_accounts(self) -> None:
        """UT-SR-04.01: unknown folder => E_MAILBOX_NOT_FOUND, hint lists all declared accounts' folders."""
        with self.assertRaises(MailqueryError) as context:
            self.run_search(include_mailboxes=("Nope",))
        self.assertEqual(context.exception.code, "E_MAILBOX_NOT_FOUND")
        self.assertEqual(context.exception.exit_code, 2)
        self.assertIn("Nope", context.exception.message)
        hint = context.exception.hint
        # Default config declares the three accounts: their folders are all listed.
        for folder in ("INBOX", "Facturas", "Archivo", "[Gmail]/All Mail", "Recovered Messages"):
            self.assertIn(folder, hint)

        # Only declared accounts are listed.
        self.use_config(ICLOUD_ONLY)
        with self.assertRaises(MailqueryError) as context:
            self.run_search(include_mailboxes=("Nope",))
        self.assertEqual(context.exception.code, "E_MAILBOX_NOT_FOUND")
        self.assertIn("Facturas", context.exception.hint)
        self.assertNotIn("Recovered Messages", context.exception.hint)
        self.assertNotIn("[Gmail]/All Mail", context.exception.hint)

    def test_ut_sr_04_02_include_mailbox_resolves_in_its_own_driver(self) -> None:
        """UT-SR-04.02: --include-mailbox resolves a folder inside its own driver."""
        archive = {
            "id": "graph-archive",
            "account_uuid": PLUGIN_ACCOUNT_UUID,
            "name": "Archive",
            "path": "Archive",
            "url": "graph://graph-account/Archive",
            "is_inbox": False,
            "is_aggregate": False,
            "total": 1,
            "unread": 0,
        }
        plugin = FakePluginBackend(
            rows=[self.plugin_row("P1", minutes_ago=12, mailbox_id="graph-archive")],
            mailboxes=[*PLUGIN_MAILBOXES, archive],
        )
        config = self.multi_driver_config()
        scoped = search.run_search(
            self.backend,
            config,
            search.Filters(),
            drivers={PLUGIN_DRIVER: plugin},
        )
        self.assertNotIn(prefixed_uid("P1", PLUGIN_DRIVER), self.uids(scoped))
        included = search.run_search(
            self.backend,
            config,
            search.Filters(include_mailboxes=("Archive",)),
            drivers={PLUGIN_DRIVER: plugin},
        )
        self.assertIn(prefixed_uid("P1", PLUGIN_DRIVER), self.uids(included))
        plugin_only = dataclasses.replace(
            config,
            scopes=tuple(
                scope for scope in config.scopes if scope.driver == PLUGIN_DRIVER
            ),
        )
        unknown = search.run_search(
            None,
            plugin_only,
            search.Filters(include_mailboxes=("Archive",)),
            drivers={PLUGIN_DRIVER: plugin},
            native="apple_mail",
        )
        self.assertIn(prefixed_uid("P1", PLUGIN_DRIVER), self.uids(unknown))

    def test_include_mailbox_outside_declared_accounts(self) -> None:
        self.use_config(ICLOUD_ONLY)
        with self.assertRaises(MailqueryError) as context:
            self.run_search(include_mailboxes=("Recovered Messages",))
        self.assertEqual(context.exception.code, "E_ACCOUNT_NOT_IN_SCOPE")
        self.assertEqual(context.exception.exit_code, 2)

    def test_dedupe_counts_scoped_copies(self) -> None:
        # Default config: only the iCloud INBOX copy of the duplicate is scoped.
        self.assertEqual(
            self.message_by_uid(
                self.run_search(subject=("Shared duplicate",)), 83143
            )["duplicate_count"],
            1,
        )
        # Declaring [Gmail]/All Mail brings the second copy into the scope.
        self.use_config(DEDUPE_CONFIG)
        result = self.run_search(subject=("Shared duplicate",))
        self.assertEqual(self.uids(result), [prefixed_uid(83143)])
        message = result["messages"][0]
        self.assertEqual(message["duplicate_count"], 2)
        self.assertEqual(message["mailbox"]["account"]["uuid"], ACCOUNT_ICLOUD)
        self.assertEqual(message["mailbox"]["name"], "INBOX")

    def test_no_accounts_returns_empty_with_warning(self) -> None:
        self.use_config("")
        result = self.run_search()
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["messages"], [])
        self.assertFalse(result["truncated"])
        self.assertIsNone(result["hint"])
        self.assertEqual(result["scan"]["candidates"], 0)
        self.assertEqual(warning_codes(result["warnings"]), ["W_NO_ACCOUNTS"])

    def test_unscoped_account_is_not_read(self) -> None:
        self.use_config(ICLOUD_ONLY)
        result = self.run_search()
        self.assertEqual(self.uids(result), [prefixed_uid(83170), prefixed_uid(83150), prefixed_uid(83143), prefixed_uid(2714), prefixed_uid(83220), prefixed_uid(83200), prefixed_uid(830), prefixed_uid(83190)])
        self.assertNotIn(prefixed_uid(83160), self.uids(result))
        self.assertNotIn(prefixed_uid(83210), self.uids(result))


# --------------------------------------------------------------------------- #
# search --text
# --------------------------------------------------------------------------- #


class SearchTextTest(SearchFixtureTest):
    """Bounded content scans (RF-17): validation, matching and counters."""

    def assert_unbounded(self, **filters: object) -> MailqueryError:
        with self.assertRaises(MailqueryError) as context:
            self.run_search(**filters)
        self.assertEqual(context.exception.code, "E_UNBOUNDED_SCAN")
        self.assertEqual(context.exception.exit_code, 4)
        return context.exception

    def test_ut_sr_03_01_text_without_narrowing_filter_is_unbounded(self) -> None:
        """UT-SR-03.01: --text x alone => E_UNBOUNDED_SCAN naming --text, hint lists the narrowing filters."""
        self.use_config(ICLOUD_ONLY)
        error = self.assert_unbounded(text=("invoice",))
        self.assertIn("--text", error.message)
        for option in (
            "--since",
            "--until",
            "--from",
            "--to",
            "--cc",
            "--subject",
            "--include-mailbox",
        ):
            self.assertIn(option, error.hint)

    def test_ut_sr_03_02_empty_filter_value_does_not_narrow_text(self) -> None:
        """UT-SR-03.02: --text x --from "" => E_UNBOUNDED_SCAN."""
        self.use_config(ICLOUD_ONLY)
        self.assert_unbounded(text=("x",), from_=("",))
        self.assert_unbounded(text=("x",), subject=("  ",), to=("",), cc=("",))

    def test_ut_sr_03_03_inbox_as_included_folder_does_not_narrow_text(self) -> None:
        """UT-SR-03.03: --text x --include-mailbox INBOX => E_UNBOUNDED_SCAN."""
        self.use_config(ICLOUD_ONLY)
        self.assert_unbounded(text=("x",), include_mailboxes=("INBOX",))

    def test_ut_sr_03_04_text_with_to_filter_runs_and_counts_candidates_after_it(self) -> None:
        """UT-SR-03.04: --text x --to y runs; scan.candidates counts the messages after --to."""
        self.use_config(ICLOUD_ONLY)
        result = self.run_search(text=("invoice",), to=("me@fixture.example",))
        self.assertEqual(self.uids(result), [prefixed_uid(2714)])
        self.assertEqual(result["scan"]["mode"], "text")
        self.assertEqual(result["scan"]["candidates"], 8)
        nobody = self.run_search(text=("invoice",), to=("nobody@fixture.example",))
        self.assertEqual(nobody["count"], 0)
        self.assertEqual(nobody["scan"]["candidates"], 0)

    def test_ut_sr_03_05_candidates_equal_to_max_scan_run(self) -> None:
        """UT-SR-03.05: candidates == max_scan => the scan runs."""
        self.use_config(ICLOUD_ONLY)
        self.config = dataclasses.replace(
            self.config, search=SearchConfig(default_limit=20, max_scan=8)
        )
        result = self.run_search(text=("invoice",), to=("me@fixture.example",))
        self.assertEqual(self.uids(result), [prefixed_uid(2714)])
        self.assertEqual(result["scan"]["candidates"], 8)

    def test_ut_sr_03_06_multi_driver_scan_budget_is_the_sum(self) -> None:
        """UT-SR-03.06: multi-driver max_scan compares the summed candidates."""
        config = self.multi_driver_config()
        plugin = FakePluginBackend(
            rows=[
                self.plugin_row("P1", minutes_ago=12),
                self.plugin_row("P2", minutes_ago=18),
                self.plugin_row("P3", minutes_ago=24),
            ]
        )
        filters = search.Filters(
            text=("invoice",), subject=("*",), since=search.parse_relative_time("7d")
        )
        plugin_only = dataclasses.replace(
            config,
            scopes=tuple(
                scope for scope in config.scopes if scope.driver == PLUGIN_DRIVER
            ),
        )
        native_only = dataclasses.replace(
            config,
            scopes=tuple(
                scope for scope in config.scopes if scope.driver != PLUGIN_DRIVER
            ),
        )
        native = search.run_search(self.backend, native_only, filters)
        only_plugin = search.run_search(
            None,
            plugin_only,
            filters,
            drivers={PLUGIN_DRIVER: plugin},
            native="apple_mail",
        )
        permissive = dataclasses.replace(
            config,
            search=dataclasses.replace(config.search, max_scan=50000),
        )
        merged = search.run_search(
            self.backend, permissive, filters, drivers={PLUGIN_DRIVER: plugin}
        )
        self.assertEqual(
            merged["scan"]["candidates"],
            native["scan"]["candidates"] + only_plugin["scan"]["candidates"],
        )
        exact = merged["scan"]["candidates"]
        allowed = dataclasses.replace(
            config, search=dataclasses.replace(config.search, max_scan=exact)
        )
        self.assertEqual(
            search.run_search(
                self.backend, allowed, filters, drivers={PLUGIN_DRIVER: plugin}
            )["scan"]["candidates"],
            exact,
        )
        too_small = dataclasses.replace(
            config, search=dataclasses.replace(config.search, max_scan=exact - 1)
        )
        with self.assertRaises(MailqueryError) as context:
            search.run_search(
                self.backend, too_small, filters, drivers={PLUGIN_DRIVER: plugin}
            )
        self.assertEqual(context.exception.code, "E_SCAN_TOO_LARGE")
        self.assertIn(str(exact), context.exception.message)

    def test_text_narrowed_by_since(self) -> None:
        result = self.run_search(
            text=("invoice",), since=search.parse_relative_time("1y")
        )
        self.assertEqual(self.uids(result), [prefixed_uid(2714)])
        self.assertEqual(result["scan"]["mode"], "text")
        self.assertEqual(result["scan"]["candidates"], 11)
        self.assertEqual(result["scan"]["messages_read"], 10)
        self.assertIn(
            "Please find the invoice attached.",
            result["messages"][0]["snippet"],
        )
        self.assertIn("W_EMLX_MISSING", warning_codes(result["warnings"]))
        self.assertIn("W_EMLX_CORRUPT", warning_codes(result["warnings"]))

    def test_text_wildcards_and_phrases(self) -> None:
        self.assertEqual(
            self.uids(
                self.run_search(
                    text=("*invoice attached*",),
                    since=search.parse_relative_time("1y"),
                )
            ),
            [prefixed_uid(2714)],
        )
        self.assertEqual(
            self.uids(
                self.run_search(
                    text=("remember *",), since=search.parse_relative_time("1y")
                )
            ),
            [prefixed_uid(83150)],
        )
        self.assertEqual(
            self.uids(
                self.run_search(
                    text=("invoice attached",), since=search.parse_relative_time("1y")
                )
            ),
            [prefixed_uid(2714)],
        )
        self.assertEqual(
            self.uids(
                self.run_search(
                    text=("invoice missing",), since=search.parse_relative_time("1y")
                )
            ),
            [],
        )

    def test_ut_sr_02_02_text_value_is_one_pattern_not_and_terms(self) -> None:
        """UT-SR-02.02: --text "attached invoice" does not match "invoice attached"."""
        since = search.parse_relative_time("1y")
        self.assertEqual(
            self.uids(self.run_search(text=("invoice attached",), since=since)), [prefixed_uid(2714)]
        )
        self.assertEqual(
            self.uids(self.run_search(text=("attached invoice",), since=since)), []
        )

    def test_text_no_match_is_success(self) -> None:
        result = self.run_search(
            text=("zzz-nothing-here",), since=search.parse_relative_time("7d")
        )
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["messages"], [])
        self.assertFalse(result["truncated"])
        self.assertIsNone(result["hint"])
        self.assertEqual(result["scan"]["mode"], "text")

    def test_text_narrowed_by_extra_folder(self) -> None:
        self.use_config(ICLOUD_WITH_ARCHIVO)
        result = self.run_search(text=("Ancient message",))
        self.assertEqual(self.uids(result), [prefixed_uid(83190)])
        self.assertEqual(result["scan"]["mode"], "text")
        self.assertEqual(result["scan"]["candidates"], 9)

    def test_text_narrowed_by_from_filter(self) -> None:
        self.use_config(ICLOUD_ONLY)
        result = self.run_search(text=("invoice",), from_=("billing",))
        self.assertEqual(self.uids(result), [prefixed_uid(2714)])
        self.assertEqual(result["scan"]["candidates"], 1)
        self.assertEqual(result["scan"]["messages_read"], 1)

    def test_text_scan_too_large_fails_without_partial_results(self) -> None:
        config = Config(
            home=self.fx.home,
            logging=LoggingConfig(),
            search=SearchConfig(default_limit=20, max_scan=3),
            new=NewConfig(),
            scopes=(
                ScopeEntry(key=ICLOUD_LABEL, mailbox_list=("Facturas", "Archivo")),
                ScopeEntry(key=GMAIL_LABEL),
            ),
        )
        with self.assertRaises(MailqueryError) as context:
            search.run_search(
                self.backend,
                config,
                search.Filters(
                    text=("invoice",), since=search.parse_relative_time("1y")
                ),
            )
        self.assertEqual(context.exception.code, "E_SCAN_TOO_LARGE")
        self.assertEqual(context.exception.exit_code, 4)
        self.assertIn("11", context.exception.message)
        self.assertIn("3", context.exception.message)


# --------------------------------------------------------------------------- #
# new
# --------------------------------------------------------------------------- #


class NewTest(SearchFixtureTest):
    """Cursor semantics of ``new`` (PRD 11.2, 12.3, 18)."""

    def run_new(self, state: StateStore, **kwargs: object) -> dict:
        return search.run_new(
            self.backend, self.config, state, **kwargs
        )

    FIRST_RUN_10MIN = (
        "W_FIRST_RUN: first run: emitted the messages received in the last "
        "10min before the newest message"
    )

    def test_ut_sr_07_01_message_exactly_at_the_window_start_is_included(self) -> None:
        """UT-SR-07.01: a message exactly at D - lookback is included."""
        # 83170 is D (15 min old); 83160 is 20 min old, i.e. exactly D - 300 s.
        self.use_lookback("5min", 300)
        result = self.run_new(self.fresh_state())
        self.assertEqual(self.uids(result), [prefixed_uid(83160), prefixed_uid(83170)])

    def test_ut_sr_07_02_message_one_second_before_the_window_is_excluded(self) -> None:
        """UT-SR-07.02: a message one second before D - lookback is excluded."""
        self.use_lookback("299s", 299)
        result = self.run_new(self.fresh_state())
        self.assertEqual(self.uids(result), [prefixed_uid(83170)])

    def test_ut_sr_07_03_scope_with_a_single_message_emits_it(self) -> None:
        """UT-SR-07.03: a scope with one message emits it."""
        fx = build_store()
        self.addCleanup(fx.cleanup)
        write_config(fx.home, DEFAULT_CONFIG)
        connection = sqlite3.connect(fx.envelope_index)
        try:
            connection.execute("UPDATE messages SET deleted = 1 WHERE ROWID <> 83170")
            connection.commit()
        finally:
            connection.close()
        store = open_store(mail_root=fx.mail_root, tmp_root=fx.home / "tmp")
        self.addCleanup(store.close)
        labels = AccountLabels(fx.accounts_db, tmp_dir=fx.home / "tmp")
        result = search.run_new(
            AppleMailBackend(store, labels), load_config(fx.home), StateStore(fx.home, _all_installed)
        )
        self.assertEqual(self.uids(result), [prefixed_uid(83170)])
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["cursor"]["current"]["last_uid"], prefixed_uid(83170))
        self.assertEqual(
            warning_codes(result["warnings"]), ["W_EMLX_MISSING", "W_FIRST_RUN"]
        )

    def test_ut_sr_07_04_limit_smaller_than_the_window_keeps_the_most_recent(self) -> None:
        """UT-SR-07.04: --limit below the window size keeps the newest, ascending."""
        self.use_lookback("1h", 3600)
        full = self.run_new(self.fresh_state(), peek=True)
        self.assertEqual(self.uids(full), [prefixed_uid(83143), prefixed_uid(83150), prefixed_uid(83160), prefixed_uid(83170)])
        state = self.fresh_state()
        result = self.run_new(state, limit=2)
        self.assertEqual(self.uids(result), [prefixed_uid(83160), prefixed_uid(83170)])
        self.assertEqual(result["count"], 2)
        self.assertTrue(result["truncated"])
        self.assertIsNotNone(result["hint"])
        self.assertEqual(
            warning_codes(result["warnings"]),
            ["W_RESULTS_TRUNCATED", "W_EMLX_MISSING", "W_FIRST_RUN"],
        )
        self.assertIn("2 more messages", result["warnings"][0])
        persisted = state.load()
        self.assertEqual(persisted.cursor.last_uid, prefixed_uid(83170))
        self.assertEqual(persisted.emitted_uids, (prefixed_uid(83160), prefixed_uid(83170)))

    def test_ut_sr_07_05_first_run_peek_emits_and_does_not_write_state(self) -> None:
        """UT-SR-07.05: --peek on a first run emits the window and writes no state."""
        state = self.fresh_state()
        result = self.run_new(state, peek=True)
        self.assertEqual(self.uids(result), [prefixed_uid(83160), prefixed_uid(83170)])
        self.assertIsNone(result["cursor"]["previous"])
        self.assertIsNone(result["cursor"]["current"])
        self.assertFalse((self.fx.home / "state.json").exists())

    def test_ut_sr_07_06_first_run_sets_cursor_and_ring_to_the_emitted(self) -> None:
        """UT-SR-07.06: without --peek the cursor is the last emitted and the ring holds the uids."""
        state = self.fresh_state()
        result = self.run_new(state)
        self.assertEqual(
            set(result),
            {"count", "truncated", "hint", "messages", "scan", "cursor", "warnings"},
        )
        self.assertEqual(self.uids(result), [prefixed_uid(83160), prefixed_uid(83170)])
        self.assertEqual(result["count"], 2)
        self.assertFalse(result["truncated"])
        self.assertIsNone(result["hint"])
        self.assertEqual(result["scan"]["mode"], "metadata")
        self.assertEqual(result["scan"]["candidates"], 2)
        self.assertEqual(result["scan"]["messages_read"], 1)
        self.assertEqual(
            warning_codes(result["warnings"]), ["W_EMLX_MISSING", "W_FIRST_RUN"]
        )
        self.assertEqual(result["warnings"][-1], self.FIRST_RUN_10MIN)
        self.assertIsNone(result["cursor"]["previous"])
        current = result["cursor"]["current"]
        self.assertEqual(
            set(current), {"last_date_received", "last_uid", "lookback_seconds"}
        )
        self.assertEqual(current["last_uid"], prefixed_uid(83170))
        self.assertEqual(current["lookback_seconds"], 600)
        self.assertGreater(current["last_date_received"], 0)

        persisted = state.load()
        self.assertEqual(persisted.cursor.last_uid, prefixed_uid(83170))
        self.assertEqual(persisted.emitted_uids, (prefixed_uid(83160), prefixed_uid(83170)))
        self.assertEqual(persisted.last_run.command, "new")

    def test_ut_sr_07_07_declared_accounts_without_messages_emit_nothing_and_write_no_state(self) -> None:
        """UT-SR-07.07: declared accounts without messages: count 0, W_FIRST_RUN, no state."""
        self.use_config(f'[scope."{LOCAL_LABEL}"]\n')
        result = self.run_new(self.fresh_state())
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["messages"], [])
        self.assertEqual(result["warnings"], [self.FIRST_RUN_10MIN])
        self.assertIsNone(result["cursor"]["previous"])
        self.assertIsNone(result["cursor"]["current"])
        self.assertFalse((self.fx.home / "state.json").exists())

    def test_ut_sr_07_08_without_declared_accounts_warns_no_accounts_then_first_run(self) -> None:
        """UT-SR-07.08: no accounts: W_NO_ACCOUNTS then W_FIRST_RUN, no state."""
        self.use_config("")
        result = self.run_new(self.fresh_state())
        self.assertEqual(result["count"], 0)
        self.assertIsNone(result["cursor"]["current"])
        self.assertEqual(
            result["warnings"], [search.NO_ACCOUNTS_WARNING, self.FIRST_RUN_10MIN]
        )
        self.assertFalse((self.fx.home / "state.json").exists())

    def test_ut_sr_07_09_first_run_warning_shows_the_lookback_as_written(self) -> None:
        """UT-SR-07.09: lookback = "1h" shows 1h in W_FIRST_RUN."""
        self.use_lookback("1h", 3600)
        result = self.run_new(self.fresh_state(), peek=True)
        self.assertEqual(
            result["warnings"][-1],
            "W_FIRST_RUN: first run: emitted the messages received in the last "
            "1h before the newest message",
        )

    def test_ut_sr_08_01_every_run_uses_the_current_config_lookback(self) -> None:
        """UT-SR-08.01: the config lookback wins over the stored one and is stored."""
        # Cursor 25 min old with a stored lookback of 60 s. 83150 (30 min old) is
        # 5 min before the cursor: only the config lookback (10 min) reaches it.
        state = self.seed_state(age=timedelta(minutes=25), lookback_seconds=60)
        result = self.run_new(state)
        self.assertEqual(self.uids(result), [prefixed_uid(83150), prefixed_uid(83160), prefixed_uid(83170)])
        self.assertEqual(result["cursor"]["previous"]["lookback_seconds"], 60)
        self.assertEqual(result["cursor"]["current"]["lookback_seconds"], 600)
        self.assertEqual(state.load().cursor.lookback_seconds, 600)

    def test_subsequent_run_emits_lookback_window(self) -> None:
        state = self.seed_state(age=timedelta(hours=2))
        result = self.run_new(state)
        self.assertEqual(self.uids(result), [prefixed_uid(83143), prefixed_uid(83150), prefixed_uid(83160), prefixed_uid(83170)])
        self.assertFalse(result["truncated"])
        self.assertIsNone(result["hint"])
        self.assertEqual(result["scan"]["candidates"], 4)
        self.assertEqual(result["scan"]["messages_read"], 3)
        self.assertIn("W_EMLX_MISSING", warning_codes(result["warnings"]))
        self.assertEqual(result["cursor"]["previous"]["last_uid"], prefixed_uid(1))
        self.assertEqual(result["cursor"]["current"]["last_uid"], prefixed_uid(83170))

        persisted = state.load()
        self.assertEqual(persisted.cursor.last_uid, prefixed_uid(83170))
        self.assertEqual(
            set(persisted.emitted_uids), {prefixed_uid(83143), prefixed_uid(83150), prefixed_uid(83160), prefixed_uid(83170)}
        )

    def test_rerun_after_cursor_advance_emits_nothing(self) -> None:
        state = self.seed_state(age=timedelta(hours=2))
        self.assertEqual(self.run_new(state)["count"], 4)
        result = self.run_new(state)
        self.assertEqual(result["count"], 0)
        self.assertEqual(
            result["cursor"]["previous"], result["cursor"]["current"]
        )
        self.assertEqual(warning_codes(result["warnings"]), [])

    def test_limit_advances_cursor_and_next_run_continues(self) -> None:
        state = self.seed_state(age=timedelta(hours=2))
        first = self.run_new(state, limit=2)
        self.assertEqual(self.uids(first), [prefixed_uid(83143), prefixed_uid(83150)])
        self.assertTrue(first["truncated"])
        self.assertIsNotNone(first["hint"])
        self.assertIn("W_RESULTS_TRUNCATED", warning_codes(first["warnings"]))
        self.assertEqual(first["cursor"]["current"]["last_uid"], prefixed_uid(83150))
        self.assertEqual(state.load().cursor.last_uid, prefixed_uid(83150))

        second = self.run_new(state, limit=2)
        self.assertEqual(self.uids(second), [prefixed_uid(83160), prefixed_uid(83170)])
        self.assertFalse(second["truncated"])
        self.assertEqual(second["cursor"]["current"]["last_uid"], prefixed_uid(83170))

    def test_peek_does_not_advance_cursor(self) -> None:
        state = self.seed_state(age=timedelta(hours=2))
        peeked = self.run_new(state, peek=True)
        self.assertEqual(self.uids(peeked), [prefixed_uid(83143), prefixed_uid(83150), prefixed_uid(83160), prefixed_uid(83170)])
        self.assertEqual(
            peeked["cursor"]["previous"], peeked["cursor"]["current"]
        )
        self.assertEqual(state.load().cursor.last_uid, prefixed_uid(1))
        # The same messages are still new for the real run.
        self.assertEqual(self.run_new(state)["count"], 4)

    def test_emitted_ring_suppresses_duplicates(self) -> None:
        state = self.seed_state(age=timedelta(hours=2), emitted_uids=(83170,))
        result = self.run_new(state)
        self.assertEqual(self.uids(result), [prefixed_uid(83143), prefixed_uid(83150), prefixed_uid(83160)])

    def test_new_scope_only_declared_accounts(self) -> None:
        self.use_config(ICLOUD_ONLY)
        state = self.seed_state(age=timedelta(hours=2))
        result = self.run_new(state)
        self.assertEqual(self.uids(result), [prefixed_uid(83143), prefixed_uid(83150), prefixed_uid(83170)])
        self.assertNotIn(prefixed_uid(83160), self.uids(result))

    def test_new_without_accounts_and_with_a_cursor_only_warns_no_accounts(self) -> None:
        self.use_config("")
        state = self.seed_state()
        result = self.run_new(state)
        self.assertEqual(result["count"], 0)
        self.assertEqual(warning_codes(result["warnings"]), ["W_NO_ACCOUNTS"])

    def test_new_limit_accepts_up_to_500(self) -> None:
        state = self.fresh_state()
        result = self.run_new(state, limit=1000)
        self.assertEqual(self.uids(result), [prefixed_uid(83160), prefixed_uid(83170)])
        self.assertIsNone(result["hint"])


class NewDatesTest(ExtendedSearchFixtureTest):
    """Null, zero, unrepresentable and future dates in ``new`` (PRD 12.3, 17).

    The clock is injected: "now" is the moment the fixture was built, so the
    ``now + 30 days`` message (90163) is in the future.
    """

    INVALID_UIDS = (UID_DATE_NULL, UID_DATE_ZERO, UID_DATE_HUGE)

    def run_new(self, state: StateStore, now: float | None = None, **kwargs: object) -> dict:
        moment = self.fx.now.timestamp() if now is None else now
        return search.run_new(
            self.backend,
            self.config,
            state,
            clock=lambda: moment,
            **kwargs,
        )

    @property
    def future_ts(self) -> int:
        return int((self.fx.now - self.fx.message(UID_DATE_FUTURE).age).timestamp())

    def assert_cursor_is_real_newest(self, result: dict) -> None:
        current = result["cursor"]["current"]
        self.assertEqual(current["last_uid"], prefixed_uid(83170))
        self.assertLessEqual(current["last_date_received"], self.fx.now.timestamp())

    def test_ut_sr_09_01_null_date_does_not_enter_the_first_run(self) -> None:
        """UT-SR-09.01: a NULL date_received is not emitted on a first run."""
        result = self.run_new(self.fresh_state())
        self.assertNotIn(UID_DATE_NULL, self.uids(result))
        self.assertEqual(self.uids(result), [prefixed_uid(83160), prefixed_uid(83170)])
        self.assert_cursor_is_real_newest(result)

    def test_ut_sr_09_02_zero_date_does_not_enter_the_first_run(self) -> None:
        """UT-SR-09.02: date_received 0 is not emitted on a first run."""
        result = self.run_new(self.fresh_state())
        self.assertNotIn(UID_DATE_ZERO, self.uids(result))
        self.assert_cursor_is_real_newest(result)

    def test_ut_sr_09_03_unrepresentable_date_does_not_enter_the_first_run(self) -> None:
        """UT-SR-09.03: date_received 1e20 is not emitted and is not "the newest"."""
        result = self.run_new(self.fresh_state())
        self.assertNotIn(UID_DATE_HUGE, self.uids(result))
        self.assert_cursor_is_real_newest(result)

    def test_ut_sr_09_04_invalid_dates_do_not_enter_later_runs_nor_move_the_cursor(self) -> None:
        """UT-SR-09.04: in later runs they are not emitted and do not move the cursor."""
        # A cursor at epoch 1 makes every message of the scope a candidate.
        state = self.seed_state(last_date_received=1)
        result = self.run_new(state)
        emitted = self.uids(result)
        for uid in self.INVALID_UIDS + (UID_DATE_FUTURE,):
            self.assertNotIn(uid, emitted)
        self.assertIn(prefixed_uid(83170), emitted)
        self.assert_cursor_is_real_newest(result)
        self.assertEqual(state.load().cursor.last_uid, prefixed_uid(83170))

    def test_ut_sr_09_05_search_shows_invalid_dates_as_null_without_aborting(self) -> None:
        """UT-SR-09.05: search lists them with date_received null."""
        result = self.run_search(limit=200)
        for uid in self.INVALID_UIDS:
            message = self.message_by_uid(result, uid)
            self.assertIsNone(message["date_received"])
            self.assertIsNone(message["date_sent"])
        self.assertIsNotNone(
            self.message_by_uid(result, 83170)["date_received"]
        )

    def test_ut_sr_10_01_future_message_does_not_enter_the_first_run(self) -> None:
        """UT-SR-10.01: a future message is not emitted nor "the newest" on a first run."""
        result = self.run_new(self.fresh_state())
        self.assertNotIn(UID_DATE_FUTURE, self.uids(result))
        self.assert_cursor_is_real_newest(result)
        self.assertLess(result["cursor"]["current"]["last_date_received"], self.future_ts)

    def test_ut_sr_10_02_future_message_does_not_enter_later_runs_nor_move_the_cursor(self) -> None:
        """UT-SR-10.02: in later runs it is not emitted and does not move the cursor."""
        state = self.seed_state(age=timedelta(hours=2))
        result = self.run_new(state)
        self.assertNotIn(UID_DATE_FUTURE, self.uids(result))
        self.assert_cursor_is_real_newest(result)
        self.assertLess(state.load().cursor.last_date_received, self.future_ts)

    def test_ut_sr_10_03_message_enters_once_it_is_no_longer_in_the_future(self) -> None:
        """UT-SR-10.03: when it stops being future it is emitted in that run."""
        state = self.fresh_state()
        first = self.run_new(state)
        self.assertNotIn(UID_DATE_FUTURE, self.uids(first))
        later = self.fx.now.timestamp() + 31 * 24 * 3600
        second = self.run_new(state, now=later)
        self.assertEqual(self.uids(second), [prefixed_uid(UID_DATE_FUTURE)])
        self.assertEqual(second["cursor"]["current"]["last_uid"], prefixed_uid(UID_DATE_FUTURE))
        self.assertEqual(state.load().cursor.last_date_received, self.future_ts)

    def test_ut_sr_10_04_date_equal_to_the_run_time_enters(self) -> None:
        """UT-SR-10.04: a message whose date equals the run time is emitted."""
        result = self.run_new(self.fresh_state(), now=float(self.future_ts))
        self.assertEqual(self.uids(result), [prefixed_uid(UID_DATE_FUTURE)])
        # One second earlier it is still in the future.
        early = self.run_new(self.fresh_state(), now=float(self.future_ts - 1))
        self.assertNotIn(UID_DATE_FUTURE, self.uids(early))

    def test_ut_sr_10_05_search_and_show_display_the_future_date(self) -> None:
        """UT-SR-10.05: search and show display a future message with its date."""
        expected = output.iso_timestamp(self.future_ts)
        self.assertIsNotNone(expected)
        listed = self.message_by_uid(self.run_search(limit=200), UID_DATE_FUTURE)
        self.assertEqual(listed["date_received"], expected)
        shown = search.run_show(self.backend, self.config, UID_DATE_FUTURE)
        self.assertEqual(shown["message"]["date_received"], expected)


# --------------------------------------------------------------------------- #
# show
# --------------------------------------------------------------------------- #


class ShowTest(SearchFixtureTest):
    """Message detail (``show``)."""

    SHOW_KEYS = [
        "uid",
        "message_id",
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
        "headers",
        "body_text",
        "body_truncated",
        "attachments",
        "partial",
        "readable",
        "source",
    ]

    def show(self, uid: int) -> dict:
        return search.run_show(self.backend, self.config, uid)

    def test_ut_sr_11_01_declared_account_folder_in_scope_returns_the_fields_in_order(self) -> None:
        """UT-SR-11.01: a uid of a declared account in an in-scope folder succeeds."""
        result = self.show(83143)
        self.assertEqual(set(result), {"message", "warnings"})
        message = result["message"]
        self.assertEqual(list(message), self.SHOW_KEYS)
        self.assertEqual(message["uid"], prefixed_uid(83143))
        self.assertEqual(message["subject"], "Shared duplicate")
        self.assertEqual(
            message["message_id"], "<duplicate-4@fixture.example>"
        )
        self.assertEqual(message["from"]["name"], "Shared Sender")
        self.assertEqual(
            message["from"]["address"], "shared@fixture.example"
        )
        self.assertEqual(
            message["to"], [{"name": "Fixture User", "address": "me@fixture.example"}]
        )
        self.assertEqual(message["cc"], [])
        self.assertEqual(message["mailbox"]["name"], "INBOX")
        self.assertEqual(
            message["mailbox"]["account"]["uuid"], ACCOUNT_ICLOUD
        )
        self.assertFalse(message["is_read"])
        self.assertFalse(message["is_flagged"])
        self.assertFalse(message["has_attachments"])
        self.assertIn("Duplicate body from the inbox.", message["body_text"])
        self.assertFalse(message["body_truncated"])
        self.assertEqual(message["attachments"], [])
        self.assertFalse(message["partial"])
        self.assertTrue(message["readable"])
        self.assertEqual(
            set(message["headers"]),
            {"From", "To", "Cc", "Subject", "Date", "Message-ID"},
        )
        self.assertIn("Shared Sender", message["headers"]["From"])
        self.assertEqual(
            message["headers"]["Subject"], "Shared duplicate"
        )
        self.assertEqual(
            message["headers"]["Message-ID"], "<duplicate-4@fixture.example>"
        )
        self.assertTrue(message["headers"]["Date"])
        self.assertIsNotNone(message["source"]["emlx_path"])
        self.assertTrue(message["source"]["emlx_path"].endswith("83143.emlx"))
        self.assertFalse(message["source"]["partial"])
        self.assertEqual(result["warnings"], [])

    def test_show_partial_with_attachment(self) -> None:
        message = self.show(79658)["message"]
        self.assertTrue(message["partial"])
        self.assertTrue(message["source"]["partial"])
        self.assertTrue(message["source"]["emlx_path"].endswith("79658.partial.emlx"))
        self.assertIn("Adjuntamos la factura", message["body_text"])
        self.assertEqual(
            message["attachments"],
            [{"index": 1, "name": "factura-79658.pdf", "cached_path": None}],
        )
        self.assertTrue(message["has_attachments"])

    def test_show_html_only_body(self) -> None:
        message = self.show(83200)["message"]
        self.assertTrue(message["readable"])
        self.assertIn("There is no plain text part", message["body_text"])
        self.assertNotIn("<html", message["body_text"])

    def test_show_missing_emlx(self) -> None:
        result = self.show(83170)
        message = result["message"]
        self.assertFalse(message["readable"])
        self.assertEqual(message["body_text"], "")
        self.assertIsNone(message["source"]["emlx_path"])
        self.assertIn("W_EMLX_MISSING", warning_codes(result["warnings"]))

    def test_show_corrupt_emlx(self) -> None:
        result = self.show(83180)
        message = result["message"]
        self.assertFalse(message["readable"])
        self.assertEqual(message["body_text"], "")
        self.assertIn("W_EMLX_CORRUPT", warning_codes(result["warnings"]))

    def test_ut_sr_11_02_declared_account_folder_outside_mailbox_list_succeeds(self) -> None:
        """UT-SR-11.02: a uid of a declared account outside ``mailbox_list`` succeeds."""
        message = self.show(83160)["message"]
        self.assertEqual(message["mailbox"]["account"]["uuid"], ACCOUNT_GMAIL)
        self.assertEqual(message["mailbox"]["path"], "[Gmail]/All Mail")
        self.assertTrue(message["readable"])

    def test_ut_sr_11_03_without_declared_accounts_is_not_in_scope(self) -> None:
        """UT-SR-11.03: no declared accounts, or an undeclared account: E_ACCOUNT_NOT_IN_SCOPE."""
        self.use_config("")
        with self.assertRaises(MailqueryError) as context:
            self.show(2714)
        self.assertEqual(context.exception.code, "E_ACCOUNT_NOT_IN_SCOPE")
        self.assertEqual(context.exception.exit_code, 2)
        self.assertTrue(context.exception.hint)

        self.use_config(ICLOUD_ONLY)  # 83160 lives in the undeclared Gmail account
        with self.assertRaises(MailqueryError) as context:
            self.show(83160)
        self.assertEqual(context.exception.code, "E_ACCOUNT_NOT_IN_SCOPE")
        self.assertTrue(context.exception.hint)

    def test_ut_sr_11_04_unknown_uid_is_not_found(self) -> None:
        """UT-SR-11.04: a uid that does not exist is E_USAGE "was not found"."""
        for uid in (99999, 12345):  # orphan .emlx (no row) and unknown uid
            with self.subTest(uid=uid):
                with self.assertRaises(MailqueryError) as context:
                    self.show(uid)
                self.assertEqual(context.exception.code, "E_USAGE")
                self.assertEqual(context.exception.exit_code, 2)
                self.assertIn("was not found", context.exception.message)
                self.assertTrue(context.exception.hint)

    def test_ut_sr_11_06_unknown_scope_account_fails_like_search(self) -> None:
        """UT-SR-11.06: an unknown account in ``[scope]`` gives search's error."""
        self.use_config(ICLOUD_ONLY + '\n[scope."Nobody (nobody@fixture.example)"]\n')
        with self.assertRaises(MailqueryError) as from_search:
            self.run_search()
        with self.assertRaises(MailqueryError) as from_show:
            self.show(2714)  # lives in iCloud, not in the unknown account
        self.assertNotEqual(from_show.exception.code, "E_USAGE")
        self.assertEqual(from_show.exception.code, from_search.exception.code)
        self.assertEqual(from_show.exception.exit_code, from_search.exception.exit_code)

    def test_ut_sr_11_07_missing_mailbox_list_folder_fails_like_search(self) -> None:
        """UT-SR-11.07: a ``mailbox_list`` folder that does not exist is E_MAILBOX_NOT_FOUND."""
        self.use_config(f'[scope."{ICLOUD_LABEL}"]\nmailbox_list = ["NoSuchFolder"]\n')
        with self.assertRaises(MailqueryError) as from_search:
            self.run_search()
        self.assertEqual(from_search.exception.code, "E_MAILBOX_NOT_FOUND")
        with self.assertRaises(MailqueryError) as from_show:
            self.show(2714)  # INBOX message, not in the missing folder
        self.assertEqual(from_show.exception.code, "E_MAILBOX_NOT_FOUND")

    def test_ut_sr_11_08_body_limit_is_20000_characters(self) -> None:
        """UT-SR-11.08: bodies of 20,000 and 20,001 characters: body_truncated false / true."""
        fx = build_store()
        self.addCleanup(fx.cleanup)
        write_config(fx.home, DEFAULT_CONFIG)
        store = open_store(mail_root=fx.mail_root, tmp_root=fx.home / "tmp")
        self.addCleanup(store.close)
        labels = AccountLabels(fx.accounts_db, tmp_dir=fx.home / "tmp")
        config = load_config(fx.home)
        for length, truncated in ((20_000, False), (20_001, True)):
            with self.subTest(length=length):
                message = dataclasses.replace(fx.message(83143), body="a" * length)
                make_fixtures._write_emlx_files(fx.mail_root, message, fx.now)
                result = search.run_show(AppleMailBackend(store, labels), config, 83143)
                shown = result["message"]
                self.assertEqual(len(shown["body_text"]), 20_000)
                self.assertIs(shown["body_truncated"], truncated)
                self.assertEqual(
                    warning_codes(result["warnings"]),
                    ["W_BODY_TRUNCATED"] if truncated else [],
                )


class ShowExtendedTest(ExtendedSearchFixtureTest):
    """``show`` over the extended store (deleted messages)."""

    def test_ut_sr_11_05_deleted_message_is_not_found(self) -> None:
        """UT-SR-11.05: the uid of a deleted message is E_USAGE "was not found"."""
        with self.assertRaises(MailqueryError) as context:
            search.run_show(self.backend, self.config, UID_DELETED)
        self.assertEqual(context.exception.code, "E_USAGE")
        self.assertIn("was not found", context.exception.message)


# --------------------------------------------------------------------------- #
# mailboxes
# --------------------------------------------------------------------------- #


class MailboxesTest(SearchFixtureTest):
    """Mailbox catalog with recalculated counters and included flags."""

    EXPECTED_MAILBOXES = {
        (ACCOUNT_ICLOUD, "INBOX"): (8, 3, True),
        (ACCOUNT_ICLOUD, "Facturas"): (1, 0, True),
        (ACCOUNT_ICLOUD, "Archivo"): (1, 0, True),
        (ACCOUNT_GMAIL, "INBOX"): (2, 1, True),
        (ACCOUNT_GMAIL, "[Gmail]/All Mail"): (3, 1, False),
        (ACCOUNT_GMAIL, "[Gmail]/Important"): (0, 0, False),
        (ACCOUNT_LOCAL, "Recovered Messages"): (0, 0, False),
    }

    def mailboxes(self) -> dict:
        return search.run_mailboxes(self.backend, self.config)

    def test_result_shape(self) -> None:
        result = self.mailboxes()
        self.assertEqual(
            set(result), {"accounts", "mailboxes", "excluded_stores", "warnings"}
        )
        self.assertEqual(result["excluded_stores"], [])
        self.assertEqual(len(result["accounts"]), 3)
        self.assertEqual(len(result["mailboxes"]), 7)
        for account in result["accounts"]:
            self.assertEqual(
                set(account), {"uuid", "label", "email", "declared"}
            )
            self.assertTrue(account["declared"])
        for mailbox in result["mailboxes"]:
            self.assertEqual(
                set(mailbox),
                {
                    "account",
                    "name",
                    "path",
                    "url",
                    "total",
                    "unread",
                    "included",
                },
            )
        self.assertEqual(result["warnings"], [])

    def test_declared_accounts_and_recalculated_counters(self) -> None:
        result = self.mailboxes()
        self.assertEqual(
            [account["uuid"] for account in result["accounts"]],
            [ACCOUNT_ICLOUD, ACCOUNT_GMAIL, ACCOUNT_LOCAL],
        )
        actual = {
            (mailbox["account"]["uuid"], mailbox["path"]): (
                mailbox["total"],
                mailbox["unread"],
                mailbox["included"],
            )
            for mailbox in result["mailboxes"]
        }
        self.assertEqual(actual, self.EXPECTED_MAILBOXES)
        # The fake counters stored in the fixture must be ignored.
        gmail_inbox = next(
            mailbox
            for mailbox in result["mailboxes"]
            if mailbox["account"]["uuid"] == ACCOUNT_GMAIL
            and mailbox["path"] == "INBOX"
        )
        self.assertEqual(gmail_inbox["total"], 2)
        self.assertEqual(gmail_inbox["unread"], 1)
        self.assertIn("Gmail", gmail_inbox["account"]["label"])

    def test_included_flags_follow_config_scope(self) -> None:
        self.use_config(ICLOUD_WITH_FACTURAS)
        result = self.mailboxes()
        included = {
            (mailbox["account"]["uuid"], mailbox["path"]): mailbox["included"]
            for mailbox in result["mailboxes"]
        }
        self.assertTrue(included[(ACCOUNT_ICLOUD, "INBOX")])
        self.assertTrue(included[(ACCOUNT_ICLOUD, "Facturas")])
        self.assertFalse(included[(ACCOUNT_ICLOUD, "Archivo")])
        self.assertFalse(included[(ACCOUNT_GMAIL, "INBOX")])
        declared = {
            account["uuid"]: account["declared"]
            for account in result["accounts"]
        }
        self.assertTrue(declared[ACCOUNT_ICLOUD])
        self.assertFalse(declared[ACCOUNT_GMAIL])
        self.assertFalse(declared[ACCOUNT_LOCAL])

    def test_no_accounts_warning(self) -> None:
        self.use_config("")
        result = self.mailboxes()
        self.assertEqual(warning_codes(result["warnings"]), ["W_NO_ACCOUNTS"])
        self.assertTrue(
            all(account["declared"] is False for account in result["accounts"])
        )
        self.assertTrue(
            all(mailbox["included"] is False for mailbox in result["mailboxes"])
        )

    def test_account_labels_unavailable(self) -> None:
        self.use_config("")
        labels = AccountLabels(
            self.fx.root / "missing-accounts.sqlite",
            tmp_dir=self.fx.home / "tmp",
        )
        result = search.run_mailboxes(
            AppleMailBackend(self.store, labels), self.config
        )
        self.assertEqual(
            warning_codes(result["warnings"]),
            ["W_NO_ACCOUNTS", "W_ACCOUNT_LABELS_UNAVAILABLE"],
        )
        for account in result["accounts"]:
            self.assertEqual(account["label"], account["uuid"])
            self.assertIsNone(account["email"])


# --------------------------------------------------------------------------- #
# body in search / new (PRD 12.5)
# --------------------------------------------------------------------------- #


BODY_UNREADABLE_SMIME = "W_BODY_UNREADABLE: S/MIME {kind} content is not supported"


class SearchBodyTest(SearchFixtureTest):
    """``body`` object and body warnings of ``search`` (UT-SR-05)."""

    SHARED = ("Shared duplicate",)  # uid 83143: a normal readable message

    def isolated(self) -> tuple[FixturePaths, object, AccountLabels, Config]:
        """A private store so a test may rewrite ``.emlx`` files."""
        fx = build_store()
        self.addCleanup(fx.cleanup)
        write_config(fx.home, DEFAULT_CONFIG)
        store = open_store(mail_root=fx.mail_root, tmp_root=fx.home / "tmp")
        self.addCleanup(store.close)
        labels = AccountLabels(fx.accounts_db, tmp_dir=fx.home / "tmp")
        return fx, store, labels, load_config(fx.home)

    def search_shared(self) -> dict:
        return self.run_search(subject=self.SHARED)

    def test_ut_sr_05_01_unopenable_emlx_is_unavailable_and_unreadable(self) -> None:
        """UT-SR-05.01: an .emlx that cannot be opened gives false/false/false."""
        denied = PermissionError(1, "Operation not permitted")
        with mock.patch("mailquery.emlx.open", side_effect=denied, create=True):
            result = self.search_shared()
        self.assertEqual(
            result["messages"][0]["body"],
            {"available": False, "readable": False, "partial": False, "truncated": False},
        )
        self.assertEqual(warning_codes(result["warnings"]), ["W_BODY_UNREADABLE"])

    def test_ut_sr_05_02_unresolvable_path_is_unavailable_and_unreadable(self) -> None:
        """UT-SR-05.02: a path that cannot be resolved gives false/false/false."""
        with mock.patch("mailquery.emlx.resolve_path", side_effect=RuntimeError("boom")):
            result = self.search_shared()
        self.assertEqual(
            result["messages"][0]["body"],
            {"available": False, "readable": False, "partial": False, "truncated": False},
        )
        self.assertEqual(warning_codes(result["warnings"]), ["W_BODY_UNREADABLE"])

    def test_ut_sr_05_03_message_without_mailbox_is_unavailable_and_unreadable(self) -> None:
        """UT-SR-05.03: a message without a folder gives false/false/false."""
        row = {"uid": 83143, "mailbox_id": 0}
        snippet, body, loaded = search._body_fields(self.backend, row)
        self.assertEqual(snippet, "")
        self.assertEqual(
            body,
            {"available": False, "readable": False, "partial": False, "truncated": False},
        )
        self.assertIsNone(loaded["source"]["emlx_path"])
        self.assertEqual(warning_codes(loaded["warnings"]), ["W_BODY_UNREADABLE"])

    def test_ut_sr_05_04_recoverable_corrupt_emlx_is_readable_with_corrupt_warning(self) -> None:
        """UT-SR-05.04: a recoverable corrupt .emlx gives true/true/false + W_EMLX_CORRUPT."""
        fx, store, labels, config = self.isolated()
        message = fx.message(83143)
        target = None
        for mailbox in store.mailboxes:
            target = emlx.resolve_path(store, mailbox, 83143)
            if target is not None:
                break
        self.assertIsNotNone(target)
        target.write_bytes(
            b"this-is-not-a-length\n"
            b"From: Recoverable <recover@fixture.example>\r\n"
            b"Subject: Recovered\r\n"
            b"\r\n"
            b"Recovered body.\r\n"
        )
        result = search.run_search(
            AppleMailBackend(store, labels), config,
            search.Filters(subject=(message.subject,)),
        )
        self.assertEqual(
            result["messages"][0]["body"],
            {"available": True, "readable": True, "partial": False, "truncated": False},
        )
        self.assertEqual(warning_codes(result["warnings"]), ["W_EMLX_CORRUPT"])

    def test_ut_sr_05_07_snippet_truncation_boundary_is_200_characters(self) -> None:
        """UT-SR-05.07: bodies of 200 and 201 characters: body.truncated false / true."""
        fx, store, labels, config = self.isolated()
        for length, truncated in ((200, False), (201, True)):
            with self.subTest(length=length):
                message = dataclasses.replace(fx.message(83143), body="a" * length)
                make_fixtures._write_emlx_files(fx.mail_root, message, fx.now)
                result = search.run_search(
                    AppleMailBackend(store, labels),
                    config,
                    search.Filters(subject=self.SHARED),
                )
                body = result["messages"][0]["body"]
                self.assertIs(body["truncated"], truncated)
                self.assertTrue(body["available"])
                self.assertTrue(body["readable"])

    def test_ut_sr_05_08_html_without_text_is_readable_with_empty_snippet(self) -> None:
        """UT-SR-05.08: HTML with no text gives true/true, empty snippet, W_HTML_NO_TEXT."""
        fx, store, labels, config = self.isolated()
        message = dataclasses.replace(
            fx.message(83200),
            body=None,
            html="<html><head><style>p{}</style></head><body><p> </p></body></html>",
        )
        make_fixtures._write_emlx_files(fx.mail_root, message, fx.now)
        result = search.run_search(
            AppleMailBackend(store, labels), config,
            search.Filters(subject=(message.subject,)),
        )
        found = [m for m in result["messages"] if m["uid"] == prefixed_uid(83200)]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["snippet"], "")
        self.assertEqual(
            found[0]["body"],
            {"available": True, "readable": True, "partial": False, "truncated": False},
        )
        self.assertEqual(warning_codes(result["warnings"]), ["W_HTML_NO_TEXT"])


class SearchBodySmimeTest(ExtendedSearchFixtureTest):
    """S/MIME bodies in ``search`` (UT-SR-05.05, .06) over the extended store."""

    def smime_result(self, uid: int, subject: str) -> tuple[dict, dict]:
        result = self.run_search(subject=(subject,))
        return self.message_by_uid(result, uid), result

    def test_ut_sr_05_05_encrypted_smime_is_available_but_unreadable(self) -> None:
        """UT-SR-05.05: encrypted S/MIME gives true/false/false and only W_BODY_UNREADABLE."""
        message, result = self.smime_result(UID_SMIME_ENCRYPTED, "Encrypted S/MIME")
        self.assertEqual(
            message["body"],
            {"available": True, "readable": False, "partial": False, "truncated": False},
        )
        self.assertEqual(
            result["warnings"], [BODY_UNREADABLE_SMIME.format(kind="encrypted")]
        )

    def test_ut_sr_05_06_signed_smime_is_available_but_unreadable(self) -> None:
        """UT-SR-05.06: signed S/MIME gives true/false/false and only W_BODY_UNREADABLE."""
        message, result = self.smime_result(UID_SMIME_SIGNED, "Signed S/MIME")
        self.assertEqual(
            message["body"],
            {"available": True, "readable": False, "partial": False, "truncated": False},
        )
        self.assertEqual(
            result["warnings"], [BODY_UNREADABLE_SMIME.format(kind="signed")]
        )


class LabelsUnavailableTest(SearchFixtureTest):
    """``W_ACCOUNT_LABELS_UNAVAILABLE`` in data commands (UT-SR-06)."""

    def setUp(self) -> None:
        super().setUp()
        with accounts_db_unavailable() as missing:
            self.labels = AccountLabels(missing, tmp_dir=self.fx.home / "tmp")
        self.backend = AppleMailBackend(self.store, self.labels)
        # Labels are unavailable, so the scope is declared by UUID.
        self.use_config(f'[scope."{ACCOUNT_ICLOUD}"]\n')

    def test_ut_sr_06_01_search_warns_that_labels_are_unavailable(self) -> None:
        """UT-SR-06.01: search carries W_ACCOUNT_LABELS_UNAVAILABLE."""
        result = self.run_search(subject=("Shared duplicate",))
        self.assertEqual(self.uids(result), [prefixed_uid(83143)])
        self.assertEqual(result["warnings"], [search.LABELS_UNAVAILABLE_WARNING])

    def test_ut_sr_06_02_show_warns_that_labels_are_unavailable(self) -> None:
        """UT-SR-06.02: show carries W_ACCOUNT_LABELS_UNAVAILABLE."""
        result = search.run_show(self.backend, self.config, 83143)
        self.assertEqual(result["warnings"], [search.LABELS_UNAVAILABLE_WARNING])

    def test_ut_sr_06_03_first_run_of_new_warns_labels_before_first_run(self) -> None:
        """UT-SR-06.03: first new run: labels warning first of the scope ones, W_FIRST_RUN last."""
        result = search.run_new(
            self.backend, self.config, self.fresh_state(), peek=True
        )
        codes = warning_codes(result["warnings"])
        self.assertEqual(codes[0], "W_ACCOUNT_LABELS_UNAVAILABLE")
        self.assertEqual(codes[-1], "W_FIRST_RUN")
        self.assertEqual(codes.count("W_ACCOUNT_LABELS_UNAVAILABLE"), 1)


class ShowAttachmentsUnreadableTest(ExtendedSearchFixtureTest):
    """``show`` attachments when the body cannot be read (UT-SR-12)."""

    def show(self, uid: int) -> dict:
        return search.run_show(self.backend, self.config, uid)

    def test_ut_sr_12_01_missing_emlx_takes_names_from_the_index_and_warns(self) -> None:
        """UT-SR-12.01: absent .emlx with index attachments: ``{index, name, cached_path}`` + warning."""
        result = self.show(UID_MISSING_EMLX_ATTACH)
        self.assertEqual(
            result["message"]["attachments"],
            [{"index": 1, "name": "ghost.pdf", "cached_path": None}],
        )
        self.assertEqual(
            warning_codes(result["warnings"]),
            ["W_EMLX_MISSING", "W_ATTACHMENTS_UNAVAILABLE"],
        )
        # Encrypted S/MIME is the exception: [] and only the body warning.
        encrypted = self.show(UID_SMIME_ENCRYPTED)
        self.assertEqual(encrypted["message"]["attachments"], [])
        self.assertEqual(
            encrypted["warnings"],
            [BODY_UNREADABLE_SMIME.format(kind="encrypted")],
        )

    def test_ut_sr_12_02_signed_smime_without_index_row_has_no_attachments(self) -> None:
        """UT-SR-12.02: signed S/MIME without an attachments row: [] and no warning."""
        result = self.show(UID_SMIME_SIGNED)
        self.assertEqual(result["message"]["attachments"], [])
        self.assertEqual(
            result["warnings"], [BODY_UNREADABLE_SMIME.format(kind="signed")]
        )


class _LockedConnection:
    """Connection proxy whose ``execute`` fails as a locked database does.

    ``failures`` is the number of ``execute`` calls that raise ``database is
    locked`` before the real connection answers (``None`` = always).
    """

    def __init__(self, real: sqlite3.Connection, failures: int | None) -> None:
        self._real = real
        self.failures = failures
        self.attempts = 0

    def execute(self, sql: str, params=()):
        self.attempts += 1
        if self.failures is None or self.failures > 0:
            if self.failures is not None:
                self.failures -= 1
            raise sqlite3.OperationalError("database is locked")
        return self._real.execute(sql, params)

    def __getattr__(self, name: str):
        return getattr(self._real, name)


class DatabaseLockedTest(SearchFixtureTest):
    """UT-SR-13: queries and the folder catalog retry once on a locked database."""

    def lock(self, failures: int | None) -> _LockedConnection:
        self.store.mailboxes  # load the catalog while the database is not locked
        proxy = _LockedConnection(self.store.connection, failures)
        self.store.connection = proxy
        return proxy

    def test_ut_sr_13_01_query_locked_once_succeeds_after_one_retry(self) -> None:
        """UT-SR-13.01: a query locked once succeeds after a retry at 100 ms."""
        proxy = self.lock(1)
        with mock.patch("time.sleep") as sleep:
            result = self.run_search()
        self.assertEqual(self.uids(result), DEFAULT_UIDS)
        sleep.assert_called_once_with(0.1)
        self.assertGreater(proxy.attempts, 1)

    def test_ut_sr_13_02_persistent_lock_is_db_busy_with_hint(self) -> None:
        """UT-SR-13.02: a persistent lock => E_DB_BUSY, exit 5, non-empty hint, one retry."""
        proxy = self.lock(None)
        with mock.patch("time.sleep") as sleep:
            with self.assertRaises(MailqueryError) as context:
                self.run_search()
        self.assertEqual(context.exception.code, "E_DB_BUSY")
        self.assertEqual(context.exception.exit_code, 5)
        self.assertTrue(context.exception.hint)
        sleep.assert_called_once_with(0.1)
        self.assertEqual(proxy.attempts, 2)

    def test_ut_sr_13_03_locked_folder_catalog_is_db_busy(self) -> None:
        """UT-SR-13.03: the folder catalog locked => E_DB_BUSY (after one retry)."""
        proxy = _LockedConnection(self.store.connection, None)
        self.store.connection = proxy
        self.store._mailboxes = None
        with mock.patch("time.sleep") as sleep:
            with self.assertRaises(MailqueryError) as context:
                self.store.mailboxes
        self.assertEqual(context.exception.code, "E_DB_BUSY")
        self.assertEqual(context.exception.exit_code, 5)
        self.assertTrue(context.exception.hint)
        sleep.assert_called_once_with(0.1)
        self.assertEqual(proxy.attempts, 2)


class InboxDefinitionTest(ExtendedSearchFixtureTest):
    """UT-SR-14: INBOX is the top-level ``INBOX`` folder only (PRD A.5.3)."""

    def mailbox(self, rowid: int):
        return self.store.mailbox(rowid)

    def test_ut_sr_14_01_top_level_inbox_in_lowercase_is_inbox(self) -> None:
        """UT-SR-14.01: a top-level ``inbox`` in lowercase is INBOX."""
        from mailquery.store import _mailbox_from_row

        for url in ("imap://U/inbox", "imap://U/INBOX", "imap://U/Inbox"):
            with self.subTest(url=url):
                row = {"rowid": 1, "url": url}
                self.assertTrue(_mailbox_from_row(row, {}).is_inbox)
        self.assertTrue(self.mailbox(1).is_inbox)

    def test_ut_sr_14_02_nested_inbox_is_a_normal_folder(self) -> None:
        """UT-SR-14.02: ``Proyectos/Inbox`` is not INBOX, neither in is_inbox nor in the scope."""
        self.assertFalse(self.mailbox(20).is_inbox)
        self.assertFalse(self.mailbox(23).is_inbox)
        self.use_config(ICLOUD_ONLY)
        resolved = search._resolved_scope(self.config, self.backend)
        self.assertEqual(
            [mailbox["id"] for mailbox in resolved[0].mailboxes], [1]
        )
        result = self.run_search(subject=("Proyectos inbox item",))
        self.assertEqual(self.uids(result), [])


class DuplicatesExtendedTest(ExtendedSearchFixtureTest):
    """UT-SR-15: dedupe with the extended fixture."""

    def test_ut_sr_15_01_normal_folder_wins_over_the_aggregate_mailbox(self) -> None:
        """UT-SR-15.01: duplicate in a normal folder and an aggregate => the normal folder."""
        self.use_config(DEDUPE_CONFIG)
        result = self.run_search(subject=("Aggregate duplicate",))
        self.assertEqual(self.uids(result), [prefixed_uid(make_fixtures.UID_DUP_FOLDER)])
        message = result["messages"][0]
        self.assertEqual(message["duplicate_count"], 2)
        self.assertEqual(message["mailbox"]["name"], "Facturas")
        self.assertEqual(message["mailbox"]["account"]["uuid"], ACCOUNT_ICLOUD)

    def test_ut_sr_15_02_global_message_id_zero_is_unique(self) -> None:
        """UT-SR-15.02: global_message_id 0 => unique message, duplicate_count 1."""
        result = self.run_search(subject=("Global id zero",))
        self.assertEqual(self.uids(result), [prefixed_uid(make_fixtures.UID_GLOBAL_ZERO)])
        self.assertEqual(result["messages"][0]["duplicate_count"], 1)


class FolderReferenceTest(ExtendedSearchFixtureTest):
    """UT-SR-16: folder reference resolution (PRD 15.3)."""

    def set_catalog(self, mailboxes) -> None:
        mailboxes = tuple(mailboxes)
        self.store._mailboxes = mailboxes
        self.store._by_rowid = {mailbox.rowid: mailbox for mailbox in mailboxes}

    def reorder(self, first: list[int], drop: tuple[int, ...] = ()) -> dict:
        by_rowid = {mailbox.rowid: mailbox for mailbox in self.store.mailboxes}
        rest = [
            mailbox
            for rowid, mailbox in by_rowid.items()
            if rowid not in first and rowid not in drop
        ]
        self.set_catalog([by_rowid[rowid] for rowid in first] + rest)
        return by_rowid

    def test_ut_sr_16_01_inbox_is_always_the_account_inbox(self) -> None:
        """UT-SR-16.01: with ``Proyectos/Inbox`` in the account, INBOX is the account inbox."""
        self.assertEqual(self.store.resolve_mailbox(ACCOUNT_ICLOUD, "INBOX").rowid, 1)
        self.assertEqual(self.store.resolve_mailbox(ACCOUNT_ICLOUD, "inbox").rowid, 1)
        # Even when the nested folder comes first in the catalog.
        self.reorder([20, 23])
        self.assertEqual(self.store.resolve_mailbox(ACCOUNT_ICLOUD, "INBOX").rowid, 1)
        # An account without an inbox does not resolve INBOX to another folder.
        self.assertIsNone(self.store.resolve_mailbox(ACCOUNT_LOCAL, "INBOX"))

    def test_ut_sr_16_02_include_mailbox_is_tried_in_block_order(self) -> None:
        """UT-SR-16.02: INBOX with two declared accounts => the one of the first block."""
        gmail_first = (
            f'[scope."{GMAIL_LABEL}"]\n\n[scope."{ICLOUD_LABEL}"]\n'
        )
        icloud_first = (
            f'[scope."{ICLOUD_LABEL}"]\n\n[scope."{GMAIL_LABEL}"]\n'
        )
        for config, expected in ((gmail_first, 5), (icloud_first, 1)):
            with self.subTest(expected=expected):
                self.use_config(config)
                resolved = search._resolved_scope(self.config, self.backend)
                selected = search._resolve_include_mailboxes(
                    self.backend, resolved, ("INBOX",)
                )
                self.assertEqual([mailbox["id"] for mailbox in selected], [expected])

    def test_ut_sr_16_03_exact_path_or_url_beats_a_name_match(self) -> None:
        """UT-SR-16.03: an exact path or URL wins over another folder's name."""
        # Path: "Facturas" is the path of mailbox 2 and the name of 21 and 22.
        by_rowid = self.reorder([21, 22])
        self.assertEqual(
            self.store.resolve_mailbox(ACCOUNT_ICLOUD, "Facturas").rowid, 2
        )
        # URL: a folder whose name equals the URL of another folder comes first.
        target = by_rowid[22]
        decoy = dataclasses.replace(by_rowid[21], rowid=99, name=target.url)
        self.set_catalog([decoy, *self.store.mailboxes])
        self.assertEqual(
            self.store.resolve_mailbox(ACCOUNT_ICLOUD, target.url).rowid, 22
        )

    def test_ut_sr_16_04_same_name_resolves_to_the_first_in_the_catalog(self) -> None:
        """UT-SR-16.04: two folders with the same name in different paths => the first of mailboxes."""
        self.assertEqual(
            self.store.resolve_mailbox(ACCOUNT_ICLOUD, "Facturas").rowid, 2
        )
        # Without the top-level one, "Facturas" is only a name: the catalog order decides.
        self.reorder([21, 22], drop=(2,))
        self.assertEqual(
            self.store.resolve_mailbox(ACCOUNT_ICLOUD, "Facturas").rowid, 21
        )
        self.reorder([22, 21], drop=(2,))
        self.assertEqual(
            self.store.resolve_mailbox(ACCOUNT_ICLOUD, "Facturas").rowid, 22
        )


def search_attachments_warning() -> str:
    return (
        "W_ATTACHMENTS_UNAVAILABLE: attachment names come from the "
        "envelope index; the message body could not be read"
    )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

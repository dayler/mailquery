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

import unittest
from datetime import datetime, timedelta

from mailquery import search
from mailquery.accounts import AccountLabels
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
from tests.fixtures.make_fixtures import (
    ACCOUNT_GMAIL,
    ACCOUNT_ICLOUD,
    ACCOUNT_LOCAL,
    DEFAULT_CONFIG,
    GMAIL_LABEL,
    ICLOUD_LABEL,
    MAILBOX_URLS,
    FixturePaths,
    build_store,
    write_config,
    write_state,
)

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

    def test_matches_substring_and_case_insensitive(self) -> None:
        self.assertTrue(search.matches("invoice", "Invoice 2026-10"))
        self.assertTrue(search.matches("INVOICE", "invoice 2026-10"))
        self.assertFalse(search.matches("invoice", "Factura septiembre"))
        self.assertTrue(search.matches("", "anything"))

    def test_matches_wildcards(self) -> None:
        self.assertTrue(search.matches("*factura*", "La Factura de septiembre"))
        self.assertTrue(search.matches("f?ctura", "factura"))
        self.assertFalse(search.matches("f?ctura", "fctura"))
        self.assertTrue(search.matches("*2026-10*", "Invoice 2026-10"))
        self.assertFalse(search.matches("*2026-11*", "Invoice 2026-10"))

    def test_matches_is_accent_insensitive(self) -> None:
        self.assertTrue(search.matches("informacion", "Información mensual"))
        self.assertTrue(search.matches("INFORMACIÓN", "informacion mensual"))
        self.assertTrue(search.matches("septiembre", "Septiembre"))

    def test_matches_treats_regex_characters_literally(self) -> None:
        self.assertTrue(search.matches("a.b", "a.b"))
        self.assertFalse(search.matches("a.b", "axb"))
        self.assertTrue(search.matches("invoice (2026)", "invoice (2026)"))
        self.assertFalse(search.matches("invoice (2026)", "invoice 2026"))

    def test_filter_terms_mixed_semantics(self) -> None:
        self.assertEqual(
            search._filter_terms(("invoice 2026",)), ("invoice", "2026")
        )
        self.assertEqual(
            search._filter_terms(("*invoice 2026*",)), ("*invoice 2026*",)
        )
        self.assertEqual(
            search._filter_terms(("  a  b ", "*x*")), ("a", "b", "*x*")
        )
        self.assertEqual(search._filter_terms(("", "   ")), ())


# --------------------------------------------------------------------------- #
# Fixture-backed base class
# --------------------------------------------------------------------------- #


class SearchFixtureTest(unittest.TestCase):
    """Base class that opens the synthetic store, labels and config."""

    fx: FixturePaths

    @classmethod
    def setUpClass(cls) -> None:
        try:
            cls.fx = build_store()
        except NotImplementedError as exc:  # pragma: no cover - transitional
            raise unittest.SkipTest(f"dependency module is still a stub: {exc}")

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
        return StateStore(self.fx.home)

    def seed_state(
        self,
        *,
        age: timedelta = timedelta(hours=2),
        last_uid: int = 0,
        lookback_seconds: int = 600,
        emitted_uids: tuple[int, ...] = (),
    ) -> StateStore:
        state = self.fresh_state()
        last_date_received = int((self.fx.now - age).timestamp())
        write_state(
            self.fx.home,
            {
                "schema": 1,
                "updated_at": "",
                "last_run": None,
                "cursor": {
                    "last_date_received": last_date_received,
                    "last_uid": last_uid,
                    "lookback_seconds": lookback_seconds,
                },
                "emitted_uids": list(emitted_uids),
            },
        )
        return state

    def run_search(self, **filters: object) -> dict:
        return search.run_search(
            self.store, self.config, self.labels, search.Filters(**filters)
        )

    @staticmethod
    def uids(result: dict) -> list[int]:
        return [message["uid"] for message in result["messages"]]

    def message_by_uid(self, result: dict, uid: int) -> dict:
        for message in result["messages"]:
            if message["uid"] == uid:
                return message
        raise AssertionError(f"uid {uid} not in result: {self.uids(result)}")


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
        self.assertEqual(self.uids(result), [83160])
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
        self.assertEqual(self.uids(result), [83210])
        self.assertEqual(result["messages"][0]["mailbox"]["name"], "INBOX")

    def test_subject_substring_and_wildcards(self) -> None:
        cases = {
            ("invoice",): [2714],
            ("INVOICE",): [2714],
            ("*factura*",): [79658],
            ("?nvoice",): [2714],
            ("*2026-10*",): [2714],
            ("zzz-no-match",): [],
        }
        for patterns, expected in cases.items():
            with self.subTest(patterns=patterns):
                self.assertEqual(self.uids(self.run_search(subject=patterns)), expected)

    def test_subject_terms_are_and(self) -> None:
        self.assertEqual(
            self.uids(self.run_search(subject=("invoice 2026",))), [2714]
        )
        self.assertEqual(self.uids(self.run_search(subject=("invoice 2025",))), [])
        # A wildcard value is one pattern, so the phrase is matched literally.
        self.assertEqual(
            self.uids(self.run_search(subject=("*invoice 2026*",))), [2714]
        )
        # Repeating the flag is AND too.
        self.assertEqual(
            self.uids(self.run_search(subject=("invoice", "2026"))), [2714]
        )

    def test_from_to_cc_filters(self) -> None:
        self.assertEqual(
            self.uids(self.run_search(from_=("billing@fixture.example",))), [2714]
        )
        self.assertEqual(
            self.uids(self.run_search(from_=("Billing Team",))), [2714]
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
        self.assertEqual(self.uids(self.run_search(cc=("finance",))), [2714])
        self.assertEqual(self.uids(self.run_search(cc=("nobody",))), [])

    def test_relative_since_and_until(self) -> None:
        since_week = self.run_search(since=search.parse_relative_time("7d"))
        self.assertEqual(
            self.uids(since_week),
            [83170, 83160, 83150, 83143, 83210, 2714, 83220, 83200],
        )
        until_week = self.run_search(until=search.parse_relative_time("7d"))
        self.assertEqual(self.uids(until_week), [79658, 83180, 830, 83190])
        minute_window = self.run_search(since=search.parse_relative_time("45min"))
        self.assertEqual(self.uids(minute_window), [83170, 83160, 83150])

    def test_state_filters(self) -> None:
        self.assertEqual(
            self.uids(self.run_search(unread=True)), [83150, 83143, 83210, 2714]
        )
        self.assertEqual(self.uids(self.run_search(flagged=True)), [83150])
        self.assertEqual(
            self.uids(self.run_search(has_attachments=True)),
            [83210, 2714, 79658],
        )
        self.assertEqual(
            self.uids(self.run_search(flagged=True, unread=True)), [83150]
        )
        self.assertEqual(
            self.uids(
                self.run_search(
                    unread=True,
                    flagged=True,
                    since=search.parse_relative_time("7d"),
                )
            ),
            [83150],
        )

    def test_combined_filters_are_and(self) -> None:
        result = self.run_search(
            unread=True,
            since=search.parse_relative_time("7d"),
            has_attachments=True,
        )
        self.assertEqual(self.uids(result), [83210, 2714])

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
            {"available": True, "partial": False, "truncated": False},
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
        self.assertEqual(missing_message["uid"], 83170)
        self.assertEqual(missing_message["snippet"], "")
        self.assertFalse(missing_message["body"]["available"])
        self.assertIn("W_EMLX_MISSING", warning_codes(missing["warnings"]))

        corrupt = self.run_search(subject=("Corrupt body",))
        self.assertEqual(corrupt["messages"][0]["uid"], 83180)
        self.assertEqual(corrupt["messages"][0]["snippet"], "")
        self.assertIn("W_EMLX_CORRUPT", warning_codes(corrupt["warnings"]))

    def test_include_mailbox_adds_folder_and_keeps_inbox_priority(self) -> None:
        result = self.run_search(
            subject=("Shared duplicate",),
            include_mailboxes=("[Gmail]/All Mail",),
        )
        self.assertEqual(self.uids(result), [83143])
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

    def test_include_mailbox_unknown_folder(self) -> None:
        with self.assertRaises(MailqueryError) as context:
            self.run_search(include_mailboxes=("Nope",))
        self.assertEqual(context.exception.code, "E_MAILBOX_NOT_FOUND")
        self.assertEqual(context.exception.exit_code, 2)

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
        self.assertEqual(self.uids(result), [83143])
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
        self.assertEqual(self.uids(result), [83170, 83150, 83143, 2714, 83220, 83200, 830, 83190])
        self.assertNotIn(83160, self.uids(result))
        self.assertNotIn(83210, self.uids(result))


# --------------------------------------------------------------------------- #
# search --text
# --------------------------------------------------------------------------- #


class SearchTextTest(SearchFixtureTest):
    """Bounded content scans (RF-17): validation, matching and counters."""

    def test_text_requires_narrowing_filter(self) -> None:
        self.use_config(ICLOUD_ONLY)
        with self.assertRaises(MailqueryError) as context:
            self.run_search(text=("invoice",))
        self.assertEqual(context.exception.code, "E_UNBOUNDED_SCAN")
        self.assertEqual(context.exception.exit_code, 4)
        self.assertTrue(context.exception.hint)

    def test_text_narrowed_by_since(self) -> None:
        result = self.run_search(
            text=("invoice",), since=search.parse_relative_time("1y")
        )
        self.assertEqual(self.uids(result), [2714])
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
            [2714],
        )
        self.assertEqual(
            self.uids(
                self.run_search(
                    text=("remember *",), since=search.parse_relative_time("1y")
                )
            ),
            [83150],
        )
        self.assertEqual(
            self.uids(
                self.run_search(
                    text=("invoice attached",), since=search.parse_relative_time("1y")
                )
            ),
            [2714],
        )
        self.assertEqual(
            self.uids(
                self.run_search(
                    text=("invoice missing",), since=search.parse_relative_time("1y")
                )
            ),
            [],
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
        self.assertEqual(self.uids(result), [83190])
        self.assertEqual(result["scan"]["mode"], "text")
        self.assertEqual(result["scan"]["candidates"], 9)

    def test_text_narrowed_by_from_filter(self) -> None:
        self.use_config(ICLOUD_ONLY)
        result = self.run_search(text=("invoice",), from_=("billing",))
        self.assertEqual(self.uids(result), [2714])
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
                self.store,
                config,
                self.labels,
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
            self.store, self.config, self.labels, state, **kwargs
        )

    def test_first_run_is_a_baseline(self) -> None:
        state = self.fresh_state()
        result = self.run_new(state)
        self.assertEqual(
            set(result),
            {"count", "truncated", "hint", "messages", "scan", "cursor", "warnings"},
        )
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["messages"], [])
        self.assertFalse(result["truncated"])
        self.assertIsNone(result["hint"])
        self.assertEqual(warning_codes(result["warnings"]), ["W_FIRST_RUN"])
        self.assertIsNone(result["cursor"]["previous"])
        current = result["cursor"]["current"]
        self.assertEqual(
            set(current),
            {"last_date_received", "last_uid", "lookback_seconds"},
        )
        self.assertEqual(current["last_uid"], 83170)
        self.assertEqual(current["lookback_seconds"], 600)
        self.assertGreater(current["last_date_received"], 0)

        persisted = state.load()
        self.assertEqual(persisted.cursor.last_uid, 83170)
        self.assertEqual(set(persisted.emitted_uids), {83160, 83170})
        self.assertEqual(persisted.last_run.command, "new")

    def test_first_run_peek_does_not_write_state(self) -> None:
        state = self.fresh_state()
        result = self.run_new(state, peek=True)
        self.assertEqual(result["count"], 0)
        self.assertIsNone(result["cursor"]["current"])
        self.assertFalse((self.fx.home / "state.json").exists())

    def test_subsequent_run_emits_lookback_window(self) -> None:
        state = self.seed_state(age=timedelta(hours=2))
        result = self.run_new(state)
        self.assertEqual(self.uids(result), [83143, 83150, 83160, 83170])
        self.assertFalse(result["truncated"])
        self.assertIsNone(result["hint"])
        self.assertEqual(result["scan"]["candidates"], 4)
        self.assertEqual(result["scan"]["messages_read"], 3)
        self.assertIn("W_EMLX_MISSING", warning_codes(result["warnings"]))
        self.assertEqual(result["cursor"]["previous"]["last_uid"], 0)
        self.assertEqual(result["cursor"]["current"]["last_uid"], 83170)

        persisted = state.load()
        self.assertEqual(persisted.cursor.last_uid, 83170)
        self.assertEqual(
            set(persisted.emitted_uids), {83143, 83150, 83160, 83170}
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
        self.assertEqual(self.uids(first), [83143, 83150])
        self.assertTrue(first["truncated"])
        self.assertIsNotNone(first["hint"])
        self.assertIn("W_RESULTS_TRUNCATED", warning_codes(first["warnings"]))
        self.assertEqual(first["cursor"]["current"]["last_uid"], 83150)
        self.assertEqual(state.load().cursor.last_uid, 83150)

        second = self.run_new(state, limit=2)
        self.assertEqual(self.uids(second), [83160, 83170])
        self.assertFalse(second["truncated"])
        self.assertEqual(second["cursor"]["current"]["last_uid"], 83170)

    def test_peek_does_not_advance_cursor(self) -> None:
        state = self.seed_state(age=timedelta(hours=2))
        peeked = self.run_new(state, peek=True)
        self.assertEqual(self.uids(peeked), [83143, 83150, 83160, 83170])
        self.assertEqual(
            peeked["cursor"]["previous"], peeked["cursor"]["current"]
        )
        self.assertEqual(state.load().cursor.last_uid, 0)
        # The same messages are still new for the real run.
        self.assertEqual(self.run_new(state)["count"], 4)

    def test_emitted_ring_suppresses_duplicates(self) -> None:
        state = self.seed_state(age=timedelta(hours=2), emitted_uids=(83170,))
        result = self.run_new(state)
        self.assertEqual(self.uids(result), [83143, 83150, 83160])

    def test_new_scope_only_declared_accounts(self) -> None:
        self.use_config(ICLOUD_ONLY)
        state = self.seed_state(age=timedelta(hours=2))
        result = self.run_new(state)
        self.assertEqual(self.uids(result), [83143, 83150, 83170])
        self.assertNotIn(83160, self.uids(result))

    def test_new_without_accounts(self) -> None:
        self.use_config("")
        state = self.fresh_state()
        result = self.run_new(state)
        self.assertEqual(result["count"], 0)
        self.assertIsNone(result["cursor"]["current"])
        self.assertEqual(warning_codes(result["warnings"]), ["W_NO_ACCOUNTS"])

    def test_new_limit_accepts_up_to_500(self) -> None:
        state = self.fresh_state()
        result = self.run_new(state, limit=1000)
        self.assertEqual(result["count"], 0)
        self.assertIsNone(result["hint"])


# --------------------------------------------------------------------------- #
# show
# --------------------------------------------------------------------------- #


class ShowTest(SearchFixtureTest):
    """Message detail (``show``)."""

    def show(self, uid: int) -> dict:
        return search.run_show(self.store, self.labels, uid)

    def test_show_inbox_message(self) -> None:
        result = self.show(83143)
        self.assertEqual(set(result), {"message", "warnings"})
        message = result["message"]
        self.assertEqual(message["uid"], 83143)
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
            message["attachments"], [{"name": "factura-79658.pdf"}]
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

    def test_show_gmail_message_uses_physical_mailbox(self) -> None:
        message = self.show(83160)["message"]
        self.assertEqual(message["mailbox"]["account"]["uuid"], ACCOUNT_GMAIL)
        self.assertEqual(message["mailbox"]["path"], "[Gmail]/All Mail")
        self.assertTrue(message["readable"])

    def test_show_not_found_raises_usage_error(self) -> None:
        for uid in (99999, 12345):  # orphan .emlx (no row) and unknown uid
            with self.subTest(uid=uid):
                with self.assertRaises(MailqueryError) as context:
                    self.show(uid)
                self.assertEqual(context.exception.code, "E_USAGE")
                self.assertEqual(context.exception.exit_code, 2)
                self.assertTrue(context.exception.hint)


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
        return search.run_mailboxes(self.store, self.config, self.labels)

    def test_result_shape(self) -> None:
        result = self.mailboxes()
        self.assertEqual(set(result), {"accounts", "mailboxes", "warnings"})
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
        result = search.run_mailboxes(self.store, self.config, labels)
        self.assertEqual(
            warning_codes(result["warnings"]),
            ["W_NO_ACCOUNTS", "W_ACCOUNT_LABELS_UNAVAILABLE"],
        )
        for account in result["accounts"]:
            self.assertEqual(account["label"], account["uuid"])
            self.assertIsNone(account["email"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

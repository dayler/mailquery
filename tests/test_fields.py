"""Default row of ``search``/``new`` and ``--fields`` in the three commands.

Covers the TEST-CATALOG group UT-FLD (default row and ``--fields``) and DOC-10
(documentation of the row and of ``--fields``): the six-field default row, the
body and recipient reads it avoids, the field selection of ``search``, ``new``
and ``show``, the warnings that follow the delivered fields, the cursor
independence of ``new --fields``, the final F1 compatibility, and the help, the
READMEs, the skill and the recipes.

The stores are the synthetic Apple Mail fixture, the in-memory Outlook double
and the plugin double. Every run uses a temporary home: the real
``~/Library/Mail`` and ``~/.mailquery`` are never read.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from mailquery import cli as cli_mod
from mailquery import emlx
from mailquery import search
from mailquery.accounts import AccountLabels
from mailquery.backends import get_backend
from mailquery.backends import outlook_com
from mailquery.backends.apple_mail import AppleMailBackend
from mailquery.config import load_config
from mailquery.search import DEFAULT_ROW_FIELDS, SEARCH_ROW_FIELDS, SHOW_FIELDS
from mailquery.state import StateStore
from mailquery.store import open_store
from tests.fakes import outlook as fk
from tests.fakes.plugin import (
    ACCOUNT_LABEL,
    DEFAULT_ROWS,
    DRIVER,
    FakeEntryPoint,
    FakePluginBackend,
    internal_entry_points,
)
from tests.fixtures.make_fixtures import (
    DEFAULT_CONFIG,
    UID_ATTACH_MULTI,
    UID_ATTACH_SMIME,
    UID_BODY_SENDER_HEADERS,
    UID_MISSING_EMLX_ATTACH,
    build_store,
    prefixed_uid,
    write_config,
    write_state,
)

SEARCH_FIELDS_TEXT = ", ".join((*SEARCH_ROW_FIELDS, "all"))
SHOW_FIELDS_TEXT = ", ".join((*SHOW_FIELDS, "all"))
DEFAULT_ROW_TEXT = ", ".join(DEFAULT_ROW_FIELDS)

_ROOT = Path(__file__).resolve().parents[1]


def _all_installed(driver: str) -> bool:
    return True


def _warning_codes(warnings) -> list[str]:
    return [str(warning).split(":", 1)[0] for warning in warnings]


def _plugin_scope(home: Path) -> None:
    write_config(home, f'[scope."{DRIVER}:{ACCOUNT_LABEL}"]\n')


def _registry(plugin: object) -> object:
    return cli_mod.BackendRegistry(
        platform=sys.platform,
        entry_points=[
            *internal_entry_points(),
            FakeEntryPoint(DRIVER, plugin=plugin),
        ],
    )


def _plugin_row(**overrides) -> dict:
    row = dict(DEFAULT_ROWS[0])
    row.update(overrides)
    return row


def _plugin(*, rows=None, to_entries=None) -> FakePluginBackend:
    class _ConfiguredPlugin(FakePluginBackend):
        def __init__(self, context=None):
            super().__init__(context, rows=rows)

        def recipients(self, uids):
            self.calls.append("recipients")
            entries = [dict(entry) for entry in (to_entries or [])]
            return {str(uid): {"to": entries, "cc": []} for uid in uids}

    return _ConfiguredPlugin()


def _plugin_cli(home: Path, argv, plugin: object):
    registry = _registry(plugin)
    stdout, stderr = io.StringIO(), io.StringIO()
    with (
        mock.patch.object(cli_mod, "BackendRegistry", lambda *a, **k: registry),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        code = cli_mod.main(list(argv), home=home)
    raw = stdout.getvalue()
    return code, (json.loads(raw) if raw.strip() else None), stderr.getvalue()


class _AppleCase(unittest.TestCase):
    """One synthetic Apple Mail store per test, driven through ``cli.main``."""

    body_samples = False
    attachments = False
    extended = False

    def setUp(self) -> None:
        self.fx = build_store(
            body_samples=self.body_samples,
            attachments=self.attachments,
            extended=self.extended,
        )
        self.addCleanup(self.fx.cleanup)
        self.addCleanup(cli_mod._close_logging_handlers)
        write_config(self.fx.home, DEFAULT_CONFIG)

    def run_cli(self, *argv: str):
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            code = cli_mod.main(
                list(argv),
                home=self.fx.home,
                mail_root=self.fx.mail_root,
                accounts_db=self.fx.accounts_db,
            )
        raw = stdout.getvalue()
        return code, (json.loads(raw) if raw.strip() else None), stderr.getvalue()

    def run_ok(self, *argv: str) -> dict:
        code, payload, stderr = self.run_cli(*argv)
        self.assertEqual(code, 0, f"{argv}: {payload} {stderr}")
        assert payload is not None
        self.assertIs(payload.get("ok"), True)
        return payload

    def run_error(self, *argv: str, exit_code: int, code: str) -> dict:
        actual, payload, stderr = self.run_cli(*argv)
        self.assertEqual(actual, exit_code, f"{argv}: {payload} {stderr}")
        assert payload is not None
        self.assertIs(payload.get("ok"), False)
        self.assertEqual(payload["error"]["code"], code)
        return payload

    def backend(self) -> AppleMailBackend:
        store = open_store(
            mail_root=self.fx.mail_root, tmp_root=self.fx.home / "tmp"
        )
        self.addCleanup(store.close)
        labels = AccountLabels(self.fx.accounts_db, tmp_dir=self.fx.home / "tmp")
        return AppleMailBackend(store, labels)

    def config(self):
        return load_config(self.fx.home)

    def message_by_uid(self, payload: dict, uid: int) -> dict:
        wanted = prefixed_uid(uid)
        for message in payload["messages"]:
            if message["uid"] == wanted:
                return message
        self.fail(f"uid {wanted} not in result")


# --------------------------------------------------------------------------- #
# UT-FLD-01 — default row
# --------------------------------------------------------------------------- #


class DefaultRowTests(_AppleCase):
    """UT-FLD-01: the six-field default row of ``search`` and ``new``."""

    def test_ut_fld_01_01_default_rows_have_six_fields_with_full_row_values(self) -> None:
        """UT-FLD-01.01: default row has the six canonical fields with the full row values."""
        backend = self.backend()
        config = self.config()
        default = search.run_search(backend, config, search.Filters())
        full = search.run_search(backend, config, search.Filters(), fields=("all",))
        self.assertEqual(list(default["messages"][0]), list(DEFAULT_ROW_FIELDS))
        for short, complete in zip(default["messages"], full["messages"]):
            self.assertEqual(list(short), list(DEFAULT_ROW_FIELDS))
            for name in DEFAULT_ROW_FIELDS:
                self.assertEqual(short[name], complete[name], name)

        store = StateStore(self.fx.home, _all_installed)
        new_default = search.run_new(backend, config, store, peek=True)
        new_full = search.run_new(
            backend, config, StateStore(self.fx.home, _all_installed),
            peek=True, fields=("all",),
        )
        self.assertTrue(new_default["messages"])
        for short, complete in zip(new_default["messages"], new_full["messages"]):
            self.assertEqual(list(short), list(DEFAULT_ROW_FIELDS))
            for name in DEFAULT_ROW_FIELDS:
                self.assertEqual(short[name], complete[name], name)
        self._assert_outlook_default_row()

    def _assert_outlook_default_row(self) -> None:
        """The Outlook double gives the same six-field default row (UT-FLD-01.01)."""
        fake = self._outlook_items()
        backend = self._outlook_backend(fake)
        config = self._outlook_config()
        default = search.run_search(
            backend, config, search.Filters(since=0.0, limit=200)
        )
        full = search.run_search(
            backend, config, search.Filters(since=0.0, limit=200), fields=("all",)
        )
        self.assertGreater(default["count"], 0)
        for short, complete in zip(default["messages"], full["messages"]):
            self.assertEqual(list(short), list(DEFAULT_ROW_FIELDS))
            for name in DEFAULT_ROW_FIELDS:
                self.assertEqual(short[name], complete[name], name)

    def test_ut_fld_01_02_response_fields_do_not_change(self) -> None:
        """UT-FLD-01.02: only ``content_notice`` is added outside ``messages[]``."""
        default = self.run_ok("search", "--since", "1mo", "--subject", "Invoice 2026-10")
        full = self.run_ok(
            "search", "--since", "1mo", "--subject", "Invoice 2026-10", "--fields", "all"
        )
        self.assertEqual(set(default), set(full))
        self.assertIn("content_notice", default)
        self.assertEqual(default["hint"], full["hint"])
        self.assertEqual(default["truncated"], full["truncated"])
        self.assertEqual(default["scan"]["mode"], full["scan"]["mode"])
        self.assertEqual(default["scan"]["candidates"], full["scan"]["candidates"])
        self.assertEqual(default["scan"]["messages_read"], full["scan"]["messages_read"])

        new_default = self.run_ok("new", "--peek", "--limit", "1")
        new_full = self.run_ok("new", "--peek", "--limit", "1", "--fields", "all")
        self.assertEqual(set(new_default), set(new_full))
        self.assertEqual(new_default["cursor"], new_full["cursor"])
        self.assertEqual(new_default["hint"], new_full["hint"])
        self.assertEqual(new_default["scan"]["messages_read"], new_full["scan"]["messages_read"])

    # -- Outlook helpers ---------------------------------------------------- #

    def _outlook_items(self) -> "fk.FakeOutlook":
        return fk.FakeOutlook.item_matrix(
            datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
        )

    def _outlook_backend(self, fake) -> object:
        backend = get_backend(
            platform="win32",
            outlook_app=fake,
            registry=fake.registry,
            security_center=fake.security_center,
            pywin32=None,
            tmp_root=self.fx.home / "tmp",
        )
        self.addCleanup(backend.close)
        return backend

    def _outlook_config(self):
        write_config(self.fx.home, '[scope."ana@example.com"]\n')
        return load_config(self.fx.home)


# --------------------------------------------------------------------------- #
# UT-FLD-02 — no body reads
# --------------------------------------------------------------------------- #


class NoBodyReadTests(_AppleCase):
    """UT-FLD-02: the default row reads headers instead of bodies."""

    body_samples = True

    def test_ut_fld_02_01_search_and_new_read_no_bodies(self) -> None:
        """UT-FLD-02.01: without ``--text`` no body is extracted and one header block is read per row."""
        extract = mock.patch.object(emlx, "_extract_body_text", wraps=emlx._extract_body_text)
        with extract as spy:
            payload = self.run_ok("search", "--subject", "Invoice 2026-10")
        self.assertEqual(spy.call_count, 0)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["scan"]["messages_read"], 1)

        with mock.patch.object(
            emlx, "_extract_body_text", wraps=emlx._extract_body_text
        ) as spy:
            new_payload = self.run_ok("new", "--limit", "1")
        self.assertEqual(spy.call_count, 0)
        self.assertEqual(new_payload["count"], 1)
        self.assertEqual(new_payload["scan"]["messages_read"], 1)

    def test_ut_fld_02_02_outlook_reads_no_body_members(self) -> None:
        """UT-FLD-02.02: the Outlook default row opens items for headers only."""
        fake = fk.FakeOutlook.item_matrix(
            datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
        )
        backend = self._backend(fake)
        write_config(self.fx.home, '[scope."ana@example.com"]\n')
        payload = self._search(backend)
        self.assertGreater(payload["count"], 0)
        for member in ("Body", "HTMLBody", "BodyFormat"):
            self.assertEqual(
                fake.call_log.count(kind="Item", member=member), 0, member
            )
        # An S/MIME or unopenable item gives no header read and is never opened.
        unopened = {
            str(fake.item(key).entry_id)
            for key in (
                "smime_encrypted",
                "smime_signed",
                "unopenable_with_attachments",
                "unopenable_without_attachments",
            )
        }
        returned = {message["uid"].split(":", 1)[1] for message in payload["messages"]}
        self.assertTrue(unopened <= returned)
        self.assertEqual(
            backend.items_opened, len(returned) - len(unopened & returned)
        )
        for uid in unopened:
            self.assertNotIn(uid, backend._opened)

    def test_ut_fld_02_03_text_without_body_fields_returns_no_body(self) -> None:
        """UT-FLD-02.03: ``--text`` reads the body to filter but the row carries no body fields."""
        with mock.patch.object(
            emlx, "_extract_body_text", wraps=emlx._extract_body_text
        ) as spy:
            payload = self.run_ok("search", "--text", "Sender headers", "--since", "1d")
        self.assertGreater(spy.call_count, 0)
        self.assertEqual(payload["scan"]["mode"], "text")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(list(payload["messages"][0]), list(DEFAULT_ROW_FIELDS))

    def test_ut_fld_02_04_plugin_reads_no_body(self) -> None:
        """UT-FLD-02.04: a plugin default row calls neither ``load_snippet`` nor ``load_body``."""
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            _plugin_scope(home)
            plugin = _plugin(
                rows=[
                    _plugin_row(
                        uid="row-1",
                        subject="Pago https://evil.example/pay",
                        sender_name="Banco",
                        headers={
                            "Authentication-Results": "mx; spf=softfail dkim=none dmarc=fail",
                            "Reply-To": "otro@other.example",
                        },
                    )
                ]
            )
            code, payload, stderr = _plugin_cli(home, ["search", "--since", "2020-01-01"], plugin)
        self.assertEqual(code, 0, f"{payload} {stderr}")
        assert payload is not None
        self.assertNotIn("load_body", plugin.calls)
        self.assertNotIn("load_snippet", plugin.calls)
        message = payload["messages"][0]
        self.assertEqual(list(message), list(DEFAULT_ROW_FIELDS))
        codes = _warning_codes(payload["warnings"])
        self.assertNotIn("W_SENDER_AUTH_FAILED", codes)
        self.assertNotIn("W_REPLY_TO_MISMATCH", codes)

    def test_ut_fld_02_05_missing_emlx_reads_no_headers(self) -> None:
        """UT-FLD-02.05: a missing ``.emlx`` gives no header read, no count and no warnings."""
        payload = self.run_ok("search", "--subject", "Missing body")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["scan"]["messages_read"], 0)
        self.assertEqual(payload["warnings"], [])

    def test_ut_fld_02_06_to_filter_reads_recipients_without_delivering_them(self) -> None:
        """UT-FLD-02.06: ``--to`` filters on recipients without adding them to the row."""
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            _plugin_scope(home)
            plugin = _plugin(
                rows=[_plugin_row(uid="row-1", subject="Plain subject")],
                to_entries=[{"name": "https://evil.example/ana", "address": "ana@example.com"}],
            )
            code, payload, stderr = _plugin_cli(
                home, ["search", "--to", "evil.example", "--since", "2020-01-01"], plugin
            )
        self.assertEqual(code, 0, f"{payload} {stderr}")
        assert payload is not None
        self.assertEqual(payload["count"], 1)
        message = payload["messages"][0]
        self.assertNotIn("to", message)
        self.assertNotIn("cc", message)
        self.assertEqual(_warning_codes(payload["warnings"]), [])

    # -- Outlook helpers ---------------------------------------------------- #

    def _backend(self, fake):
        backend = get_backend(
            platform="win32",
            outlook_app=fake,
            registry=fake.registry,
            security_center=fake.security_center,
            pywin32=None,
            tmp_root=self.fx.home / "tmp",
        )
        self.addCleanup(backend.close)
        return backend

    def _search(self, backend) -> dict:
        patcher = mock.patch.object(outlook_com, "get_drive_type", self._fake_drive_type)
        patcher.start()
        self.addCleanup(patcher.stop)
        config = load_config(self.fx.home)
        return search.run_search(
            backend, config, search.Filters(since=0.0, limit=200)
        )

    @staticmethod
    def _fake_drive_type(path: str) -> int:
        return fk.DRIVE_FIXED


# --------------------------------------------------------------------------- #
# UT-FLD-03 — ``--fields`` in search and new
# --------------------------------------------------------------------------- #


class SearchFieldsTests(_AppleCase):
    """UT-FLD-03: ``--fields`` extends the search/new row."""

    body_samples = True

    def test_ut_fld_03_01_snippet_is_appended(self) -> None:
        """UT-FLD-03.01: ``--fields snippet`` adds ``snippet`` at the end of the default row."""
        payload = self.run_ok("search", "--subject", "Sender headers", "--fields", "snippet")
        message = payload["messages"][0]
        self.assertEqual(list(message), [*DEFAULT_ROW_FIELDS, "snippet"])
        self.assertIn("hxxps://evil.example/pay", message["snippet"])

    def test_ut_fld_03_02_all_gives_the_full_row(self) -> None:
        """UT-FLD-03.02: ``--fields all`` gives the full search row in canonical order."""
        payload = self.run_ok("search", "--subject", "Sender headers", "--fields", "all")
        self.assertEqual(list(payload["messages"][0]), list(SEARCH_ROW_FIELDS))

    def test_ut_fld_03_03_comma_and_repeated_values_match(self) -> None:
        """UT-FLD-03.03: ``to,uid`` and ``uid`` + ``to`` give the default row plus ``to``."""
        comma = self.run_ok("search", "--subject", "Invoice 2026-10", "--fields", "to,uid")
        repeated = self.run_ok(
            "search", "--subject", "Invoice 2026-10", "--fields", "uid", "--fields", "to"
        )
        expected = [
            "uid",
            "subject",
            "from",
            "to",
            "date_received",
            "is_read",
            "has_attachments",
        ]
        self.assertEqual(list(comma["messages"][0]), expected)
        self.assertEqual(comma["messages"], repeated["messages"])

    def test_ut_fld_03_04_unknown_and_empty_fields_are_usage_errors(self) -> None:
        """UT-FLD-03.04: unknown or empty names ⇒ E_USAGE with the search field list."""
        for names in (["remitente"], [""], ["uid,,to"]):
            with self.subTest(fields=names):
                payload = self.run_error(
                    "search", "--fields", *names, exit_code=2, code="E_USAGE"
                )
                name = "" if names != ["remitente"] else "remitente"
                self.assertEqual(
                    payload["error"]["message"],
                    f"unknown field '{name}' in --fields",
                )
                self.assertEqual(
                    payload["error"]["hint"], f"valid fields: {SEARCH_FIELDS_TEXT}"
                )

    def test_ut_fld_03_05_error_happens_before_the_home_and_the_store(self) -> None:
        """UT-FLD-03.05: ``--fields`` is validated before creating the home and opening the store."""
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            stdout, stderr = io.StringIO(), io.StringIO()
            with (
                mock.patch.object(
                    cli_mod, "ensure_app_home", side_effect=AssertionError("home")
                ),
                mock.patch(
                    "mailquery.store.open_store",
                    side_effect=AssertionError("store"),
                ),
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                code = cli_mod.main(["search", "--fields", "nope"], home=home)
        self.assertEqual(code, 2)
        self.assertFalse(home.exists())
        self.assertEqual(json.loads(stdout.getvalue())["error"]["code"], "E_USAGE")

    def test_ut_fld_03_06_field_names_are_case_sensitive(self) -> None:
        """UT-FLD-03.06: spaces around names are stripped and names stay case-sensitive."""
        spaced = self.run_ok("search", "--subject", "Invoice 2026-10", "--fields", "to, uid")
        plain = self.run_ok("search", "--subject", "Invoice 2026-10", "--fields", "to,uid")
        self.assertEqual(spaced["messages"], plain["messages"])
        for name in ("ALL", "Snippet"):
            with self.subTest(name=name):
                payload = self.run_error(
                    "search", "--fields", name, exit_code=2, code="E_USAGE"
                )
                self.assertEqual(
                    payload["error"]["message"], f"unknown field '{name}' in --fields"
                )
        single = self.run_error("search", "--fields", " ", exit_code=2, code="E_USAGE")
        self.assertEqual(single["error"]["message"], "unknown field '' in --fields")

    def test_ut_fld_03_07_new_accepts_fields(self) -> None:
        """UT-FLD-03.07: ``new --fields snippet`` adds the snippet to the default row."""
        payload = self.run_ok("new", "--peek", "--limit", "1", "--fields", "snippet")
        message = payload["messages"][0]
        self.assertEqual(list(message), [*DEFAULT_ROW_FIELDS, "snippet"])


# --------------------------------------------------------------------------- #
# UT-FLD-04 — ``show --fields``
# --------------------------------------------------------------------------- #


class ShowFieldsTests(_AppleCase):
    """UT-FLD-04: ``--fields`` selects the fields of ``show``."""

    attachments = True

    def test_ut_fld_04_01_attachments_only(self) -> None:
        """UT-FLD-04.01: ``--fields attachments`` delivers only ``uid`` and the attachments."""
        payload = self.run_ok("show", prefixed_uid(UID_ATTACH_MULTI), "--fields", "attachments")
        message = payload["message"]
        self.assertEqual(list(message), ["uid", "attachments"])
        self.assertTrue(message["attachments"])
        self.assertEqual(_warning_codes(payload["warnings"]), [])

        smime = self.run_ok(
            "show", prefixed_uid(UID_ATTACH_SMIME), "--fields", "attachments"
        )
        self.assertEqual(list(smime["message"]), ["uid", "attachments"])
        self.assertEqual(smime["message"]["attachments"], [])
        self.assertEqual(_warning_codes(smime["warnings"]), [])

    def test_ut_fld_04_02_body_text_does_not_query_attachments(self) -> None:
        """UT-FLD-04.02: ``--fields body_text`` never calls the attachment operations."""
        backend = self.backend()
        uid = backend.parse_uid(str(UID_ATTACH_MULTI))
        config = self.config()
        with (
            mock.patch.object(backend, "attachments", side_effect=AssertionError("attachments")),
            mock.patch.object(
                backend, "attachment_names", side_effect=AssertionError("attachment_names")
            ),
        ):
            payload = search.run_show(
                backend, config, uid, fields=("body_text",)
            )
        self.assertEqual(list(payload["message"]), ["uid", "body_text"])
        self.assertTrue(payload["message"]["body_text"])

    def test_ut_fld_04_03_headers_without_reading_the_body(self) -> None:
        """UT-FLD-04.03: ``--fields headers`` reads the header block only."""
        backend = self.backend()
        uid = backend.parse_uid(str(2714))
        config = self.config()
        with mock.patch.object(
            emlx, "_extract_body_text", side_effect=AssertionError("body")
        ):
            payload = search.run_show(backend, config, uid, fields=("headers",))
        self.assertEqual(list(payload["message"]), ["uid", "headers"])
        self.assertEqual(
            set(payload["message"]["headers"]),
            {"From", "To", "Cc", "Subject", "Date", "Message-ID"},
        )

    def test_ut_fld_04_04_without_fields_show_is_unchanged(self) -> None:
        """UT-FLD-04.04: without ``--fields``, ``show`` returns the whole message."""
        default = self.run_ok("show", prefixed_uid(UID_ATTACH_MULTI))
        full = self.run_ok(
            "show", prefixed_uid(UID_ATTACH_MULTI), "--fields", "all"
        )
        self.assertEqual(list(default["message"]), list(SHOW_FIELDS))
        self.assertEqual(default["message"], full["message"])
        self.assertIn("content_notice", default)

    def test_ut_fld_04_05_unknown_field_uses_the_show_list(self) -> None:
        """UT-FLD-04.05: an unknown show field ⇒ E_USAGE with the show field list."""
        payload = self.run_error(
            "show", prefixed_uid(UID_ATTACH_MULTI), "--fields", "snippet",
            exit_code=2, code="E_USAGE",
        )
        self.assertEqual(payload["error"]["message"], "unknown field 'snippet' in --fields")
        self.assertEqual(payload["error"]["hint"], f"valid fields: {SHOW_FIELDS_TEXT}")

    def test_ut_fld_04_06_source_and_partial_read_and_deliver_the_body(self) -> None:
        """UT-FLD-04.06: ``source`` and ``partial`` alone read the body and keep its warnings."""
        for field in ("source", "partial"):
            with self.subTest(field=field):
                payload = self.run_ok(
                    "show", prefixed_uid(83180), "--fields", field
                )
                self.assertEqual(list(payload["message"]), ["uid", field])
                self.assertIn("W_EMLX_CORRUPT", _warning_codes(payload["warnings"]))


# --------------------------------------------------------------------------- #
# UT-FLD-05 — warnings follow the delivered fields
# --------------------------------------------------------------------------- #


class DeliveredWarningsTests(_AppleCase):
    """UT-FLD-05: content warnings depend on the delivered fields."""

    body_samples = True
    extended = True

    def test_ut_fld_05_01_body_warnings_only_with_the_body(self) -> None:
        """UT-FLD-05.01: hidden text and body URLs count only when the body is delivered."""
        default = self.run_ok("search", "--subject", "Hidden html body")
        self.assertEqual(_warning_codes(default["warnings"]), [])
        for fields in ("snippet", "body", "all"):
            with self.subTest(fields=fields):
                payload = self.run_ok(
                    "search", "--subject", "Hidden html body", "--fields", fields
                )
                self.assertIn("W_HIDDEN_CONTENT", _warning_codes(payload["warnings"]))

        links_default = self.run_ok("search", "--subject", "Sender headers")
        self.assertNotIn("W_EXTERNAL_LINKS", _warning_codes(links_default["warnings"]))
        for fields in ("snippet", "body", "all"):
            with self.subTest(fields=fields):
                payload = self.run_ok(
                    "search", "--subject", "Sender headers", "--fields", fields
                )
                self.assertIn("W_EXTERNAL_LINKS", _warning_codes(payload["warnings"]))

        show = self.run_ok(
            "show", prefixed_uid(UID_BODY_SENDER_HEADERS), "--fields", "body_text"
        )
        self.assertIn("W_EXTERNAL_LINKS", _warning_codes(show["warnings"]))

    def test_ut_fld_05_02_subject_and_recipient_urls(self) -> None:
        """UT-FLD-05.02: a subject URL counts by default; a recipient URL only with ``to``."""
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            _plugin_scope(home)
            row = _plugin_row(uid="row-1", subject="Pago https://evil.example/pay")
            plugin = _plugin(
                rows=[row],
                to_entries=[
                    {"name": "https://evil.example/ana", "address": "ana@example.com"}
                ],
            )
            code, default, stderr = _plugin_cli(
                home, ["search", "--since", "2020-01-01"], plugin
            )
            self.assertEqual(code, 0, f"{default} {stderr}")
            assert default is not None
            self.assertIn("W_EXTERNAL_LINKS: 1 external link(s)", default["warnings"][0])
            code, with_to, stderr = _plugin_cli(
                home,
                ["search", "--since", "2020-01-01", "--fields", "to"],
                _plugin(
                    rows=[row],
                    to_entries=[
                        {"name": "https://evil.example/ana", "address": "ana@example.com"}
                    ],
                ),
            )
            self.assertEqual(code, 0, f"{with_to} {stderr}")
            assert with_to is not None
            self.assertIn("W_EXTERNAL_LINKS: 2 external link(s)", with_to["warnings"][0])

    def test_ut_fld_05_03_sender_warnings_always_appear(self) -> None:
        """UT-FLD-05.03: the sender warnings appear with and without ``--fields``."""
        for argv in (
            ("search", "--subject", "Sender headers"),
            ("search", "--subject", "Sender headers", "--fields", "all"),
            ("show", prefixed_uid(UID_BODY_SENDER_HEADERS), "--fields", "attachments"),
        ):
            with self.subTest(argv=argv):
                payload = self.run_ok(*argv)
                codes = _warning_codes(payload["warnings"])
                self.assertIn("W_SENDER_AUTH_FAILED", codes)
                self.assertIn("W_REPLY_TO_MISMATCH", codes)

    def test_ut_fld_05_04_body_status_warnings_need_a_delivered_body(self) -> None:
        """UT-FLD-05.04: body-status warnings need the body; ``--text`` alone does not emit them."""
        default = self.run_ok("search", "--subject", "Signed S/MIME with auth results")
        self.assertNotIn("W_BODY_UNREADABLE", _warning_codes(default["warnings"]))
        full = self.run_ok(
            "search", "--subject", "Signed S/MIME with auth results", "--fields", "all"
        )
        self.assertIn("W_BODY_UNREADABLE", _warning_codes(full["warnings"]))

        missing = self.run_ok("search", "--subject", "Missing body")
        self.assertNotIn("W_EMLX_MISSING", _warning_codes(missing["warnings"]))
        missing_full = self.run_ok("search", "--subject", "Missing body", "--fields", "all")
        self.assertIn("W_EMLX_MISSING", _warning_codes(missing_full["warnings"]))

        text = self.run_ok("search", "--text", "Signed", "--since", "1d")
        self.assertNotIn("W_BODY_UNREADABLE", _warning_codes(text["warnings"]))
        text_full = self.run_ok(
            "search", "--text", "Signed", "--since", "1d", "--fields", "snippet"
        )
        self.assertIn("W_BODY_UNREADABLE", _warning_codes(text_full["warnings"]))

    def test_ut_fld_05_05_attachments_unavailable_only_with_attachments(self) -> None:
        """UT-FLD-05.05: ``W_ATTACHMENTS_UNAVAILABLE`` only when ``show`` delivers attachments."""
        headers = self.run_ok(
            "show", prefixed_uid(UID_MISSING_EMLX_ATTACH), "--fields", "headers"
        )
        self.assertNotIn("W_ATTACHMENTS_UNAVAILABLE", _warning_codes(headers["warnings"]))
        attachments = self.run_ok(
            "show", prefixed_uid(UID_MISSING_EMLX_ATTACH), "--fields", "attachments"
        )
        self.assertIn(
            "W_ATTACHMENTS_UNAVAILABLE", _warning_codes(attachments["warnings"])
        )


# --------------------------------------------------------------------------- #
# UT-FLD-06 — ``new --fields``
# --------------------------------------------------------------------------- #


class NewFieldsTests(_AppleCase):
    """UT-FLD-06: ``new --fields`` extends the row without touching the cursor."""

    body_samples = True

    def _seed_state(self) -> None:
        write_state(
            self.fx.home,
            {
                "schema": 2,
                "updated_at": "",
                "last_run": None,
                "cursor": {
                    "last_date_received": int(
                        (self.fx.now - timedelta(hours=2)).timestamp()
                    ),
                    "last_uid": prefixed_uid(1),
                    "lookback_seconds": 600,
                },
                "emitted_uids": [],
            },
        )

    def test_ut_fld_06_01_snippet_is_added(self) -> None:
        """UT-FLD-06.01: ``new --fields snippet`` adds the snippet to the default row."""
        payload = self.run_ok("new", "--peek", "--limit", "2", "--fields", "snippet")
        self.assertTrue(payload["messages"])
        for message in payload["messages"]:
            self.assertEqual(list(message), [*DEFAULT_ROW_FIELDS, "snippet"])

    def test_ut_fld_06_02_cursor_advances_the_same(self) -> None:
        """UT-FLD-06.02: the state after ``new --fields snippet`` equals the plain ``new`` state."""
        self._seed_state()
        self.run_ok("new", "--limit", "2", "--fields", "snippet")
        with_fields = (self.fx.home / "state.json").read_text(encoding="utf-8")

        self._seed_state()
        self.run_ok("new", "--limit", "2")
        plain = (self.fx.home / "state.json").read_text(encoding="utf-8")
        self.assertEqual(json.loads(with_fields), json.loads(plain))


# --------------------------------------------------------------------------- #
# UT-FLD-07 — final F1 compatibility
# --------------------------------------------------------------------------- #


class CompatibilityTests(_AppleCase):
    """UT-FLD-07: only ``content_notice`` is new with the full row."""

    def test_ut_fld_07_01_only_content_notice_is_new(self) -> None:
        """UT-FLD-07.01: full rows keep every field and the only new payload key is ``content_notice``."""
        search_payload = self.run_ok("search", "--since", "1mo", "--fields", "all")
        for message in search_payload["messages"]:
            self.assertEqual(list(message), list(SEARCH_ROW_FIELDS))
        self.assertEqual(
            set(search_payload),
            {
                "ok",
                "command",
                "generated_at",
                "content_notice",
                "count",
                "truncated",
                "hint",
                "warnings",
                "messages",
                "scan",
            },
        )
        new_payload = self.run_ok("new", "--peek", "--fields", "all")
        for message in new_payload["messages"]:
            self.assertEqual(list(message), list(SEARCH_ROW_FIELDS))
        self.assertEqual(
            set(new_payload),
            {
                "ok",
                "command",
                "generated_at",
                "content_notice",
                "count",
                "truncated",
                "hint",
                "warnings",
                "messages",
                "scan",
                "cursor",
            },
        )
        show_payload = self.run_ok("show", prefixed_uid(2714))
        self.assertEqual(list(show_payload["message"]), list(SHOW_FIELDS))
        self.assertEqual(
            set(show_payload),
            {"ok", "command", "generated_at", "content_notice", "message", "warnings"},
        )


# --------------------------------------------------------------------------- #
# DOC-10 — documentation of the row and of ``--fields``
# --------------------------------------------------------------------------- #


class DocumentationTests(unittest.TestCase):
    """DOC-10: help, READMEs, skill and recipes describe the row and ``--fields``."""

    def _help(self, command: str) -> str:
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            code = cli_mod.main([command, "--help"])
        self.assertEqual(code, 0, stderr.getvalue())
        return stdout.getvalue()

    def test_doc_10_01_help_lists_the_fields_of_each_command(self) -> None:
        """DOC-10.01: each command help describes ``--fields`` with its field list."""
        for command, expected in (
            ("search", SEARCH_FIELDS_TEXT),
            ("new", SEARCH_FIELDS_TEXT),
            ("show", SHOW_FIELDS_TEXT),
        ):
            text = self._help(command)
            self.assertIn("--fields", text)
            self.assertIn(expected, " ".join(text.split()))

    def test_doc_10_02_readmes_document_the_default_row_and_fields(self) -> None:
        """DOC-10.02: both READMEs document the default row and ``--fields`` with examples."""
        english = (_ROOT / "README.md").read_text(encoding="utf-8")
        spanish = (_ROOT / "README.es.md").read_text(encoding="utf-8")
        for text in (english, spanish):
            for expected in ("--fields snippet", "--fields all", "--fields attachments"):
                self.assertIn(expected, text)
        for name in DEFAULT_ROW_FIELDS:
            self.assertIn(name, english)
            self.assertIn(name, spanish)
        self.assertIn("default row", english)
        self.assertIn("fila por defecto", spanish)
        self.assertIn("--fields", spanish)

    def test_doc_10_03_skill_explains_the_row_and_the_no_content_triage(self) -> None:
        """DOC-10.03: the skill documents the row, ``new --fields snippet`` and the triage rule."""
        skill = (_ROOT / "skills" / "mailquery" / "SKILL.md").read_text(encoding="utf-8")
        for expected in (
            "default row",
            "--fields snippet",
            "new --fields snippet",
            "search --unread",
            "Triage with metadata",
        ):
            self.assertIn(expected, skill)

    def test_doc_10_04_recipes_request_the_fields_they_consume(self) -> None:
        """DOC-10.04: the digest recipe asks for the snippet; no recipe consumes an undelivered field."""
        digest = (_ROOT / "docs" / "recipes" / "01-new-mail-digest.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("mailquery new --fields snippet", digest)
        recipe = (
            _ROOT / "docs" / "recipes" / "02-search-invoices.md"
        ).read_text(encoding="utf-8")
        commands = [
            line.strip()
            for line in recipe.splitlines()
            if line.strip().startswith("mailquery search")
        ]
        self.assertTrue(commands)
        for command in commands:
            self.assertIn("--fields", command)

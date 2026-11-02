"""Tests for ``mailquery.config``.

Covers the strict ``config.toml`` schema, duration parsing, the application
home layout and the account/mailbox scope resolution rules (PRD 15). Scope
resolution is tested against small fake store/labels objects (always runs) and
against the synthetic fixture store (skipped while ``store.py``/``accounts.py``
are still stubs).
"""

from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path

from mailquery.accounts import AccountLabel
from mailquery.config import (
    APP_HOME_SUBDIRS,
    Config,
    LoggingConfig,
    NewConfig,
    ScopeEntry,
    SearchConfig,
    app_home,
    ensure_app_home,
    load_config,
    parse_duration,
    resolve_scope,
)
from mailquery.errors import MailqueryError, exit_code_for
from mailquery.store import Mailbox

from tests.fixtures.make_fixtures import (
    ACCOUNT_GMAIL,
    ACCOUNT_ICLOUD,
    ACCOUNT_LOCAL,
    DEFAULT_CONFIG,
    build_store,
    write_config,
)

ACCOUNT_ICLOUD_ALT = "AAAAAAAA-0000-4000-8000-000000000009"
ACCOUNT_MISSING = "DDDDDDDD-0000-4000-8000-000000000004"

ICLOUD_LABEL = "iCloud (fixture@icloud.com)"
ICLOUD_ALT_LABEL = "iCloud alt (fixture@icloud.com)"
GMAIL_LABEL = "Gmail (fixture@gmail.com)"
LOCAL_LABEL = "On My Device"
MISSING_LABEL = "Archive (old@example.com)"

GMAIL_URL_INBOX = f"imap://{ACCOUNT_GMAIL}/INBOX"
GMAIL_URL_IMPORTANT = f"imap://{ACCOUNT_GMAIL}/%5BGmail%5D/Important"
GMAIL_URL_ALL = f"imap://{ACCOUNT_GMAIL}/%5BGmail%5D/All%20Mail"


# --------------------------------------------------------------------------- #
# Fake store / labels
# --------------------------------------------------------------------------- #


def _mailbox(
    rowid: int,
    account_uuid: str,
    url: str,
    name: str,
    path: str,
    *,
    is_inbox: bool = False,
    is_aggregate: bool = False,
    account_kind: str = "imap",
) -> Mailbox:
    return Mailbox(
        rowid=rowid,
        url=url,
        name=name,
        path=path,
        account_uuid=account_uuid,
        account_kind=account_kind,
        is_inbox=is_inbox,
        is_aggregate=is_aggregate,
        message_count=0,
        unread_count=0,
    )


def _fake_mailboxes() -> tuple[Mailbox, ...]:
    return (
        _mailbox(1, ACCOUNT_ICLOUD, f"imap://{ACCOUNT_ICLOUD}/INBOX", "INBOX", "INBOX", is_inbox=True),
        _mailbox(2, ACCOUNT_ICLOUD, f"imap://{ACCOUNT_ICLOUD}/Facturas", "Facturas", "Facturas"),
        _mailbox(3, ACCOUNT_ICLOUD, f"imap://{ACCOUNT_ICLOUD}/Archivo", "Archivo", "Archivo"),
        _mailbox(
            4,
            ACCOUNT_ICLOUD_ALT,
            f"imap://{ACCOUNT_ICLOUD_ALT}/INBOX",
            "INBOX",
            "INBOX",
            is_inbox=True,
        ),
        _mailbox(5, ACCOUNT_GMAIL, GMAIL_URL_INBOX, "INBOX", "INBOX", is_inbox=True),
        _mailbox(6, ACCOUNT_GMAIL, GMAIL_URL_ALL, "All Mail", "[Gmail]/All Mail", is_aggregate=True),
        _mailbox(7, ACCOUNT_GMAIL, GMAIL_URL_IMPORTANT, "Important", "[Gmail]/Important"),
        _mailbox(
            8,
            ACCOUNT_LOCAL,
            f"local://{ACCOUNT_LOCAL}/Recovered%20Messages",
            "Recovered Messages",
            "Recovered Messages",
            account_kind="local",
        ),
    )


class _FakeStore:
    def __init__(self, mailboxes: tuple[Mailbox, ...]) -> None:
        self._mailboxes = mailboxes
        self._by_rowid = {mailbox.rowid: mailbox for mailbox in mailboxes}

    @property
    def mailboxes(self) -> tuple[Mailbox, ...]:
        return self._mailboxes

    def mailbox(self, rowid: int) -> Mailbox:
        return self._by_rowid[rowid]

    def resolve_mailbox(self, account_uuid: str, ref: str) -> Mailbox | None:
        needle = ref.strip().casefold()
        for mailbox in self._mailboxes:
            if mailbox.account_uuid != account_uuid:
                continue
            if needle in (
                mailbox.name.casefold(),
                mailbox.path.casefold(),
                mailbox.url.casefold(),
            ):
                return mailbox
        return None


def _fake_labels(available: bool = True) -> "_FakeLabels":
    labels = [
        AccountLabel(ACCOUNT_ICLOUD, ICLOUD_LABEL, "fixture@icloud.com", "iCloud"),
        AccountLabel(ACCOUNT_ICLOUD_ALT, ICLOUD_ALT_LABEL, "fixture@icloud.com", "iCloud"),
        AccountLabel(ACCOUNT_GMAIL, GMAIL_LABEL, "fixture@gmail.com", "Gmail"),
        AccountLabel(ACCOUNT_LOCAL, LOCAL_LABEL, None, None, True),
        AccountLabel(ACCOUNT_MISSING, MISSING_LABEL, "old@example.com", "IMAP"),
    ]
    return _FakeLabels(labels, available=available)


class _FakeLabels:
    def __init__(self, labels: list[AccountLabel], *, available: bool = True) -> None:
        self._labels = labels
        self._available = available

    @property
    def available(self) -> bool:
        return self._available

    def all(self) -> list[AccountLabel]:
        return list(self._labels) if self._available else []

    def get(self, account_uuid: str) -> AccountLabel | None:
        if not self._available:
            return None
        for label in self._labels:
            if label.uuid == account_uuid:
                return label
        return None

    def label_for(self, account_uuid: str) -> str:
        label = self.get(account_uuid)
        return label.label if label is not None else account_uuid


def _config(*scopes: tuple[str, tuple[str, ...]]) -> Config:
    entries = tuple(ScopeEntry(key=key, mailbox_list=tuple(refs)) for key, refs in scopes)
    return Config(home=Path(tempfile.gettempdir()), scopes=entries)


class _ErrorAssertions(unittest.TestCase):
    def assertMailqueryError(self, code: str, func, *args, **kwargs) -> MailqueryError:
        with self.assertRaises(MailqueryError) as context:
            func(*args, **kwargs)
        error = context.exception
        self.assertEqual(error.code, code)
        self.assertEqual(error.exit_code, exit_code_for(code))
        return error


# --------------------------------------------------------------------------- #
# Application home and durations
# --------------------------------------------------------------------------- #


class AppHomeTests(unittest.TestCase):
    def test_app_home_is_dot_mailquery_under_home(self) -> None:
        self.assertEqual(app_home(), Path.home() / ".mailquery")

    def test_ensure_app_home_creates_runtime_directories_with_0700(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "nested" / "home"
            ensure_app_home(home)
            self.assertTrue(home.is_dir())
            for name in APP_HOME_SUBDIRS:
                directory = home / name
                self.assertTrue(directory.is_dir(), name)
                mode = stat.S_IMODE(os.stat(directory).st_mode)
                self.assertEqual(mode, 0o700, name)
            self.assertEqual(stat.S_IMODE(os.stat(home).st_mode), 0o700)


class ParseDurationTests(unittest.TestCase):
    def test_valid_durations(self) -> None:
        cases = {
            "1min": 60,
            "10min": 600,
            "2h": 7200,
            "1d": 86400,
            "1440min": 86400,
            " 10min ": 600,
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(parse_duration(value), expected)

    def test_invalid_durations(self) -> None:
        for value in (
            "10",
            "min",
            "10s",
            "0min",
            "0h",
            "2d",
            "25h",
            "-5min",
            "1.5h",
            "",
            "10MIN",
            600,
            None,
        ):
            with self.subTest(value=value):
                with self.assertRaises(MailqueryError) as context:
                    parse_duration(value)  # type: ignore[arg-type]
                self.assertEqual(context.exception.code, "E_CONFIG_INVALID")

    def test_range_error_mentions_valid_range(self) -> None:
        with self.assertRaises(MailqueryError) as context:
            parse_duration("2d")
        self.assertIn("1min..1d", context.exception.hint)


# --------------------------------------------------------------------------- #
# config.toml parsing and validation
# --------------------------------------------------------------------------- #


class LoadConfigTests(_ErrorAssertions):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name) / "home"

    def _write(self, content: str) -> Path:
        return write_config(self.home, content)

    def _load(self, content: str | None = None) -> Config:
        if content is not None:
            self._write(content)
        return load_config(self.home)

    def _load_error(self, content: str) -> MailqueryError:
        self._write(content)
        with self.assertRaises(MailqueryError) as context:
            load_config(self.home)
        error = context.exception
        self.assertEqual(error.code, "E_CONFIG_INVALID")
        self.assertEqual(error.exit_code, 2)
        return error

    # -- defaults ---------------------------------------------------------

    def test_absent_file_uses_defaults_and_no_scopes(self) -> None:
        self.home.mkdir(parents=True)
        config = load_config(self.home)
        self.assertEqual(config.home, self.home)
        self.assertEqual(config.logging, LoggingConfig())
        self.assertEqual(config.search, SearchConfig())
        self.assertEqual(config.new, NewConfig())
        self.assertEqual(config.scopes, ())
        self.assertFalse(config.has_scopes)

    def test_missing_home_directory_uses_defaults(self) -> None:
        config = load_config(self.home / "does-not-exist")
        self.assertEqual(config.home, self.home / "does-not-exist")
        self.assertFalse(config.has_scopes)

    def test_empty_scope_table_means_no_accounts(self) -> None:
        config = self._load("[scope]\n")
        self.assertEqual(config.scopes, ())
        self.assertFalse(config.has_scopes)

    # -- valid documents --------------------------------------------------

    def test_full_valid_config(self) -> None:
        content = f"""\
[logging]
level = "debug"
retention_days = 14

[search]
default_limit = 50
max_scan = 10000

[new]
default_limit = 200
lookback = "15min"

[scope."{ICLOUD_LABEL}"]
mailbox_list = ["Facturas", "Archivo"]

[scope."{ACCOUNT_GMAIL}"]
"""
        config = self._load(content)
        self.assertEqual(config.logging, LoggingConfig(level="debug", retention_days=14))
        self.assertEqual(config.search, SearchConfig(default_limit=50, max_scan=10000))
        self.assertEqual(config.new, NewConfig(default_limit=200, lookback="15min", lookback_seconds=900))
        self.assertEqual(
            config.scopes,
            (
                ScopeEntry(key=ICLOUD_LABEL, mailbox_list=("Facturas", "Archivo")),
                ScopeEntry(key=ACCOUNT_GMAIL, mailbox_list=()),
            ),
        )
        self.assertTrue(config.has_scopes)

    def test_partial_sections_keep_defaults(self) -> None:
        config = self._load("[search]\ndefault_limit = 50\n")
        self.assertEqual(config.search, SearchConfig(default_limit=50, max_scan=5000))
        self.assertEqual(config.logging, LoggingConfig())

    def test_scope_entry_without_mailbox_list_observes_inbox_only(self) -> None:
        config = self._load(f'[scope."{GMAIL_LABEL}"]\n')
        self.assertEqual(config.scopes, (ScopeEntry(key=GMAIL_LABEL, mailbox_list=()),))

    def test_toml_inline_table_scope_is_accepted(self) -> None:
        content = f'scope = {{ "{GMAIL_LABEL}" = {{ mailbox_list = ["[Gmail]/Important"] }} }}\n'
        config = self._load(content)
        self.assertEqual(
            config.scopes,
            (ScopeEntry(key=GMAIL_LABEL, mailbox_list=("[Gmail]/Important",)),),
        )

    def test_lookback_minimum_and_maximum(self) -> None:
        self.assertEqual(self._load('[new]\nlookback = "1min"\n').new.lookback_seconds, 60)
        self.assertEqual(self._load('[new]\nlookback = "1d"\n').new.lookback_seconds, 86400)

    # -- syntax errors ----------------------------------------------------

    def test_invalid_toml_syntax(self) -> None:
        error = self._load_error("this is = = not toml\n")
        self.assertIn("invalid TOML", error.message)
        self.assertIn("TOML", error.hint)

    # -- unknown keys/sections -------------------------------------------

    def test_unknown_top_level_scalar_key(self) -> None:
        error = self._load_error("verbose = true\n")
        self.assertIn("verbose", error.message)
        self.assertIn("logging", error.hint)

    def test_unknown_top_level_account_table(self) -> None:
        error = self._load_error('["someone@example.com"]\nmailbox_list = ["INBOX"]\n')
        self.assertIn("top-level section", error.message)
        self.assertIn("[scope.", error.hint)

    def test_unknown_keys_in_known_sections(self) -> None:
        cases = (
            ("[logging]\nverbose = true\n", "verbose"),
            ("[search]\nlimit = 3\n", "limit"),
            ("[new]\npeek = true\n", "peek"),
            ("[scope.\"x\"]\nextra = 1\n", "extra"),
        )
        for content, needle in cases:
            with self.subTest(content=content):
                error = self._load_error(content)
                self.assertIn(needle, error.message)

    def test_nested_unknown_logging_section(self) -> None:
        error = self._load_error("[logging.extra]\nfoo = 1\n")
        self.assertIn("extra", error.message)

    # -- wrong types / values --------------------------------------------

    def test_invalid_values_are_config_errors(self) -> None:
        cases = (
            ('[logging]\nlevel = "loud"\n', "[logging].level"),
            ("[logging]\nlevel = 1\n", "[logging].level"),
            ("[logging]\nretention_days = 0\n", "retention_days"),
            ("[logging]\nretention_days = 366\n", "retention_days"),
            ('[logging]\nretention_days = "7"\n', "must be an integer"),
            ("[logging]\nretention_days = true\n", "must be an integer"),
            ("[search]\ndefault_limit = 0\n", "default_limit"),
            ("[search]\ndefault_limit = 201\n", "default_limit"),
            ("[search]\nmax_scan = 99\n", "max_scan"),
            ("[search]\nmax_scan = 50001\n", "max_scan"),
            ("[new]\ndefault_limit = 0\n", "default_limit"),
            ("[new]\ndefault_limit = 501\n", "default_limit"),
            ('[new]\nlookback = "10s"\n', "duration"),
            ('[new]\nlookback = "2d"\n', "duration out of range"),
            ("[new]\nlookback = 10\n", "lookback"),
            ('[scope."x"]\nmailbox_list = "Facturas"\n', "mailbox_list"),
            ('[scope."x"]\nmailbox_list = [1]\n', "mailbox_list[0]"),
            ('[scope."x"]\nmailbox_list = [""]\n', "must not be empty"),
            ('[scope]\nx = "oops"\n', "[scope"),
            ('scope = "oops"\n', "scope"),
            ("logging = true\n", "logging"),
        )
        for content, needle in cases:
            with self.subTest(content=content):
                error = self._load_error(content)
                self.assertIn(needle, error.message)

    def test_range_hints_document_valid_ranges(self) -> None:
        cases = (
            ("[logging]\nretention_days = 400\n", "1..365"),
            ("[search]\ndefault_limit = 0\n", "1..200"),
            ("[search]\nmax_scan = 99\n", "100..50000"),
            ("[new]\ndefault_limit = 0\n", "1..500"),
            ('[new]\nlookback = "90s"\n', "1min..1d"),
        )
        for content, hint in cases:
            with self.subTest(content=content):
                error = self._load_error(content)
                self.assertIn(hint, error.hint)

    def test_enum_hint_lists_valid_levels(self) -> None:
        error = self._load_error('[logging]\nlevel = "warn"\n')
        for level in ("error", "warning", "info", "debug"):
            self.assertIn(level, error.hint)


# --------------------------------------------------------------------------- #
# Scope resolution with a fake store
# --------------------------------------------------------------------------- #


class ResolveScopeTests(_ErrorAssertions):
    def setUp(self) -> None:
        self.store = _FakeStore(_fake_mailboxes())
        self.labels = _fake_labels()

    def _resolve(self, config: Config):
        return resolve_scope(config, self.store, self.labels)

    def test_no_scopes_resolves_to_empty_list(self) -> None:
        self.assertEqual(self._resolve(Config(home=Path("/tmp"))), [])

    def test_label_resolution_includes_inbox_first_and_extra_folders(self) -> None:
        scopes = self._resolve(
            _config((ICLOUD_LABEL, ("Facturas", "Archivo")),)
        )
        self.assertEqual(len(scopes), 1)
        scope = scopes[0]
        self.assertEqual(scope.account_uuid, ACCOUNT_ICLOUD)
        self.assertEqual(scope.account_label, ICLOUD_LABEL)
        self.assertEqual(scope.account_email, "fixture@icloud.com")
        self.assertEqual([mailbox.name for mailbox in scope.mailboxes], ["INBOX", "Facturas", "Archivo"])
        self.assertTrue(scope.mailboxes[0].is_inbox)

    def test_inbox_is_first_even_when_declared_last(self) -> None:
        scopes = self._resolve(_config((ICLOUD_LABEL, ("Archivo", "Facturas")),))
        self.assertEqual(scopes[0].mailboxes[0].name, "INBOX")

    def test_explicit_inbox_reference_is_not_duplicated(self) -> None:
        scopes = self._resolve(_config((ICLOUD_LABEL, ("INBOX", "Facturas")),))
        self.assertEqual(len(scopes[0].mailboxes), 2)

    def test_label_resolution_is_case_insensitive(self) -> None:
        scopes = self._resolve(_config((ICLOUD_LABEL.upper(), ()),))
        self.assertEqual(scopes[0].account_uuid, ACCOUNT_ICLOUD)

    def test_unique_email_resolution(self) -> None:
        scopes = self._resolve(_config(("fixture@gmail.com", ()),))
        self.assertEqual(scopes[0].account_uuid, ACCOUNT_GMAIL)
        self.assertEqual([mailbox.name for mailbox in scopes[0].mailboxes], ["INBOX"])

    def test_duplicate_email_is_ambiguous(self) -> None:
        error = self._resolve_error(_config(("fixture@icloud.com", ()),))
        self.assertEqual(error.code, "E_ACCOUNT_AMBIGUOUS")
        self.assertIn("fixture@icloud.com", error.message)
        self.assertIn(ICLOUD_LABEL, error.hint)
        self.assertIn(ICLOUD_ALT_LABEL, error.hint)
        self.assertIn(ACCOUNT_ICLOUD, error.hint)
        self.assertIn(ACCOUNT_ICLOUD_ALT, error.hint)

    def test_full_uuid_resolution_is_case_insensitive(self) -> None:
        scopes = self._resolve(_config((ACCOUNT_GMAIL.lower(), ()),))
        self.assertEqual(scopes[0].account_uuid, ACCOUNT_GMAIL)

    def test_unique_uuid_prefix_resolution(self) -> None:
        for prefix in ("BBBBBBBB", "bbbbbbbb-0000-4000"):
            with self.subTest(prefix=prefix):
                scopes = self._resolve(_config((prefix, ()),))
                self.assertEqual(scopes[0].account_uuid, ACCOUNT_GMAIL)

    def test_ambiguous_uuid_prefix_lists_candidates(self) -> None:
        error = self._resolve_error(_config(("AAAAAAAA", ()),))
        self.assertEqual(error.code, "E_ACCOUNT_AMBIGUOUS")
        self.assertIn(ACCOUNT_ICLOUD, error.hint)
        self.assertIn(ACCOUNT_ICLOUD_ALT, error.hint)

    def test_short_uuid_prefix_is_unknown(self) -> None:
        error = self._resolve_error(_config(("BBBB", ()),))
        self.assertEqual(error.code, "E_CONFIG_ACCOUNT_UNKNOWN")
        self.assertIn("BBBB", error.message)

    def test_unknown_label_is_reported_with_known_accounts(self) -> None:
        error = self._resolve_error(_config(("Nope (nobody@example.com)", ()),))
        self.assertEqual(error.code, "E_CONFIG_ACCOUNT_UNKNOWN")
        self.assertIn("Nope (nobody@example.com)", error.message)
        self.assertIn(ICLOUD_LABEL, error.hint)
        self.assertIn(GMAIL_LABEL, error.hint)

    def test_account_known_only_in_accounts_db_is_unknown_in_store(self) -> None:
        error = self._resolve_error(_config((MISSING_LABEL, ()),))
        self.assertEqual(error.code, "E_CONFIG_ACCOUNT_UNKNOWN")

    def test_labels_unavailable_rejects_labels_and_emails(self) -> None:
        self.labels = _fake_labels(available=False)
        for key in (ICLOUD_LABEL, "fixture@gmail.com"):
            with self.subTest(key=key):
                error = self._resolve_error(_config((key, ()),))
                self.assertEqual(error.code, "E_ACCOUNT_LABELS_UNAVAILABLE")
                self.assertIn(key, error.message)
                self.assertIn("UUID", error.hint)

    def test_labels_unavailable_still_resolves_uuid_and_prefix(self) -> None:
        self.labels = _fake_labels(available=False)
        scopes = self._resolve(_config((ACCOUNT_ICLOUD, ()), ("BBBBBBBB", ()),))
        self.assertEqual([scope.account_uuid for scope in scopes], [ACCOUNT_ICLOUD, ACCOUNT_GMAIL])
        self.assertEqual(scopes[0].account_label, ACCOUNT_ICLOUD)
        self.assertIsNone(scopes[0].account_email)
        self.assertTrue(scopes[0].mailboxes[0].is_inbox)

    def test_labels_unavailable_unknown_uuid_is_an_unknown_account(self) -> None:
        self.labels = _fake_labels(available=False)
        for key in (ACCOUNT_MISSING, "DDDDDDDD"):
            with self.subTest(key=key):
                error = self._resolve_error(_config((key, ()),))
                self.assertEqual(error.code, "E_CONFIG_ACCOUNT_UNKNOWN")

    def test_mailbox_reference_by_name_path_and_url(self) -> None:
        cases = (
            ("facturas", ACCOUNT_ICLOUD, 2),
            ("[gmail]/all mail", ACCOUNT_GMAIL, 6),
            (GMAIL_URL_IMPORTANT, ACCOUNT_GMAIL, 7),
        )
        for ref, account_uuid, rowid in cases:
            with self.subTest(ref=ref):
                scopes = self._resolve(_config((account_uuid, (ref,)),))
                self.assertIn(rowid, [mailbox.rowid for mailbox in scopes[0].mailboxes])

    def test_unknown_mailbox_reports_valid_folders(self) -> None:
        error = self._resolve_error(_config((ICLOUD_LABEL, ("Missing",)),))
        self.assertEqual(error.code, "E_MAILBOX_NOT_FOUND")
        self.assertIn("Missing", error.message)
        self.assertIn(ICLOUD_LABEL, error.message)
        self.assertIn("INBOX", error.hint)
        self.assertIn("Facturas", error.hint)
        self.assertIn("Archivo", error.hint)

    def test_duplicate_blocks_for_same_account_are_merged(self) -> None:
        scopes = self._resolve(
            _config(
                (GMAIL_LABEL, ("[Gmail]/All Mail",)),
                ("fixture@gmail.com", ("[Gmail]/Important",)),
            )
        )
        self.assertEqual(len(scopes), 1)
        self.assertEqual(
            [mailbox.name for mailbox in scopes[0].mailboxes],
            ["INBOX", "All Mail", "Important"],
        )

    def test_multiple_accounts_keep_declaration_order(self) -> None:
        scopes = self._resolve(
            _config(
                (GMAIL_LABEL, ()),
                (ICLOUD_LABEL, ()),
                (LOCAL_LABEL, ()),
            )
        )
        self.assertEqual(
            [scope.account_uuid for scope in scopes],
            [ACCOUNT_GMAIL, ACCOUNT_ICLOUD, ACCOUNT_LOCAL],
        )

    def test_local_account_without_inbox_resolves_to_no_mailboxes(self) -> None:
        scopes = self._resolve(_config((LOCAL_LABEL, ()),))
        self.assertEqual(scopes[0].account_uuid, ACCOUNT_LOCAL)
        self.assertEqual(scopes[0].mailboxes, ())
        self.assertIsNone(scopes[0].account_email)

    def _resolve_error(self, config: Config) -> MailqueryError:
        with self.assertRaises(MailqueryError) as context:
            resolve_scope(config, self.store, self.labels)
        return context.exception


# --------------------------------------------------------------------------- #
# Scope resolution against the synthetic Mail store (integration-ish)
# --------------------------------------------------------------------------- #


class FixtureScopeResolutionTests(unittest.TestCase):
    """Uses ``build_store()``; skipped while store/accounts are still stubs."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.fx = build_store()
        write_config(cls.fx.home, DEFAULT_CONFIG)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.fx.cleanup()

    def _open_store(self):
        from mailquery.store import open_store

        try:
            store = open_store(self.fx.mail_root, tmp_root=self.fx.root / "tmp")
        except NotImplementedError as exc:
            self.skipTest(f"store.py dependency not implemented yet: {exc}")
        self.addCleanup(store.close)
        return store

    def _open_labels(self, db_path: Path | None = None):
        from mailquery.accounts import AccountLabels

        try:
            return AccountLabels(
                self.fx.accounts_db if db_path is None else db_path,
                tmp_dir=self.fx.root / "tmp",
            )
        except NotImplementedError as exc:
            self.skipTest(f"accounts.py dependency not implemented yet: {exc}")

    def test_fixture_accounts_resolve_by_label(self) -> None:
        store = self._open_store()
        labels = self._open_labels()
        self.assertTrue(labels.available)
        scopes = resolve_scope(load_config(self.fx.home), store, labels)
        by_uuid = {scope.account_uuid: scope for scope in scopes}
        self.assertEqual(set(by_uuid), {ACCOUNT_ICLOUD, ACCOUNT_GMAIL, ACCOUNT_LOCAL})
        icloud = by_uuid[ACCOUNT_ICLOUD]
        self.assertEqual(icloud.account_label, ICLOUD_LABEL)
        self.assertEqual(icloud.account_email, "fixture@icloud.com")
        self.assertEqual(
            [mailbox.name for mailbox in icloud.mailboxes],
            ["INBOX", "Facturas", "Archivo"],
        )
        self.assertTrue(icloud.mailboxes[0].is_inbox)
        self.assertEqual([mailbox.name for mailbox in by_uuid[ACCOUNT_GMAIL].mailboxes], ["INBOX"])
        self.assertEqual(by_uuid[ACCOUNT_LOCAL].account_label, LOCAL_LABEL)

    def test_fixture_resolves_uuid_without_account_labels(self) -> None:
        store = self._open_store()
        labels = self._open_labels(db_path=self.fx.root / "missing-accounts.sqlite")
        self.assertFalse(labels.available)
        config = Config(
            home=self.fx.home,
            scopes=(ScopeEntry(key=ACCOUNT_ICLOUD), ScopeEntry(key=ACCOUNT_GMAIL)),
        )
        scopes = resolve_scope(config, store, labels)
        self.assertEqual([scope.account_uuid for scope in scopes], [ACCOUNT_ICLOUD, ACCOUNT_GMAIL])
        self.assertEqual(scopes[0].account_label, ACCOUNT_ICLOUD)
        self.assertIsNone(scopes[0].account_email)
        self.assertTrue(scopes[0].mailboxes[0].is_inbox)


if __name__ == "__main__":
    unittest.main()

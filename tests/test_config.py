"""Tests for ``mailquery.config``.

Covers the strict ``config.toml`` schema, duration parsing, the application
home layout and the account/mailbox scope resolution rules (PRD 15). Scope
resolution is tested against a small fake backend (the ``MailBackend`` methods
that ``resolve_scope`` uses) and against the Apple Mail backend over the
synthetic fixture store.
"""

from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path

from mailquery.accounts import AccountLabel
from mailquery.backends.apple_mail import AppleMailBackend
from mailquery.backends.registry import INTERNAL_CAPABILITIES, package_version
from mailquery.config import (
    APP_HOME_SUBDIRS,
    AttachmentsConfig,
    Config,
    LoggingConfig,
    NewConfig,
    ScopeEntry,
    SearchConfig,
    app_home,
    declared_drivers,
    driver_in_scope,
    ensure_app_home,
    load_config,
    parse_duration,
    require_driver_in_scope,
    resolve_scope,
)
from mailquery.errors import MailqueryError, exit_code_for
from mailquery.store import Mailbox

from tests.fixtures.make_fixtures import (
    ACCOUNT_GMAIL,
    ACCOUNT_ICLOUD,
    ACCOUNT_LOCAL,
    DEFAULT_CONFIG,
    PREFIXED_CONFIG,
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


class _FakeBackend:
    """Fake ``MailBackend``: the protocol v1 methods that ``resolve_scope`` uses."""

    driver = "apple_mail"
    plugin_api = 1
    capabilities = dict(INTERNAL_CAPABILITIES["apple_mail"])

    def __init__(
        self,
        mailboxes: tuple[Mailbox, ...],
        labels: "_FakeLabels",
        *,
        driver: str | None = None,
    ) -> None:
        self._mailboxes = mailboxes
        self._labels = labels
        if driver is not None:
            self.driver = driver

    @property
    def labels_available(self) -> bool:
        return self._labels.available

    def accounts(self) -> list[dict]:
        rows: list[dict] = []
        seen: set[str] = set()
        for mailbox in self._mailboxes:
            uuid = mailbox.account_uuid
            if uuid in seen:
                continue
            seen.add(uuid)
            entry = self._labels.get(uuid)
            rows.append(
                {
                    "uuid": uuid,
                    "label": entry.label if entry is not None else uuid,
                    "email": entry.email if entry is not None else None,
                    "local": mailbox.account_kind == "local",
                }
            )
        return rows

    def mailboxes(self) -> list[dict]:
        return [_row(mailbox) for mailbox in self._mailboxes]

    def excluded_stores(self) -> list[dict]:
        return []

    def resolve_mailbox(self, account_uuid: str, ref: str) -> dict | None:
        needle = ref.strip().casefold()
        for mailbox in self._mailboxes:
            if mailbox.account_uuid != account_uuid:
                continue
            if needle in (
                mailbox.name.casefold(),
                mailbox.path.casefold(),
                mailbox.url.casefold(),
            ):
                return _row(mailbox)
        return None

    @staticmethod
    def parse_native_id(native_id: str) -> str:
        return native_id


class _StubRegistry:
    """Minimal ``BackendRegistry`` seam: the driver check ``load_config`` needs."""

    def __init__(self, installed: tuple[str, ...] = ("apple_mail", "outlook")) -> None:
        self._installed = frozenset(installed)

    def installed(self) -> list[str]:
        return sorted(self._installed)

    def is_installed(self, driver: str) -> bool:
        return driver in self._installed


PLUGIN_DRIVER = "graph"
PLUGIN_CAPABILITIES = {
    "network": True,
    "readonly": "promise",
    "body_local": True,
    "attachments": "remote",
    "native_order": "text",
}


def _plugin_mailbox(
    rowid: int,
    account_uuid: str,
    name: str,
    path: str,
    *,
    is_inbox: bool = False,
) -> dict:
    return {
        "id": rowid,
        "account_uuid": account_uuid,
        "name": name,
        "path": path,
        "url": f"plugin://{account_uuid}/{path}",
        "is_inbox": is_inbox,
        "is_aggregate": False,
        "total": 0,
        "unread": 0,
    }


class _PluginBackend:
    """Fake external driver with opaque ``label``/``uuid`` account identifiers (RF-36)."""

    driver = PLUGIN_DRIVER
    plugin_api = 1
    capabilities = dict(PLUGIN_CAPABILITIES)
    labels_available = True

    def __init__(
        self,
        accounts: list[dict],
        mailboxes: tuple[dict, ...] = (),
    ) -> None:
        self._accounts = [dict(account) for account in accounts]
        self._mailboxes = [dict(mailbox) for mailbox in mailboxes]
        self.calls: list[str] = []

    def accounts(self) -> list[dict]:
        self.calls.append("accounts")
        return [dict(account) for account in self._accounts]

    def mailboxes(self) -> list[dict]:
        self.calls.append("mailboxes")
        return [dict(mailbox) for mailbox in self._mailboxes]

    def excluded_stores(self) -> list[dict]:
        return []

    def resolve_mailbox(self, account_uuid: str, ref: str) -> dict | None:
        needle = ref.strip().casefold()
        for mailbox in self._mailboxes:
            if mailbox["account_uuid"] != account_uuid:
                continue
            if needle in (mailbox["name"].casefold(), mailbox["path"].casefold()):
                return dict(mailbox)
        return None

    @staticmethod
    def parse_native_id(native_id: str) -> str:
        return native_id


class _ExcludedBackend:
    """Fake Outlook driver whose declared label is an excluded store (PRD 15.3)."""

    driver = "outlook"
    plugin_api = 1
    capabilities = dict(INTERNAL_CAPABILITIES["outlook"])
    labels_available = True

    EXCLUDED = {
        "label": "Exchange shared (Soporte)",
        "path": "\\\\nas01\\backup\\soporte.pst",
        "reason": "shared_mailbox",
    }

    def accounts(self) -> list[dict]:
        return [
            {
                "uuid": None,
                "label": self.EXCLUDED["label"],
                "email": None,
                "local": False,
                "excluded": dict(self.EXCLUDED),
            }
        ]

    def mailboxes(self) -> list[dict]:
        return []

    def excluded_stores(self) -> list[dict]:
        return [dict(self.EXCLUDED)]

    def resolve_mailbox(self, account_uuid: str, ref: str) -> dict | None:
        return None

    @staticmethod
    def parse_native_id(native_id: str) -> str:
        return native_id


def _plugin_accounts() -> list[dict]:
    return [
        {
            "uuid": "acct-000001",
            "label": "work",
            "email": "work@example.com",
            "local": False,
        },
        {
            "uuid": "acct-000002",
            "label": "Home",
            "email": None,
            "local": False,
        },
    ]


def _plugin_backend() -> _PluginBackend:
    return _PluginBackend(
        _plugin_accounts(),
        (
            _plugin_mailbox(101, "acct-000001", "INBOX", "INBOX", is_inbox=True),
            _plugin_mailbox(102, "acct-000001", "Facturas", "INBOX/Facturas"),
            _plugin_mailbox(103, "acct-000002", "INBOX", "INBOX", is_inbox=True),
        ),
    )



def _row(mailbox: Mailbox) -> dict:
    return {
        "id": mailbox.rowid,
        "account_uuid": mailbox.account_uuid,
        "name": mailbox.name,
        "path": mailbox.path,
        "url": mailbox.url,
        "is_inbox": mailbox.is_inbox,
        "is_aggregate": mailbox.is_aggregate,
        "total": mailbox.message_count,
        "unread": mailbox.unread_count,
    }


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
                if os.name == "posix":
                    mode = stat.S_IMODE(os.stat(directory).st_mode)
                    self.assertEqual(mode, 0o700, name)
            if os.name == "posix":
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
        self.assertEqual(config.attachments, AttachmentsConfig())
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
max_size_mb = 14

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
        self.assertEqual(config.logging, LoggingConfig(level="debug", max_size_mb=14))
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
            ("[logging]\nmax_size_mb = 0\n", "max_size_mb"),
            ("[logging]\nmax_size_mb = 1025\n", "max_size_mb"),
            ('[logging]\nmax_size_mb = "10"\n', "must be an integer"),
            ("[logging]\nmax_size_mb = true\n", "must be an integer"),
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
            ("[logging]\nmax_size_mb = 2000\n", "1..1024"),
            ("[search]\ndefault_limit = 0\n", "1..200"),
            ("[search]\nmax_scan = 99\n", "100..50000"),
            ("[new]\ndefault_limit = 0\n", "1..500"),
            ('[new]\nlookback = "90s"\n', "1min..1d"),
        )
        for content, hint in cases:
            with self.subTest(content=content):
                error = self._load_error(content)
                self.assertIn(hint, error.hint)

    def test_ut_cfg_01_01_max_size_mb_accepts_its_limits(self) -> None:
        """UT-CFG-01.01: 1 and 1024 are valid max_size_mb values."""
        self.assertEqual(self._load("[logging]\nmax_size_mb = 1\n").logging.max_size_mb, 1)
        self.assertEqual(self._load("[logging]\nmax_size_mb = 1024\n").logging.max_size_mb, 1024)

    def test_ut_cfg_02_01_retention_days_is_an_unknown_key_with_its_hint(self) -> None:
        """UT-CFG-02.01: [logging].retention_days => E_CONFIG_INVALID with the replacement hint."""
        error = self._load_error("[logging]\nretention_days = 7\n")
        self.assertEqual(error.code, "E_CONFIG_INVALID")
        self.assertIn("retention_days", error.message)
        self.assertEqual(error.hint, "retention_days was replaced by max_size_mb")

    def test_enum_hint_lists_valid_levels(self) -> None:
        error = self._load_error('[logging]\nlevel = "warn"\n')
        for level in ("error", "warning", "info", "debug"):
            self.assertIn(level, error.hint)


# --------------------------------------------------------------------------- #
# Scope resolution with a fake store
# --------------------------------------------------------------------------- #


class ResolveScopeTests(_ErrorAssertions):
    def setUp(self) -> None:
        self.backend = _FakeBackend(_fake_mailboxes(), _fake_labels())

    def _resolve(self, config: Config):
        return resolve_scope(config, self.backend)

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
        self.assertEqual([mailbox["name"] for mailbox in scope.mailboxes], ["INBOX", "Facturas", "Archivo"])
        self.assertTrue(scope.mailboxes[0]["is_inbox"])

    def test_inbox_is_first_even_when_declared_last(self) -> None:
        scopes = self._resolve(_config((ICLOUD_LABEL, ("Archivo", "Facturas")),))
        self.assertEqual(scopes[0].mailboxes[0]["name"], "INBOX")

    def test_explicit_inbox_reference_is_not_duplicated(self) -> None:
        scopes = self._resolve(_config((ICLOUD_LABEL, ("INBOX", "Facturas")),))
        self.assertEqual(len(scopes[0].mailboxes), 2)

    def test_label_resolution_is_case_insensitive(self) -> None:
        scopes = self._resolve(_config((ICLOUD_LABEL.upper(), ()),))
        self.assertEqual(scopes[0].account_uuid, ACCOUNT_ICLOUD)

    def test_unique_email_resolution(self) -> None:
        scopes = self._resolve(_config(("fixture@gmail.com", ()),))
        self.assertEqual(scopes[0].account_uuid, ACCOUNT_GMAIL)
        self.assertEqual([mailbox["name"] for mailbox in scopes[0].mailboxes], ["INBOX"])

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
        self.backend = _FakeBackend(_fake_mailboxes(), _fake_labels(available=False))
        for key in (ICLOUD_LABEL, "fixture@gmail.com"):
            with self.subTest(key=key):
                error = self._resolve_error(_config((key, ()),))
                self.assertEqual(error.code, "E_ACCOUNT_LABELS_UNAVAILABLE")
                self.assertIn(key, error.message)
                self.assertIn("UUID", error.hint)

    def test_labels_unavailable_still_resolves_uuid_and_prefix(self) -> None:
        self.backend = _FakeBackend(_fake_mailboxes(), _fake_labels(available=False))
        scopes = self._resolve(_config((ACCOUNT_ICLOUD, ()), ("BBBBBBBB", ()),))
        self.assertEqual([scope.account_uuid for scope in scopes], [ACCOUNT_ICLOUD, ACCOUNT_GMAIL])
        self.assertEqual(scopes[0].account_label, ACCOUNT_ICLOUD)
        self.assertIsNone(scopes[0].account_email)
        self.assertTrue(scopes[0].mailboxes[0]["is_inbox"])

    def test_labels_unavailable_unknown_uuid_is_an_unknown_account(self) -> None:
        self.backend = _FakeBackend(_fake_mailboxes(), _fake_labels(available=False))
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
                self.assertIn(rowid, [mailbox["id"] for mailbox in scopes[0].mailboxes])

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
            [mailbox["name"] for mailbox in scopes[0].mailboxes],
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
            resolve_scope(config, self.backend)
        return context.exception


# --------------------------------------------------------------------------- #
# Scope resolution against the synthetic Mail store (integration-ish)
# --------------------------------------------------------------------------- #


class FixtureScopeResolutionTests(unittest.TestCase):
    """Uses ``build_store()``."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.fx = build_store()
        write_config(cls.fx.home, DEFAULT_CONFIG)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.fx.cleanup()

    def _open_store(self):
        from mailquery.store import open_store

        store = open_store(self.fx.mail_root, tmp_root=self.fx.root / "tmp")
        self.addCleanup(store.close)
        return store

    def _open_labels(self, db_path: Path | None = None):
        from mailquery.accounts import AccountLabels

        return AccountLabels(
            self.fx.accounts_db if db_path is None else db_path,
            tmp_dir=self.fx.root / "tmp",
        )

    def test_fixture_accounts_resolve_by_label(self) -> None:
        store = self._open_store()
        labels = self._open_labels()
        self.assertTrue(labels.available)
        scopes = resolve_scope(load_config(self.fx.home), AppleMailBackend(store, labels))
        by_uuid = {scope.account_uuid: scope for scope in scopes}
        self.assertEqual(set(by_uuid), {ACCOUNT_ICLOUD, ACCOUNT_GMAIL, ACCOUNT_LOCAL})
        icloud = by_uuid[ACCOUNT_ICLOUD]
        self.assertEqual(icloud.account_label, ICLOUD_LABEL)
        self.assertEqual(icloud.account_email, "fixture@icloud.com")
        self.assertEqual(
            [mailbox["name"] for mailbox in icloud.mailboxes],
            ["INBOX", "Facturas", "Archivo"],
        )
        self.assertTrue(icloud.mailboxes[0]["is_inbox"])
        self.assertEqual([mailbox["name"] for mailbox in by_uuid[ACCOUNT_GMAIL].mailboxes], ["INBOX"])
        self.assertEqual(by_uuid[ACCOUNT_LOCAL].account_label, LOCAL_LABEL)

    def test_fixture_resolves_uuid_without_account_labels(self) -> None:
        store = self._open_store()
        labels = self._open_labels(db_path=self.fx.root / "missing-accounts.sqlite")
        self.assertFalse(labels.available)
        config = Config(
            home=self.fx.home,
            scopes=(ScopeEntry(key=ACCOUNT_ICLOUD), ScopeEntry(key=ACCOUNT_GMAIL)),
        )
        scopes = resolve_scope(config, AppleMailBackend(store, labels))
        self.assertEqual([scope.account_uuid for scope in scopes], [ACCOUNT_ICLOUD, ACCOUNT_GMAIL])
        self.assertEqual(scopes[0].account_label, ACCOUNT_ICLOUD)
        self.assertIsNone(scopes[0].account_email)
        self.assertTrue(scopes[0].mailboxes[0]["is_inbox"])

    def _backend_with_extra_labels(self) -> AppleMailBackend:
        # The accounts database knows accounts that have no folders in the store.
        store = self._open_store()
        return AppleMailBackend(store, _fake_labels())

    def test_label_of_an_account_without_folders_is_unknown_and_lists_every_label(self) -> None:
        backend = self._backend_with_extra_labels()
        with self.assertRaises(MailqueryError) as context:
            resolve_scope(_config((MISSING_LABEL, ()),), backend)
        error = context.exception
        self.assertEqual(error.code, "E_CONFIG_ACCOUNT_UNKNOWN")
        self.assertIn(MISSING_LABEL, error.hint)
        self.assertIn(ICLOUD_ALT_LABEL, error.hint)
        self.assertIn(GMAIL_LABEL, error.hint)

    def test_shared_email_is_ambiguous_across_every_label_entry(self) -> None:
        # ICLOUD_ALT has no folders in the store, yet it still makes the email ambiguous.
        backend = self._backend_with_extra_labels()
        with self.assertRaises(MailqueryError) as context:
            resolve_scope(_config(("fixture@icloud.com", ()),), backend)
        error = context.exception
        self.assertEqual(error.code, "E_ACCOUNT_AMBIGUOUS")
        self.assertIn(ICLOUD_LABEL, error.hint)
        self.assertIn(ICLOUD_ALT_LABEL, error.hint)
        self.assertIn(ACCOUNT_ICLOUD_ALT, error.hint)

    def test_uuid_of_an_account_without_folders_is_unknown(self) -> None:
        backend = self._backend_with_extra_labels()
        with self.assertRaises(MailqueryError) as context:
            resolve_scope(_config((ACCOUNT_MISSING, ()),), backend)
        self.assertEqual(context.exception.code, "E_CONFIG_ACCOUNT_UNKNOWN")


# --------------------------------------------------------------------------- #
# M02 — UT-DRV-01: [scope."<driver>:<cuenta>"] schema (AC-03, RF-36)
# --------------------------------------------------------------------------- #


class _DriverConfigCase(_ErrorAssertions):
    """Temporary home plus the load/resolve helpers shared by the UT-DRV cases."""

    INSTALLED = ("apple_mail", "outlook")

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name) / "home"
        self.backend = _FakeBackend(_fake_mailboxes(), _fake_labels())

    def _load(self, content: str, *, installed: tuple[str, ...] | None = None):
        write_config(self.home, content)
        registry = _StubRegistry(self.INSTALLED if installed is None else installed)
        return load_config(self.home, registry=registry)

    def _load_error(
        self, content: str, code: str = "E_DRIVER_UNKNOWN", *, installed: tuple[str, ...] | None = None
    ) -> MailqueryError:
        write_config(self.home, content)
        registry = _StubRegistry(self.INSTALLED if installed is None else installed)
        with self.assertRaises(MailqueryError) as context:
            load_config(self.home, registry=registry)
        error = context.exception
        self.assertEqual(error.code, code)
        self.assertEqual(error.exit_code, exit_code_for(code))
        return error

    def _resolve(self, content: str, backend, *, installed: tuple[str, ...] | None = None):
        return resolve_scope(self._load(content, installed=installed), backend)


class DriverScopeSchemaTests(_DriverConfigCase):
    """UT-DRV-01 — ``[scope."<driver>:<cuenta>"]`` schema and native fallback (AC-03)."""

    def test_ut_drv_01_01_prefixed_block_resolves_the_account_inside_its_driver(self) -> None:
        """UT-DRV-01.01: `apple_mail:<label>` resolves the account inside that driver."""
        config = self._load(
            f'[scope."apple_mail:{ICLOUD_LABEL}"]\nmailbox_list = ["Facturas"]\n'
        )
        self.assertEqual(len(config.scopes), 1)
        entry = config.scopes[0]
        self.assertEqual(entry.key, f"apple_mail:{ICLOUD_LABEL}")
        self.assertEqual(entry.driver, "apple_mail")
        self.assertEqual(entry.account_ref, ICLOUD_LABEL)
        scopes = resolve_scope(config, self.backend)
        self.assertEqual(len(scopes), 1)
        self.assertEqual(scopes[0].driver, "apple_mail")
        self.assertEqual(scopes[0].account_uuid, ACCOUNT_ICLOUD)
        self.assertEqual([mailbox["name"] for mailbox in scopes[0].mailboxes], ["INBOX", "Facturas"])

    def test_ut_drv_01_02_unprefixed_block_uses_the_platform_native_driver(self) -> None:
        """UT-DRV-01.02: an unprefixed key keeps using the native driver of the platform."""
        config = self._load(f'[scope."{ICLOUD_LABEL}"]\n')
        entry = config.scopes[0]
        self.assertIsNone(entry.driver)
        self.assertIsNone(entry.account)
        self.assertEqual(entry.account_ref, ICLOUD_LABEL)
        self.assertEqual(declared_drivers(config, native="apple_mail"), ("apple_mail",))
        scopes = resolve_scope(config, self.backend)
        self.assertEqual(scopes[0].driver, "apple_mail")
        self.assertEqual(scopes[0].account_uuid, ACCOUNT_ICLOUD)

    def test_ut_drv_01_03_account_label_with_colon_needs_the_explicit_prefix(self) -> None:
        """UT-DRV-01.03: a label containing ':' works with its prefix; without it is E_DRIVER_UNKNOWN."""
        label = "PST: Archivo"
        backend = _FakeBackend(
            (
                _mailbox(
                    20, ACCOUNT_ICLOUD, f"imap://{ACCOUNT_ICLOUD}/INBOX", "INBOX", "INBOX", is_inbox=True
                ),
                _mailbox(
                    21,
                    ACCOUNT_ICLOUD,
                    f"imap://{ACCOUNT_ICLOUD}/PST%3A%20Archivo",
                    label,
                    label,
                ),
            ),
            _FakeLabels([AccountLabel(ACCOUNT_ICLOUD, label, "pst@example.com", "IMAP")]),
        )
        scopes = self._resolve(f'[scope."apple_mail:{label}"]\n', backend)
        self.assertEqual(scopes[0].account_uuid, ACCOUNT_ICLOUD)
        self.assertEqual(scopes[0].account_label, label)
        # Documented limitation: the first ':' is the driver separator.
        error = self._load_error(f'[scope."{label}"]\n')
        self.assertIn("PST", error.message)

    def test_ut_drv_01_04_invalid_driver_prefix_is_driver_unknown(self) -> None:
        """UT-DRV-01.04: uppercase, hyphen, empty or >64 driver ⇒ E_DRIVER_UNKNOWN (exit 2)."""
        for driver in ("Apple_Mail", "apple-mail", "", "a" * 65):
            with self.subTest(driver=driver):
                error = self._load_error(f'[scope."{driver}:account"]\n')
                self.assertEqual(error.exit_code, 2)

    def test_ut_drv_01_05_well_formed_but_not_installed_driver_is_driver_unknown(self) -> None:
        """UT-DRV-01.05: a well-formed driver that is not installed is not ignored."""
        error = self._load_error('[scope."graph:trabajo@example.com"]\n')
        self.assertIn("graph", error.message)
        self.assertIn("pipx inject", error.hint)
        # Every data command loads config.toml before doing any work, so the
        # error above is what makes all of them fail with E_DRIVER_UNKNOWN.
        self.assertEqual(exit_code_for(error.code), 2)

    def test_ut_drv_01_06_blocks_for_the_same_driver_and_account_are_merged(self) -> None:
        """UT-DRV-01.06: two blocks of the same (driver, account) merge mailbox_list."""
        config = self._load(
            f'[scope."apple_mail:{GMAIL_LABEL}"]\nmailbox_list = ["[Gmail]/All Mail"]\n\n'
            f'[scope."apple_mail:fixture@gmail.com"]\nmailbox_list = ["[Gmail]/Important"]\n'
        )
        scopes = resolve_scope(config, self.backend)
        self.assertEqual(len(scopes), 1)
        self.assertEqual(scopes[0].driver, "apple_mail")
        self.assertEqual(scopes[0].account_uuid, ACCOUNT_GMAIL)
        self.assertEqual(
            [mailbox["name"] for mailbox in scopes[0].mailboxes],
            ["INBOX", "All Mail", "Important"],
        )


# --------------------------------------------------------------------------- #
# M02 — UT-DRV-02: account resolution inside each driver (AC-03, RF-36)
# --------------------------------------------------------------------------- #


class DriverAccountResolutionTests(_DriverConfigCase):
    """UT-DRV-02 — account resolution per driver (AC-03)."""

    def test_ut_drv_02_01_internal_backend_forms_resolve_within_the_driver(self) -> None:
        """UT-DRV-02.01: label, unique email, full UUID and UUID prefix ≥ 8 inside apple_mail."""
        cases = (
            (ICLOUD_LABEL, ACCOUNT_ICLOUD),
            ("fixture@gmail.com", ACCOUNT_GMAIL),
            (ACCOUNT_GMAIL.lower(), ACCOUNT_GMAIL),
            ("BBBBBBBB", ACCOUNT_GMAIL),
        )
        for reference, account_uuid in cases:
            with self.subTest(reference=reference):
                scopes = self._resolve(f'[scope."apple_mail:{reference}"]\n', self.backend)
                self.assertEqual(scopes[0].driver, "apple_mail")
                self.assertEqual(scopes[0].account_uuid, account_uuid)

    def test_ut_drv_02_02_plugin_labels_and_uuids_are_opaque(self) -> None:
        """UT-DRV-02.02: a plugin resolves its short label and opaque UUID exactly, never by prefix."""
        backend = _plugin_backend()
        scopes = self._resolve(
            f'[scope."{PLUGIN_DRIVER}:work"]\nmailbox_list = ["Facturas"]\n',
            backend,
            installed=("graph",),
        )
        self.assertEqual(scopes[0].driver, PLUGIN_DRIVER)
        self.assertEqual(scopes[0].account_uuid, "acct-000001")
        self.assertEqual(
            [mailbox["name"] for mailbox in scopes[0].mailboxes], ["INBOX", "Facturas"]
        )
        scopes = self._resolve(
            f'[scope."{PLUGIN_DRIVER}:acct-000002"]\n', backend, installed=("graph",)
        )
        self.assertEqual(scopes[0].account_uuid, "acct-000002")
        # The internal "unique UUID prefix >= 8" form does not apply to plugins.
        with self.assertRaises(MailqueryError) as context:
            self._resolve(
                f'[scope."{PLUGIN_DRIVER}:acct-000"]\n', backend, installed=("graph",)
            )
        self.assertEqual(context.exception.code, "E_CONFIG_ACCOUNT_UNKNOWN")

    def test_ut_drv_02_03_unknown_and_ambiguous_accounts_keep_their_errors(self) -> None:
        """UT-DRV-02.03: unknown ⇒ E_CONFIG_ACCOUNT_UNKNOWN; ambiguous ⇒ E_ACCOUNT_AMBIGUOUS."""
        backend = _plugin_backend()
        with self.assertRaises(MailqueryError) as context:
            self._resolve(f'[scope."{PLUGIN_DRIVER}:nope"]\n', backend, installed=("graph",))
        self.assertEqual(context.exception.code, "E_CONFIG_ACCOUNT_UNKNOWN")
        duplicated = _PluginBackend(
            [
                {"uuid": "acct-a", "label": "Dup", "email": None, "local": False},
                {"uuid": "acct-b", "label": "Dup", "email": None, "local": False},
            ],
            (_plugin_mailbox(104, "acct-a", "INBOX", "INBOX", is_inbox=True),),
        )
        with self.assertRaises(MailqueryError) as context:
            self._resolve(f'[scope."{PLUGIN_DRIVER}:Dup"]\n', duplicated, installed=("graph",))
        error = context.exception
        self.assertEqual(error.code, "E_ACCOUNT_AMBIGUOUS")
        self.assertIn("acct-a", error.hint)
        self.assertIn("acct-b", error.hint)

    def test_ut_drv_02_04_excluded_store_is_reported_without_aborting(self) -> None:
        """UT-DRV-02.04: Outlook excluded store ⇒ W_STORE_EXCLUDED entry, no abort (PRD 15.3)."""
        backend = _ExcludedBackend()
        config = self._load(
            f'[scope."outlook:{_ExcludedBackend.EXCLUDED["label"]}"]\n', installed=("outlook",)
        )
        excluded: list[dict] = []
        scopes = resolve_scope(config, backend, excluded=excluded)
        self.assertEqual(scopes, [])
        self.assertEqual(excluded, [dict(_ExcludedBackend.EXCLUDED)])
        self.assertEqual(excluded[0]["label"], _ExcludedBackend.EXCLUDED["label"])
        self.assertEqual(excluded[0]["path"], _ExcludedBackend.EXCLUDED["path"])


# --------------------------------------------------------------------------- #
# M02 — UT-DRV-03: installed-but-not-declared drivers (AC-03, RF-36)
# --------------------------------------------------------------------------- #


class DriverInScopeTests(_DriverConfigCase):
    """UT-DRV-03 — a driver installed but not declared stays out of scope (AC-03)."""

    def _native_config(self):
        return self._load(f'[scope."{ICLOUD_LABEL}"]\n')

    def test_ut_drv_03_01_data_scopes_do_not_query_an_undeclared_driver(self) -> None:
        """UT-DRV-03.01: only declared drivers are queried; an undeclared plugin is never called."""
        plugin = _plugin_backend()
        config = self._native_config()
        scopes = resolve_scope(config, self.backend, drivers={PLUGIN_DRIVER: plugin})
        self.assertEqual([scope.driver for scope in scopes], ["apple_mail"])
        self.assertEqual(plugin.calls, [])
        self.assertEqual(declared_drivers(config, native="apple_mail"), ("apple_mail",))

    def test_ut_drv_03_02_helper_reports_account_not_in_scope_with_its_hint(self) -> None:
        """UT-DRV-03.02: the scope helper raises E_ACCOUNT_NOT_IN_SCOPE (exit 2) with the hint."""
        config = self._native_config()
        self.assertFalse(driver_in_scope(config, PLUGIN_DRIVER, native="apple_mail"))
        with self.assertRaises(MailqueryError) as context:
            require_driver_in_scope(config, PLUGIN_DRIVER, native="apple_mail")
        error = context.exception
        self.assertEqual(error.code, "E_ACCOUNT_NOT_IN_SCOPE")
        self.assertEqual(error.exit_code, 2)
        self.assertIn("graph", error.message)
        self.assertIn("config.toml", error.hint)
        declared = self._load(
            f'[scope."{PLUGIN_DRIVER}:work"]\n', installed=("graph",)
        )
        self.assertTrue(driver_in_scope(declared, PLUGIN_DRIVER, native="apple_mail"))
        require_driver_in_scope(declared, PLUGIN_DRIVER, native="apple_mail")

    def test_ut_drv_03_03_uninstalled_prefix_is_driver_unknown(self) -> None:
        """UT-DRV-03.03: a prefix of a driver that is not installed ⇒ E_DRIVER_UNKNOWN (exit 2)."""
        error = self._load_error(
            f'[scope."{PLUGIN_DRIVER}:work"]\n', installed=("apple_mail",)
        )
        self.assertEqual(error.code, "E_DRIVER_UNKNOWN")
        self.assertEqual(error.exit_code, 2)


# --------------------------------------------------------------------------- #
# M02 — UT-DRV-04: [attachments] table (AC-14, RF-42/49, §13)
# --------------------------------------------------------------------------- #


class AttachmentsConfigTests(_DriverConfigCase):
    """UT-DRV-04 — ``[attachments]`` defaults, ranges and closed schema (AC-14)."""

    def _attachments(self, content: str) -> AttachmentsConfig:
        return self._load(content).attachments

    def test_ut_drv_04_01_absent_table_uses_the_documented_defaults(self) -> None:
        """UT-DRV-04.01: no [attachments] table ⇒ enabled=true, 100/200/50."""
        attachments = self._attachments("# no attachments table\n")
        self.assertEqual(
            attachments,
            AttachmentsConfig(
                enabled=True,
                max_file_size_mb=100,
                max_total_size_mb=200,
                max_count=50,
            ),
        )

    def test_ut_drv_04_02_valid_custom_values_are_accepted_and_exposed(self) -> None:
        """UT-DRV-04.02: valid custom values are exposed as written."""
        attachments = self._attachments(
            "[attachments]\nenabled = false\nmax_file_size_mb = 5\n"
            "max_total_size_mb = 10\nmax_count = 3\n"
        )
        self.assertFalse(attachments.enabled)
        self.assertEqual(attachments.max_file_size_mb, 5)
        self.assertEqual(attachments.max_total_size_mb, 10)
        self.assertEqual(attachments.max_count, 3)

    def test_ut_drv_04_03_out_of_range_or_wrong_type_is_config_invalid(self) -> None:
        """UT-DRV-04.03: wrong types and out-of-range values ⇒ E_CONFIG_INVALID (exit 2)."""
        cases = (
            "[attachments]\nenabled = 1\n",
            '[attachments]\nenabled = "true"\n',
            "[attachments]\nmax_file_size_mb = 0\n",
            "[attachments]\nmax_file_size_mb = 501\n",
            '[attachments]\nmax_file_size_mb = "100"\n',
            "[attachments]\nmax_file_size_mb = true\n",
            "[attachments]\nmax_total_size_mb = 0\n",
            "[attachments]\nmax_total_size_mb = 1025\n",
            "[attachments]\nmax_count = 0\n",
            "[attachments]\nmax_count = 501\n",
        )
        for content in cases:
            with self.subTest(content=content):
                error = self._load_error(content, "E_CONFIG_INVALID")
                self.assertEqual(error.exit_code, 2)

    def test_ut_drv_04_04_total_below_file_size_is_config_invalid_with_hint(self) -> None:
        """UT-DRV-04.04: max_total_size_mb < max_file_size_mb ⇒ E_CONFIG_INVALID with both keys."""
        error = self._load_error(
            "[attachments]\nmax_file_size_mb = 200\nmax_total_size_mb = 100\n",
            "E_CONFIG_INVALID",
        )
        self.assertIn("max_total_size_mb", error.message)
        self.assertIn("max_file_size_mb", error.message)
        self.assertIn("max_total_size_mb", error.hint)
        self.assertIn("max_file_size_mb", error.hint)

    def test_ut_drv_04_05_unknown_key_or_section_is_config_invalid(self) -> None:
        """UT-DRV-04.05: unknown key in [attachments] or an unknown section ⇒ E_CONFIG_INVALID."""
        for content in (
            "[attachments]\nenabled_extra = true\n",
            "[attachments.sub]\nenabled = true\n",
            "[attachment]\nenabled = true\n",
        ):
            with self.subTest(content=content):
                self._load_error(content, "E_CONFIG_INVALID")


# --------------------------------------------------------------------------- #
# M02 — UT-DRV-01/02 against the synthetic store (prefixed fixture config)
# --------------------------------------------------------------------------- #


class PrefixedFixtureScopeTests(unittest.TestCase):
    """The prefixed fixture config resolves the native driver against the real store."""

    def test_ut_drv_01_02_prefixed_fixture_config_resolves_the_native_driver(self) -> None:
        fx = build_store()
        self.addCleanup(fx.cleanup)
        write_config(fx.home, PREFIXED_CONFIG)
        config = load_config(fx.home, registry=_StubRegistry())
        backend = AppleMailBackend(
            mail_root=fx.mail_root,
            accounts_db=fx.accounts_db,
            tmp_root=fx.home / "tmp",
        )
        self.addCleanup(backend.close)
        scopes = resolve_scope(config, backend)
        self.assertEqual([scope.driver for scope in scopes], ["apple_mail", "apple_mail"])
        self.assertEqual(
            [scope.account_uuid for scope in scopes], [ACCOUNT_ICLOUD, ACCOUNT_GMAIL]
        )
        self.assertEqual(
            [mailbox["name"] for mailbox in scopes[0].mailboxes], ["INBOX", "Facturas"]
        )


if __name__ == "__main__":
    unittest.main()

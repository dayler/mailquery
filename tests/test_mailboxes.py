"""``mailboxes`` grouped by account, its ``--fields`` and the deferred counters.

Covers the TEST-CATALOG groups UT-MBX-01 (default shape grouped by account),
UT-MBX-02 (references copied from the output still resolve), UT-MBX-03
(``--fields``), UT-MBX-04 (no message is counted unless requested) and UT-MBX-05
(help), plus DOC-13 (READMEs, skill and example configuration).

The stores are the synthetic Apple Mail fixture, the in-memory Outlook double
and the plugin double. Every run uses a temporary home: the real
``~/Library/Mail`` and ``~/.mailquery`` are never read.
"""

from __future__ import annotations

import contextlib
import io
import json
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest import mock

from mailquery import cli as cli_mod
from mailquery import search
from mailquery import store as store_module
from mailquery.accounts import AccountLabels
from mailquery.backends import get_backend
from mailquery.backends.apple_mail import AppleMailBackend
from mailquery.config import load_config
from mailquery.state import StateStore
from mailquery.store import open_store
from tests.fakes import outlook as fk
from tests.fakes.plugin import (
    ACCOUNT_LABEL as PLUGIN_ACCOUNT_LABEL,
    ACCOUNT_UUID as PLUGIN_ACCOUNT_UUID,
    DEFAULT_MAILBOXES as PLUGIN_MAILBOXES,
    DRIVER as PLUGIN_DRIVER,
    FakeEntryPoint,
    FakePluginBackend,
    internal_entry_points,
)
from tests.fixtures.make_fixtures import (
    ACCOUNT_GMAIL,
    ACCOUNT_ICLOUD,
    ACCOUNT_LOCAL,
    DEFAULT_CONFIG,
    ICLOUD_LABEL,
    build_store,
    write_config,
)

_ROOT = Path(__file__).resolve().parents[1]
_FIELDS_TEXT = "valid fields: name, path, url, total, unread, included"


def _all_installed(driver: str) -> bool:
    return True


def _plugin_scope(*labels: str) -> str:
    return "".join(f'[scope."{PLUGIN_DRIVER}:{label}"]\n' for label in labels)


class _CliCase(unittest.TestCase):
    """In-process ``cli.main`` runs; subclasses set ``self.home``."""

    def setUp(self) -> None:
        self.addCleanup(cli_mod._close_logging_handlers)

    def run_cli(
        self,
        *argv: str,
        backend: object | None = None,
        home: Path | None = None,
        mail_root: Path | None = None,
        accounts_db: Path | None = None,
    ):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli_mod.main(
                list(argv),
                home=self.home if home is None else home,
                mail_root=mail_root,
                accounts_db=accounts_db,
                backend=backend,
            )
        raw = out.getvalue()
        return code, (json.loads(raw) if raw.strip() else None), err.getvalue()

    def run_ok(self, *argv: str, **kwargs) -> dict:
        code, payload, stderr = self.run_cli(*argv, **kwargs)
        self.assertEqual(code, 0, f"{argv}: {payload} {stderr}")
        assert payload is not None
        self.assertIs(payload.get("ok"), True)
        return payload

    def run_error(self, *argv: str, exit_code: int, code: str, **kwargs) -> dict:
        actual, payload, stderr = self.run_cli(*argv, **kwargs)
        self.assertEqual(actual, exit_code, f"{argv}: {payload} {stderr}")
        assert payload is not None
        self.assertIs(payload.get("ok"), False)
        self.assertEqual(payload["error"]["code"], code)
        return payload

    def plugin_registry(self, plugin: FakePluginBackend):
        return cli_mod.BackendRegistry(
            platform=sys.platform,
            entry_points=[
                *internal_entry_points(),
                FakeEntryPoint(PLUGIN_DRIVER, plugin=plugin),
            ],
        )

    def outlook_backend(self, fake: fk.FakeOutlook):
        backend = get_backend(
            platform="win32",
            outlook_app=fake,
            registry=fake.registry,
            security_center=fake.security_center,
            pywin32=None,
            tmp_root=self.home / "tmp",
        )
        self.addCleanup(backend.close)
        return backend

    def run_outlook(
        self, fake: fk.FakeOutlook, *argv: str, home: Path | None = None
    ) -> dict:
        return self.run_ok(*argv, backend=self.outlook_backend(fake), home=home)

    def run_plugin(
        self, plugin: FakePluginBackend, *argv: str, home: Path | None = None
    ) -> dict:
        registry = self.plugin_registry(plugin)
        with mock.patch.object(cli_mod, "BackendRegistry", lambda *a, **k: registry):
            return self.run_ok(*argv, home=home)


class _AppleCase(_CliCase):
    """One synthetic Apple Mail store per test."""

    def setUp(self) -> None:
        super().setUp()
        self.fx = build_store()
        self.addCleanup(self.fx.cleanup)
        self.home = self.fx.home
        self.root = self.fx.root
        write_config(self.fx.home, DEFAULT_CONFIG)

    def run_cli(self, *argv: str, **kwargs):
        kwargs.setdefault("mail_root", self.fx.mail_root)
        kwargs.setdefault("accounts_db", self.fx.accounts_db)
        return super().run_cli(*argv, **kwargs)

    def backend(self) -> AppleMailBackend:
        store = open_store(mail_root=self.fx.mail_root, tmp_root=self.fx.home / "tmp")
        self.addCleanup(store.close)
        labels = AccountLabels(self.fx.accounts_db, tmp_dir=self.fx.home / "tmp")
        return AppleMailBackend(store, labels)

    def config(self):
        return load_config(self.fx.home)

    def account(self, payload: dict, uuid: str) -> dict:
        return next(account for account in payload["accounts"] if account["uuid"] == uuid)


# --------------------------------------------------------------------------- #
# UT-MBX-01 — default shape grouped by account
# --------------------------------------------------------------------------- #


class DefaultShapeTests(_AppleCase):
    """UT-MBX-01: every account lists its folders and each folder has path/included."""

    def test_ut_mbx_01_01_top_level_keys_in_the_three_sources(self) -> None:
        """UT-MBX-01.01: the six top-level keys, with Apple Mail, Outlook and a plugin."""
        expected = [
            "ok",
            "command",
            "generated_at",
            "accounts",
            "excluded_stores",
            "warnings",
        ]
        self.assertEqual(list(self.run_ok("mailboxes")), expected)
        outlook_home = self.root / "outlook-home"
        outlook_home.mkdir()
        write_config(outlook_home, '[scope."ana.perez@example.com"]\n')
        self.assertEqual(
            list(
                self.run_outlook(
                    fk.FakeOutlook.default(), "mailboxes", home=outlook_home
                )
            ),
            expected,
        )
        write_config(self.home, _plugin_scope(PLUGIN_ACCOUNT_LABEL))
        self.assertEqual(
            list(self.run_plugin(FakePluginBackend(), "mailboxes")), expected
        )

    def test_ut_mbx_01_02_accounts_and_folders_keep_the_previous_order(self) -> None:
        """UT-MBX-01.02: account and folder order preserve the flat catalog values."""
        default = self.run_ok("mailboxes")
        for account in default["accounts"]:
            self.assertEqual(
                list(account), ["uuid", "label", "email", "declared", "mailboxes"]
            )
            for folder in account["mailboxes"]:
                self.assertEqual(list(folder), ["path", "included"])
                self.assertIsInstance(folder["included"], bool)
        flat = [
            folder["path"]
            for account in default["accounts"]
            for folder in account["mailboxes"]
        ]
        catalog = [row["path"] for row in self.backend().mailboxes()]
        self.assertEqual(flat, catalog)
        self.assertEqual(
            [account["uuid"] for account in default["accounts"]],
            [ACCOUNT_ICLOUD, ACCOUNT_GMAIL, ACCOUNT_LOCAL],
        )

    def test_ut_mbx_01_03_no_account_object_and_no_flat_list(self) -> None:
        """UT-MBX-01.03: no folder carries ``account`` and there is no top-level list."""
        payload = self.run_ok("mailboxes")
        self.assertNotIn("mailboxes", payload)
        for account in payload["accounts"]:
            for folder in account["mailboxes"]:
                self.assertNotIn("account", folder)

    def test_ut_mbx_01_04_empty_account_and_driver_order(self) -> None:
        """UT-MBX-01.04: an account without folders has ``mailboxes: []``."""
        empty_label = "Graph empty"
        write_config(
            self.home,
            _plugin_scope(PLUGIN_ACCOUNT_LABEL, empty_label)
            + f'[scope."{ICLOUD_LABEL}"]\n',
        )
        plugin = FakePluginBackend(
            accounts=[
                {
                    "uuid": PLUGIN_ACCOUNT_UUID,
                    "label": PLUGIN_ACCOUNT_LABEL,
                    "email": None,
                    "local": False,
                },
                {
                    "uuid": "graph-empty",
                    "label": empty_label,
                    "email": None,
                    "local": False,
                },
            ],
            mailboxes=[
                *PLUGIN_MAILBOXES,
                {
                    "id": "graph-orphan",
                    "account_uuid": "",
                    "name": "Orphan",
                    "path": "Orphan",
                    "url": "graph:///Orphan",
                    "is_inbox": False,
                    "is_aggregate": False,
                    "total": 0,
                    "unread": 0,
                },
            ],
        )
        config = load_config(self.home, registry=self.plugin_registry(plugin))
        payload = search.run_mailboxes(
            self.backend(),
            config,
            drivers={PLUGIN_DRIVER: plugin},
            native="apple_mail",
        )
        self.assertEqual(
            [account["uuid"] for account in payload["accounts"]],
            [
                PLUGIN_ACCOUNT_UUID,
                "graph-empty",
                "",
                ACCOUNT_ICLOUD,
                ACCOUNT_GMAIL,
                ACCOUNT_LOCAL,
            ],
        )
        empty = self.account(payload, "graph-empty")
        self.assertIs(empty["declared"], True)
        self.assertEqual(empty["mailboxes"], [])
        orphan = self.account(payload, "")
        self.assertIs(orphan["declared"], False)
        self.assertEqual(
            orphan["mailboxes"], [{"path": "Orphan", "included": False}]
        )
        self.assertEqual(payload["excluded_stores"], [])
        self.assertEqual(self.account(payload, ACCOUNT_ICLOUD)["mailboxes"][0]["path"], "INBOX")


# --------------------------------------------------------------------------- #
# UT-MBX-02 — references copied from the output
# --------------------------------------------------------------------------- #


class ReferenceTests(_AppleCase):
    """UT-MBX-02: a path, name or URL copied from ``mailboxes`` resolves."""

    def folder(self, account_uuid: str, path: str) -> dict:
        account = self.account(self.run_ok("mailboxes", "--fields", "name,url"), account_uuid)
        return next(entry for entry in account["mailboxes"] if entry["path"] == path)

    def test_ut_mbx_02_01_copied_path_resolves(self) -> None:
        """UT-MBX-02.01: a copied ``path`` resolves in ``mailbox_list`` and ``--include-mailbox``."""
        path = self.folder(ACCOUNT_ICLOUD, "Archivo")["path"]
        included = self.run_ok("search", "--include-mailbox", path)
        self.assertGreaterEqual(included["count"], 1)
        write_config(self.home, f'[scope."{ICLOUD_LABEL}"]\nmailbox_list = ["{path}"]\n')
        configured = self.run_ok("search")
        self.assertGreaterEqual(configured["count"], 1)

    def test_ut_mbx_02_02_copied_name_and_url_resolve(self) -> None:
        """UT-MBX-02.02: the ``name`` and the ``url`` of ``--fields name,url`` resolve."""
        folder = self.folder(ACCOUNT_ICLOUD, "Archivo")
        for ref in (folder["name"], folder["url"]):
            with self.subTest(ref=ref):
                payload = self.run_ok("search", "--include-mailbox", ref)
                self.assertGreaterEqual(payload["count"], 1)
                write_config(
                    self.home,
                    f'[scope."{ICLOUD_LABEL}"]\nmailbox_list = ["{ref}"]\n',
                )
                self.assertGreaterEqual(self.run_ok("search")["count"], 1)
                write_config(self.home, DEFAULT_CONFIG)


# --------------------------------------------------------------------------- #
# UT-MBX-03 — --fields
# --------------------------------------------------------------------------- #


class FieldsTests(_AppleCase):
    """UT-MBX-03: ``--fields`` adds folder fields in the canonical order."""

    def test_ut_mbx_03_01_fields_are_added_in_canonical_order(self) -> None:
        """UT-MBX-03.01: comma-separated and repeated values add the same fields."""
        full = self.run_ok("mailboxes", "--fields", "name,url,total,unread")
        repeated = self.run_ok(
            "mailboxes", "--fields", "total", "--fields", "name,url,unread"
        )
        self.assertEqual(full["accounts"], repeated["accounts"])
        default = self.run_ok("mailboxes")
        expected = {
            (row["account_uuid"], row["path"]): (row["name"], row["url"], row["total"], row["unread"])
            for row in self.backend().mailboxes()
        }
        for account, plain in zip(full["accounts"], default["accounts"]):
            for folder, base in zip(account["mailboxes"], plain["mailboxes"]):
                self.assertEqual(
                    list(folder),
                    ["name", "path", "url", "total", "unread", "included"],
                )
                self.assertEqual(folder["path"], base["path"])
                self.assertEqual(folder["included"], base["included"])
                self.assertEqual(
                    (folder["name"], folder["url"], folder["total"], folder["unread"]),
                    expected[(account["uuid"], folder["path"])],
                )

    def test_ut_mbx_03_02_path_and_included_are_the_default(self) -> None:
        """UT-MBX-03.02: ``--fields path,included`` returns the default output."""
        default = self.run_ok("mailboxes")
        selected = self.run_ok("mailboxes", "--fields", "path,included")
        self.assertEqual(
            {key: value for key, value in selected.items() if key != "generated_at"},
            {key: value for key, value in default.items() if key != "generated_at"},
        )

    def test_ut_mbx_03_03_unknown_fields_are_usage_before_the_home(self) -> None:
        """UT-MBX-03.03: ``all``, an unknown name and an empty name are ``E_USAGE``."""
        missing_home = self.root / "missing-home"
        self.assertFalse(missing_home.exists())
        for value in ("all", "carpeta", ""):
            with self.subTest(value=value):
                with mock.patch.object(cli_mod, "_execute") as execute:
                    code, payload, stderr = self.run_cli(
                        "mailboxes", "--fields", value, home=missing_home
                    )
                execute.assert_not_called()
                self.assertEqual(code, 2, payload)
                assert payload is not None
                self.assertEqual(payload["error"]["code"], "E_USAGE")
                self.assertEqual(
                    payload["error"]["message"], f"unknown field '{value}' in --fields"
                )
                self.assertEqual(payload["error"]["hint"], _FIELDS_TEXT)
                self.assertIn("E_USAGE", stderr)
                self.assertFalse(missing_home.exists())


# --------------------------------------------------------------------------- #
# UT-MBX-04 — no counters unless requested
# --------------------------------------------------------------------------- #


class NoCountingTests(_AppleCase):
    """UT-MBX-04: without ``total``/``unread`` no message is counted."""

    def counter_spy(self):
        return mock.patch.object(
            store_module, "_mailbox_counters", wraps=store_module._mailbox_counters
        )

    def test_ut_mbx_04_01_apple_counts_only_when_requested(self) -> None:
        """UT-MBX-04.01: the Apple counter query runs only with ``total`` or ``unread``."""
        backend = self.backend()
        config = self.config()
        with self.counter_spy() as spy:
            search.run_mailboxes(backend, config)
            self.assertEqual(spy.call_count, 0)
            search.run_mailboxes(backend, config, fields=("unread",))
            self.assertEqual(spy.call_count, 1)

    def test_ut_mbx_04_02_outlook_reads_no_folder_tables_without_counters(self) -> None:
        """UT-MBX-04.02: Outlook folder tables are read only when counters are requested."""
        write_config(self.home, '[scope."ana.perez@example.com"]\n')
        plain_fake = fk.FakeOutlook.default()
        self.run_outlook(plain_fake, "mailboxes")
        self.assertEqual(plain_fake.call_log.count(kind="Folder", member="GetTable"), 0)
        full_fake = fk.FakeOutlook.default()
        self.run_outlook(full_fake, "mailboxes", "--fields", "total")
        self.assertGreater(
            full_fake.call_log.count(kind="Folder", member="GetTable"), 0
        )

    def test_ut_mbx_04_03_plugin_counters_are_omitted_by_default(self) -> None:
        """UT-MBX-04.03: a plugin that delivers counters hides them without ``--fields``."""
        write_config(self.home, _plugin_scope(PLUGIN_ACCOUNT_LABEL))
        payload = self.run_plugin(FakePluginBackend(), "mailboxes")
        (account,) = payload["accounts"]
        self.assertEqual([list(folder) for folder in account["mailboxes"]], [["path", "included"]])

    def test_ut_mbx_04_04_search_new_and_show_do_not_count(self) -> None:
        """UT-MBX-04.04: ``search``, ``new`` and ``show`` no longer read the counters."""
        backend = self.backend()
        config = self.config()
        with self.counter_spy() as spy:
            found = search.run_search(backend, config, search.Filters())
            self.assertGreater(found["count"], 0)
            fresh = search.run_new(
                backend, config, StateStore(self.home, _all_installed), peek=True
            )
            self.assertTrue(fresh["messages"])
            shown = search.run_show(backend, config, 2714)
            self.assertEqual(shown["message"]["uid"], "apple_mail:2714")
            self.assertEqual(spy.call_count, 0)

    def test_ut_mbx_04_05_second_counter_request_reuses_the_count(self) -> None:
        """UT-MBX-04.05: two counter requests in one process count once."""
        backend = self.backend()
        config = self.config()
        with self.counter_spy() as spy:
            first = search.run_mailboxes(backend, config, fields=("total",))
            second = search.run_mailboxes(backend, config, fields=("unread",))
            self.assertEqual(spy.call_count, 1)
        first_inbox = self.account(first, ACCOUNT_ICLOUD)["mailboxes"][0]
        second_inbox = self.account(second, ACCOUNT_ICLOUD)["mailboxes"][0]
        self.assertEqual(first_inbox["total"], 8)
        self.assertEqual(second_inbox["unread"], 3)

    def test_ut_mbx_04_06_sqlite_error_keeps_the_error_contract(self) -> None:
        """UT-MBX-04.06: a deferred counter error keeps the code and exit of the old path."""
        failure = sqlite3.OperationalError("database disk image is malformed")
        with mock.patch.object(store_module, "_mailbox_counters", side_effect=failure):
            plain = self.run_ok("mailboxes")
            self.assertEqual(len(self.account(plain, ACCOUNT_ICLOUD)["mailboxes"]), 3)
            payload = self.run_error(
                "mailboxes", "--fields", "total", exit_code=1, code="E_INTERNAL"
            )
            self.assertIn("OperationalError", payload["error"]["message"])

    def test_ut_mbx_04_07_plugin_without_counters_does_not_fail(self) -> None:
        """UT-MBX-04.07: a plugin row without counters is served with ``null`` counters."""
        write_config(self.home, _plugin_scope(PLUGIN_ACCOUNT_LABEL))
        plugin = FakePluginBackend(
            mailboxes=[
                {
                    "id": "graph-inbox",
                    "account_uuid": PLUGIN_ACCOUNT_UUID,
                    "name": "INBOX",
                    "path": "INBOX",
                    "url": "graph://graph-account/INBOX",
                    "is_inbox": True,
                    "is_aggregate": False,
                }
            ]
        )
        payload = self.run_plugin(plugin, "mailboxes", "--fields", "total,unread")
        (account,) = payload["accounts"]
        self.assertEqual(
            list(account["mailboxes"][0]),
            ["path", "total", "unread", "included"],
        )
        self.assertIsNone(account["mailboxes"][0]["total"])
        self.assertIsNone(account["mailboxes"][0]["unread"])
        counted = FakePluginBackend()
        self.assertEqual(
            self.run_plugin(counted, "mailboxes", "--fields", "total")["accounts"][0][
                "mailboxes"
            ][0]["total"],
            PLUGIN_MAILBOXES[0]["total"],
        )


# --------------------------------------------------------------------------- #
# UT-MBX-05 — help
# --------------------------------------------------------------------------- #


class HelpTests(unittest.TestCase):
    """UT-MBX-05: the ``--fields`` help and the general help line."""

    def help_text(self, argv) -> str:
        out, err = io.StringIO(), io.StringIO()
        with (
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
            self.assertRaises(SystemExit),
        ):
            cli_mod.build_parser().parse_args(list(argv))
        return out.getvalue()

    def test_ut_mbx_05_01_mailboxes_help_describes_fields(self) -> None:
        """UT-MBX-05.01: ``mailboxes --help`` lists the valid fields."""
        text = self.help_text(["mailboxes", "--help"])
        self.assertIn("--fields", text)
        self.assertIn("name, path, url, total, unread, included", text)
        self.assertIn("only with --fields total or unread", text)

    def test_ut_mbx_05_02_general_help_line(self) -> None:
        """UT-MBX-05.02: the general help lists the new ``mailboxes`` line."""
        text = self.help_text(["--help"])
        self.assertIn("list accounts and their folders (counters with --fields)", text)


# --------------------------------------------------------------------------- #
# DOC-13 — documentation of the new output
# --------------------------------------------------------------------------- #


class DocumentationTests(unittest.TestCase):
    """DOC-13: READMEs, skill and example configuration describe the grouped output."""

    def test_doc_13_01_readmes_show_the_grouped_output(self) -> None:
        """DOC-13.01: both READMEs show the grouped shape and the counters with --fields."""
        for name in ("README.md", "README.es.md"):
            with self.subTest(readme=name):
                text = (_ROOT / name).read_text(encoding="utf-8")
                section = text.split("### `mailquery mailboxes`", 1)[1].split("\n### ", 1)[0]
                self.assertIn('"mailboxes": [', section)
                self.assertIn('"declared": true', section)
                self.assertNotIn('"account":', section)
                self.assertIn("--fields total,unread", section)

    def test_doc_13_02_skill_uses_mailboxes_with_and_without_fields(self) -> None:
        """DOC-13.02: the skill lists folders without ``--fields`` and counters with it."""
        text = (_ROOT / "skills" / "mailquery" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn(
            "| `mailquery mailboxes [--fields LIST]` | accounts and their folders", text
        )
        self.assertIn("--fields total,unread", text)
        self.assertIn("without `--fields`", text)

    def test_doc_13_03_example_config_explains_the_folder_references(self) -> None:
        """DOC-13.03: ``config.example.toml`` explains the path, name and URL references."""
        text = (_ROOT / "docs" / "config.example.toml").read_text(encoding="utf-8")
        self.assertIn("path shown by `mailquery mailboxes`", text)
        self.assertIn("`mailquery mailboxes --fields name,url`", text)


if __name__ == "__main__":  # pragma: no cover - manual runs
    unittest.main()

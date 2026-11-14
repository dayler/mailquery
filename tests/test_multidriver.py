"""Unit tests for the multi-driver engine (UT-MD-01..07; PRD §6.5, §11.2).

Two layers are covered:

* the command functions (``search.run_search``/``run_new``/``run_show``/
  ``run_mailboxes``) with the synthetic Apple Mail fixture plus the API 1 plugin
  double as a second driver: merge and total order, global cursor, limits,
  mailboxes composition and ``show`` dispatch;
* the CLI with an injected :class:`BackendRegistry` (the registry seam):
  declared-driver loading, fail-fast, closing and the ``event=start`` log.

Every path is temporary (fixture store, fake home): the tests never read the
real mail client or ``~/.mailquery``.
"""

from __future__ import annotations

import io
import json
import logging
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import timedelta
from unittest import mock

from mailquery import cli as cli_mod
from mailquery import search
from mailquery.accounts import AccountLabels
from mailquery.backends.apple_mail import AppleMailBackend
from mailquery.backends.registry import BackendRegistry
from mailquery.config import load_config
from mailquery.errors import MailqueryError
from mailquery.plugins import PluginError, Reason
from mailquery.state import StateStore
from mailquery.store import open_store
from tests.fakes.plugin import (
    ACCOUNT_LABEL as PLUGIN_ACCOUNT_LABEL,
    ACCOUNT_UUID as PLUGIN_ACCOUNT_UUID,
    CAPABILITIES as PLUGIN_CAPABILITIES,
    DEFAULT_ATTACHMENTS as PLUGIN_ATTACHMENTS,
    DRIVER as PLUGIN_DRIVER,
    FakeEntryPoint,
    FakePluginBackend,
    internal_entry_points,
    plugin_class,
    plugin_factory,
)
from tests.fixtures.make_fixtures import (
    ACCOUNT_ICLOUD,
    DEFAULT_CONFIG,
    GMAIL_LABEL,
    ICLOUD_LABEL,
    build_store,
    prefixed_uid,
    write_config,
    write_state,
)

PLUGIN_ACCOUNT_BLOCK = f'[scope."{PLUGIN_DRIVER}:{PLUGIN_ACCOUNT_LABEL}"]'

#: Default fixture config plus one plugin account: apple_mail + graph.
MULTI_CONFIG = f"{DEFAULT_CONFIG}\n{PLUGIN_ACCOUNT_BLOCK}\n"

#: Only the plugin declares an account: the native driver stays out of scope.
PLUGIN_ONLY_CONFIG = f"{PLUGIN_ACCOUNT_BLOCK}\n"

#: Only the native driver (unprefixed block).
ICLOUD_ONLY_CONFIG = f'[scope."{ICLOUD_LABEL}"]\n'

#: Two Apple Mail accounts with the shared duplicate plus the plugin.
DEDUPE_MULTI_CONFIG = (
    f'[scope."{ICLOUD_LABEL}"]\nmailbox_list = ["Facturas", "Archivo"]\n\n'
    f'[scope."{GMAIL_LABEL}"]\nmailbox_list = ["[Gmail]/All Mail"]\n\n'
    f"{PLUGIN_ACCOUNT_BLOCK}\n"
)

#: Default ``search`` order of the Apple Mail fixture (search_default.json).
APPLE_SEARCH_ORDER = [
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


def _close_log_handlers() -> None:
    """Release the log file ``cli.main`` leaves open (Windows cannot delete it)."""
    logger = logging.getLogger("mailquery")
    for handler in list(logger.handlers):
        if isinstance(handler, logging.FileHandler):
            logger.removeHandler(handler)
            handler.close()


def capturing_factory(**instance_kwargs):
    """``plugin_factory`` that records every instance the core builds (close test)."""
    base = plugin_factory(**instance_kwargs)
    created: list[FakePluginBackend] = []

    def wrapper(context=None):
        instance = base(context)
        created.append(instance)
        return instance

    wrapper.driver = base.driver
    wrapper.plugin_api = base.plugin_api
    wrapper.capabilities = base.capabilities
    wrapper.native_order = base.native_order
    return wrapper, created


def registry_for(*entries: FakeEntryPoint, platform: str | None = None) -> BackendRegistry:
    """Registry with the built-in entry points plus the given plugin entry points."""
    return BackendRegistry(
        platform=sys.platform if platform is None else platform,
        entry_points=[*internal_entry_points(), *entries],
    )


class MultiDriverCase(unittest.TestCase):
    """One temporary Apple Mail fixture plus the plugin double per test."""

    def setUp(self) -> None:
        self.fx = build_store()
        self.addCleanup(self.fx.cleanup)
        self.addCleanup(_close_log_handlers)
        self.registry = registry_for(
            FakeEntryPoint(PLUGIN_DRIVER, plugin=FakePluginBackend)
        )
        self.store = open_store(mail_root=self.fx.mail_root, tmp_root=self.fx.home / "tmp")
        self.addCleanup(self.store.close)
        self.labels = AccountLabels(self.fx.accounts_db, tmp_dir=self.fx.home / "tmp")
        self.backend = AppleMailBackend(self.store, self.labels)
        self.use_config(MULTI_CONFIG)

    # -- fixture helpers ---------------------------------------------------- #

    def use_config(self, content: str):
        write_config(self.fx.home, content)
        self.config = load_config(self.fx.home, registry=self.registry)
        return self.config

    def timestamp(self, *, minutes_ago: float = 0, seconds_ago: float = 0) -> int:
        moment = self.fx.now - timedelta(minutes=minutes_ago, seconds=seconds_ago)
        return int(moment.timestamp())

    def plugin_row(
        self,
        native_id: str,
        *,
        minutes_ago: float,
        native_order_key: str | None = None,
        **extra,
    ):
        date = self.timestamp(minutes_ago=minutes_ago)
        row = {
            "uid": native_id,
            "native_order_key": native_id if native_order_key is None else native_order_key,
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
        row.update(extra)
        return row

    def fresh_state(self) -> StateStore:
        path = self.fx.home / "state.json"
        path.unlink(missing_ok=True)
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        return StateStore(self.fx.home, self.registry.is_installed)

    def read_state(self) -> dict:
        return json.loads((self.fx.home / "state.json").read_text(encoding="utf-8"))

    def seed_cursor(
        self,
        *,
        minutes_ago: float = 60,
        last_uid: str = prefixed_uid(83143),
        emitted_uids: tuple[str, ...] = (),
        lookback_seconds: int = 600,
    ) -> StateStore:
        write_state(
            self.fx.home,
            {
                "schema": 2,
                "updated_at": "",
                "last_run": None,
                "cursor": {
                    "last_date_received": self.timestamp(minutes_ago=minutes_ago),
                    "last_uid": last_uid,
                    "lookback_seconds": lookback_seconds,
                },
                "emitted_uids": list(emitted_uids),
            },
        )
        return StateStore(self.fx.home, self.registry.is_installed)

    # -- command helpers ---------------------------------------------------- #

    def run_search(self, plugin: FakePluginBackend, **filters):
        return search.run_search(
            self.backend,
            self.config,
            search.Filters(**filters),
            drivers={PLUGIN_DRIVER: plugin},
            fields=("all",),
        )

    def run_new(
        self,
        plugin: FakePluginBackend | None = None,
        *,
        state_store: StateStore | None = None,
        peek: bool = False,
        limit: int | None = None,
        drivers: dict | None = None,
    ):
        store = state_store if state_store is not None else self.fresh_state()
        mapping = (
            {PLUGIN_DRIVER: plugin}
            if drivers is None and plugin is not None
            else (drivers or {})
        )
        return search.run_new(
            self.backend,
            self.config,
            store,
            drivers=mapping,
            peek=peek,
            limit=limit,
            clock=lambda: self.fx.now.timestamp(),
            fields=("all",),
        )

    def run_mailboxes(self, plugin: FakePluginBackend):
        return search.run_mailboxes(
            self.backend, self.config, drivers={PLUGIN_DRIVER: plugin}
        )

    def run_cli(self, *argv: str, registry: BackendRegistry | None = None, backend=None):
        registry = registry or self.registry
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            mock.patch.object(cli_mod, "BackendRegistry", lambda *a, **k: registry),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            code = cli_mod.main(
                list(argv),
                home=self.fx.home,
                mail_root=self.fx.mail_root,
                accounts_db=self.fx.accounts_db,
                backend=backend,
            )
        raw = stdout.getvalue()
        payload = json.loads(raw) if raw.strip() else None
        return code, payload, stderr.getvalue()

    def run_cli_ok(self, *argv: str, **kwargs) -> dict:
        code, payload, stderr = self.run_cli(*argv, **kwargs)
        self.assertEqual(code, 0, f"{argv} failed: {payload} {stderr}")
        assert payload is not None
        self.assertTrue(payload.get("ok"), payload)
        return payload

    def run_cli_error(self, *argv: str, **kwargs):
        code, payload, stderr = self.run_cli(*argv, **kwargs)
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertFalse(payload.get("ok"), payload)
        self.assertNotIn("messages", payload)
        self.assertNotIn("accounts", payload)
        return code, payload, stderr

    def log_text(self) -> str:
        return (self.fx.home / "logs" / "mailquery.log").read_text(encoding="utf-8")

    def start_lines(self) -> list[str]:
        return [line for line in self.log_text().splitlines() if "event=start" in line]

    @staticmethod
    def uids(payload: dict) -> list[str]:
        return [message["uid"] for message in payload["messages"]]


# --------------------------------------------------------------------------- #
# UT-MD-01 — declared-driver loading and fail-fast (AC-04)
# --------------------------------------------------------------------------- #


class DriverLifecycleTest(MultiDriverCase):
    def test_ut_md_01_01_only_declared_drivers_are_loaded(self) -> None:
        """UT-MD-01.01: only drivers declared in [scope] (plus the native) are loaded."""
        graph_entry = FakeEntryPoint(PLUGIN_DRIVER, plugin=plugin_factory())
        other_entry = FakeEntryPoint("other", plugin=plugin_class(driver="other"))
        registry = registry_for(graph_entry, other_entry)
        payload = self.run_cli_ok("mailboxes", registry=registry)
        self.assertEqual(payload["command"], "mailboxes")
        self.assertEqual(graph_entry.load_calls, 1, "the declared plugin is loaded")
        self.assertEqual(other_entry.load_calls, 0, "the undeclared plugin is not imported")
        start = self.start_lines()
        self.assertEqual(len(start), 1)
        self.assertRegex(start[0], r"event=start command=mailboxes backend=apple_mail drivers=apple_mail,graph$")
        self.assertNotIn("other", start[0])

    def test_ut_md_01_02_declared_driver_that_does_not_load_fails_without_partial_results(self) -> None:
        """UT-MD-01.02: an unimportable declared plugin fails with E_PLUGIN_INCOMPATIBLE."""
        broken = FakeEntryPoint(
            PLUGIN_DRIVER, import_error=ImportError("No module named 'missing_dep'")
        )
        registry = registry_for(broken)
        code, payload, stderr = self.run_cli_error("mailboxes", registry=registry)
        self.assertEqual(code, 3)
        self.assertEqual(payload["error"]["code"], "E_PLUGIN_INCOMPATIBLE")
        self.assertEqual(set(payload), {"ok", "command", "error"})
        self.assertTrue(stderr.strip())

    def test_ut_md_01_03_runtime_driver_failure_fails_without_partial_messages(self) -> None:
        """UT-MD-01.03: a driver that fails mid-merge fails the command, no messages[]."""
        failing = plugin_factory(
            failures={
                "query": MailqueryError(
                    "E_PLUGIN_FAILED", "plugin query failed", "retry the command"
                )
            }
        )
        registry = registry_for(FakeEntryPoint(PLUGIN_DRIVER, plugin=failing))
        code, payload, _ = self.run_cli_error("search", registry=registry)
        self.assertEqual(code, 3)
        self.assertEqual(payload["error"]["code"], "E_PLUGIN_FAILED")
        self.assertNotIn("messages", payload)

    def test_ut_md_01_04_every_open_driver_is_closed_even_on_failure(self) -> None:
        """UT-MD-01.04: all opened drivers are closed (best effort) when the command fails."""
        failing, created = capturing_factory(
            failures={
                "query": MailqueryError(
                    "E_PLUGIN_FAILED", "plugin query failed", "retry the command"
                )
            }
        )
        registry = registry_for(FakeEntryPoint(PLUGIN_DRIVER, plugin=failing))
        with mock.patch.object(self.backend, "close", wraps=self.backend.close) as close_mock:
            code, _payload, _ = self.run_cli(
                "search", registry=registry, backend=self.backend
            )
        self.assertEqual(code, 3)
        self.assertTrue(close_mock.called, "the native driver is closed")
        self.assertEqual(len(created), 1)
        self.assertTrue(created[0].closed, "the plugin driver is closed")


# --------------------------------------------------------------------------- #
# UT-MD-02 — merge and total order (AC-04, PRD §11.3)
# --------------------------------------------------------------------------- #


class MergeOrderTest(MultiDriverCase):
    def test_ut_md_02_01_search_merges_two_drivers_in_total_order(self) -> None:
        """UT-MD-02.01: search order is (date_received DESC, driver ASC, key DESC)."""
        plugin = FakePluginBackend(
            rows=[
                self.plugin_row("P1", minutes_ago=12),
                self.plugin_row("P2", minutes_ago=25),
            ]
        )
        payload = self.run_search(plugin)
        expected = [
            prefixed_uid("P1", PLUGIN_DRIVER),
            prefixed_uid(83170),
            prefixed_uid(83160),
            prefixed_uid("P2", PLUGIN_DRIVER),
            *APPLE_SEARCH_ORDER[2:],
        ]
        self.assertEqual(self.uids(payload), expected)
        self.assertEqual(payload["count"], 14)
        self.assertIs(payload["truncated"], False)

    def test_ut_md_02_02_new_merges_ascending_and_advances_the_cursor(self) -> None:
        """UT-MD-02.02: new is ascending; the cursor advances with the last emitted."""
        plugin = FakePluginBackend(
            rows=[
                self.plugin_row("P1", minutes_ago=16),
                self.plugin_row("P2", minutes_ago=18),
            ]
        )
        payload = self.run_new(plugin)
        self.assertEqual(
            self.uids(payload),
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
        self.assertEqual(
            set(self.read_state()["emitted_uids"]),
            {
                prefixed_uid(83160),
                prefixed_uid("P1", PLUGIN_DRIVER),
                prefixed_uid("P2", PLUGIN_DRIVER),
                prefixed_uid(83170),
            },
        )

    def test_ut_md_02_03_same_message_id_in_two_drivers_is_two_results(self) -> None:
        """UT-MD-02.03: no cross-driver dedupe; duplicate_count is per driver."""
        self.use_config(DEDUPE_MULTI_CONFIG)
        plugin = FakePluginBackend(
            rows=[
                self.plugin_row(
                    "P1", minutes_ago=59, message_id="<duplicate-4@fixture.example>"
                )
            ]
        )
        payload = self.run_search(plugin)
        shared = [
            message
            for message in payload["messages"]
            if message["message_id"] == "<duplicate-4@fixture.example>"
        ]
        self.assertEqual(len(shared), 2, "one result per driver")
        by_uid = {message["uid"]: message for message in shared}
        self.assertEqual(by_uid[prefixed_uid(83143)]["duplicate_count"], 2)
        self.assertEqual(
            by_uid[prefixed_uid("P1", PLUGIN_DRIVER)]["duplicate_count"], 1
        )

    def test_ut_md_02_04_duplicate_inside_a_driver_keeps_the_canonical_copy(self) -> None:
        """UT-MD-02.04: in-driver dedupe keeps INBOX and counts the copies."""
        self.use_config(DEDUPE_MULTI_CONFIG)
        plugin = FakePluginBackend(rows=[self.plugin_row("P1", minutes_ago=12)])
        payload = self.run_search(plugin)
        canonical = {
            message["uid"]: message for message in payload["messages"]
        }[prefixed_uid(83143)]
        self.assertEqual(canonical["duplicate_count"], 2)
        self.assertEqual(canonical["mailbox"]["name"], "INBOX")
        self.assertNotIn(prefixed_uid(83142), self.uids(payload))

    def test_ut_md_02_05_native_order_key_is_compared_by_capability(self) -> None:
        """UT-MD-02.05: numeric keys compare as ints, text keys as text."""
        self.use_config(PLUGIN_ONLY_CONFIG)
        cases = (
            ("numeric", ["9", "10"], ["10", "9"]),
            ("text", ["9", "10"], ["9", "10"]),
        )
        for capability, keys, expected in cases:
            with self.subTest(native_order=capability):
                capabilities = dict(PLUGIN_CAPABILITIES, native_order=capability)
                plugin = FakePluginBackend(
                    rows=[
                        self.plugin_row(key, minutes_ago=5, native_order_key=key)
                        for key in keys
                    ],
                    capabilities=capabilities,
                )
                result = search.run_search(
                    None,
                    self.config,
                    search.Filters(),
                    drivers={PLUGIN_DRIVER: plugin},
                    native="apple_mail",
                )
                self.assertEqual(
                    self.uids(result),
                    [prefixed_uid(key, PLUGIN_DRIVER) for key in expected],
                )

    def test_ut_md_02_06_same_date_is_decided_by_driver_ascending(self) -> None:
        """UT-MD-02.06: at the same date the driver name decides (ASC in both orders)."""
        plugin = FakePluginBackend(rows=[self.plugin_row("P1", minutes_ago=15)])
        payload = self.run_search(plugin)
        uids = self.uids(payload)
        first = uids.index(prefixed_uid(83170))
        self.assertEqual(
            uids[first : first + 2],
            [prefixed_uid(83170), prefixed_uid("P1", PLUGIN_DRIVER)],
            "apple_mail sorts before graph at the same date",
        )


# --------------------------------------------------------------------------- #
# UT-MD-03 — mailboxes composition (AC-04, PRD §11.3)
# --------------------------------------------------------------------------- #


class MailboxesMergeTest(MultiDriverCase):
    def test_ut_md_03_01_lists_are_concatenated_in_scope_block_order(self) -> None:
        """UT-MD-03.01: accounts/mailboxes/excluded_stores follow the [scope] block order."""
        self.use_config(
            f"{PLUGIN_ACCOUNT_BLOCK}\n\n[scope.\"{ICLOUD_LABEL}\"]\n"
        )
        plugin = FakePluginBackend()
        payload = self.run_mailboxes(plugin)
        self.assertEqual(
            [account["uuid"] for account in payload["accounts"][:2]],
            [PLUGIN_ACCOUNT_UUID, ACCOUNT_ICLOUD],
        )
        self.assertEqual(
            payload["mailboxes"][0]["account"]["uuid"], PLUGIN_ACCOUNT_UUID
        )
        self.assertTrue(
            all(account["declared"] for account in payload["accounts"][:2])
        )
        self.assertEqual(payload["excluded_stores"], [])

    def test_ut_md_03_02_plugin_accounts_are_opaque_and_have_no_excluded_stores(self) -> None:
        """UT-MD-03.02: plugin label/uuid are opaque; excluded_stores is empty."""
        self.use_config(
            f"{PLUGIN_ACCOUNT_BLOCK}\n\n[scope.\"{ICLOUD_LABEL}\"]\n"
        )
        plugin = FakePluginBackend()
        payload = self.run_mailboxes(plugin)
        account = payload["accounts"][0]
        self.assertEqual(account["uuid"], PLUGIN_ACCOUNT_UUID)
        self.assertEqual(account["label"], PLUGIN_ACCOUNT_LABEL)
        self.assertIsNone(account["email"])
        self.assertIs(account["declared"], True)
        self.assertEqual(payload["excluded_stores"], [])

    def test_ut_md_03_03_undeclared_driver_contributes_nothing(self) -> None:
        """UT-MD-03.03: the native driver is not consulted when only the plugin is declared."""
        self.use_config(PLUGIN_ONLY_CONFIG)
        plugin = FakePluginBackend()
        payload = self.run_mailboxes(plugin)
        self.assertEqual(
            [account["uuid"] for account in payload["accounts"]],
            [PLUGIN_ACCOUNT_UUID],
        )
        self.assertNotIn(ACCOUNT_ICLOUD, [account["uuid"] for account in payload["accounts"]])


# --------------------------------------------------------------------------- #
# UT-MD-04 — global cursor and lookback (AC-04, PRD §11.2)
# --------------------------------------------------------------------------- #


class GlobalCursorTest(MultiDriverCase):
    def test_ut_md_04_01_every_driver_uses_the_same_watermark(self) -> None:
        """UT-MD-04.01: one global cursor; each driver gets the same last_date/lookback."""
        state_store = self.seed_cursor(minutes_ago=60)
        expected_since = self.timestamp(minutes_ago=70)
        plugin = FakePluginBackend(rows=[self.plugin_row("P1", minutes_ago=30)])
        with mock.patch.object(
            self.backend, "query", wraps=self.backend.query
        ) as native_query:
            self.run_new(plugin, state_store=state_store)
        native_since = [
            call.kwargs["since"] for call in native_query.call_args_list if "since" in call.kwargs
        ]
        self.assertEqual(native_since, [expected_since])
        plugin_since = [query["kwargs"].get("since") for query in plugin.queries]
        self.assertEqual(plugin_since[-1], expected_since)

    def test_ut_md_04_02_first_run_window_is_computed_over_the_merged_set(self) -> None:
        """UT-MD-04.02: the first-run window and the ring are merged and prefixed."""
        plugin = FakePluginBackend(
            rows=[
                self.plugin_row("P1", minutes_ago=16),
                self.plugin_row("P2", minutes_ago=18),
            ]
        )
        payload = self.run_new(plugin)
        self.assertEqual(payload["count"], 4)
        ring = self.read_state()["emitted_uids"]
        self.assertEqual(len(ring), 4)
        self.assertTrue(all(":" in uid for uid in ring))
        self.assertEqual(payload["cursor"]["current"]["lookback_seconds"], 600)

    def test_ut_md_04_03_cursor_of_an_installed_but_undeclared_driver_is_kept(self) -> None:
        """UT-MD-04.03: installed-but-undeclared last_uid keeps the cursor and uses the date."""
        self.use_config(ICLOUD_ONLY_CONFIG)
        state_store = self.seed_cursor(
            minutes_ago=10,
            last_uid=prefixed_uid("P9", PLUGIN_DRIVER),
            emitted_uids=(prefixed_uid(83170), prefixed_uid(83160), prefixed_uid(83150)),
        )
        payload = self.run_new(state_store=state_store, drivers={})
        self.assertEqual(
            payload["cursor"]["previous"]["last_uid"],
            prefixed_uid("P9", PLUGIN_DRIVER),
        )
        self.assertEqual(
            payload["cursor"]["current"]["last_uid"],
            prefixed_uid("P9", PLUGIN_DRIVER),
        )

    def test_ut_md_04_04_ring_uids_of_undeclared_drivers_survive(self) -> None:
        """UT-MD-04.04: foreign ring uids stay in the ring and do not break new."""
        self.use_config(ICLOUD_ONLY_CONFIG)
        foreign = ("outlook:ABC123", prefixed_uid("P7", PLUGIN_DRIVER))
        state_store = self.seed_cursor(
            minutes_ago=5, emitted_uids=foreign + (prefixed_uid(83170),)
        )
        payload = self.run_new(state_store=state_store, drivers={})
        ring = self.read_state()["emitted_uids"]
        for uid in foreign:
            self.assertIn(uid, ring)
        for uid in payload["messages"]:
            self.assertIn(uid["uid"], ring)


# --------------------------------------------------------------------------- #
# UT-MD-05 — limits and scan (AC-04, PRD.md §12.5)
# --------------------------------------------------------------------------- #


class LimitsMergeTest(MultiDriverCase):
    def test_ut_md_05_01_limit_is_applied_after_the_merge(self) -> None:
        """UT-MD-05.01: --limit is applied to the merged list; truncated/hint follow."""
        plugin = FakePluginBackend(
            rows=[
                self.plugin_row("P1", minutes_ago=12),
                self.plugin_row("P2", minutes_ago=25),
            ]
        )
        payload = self.run_search(plugin, limit=5)
        self.assertEqual(payload["count"], 5)
        self.assertEqual(
            self.uids(payload),
            [
                prefixed_uid("P1", PLUGIN_DRIVER),
                prefixed_uid(83170),
                prefixed_uid(83160),
                prefixed_uid("P2", PLUGIN_DRIVER),
                prefixed_uid(83150),
            ],
        )
        self.assertIs(payload["truncated"], True)
        self.assertIsNotNone(payload["hint"])
        self.assertIn("W_RESULTS_TRUNCATED", " ".join(payload["warnings"]))

    def test_ut_md_05_02_scan_counters_are_summed_per_driver(self) -> None:
        """UT-MD-05.02: scan.candidates and scan.messages_read add every driver."""
        plugin = FakePluginBackend(
            rows=[
                self.plugin_row("P1", minutes_ago=12, body_text="body one"),
                self.plugin_row("P2", minutes_ago=25, body_text="body two"),
            ]
        )
        multi = self.run_search(plugin)

        self.use_config(DEFAULT_CONFIG)
        native = search.run_search(
            self.backend, self.config, search.Filters(), drivers={}, fields=("all",)
        )
        self.use_config(PLUGIN_ONLY_CONFIG)
        only_plugin = search.run_search(
            None,
            self.config,
            search.Filters(),
            drivers={PLUGIN_DRIVER: plugin},
            native="apple_mail",
            fields=("all",),
        )
        self.assertEqual(
            multi["scan"]["candidates"],
            native["scan"]["candidates"] + only_plugin["scan"]["candidates"],
        )
        self.assertEqual(
            multi["scan"]["messages_read"],
            native["scan"]["messages_read"] + only_plugin["scan"]["messages_read"],
        )

    def test_ut_md_05_03_limit_above_the_total_is_not_truncated(self) -> None:
        """UT-MD-05.03: a limit above the merged total sets neither truncated nor hint."""
        plugin = FakePluginBackend(rows=[self.plugin_row("P1", minutes_ago=12)])
        payload = self.run_search(plugin, limit=200)
        self.assertIs(payload["truncated"], False)
        self.assertIsNone(payload["hint"])
        self.assertEqual(payload["count"], len(payload["messages"]))


# --------------------------------------------------------------------------- #
# UT-MD-06 — multi-driver log (AC-19, PRD §14)
# --------------------------------------------------------------------------- #


class MultiDriverLogTest(MultiDriverCase):
    def test_ut_md_06_01_start_logs_native_backend_and_declared_drivers(self) -> None:
        """UT-MD-06.01: event=start names backend=<native> and drivers=<declared list>."""
        entry = FakeEntryPoint(PLUGIN_DRIVER, plugin=plugin_factory())
        registry = registry_for(entry)
        self.run_cli_ok("mailboxes", registry=registry)
        start = self.start_lines()
        self.assertEqual(len(start), 1)
        self.assertRegex(
            start[0],
            r"event=start command=mailboxes backend=apple_mail drivers=apple_mail,graph$",
        )

    def test_ut_md_06_02_log_has_no_uids_accounts_paths_or_terms(self) -> None:
        """UT-MD-06.02: the log never records uids, accounts, paths, subjects or terms."""
        entry = FakeEntryPoint(PLUGIN_DRIVER, plugin=plugin_factory())
        registry = registry_for(entry)
        self.run_cli_ok("search", "--subject", "Invoice", registry=registry)
        log = self.log_text()
        forbidden = (
            "83170",
            "Invoice",
            "invoice-2026-10",
            str(self.fx.root),
            PLUGIN_ACCOUNT_UUID,
            PLUGIN_ACCOUNT_LABEL,
            "plugin@example.com",
        )
        for token in forbidden:
            self.assertNotIn(token, log)

    def test_ut_md_06_03_one_declared_driver_logs_native_backend_and_that_driver(self) -> None:
        """UT-MD-06.03: with only a plugin declared, backend= is still the native driver."""
        self.use_config(PLUGIN_ONLY_CONFIG)
        entry = FakeEntryPoint(PLUGIN_DRIVER, plugin=plugin_factory())
        registry = registry_for(entry)
        with mock.patch.object(cli_mod, "get_backend", side_effect=AssertionError):
            payload = self.run_cli_ok("mailboxes", registry=registry)
        self.assertEqual(
            [account["uuid"] for account in payload["accounts"]],
            [PLUGIN_ACCOUNT_UUID],
        )
        start = self.start_lines()
        self.assertRegex(
            start[-1],
            r"event=start command=mailboxes backend=apple_mail drivers=graph$",
        )


# --------------------------------------------------------------------------- #
# UT-MD-07 — show with a declared external driver (AC-05, AC-07)
# --------------------------------------------------------------------------- #


class ShowPluginTest(MultiDriverCase):
    def show_plugin(
        self,
        *,
        rows=None,
        capabilities=None,
        attachments=None,
        accounts=None,
        mailboxes=None,
    ):
        factory = plugin_factory(
            rows=rows,
            capabilities=capabilities,
            attachments=attachments,
            accounts=accounts,
            mailboxes=mailboxes,
        )
        entry = FakeEntryPoint(PLUGIN_DRIVER, plugin=factory)
        return entry, registry_for(entry)

    def test_ut_md_07_01_show_loads_the_declared_plugin(self) -> None:
        """UT-MD-07.01: show <plugin>:<id> returns prefixed uid, body and attachments."""
        rows = [
            self.plugin_row("P1", minutes_ago=12, body_text="Remote body text"),
        ]
        _entry, registry = self.show_plugin(rows=rows)
        payload = self.run_cli_ok("show", f"{PLUGIN_DRIVER}:P1", registry=registry)
        message = payload["message"]
        self.assertEqual(message["uid"], prefixed_uid("P1", PLUGIN_DRIVER))
        self.assertEqual(message["body_text"], "Remote body text")
        self.assertIs(message["readable"], True)
        self.assertEqual(
            message["attachments"],
            [
                {"index": entry["index"], "name": entry["name"], "cached_path": None}
                for entry in PLUGIN_ATTACHMENTS
            ],
        )
        self.assertEqual(message["mailbox"]["account"]["uuid"], PLUGIN_ACCOUNT_UUID)
        self.assertEqual(message["mailbox"]["account"]["label"], PLUGIN_ACCOUNT_LABEL)

    def test_ut_md_07_02_body_local_false_warnings_are_preserved(self) -> None:
        """UT-MD-07.02: a non-local plugin body applies W_BODY_NOT_LOCAL/W_BODY_UNREADABLE."""
        cases = ("W_BODY_NOT_LOCAL", "W_BODY_UNREADABLE")
        for warning in cases:
            with self.subTest(warning=warning):
                rows = [
                    self.plugin_row(
                        "P1",
                        minutes_ago=12,
                        readable=False,
                        available=False,
                        warnings=[f"{warning}: the body is not available"],
                    )
                ]
                _entry, registry = self.show_plugin(rows=rows)
                payload = self.run_cli_ok(
                    "show", f"{PLUGIN_DRIVER}:P1", registry=registry
                )
                message = payload["message"]
                self.assertIs(message["readable"], False)
                self.assertTrue(
                    any(item.startswith(warning) for item in payload["warnings"])
                )
                self.assertEqual(len(message["attachments"]), len(PLUGIN_ATTACHMENTS))

    def test_ut_md_07_03_undeclared_plugin_is_not_loaded(self) -> None:
        """UT-MD-07.03: show of an installed-but-undeclared driver is E_ACCOUNT_NOT_IN_SCOPE."""
        self.use_config(ICLOUD_ONLY_CONFIG)
        entry = FakeEntryPoint(PLUGIN_DRIVER, plugin=plugin_factory())
        registry = registry_for(entry)
        code, payload, _ = self.run_cli_error(
            "show", f"{PLUGIN_DRIVER}:P1", registry=registry
        )
        self.assertEqual(code, 2)
        self.assertEqual(payload["error"]["code"], "E_ACCOUNT_NOT_IN_SCOPE")
        self.assertEqual(entry.load_calls, 0, "the plugin must not be imported")

    def test_ut_md_07_04_attachments_none_returns_no_attachments(self) -> None:
        """UT-MD-07.04: attachments='none' returns [] without calling the operation."""
        capabilities = dict(
            network=False,
            readonly="promise",
            body_local=True,
            attachments="none",
            native_order="text",
        )
        factory, created = capturing_factory(
            rows=[self.plugin_row("P1", minutes_ago=12)], capabilities=capabilities
        )
        entry = FakeEntryPoint(PLUGIN_DRIVER, plugin=factory)
        payload = self.run_cli_ok(
            "show", f"{PLUGIN_DRIVER}:P1", registry=registry_for(entry)
        )
        self.assertEqual(payload["message"]["attachments"], [])
        self.assertEqual(len(created), 1)
        self.assertNotIn("attachments", created[0].calls)

    def test_ut_md_07_05_remote_attachments_only_report_names_and_write_nothing(self) -> None:
        """UT-MD-07.05: remote attachments only report names; show writes and downloads nothing."""
        _entry, registry = self.show_plugin(
            rows=[self.plugin_row("P1", minutes_ago=12)]
        )
        payload = self.run_cli_ok("show", f"{PLUGIN_DRIVER}:P1", registry=registry)
        names = [entry["name"] for entry in payload["message"]["attachments"]]
        self.assertEqual(names, [entry["name"] for entry in PLUGIN_ATTACHMENTS])
        self.assertTrue(
            all(entry["cached_path"] is None for entry in payload["message"]["attachments"])
        )
        self.assertFalse((self.fx.home / "attachments").exists(), "show writes no cache")

    def test_ut_md_07_06_plugin_native_order_key_orders_search(self) -> None:
        """UT-MD-07.06: the plugin native_order_key (text) orders its search results."""
        self.use_config(PLUGIN_ONLY_CONFIG)
        rows = [
            self.plugin_row("P1", minutes_ago=5, native_order_key="A"),
            self.plugin_row("P2", minutes_ago=5, native_order_key="B"),
        ]
        plugin = FakePluginBackend(rows=rows)
        payload = search.run_search(
            None,
            self.config,
            search.Filters(),
            drivers={PLUGIN_DRIVER: plugin},
            native="apple_mail",
            fields=("all",),
        )
        self.assertEqual(
            self.uids(payload),
            [
                prefixed_uid("P2", PLUGIN_DRIVER),
                prefixed_uid("P1", PLUGIN_DRIVER),
            ],
        )


# --------------------------------------------------------------------------- #
# Runtime plugin errors and metadata timeout (UT-ERR-03.04, UT-ERR-04.05)
# --------------------------------------------------------------------------- #


class PluginRuntimeErrorTest(MultiDriverCase):
    """Fail-fast behavior of a mapped plugin error and of the metadata deadline."""

    def test_ut_err_03_04_mapped_plugin_error_has_no_partial_results_and_closes_drivers(
        self,
    ) -> None:
        """UT-ERR-03.04: a mapped plugin failure fails the command and closes every driver."""
        failing, created = capturing_factory(
            failures={"query": PluginError(Reason.BUSY, hint="the plugin is busy")}
        )
        registry = registry_for(FakeEntryPoint(PLUGIN_DRIVER, plugin=failing))
        with mock.patch.object(
            self.backend, "close", wraps=self.backend.close
        ) as close_mock:
            code, payload, _stderr = self.run_cli_error(
                "search", registry=registry, backend=self.backend
            )
        self.assertEqual(code, 5)
        assert payload is not None
        self.assertEqual(payload["error"]["code"], "E_CLIENT_BUSY")
        self.assertNotIn("messages", payload)
        self.assertNotIn("count", payload)
        self.assertTrue(close_mock.called, "the native driver is closed")
        self.assertEqual(len(created), 1)
        self.assertTrue(created[0].closed, "the plugin driver is closed")

    def test_ut_err_04_05_timeout_during_merge_fails_without_messages_and_closes(
        self,
    ) -> None:
        """UT-ERR-04.05: a merge timeout is E_CLIENT_TIMEOUT, no messages[], drivers closed."""
        slow, created = capturing_factory(delays={"query": 2.0})
        registry = registry_for(FakeEntryPoint(PLUGIN_DRIVER, plugin=slow))
        with (
            mock.patch("mailquery.plugins.api.METADATA_TIMEOUT_SECONDS", 0.2),
            mock.patch.object(
                self.backend, "close", wraps=self.backend.close
            ) as close_mock,
        ):
            code, payload, _stderr = self.run_cli_error(
                "search", registry=registry, backend=self.backend
            )
        self.assertEqual(code, 3)
        assert payload is not None
        self.assertEqual(payload["error"]["code"], "E_CLIENT_TIMEOUT")
        self.assertNotIn("messages", payload)
        self.assertTrue(close_mock.called, "the native driver is closed")
        self.assertEqual(len(created), 1)
        self.assertTrue(created[0].closed, "the plugin driver is closed")


if __name__ == "__main__":  # pragma: no cover - manual runs
    unittest.main()

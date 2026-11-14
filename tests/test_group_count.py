"""``--group-by``, ``--count`` and the no-results ``hint`` of ``search``.

Covers the TEST-CATALOG groups UT-GRP-01 to UT-GRP-10 (grouping by one and two
keys, the group order and its limits, counting, the errors, the reads, the
scope hint, the warnings and ``content_notice`` of both options, and their
rejection in ``new``) and DOC-11 (help, READMEs and skill of both options).

The stores are the synthetic Apple Mail fixture, the plugin double and the
Outlook double. Every run uses a temporary home: the real ``~/Library/Mail``
and ``~/.mailquery`` are never read.
"""

from __future__ import annotations

import contextlib
import dataclasses
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
from mailquery import output
from mailquery import search
from mailquery.backends import get_backend
from mailquery.config import load_config
from mailquery.search import (
    DEFAULT_ROW_FIELDS,
    GROUP_KEYS,
    GROUP_MAX_GROUPS,
    GROUP_MAX_LIMIT,
)
from tests.fakes import outlook as fk
from tests.fakes.plugin import (
    ACCOUNT_LABEL,
    ACCOUNT_UUID,
    DEFAULT_ROWS,
    DRIVER,
    FakeEntryPoint,
    FakePluginBackend,
    internal_entry_points,
)
from tests.fixtures.make_fixtures import (
    DEFAULT_CONFIG,
    GMAIL_LABEL,
    ICLOUD_LABEL,
    LOCAL_LABEL,
    UID_BODY_SENDER_HEADERS,
    build_store,
    prefixed_uid,
    write_config,
)

_ROOT = Path(__file__).resolve().parents[1]
#: Injected local zone of the date-key cases (UTC-4).
_UTC_MINUS_4 = timezone(timedelta(hours=-4))
#: Fixed clock of the plugin rows: their dates are relative values of this.
BASE = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)

GROUP_KEYS_TEXT = ", ".join(GROUP_KEYS)
TWO_ACCOUNT_CONFIG = f'[scope."{ICLOUD_LABEL}"]\n\n[scope."{GMAIL_LABEL}"]\n'
PLUGIN_CONFIG = f'[scope."{DRIVER}:{ACCOUNT_LABEL}"]\n'


def _no_results(folders: int, accounts: int) -> str:
    return (
        f"no messages matched in {folders} folder(s) of {accounts} account(s); "
        'run "mailquery mailboxes" to see other folders, or add --include-mailbox'
    )


def _warning_codes(warnings) -> list[str]:
    return [str(warning).split(":", 1)[0] for warning in warnings]


def _plugin_registry(plugin: object) -> object:
    return cli_mod.BackendRegistry(
        platform=sys.platform,
        entry_points=[
            *internal_entry_points(),
            FakeEntryPoint(DRIVER, plugin=plugin),
        ],
    )


def _plugin_cli(home: Path, argv, plugin: object):
    """Run one command with the plugin double injected through the registry."""
    registry = _plugin_registry(plugin)
    stdout, stderr = io.StringIO(), io.StringIO()
    with (
        mock.patch.object(cli_mod, "BackendRegistry", lambda *a, **k: registry),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        code = cli_mod.main(list(argv), home=home)
    raw = stdout.getvalue()
    return code, (json.loads(raw) if raw.strip() else None), stderr.getvalue()


def _row(
    native_id: str,
    *,
    sender: tuple[str, str | None] = ("Plugin", "plugin@example.com"),
    subject: str | None = None,
    received: datetime | None = None,
    **overrides,
) -> dict:
    """One row of the plugin double, relative to the fixed ``BASE`` clock."""
    row = dict(DEFAULT_ROWS[0])
    date = float(received.timestamp()) if received is not None else row["date_received"]
    row.update(
        {
            "uid": native_id,
            "native_order_key": native_id,
            "global_message_id": 0,
            "subject": subject if subject is not None else f"Plugin {native_id}",
            "sender_name": sender[0],
            "sender_address": sender[1],
            "date_received": date,
            "date_sent": date,
            "has_attachments": False,
        }
    )
    row.update(overrides)
    return row


def _ago(minutes: float) -> datetime:
    return BASE - timedelta(minutes=minutes)


# --------------------------------------------------------------------------- #
# Shared cases
# --------------------------------------------------------------------------- #


class _HomeCase(unittest.TestCase):
    """Temporary home and ``cli.main`` in process (no built-in store)."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.addCleanup(cli_mod._close_logging_handlers)

    def run_cli(self, *argv: str, backend: object = None):
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            code = cli_mod.main(list(argv), home=self.home, backend=backend)
        raw = stdout.getvalue()
        return code, (json.loads(raw) if raw.strip() else None), stderr.getvalue()

    def run_ok(self, *argv: str, backend: object = None) -> dict:
        code, payload, stderr = self.run_cli(*argv, backend=backend)
        self.assertEqual(code, 0, f"{argv}: {payload} {stderr}")
        assert payload is not None
        self.assertIs(payload.get("ok"), True)
        return payload

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


class _AppleCase(_HomeCase):
    """One synthetic Apple Mail store per test, driven through ``cli.main``."""

    body_samples = False
    extended = False

    def setUp(self) -> None:
        self.addCleanup(cli_mod._close_logging_handlers)
        self.fx = build_store(body_samples=self.body_samples, extended=self.extended)
        self.addCleanup(self.fx.cleanup)
        self.root = self.fx.root
        self.home = self.fx.home
        write_config(self.home, DEFAULT_CONFIG)

    def configure(self, content: str) -> None:
        write_config(self.home, content)

    def run_cli(self, *argv: str, backend: object = None):
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            code = cli_mod.main(
                list(argv),
                home=self.home,
                mail_root=self.fx.mail_root,
                accounts_db=self.fx.accounts_db,
            )
        raw = stdout.getvalue()
        return code, (json.loads(raw) if raw.strip() else None), stderr.getvalue()

    def run_error(self, *argv: str, exit_code: int, code: str) -> dict:
        actual, payload, stderr = self.run_cli(*argv)
        self.assertEqual(actual, exit_code, f"{argv}: {payload} {stderr}")
        assert payload is not None
        self.assertIs(payload.get("ok"), False)
        self.assertEqual(payload["error"]["code"], code)
        return payload


class _PluginCase(_HomeCase):
    """Temporary home that declares the plugin account, plus a direct engine helper."""

    accounts = None
    mailboxes = None

    def setUp(self) -> None:
        super().setUp()
        write_config(self.home, PLUGIN_CONFIG)

    def plugin(self, rows=(), **kwargs) -> FakePluginBackend:
        return FakePluginBackend(
            rows=list(rows),
            accounts=self.accounts,
            mailboxes=self.mailboxes,
            **kwargs,
        )

    def config(self, plugin=None, **search_overrides):
        """Loaded config; a plugin instance provides the registry its scope needs."""
        registry = _plugin_registry(plugin) if plugin is not None else None
        config = load_config(self.home, registry=registry)
        if search_overrides:
            return dataclasses.replace(
                config,
                search=dataclasses.replace(config.search, **search_overrides),
            )
        return config

    def run_core(
        self, plugin, *, group_by=None, count=False, config=None, **filters
    ) -> dict:
        """``search.run_search`` over the plugin double (no CLI)."""
        return search.run_search(
            None,
            config if config is not None else self.config(plugin),
            search.Filters(**filters),
            drivers={DRIVER: plugin},
            native="apple_mail",
            group_by=group_by,
            count=count,
        )

    def run_plugin(self, plugin, *argv: str) -> dict:
        code, payload, stderr = _plugin_cli(self.home, ["search", *argv], plugin)
        self.assertEqual(code, 0, f"{argv}: {payload} {stderr}")
        assert payload is not None
        self.assertIs(payload.get("ok"), True)
        return payload

    def run_plugin_error(self, *argv: str) -> tuple[int, dict]:
        code, payload, stderr = _plugin_cli(self.home, list(argv), self.plugin())
        assert payload is not None
        self.assertIs(payload.get("ok"), False, f"{stderr}")
        return code, payload


# --------------------------------------------------------------------------- #
# UT-GRP-01 — ``--group-by from``
# --------------------------------------------------------------------------- #


class GroupByFromTests(_PluginCase):
    """UT-GRP-01: one group per sender, newest messages first."""

    def _rows(self):
        rows = [
            _row(
                f"banco-{minutes}",
                sender=("Banco", "BANCO@Example.COM"),
                received=_ago(minutes),
            )
            for minutes in range(7)
        ]
        rows += [
            _row("otro-1", sender=("Otro", "otro@example.com"), received=_ago(10)),
            _row("otro-2", sender=("Otro", "otro@example.com"), received=_ago(11)),
        ]
        return rows

    def test_ut_grp_01_01_group_per_sender_with_five_newest(self) -> None:
        """UT-GRP-01.01: sender groups (lowercase) with count and the 5 newest rows, without ``from``."""
        payload = self.run_plugin(
            self.plugin(self._rows()), "--group-by", "from", "--limit", "5"
        )
        self.assertEqual(payload["count"], 9)
        self.assertIs(payload["truncated"], False)
        self.assertIsNone(payload["hint"])
        self.assertEqual(len(payload["groups"]), 2)
        banco = payload["groups"][0]
        self.assertEqual(list(banco), ["from", "count", "messages"])
        self.assertEqual(banco["from"], "banco@example.com")
        self.assertEqual(banco["count"], 7)
        self.assertEqual(len(banco["messages"]), 5)
        self.assertEqual(
            [message["uid"] for message in banco["messages"]],
            [f"{DRIVER}:banco-{minutes}" for minutes in range(5)],
        )
        for message in banco["messages"]:
            self.assertEqual(
                list(message),
                ["uid", "subject", "date_received", "is_read", "has_attachments"],
            )
        other = payload["groups"][1]
        self.assertEqual(other["from"], "otro@example.com")
        self.assertEqual(other["count"], 2)

    def test_ut_grp_01_02_groups_are_ordered_by_their_newest_message(self) -> None:
        """UT-GRP-01.02: the group with the newest message comes first."""
        payload = self.run_plugin(
            self.plugin(
                [
                    _row("late", sender=("A", "a@example.com"), received=_ago(1)),
                    _row("middle", sender=("B", "b@example.com"), received=_ago(5)),
                    _row("early", sender=("C", "c@example.com"), received=_ago(20)),
                ]
            ),
            "--group-by",
            "from",
        )
        self.assertEqual(
            [group["from"] for group in payload["groups"]],
            ["a@example.com", "b@example.com", "c@example.com"],
        )

    def test_ut_grp_01_03_limit_zero_gives_no_messages(self) -> None:
        """UT-GRP-01.03: ``--limit 0`` delivers ``messages: []`` in every group."""
        payload = self.run_plugin(
            self.plugin(self._rows()), "--group-by", "from", "--limit", "0"
        )
        self.assertEqual([group["count"] for group in payload["groups"]], [7, 2])
        for group in payload["groups"]:
            self.assertEqual(group["messages"], [])

    def test_ut_grp_01_04_fields_snippet_is_added_to_group_rows(self) -> None:
        """UT-GRP-01.04: ``--fields snippet`` adds ``snippet`` to the group rows."""
        payload = self.run_plugin(
            self.plugin(self._rows()),
            "--group-by",
            "from",
            "--fields",
            "snippet",
        )
        row = payload["groups"][0]["messages"][0]
        expected = [name for name in DEFAULT_ROW_FIELDS if name != "from"]
        self.assertEqual(list(row), [*expected, "snippet"])
        self.assertEqual(row["snippet"], "Plugin body")

    def test_ut_grp_01_06_default_limit_does_not_apply(self) -> None:
        """UT-GRP-01.06: ``[search].default_limit`` does not change the 5 per group."""
        plugin = self.plugin(
            [
                _row(
                    f"row-{minutes}",
                    sender=("S", "s@example.com"),
                    received=_ago(minutes),
                )
                for minutes in range(7)
            ]
        )
        payload = self.run_core(
            plugin, group_by=("from",), config=self.config(plugin, default_limit=20)
        )
        self.assertEqual(payload["groups"][0]["count"], 7)
        self.assertEqual(len(payload["groups"][0]["messages"]), 5)


class GroupByFromAppleTests(_AppleCase):
    """UT-GRP-01: grouping after deduplication over the synthetic store."""

    def test_ut_grp_01_05_dedupe_happens_before_grouping(self) -> None:
        """UT-GRP-01.05: the Gmail/INBOX duplicate of the synthetic store counts once."""
        self.configure(
            f'[scope."{ICLOUD_LABEL}"]\nmailbox_list = ["Facturas", "Archivo"]\n\n'
            f'[scope."{GMAIL_LABEL}"]\nmailbox_list = ["All Mail"]\n\n'
            f'[scope."{LOCAL_LABEL}"]\n'
        )
        payload = self.run_ok("search", "--group-by", "from", "--fields", "all")
        self.assertEqual(payload["count"], 12)
        self.assertEqual(
            sum(group["count"] for group in payload["groups"]), payload["count"]
        )
        shared = next(
            group
            for group in payload["groups"]
            if group["from"] == "shared@fixture.example"
        )
        self.assertEqual(shared["count"], 1)
        self.assertEqual(shared["messages"][0]["uid"], prefixed_uid(83143))


# --------------------------------------------------------------------------- #
# UT-GRP-02 — two keys and dates
# --------------------------------------------------------------------------- #


class GroupKeysTests(_PluginCase):
    """UT-GRP-02: two keys, local dates, null keys and the group order."""

    def test_ut_grp_02_01_comma_and_repeated_keys_match(self) -> None:
        """UT-GRP-02.01: ``domain,month`` and ``--group-by domain --group-by month`` match."""
        rows = [
            _row(
                "a",
                sender=("A", "a@a.example"),
                received=datetime(2026, 11, 5, 12, tzinfo=timezone.utc),
            ),
            _row(
                "b",
                sender=("B", "b@a.example"),
                received=datetime(2026, 11, 20, 12, tzinfo=timezone.utc),
            ),
            _row(
                "c",
                sender=("C", "c@b.example"),
                received=datetime(2026, 12, 2, 12, tzinfo=timezone.utc),
            ),
        ]
        with mock.patch.object(output, "LOCAL_ZONE", _UTC_MINUS_4):
            comma = self.run_plugin(
                self.plugin(rows), "--group-by", "domain,month", "--fields", "all"
            )
            repeated = self.run_plugin(
                self.plugin(rows),
                "--group-by",
                "domain",
                "--group-by",
                "month",
                "--fields",
                "all",
            )
        self.assertEqual(comma["groups"], repeated["groups"])
        self.assertEqual(
            list(comma["groups"][0]), ["domain", "month", "count", "messages"]
        )
        self.assertEqual(
            [
                (group["domain"], group["month"], group["count"])
                for group in comma["groups"]
            ],
            [("b.example", "2026-12", 1), ("a.example", "2026-11", 2)],
        )

    def test_ut_grp_02_02_dates_use_the_local_zone(self) -> None:
        """UT-GRP-02.02: a message at 02:00 UTC falls on the previous local day."""
        rows = [
            _row("night", received=datetime(2026, 11, 13, 2, 0, tzinfo=timezone.utc)),
            _row("month", received=datetime(2026, 12, 1, 2, 0, tzinfo=timezone.utc)),
        ]
        with mock.patch.object(output, "LOCAL_ZONE", _UTC_MINUS_4):
            day = self.run_plugin(self.plugin(rows), "--group-by", "day")
            month = self.run_plugin(self.plugin(rows), "--group-by", "month")
        self.assertEqual(
            {group["day"] for group in day["groups"]},
            {"2026-11-12", "2026-11-30"},
        )
        self.assertEqual({group["month"] for group in month["groups"]}, {"2026-11"})

    def test_ut_grp_02_03_iso_week_across_the_year_change(self) -> None:
        """UT-GRP-02.03: 2026-12-31 and 2027-01-01 are 2026-W53; 2027-01-04 is 2027-W01."""
        rows = [
            _row(
                "new-year-eve",
                received=datetime(2026, 12, 31, 12, tzinfo=timezone.utc),
            ),
            _row("new-year", received=datetime(2027, 1, 1, 12, tzinfo=timezone.utc)),
            _row("monday", received=datetime(2027, 1, 4, 12, tzinfo=timezone.utc)),
        ]
        with mock.patch.object(output, "LOCAL_ZONE", _UTC_MINUS_4):
            payload = self.run_plugin(self.plugin(rows), "--group-by", "week")
        self.assertEqual(
            [(group["week"], group["count"]) for group in payload["groups"]],
            [("2027-W01", 1), ("2026-W53", 2)],
        )

    def test_ut_grp_02_04_null_keys_form_the_last_group(self) -> None:
        """UT-GRP-02.04: undated messages and senders without an address form the ``null`` group."""
        rows = [
            _row("dated", sender=("A", "a@example.com"), received=_ago(0)),
            _row(
                "undated",
                sender=("B", "b@example.com"),
                date_received=None,
                date_sent=None,
            ),
            _row("zero", date_received=0, date_sent=0),
            _row("huge", date_received=1e20, date_sent=1e20),
        ]
        with mock.patch.object(output, "LOCAL_ZONE", _UTC_MINUS_4):
            day = self.run_plugin(self.plugin(rows), "--group-by", "day")
        self.assertEqual(day["groups"][-1]["day"], None)
        self.assertEqual(day["groups"][-1]["count"], 3)
        self.assertEqual(day["groups"][0]["day"], "2026-11-10")
        senders = self.run_plugin(
            self.plugin(
                [
                    _row("one", sender=("A", "a@example.com"), received=_ago(0)),
                    _row("two", sender=("B", None), received=_ago(1)),
                ]
            ),
            "--group-by",
            "from",
        )
        self.assertEqual(senders["groups"][-1]["from"], None)

    def test_ut_grp_02_06_ties_sort_by_keys_and_undated_groups_go_last(self) -> None:
        """UT-GRP-02.06: equal newest messages order by keys; a group without dates goes after."""
        payload = self.run_plugin(
            self.plugin(
                [
                    _row("b", sender=("B", "b@example.com"), received=_ago(0)),
                    _row("a", sender=("A", "a@example.com"), received=_ago(0)),
                    _row(
                        "c",
                        sender=("C", "c@example.com"),
                        date_received=None,
                        date_sent=None,
                    ),
                ]
            ),
            "--group-by",
            "from",
        )
        self.assertEqual(
            [group["from"] for group in payload["groups"]],
            ["a@example.com", "b@example.com", "c@example.com"],
        )

    def test_ut_grp_02_07_address_without_at_has_no_domain(self) -> None:
        """UT-GRP-02.07: an address without ``@`` keeps ``from`` and gives a ``null`` domain."""
        from_payload = self.run_plugin(
            self.plugin([_row("one", sender=("X", "SinArroba"))]), "--group-by", "from"
        )
        self.assertEqual(from_payload["groups"][0]["from"], "sinarroba")
        domain_payload = self.run_plugin(
            self.plugin([_row("one", sender=("X", "SinArroba"))]),
            "--group-by",
            "domain",
        )
        self.assertEqual(domain_payload["groups"][0]["domain"], None)

    def test_ut_grp_02_08_null_month_group_goes_after_the_dated_ones(self) -> None:
        """UT-GRP-02.08: groups with a ``null`` key sort after the others, keys ascending."""
        rows = [
            _row(
                "one",
                sender=("A", "one@example.com"),
                received=datetime(2026, 11, 5, 12, tzinfo=timezone.utc),
            ),
            _row(
                "two",
                sender=("B", "two@example.com"),
                received=datetime(2026, 11, 20, 12, tzinfo=timezone.utc),
            ),
            _row(
                "three",
                sender=("C", "three@aaa.com"),
                received=datetime(2026, 11, 10, 12, tzinfo=timezone.utc),
            ),
            _row(
                "four",
                sender=("D", "four@example.com"),
                date_received=None,
                date_sent=None,
            ),
            _row(
                "five",
                sender=("E", "five@aaa.com"),
                date_received=None,
                date_sent=None,
            ),
        ]
        with mock.patch.object(output, "LOCAL_ZONE", _UTC_MINUS_4):
            payload = self.run_plugin(self.plugin(rows), "--group-by", "domain,month")
        self.assertEqual(
            [(group["domain"], group["month"]) for group in payload["groups"]],
            [
                ("example.com", "2026-11"),
                ("aaa.com", "2026-11"),
                ("aaa.com", None),
                ("example.com", None),
            ],
        )


class GroupMailboxKeysTests(_AppleCase):
    """UT-GRP-02: ``mailbox`` and ``account`` group keys over the synthetic store."""

    def test_ut_grp_02_05_mailbox_and_account_keys(self) -> None:
        """UT-GRP-02.05: ``mailbox`` gives account and path; ``account`` gives the label."""
        mailbox = self.run_ok("search", "--group-by", "mailbox")
        in_cloud = next(
            group
            for group in mailbox["groups"]
            if group["mailbox"] == {"account": ICLOUD_LABEL, "path": "INBOX"}
        )
        self.assertEqual(in_cloud["count"], 8)
        for group in mailbox["groups"]:
            for message in group["messages"]:
                self.assertNotIn("mailbox", message)
        account = self.run_ok("search", "--group-by", "account")
        self.assertEqual(
            {group["account"] for group in account["groups"]},
            {ICLOUD_LABEL, GMAIL_LABEL},
        )


class GroupAccountUuidTests(_PluginCase):
    """UT-GRP-02: the account label falls back to its uuid."""

    def test_ut_grp_02_05_account_without_label_uses_the_uuid(self) -> None:
        """UT-GRP-02.05: a plugin account without a label groups by its uuid."""
        self.accounts = [
            {"uuid": ACCOUNT_UUID, "label": None, "email": None, "local": False}
        ]
        write_config(self.home, f'[scope."{DRIVER}:{ACCOUNT_UUID}"]\n')
        payload = self.run_plugin(
            self.plugin([_row("one"), _row("two")]), "--group-by", "account"
        )
        self.assertEqual(payload["groups"][0]["account"], ACCOUNT_UUID)


# --------------------------------------------------------------------------- #
# UT-GRP-03 — errors of ``--group-by`` and ``--limit``
# --------------------------------------------------------------------------- #


class GroupByErrorTests(_HomeCase):
    """UT-GRP-03: ``--group-by`` and ``--limit`` errors before the home exists."""

    def run_error(self, *argv: str) -> dict:
        code, payload, stderr = self.run_cli(*argv)
        self.assertEqual(code, 2, f"{argv}: {payload} {stderr}")
        assert payload is not None
        self.assertIs(payload.get("ok"), False)
        self.assertEqual(payload["error"]["code"], "E_USAGE")
        return payload

    def test_ut_grp_03_01_key_errors_are_literal(self) -> None:
        """UT-GRP-03.01: three keys, a repeated key and an unknown key are ``E_USAGE``."""
        cases = {
            "from,domain,month": "--group-by accepts at most two keys",
            "from,from": "duplicate key 'from' in --group-by",
            "sender": "unknown key 'sender' in --group-by",
        }
        for value, message in cases.items():
            with self.subTest(value=value):
                payload = self.run_error("search", "--group-by", value)
                self.assertEqual(payload["error"]["message"], message)
                self.assertEqual(
                    payload["error"]["hint"],
                    f"valid keys: {GROUP_KEYS_TEXT}; at most two",
                )

    def test_ut_grp_03_02_limit_out_of_range_with_group_by(self) -> None:
        """UT-GRP-03.02: ``--limit 51`` and ``--limit -1`` with ``--group-by`` are ``E_USAGE``."""
        for value in (51, -1):
            with self.subTest(value=value):
                payload = self.run_error(
                    "search", "--group-by", "from", "--limit", str(value)
                )
                self.assertEqual(
                    payload["error"]["message"],
                    f"invalid --limit {value} with --group-by: expected 0 to 50",
                )
                self.assertEqual(
                    payload["error"]["hint"],
                    "use --limit between 0 and 50 messages per group",
                )

    def test_ut_grp_03_03_error_happens_before_the_home_and_the_store(self) -> None:
        """UT-GRP-03.03: the errors happen before creating the home and opening the store."""
        unused_home = self.root / "unused-home"
        with (
            mock.patch.object(
                cli_mod, "ensure_app_home", side_effect=AssertionError("home")
            ),
            mock.patch(
                "mailquery.store.open_store", side_effect=AssertionError("store")
            ),
        ):
            stdout, stderr = io.StringIO(), io.StringIO()
            with (
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                code = cli_mod.main(
                    ["search", "--group-by", "sender"], home=unused_home
                )
        self.assertEqual(code, 2, stderr.getvalue())
        self.assertFalse(unused_home.exists())
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["error"]["code"], "E_USAGE")


class GroupByValidLimitTests(_AppleCase):
    """UT-GRP-03: valid ``--limit`` values and the key list format."""

    def test_ut_grp_03_04_limit_fifty_is_valid(self) -> None:
        """UT-GRP-03.04: ``--limit 50`` with ``--group-by`` is valid."""
        payload = self.run_ok("search", "--group-by", "from", "--limit", "50")
        self.assertTrue(payload["groups"])
        for group in payload["groups"]:
            self.assertLessEqual(len(group["messages"]), GROUP_MAX_LIMIT)

    def test_ut_grp_03_05_key_list_format(self) -> None:
        """UT-GRP-03.05: empty keys are unknown, names are case-sensitive and spaces are ignored."""
        for value, key in (("", ""), ("from,", ""), ("FROM", "FROM")):
            with self.subTest(value=value):
                payload = self.run_error(
                    "search", "--group-by", value, exit_code=2, code="E_USAGE"
                )
                self.assertEqual(
                    payload["error"]["message"],
                    f"unknown key '{key}' in --group-by",
                )
        spaced = self.run_ok("search", "--group-by", "from, month")
        plain = self.run_ok("search", "--group-by", "from,month")
        self.assertEqual(spaced["groups"], plain["groups"])


# --------------------------------------------------------------------------- #
# UT-GRP-04 — more than 50 groups
# --------------------------------------------------------------------------- #


class GroupTruncationTests(_PluginCase):
    """UT-GRP-04: at most 50 groups, with the truncated warning and hint."""

    def _senders(self, count: int) -> list[dict]:
        return [
            _row(
                f"row-{index:02d}",
                sender=("Sender", f"sender{index:02d}@example.com"),
                received=_ago(index),
            )
            for index in range(count)
        ]

    def test_ut_grp_04_01_more_than_fifty_groups_truncate(self) -> None:
        """UT-GRP-04.01: 53 senders give 50 groups, the truncated warning and the total count."""
        payload = self.run_plugin(
            self.plugin(self._senders(53)), "--group-by", "from"
        )
        self.assertEqual(len(payload["groups"]), GROUP_MAX_GROUPS)
        self.assertIs(payload["truncated"], True)
        self.assertEqual(payload["hint"], "3 more group(s); refine the filters")
        self.assertEqual(
            payload["warnings"],
            ["W_RESULTS_TRUNCATED: 3 more group(s); refine the filters"],
        )
        self.assertEqual(payload["count"], 53)

    def test_ut_grp_04_02_exactly_fifty_groups_are_not_truncated(self) -> None:
        """UT-GRP-04.02: 50 senders give 50 groups without the warning."""
        payload = self.run_plugin(
            self.plugin(self._senders(50)), "--group-by", "from"
        )
        self.assertEqual(len(payload["groups"]), 50)
        self.assertIs(payload["truncated"], False)
        self.assertEqual(payload["warnings"], [])

    def test_ut_grp_04_03_fifty_one_groups_report_one_more(self) -> None:
        """UT-GRP-04.03: 51 senders report ``1 more group(s)``."""
        payload = self.run_plugin(
            self.plugin(self._senders(51)), "--group-by", "from"
        )
        self.assertEqual(len(payload["groups"]), 50)
        self.assertIs(payload["truncated"], True)
        self.assertEqual(payload["hint"], "1 more group(s); refine the filters")


# --------------------------------------------------------------------------- #
# UT-GRP-05 — ``--count``
# --------------------------------------------------------------------------- #


class CountTests(_AppleCase):
    """UT-GRP-05: the count-only response and its errors."""

    def test_ut_grp_05_01_response_shape_and_order(self) -> None:
        """UT-GRP-05.01: ``--count`` returns exactly its eight keys, in order, with ``hint: null``."""
        payload = self.run_ok("search", "--count")
        self.assertEqual(
            list(payload),
            [
                "ok",
                "command",
                "generated_at",
                "content_notice",
                "count",
                "hint",
                "warnings",
                "scan",
            ],
        )
        self.assertEqual(payload["count"], 12)
        self.assertIsNone(payload["hint"])

    def test_ut_grp_05_03_zero_results_keep_the_scope_hint(self) -> None:
        """UT-GRP-05.03: zero results give ``count: 0``, the scope hint and exit 0."""
        payload = self.run_ok("search", "--subject", "zzz-nothing", "--count")
        self.assertEqual(payload["count"], 0)
        self.assertEqual(payload["hint"], _no_results(4, 3))

    def test_ut_grp_05_04_count_combination_errors_are_literal(self) -> None:
        """UT-GRP-05.04: ``--count`` with ``--fields``, ``--group-by`` or ``--limit`` is ``E_USAGE``."""
        for extra in (
            ("--fields", "snippet"),
            ("--group-by", "from"),
            ("--limit", "5"),
        ):
            with self.subTest(extra=extra):
                payload = self.run_error(
                    "search", "--count", *extra, exit_code=2, code="E_USAGE"
                )
                self.assertEqual(
                    payload["error"]["message"],
                    "--count cannot be combined with --fields, --group-by or --limit",
                )
                self.assertEqual(
                    payload["error"]["hint"],
                    "use --count alone, or drop it to list the messages",
                )

    def test_ut_grp_05_05_count_with_text_keeps_the_scan_limits(self) -> None:
        """UT-GRP-05.05: ``--count --text`` without narrowing is ``E_UNBOUNDED_SCAN``."""
        self.configure(TWO_ACCOUNT_CONFIG)
        payload = self.run_error(
            "search",
            "--count",
            "--text",
            "invoice",
            exit_code=4,
            code="E_UNBOUNDED_SCAN",
        )
        self.assertIn("--text", payload["error"]["message"])


class CountPluginTests(_PluginCase):
    """UT-GRP-05: counting many messages and the scan budget."""

    def test_ut_grp_05_02_count_has_no_limit_and_dedupes(self) -> None:
        """UT-GRP-05.02: 250 messages after deduplication, above the 200 limit."""
        rows = [
            _row(f"row-{index:03d}", received=_ago(index)) for index in range(249)
        ]
        rows += [
            _row("dup-a", received=_ago(300), global_message_id=900),
            _row("dup-b", received=_ago(301), global_message_id=900),
        ]
        payload = self.run_plugin(self.plugin(rows), "--count")
        self.assertEqual(payload["count"], 250)
        self.assertGreater(payload["count"], 200)

    def test_ut_grp_05_05_count_over_max_scan_is_scan_too_large(self) -> None:
        """UT-GRP-05.05: ``--count --text`` above ``[search].max_scan`` is ``E_SCAN_TOO_LARGE``."""
        write_config(self.home, "[search]\nmax_scan = 100\n\n" + PLUGIN_CONFIG)
        rows = [_row(f"row-{index:03d}", received=_ago(index)) for index in range(250)]
        code, payload, stderr = _plugin_cli(
            self.home,
            ["search", "--count", "--text", "x", "--since", "2020-01-01"],
            self.plugin(rows),
        )
        self.assertEqual(code, 4, f"{payload} {stderr}")
        assert payload is not None
        self.assertEqual(payload["error"]["code"], "E_SCAN_TOO_LARGE")


# --------------------------------------------------------------------------- #
# UT-GRP-06 — ``new`` without grouping or counting
# --------------------------------------------------------------------------- #


class NewRejectionTests(_HomeCase):
    """UT-GRP-06: ``new`` rejects both options and leaves ``state.json`` alone."""

    def test_ut_grp_06_01_new_rejects_group_by_and_count(self) -> None:
        """UT-GRP-06.01: ``new --group-by`` and ``new --count`` are ``E_USAGE`` without touching the state."""
        for argv in (("new", "--group-by", "from"), ("new", "--count")):
            with self.subTest(argv=argv):
                code, payload, stderr = self.run_cli(*argv)
                self.assertEqual(code, 2, f"{payload} {stderr}")
                assert payload is not None
                self.assertIs(payload.get("ok"), False)
                self.assertEqual(payload["error"]["code"], "E_USAGE")
                self.assertFalse((self.home / "state.json").exists())

        state = self.home / "state.json"
        state.write_text('{"schema": 2}', encoding="utf-8")
        code, payload, _stderr = self.run_cli("new", "--count")
        self.assertEqual(code, 2)
        assert payload is not None
        self.assertEqual(payload["error"]["code"], "E_USAGE")
        self.assertEqual(state.read_text(encoding="utf-8"), '{"schema": 2}')


# --------------------------------------------------------------------------- #
# UT-GRP-07 — reads
# --------------------------------------------------------------------------- #


class GroupReadTests(_AppleCase):
    """UT-GRP-07: grouping reads no bodies and only the emitted headers."""

    def test_ut_grp_07_01_group_by_reads_no_bodies(self) -> None:
        """UT-GRP-07.01: without ``--text`` no body is extracted; only emitted rows read headers."""
        with mock.patch.object(
            emlx, "_extract_body_text", wraps=emlx._extract_body_text
        ) as spy:
            payload = self.run_ok("search", "--group-by", "from", "--limit", "1")
        self.assertEqual(spy.call_count, 0)
        self.assertEqual(payload["count"], 12)
        self.assertEqual(len(payload["groups"]), 12)
        plain = self.run_ok("search")
        self.assertGreater(payload["scan"]["messages_read"], 0)
        self.assertEqual(
            payload["scan"]["messages_read"], plain["scan"]["messages_read"]
        )

        with mock.patch.object(
            emlx, "_extract_body_text", wraps=emlx._extract_body_text
        ) as spy:
            empty = self.run_ok("search", "--group-by", "account", "--limit", "0")
        self.assertEqual(spy.call_count, 0)
        self.assertTrue(empty["groups"])
        self.assertEqual(empty["scan"]["messages_read"], 0)

    def test_ut_grp_07_03_text_filters_before_grouping(self) -> None:
        """UT-GRP-07.03: ``--text`` reads the body and the groups keep only matching messages."""
        with mock.patch.object(
            emlx, "_extract_body_text", wraps=emlx._extract_body_text
        ) as spy:
            payload = self.run_ok(
                "search",
                "--text",
                "invoice",
                "--since",
                "1y",
                "--group-by",
                "from",
            )
        self.assertGreater(spy.call_count, 0)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(len(payload["groups"]), 1)
        group = payload["groups"][0]
        self.assertEqual(group["from"], "billing@fixture.example")
        self.assertEqual(len(group["messages"]), 1)
        self.assertNotIn("snippet", group["messages"][0])


class CountReadTests(_AppleCase):
    """UT-GRP-07: ``--count`` reads neither bodies nor headers."""

    def test_ut_grp_07_02_count_reads_no_bodies_or_headers(self) -> None:
        """UT-GRP-07.02: ``--count`` reads nothing; the Outlook double opens no item."""
        with mock.patch.object(
            emlx, "_extract_body_text", side_effect=AssertionError("body")
        ):
            payload = self.run_ok("search", "--count")
        self.assertEqual(payload["count"], 12)
        self.assertEqual(payload["scan"]["messages_read"], 0)

        fake = fk.FakeOutlook.item_matrix(
            datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
        )
        backend = self.outlook_backend(fake)
        write_config(self.home, '[scope."ana@example.com"]\n')
        payload = search.run_search(
            backend, load_config(self.home), search.Filters(), count=True
        )
        self.assertGreater(payload["count"], 0)
        self.assertEqual(payload["scan"]["messages_read"], 0)
        self.assertEqual(backend.items_opened, 0)
        for member in ("Body", "HTMLBody", "BodyFormat"):
            self.assertEqual(
                fake.call_log.count(kind="Item", member=member), 0, member
            )


# --------------------------------------------------------------------------- #
# UT-GRP-08 — the no-results hint
# --------------------------------------------------------------------------- #


class NoResultsHintTests(_AppleCase):
    """UT-GRP-08: the scope hint of a ``search`` without results."""

    def test_ut_grp_08_01_apple_mail_counts_folders_and_accounts(self) -> None:
        """UT-GRP-08.01: two accounts with only INBOX give ``2 folder(s) of 2 account(s)``."""
        self.configure(TWO_ACCOUNT_CONFIG)
        payload = self.run_ok("search", "--subject", "zzz-nothing")
        self.assertEqual(payload["count"], 0)
        self.assertEqual(payload["hint"], _no_results(2, 2))

    def test_ut_grp_08_01_outlook_counts_folders_and_accounts(self) -> None:
        """UT-GRP-08.01: the Outlook double gives the same hint for two accounts."""
        fake = fk.FakeOutlook()
        fake.add_exchange_account("exchange", "ana@example.com")
        fake.add_imap_account("imap", "bea@example.com")
        backend = self.outlook_backend(fake)
        write_config(
            self.home, '[scope."ana@example.com"]\n[scope."bea@example.com"]\n'
        )
        payload = search.run_search(
            backend, load_config(self.home), search.Filters()
        )
        self.assertEqual(payload["count"], 0)
        self.assertEqual(payload["hint"], _no_results(2, 2))

    def test_ut_grp_08_02_counts_inbox_mailbox_list_and_include(self) -> None:
        """UT-GRP-08.02: INBOX, ``mailbox_list`` and ``--include-mailbox`` count; also grouped and counted."""
        self.configure(f'[scope."{ICLOUD_LABEL}"]\nmailbox_list = ["Facturas"]\n')
        expected = _no_results(3, 1)
        for extra in ((), ("--group-by", "from"), ("--count",)):
            with self.subTest(extra=extra):
                payload = self.run_ok(
                    "search",
                    "--subject",
                    "zzz-nothing",
                    "--include-mailbox",
                    "Archivo",
                    *extra,
                )
                self.assertEqual(payload["count"], 0)
                self.assertEqual(payload["hint"], expected)

        # A declared account without any folder is still a read account, with 0 folders.
        backend = self.outlook_backend(fk.FakeOutlook.store_matrix())
        write_config(self.home, '[scope."PST (Notas)"]\n')
        payload = search.run_search(
            backend, load_config(self.home), search.Filters(subject=("zzz",))
        )
        self.assertEqual(payload["hint"], _no_results(0, 1))

    def test_ut_grp_08_03_excluded_store_is_not_counted(self) -> None:
        """UT-GRP-08.03: a declared excluded store is not counted in accounts or folders."""
        fake = fk.FakeOutlook.default()
        backend = self.outlook_backend(fake)
        write_config(
            self.home,
            '[scope."Exchange (ana.perez@example.com)"]\n'
            '[scope."Exchange shared (Soporte)"]\n',
        )
        payload = search.run_search(
            backend, load_config(self.home), search.Filters(subject=("zzz",))
        )
        self.assertEqual(payload["count"], 0)
        self.assertEqual(payload["hint"], _no_results(1, 1))
        self.assertIn("W_STORE_EXCLUDED", " ".join(payload["warnings"]))

    def test_ut_grp_08_04_no_accounts_read_has_no_hint(self) -> None:
        """UT-GRP-08.04: with no account read the hint is ``null`` and ``W_NO_ACCOUNTS`` appears."""
        self.configure("")
        payload = self.run_ok("search", "--subject", "zzz-nothing")
        self.assertEqual(payload["count"], 0)
        self.assertIsNone(payload["hint"])
        self.assertIn("W_NO_ACCOUNTS", " ".join(payload["warnings"]))

        fake = fk.FakeOutlook.default()
        backend = self.outlook_backend(fake)
        write_config(self.home, '[scope."Exchange shared (Soporte)"]\n')
        payload = search.run_search(
            backend, load_config(self.home), search.Filters()
        )
        self.assertIsNone(payload["hint"])
        self.assertIn("W_NO_ACCOUNTS", " ".join(payload["warnings"]))

    def test_ut_grp_08_05_results_keep_the_hint_null_and_new_is_unchanged(self) -> None:
        """UT-GRP-08.05: with results ``hint`` stays ``null``; ``new`` without mail is ``null`` too."""
        payload = self.run_ok("search", "--since", "1mo")
        self.assertTrue(payload["messages"])
        self.assertIsNone(payload["hint"])
        self.run_ok("new")
        empty = self.run_ok("new")
        self.assertEqual(empty["count"], 0)
        self.assertIsNone(empty["hint"])

    def test_ut_grp_08_07_each_folder_counts_once_per_account(self) -> None:
        """UT-GRP-08.07: INBOX and a folder repeated in ``mailbox_list``/``--include-mailbox`` count once."""
        self.configure(
            f'[scope."{ICLOUD_LABEL}"]\nmailbox_list = ["INBOX", "Facturas"]\n'
        )
        payload = self.run_ok(
            "search", "--subject", "zzz-nothing", "--include-mailbox", "Facturas"
        )
        self.assertEqual(payload["hint"], _no_results(2, 1))


class NoResultsHintPluginTests(_PluginCase):
    """UT-GRP-08: the hint over the plugin double."""

    def _two_accounts(self) -> None:
        self.accounts = [
            {"uuid": "graph-a", "label": "Graph A", "email": None, "local": False},
            {"uuid": "graph-b", "label": "Graph B", "email": None, "local": False},
        ]
        self.mailboxes = [
            {
                "id": "a-inbox",
                "account_uuid": "graph-a",
                "name": "INBOX",
                "path": "INBOX",
                "url": "graph://graph-a/INBOX",
                "is_inbox": True,
                "is_aggregate": False,
                "total": 0,
                "unread": 0,
            },
            {
                "id": "b-inbox",
                "account_uuid": "graph-b",
                "name": "INBOX",
                "path": "INBOX",
                "url": "graph://graph-b/INBOX",
                "is_inbox": True,
                "is_aggregate": False,
                "total": 0,
                "unread": 0,
            },
        ]
        write_config(
            self.home, '[scope."graph:Graph A"]\n[scope."graph:Graph B"]\n'
        )

    def test_ut_grp_08_01_plugin_counts_folders_and_accounts(self) -> None:
        """UT-GRP-08.01: a plugin with two accounts gives the same hint."""
        self._two_accounts()
        payload = self.run_plugin(self.plugin(), "--subject", "zzz-nothing")
        self.assertEqual(payload["count"], 0)
        self.assertEqual(payload["hint"], _no_results(2, 2))

    def test_ut_grp_08_06_hint_has_no_names_and_adds_no_driver_calls(self) -> None:
        """UT-GRP-08.06: the hint has no names and computing it adds no plugin call."""
        plain_plugin = self.plugin()
        plain = self.run_plugin(plain_plugin, "--subject", "zzz-nothing")
        counted_plugin = self.plugin()
        counted = self.run_plugin(counted_plugin, "--subject", "zzz-nothing", "--count")
        self.assertEqual(plain["hint"], counted["hint"])
        self.assertEqual(plain_plugin.calls, counted_plugin.calls)
        for name in ("INBOX", ACCOUNT_LABEL, "graph", "example.com"):
            self.assertNotIn(name, plain["hint"])


class NoResultsHintOutlookTests(_AppleCase):
    """UT-GRP-08: the hint over the Outlook double."""

    def test_ut_grp_08_06_hint_adds_no_com_call(self) -> None:
        """UT-GRP-08.06: a plain search and a counted one make the same COM calls."""
        fake = fk.FakeOutlook.default()
        write_config(self.home, '[scope."ana.perez@example.com"]\n')
        config = load_config(self.home)
        plain_backend = self.outlook_backend(fake)
        fake.call_log.clear()
        plain = search.run_search(
            plain_backend, config, search.Filters(subject=("zzz",))
        )
        plain_calls = [
            (entry.kind, entry.member, entry.action) for entry in fake.call_log
        ]
        counted_backend = self.outlook_backend(fake)
        fake.call_log.clear()
        counted = search.run_search(
            counted_backend, config, search.Filters(subject=("zzz",)), count=True
        )
        counted_calls = [
            (entry.kind, entry.member, entry.action) for entry in fake.call_log
        ]
        self.assertEqual(plain["hint"], counted["hint"])
        self.assertEqual(plain_calls, counted_calls)


# --------------------------------------------------------------------------- #
# UT-GRP-09 — warnings with ``--count`` and ``--group-by``
# --------------------------------------------------------------------------- #


class GroupWarningTests(_AppleCase):
    """UT-GRP-09: only scope warnings with ``--count``; delivered-field warnings in groups."""

    body_samples = True

    def test_ut_grp_09_01_count_keeps_only_scope_warnings(self) -> None:
        """UT-GRP-09.01: ``--count`` emits no content or sender warning."""
        payload = self.run_ok("search", "--subject", "Sender headers", "--count")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["warnings"], [])

    def test_ut_grp_09_02_group_by_keeps_sender_warnings_and_delivered_body_warnings(
        self,
    ) -> None:
        """UT-GRP-09.02: sender warnings always; the body URLs only with ``--fields snippet``."""
        grouped = self.run_ok(
            "search", "--subject", "Sender headers", "--group-by", "from"
        )
        codes = _warning_codes(grouped["warnings"])
        self.assertIn("W_SENDER_AUTH_FAILED", codes)
        self.assertIn("W_REPLY_TO_MISMATCH", codes)
        self.assertNotIn("W_EXTERNAL_LINKS", codes)

        full = self.run_ok(
            "search",
            "--subject",
            "Sender headers",
            "--group-by",
            "from",
            "--fields",
            "snippet",
        )
        codes = _warning_codes(full["warnings"])
        self.assertIn("W_SENDER_AUTH_FAILED", codes)
        self.assertIn("W_EXTERNAL_LINKS", codes)
        self.assertEqual(
            full["groups"][0]["messages"][0]["uid"],
            prefixed_uid(UID_BODY_SENDER_HEADERS),
        )


class GroupWarningPluginTests(_PluginCase):
    """UT-GRP-09: the plugin double adds no content warning with ``--count``."""

    def test_ut_grp_09_01_count_keeps_only_scope_warnings(self) -> None:
        """UT-GRP-09.01: a plugin message with URLs and failed authentication counts without warnings."""
        plugin = self.plugin(
            [
                _row(
                    "one",
                    subject="Pago https://evil.example/pay",
                    headers={
                        "Authentication-Results": "mx; spf=softfail dkim=none dmarc=fail",
                        "Reply-To": "otro@other.example",
                    },
                )
            ]
        )
        payload = self.run_plugin(plugin, "--count")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["warnings"], [])


# --------------------------------------------------------------------------- #
# UT-GRP-10 — ``content_notice`` with any option
# --------------------------------------------------------------------------- #


class ContentNoticeTests(_AppleCase):
    """UT-GRP-10: the fixed notice follows ``generated_at`` with both options."""

    def test_ut_grp_10_01_content_notice_after_generated_at(self) -> None:
        """UT-GRP-10.01: ``search --count`` and ``search --group-by`` carry ``content_notice``."""
        for argv in (("search", "--count"), ("search", "--group-by", "from")):
            with self.subTest(argv=argv):
                payload = self.run_ok(*argv)
                self.assertEqual(
                    list(payload)[:4],
                    ["ok", "command", "generated_at", "content_notice"],
                )
                self.assertEqual(payload["content_notice"], output.CONTENT_NOTICE)


# --------------------------------------------------------------------------- #
# DOC-11 — documentation of ``--group-by`` and ``--count``
# --------------------------------------------------------------------------- #


class DocumentationTests(_HomeCase):
    """DOC-11: help, READMEs and skill describe grouping and counting."""

    def test_doc_11_01_search_help_describes_both_options(self) -> None:
        """DOC-11.01: ``search --help`` describes ``--group-by`` with its keys and ``--count``."""
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            code = cli_mod.main(["search", "--help"])
        text = " ".join(stdout.getvalue().split())
        self.assertEqual(code, 0, stderr.getvalue())
        self.assertIn("--group-by", text)
        self.assertIn("--count", text)
        for key in GROUP_KEYS:
            self.assertIn(key, text)
        self.assertIn("at most 50 groups", text)

    def test_doc_11_02_readmes_document_both_options(self) -> None:
        """DOC-11.02: both READMEs document ``--group-by``, ``--count`` and the no-results hint."""
        english = (_ROOT / "README.md").read_text(encoding="utf-8")
        spanish = (_ROOT / "README.es.md").read_text(encoding="utf-8")
        for text in (english, spanish):
            self.assertIn("--group-by", text)
            self.assertIn("--count", text)
            self.assertIn("domain,month", text)
            self.assertIn("no messages matched in", text)
            self.assertIn("--include-mailbox", text)

    def test_doc_11_03_skill_explains_both_options(self) -> None:
        """DOC-11.03: the skill explains both options and that ``new`` does not accept them."""
        skill = (_ROOT / "skills" / "mailquery" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("--group-by", skill)
        self.assertIn("--count", skill)
        self.assertIn("does not accept", skill)
        self.assertIn("new", skill)


if __name__ == "__main__":  # pragma: no cover - manual runs
    unittest.main()

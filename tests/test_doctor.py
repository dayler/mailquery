"""``doctor --failures``, the ``plugins`` section and diagnosis without preflight.

Covers the TEST-CATALOG groups UT-DR-01 (``--failures`` with every check
passing), UT-DR-02 (``--failures`` with a failing check), UT-DR-03
(``--failures`` in the text report), UT-DR-04 (``doctor`` without
``--failures``), UT-DR-05 (the ``plugins`` section), UT-DR-06 (a plugin that
does not pass ``driver`` or cannot be opened), UT-DR-07 (an invalid or hung
``doctor_checks()``), UT-DR-08 (``Plugins:`` and ``Result:``), UT-DR-09
(``--failures`` with plugins) and DOC-12 (diagnosis instead of preflight).

The stores are the synthetic Apple Mail fixture and the in-memory Outlook
double; plugins are the plugin double. Every run uses a temporary home: the
real ``~/Library/Mail`` and ``~/.mailquery`` are never read.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

from mailquery import cli as cli_mod
from mailquery.backends import get_backend
from mailquery.backends.apple_mail import AppleMailBackend
from mailquery.plugins import PluginError, Reason
from tests.fakes import outlook as fk
from tests.fakes.plugin import (
    ACCOUNT_LABEL as PLUGIN_ACCOUNT_LABEL,
    ACCOUNT_UUID as PLUGIN_ACCOUNT_UUID,
    CAPABILITIES as PLUGIN_CAPABILITIES,
    DEFAULT_MAILBOXES as PLUGIN_MAILBOXES,
    DRIVER as PLUGIN_DRIVER,
    FakeEntryPoint,
    FakePluginBackend,
    internal_entry_points,
    plugin_class,
)
from tests.fixtures.make_fixtures import (
    DEFAULT_CONFIG,
    build_store,
    write_config,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SKILL_FILE = _REPO_ROOT / "skills" / "mailquery" / "SKILL.md"
_README_EN = _REPO_ROOT / "README.md"
_README_ES = _REPO_ROOT / "README.es.md"
_ARCHIVE_MAILBOX = {
    "id": "graph-archive",
    "account_uuid": PLUGIN_ACCOUNT_UUID,
    "name": "Archive",
    "path": "Archive",
    "url": "graph://graph-account/Archive",
    "is_inbox": False,
    "is_aggregate": False,
    "total": 0,
    "unread": 0,
}
_PLUGIN_KEY = f"{PLUGIN_DRIVER}:{PLUGIN_ACCOUNT_LABEL}"
_PLUGIN_CONFIG = f'[scope."{_PLUGIN_KEY}"]\nmailbox_list = ["Archive"]\n'


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _without_generated(payload: dict) -> dict:
    return {key: value for key, value in payload.items() if key != "generated_at"}


def _plugin_entries(driver: str = PLUGIN_DRIVER) -> dict[str, object]:
    """Metadata of a stand-in plugin entry point (used by plain function targets)."""
    return {
        "driver": driver,
        "plugin_api": 1,
        "capabilities": dict(PLUGIN_CAPABILITIES),
        "native_order": "text",
    }


def _configured_plugin(**kwargs) -> FakePluginBackend:
    """Plugin double with the fixture account plus an ``Archive`` folder."""
    kwargs.setdefault(
        "mailboxes", [*PLUGIN_MAILBOXES, dict(_ARCHIVE_MAILBOX)]
    )
    return FakePluginBackend(**kwargs)


def _plugin_with_checks(checks, **attributes) -> FakePluginBackend:
    """Plugin double whose ``doctor_checks()`` returns ``checks``."""
    plugin = _configured_plugin(**attributes)
    plugin.doctor_checks = lambda: [dict(check) for check in checks]
    return plugin


def _factory(driver: str, *, raises: BaseException | None = None):
    """Entry-point target with metadata that builds (or fails to build) a double."""

    def target(context=None):
        if raises is not None:
            raise raises
        return FakePluginBackend(context)

    for name, value in _plugin_entries(driver).items():
        setattr(target, name, value)
    return target


class _DoctorCase(unittest.TestCase):
    """In-process ``cli.main`` over the synthetic Apple Mail store."""

    def setUp(self) -> None:
        self.fx = build_store()
        self.addCleanup(self.fx.cleanup)
        self.addCleanup(cli_mod._close_logging_handlers)
        self.home = self.fx.home
        write_config(self.home, DEFAULT_CONFIG)

    def run_cli(
        self,
        *argv: str,
        backend: object | None = None,
        home: Path | None = None,
        mail_root: Path | None = None,
        accounts_db: Path | None = None,
        registry: object | None = None,
    ):
        out, err = io.StringIO(), io.StringIO()
        patcher = (
            mock.patch.object(cli_mod, "BackendRegistry", lambda *a, **k: registry)
            if registry is not None
            else contextlib.nullcontext()
        )
        with patcher, contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli_mod.main(
                list(argv),
                home=self.home if home is None else home,
                mail_root=self.fx.mail_root if mail_root is None else mail_root,
                accounts_db=(
                    self.fx.accounts_db if accounts_db is None else accounts_db
                ),
                backend=backend,
            )
        raw = out.getvalue()
        return code, raw, err.getvalue()

    def run_json(self, *argv: str, **kwargs) -> tuple[int, dict]:
        code, raw, err = self.run_cli(*argv, **kwargs)
        self.assertEqual(err, "")
        self.assertTrue(raw.strip(), "doctor --json printed nothing")
        return code, json.loads(raw)

    def run_doctor_json(self, *extra: str, **kwargs) -> dict:
        code, payload = self.run_json("doctor", "--json", *extra, **kwargs)
        self.assertEqual(code, 0, payload)
        self.assertIs(payload["ok"], True)
        return payload

    def run_text(self, *extra: str, **kwargs) -> str:
        code, raw, err = self.run_cli("doctor", *extra, **kwargs)
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertFalse(raw.lstrip().startswith("{"), "default doctor output must be text")
        return raw

    @staticmethod
    def by_name(payload: dict) -> dict[str, dict]:
        return {check["name"]: check for check in payload["checks"]}

    @staticmethod
    def plugin_registry(*entries) -> object:
        return cli_mod.BackendRegistry(
            platform=sys.platform,
            entry_points=[*internal_entry_points(), *entries],
        )

    def plugin_entry(self, plugin: object, driver: str = PLUGIN_DRIVER) -> FakeEntryPoint:
        return FakeEntryPoint(driver, plugin=plugin)

    def apple_backend(self) -> AppleMailBackend:
        backend = AppleMailBackend(
            mail_root=self.fx.mail_root,
            accounts_db=self.fx.accounts_db,
            tmp_root=self.home / "tmp",
        )
        self.addCleanup(backend.close)
        return backend

    def outlook_backend(self, fake: fk.FakeOutlook) -> object:
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


# --------------------------------------------------------------------------- #
# UT-DR-01 — --failures with every check passing
# --------------------------------------------------------------------------- #


class FailuresAllPassTests(_DoctorCase):
    """UT-DR-01: the empty failures payload of a healthy installation."""

    def test_ut_dr_01_01_all_checks_pass(self) -> None:
        """UT-DR-01.01: exact empty payload, key order and exit 0."""
        code, payload = self.run_json("doctor", "--json", "--failures")
        self.assertEqual(code, 0)
        self.assertEqual(
            list(payload),
            [
                "ok",
                "command",
                "generated_at",
                "checks",
                "not_evaluated",
                "plugins",
                "warnings",
            ],
        )
        self.assertIs(payload["ok"], True)
        self.assertEqual(payload["command"], "doctor")
        self.assertIsInstance(payload["generated_at"], str)
        self.assertEqual(payload["checks"], [])
        self.assertEqual(payload["not_evaluated"], [])
        self.assertEqual(payload["plugins"], [])
        self.assertEqual(payload["warnings"], [])


# --------------------------------------------------------------------------- #
# UT-DR-02 — --failures with a failing check
# --------------------------------------------------------------------------- #


class FailuresWithFailureTests(_DoctorCase):
    """UT-DR-02: only the failing checks, plus the names that were not evaluated."""

    def test_ut_dr_02_01_broken_store_filters_checks_and_lists_dependants(self) -> None:
        """UT-DR-02.01: a failing store leaves only ``store`` and the four dependants."""
        payload = self.run_doctor_json(
            "--failures", mail_root=self.fx.root / "missing-mail"
        )
        self.assertEqual([check["name"] for check in payload["checks"]], ["store"])
        self.assertIn("E_STORE_NOT_FOUND", payload["checks"][0]["detail"])
        self.assertEqual(
            payload["not_evaluated"],
            ["envelope_index", "schema", "readonly_strategy", "config"],
        )

    def test_ut_dr_02_02_outlook_closed_lists_only_outlook(self) -> None:
        """UT-DR-02.02: Outlook closed ⇒ ``outlook`` and its three dependants."""
        write_config(self.home, '[scope."ana.perez@example.com"]\n')
        payload = self.run_doctor_json(
            "--failures", backend=self.outlook_backend(fk.SCENARIOS["not_running"]())
        )
        self.assertEqual([check["name"] for check in payload["checks"]], ["outlook"])
        self.assertIn("E_OUTLOOK_NOT_RUNNING", payload["checks"][0]["detail"])
        self.assertEqual(
            payload["not_evaluated"], ["stores", "readonly_strategy", "config"]
        )

    def test_ut_dr_02_03_concrete_not_evaluated_cause_stays_in_checks(self) -> None:
        """UT-DR-02.03: ``not evaluated: <cause>`` that is not ``<check> failed`` is a failure."""
        backend = self.apple_backend()

        def custom_checks() -> list[dict]:
            return [
                {
                    "name": "store",
                    "ok": False,
                    "detail": "not evaluated: TCC denied",
                }
            ]

        backend.doctor_checks = custom_checks
        payload = self.run_doctor_json("--failures", backend=backend)
        self.assertEqual([check["name"] for check in payload["checks"]], ["store"])
        self.assertEqual(payload["checks"][0]["detail"], "not evaluated: TCC denied")
        self.assertEqual(payload["not_evaluated"], ["config"])

    def test_ut_dr_02_04_exit_zero_and_ok_true_in_every_case(self) -> None:
        """UT-DR-02.04: a failing check never changes the exit code nor ``ok``."""
        cases = {
            "store": {"mail_root": self.fx.root / "missing-mail"},
        }
        for label, kwargs in cases.items():
            with self.subTest(case=label):
                code, payload = self.run_json(
                    "doctor", "--json", "--failures", **kwargs
                )
                self.assertEqual(code, 0)
                self.assertIs(payload["ok"], True)
        code, payload = self.run_json(
            "doctor",
            "--json",
            "--failures",
            backend=self.outlook_backend(fk.SCENARIOS["not_running"]()),
        )
        self.assertEqual(code, 0)
        self.assertIs(payload["ok"], True)


# --------------------------------------------------------------------------- #
# UT-DR-03 — --failures in the text report
# --------------------------------------------------------------------------- #


class FailuresTextTests(_DoctorCase):
    """UT-DR-03: the filtered human report."""

    def test_ut_dr_03_01_all_passed_text(self) -> None:
        """UT-DR-03.01: title, Generated at, Checks: and ``all checks passed``."""
        text = self.run_text("--failures")
        self.assertIn("mailquery doctor - environment and read-only diagnosis", text)
        self.assertIn("Generated at: ", text)
        self.assertIn("Checks:", text)
        self.assertIn("all checks passed", text)
        self.assertNotIn("[ok]", text)
        self.assertNotIn("Plugins:", text)

    def test_ut_dr_03_02_failures_text_shows_rows_and_not_evaluated(self) -> None:
        """UT-DR-03.02: one row per failing check, the not evaluated line and no passing rows."""
        text = self.run_text(
            "--failures", mail_root=self.fx.root / "missing-mail"
        )
        flat = " ".join(text.split())
        self.assertIn("[FAIL] store", flat)
        self.assertIn("E_STORE_NOT_FOUND", flat)
        self.assertIn(
            "not evaluated: envelope_index, schema, readonly_strategy, config", flat
        )
        self.assertNotIn("[ok]", text)
        self.assertNotIn("Plugins:", text)


# --------------------------------------------------------------------------- #
# UT-DR-04 — doctor without --failures
# --------------------------------------------------------------------------- #


class WithoutFailuresTests(_DoctorCase):
    """UT-DR-04: the full report only gains ``plugins`` and the diagnosis title."""

    def test_ut_dr_04_01_full_json_and_text_keep_the_previous_contract(self) -> None:
        """UT-DR-04.01: full JSON plus ``plugins: []``; text with the new title and no Plugins:."""
        payload = self.run_doctor_json()
        self.assertEqual(
            list(payload),
            ["ok", "command", "generated_at", "checks", "plugins", "warnings"],
        )
        self.assertEqual(payload["plugins"], [])
        self.assertEqual(len(payload["checks"]), 11)
        self.assertNotIn("not_evaluated", payload)
        text = self.run_text()
        self.assertIn("mailquery doctor - environment and read-only diagnosis", text)
        self.assertNotIn("Plugins:", text)
        self.assertIn("Result: 11/11 checks passed", text)


# --------------------------------------------------------------------------- #
# UT-DR-05 — the plugins section
# --------------------------------------------------------------------------- #


class PluginSectionTests(_DoctorCase):
    """UT-DR-05: declared plugins, their checks and their own config resolution."""

    def test_ut_dr_05_01_valid_checks_then_the_plugin_config(self) -> None:
        """UT-DR-05.01: the plugin's checks stay unchanged and ``config`` resolves its blocks."""
        plugin = _plugin_with_checks(
            [
                {"name": "profile", "ok": True, "detail": "profile found"},
                {"name": "login", "ok": False, "detail": "login rejected"},
            ]
        )
        write_config(self.home, _PLUGIN_CONFIG)
        payload = self.run_doctor_json(
            registry=self.plugin_registry(self.plugin_entry(plugin))
        )
        self.assertEqual(len(payload["plugins"]), 1)
        section = payload["plugins"][0]
        self.assertEqual(list(section), ["driver", "checks"])
        self.assertEqual(section["driver"], PLUGIN_DRIVER)
        self.assertEqual(
            section["checks"],
            [
                {"name": "profile", "ok": True, "detail": "profile found"},
                {"name": "login", "ok": False, "detail": "login rejected"},
                {
                    "name": "config",
                    "ok": True,
                    "detail": (
                        f"{_PLUGIN_KEY} → {PLUGIN_ACCOUNT_LABEL} "
                        f"({PLUGIN_ACCOUNT_UUID}): INBOX, Archive"
                    ),
                },
            ],
        )

    def test_ut_dr_05_02_unresolved_block_fails_the_plugin_config(self) -> None:
        """UT-DR-05.02: an unknown account ⇒ ``<key>: <code>: <message> (hint: …)``."""
        plugin = _configured_plugin()
        key = f"{PLUGIN_DRIVER}:No Such Account"
        write_config(self.home, f'[scope."{key}"]\n')
        payload = self.run_doctor_json(
            registry=self.plugin_registry(self.plugin_entry(plugin))
        )
        config = next(
            check
            for check in payload["plugins"][0]["checks"]
            if check["name"] == "config"
        )
        self.assertFalse(config["ok"], config)
        self.assertTrue(config["detail"].startswith(f"{key}: E_CONFIG_ACCOUNT_UNKNOWN: "))
        self.assertIn("(hint: ", config["detail"])

    def test_ut_dr_05_03_native_checks_do_not_list_plugin_blocks(self) -> None:
        """UT-DR-05.03: top-level checks are unchanged except ``driver`` and ``config``."""
        base = self.by_name(self.run_doctor_json())
        write_config(self.home, _PLUGIN_CONFIG)
        payload = self.run_doctor_json(
            registry=self.plugin_registry(self.plugin_entry(_configured_plugin()))
        )
        checks = self.by_name(payload)
        for name, check in base.items():
            if name in ("driver", "config"):
                continue
            with self.subTest(check=name):
                self.assertEqual(checks[name], check)
        self.assertIn("graph (api=1;", checks["driver"]["detail"])
        self.assertEqual(
            checks["config"],
            {
                "name": "config",
                "ok": True,
                "detail": "0 account block(s) declared for driver apple_mail",
            },
        )

    def test_ut_dr_05_04_several_plugins_follow_their_first_block(self) -> None:
        """UT-DR-05.04: one section per plugin, in the order of its first block."""
        config = (
            f'[scope."beta:{PLUGIN_ACCOUNT_LABEL}"]\n'
            f'[scope."alpha:{PLUGIN_ACCOUNT_LABEL}"]\n'
        )
        write_config(self.home, config)
        registry = self.plugin_registry(
            FakeEntryPoint("alpha", plugin=plugin_class(driver="alpha")),
            FakeEntryPoint("beta", plugin=plugin_class(driver="beta")),
        )
        payload = self.run_doctor_json(registry=registry)
        self.assertEqual(
            [section["driver"] for section in payload["plugins"]],
            ["beta", "alpha"],
        )

    def test_ut_dr_05_05_close_failure_does_not_change_the_report(self) -> None:
        """UT-DR-05.05: a raising ``close()`` keeps the report and exits 0."""
        write_config(self.home, _PLUGIN_CONFIG)
        clean = _configured_plugin()
        clean_payload = self.run_doctor_json(
            registry=self.plugin_registry(self.plugin_entry(clean))
        )
        broken = _configured_plugin()

        def broken_close() -> None:
            raise RuntimeError("close failed")

        broken.close = broken_close
        payload = self.run_doctor_json(
            registry=self.plugin_registry(self.plugin_entry(broken))
        )
        self.assertEqual(_without_generated(payload), _without_generated(clean_payload))


# --------------------------------------------------------------------------- #
# UT-DR-06 — a plugin that does not pass driver or cannot be opened
# --------------------------------------------------------------------------- #


class PluginDriverFailureTests(_DoctorCase):
    """UT-DR-06: a plugin that never runs is reported as a not evaluated config."""

    def test_ut_dr_06_01_driver_failure_skips_doctor_checks(self) -> None:
        """UT-DR-06.01: incompatible plugin ⇒ only ``config`` with ``not evaluated: driver failed``."""

        def fail_if_called() -> list[dict]:
            raise AssertionError("doctor_checks must not be called")

        plugin = plugin_class(
            plugin_api=2, doctor_checks=staticmethod(fail_if_called)
        )
        write_config(self.home, _PLUGIN_CONFIG)
        payload = self.run_doctor_json(
            registry=self.plugin_registry(self.plugin_entry(plugin))
        )
        self.assertEqual(
            payload["plugins"],
            [
                {
                    "driver": PLUGIN_DRIVER,
                    "checks": [
                        {
                            "name": "config",
                            "ok": False,
                            "detail": "not evaluated: driver failed",
                        }
                    ],
                }
            ],
        )
        self.assertIn("E_PLUGIN_INCOMPATIBLE", self.by_name(payload)["driver"]["detail"])

    def test_ut_dr_06_02_open_failure_is_a_plugin_check(self) -> None:
        """UT-DR-06.02: a constructor that fails ⇒ ``plugin`` false with ``E_PLUGIN_FAILED``."""
        write_config(self.home, _PLUGIN_CONFIG)
        payload = self.run_doctor_json(
            registry=self.plugin_registry(
                FakeEntryPoint(PLUGIN_DRIVER, plugin=_factory(PLUGIN_DRIVER, raises=RuntimeError("boom")))
            )
        )
        checks = payload["plugins"][0]["checks"]
        self.assertEqual([check["name"] for check in checks], ["plugin", "config"])
        self.assertFalse(checks[0]["ok"])
        self.assertTrue(checks[0]["detail"].startswith("E_PLUGIN_FAILED: "))
        self.assertIn("failed to start", checks[0]["detail"])
        self.assertEqual(checks[1]["detail"], "not evaluated: plugin failed")
        self.assertIs(payload["ok"], True)


# --------------------------------------------------------------------------- #
# UT-DR-07 — invalid or hung doctor_checks()
# --------------------------------------------------------------------------- #


_INVALID_DOCTOR_CHECKS = {
    "not a list": {"name": "profile", "ok": True, "detail": ""},
    "item not a dict": ["profile"],
    "missing detail": [{"name": "profile", "ok": True}],
    "ok not a boolean": [{"name": "profile", "ok": "yes", "detail": ""}],
    "detail not text": [{"name": "profile", "ok": True, "detail": 1}],
    "repeated name": [
        {"name": "profile", "ok": True, "detail": ""},
        {"name": "profile", "ok": True, "detail": ""},
    ],
    "reserved config": [{"name": "config", "ok": True, "detail": ""}],
    "reserved plugin": [{"name": "plugin", "ok": True, "detail": ""}],
    "newline in detail": [{"name": "profile", "ok": True, "detail": "a\nb"}],
    "carriage return in detail": [{"name": "profile", "ok": True, "detail": "a\r"}],
}


class InvalidDoctorChecksTests(_DoctorCase):
    """UT-DR-07: exceptions, invalid returns, timeouts and failing config calls."""

    def setUp(self) -> None:
        super().setUp()
        write_config(self.home, _PLUGIN_CONFIG)

    def test_ut_dr_07_01_exception_is_a_plugin_failure(self) -> None:
        """UT-DR-07.01: a raising ``doctor_checks()`` ⇒ ``plugin`` false, then ``config``."""
        plugin = _configured_plugin(failures={"doctor_checks": RuntimeError("boom")})
        payload = self.run_doctor_json(
            registry=self.plugin_registry(self.plugin_entry(plugin))
        )
        checks = payload["plugins"][0]["checks"]
        self.assertEqual([check["name"] for check in checks], ["plugin", "config"])
        self.assertFalse(checks[0]["ok"])
        self.assertTrue(checks[0]["detail"].startswith("E_PLUGIN_FAILED: "))
        self.assertTrue(checks[1]["ok"], checks[1])
        self.assertEqual(
            cli_mod._plugin_failure_detail("graph", RuntimeError("boom")),
            "E_PLUGIN_FAILED: RuntimeError: boom",
        )

    def test_ut_dr_07_02_invalid_returns_are_plugin_failures(self) -> None:
        """UT-DR-07.02: every invalid shape ⇒ ``plugin`` false with ``E_PLUGIN_FAILED``."""
        for label, value in _INVALID_DOCTOR_CHECKS.items():
            with self.subTest(case=label):
                plugin = _configured_plugin(results={"doctor_checks": value})
                payload = self.run_doctor_json(
                    registry=self.plugin_registry(self.plugin_entry(plugin))
                )
                checks = payload["plugins"][0]["checks"]
                self.assertEqual(checks[0]["name"], "plugin", checks)
                self.assertFalse(checks[0]["ok"])
                self.assertTrue(
                    checks[0]["detail"].startswith("E_PLUGIN_FAILED: "),
                    checks[0]["detail"],
                )
                self.assertEqual(checks[-1]["name"], "config")

    def test_ut_dr_07_03_timeout_is_a_plugin_failure(self) -> None:
        """UT-DR-07.03: an unanswered ``doctor_checks()`` ⇒ the fixed 30 s timeout text."""
        plugin = _configured_plugin(delays={"doctor_checks": 0.3})
        with mock.patch("mailquery.plugins.api.METADATA_TIMEOUT_SECONDS", 0.05):
            payload = self.run_doctor_json(
                registry=self.plugin_registry(self.plugin_entry(plugin))
            )
        plugin_check = payload["plugins"][0]["checks"][0]
        self.assertEqual(plugin_check["name"], "plugin")
        self.assertFalse(plugin_check["ok"])
        self.assertEqual(
            plugin_check["detail"],
            "timeout after 30 s: plugin 'graph' did not respond",
        )
        # The rest of the report is complete and unchanged.
        self.assertEqual(len(payload["checks"]), 11)
        self.assertTrue(all(check["ok"] for check in payload["checks"]))

    def test_ut_dr_07_04_failing_account_calls_fail_the_plugin_config(self) -> None:
        """UT-DR-07.04: ``accounts()``/``resolve_mailbox()`` errors use the native config format."""
        key = _PLUGIN_KEY
        cases = {
            "accounts exception": _configured_plugin(
                failures={"accounts": RuntimeError("boom")}
            ),
            "resolve exception": _configured_plugin(
                failures={"resolve_mailbox": RuntimeError("boom")}
            ),
        }
        for label, plugin in cases.items():
            with self.subTest(case=label):
                payload = self.run_doctor_json(
                    registry=self.plugin_registry(self.plugin_entry(plugin))
                )
                config = next(
                    check
                    for check in payload["plugins"][0]["checks"]
                    if check["name"] == "config"
                )
                self.assertFalse(config["ok"], config)
                self.assertTrue(
                    config["detail"].startswith(f"{key}: E_PLUGIN_FAILED: "),
                    config["detail"],
                )
                self.assertIn("(hint: ", config["detail"])
        plugin = _configured_plugin(delays={"accounts": 0.3})
        with mock.patch("mailquery.plugins.api.METADATA_TIMEOUT_SECONDS", 0.05):
            payload = self.run_doctor_json(
                registry=self.plugin_registry(self.plugin_entry(plugin))
            )
        config = next(
            check
            for check in payload["plugins"][0]["checks"]
            if check["name"] == "config"
        )
        self.assertFalse(config["ok"], config)
        self.assertTrue(
            config["detail"].startswith(f"{key}: E_CLIENT_TIMEOUT: "), config["detail"]
        )
        self.assertIn("(hint: ", config["detail"])

        # A malformed account row is a core-level resolution failure, not a
        # mapped plugin error: the config check reports it and keeps going.
        malformed = _configured_plugin(accounts=[{"unexpected": "row"}])
        payload = self.run_doctor_json(
            registry=self.plugin_registry(self.plugin_entry(malformed))
        )
        config = next(
            check
            for check in payload["plugins"][0]["checks"]
            if check["name"] == "config"
        )
        self.assertFalse(config["ok"], config)
        self.assertTrue(config["detail"].startswith(f"{key}: KeyError: "), config["detail"])

        # A failure while building the driver wrapper is also reported by the
        # plugin config check instead of aborting the report.
        with mock.patch.object(
            cli_mod, "wrap_driver", side_effect=RuntimeError("boom")
        ):
            payload = self.run_doctor_json(
                registry=self.plugin_registry(self.plugin_entry(_configured_plugin()))
            )
        config = next(
            check
            for check in payload["plugins"][0]["checks"]
            if check["name"] == "config"
        )
        self.assertFalse(config["ok"], config)
        self.assertEqual(config["detail"], "RuntimeError: boom")


# --------------------------------------------------------------------------- #
# UT-DR-08 — text and Result:
# --------------------------------------------------------------------------- #


class PluginTextTests(_DoctorCase):
    """UT-DR-08: the Plugins: section and the Result line."""

    def _plugin(self) -> FakePluginBackend:
        return _plugin_with_checks(
            [
                {"name": "profile", "ok": True, "detail": "profile found"},
                {"name": "login", "ok": False, "detail": "login rejected"},
            ]
        )

    def test_ut_dr_08_01_text_shows_plugins_and_their_rows(self) -> None:
        """UT-DR-08.01: ``Plugins:``, the driver and its rows in the Checks: format."""
        write_config(self.home, _PLUGIN_CONFIG)
        text = self.run_text(
            registry=self.plugin_registry(self.plugin_entry(self._plugin()))
        )
        self.assertIn("Plugins:", text)
        self.assertIn(f"  {PLUGIN_DRIVER}", text)
        self.assertIn("[FAIL] login", text)
        self.assertIn("[ok]", text)
        self.assertIn("INBOX, Archive", text)
        for line in text.splitlines():
            self.assertLessEqual(len(line), 100, f"doctor line too long: {line!r}")

    def test_ut_dr_08_02_result_counts_plugin_checks(self) -> None:
        """UT-DR-08.02: ``Result:`` adds the plugin checks to the top-level ones."""
        write_config(self.home, _PLUGIN_CONFIG)
        text = self.run_text(
            registry=self.plugin_registry(self.plugin_entry(self._plugin()))
        )
        self.assertIn("Result: 13/14 checks passed (1 failed)", text)


# --------------------------------------------------------------------------- #
# UT-DR-09 — --failures with plugins
# --------------------------------------------------------------------------- #


class FailuresWithPluginsTests(_DoctorCase):
    """UT-DR-09: plugin sections are filtered like the top-level checks."""

    def test_ut_dr_09_01_only_failing_plugins_are_listed(self) -> None:
        """UT-DR-09.01: a failing plugin and a not evaluated one stay; a healthy one goes."""
        failing = plugin_class(
            driver="alpha",
            doctor_checks=lambda self: [
                {"name": "login", "ok": False, "detail": "login rejected"}
            ],
        )
        healthy = plugin_class(
            driver="beta",
            doctor_checks=lambda self: [
                {"name": "login", "ok": True, "detail": "login fine"}
            ],
        )
        unopenable = _factory("gamma", raises=RuntimeError("boom"))
        config = (
            f'[scope."alpha:{PLUGIN_ACCOUNT_LABEL}"]\n'
            f'[scope."beta:{PLUGIN_ACCOUNT_LABEL}"]\n'
            f'[scope."gamma:{PLUGIN_ACCOUNT_LABEL}"]\n'
        )
        write_config(self.home, config)
        registry = self.plugin_registry(
            FakeEntryPoint("alpha", plugin=failing),
            FakeEntryPoint("beta", plugin=healthy),
            FakeEntryPoint("gamma", plugin=unopenable),
        )
        payload = self.run_doctor_json("--failures", registry=registry)
        self.assertEqual(payload["checks"], [])
        self.assertEqual(payload["not_evaluated"], [])
        self.assertEqual(
            [section["driver"] for section in payload["plugins"]],
            ["alpha", "gamma"],
        )
        text = self.run_text("--failures", registry=registry)
        flat = " ".join(text.split())
        self.assertIn("Plugins:", text)
        self.assertIn("[FAIL] login", flat)
        self.assertIn("not evaluated: config", flat)
        alpha, gamma = payload["plugins"]
        self.assertEqual(
            alpha["checks"],
            [{"name": "login", "ok": False, "detail": "login rejected"}],
        )
        self.assertEqual(alpha["not_evaluated"], [])
        self.assertEqual([check["name"] for check in gamma["checks"]], ["plugin"])
        self.assertFalse(gamma["checks"][0]["ok"])
        self.assertEqual(gamma["not_evaluated"], ["config"])

    def test_ut_dr_09_02_only_the_plugin_fails(self) -> None:
        """UT-DR-09.02: a failing plugin hides Checks: in text and empties checks/not_evaluated."""
        plugin = _plugin_with_checks(
            [{"name": "login", "ok": False, "detail": "login rejected"}]
        )
        write_config(self.home, _PLUGIN_CONFIG)
        text = self.run_text(
            "--failures",
            registry=self.plugin_registry(self.plugin_entry(plugin)),
        )
        self.assertIn("Plugins:", text)
        self.assertNotIn("Checks:", text)
        self.assertNotIn("[ok]", text)
        payload = self.run_doctor_json(
            "--failures",
            registry=self.plugin_registry(self.plugin_entry(plugin)),
        )
        self.assertEqual(payload["checks"], [])
        self.assertEqual(payload["not_evaluated"], [])
        self.assertEqual([section["driver"] for section in payload["plugins"]], ["graph"])
        self.assertEqual(
            payload["plugins"][0]["checks"],
            [{"name": "login", "ok": False, "detail": "login rejected"}],
        )
        self.assertEqual(payload["plugins"][0]["not_evaluated"], [])

    def test_ut_dr_09_03_nothing_fails_with_a_plugin(self) -> None:
        """UT-DR-09.03: a healthy plugin leaves ``plugins: []`` and ``all checks passed``."""
        write_config(self.home, _PLUGIN_CONFIG)
        registry = self.plugin_registry(self.plugin_entry(_configured_plugin()))
        text = self.run_text("--failures", registry=registry)
        self.assertIn("all checks passed", text)
        self.assertNotIn("Plugins:", text)
        payload = self.run_doctor_json("--failures", registry=registry)
        self.assertEqual(payload["checks"], [])
        self.assertEqual(payload["not_evaluated"], [])
        self.assertEqual(payload["plugins"], [])


# --------------------------------------------------------------------------- #
# DOC-12 — diagnosis instead of preflight
# --------------------------------------------------------------------------- #


def _help_text(argv: list[str]) -> str:
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
        code = cli_mod.main(list(argv))
    assert code == 0, f"{argv} exited {code}"
    return stdout.getvalue()


class DiagnosisDocumentationTests(unittest.TestCase):
    """DOC-12: help, skill and READMEs present ``doctor`` as diagnosis."""

    def test_doc_12_01_help_describes_failures_and_diagnosis(self) -> None:
        """DOC-12.01: ``doctor --help`` has ``--failures``; the root help says diagnosis."""
        doctor_help = _help_text(["doctor", "--help"])
        self.assertIn("--failures", doctor_help)
        self.assertIn("mailquery doctor --json --failures", doctor_help)
        root_help = _help_text(["--help"])
        self.assertIn("environment and read-only diagnosis", root_help)
        self.assertNotIn("read-only preflight", root_help)

    def test_doc_12_02_no_preflight_wording(self) -> None:
        """DOC-12.02: no document keeps the preflight rule or preflight wording."""
        documents = {
            "skill": _read(_SKILL_FILE),
            "README.md": _read(_README_EN),
            "README.es.md": _read(_README_ES),
            "root help": _help_text(["--help"]),
        }
        forbidden = (
            "Preflight once per session",
            "# 1. preflight",
            "read-only preflight",
            "before each use",
            "antes de cada uso",
        )
        for label, text in documents.items():
            for marker in forbidden:
                with self.subTest(document=label, marker=marker):
                    self.assertNotIn(marker, text)
        skill = documents["skill"]
        self.assertNotIn("preflight", skill.casefold())

    def test_doc_12_03_skill_diagnoses_from_errors(self) -> None:
        """DOC-12.03: the skill points to ``doctor --json --failures`` and starts with a search."""
        skill = _read(_SKILL_FILE)
        self.assertIn("mailquery doctor --json --failures", skill)
        self.assertIn("after an exit 3 or 6", skill)
        self.assertIn("mailboxes", skill)
        self.assertIn("config.toml", skill)
        self.assertIn("`search` returns 0", skill)
        code = skill.split("## Examples", 1)[1].split("```bash", 1)[1]
        first = next(line for line in code.splitlines() if line.strip())
        self.assertTrue(first.startswith("mailquery search"), first)

    def test_doc_12_04_readmes_describe_doctor_as_verification_and_diagnosis(self) -> None:
        """DOC-12.04: both READMEs document --failures, plugins and the diagnosis use."""
        for label, path in (("README.md", _README_EN), ("README.es.md", _README_ES)):
            text = _read(path)
            with self.subTest(document=label):
                self.assertIn("### `mailquery doctor [--json] [--failures]`", text)
                lowered = text.lower()
                self.assertTrue(
                    "after installing" in lowered or "tras instalar" in lowered,
                    "doctor must be documented as verification after install/upgrade",
                )
                self.assertIn("--failures", text)
                self.assertIn("Plugins:", text)
                self.assertIn("plugins[]", text)


if __name__ == "__main__":  # pragma: no cover - manual runs
    unittest.main()

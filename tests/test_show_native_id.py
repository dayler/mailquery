"""UT-SNI-01: ``show --show-native-id`` renders the driver's native id.

RF-83/RF-73 (AC-68/AC-70): the option is a debugging presentation change of
``message.uid`` available only in ``show``; a driver without the optional
``display_native_id`` hook and the native Apple Mail driver leave the response
unchanged.
"""

from __future__ import annotations

import contextlib
import io
import json
import logging
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from mailquery import cli as cli_mod
from mailquery.backends.registry import BackendRegistry
from mailquery.native_ids import cache_path

from tests.fakes.plugin import (
    ACCOUNT_LABEL as PLUGIN_ACCOUNT_LABEL,
    DRIVER,
    FakeEntryPoint,
    FakePluginBackend,
    internal_entry_points,
    plugin_class,
    plugin_factory,
)
from tests.fixtures.make_fixtures import build_store, prefixed_uid, write_config

#: Config with only the plugin account declared: the native driver is never opened.
PLUGIN_SCOPE = f'[scope."{DRIVER}:{PLUGIN_ACCOUNT_LABEL}"]\n'

#: A valid native form the plugin double returns from ``display_native_id``.
NATIVE_FORM = "graph-ENTRY.1"


def _normalized(payload: dict) -> dict:
    """Drop the run-dependent fields (timestamp and scan duration) for comparisons."""
    normalized = json.loads(json.dumps(payload))
    normalized.pop("generated_at", None)
    scan = normalized.get("scan")
    if isinstance(scan, dict):
        scan.pop("duration_ms", None)
    return normalized


def _cache_state(home: Path) -> bytes | None:
    """Bytes of the native id cache file, or ``None`` when it does not exist."""
    path = cache_path(home)
    return path.read_bytes() if path.exists() else None


def _close_log_handlers() -> None:
    """Release the log file ``cli.main`` leaves open (Windows cannot delete it)."""
    logger = logging.getLogger("mailquery")
    for handler in list(logger.handlers):
        if isinstance(handler, logging.FileHandler):
            logger.removeHandler(handler)
            handler.close()


def _run_cli(argv, *, home, mail_root=None, accounts_db=None, registry=None):
    """Run the CLI in-process and return ``(exit code, JSON payload, raw stdout, stderr)``."""
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.ExitStack() as stack:
        if registry is not None:
            stack.enter_context(
                mock.patch.object(cli_mod, "BackendRegistry", lambda *a, **k: registry)
            )
        stack.enter_context(contextlib.redirect_stdout(stdout))
        stack.enter_context(contextlib.redirect_stderr(stderr))
        code = cli_mod.main(
            list(argv),
            home=home,
            mail_root=mail_root,
            accounts_db=accounts_db,
        )
    raw = stdout.getvalue()
    try:
        payload = json.loads(raw) if raw.strip() else None
    except json.JSONDecodeError:
        payload = None
    return code, payload, raw, stderr.getvalue()


class _ShowCase(unittest.TestCase):
    """Synthetic Apple Mail store, fake home and the plugin doubles a command builds."""

    def setUp(self) -> None:
        self.fx = build_store()
        self.addCleanup(self.fx.cleanup)
        self.addCleanup(_close_log_handlers)
        self.instances: list[FakePluginBackend] = []

    def plugin_entry(self, **kwargs: object) -> FakeEntryPoint:
        base = plugin_factory(**kwargs)

        def factory(context=None):
            instance = base(context)
            self.instances.append(instance)
            return instance

        factory.driver = base.driver
        factory.plugin_api = base.plugin_api
        factory.capabilities = base.capabilities
        factory.native_order = base.native_order
        return FakeEntryPoint(DRIVER, plugin=factory)

    def registry(self, *entries: FakeEntryPoint) -> BackendRegistry:
        return BackendRegistry(
            platform=sys.platform,
            entry_points=[*internal_entry_points(), *entries],
        )

    def use_plugin_config(self) -> None:
        write_config(self.fx.home, PLUGIN_SCOPE)

    def run_command(self, *argv: str, registry=None):
        return _run_cli(
            argv,
            home=self.fx.home,
            mail_root=self.fx.mail_root,
            accounts_db=self.fx.accounts_db,
            registry=registry,
        )

    def assert_success(self, *argv: str, registry=None) -> dict:
        code, payload, _raw, stderr = self.run_command(*argv, registry=registry)
        self.assertEqual(code, 0, f"{argv} failed: {payload} {stderr}")
        assert payload is not None
        self.assertTrue(payload.get("ok"), payload)
        return payload


class AppleMailShowNativeIdTests(_ShowCase):
    """UT-SNI-01.01/.07: Apple Mail and the help contract."""

    def test_ut_sni_01_01_apple_mail_output_is_unchanged(self) -> None:
        """UT-SNI-01.01: the option changes neither the keys nor the values."""
        write_config(self.fx.home)
        uid = prefixed_uid(2714)
        without = self.assert_success("show", uid)
        with_option = self.assert_success("show", uid, "--show-native-id")
        self.assertEqual(_normalized(with_option), _normalized(without))
        self.assertEqual(with_option["message"]["uid"], uid)

    def test_ut_sni_01_07_show_help_describes_the_debugging_option(self) -> None:
        """UT-SNI-01.07: ``show --help`` documents ``--show-native-id`` as debugging only."""
        unused_home = self.fx.root / "unused-home"
        code, _payload, raw, stderr = _run_cli(["show", "--help"], home=unused_home)
        self.assertEqual((code, stderr), (0, ""))
        self.assertIn("--show-native-id", raw)
        flat = " ".join(raw.split())
        self.assertIn(
            "debugging option: show the driver's native id in message.uid instead of "
            "the short uid; the native id is not accepted as input",
            flat,
        )
        self.assertFalse(unused_home.exists(), "--help must not touch the filesystem")


class PluginShowNativeIdTests(_ShowCase):
    """UT-SNI-01.02/.03/.04/.06/.08: the plugin hook and its failures."""

    def setUp(self) -> None:
        super().setUp()
        self.use_plugin_config()

    def test_ut_sni_01_02_plugin_native_form_replaces_only_the_uid(self) -> None:
        """UT-SNI-01.02: uid is ``<driver>:<native form>``; everything else is unchanged."""
        registry = self.registry(self.plugin_entry(results={"display_native_id": NATIVE_FORM}))
        before = self.assert_success(
            "show", f"{DRIVER}:B", "--fields", "all", registry=registry
        )
        cache_after_first = _cache_state(self.fx.home)
        after = self.assert_success(
            "show", f"{DRIVER}:B", "--fields", "all", "--show-native-id", registry=registry
        )
        self.assertEqual(after["message"]["uid"], f"{DRIVER}:{NATIVE_FORM}")
        self.assertEqual(self.instances[-1].display_calls, ["B"])
        expected = _normalized(before)
        expected["message"]["uid"] = f"{DRIVER}:{NATIVE_FORM}"
        self.assertEqual(_normalized(after), expected)
        self.assertEqual(_cache_state(self.fx.home), cache_after_first)
        self.assertIn("cached_path", json.dumps(after["message"]))

    def test_ut_sni_01_03_plugin_without_the_hook_is_unchanged(self) -> None:
        """UT-SNI-01.03: a driver without ``display_native_id`` gives the same response."""
        hookless = plugin_class(display_native_id=None)
        self.assertIsNone(hookless.display_native_id)
        registry = self.registry(FakeEntryPoint(DRIVER, plugin=hookless))
        without = self.assert_success("show", f"{DRIVER}:B", "--fields", "all", registry=registry)
        with_option = self.assert_success(
            "show", f"{DRIVER}:B", "--fields", "all", "--show-native-id", registry=registry
        )
        self.assertEqual(_normalized(with_option), _normalized(without))
        self.assertEqual(with_option["message"]["uid"], f"{DRIVER}:B")

    def test_ut_sni_01_04_invalid_native_form_is_plugin_failed(self) -> None:
        """UT-SNI-01.04: an invalid ``<native_id>`` ⇒ E_PLUGIN_FAILED (exit 3), no message."""
        registry = self.registry(self.plugin_entry(results={"display_native_id": ".."}))
        code, payload, _raw, _stderr = self.run_command(
            "show", f"{DRIVER}:B", "--show-native-id", registry=registry
        )
        self.assertEqual(code, 3)
        assert payload is not None
        self.assertEqual(payload["error"]["code"], "E_PLUGIN_FAILED")
        self.assertNotIn("message", payload)
        self.assertNotIn("messages", payload)

    def test_ut_sni_01_05_only_show_accepts_the_option(self) -> None:
        """UT-SNI-01.05: the other commands reject the option with E_USAGE, without a home."""
        with tempfile.TemporaryDirectory(prefix="mailquery-sni-") as tmp:
            home = Path(tmp) / "home"
            for command in ("search", "new", "attachment", "mailboxes", "doctor"):
                with self.subTest(command=command):
                    code, payload, _raw, _stderr = _run_cli(
                        [command, "--show-native-id"], home=home
                    )
                    self.assertEqual(code, 2)
                    assert payload is not None
                    self.assertEqual(payload["error"]["code"], "E_USAGE")
                    self.assertFalse(home.exists(), f"{command} created the home")

    def test_ut_sni_01_06_native_form_over_the_deadline_is_client_timeout(self) -> None:
        """UT-SNI-01.06: a hook over the metadata deadline ⇒ E_CLIENT_TIMEOUT (exit 3)."""
        registry = self.registry(self.plugin_entry(delays={"display_native_id": 0.2}))
        with mock.patch("mailquery.plugins.api.METADATA_TIMEOUT_SECONDS", 0.05):
            code, payload, _raw, _stderr = self.run_command(
                "show", f"{DRIVER}:B", "--show-native-id", registry=registry
            )
        self.assertEqual(code, 3)
        assert payload is not None
        self.assertEqual(payload["error"]["code"], "E_CLIENT_TIMEOUT")
        self.assertNotIn("message", payload)
        time.sleep(0.25)

    def test_ut_sni_01_08_uid_with_selected_fields_shows_the_native_form(self) -> None:
        """UT-SNI-01.08: ``--fields subject`` still delivers the native uid."""
        registry = self.registry(self.plugin_entry(results={"display_native_id": NATIVE_FORM}))
        payload = self.assert_success(
            "show", f"{DRIVER}:B", "--fields", "subject", "--show-native-id", registry=registry
        )
        self.assertEqual(list(payload["message"]), ["uid", "subject"])
        self.assertEqual(payload["message"]["uid"], f"{DRIVER}:{NATIVE_FORM}")

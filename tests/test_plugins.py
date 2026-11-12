"""M01: plugin API 1, backend registry, ``--version`` and plugin hygiene (UT-PL-01..04).

Covers AC-01 (entry point group, driver/plugin_api validation, duplicates),
AC-02 (capability validation), AC-18 (``--version`` additive ``drivers:``) and
the plugin-file boundaries of RF-39 (PRD §6.5, §12.6, §12.9; plan §5.1 C1).
"""

from __future__ import annotations

import ast
import importlib.metadata
import io
import json
import logging
import os
import platform
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import mailquery
from mailquery import cli as cli_mod
from mailquery.backends import registry as registry_mod
from mailquery.backends.registry import BackendRegistry, package_version
from mailquery.errors import MailqueryError
from mailquery.plugins import (
    PLUGIN_API,
    PluginContext,
    PluginError,
    Reason,
    call_driver,
)

from tests.fakes.plugin import (
    ACCOUNT_LABEL as PLUGIN_ACCOUNT_LABEL,
    CAPABILITIES,
    DRIVER,
    INTERNAL_TARGETS,
    VERSION,
    FakeEntryPoint,
    FakePluginBackend,
    internal_entry_points,
    plugin_class,
    plugin_factory,
)
from tests.fixtures.make_fixtures import DEFAULT_CONFIG, build_store, write_config

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src" / "mailquery"
FAKES_ROOT = Path(__file__).resolve().parent / "fakes"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _import_roots(path: Path) -> list[tuple[str, int]]:
    """Return ``(top-level module, line)`` for every absolute import of ``path``."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((alias.name.split(".")[0], node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.append((node.module.split(".")[0], node.lineno))
    return found


def _import_modules(path: Path) -> list[str]:
    """Return every dotted module imported by ``path``."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.append(node.module)
            found.extend(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def _real_platform_text() -> str:
    if sys.platform == "win32":
        return f"Windows {platform.version()} {platform.machine()}"
    if sys.platform == "darwin":
        return f"macOS {platform.mac_ver()[0]} {platform.machine()}"
    return f"{platform.system()} {platform.release()} {platform.machine()}"


def _expected_drivers(entry_points, platform_name: str) -> str:
    """``drivers: ...`` body: platform-filtered internals plus every external plugin."""
    versions = {entry.name: entry.version for entry in entry_points}
    if platform_name == "win32":
        versions["outlook"] = package_version()
    else:
        versions["apple_mail"] = package_version()
    return ", ".join(f"{name} {version}" for name, version in sorted(versions.items()))


def _version_line(backend: str, platform_text: str, drivers: str) -> str:
    return (
        f"mailquery {mailquery.__version__} (backend {backend}; "
        f"Python {platform.python_version()}; {platform_text}; drivers: {drivers})\n"
    )


def _normalized(payload: dict) -> dict:
    """Drop the run-dependent fields (timestamp and scan duration) for comparisons."""
    normalized = json.loads(json.dumps(payload))
    normalized.pop("generated_at", None)
    scan = normalized.get("scan")
    if isinstance(scan, dict):
        scan.pop("duration_ms", None)
    return normalized


class _PluginTestCase(unittest.TestCase):
    def registry(self, entry_points=(), platform_name=None) -> BackendRegistry:
        return BackendRegistry(
            entry_points=list(entry_points),
            platform=platform_name if platform_name is not None else sys.platform,
        )

    def assert_plugin_error(self, expected_code: str, call) -> MailqueryError:
        with self.assertRaises(MailqueryError) as context:
            call()
        error = context.exception
        self.assertEqual(error.code, expected_code)
        self.assertEqual(error.exit_code, 3 if expected_code == "E_PLUGIN_INCOMPATIBLE" else 2)
        return error


# --------------------------------------------------------------------------- #
# UT-PL-01 — driver registry (AC-01, RF-35)
# --------------------------------------------------------------------------- #


class RegistryTests(_PluginTestCase):
    def test_ut_pl_01_01_builtin_drivers_are_listed_from_metadata_without_imports(self) -> None:
        """UT-PL-01.01: the group exposes apple_mail/outlook; metadata lists them unimported."""
        entries = internal_entry_points()
        registry = self.registry(entries, platform_name="darwin")
        with mock.patch.object(
            registry_mod, "_import_target", side_effect=AssertionError("driver imported")
        ):
            listed = registry.declared(["apple_mail", "outlook"])
        by_driver = {item["driver"]: item for item in listed}
        self.assertEqual(set(by_driver), {"apple_mail", "outlook"})
        for driver, item in by_driver.items():
            self.assertEqual(item["driver"], driver)
            self.assertEqual(item["plugin_api"], PLUGIN_API)
            self.assertEqual(item["version"], package_version())
            self.assertTrue(item["internal"])
        self.assertEqual([entry.load_calls for entry in entries], [0, 0])
        versions = dict(registry.versions(platform="darwin"))
        self.assertEqual(versions["apple_mail"], package_version())

    def test_ut_pl_01_02_development_fallback_resolves_internal_drivers(self) -> None:
        """UT-PL-01.02: without installed metadata the static fallback exposes both internals."""
        registry = self.registry([], platform_name="darwin")
        self.assertEqual(registry.installed(), ["apple_mail", "outlook"])
        self.assertEqual(
            sorted(item["driver"] for item in registry.declared(["apple_mail", "outlook"])),
            ["apple_mail", "outlook"],
        )
        self.assertIn("apple_mail", dict(registry.versions(platform="darwin")))

    def test_ut_pl_01_03_injected_external_plugin_is_registered_by_the_same_path(self) -> None:
        """UT-PL-01.03: a valid external plugin (injected metadata) is listed with API 1/caps."""
        entry = FakeEntryPoint(DRIVER, plugin=FakePluginBackend, version=VERSION)
        registry = self.registry([entry], platform_name="darwin")
        metadata = registry.info(DRIVER)
        self.assertEqual(metadata["driver"], DRIVER)
        self.assertEqual(metadata["plugin_api"], PLUGIN_API)
        self.assertEqual(metadata["version"], VERSION)
        self.assertEqual(metadata["capabilities"], CAPABILITIES)
        self.assertFalse(metadata["internal"])
        self.assertEqual(registry.info(DRIVER), metadata)
        self.assertEqual(entry.load_calls, 1, "metadata must be cached after the first load")
        self.assertIn(DRIVER, registry.installed())
        self.assertIn((DRIVER, VERSION), registry.versions(platform="darwin"))

    def test_ut_pl_01_04_reserved_driver_names_are_rejected(self) -> None:
        """UT-PL-01.04: a plugin declaring a reserved name ⇒ E_PLUGIN_INCOMPATIBLE."""
        for reserved in sorted(INTERNAL_TARGETS):
            with self.subTest(driver=reserved):
                entry = FakeEntryPoint(reserved, plugin=FakePluginBackend)
                registry = self.registry([entry], platform_name="darwin")
                error = self.assert_plugin_error(
                    "E_PLUGIN_INCOMPATIBLE", lambda: registry.info(reserved)
                )
                self.assertIn("reserved", error.message)

    def test_ut_pl_01_05_invalid_driver_names_are_rejected(self) -> None:
        """UT-PL-01.05: names outside ``[a-z0-9_]{1,64}`` ⇒ E_PLUGIN_INCOMPATIBLE."""
        for name in ("Apple_Mail", "apple-mail", "", "a" * 65):
            with self.subTest(name=name):
                entry = FakeEntryPoint(name, plugin=FakePluginBackend)
                registry = self.registry([entry], platform_name="darwin")
                error = self.assert_plugin_error(
                    "E_PLUGIN_INCOMPATIBLE", lambda: registry.info(name)
                )
                self.assertIn("[a-z0-9_]{1,64}", error.message)
        valid = "a" * 64
        entry = FakeEntryPoint(valid, plugin=plugin_class(driver=valid))
        self.assertEqual(self.registry([entry]).info(valid)["driver"], valid)

    def test_ut_pl_01_06_missing_or_wrong_plugin_api_is_rejected(self) -> None:
        """UT-PL-01.06: plugin_api absent or ≠ 1 ⇒ E_PLUGIN_INCOMPATIBLE with expected/found."""
        variants = {
            "absent": SimpleNamespace(driver=DRIVER, capabilities=dict(CAPABILITIES)),
            "none": plugin_class(plugin_api=None),
            "two": plugin_class(plugin_api=2),
        }
        for label, plugin in variants.items():
            with self.subTest(variant=label):
                entry = FakeEntryPoint(DRIVER, plugin=plugin)
                registry = self.registry([entry])
                error = self.assert_plugin_error(
                    "E_PLUGIN_INCOMPATIBLE", lambda: registry.info(DRIVER)
                )
                self.assertIn("expected 1", error.hint)
                expected_found = "found 2" if label == "two" else "found None"
                self.assertIn(expected_found, error.hint)

    def test_ut_pl_01_07_unimportable_plugin_keeps_other_drivers_listable(self) -> None:
        """UT-PL-01.07: a declared plugin that cannot import ⇒ E_PLUGIN_INCOMPATIBLE; listing survives."""
        broken = FakeEntryPoint(
            "broken", import_error=ImportError("No module named 'missing_dep'")
        )
        graph = FakeEntryPoint(DRIVER, plugin=FakePluginBackend)
        registry = self.registry([broken, graph], platform_name="darwin")
        error = self.assert_plugin_error(
            "E_PLUGIN_INCOMPATIBLE", lambda: registry.declared(["broken"])
        )
        self.assertIn("missing_dep", error.message + error.hint)
        self.assertEqual(registry.installed(), ["apple_mail", "broken", "graph", "outlook"])
        self.assertEqual(registry.info("apple_mail")["driver"], "apple_mail")
        self.assertEqual(registry.info(DRIVER)["driver"], DRIVER)

    def test_ut_pl_01_08_loading_is_lazy_and_only_touches_the_requested_driver(self) -> None:
        """UT-PL-01.08: the native declaration never imports the plugin; loading one driver only."""
        graph = FakeEntryPoint(DRIVER, plugin=FakePluginBackend)
        registry = self.registry([graph], platform_name="darwin")
        registry.declared(["apple_mail"])
        self.assertEqual(graph.load_calls, 0)
        with mock.patch.object(registry_mod, "_import_target", return_value=object()) as import_mock:
            registry.load("apple_mail")
        self.assertEqual(import_mock.call_args.args[0], INTERNAL_TARGETS["apple_mail"])
        self.assertEqual(graph.load_calls, 0)

    def test_ut_pl_01_09_drivers_are_alphabetical_and_platform_filtered(self) -> None:
        """UT-PL-01.09: ``drivers:`` is alphabetical; internals are filtered by platform."""
        graph = FakeEntryPoint(DRIVER, plugin=FakePluginBackend, version=VERSION)
        registry = self.registry([graph], platform_name="darwin")
        darwin = ", ".join(f"{name} {ver}" for name, ver in registry.versions(platform="darwin"))
        self.assertEqual(darwin, f"apple_mail {package_version()}, graph {VERSION}")
        windows = ", ".join(
            f"{name} {ver}" for name, ver in registry.versions(platform="win32")
        )
        self.assertEqual(windows, f"graph {VERSION}, outlook {package_version()}")

    def test_ut_pl_01_10_duplicate_driver_is_rejected(self) -> None:
        """UT-PL-01.10: two plugins (or two internal entries) with the same driver ⇒ incompatible."""
        two_plugins = [
            FakeEntryPoint(DRIVER, plugin=FakePluginBackend),
            FakeEntryPoint(DRIVER, plugin=plugin_class()),
        ]
        error = self.assert_plugin_error(
            "E_PLUGIN_INCOMPATIBLE", lambda: self.registry(two_plugins).info(DRIVER)
        )
        self.assertEqual(error.exit_code, 3)
        self.assertIn("duplicate", error.message)
        apple_mail = FakeEntryPoint("apple_mail", INTERNAL_TARGETS["apple_mail"])
        duplicated_internal = [apple_mail, FakeEntryPoint("apple_mail", apple_mail.value)]
        error = self.assert_plugin_error(
            "E_PLUGIN_INCOMPATIBLE",
            lambda: self.registry(duplicated_internal).info("apple_mail"),
        )
        self.assertIn("duplicate", error.message)


# --------------------------------------------------------------------------- #
# UT-PL-02 — capabilities (AC-02, RF-38)
# --------------------------------------------------------------------------- #


class CapabilityTests(_PluginTestCase):
    def capabilities(self, **overrides) -> dict:
        caps = dict(CAPABILITIES)
        caps.update(overrides)
        return caps

    def test_ut_pl_02_01_valid_capability_map_is_accepted_and_exposed(self) -> None:
        """UT-PL-02.01: a valid network/readonly/body_local/attachments/native_order map is exposed."""
        entry = FakeEntryPoint(DRIVER, plugin=plugin_class(capabilities=dict(CAPABILITIES)))
        metadata = self.registry([entry]).info(DRIVER)
        self.assertEqual(metadata["capabilities"], CAPABILITIES)
        self.assertEqual(
            set(metadata["capabilities"]),
            {"network", "readonly", "body_local", "attachments", "native_order"},
        )

    def test_ut_pl_02_02_missing_capability_is_rejected(self) -> None:
        """UT-PL-02.02: a missing capability ⇒ E_PLUGIN_INCOMPATIBLE."""
        for missing in tuple(CAPABILITIES):
            with self.subTest(missing=missing):
                caps = dict(CAPABILITIES)
                del caps[missing]
                entry = FakeEntryPoint(DRIVER, plugin=plugin_class(capabilities=caps))
                self.assert_plugin_error(
                    "E_PLUGIN_INCOMPATIBLE", lambda: self.registry([entry]).info(DRIVER)
                )

    def test_ut_pl_02_03_out_of_enum_capability_value_is_rejected(self) -> None:
        """UT-PL-02.03: attachments/readonly/native_order outside their enum ⇒ incompatible."""
        variants = {
            "attachments": self.capabilities(attachments="zip"),
            "readonly": self.capabilities(readonly="yes"),
            "native_order": self.capabilities(native_order="alpha"),
            "network": self.capabilities(network="yes"),
            "body_local": self.capabilities(body_local=1),
        }
        for label, caps in variants.items():
            with self.subTest(capability=label):
                entry = FakeEntryPoint(DRIVER, plugin=plugin_class(capabilities=caps))
                self.assert_plugin_error(
                    "E_PLUGIN_INCOMPATIBLE", lambda: self.registry([entry]).info(DRIVER)
                )

    def test_ut_pl_02_04_remote_attachments_require_network(self) -> None:
        """UT-PL-02.04: ``attachments: remote`` without ``network: true`` ⇒ incompatible."""
        caps = self.capabilities(attachments="remote", network=False)
        entry = FakeEntryPoint(DRIVER, plugin=plugin_class(capabilities=caps))
        error = self.assert_plugin_error(
            "E_PLUGIN_INCOMPATIBLE", lambda: self.registry([entry]).info(DRIVER)
        )
        self.assertIn("network", error.message)

    def test_ut_pl_02_05_non_local_body_requires_network(self) -> None:
        """UT-PL-02.05: ``body_local: false`` without ``network: true`` ⇒ incompatible."""
        caps = self.capabilities(body_local=False, network=False)
        entry = FakeEntryPoint(DRIVER, plugin=plugin_class(capabilities=caps))
        error = self.assert_plugin_error(
            "E_PLUGIN_INCOMPATIBLE", lambda: self.registry([entry]).info(DRIVER)
        )
        self.assertIn("network", error.message)

    def test_ut_pl_02_06_each_driver_validates_its_own_capability_map(self) -> None:
        """UT-PL-02.06: several drivers, each map validated separately and exposed as declared."""
        local_caps = {
            "network": False,
            "readonly": "structural",
            "body_local": True,
            "attachments": "local",
            "native_order": "numeric",
        }
        graph = FakeEntryPoint(DRIVER, plugin=plugin_class(capabilities=dict(CAPABILITIES)))
        mail = FakeEntryPoint(
            "mail",
            plugin=plugin_class(driver="mail", capabilities=dict(local_caps)),
        )
        listed = {item["driver"]: item for item in self.registry([graph, mail]).declared(
            [DRIVER, "mail"]
        )}
        self.assertEqual(listed[DRIVER]["capabilities"], CAPABILITIES)
        self.assertEqual(listed["mail"]["capabilities"], local_caps)


# --------------------------------------------------------------------------- #
# UT-PL-03 — ``--version`` (AC-18, DP-02)
# --------------------------------------------------------------------------- #


class VersionTests(_PluginTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="mailquery-m01-version-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()

    def patched(
        self,
        *,
        plat: str,
        system: str = "Linux",
        release: str = "6.1",
        version: str = "1",
        mac: str = "",
        machine: str = "x86_64",
    ) -> None:
        patchers = [
            mock.patch.object(sys, "platform", plat),
            mock.patch("platform.system", return_value=system),
            mock.patch("platform.release", return_value=release),
            mock.patch("platform.version", return_value=version),
            mock.patch("platform.machine", return_value=machine),
            mock.patch("platform.mac_ver", return_value=(mac, ("", "", ""), machine)),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_version(self, argv=("--version",), *, home=None, entry_points=()):
        home = self.home if home is None else home
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            mock.patch.object(
                registry_mod, "installed_entry_points", return_value=tuple(entry_points)
            ),
            mock.patch.dict(os.environ, {"HOME": str(home), "USERPROFILE": str(home)}),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            code = cli_mod.main(list(argv), home=home)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_ut_pl_03_01_version_line_keeps_the_prefix_and_appends_drivers(self) -> None:
        """UT-PL-03.01: installed version prefix plus alphabetical ``; drivers: ...`` in parentheses."""
        entry = FakeEntryPoint(DRIVER, plugin=FakePluginBackend, version=VERSION)
        platform_name = sys.platform
        backend = "outlook" if platform_name == "win32" else "apple_mail"
        expected = _version_line(
            backend, _real_platform_text(), _expected_drivers([entry], platform_name)
        )
        code, stdout, stderr = self.run_version(entry_points=[entry])
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(stdout, expected)
        self.assertIn(f"drivers: {_expected_drivers([entry], platform_name)})", stdout)
        self.assertEqual(self.run_version(["-v"], entry_points=[entry]), (code, stdout, stderr))

    def test_ut_pl_03_02_internal_drivers_follow_the_platform_and_plugins_always_show(self) -> None:
        """UT-PL-03.02: macOS lists apple_mail only, Windows outlook only; external plugins always."""
        entry = FakeEntryPoint(DRIVER, plugin=FakePluginBackend, version=VERSION)
        self.patched(plat="darwin", system="Darwin", mac="14.5", machine="arm64")
        code, stdout, _ = self.run_version(entry_points=[entry])
        self.assertEqual(code, 0)
        self.assertEqual(
            stdout,
            _version_line(
                "apple_mail", "macOS 14.5 arm64", _expected_drivers([entry], "darwin")
            ),
        )
        self.assertIn(f"drivers: apple_mail {package_version()}, graph {VERSION})", stdout)
        self.assertNotIn("outlook", stdout)
        self.patched(
            plat="win32", system="Windows", release="11", version="10.0.26200", machine="AMD64"
        )
        code, stdout, _ = self.run_version(entry_points=[entry])
        self.assertEqual(code, 0)
        self.assertEqual(
            stdout,
            _version_line(
                "outlook", "Windows 10.0.26200 AMD64", _expected_drivers([entry], "win32")
            ),
        )
        self.assertIn(f"drivers: graph {VERSION}, outlook {package_version()})", stdout)
        self.assertNotIn("apple_mail", stdout)

    def test_ut_pl_03_03_version_has_no_side_effects(self) -> None:
        """UT-PL-03.03: no home/config/log/lock/store, ``cmd -v`` is E_USAGE and help ordering holds."""
        missing_home = self.root / "no-such-home"
        entry = FakeEntryPoint(DRIVER, plugin=FakePluginBackend, version=VERSION)
        with (
            mock.patch.object(cli_mod, "ensure_app_home", side_effect=AssertionError),
            mock.patch.object(cli_mod, "load_config", side_effect=AssertionError),
            mock.patch.object(cli_mod, "get_backend", side_effect=AssertionError),
            mock.patch.object(cli_mod, "RunLock", side_effect=AssertionError),
            mock.patch.object(cli_mod, "setup_logging", side_effect=AssertionError),
        ):
            code, stdout, _ = self.run_version(
                home=missing_home, entry_points=[entry]
            )
        self.assertEqual(code, 0)
        self.assertTrue(stdout.startswith("mailquery "))
        self.assertFalse(missing_home.exists())
        self.assertFalse((self.home / "logs" / "mailquery.log").exists())
        # A broken config is not read and a debug level does not create the log.
        write_config(self.home, "this is = = not toml\n")
        with mock.patch.object(cli_mod, "load_config", side_effect=AssertionError):
            code, stdout, _ = self.run_version(["--log-level", "debug", "-v"])
        self.assertEqual(code, 0)
        self.assertTrue(stdout.startswith("mailquery "))
        self.assertFalse((self.home / "logs" / "mailquery.log").exists())
        # ``cmd -v`` stays E_USAGE (the subcommands have no version flag).
        code, stdout, _ = self.run_version(["search", "-v"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(stdout)["error"]["code"], "E_USAGE")
        # The first of -v/-h wins; both exit 0.
        code, stdout, _ = self.run_version(["-v", "-h"])
        self.assertEqual(code, 0)
        self.assertTrue(stdout.startswith("mailquery "))
        self.assertNotIn("usage:", stdout)
        code, stdout, _ = self.run_version(["-h", "-v"])
        self.assertEqual(code, 0)
        self.assertIn("usage: mailquery", stdout)

    def test_ut_pl_03_04_incompatible_plugin_is_listed_by_metadata(self) -> None:
        """UT-PL-03.04: an installed plugin shows up even if incompatible; doctor reports it later."""
        entry = FakeEntryPoint(
            DRIVER, plugin=plugin_class(plugin_api=2), version="0.3.0"
        )
        code, stdout, stderr = self.run_version(entry_points=[entry])
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn(f"graph 0.3.0", stdout)
        self.assertIn("drivers: ", stdout)
        self.assertEqual(entry.load_calls, 0)

    def test_ut_pl_03_05_version_never_imports_plugin_modules(self) -> None:
        """UT-PL-03.05: distribution metadata only; a plugin without platform metadata is never filtered."""
        entry = FakeEntryPoint(
            DRIVER,
            value="mailquery_does_not_exist_plugin:Backend",
            import_error=ImportError("plugin import must not happen"),
            version=VERSION,
        )
        self.patched(plat="darwin", system="Darwin", mac="14.5", machine="arm64")
        code, stdout, _ = self.run_version(entry_points=[entry])
        self.assertEqual(code, 0)
        self.assertIn(f"graph {VERSION}", stdout)
        self.assertEqual(entry.load_calls, 0)
        self.assertNotIn("mailquery_does_not_exist_plugin", sys.modules)
        self.patched(
            plat="win32", system="Windows", release="11", version="10.0.26200", machine="AMD64"
        )
        code, stdout, _ = self.run_version(entry_points=[entry])
        self.assertEqual(code, 0)
        self.assertIn(f"graph {VERSION}", stdout)
        self.assertEqual(entry.load_calls, 0)

    def test_ut_pl_03_06_missing_distribution_metadata_falls_back_to_dunder_version(self) -> None:
        """UT-PL-03.06: without an installed package ``--version`` uses ``__version__`` and exits 0."""
        not_found = importlib.metadata.PackageNotFoundError("mailquery")
        with mock.patch("importlib.metadata.version", side_effect=not_found):
            code, stdout, stderr = self.run_version(entry_points=[])
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertTrue(stdout.startswith(f"mailquery {mailquery.__version__} (backend "))
        self.assertIn("drivers: ", stdout)
        self.assertIn(f"{mailquery.__version__})", stdout)
        internal = "outlook" if sys.platform == "win32" else "apple_mail"
        self.assertIn(f"drivers: {internal} {mailquery.__version__})", stdout)


# --------------------------------------------------------------------------- #
# UT-PL-04 — plugin API and autonomous plugin files (AC-01, RF-39)
# --------------------------------------------------------------------------- #


class PluginApiTests(_PluginTestCase):
    def test_ut_pl_04_01_public_api_is_self_contained(self) -> None:
        """UT-PL-04.01: PluginContext/PluginError/Reason/PLUGIN_API and a plugin using only that package."""
        context = PluginContext(home=Path("/home/u"), tmp_dir=Path("/home/u/tmp"))
        self.assertEqual(context.home, Path("/home/u"))
        self.assertEqual(context.tmp_dir, Path("/home/u/tmp"))
        error = PluginError(
            Reason.BUSY, hint="retry later", detail="detail text", log_message="log text"
        )
        self.assertEqual(error.reason, Reason.BUSY)
        self.assertEqual(error.hint, "retry later")
        self.assertEqual(error.detail, "detail text")
        self.assertEqual(error.log_message, "log text")
        defaults = PluginError(Reason.TIMEOUT)
        self.assertEqual((defaults.hint, defaults.detail, defaults.log_message), ("", "", ""))
        self.assertEqual(PLUGIN_API, 1)
        self.assertEqual(
            {reason.value for reason in Reason},
            {
                "invalid_uid",
                "not_found",
                "not_local",
                "not_downloaded",
                "unsupported",
                "corrupt",
                "smime",
                "unreadable",
                "network",
                "permission",
                "auth",
                "busy",
                "timeout",
            },
        )
        self.assertEqual(len(Reason), 13)
        # The double only needs the public package: stdlib + mailquery.plugins.
        allowed = set(sys.stdlib_module_names) | {"mailquery"}
        offenders = []
        for root, line in _import_roots(FAKES_ROOT / "plugin.py"):
            if root not in allowed:
                offenders.append(f"plugin.py:{line} imports {root}")
        for module in _import_modules(FAKES_ROOT / "plugin.py"):
            if module.startswith("mailquery.") and module != "mailquery.plugins":
                self.assertTrue(
                    module.startswith("mailquery.plugins."),
                    f"the plugin double imports an internal module: {module}",
                )
        self.assertEqual(offenders, [])

    def run_fixture(self, fx, argv):
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            mock.patch.dict(
                os.environ, {"HOME": str(fx.home), "USERPROFILE": str(fx.home)}
            ),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            code = cli_mod.main(
                list(argv),
                home=fx.home,
                mail_root=fx.mail_root,
                accounts_db=fx.accounts_db,
            )
        return code, stdout.getvalue(), stderr.getvalue()

    def test_ut_pl_04_02_core_does_not_read_plugin_config_or_log(self) -> None:
        """UT-PL-04.02: commands and doctor behave the same with ``<driver>.toml``/log present."""
        fx = build_store()
        self.addCleanup(fx.cleanup)
        write_config(fx.home, DEFAULT_CONFIG)
        conditions = {}
        for command in (("search",), ("doctor", "--json")):
            code, stdout, _ = self.run_fixture(fx, command)
            self.assertEqual(code, 0)
            conditions[command] = _normalized(json.loads(stdout))
        plugin_config = fx.home / "graph.toml"
        plugin_config.write_text('token = "secret"\n', encoding="utf-8")
        log_dir = fx.home / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        plugin_log = log_dir / "graph.log"
        plugin_log.write_text("plugin log line\n", encoding="utf-8")
        for command in (("search",), ("doctor", "--json")):
            code, stdout, _ = self.run_fixture(fx, command)
            self.assertEqual(code, 0)
            self.assertEqual(_normalized(json.loads(stdout)), conditions[command])
        self.assertEqual(plugin_config.read_text(encoding="utf-8"), 'token = "secret"\n')
        self.assertEqual(plugin_log.read_text(encoding="utf-8"), "plugin log line\n")

    def test_ut_pl_04_03_core_never_creates_rotates_or_deletes_plugin_files(self) -> None:
        """UT-PL-04.03: the core does not create/rotate/delete plugin toml, log or tmp dir."""
        clean = build_store()
        self.addCleanup(clean.cleanup)
        write_config(clean.home, DEFAULT_CONFIG)
        for command in (("search",), ("new",), ("doctor", "--json")):
            self.assertEqual(self.run_fixture(clean, command)[0], 0)
        self.assertFalse((clean.home / "graph.toml").exists())
        self.assertFalse((clean.home / "logs" / "graph.log").exists())
        self.assertFalse((clean.home / "tmp" / "plugin-graph").exists())
        seeded = build_store()
        self.addCleanup(seeded.cleanup)
        write_config(seeded.home, DEFAULT_CONFIG)
        plugin_config = seeded.home / "graph.toml"
        plugin_config.write_text("keep = true\n", encoding="utf-8")
        log_dir = seeded.home / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        plugin_log = log_dir / "graph.log"
        plugin_log.write_text("keep this line\n", encoding="utf-8")
        plugin_tmp = seeded.home / "tmp" / "plugin-graph"
        plugin_tmp.mkdir(parents=True)
        sentinel = plugin_tmp / "keep.txt"
        sentinel.write_text("keep\n", encoding="utf-8")
        for command in (("search",), ("new",), ("doctor", "--json")):
            self.assertEqual(self.run_fixture(seeded, command)[0], 0)
        self.assertEqual(plugin_config.read_text(encoding="utf-8"), "keep = true\n")
        self.assertEqual(plugin_log.read_text(encoding="utf-8"), "keep this line\n")
        self.assertTrue(sentinel.is_file())
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep\n")

    def test_ut_pl_04_04_plugin_package_and_registry_use_only_stdlib_and_mailquery(self) -> None:
        """UT-PL-04.04: ``plugins/**`` and ``backends/registry.py`` import stdlib and mailquery only."""
        allowed = set(sys.stdlib_module_names) | {"mailquery"}
        paths = sorted((SRC_ROOT / "plugins").rglob("*.py")) + [
            SRC_ROOT / "backends" / "registry.py"
        ]
        offenders = []
        for path in paths:
            for root, line in _import_roots(path):
                if root not in allowed:
                    offenders.append(f"{path.relative_to(SRC_ROOT)}:{line} imports {root}")
            # RNF-12: they must not depend on backend implementations or the store.
            for module in _import_modules(path):
                if module in {
                    "mailquery.store",
                    "mailquery.emlx",
                    "mailquery.accounts",
                    "mailquery.search",
                    "mailquery.config",
                }:
                    offenders.append(f"{path.relative_to(SRC_ROOT)} imports {module}")
        self.assertEqual(offenders, [])


# --------------------------------------------------------------------------- #
# M05 — plugin error protocol and metadata timeout (UT-ERR-01..04)
# --------------------------------------------------------------------------- #

#: Config with only the plugin account declared: the native driver is never opened.
PLUGIN_ONLY_CONFIG = f'[scope."{DRIVER}:{PLUGIN_ACCOUNT_LABEL}"]\n'

#: Config for the minimal injected native backend (UT-ERR-03.03).
NATIVE_FAKE_CONFIG = '[scope."Fake"]\n'

#: PRD §12.6 mapping in attachment operations: reason -> (code, exit).
ATTACHMENT_REASON_MAP = (
    ("invalid_uid", "E_USAGE", 2),
    ("not_found", "E_USAGE", 2),
    ("not_local", "E_ATTACHMENT_UNAVAILABLE", 3),
    ("not_downloaded", "E_ATTACHMENT_UNAVAILABLE", 3),
    ("unsupported", "E_ATTACHMENT_UNAVAILABLE", 3),
    ("network", "E_ATTACHMENT_UNAVAILABLE", 3),
    ("corrupt", "E_ATTACHMENT_UNREADABLE", 3),
    ("smime", "E_ATTACHMENT_UNREADABLE", 3),
    ("unreadable", "E_ATTACHMENT_UNREADABLE", 3),
    ("permission", "E_PERMISSION", 3),
    ("auth", "E_PERMISSION", 3),
    ("busy", "E_CLIENT_BUSY", 5),
    ("timeout", "E_CLIENT_TIMEOUT", 3),
)

#: PRD §12.6 mapping in every other operation: the attachment-only reasons fail as E_PLUGIN_FAILED.
REST_REASON_MAP = tuple(
    (reason, "E_PLUGIN_FAILED", 3)
    if reason
    in {
        "not_local",
        "not_downloaded",
        "unsupported",
        "network",
        "corrupt",
        "smime",
        "unreadable",
    }
    else (reason, code, exit_code)
    for reason, code, exit_code in ATTACHMENT_REASON_MAP
)

#: Core-owned English message templates of PRD §12.6 (the driver name is substituted).
MESSAGE_TEMPLATES = {
    "not_local": "not available in the local store",
    "not_downloaded": "could not be retrieved from its origin",
    "network": "could not be retrieved from its origin",
    "unsupported": f"cannot be recovered by driver '{DRIVER}'",
    "corrupt": "is corrupt or unreadable",
    "unreadable": "is corrupt or unreadable",
    "smime": "is S/MIME protected and cannot be extracted",
    "permission": "cannot be read: permission denied",
    "auth": "cannot be read: permission denied",
    "busy": "is temporarily unavailable",
    "timeout": "did not respond within the timeout",
}


def _close_log_handlers() -> None:
    """Release the log file ``cli.main`` leaves open (Windows cannot delete it)."""
    logger = logging.getLogger("mailquery")
    for handler in list(logger.handlers):
        if isinstance(handler, logging.FileHandler):
            logger.removeHandler(handler)
            handler.close()


class _ReasonMappingCase(unittest.TestCase):
    """Helpers to drive the public wrapper with a ``PluginError``."""

    def mapped(
        self,
        reason,
        *,
        operation: str = "query",
        hint: str = "",
        detail: str = "",
        log_message: str = "",
        driver: str = DRIVER,
        internal: bool = False,
    ) -> MailqueryError:
        def call():
            raise PluginError(reason, hint, detail, log_message)

        with self.assertRaises(MailqueryError) as context:
            call_driver(operation, call, driver=driver, internal=internal)
        return context.exception

    def assert_maps(self, error: MailqueryError, code: str, exit_code: int) -> None:
        self.assertEqual(error.code, code)
        self.assertEqual(error.exit_code, exit_code)
        self.assertNotEqual(error.code, "E_INTERNAL")


# UT-ERR-01 — reason -> code/exit mapping (AC-16, PRD §12.6)
# --------------------------------------------------------------------------- #


class PluginErrorMappingTests(_ReasonMappingCase):
    def test_ut_err_01_01_attachment_operations_map_the_whole_reason_table(self) -> None:
        """UT-ERR-01.01: every PRD §12.6 reason in an attachment operation maps to its code."""
        for reason, code, exit_code in ATTACHMENT_REASON_MAP:
            with self.subTest(reason=reason):
                error = self.mapped(reason, operation="attachments")
                self.assert_maps(error, code, exit_code)

    def test_ut_err_01_02_other_operations_map_the_whole_reason_table(self) -> None:
        """UT-ERR-01.02: attachment-only reasons fail as E_PLUGIN_FAILED elsewhere."""
        for reason, code, exit_code in REST_REASON_MAP:
            with self.subTest(reason=reason):
                error = self.mapped(reason, operation="query")
                self.assert_maps(error, code, exit_code)

    def test_ut_err_01_03_unknown_empty_or_non_string_reason_is_plugin_failed(self) -> None:
        """UT-ERR-01.03: unknown/empty/non-string reason => E_PLUGIN_FAILED, never E_INTERNAL."""
        for reason in ("unknown_reason", "", 0, None):
            with self.subTest(reason=repr(reason)):
                error = self.mapped(reason)
                self.assert_maps(error, "E_PLUGIN_FAILED", 3)

    def test_ut_err_01_04_plugin_cannot_choose_code_or_exit(self) -> None:
        """UT-ERR-01.04: code/exit are the core's; plugin attributes and exceptions are ignored."""
        plugin_error = PluginError(Reason.BUSY)
        plugin_error.code = "E_INTERNAL"  # type: ignore[attr-defined]
        plugin_error.exit_code = 1  # type: ignore[attr-defined]
        plugin_error.exit = 1  # type: ignore[attr-defined]

        def call():
            raise plugin_error

        with self.assertRaises(MailqueryError) as context:
            call_driver("query", call, driver=DRIVER, internal=False)
        self.assert_maps(context.exception, "E_CLIENT_BUSY", 5)

        def forged():
            raise MailqueryError("E_INTERNAL", "plugin-chosen internal error")

        with self.assertRaises(MailqueryError) as forged_context:
            call_driver("query", forged, driver=DRIVER, internal=False)
        self.assert_maps(forged_context.exception, "E_PLUGIN_FAILED", 3)
        self.assertNotIn("plugin-chosen internal error", forged_context.exception.message)

    def test_ut_err_01_05_error_payload_keeps_the_documented_shape(self) -> None:
        """UT-ERR-01.05: the error payload is {ok, command, error} with no generated_at."""
        error = self.mapped(Reason.BUSY)
        payload = error.to_payload("search")
        self.assertEqual(set(payload), {"ok", "command", "error"})
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["command"], "search")
        self.assertEqual(set(payload["error"]), {"code", "message", "hint"})
        self.assertNotIn("generated_at", payload)


# UT-ERR-02 — sanitization, limits, templates and logging (AC-16, AC-19)
# --------------------------------------------------------------------------- #


class PluginErrorSanitizationTests(_ReasonMappingCase):
    def test_ut_err_02_01_hint_detail_and_log_message_are_byte_truncated_without_splitting(
        self,
    ) -> None:
        """UT-ERR-02.01: 301/201/201-byte fields become ≤300/200/200 bytes UTF-8-safe."""
        hint = "a" * 299 + "é"  # 299 + 2 = 301 bytes
        detail = "b" * 199 + "é"  # 199 + 2 = 201 bytes
        log_message = "c" * 199 + "é"  # 199 + 2 = 201 bytes
        error = self.mapped(
            Reason.BUSY, hint=hint, detail=detail, log_message=log_message
        )
        self.assertEqual(error.hint, "a" * 299)
        self.assertLessEqual(len(error.hint.encode("utf-8")), 300)
        assert error.log_message is not None
        self.assertEqual(error.log_message, "c" * 199)
        self.assertLessEqual(len(error.log_message.encode("utf-8")), 200)
        detail_part = error.message.split(": ", 1)[1]
        self.assertEqual(detail_part, "b" * 199)
        self.assertLessEqual(len(detail_part.encode("utf-8")), 200)
        for field in (error.hint, error.message, error.log_message):
            self.assertNotIn("\ufffd", field)

        # Boundary: a field that already fits is not touched.
        exact = self.mapped(Reason.BUSY, hint="a" * 300)
        self.assertEqual(exact.hint, "a" * 300)

    def test_ut_err_02_02_control_characters_are_removed_from_error_fields(self) -> None:
        """UT-ERR-02.02: NUL, CR, LF, ANSI and RLO are removed from hint/detail/log_message."""
        for control in ("\x00", "\r", "\n", "\x1b[31m", "\u202e"):
            with self.subTest(control=repr(control)):
                error = self.mapped(
                    Reason.BUSY,
                    hint=f"h{control}h",
                    detail=f"a{control}b",
                    log_message=f"l{control}l",
                )
                self.assertEqual(error.hint, "hh")
                self.assertEqual(error.message.split(": ", 1)[1], "ab")
                assert error.log_message is not None
                self.assertEqual(error.log_message, "ll")
                for field in (error.hint, error.message, error.log_message):
                    self.assertNotIn(control, field)

    def test_ut_err_02_03_message_uses_the_reason_template_plus_sanitized_detail(self) -> None:
        """UT-ERR-02.03: each PRD §12.6 motive yields its template, then `: detail`."""
        for reason, template in MESSAGE_TEMPLATES.items():
            with self.subTest(reason=reason):
                with_detail = self.mapped(
                    reason, operation="attachments", detail="more detail"
                )
                self.assertEqual(with_detail.message, f"{template}: more detail")
                without_detail = self.mapped(reason, operation="attachments")
                self.assertEqual(without_detail.message, template)

    def test_ut_err_02_06_default_hints_are_the_reason_or_code_hints(self) -> None:
        """UT-ERR-02.06: plugin hint wins; otherwise the reason/code hint is used."""
        expected = {
            "not_local": "open the message",
            "not_downloaded": "open the message",
            "network": "check the network connection",
            "unsupported": "install or declare a driver",
            "smime": "S/MIME attachments cannot be extracted",
            "corrupt": "corrupt",
            "unreadable": "cannot be read",
            "permission": "grant the required permissions",
            "auth": "grant the required permissions",
            "busy": "retry once",
            "timeout": "doctor",
        }
        for reason, fragment in expected.items():
            with self.subTest(reason=reason):
                error = self.mapped(reason, operation="attachments")
                self.assertIn(fragment, error.hint)

        failed = self.mapped("unknown_reason")
        self.assertIn('run "mailquery doctor"', failed.hint)

        plugin_hint = self.mapped(Reason.BUSY, hint="the plugin says wait")
        self.assertEqual(plugin_hint.hint, "the plugin says wait")

        registry = BackendRegistry(entry_points=[], platform=sys.platform)
        with self.assertRaises(MailqueryError) as unknown_context:
            registry.info("not_installed_driver")
        unknown_driver = unknown_context.exception
        self.assertEqual(unknown_driver.code, "E_DRIVER_UNKNOWN")
        self.assertIn("installed drivers:", unknown_driver.hint)
        self.assertIn("pipx inject mailquery", unknown_driver.hint)


# UT-ERR-03 — unmapped failures (AC-16)
# --------------------------------------------------------------------------- #


class PluginErrorFallbackTests(_ReasonMappingCase):
    def test_ut_err_03_01_unmapped_exception_is_plugin_failed_without_traceback(self) -> None:
        """UT-ERR-03.01: a plugin exception => E_PLUGIN_FAILED, plugin text never in the JSON."""

        def call():
            raise RuntimeError("plugin bug: internal secret")

        with self.assertRaises(MailqueryError) as context:
            call_driver("query", call, driver=DRIVER, internal=False)
        error = context.exception
        self.assert_maps(error, "E_PLUGIN_FAILED", 3)
        rendered = json.dumps(error.to_payload("search"))
        self.assertNotIn("RuntimeError", rendered)
        self.assertNotIn("plugin bug", rendered)
        self.assertNotIn("Traceback", rendered)
        self.assertIsNotNone(error.log_message)

    def test_ut_err_03_02_invalid_return_values_are_plugin_failed(self) -> None:
        """UT-ERR-03.02: invalid plugin return types => E_PLUGIN_FAILED."""
        cases = (
            ("query", lambda: ["not a row"]),
            ("query", lambda: {"rows": []}),
            ("parse_native_id", lambda: 123),
            ("attachments", lambda: [{"index": 1}]),
            ("attachments", lambda: "not a list"),
            ("load_body", lambda: {"attachments": "not a list"}),
            ("attachment_names", lambda: [1, 2]),
            ("find_message", lambda: ("row",)),
        )
        for operation, call in cases:
            with self.subTest(operation=operation, value=repr(call())):
                with self.assertRaises(MailqueryError) as context:
                    call_driver(operation, call, driver=DRIVER, internal=False)
                self.assert_maps(context.exception, "E_PLUGIN_FAILED", 3)


class _MinimalNativeBackend:
    """Injected native backend whose metadata operation raises an unexpected core error."""

    driver = "apple_mail"
    plugin_api = 1
    native_order = "numeric"
    labels_available = True
    capabilities = {
        "network": False,
        "readonly": "structural",
        "body_local": True,
        "attachments": "local",
        "native_order": "numeric",
    }
    ACCOUNT = {
        "uuid": "fake-native-uuid",
        "label": "Fake",
        "email": None,
        "local": True,
        "store_index": 0,
        "labelled": True,
    }
    MAILBOX = {
        "id": 1,
        "account_uuid": "fake-native-uuid",
        "name": "INBOX",
        "path": "INBOX",
        "url": "mailbox://fake/INBOX",
        "is_inbox": True,
        "is_aggregate": False,
        "total": 0,
        "unread": 0,
    }

    def describe(self) -> dict:
        return {}

    def accounts(self) -> list:
        return [dict(self.ACCOUNT)]

    def mailboxes(self, account_uuids=None) -> list:
        return [dict(self.MAILBOX)]

    def excluded_stores(self) -> list:
        return []

    def resolve_mailbox(self, account_uuid, ref):
        return dict(self.MAILBOX)

    def query(self, *args, **kwargs):
        raise RuntimeError("core bug in the native driver")

    def membership(self, uids):
        return {}

    def duplicate_counts(self, mailbox_ids):
        return {}

    def recipients(self, uids):
        return {}

    def attachment_names(self, uid):
        return []

    def attachments(self, uid):
        return []

    def attachment_stream(self, uid, index):
        return iter(())

    def find_message(self, uid):
        return None

    def load_body(self, row):
        return {
            "available": False,
            "readable": False,
            "partial": False,
            "headers": {},
            "body_text": "",
            "attachments": [],
            "source": {"emlx_path": None, "partial": False},
            "warnings": [],
        }

    @staticmethod
    def parse_uid(raw):
        return int(raw)

    @staticmethod
    def parse_native_id(native_id):
        return int(native_id)

    def doctor_checks(self):
        return []

    def close(self) -> None:
        pass


class PluginErrorRuntimeTests(unittest.TestCase):
    """CLI-level cases: logging rules, core-internal failures and timeout side effects."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="mailquery-m05-")
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(_close_log_handlers)
        self.home = Path(self._tmp.name) / "home"
        self.home.mkdir()

    # -- helpers ------------------------------------------------------------ #

    def registry(self, plugin) -> BackendRegistry:
        return BackendRegistry(
            platform=sys.platform,
            entry_points=[
                *internal_entry_points(),
                FakeEntryPoint(DRIVER, plugin=plugin),
            ],
        )

    def use_plugin_config(self) -> None:
        write_config(self.home, PLUGIN_ONLY_CONFIG)

    def run_cli(self, *argv: str, registry=None, backend=None):
        registry = registry if registry is not None else self.registry(FakePluginBackend)
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            mock.patch.object(cli_mod, "BackendRegistry", lambda *a, **k: registry),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            code = cli_mod.main(list(argv), home=self.home, backend=backend)
        raw = stdout.getvalue()
        payload = json.loads(raw) if raw.strip() else None
        return code, payload, stderr.getvalue()

    def log_text(self) -> str:
        return (self.home / "logs" / "mailquery.log").read_text(encoding="utf-8")

    # -- UT-ERR-02.04/.05 ---------------------------------------------------- #

    def test_ut_err_01_02_show_plugin_native_id_reason_is_mapped_in_the_cli(
        self,
    ) -> None:
        """UT-ERR-01.02 (runtime): a plugin parse_native_id reason maps to the core code."""

        def reject(native_id):
            raise PluginError(Reason.INVALID_UID, "bad native id")

        plugin = plugin_class(parse_native_id=staticmethod(reject))
        self.use_plugin_config()
        code, payload, _stderr = self.run_cli(
            "show", f"{DRIVER}:bad", registry=self.registry(plugin)
        )
        self.assertEqual(code, 2)
        assert payload is not None
        self.assertEqual(payload["error"]["code"], "E_USAGE")
        self.assertNotEqual(payload["error"]["code"], "E_INTERNAL")

    def test_ut_err_02_04_the_log_records_the_sanitized_log_message_only(self) -> None:
        """UT-ERR-02.04: the log gets log_message; hint and detail are never logged."""
        plugin = plugin_factory(
            failures={
                "query": PluginError(
                    Reason.BUSY,
                    hint="HINT-SECRET",
                    detail="DETAIL-SECRET",
                    log_message="driver is busy (sanitized)",
                )
            }
        )
        self.use_plugin_config()
        code, payload, _stderr = self.run_cli("search", registry=self.registry(plugin))
        self.assertEqual(code, 5)
        assert payload is not None
        self.assertEqual(payload["error"]["code"], "E_CLIENT_BUSY")
        log = self.log_text()
        self.assertIn("driver is busy (sanitized)", log)
        self.assertNotIn("HINT-SECRET", log)
        self.assertNotIn("DETAIL-SECRET", log)
        self.assertNotIn("Traceback", log)
        self.assertIn("code=E_CLIENT_BUSY", log)

    def test_ut_err_02_05_plugin_pii_never_reaches_the_log(self) -> None:
        """UT-ERR-02.05: hint/detail PII stays out of the log; log_message is sanitized."""
        dirty_log = "plugin failed\x00\r\n\x1b[31m at term"
        plugin = plugin_factory(
            failures={
                "query": PluginError(
                    Reason.NOT_LOCAL,
                    hint="uid 83143 file.pdf /Users/me/secret account me@example.com term invoice",
                    detail="uid 83143 file.pdf /Users/me/secret account me@example.com term invoice",
                    log_message=dirty_log,
                )
            }
        )
        self.use_plugin_config()
        code, _payload, _stderr = self.run_cli("search", registry=self.registry(plugin))
        self.assertEqual(code, 3)
        log = self.log_text()
        self.assertIn("plugin failed at term", log)
        for leaked in (
            "83143",
            "file.pdf",
            "/Users/me/secret",
            "me@example.com",
            "invoice",
            "\x00",
            "\x1b",
            "\r",
        ):
            self.assertNotIn(leaked, log)

    # -- UT-ERR-03.03 -------------------------------------------------------- #

    def test_ut_err_03_03_unexpected_core_failure_is_still_internal(self) -> None:
        """UT-ERR-03.03: a native driver's unexpected exception stays E_INTERNAL (exit 1)."""
        write_config(self.home, NATIVE_FAKE_CONFIG)
        code, payload, _stderr = self.run_cli(
            "search", backend=_MinimalNativeBackend()
        )
        self.assertEqual(code, 1)
        assert payload is not None
        self.assertEqual(payload["error"]["code"], "E_INTERNAL")
        self.assertNotEqual(payload["error"]["code"], "E_PLUGIN_FAILED")
        self.assertIn("Traceback", self.log_text())  # PRD 14: only E_INTERNAL traces

    # -- UT-ERR-04.02 -------------------------------------------------------- #

    def test_ut_err_04_02_timeout_leaves_no_partial_results_nor_state(self) -> None:
        """UT-ERR-04.02: a metadata timeout fails `new` without messages[] or state.json."""
        plugin = plugin_factory(delays={"query": 2.0})
        self.use_plugin_config()
        with mock.patch(
            "mailquery.plugins.api.METADATA_TIMEOUT_SECONDS", 0.2
        ):
            code, payload, _stderr = self.run_cli("new", registry=self.registry(plugin))
        self.assertEqual(code, 3)
        assert payload is not None
        self.assertEqual(payload["error"]["code"], "E_CLIENT_TIMEOUT")
        self.assertNotIn("messages", payload)
        self.assertNotIn("cursor", payload)
        self.assertFalse((self.home / "state.json").exists())


# UT-ERR-04 — metadata timeout (AC-17, RNF-16)
# --------------------------------------------------------------------------- #


class MetadataTimeoutTests(unittest.TestCase):
    def test_ut_err_04_01_plugin_metadata_timeout_maps_to_client_timeout(self) -> None:
        """UT-ERR-04.01: an injected short deadline fails the operation, without retries."""
        calls: list[int] = []

        def slow():
            calls.append(1)
            time.sleep(0.3)
            return []

        started = time.monotonic()
        with mock.patch("mailquery.plugins.api.METADATA_TIMEOUT_SECONDS", 0.05):
            with self.assertRaises(MailqueryError) as context:
                call_driver("query", slow, driver=DRIVER, internal=False)
        elapsed = time.monotonic() - started
        self.assertEqual(context.exception.code, "E_CLIENT_TIMEOUT")
        self.assertEqual(context.exception.exit_code, 3)
        self.assertEqual(len(calls), 1, "no automatic retry")
        self.assertLess(elapsed, 1.0, "the deadline is injected, not the 30 s default")
        self.assertIsNotNone(context.exception.log_message)

    def test_ut_err_04_03_operation_below_the_deadline_is_not_interrupted(self) -> None:
        """UT-ERR-04.03: an operation under the deadline returns its value unchanged."""
        rows = [{"uid": "A", "native_order_key": "1"}]

        def fast():
            time.sleep(0.01)
            return list(rows)

        self.assertEqual(
            call_driver("query", fast, driver=DRIVER, internal=False, timeout=0.5),
            rows,
        )

    def test_ut_err_04_04_native_metadata_operations_are_wrapped_too(self) -> None:
        """UT-ERR-04.04: the native path checks the injected deadline inline (no worker thread)."""
        main_thread = threading.get_ident()
        observed: list[int] = []

        def slow():
            observed.append(threading.get_ident())
            time.sleep(0.2)
            return []

        for driver in ("apple_mail", "outlook"):
            with self.subTest(driver=driver):
                with self.assertRaises(MailqueryError) as context:
                    call_driver(
                        "query", slow, driver=driver, internal=True, timeout=0.05
                    )
                self.assertEqual(context.exception.code, "E_CLIENT_TIMEOUT")
                self.assertEqual(context.exception.exit_code, 3)
                # Inline execution keeps the driver's SQLite/COM thread affinity.
                self.assertEqual(observed[-1], main_thread)


if __name__ == "__main__":
    unittest.main()

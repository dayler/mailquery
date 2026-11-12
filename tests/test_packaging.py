"""TC-06, PKG-01 and PKG-02: packaging metadata and version derivation (no bump).

M11 keeps the package on the current version (``mailquery.__version__``, 2.0.1):
the PRD-v2.1 features are part of a future, not-yet-released 3.0.0, so the tests
derive every expected version from the package instead of pinning a literal
(M11-T01, milestone PKG-02; plan §5.1 D15).
"""

import importlib.metadata
import re
import sys
import tomllib
import unittest
from pathlib import Path

import mailquery
from mailquery.backends.registry import BackendRegistry, package_version

from tests.fakes.plugin import FakeEntryPoint
from tests.test_smoke import version_line_regex

ROOT = Path(__file__).resolve().parent.parent
ENTRY_POINT_GROUP = "mailquery.backends"
EXPECTED_TARGETS = {
    "apple_mail": "mailquery.backends.apple_mail:AppleMailBackend",
    "outlook": "mailquery.backends.outlook:OutlookBackend",
}


def _load() -> dict:
    with open(ROOT / "pyproject.toml", "rb") as fh:
        return tomllib.load(fh)


def _installed_version() -> str | None:
    try:
        return importlib.metadata.version("mailquery")
    except importlib.metadata.PackageNotFoundError:
        return None


class PackagingTests(unittest.TestCase):
    def test_tc_06_01_version_entry_points_and_console_script(self):
        """TC-06.01: version without bump, entry point group and console script."""
        project = _load()["project"]
        self.assertEqual(project["version"], mailquery.__version__)
        self.assertFalse(mailquery.__version__.startswith("3."), "this phase does not bump to 3.x")
        self.assertEqual(
            project.get("entry-points", {}).get(ENTRY_POINT_GROUP), EXPECTED_TARGETS
        )
        self.assertEqual(project["scripts"], {"mailquery": "mailquery.cli:main"})
        self.assertGreaterEqual(self._requires_python(project["requires-python"]), (3, 11))

    @staticmethod
    def _requires_python(spec: str) -> tuple[int, int]:
        m = re.fullmatch(r"\s*>=\s*(\d+)\.(\d+)(?:\.\d+)?\s*", spec)
        assert m is not None, spec
        return int(m.group(1)), int(m.group(2))

    def test_tc_06_02_version_matches_metadata_and_entry_points_resolve(self):
        """TC-06.02: ``__version__`` matches the distribution; injected metadata resolves both drivers."""
        installed = _installed_version()
        if installed is not None:
            self.assertEqual(installed, mailquery.__version__)
        injected = [FakeEntryPoint(name, target) for name, target in EXPECTED_TARGETS.items()]
        declared = BackendRegistry(entry_points=injected, platform="darwin").declared(
            sorted(EXPECTED_TARGETS)
        )
        self.assertEqual({item["driver"] for item in declared}, set(EXPECTED_TARGETS))
        self.assertEqual({item["plugin_api"] for item in declared}, {1})

    def test_tc_06_03_no_new_runtime_dependencies(self):
        """TC-06.03: the only runtime dependency is pywin32, Windows-only."""
        deps = _load()["project"]["dependencies"]
        norm = [re.sub(r"\s+", "", d).replace("'", '"') for d in deps]
        self.assertEqual(norm, ['pywin32;sys_platform=="win32"'])


class PluginPackagingTests(unittest.TestCase):
    def test_pkg_01_01_pyproject_declares_the_backend_entry_point_group(self) -> None:
        """PKG-01.01: ``mailquery.backends`` declares apple_mail and outlook with their targets."""
        groups = _load()["project"].get("entry-points", {})
        self.assertIn(ENTRY_POINT_GROUP, groups)
        self.assertEqual(groups[ENTRY_POINT_GROUP], EXPECTED_TARGETS)

    def test_pkg_01_02_installed_metadata_matches_injected_and_static_metadata(self) -> None:
        """PKG-01.02: metadata exposes both entry points; injected metadata == static fallback."""
        injected = [
            FakeEntryPoint(name, target)
            for name, target in EXPECTED_TARGETS.items()
        ]
        with_metadata = BackendRegistry(entry_points=injected, platform="darwin")
        fallback = BackendRegistry(entry_points=[], platform="darwin")
        drivers = sorted(EXPECTED_TARGETS)
        self.assertEqual(
            {item["driver"]: item["plugin_api"] for item in with_metadata.declared(drivers)},
            {item["driver"]: item["plugin_api"] for item in fallback.declared(drivers)},
        )
        self.assertEqual(
            dict(with_metadata.versions(platform="darwin")),
            dict(fallback.versions(platform="darwin")),
        )
        installed = {
            entry.name: entry.value
            for entry in importlib.metadata.entry_points(group=ENTRY_POINT_GROUP)
        }
        if not installed:
            self.skipTest(
                "the installed mailquery distribution does not expose "
                f"{ENTRY_POINT_GROUP} (stale editable install; reinstall to exercise this case)"
            )
        self.assertEqual(installed, EXPECTED_TARGETS)

    def test_pkg_01_03_version_and_console_script_are_unchanged(self) -> None:
        """PKG-01.03: version stays in sync with ``mailquery.__version__``; console script unchanged."""
        project = _load()["project"]
        self.assertEqual(project["version"], mailquery.__version__)
        self.assertEqual(package_version(), mailquery.__version__)
        self.assertEqual(project["scripts"], {"mailquery": "mailquery.cli:main"})


class ReleasePackagingTests(unittest.TestCase):
    def test_pkg_02_01_packaging_is_ready_without_a_version_bump(self) -> None:
        """PKG-02.01: entry points/console script are final and the version is not bumped."""
        project = _load()["project"]
        self.assertEqual(project["version"], mailquery.__version__)
        self.assertEqual(project["scripts"], {"mailquery": "mailquery.cli:main"})
        self.assertEqual(project.get("entry-points", {}).get(ENTRY_POINT_GROUP), EXPECTED_TARGETS)
        self.assertFalse(mailquery.__version__.startswith("3."))
        installed = _installed_version()
        if installed is not None:
            self.assertEqual(installed, mailquery.__version__)

    def test_pkg_02_03_smoke_install_version_regex_is_derived_from_the_package(self) -> None:
        """PKG-02.03: SMOKE-INSTALL.02 accepts the current ``-v`` line without a literal version."""
        backend = "outlook" if sys.platform == "win32" else "apple_mail"
        line = (
            f"mailquery {mailquery.__version__} (backend {backend}; Python 3.14.0; "
            f"Windows 10.0.26200 AMD64; drivers: {backend} {mailquery.__version__})\n"
        )
        self.assertRegex(line, version_line_regex(backend))
        if mailquery.__version__ != "2.0.0":
            stale = (
                f"mailquery 2.0.0 (backend {backend}; Python 3.14.0; "
                f"Windows 10.0.26200 AMD64; drivers: {backend} 2.0.0)\n"
            )
            self.assertNotRegex(stale, version_line_regex(backend))


if __name__ == "__main__":
    unittest.main()

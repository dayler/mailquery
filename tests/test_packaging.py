"""TC-06 and PKG-01: pyproject.toml packaging and plugin entry points (PRD-v2.1 AC-01).

``PKG-01`` extends the 2.0.1 ``TC-06``: version/console-script stay untouched and
the ``mailquery.backends`` entry point group declares both built-in drivers
(M01-T04/T07; plan §7.2).
"""

import importlib.metadata
import re
import tomllib
import unittest
from pathlib import Path

import mailquery
from mailquery.backends.registry import BackendRegistry

from tests.fakes.plugin import FakeEntryPoint

ROOT = Path(__file__).resolve().parent.parent
ENTRY_POINT_GROUP = "mailquery.backends"
EXPECTED_TARGETS = {
    "apple_mail": "mailquery.backends.apple_mail:AppleMailBackend",
    "outlook": "mailquery.backends.outlook:OutlookBackend",
}


def _load() -> dict:
    with open(ROOT / "pyproject.toml", "rb") as fh:
        return tomllib.load(fh)


class PackagingTests(unittest.TestCase):
    def test_tc_06_01_version_matches_package(self):
        """TC-06.01: version == mailquery.__version__."""
        self.assertEqual(_load()["project"]["version"], mailquery.__version__)

    def test_tc_06_02_pywin32_dependency_marker(self):
        """TC-06.02: pywin32 dependency carries sys_platform == "win32"."""
        deps = _load()["project"]["dependencies"]
        norm = [re.sub(r"\s+", "", d).replace("'", '"') for d in deps]
        self.assertIn('pywin32;sys_platform=="win32"', norm)

    def test_tc_06_03_console_script(self):
        """TC-06.03: console script mailquery."""
        scripts = _load()["project"]["scripts"]
        self.assertEqual(scripts.get("mailquery"), "mailquery.cli:main")

    def test_tc_06_04_requires_python(self):
        """TC-06.04: requires-python >= 3.11."""
        spec = _load()["project"]["requires-python"]
        m = re.fullmatch(r"\s*>=\s*(\d+)\.(\d+)(?:\.\d+)?\s*", spec)
        self.assertIsNotNone(m, spec)
        self.assertGreaterEqual((int(m.group(1)), int(m.group(2))), (3, 11))


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
        self.assertEqual(project["version"], "2.0.1")
        self.assertEqual(project["scripts"], {"mailquery": "mailquery.cli:main"})


if __name__ == "__main__":
    unittest.main()

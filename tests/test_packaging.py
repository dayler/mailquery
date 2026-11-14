"""TC-06, PKG-01, PKG-02, PKG-03 and DOC-07: packaging, dependencies and READMEs.

``develop`` carries the development pre-release (``mailquery.__version__``, 3.0.0a0),
not yet released: the tests derive every expected version from the package
instead of pinning a literal (PKG-02).
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
CSS_INLINE_REQUIREMENT = "css-inline~=0.23.1"
ADVISORIES_URL = "https://github.com/Stranger6667/css-inline/security/advisories"


def _load() -> dict:
    with open(ROOT / "pyproject.toml", "rb") as fh:
        return tomllib.load(fh)


def _readme(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def _section(text: str, heading: str) -> str:
    """Body of the level-2 section whose heading line contains ``heading``."""
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.startswith("## ") and heading in line:
            start = index
            break
    if start is None:
        return ""
    body = []
    for line in lines[start + 1:]:
        if line.startswith("## ") or line.startswith("# "):
            break
        body.append(line)
    return "\n".join(body)


def _subsection(text: str, heading: str) -> str:
    """Body of the level-3 subsection whose heading line contains ``heading``."""
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.startswith("### ") and heading in line:
            start = index
            break
    if start is None:
        return ""
    body = []
    for line in lines[start + 1:]:
        if line.startswith("### ") or line.startswith("## "):
            break
        body.append(line)
    return "\n".join(body)


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
        self.assertEqual(mailquery.__version__.split(".")[0], "3", "develop carries the 3.x major")
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

    def test_tc_06_03_runtime_dependencies_are_css_inline_and_pywin32(self):
        """TC-06.03: the runtime dependencies are css-inline and the Windows-only pywin32."""
        deps = _load()["project"]["dependencies"]
        norm = [re.sub(r"\s+", "", d).replace("'", '"') for d in deps]
        self.assertEqual(norm, [CSS_INLINE_REQUIREMENT, 'pywin32;sys_platform=="win32"'])


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
        """PKG-02.01: entry points/console script are final and the version is the development major."""
        project = _load()["project"]
        self.assertEqual(project["version"], mailquery.__version__)
        self.assertEqual(project["scripts"], {"mailquery": "mailquery.cli:main"})
        self.assertEqual(project.get("entry-points", {}).get(ENTRY_POINT_GROUP), EXPECTED_TARGETS)
        self.assertEqual(mailquery.__version__.split(".")[0], "3")
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


class DependencyPackagingTests(unittest.TestCase):
    def test_pkg_03_01_css_inline_is_a_patch_range_without_a_platform_marker(self) -> None:
        """PKG-03.01: the css-inline entry is the literal patch range ``css-inline~=0.23.1``."""
        deps = _load()["project"]["dependencies"]
        entries = [dep for dep in deps if dep.strip().lower().startswith("css-inline")]
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(entry, CSS_INLINE_REQUIREMENT)
        self.assertNotIn("==", entry)
        self.assertNotIn(">=", entry)
        self.assertNotIn(";", entry)
        self.assertNotIn("<", entry)

    def test_pkg_03_02_pywin32_is_the_only_windows_marker(self) -> None:
        """PKG-03.02: pywin32 is the only dependency with the ``sys_platform == "win32"`` marker."""
        deps = _load()["project"]["dependencies"]
        marked = [dep for dep in deps if ";" in dep]
        self.assertEqual(marked, ['pywin32; sys_platform == "win32"'])

    def test_pkg_03_03_coverage_configuration_guards_the_suite(self) -> None:
        """PKG-03.03: the coverage tables set the 85 % gate; coverage is not a runtime dependency."""
        data = _load()
        self.assertEqual(data["tool"]["coverage"]["report"]["fail_under"], 85)
        self.assertIs(data["tool"]["coverage"]["run"]["branch"], True)
        deps = data["project"]["dependencies"]
        self.assertFalse(any("coverage" in dep for dep in deps), deps)


class ReadmeCssInlineTests(unittest.TestCase):
    def test_doc_07_01_readme_has_the_css_inline_security_update(self) -> None:
        """DOC-07.01: README.md documents the css-inline security update procedure."""
        section = _section(_readme("README.md"), "Install, upgrade and uninstall")
        body = _subsection(section, "Security update of `css-inline`")
        self.assertTrue(body)
        for command in (
            "pipx runpip mailquery show css-inline",
            'pipx runpip mailquery install --upgrade "css-inline~=0.23.1"',
            "pipx reinstall mailquery",
            'pipx runpip mailquery install "css-inline==',
        ):
            self.assertIn(command, body)
        self.assertIn(ADVISORIES_URL, body)

    def test_doc_07_02_spanish_readme_has_the_css_inline_security_update(self) -> None:
        """DOC-07.02: README.es.md documents the css-inline security update procedure."""
        section = _section(_readme("README.es.md"), "Instalar, actualizar y desinstalar")
        body = _subsection(section, "Actualización de seguridad de `css-inline`")
        self.assertTrue(body)
        for command in (
            "pipx runpip mailquery show css-inline",
            'pipx runpip mailquery install --upgrade "css-inline~=0.23.1"',
            "pipx reinstall mailquery",
            'pipx runpip mailquery install "css-inline==',
        ):
            self.assertIn(command, body)
        self.assertIn(ADVISORIES_URL, body)

    def test_doc_07_03_both_readmes_name_css_inline_where_it_is_needed(self) -> None:
        """DOC-07.03: both READMEs name css-inline in the intro, requirements and test steps."""
        for name, requirements, tests in (
            ("README.md", "Requirements", "Running the tests"),
            ("README.es.md", "Requisitos", "Ejecutar los tests"),
        ):
            text = _readme(name)
            intro = text.split("\n## ", 1)[0]
            self.assertIn("css-inline", intro, name)
            self.assertIn("css-inline", _section(text, requirements), name)
            test_steps = _section(text, tests)
            self.assertIn("css-inline", test_steps, name)
            self.assertIn("coverage run", test_steps, name)
            self.assertIn("coverage report", test_steps, name)

    def test_doc_07_04_readmes_drop_the_standard_library_only_claim(self) -> None:
        """DOC-07.04: neither README claims the tool uses the standard library only."""
        for name in ("README.md", "README.es.md"):
            flat = " ".join(_readme(name).lower().split())
            self.assertNotIn("standard library only", flat, name)
            self.assertNotIn("solo biblioteca estándar", flat, name)


if __name__ == "__main__":
    unittest.main()

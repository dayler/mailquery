"""TC-06: pyproject.toml packaging metadata (PRD 13.2, 23.4, ADR-08)."""

import re
import tomllib
import unittest
from pathlib import Path

import mailquery

ROOT = Path(__file__).resolve().parent.parent


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


if __name__ == "__main__":
    unittest.main()

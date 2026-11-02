"""Tests for the deployment scripts and the example configuration template.

These tests never install anything and never touch the real ~/.mailquery: they
validate syntax, help/plan output, the config template and the safety rules of
the installers.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
INSTALL_SH = SCRIPTS_DIR / "install.sh"
INSTALL_PS1 = SCRIPTS_DIR / "install.ps1"
INSTALL_BAT = SCRIPTS_DIR / "install.bat"
TEMPLATE = REPO_ROOT / "docs" / "config.example.toml"

SH = shutil.which("sh")
PWSH = shutil.which("pwsh") or shutil.which("powershell")


def _env(home: Path | None = None) -> dict[str, str]:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    if home is not None:
        env["HOME"] = str(home)
    return env


def _run_sh(*arguments: str, home: Path | None = None) -> subprocess.CompletedProcess[str]:
    assert SH is not None
    return subprocess.run(
        [SH, str(INSTALL_SH), *arguments],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        env=_env(home),
        timeout=60,
    )


class DeploymentFilesTest(unittest.TestCase):
    def test_expected_files_exist(self) -> None:
        for path in (INSTALL_SH, INSTALL_PS1, INSTALL_BAT, TEMPLATE):
            self.assertTrue(path.is_file(), f"missing {path}")
        self.assertTrue(os.access(INSTALL_SH, os.X_OK), "install.sh must be executable")

    def test_gitattributes_keeps_script_line_endings(self) -> None:
        content = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
        self.assertIn("*.sh text eol=lf", content)
        self.assertIn("*.ps1 text eol=crlf", content)
        self.assertIn("*.bat text eol=crlf", content)

    def test_bat_wrapper_delegates_to_powershell(self) -> None:
        content = INSTALL_BAT.read_text(encoding="utf-8")
        lowered = content.lower()
        self.assertIn("powershell", lowered)
        self.assertIn("install.ps1", content)
        self.assertIn("ERRORLEVEL", content)

    def test_ps1_exposes_expected_parameters(self) -> None:
        content = INSTALL_PS1.read_text(encoding="utf-8")
        for parameter in (
            "DryRun",
            "PrintConfig",
            "NoConfig",
            "ForceConfig",
            "Python",
            "FromGit",
            "Uninstall",
            "Purge",
        ):
            self.assertIn(f"${parameter}", content, parameter)
            self.assertIn(f"[switch]$" if parameter not in ("Python",) else "[string]$", content)


class ConfigTemplateTest(unittest.TestCase):
    def test_template_is_valid_toml_with_defaults(self) -> None:
        from mailquery.config import load_config

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            shutil.copy(TEMPLATE, home / "config.toml")
            config = load_config(home)

        self.assertEqual(config.scopes, ())
        self.assertFalse(config.has_scopes)
        self.assertEqual(config.logging.level, "info")
        self.assertEqual(config.logging.retention_days, 7)
        self.assertEqual(config.search.default_limit, 20)
        self.assertEqual(config.search.max_scan, 5000)
        self.assertEqual(config.new.default_limit, 100)
        self.assertEqual(config.new.lookback_seconds, 600)

    def test_template_has_no_active_scope_blocks(self) -> None:
        for lineno, line in enumerate(TEMPLATE.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("[scope"):
                self.assertTrue(
                    stripped.startswith("#"),
                    f"scope block must stay commented at line {lineno}: {stripped}",
                )

    def test_template_documents_every_configurable_section(self) -> None:
        content = TEMPLATE.read_text(encoding="utf-8")
        for section in ("[logging]", "[search]", "[new]", "[scope."):
            self.assertIn(section, content)


@unittest.skipUnless(SH is not None, "POSIX shell is not available")
class InstallShTest(unittest.TestCase):
    def test_syntax_is_valid(self) -> None:
        result = subprocess.run(
            [SH, "-n", str(INSTALL_SH)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_help_exits_zero(self) -> None:
        result = _run_sh("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Usage: scripts/install.sh", result.stdout)
        self.assertIn("--dry-run", result.stdout)
        self.assertIn("--print-config", result.stdout)

    def test_print_config_matches_template(self) -> None:
        result = _run_sh("--print-config")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, TEMPLATE.read_text(encoding="utf-8"))

    def test_dry_run_prints_plan_and_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            result = _run_sh("--dry-run", home=home)
            self.assertEqual(result.returncode, 0, result.stderr)
            combined = result.stdout + result.stderr
            self.assertIn("dry-run", combined.lower())
            self.assertIn("Deployment plan", combined)
            self.assertIn("config", combined)
            self.assertFalse((home / ".mailquery").exists(), "dry-run must not create the app home")

    def test_dry_run_with_no_config_mentions_skip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            result = _run_sh("--dry-run", "--no-config", home=home)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("skipped (--no-config)", result.stdout + result.stderr)

    def test_dry_run_uninstall_and_purge(self) -> None:
        result = _run_sh("--dry-run", "--uninstall", "--purge")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("uninstall", result.stderr.lower())
        self.assertIn("rm -rf", result.stderr)

    def test_unknown_option_is_usage_error(self) -> None:
        result = _run_sh("--unknown-option")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown option", result.stderr)

    def test_purge_requires_uninstall(self) -> None:
        result = _run_sh("--purge")
        self.assertEqual(result.returncode, 2)
        self.assertIn("--purge requires --uninstall", result.stderr)

    def test_force_config_rejects_no_config(self) -> None:
        result = _run_sh("--force-config", "--no-config")
        self.assertEqual(result.returncode, 2)
        self.assertIn("cannot be combined", result.stderr)

    def test_dry_run_never_overwrites_existing_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            config_dir = home / ".mailquery"
            config_dir.mkdir(parents=True)
            existing = config_dir / "config.toml"
            existing.write_text("# user config\n", encoding="utf-8")
            result = _run_sh("--dry-run", home=home)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("already exists", result.stdout + result.stderr)
            self.assertEqual(existing.read_text(encoding="utf-8"), "# user config\n")


@unittest.skipUnless(PWSH is not None, "PowerShell is not available")
class InstallPs1Test(unittest.TestCase):
    def test_script_parses(self) -> None:
        assert PWSH is not None
        command = (
            "$errors = $null; "
            "[void][System.Management.Automation.Language.Parser]::ParseFile("
            f"'{INSTALL_PS1}', [ref]$null, [ref]$errors); "
            "if ($errors.Count -gt 0) { "
            "$errors | ForEach-Object { Write-Output $_.Message }; exit 1 }"
        )
        result = subprocess.run(
            [PWSH, "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_dry_run(self) -> None:
        assert PWSH is not None
        result = subprocess.run(
            [
                PWSH,
                "-NoProfile",
                "-NonInteractive",
                "-File",
                str(INSTALL_PS1),
                "-DryRun",
                "-NoConfig",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Deployment plan", result.stdout + result.stderr)


if __name__ == "__main__":  # pragma: no cover - manual runs
    unittest.main()

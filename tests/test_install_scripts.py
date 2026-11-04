"""Tests for the deployment scripts and the example configuration template.

These tests never install anything and never touch the real ~/.mailquery: they
validate syntax, help/plan output, the config template and the safety rules of
the installers.
"""

from __future__ import annotations

import atexit
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import venv
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
INSTALL_SH = SCRIPTS_DIR / "install.sh"
INSTALL_PS1 = SCRIPTS_DIR / "install.ps1"
INSTALL_BAT = SCRIPTS_DIR / "install.bat"
TEMPLATE = REPO_ROOT / "docs" / "config.example.toml"

SH = shutil.which("sh")
PWSH = shutil.which("pwsh") or shutil.which("powershell")


# Isolation (plan 7.1): no subprocess may see the user's real home.
_ISOLATED_HOME = tempfile.mkdtemp(prefix="mailquery-test-home-")
atexit.register(shutil.rmtree, _ISOLATED_HOME, ignore_errors=True)


def _env(home: Path | None = None) -> dict[str, str]:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    isolated = str(home) if home is not None else _ISOLATED_HOME
    env["HOME"] = isolated
    env["USERPROFILE"] = isolated
    return env


def _run_sh(*arguments: str, home: Path | None = None) -> subprocess.CompletedProcess[str]:
    assert SH is not None
    return subprocess.run(
        [SH, str(INSTALL_SH), *arguments],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
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
        self.assertEqual(config.logging.max_size_mb, 10)
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
            encoding="utf-8",
            env=_env(),
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
            encoding="utf-8",
            env=_env(),
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
            encoding="utf-8",
            env=_env(),
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Deployment plan", result.stdout + result.stderr)


@unittest.skipUnless(sys.platform == "win32" and PWSH is not None, "UT-INS-01 runs only on win32 with PowerShell")
class InstallPs1FinalCheckTest(unittest.TestCase):
    """UT-INS-01: final check of install.ps1 with fake pipx and mailquery shims."""

    GOOD_VERSION = "mailquery 2.0.0 (backend outlook; Python 3.14.0; Windows 10.0.26200 AMD64)"

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.mkdtemp(prefix="mailquery-ins-")
        cls.addClassCleanup(shutil.rmtree, cls._tmp, ignore_errors=True)
        cls.venvs = Path(cls._tmp) / "venvs"
        cls.venv = cls.venvs / "mailquery"
        venv.create(cls.venv, with_pip=False)
        cls.bin = Path(cls._tmp) / "bin"
        cls.bin.mkdir()
        (cls.bin / "pipx.cmd").write_text(
            "@echo off\r\n"
            'echo pipx %*>>"%MQ_FAKE_LOG%"\r\n'
            'if "%~1"=="environment" echo %MQ_FAKE_VENVS%\r\n'
            "exit /b 0\r\n",
            encoding="ascii",
        )
        (cls.bin / "mailquery.cmd").write_text(
            "@echo off\r\n"
            'echo mailquery %*>>"%MQ_FAKE_LOG%"\r\n'
            'if "%~1"=="-v" goto version\r\n'
            "exit /b 0\r\n"
            ":version\r\n"
            "echo %MQ_FAKE_VERSION%\r\n"
            "exit /b %MQ_FAKE_VERSION_RC%\r\n",
            encoding="ascii",
        )

    def _site_packages_stub(self) -> Path:
        return self.venv / "Lib" / "site-packages" / "win32com"

    def _run(self, *, win32com_ok: bool, version: str, version_rc: int = 0):
        stub = self._site_packages_stub()
        shutil.rmtree(stub, ignore_errors=True)
        if win32com_ok:
            stub.mkdir(parents=True)
            (stub / "__init__.py").write_text("", encoding="utf-8")
        home = Path(tempfile.mkdtemp(prefix="home-", dir=self._tmp))
        log = Path(self._tmp) / "calls.log"
        log.write_text("", encoding="ascii")
        env = _env(home)
        env["PATH"] = str(self.bin) + os.pathsep + env.get("PATH", "")
        env["MQ_FAKE_LOG"] = str(log)
        env["MQ_FAKE_VENVS"] = str(self.venvs)
        env["MQ_FAKE_VERSION"] = version
        env["MQ_FAKE_VERSION_RC"] = str(version_rc)
        assert PWSH is not None
        result = subprocess.run(
            [PWSH, "-NoProfile", "-NonInteractive", "-File", str(INSTALL_PS1)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            timeout=120,
        )
        return result, home, log.read_text(encoding="ascii")

    def test_ut_ins_01_01_win32com_import_failure_is_reported(self) -> None:
        """UT-INS-01.01: import win32com fails in the venv => hint and exit != 0."""
        result, _home, _calls = self._run(win32com_ok=False, version=self.GOOD_VERSION)
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0, output)
        self.assertIn("win32com", output)
        self.assertIn("pipx reinstall mailquery", output)

    def test_ut_ins_01_02_bad_version_output_is_reported(self) -> None:
        """UT-INS-01.02: mailquery -v fails or lacks 'backend outlook' => hint and exit != 0."""
        wrong, _home, _calls = self._run(
            win32com_ok=True, version="mailquery 2.0.0 (backend apple_mail; Python 3.14.0)"
        )
        wrong_output = wrong.stdout + wrong.stderr
        self.assertNotEqual(wrong.returncode, 0, wrong_output)
        self.assertIn("pipx reinstall mailquery", wrong_output)
        failing, _home, _calls = self._run(
            win32com_ok=True, version=self.GOOD_VERSION, version_rc=1
        )
        failing_output = failing.stdout + failing.stderr
        self.assertNotEqual(failing.returncode, 0, failing_output)
        self.assertIn("pipx reinstall mailquery", failing_output)

    def test_ut_ins_01_03_success_seeds_config_with_restricted_acl(self) -> None:
        """UT-INS-01.03: everything fine => exit 0 and config.toml seeded with a restricted ACL."""
        result, home, calls = self._run(win32com_ok=True, version=self.GOOD_VERSION)
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assertNotIn("only runs on macOS", output)
        config = home / ".mailquery" / "config.toml"
        self.assertTrue(config.is_file(), output)
        self.assertEqual(config.read_text(encoding="utf-8"), TEMPLATE.read_text(encoding="utf-8"))
        acl = subprocess.run(
            ["icacls", str(config)], capture_output=True, text=True, encoding="utf-8", timeout=30
        )
        self.assertEqual(acl.returncode, 0, acl.stderr)
        self.assertNotIn("(I)", acl.stdout, "inherited ACEs must be removed")
        self.assertIn(os.environ.get("USERNAME", ""), acl.stdout)
        self.assertIn("mailquery --help", calls)
        self.assertIn("mailquery doctor", calls)


if __name__ == "__main__":  # pragma: no cover - manual runs
    unittest.main()

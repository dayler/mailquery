"""SMOKE-INSTALL / SMOKE-NEW: real install and read-only run against the host mail client.

These are the only tests that read the installed Outlook / Apple Mail (PRD 13.2, 23.2,
annex B.10). They install the package with ``pipx`` into temporary pipx dirs, run the
installed ``mailquery`` with a temporary HOME/USERPROFILE and skip (never fail) where
they do not apply: Linux, Windows without classic Outlook running, macOS without
``~/Library/Mail``.
"""

import json
import math
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REAL_HOME = Path.home()
EXE = "mailquery.exe" if sys.platform == "win32" else "mailquery"
RUNS = 20  # runs per command for the p95 budget check (PRD 19)
SLOW_RUNS = {"mailboxes": 10}  # slower command: fewer runs

# PRD 19: p95 budgets in seconds, (macOS, Windows).
BUDGET = {
    "doctor": (2.0, 3.0),
    "mailboxes": (0.15, 1.0),
    "search": (0.5, 1.0),
    "new": (0.5, 1.0),
    "show": (0.15, 0.5),
    "search_text": (3.0, 10.0),
}
BUDGET_COL = 1 if sys.platform == "win32" else 0


def _outlook_running() -> bool:
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq OUTLOOK.EXE", "/NH"],
            capture_output=True, text=True, timeout=30,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return "OUTLOOK.EXE" in out.upper()


def _skip_reason() -> str | None:
    if sys.platform == "win32":
        if not _outlook_running():
            return "classic Outlook (OUTLOOK.EXE) is not running"
    elif sys.platform == "darwin":
        if not (REAL_HOME / "Library" / "Mail").is_dir():
            return "no ~/Library/Mail"
    else:
        return "SMOKE applies only to Windows and macOS"
    if shutil.which("pipx") is None:
        return "pipx is not available"
    return None


def _snapshot(path: Path) -> dict | None:
    """Existence, listing, sizes and mtimes of a tree (None if it does not exist)."""
    if not path.exists():
        return None
    snap = {}
    for p in sorted(path.rglob("*")):
        st = p.lstat()
        snap[str(p.relative_to(path))] = (st.st_size, st.st_mtime_ns)
    st = path.lstat()
    snap["."] = (None, st.st_mtime_ns)
    return snap


def _p95(values: list[float]) -> float:
    s = sorted(values)
    return s[max(0, math.ceil(0.95 * len(s)) - 1)]


class SmokeTest(unittest.TestCase):
    """One real pipx install per class; read-only commands against the real client."""

    timings: dict[str, list[float]] = {}

    @classmethod
    def setUpClass(cls):
        reason = _skip_reason()
        if reason:
            raise unittest.SkipTest(reason)
        cls.real_mq_before = _snapshot(REAL_HOME / ".mailquery")
        cls.tmp = Path(tempfile.mkdtemp(prefix="mq-smoke-"))
        cls.addClassCleanup(shutil.rmtree, cls.tmp, ignore_errors=True)
        cls.home = cls.tmp / "home"
        cls.home.mkdir()
        cls.pipx_home = cls.tmp / "pipx-home"
        cls.pipx_bin = cls.tmp / "pipx-bin"
        cls.pipx_home.mkdir()
        cls.pipx_bin.mkdir()
        if sys.platform == "darwin":
            lib = cls.home / "Library"
            lib.mkdir()
            for name in ("Mail", "Accounts"):
                real = REAL_HOME / "Library" / name
                if real.exists():
                    os.symlink(real, lib / name)
        cls.env = dict(os.environ)
        cls.env.update({
            "HOME": str(cls.home),
            "USERPROFILE": str(cls.home),
            "PIPX_HOME": str(cls.pipx_home),
            "PIPX_BIN_DIR": str(cls.pipx_bin),
            "PYTHONUTF8": "1",
        })
        cls.env.pop("PYTHONPATH", None)
        cls.env["PATH"] = str(cls.pipx_bin) + os.pathsep + cls.env.get("PATH", "")
        cls.exe = str(cls.pipx_bin / EXE)
        cls.install = subprocess.run(
            ["pipx", "install", str(ROOT)], cwd=str(cls.tmp), env=cls.env,
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900,
        )
        if cls.install.returncode != 0:
            return  # SMOKE-INSTALL.01 reports it; the other cases fail on the missing exe
        # The first run in a fresh HOME builds the pywin32 cache (slow): not measured.
        rc, out, _, _ = cls._run(["mailboxes"])
        accounts = json.loads(out)["accounts"] if rc == 0 else []
        cls.first_account = accounts[0]["label"] if accounts else None
        if cls.first_account:
            cfg = cls.home / ".mailquery"
            cfg.mkdir(exist_ok=True)
            label = json.dumps(cls.first_account, ensure_ascii=False)
            (cfg / "config.toml").write_text(f"[scope.{label}]\n", encoding="utf-8")

    @classmethod
    def _run(cls, args, record=None):
        t0 = time.perf_counter()
        p = subprocess.run(
            [cls.exe, *args], env=cls.env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=600, cwd=str(cls.tmp),
        )
        dt = time.perf_counter() - t0
        if record:
            cls.timings.setdefault(record, []).append(dt)
        return p.returncode, p.stdout, p.stderr, dt

    def _json(self, args, command, record=None):
        rc, out, err, _ = self._run(args, record)
        self.assertEqual(rc, 0, f"{args}: exit {rc}\n{out}\n{err}")
        data = json.loads(out)
        self.assertIs(data["ok"], True)
        self.assertEqual(data["command"], command)
        self.assertIn("generated_at", data)
        self.assertEqual(out, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        return data

    def _check_list_shape(self, data):
        for key in ("count", "truncated", "hint", "warnings", "messages", "scan"):
            self.assertIn(key, data)
        self.assertEqual(data["count"], len(data["messages"]))
        for key in ("mode", "candidates", "messages_read", "duration_ms"):
            self.assertIn(key, data["scan"])
        for m in data["messages"]:
            for key in ("uid", "subject", "from", "to", "cc", "date_received", "mailbox",
                        "is_read", "body"):
                self.assertIn(key, m)

    def _counters(self):
        data = self._json(["mailboxes"], "mailboxes")
        return {m["url"]: (m["total"], m["unread"]) for m in data["mailboxes"] if m["included"]}

    def _search(self, *args):
        return self._json(["search", *args], "search")

    # --- SMOKE-INSTALL -------------------------------------------------------

    def test_smoke_install_01_pipx_install_exit_0(self):
        """SMOKE-INSTALL.01: pipx install . with temporary PIPX_HOME/PIPX_BIN_DIR => exit 0."""
        self.assertEqual(
            self.install.returncode, 0, self.install.stdout + "\n" + self.install.stderr
        )
        self.assertTrue(Path(self.exe).exists(), self.exe)

    def test_smoke_install_02_version_shows_platform_backend(self):
        """SMOKE-INSTALL.02: mailquery -v shows the platform backend (PRD 12.9)."""
        rc, out, err, _ = self._run(["-v"])
        self.assertEqual(rc, 0, err)
        backend = "outlook" if sys.platform == "win32" else "apple_mail"
        self.assertRegex(out, rf"^mailquery 2\.0\.0 \(backend {backend}; Python \d+\.\d+\.\d+; ")
        self.assertEqual(len(out.strip().splitlines()), 1)

    def test_smoke_install_03_doctor_all_checks_ok(self):
        """SMOKE-INSTALL.03: first account declared => doctor --json has every check ok=true."""
        self.assertIsNotNone(self.first_account, "mailquery mailboxes lists no account")
        data = self._json(["doctor", "--json"], "doctor", record="doctor")
        self.assertTrue(data["checks"])
        bad = [c for c in data["checks"] if c["ok"] is not True]
        self.assertEqual(bad, [])

    def test_smoke_install_04_real_mailquery_home_unchanged(self):
        """SMOKE-INSTALL.04: the user's real ~/.mailquery does not change."""
        self.assertEqual(_snapshot(REAL_HOME / ".mailquery"), self.real_mq_before)

    # --- SMOKE-NEW -----------------------------------------------------------

    def test_smoke_new_01_mailboxes_json(self):
        """SMOKE-NEW.01: mailboxes => exit 0 and PRD 12.5 JSON."""
        data = self._json(["mailboxes"], "mailboxes", record="mailboxes")
        for key in ("accounts", "mailboxes", "excluded_stores", "warnings"):
            self.assertIn(key, data)
        self.assertTrue(any(m["included"] for m in data["mailboxes"]))
        self.assertTrue(any(a["declared"] for a in data["accounts"]))

    def test_smoke_new_02_new_json(self):
        """SMOKE-NEW.02: new => exit 0 and PRD 12.5 JSON."""
        data = self._json(["new"], "new", record="new")
        self._check_list_shape(data)
        self.assertIn("cursor", data)
        self.assertIn("previous", data["cursor"])
        self.assertIn("current", data["cursor"])

    def test_smoke_new_03_search_since_1w_json(self):
        """SMOKE-NEW.03: search --since 1w => exit 0 and PRD 12.5 JSON."""
        data = self._json(["search", "--since", "1w"], "search", record="search")
        self._check_list_shape(data)

    def test_smoke_new_04_search_text_json(self):
        """SMOKE-NEW.04: search --text "*e*" --since 1d => exit 0 and PRD 12.5 JSON."""
        data = self._json(["search", "--text", "*e*", "--since", "1d"], "search")
        self._check_list_shape(data)
        self.assertEqual(data["scan"]["mode"], "text")

    def test_smoke_new_05_show_json(self):
        """SMOKE-NEW.05: show <messages[0].uid of the search> => exit 0 and PRD 12.5 JSON."""
        found = self._search("--since", "1w")
        self.assertTrue(found["messages"], "no message in the last week to show")
        uid = found["messages"][0]["uid"]
        data = self._json(["show", str(uid)], "show", record="show")
        self.assertIn("message", data)
        self.assertEqual(data["message"]["uid"], uid)
        self.assertIn("warnings", data)

    def test_smoke_new_06_unread_counters_unchanged(self):
        """SMOKE-NEW.06: per included folder, unread_after - unread_before == total_after - total_before."""
        # Mail arriving during the test is unread and raises both counters by the same
        # amount; a message marked as read by the tool would lower unread alone.
        before = self._counters()
        self.assertTrue(before)
        self._json(["new"], "new")
        self._json(["search", "--since", "1w"], "search")
        self._json(["doctor", "--json"], "doctor")
        after = self._counters()
        self.assertTrue(set(after) == set(before), "the included folders changed")
        print(
            f"\nSMOKE counters: {len(before)} included folders, total before="
            f"{sum(t for t, _ in before.values())} after={sum(t for t, _ in after.values())}, "
            f"unread before={sum(u for _, u in before.values())} "
            f"after={sum(u for _, u in after.values())}"
        )
        for url, (total_before, unread_before) in before.items():
            total_after, unread_after = after[url]
            with self.subTest(folder=sorted(before).index(url)):
                self.assertEqual(unread_after - unread_before, total_after - total_before)

    def test_smoke_new_07_within_p95_budget(self):
        """SMOKE-NEW.07: doctor and every command within the PRD 19 budget of the platform."""
        found = self._search("--since", "1w")
        self.assertTrue(found["messages"], "no message in the last week to show")
        uid = str(found["messages"][0]["uid"])
        text = self._json(["search", "--text", "*e*", "--since", "1d"], "search")
        commands = {
            "doctor": ["doctor", "--json"],
            "mailboxes": ["mailboxes"],
            "search": ["search", "--since", "1w"],
            "new": ["new"],
            "show": ["show", uid],
        }
        if text["scan"]["candidates"] <= 500:
            commands["search_text"] = ["search", "--text", "*e*", "--since", "1d"]
        # Orchestrator decision: PRD 19 budgets are per OPERATION and the macOS ones were
        # validated in-process (annex A.9), so they exclude interpreter start and the pipx
        # launcher. The asserted value is therefore the operation time the CLI logs as
        # ``duration_ms`` in the ``event=end`` line of the run (backend connection + work);
        # ``doctor`` logs no duration_ms, so its wall-time p95 is asserted. Wall-time
        # min/median/p95 are printed for information only.
        log_path = self.home / ".mailquery" / "logs" / "mailquery.log"

        def end_durations(command):
            if not log_path.exists():
                return []
            found = []
            for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
                if f"event=end command={command} " in line and " duration_ms=" in line:
                    found.append(int(line.rsplit(" duration_ms=", 1)[1].split()[0]))
            return found

        summary = {}
        rows = []
        for name, args in commands.items():
            runs = SLOW_RUNS.get(name, RUNS)
            command = args[0]
            op_times = []
            for _ in range(runs):
                before = len(end_durations(command))
                rc, out, err, _ = self._run(args, record=name)
                self.assertEqual(rc, 0, f"{args}: {out}\n{err}")
                if name != "doctor":
                    after = end_durations(command)
                    self.assertEqual(len(after), before + 1, f"{args}: no new event=end line")
                    op_times.append(after[-1] / 1000.0)
            wall = self.timings[name][-runs:]
            asserted = wall if name == "doctor" else op_times
            summary[name] = _p95(asserted)
            op = (
                f"op p95={summary[name]:.3f}s"
                if op_times else "op p95=n/a (no duration_ms)"
            )
            rows.append(
                f"  {name:<12} n={runs:<3} {op} budget<{BUDGET[name][BUDGET_COL]}s | "
                f"wall min={min(wall):.3f}s median={statistics.median(wall):.3f}s "
                f"p95={_p95(wall):.3f}s"
            )
        print(
            "\nSMOKE budgets (asserted: logged operation time duration_ms, nearest-rank "
            "p95, doctor = wall time; PRD 19):\n" + "\n".join(rows)
        )
        for name, t in summary.items():
            with self.subTest(command=name):
                self.assertLess(t, BUDGET[name][BUDGET_COL])
        self.assertEqual(_snapshot(REAL_HOME / ".mailquery"), self.real_mq_before)


if __name__ == "__main__":
    unittest.main()

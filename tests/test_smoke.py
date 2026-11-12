"""SMOKE-INSTALL / SMOKE-NEW: real install and read-only run against the host mail client.

These are the only tests that read the installed Outlook / Apple Mail (PRD 13.2, 23.2,
annex B.10). They install the package with ``pipx`` into temporary pipx dirs, run the
installed ``mailquery`` with a temporary HOME/USERPROFILE and skip (never fail) where
they do not apply: Linux, Windows without classic Outlook running, macOS without an
Apple Mail store (V9/V10/V11) under ``~/Library/Mail`` or with no account that exposes
an included mailbox.
"""

import hashlib
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import mailquery

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


def version_line_regex(backend: str) -> str:
    """Regex of the current ``mailquery -v`` line (M11: derived from ``__version__``).

    The line keeps the base prefix, the native ``backend <driver>`` and the additive
    ``; drivers: <driver> <version>, ...`` part (PRD §12.9); the expected version
    is always ``mailquery.__version__`` so the tests never pin a literal.
    """
    version = re.escape(mailquery.__version__)
    return (
        rf"^mailquery {version} \(backend {backend}; Python \d+\.\d+\.\d+; "
        rf".+; drivers: .*\b{backend} {version}\)\n?$"
    )


def _outlook_running() -> bool:
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq OUTLOOK.EXE", "/NH"],
            capture_output=True, text=True, timeout=30,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return "OUTLOOK.EXE" in out.upper()


def _apple_mail_store_missing(mail_root: Path) -> bool:
    """True when ``mail_root`` holds no supported store (V9/V10/V11 with an Envelope Index).

    A ``~/Library/Mail`` without a store (e.g. the GitHub macOS runner) is not an Apple
    Mail host. A listing denied by TCC is *not* treated as missing: the store may be
    there and the failure (no Full Disk Access) must surface.
    """
    try:
        entries = list(mail_root.iterdir())
    except PermissionError:
        return False
    except OSError:
        return True
    for entry in entries:
        if entry.name in ("V9", "V10", "V11"):
            try:
                if (entry / "MailData" / "Envelope Index").is_file():
                    return False
            except PermissionError:
                return False
            except OSError:
                continue
    return True


def _skip_reason() -> str | None:
    if sys.platform == "win32":
        if not _outlook_running():
            return "classic Outlook (OUTLOOK.EXE) is not running"
    elif sys.platform == "darwin":
        if _apple_mail_store_missing(REAL_HOME / "Library" / "Mail"):
            return "no Apple Mail store (V9/V10/V11) under ~/Library/Mail"
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


def _sha256(path: Path) -> str:
    """SHA-256 of a file (SMOKE-ATT)."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
        # The first account of the client is not always a usable scope (macOS lists
        # "On My Device" first and it has no INBOX): declare accounts in order until one
        # exposes an included mailbox, so the SMOKE-NEW cases never run on empty data.
        cls.first_account = None
        rc, out, _, _ = cls._run(["mailboxes"])
        if rc != 0:
            return  # leave first_account None: the SMOKE cases surface the CLI error
        for account in json.loads(out)["accounts"]:
            cfg = cls.home / ".mailquery"
            cfg.mkdir(exist_ok=True)
            label = json.dumps(account["label"], ensure_ascii=False)
            (cfg / "config.toml").write_text(f"[scope.{label}]\n", encoding="utf-8")
            rc, out, _, _ = cls._run(["mailboxes"])
            if rc != 0:
                return  # a scope that errors must surface, not be skipped
            if any(m["included"] for m in json.loads(out)["mailboxes"]):
                cls.first_account = account["label"]
                break
        else:
            raise unittest.SkipTest(
                "no account exposes an included mailbox "
                "(declare one in ~/.mailquery/config.toml)"
            )

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
        """SMOKE-INSTALL.02: mailquery -v shows the platform backend and the current version."""
        rc, out, err, _ = self._run(["-v"])
        self.assertEqual(rc, 0, err)
        backend = "outlook" if sys.platform == "win32" else "apple_mail"
        self.assertRegex(out, version_line_regex(backend))
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


# --------------------------------------------------------------------------- #
# SMOKE-ATT-OL — real Outlook attachment recovery (Windows host, M10)
# --------------------------------------------------------------------------- #


class SmokeAttOutlook(unittest.TestCase):
    """SMOKE-ATT-OL: recover one real local attachment through the COM exception.

    Runs only on a Windows host with classic Outlook running and ``pipx``
    available (the same rules as SMOKE-NEW); everywhere else the class is
    skipped. It recovers one attachment of a message that already holds local
    content — it never asks Outlook to download anything — and checks the file,
    the cache hit and the read-only store counters.
    """

    @classmethod
    def setUpClass(cls) -> None:
        if sys.platform != "win32":
            raise unittest.SkipTest(
                "SMOKE-ATT-OL runs only on Windows with classic Outlook"
            )
        if not _outlook_running():
            raise unittest.SkipTest("classic Outlook (OUTLOOK.EXE) is not running")
        if shutil.which("pipx") is None:
            raise unittest.SkipTest("pipx is not available")
        cls.real_mq_before = _snapshot(REAL_HOME / ".mailquery")
        cls.tmp = Path(tempfile.mkdtemp(prefix="mq-smoke-att-ol-"))
        cls.addClassCleanup(shutil.rmtree, cls.tmp, ignore_errors=True)
        cls.home = cls.tmp / "home"
        cls.home.mkdir()
        cls.pipx_home = cls.tmp / "pipx-home"
        cls.pipx_bin = cls.tmp / "pipx-bin"
        cls.pipx_home.mkdir()
        cls.pipx_bin.mkdir()
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
            ["pipx", "install", str(ROOT)],
            cwd=str(cls.tmp),
            env=cls.env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=900,
        )
        if cls.install.returncode != 0:
            return
        cls.scope_account = cls._declare_first_usable_account()

    @classmethod
    def _run(cls, args):
        return subprocess.run(
            [cls.exe, *args],
            env=cls.env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
            cwd=str(cls.tmp),
        )

    @classmethod
    def _declare_first_usable_account(cls):
        """Declare accounts in order until one exposes an included mailbox."""
        rc = cls._run(["mailboxes"]).returncode
        if rc != 0:
            return None
        listed = json.loads(cls._run(["mailboxes"]).stdout)
        for account in listed["accounts"]:
            config = cls.home / ".mailquery"
            config.mkdir(exist_ok=True)
            label = json.dumps(account["label"], ensure_ascii=False)
            (config / "config.toml").write_text(
                f"[scope.{label}]\n", encoding="utf-8"
            )
            result = cls._run(["mailboxes"])
            if result.returncode != 0:
                return None
            if any(m["included"] for m in json.loads(result.stdout)["mailboxes"]):
                return account["label"]
        return None

    def _json(self, args, command):
        result = self._run(args)
        self.assertEqual(result.returncode, 0, f"{args}: {result.stdout}\n{result.stderr}")
        payload = json.loads(result.stdout)
        self.assertIs(payload["ok"], True)
        self.assertEqual(payload["command"], command)
        self.assertIn("generated_at", payload)
        return payload

    def _attachment_uid(self) -> str:
        self.assertIsNotNone(self.scope_account, "no declared account exposes a mailbox")
        messages = self._json(["search", "--has-attachments", "--limit", "5"], "search")["messages"]
        self.assertTrue(messages, "no message with attachments in the declared scope")
        return messages[0]["uid"]

    def test_smoke_att_ol_01_recovers_a_local_attachment(self) -> None:
        """SMOKE-ATT-OL.01: attachment --index 1 => exit 0, JSON contract, file written."""
        uid = self._attachment_uid()
        payload = self._json(["attachment", uid, "--index", "1"], "attachment")
        self.assertEqual(payload["count"], 1)
        record = payload["attachments"][0]
        self.assertIs(record["saved"], True)
        path = Path(record["path"])
        self.assertTrue(path.is_file(), path)
        self.assertEqual(record["size_bytes"], path.stat().st_size)
        self.assertGreater(record["size_bytes"], 0)
        self.assertEqual(record["sha256"], _sha256(path))
        self.assertEqual(_snapshot(REAL_HOME / ".mailquery"), self.real_mq_before)

    def test_smoke_att_ol_02_second_run_is_a_cache_hit(self) -> None:
        """SMOKE-ATT-OL.02: a second run returns cached:true with the same sha256."""
        uid = self._attachment_uid()
        first = self._json(["attachment", uid, "--index", "1"], "attachment")["attachments"][0]
        second = self._json(["attachment", uid, "--index", "1"], "attachment")["attachments"][0]
        self.assertIs(second["cached"], True)
        self.assertEqual(second["sha256"], first["sha256"])
        self.assertEqual(second["path"], first["path"])

    def test_smoke_att_ol_03_store_counters_are_unchanged(self) -> None:
        """SMOKE-ATT-OL.03: recovering attachments leaves the included folders untouched."""
        uid = self._attachment_uid()
        before = {
            m["url"]: (m["total"], m["unread"])
            for m in self._json(["mailboxes"], "mailboxes")["mailboxes"]
            if m["included"]
        }
        self._json(["attachment", uid, "--index", "1"], "attachment")
        after = {
            m["url"]: (m["total"], m["unread"])
            for m in self._json(["mailboxes"], "mailboxes")["mailboxes"]
            if m["included"]
        }
        self.assertEqual(after, before)
        self.assertEqual(_snapshot(REAL_HOME / ".mailquery"), self.real_mq_before)


# --------------------------------------------------------------------------- #
# SMOKE-ATT-AM — real Apple Mail attachment recovery (macOS only, read-only)
# --------------------------------------------------------------------------- #


def _attachment_smoke_skip_reason(
    platform: str | None = None,
    *,
    mail_root: Path | None = None,
    pipx_available: bool | None = None,
) -> str | None:
    """Reason to skip SMOKE-ATT-AM, or ``None`` when it can run (pure helper)."""
    current = sys.platform if platform is None else platform
    if current != "darwin":
        return f"SMOKE-ATT-AM applies only to macOS (this host is {current})"
    root = (REAL_HOME / "Library" / "Mail") if mail_root is None else mail_root
    if _apple_mail_store_missing(root):
        return "no Apple Mail store (V9/V10/V11) under ~/Library/Mail"
    available = shutil.which("pipx") is not None if pipx_available is None else pipx_available
    if not available:
        return "pipx is not available"
    return None


class SmokeAttAppleMail(unittest.TestCase):
    """SMOKE-ATT-AM: recover one real local Apple Mail attachment (read-only).

    It installs the package with ``pipx`` into temporary dirs, declares the first
    account that exposes an included mailbox and scans ``search --has-attachments``
    for a message whose attachment index 1 can be recovered locally. The cache is
    cleared before the cases so .02 is a real first extraction. If no recoverable
    local attachment exists the class skips with a documented reason (never fails).
    """

    @classmethod
    def setUpClass(cls) -> None:
        reason = _attachment_smoke_skip_reason()
        if reason:
            raise unittest.SkipTest(reason)
        cls.real_mq_before = _snapshot(REAL_HOME / ".mailquery")
        cls.tmp = Path(tempfile.mkdtemp(prefix="mq-smoke-att-"))
        cls.addClassCleanup(shutil.rmtree, cls.tmp, ignore_errors=True)
        cls.home = cls.tmp / "home"
        cls.home.mkdir()
        cls.pipx_home = cls.tmp / "pipx-home"
        cls.pipx_bin = cls.tmp / "pipx-bin"
        cls.pipx_home.mkdir()
        cls.pipx_bin.mkdir()
        lib = cls.home / "Library"
        lib.mkdir()
        for name in ("Mail", "Accounts"):
            real = REAL_HOME / "Library" / name
            if real.exists():
                os.symlink(real, lib / name)
        cls.env = dict(os.environ)
        cls.env.update(
            {
                "HOME": str(cls.home),
                "USERPROFILE": str(cls.home),
                "PIPX_HOME": str(cls.pipx_home),
                "PIPX_BIN_DIR": str(cls.pipx_bin),
                "PYTHONUTF8": "1",
            }
        )
        cls.env.pop("PYTHONPATH", None)
        cls.env["PATH"] = str(cls.pipx_bin) + os.pathsep + cls.env.get("PATH", "")
        cls.exe = str(cls.pipx_bin / EXE)
        cls.install = subprocess.run(
            ["pipx", "install", str(ROOT)],
            cwd=str(cls.tmp),
            env=cls.env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=900,
        )
        if cls.install.returncode != 0:
            raise unittest.SkipTest("pipx install failed (see SMOKE-INSTALL.01)")
        rc, out, _err = cls._run(["mailboxes"])
        if rc != 0:
            raise unittest.SkipTest("mailquery mailboxes failed on the real store")
        account = None
        for candidate in json.loads(out)["accounts"]:
            cfg = cls.home / ".mailquery"
            cfg.mkdir(exist_ok=True)
            label = json.dumps(candidate["label"], ensure_ascii=False)
            (cfg / "config.toml").write_text(f"[scope.{label}]\n", encoding="utf-8")
            rc, out, _err = cls._run(["mailboxes"])
            if rc != 0:
                raise unittest.SkipTest("a declared account failed on the real store")
            if any(mailbox["included"] for mailbox in json.loads(out)["mailboxes"]):
                account = candidate["label"]
                break
        if account is None:
            raise unittest.SkipTest("no account exposes an included mailbox")
        cls.account = account
        cls.uid = None
        rc, out, _err = cls._run(
            ["search", "--has-attachments", "--since", "1y", "--limit", "50"]
        )
        if rc == 0:
            for message in json.loads(out)["messages"]:
                uid = message["uid"]
                rc, shown, _err = cls._run(["show", uid])
                if rc != 0:
                    continue
                attachments = json.loads(shown).get("message", {}).get("attachments") or []
                if not attachments:
                    continue
                rc, _out, _err = cls._run(["attachment", uid, "--index", "1"])
                if rc == 0:
                    cls.uid = uid
                    cls.attachments = attachments
                    break
        if cls.uid is None:
            raise unittest.SkipTest(
                "no locally recoverable attachment found in the last year "
                "(not_local/blocked/S-MIME only): best-effort SMOKE, documented skip"
            )
        # Clear the cache so .02 exercises a real first extraction.
        shutil.rmtree(cls.home / ".mailquery" / "attachments", ignore_errors=True)

    @classmethod
    def _run(cls, args) -> tuple[int, str, str]:
        result = subprocess.run(
            [cls.exe, *args],
            env=cls.env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
            cwd=str(cls.tmp),
        )
        return result.returncode, result.stdout, result.stderr

    @classmethod
    def _json(cls, args) -> dict:
        rc, out, err = cls._run(args)
        assert rc == 0, f"{args}: exit {rc}\n{out}\n{err}"
        data = json.loads(out)
        assert data["ok"] is True, data
        return data

    def _recover(self) -> dict:
        rc, out, err = self._run(["attachment", self.uid, "--index", "1"])
        self.assertEqual(rc, 0, f"{out}\n{err}")
        payload = json.loads(out)
        self.assertIs(payload["ok"], True)
        return payload

    def test_smoke_att_am_01_show_lists_the_local_attachment(self) -> None:
        """SMOKE-ATT-AM.01: show <uid> ⇒ exit 0 and attachments[] with index/name."""
        payload = self._json(["show", str(self.uid)])
        attachments = payload["message"]["attachments"]
        self.assertTrue(attachments)
        self.assertEqual(attachments[0]["index"], 1)
        self.assertIsInstance(attachments[0]["name"], str)
        self.assertTrue(attachments[0]["name"])
        # show never writes: the cache directory must not exist yet.
        self.assertFalse((self.home / ".mailquery" / "attachments").exists())

    def test_smoke_att_am_02_attachment_recovers_the_local_file(self) -> None:
        """SMOKE-ATT-AM.02: attachment --index 1 ⇒ saved 0600 file; sha256 and store unchanged."""
        source = self._json(["show", str(self.uid)])["message"]["source"]["emlx_path"]
        before = _snapshot(Path(source).parent) if source else None
        payload = self._recover()
        entry = payload["attachments"][0]
        self.assertIs(entry["cached"], False)
        path = Path(entry["path"])
        self.assertTrue(path.is_file())
        self.assertTrue(str(path).startswith(str(self.home / ".mailquery" / "attachments")))
        if os.name == "posix":
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), entry["sha256"])
        self.assertEqual(path.stat().st_size, entry["size_bytes"])
        if source and before is not None:
            self.assertEqual(_snapshot(Path(source).parent), before, "the .emlx folder changed")

    def test_smoke_att_am_03_second_run_is_a_cache_hit(self) -> None:
        """SMOKE-ATT-AM.03: the second attachment run returns cached:true (no time budget)."""
        first = self._recover()
        second = self._recover()
        self.assertIs(second["attachments"][0]["cached"], True)
        self.assertEqual(
            second["attachments"][0]["sha256"], first["attachments"][0]["sha256"]
        )
        self.assertEqual(
            second["attachments"][0]["path"], first["attachments"][0]["path"]
        )
        self.assertEqual(_snapshot(REAL_HOME / ".mailquery"), self.real_mq_before)

    def test_smoke_att_am_04_skip_reason_is_documented(self) -> None:
        """SMOKE-ATT-AM.04: non-macOS hosts have a documented skip reason (never a failure)."""
        self.assertIn("macOS", _attachment_smoke_skip_reason("linux"))
        self.assertIn("macOS", _attachment_smoke_skip_reason("win32"))

if __name__ == "__main__":
    unittest.main()

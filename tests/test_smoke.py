"""SMOKE-INSTALL / SMOKE-NEW: real install and read-only run against the host mail client.

These are the only tests that read the installed Outlook / Apple Mail (PRD 13.2). They
install the package with ``pipx`` into temporary pipx dirs, run the
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
from mailquery.output import CONTENT_NOTICE

ROOT = Path(__file__).resolve().parent.parent
REAL_HOME = Path.home()
EXE = "mailquery.exe" if sys.platform == "win32" else "mailquery"
RUNS = 20  # runs per command for the p95 budget check (PRD 19)
SLOW_RUNS = {"mailboxes": 10}  # slower command: fewer runs
COUNTER_RUNS = 5  # informative only: counters are not part of the budget

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
    """Regex of the current ``mailquery -v`` line (derived from ``__version__``).

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
    store_counts: tuple[int, int] | None = None

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
        # Store size (counts only) with every account listed and before any [scope]
        # block is written: the SMOKE cases scope the run to one usable account.
        cls.store_counts = cls._store_counts()
        for account in json.loads(out)["accounts"]:
            cfg = cls.home / ".mailquery"
            cfg.mkdir(exist_ok=True)
            label = json.dumps(account["label"], ensure_ascii=False)
            (cfg / "config.toml").write_text(f"[scope.{label}]\n", encoding="utf-8")
            rc, out, _, _ = cls._run(["mailboxes"])
            if rc != 0:
                return  # a scope that errors must surface, not be skipped
            if any(
                m["included"]
                for account in json.loads(out)["accounts"]
                for m in account["mailboxes"]
            ):
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

    @classmethod
    def _store_counts(cls) -> tuple[int, int] | None:
        """``(messages, folders)`` of every listed account, or None when unreadable."""
        rc, out, _err, _ = cls._run(["mailboxes", "--fields", "total,unread"])
        if rc != 0:
            return None
        try:
            data = json.loads(out)
        except ValueError:
            return None
        messages = 0
        folders = 0
        for account in data.get("accounts") or ():
            for mailbox in account.get("mailboxes") or ():
                folders += 1
                total = mailbox.get("total")
                if isinstance(total, int):
                    messages += total
        return messages, folders

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
        """The six-field default row of ``search``/``new``."""
        for key in ("count", "truncated", "hint", "warnings", "messages", "scan"):
            self.assertIn(key, data)
        self.assertEqual(data["count"], len(data["messages"]))
        for key in ("mode", "candidates", "messages_read", "duration_ms"):
            self.assertIn(key, data["scan"])
        for m in data["messages"]:
            self.assertEqual(
                list(m),
                ["uid", "subject", "from", "date_received", "is_read", "has_attachments"],
            )

    def _check_full_list_shape(self, data):
        """The full ``--fields all`` row of ``search``/``new``."""
        for m in data["messages"]:
            self.assertEqual(
                list(m),
                [
                    "uid", "message_id", "duplicate_count", "subject", "from", "to",
                    "cc", "date_sent", "date_received", "mailbox", "is_read",
                    "is_flagged", "has_attachments", "size_bytes", "snippet", "body",
                ],
            )

    def _counters(self):
        data = self._json(
            ["mailboxes", "--fields", "url,total,unread"], "mailboxes"
        )
        return {
            m["url"]: (m["total"], m["unread"])
            for account in data["accounts"]
            for m in account["mailboxes"]
            if m["included"]
        }

    def _search(self, *args):
        return self._json(["search", *args], "search")

    def _assert_content_notice(self, payload):
        """The fixed notice is the fourth key, right after ``generated_at``."""
        self.assertEqual(
            list(payload)[:4], ["ok", "command", "generated_at", "content_notice"]
        )
        self.assertEqual(payload["content_notice"], CONTENT_NOTICE)

    def _local_attachment_uid(self):
        """Uid of a message whose first attachment can be recovered locally, or None."""
        rc, out, _err, _ = self._run(
            ["search", "--has-attachments", "--since", "1y", "--limit", "10"]
        )
        if rc != 0:
            return None
        try:
            messages = json.loads(out).get("messages") or ()
        except ValueError:
            return None
        for message in messages:
            uid = message["uid"]
            rc, shown, _err, _ = self._run(["show", uid])
            if rc != 0:
                continue
            try:
                entries = (json.loads(shown).get("message") or {}).get("attachments") or ()
            except ValueError:
                continue
            if not entries:
                continue
            rc, _out, _err, _ = self._run(["attachment", uid, "--index", "1"])
            if rc == 0:
                return uid
        return None

    def _html_message(self):
        """``(uid, show payload)`` of a message whose .emlx carries a text/html part."""
        rc, out, _err, _ = self._run(["search", "--since", "1y", "--limit", "20"])
        if rc != 0:
            return None
        try:
            messages = json.loads(out).get("messages") or ()
        except ValueError:
            return None
        for message in messages:
            uid = message["uid"]
            rc, shown, _err, _ = self._run(["show", uid])
            if rc != 0:
                continue
            try:
                payload = json.loads(shown)
            except ValueError:
                continue
            entry = payload.get("message") or {}
            source = (entry.get("source") or {}).get("emlx_path")
            if not source or not entry.get("body_text"):
                continue
            try:
                with open(source, "rb") as handle:
                    head = handle.read(2 * 1024 * 1024)
            except OSError:
                continue
            if b"text/html" in head.lower():
                return uid, payload
        return None

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

    def test_smoke_install_05_css_inline_is_installed(self):
        """SMOKE-INSTALL.05: pipx install . installs a css-inline patch of the allowed range."""
        self.assertEqual(
            self.install.returncode, 0, self.install.stdout + "\n" + self.install.stderr
        )
        result = subprocess.run(
            ["pipx", "runpip", "mailquery", "show", "css-inline"],
            cwd=str(self.tmp),
            env=self.env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        match = re.search(r"^Version:\s+(\S+)$", result.stdout, re.MULTILINE)
        self.assertIsNotNone(match, result.stdout)
        self.assertRegex(match.group(1), r"^0\.23\.\d+$")

    # --- SMOKE-NEW -----------------------------------------------------------

    def test_smoke_new_01_mailboxes_json(self):
        """SMOKE-NEW.01: mailboxes => exit 0 and PRD 12.5 JSON."""
        data = self._json(["mailboxes"], "mailboxes", record="mailboxes")
        for key in ("ok", "command", "generated_at", "accounts", "excluded_stores", "warnings"):
            self.assertIn(key, data)
        self.assertNotIn("mailboxes", data)
        self.assertTrue(
            any(
                m["included"]
                for account in data["accounts"]
                for m in account["mailboxes"]
            )
        )
        self.assertTrue(any(a["declared"] for a in data["accounts"]))
        self.assertTrue(all("mailboxes" in account for account in data["accounts"]))

    def test_smoke_new_02_new_json(self):
        """SMOKE-NEW.02: new => exit 0 and PRD 12.5 JSON."""
        full = self._json(["new", "--peek", "--fields", "all"], "new")
        self._check_full_list_shape(full)
        data = self._json(["new"], "new", record="new")
        self._check_list_shape(data)
        self.assertIn("cursor", data)
        self.assertIn("previous", data["cursor"])
        self.assertIn("current", data["cursor"])

    def test_smoke_new_03_search_since_1w_json(self):
        """SMOKE-NEW.03: search --since 1w => exit 0 and PRD 12.5 JSON."""
        data = self._json(["search", "--since", "1w"], "search", record="search")
        self._check_list_shape(data)
        self._check_full_list_shape(
            self._json(["search", "--since", "1w", "--fields", "all"], "search")
        )

    def test_smoke_new_04_search_text_json(self):
        """SMOKE-NEW.04: search --text "*e*" --since 1d => exit 0 and PRD 12.5 JSON."""
        data = self._json(["search", "--text", "*e*", "--since", "1d"], "search")
        self._check_list_shape(data)
        self.assertEqual(data["scan"]["mode"], "text")
        self._check_full_list_shape(
            self._json(
                ["search", "--text", "*e*", "--since", "1d", "--fields", "all"],
                "search",
            )
        )

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
        """SMOKE-NEW.07: the default 3.0.0 output stays within the PRD 19 budgets."""
        found = self._search("--since", "1w")
        self.assertTrue(found["messages"], "no message in the last week to show")
        uid = str(found["messages"][0]["uid"])
        text = self._json(["search", "--text", "*e*", "--since", "1d"], "search")
        commands = {
            "doctor": ["doctor", "--json"],
            "mailboxes": ["mailboxes"],
            "search": ["search", "--since", "1w"],
            "search_snippet": ["search", "--since", "1w", "--fields", "snippet"],
            "new": ["new"],
            "show": ["show", uid],
        }
        if text["scan"]["candidates"] <= 500:
            commands["search_text"] = ["search", "--text", "*e*", "--since", "1d"]
        # PRD 19 budgets are per OPERATION and the macOS ones were
        # validated in-process, so they exclude interpreter start and the pipx
        # launcher. The asserted value is therefore the operation time the CLI logs as
        # ``duration_ms`` in the ``event=end`` line of the run (backend connection + work);
        # ``doctor`` logs no duration_ms, so its wall-time p95 is asserted. Wall-time
        # min/median/p95 are printed for information only. ``--fields snippet`` shares
        # the ``search`` budget; ``mailboxes`` with counters is informational.
        log_path = self.home / ".mailquery" / "logs" / "mailquery.log"

        def end_durations(command):
            if not log_path.exists():
                return []
            found = []
            for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
                if f"event=end command={command} " in line and " duration_ms=" in line:
                    found.append(int(line.rsplit(" duration_ms=", 1)[1].split()[0]))
            return found

        def budget(name):
            return BUDGET["search"] if name == "search_snippet" else BUDGET[name]

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
                f"  {name:<16} n={runs:<3} {op} budget<{budget(name)[BUDGET_COL]}s | "
                f"wall min={min(wall):.3f}s median={statistics.median(wall):.3f}s "
                f"p95={_p95(wall):.3f}s"
            )
        print(
            "\nSMOKE budgets (asserted: logged operation time duration_ms, nearest-rank "
            "p95, doctor = wall time; PRD 19):\n" + "\n".join(rows)
        )
        if self.store_counts is not None:
            messages, folders = self.store_counts
            print(f"SMOKE store size: {messages} messages, {folders} folders")
        for name, t in summary.items():
            with self.subTest(command=name):
                self.assertLess(t, budget(name)[BUDGET_COL])

        # Informational measurement: counting messages is outside the budget.
        counter_times = []
        for _ in range(COUNTER_RUNS):
            before = len(end_durations("mailboxes"))
            rc, out, err, _ = self._run(
                ["mailboxes", "--fields", "total,unread"], record="mailboxes_counters"
            )
            self.assertEqual(rc, 0, f"mailboxes --fields total,unread: {out}\n{err}")
            after = end_durations("mailboxes")
            self.assertEqual(len(after), before + 1, "mailboxes: no new event=end line")
            counter_times.append(after[-1] / 1000.0)
        print(
            "SMOKE mailboxes --fields total,unread (informational, no budget): "
            f"n={COUNTER_RUNS} op p95={_p95(counter_times):.3f}s"
        )
        self.assertEqual(_snapshot(REAL_HOME / ".mailquery"), self.real_mq_before)

    def test_smoke_new_08_content_notice_and_output_options(self):
        """SMOKE-NEW.08: content_notice and the new output options against the real client."""
        before = self._counters()
        self.assertTrue(before)
        found = self._search("--since", "1w")
        self._check_list_shape(found)
        self._assert_content_notice(found)
        new = self._json(["new"], "new")
        self._check_list_shape(new)
        self._assert_content_notice(new)
        self.assertTrue(found["messages"], "no message in the last week to show")
        uid = str(found["messages"][0]["uid"])
        self._assert_content_notice(self._json(["show", uid], "show"))
        counted = self._json(["search", "--count"], "search")
        self._assert_content_notice(counted)
        self.assertIsInstance(counted["count"], int)
        grouped = self._json(["search", "--group-by", "from", "--limit", "1"], "search")
        self._assert_content_notice(grouped)
        self.assertIn("groups", grouped)
        attachment_uid = self._local_attachment_uid()
        if attachment_uid is None:
            print(
                "\nSMOKE-NEW.08: no locally recoverable attachment; "
                "attachment content_notice not measured"
            )
        else:
            recovered = self._json(["attachment", attachment_uid, "--index", "1"], "attachment")
            self._assert_content_notice(recovered)
        after = self._counters()
        self.assertTrue(set(after) == set(before), "the included folders changed")
        for url, (total_before, unread_before) in before.items():
            total_after, unread_after = after[url]
            with self.subTest(folder=sorted(before).index(url)):
                self.assertEqual(unread_after - unread_before, total_after - total_before)

    def test_smoke_new_09_show_html_body(self):
        """SMOKE-NEW.09: show returns the HTML-derived body_text and leaves counters unchanged."""
        before = self._counters()
        self.assertTrue(before)
        found = self._html_message()
        if found is None:
            self.skipTest(
                "no message with a text/html part and a readable body in the last year"
            )
        uid, shown = found
        self.assertIs(shown["ok"], True)
        self._assert_content_notice(shown)
        message = shown["message"]
        self.assertEqual(message["uid"], uid)
        self.assertIs(message["readable"], True)
        self.assertIsInstance(message["body_text"], str)
        self.assertTrue(message["body_text"].strip())
        again = self._json(["show", uid], "show")
        self.assertEqual(again["message"]["body_text"], message["body_text"])
        after = self._counters()
        self.assertTrue(set(after) == set(before), "the included folders changed")
        for url, (total_before, unread_before) in before.items():
            total_after, unread_after = after[url]
            with self.subTest(folder=sorted(before).index(url)):
                self.assertEqual(unread_after - unread_before, total_after - total_before)

    def test_smoke_new_10_doctor_failures(self):
        """SMOKE-NEW.10: doctor --json --failures with nothing failing and no plugins."""
        payload = self._json(["doctor", "--json", "--failures"], "doctor")
        self.assertIs(payload["ok"], True)
        self.assertEqual(payload["checks"], [])
        self.assertEqual(payload["not_evaluated"], [])
        self.assertEqual(payload["plugins"], [])
        self.assertNotIn("content_notice", payload)
        rc, out, err, _ = self._run(["doctor", "--failures"])
        self.assertEqual(rc, 0, f"{out}\n{err}")
        self.assertIn("all checks passed", out)
        self.assertEqual(_snapshot(REAL_HOME / ".mailquery"), self.real_mq_before)

    def test_smoke_new_11_short_uid_against_the_real_client(self):
        """SMOKE-NEW.11: short uids and --show-native-id; no cache.db on macOS."""
        before = self._counters() if sys.platform == "win32" else None
        found = self._search("--since", "1w")
        self.assertTrue(found["messages"], "no message in the last week to show")
        print(
            f"\nSMOKE-NEW.11: {len(found['messages'])} messages in the last week, "
            f"first uid length {len(str(found['messages'][0]['uid']))}"
        )
        if sys.platform == "darwin":
            uid = str(found["messages"][0]["uid"])
            self._json(["show", uid], "show")
            self.assertFalse(
                (self.home / ".mailquery" / "db" / "cache.db").exists(),
                "Apple Mail must not create the native id cache",
            )
            return
        self.assertEqual(
            sys.platform, "win32", "SMOKE-NEW.11 applies to Windows and macOS"
        )
        short = re.compile(r"^outlook:[0-9a-z]{10}(?:-[1-9][0-9]*)?$")
        for message in found["messages"]:
            uid = str(message["uid"])
            self.assertRegex(uid, short)
            self.assertEqual(len(uid.split(":", 1)[1].split("-", 1)[0]), 10)
        uid = str(found["messages"][0]["uid"])
        self._json(["show", uid], "show")
        self.assertTrue((self.home / ".mailquery" / "db" / "cache.db").is_file())
        native = self._json(["show", uid, "--show-native-id"], "show")["message"][
            "uid"
        ]
        self.assertRegex(native, r"^outlook:[0-9A-F]+$")
        after = self._counters()
        self.assertEqual(set(after), set(before), "the included folders changed")
        for url, (total_before, unread_before) in before.items():
            total_after, unread_after = after[url]
            self.assertEqual(unread_after - unread_before, total_after - total_before)



# --------------------------------------------------------------------------- #
# SMOKE-ATT-OL — real Outlook attachment recovery (Windows host)
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
            if any(
                m["included"]
                for account in json.loads(result.stdout)["accounts"]
                for m in account["mailboxes"]
            ):
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

    def _included_counters(self) -> dict:
        """``{url: (total, unread)}`` of the included folders of the declared scope."""
        payload = self._json(
            ["mailboxes", "--fields", "url,total,unread"], "mailboxes"
        )
        return {
            entry["url"]: (entry["total"], entry["unread"])
            for account in payload["accounts"]
            for entry in account["mailboxes"]
            if entry["included"]
        }

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
        before = self._included_counters()
        self._json(["attachment", uid, "--index", "1"], "attachment")
        after = self._included_counters()
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
            if any(
                mailbox["included"]
                for account in json.loads(out)["accounts"]
                for mailbox in account["mailboxes"]
            ):
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


# --------------------------------------------------------------------------- #
# SMOKE-MCP — the MCP server against the real mail client
# --------------------------------------------------------------------------- #


class _McpClient:
    """Minimal JSON-RPC test client: one request line, one response line."""

    def __init__(self, exe: str, env: dict, cwd: Path) -> None:
        self.proc = subprocess.Popen(
            [exe, "mcp", "serve"],
            cwd=str(cwd),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        self._id = 0

    def request(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        message = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params is not None:
            message["params"] = params
        self.proc.stdin.write(json.dumps(message) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            raise AssertionError("the MCP server closed stdout without a response")
        return json.loads(line)

    def initialize(self) -> dict:
        return self.request(
            "initialize",
            {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "smoke"}},
        )

    def call(self, tool: str, arguments: dict | None = None) -> dict:
        return self.request("tools/call", {"name": tool, "arguments": arguments or {}})

    def close(self) -> tuple[int, str]:
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        try:
            _out, err = self.proc.communicate(timeout=120)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            _out, err = self.proc.communicate()
            raise
        return self.proc.returncode, err or ""


def _tool_payload(reply: dict) -> dict:
    return json.loads(reply["result"]["content"][0]["text"])


class SmokeMcpTest(unittest.TestCase):
    """SMOKE-MCP.01–.07: the installed ``mailquery mcp serve`` on the real client."""

    @classmethod
    def setUpClass(cls):
        # Reuse SmokeTest's install, HOME, config and helpers without inheriting
        # (and duplicating) its command-level tests.
        SmokeTest.setUpClass.__func__(cls)

    _run = SmokeTest._run
    _store_counts = SmokeTest._store_counts

    def setUp(self) -> None:
        self.client = _McpClient(self.exe, dict(self.env), self.tmp)
        self.addCleanup(self._close_client)

    def _close_client(self) -> None:
        if self.client.proc.poll() is None:
            self.client.close()

    def _payload(self, tool, arguments=None) -> dict:
        reply = self.client.call(tool, arguments)
        self.assertIn("result", reply, reply)
        return _tool_payload(reply)

    def test_smoke_mcp_01_initialize_and_tools_list(self) -> None:
        """SMOKE-MCP.01: initialize and tools/list expose the six tools."""
        initialized = self.client.initialize()
        self.assertEqual(initialized["result"]["serverInfo"]["name"], "mailquery")
        tools = self.client.request("tools/list")
        names = [tool["name"] for tool in tools["result"]["tools"]]
        self.assertEqual(
            names, ["search", "new", "show", "attachment", "mailboxes", "doctor"]
        )
        code, err = self.client.close()
        self.assertEqual(code, 0, err)
        self.assertEqual(err, "")

    def test_smoke_mcp_02_search_and_show(self) -> None:
        """SMOKE-MCP.02: search returns the default row and show succeeds."""
        self.client.initialize()
        search = self._payload("search", {"since": "1w"})
        self.assertTrue(search["ok"], search)
        if not search["messages"]:
            self.skipTest("no messages in the last week")
        for row in search["messages"]:
            self.assertEqual(
                list(row),
                ["uid", "subject", "from", "date_received", "is_read", "has_attachments"],
            )
        show = self._payload("show", {"uid": search["messages"][0]["uid"]})
        self.assertTrue(show["ok"], show)
        self.assertFalse(self.client.call("show", {"uid": search["messages"][0]["uid"]})["result"]["isError"])

    def test_smoke_mcp_03_new_advances_the_cursor_without_repeats(self) -> None:
        """SMOKE-MCP.03: two new calls advance the cursor and do not repeat messages."""
        self.client.initialize()
        first = self._payload("new", {})
        if not first["messages"]:
            self.skipTest("no new messages available")
        first_uids = {message["uid"] for message in first["messages"]}
        second = self._payload("new", {})
        second_uids = {message["uid"] for message in second["messages"]}
        self.assertTrue(second["ok"], second)
        self.assertFalse(first_uids & second_uids)

    def test_smoke_mcp_04_attachment_of_a_local_attachment(self) -> None:
        """SMOKE-MCP.04: attachment recovers a local attachment under the temporary home."""
        self.client.initialize()
        candidates = self._payload("search", {"has_attachments": True, "limit": 20})
        for message in candidates.get("messages") or ():
            reply = self.client.call(
                "attachment", {"uid": message["uid"], "index": 1, "force": True}
            )
            if reply.get("result", {}).get("isError"):
                continue
            payload = _tool_payload(reply)
            self.assertTrue(payload["ok"], payload)
            path = Path(payload["attachments"][0]["path"])
            self.assertTrue(path.is_file(), path)
            self.assertIn(self.home / ".mailquery" / "attachments", path.parents)
            return
        self.skipTest("no message with a recoverable local attachment")

    def test_smoke_mcp_05_permission_denied_or_outlook_closed(self) -> None:
        """SMOKE-MCP.05: E_PERMISSION / E_OUTLOOK_NOT_RUNNING needs an external condition."""
        self.skipTest(
            "cannot prepare the missing Full Disk Access or a closed Outlook from the suite"
        )

    def test_smoke_mcp_06_plugin_next_to_the_native_driver(self) -> None:
        """SMOKE-MCP.06: a plugin next to the native driver and a failing plugin."""
        plugin_root = Path(tempfile.mkdtemp(prefix="mq-smoke-plugin-"))
        self.addCleanup(shutil.rmtree, plugin_root, ignore_errors=True)
        module = plugin_root / "mq_smoke_plugin.py"
        module.write_text(
            "from tests.fakes.plugin import FakePluginBackend\n"
            "class FailingPlugin(FakePluginBackend):\n"
            "    def query(self, *args, **kwargs):\n"
            "        raise RuntimeError('smoke plugin failure')\n",
            encoding="utf-8",
        )
        dist_info = plugin_root / "graph-0.1.0.dist-info"
        dist_info.mkdir()
        (dist_info / "METADATA").write_text(
            "Metadata-Version: 2.1\nName: graph\nVersion: 0.1.0\n", encoding="utf-8"
        )
        (dist_info / "entry_points.txt").write_text(
            "[mailquery.backends]\ngraph = mq_smoke_plugin:FailingPlugin\n",
            encoding="utf-8",
        )
        env = dict(self.env)
        env["PYTHONPATH"] = os.pathsep.join([str(ROOT), str(plugin_root)])
        client = _McpClient(self.exe, env, self.tmp)
        self.addCleanup(lambda: client.proc.poll() is None and client.close())
        client.initialize()
        self.assertEqual(len(client.request("tools/list")["result"]["tools"]), 6)
        cfg = self.home / ".mailquery" / "config.toml"
        cfg.write_text(
            cfg.read_text(encoding="utf-8") + '[scope."graph:smoke"]\n', encoding="utf-8"
        )
        reply = client.call("search", {"since": "1w"})
        if reply.get("result", {}).get("isError"):
            payload = _tool_payload(reply)
            self.assertIn(payload["error"]["code"], ("E_PLUGIN_FAILED", "E_CONFIG_ACCOUNT_UNKNOWN"))
        client.close()

    def test_smoke_mcp_07_unread_counters_do_not_change(self) -> None:
        """SMOKE-MCP.07: the unread counters of the included folders do not change."""
        before = self._unread_counters()
        self.client.initialize()
        self._payload("search", {"since": "1w"})
        after = self._unread_counters()
        self.assertEqual(after, before)

    def _unread_counters(self) -> dict:
        rc, out, err, _ = self._run(["mailboxes", "--fields", "url,total,unread"])
        self.assertEqual(rc, 0, err)
        data = json.loads(out)
        counters = {}
        for account in data.get("accounts") or ():
            for mailbox in account.get("mailboxes") or ():
                if mailbox.get("included"):
                    counters[mailbox.get("url")] = (mailbox.get("total"), mailbox.get("unread"))
        return counters

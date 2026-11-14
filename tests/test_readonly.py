"""Mandatory, blocking read-only guard (PRD §4, §20, §21.3).

The single most important invariant of mailquery (I-1) is that it never writes
to the Apple Mail store. This test snapshots **every** file under the synthetic
store (relative path, size, ``mtime_ns`` and SHA-256) plus every directory,
runs every command end to end through :func:`mailquery.cli.main` and asserts
after each invocation that:

1. the store snapshot is byte-identical (no modified, created or deleted
   files/directories under ``fx.mail_root``);
2. every new or modified file in the fixture root lives under ``fx.home``
   (``~/.mailquery``), so nothing leaked outside the app home;
3. the command actually succeeded and emitted the documented JSON contract.

The test is part of the CI gate: it must never be skipped. If a dependency
module is still a stub the test fails, which is the intended blocking behavior.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import unittest
from pathlib import Path

from tests.fixtures.make_fixtures import (
    DEFAULT_CONFIG,
    ICLOUD_LABEL,
    LIMIT_1MB_CONFIG,
    UID_ATTACH_BIG,
    UID_ATTACH_EMPTY,
    UID_ATTACH_EXECUTABLE,
    UID_ATTACH_HOSTILE_RESERVED,
    UID_ATTACH_PARTIAL,
    UID_ATTACH_SMIME,
    UID_SMIME_ENCRYPTED,
    UID_SMIME_SIGNED,
    build_store,
    prefixed_uid,
    write_config,
)

from mailquery import cli


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _snapshot(root: Path) -> tuple[dict[str, tuple[int, int, str]], set[str]]:
    """Return ``({relative file -> (size, mtime_ns, sha256)}, {relative dirs})``."""
    files: dict[str, tuple[int, int, str]] = {}
    directories: set[str] = set()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            directories.add(relative)
        elif path.is_file():
            stat = path.stat()
            files[relative] = (stat.st_size, stat.st_mtime_ns, _sha256(path))
    return files, directories


def _relative_prefix(base: Path, root: Path) -> str:
    """Return ``base`` as a POSIX path relative to ``root`` ('' when equal)."""
    relative = base.resolve().relative_to(root.resolve()).as_posix()
    return "" if relative == "." else relative


def _inside(relative: str, prefix: str) -> bool:
    """True when the snapshot-relative ``relative`` path is under ``prefix``."""
    if not prefix:
        return True
    return relative == prefix or relative.startswith(prefix + "/")


class ReadOnlyStoreTest(unittest.TestCase):
    """PRD §20 read-only gate: hashes and mtimes unchanged, no new store files."""

    def setUp(self) -> None:
        # Extended store: WAL-mode Envelope Index with -wal/-shm, S/MIME, deleted
        # rows... plus the attachment fixtures (``attachments=True``).
        self.fx = build_store(extended=True, attachments=True)
        self.addCleanup(self.fx.cleanup)
        # Default fixture config declares the three accounts (two extra folders).
        write_config(self.fx.home)
        self.initial_files, self.initial_dirs = _snapshot(self.fx.root)

    # -- helpers ---------------------------------------------------------- #

    def run_cli(self, *args: str) -> tuple[int, dict | None, str]:
        """Invoke ``cli.main`` with the fixture paths and capture the JSON."""
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = cli.main(
                list(args),
                home=self.fx.home,
                mail_root=self.fx.mail_root,
                accounts_db=self.fx.accounts_db,
            )
        raw = stdout.getvalue()
        payload = json.loads(raw) if raw.strip() else None
        return code, payload, stderr.getvalue()

    def assert_store_unchanged(self) -> None:
        """Assert the Mail store is byte-identical to the initial snapshot."""
        files, directories = _snapshot(self.fx.root)
        mail_prefix = _relative_prefix(self.fx.mail_root, self.fx.root)
        home_prefix = _relative_prefix(self.fx.home, self.fx.root)
        initial_mail_files = {
            path: info for path, info in self.initial_files.items() if _inside(path, mail_prefix)
        }
        current_mail_files = {
            path: info for path, info in files.items() if _inside(path, mail_prefix)
        }
        self.maxDiff = None
        self.assertEqual(
            sorted(initial_mail_files),
            sorted(current_mail_files),
            "read-only violation: files were created or deleted under fx.mail_root",
        )
        for path, expected in initial_mail_files.items():
            if path.endswith("-shm"):
                # SQLite's shared-memory index is initialised by any reader (even
                # read-only), so its size/mtime/content legitimately change; the
                # database and the -wal file are compared as usual.
                continue
            self.assertEqual(
                current_mail_files[path],
                expected,
                f"read-only violation: fx.mail_root file changed: {path}",
            )
        initial_mail_dirs = {path for path in self.initial_dirs if _inside(path, mail_prefix)}
        current_mail_dirs = {path for path in directories if _inside(path, mail_prefix)}
        self.assertEqual(
            initial_mail_dirs,
            current_mail_dirs,
            "read-only violation: directories were created or deleted under fx.mail_root",
        )

        # Nothing outside the app home may be created or modified either.
        for path in set(files) - set(self.initial_files):
            self.assertTrue(
                _inside(path, home_prefix),
                f"write outside the app home: {path}",
            )
        for path in directories - self.initial_dirs:
            self.assertTrue(
                _inside(path, home_prefix),
                f"directory created outside the app home: {path}",
            )
        for path in set(files) & set(self.initial_files):
            if path.endswith("-shm"):
                continue  # see above: reader-initialised shared-memory index
            if files[path] != self.initial_files[path] and not _inside(path, home_prefix):
                self.fail(f"file modified outside the app home: {path}")

    def assert_ok(self, code: int, payload: dict | None, command: str) -> dict:
        self.assertEqual(code, 0, f"command {command} failed")
        self.assertIsNotNone(payload, f"command {command} produced no JSON on stdout")
        assert payload is not None
        self.assertIs(payload.get("ok"), True)
        self.assertEqual(payload.get("command"), command)
        self.assertIsInstance(payload.get("generated_at"), str)
        self.assertIsInstance(payload.get("warnings"), list)
        return payload

    # -- the gate --------------------------------------------------------- #

    def test_tc_03_01_all_commands_leave_the_store_untouched(self) -> None:
        """TC-03.01: every command (new first run, out-of-scope show, S/MIME) leaves the store untouched."""
        scenarios = [
            (("doctor", "--json"), "doctor"),
            (("doctor", "--json", "--failures"), "doctor"),
            (("mailboxes",), "mailboxes"),
            (("mailboxes", "--fields", "total,unread"), "mailboxes"),
            (("mailboxes", "--fields", "name,url"), "mailboxes"),
            (("search", "--strip-links"), "search"),
            (("search", "--subject", "Invoice", "--strip-links"), "search"),
            (("search", "--text", "factura", "--strip-links"), "search"),
            (("search", "--include-mailbox", "Archivo", "--strip-links"), "search"),
            (("search", "--unread", "--limit", "1", "--strip-links"), "search"),
            (("search", "--since", "7d", "--flagged", "--strip-links"), "search"),
            (("search", "--fields", "all"), "search"),
            (("search", "--group-by", "from,month"), "search"),
            (("search", "--count"), "search"),
            (("new", "--fields", "all"), "new"),
            (("new", "--strip-links"), "new"),
            (("new", "--strip-links"), "new"),
            (("new", "--peek", "--strip-links"), "new"),
            (("show", "2714", "--strip-links"), "show"),
            (("show", "2714", "--fields", "attachments"), "show"),
            (("show", "79658", "--strip-links"), "show"),
            (("show", "83170", "--strip-links"), "show"),
            (("show", "83180", "--strip-links"), "show"),
            (("show", str(UID_SMIME_ENCRYPTED), "--strip-links"), "show"),
            (("show", str(UID_SMIME_SIGNED), "--strip-links"), "show"),
        ]
        # The filtered text report is read-only too (it prints no JSON).
        with self.subTest(argv=("doctor", "--failures")):
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = cli.main(
                    ["doctor", "--failures"],
                    home=self.fx.home,
                    mail_root=self.fx.mail_root,
                    accounts_db=self.fx.accounts_db,
                )
            self.assertEqual(code, 0)
            self.assertEqual(stderr.getvalue(), "")
            self.assertIn("all checks passed", stdout.getvalue())
            self.assert_store_unchanged()

        payloads: dict[str, list[dict]] = {}
        for argv, command in scenarios:
            with self.subTest(argv=argv):
                code, payload, _stderr = self.run_cli(*argv)
                result = self.assert_ok(code, payload, command)
                payloads.setdefault(command, []).append(result)
                self.assert_store_unchanged()

        self.assertGreaterEqual(payloads["search"][0]["count"], 12)
        self.assertIn("checks", payloads["doctor"][0])
        self.assertIn("not_evaluated", payloads["doctor"][1])
        self.assertEqual(payloads["doctor"][1]["checks"], [])
        self.assertEqual(payloads["doctor"][1]["plugins"], [])
        self.assertTrue(payloads["mailboxes"][0]["accounts"])
        self.assertTrue(
            all(
                "mailboxes" in account
                for account in payloads["mailboxes"][0]["accounts"]
            )
        )
        self.assertEqual(payloads["show"][0]["message"]["uid"], prefixed_uid(2714))
        self.assertEqual(payloads["show"][3]["message"]["uid"], prefixed_uid(83170))
        # First run: emits the window and writes only the state; then nothing new.
        self.assertTrue(payloads["new"][0]["messages"])
        self.assertTrue(
            {prefixed_uid(83160), prefixed_uid(83170)}
            <= {message["uid"] for message in payloads["new"][0]["messages"]}
        )
        self.assertEqual(payloads["new"][1]["count"], 0)
        self.assertEqual(payloads["new"][2]["count"], 0)
        self.assertEqual(payloads["new"][3]["count"], 0)
        # S/MIME messages are listed but their body is never read.
        for result in payloads["show"][-2:]:
            self.assertIs(result["message"]["readable"], False)

        # Out of scope: only iCloud declared, a Gmail uid is rejected (exit 2).
        write_config(self.fx.home, f'[scope."{ICLOUD_LABEL}"]\n')
        code, payload, _stderr = self.run_cli("show", "83160")
        self.assertEqual(code, 2)
        assert payload is not None
        self.assertEqual(payload["error"]["code"], "E_ACCOUNT_NOT_IN_SCOPE")
        self.assert_store_unchanged()

    def test_tc_03_02_attachment_flows_leave_the_store_untouched(self) -> None:
        """TC-03: attachment success, cache, blocked, limit, S/MIME and empty leave it untouched."""
        scenarios = [
            (("attachment", prefixed_uid(2714), "--index", "1"), 0, None),
            (("attachment", prefixed_uid(2714), "--index", "1"), 0, None),  # cached
            (("attachment", prefixed_uid(UID_ATTACH_EMPTY), "--index", "1"), 0, None),
            (
                ("attachment", prefixed_uid(UID_ATTACH_HOSTILE_RESERVED), "--all"),
                4,
                "E_ATTACHMENT_BLOCKED",
            ),
            (
                ("attachment", prefixed_uid(UID_ATTACH_EXECUTABLE), "--index", "2"),
                4,
                "E_ATTACHMENT_BLOCKED",
            ),
            (
                ("attachment", prefixed_uid(UID_ATTACH_SMIME), "--index", "1"),
                3,
                "E_ATTACHMENT_UNREADABLE",
            ),
            (
                ("attachment", prefixed_uid(UID_ATTACH_PARTIAL), "--index", "2"),
                3,
                "E_ATTACHMENT_UNAVAILABLE",
            ),
        ]
        for argv, expected_exit, expected_code in scenarios:
            with self.subTest(argv=argv):
                code, payload, _stderr = self.run_cli(*argv)
                self.assertEqual(code, expected_exit, payload)
                if expected_code is None:
                    self.assert_ok(code, payload, "attachment")
                else:
                    assert payload is not None
                    self.assertIs(payload.get("ok"), False)
                    self.assertEqual(payload["error"]["code"], expected_code)
                self.assert_store_unchanged()

        # Known-size limit: needs its own config (restored before finishing).
        write_config(self.fx.home, LIMIT_1MB_CONFIG)
        with self.subTest(argv=("attachment", prefixed_uid(UID_ATTACH_BIG), "--index", "1")):
            code, payload, _stderr = self.run_cli(
                "attachment", prefixed_uid(UID_ATTACH_BIG), "--index", "1"
            )
            self.assertEqual(code, 4, payload)
            assert payload is not None
            self.assertEqual(payload["error"]["code"], "E_ATTACHMENT_TOO_LARGE")
            self.assert_store_unchanged()
        write_config(self.fx.home, DEFAULT_CONFIG)
        self.assert_store_unchanged()

    def test_doctor_human_report_does_not_touch_the_store(self) -> None:
        """The default human-readable doctor report is read-only too."""
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = cli.main(
                ["doctor"],
                home=self.fx.home,
                mail_root=self.fx.mail_root,
                accounts_db=self.fx.accounts_db,
            )
        self.assertEqual(code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertIn("Checks:", stdout.getvalue())
        self.assert_store_unchanged()

    def test_store_snapshot_sees_no_new_files_after_whole_suite(self) -> None:
        """Belt-and-braces: final snapshot after the full command sweep."""
        for argv in (
            ("doctor", "--json"),
            ("mailboxes",),
            ("search",),
            ("search", "--fields", "all"),
            ("new",),
            ("new", "--fields", "all"),
            ("new", "--peek"),
            ("show", "83170"),
            ("show", "83170", "--fields", "attachments"),
        ):
            self.run_cli(*argv)
        self.assert_store_unchanged()

    def test_only_app_home_receives_new_files(self) -> None:
        """The state/lock/log/tmp artifacts are created inside ``fx.home`` only."""
        self.run_cli("new")
        self.assert_store_unchanged()

        store_files, _ = _snapshot(self.fx.home)
        self.assertIn("state.json", store_files)
        self.assertIn("locks/mailquery.lock", store_files)
        self.assertTrue(any(path.startswith("logs/") for path in store_files))
        if os.name == "posix":
            self.assertEqual(
                (self.fx.home / "state.json").stat().st_mode & 0o777,
                0o600,
            )

    def test_no_file_under_mail_root_is_world_or_group_writable_after_reads(self) -> None:
        """Defensive: reading must not relax any on-disk permission."""
        mail_prefix = _relative_prefix(self.fx.mail_root, self.fx.root)
        mail_files = [
            path for path in self.initial_files if _inside(path, mail_prefix)
        ]
        before = {
            path: (self.fx.root / path).stat().st_mode for path in mail_files
        }
        self.run_cli("mailboxes")
        self.run_cli("show", "2714")
        after = {
            path: (self.fx.root / path).stat().st_mode for path in mail_files
        }
        self.assertEqual(before, after)
        self.assert_store_unchanged()


if __name__ == "__main__":  # pragma: no cover - manual runs
    unittest.main()

"""Tests for :mod:`mailquery.store` against the synthetic Apple Mail store."""

from __future__ import annotations

import hashlib
import plistlib
import shutil
import sqlite3
import unicodedata
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import quote

from tests.fixtures import make_fixtures as fixtures
from mailquery import store as store_module
from mailquery.errors import MailqueryError
from mailquery.store import (
    REQUIRED_COLUMNS,
    StoreVersion,
    detect_version,
    open_store,
)

ENVELOPE_INDEX = "Envelope Index"


def _snapshot(root: Path, *, ignore_suffixes: tuple[str, ...] = ()) -> dict[str, tuple[int, int, str]]:
    """Return ``relpath -> (size, mtime_ns, sha256)`` for every file below root."""
    snapshot: dict[str, tuple[int, int, str]] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(path.name.endswith(suffix) for suffix in ignore_suffixes):
            continue
        stat = path.stat()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        snapshot[str(path.relative_to(root))] = (stat.st_size, stat.st_mtime_ns, digest)
    return snapshot


class StoreTestCase:
    """Common fixture setup/teardown for the store tests."""

    def setUp(self) -> None:
        self.fx = fixtures.build_store()
        self.addCleanup(self.fx.cleanup)
        self.tmp_root = self.fx.home / "tmp"

    # -- helpers ------------------------------------------------------------ #

    def open_store(self, **kwargs):
        kwargs.setdefault("mail_root", self.fx.mail_root)
        kwargs.setdefault("tmp_root", self.tmp_root)
        return open_store(**kwargs)

    def write_plist(self, payload: dict, mail_root: Path | None = None) -> None:
        root = mail_root if mail_root is not None else self.fx.mail_root
        (root / "PersistenceInfo.plist").write_bytes(plistlib.dumps(payload))

    def index_path(self, mail_root: Path | None = None) -> Path:
        root = mail_root if mail_root is not None else self.fx.mail_root
        return root / fixtures.VERSION / "MailData" / ENVELOPE_INDEX

    def leftover_tmp_dirs(self) -> list[Path]:
        if not self.tmp_root.exists():
            return []
        return [entry for entry in self.tmp_root.iterdir() if entry.is_dir()]


class DetectVersionTests(StoreTestCase, unittest.TestCase):
    def test_detects_fixture_version(self) -> None:
        version = detect_version(self.fx.mail_root)
        self.assertIsInstance(version, StoreVersion)
        self.assertEqual(version.mail_root, self.fx.mail_root)
        self.assertEqual(version.version, fixtures.VERSION)
        self.assertEqual(version.version_uuid, fixtures.VERSION_UUID)
        self.assertEqual(version.data_dir, self.fx.mail_root / fixtures.VERSION / "MailData")
        self.assertEqual(version.envelope_index, self.fx.envelope_index)

    def test_default_mail_root_is_library_mail(self) -> None:
        with mock.patch.object(
            store_module, "_default_mail_root", return_value=self.fx.mail_root
        ) as default_root:
            version = detect_version()
        default_root.assert_called_once_with()
        self.assertEqual(version.version, fixtures.VERSION)

    def test_missing_mail_root_raises_store_not_found(self) -> None:
        with self.assertRaises(MailqueryError) as ctx:
            detect_version(self.fx.root / "does-not-exist")
        self.assertEqual(ctx.exception.code, "E_STORE_NOT_FOUND")
        self.assertEqual(ctx.exception.exit_code, 3)
        self.assertTrue(ctx.exception.hint)

    def test_mail_root_that_is_a_file_raises_store_not_found(self) -> None:
        path = self.fx.root / "not-a-directory"
        path.write_text("x", encoding="utf-8")
        with self.assertRaises(MailqueryError) as ctx:
            detect_version(path)
        self.assertEqual(ctx.exception.code, "E_STORE_NOT_FOUND")

    def test_unsupported_version_raises_schema_unsupported(self) -> None:
        self.write_plist(
            {
                "LastUsedVersionDirectoryName": "V8",
                "VersionDirectoryIdentifiers": {"V8": fixtures.VERSION_UUID},
            }
        )
        with self.assertRaises(MailqueryError) as ctx:
            detect_version(self.fx.mail_root)
        self.assertEqual(ctx.exception.code, "E_SCHEMA_UNSUPPORTED")
        self.assertEqual(ctx.exception.exit_code, 3)
        self.assertIn("V8", ctx.exception.message)
        self.assertIn("V10", ctx.exception.hint)

    def test_missing_version_directory_raises_store_not_found(self) -> None:
        shutil.rmtree(self.fx.mail_root / fixtures.VERSION)
        with self.assertRaises(MailqueryError) as ctx:
            detect_version(self.fx.mail_root)
        self.assertEqual(ctx.exception.code, "E_STORE_NOT_FOUND")

    def test_missing_plist_falls_back_to_disk(self) -> None:
        (self.fx.mail_root / "PersistenceInfo.plist").unlink()
        version = detect_version(self.fx.mail_root)
        self.assertEqual(version.version, fixtures.VERSION)
        self.assertEqual(version.version_uuid, fixtures.VERSION_UUID)

    def test_plist_without_version_uuid_is_recovered_from_disk(self) -> None:
        self.write_plist({"LastUsedVersionDirectoryName": fixtures.VERSION})
        version = detect_version(self.fx.mail_root)
        self.assertEqual(version.version, fixtures.VERSION)
        self.assertEqual(version.version_uuid, fixtures.VERSION_UUID)

    def test_corrupt_plist_falls_back_to_disk(self) -> None:
        (self.fx.mail_root / "PersistenceInfo.plist").write_bytes(b"not a plist")
        version = detect_version(self.fx.mail_root)
        self.assertEqual(version.version, fixtures.VERSION)

    def test_permission_error_raises_permission(self) -> None:
        with mock.patch.object(
            store_module.Path, "read_bytes", side_effect=PermissionError("denied")
        ):
            with self.assertRaises(MailqueryError) as ctx:
                detect_version(self.fx.mail_root)
        self.assertEqual(ctx.exception.code, "E_PERMISSION")
        self.assertEqual(ctx.exception.exit_code, 3)
        self.assertIn("Full Disk Access", ctx.exception.hint)


class OpenStoreStrategyTests(StoreTestCase, unittest.TestCase):
    def test_copy_strategy_when_shm_is_missing(self) -> None:
        before = _snapshot(self.fx.mail_root)
        opened = self.open_store()
        try:
            self.assertEqual(opened.strategy, "copy_ro")
            self.assertIsNotNone(opened.tmp_dir)
            self.assertTrue(opened.tmp_dir.is_relative_to(self.tmp_root))
            database_path = Path(
                opened.connection.execute("PRAGMA database_list").fetchone()[2]
            ).resolve()
            self.assertEqual(database_path, (opened.tmp_dir / ENVELOPE_INDEX).resolve())
            self.assertEqual(len(opened.mailboxes), 7)
        finally:
            opened.close()
        self.assertEqual(_snapshot(self.fx.mail_root), before)
        self.assertEqual(self.leftover_tmp_dirs(), [])
        self.assertFalse((self.fx.envelope_index.parent / "Envelope Index-shm").exists())
        self.assertFalse((self.fx.envelope_index.parent / "Envelope Index-wal").exists())

    def test_live_strategy_when_shm_exists(self) -> None:
        writer = sqlite3.connect(self.fx.envelope_index)
        try:
            writer.execute("PRAGMA journal_mode=WAL")
            writer.execute("INSERT INTO subjects (subject) VALUES ('live-wal-probe')")
            writer.commit()
            self.assertTrue(
                (self.fx.envelope_index.parent / "Envelope Index-shm").exists()
            )
            # -shm read marks are expected to change; the DB and -wal must not.
            before = _snapshot(
                self.fx.mail_root, ignore_suffixes=("-shm",)
            )
            opened = open_store(self.fx.mail_root, tmp_root=self.tmp_root)
            try:
                self.assertEqual(opened.strategy, "live_ro")
                self.assertIsNone(opened.tmp_dir)
                self.assertFalse(self.tmp_root.exists())
                database_path = Path(
                    opened.connection.execute("PRAGMA database_list").fetchone()[2]
                ).resolve()
                self.assertEqual(database_path, self.fx.envelope_index.resolve())
                row = opened.connection.execute(
                    "SELECT COUNT(*) FROM subjects WHERE subject='live-wal-probe'"
                ).fetchone()
                self.assertEqual(row[0], 1)  # immutable=1 would miss the -wal
                self.assertEqual(len(opened.mailboxes), 7)
            finally:
                opened.close()
            self.assertEqual(_snapshot(self.fx.mail_root, ignore_suffixes=("-shm",)), before)
            self.assertTrue(
                (self.fx.envelope_index.parent / "Envelope Index-shm").exists()
            )
        finally:
            writer.close()

    def test_copy_strategy_copies_and_recovers_wal(self) -> None:
        other = fixtures.build_store()
        self.addCleanup(other.cleanup)
        writer = sqlite3.connect(other.envelope_index)
        mail_root = self.fx.root / "mail-with-wal"
        data_dir = mail_root / fixtures.VERSION / "MailData"
        try:
            writer.execute("PRAGMA journal_mode=WAL")
            writer.execute("INSERT INTO subjects (subject) VALUES ('copied-wal-probe')")
            writer.commit()
            data_dir.mkdir(parents=True)
            shutil.copy2(
                other.mail_root / "PersistenceInfo.plist",
                mail_root / "PersistenceInfo.plist",
            )
            shutil.copy2(other.envelope_index, data_dir / ENVELOPE_INDEX)
            shutil.copy2(
                other.envelope_index.parent / "Envelope Index-wal",
                data_dir / "Envelope Index-wal",
            )
        finally:
            writer.close()

        opened = open_store(mail_root, tmp_root=self.tmp_root)
        try:
            self.assertEqual(opened.strategy, "copy_ro")
            self.assertTrue((opened.tmp_dir / "Envelope Index-wal").is_file())
            row = opened.connection.execute(
                "SELECT COUNT(*) FROM subjects WHERE subject='copied-wal-probe'"
            ).fetchone()
            self.assertEqual(row[0], 1)
            self.assertEqual(len(opened.mailboxes), 7)
        finally:
            opened.close()
        self.assertEqual(self.leftover_tmp_dirs(), [])

    def test_schema_fingerprint_failure(self) -> None:
        connection = sqlite3.connect(self.fx.envelope_index)
        try:
            connection.execute("DROP TABLE labels")
            connection.commit()
        finally:
            connection.close()
        with self.assertRaises(MailqueryError) as ctx:
            self.open_store()
        self.assertEqual(ctx.exception.code, "E_SCHEMA_UNSUPPORTED")
        self.assertEqual(ctx.exception.exit_code, 3)
        self.assertIn("labels", ctx.exception.message)
        self.assertEqual(self.leftover_tmp_dirs(), [])

    def test_missing_envelope_index(self) -> None:
        self.fx.envelope_index.unlink()
        with self.assertRaises(MailqueryError) as ctx:
            self.open_store()
        self.assertEqual(ctx.exception.code, "E_STORE_NOT_FOUND")

    def test_fingerprint_reports_full_schema(self) -> None:
        opened = self.open_store()
        try:
            fingerprint = opened.fingerprint()
            self.assertEqual(set(fingerprint), set(REQUIRED_COLUMNS))
            self.assertTrue(all(fingerprint.values()))
            self.assertEqual(opened.missing_columns(), [])
        finally:
            opened.close()

    def test_public_attributes_match_contract(self) -> None:
        opened = self.open_store()
        try:
            self.assertEqual(opened.version, detect_version(self.fx.mail_root))
            self.assertEqual(opened.strategy, "copy_ro")
            self.assertIsInstance(opened.connection, sqlite3.Connection)
            self.assertIsInstance(opened.mailboxes, tuple)
            self.assertEqual(opened.mailbox(1).name, "INBOX")
            self.assertEqual(opened.mailbox_dir(opened.mailbox(1)).name, "INBOX.mbox")
            self.assertIsNotNone(opened.resolve_mailbox(fixtures.ACCOUNT_ICLOUD, "INBOX"))
            self.assertIsInstance(opened.fingerprint(), dict)
        finally:
            opened.close()

    def test_db_busy_after_one_retry(self) -> None:
        with mock.patch.object(
            store_module,
            "_connect_readonly",
            side_effect=sqlite3.OperationalError("database is locked"),
        ) as connect, mock.patch.object(store_module.time, "sleep") as sleep:
            with self.assertRaises(MailqueryError) as ctx:
                self.open_store()
        self.assertEqual(ctx.exception.code, "E_DB_BUSY")
        self.assertEqual(ctx.exception.exit_code, 5)
        self.assertEqual(connect.call_count, 2)
        sleep.assert_called_once_with(0.1)
        self.assertEqual(self.leftover_tmp_dirs(), [])

    def test_db_busy_retry_succeeds(self) -> None:
        real_connect = store_module._connect_readonly
        attempts: list[int] = []

        def flaky_connect(path):
            attempts.append(1)
            if len(attempts) == 1:
                raise sqlite3.OperationalError("database is locked")
            return real_connect(path)

        with mock.patch.object(
            store_module, "_connect_readonly", side_effect=flaky_connect
        ) as connect, mock.patch.object(store_module.time, "sleep") as sleep:
            opened = self.open_store()
            try:
                self.assertEqual(opened.strategy, "copy_ro")
                self.assertEqual(len(opened.mailboxes), 7)
            finally:
                opened.close()
        self.assertEqual(connect.call_count, 2)
        sleep.assert_called_once_with(0.1)

    def test_tcc_permission_error_maps_to_permission(self) -> None:
        # macOS TCC / Full Disk Access denial surfaces as a raw PermissionError
        # from sqlite3.connect(), not as sqlite3.Error (PRD 17).
        from tests.mocks import tcc_denied

        before = _snapshot(self.fx.mail_root)
        with tcc_denied() as connect:
            with self.assertRaises(MailqueryError) as ctx:
                self.open_store()
        self.assertEqual(ctx.exception.code, "E_PERMISSION")
        self.assertEqual(ctx.exception.exit_code, 3)
        self.assertIn("Full Disk Access", ctx.exception.hint)
        self.assertGreaterEqual(connect.call_count, 1)
        self.assertEqual(self.leftover_tmp_dirs(), [])
        self.assertEqual(_snapshot(self.fx.mail_root), before)

    def test_raw_oserror_from_connect_maps_to_permission(self) -> None:
        # A raw OSError (e.g. "Operation not permitted" without Python's
        # PermissionError subclassing) must map to E_PERMISSION as well.
        error = OSError(5, "Input/output error")
        self.assertNotIsInstance(error, PermissionError)
        with mock.patch("sqlite3.connect", side_effect=error):
            with self.assertRaises(MailqueryError) as ctx:
                self.open_store()
        self.assertEqual(ctx.exception.code, "E_PERMISSION")
        self.assertEqual(ctx.exception.exit_code, 3)
        self.assertIn("Full Disk Access", ctx.exception.hint)
        self.assertEqual(self.leftover_tmp_dirs(), [])

    def test_busy_connect_uses_documented_retry(self) -> None:
        # The shared mocks helper patches sqlite3.connect itself, exactly as
        # Apple Mail's locked database behaves (PRD 9.6/17).
        from tests.mocks import db_busy

        before = _snapshot(self.fx.mail_root)
        with db_busy() as connect, mock.patch.object(store_module.time, "sleep") as sleep:
            with self.assertRaises(MailqueryError) as ctx:
                self.open_store()
        self.assertEqual(ctx.exception.code, "E_DB_BUSY")
        self.assertEqual(ctx.exception.exit_code, 5)
        self.assertEqual(connect.call_count, 2)
        sleep.assert_called_once_with(0.1)
        self.assertEqual(self.leftover_tmp_dirs(), [])
        self.assertEqual(_snapshot(self.fx.mail_root), before)

    def test_non_busy_operational_error_maps_to_store_not_found(self) -> None:
        with mock.patch.object(
            store_module,
            "_connect_readonly",
            side_effect=sqlite3.OperationalError("unable to open database file"),
        ):
            with self.assertRaises(MailqueryError) as ctx:
                self.open_store()
        self.assertEqual(ctx.exception.code, "E_STORE_NOT_FOUND")

    def test_refuses_temporary_directory_inside_mail_root(self) -> None:
        inside = self.fx.mail_root / "tmp"
        with self.assertRaises(MailqueryError) as ctx:
            open_store(self.fx.mail_root, tmp_root=inside)
        self.assertEqual(ctx.exception.code, "E_PERMISSION")
        self.assertFalse(inside.exists())

    def test_default_tmp_root_is_used_by_open_store(self) -> None:
        with mock.patch.object(store_module, "_default_tmp_root", return_value=self.tmp_root):
            opened = open_store(self.fx.mail_root)
            try:
                self.assertEqual(opened.strategy, "copy_ro")
                self.assertTrue(opened.tmp_dir.is_relative_to(self.tmp_root))
            finally:
                opened.close()


class ReadOnlyGuaranteeTests(StoreTestCase, unittest.TestCase):
    def test_store_files_untouched_by_a_full_read(self) -> None:
        before = _snapshot(self.fx.mail_root)
        opened = self.open_store()
        try:
            for mailbox in opened.mailboxes:
                opened.mailbox_dir(mailbox)
                opened.mailbox(mailbox.rowid)
            opened.fingerprint()
            opened.resolve_mailbox(fixtures.ACCOUNT_GMAIL, "inbox")
            opened.connection.execute("SELECT COUNT(*) FROM messages").fetchone()
        finally:
            opened.close()
        after = _snapshot(self.fx.mail_root)
        self.assertEqual(after, before)
        self.assertFalse((self.fx.envelope_index.parent / "Envelope Index-shm").exists())
        self.assertFalse((self.fx.envelope_index.parent / "Envelope Index-wal").exists())

    def test_connection_has_query_only_enabled(self) -> None:
        opened = self.open_store()
        try:
            self.assertEqual(
                opened.connection.execute("PRAGMA query_only").fetchone()[0], 1
            )
            with self.assertRaises(sqlite3.Error):
                opened.connection.execute("CREATE TABLE should_not_work (x INTEGER)")
        finally:
            opened.close()


class MailboxCatalogTests(StoreTestCase, unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.opened = self.open_store()
        self.addCleanup(self.opened.close)

    def test_catalog_matches_fixture(self) -> None:
        mailboxes = self.opened.mailboxes
        rowids = (1, 2, 3, 5, 6, 7, 8)
        self.assertEqual(len(mailboxes), len(rowids))
        self.assertEqual(mailboxes, tuple(self.opened.mailbox(rowid) for rowid in rowids))
        with self.assertRaises(KeyError):
            self.opened.mailbox(999)

    def test_gmail_url_is_percent_decoded(self) -> None:
        mailbox = self.opened.mailbox(fixtures.MAILBOX_GMAIL_ALL_MAIL)
        self.assertEqual(mailbox.url, fixtures.MAILBOX_URLS[fixtures.MAILBOX_GMAIL_ALL_MAIL])
        self.assertEqual(mailbox.name, "All Mail")
        self.assertEqual(mailbox.path, "[Gmail]/All Mail")
        self.assertEqual(mailbox.account_uuid, fixtures.ACCOUNT_GMAIL)
        self.assertEqual(mailbox.account_kind, "imap")
        self.assertFalse(mailbox.is_inbox)
        self.assertTrue(mailbox.is_aggregate)
        self.assertEqual(
            self.opened.mailbox(fixtures.MAILBOX_GMAIL_IMPORTANT).path,
            "[Gmail]/Important",
        )

    def test_inbox_flags(self) -> None:
        self.assertTrue(self.opened.mailbox(fixtures.MAILBOX_ICLOUD_INBOX).is_inbox)
        self.assertTrue(self.opened.mailbox(fixtures.MAILBOX_GMAIL_INBOX).is_inbox)
        self.assertTrue(self.opened.mailbox(fixtures.MAILBOX_ICLOUD_INBOX).is_aggregate is False)

    def test_local_mailbox(self) -> None:
        mailbox = self.opened.mailbox(fixtures.MAILBOX_LOCAL_RECOVERED)
        self.assertEqual(mailbox.account_uuid, fixtures.ACCOUNT_LOCAL)
        self.assertEqual(mailbox.account_kind, "local")
        self.assertEqual(mailbox.name, "Recovered Messages")
        self.assertEqual(mailbox.path, "Recovered Messages")

    def test_resolve_mailbox_by_name_path_and_url(self) -> None:
        self.assertEqual(
            self.opened.resolve_mailbox(fixtures.ACCOUNT_GMAIL, "inbox").rowid,
            fixtures.MAILBOX_GMAIL_INBOX,
        )
        self.assertEqual(
            self.opened.resolve_mailbox(fixtures.ACCOUNT_GMAIL, "[gmail]/ALL MAIL").rowid,
            fixtures.MAILBOX_GMAIL_ALL_MAIL,
        )
        self.assertEqual(
            self.opened.resolve_mailbox(
                fixtures.ACCOUNT_GMAIL,
                fixtures.MAILBOX_URLS[fixtures.MAILBOX_GMAIL_IMPORTANT],
            ).rowid,
            fixtures.MAILBOX_GMAIL_IMPORTANT,
        )
        self.assertEqual(
            self.opened.resolve_mailbox(
                fixtures.ACCOUNT_GMAIL,
                f"imap://{fixtures.ACCOUNT_GMAIL}/[Gmail]/All Mail",
            ).rowid,
            fixtures.MAILBOX_GMAIL_ALL_MAIL,
        )

    def test_resolve_mailbox_is_case_insensitive_on_account(self) -> None:
        self.assertEqual(
            self.opened.resolve_mailbox(fixtures.ACCOUNT_ICLOUD.lower(), "INBOX").rowid,
            fixtures.MAILBOX_ICLOUD_INBOX,
        )

    def test_resolve_mailbox_absent_or_other_account(self) -> None:
        self.assertIsNone(self.opened.resolve_mailbox(fixtures.ACCOUNT_ICLOUD, "Nope"))
        self.assertIsNone(self.opened.resolve_mailbox(fixtures.ACCOUNT_ICLOUD, "All Mail"))
        self.assertIsNone(self.opened.resolve_mailbox(fixtures.ACCOUNT_ICLOUD, ""))
        self.assertIsNone(self.opened.resolve_mailbox("unknown-account", "INBOX"))

    def test_mailbox_dir_formula(self) -> None:
        icloud_inbox = self.opened.mailbox_dir(
            self.opened.mailbox(fixtures.MAILBOX_ICLOUD_INBOX)
        )
        self.assertEqual(
            icloud_inbox,
            self.fx.mail_root / fixtures.VERSION / fixtures.ACCOUNT_ICLOUD / "INBOX.mbox",
        )
        self.assertTrue(icloud_inbox.is_dir())
        all_mail = self.opened.mailbox_dir(
            self.opened.mailbox(fixtures.MAILBOX_GMAIL_ALL_MAIL)
        )
        self.assertEqual(
            all_mail,
            self.fx.mail_root
            / fixtures.VERSION
            / fixtures.ACCOUNT_GMAIL
            / "[Gmail].mbox"
            / "All Mail.mbox",
        )
        self.assertTrue(all_mail.is_dir())
        local = self.opened.mailbox_dir(
            self.opened.mailbox(fixtures.MAILBOX_LOCAL_RECOVERED)
        )
        self.assertEqual(
            local,
            self.fx.mail_root
            / fixtures.VERSION
            / fixtures.ACCOUNT_LOCAL
            / "Recovered Messages.mbox",
        )

    def test_unicode_url_decoding_and_nfc_nfd_fallback(self) -> None:
        cafe = "Caf\u00e9"
        arbol = "\u00c1rbol"
        arbol_nfd = unicodedata.normalize("NFD", arbol)
        self.assertNotEqual(arbol, arbol_nfd)
        account_dir = self.fx.mail_root / fixtures.VERSION / fixtures.ACCOUNT_ICLOUD
        (account_dir / f"{cafe}.mbox").mkdir()
        (account_dir / f"{arbol_nfd}.mbox").mkdir()
        connection = sqlite3.connect(self.fx.envelope_index)
        try:
            connection.execute(
                "INSERT INTO mailboxes (ROWID, url) VALUES (?, ?)",
                (100, f"imap://{fixtures.ACCOUNT_ICLOUD}/{quote(cafe, safe='')}"),
            )
            connection.execute(
                "INSERT INTO mailboxes (ROWID, url) VALUES (?, ?)",
                (101, f"imap://{fixtures.ACCOUNT_ICLOUD}/{quote(arbol, safe='')}"),
            )
            connection.execute(
                "INSERT INTO mailboxes (ROWID, url) VALUES (?, ?)",
                (102, f"imap://{fixtures.ACCOUNT_ICLOUD}/Missing"),
            )
            connection.commit()
        finally:
            connection.close()

        opened = self.open_store()
        try:
            decoded = opened.mailbox(100)
            self.assertEqual(decoded.name, cafe)
            self.assertEqual(decoded.path, cafe)
            self.assertEqual(opened.mailbox_dir(decoded), account_dir / f"{cafe}.mbox")

            fallback = opened.mailbox(101)
            self.assertEqual(fallback.path, arbol)
            resolved = opened.mailbox_dir(fallback)
            self.assertTrue(resolved.is_dir())
            self.assertEqual(
                unicodedata.normalize("NFC", resolved.name),
                unicodedata.normalize("NFC", f"{arbol}.mbox"),
            )
            self.assertIn(
                resolved,
                (
                    account_dir / f"{arbol}.mbox",
                    account_dir / f"{arbol_nfd}.mbox",
                ),
            )

            missing = opened.mailbox(102)
            self.assertFalse(opened.mailbox_dir(missing).exists())
            self.assertEqual(
                opened.mailbox_dir(missing),
                account_dir / "Missing.mbox",
            )
        finally:
            opened.close()


class MailboxCounterTests(StoreTestCase, unittest.TestCase):
    EXPECTED = {
        fixtures.MAILBOX_ICLOUD_INBOX: (8, 3),
        fixtures.MAILBOX_ICLOUD_FACTURAS: (1, 0),
        fixtures.MAILBOX_ICLOUD_ARCHIVO: (1, 0),
        fixtures.MAILBOX_GMAIL_INBOX: (2, 1),
        fixtures.MAILBOX_GMAIL_ALL_MAIL: (3, 1),
        fixtures.MAILBOX_GMAIL_IMPORTANT: (0, 0),
        fixtures.MAILBOX_LOCAL_RECOVERED: (0, 0),
    }

    def setUp(self) -> None:
        super().setUp()
        self.opened = self.open_store()
        self.addCleanup(self.opened.close)

    def test_counters_are_recalculated(self) -> None:
        for rowid, expected in self.EXPECTED.items():
            mailbox = self.opened.mailbox(rowid)
            self.assertEqual(
                (mailbox.message_count, mailbox.unread_count),
                expected,
                f"counters differ for {mailbox.path!r}",
            )

    def test_fake_stored_counters_are_ignored(self) -> None:
        # The fixture stores deliberately wrong values for these mailboxes.
        self.assertEqual(fixtures.FAKE_COUNTERS[fixtures.MAILBOX_GMAIL_INBOX], (36, 0))
        self.assertEqual(
            self.opened.mailbox(fixtures.MAILBOX_GMAIL_INBOX).message_count, 2
        )
        self.assertEqual(fixtures.FAKE_COUNTERS[fixtures.MAILBOX_ICLOUD_INBOX], (9999, 9999))
        self.assertEqual(
            self.opened.mailbox(fixtures.MAILBOX_ICLOUD_INBOX).message_count, 8
        )

    def test_label_membership_counts_for_gmail_inbox(self) -> None:
        # 83160 and 83210 live in [Gmail]/All Mail and are INBOX members only
        # through the labels table.
        gmail_inbox = self.opened.mailbox(fixtures.MAILBOX_GMAIL_INBOX)
        self.assertEqual((gmail_inbox.message_count, gmail_inbox.unread_count), (2, 1))
        all_mail = self.opened.mailbox(fixtures.MAILBOX_GMAIL_ALL_MAIL)
        self.assertEqual((all_mail.message_count, all_mail.unread_count), (3, 1))

    def test_aggregate_and_empty_mailboxes(self) -> None:
        self.assertTrue(self.opened.mailbox(fixtures.MAILBOX_GMAIL_ALL_MAIL).is_aggregate)
        important = self.opened.mailbox(fixtures.MAILBOX_GMAIL_IMPORTANT)
        self.assertEqual((important.message_count, important.unread_count), (0, 0))

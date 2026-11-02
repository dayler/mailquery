"""Tests for :mod:`mailquery.accounts` against the synthetic Accounts4.sqlite."""

from __future__ import annotations

import dataclasses
import hashlib
import shutil
import sqlite3
import unittest
from pathlib import Path
from unittest import mock

from tests.fixtures import make_fixtures as fixtures
from mailquery import accounts as accounts_module
from mailquery.accounts import AccountLabel, AccountLabels, default_accounts_db_path


def _snapshot(root: Path) -> dict[str, tuple[int, int, str]]:
    """Return ``relpath -> (size, mtime_ns, sha256)`` for every file below root."""
    snapshot: dict[str, tuple[int, int, str]] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        stat = path.stat()
        snapshot[str(path.relative_to(root))] = (
            stat.st_size,
            stat.st_mtime_ns,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
    return snapshot


class AccountsTestCase(unittest.TestCase):
    """Build one synthetic store per test class (accounts tests are read-only)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.fx = fixtures.build_store()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.fx.cleanup()

    def setUp(self) -> None:
        self.tmp_dir = self.fx.root / f"tmp-{self._testMethodName}"

    def labels(self, db_path: Path | None = None) -> AccountLabels:
        return AccountLabels(
            self.fx.accounts_db if db_path is None else db_path,
            tmp_dir=self.tmp_dir,
        )

    def copy_accounts_db(self) -> Path:
        """Copy the fixture accounts database so a test can mutate it."""
        target = self.fx.root / f"accounts-{self._testMethodName}" / "Accounts4.sqlite"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.fx.accounts_db, target)
        return target

    def execute_on(self, db_path: Path, *statements: str) -> None:
        connection = sqlite3.connect(db_path)
        try:
            for statement in statements:
                connection.execute(statement)
            connection.commit()
        finally:
            connection.close()


class DefaultPathTests(unittest.TestCase):
    def test_default_accounts_db_path(self) -> None:
        expected = Path.home() / "Library" / "Accounts" / "Accounts4.sqlite"
        self.assertEqual(default_accounts_db_path(), expected)


class FixtureLabelTests(AccountsTestCase):
    def test_available(self) -> None:
        labels = self.labels()
        self.assertTrue(labels.available)
        self.assertIsNone(labels.warning)

    def test_all_exposes_only_mail_accounts(self) -> None:
        labels = self.labels()
        exposed = {label.uuid: label for label in labels.all()}
        self.assertEqual(
            set(exposed),
            {
                fixtures.ACCOUNT_ICLOUD,
                fixtures.ACCOUNT_GMAIL,
                fixtures.ACCOUNT_LOCAL,
            },
        )
        self.assertEqual(len(labels.all()), 3)

    def test_icloud_label_uses_parent_provider_and_email(self) -> None:
        label = self.labels().get(fixtures.ACCOUNT_ICLOUD)
        self.assertIsNotNone(label)
        self.assertEqual(label.label, fixtures.ICLOUD_LABEL)
        self.assertEqual(label.email, "fixture@icloud.com")
        self.assertEqual(label.provider, "iCloud")
        self.assertFalse(label.local)

    def test_gmail_label_uses_parent_provider_and_email(self) -> None:
        label = self.labels().get(fixtures.ACCOUNT_GMAIL)
        self.assertIsNotNone(label)
        self.assertEqual(label.label, fixtures.GMAIL_LABEL)
        self.assertEqual(label.email, "fixture@gmail.com")
        self.assertEqual(label.provider, "Gmail")
        self.assertFalse(label.local)

    def test_local_account_label(self) -> None:
        label = self.labels().get(fixtures.ACCOUNT_LOCAL)
        self.assertIsNotNone(label)
        self.assertEqual(label.label, fixtures.LOCAL_LABEL)
        self.assertTrue(label.local)
        self.assertIsNone(label.email)

    def test_non_mail_accounts_are_filtered_out(self) -> None:
        labels = self.labels()
        # Parent provider accounts and Apple ID authentication helpers are not
        # Mail store accounts (their identifiers never appear in mailbox URLs).
        for identifier in ("PARENT-ICLOUD", "PARENT-GMAIL", "NOT-A-MAIL-ACCOUNT"):
            self.assertIsNone(labels.get(identifier), identifier)
        self.assertNotIn(
            "NOT-A-MAIL-ACCOUNT", {label.uuid for label in labels.all()}
        )

    def test_get_is_case_insensitive(self) -> None:
        labels = self.labels()
        for spelling in (
            fixtures.ACCOUNT_ICLOUD,
            fixtures.ACCOUNT_ICLOUD.lower(),
            fixtures.ACCOUNT_ICLOUD.upper(),
            f"  {fixtures.ACCOUNT_ICLOUD}  ",
        ):
            found = labels.get(spelling)
            self.assertIsNotNone(found, spelling)
            self.assertEqual(found.uuid, fixtures.ACCOUNT_ICLOUD)

    def test_get_unknown_or_empty(self) -> None:
        labels = self.labels()
        self.assertIsNone(labels.get("UNKNOWN-UUID"))
        self.assertIsNone(labels.get(""))
        self.assertIsNone(labels.get(None))

    def test_label_for_known_account(self) -> None:
        labels = self.labels()
        self.assertEqual(labels.label_for(fixtures.ACCOUNT_GMAIL), fixtures.GMAIL_LABEL)
        self.assertEqual(labels.label_for(fixtures.ACCOUNT_LOCAL), fixtures.LOCAL_LABEL)

    def test_label_for_unknown_falls_back_to_uuid(self) -> None:
        labels = self.labels()
        self.assertEqual(labels.label_for("UNKNOWN-UUID"), "UNKNOWN-UUID")

    def test_labels_are_available_lazily(self) -> None:
        labels = self.labels()
        self.assertFalse(labels._loaded)
        with mock.patch.object(
            AccountLabels, "_read_rows", wraps=labels._read_rows
        ) as read_rows:
            self.assertTrue(labels.available)
            self.assertEqual(len(labels.all()), 3)
            self.assertEqual(labels.label_for(fixtures.ACCOUNT_LOCAL), fixtures.LOCAL_LABEL)
        self.assertEqual(read_rows.call_count, 1)

    def test_account_label_dataclass_has_no_credentials(self) -> None:
        fields = {field.name for field in dataclasses.fields(AccountLabel)}
        self.assertEqual(fields, {"uuid", "label", "email", "provider", "local"})

    def test_query_never_reads_credentials(self) -> None:
        sql = accounts_module._LABEL_QUERY.upper()
        for forbidden in (
            "CREDENTIAL",
            "PASSWORD",
            "TOKEN",
            "ZDATACLASSPROPERTIES",
            "ZAUTHENTICATIONTYPE",
            "ZCREDENTIALTYPE",
        ):
            self.assertNotIn(forbidden, sql)

    def test_read_only_no_side_effects(self) -> None:
        accounts_dir = self.fx.accounts_db.parent
        before = _snapshot(accounts_dir)
        labels = self.labels()
        self.assertTrue(labels.available)
        self.assertEqual(len(labels.all()), 3)
        after = _snapshot(accounts_dir)
        self.assertEqual(after, before)
        self.assertFalse((accounts_dir / "Accounts4.sqlite-shm").exists())
        self.assertFalse((accounts_dir / "Accounts4.sqlite-wal").exists())

    def test_copy_is_cleaned_up(self) -> None:
        labels = self.labels()
        self.assertTrue(labels.available)
        self.assertTrue(self.tmp_dir.exists())
        self.assertEqual(list(self.tmp_dir.iterdir()), [])


class UnavailableLabelsTests(AccountsTestCase):
    def test_missing_database(self) -> None:
        labels = self.labels(self.fx.root / "no-such" / "Accounts4.sqlite")
        self.assertFalse(labels.available)
        self.assertEqual(labels.all(), [])
        self.assertIn("not found", labels.warning)
        self.assertEqual(labels.label_for("ABC-UUID"), "ABC-UUID")

    def test_schema_feature_detection_failure(self) -> None:
        db_path = self.copy_accounts_db()
        self.execute_on(db_path, "DROP TABLE ZACCOUNTTYPE")
        labels = self.labels(db_path)
        self.assertFalse(labels.available)
        self.assertIn("unsupported accounts schema", labels.warning)
        self.assertIn("ZACCOUNTTYPE", labels.warning)
        self.assertEqual(labels.label_for("ABC-UUID"), "ABC-UUID")

    def test_file_that_is_not_a_database(self) -> None:
        db_path = self.fx.root / f"garbage-{self._testMethodName}" / "Accounts4.sqlite"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db_path.write_bytes(b"this is not a sqlite database")
        labels = self.labels(db_path)
        self.assertFalse(labels.available)
        self.assertEqual(labels.all(), [])
        self.assertEqual(labels.label_for("ABC-UUID"), "ABC-UUID")

    def test_locked_database_is_treated_as_unavailable(self) -> None:
        with mock.patch.object(
            accounts_module,
            "_connect_readonly",
            side_effect=sqlite3.OperationalError("database is locked"),
        ) as connect, mock.patch.object(accounts_module.time, "sleep") as sleep:
            labels = self.labels()
            self.assertFalse(labels.available)
        self.assertEqual(connect.call_count, 2)
        sleep.assert_called_once_with(0.1)
        self.assertIn("locked", labels.warning)

    def test_refuses_temporary_directory_inside_accounts_directory(self) -> None:
        accounts_dir = self.fx.accounts_db.parent
        labels = AccountLabels(self.fx.accounts_db, tmp_dir=accounts_dir)
        self.assertFalse(labels.available)
        self.assertIn("refusing", labels.warning)
        self.assertEqual(
            sorted(entry.name for entry in accounts_dir.iterdir()),
            ["Accounts4.sqlite"],
        )

    def test_available_without_any_mail_account(self) -> None:
        db_path = self.copy_accounts_db()
        self.execute_on(db_path, "DELETE FROM ZACCOUNT WHERE ZACCOUNTTYPE IN (40, 53)")
        labels = self.labels(db_path)
        self.assertTrue(labels.available)
        self.assertEqual(labels.all(), [])
        self.assertEqual(labels.label_for("ABC-UUID"), "ABC-UUID")


class LabelRuleTests(AccountsTestCase):
    def test_ambiguous_labels_across_two_accounts(self) -> None:
        db_path = self.copy_accounts_db()
        self.execute_on(
            db_path,
            "INSERT INTO ZACCOUNT (Z_PK, ZACCOUNTTYPE, ZPARENTACCOUNT, ZIDENTIFIER) "
            "VALUES (7, 40, 10, 'DDDDDDDD-0000-4000-8000-000000000007')",
        )
        labels = self.labels(db_path)
        self.assertTrue(labels.available)
        matching = [label for label in labels.all() if label.label == fixtures.ICLOUD_LABEL]
        self.assertEqual(len(matching), 2)
        self.assertEqual(
            {label.uuid for label in matching},
            {
                fixtures.ACCOUNT_ICLOUD,
                "DDDDDDDD-0000-4000-8000-000000000007",
            },
        )

    def test_standalone_imap_account_without_parent(self) -> None:
        db_path = self.copy_accounts_db()
        self.execute_on(
            db_path,
            "INSERT INTO ZACCOUNT (Z_PK, ZACCOUNTTYPE, ZIDENTIFIER, ZUSERNAME) "
            "VALUES (7, 40, 'DDDDDDDD-0000-4000-8000-000000000007', "
            "'standalone@example.com')",
        )
        label = self.labels(db_path).get("DDDDDDDD-0000-4000-8000-000000000007")
        self.assertIsNotNone(label)
        self.assertEqual(label.label, "IMAP (standalone@example.com)")
        self.assertEqual(label.provider, "IMAP")
        self.assertEqual(label.email, "standalone@example.com")
        self.assertFalse(label.local)

    def test_parent_without_email_uses_description(self) -> None:
        db_path = self.copy_accounts_db()
        self.execute_on(
            db_path,
            "INSERT INTO ZACCOUNT (Z_PK, ZACCOUNTTYPE, ZACCOUNTDESCRIPTION, ZIDENTIFIER) "
            "VALUES (11, 52, 'iCloud', 'PARENT-NOEMAIL')",
            "INSERT INTO ZACCOUNT (Z_PK, ZACCOUNTTYPE, ZPARENTACCOUNT, ZIDENTIFIER) "
            "VALUES (12, 40, 11, 'FFFFFFFF-0000-4000-8000-000000000012')",
        )
        label = self.labels(db_path).get("FFFFFFFF-0000-4000-8000-000000000012")
        self.assertIsNotNone(label)
        self.assertEqual(label.label, "iCloud")
        self.assertIsNone(label.email)
        self.assertEqual(label.provider, "iCloud")

    def test_imap_without_email_uses_type_description(self) -> None:
        db_path = self.copy_accounts_db()
        self.execute_on(
            db_path,
            "INSERT INTO ZACCOUNT (Z_PK, ZACCOUNTTYPE, ZIDENTIFIER) "
            "VALUES (7, 40, 'DDDDDDDD-0000-4000-8000-000000000007')",
        )
        label = self.labels(db_path).get("DDDDDDDD-0000-4000-8000-000000000007")
        self.assertIsNotNone(label)
        self.assertEqual(label.label, "IMAP")
        self.assertIsNone(label.email)

    def test_duplicate_identifier_keeps_first_row(self) -> None:
        db_path = self.copy_accounts_db()
        self.execute_on(
            db_path,
            "INSERT INTO ZACCOUNT (Z_PK, ZACCOUNTTYPE, ZPARENTACCOUNT, ZIDENTIFIER) "
            f"VALUES (7, 40, 10, '{fixtures.ACCOUNT_ICLOUD}')",
        )
        labels = self.labels(db_path)
        self.assertEqual(len(labels.all()), 3)
        kept = labels.get(fixtures.ACCOUNT_ICLOUD)
        self.assertIsNotNone(kept)
        self.assertEqual(kept.uuid, fixtures.ACCOUNT_ICLOUD)

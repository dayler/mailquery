"""Outlook backend tests (plan 7.5).

This module starts with sanity tests of the in-memory Outlook Object Model fake
(``tests/fakes/outlook.py``) and of the subprocess launcher
(``tests/fakes/run_cli.py``): every scenario builds, every member access is
logged and mutations are counted. The OL-* cases follow (W3-T02 onwards).
Pure Python: runs on Linux, macOS and Windows without pywin32 or Outlook; the
only exception is OL-05.02, which needs a real Windows host (plan 7.7).
"""

from __future__ import annotations

import ast
import importlib.abc
import importlib.machinery
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest import mock

from tests.fakes import outlook as fk
from tests.fakes import run_cli
from tests.fixtures.make_fixtures import prefixed_uid

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC_ROOT = _REPO_ROOT / "src"


def _connect(fake: fk.FakeOutlook):
    return fake.GetActiveObject("Outlook.Application")


def _stores(fake: fk.FakeOutlook) -> dict[str, object]:
    """COM Store objects of the fake keyed by their spec key (profile order)."""
    stores = _connect(fake).Session.Stores
    return {spec.key: stores.Item(index + 1) for index, spec in enumerate(fake.stores)}


def _walk(folder, depth: int = 0) -> list[tuple[int, object]]:
    out = []
    children = folder.Folders
    for index in range(1, children.Count + 1):
        child = children.Item(index)
        out.append((depth, child))
        out.extend(_walk(child, depth + 1))
    return out


class FakeConnectionTests(unittest.TestCase):
    def test_connect_logs_get_active_object_and_never_dispatch(self) -> None:
        fake = fk.FakeOutlook.default()
        app = _connect(fake)
        self.assertEqual(app.Version, "16.0.0.20430")
        self.assertEqual(
            fake.call_log.count(kind="Connector", member="GetActiveObject", action="call"), 1
        )
        self.assertEqual(fake.call_log.count(member="Dispatch"), 0)
        self.assertEqual(fake.mutations.total, 0)

    def test_not_running_raises_mk_e_unavailable(self) -> None:
        fake = fk.FakeOutlook.default()
        fake.running = False
        with self.assertRaises(fk.com_error) as caught:
            _connect(fake)
        self.assertEqual(fk.hresult_of(caught.exception), fk.MK_E_UNAVAILABLE)
        self.assertLess(caught.exception.hresult, 0)  # signed, like pywin32

    def test_dispatch_variants_count_as_forbidden(self) -> None:
        fake = fk.FakeOutlook.default()
        fake.Dispatch("Outlook.Application")
        fake.DispatchEx("Outlook.Application")
        fake.EnsureDispatch("Outlook.Application")
        self.assertEqual(fake.mutations.forbidden_calls, 3)
        self.assertEqual(fake.call_log.count(kind="Connector", action="forbidden"), 3)

    def test_registry_and_security_center_variants(self) -> None:
        self.assertEqual(
            fk.FakeRegistry.outlook(16).get_value("HKCR", fk.CURVER_KEY), "Outlook.Application.16"
        )
        self.assertEqual(
            fk.FakeRegistry.outlook(15).get_value("hkcr", fk.CURVER_KEY.lower()),
            "Outlook.Application.15",
        )
        with self.assertRaises(FileNotFoundError):
            fk.FakeRegistry.unregistered().get_value("HKCR", fk.CURVER_KEY)
        self.assertTrue(fk.FakeSecurityCenter.active().antivirus_products())
        self.assertEqual(fk.FakeSecurityCenter.none().antivirus_products(), [])
        with self.assertRaises(OSError):
            fk.FakeSecurityCenter.unavailable().antivirus_products()
        inactive = fk.FakeSecurityCenter.inactive().antivirus_products()[0]
        self.assertFalse(inactive["productState"] & 0x1000)


class FakeCallLogTests(unittest.TestCase):
    def test_every_member_access_is_logged_with_its_kind(self) -> None:
        fake = fk.FakeOutlook.default()
        store = _stores(fake)["exchange"]
        store.DisplayName
        inbox = store.GetDefaultFolder(fk.OL_FOLDER_INBOX)
        inbox.Name
        members = fake.call_log.members()
        for expected in (
            ("Application", "Session"),
            ("NameSpace", "Stores"),
            ("Stores", "Item"),
            ("Store", "DisplayName"),
            ("Store", "GetDefaultFolder"),
            ("Folder", "Name"),
        ):
            self.assertIn(expected, members)
        entry = [e for e in fake.call_log if e.member == "GetDefaultFolder"][0]
        self.assertEqual((entry.action, entry.args), ("call", (fk.OL_FOLDER_INBOX,)))

    def test_fake_members_are_exactly_the_documented_whitelist(self) -> None:
        for kind, cls in fk.COM_CLASSES.items():
            self.assertEqual(set(cls.member_names()), set(fk.OOM_MEMBERS[kind]), kind)
        self.assertEqual(set(fk.COM_CLASSES), set(fk.OOM_MEMBERS))

    def test_unknown_member_raises_attribute_error_and_is_logged(self) -> None:
        fake = fk.FakeOutlook.default()
        app = _connect(fake)
        with self.assertRaises(AttributeError):
            app.GetNamespace
        self.assertEqual(fake.call_log.count(member="GetNamespace", action="unknown"), 1)
        self.assertEqual(fake.mutations.total, 0)

    def test_member_names_are_case_insensitive_and_logged_as_written(self) -> None:
        fake = fk.FakeOutlook.default()
        self.assertEqual(_connect(fake).version, "16.0.0.20430")
        self.assertEqual(fake.call_log.count(kind="Application", member="version"), 1)


class FakeMutationTests(unittest.TestCase):
    def test_assignment_is_counted_and_not_applied(self) -> None:
        fake = fk.FakeOutlook.default()
        spec = fake.item("normal")
        item = _connect(fake).Session.GetItemFromID(spec.entry_id, spec.folder.store.store_id)
        item.UnRead = False
        item.Body = "changed"
        self.assertEqual(fake.mutations.assignments, 2)
        self.assertEqual(item.Body, spec.body)
        self.assertEqual(fake.call_log.count(kind="Item", action="set"), 2)

    def test_forbidden_members_are_counted(self) -> None:
        fake = fk.FakeOutlook.default()
        spec = fake.item("normal")
        session = _connect(fake).Session
        item = session.GetItemFromID(spec.entry_id)
        item.Delete()
        item.Move(None)
        item.Recipients.Item(1).AddressEntry
        store = _stores(fake)["exchange"]
        store.GetRootFolder().Folders.Add("x")
        self.assertEqual(fake.mutations.forbidden_calls, 4)
        self.assertEqual(fake.call_log.count(action="forbidden"), 4)
        self.assertEqual([f.name for f in spec.folder.store.root.children][0], "Inbox")
        self.assertEqual(store.GetRootFolder().Folders.Count, 7)  # Folders.Add did nothing

    def test_columns_add_is_not_a_mutation(self) -> None:
        fake = fk.FakeOutlook.default()
        inbox = _stores(fake)["exchange"].GetDefaultFolder(fk.OL_FOLDER_INBOX)
        table = inbox.GetTable("", fk.OL_USER_ITEMS)
        table.Columns.Add(fk.PR_SUBJECT)
        self.assertEqual(fake.mutations.total, 0)


class FakeFailureTests(unittest.TestCase):
    def test_transient_rejection_once_then_success(self) -> None:
        fake = fk.FakeOutlook.default()
        app = _connect(fake)
        fake.reject_next(times=1)
        with self.assertRaises(fk.com_error) as caught:
            app.Session
        self.assertEqual(fk.hresult_of(caught.exception), fk.RPC_E_CALL_REJECTED)
        self.assertIsNotNone(app.Session)

    def test_transient_rejection_twice(self) -> None:
        fake = fk.FakeOutlook.default()
        app = _connect(fake)
        fake.reject_next(times=2, hresult=fk.RPC_E_SERVERCALL_RETRYLATER)
        for _ in range(2):
            with self.assertRaises(fk.com_error):
                app.Session
        app.Session

    def test_access_denied_and_unknown_hresult_on_a_given_member(self) -> None:
        fake = fk.FakeOutlook.default()
        session = _connect(fake).Session
        fake.fail_next(fk.E_ACCESSDENIED, kind="NameSpace", member="Stores")
        fake.fail_next(fk.E_UNEXPECTED, kind="NameSpace", member="Accounts")
        session.GetItemFromID(fake.item("normal").entry_id)  # other members unaffected
        with self.assertRaises(fk.com_error) as denied:
            session.Stores
        with self.assertRaises(fk.com_error) as unknown:
            session.Accounts
        self.assertEqual(fk.hresult_of(denied.exception), fk.E_ACCESSDENIED)
        self.assertEqual(fk.hresult_of(unknown.exception), fk.E_UNEXPECTED)

    def test_failure_skip_targets_a_later_call(self) -> None:
        fake = fk.FakeOutlook.default()
        app = _connect(fake)
        fake.fail_next(fk.E_FAIL, skip=1)
        app.Version
        with self.assertRaises(fk.com_error):
            app.Version

    def test_hang_blocks_until_released(self) -> None:
        fake = fk.FakeOutlook.default()
        app = _connect(fake)
        fake.hang_next(kind="Application", member="Session", timeout=5.0)
        threading.Timer(0.2, fake.release).start()
        started = time.monotonic()
        app.Session
        elapsed = time.monotonic() - started
        self.assertGreaterEqual(elapsed, 0.15)
        self.assertLess(elapsed, 4.0)
        self.assertEqual(fake.hangs, 1)

    def test_missing_property_is_wrapped_not_found(self) -> None:
        fake = fk.FakeOutlook.item_matrix()
        spec = fake.item("internal_no_headers")
        item = _connect(fake).Session.GetItemFromID(spec.entry_id)
        with self.assertRaises(fk.com_error) as caught:
            item.PropertyAccessor.GetProperty(fk.PR_TRANSPORT_MESSAGE_HEADERS)
        self.assertEqual(caught.exception.hresult, fk.to_signed(fk.DISP_E_EXCEPTION))
        self.assertEqual(fk.hresult_of(caught.exception), fk.MAPI_E_NOT_FOUND)
        self.assertEqual(len(caught.exception.args), 4)

    def test_malformed_schema_name_is_invalid_arg(self) -> None:
        fake = fk.FakeOutlook.default()
        store = _stores(fake)["exchange"]
        with self.assertRaises(fk.com_error) as caught:
            store.PropertyAccessor.GetProperty("http://schemas.microsoft.com/mapi/proptag/0FF90102")
        self.assertEqual(fk.hresult_of(caught.exception), fk.E_INVALIDARG)

    def test_hresult_of_reads_direct_wrapped_and_foreign_shapes(self) -> None:
        class Foreign(Exception):
            pass

        foreign = Foreign(fk.to_signed(fk.RPC_E_CALL_REJECTED), "rejected", None, None)
        self.assertEqual(fk.hresult_of(foreign), fk.RPC_E_CALL_REJECTED)
        wrapped = fk.make_com_error(fk.MAPI_E_LOGON_FAILED, wrapped=True)
        self.assertEqual(fk.hresult_of(wrapped), fk.MAPI_E_LOGON_FAILED)
        self.assertIsNone(fk.hresult_of(ValueError("x")))


class FakeScenarioTests(unittest.TestCase):
    def test_default_profile_is_the_golden_profile(self) -> None:
        fake = fk.FakeOutlook.default()
        self.assertEqual([s.key for s in fake.stores], ["exchange", "shared"])
        self.assertEqual(len(fake.accounts), 1)
        account = _connect(fake).Session.Accounts.Item(1)
        self.assertEqual(account.AccountType, fk.OL_EXCHANGE)
        self.assertEqual(account.DeliveryStore.StoreID, fake.store("exchange").store_id)
        exchange = _stores(fake)["exchange"]
        self.assertTrue(exchange.IsCachedExchange)
        self.assertEqual(_stores(fake)["shared"].ExchangeStoreType, fk.OL_EXCHANGE_MAILBOX)
        inbox = fake.store("exchange").inbox
        self.assertEqual(
            [i.key for i in inbox.items], ["normal", "header_only", "smime_encrypted"]
        )
        self.assertTrue(fake.item("normal").has_attachments)
        self.assertEqual(fake.item("header_only").download_state, fk.OL_HEADER_ONLY)
        self.assertEqual(fake.item("smime_encrypted").message_class, "IPM.Note.SMIME")
        self.assertEqual(fake.store("exchange").uuid, "D70DBCF6-1C2A-4B6E-9A51-E0C3B2A49F10")
        self.assertEqual(fake.mutations.total, 0)

    def test_store_matrix_builds_every_store_kind(self) -> None:
        fake = fk.FakeOutlook.store_matrix()
        stores = _stores(fake)
        expected = {
            "exchange_cached", "exchange_online", "shared", "public", "imap", "pop3", "eas",
            "pst", "pst_no_inbox", "pst_removable", "pst_unc", "pst_mapped", "other_type",
            "exchange_archive", "unavailable_named", "unavailable_unnamed",
        }
        self.assertEqual(set(stores), expected)
        self.assertTrue(stores["exchange_cached"].IsCachedExchange)
        self.assertFalse(stores["exchange_online"].IsCachedExchange)
        self.assertEqual(stores["public"].ExchangeStoreType, fk.OL_EXCHANGE_PUBLIC_FOLDER)
        self.assertEqual(stores["pst"].ExchangeStoreType, fk.OL_NOT_EXCHANGE)
        types = {
            fake.account_for(key).account_type
            for key in ("exchange_cached", "imap", "pop3", "eas", "other_type")
        }
        self.assertEqual(types, {fk.OL_EXCHANGE, fk.OL_IMAP, fk.OL_POP3, fk.OL_EAS, fk.OL_HTTP})
        self.assertTrue(stores["pop3"].FilePath.endswith(".pst"))
        self.assertTrue(stores["pst_unc"].FilePath.startswith("\\\\"))
        self.assertEqual(fake.drive_type("E:\\"), fk.DRIVE_REMOVABLE)
        self.assertEqual(fake.drive_type(stores["pst_mapped"].FilePath[:2] + "\\"), fk.DRIVE_REMOTE)
        self.assertEqual(fake.drive_type("C:\\"), fk.DRIVE_FIXED)
        with self.assertRaises(fk.com_error) as no_inbox:
            stores["pst_no_inbox"].GetDefaultFolder(fk.OL_FOLDER_INBOX)
        self.assertEqual(fk.hresult_of(no_inbox.exception), fk.MAPI_E_NOT_FOUND)
        self.assertTrue(stores["unavailable_named"].DisplayName)
        with self.assertRaises(fk.com_error) as named:
            stores["unavailable_named"].ExchangeStoreType
        self.assertEqual(fk.hresult_of(named.exception), fk.MAPI_E_LOGON_FAILED)
        with self.assertRaises(fk.com_error):
            stores["unavailable_unnamed"].DisplayName
        keys = [s.record_key for s in fake.stores]
        self.assertEqual(len(set(keys)), len(keys))
        self.assertTrue(all(len(k) == 16 for k in keys))
        record_key = stores["imap"].PropertyAccessor.GetProperty(fk.PR_RECORD_KEY)
        self.assertIsInstance(record_key, memoryview)
        self.assertEqual(bytes(record_key), fake.store("imap").record_key)
        for spec in fake.stores:
            if spec.unavailable is None:
                self.assertTrue(any(f.items for f in spec.walk()), spec.key)

    def test_folder_matrix_builds_localized_and_special_folders(self) -> None:
        fake = fk.FakeOutlook.folder_matrix()
        stores = _stores(fake)
        self.assertEqual(stores["es"].GetDefaultFolder(fk.OL_FOLDER_INBOX).Name, "Bandeja de entrada")
        self.assertEqual(stores["de"].GetDefaultFolder(fk.OL_FOLDER_INBOX).Name, "Posteingang")
        walked = _walk(stores["es"].GetRootFolder())
        by_id = {folder.EntryID: (depth, folder) for depth, folder in walked}
        for kind in fk.SYNC_FOLDER_IDS:
            self.assertIn(stores["es"].GetDefaultFolder(kind).EntryID, by_id)
        sync = fake.store("es").default_folders[fk.OL_FOLDER_SYNC_ISSUES]
        self.assertEqual(len(sync.children), 3)
        self.assertTrue(any(child.children for child in sync.children))
        item_types = {folder.DefaultItemType for _, folder in walked}
        self.assertTrue({fk.OL_MAIL_ITEM, fk.OL_APPOINTMENT_ITEM, fk.OL_CONTACT_ITEM, fk.OL_TASK_ITEM} <= item_types)
        folder_types = {
            folder.PropertyAccessor.GetProperty(fk.PR_FOLDER_TYPE) for _, folder in walked
        }
        self.assertEqual(folder_types, {fk.FOLDER_GENERIC, fk.FOLDER_SEARCH})
        names = [folder.Name for _, folder in walked]
        self.assertTrue(any("/" in n for n in names))
        self.assertTrue(any("%" in n for n in names))
        self.assertTrue(any(any(ord(c) > 127 for c in n) for n in names))
        self.assertEqual(names.count("Facturas"), 2)
        self.assertIn("Inbox", names)  # a plain folder named Inbox that is not the INBOX
        hidden_item = fake.item("in_hidden_folder")
        self.assertIs(hidden_item.folder.parent, sync)

    def test_item_matrix_covers_every_item_case(self) -> None:
        now = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
        fake = fk.FakeOutlook.item_matrix(now=now)
        expected = {
            "normal", "smime_encrypted", "smime_signed", "header_only", "meeting_request",
            "delivery_receipt", "task", "imap_deleted", "html_only", "html_no_text",
            "no_message_id", "empty_message_id", "internal_no_headers", "no_smtp",
            "exchange_dn", "flagged", "flagged_completed", "visible_attachment",
            "hidden_attachment", "unopenable_with_attachments", "unopenable_without_attachments",
            "duplicate_inbox", "duplicate_facturas", "facturas_recent", "same_date_a",
            "same_date_b", "dst_before", "dst_after",
        }
        self.assertTrue(expected <= set(fake.items))
        session = _connect(fake).Session

        def open_item(key):
            return session.GetItemFromID(fake.item(key).entry_id)

        self.assertEqual(open_item("header_only").DownloadState, fk.OL_HEADER_ONLY)
        with self.assertRaises(AttributeError):
            open_item("meeting_request").HTMLBody
        self.assertEqual(open_item("html_only").Body, "")
        self.assertTrue(open_item("html_only").HTMLBody)
        for key in ("unopenable_with_attachments", "unopenable_without_attachments"):
            with self.assertRaises(fk.com_error):
                open_item(key)
        self.assertTrue(fake.item("unopenable_with_attachments").has_attachments)
        self.assertFalse(fake.item("unopenable_without_attachments").has_attachments)
        hidden = open_item("hidden_attachment").Attachments.Item(1)
        self.assertIs(hidden.PropertyAccessor.GetProperty(fk.PR_ATTACHMENT_HIDDEN), True)
        self.assertFalse(fake.item("hidden_attachment").has_attachments)
        visible = open_item("visible_attachment").Attachments.Item(1)
        with self.assertRaises(fk.com_error):
            visible.PropertyAccessor.GetProperty(fk.PR_ATTACHMENT_HIDDEN)
        self.assertEqual(visible.FileName, "contrato.pdf")
        recipient = open_item("no_smtp").Recipients.Item(1)
        with self.assertRaises(fk.com_error):
            recipient.PropertyAccessor.GetProperty(fk.PR_SMTP_ADDRESS)
        self.assertEqual(recipient.PropertyAccessor.GetProperty(fk.PR_ADDRTYPE), "EX")
        dn = open_item("exchange_dn").PropertyAccessor
        self.assertTrue(dn.GetProperty(fk.PR_SENDER_EMAIL_ADDRESS).startswith("/O="))
        self.assertIn("@", dn.GetProperty(fk.PR_SENDER_SMTP_ADDRESS))
        self.assertEqual(fake.item("flagged").flag_status, fk.FLAG_STATUS_FLAGGED)
        self.assertEqual(fake.item("flagged_completed").flag_status, fk.FLAG_STATUS_COMPLETE)
        self.assertTrue(fake.item("imap_deleted").msg_status & fk.MSGSTATUS_DELMARKED)
        self.assertEqual(
            fake.item("duplicate_inbox").message_id, fake.item("duplicate_facturas").message_id
        )
        recent = fake.item("facturas_recent")
        self.assertEqual(recent.folder.name, "Facturas")
        self.assertLess(now - recent.received, timedelta(days=31))
        self.assertEqual(fake.item("same_date_a").received, fake.item("same_date_b").received)
        self.assertEqual(len(fake.item("normal").entry_id), 140)
        self.assertEqual(
            bytes.fromhex(fake.item("normal").entry_id)[4:20], fake.item("normal").folder.store.record_key
        )
        self.assertEqual(fake.mutations.total, 0)


class FakeTableTests(unittest.TestCase):
    def test_default_and_added_columns(self) -> None:
        fake = fk.FakeOutlook.default()
        inbox = _stores(fake)["exchange"].GetDefaultFolder(fk.OL_FOLDER_INBOX)
        table = inbox.GetTable("", fk.OL_USER_ITEMS)
        columns = table.Columns
        for name in (fk.PR_LONGTERM_ENTRYID_FROM_TABLE, fk.PR_MESSAGE_DELIVERY_TIME, fk.PR_INTERNET_MESSAGE_ID):
            columns.Add(name)
        self.assertEqual(table.GetRowCount(), 3)
        rows = []
        while not table.EndOfTable:
            rows.append(table.GetNextRow().GetValues())
        self.assertIsNone(table.GetNextRow())
        first = rows[0]
        self.assertEqual(len(first), 8)
        spec = fake.item("normal")
        self.assertEqual(first[0], spec.short_id)
        self.assertNotEqual(first[0], spec.entry_id)
        self.assertEqual(first[4], "IPM.Note")
        self.assertEqual(bytes(first[5]).hex().upper(), spec.entry_id)
        self.assertEqual(first[6], spec.received)
        self.assertEqual(first[6].tzinfo, timezone.utc)
        self.assertEqual(first[7], spec.message_id)

    def test_missing_value_in_table_is_none(self) -> None:
        fake = fk.FakeOutlook.item_matrix()
        folder = _connect(fake).Session.GetItemFromID(fake.item("no_message_id").entry_id).Parent
        table = folder.GetTable("", fk.OL_USER_ITEMS)
        table.Columns.Add(fk.PR_LONGTERM_ENTRYID_FROM_TABLE)
        table.Columns.Add(fk.PR_INTERNET_MESSAGE_ID)
        wanted = fake.item("no_message_id").entry_id
        while not table.EndOfTable:
            values = table.GetNextRow().GetValues()
            if bytes(values[5]).hex().upper() == wanted:
                self.assertIsNone(values[6])
                return
        self.fail("item not listed")

    def test_date_filter_grammar_ignores_seconds(self) -> None:
        fake = fk.FakeOutlook.default()
        inbox = _stores(fake)["exchange"].GetDefaultFolder(fk.OL_FOLDER_INBOX)
        received = fake.item("normal").received  # 13:54:09 UTC
        cut = received.strftime("%Y-%m-%d %H:%M")
        flt = f'@SQL="{fk.PR_MESSAGE_DELIVERY_TIME}" >= \'{cut}\''
        keys_at_minute = {r for r in self._keys(fake, inbox.GetTable(flt, fk.OL_USER_ITEMS))}
        self.assertIn("normal", keys_at_minute)
        later = (received + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M")
        flt2 = (
            f'@SQL=("{fk.PR_MESSAGE_DELIVERY_TIME}" >= \'2000-01-01 00:00\' AND '
            f'"{fk.PR_MESSAGE_DELIVERY_TIME}" < \'{later}\')'
        )
        self.assertIn("normal", self._keys(fake, inbox.GetTable(flt2, fk.OL_USER_ITEMS)))
        self.assertEqual(inbox.GetTable("", fk.OL_HIDDEN_ITEMS).GetRowCount(), 0)

    def test_unsupported_filter_is_rejected(self) -> None:
        fake = fk.FakeOutlook.default()
        inbox = _stores(fake)["exchange"].GetDefaultFolder(fk.OL_FOLDER_INBOX)
        with self.assertRaises(fk.FakeFilterError):
            inbox.GetTable("[Subject] = 'x'", fk.OL_USER_ITEMS)
        with self.assertRaises(fk.FakeFilterError):
            inbox.GetTable(f'@SQL="{fk.PR_SUBJECT}" = \'x\'', fk.OL_USER_ITEMS)

    @staticmethod
    def _keys(fake, table) -> set[str]:
        table.Columns.Add(fk.PR_LONGTERM_ENTRYID_FROM_TABLE)
        by_id = {spec.entry_id: key for key, spec in fake.items.items()}
        keys = set()
        while not table.EndOfTable:
            values = table.GetNextRow().GetValues()
            keys.add(by_id[bytes(values[5]).hex().upper()])
        return keys


class FakeZoneTests(unittest.TestCase):
    def test_zone_with_daylight_saving_transition(self) -> None:
        zone = fk.FakeZone.santiago()
        before = datetime(2026, 9, 6, 3, 30, tzinfo=timezone.utc).astimezone(zone)
        after = datetime(2026, 9, 6, 4, 30, tzinfo=timezone.utc).astimezone(zone)
        self.assertEqual(before.utcoffset(), timedelta(hours=-4))
        self.assertEqual(after.utcoffset(), timedelta(hours=-3))
        self.assertEqual(before.isoformat(), "2026-09-05T23:30:00-04:00")
        self.assertEqual(after.isoformat(), "2026-09-06T01:30:00-03:00")
        back = datetime(2027, 4, 4, 2, 30, tzinfo=timezone.utc).astimezone(zone)
        again = datetime(2027, 4, 4, 3, 30, tzinfo=timezone.utc).astimezone(zone)
        self.assertEqual(back.replace(tzinfo=None), again.replace(tzinfo=None))  # repeated hour
        self.assertEqual(back.utcoffset() - again.utcoffset(), timedelta(hours=1))
        self.assertEqual(fk.FakeZone.fixed(5.5).utcoffset(None), timedelta(hours=5, minutes=30))
        dst = fk.FakeOutlook.item_matrix()
        self.assertEqual(
            dst.item("dst_after").received - dst.item("dst_before").received, timedelta(hours=1)
        )


class RunCliTests(unittest.TestCase):
    def test_parse_args_splits_launcher_and_cli_options(self) -> None:
        options, argv = run_cli.parse_args(
            ["--scenario", "item_matrix", "--timeout", "0.2", "--hang", "NameSpace.Stores",
             "--", "search", "--since", "1d"]
        )
        self.assertEqual(options.scenario, "item_matrix")
        self.assertEqual(options.timeout, 0.2)
        self.assertEqual(argv, ["search", "--since", "1d"])

    def test_build_fake_applies_scenario_and_hang(self) -> None:
        fake = run_cli.build_fake("not_running")
        self.assertFalse(fake.running)
        fake = run_cli.build_fake("old_version")
        self.assertEqual(fake.registry.get_value("HKCR", fk.CURVER_KEY), "Outlook.Application.15")
        fake = run_cli.build_fake("default", hang="NameSpace.Stores", hang_timeout=0.05)
        session = _connect(fake).Session
        session.Stores
        self.assertEqual(fake.hangs, 1)
        with self.assertRaises(ValueError):
            run_cli.build_fake("nope")

    def test_list_scenarios_in_a_subprocess(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            env = dict(os.environ)
            env["HOME"] = env["USERPROFILE"] = home
            result = subprocess.run(
                [sys.executable, "-B", str(_REPO_ROOT / "tests" / "fakes" / "run_cli.py"),
                 "--list-scenarios"],
                capture_output=True,
                env=env,
                cwd=home,
                timeout=120,
                encoding="utf-8",
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), sorted(fk.SCENARIOS))


# --------------------------------------------------------------------------- #
# OL-* helpers
# --------------------------------------------------------------------------- #

HINT_DEPENDENCY = "pipx reinstall mailquery"
HINT_UNSUPPORTED = "install classic Outlook (version 16.0 or later); the new Outlook is not supported"
HINT_NOT_RUNNING = "open classic Outlook with the same user, without elevation, and retry"
#: `checks[].name` of the Outlook doctor, in the order of PRD 12.8.
_OUTLOOK_DOCTOR_CHECKS = (
    "python", "home", "driver", "pywin32", "outlook", "stores",
    "readonly_strategy", "object_model_guard", "config", "state", "lock",
)
_DOCTOR_TIMEOUT = "timeout after 30 s: Outlook did not respond (possible security prompt)"
_DISPATCH_NAMES = frozenset({"Dispatch", "DispatchEx", "EnsureDispatch"})


def _oc():
    """``mailquery.backends.outlook_com``, imported lazily (it is created in W3-T02)."""
    from mailquery.backends import outlook_com

    return outlook_com


def _backend(fake: fk.FakeOutlook, **overrides):
    """The production Outlook backend over the fake (plan 4.2 injection)."""
    from mailquery.backends import get_backend

    kwargs = {
        "outlook_app": fake,
        "registry": fake.registry,
        "security_center": fake.security_center,
        "pywin32": None,
    }
    kwargs.update(overrides)
    return get_backend(platform="win32", **kwargs)


def _app(fake: fk.FakeOutlook, watchdog=None):
    """Read-only Application proxy over the fake."""
    return _oc().connect(
        outlook_app=fake, registry=fake.registry, pywin32=True, watchdog=watchdog
    )


class _RecordingWatchdog:
    """Factory of a watchdog whose expiry is recorded instead of ending the process."""

    def __init__(self, seconds: float) -> None:
        self.expired: list[float] = []
        self.event = threading.Event()
        self.watchdog = _oc().Watchdog(timeout=seconds, on_expire=self._record)

    def _record(self, _watchdog, seconds: float) -> None:
        self.expired.append(seconds)
        self.event.set()


class _OutlookCliCase(unittest.TestCase):
    """``cli.main`` in-process over the fake, with a temporary home."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.home = self.root / ".mailquery"
        from mailquery import cli

        self.cli = cli
        self.addCleanup(cli._close_logging_handlers)

    def run_main(self, argv, backend) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = self.cli.main(list(argv), home=self.home, backend=backend)
        return code, out.getvalue(), err.getvalue()

    def search(self, backend) -> tuple[int, str, str]:
        return self.run_main(["search", "--since", "1d"], backend)

    def assert_error(self, result, exit_code: int, code: str) -> dict:
        returncode, stdout, stderr = result
        self.assertEqual(returncode, exit_code, stdout + stderr)
        payload = json.loads(stdout)
        self.assertEqual(stdout, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], code)
        self.assertTrue(payload["error"]["hint"].strip())
        self.assertIn(f"mailquery: {code}: ", stderr)
        return payload["error"]


def _assert_internal(case: unittest.TestCase, action) -> None:
    from mailquery.errors import MailqueryError

    with case.assertRaises(MailqueryError) as caught:
        action()
    case.assertEqual(caught.exception.code, "E_INTERNAL")
    case.assertEqual(caught.exception.exit_code, 1)
    case.assertTrue(caught.exception.hint.strip())


# --------------------------------------------------------------------------- #
# OL-01 — Read-only proxy (annex B.2 point 2)
# --------------------------------------------------------------------------- #


class OutlookReadOnlyProxyTests(unittest.TestCase):
    def test_ol_01_01_members_outside_the_whitelist_are_rejected(self) -> None:
        """OL-01.01: mutating or non-whitelisted members ⇒ E_INTERNAL, the fake untouched."""
        fake = fk.FakeOutlook.default()
        app = _app(fake)
        session = app.Session
        spec = fake.item("normal")
        item = session.GetItemFromID(spec.entry_id, spec.folder.store.store_id)
        store = session.Stores.Item(1)
        folder = store.GetRootFolder().Folders.Item(1)
        recipient = item.Recipients.Item(1)
        targets = {
            "Item": item,
            "Folder": folder,
            "Folders": folder.Folders,
            "Recipient": recipient,
            "Application": app,
            "NameSpace": session,
            "PropertyAccessor": item.PropertyAccessor,
            "Store": store,
        }
        fake.call_log.clear()
        cases = [
            ("Item", name)
            for name in (
                "Delete", "Move", "Copy", "Save", "SaveAs", "Send", "Display", "Close",
                "Reply", "ReplyAll", "Forward", "PrintOut", "MarkForDownload", "UnRead",
                "ReceivedTime", "delete", "body",
            )
        ] + [
            ("Folder", "Items"),  # Items.Remove is unreachable: Items is not whitelisted
            ("Folder", "Delete"),
            ("Folders", "Add"),
            ("Folders", "Remove"),
            ("Recipient", "AddressEntry"),
            ("Recipient", "GetExchangeUser"),
            ("Recipient", "Address"),
            ("Application", "GetNamespace"),
            ("Application", "Quit"),
            ("Application", "CreateItem"),
            ("NameSpace", "Logon"),
            ("NameSpace", "GetNamespace"),
            ("PropertyAccessor", "SetProperty"),
            ("PropertyAccessor", "DeleteProperties"),
            ("Store", "GetExchangeDistributionList"),
        ]
        for kind, name in cases:
            with self.subTest(kind=kind, member=name):
                _assert_internal(self, lambda: getattr(targets[kind], name))
        self.assertEqual(len(fake.call_log), 0, list(fake.call_log))
        self.assertEqual(fake.mutations.total, 0)
        # The whitelist is exactly the documented OOM surface the fake implements.
        oc = _oc()
        self.assertEqual(oc.READONLY_MEMBERS, fk.OOM_MEMBERS)
        for kind, cls in fk.COM_CLASSES.items():
            with self.subTest(kind=kind):
                declared = {m for m in oc.READONLY_MEMBERS[kind] if m in oc.READONLY_METHODS}
                self.assertEqual(declared, set(cls._METHODS))

    def test_ol_01_02_assignments_are_rejected(self) -> None:
        """OL-01.02: assigning UnRead or any other property ⇒ E_INTERNAL, nothing set."""
        fake = fk.FakeOutlook.default()
        app = _app(fake)
        spec = fake.item("normal")
        item = app.Session.GetItemFromID(spec.entry_id, spec.folder.store.store_id)
        folder = item.Parent
        fake.call_log.clear()
        assignments = [
            (item, "UnRead", False),
            (item, "Body", "changed"),
            (item, "Subject", "changed"),
            (item, "MessageClass", "IPM.Note"),
            (folder, "Name", "renamed"),
            (app, "Version", "0"),
            (item, "_private", 1),
        ]
        for target, name, value in assignments:
            with self.subTest(member=name):
                _assert_internal(self, lambda: setattr(target, name, value))
        for name in ("Body", "UnRead"):
            with self.subTest(delete=name):
                _assert_internal(self, lambda: delattr(item, name))
        self.assertEqual(fake.call_log.count(action="set"), 0)
        self.assertEqual(fake.mutations.total, 0)
        self.assertEqual(item.Body, spec.body)

    def test_ol_01_03_dunder_and_private_names_are_rejected(self) -> None:
        """OL-01.03: dunder and private names ⇒ E_INTERNAL, the raw object is never reached."""
        fake = fk.FakeOutlook.default()
        app = _app(fake)
        session = app.Session
        fake.call_log.clear()
        names = [
            "__dict__", "__init__", "__getattr__", "__reduce__", "__reduce_ex__", "__call__",
            "__iter__", "_oleobj_", "_FlagAsMethod", "_rt", "_get_Version", "_",
            *_oc().ReadOnlyCom.__slots__,
        ]
        for target in (app, session):
            for name in names:
                with self.subTest(target=repr(target), name=name):
                    _assert_internal(self, lambda: getattr(target, name))
        self.assertEqual(len(fake.call_log), 0)
        self.assertEqual(fake.mutations.total, 0)

    def test_ol_01_04_every_returned_object_is_wrapped(self) -> None:
        """OL-01.04: every returned COM object is a proxy, collection items included."""
        oc = _oc()
        fake = fk.FakeOutlook.default()
        app = _app(fake)
        session = app.Session
        stores = session.Stores
        store = stores.Item(1)
        root = store.GetRootFolder()
        folders = root.Folders
        inbox = store.GetDefaultFolder(fk.OL_FOLDER_INBOX)
        table = inbox.GetTable("", fk.OL_USER_ITEMS)
        columns = table.Columns
        column = columns.Add(fk.PR_SUBJECT)
        row = table.GetNextRow()
        accounts = session.Accounts
        account = accounts.Item(1)
        spec = fake.item("normal")
        item = session.GetItemFromID(spec.entry_id, spec.folder.store.store_id)
        attachments = item.Attachments
        recipients = item.Recipients
        expected = {
            "Application": app,
            "NameSpace": session,
            "Stores": stores,
            "Store": store,
            "Folder": root,
            "Folders": folders,
            "Table": table,
            "Columns": columns,
            "Column": column,
            "Row": row,
            "Accounts": accounts,
            "Account": account,
            "Item": item,
            "Attachments": attachments,
            "Recipients": recipients,
        }
        expected_more = [
            ("Folder", folders.Item(1)),
            ("Folder", inbox),
            ("Folder", item.Parent),
            ("Store", account.DeliveryStore),
            ("Attachment", attachments.Item(1)),
            ("Recipient", recipients.Item(1)),
            ("PropertyAccessor", store.PropertyAccessor),
            ("PropertyAccessor", inbox.PropertyAccessor),
            ("PropertyAccessor", item.PropertyAccessor),
            ("PropertyAccessor", attachments.Item(1).PropertyAccessor),
            ("PropertyAccessor", recipients.Item(1).PropertyAccessor),
        ]
        for kind, value in [*expected.items(), *expected_more]:
            with self.subTest(kind=kind):
                self.assertIs(type(value), oc.ReadOnlyCom)
                self.assertEqual(repr(value), f"<ReadOnlyCom {kind}>")
        # Scalars are returned as they are.
        self.assertEqual(app.Version, fk.DEFAULT_VERSION)
        self.assertIsInstance(row.GetValues(), tuple)
        self.assertIsInstance(store.PropertyAccessor.GetProperty(fk.PR_RECORD_KEY), memoryview)
        self.assertEqual(stores.Count, 2)
        while not table.EndOfTable:
            table.GetNextRow()
        self.assertIsNone(table.GetNextRow())
        self.assertEqual(fake.mutations.total, 0)


# --------------------------------------------------------------------------- #
# OL-02 — Client detection (PRD 12.6, annex B.7, RF-28)
# --------------------------------------------------------------------------- #


class OutlookDetectionTests(_OutlookCliCase):
    def test_ol_02_01_pywin32_missing_is_dependency_missing(self) -> None:
        """OL-02.01: pywin32 not importable (even with Outlook unregistered) ⇒ exit 3."""
        fake = fk.FakeOutlook(registry=fk.FakeRegistry.unregistered())
        error = self.assert_error(
            self.search(_backend(fake, pywin32=False)), 3, "E_DEPENDENCY_MISSING"
        )
        self.assertEqual(error["hint"], HINT_DEPENDENCY)
        self.assertEqual(len(fake.call_log), 0)
        self.assertEqual(fake.registry.reads, [])
        # The real import path: win32com cannot be imported.
        blocked = {"win32com": None, "win32com.client": None, "pythoncom": None, "pywintypes": None}
        with mock.patch.dict(sys.modules, blocked):
            backend = _backend(
                fake, outlook_app=None, pywin32=None, tmp_root=self.home / "tmp"
            )
            error = self.assert_error(self.search(backend), 3, "E_DEPENDENCY_MISSING")
        self.assertEqual(error["hint"], HINT_DEPENDENCY)
        self.assertEqual(fake.registry.reads, [])

    def test_ol_02_02_unregistered_outlook_is_client_unsupported(self) -> None:
        """OL-02.02: Outlook not registered ⇒ E_CLIENT_UNSUPPORTED (exit 3), hint of B.7."""
        fake = fk.FakeOutlook(registry=fk.FakeRegistry.unregistered())
        error = self.assert_error(self.search(_backend(fake)), 3, "E_CLIENT_UNSUPPORTED")
        self.assertEqual(error["hint"], HINT_UNSUPPORTED)
        self.assertEqual(fake.call_log.count(member="GetActiveObject"), 0)

    def test_ol_02_03_curver_15_is_client_unsupported(self) -> None:
        """OL-02.03: CurVer 15.0 ⇒ E_CLIENT_UNSUPPORTED."""
        fake = run_cli.build_fake("old_version")
        error = self.assert_error(self.search(_backend(fake)), 3, "E_CLIENT_UNSUPPORTED")
        self.assertEqual(error["hint"], HINT_UNSUPPORTED)
        self.assertIn("15", error["message"])
        self.assertEqual(fake.call_log.count(member="GetActiveObject"), 0)

    def test_ol_02_04_curver_16_continues(self) -> None:
        """OL-02.04: CurVer 16.0 (the lower bound) ⇒ detection continues and connects."""
        fake = fk.FakeOutlook.default()
        self.assertEqual(
            fake.registry.get_value(fk.HKCR, fk.CURVER_KEY), "Outlook.Application.16"
        )
        info = _backend(fake).describe()
        self.assertEqual(info["version"], fk.DEFAULT_VERSION)
        self.assertEqual(fake.call_log.count(member="GetActiveObject"), 1)

    def test_ol_02_05_no_instance_is_outlook_not_running_exit_6(self) -> None:
        """OL-02.05: no running instance ⇒ E_OUTLOOK_NOT_RUNNING, exit 6, hint of B.7."""
        fake = run_cli.build_fake("not_running")
        error = self.assert_error(self.search(_backend(fake)), 6, "E_OUTLOOK_NOT_RUNNING")
        self.assertEqual(error["hint"], HINT_NOT_RUNNING)
        self.assertEqual(fake.call_log.count(member="GetActiveObject"), 1)
        self.assertEqual(fake.mutations.total, 0)

    def test_ol_02_06_running_instance_connects_with_get_active_object(self) -> None:
        """OL-02.06: a running instance ⇒ connection with GetActiveObject("Outlook.Application")."""
        fake = fk.FakeOutlook.default()
        backend = _backend(fake)
        self.assertEqual(backend.driver, "outlook")
        self.assertEqual(backend.describe()["strategy"], "com_readonly")
        connects = [e for e in fake.call_log if e.kind == "Connector"]
        self.assertEqual(
            [(e.member, e.action, e.args) for e in connects],
            [("GetActiveObject", "call", ("Outlook.Application",))],
        )
        backend.describe()  # the connection is reused
        self.assertEqual(fake.call_log.count(member="GetActiveObject"), 1)

    def test_ol_02_07_call_log_never_records_dispatch(self) -> None:
        """OL-02.07: no Dispatch/DispatchEx/EnsureDispatch, in any detection outcome."""
        from mailquery.errors import MailqueryError

        for scenario in ("default", "not_running", "unregistered", "old_version"):
            with self.subTest(scenario=scenario):
                fake = run_cli.build_fake(scenario)
                try:
                    _backend(fake).describe()
                except MailqueryError:
                    pass
                self.assertFalse({e.member for e in fake.call_log} & _DISPATCH_NAMES)
                self.assertEqual(fake.mutations.total, 0)
        tree = ast.parse((_SRC_ROOT / "mailquery" / "backends" / "outlook_com.py").read_text("utf-8"))
        used = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                used.add(node.attr)
            elif isinstance(node, ast.Name):
                used.add(node.id)
            elif isinstance(node, ast.alias):
                used.add(node.name.split(".")[-1])
        self.assertEqual(used & _DISPATCH_NAMES, set())


# --------------------------------------------------------------------------- #
# OL-03 — COM errors (annex B.7); failure injected in the first COM call
# --------------------------------------------------------------------------- #


class OutlookComErrorTests(_OutlookCliCase):
    def test_ol_03_01_access_denied_is_permission_exit_3(self) -> None:
        """OL-03.01: E_ACCESSDENIED ⇒ E_PERMISSION, exit 3, non-empty hint."""
        fake = fk.FakeOutlook.default()
        fake.fail_next(fk.E_ACCESSDENIED)
        self.assert_error(self.search(_backend(fake)), 3, "E_PERMISSION")
        self.assertEqual(fake.call_log.count(kind="Application", member="Version"), 1)

    def test_ol_03_02_transient_rejection_once_succeeds_after_100_ms(self) -> None:
        """OL-03.02: one transient rejection ⇒ one retry after 100 ms, then success."""
        fake = fk.FakeOutlook.default()
        backend = _backend(fake)
        fake.reject_next(times=1)
        from mailquery.backends import outlook_com

        # The 100 ms wait is checked on the sleep call itself, not with a wall clock:
        # time.monotonic() ticks every ~15.6 ms on some Windows runners.
        with mock.patch.object(outlook_com.time, "sleep", wraps=time.sleep) as sleep:
            info = backend.describe()
        self.assertEqual(info["version"], fk.DEFAULT_VERSION)
        self.assertEqual(outlook_com.RETRY_DELAY_SECONDS, 0.1)
        retry_waits = [c for c in sleep.call_args_list if c == mock.call(outlook_com.RETRY_DELAY_SECONDS)]
        self.assertEqual(len(retry_waits), 1)
        self.assertEqual(fake.call_log.count(kind="Application", member="Version"), 2)

    def test_ol_03_03_transient_rejection_twice_is_client_busy_exit_5(self) -> None:
        """OL-03.03: two transient rejections ⇒ E_CLIENT_BUSY, exit 5, non-empty hint."""
        fake = fk.FakeOutlook.default()
        fake.reject_next(times=2, hresult=fk.RPC_E_SERVERCALL_RETRYLATER)
        self.assert_error(self.search(_backend(fake)), 5, "E_CLIENT_BUSY")
        self.assertEqual(fake.call_log.count(kind="Application", member="Version"), 2)

    def test_ol_03_04_unknown_hresult_is_internal_with_hint(self) -> None:
        """OL-03.04: an unknown HRESULT ⇒ E_INTERNAL (exit 1), non-empty hint."""
        fake = fk.FakeOutlook.default()
        fake.fail_next(fk.E_UNEXPECTED, wrapped=True)
        error = self.assert_error(self.search(_backend(fake)), 1, "E_INTERNAL")
        self.assertIn("0x8000FFFF", error["message"])


# --------------------------------------------------------------------------- #
# OL-04 — Timeout (RF-33, PRD 12.8, D-03); 0.2 s deadline
# --------------------------------------------------------------------------- #


class OutlookTimeoutTests(unittest.TestCase):
    def run_hung_search(
        self, *argv: str, prepare=None, hang: str = "first"
    ) -> tuple[subprocess.CompletedProcess, Path, float]:
        """``run_cli.py`` hung on the first COM call (or on ``hang``, a ``Kind.Member``).

        ``argv`` defaults to ``search --since 1d``.
        """
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        home = root / ".mailquery"
        env = dict(os.environ)
        env["HOME"] = env["USERPROFILE"] = str(root)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        if prepare is not None:
            prepare(home)
        started = time.monotonic()
        result = subprocess.run(
            [
                sys.executable, "-B", str(_REPO_ROOT / "tests" / "fakes" / "run_cli.py"),
                "--home", str(home), "--timeout", "0.2", "--hang", hang,
                "--hang-timeout", "60", "--", *(argv or ("search", "--since", "1d")),
            ],
            capture_output=True,
            env=env,
            cwd=str(root),
            timeout=120,
            encoding="utf-8",
        )
        return result, home, time.monotonic() - started

    def test_ol_04_01_hung_search_is_client_timeout_exit_3(self) -> None:
        """OL-04.01: search hung in the first COM call ⇒ E_CLIENT_TIMEOUT, exit 3, full JSON."""
        result, _home, elapsed = self.run_hung_search()
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertLess(elapsed, 45.0)  # the hang (60 s) was not waited for
        payload = json.loads(result.stdout)
        self.assertEqual(result.stdout, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        self.assertEqual(payload["ok"], False)
        self.assertEqual(payload["command"], "search")
        self.assertEqual(payload["error"]["code"], "E_CLIENT_TIMEOUT")
        self.assertIn("doctor", payload["error"]["hint"])
        self.assertIn("mailquery: E_CLIENT_TIMEOUT: ", result.stderr)
        self.assertIn("mailquery: hint: ", result.stderr)

    def test_ol_04_02_hung_new_is_client_timeout_and_state_is_not_written(self) -> None:
        """OL-04.02: `new` hung in the first COM call ⇒ E_CLIENT_TIMEOUT, exit 3, full JSON; no state written."""
        seeded = json.dumps(
            {
                "schema": 1,
                "updated_at": "2026-11-01T10:00:00+00:00",
                "last_run": {"command": "new", "at": "2026-11-01T10:00:00+00:00"},
                "cursor": {"last_date_received": 1790000000, "last_uid": "00AB", "lookback_seconds": 600},
                "emitted_uids": ["00AB"],
            },
            indent=2,
        ) + "\n"

        def without_state(home: Path) -> None:
            home.mkdir(parents=True)
            (home / "config.toml").write_text(_scope_toml("ana.perez@example.com"), encoding="utf-8")

        def with_state(home: Path) -> None:
            without_state(home)
            (home / "state.json").write_text(seeded, encoding="utf-8")

        for label, prepare in (("first run", without_state), ("saved cursor", with_state)):
            with self.subTest(case=label):
                result, home, elapsed = self.run_hung_search("new", prepare=prepare)
                self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
                self.assertLess(elapsed, 45.0)  # the hang (60 s) was not waited for
                payload = json.loads(result.stdout)
                self.assertEqual(
                    result.stdout, json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
                )
                self.assertEqual(payload["ok"], False)
                self.assertEqual(payload["command"], "new")
                self.assertEqual(payload["error"]["code"], "E_CLIENT_TIMEOUT")
                self.assertIn("doctor", payload["error"]["hint"])
                self.assertIn("mailquery: E_CLIENT_TIMEOUT: ", result.stderr)
                state_path = home / "state.json"
                if prepare is with_state:
                    self.assertEqual(state_path.read_text(encoding="utf-8"), seeded)
                else:
                    self.assertFalse(state_path.exists())
                self.assertEqual([p.name for p in home.glob(".state-*")], [])

    def run_hung_doctor(self, hang: str, *extra: str) -> tuple[subprocess.CompletedProcess, Path]:
        """`doctor` (with one declared account) hung on ``hang``; returns the run and the home."""

        def declared(home: Path) -> None:
            home.mkdir(parents=True)
            (home / "config.toml").write_text(_scope_toml("ana.perez@example.com"), encoding="utf-8")

        result, home, elapsed = self.run_hung_search("doctor", *extra, prepare=declared, hang=hang)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertLess(elapsed, 45.0)  # the hang (60 s) was not waited for
        return result, home

    def assert_hung_doctor(self, hang: str, expected: dict[str, tuple[bool, str | None]]) -> None:
        """JSON and text reports of a hung `doctor`: ``expected`` = {check: (ok, exact detail)}."""
        result, home = self.run_hung_doctor(hang, "--json")
        payload = json.loads(result.stdout)
        self.assertEqual(result.stdout, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["command"], "doctor")
        self.assertEqual([check["name"] for check in payload["checks"]], list(_OUTLOOK_DOCTOR_CHECKS))
        by_name = {check["name"]: check for check in payload["checks"]}
        for name in _OUTLOOK_DOCTOR_CHECKS:
            ok, detail = expected.get(name, (True, None))
            with self.subTest(check=name):
                self.assertIs(by_name[name]["ok"], ok, by_name[name])
                if detail is not None:
                    self.assertEqual(by_name[name]["detail"], detail)
        log = (home / "logs" / "mailquery.log").read_text(encoding="utf-8")
        self.assertIn("event=end command=doctor exit_code=0", log)
        # The default text report is completed the same way.
        text, _home = self.run_hung_doctor(hang)
        self.assertFalse(text.stdout.lstrip().startswith("{"))
        flat = " ".join(text.stdout.split())
        for name, (ok, detail) in expected.items():
            if detail is not None:
                self.assertIn(f"[{'ok]' if ok else 'FAIL]'} {name}", flat)
                self.assertIn(detail, flat)
        failed = sum(1 for ok, _detail in expected.values() if not ok)
        passed = len(_OUTLOOK_DOCTOR_CHECKS) - failed
        self.assertIn(f"Result: {passed}/{len(_OUTLOOK_DOCTOR_CHECKS)} checks passed", flat)

    def test_ol_04_03_doctor_hung_in_outlook_completes_the_report(self) -> None:
        """OL-04.03: doctor hung in `outlook` ⇒ outlook timeout text; dependents not evaluated; exit 0."""
        self.assert_hung_doctor(
            "first",  # the first OOM access is the outlook check's Application.Version
            {
                "outlook": (False, _DOCTOR_TIMEOUT),
                "stores": (False, "not evaluated: outlook failed"),
                "readonly_strategy": (False, "not evaluated: outlook failed"),
                "config": (False, "not evaluated: stores failed"),
            },
        )

    def test_ol_04_04_doctor_hung_in_stores_completes_the_report(self) -> None:
        """OL-04.04: doctor hung in `stores` ⇒ stores timeout text; config resolution not evaluated; exit 0."""
        self.assert_hung_doctor(
            "NameSpace.Stores",
            {
                "stores": (False, _DOCTOR_TIMEOUT),
                "config": (False, "not evaluated: stores failed"),
            },
        )

    def test_ol_04_05_python_work_between_calls_does_not_time_out(self) -> None:
        """OL-04.05: Python time between COM calls longer than the deadline ⇒ no timeout."""
        recorder = _RecordingWatchdog(0.2)
        fake = fk.FakeOutlook.default()
        app = _app(fake, watchdog=recorder.watchdog)
        app.Version
        time.sleep(0.5)  # Python work, no COM call in flight
        session = app.Session
        time.sleep(0.3)
        self.assertEqual(recorder.expired, [])
        self.assertFalse(recorder.watchdog.armed)
        # Control: the same watchdog fires while a COM call is in flight.
        fake.hang_next(kind="NameSpace", member="Stores", timeout=1.5)
        session.Stores
        self.assertTrue(recorder.event.wait(2.0))
        self.assertEqual(recorder.expired, [0.2])

    def test_ol_04_06_timeout_error_is_logged(self) -> None:
        """OL-04.06: the E_CLIENT_TIMEOUT error is written to the log."""
        result, home, _elapsed = self.run_hung_search()
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        log = (home / "logs" / "mailquery.log").read_text(encoding="utf-8")
        self.assertIn("event=error command=search code=E_CLIENT_TIMEOUT", log)


# --------------------------------------------------------------------------- #
# OL-05 — pywin32 cache (annex B.2 point 6)
# --------------------------------------------------------------------------- #


class _FakePywin32Finder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Stand-in pywin32: records ``win32com.__gen_path__`` when ``win32com.client`` loads."""

    NAMES = ("win32com", "win32com.client", "pythoncom", "pywintypes")

    def __init__(self) -> None:
        self.gen_path_at_client_import: list[object] = []

    def find_spec(self, name, path=None, target=None):
        if name not in self.NAMES:
            return None
        return importlib.machinery.ModuleSpec(name, self, is_package=(name == "win32com"))

    def create_module(self, spec):
        return None

    def exec_module(self, module: types.ModuleType) -> None:
        if module.__name__ == "win32com":
            module.__path__ = []
        elif module.__name__ == "win32com.client":
            parent = sys.modules["win32com"]
            self.gen_path_at_client_import.append(getattr(parent, "__gen_path__", None))


class OutlookPywin32CacheTests(unittest.TestCase):
    def test_ol_05_01_gen_path_is_set_before_importing_win32com_client(self) -> None:
        """OL-05.01: win32com.__gen_path__ = <home>/tmp/gen_py before win32com.client loads."""
        finder = _FakePywin32Finder()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / ".mailquery"
            with mock.patch.dict(sys.modules), mock.patch.object(
                sys, "meta_path", [finder, *sys.meta_path]
            ):
                for name in _FakePywin32Finder.NAMES:
                    sys.modules.pop(name, None)
                backend = _backend(
                    fk.FakeOutlook(),
                    outlook_app=None,
                    registry=fk.FakeRegistry.unregistered(),
                    tmp_root=home / "tmp",
                )
                from mailquery.errors import MailqueryError

                with self.assertRaises(MailqueryError) as caught:
                    backend.describe()
            self.assertEqual(caught.exception.code, "E_CLIENT_UNSUPPORTED")
            gen_path = home / "tmp" / "gen_py"
            self.assertEqual(finder.gen_path_at_client_import, [str(gen_path)])
            self.assertTrue(gen_path.is_dir())

    @unittest.skipUnless(sys.platform == "win32", "OL-05.02 needs a real Windows host (plan 7.7)")
    def test_ol_05_02_real_cache_files_only_under_home_gen_py(self) -> None:
        """OL-05.02: on real Windows, no pywin32 cache file outside <home>/tmp/gen_py."""
        script = (
            "import sys\n"
            "from pathlib import Path\n"
            "from mailquery.backends import get_backend\n"
            "from mailquery.errors import MailqueryError\n"
            "home = Path(sys.argv[1])\n"
            "backend = get_backend(platform='win32', tmp_root=home / 'tmp')\n"
            "try:\n"
            "    print('connected' if backend.describe().get('version') else 'no-version')\n"
            "except MailqueryError as exc:\n"
            "    print(exc.code)\n"
            "finally:\n"
            "    backend.close()\n"
        )
        default_dirs = [Path(tempfile.gettempdir()) / "gen_py"]
        spec = importlib.util.find_spec("win32com")
        if spec is not None and spec.submodule_search_locations:
            default_dirs.append(Path(list(spec.submodule_search_locations)[0]) / "gen_py")
        before = _tree_snapshot(default_dirs)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            user, temp = root / "user", root / "temp"
            user.mkdir()
            temp.mkdir()
            home = user / ".mailquery"
            env = dict(os.environ)
            env.update(
                HOME=str(user),
                USERPROFILE=str(user),
                TEMP=str(temp),
                TMP=str(temp),
                PYTHONPATH=str(_SRC_ROOT),
                PYTHONDONTWRITEBYTECODE="1",
            )
            result = subprocess.run(
                [sys.executable, "-B", "-c", script, str(home)],
                capture_output=True,
                env=env,
                cwd=str(root),
                timeout=120,
                encoding="utf-8",
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(
                result.stdout.strip(),
                {
                    "connected", "E_DEPENDENCY_MISSING", "E_CLIENT_UNSUPPORTED",
                    "E_OUTLOOK_NOT_RUNNING", "E_PERMISSION", "E_CLIENT_BUSY",
                },
                result.stderr,
            )
            gen_path = home / "tmp" / "gen_py"
            outside = [
                str(path)
                for path in root.rglob("*")
                if path.is_file() and not path.is_relative_to(gen_path)
            ]
            self.assertEqual(outside, [])
        self.assertEqual(_tree_snapshot(default_dirs), before)


def _tree_snapshot(directories) -> list[tuple[str, int, int]]:
    """(path, size, mtime) of every file under the directories that exist."""
    found = []
    for directory in directories:
        if directory.is_dir():
            for path in directory.rglob("*"):
                if path.is_file():
                    stat = path.stat()
                    found.append((str(path), stat.st_size, stat.st_mtime_ns))
    return sorted(found)


# --------------------------------------------------------------------------- #
# Stores and accounts (annex B.3, B.4; W3-T03)
# --------------------------------------------------------------------------- #

_STORE_LEVEL_MEMBERS = frozenset(
    {
        ("Application", "Session"),
        ("NameSpace", "Stores"),
        ("NameSpace", "Accounts"),
        ("Stores", "Count"),
        ("Stores", "Item"),
        ("Accounts", "Count"),
        ("Accounts", "Item"),
        ("Account", "AccountType"),
        ("Account", "SmtpAddress"),
        ("Account", "DeliveryStore"),
        ("Store", "DisplayName"),
        ("Store", "ExchangeStoreType"),
        ("Store", "IsCachedExchange"),
        ("Store", "FilePath"),
        ("Store", "StoreID"),
        ("Store", "PropertyAccessor"),
        ("PropertyAccessor", "GetProperty"),
    }
)

# (label, email, local) of each candidate of the store matrix, in profile order.
_MATRIX_CANDIDATES = {
    "exchange_cached": ("Exchange (ana@example.com)", "ana@example.com", False),
    "imap": ("IMAP (carla@example.org)", "carla@example.org", False),
    "pop3": ("POP3 (diego@example.net)", "diego@example.net", False),
    "eas": ("EAS (elena@outlook.example)", "elena@outlook.example", False),
    "pst": ("PST (Archivo 2024)", None, True),
    "pst_no_inbox": ("PST (Notas)", None, True),
    "pst_removable": ("PST (Respaldo USB)", None, True),
}

# excluded_stores() entry of each excluded store of the store matrix, in profile order.
_MATRIX_EXCLUDED = {
    "exchange_online": ("Exchange (bruno@example.com)", None, "online_mode"),
    "shared": ("Exchange shared (Soporte)", None, "shared_mailbox"),
    "public": ("Public Folders (Public Folders - ana@example.com)", None, "public_folders"),
    "pst_unc": ("PST (Archivo 2019)", "\\\\nas01\\backup\\archivo2019.pst", "network_path"),
    "pst_mapped": ("PST (Archivo 2018)", "Z:\\archivo2018.pst", "network_path"),
    "other_type": (
        "HTTP (fede@example.com)",
        "C:\\Users\\ana\\Documents\\Outlook Files\\fede@example.com.pst",
        "unsupported_account_type",
    ),
    "exchange_archive": ("Archivo en línea - ana@example.com", None, "online_mode"),
    "unavailable_named": ("Buzón remoto", None, "unavailable"),
    "unavailable_unnamed": ("unknown", None, "unavailable"),
}


class _StoreCase(unittest.TestCase):
    """Outlook backend over a fake profile, with the fake's drive types patched in."""

    def make(self, fake: fk.FakeOutlook):
        patcher = mock.patch.object(_oc(), "get_drive_type", fake.drive_type)
        patcher.start()
        self.addCleanup(patcher.stop)
        backend = _backend(fake)
        self.addCleanup(backend.close)
        return backend

    @staticmethod
    def uuid_of(fake: fk.FakeOutlook, key: str) -> str:
        import uuid

        return str(uuid.UUID(bytes=fake.store(key).record_key)).upper()


class OutlookAccountUuidTests(_StoreCase):
    def test_ol_08_01_account_uuid_is_the_record_key_as_uppercase_uuid(self) -> None:
        """OL-08.01: account.uuid = the 16 bytes of PR_RECORD_KEY as an uppercase 8-4-4-4-12 UUID."""
        import re

        fake = fk.FakeOutlook.default()
        backend = self.make(fake)
        rows = {row["label"]: row for row in backend.accounts()}
        exchange = rows["Exchange (ana.perez@example.com)"]
        self.assertEqual(exchange["uuid"], "D70DBCF6-1C2A-4B6E-9A51-E0C3B2A49F10")
        record_key = bytes.fromhex(exchange["uuid"].replace("-", ""))
        self.assertEqual(record_key, fake.store("exchange").record_key)
        pattern = re.compile(r"[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}")
        matrix = fk.FakeOutlook.store_matrix()
        for row in self.make(matrix).accounts():
            if row["uuid"] is None:
                continue
            with self.subTest(label=row["label"]):
                self.assertRegex(row["uuid"], pattern)
                self.assertIn(
                    bytes.fromhex(row["uuid"].replace("-", "")),
                    [spec.record_key for spec in matrix.stores],
                )


class OutlookStoreClassificationTests(_StoreCase):
    def test_store_matrix_candidates_have_the_annex_labels(self) -> None:
        """Annex B.3: candidates and their labels, email (null for PST) and uuid, in profile order."""
        fake = fk.FakeOutlook.store_matrix()
        rows = [row for row in self.make(fake).accounts() if "excluded" not in row]
        expected = [
            {"uuid": self.uuid_of(fake, key), "label": label, "email": email, "local": local}
            for key, (label, email, local) in _MATRIX_CANDIDATES.items()
        ]
        self.assertEqual(rows, expected)

    def test_store_matrix_excluded_stores_have_label_path_and_reason(self) -> None:
        """Annex B.3 / RF-34: every excluded store with its label, path and reason, in profile order."""
        fake = fk.FakeOutlook.store_matrix()
        got = self.make(fake).excluded_stores()
        expected = [
            {"label": label, "path": path, "reason": reason}
            for label, path, reason in _MATRIX_EXCLUDED.values()
        ]
        self.assertEqual(got, expected)

    def test_excluded_stores_are_flagged_account_rows(self) -> None:
        """accounts() also returns each excluded store, flagged with its excluded_stores() entry."""
        fake = fk.FakeOutlook.store_matrix()
        backend = self.make(fake)
        flagged = [row for row in backend.accounts() if "excluded" in row]
        self.assertEqual([row["excluded"] for row in flagged], backend.excluded_stores())
        by_label = {row["label"]: row for row in flagged}
        self.assertEqual(
            by_label["Exchange (bruno@example.com)"]["uuid"], self.uuid_of(fake, "exchange_online")
        )
        self.assertEqual(by_label["Exchange (bruno@example.com)"]["email"], "bruno@example.com")
        self.assertEqual(by_label["Exchange shared (Soporte)"]["uuid"], self.uuid_of(fake, "shared"))
        self.assertIsNone(by_label["Exchange shared (Soporte)"]["email"])
        self.assertEqual(by_label["HTTP (fede@example.com)"]["email"], "fede@example.com")
        # An unreadable store has no PR_RECORD_KEY, hence no uuid.
        self.assertIsNone(by_label["Buzón remoto"]["uuid"])
        self.assertIsNone(by_label["unknown"]["uuid"])
        self.assertTrue(backend.labels_available)

    def test_profile_order_mixes_candidates_and_excluded(self) -> None:
        """accounts() keeps the order of NameSpace.Stores."""
        fake = fk.FakeOutlook.store_matrix()
        labels = [row["label"] for row in self.make(fake).accounts()]
        expected_by_key = {
            **{key: value[0] for key, value in _MATRIX_CANDIDATES.items()},
            **{key: value[0] for key, value in _MATRIX_EXCLUDED.items()},
        }
        self.assertEqual(labels, [expected_by_key[spec.key] for spec in fake.stores])

    def test_second_exchange_account_with_store_type_4_is_a_candidate(self) -> None:
        """Annex B.11: the delivery store of a second account (ExchangeStoreType 4) is a candidate."""
        fake = fk.FakeOutlook()
        fake.add_exchange_account("first", "uno@example.com")
        second = fake.add_exchange_account("second", "dos@example.com")
        self.assertEqual(second.store_type, fk.OL_ADDITIONAL_EXCHANGE_MAILBOX)
        backend = self.make(fake)
        self.assertEqual(
            [row["label"] for row in backend.accounts()],
            ["Exchange (uno@example.com)", "Exchange (dos@example.com)"],
        )
        self.assertEqual(backend.excluded_stores(), [])

    def test_account_files_on_the_network_are_network_path(self) -> None:
        """IMAP/POP3/EAS data files on UNC or mapped drives: network_path, label as if local."""
        fake = fk.FakeOutlook()
        fake.drive_types["Y:"] = fk.DRIVE_REMOTE
        fake.add_imap_account("imap", "carla@example.org", file_path="\\\\srv\\mail\\carla.ost")
        fake.add_pop3_account("pop3", "diego@example.net", file_path="Y:\\diego.pst")
        fake.add_eas_account("eas", "elena@outlook.example", file_path="\\\\srv\\mail\\elena.ost")
        backend = self.make(fake)
        self.assertEqual(
            backend.excluded_stores(),
            [
                {"label": "IMAP (carla@example.org)", "path": "\\\\srv\\mail\\carla.ost",
                 "reason": "network_path"},
                {"label": "POP3 (diego@example.net)", "path": "Y:\\diego.pst",
                 "reason": "network_path"},
                {"label": "EAS (elena@outlook.example)", "path": "\\\\srv\\mail\\elena.ost",
                 "reason": "network_path"},
            ],
        )
        self.assertEqual([row for row in backend.accounts() if "excluded" not in row], [])

    def test_other_account_type_is_unsupported_with_its_type_label(self) -> None:
        """olOtherAccount (5) ⇒ unsupported_account_type, label `Other (<smtp>)`, path or null."""
        fake = fk.FakeOutlook()
        fake.add_other_account(
            "other", "otro@example.com", account_type=fk.OL_OTHER_ACCOUNT, file_path="C:\\o.pst"
        )
        no_file = fake.add_store("http", "Hotmail")
        fake.add_account(no_file, fk.OL_HTTP, "hotmail@example.com")
        self.assertEqual(
            self.make(fake).excluded_stores(),
            [
                {"label": "Other (otro@example.com)", "path": "C:\\o.pst",
                 "reason": "unsupported_account_type"},
                {"label": "HTTP (hotmail@example.com)", "path": None,
                 "reason": "unsupported_account_type"},
            ],
        )

    def test_unavailable_store_never_blocks_the_others(self) -> None:
        """An unreadable store (also an account's delivery store) is unavailable; the rest is read."""
        fake = fk.FakeOutlook()
        broken = fake.add_store(
            "broken", "Buzón caído", store_type=fk.OL_PRIMARY_EXCHANGE_MAILBOX, unavailable="named"
        )
        fake.add_account(broken, fk.OL_EXCHANGE, "caido@example.com")
        fake.add_unavailable_store("anonymous")
        fake.add_exchange_account("ok", "ok@example.com")
        fake.add_pst("pst", "Archivo", "C:\\archivo.pst")
        backend = self.make(fake)
        self.assertEqual(
            [row["label"] for row in backend.accounts() if "excluded" not in row],
            ["Exchange (ok@example.com)", "PST (Archivo)"],
        )
        self.assertEqual(
            backend.excluded_stores(),
            [
                {"label": "Buzón caído", "path": None, "reason": "unavailable"},
                {"label": "unknown", "path": None, "reason": "unavailable"},
            ],
        )

    def test_unavailable_store_keeps_the_path_it_could_read(self) -> None:
        """A store that fails after DisplayName and FilePath were read keeps both."""
        fake = fk.FakeOutlook()
        fake.add_pst("pst", "Archivo", "C:\\archivo.pst")
        fake.fail_next(fk.MAPI_E_FAILONEPROVIDER, kind="Store", member="StoreID", wrapped=True)
        self.assertEqual(
            self.make(fake).excluded_stores(),
            [{"label": "Archivo", "path": "C:\\archivo.pst", "reason": "unavailable"}],
        )

    def test_only_store_level_properties_are_read(self) -> None:
        """No folder, item or address-book member is touched for any store; nothing is mutated."""
        fake = fk.FakeOutlook.store_matrix()
        backend = self.make(fake)
        backend.accounts()
        backend.excluded_stores()
        touched = fake.call_log.members() - {("Connector", "GetActiveObject")}
        self.assertLessEqual(touched, _STORE_LEVEL_MEMBERS, touched - _STORE_LEVEL_MEMBERS)
        self.assertEqual(fake.mutations.total, 0)

    def test_profile_is_read_once_per_backend(self) -> None:
        """accounts() and excluded_stores() share one enumeration of the profile."""
        fake = fk.FakeOutlook.default()
        backend = self.make(fake)
        backend.accounts()
        reads = fake.call_log.count(kind="Stores", member="Count")
        backend.excluded_stores()
        backend.accounts()
        self.assertEqual(fake.call_log.count(kind="Stores", member="Count"), reads)


class OutlookExcludedScopeResolutionTests(_StoreCase):
    """``resolve_scope`` resolves [scope] keys against candidates and excluded stores (PRD 15.3)."""

    def resolve(self, fake: fk.FakeOutlook, *keys: str, mailbox_list=()):
        from mailquery.config import Config, ScopeEntry, resolve_scope

        backend = self.make(fake)
        config = Config(
            home=Path("unused"),
            scopes=tuple(ScopeEntry(key=key, mailbox_list=tuple(mailbox_list)) for key in keys),
        )
        excluded: list[dict] = []
        # Folders are W3-T04: an excluded account never needs them.
        with mock.patch.object(backend, "mailboxes_without_counters", return_value=[]):
            resolved = resolve_scope(config, backend, excluded=excluded)
        return resolved, excluded

    def test_label_email_and_uuid_of_excluded_stores_resolve_to_the_hook(self) -> None:
        fake = fk.FakeOutlook.store_matrix()
        keys = [
            "Exchange shared (Soporte)",
            "bruno@example.com",
            self.uuid_of(fake, "pst_unc"),
            self.uuid_of(fake, "public")[:8].lower(),
            "Buzón remoto",
        ]
        resolved, excluded = self.resolve(fake, *keys, mailbox_list=["Facturas"])
        self.assertEqual(resolved, [])
        self.assertEqual(
            excluded,
            [
                {"label": "Exchange shared (Soporte)", "path": None, "reason": "shared_mailbox"},
                {"label": "Exchange (bruno@example.com)", "path": None, "reason": "online_mode"},
                {"label": "PST (Archivo 2019)", "path": "\\\\nas01\\backup\\archivo2019.pst",
                 "reason": "network_path"},
                {"label": "Public Folders (Public Folders - ana@example.com)", "path": None,
                 "reason": "public_folders"},
                {"label": "Buzón remoto", "path": None, "reason": "unavailable"},
            ],
        )

    def test_same_excluded_store_declared_twice_is_reported_once(self) -> None:
        fake = fk.FakeOutlook.default()
        uuid = self.uuid_of(fake, "shared")
        _resolved, excluded = self.resolve(fake, "Exchange shared (Soporte)", uuid)
        self.assertEqual(
            excluded, [{"label": "Exchange shared (Soporte)", "path": None, "reason": "shared_mailbox"}]
        )

    def test_unknown_key_lists_only_candidates_as_known_accounts(self) -> None:
        from mailquery.errors import MailqueryError

        fake = fk.FakeOutlook.default()
        with self.assertRaises(MailqueryError) as caught:
            self.resolve(fake, "nadie@example.com")
        self.assertEqual(caught.exception.code, "E_CONFIG_ACCOUNT_UNKNOWN")
        self.assertIn(
            "known accounts: Exchange (ana.perez@example.com) "
            "(D70DBCF6-1C2A-4B6E-9A51-E0C3B2A49F10)",
            caught.exception.hint,
        )
        self.assertNotIn("Soporte", caught.exception.hint)

    def test_without_the_hook_an_excluded_account_is_skipped_silently(self) -> None:
        from mailquery.config import Config, ScopeEntry, resolve_scope

        fake = fk.FakeOutlook.default()
        backend = self.make(fake)
        config = Config(home=Path("unused"), scopes=(ScopeEntry(key="Exchange shared (Soporte)"),))
        with mock.patch.object(backend, "mailboxes_without_counters", return_value=[]):
            self.assertEqual(resolve_scope(config, backend), [])


# --------------------------------------------------------------------------- #
# Folders (annex B.3, B.4, PRD 15.3; W3-T04)
# --------------------------------------------------------------------------- #

# Paths of the "es" account of the folder matrix, in depth-first enumeration order.
_ES_PATHS = [
    "INBOX",
    "INBOX/Facturas",
    "Elementos eliminados",
    "Elementos enviados",
    "Proyectos",
    "Proyectos/Inbox",
    "Clientes%2FProveedores",
    "100%25 Reales",
    "Facturación ñ",
    "Archivo",
    "Archivo/Facturas",
]
_DE_PATHS = ["INBOX", "INBOX/Rechnungen", "Gelöschte Elemente", "Gesendete Elemente"]


class _FolderCase(_StoreCase):
    def folders(self, backend, fake: fk.FakeOutlook, key: str) -> list[dict]:
        uuid = self.uuid_of(fake, key)
        return [row for row in backend.mailboxes() if row["account_uuid"] == uuid]

    def by_path(self, backend, fake: fk.FakeOutlook, key: str) -> dict[str, dict]:
        return {row["path"]: row for row in self.folders(backend, fake, key)}


class OutlookInboxTests(_FolderCase):
    def test_ol_10_01_localized_inbox_is_inbox(self) -> None:
        """OL-10.01: the inbox found by function (Spanish and German names) is `INBOX`."""
        fake = fk.FakeOutlook.folder_matrix()
        backend = self.make(fake)
        for key in ("es", "de"):
            with self.subTest(account=key):
                rows = self.folders(backend, fake, key)
                inboxes = [row for row in rows if row["is_inbox"]]
                self.assertEqual(len(inboxes), 1, rows)
                self.assertEqual(inboxes[0]["path"], "INBOX")
                self.assertEqual(inboxes[0]["name"], "INBOX")
                self.assertEqual(
                    inboxes[0]["url"], f"outlook://{self.uuid_of(fake, key)}/INBOX"
                )
                self.assertNotIn("Bandeja de entrada", [row["name"] for row in rows])
                self.assertNotIn("Posteingang", [row["name"] for row in rows])
        # A folder named "Inbox" that is not the store's inbox is not INBOX.
        es = self.by_path(backend, fake, "es")
        self.assertFalse(es["Proyectos/Inbox"]["is_inbox"])
        self.assertEqual(es["Proyectos/Inbox"]["name"], "Inbox")

    def test_ol_10_02_inbox_subfolder_is_prefixed_with_inbox(self) -> None:
        """OL-10.02: a subfolder of the inbox is `INBOX/Facturas` (any language)."""
        fake = fk.FakeOutlook.folder_matrix()
        backend = self.make(fake)
        es = self.by_path(backend, fake, "es")
        self.assertEqual(es["INBOX/Facturas"]["name"], "Facturas")
        self.assertFalse(es["INBOX/Facturas"]["is_inbox"])
        de = self.by_path(backend, fake, "de")
        self.assertEqual(de["INBOX/Rechnungen"]["name"], "Rechnungen")
        self.assertEqual(
            de["INBOX/Rechnungen"]["url"], f"outlook://{self.uuid_of(fake, 'de')}/INBOX/Rechnungen"
        )

    def test_ol_10_03_pst_without_inbox_observes_only_mailbox_list(self) -> None:
        """OL-10.03: a PST without inbox has no INBOX; [scope] observes only mailbox_list, no error."""
        from mailquery.config import Config, ScopeEntry, resolve_scope

        fake = fk.FakeOutlook.store_matrix()
        backend = self.make(fake)
        uuid = self.uuid_of(fake, "pst_no_inbox")
        rows = self.folders(backend, fake, "pst_no_inbox")
        self.assertEqual([row["path"] for row in rows], ["Deleted Items", "Proyectos"])
        self.assertFalse(any(row["is_inbox"] for row in rows))
        self.assertIsNone(backend.resolve_mailbox(uuid, "INBOX"))
        self.assertIsNone(backend.resolve_mailbox(uuid, "inbox/Proyectos"))

        plain = Config(home=Path("unused"), scopes=(ScopeEntry(key="PST (Notas)"),))
        resolved = resolve_scope(plain, backend)
        self.assertEqual([scope.account_uuid for scope in resolved], [uuid])
        self.assertEqual(resolved[0].mailboxes, ())

        listed = Config(
            home=Path("unused"),
            scopes=(ScopeEntry(key="PST (Notas)", mailbox_list=("Proyectos",)),),
        )
        resolved = resolve_scope(listed, backend)
        self.assertEqual([row["path"] for row in resolved[0].mailboxes], ["Proyectos"])

        # A PST with an inbox gets it, found by function, like any account.
        pst = self.folders(backend, fake, "pst")
        self.assertEqual([row["path"] for row in pst if row["is_inbox"]], ["INBOX"])


class OutlookFolderPathTests(_FolderCase):
    def test_ol_11_01_path_uses_slash_separator(self) -> None:
        """OL-11.01: paths join the segments with `/`, depth-first in enumeration order."""
        fake = fk.FakeOutlook.folder_matrix()
        backend = self.make(fake)
        self.assertEqual([row["path"] for row in self.folders(backend, fake, "es")], _ES_PATHS)
        self.assertEqual([row["path"] for row in self.folders(backend, fake, "de")], _DE_PATHS)
        # Stores in profile order: every "es" folder comes before the "de" ones.
        uuids = [row["account_uuid"] for row in backend.mailboxes()]
        self.assertEqual(
            uuids,
            [self.uuid_of(fake, "es")] * len(_ES_PATHS) + [self.uuid_of(fake, "de")] * len(_DE_PATHS),
        )

    def test_ol_11_02_percent_and_slash_inside_a_name_are_encoded(self) -> None:
        """OL-11.02: `%` ⇒ `%25` and `/` ⇒ `%2F` inside a segment, also below other folders."""
        fake = fk.FakeOutlook.folder_matrix()
        fake.folder("es.percent").add_folder("50/50 %", key="es.percent_child")
        backend = self.make(fake)
        es = self.by_path(backend, fake, "es")
        self.assertIn("Clientes%2FProveedores", es)
        self.assertIn("100%25 Reales", es)
        self.assertIn("100%25 Reales/50%2F50 %25", es)
        self.assertNotIn("Clientes/Proveedores", es)

    def test_ol_11_03_name_is_the_encoded_last_segment(self) -> None:
        """OL-11.03: name = last segment of path, with the same encoding."""
        fake = fk.FakeOutlook.folder_matrix()
        fake.folder("es.percent").add_folder("50/50 %", key="es.percent_child")
        backend = self.make(fake)
        rows = self.folders(backend, fake, "es")
        for row in rows:
            with self.subTest(path=row["path"]):
                self.assertEqual(row["name"], row["path"].split("/")[-1])
        es = self.by_path(backend, fake, "es")
        self.assertEqual(es["Clientes%2FProveedores"]["name"], "Clientes%2FProveedores")
        self.assertEqual(es["100%25 Reales/50%2F50 %25"]["name"], "50%2F50 %25")
        self.assertEqual(es["Archivo/Facturas"]["name"], "Facturas")
        self.assertTrue(all(row["is_aggregate"] is False for row in backend.mailboxes()))

    def test_ol_11_04_url_percent_encodes_the_decoded_segments(self) -> None:
        """OL-11.04: url = outlook://<uuid>/<path>, segments decoded then RFC 3986 encoded (UTF-8)."""
        fake = fk.FakeOutlook.folder_matrix()
        fake.folder("es.percent").add_folder("50/50 %", key="es.percent_child")
        fake.store("es").add_folder("R&D ~v1.0_x-y (2026)+", key="es.reserved")
        backend = self.make(fake)
        uuid = self.uuid_of(fake, "es")
        es = self.by_path(backend, fake, "es")
        expected = {
            "INBOX": "INBOX",
            "INBOX/Facturas": "INBOX/Facturas",
            "Clientes%2FProveedores": "Clientes%2FProveedores",
            "100%25 Reales": "100%25%20Reales",
            "100%25 Reales/50%2F50 %25": "100%25%20Reales/50%2F50%20%25",
            "Facturación ñ": "Facturaci%C3%B3n%20%C3%B1",
            "Elementos eliminados": "Elementos%20eliminados",
            "R&D ~v1.0_x-y (2026)+": "R%26D%20~v1.0_x-y%20%282026%29%2B",
        }
        for path, encoded in expected.items():
            with self.subTest(path=path):
                self.assertEqual(es[path]["url"], f"outlook://{uuid}/{encoded}")
        for row in backend.mailboxes():
            self.assertTrue(row["url"].isascii(), row["url"])


class OutlookListedFoldersTests(_FolderCase):
    def test_ol_12_01_sync_folders_and_subfolders_are_hidden_in_any_language(self) -> None:
        """OL-12.01: Conflicts, Sync Issues, Local/Server Failures and subfolders are never listed."""
        fake = fk.FakeOutlook.folder_matrix()
        # A user folder called like a sync folder is listed: hiding is by function.
        fake.store("de").add_folder("Conflicts", key="de.user_conflicts")
        backend = self.make(fake)
        hidden_names = {
            names[role]
            for names in fk.LOCALES.values()
            for role in ("sync", "conflicts", "local", "server")
        } | {"Antiguos"}
        es_paths = [row["path"] for row in self.folders(backend, fake, "es")]
        self.assertEqual(es_paths, _ES_PATHS)
        for row in self.folders(backend, fake, "es"):
            self.assertFalse(set(row["path"].split("/")) & hidden_names, row["path"])
        self.assertEqual(
            [row["path"] for row in self.folders(backend, fake, "de")], [*_DE_PATHS, "Conflicts"]
        )
        # Hidden folders are not read: two counter tables per listed folder with items
        # (an empty one is counted from its own counters), never one of theirs.
        self.assertEqual(
            fake.call_log.count(kind="Folder", member="GetTable"),
            2 * _listed_with_items(fake, backend.mailboxes()),
        )
        # The default English profile hides them too.
        default = fk.FakeOutlook.default()
        paths = [row["path"] for row in self.make(default).mailboxes()]
        self.assertEqual(paths, ["INBOX", "Deleted Items", "Sent Items"])

    def test_ol_12_02_calendar_contacts_tasks_and_search_folders_are_not_listed(self) -> None:
        """OL-12.02: only mail folders are listed (no calendar, contacts, tasks, notes, journal, search)."""
        fake = fk.FakeOutlook.folder_matrix()
        es = fake.store("es")
        es.add_folder("Notas", key="es.notes", item_type=fk.OL_NOTE_ITEM)
        es.add_folder("Diario", key="es.journal", item_type=fk.OL_JOURNAL_ITEM)
        backend = self.make(fake)
        names = {row["name"] for row in self.folders(backend, fake, "es")}
        for excluded in ("Calendario", "Contactos", "Tareas", "Correo sin leer", "Notas", "Diario"):
            with self.subTest(folder=excluded):
                self.assertNotIn(excluded, names)
        self.assertEqual(fake.mutations.total, 0)

    def test_ol_12_03_counters_count_only_searchable_items(self) -> None:
        """OL-12.03: total/unread = searchable items; meetings count, receipts, tasks, IMAP-deleted do not."""
        fake = fk.FakeOutlook()
        store = fake.add_exchange_account("exchange", "ana@example.com")
        inbox = store.inbox
        assert inbox is not None
        inbox.add_message("mail_unread")
        inbox.add_message("mail_read", read=True)
        inbox.add_message("smime_unread", message_class="IPM.Note.SMIME")
        inbox.add_message("signed_read", message_class="ipm.note.smime.multipartsigned", read=True)
        inbox.add_message("meeting_request", message_class="IPM.Schedule.Meeting.Request")
        inbox.add_message("meeting_canceled", message_class="IPM.Schedule.Meeting.Canceled", read=True)
        inbox.add_message("meeting_response", message_class="IPM.Schedule.Meeting.Resp.Pos")
        inbox.add_message("receipt", message_class="IPM.Report.IPM.Note.DR")
        inbox.add_message("read_receipt", message_class="REPORT.IPM.Note.IPNRN")
        inbox.add_message("task", message_class="IPM.Task")
        inbox.add_message("post", message_class="IPM.Post")
        inbox.add_message("notes_like", message_class="IPM.NoteBook")
        inbox.add_message("imap_deleted", msg_status=fk.MSGSTATUS_DELMARKED)
        inbox.add_message("imap_deleted_read", read=True, msg_status=fk.MSGSTATUS_DELMARKED)
        inbox.add_folder("Vacía", key="empty")
        backend = self.make(fake)
        rows = self.by_path(backend, fake, "exchange")
        self.assertEqual((rows["INBOX"]["total"], rows["INBOX"]["unread"]), (7, 4))
        self.assertEqual((rows["INBOX/Vacía"]["total"], rows["INBOX/Vacía"]["unread"]), (0, 0))
        self.assertIsInstance(rows["INBOX"]["total"], int)
        # Counters come from the folder tables: no item is opened, nothing is mutated.
        self.assertEqual(fake.call_log.count(kind="NameSpace", member="GetItemFromID"), 0)
        self.assertEqual(fake.call_log.count(kind="Item"), 0)
        self.assertEqual(fake.mutations.total, 0)


class OutlookInboxReferenceTests(_FolderCase):
    def test_ol_13_01_inbox_and_inbox_prefix_in_any_language(self) -> None:
        """OL-13.01: `INBOX` and `INBOX/…` resolve in any language, case-insensitively."""
        fake = fk.FakeOutlook.folder_matrix()
        backend = self.make(fake)
        es_uuid, de_uuid = self.uuid_of(fake, "es"), self.uuid_of(fake, "de")
        cases = [
            (es_uuid, "INBOX", "INBOX"),
            (es_uuid, "inbox", "INBOX"),
            # "Inbox" is also the name of Proyectos/Inbox: the alias always wins.
            (es_uuid, "Inbox", "INBOX"),
            (es_uuid, "INBOX/Facturas", "INBOX/Facturas"),
            (es_uuid, "inbox/facturas", "INBOX/Facturas"),
            (es_uuid, "Proyectos/Inbox", "Proyectos/Inbox"),
            (de_uuid, "INBOX", "INBOX"),
            (de_uuid, "Inbox/Rechnungen", "INBOX/Rechnungen"),
            (de_uuid.lower(), "INBOX", "INBOX"),
        ]
        for account, ref, path in cases:
            with self.subTest(account=account, ref=ref):
                row = backend.resolve_mailbox(account, ref)
                self.assertIsNotNone(row)
                self.assertEqual(row["path"], path)
                self.assertEqual(row["account_uuid"], account.upper())
        self.assertTrue(backend.resolve_mailbox(es_uuid, "INBOX")["is_inbox"])
        # The localized name is not a reference: the inbox is listed as INBOX.
        self.assertIsNone(backend.resolve_mailbox(es_uuid, "Bandeja de entrada"))
        self.assertIsNone(backend.resolve_mailbox(de_uuid, "INBOX/Facturas"))
        self.assertIsNone(backend.resolve_mailbox("00000000-0000-0000-0000-000000000000", "INBOX"))


# --------------------------------------------------------------------------- #
# OL-14, OL-15, OL-16, OL-19 — Items (annex B.4)
# --------------------------------------------------------------------------- #

_ITEMS_NOW = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
_ADDRESS_BOOK_MEMBERS = frozenset(
    {"AddressEntry", "GetExchangeUser", "GetExchangeDistributionList", "Address"}
)


def _searchable_specs(fake: fk.FakeOutlook) -> list:
    """Items annex B.4 makes searchable: mail and meetings, minus IMAP-deleted."""
    return [
        spec
        for spec in fake.items.values()
        if spec.kind in ("mail", "meeting") and not spec.msg_status & fk.MSGSTATUS_DELMARKED
    ]


class _ItemCase(_StoreCase):
    """The item matrix (annex B.4) in one cached Exchange account."""

    def make_items(self, zone=None):
        fake = fk.FakeOutlook.item_matrix(_ITEMS_NOW)
        if zone is not None:
            fake.zone = zone  # the host zone: only the built-in time columns use it (P-5)
        return fake, self.make(fake)

    @staticmethod
    def all_ids(backend) -> list:
        return [row["id"] for row in backend.mailboxes()]

    def row_of(self, fake: fk.FakeOutlook, backend, key: str, **filters) -> dict | None:
        uid = fake.item(key).entry_id
        rows = backend.query(self.all_ids(backend), **filters)
        return next((row for row in rows if row["uid"] == uid), None)

    def assert_read_only(self, fake: fk.FakeOutlook) -> None:
        members = {member for _kind, member in fake.call_log.members()}
        self.assertFalse(members & _ADDRESS_BOOK_MEMBERS, members & _ADDRESS_BOOK_MEMBERS)
        self.assertEqual(fake.mutations.total, 0)


class OutlookUidOrderTests(_ItemCase):
    def test_ol_14_01_uid_is_the_permanent_entryid_not_the_table_id(self) -> None:
        """OL-14.01: uid = permanent EntryID in uppercase hex, not the short table id."""
        fake, backend = self.make_items()
        rows = backend.query(self.all_ids(backend))
        uids = [row["uid"] for row in rows]
        self.assertEqual(sorted(uids), sorted(spec.entry_id for spec in _searchable_specs(fake)))
        for spec in _searchable_specs(fake):
            self.assertNotIn(spec.short_id, uids)
        normal = fake.item("normal")
        row = next(row for row in rows if row["uid"] == normal.entry_id)
        self.assertIsInstance(row["uid"], str)
        self.assertEqual(len(row["uid"]), 140)
        self.assertRegex(row["uid"], r"^[0-9A-F]+$")
        # The metadata comes from the folder tables: no item is opened.
        self.assertEqual(fake.call_log.count(kind="NameSpace", member="GetItemFromID"), 0)
        self.assertEqual(fake.call_log.count(kind="Item"), 0)
        # show accepts the same token and finds the same row.
        found, mailbox = backend.find_message(backend.parse_uid(row["uid"]))
        self.assertEqual(found, row)
        self.assertEqual(mailbox["path"], "INBOX")
        self.assert_read_only(fake)

    def test_ol_14_02_same_date_is_ordered_by_uid_as_a_string(self) -> None:
        """OL-14.02: total order (date_received, uid), uid compared as a string."""
        fake, backend = self.make_items()
        pair = sorted([fake.item("same_date_a").entry_id, fake.item("same_date_b").entry_id])
        self.assertEqual(fake.item("same_date_a").received, fake.item("same_date_b").received)
        ascending = backend.query(self.all_ids(backend), order="asc")
        descending = backend.query(self.all_ids(backend), order="desc")
        self.assertEqual([row["uid"] for row in ascending if row["uid"] in pair], pair)
        self.assertEqual([row["uid"] for row in descending if row["uid"] in pair], pair[::-1])
        keys = [(row["date_received"], row["uid"]) for row in ascending]
        self.assertEqual(keys, sorted(keys))
        self.assertEqual([(row["date_received"], row["uid"]) for row in descending], keys[::-1])


class OutlookDateTests(_ItemCase):
    def test_ol_15_01_utc_times_are_emitted_with_the_local_offset(self) -> None:
        """OL-15.01: delivery/submit times read in UTC, ISO 8601 with the local offset (zone != UTC)."""
        from mailquery import output

        zone = fk.FakeZone.fixed(-4)
        fake, backend = self.make_items(zone)
        spec = fake.item("normal")
        row = self.row_of(fake, backend, "normal")
        self.assertEqual(row["date_received"], int(spec.received.timestamp()))
        self.assertEqual(row["date_sent"], int(spec.sent.timestamp()))
        with mock.patch.object(output, "LOCAL_ZONE", zone):
            received = output.iso_timestamp(row["date_received"])
            sent = output.iso_timestamp(row["date_sent"])
        self.assertEqual(received, spec.received.astimezone(zone).isoformat(timespec="seconds"))
        self.assertEqual(sent, spec.sent.astimezone(zone).isoformat(timespec="seconds"))
        self.assertTrue(received.endswith("-04:00"), received)
        # The built-in ReceivedTime/SentOn are never read (P-5).
        self.assertFalse(
            {member for _kind, member in fake.call_log.members()} & {"ReceivedTime", "SentOn"}
        )

    def test_ol_15_02_daylight_saving_change(self) -> None:
        """OL-15.02: each side of a DST change gets its own offset; cuts stay exact."""
        from mailquery import output

        zone = fk.FakeZone.santiago()
        fake, backend = self.make_items(zone)
        before = self.row_of(fake, backend, "dst_before")
        after = self.row_of(fake, backend, "dst_after")
        with mock.patch.object(output, "LOCAL_ZONE", zone):
            self.assertEqual(output.iso_timestamp(before["date_received"]), "2026-09-05T23:30:00-04:00")
            self.assertEqual(output.iso_timestamp(after["date_received"]), "2026-09-06T01:30:00-03:00")
        self.assertEqual(after["date_received"] - before["date_received"], 3600)
        uids = {row["uid"] for row in backend.query(self.all_ids(backend), since=after["date_received"])}
        self.assertIn(after["uid"], uids)
        self.assertNotIn(before["uid"], uids)


class OutlookAddressTests(_ItemCase):
    def test_ol_16_01_smtp_address_of_the_item(self) -> None:
        """OL-16.01: from/to/cc are the SMTP addresses the item carries."""
        fake, backend = self.make_items()
        row = self.row_of(fake, backend, "normal")
        self.assertEqual((row["sender_name"], row["sender_address"]), ("Remitente", "remitente@example.com"))
        recipients = backend.recipients([row["uid"]])
        self.assertEqual(
            recipients[row["uid"]],
            {
                "to": [{"name": "Ana", "address": "ana@example.com"}],
                "cc": [{"name": "Copia", "address": "copia@example.com"}],
            },
        )
        self.assert_read_only(fake)

    def test_ol_16_02_exchange_dn_is_never_used(self) -> None:
        """OL-16.02: an internal Exchange DN is never an address; the address book is never read."""
        fake, backend = self.make_items()
        for key, address in (("exchange_dn", "jefe@example.com"), ("internal_no_headers", "colega@example.com")):
            with self.subTest(item=key):
                self.assertTrue(fake.item(key).sender_email.startswith("/O="))
                row = self.row_of(fake, backend, key)
                self.assertEqual(row["sender_address"], address)
        uids = [row["uid"] for row in backend.query(self.all_ids(backend))]
        recipients = backend.recipients(uids)
        addresses = [
            entry["address"]
            for bucket in recipients.values()
            for entry in bucket["to"] + bucket["cc"]
        ]
        self.assertTrue(addresses)
        self.assertFalse([address for address in addresses if address.startswith("/")])
        self.assert_read_only(fake)

    def test_ol_16_03_missing_smtp_address_is_empty_and_keeps_the_name(self) -> None:
        """OL-16.03: no SMTP address on the item ⇒ address "" with the name kept."""
        fake, backend = self.make_items()
        row = self.row_of(fake, backend, "no_smtp")
        self.assertEqual((row["sender_name"], row["sender_address"]), ("Sin SMTP", ""))
        recipients = backend.recipients([row["uid"]])
        self.assertEqual(
            recipients[row["uid"]],
            {"to": [{"name": "Destino sin SMTP", "address": ""}], "cc": []},
        )
        self.assert_read_only(fake)


class OutlookFlagAttachmentTests(_ItemCase):
    def flagged_uids(self, backend) -> set[str]:
        return {row["uid"] for row in backend.query(self.all_ids(backend), flagged=True)}

    def attachment_uids(self, backend) -> set[str]:
        return {row["uid"] for row in backend.query(self.all_ids(backend), has_attachments=True)}

    def test_ol_19_01_flagged_not_completed_is_flagged(self) -> None:
        """OL-19.01: flagged and not completed ⇒ is_flagged=true."""
        fake, backend = self.make_items()
        row = self.row_of(fake, backend, "flagged")
        self.assertTrue(row["flagged"])
        self.assertEqual(self.flagged_uids(backend), {row["uid"]})

    def test_ol_19_02_flag_completed_is_not_flagged(self) -> None:
        """OL-19.02: a flag marked completed ⇒ is_flagged=false."""
        fake, backend = self.make_items()
        row = self.row_of(fake, backend, "flagged_completed")
        self.assertFalse(row["flagged"])
        self.assertNotIn(row["uid"], self.flagged_uids(backend))

    def test_ol_19_03_visible_attachment_counts_and_is_listed(self) -> None:
        """OL-19.03: a visible attachment counts in has_attachments and is listed."""
        fake, backend = self.make_items()
        row = self.row_of(fake, backend, "visible_attachment")
        self.assertTrue(row["has_attachments"])
        self.assertIn(row["uid"], self.attachment_uids(backend))
        self.assertEqual(backend.attachment_names(row["uid"]), ["contrato.pdf"])
        self.assert_read_only(fake)

    def test_ol_19_04_hidden_attachment_neither_counts_nor_is_listed(self) -> None:
        """OL-19.04: a hidden attachment is neither counted nor listed."""
        fake, backend = self.make_items()
        row = self.row_of(fake, backend, "hidden_attachment")
        self.assertFalse(row["has_attachments"])
        self.assertNotIn(row["uid"], self.attachment_uids(backend))
        self.assertEqual(backend.attachment_names(row["uid"]), [])
        self.assert_read_only(fake)


class OutlookItemLookupTests(_ItemCase):
    """membership, duplicate_counts and find_message (annex B.4, PRD 12.4, RF-07)."""

    def test_membership_is_the_folder_of_each_uid(self) -> None:
        fake, backend = self.make_items()
        rows = backend.query(self.all_ids(backend))
        membership = backend.membership([row["uid"] for row in rows])
        self.assertEqual(membership, {row["uid"]: {row["mailbox_id"]} for row in rows})
        facturas = self.row_of(fake, backend, "duplicate_facturas")
        self.assertEqual(facturas["mailbox_id"], fake.folder("facturas").entry_id)

    def test_duplicate_counts_by_internet_message_id(self) -> None:
        fake, backend = self.make_items()
        inbox_id = fake.store("exchange").inbox.entry_id
        rows = {row["uid"]: row for row in backend.query(self.all_ids(backend))}
        first = rows[fake.item("duplicate_inbox").entry_id]
        second = rows[fake.item("duplicate_facturas").entry_id]
        self.assertTrue(first["global_message_id"])
        self.assertEqual(first["global_message_id"], second["global_message_id"])
        self.assertEqual(first["message_id"], "<duplicado-1@example.com>")
        counts = backend.duplicate_counts(self.all_ids(backend))
        self.assertEqual(counts[first["global_message_id"]], 2)
        self.assertEqual(backend.duplicate_counts([inbox_id])[first["global_message_id"]], 1)
        # Without a Message-ID (missing or empty) a message is unique: no key, no count.
        for key in ("no_message_id", "empty_message_id"):
            with self.subTest(item=key):
                row = rows[fake.item(key).entry_id]
                self.assertEqual(row["global_message_id"], 0)
                self.assertEqual(row["message_id"], "")
        self.assertNotIn(0, counts)
        self.assertEqual(set(counts.values()) - {1}, {2})

    def test_find_message_of_an_excluded_store_is_reported_without_opening_items(self) -> None:
        from mailquery.backends.base import ExcludedStoreError

        fake = fk.FakeOutlook.default()
        backend = self.make(fake)
        uid = fake.item("shared_message").entry_id
        with self.assertRaises(ExcludedStoreError) as caught:
            backend.find_message(uid)
        self.assertEqual(
            caught.exception.entry,
            {"label": "Exchange shared (Soporte)", "path": None, "reason": "shared_mailbox"},
        )
        self.assertEqual(fake.call_log.count(kind="NameSpace", member="GetItemFromID"), 0)
        self.assertEqual(fake.call_log.count(kind="Item"), 0)
        self.assertEqual(fake.mutations.total, 0)

    def test_find_message_not_found_cases(self) -> None:
        fake, backend = self.make_items()
        normal = fake.item("normal").entry_id
        missing_tail = normal[:40] + "0" * (len(normal) - 40)
        unknown_store = "00000000" + "AB" * 16 + normal[40:]
        for label, uid in (
            ("receipt", fake.item("delivery_receipt").entry_id),
            ("task", fake.item("task").entry_id),
            ("imap_deleted", fake.item("imap_deleted").entry_id),
            ("missing item", missing_tail),
            ("unknown store", unknown_store),
            ("too short", "0000"),
            ("odd length", normal[:-1]),
        ):
            with self.subTest(case=label):
                self.assertIsNone(backend.find_message(uid))
        folders = fk.FakeOutlook.folder_matrix()
        folder_backend = self.make(folders)
        for key in ("in_hidden_folder", "in_hidden_subfolder"):
            with self.subTest(case=key):
                self.assertIsNone(folder_backend.find_message(folders.item(key).entry_id))
        self.assertEqual(fake.mutations.total + folders.mutations.total, 0)

    def test_find_message_of_an_unopenable_item_comes_from_the_folder_table(self) -> None:
        fake, backend = self.make_items()
        for key, attachments in (
            ("unopenable_with_attachments", True),
            ("unopenable_without_attachments", False),
        ):
            with self.subTest(item=key):
                expected = self.row_of(fake, backend, key)
                found, mailbox = backend.find_message(expected["uid"])
                self.assertEqual(found, expected)
                self.assertEqual(found["has_attachments"], attachments)
                self.assertTrue(mailbox["is_inbox"])
                self.assertEqual(backend.recipients([expected["uid"]]), {})
                self.assertEqual(backend.attachment_names(expected["uid"]), [])

    def test_smime_and_header_only_attachment_names_read_no_content(self) -> None:
        fake, backend = self.make_items()
        for key in ("smime_encrypted", "smime_signed", "header_only"):
            with self.subTest(item=key):
                fake.call_log.clear()
                self.assertEqual(backend.attachment_names(fake.item(key).entry_id), [])
                self.assertEqual(fake.call_log.count(kind="Attachments"), 0)
                self.assertEqual(fake.call_log.count(kind="Item", member="Body"), 0)


# --------------------------------------------------------------------------- #
# OL-17, OL-20…OL-23 — dedupe, body and show (PRD 12.4, 12.5, 12.10, annex B.4)
# --------------------------------------------------------------------------- #

#: Field order of ``show``'s ``message`` (PRD 12.4).
_SHOW_FIELDS = [
    "uid", "message_id", "subject", "from", "to", "cc", "date_sent", "date_received",
    "mailbox", "is_read", "is_flagged", "has_attachments", "size_bytes", "headers",
    "body_text", "body_truncated", "attachments", "partial", "readable", "source",
]
_HEADER_NAMES = ["From", "To", "Cc", "Subject", "Date", "Message-ID"]
_SMIME_ENCRYPTED = "W_BODY_UNREADABLE: S/MIME encrypted content is not supported"
_SMIME_SIGNED = "W_BODY_UNREADABLE: S/MIME signed content is not supported"
#: Item members that read content or could ask for a download (annex B.2 points 4 and 5).
_CONTENT_MEMBERS = frozenset({"Body", "HTMLBody", "Attachments", "MarkForDownload"})
_ITEM_SCOPE = '[scope."ana@example.com"]\nmailbox_list = ["INBOX/Facturas"]\n'
_SINCE_ALL = ["--since", "2026-01-01", "--limit", "200"]


class _OutlookCommandCase(_OutlookCliCase):
    """Commands through ``cli.main`` over a fake profile with a declared account."""

    def use(self, fake: fk.FakeOutlook, scope: str = _ITEM_SCOPE) -> fk.FakeOutlook:
        self.fake = fake
        self.home.mkdir(parents=True, exist_ok=True)
        (self.home / "config.toml").write_text(scope, encoding="utf-8")
        patcher = mock.patch.object(_oc(), "get_drive_type", fake.drive_type)
        patcher.start()
        self.addCleanup(patcher.stop)
        return fake

    def items(self) -> fk.FakeOutlook:
        return self.use(fk.FakeOutlook.item_matrix(_ITEMS_NOW))

    def run_json(self, *argv: str) -> dict:
        backend = _backend(self.fake, tmp_root=self.home / "tmp")
        self.addCleanup(backend.close)
        code, stdout, stderr = self.run_main(list(argv), backend)
        self.assertEqual(code, 0, stdout + stderr)
        payload = json.loads(stdout)
        self.assertTrue(payload["ok"])
        return payload

    def run_error(self, exit_code: int, code: str, *argv: str, backend=None) -> dict:
        backend = backend if backend is not None else _backend(self.fake, tmp_root=self.home / "tmp")
        self.addCleanup(backend.close)
        return self.assert_error(self.run_main(list(argv), backend), exit_code, code)

    def search(self, *extra: str) -> dict:  # type: ignore[override]
        return self.run_json("search", *_SINCE_ALL, *extra)

    def message_of(self, payload: dict, key: str) -> dict:
        uid = _uid(self.fake.item(key).entry_id)
        return next(message for message in payload["messages"] if message["uid"] == uid)

    def show(self, key: str) -> dict:
        return self.run_json("show", self.fake.item(key).entry_id)

    def content_members(self) -> set[tuple[str, str]]:
        """Body, attachment and download members read so far (annex B.2 points 4 and 5)."""
        return {
            (kind, member) for kind, member in self.fake.call_log.members()
            if (kind == "Item" and member in _CONTENT_MEMBERS)
            or kind in ("Attachments", "Attachment")
        }

    def assert_read_only(self) -> None:
        members = {member for _kind, member in self.fake.call_log.members()}
        self.assertFalse(members & _ADDRESS_BOOK_MEMBERS)
        self.assertEqual(self.fake.mutations.total, 0)


class OutlookDedupeTests(_OutlookCommandCase):
    def test_ol_17_01_same_message_id_in_two_folders_is_one_inbox_result(self) -> None:
        """OL-17.01: same Message-ID in INBOX and INBOX/Facturas ⇒ canonical INBOX, duplicate_count 2."""
        fake = self.items()
        payload = self.search()
        uids = [message["uid"] for message in payload["messages"]]
        self.assertIn(_uid(fake.item("duplicate_inbox").entry_id), uids)
        self.assertNotIn(_uid(fake.item("duplicate_facturas").entry_id), uids)
        message = self.message_of(payload, "duplicate_inbox")
        self.assertEqual(message["duplicate_count"], 2)
        self.assertEqual(message["message_id"], "<duplicado-1@example.com>")
        self.assertEqual(message["mailbox"]["path"], "INBOX")
        self.assertEqual(self.message_of(payload, "facturas_recent")["duplicate_count"], 1)
        self.assert_read_only()

    def test_ol_17_02_missing_or_empty_message_id_is_unique(self) -> None:
        """OL-17.02: without a Message-ID (missing or empty) every message is unique."""
        self.items()
        payload = self.search()
        for key in ("no_message_id", "empty_message_id"):
            with self.subTest(item=key):
                message = self.message_of(payload, key)
                self.assertEqual(message["message_id"], "")
                self.assertEqual(message["duplicate_count"], 1)


class OutlookBodyTests(_OutlookCommandCase):
    def body_of(self, key: str) -> tuple[dict, list[str]]:
        """``search`` narrowed by the item's subject; its message and the warnings not about others."""
        spec = self.fake.item(key)
        payload = self.search("--subject", spec.subject)
        wanted = _uid(spec.entry_id)
        messages = [m for m in payload["messages"] if m["uid"] == wanted]
        self.assertEqual(len(messages), 1, payload)
        # Warnings quote the native uid of 2.0.1, so the filter uses the native part.
        others = [
            m["uid"].split(":", 1)[-1]
            for m in payload["messages"]
            if m["uid"] != wanted
        ]
        warnings = [w for w in payload["warnings"] if not any(uid in w for uid in others)]
        return messages[0], warnings

    def test_ol_20_01_plain_text_body(self) -> None:
        """OL-20.01: plain text body in search (snippet) and show (body_text, field order)."""
        self.items()
        message, warnings = self.body_of("normal")
        self.assertEqual(message["snippet"], "Cuerpo de normal.")
        self.assertEqual(
            message["body"], {"available": True, "readable": True, "partial": False, "truncated": False}
        )
        self.assertEqual(warnings, [])
        fake = self.use(fk.FakeOutlook.default(), '[scope."ana.perez@example.com"]\n')
        payload = self.show("normal")
        shown = payload["message"]
        self.assertEqual(list(shown), _SHOW_FIELDS)
        spec = fake.item("normal")
        self.assertEqual(shown["uid"], _uid(spec.entry_id))
        self.assertEqual(shown["body_text"], "Estimado cliente, adjuntamos la factura de octubre.")
        self.assertFalse(shown["body_truncated"])
        self.assertEqual(
            shown["attachments"],
            [{"index": 1, "name": "factura-2026-10.pdf", "cached_path": None}],
        )
        self.assertTrue(shown["has_attachments"])
        self.assertIs(shown["partial"], False)
        self.assertIs(shown["readable"], True)
        self.assertEqual(shown["source"], {"emlx_path": None, "partial": False})
        self.assertEqual(shown["mailbox"]["path"], "INBOX")
        self.assertTrue(shown["mailbox"]["url"].startswith("outlook://"))
        self.assertEqual(shown["from"], {"name": "Proveedor SA", "address": "facturas@proveedor.example"})
        self.assertEqual(shown["to"], [{"name": "Ana Pérez", "address": "ana.perez@example.com"}])
        self.assertEqual(shown["size_bytes"], 48213)
        self.assertEqual(payload["warnings"], [])
        self.assert_read_only()

    def test_ol_20_02_empty_text_with_html_is_converted(self) -> None:
        """OL-20.02: empty Body + HTMLBody ⇒ HTML converted to text; a meeting item has no HTMLBody."""
        fake = self.items()
        message, warnings = self.body_of("html_only")
        self.assertEqual(message["snippet"], "Solo HTML")
        self.assertEqual(
            message["body"], {"available": True, "readable": True, "partial": False, "truncated": False}
        )
        self.assertEqual(warnings, [])
        self.assertEqual(self.show("html_only")["message"]["body_text"], "Solo HTML")
        # MeetingItem: HTMLBody raises AttributeError (host) ⇒ simply no HTML.
        fake.store("exchange").inbox.add_message(
            "meeting_no_body", subject="Convocatoria sin cuerpo",
            message_class="IPM.Schedule.Meeting.Request", body="", html="",
        )
        fake.call_log.clear()
        message, warnings = self.body_of("meeting_no_body")
        self.assertEqual(message["snippet"], "")
        self.assertEqual(
            message["body"], {"available": True, "readable": True, "partial": False, "truncated": False}
        )
        self.assertEqual(warnings, [])
        self.assertIn(("Item", "HTMLBody"), fake.call_log.members())

    def test_ol_20_03_html_without_text_is_html_no_text(self) -> None:
        """OL-20.03: HTML that yields no text ⇒ available/readable true, snippet "" + W_HTML_NO_TEXT."""
        self.items()
        message, warnings = self.body_of("html_no_text")
        self.assertEqual(message["snippet"], "")
        self.assertEqual(
            message["body"], {"available": True, "readable": True, "partial": False, "truncated": False}
        )
        self.assertEqual(warnings, ["W_HTML_NO_TEXT: HTML body produced no plain text"])

    def test_ol_20_04_header_only_item_is_body_not_local_without_download(self) -> None:
        """OL-20.04: header-only item ⇒ false/false/false + W_BODY_NOT_LOCAL; no download/body member."""
        fake = self.items()
        message, warnings = self.body_of("header_only")
        self.assertEqual(message["snippet"], "")
        self.assertEqual(
            message["body"], {"available": False, "readable": False, "partial": False, "truncated": False}
        )
        self.assertEqual(len(warnings), 1, warnings)
        self.assertTrue(warnings[0].startswith("W_BODY_NOT_LOCAL: "), warnings)
        shown = self.show("header_only")
        self.assertEqual(shown["message"]["body_text"], "")
        self.assertIs(shown["message"]["readable"], False)
        self.assertEqual(shown["message"]["attachments"], [])
        self.assertEqual([w.split(":")[0] for w in shown["warnings"]], ["W_BODY_NOT_LOCAL"])
        self.assertEqual(self.content_members(), set())
        self.assert_read_only()

    def assert_smime(self, key: str, warning: str) -> None:
        fake = self.items()
        message, warnings = self.body_of(key)
        self.assertEqual(message["snippet"], "")
        self.assertEqual(
            message["body"], {"available": True, "readable": False, "partial": False, "truncated": False}
        )
        self.assertEqual(warnings, [warning])
        payload = self.show(key)
        shown = payload["message"]
        self.assertEqual(shown["body_text"], "")
        self.assertIs(shown["readable"], False)
        self.assertTrue(shown["has_attachments"])  # the technical smime.p7m/.p7s
        self.assertEqual(shown["attachments"], [])
        self.assertEqual(payload["warnings"], [warning])  # no W_ATTACHMENTS_UNAVAILABLE
        self.assertEqual(self.content_members(), set())
        self.assertEqual(fake.call_log.count(kind="Attachment"), 0)
        self.assert_read_only()

    def test_ol_20_05_smime_encrypted_is_unreadable_without_reading_content(self) -> None:
        """OL-20.05: S/MIME encrypted ⇒ true/false/false + exact W_BODY_UNREADABLE; no body/attachment member."""
        self.assert_smime("smime_encrypted", _SMIME_ENCRYPTED)

    def test_ol_20_06_smime_signed_is_unreadable_without_reading_content(self) -> None:
        """OL-20.06: S/MIME signed ⇒ the same with "signed"."""
        self.assert_smime("smime_signed", _SMIME_SIGNED)

    def test_ol_20_07_unopenable_item_is_body_unreadable(self) -> None:
        """OL-20.07: an item that cannot be opened ⇒ false/false/false + W_BODY_UNREADABLE."""
        self.items()
        for key in ("unopenable_with_attachments", "unopenable_without_attachments"):
            with self.subTest(item=key):
                message, warnings = self.body_of(key)
                self.assertEqual(message["snippet"], "")
                self.assertEqual(
                    message["body"],
                    {"available": False, "readable": False, "partial": False, "truncated": False},
                )
                self.assertEqual(len(warnings), 1, warnings)
                self.assertTrue(warnings[0].startswith("W_BODY_UNREADABLE: "), warnings)
                self.assertNotIn("S/MIME", warnings[0])


class OutlookShowAttachmentTests(_OutlookCommandCase):
    def test_ol_21_01_unreadable_item_with_attachments_warns(self) -> None:
        """OL-21.01: unopenable item with has_attachments ⇒ attachments [] + W_ATTACHMENTS_UNAVAILABLE."""
        self.items()
        payload = self.show("unopenable_with_attachments")
        shown = payload["message"]
        self.assertTrue(shown["has_attachments"])
        self.assertEqual(shown["attachments"], [])
        self.assertIs(shown["readable"], False)
        self.assertEqual(shown["body_text"], "")
        codes = [warning.split(":")[0] for warning in payload["warnings"]]
        self.assertEqual(codes, ["W_BODY_UNREADABLE", "W_ATTACHMENTS_UNAVAILABLE"])
        self.assertNotIn("envelope index", payload["warnings"][1])
        self.assert_read_only()

    def test_ol_21_02_unreadable_item_without_attachments_does_not_warn(self) -> None:
        """OL-21.02: unopenable item without attachments ⇒ attachments [] and no warning."""
        self.items()
        payload = self.show("unopenable_without_attachments")
        shown = payload["message"]
        self.assertFalse(shown["has_attachments"])
        self.assertEqual(shown["attachments"], [])
        self.assertEqual([w.split(":")[0] for w in payload["warnings"]], ["W_BODY_UNREADABLE"])


class OutlookShowHeaderTests(_OutlookCommandCase):
    def test_ol_22_01_transport_headers(self) -> None:
        """OL-22.01: show headers come from PR_TRANSPORT_MESSAGE_HEADERS."""
        from email.utils import format_datetime

        fake = self.items()
        spec = fake.item("normal")
        headers = self.show("normal")["message"]["headers"]
        self.assertEqual(list(headers), _HEADER_NAMES)
        self.assertEqual(
            headers,
            {
                "From": "Remitente <remitente@example.com>",
                "To": "Ana <ana@example.com>",
                "Cc": "Copia <copia@example.com>",
                "Subject": "Normal",
                "Date": format_datetime(spec.sent),  # the RFC 5322 header, not the ISO value
                "Message-ID": spec.message_id,
            },
        )
        self.assertIn(("PropertyAccessor", "GetProperty"), fake.call_log.members())

    def test_ol_22_02_internal_mail_without_headers_is_synthesized(self) -> None:
        """OL-22.02: internal mail without transport headers ⇒ From/To/Cc/Subject/Date/Message-ID synthesized."""
        from mailquery import output

        fake = self.items()
        spec = fake.item("internal_no_headers")
        self.assertIsNone(spec.headers)
        shown = self.show("internal_no_headers")["message"]
        self.assertEqual(
            shown["headers"],
            {
                "From": "Colega <colega@example.com>",
                "To": "Ana <ana@example.com>",
                "Cc": "",
                "Subject": "Internal no headers",
                "Date": output.iso_timestamp(int(spec.sent.timestamp())),
                "Message-ID": spec.message_id,
            },
        )
        self.assertEqual(shown["date_sent"], shown["headers"]["Date"])


class OutlookShowUidTests(_OutlookCommandCase):
    def assert_not_found(self, uid: str) -> None:
        error = self.run_error(2, "E_USAGE", "show", uid)
        self.assertIn(f"message uid '{_uid(uid)}' was not found", error["message"])
        self.assertIn("excluded_stores", error["hint"])
        self.assertIn("mailboxes", error["hint"])

    def test_ol_23_01_lowercase_uid_is_usage_error(self) -> None:
        """OL-23.01: a lowercase uid ⇒ E_USAGE "expected an uppercase hexadecimal EntryID", before connecting."""
        fake = self.items()
        uid = fake.item("normal").entry_id.lower()
        error = self.run_error(2, "E_USAGE", "show", uid)
        self.assertEqual(
            error["message"],
            f"invalid uid part {uid!r}: expected an uppercase hexadecimal EntryID"
        )
        self.assertEqual(len(fake.call_log), 0)

    def test_ol_23_02_invalid_uid_with_pywin32_missing_is_usage_error(self) -> None:
        """OL-23.02: invalid uid with pywin32 absent ⇒ E_USAGE before connecting (not E_DEPENDENCY_MISSING)."""
        fake = self.items()
        for uid in ("00ab", "12G4", "0x1F"):
            with self.subTest(uid=uid):
                error = self.run_error(
                    2, "E_USAGE", "show", uid, backend=_backend(fake, pywin32=False)
                )
                self.assertIn("expected an uppercase hexadecimal EntryID", error["message"])
        blocked = {"win32com": None, "win32com.client": None, "pythoncom": None, "pywintypes": None}
        with mock.patch.dict(sys.modules, blocked):
            backend = _backend(fake, outlook_app=None, pywin32=None, tmp_root=self.home / "tmp")
            self.run_error(2, "E_USAGE", "show", "00ab", backend=backend)
        self.assertEqual(len(fake.call_log), 0)
        self.assertEqual(fake.registry.reads, [])
        # A valid uid does reach detection: pywin32 missing is then reported.
        self.run_error(
            3, "E_DEPENDENCY_MISSING", "show", fake.item("normal").entry_id,
            backend=_backend(fake, pywin32=False),
        )

    def test_ol_23_03_unknown_uid_is_not_found_with_excluded_stores_hint(self) -> None:
        """OL-23.03: unknown uid (also an EntryID of no store) ⇒ "was not found", hint to excluded_stores."""
        fake = self.items()
        normal = fake.item("normal").entry_id
        for label, uid in (
            ("missing item", normal[:40] + "0" * (len(normal) - 40)),
            ("unknown store", "00000000" + "AB" * 16 + normal[40:]),
            ("too short", "00AB"),
        ):
            with self.subTest(case=label):
                self.assert_not_found(uid)
        self.assert_read_only()

    def test_ol_23_04_item_that_is_not_mail_is_not_found(self) -> None:
        """OL-23.04: a receipt or a task ⇒ not found."""
        fake = self.items()
        for key in ("delivery_receipt", "task", "imap_deleted"):
            with self.subTest(item=key):
                self.assert_not_found(fake.item(key).entry_id)

    def test_ol_23_05_item_in_a_hidden_folder_is_not_found(self) -> None:
        """OL-23.05: an item in a sync folder (or its subfolder) ⇒ not found."""
        fake = self.use(fk.FakeOutlook.folder_matrix(), '[scope."lucia@example.es"]\n')
        for key in ("in_hidden_folder", "in_hidden_subfolder"):
            with self.subTest(item=key):
                self.assert_not_found(fake.item(key).entry_id)

    def test_ol_23_06_excluded_store_uid_is_account_not_in_scope_with_the_reason(self) -> None:
        """OL-23.06: a uid of an excluded store (by PR_RECORD_KEY) ⇒ E_ACCOUNT_NOT_IN_SCOPE with the reason."""
        fake = self.use(fk.FakeOutlook.default(), '[scope."ana.perez@example.com"]\n')
        error = self.run_error(2, "E_ACCOUNT_NOT_IN_SCOPE", "show", fake.item("shared_message").entry_id)
        self.assertIn("Exchange shared (Soporte)", error["message"])
        self.assertIn("shared_mailbox", error["message"])
        self.assertIn("excluded_stores", error["hint"])
        self.assertEqual(fake.call_log.count(kind="NameSpace", member="GetItemFromID"), 0)
        self.assertEqual(fake.call_log.count(kind="Item"), 0)
        self.assertEqual(fake.mutations.total, 0)

    def test_ol_23_07_folder_outside_mailbox_list_of_a_declared_account_succeeds(self) -> None:
        """OL-23.07: declared account, folder not in mailbox_list ⇒ success."""
        fake = self.use(fk.FakeOutlook.item_matrix(_ITEMS_NOW), '[scope."ana@example.com"]\n')
        payload = self.show("duplicate_facturas")
        self.assertEqual(payload["message"]["uid"], _uid(fake.item("duplicate_facturas").entry_id))
        self.assertEqual(payload["message"]["mailbox"]["path"], "INBOX/Facturas")
        self.assertEqual(payload["message"]["body_text"], "Cuerpo de duplicate_facturas.")


# --------------------------------------------------------------------------- #
# Commands end to end (W3-T07): candidates, exclusions, W_STORE_EXCLUDED,
# neutral fields, log, counters and the read-only gate of the W3 commands
# --------------------------------------------------------------------------- #

_NO_ACCOUNTS = "W_NO_ACCOUNTS: no accounts are declared in config.toml; nothing is observed"
#: Codes annex B.7 excludes from the Outlook backend (OL-30.04).
_FOREIGN_CODES = (
    "E_STORE_NOT_FOUND",
    "E_SCHEMA_UNSUPPORTED",
    "E_DB_BUSY",
    "E_ACCOUNT_LABELS_UNAVAILABLE",
    "W_ACCOUNT_LABELS_UNAVAILABLE",
    "W_EMLX_MISSING",
    "W_EMLX_CORRUPT",
)
#: Object kinds below store level: what an excluded store must never show in the CallLog.
_BELOW_STORE_KINDS = frozenset(
    {
        "Folders", "Folder", "Table", "Columns", "Column", "Row", "Item",
        "Attachments", "Attachment", "Recipients", "Recipient",
    }
)


def _toml_key(key: str) -> str:
    return key.replace("\\", "\\\\").replace('"', '\\"')


def _scope_toml(*keys: str) -> str:
    return "".join(f'[scope."{_toml_key(key)}"]\n' for key in keys)


def _matrix_candidate_scope() -> str:
    """Every candidate of the store matrix; the PST without inbox observes its folder."""
    return _scope_toml(*(label for label, _email, _local in _MATRIX_CANDIDATES.values())).replace(
        '[scope."PST (Notas)"]\n', '[scope."PST (Notas)"]\nmailbox_list = ["Proyectos"]\n'
    )


def _store_excluded(label: str, path: str | None, reason: str) -> str:
    where = f"{label} at {path}" if path else label
    return f"W_STORE_EXCLUDED: {where} is excluded: {reason}"


def _listed_with_items(fake: fk.FakeOutlook, rows) -> int:
    """Listed folders (``mailboxes()`` rows) that hold at least one item in the fake."""
    specs = {folder.entry_id: folder for store in fake.stores for folder in store.walk()}
    return sum(1 for row in rows if specs[row["id"]].items)


def _tables(fake: fk.FakeOutlook) -> list[list[str]]:
    """Columns added to each ``Folder.GetTable`` of the CallLog, in call order."""
    tables: list[list[str]] = []
    for entry in fake.call_log:
        if (entry.kind, entry.member) == ("Folder", "GetTable"):
            tables.append([])
        elif (entry.kind, entry.member) == ("Columns", "Add") and tables:
            tables[-1].append(entry.args[0])
    return tables


class _CommandScenarioCase(_OutlookCommandCase):
    """Command runs that tolerate errors: ``(exit code, payload)``."""

    def run_any(self, *argv: str) -> tuple[int, dict]:
        backend = _backend(self.fake, tmp_root=self.home / "tmp")
        self.addCleanup(backend.close)
        code, stdout, stderr = self.run_main(list(argv), backend)
        self.assertTrue(stdout.strip(), stderr)
        return code, json.loads(stdout)


class OutlookCandidateStoreTests(_CommandScenarioCase):
    def assert_candidate(self, key: str) -> None:
        label, email, _local = _MATRIX_CANDIDATES[key]
        fake = self.use(fk.FakeOutlook.store_matrix(), _scope_toml(label))
        payload = self.run_json("search")
        self.assertEqual(payload["count"], 1, payload)
        message = payload["messages"][0]
        self.assertEqual(message["uid"], _uid(fake.item(f"{key}_message").entry_id))
        account = message["mailbox"]["account"]
        self.assertEqual(account, {"uuid": self.uuid_of(key), "label": label, "email": email})
        self.assertEqual(payload["warnings"], [])
        shown = self.run_json("show", message["uid"])["message"]
        self.assertEqual(shown["uid"], message["uid"])
        self.assertEqual(shown["mailbox"], message["mailbox"])
        self.assertEqual(shown["body_text"], "")
        self.assert_read_only()

    def uuid_of(self, key: str) -> str:
        return self.fake.store(key).uuid

    def test_ol_06_01_cached_exchange_is_exchange_smtp(self) -> None:
        """OL-06.01: a cached Exchange account ⇒ `Exchange (<smtp>)`; search and show work."""
        self.assert_candidate("exchange_cached")

    def test_ol_06_02_imap_is_imap_smtp(self) -> None:
        """OL-06.02: an IMAP account ⇒ `IMAP (<smtp>)`; search and show work."""
        self.assert_candidate("imap")

    def test_ol_06_03_pop3_on_pst_is_pop3_smtp_not_pst(self) -> None:
        """OL-06.03: a POP3 account delivering to a PST ⇒ `POP3 (<smtp>)`, never `PST (…)`."""
        self.assert_candidate("pop3")
        self.assertTrue(self.fake.store("pop3").file_path.endswith(".pst"))
        payload = self.run_json("mailboxes")
        labels = [account["label"] for account in payload["accounts"]]
        self.assertIn("POP3 (diego@example.net)", labels)
        self.assertFalse([label for label in labels if "diego" in label and label.startswith("PST")])

    def test_ol_06_04_eas_is_eas_smtp(self) -> None:
        """OL-06.04: an EAS account ⇒ `EAS (<smtp>)`; search and show work."""
        self.assert_candidate("eas")

    def test_ol_06_05_local_pst_is_pst_name_with_null_email(self) -> None:
        """OL-06.05: a local PST ⇒ `PST (<name>)`, `email: null`; search and show work."""
        self.assert_candidate("pst")

    def test_ol_06_06_pst_on_a_removable_disk_is_a_candidate(self) -> None:
        """OL-06.06: a PST on a removable disk is local: a candidate; search and show work."""
        self.assert_candidate("pst_removable")
        self.assertEqual(self.fake.drive_type("E:\\"), fk.DRIVE_REMOVABLE)


class OutlookExcludedStoreTests(_CommandScenarioCase):
    def excluded_entry(self, key: str) -> dict:
        """``mailboxes.excluded_stores`` entry of one store of the store matrix."""
        self.use(fk.FakeOutlook.store_matrix(), _matrix_candidate_scope())
        payload = self.run_json("mailboxes")
        label, path, reason = _MATRIX_EXCLUDED[key]
        entry = {"label": label, "path": path, "reason": reason}
        self.assertIn(entry, payload["excluded_stores"])
        self.assertEqual(list(payload["excluded_stores"][0]), ["label", "path", "reason"])
        self.assertNotIn(label, [account["label"] for account in payload["accounts"]])
        return entry

    def test_ol_07_01_shared_mailbox(self) -> None:
        """OL-07.01: a shared mailbox ⇒ `shared_mailbox`, `path: null`."""
        entry = self.excluded_entry("shared")
        self.assertEqual(entry, {"label": "Exchange shared (Soporte)", "path": None, "reason": "shared_mailbox"})

    def test_ol_07_02_public_folders(self) -> None:
        """OL-07.02: public folders ⇒ `public_folders`."""
        self.assertEqual(self.excluded_entry("public")["reason"], "public_folders")

    def test_ol_07_03_exchange_in_online_mode(self) -> None:
        """OL-07.03: an Exchange account without cached mode ⇒ `online_mode`, the account label."""
        entry = self.excluded_entry("exchange_online")
        self.assertEqual(entry, {"label": "Exchange (bruno@example.com)", "path": None, "reason": "online_mode"})

    def test_ol_07_04_other_exchange_store_without_local_copy(self) -> None:
        """OL-07.04: another Exchange store without a local copy ⇒ `online_mode`, its display name."""
        entry = self.excluded_entry("exchange_archive")
        self.assertEqual(entry["reason"], "online_mode")
        self.assertEqual(entry["label"], "Archivo en línea - ana@example.com")

    def test_ol_07_05_pst_on_a_unc_path(self) -> None:
        """OL-07.05: a PST on a UNC path ⇒ `network_path` with the full path."""
        entry = self.excluded_entry("pst_unc")
        self.assertEqual(entry["path"], "\\\\nas01\\backup\\archivo2019.pst")
        self.assertEqual(entry["reason"], "network_path")

    def test_ol_07_06_pst_on_a_mapped_drive(self) -> None:
        """OL-07.06: a PST on a mapped network drive ⇒ `network_path`."""
        entry = self.excluded_entry("pst_mapped")
        self.assertEqual(entry, {"label": "PST (Archivo 2018)", "path": "Z:\\archivo2018.pst", "reason": "network_path"})

    def test_ol_07_07_account_of_another_type(self) -> None:
        """OL-07.07: an account of another type ⇒ `unsupported_account_type`, `<type> (<smtp>)`."""
        entry = self.excluded_entry("other_type")
        self.assertEqual(entry["reason"], "unsupported_account_type")
        self.assertEqual(entry["label"], "HTTP (fede@example.com)")

    def test_ol_07_08_unreadable_store_with_a_name(self) -> None:
        """OL-07.08: an unreadable store whose name was read ⇒ `unavailable` with its name."""
        entry = self.excluded_entry("unavailable_named")
        self.assertEqual(entry, {"label": "Buzón remoto", "path": None, "reason": "unavailable"})

    def test_ol_07_09_unreadable_store_without_a_name(self) -> None:
        """OL-07.09: an unreadable store without a name ⇒ `unavailable`, label `unknown`, `path: null`."""
        entry = self.excluded_entry("unavailable_unnamed")
        self.assertEqual(entry, {"label": "unknown", "path": None, "reason": "unavailable"})

    def test_ol_07_10_unavailable_store_does_not_block_the_others(self) -> None:
        """OL-07.10: with unavailable stores in the profile, every candidate is listed and read."""
        fake = self.use(fk.FakeOutlook.store_matrix(), _matrix_candidate_scope())
        mailboxes = self.run_json("mailboxes")
        reasons = [entry["reason"] for entry in mailboxes["excluded_stores"]]
        self.assertEqual(reasons.count("unavailable"), 2)
        self.assertEqual(
            [account["label"] for account in mailboxes["accounts"]],
            [label for label, _email, _local in _MATRIX_CANDIDATES.values()],
        )
        self.assertTrue(all(account["declared"] for account in mailboxes["accounts"]))
        payload = self.run_json("search")
        expected = {_uid(fake.item(f"{key}_message").entry_id) for key in _MATRIX_CANDIDATES}
        self.assertEqual({message["uid"] for message in payload["messages"]}, expected)
        self.assert_read_only()

    def test_ol_07_11_call_log_has_no_folder_or_item_of_an_excluded_store(self) -> None:
        """OL-07.11: below store level, the CallLog is the same as for a profile without the excluded stores."""

        def sweep(fake: fk.FakeOutlook) -> list[tuple]:
            self.use(fake, _matrix_candidate_scope())
            self.run_json("mailboxes")
            self.run_json("search", "--subject", "Mensaje*")
            self.run_json("show", fake.item("pst_message").entry_id)
            return [
                (entry.kind, entry.member, entry.action, entry.args)
                for entry in fake.call_log
                if entry.kind in _BELOW_STORE_KINDS
                or (entry.kind == "Store" and entry.member in ("GetRootFolder", "GetDefaultFolder"))
                or (entry.kind == "NameSpace" and entry.member == "GetItemFromID")
                or (
                    entry.kind == "PropertyAccessor"
                    and str(entry.args[0]).casefold() != fk.PR_RECORD_KEY.casefold()
                )
            ]

        full = fk.FakeOutlook.store_matrix()
        excluded_ids = {full.store(key).store_id for key in _MATRIX_EXCLUDED}
        got = sweep(full)
        only_candidates = fk.FakeOutlook.store_matrix()
        only_candidates.stores = [
            spec for spec in only_candidates.stores if spec.key not in _MATRIX_EXCLUDED
        ]
        only_candidates.accounts = [
            account for account in only_candidates.accounts
            if account.store.key not in _MATRIX_EXCLUDED
        ]
        self.assertTrue(got)
        self.assertEqual(got, sweep(only_candidates))
        opened_in = {entry[3][1] for entry in got if entry[1] == "GetItemFromID"}
        self.assertTrue(opened_in)
        self.assertFalse(opened_in & excluded_ids)
        self.assertEqual(full.mutations.total, 0)


class OutlookStoreExcludedWarningTests(_CommandScenarioCase):
    _UNC = _store_excluded("PST (Archivo 2019)", "\\\\nas01\\backup\\archivo2019.pst", "network_path")
    _SHARED = _store_excluded("Exchange shared (Soporte)", None, "shared_mailbox")

    def test_ol_09_01_declared_excluded_with_path_warns_in_search(self) -> None:
        """OL-09.01: declared and excluded with a path ⇒ `W_STORE_EXCLUDED: <label> at <path> is excluded: <reason>`."""
        fake = self.use(
            fk.FakeOutlook.store_matrix(), _scope_toml("ana@example.com", "PST (Archivo 2019)")
        )
        payload = self.run_json("search")
        self.assertEqual(payload["warnings"], [self._UNC])
        self.assertEqual(
            payload["warnings"][0],
            "W_STORE_EXCLUDED: PST (Archivo 2019) at \\\\nas01\\backup\\archivo2019.pst "
            "is excluded: network_path",
        )
        self.assertEqual(
            [message["uid"] for message in payload["messages"]],
            [_uid(fake.item("exchange_cached_message").entry_id)],
        )

    def test_ol_09_02_declared_excluded_without_path_omits_at(self) -> None:
        """OL-09.02: without a path the same text has no ` at <path>`."""
        self.use(fk.FakeOutlook.default(), _scope_toml("ana.perez@example.com", "Exchange shared (Soporte)"))
        payload = self.run_json("search")
        self.assertEqual(
            payload["warnings"][0], "W_STORE_EXCLUDED: Exchange shared (Soporte) is excluded: shared_mailbox"
        )
        self.assertEqual(
            [w for w in payload["warnings"] if w.startswith("W_STORE_EXCLUDED")], [self._SHARED]
        )
        self.assertEqual(payload["count"], 3)

    def test_ol_09_03_same_warning_in_show_and_mailboxes(self) -> None:
        """OL-09.03: the same W_STORE_EXCLUDED in `show` and `mailboxes` (once per store)."""
        fake = fk.FakeOutlook.default()
        self.use(
            fake,
            _scope_toml("ana.perez@example.com", "Exchange shared (Soporte)", fake.store("shared").uuid),
        )
        shown = self.run_json("show", fake.item("normal").entry_id)
        self.assertEqual(shown["warnings"], [self._SHARED])
        mailboxes = self.run_json("mailboxes")
        self.assertEqual(mailboxes["warnings"], [self._SHARED])
        self.assertEqual([a["label"] for a in mailboxes["accounts"]], ["Exchange (ana.perez@example.com)"])
        # The header-only body warning comes after the scope warning.
        header_only = self.run_json("show", fake.item("header_only").entry_id)
        self.assertEqual(header_only["warnings"][0], self._SHARED)
        self.assertTrue(header_only["warnings"][1].startswith("W_BODY_NOT_LOCAL: "))

    def test_ol_09_04_all_declared_excluded_is_count_0_with_both_warnings(self) -> None:
        """OL-09.04: every declared account excluded ⇒ `count: 0`, W_STORE_EXCLUDED and W_NO_ACCOUNTS.

        Order of the scope warnings: PRD 12.3 step 6 (W_NO_ACCOUNTS, W_STORE_EXCLUDED).
        """
        fake = self.use(
            fk.FakeOutlook.store_matrix(),
            _scope_toml("Exchange shared (Soporte)", "PST (Archivo 2019)", "Buzón remoto"),
        )
        expected = [
            _NO_ACCOUNTS,
            self._SHARED,
            self._UNC,
            _store_excluded("Buzón remoto", None, "unavailable"),
        ]
        payload = self.run_json("search")
        self.assertEqual(payload["count"], 0)
        self.assertEqual(payload["messages"], [])
        self.assertEqual(payload["warnings"], expected)
        mailboxes = self.run_json("mailboxes")
        self.assertEqual(mailboxes["warnings"], expected)
        self.assertFalse(any(mailbox["included"] for mailbox in mailboxes["mailboxes"]))
        self.assertEqual(fake.call_log.count(kind="NameSpace", member="GetItemFromID"), 0)


class OutlookNeutralFieldTests(_StoreCase):
    _SCENARIOS = ("default", "store_matrix", "folder_matrix", "item_matrix")

    def test_ol_28_01_is_aggregate_is_always_false(self) -> None:
        """OL-28.01: no Outlook folder is an aggregate mailbox: `is_aggregate` is always false."""
        for name in self._SCENARIOS:
            backend = self.make(fk.SCENARIOS[name]())
            rows = backend.mailboxes()
            with self.subTest(scenario=name):
                self.assertTrue(rows)
                self.assertEqual({row["is_aggregate"] for row in rows}, {False})
                self.assertEqual(
                    {row["is_aggregate"] for row in backend.mailboxes_without_counters()}, {False}
                )

    def test_ol_28_02_labels_available_is_always_true(self) -> None:
        """OL-28.02: account labels always come from the profile: `labels_available` is true."""
        for name in self._SCENARIOS:
            with self.subTest(scenario=name):
                self.assertIs(self.make(fk.SCENARIOS[name]()).labels_available, True)


class OutlookLogTests(_CommandScenarioCase):
    def run_logged(self) -> tuple[fk.FakeOutlook, str]:
        fake = self.use(
            fk.FakeOutlook.default(), _scope_toml("ana.perez@example.com", "Exchange shared (Soporte)")
        )
        self.run_json("--log-level", "debug", "mailboxes")
        self.run_json("--log-level", "debug", "search", "--subject", "Factura*")
        for key in ("normal", "header_only", "smime_encrypted"):
            self.run_json("--log-level", "debug", "show", fake.item(key).entry_id)
        self.run_any("--log-level", "debug", "show", fake.item("shared_message").entry_id)
        return fake, (self.home / "logs" / "mailquery.log").read_text(encoding="utf-8")

    def test_ol_29_01_log_names_the_outlook_backend(self) -> None:
        """OL-29.01: every command start line says `backend=outlook`."""
        _fake, log = self.run_logged()
        starts = [line for line in log.splitlines() if "event=start" in line]
        self.assertEqual(len(starts), 6)
        for line in starts:
            self.assertIn(" backend=outlook", line)

    def test_ol_29_02_log_has_the_strategy_and_outlook_version(self) -> None:
        """OL-29.02: the connection line has strategy `com_readonly` and the Outlook version."""
        _fake, log = self.run_logged()
        lines = [line for line in log.splitlines() if "strategy=" in line]
        self.assertEqual(len(lines), 6)
        for line in lines:
            self.assertIn(f"strategy=com_readonly version={fk.DEFAULT_VERSION}", line)

    def test_ol_29_03_log_has_no_uid_entryid_or_storeid(self) -> None:
        """OL-29.03: no uid, folder EntryID, StoreID, record key or account data in the log."""
        fake, log = self.run_logged()
        folded = log.casefold()
        forbidden: dict[str, str] = {}
        for spec in fake.items.values():
            forbidden[f"uid {spec.key}"] = spec.entry_id
            forbidden[f"short id {spec.key}"] = spec.short_id
        for store in fake.stores:
            forbidden[f"StoreID {store.key}"] = store.store_id
            forbidden[f"record key {store.key}"] = store.record_key.hex()
            forbidden[f"uuid {store.key}"] = store.uuid
            for folder in [store.root, *store.walk()]:
                forbidden[f"folder EntryID {folder.name}"] = folder.entry_id
        forbidden.update(
            {"email": "ana.perez@example.com", "label": "Soporte", "subject": "Factura octubre"}
        )
        for name, value in forbidden.items():
            self.assertNotIn(value.casefold(), folded, f"log leaks the {name}")
        self.assertIn("code=E_ACCOUNT_NOT_IN_SCOPE", log)


class OutlookCounterTests(_CommandScenarioCase):
    _COUNTER_COLUMNS = [fk.PR_MESSAGE_FLAGS, fk.PR_MSG_STATUS]

    def test_search_and_show_read_no_folder_counters(self) -> None:
        """Only `mailboxes` scans folder tables for `total`/`unread` (PRD 19, annex B.9)."""
        fake = self.use(fk.FakeOutlook.default(), _scope_toml("ana.perez@example.com"))
        self.run_json("search", "--since", "2026-01-01")
        tables = _tables(fake)
        # INBOX only: one item table for the query and one for the Message-ID counts.
        self.assertEqual(len(tables), 2, tables)
        self.assertNotIn(self._COUNTER_COLUMNS, tables)
        fake.call_log.clear()
        self.run_json("show", fake.item("normal").entry_id)
        self.assertEqual(_tables(fake), [])
        fake.call_log.clear()
        payload = self.run_json("mailboxes")
        # Only INBOX has items: the empty folders are counted from their own counters.
        # INBOX: the searchable-class row count, then the rows that may be IMAP-deleted.
        self.assertEqual(len(payload["mailboxes"]), 3)
        self.assertEqual(_tables(fake), [[], self._COUNTER_COLUMNS])
        inbox = next(row for row in payload["mailboxes"] if row["path"] == "INBOX")
        self.assertEqual((inbox["total"], inbox["unread"]), (3, 2))

    def test_mailboxes_counts_each_folder_once_per_backend(self) -> None:
        """`mailboxes()` counts a folder table once; later calls reuse the counters."""
        fake = fk.FakeOutlook.default()
        with mock.patch.object(_oc(), "get_drive_type", fake.drive_type):
            backend = _backend(fake)
            self.addCleanup(backend.close)
            backend.mailboxes_without_counters()
            self.assertEqual(_tables(fake), [])
            first = backend.mailboxes()
            second = backend.mailboxes()
        self.assertEqual(first, second)
        self.assertEqual(len(_tables(fake)), 2 * _listed_with_items(fake, first))


def _counter_profile(*, content_counters: bool = True) -> fk.FakeOutlook:
    """One Exchange INBOX mixing searchable items with every kind of non-searchable row."""
    fake = fk.FakeOutlook()
    store = fake.add_exchange_account("exchange", "ana@example.com")
    inbox = store.inbox
    assert inbox is not None
    inbox.content_counters = content_counters
    for index in range(6):
        inbox.add_message(f"mail_{index}", read=index < 2)
    inbox.add_message("smime_lowercase", message_class="ipm.note.smime")
    inbox.add_message("meeting_response", message_class="IPM.Schedule.Meeting.Resp.Pos")
    inbox.add_message("answered", msg_status=0x200)  # PR_MSG_STATUS >= 8 without the IMAP mark
    inbox.add_message("receipt", message_class="IPM.Report.IPM.Note.DR")
    inbox.add_message("notebook", message_class="IPM.NoteBook", read=True)
    inbox.add_message("imap_deleted", msg_status=fk.MSGSTATUS_DELMARKED)
    return fake


class OutlookRoundTripTests(_CommandScenarioCase):
    """Fewest COM round trips (PRD 19, RNF-03): counters, bulk tables, per-store walks."""

    def backend_of(self, fake: fk.FakeOutlook):
        patcher = mock.patch.object(_oc(), "get_drive_type", fake.drive_type)
        patcher.start()
        self.addCleanup(patcher.stop)
        backend = _backend(fake)
        self.addCleanup(backend.close)
        return backend

    def inbox_counters(self, fake: fk.FakeOutlook) -> tuple[int, int]:
        row = next(row for row in self.backend_of(fake).mailboxes() if row["is_inbox"])
        return row["total"], row["unread"]

    def test_mailboxes_counts_from_folder_counters_and_reads_only_exception_rows(self) -> None:
        fake = _counter_profile()
        # 6 mails (2 read), S/MIME, meeting and answered count; receipt, notebook, IMAP-deleted not.
        self.assertEqual(self.inbox_counters(fake), (9, 7))
        from mailquery.backends import outlook as ol

        tables = [e.args for e in fake.call_log if (e.kind, e.member) == ("Folder", "GetTable")]
        # Rows of other classes exist (10 of 12 have a searchable class): exceptions table.
        self.assertEqual(
            tables,
            [
                (ol.SEARCHABLE_CLASS_FILTER, fk.OL_USER_ITEMS),
                (ol.COUNTER_EXCEPTIONS_FILTER, fk.OL_USER_ITEMS),
            ],
        )
        self.assertEqual(fake.call_log.count(kind="Table", member="GetRowCount"), 1)
        self.assertEqual(fake.call_log.count(kind="Table", member="GetNextRow"), 0)
        self.assertEqual(fake.call_log.count(kind="Row"), 0)
        self.assertEqual(fake.call_log.count(kind="Table", member="GetArray"), 1)
        # The restricted table holds only the rows that may not be searchable.
        inbox = _stores(fake)["exchange"].GetDefaultFolder(fk.OL_FOLDER_INBOX)
        exceptions = inbox.GetTable(ol.COUNTER_EXCEPTIONS_FILTER, fk.OL_USER_ITEMS)
        self.assertEqual(exceptions.GetRowCount(), 4)  # answered, receipt, notebook, IMAP-deleted
        self.assertEqual(fake.mutations.total, 0)

    def test_folder_of_searchable_classes_reads_only_the_deletion_candidates(self) -> None:
        from mailquery.backends import outlook as ol

        fake = fk.FakeOutlook()
        inbox = fake.add_exchange_account("exchange", "ana@example.com").inbox
        assert inbox is not None
        for index in range(5):
            inbox.add_message(f"mail_{index}", read=index == 0)
        inbox.add_message("meeting", message_class="IPM.Schedule.Meeting.Request")
        inbox.add_message("answered", msg_status=0x200)
        inbox.add_message("imap_deleted", msg_status=fk.MSGSTATUS_DELMARKED)
        self.assertEqual(self.inbox_counters(fake), (7, 6))
        tables = [e.args for e in fake.call_log if (e.kind, e.member) == ("Folder", "GetTable")]
        self.assertEqual(
            tables,
            [
                (ol.SEARCHABLE_CLASS_FILTER, fk.OL_USER_ITEMS),
                (ol.DELETION_CANDIDATES_FILTER, fk.OL_USER_ITEMS),
            ],
        )
        folder = _stores(fake)["exchange"].GetDefaultFolder(fk.OL_FOLDER_INBOX)
        candidates = folder.GetTable(ol.DELETION_CANDIDATES_FILTER, fk.OL_USER_ITEMS)
        self.assertEqual(candidates.GetRowCount(), 2)  # answered, IMAP-deleted
        self.assertEqual(fake.call_log.count(kind="Row"), 0)

    def test_mailboxes_without_folder_counters_classifies_every_row(self) -> None:
        fake = _counter_profile(content_counters=False)
        self.assertEqual(self.inbox_counters(fake), (9, 7))
        tables = [e.args for e in fake.call_log if (e.kind, e.member) == ("Folder", "GetTable")]
        self.assertEqual(tables, [("", fk.OL_USER_ITEMS)])
        self.assertEqual(fake.call_log.count(kind="Table", member="GetNextRow"), 0)

    def test_empty_folders_are_counted_without_a_table(self) -> None:
        fake = fk.FakeOutlook.default()
        rows = self.backend_of(fake).mailboxes()
        self.assertEqual(
            [(row["path"], row["total"], row["unread"]) for row in rows],
            [("INBOX", 3, 2), ("Deleted Items", 0, 0), ("Sent Items", 0, 0)],
        )
        self.assertEqual(fake.call_log.count(kind="Folder", member="GetTable"), 2)  # INBOX only

    def test_item_tables_are_read_in_bulk(self) -> None:
        from mailquery.backends import outlook as ol

        fake = fk.FakeOutlook.item_matrix(_ITEMS_NOW)
        backend = self.backend_of(fake)
        ids = [row["id"] for row in backend.mailboxes_without_counters()]
        expected = backend.query(ids)
        inbox_rows = len(fake.store("exchange").inbox.items)
        fake.call_log.clear()
        with mock.patch.object(ol, "TABLE_CHUNK_ROWS", 4):
            self.assertEqual(backend.query(ids), expected)
            self.assertEqual(backend.duplicate_counts(ids), backend.duplicate_counts(ids))
        self.assertEqual(fake.call_log.count(kind="Table", member="GetNextRow"), 0)
        self.assertEqual(fake.call_log.count(kind="Table", member="EndOfTable"), 0)
        self.assertEqual(fake.call_log.count(kind="Row"), 0)
        self.assertGreaterEqual(
            fake.call_log.count(kind="Table", member="GetArray"), -(-inbox_rows // 4)
        )

    def two_accounts(self) -> fk.FakeOutlook:
        fake = fk.FakeOutlook()
        for key, smtp in (("first", "ana@example.com"), ("second", "bea@example.com")):
            store = fake.add_exchange_account(key, smtp)
            assert store.inbox is not None
            store.inbox.add_message(f"{key}_message", received=_ITEMS_NOW - timedelta(hours=1))
        return self.use(fake, _scope_toml("ana@example.com"))

    def test_search_new_and_show_walk_only_the_declared_store(self) -> None:
        fake = self.two_accounts()
        runs = {
            "search": ("search", *_SINCE_ALL),
            "new": ("new", "--peek"),
            "show": ("show", fake.item("first_message").entry_id),
        }
        for name, argv in runs.items():
            fake.call_log.clear()
            self.run_json(*argv)
            with self.subTest(command=name):
                self.assertEqual(fake.call_log.count(kind="Store", member="GetRootFolder"), 1)
                # The inbox and the four hidden sync folders of that store only.
                self.assertEqual(fake.call_log.count(kind="Store", member="GetDefaultFolder"), 5)
        fake.call_log.clear()
        self.run_json("mailboxes")
        self.assertEqual(fake.call_log.count(kind="Store", member="GetRootFolder"), 2)
        self.assertEqual(fake.mutations.total, 0)

    def test_show_finds_the_folder_without_walking_the_tree_again(self) -> None:
        fake = self.two_accounts()
        fake.call_log.clear()
        shown = self.run_json("show", fake.item("first_message").entry_id)["message"]
        self.assertEqual(shown["mailbox"]["path"], "INBOX")
        # One walk for the scope; finding the message reuses it.
        self.assertEqual(fake.call_log.count(kind="Store", member="GetRootFolder"), 1)
        self.assertEqual(fake.call_log.count(kind="Folder", member="GetTable"), 0)


class PyIDispatch:
    """Stand-in of pywin32's ``PyIDispatch`` (the proxy recognises it by type name)."""

    def __init__(self, members: dict[str, Any], log: list) -> None:
        self.members = members
        self.log = log
        self.ids = {name: 100 + index for index, name in enumerate(members)}

    def GetIDsOfNames(self, name: str) -> int:  # noqa: N802 - COM name
        self.log.append(("GetIDsOfNames", name))
        if name not in self.ids:
            raise fk.make_com_error(0x80020006)  # DISP_E_UNKNOWNNAME
        return self.ids[name]

    def Invoke(self, dispid: int, lcid: int, flags: int, result: bool, *args: Any) -> Any:  # noqa: N802
        name = next(n for n, i in self.ids.items() if i == dispid)
        self.log.append(("Invoke", name, flags, args))
        value = self.members[name]
        return value(*args) if callable(value) else value


class _CDispatch:
    """Stand-in of pywin32's dynamic ``CDispatch``: the raw interface is ``_oleobj_``."""

    def __init__(self, oleobj: PyIDispatch) -> None:
        self._oleobj_ = oleobj


class OutlookDirectDispatchTests(unittest.TestCase):
    """pywin32 objects are called through ``IDispatch::Invoke``, behind the same whitelist."""

    def setUp(self) -> None:
        patcher = mock.patch.dict(_oc()._KIND_DISPIDS, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.watchdog = _RecordingWatchdog(30).watchdog
        self.log: list = []

    def proxy(self, target, kind: str):
        return _oc().ReadOnlyCom(target, kind, self.watchdog)

    def test_properties_and_methods_use_invoke_with_dispids_looked_up_once_per_kind(self) -> None:
        oc = _oc()
        table = PyIDispatch({"GetRowCount": lambda: 7}, self.log)
        folders = [
            PyIDispatch({"Name": "A", "EntryID": "01", "GetTable": lambda *a: table}, self.log),
            PyIDispatch({"Name": "B", "EntryID": "02", "GetTable": lambda *a: table}, self.log),
        ]
        names = [self.proxy(_CDispatch(folders[0]), "Folder").Name, self.proxy(folders[1], "Folder").Name]
        self.assertEqual(names, ["A", "B"])
        proxy_table = self.proxy(folders[0], "Folder").GetTable("", 0)
        self.assertIsInstance(proxy_table, oc.ReadOnlyCom)
        self.assertEqual(proxy_table.GetRowCount(), 7)
        lookups = [entry[1] for entry in self.log if entry[0] == "GetIDsOfNames"]
        self.assertEqual(lookups, ["Name", "GetTable", "GetRowCount"])
        invokes = [entry[1:] for entry in self.log if entry[0] == "Invoke"]
        self.assertEqual(
            invokes,
            [
                ("Name", oc.DISPATCH_PROPERTYGET, ()),
                ("Name", oc.DISPATCH_PROPERTYGET, ()),
                ("GetTable", oc.DISPATCH_METHOD | oc.DISPATCH_PROPERTYGET, ("", 0)),
                ("GetRowCount", oc.DISPATCH_METHOD | oc.DISPATCH_PROPERTYGET, ()),
            ],
        )

    def test_items_look_dispids_up_per_object_and_unknown_names_are_attribute_errors(self) -> None:
        mail = PyIDispatch({"MessageClass": "IPM.Note", "HTMLBody": "<p>x</p>"}, self.log)
        meeting = PyIDispatch({"MessageClass": "IPM.Schedule.Meeting.Request"}, self.log)
        self.assertEqual(self.proxy(mail, "Item").MessageClass, "IPM.Note")
        self.assertEqual(self.proxy(meeting, "Item").MessageClass, "IPM.Schedule.Meeting.Request")
        with self.assertRaises(AttributeError):
            self.proxy(meeting, "Item").HTMLBody
        lookups = [entry[1] for entry in self.log if entry[0] == "GetIDsOfNames"]
        self.assertEqual(lookups, ["MessageClass", "MessageClass", "HTMLBody"])

    def test_the_whitelist_is_checked_before_any_call(self) -> None:
        from mailquery.errors import MailqueryError

        item = PyIDispatch({"Delete": lambda: None, "UnRead": True}, self.log)
        for member in ("Delete", "UnRead", "_oleobj_"):
            with self.subTest(member=member), self.assertRaises(MailqueryError) as caught:
                getattr(self.proxy(item, "Item"), member)
            self.assertEqual(caught.exception.code, "E_INTERNAL")
        with self.assertRaises(MailqueryError):
            self.proxy(item, "Item").UnRead = False
        self.assertEqual(self.log, [])

    def test_com_errors_of_invoke_are_mapped_like_dynamic_dispatch(self) -> None:
        oc = _oc()

        def fail(*_args):
            raise fk.make_com_error(fk.MAPI_E_NOT_FOUND, wrapped=True)

        accessor = PyIDispatch({"GetProperty": fail}, self.log)
        with self.assertRaises(oc.ComCallError) as caught:
            self.proxy(accessor, "PropertyAccessor").GetProperty("x")
        self.assertEqual(caught.exception.hresult, oc.MAPI_E_NOT_FOUND)


class FakeBulkTableTests(unittest.TestCase):
    def test_get_array_returns_rows_in_chunks_then_an_empty_tuple(self) -> None:
        fake = fk.FakeOutlook.default()
        inbox = _stores(fake)["exchange"].GetDefaultFolder(fk.OL_FOLDER_INBOX)
        table = inbox.GetTable("", fk.OL_USER_ITEMS)
        table.Columns.Add(fk.PR_LONGTERM_ENTRYID_FROM_TABLE)
        first, second, third = table.GetArray(2), table.GetArray(2), table.GetArray(2)
        self.assertIsInstance(first, list)
        self.assertEqual([len(first), len(second)], [2, 1])
        self.assertEqual(third, ())
        self.assertTrue(table.EndOfTable)
        reference = inbox.GetTable("", fk.OL_USER_ITEMS)
        reference.Columns.Add(fk.PR_LONGTERM_ENTRYID_FROM_TABLE)
        rows = []
        while not reference.EndOfTable:
            rows.append(reference.GetNextRow().GetValues())
        self.assertEqual(first + second, rows)

    def test_class_and_status_restrictions(self) -> None:
        fake = _counter_profile()
        inbox = _stores(fake)["exchange"].GetDefaultFolder(fk.OL_FOLDER_INBOX)
        mc, status = fk.PR_MESSAGE_CLASS, fk.PR_MSG_STATUS

        def count(text: str) -> int:
            return inbox.GetTable("@SQL=" + text, fk.OL_USER_ITEMS).GetRowCount()

        self.assertEqual(count(f"\"{mc}\" = 'ipm.note'"), 8)  # case-insensitive equality
        self.assertEqual(count(f"\"{mc}\" LIKE 'IPM.Note.%'"), 1)  # prefix, not IPM.NoteBook
        self.assertEqual(count(f"\"{mc}\" LIKE 'IPM.Note%'"), 10)
        self.assertEqual(count(f"NOT (\"{mc}\" = 'IPM.Note') AND \"{status}\" < 8"), 4)
        self.assertEqual(count(f"\"{status}\" >= 8 OR \"{mc}\" <> 'IPM.Note'"), 6)
        for unsupported in (
            f"\"{fk.PR_SUBJECT}\" = 'x'",
            f"\"{status}\" >= 'x'",
            f"\"{mc}\" > 'IPM'",
            f"(\"{mc}\" = 'IPM.Note'",
        ):
            with self.subTest(filter=unsupported), self.assertRaises(fk.FakeFilterError):
                count(unsupported)


class OutlookInternalErrorLogTests(_CommandScenarioCase):
    def test_com_internal_error_is_logged_with_traceback(self) -> None:
        """PRD 14: an E_INTERNAL from COM logs its traceback; other COM errors do not."""
        fake = self.use(fk.FakeOutlook.default(), _scope_toml("ana.perez@example.com"))
        log_path = self.home / "logs" / "mailquery.log"
        fake.fail_next(fk.E_UNEXPECTED, kind="Folder", member="GetTable", wrapped=True)
        code, payload = self.run_any("search")
        self.assertEqual((code, payload["error"]["code"]), (1, "E_INTERNAL"))
        log = log_path.read_text(encoding="utf-8")
        self.assertIn("code=E_INTERNAL", log)
        self.assertIn("Traceback (most recent call last):", log)
        self.assertIn("ComCallError", log)
        self.assertNotIn(fake.item("normal").entry_id, log)
        fake.fail_next(fk.E_ACCESSDENIED, kind="Folder", member="GetTable")
        code, payload = self.run_any("search")
        self.assertEqual((code, payload["error"]["code"]), (3, "E_PERMISSION"))
        log = log_path.read_text(encoding="utf-8")[len(log):]
        self.assertIn("code=E_PERMISSION", log)
        self.assertNotIn("Traceback", log)


class OutlookReadOnlyGateTests(_CommandScenarioCase):
    """OL-30 (full sweep, W4-T04): the 5 commands with all their flags, over every scenario.

    `mailboxes`; `search` with every filter, including `--text`, `--to` and
    `--cc` (bounded, combined and one unbounded: E_UNBOUNDED_SCAN); `new` with
    and without `--peek`/`--limit` (first and later runs); `show` of every item
    and of malformed uids; `doctor` (text report and `--json`).
    """

    _SCOPES = {
        "default": _scope_toml("ana.perez@example.com", "Exchange shared (Soporte)"),
        "store_matrix": _matrix_candidate_scope()
        + _scope_toml("Exchange shared (Soporte)", "PST (Archivo 2019)", "Buzón remoto"),
        "folder_matrix": '[scope."lucia@example.es"]\nmailbox_list = ["INBOX/Facturas", "Clientes%2FProveedores"]\n'
        '[scope."jonas@example.de"]\n',
        "item_matrix": _ITEM_SCOPE,
    }
    _SEARCHES = (
        (),
        ("--since", "2026-01-01"),
        ("--since", "30d", "--until", "now"),
        ("--unread",),
        ("--flagged",),
        ("--has-attachments",),
        ("--from", "*example*"),
        ("--subject", "*a*"),
        ("--include-mailbox", "INBOX", "--limit", "1"),
        ("--since", "2026-01-01", "--limit", "2", "--unread", "--has-attachments"),
        ("--text", "*o*", "--since", "2026-01-01"),
        ("--text", "cuerpo", "--include-mailbox", "INBOX"),
        ("--to", "*example*", "--since", "2026-01-01"),
        ("--cc", "*example*", "--since", "30d"),
        ("--to", "ana", "--cc", "copia", "--subject", "*"),
        (
            "--text", "*e*", "--to", "*@*", "--cc", "*", "--from", "*example*",
            "--subject", "*", "--since", "2026-01-01", "--until", "now", "--unread",
            "--flagged", "--has-attachments", "--include-mailbox", "INBOX", "--limit", "5",
        ),
        ("--to", "*example*"),  # unbounded on Windows: E_UNBOUNDED_SCAN (exit 4)
    )
    _NEWS = (
        ("--peek",),
        ("--peek", "--limit", "1"),
        (),
        ("--limit", "2"),
        (),
    )
    _DOCTORS = (("--json",), ())
    #: Exit codes a read-only run may end with, and the error codes of each
    #: (M10 adds the attachment protocol codes; a read-only run never mutates).
    _ERRORS = {
        2: ("E_USAGE", "E_ACCOUNT_NOT_IN_SCOPE"),
        3: (
            "E_ATTACHMENT_UNAVAILABLE",
            "E_ATTACHMENT_UNREADABLE",
            "E_PERMISSION",
            "E_CLIENT_BUSY",
            "E_CLIENT_TIMEOUT",
        ),
        4: ("E_UNBOUNDED_SCAN", "E_ATTACHMENT_BLOCKED", "E_ATTACHMENT_TOO_LARGE"),
    }

    def run_report(self, *argv: str) -> tuple[int, dict]:
        """`doctor` without `--json`: the text report, kept under ``report``."""
        backend = _backend(self.fake)
        self.addCleanup(backend.close)
        code, stdout, stderr = self.run_main(list(argv), backend)
        self.assertTrue(stdout.startswith("mailquery doctor - "), stdout + stderr)
        return code, {"report": stdout, "stderr": stderr}

    def sweep(self) -> list[tuple[fk.FakeOutlook, list[tuple[tuple[str, ...], int, dict]]]]:
        """Every command over every fake scenario: ``[(fake, [(argv, exit, payload)])]``."""
        results = []
        for name, scope in self._SCOPES.items():
            fake = self.use(fk.SCENARIOS[name](), scope)
            (self.home / "state.json").unlink(missing_ok=True)  # each scenario starts afresh
            runs: list[tuple[str, ...]] = [("mailboxes",)]
            runs += [("search", *flags) for flags in self._SEARCHES]
            runs += [("new", *flags) for flags in self._NEWS]
            runs += [("show", spec.entry_id) for spec in fake.items.values()]
            runs += [("show", "00AB"), ("show", "ab12")]
            attachment_items = [
                spec for spec in fake.items.values() if spec.attachments
            ] or list(fake.items.values())
            if attachment_items:
                attachment_uid = attachment_items[0].entry_id
                runs += [
                    ("attachment", attachment_uid, "--index", "1"),
                    ("attachment", attachment_uid, "--all"),
                    ("attachment", attachment_uid, "--index", "1", "--force"),
                ]
            runs += [("attachment", "00AB", "--index", "1")]
            runs += [("attachment", "ab12", "--index", "1")]
            runs += [("doctor", *flags) for flags in self._DOCTORS]
            outcomes = [
                (argv, *(self.run_report(*argv) if argv == ("doctor",) else self.run_any(*argv)))
                for argv in runs
            ]
            results.append((fake, outcomes))
        return results

    @classmethod
    def setUpClass(cls) -> None:
        cls._cached = None

    def results(self):
        if type(self)._cached is None:
            type(self)._cached = self.sweep()
        return type(self)._cached

    def test_ol_30_01_invoked_members_are_whitelisted(self) -> None:
        """OL-30.01: every member read or invoked is in the read-only whitelist."""
        for fake, outcomes in self.results():
            self.assertGreater(len(outcomes), 10)
            invoked = {
                (entry.kind, entry.member)
                for entry in fake.call_log
                if entry.kind != "Connector"
            }
            outside = {
                (kind, member) for kind, member in invoked
                if member not in fk.OOM_MEMBERS.get(kind, {})
            }
            self.assertEqual(outside, set())
            self.assertEqual(
                {entry.member for entry in fake.call_log if entry.kind == "Connector"},
                {"GetActiveObject"},
            )
            self.assertEqual({entry.action for entry in fake.call_log}, {"get", "call"})

        # The sweep reaches the content members (--text, --to/--cc, new and show).
        reached = set().union(*(fake.call_log.members() for fake, _outcomes in self.results()))
        self.assertTrue(
            {("Item", "Body"), ("Item", "Recipients"), ("NameSpace", "GetItemFromID")} <= reached
        )

    def test_ol_30_02_no_assignment(self) -> None:
        """OL-30.02: no property is ever assigned."""
        for fake, _outcomes in self.results():
            self.assertEqual(fake.mutations.assignments, 0)
            self.assertEqual(fake.call_log.count(action="set"), 0)

    def test_ol_30_03_no_mutation(self) -> None:
        """OL-30.03: no forbidden (mutating) member is touched."""
        for fake, _outcomes in self.results():
            self.assertEqual(fake.mutations.total, 0, fake.mutations.events)
            self.assertEqual(fake.call_log.count(action="forbidden"), 0)

    def test_ol_30_05_attachment_writes_stay_under_home_and_clean_staging(self) -> None:
        """OL-30.05: attachment runs write only under ``<home>`` and leave staging clean (M10)."""
        # Run the sweep first so the assertions see every attachment invocation.
        self.results()
        staging = self.home / "tmp" / "staging"
        leftovers = list(staging.iterdir()) if staging.is_dir() else []
        self.assertEqual(leftovers, [], f"staging leftovers: {leftovers}")
        # Every path under the test root belongs to the app home (no file leaks).
        for path in self.root.rglob("*"):
            self.assertTrue(path == self.home or self.home in path.parents, path)

    def test_ol_30_04_never_the_codes_annex_b7_excludes(self) -> None:
        """OL-30.04: no error or warning that annex B.7 excludes from this backend; no E_INTERNAL."""
        for _fake, outcomes in self.results():
            commands = {argv[0] for argv, _code, _payload in outcomes}
            self.assertEqual(
                commands,
                {"mailboxes", "search", "new", "show", "attachment", "doctor"},
            )
            for argv, code, payload in outcomes:
                with self.subTest(argv=argv):
                    if argv[0] in ("doctor", "mailboxes", "new"):
                        self.assertEqual(code, 0, payload)
                    self.assertIn(code, (0, *self._ERRORS), payload)
                    text = json.dumps(payload, ensure_ascii=False)
                    for foreign in _FOREIGN_CODES:
                        self.assertNotIn(foreign, text)
                    self.assertNotIn("E_INTERNAL", text)
                    if code != 0:
                        self.assertIn(payload["error"]["code"], self._ERRORS[code])


# --------------------------------------------------------------------------- #
# OL-18, OL-25 — `new` on Windows and searchable items (W4-T01)
# --------------------------------------------------------------------------- #

_FIRST_RUN = (
    "W_FIRST_RUN: first run: emitted the messages received in the last 10min "
    "before the newest message"
)
def _uid(entry_id: str) -> str:
    """The prefixed uid the core emits for an Outlook EntryID (test helper)."""
    return prefixed_uid(entry_id, "outlook")


def _all_installed(driver: str) -> bool:
    """``state.json`` driver check for the Outlook tests (built-ins are installed)."""
    return bool(driver)


_HEX_UID = r"^outlook:[0-9A-F]+$"


def _epoch(moment: datetime) -> int:
    return int(moment.timestamp())


class _NewCase(_CommandScenarioCase):
    """`new` through ``cli.main`` over the fake; one fresh backend per run."""

    def new(self, *extra: str) -> dict:
        return self.run_json("new", *extra)

    def state(self) -> dict:
        return json.loads((self.home / "state.json").read_text(encoding="utf-8"))

    def seed_cursor(self, moment: datetime) -> None:
        """A saved cursor at ``moment`` (later runs emit everything received since then)."""
        payload = {
            "schema": 1,
            "cursor": {"last_date_received": _epoch(moment), "last_uid": "00", "lookback_seconds": 600},
            "emitted_uids": [],
        }
        (self.home / "state.json").write_text(json.dumps(payload), encoding="utf-8")

    def uids(self, payload: dict) -> list[str]:
        return [message["uid"] for message in payload["messages"]]


class OutlookSearchableItemTests(_NewCase):
    """OL-18 (annex B.4): which items `search`, `new` and `show` see."""

    def appearances(self, *keys: str) -> dict[str, tuple[bool, bool, int]]:
        """``key -> (in search, in new, exit code of show)`` over the item matrix."""
        fake = self.items()
        self.seed_cursor(datetime(2026, 1, 1, tzinfo=timezone.utc))
        searched = set(self.uids(self.search()))
        emitted = set(self.uids(self.new("--limit", "500")))
        self.assertGreater(len(emitted), 10)
        out: dict[str, tuple[bool, bool, int]] = {}
        for key in keys:
            uid = fake.item(key).entry_id
            backend = _backend(fake)
            self.addCleanup(backend.close)
            code, stdout, stderr = self.run_main(["show", uid], backend)
            payload = json.loads(stdout)
            if code == 0:
                self.assertEqual(payload["message"]["uid"], _uid(uid))
            else:
                self.assertEqual(payload["error"]["code"], "E_USAGE", stdout + stderr)
                self.assertIn("was not found", payload["error"]["message"])
            out[key] = (_uid(uid) in searched, _uid(uid) in emitted, code)
        self.assert_read_only()
        return out

    def test_ol_18_01_receipt_and_task_are_ignored(self) -> None:
        """OL-18.01: a delivery receipt and a task ⇒ ignored in `search`, `new` and `show`."""
        found = self.appearances("delivery_receipt", "task")
        self.assertEqual(found, {"delivery_receipt": (False, False, 2), "task": (False, False, 2)})

    def test_ol_18_02_imap_deleted_is_ignored(self) -> None:
        """OL-18.02: an IMAP-deleted item ⇒ ignored in `search`, `new` and `show`."""
        self.assertEqual(self.appearances("imap_deleted"), {"imap_deleted": (False, False, 2)})

    def test_ol_18_03_meeting_request_and_smime_are_included(self) -> None:
        """OL-18.03: a meeting request and S/MIME (encrypted and signed) ⇒ included everywhere."""
        keys = ("meeting_request", "smime_encrypted", "smime_signed")
        self.assertEqual(self.appearances(*keys), {key: (True, True, 0) for key in keys})


class OutlookNewTests(_NewCase):
    """OL-25 (PRD 11.2, 12.3, 18): `new` with hexadecimal uids."""

    _SCOPE = _scope_toml("ana.perez@example.com")
    _SHARED = _store_excluded("Exchange shared (Soporte)", None, "shared_mailbox")
    _NORMAL_DATE = _epoch(datetime(2026, 11, 2, 13, 54, 9, tzinfo=timezone.utc))

    def test_ol_25_01_state_keeps_hex_uids(self) -> None:
        """OL-25.01: the state stores the hexadecimal uids (string) in the cursor and the ring."""
        from mailquery.backends.outlook import OutlookBackend
        from mailquery.state import Cursor, StateStore

        fake = self.use(fk.FakeOutlook.default(), self._SCOPE)
        uid = fake.item("normal").entry_id
        peeked = self.new("--peek")
        self.assertEqual(self.uids(peeked), [_uid(uid)])
        self.assertEqual(peeked["cursor"], {"previous": None, "current": None})
        self.assertFalse((self.home / "state.json").exists())

        payload = self.new()
        self.assertEqual(self.uids(payload), [_uid(uid)])
        self.assertEqual(payload["warnings"], [_FIRST_RUN])
        cursor = {
            "last_date_received": self._NORMAL_DATE,
            "last_uid": _uid(uid),
            "lookback_seconds": 600,
        }
        self.assertEqual(payload["cursor"], {"previous": None, "current": cursor})
        state = self.state()
        self.assertEqual(state["cursor"], cursor)
        self.assertEqual(state["emitted_uids"], [_uid(uid)])
        self.assertIsInstance(state["cursor"]["last_uid"], str)
        self.assertRegex(state["cursor"]["last_uid"], _HEX_UID)
        loaded = StateStore(self.home, _all_installed).load()
        self.assertEqual(loaded.cursor, Cursor(self._NORMAL_DATE, _uid(uid), 600))
        self.assertEqual(loaded.emitted_uids, (_uid(uid),))
        self.assert_read_only()

    def test_ol_25_02_second_run_does_not_re_emit(self) -> None:
        """OL-25.02: a second run does not re-emit what the first one emitted (ring + cursor)."""
        fake = self.use(fk.FakeOutlook.default(), self._SCOPE)
        first = self.new()
        normal = fake.item("normal").entry_id
        self.assertEqual(self.uids(first), [_uid(normal)])
        # One message arrives inside the lookback window of the saved cursor.
        later = fake.store("exchange").inbox.add_message(
            "later",
            subject="Recordatorio",
            sender=("Proveedor SA", "facturas@proveedor.example"),
            received=datetime(2026, 11, 2, 13, 58, 0, tzinfo=timezone.utc),
        )
        second = self.new()
        self.assertEqual(self.uids(second), [_uid(later.entry_id)])
        self.assertEqual(second["warnings"], [])
        self.assertEqual(second["cursor"]["previous"], first["cursor"]["current"])
        third = self.new()
        self.assertEqual(third["count"], 0)
        self.assertEqual(third["cursor"]["previous"], third["cursor"]["current"])
        self.assertEqual(self.state()["emitted_uids"], [_uid(normal), _uid(later.entry_id)])
        self.assertEqual(self.state()["cursor"]["last_uid"], _uid(later.entry_id))

    def test_ol_25_03_moved_message_is_emitted_with_its_new_uid(self) -> None:
        """OL-25.03: a message moved inside the window ⇒ exit 0 and emitted once with its new uid (PRD 18)."""
        fake = fk.FakeOutlook.default()
        archive = fake.store("exchange").inbox.add_folder("Archivo", key="archivo")
        self.use(fake, self._SCOPE + 'mailbox_list = ["INBOX/Archivo"]\n')
        old_uid = fake.item("normal").entry_id
        self.assertEqual(self.uids(self.new()), [_uid(old_uid)])
        new_uid = fake.move_item("normal", archive).entry_id
        self.assertNotEqual(new_uid, old_uid)
        moved = self.new()  # run_json asserts exit 0
        self.assertEqual(self.uids(moved), [_uid(new_uid)])
        self.assertEqual(moved["messages"][0]["mailbox"]["path"], "INBOX/Archivo")
        self.assertEqual(moved["messages"][0]["message_id"], "<factura-2026-10@proveedor.example>")
        state = self.state()
        self.assertEqual(state["emitted_uids"], [_uid(old_uid), _uid(new_uid)])
        self.assertEqual(state["cursor"]["last_date_received"], self._NORMAL_DATE)
        self.assertEqual(self.new()["count"], 0)

    def test_ol_25_04_declared_excluded_account_warns_before_first_run(self) -> None:
        """OL-25.04: a declared excluded account ⇒ W_STORE_EXCLUDED before W_FIRST_RUN."""
        fake = self.use(
            fk.FakeOutlook.default(), _scope_toml("ana.perez@example.com", "Exchange shared (Soporte)")
        )
        payload = self.new()
        self.assertEqual(self.uids(payload), [_uid(fake.item("normal").entry_id)])
        self.assertEqual(payload["warnings"], [self._SHARED, _FIRST_RUN])
        # Only the excluded account declared: no accounts left, nothing emitted nor saved.
        (self.home / "state.json").unlink()
        self.use(fk.FakeOutlook.default(), _scope_toml("Exchange shared (Soporte)"))
        payload = self.new()
        self.assertEqual(payload["count"], 0)
        self.assertEqual(payload["warnings"], [_NO_ACCOUNTS, self._SHARED, _FIRST_RUN])
        self.assertFalse((self.home / "state.json").exists())

    def test_new_core_with_string_uids_injected_clock_and_limit(self) -> None:
        """`search.run_new` over Outlook: injected clock (future dates) and --limit with hex uids."""
        from mailquery.config import load_config
        from mailquery.search import run_new
        from mailquery.state import StateStore

        fake = self.use(fk.FakeOutlook.default(), self._SCOPE)
        inbox = fake.store("exchange").inbox
        recent = inbox.add_message(
            "recent", subject="Reciente", sender=("A", "a@example.com"),
            received=datetime(2026, 11, 2, 13, 58, 0, tzinfo=timezone.utc),
        )
        future = inbox.add_message(
            "future", subject="Futuro", sender=("B", "b@example.com"),
            received=datetime(2026, 11, 2, 14, 10, 0, tzinfo=timezone.utc),
        )
        normal = fake.item("normal").entry_id
        clock = _epoch(datetime(2026, 11, 2, 14, 0, 0, tzinfo=timezone.utc))

        def run(now: int, **kwargs) -> dict:
            backend = _backend(fake)
            self.addCleanup(backend.close)
            store = StateStore(self.home, _all_installed)
            return run_new(backend, load_config(self.home), store, clock=lambda: now, **kwargs)

        first = run(clock, limit=1)  # the future message is not the newest one
        self.assertEqual(self.uids(first), [_uid(recent.entry_id)])
        self.assertTrue(first["truncated"])
        self.assertEqual(first["cursor"]["current"]["last_uid"], _uid(recent.entry_id))
        # Once its date is no longer future it enters, with what --limit left out.
        second = run(clock + 3600)
        self.assertEqual(self.uids(second), [_uid(normal), _uid(future.entry_id)])
        self.assertEqual(self.state()["emitted_uids"], [_uid(recent.entry_id), _uid(normal), _uid(future.entry_id)])
        self.assertEqual(run(clock + 3600)["count"], 0)
        self.assert_read_only()


# --------------------------------------------------------------------------- #
# OL-24 — `--text`, `--to` and `--cc` on Windows (W4-T02)
# --------------------------------------------------------------------------- #

_ANA = ("Ana", "ana@example.com")
_BEA = ("Bea Ruiz", "bea@example.com")
_NARROWING = ("--since", "--until", "--from", "--subject", "--include-mailbox")


class OutlookContentScanTests(_CommandScenarioCase):
    """OL-24 (PRD RF-17, 9.5; annex B.4): bounded `--text`, `--to` and `--cc` on Windows."""

    _SCOPE = _scope_toml("ana@example.com")  # INBOX only: no narrowing folder

    def recent(self) -> fk.FakeOutlook:
        """Six INBOX items received in the last hours (one per body state) and an old one."""
        fake = fk.FakeOutlook()
        inbox = fake.add_exchange_account("exchange", "ana@example.com").inbox
        assert inbox is not None
        now = datetime.now(timezone.utc).replace(microsecond=0)

        def add(key: str, hours: int, **fields) -> None:
            fields.setdefault("sender", ("Proveedor", "ventas@proveedor.example"))
            fields.setdefault("to", [_ANA])
            inbox.add_message(key, subject=key, received=now - timedelta(hours=hours), **fields)

        add("to_bea", 1, to=[_BEA], body="Adjunto el presupuesto anual.\r\n")
        add("cc_bea", 2, cc=[_BEA], body="El presupuesto va en copia.\r\n")
        add("other", 3, body="", html="<p>Sin relación.</p>")
        add("smime_to_bea", 4, to=[_BEA], message_class="IPM.Note.SMIME",
            attachments=[fk.AttachmentSpec("smime.p7m")])
        add("header_only_to_bea", 5, to=[_BEA], download_state=fk.OL_HEADER_ONLY)
        add("unopenable_to_bea", 6, to=[_BEA], openable=False, body="presupuesto")
        add("old_to_bea", 24 * 40, to=[_BEA], body="presupuesto antiguo")
        return self.use(fake, self._SCOPE)

    def opened(self) -> list[str]:
        """Uid of every ``GetItemFromID`` call, in call order."""
        return [
            entry.args[0] for entry in self.fake.call_log
            if (entry.kind, entry.member, entry.action) == ("NameSpace", "GetItemFromID", "call")
        ]

    def keys(self, payload: dict) -> list[str]:
        by_uid = {_uid(spec.entry_id): key for key, spec in self.fake.items.items()}
        return [by_uid[message["uid"]] for message in payload["messages"]]

    def header_reads(self) -> int:
        return sum(
            1 for entry in self.fake.call_log
            if (entry.kind, entry.member) == ("PropertyAccessor", "GetProperty")
            and entry.args and str(entry.args[0]).upper().endswith("007D001F")
        )

    def assert_unbounded(self, *argv: str) -> dict:
        backend = _backend(self.fake)
        self.addCleanup(backend.close)
        code, stdout, stderr = self.run_main(["search", *argv], backend)
        error = self.assert_error((code, stdout, stderr), 4, "E_UNBOUNDED_SCAN")
        self.assertEqual(stderr.count("E_UNBOUNDED_SCAN"), 1, stderr)
        for option in _NARROWING:
            self.assertIn(option, error["hint"])
        self.assertNotIn("--to", error["hint"])
        self.assertNotIn("--cc", error["hint"])
        self.assertEqual(self.opened(), [])
        return error

    def test_ol_24_01_to_without_narrowing_is_unbounded(self) -> None:
        """OL-24.01: --to x without a narrowing filter ⇒ E_UNBOUNDED_SCAN naming --to; hint without --to/--cc."""
        self.recent()
        error = self.assert_unbounded("--to", "bea")
        self.assertIn("--to", error["message"])
        self.assertNotIn("--text", error["message"])
        error = self.assert_unbounded("--cc", "bea", "--include-mailbox", "INBOX")
        self.assertIn("--cc", error["message"])
        self.assertNotIn("--to", error["message"])

    def test_ol_24_02_text_without_narrowing_is_unbounded(self) -> None:
        """OL-24.02: --text x without a narrowing filter ⇒ E_UNBOUNDED_SCAN; hint without --to/--cc."""
        self.recent()
        error = self.assert_unbounded("--text", "presupuesto")
        self.assertIn("--text", error["message"])

    def test_ol_24_03_text_with_to_is_one_validation_and_one_error(self) -> None:
        """OL-24.03: --text x --to y ⇒ --to does not narrow; one validation, one error."""
        self.recent()
        error = self.assert_unbounded("--text", "presupuesto", "--to", "bea")
        self.assertIn("--text", error["message"])
        self.assertIn("--to", error["message"])

    def test_ol_24_04_to_above_max_scan_is_scan_too_large(self) -> None:
        """OL-24.04: --to x --since 1y with more candidates than max_scan ⇒ E_SCAN_TOO_LARGE."""
        fake = fk.FakeOutlook()
        inbox = fake.add_exchange_account("exchange", "ana@example.com").inbox
        assert inbox is not None
        now = datetime.now(timezone.utc).replace(microsecond=0)
        for index in range(101):
            inbox.add_message(
                f"m{index}", subject=f"m{index}", sender=_ANA, to=[_BEA],
                received=now - timedelta(days=index + 1),
            )
        self.use(fake, self._SCOPE + "[search]\nmax_scan = 100\n")
        error = self.run_error(4, "E_SCAN_TOO_LARGE", "search", "--to", "bea", "--since", "1y")
        self.assertIn("--to", error["message"])
        self.assertIn("101", error["message"])
        self.assertNotIn("--to", error["hint"])
        self.assertNotIn("--cc", error["hint"])
        self.assertEqual(self.opened(), [])
        # Narrowed by --subject (which does narrow) below max_scan, the same query runs.
        payload = self.run_json("search", "--to", "bea", "--since", "1y", "--subject", "m1*")
        self.assertEqual(payload["scan"]["candidates"], 12)  # m1, m10..m19, m100

    def test_ol_24_05_to_runs_in_metadata_mode_counting_opened_items(self) -> None:
        """OL-24.05: --to x --since 1d ⇒ runs; mode metadata; candidates before --to; messages_read = items opened."""
        fake = self.recent()
        payload = self.run_json("search", "--to", "bea", "--since", "1d")
        self.assertEqual(self.keys(payload), ["to_bea", "smime_to_bea", "header_only_to_bea"])
        self.assertEqual(payload["scan"]["mode"], "metadata")
        self.assertEqual(payload["scan"]["candidates"], 6)
        # Every candidate is opened once; the unopenable one is not counted as opened.
        recent = [key for key in fake.items if key != "old_to_bea"]
        self.assertCountEqual(self.opened(), [fake.item(key).entry_id for key in recent])
        self.assertEqual(payload["scan"]["messages_read"], 5)
        self.assertEqual(self.header_reads(), 0)
        self.assert_read_only()

    def test_ol_24_06_bounded_text_matches_bodies(self) -> None:
        """OL-24.06: bounded --text ⇒ matches in the body; scan.mode text; skipped bodies warn."""
        fake = self.recent()
        payload = self.run_json("search", "--text", "presupuesto", "--since", "1d")
        self.assertEqual(self.keys(payload), ["to_bea", "cc_bea"])
        self.assertEqual(payload["scan"]["mode"], "text")
        self.assertEqual(payload["scan"]["candidates"], 6)
        self.assertIn("presupuesto anual", payload["messages"][0]["snippet"])
        codes = [warning.split(":")[0] for warning in payload["warnings"]]
        self.assertEqual(codes, ["W_BODY_UNREADABLE", "W_BODY_NOT_LOCAL", "W_BODY_UNREADABLE"])
        self.assertIn("S/MIME", payload["warnings"][0])
        # S/MIME is never opened; each other item at most once; no transport headers.
        opened = self.opened()
        self.assertNotIn(fake.item("smime_to_bea").entry_id, opened)
        self.assertEqual(len(opened), len(set(opened)))
        self.assertEqual(len(opened), 5)
        self.assertEqual(payload["scan"]["messages_read"], 4)
        self.assertEqual(self.header_reads(), 0)
        self.assertNotIn(("Item", "Attachments"), fake.call_log.members())
        self.assert_read_only()

    def test_ol_24_07_text_with_to_counts_candidates_before_to(self) -> None:
        """OL-24.07: --text x --to y --since 1d ⇒ scan.candidates = messages before --to."""
        fake = self.recent()
        payload = self.run_json("search", "--text", "presupuesto", "--to", "bea", "--since", "1d")
        self.assertEqual(self.keys(payload), ["to_bea"])
        self.assertEqual(payload["scan"]["mode"], "text")
        self.assertEqual(payload["scan"]["candidates"], 6)
        opened = self.opened()
        self.assertEqual(len(opened), len(set(opened)))
        self.assertEqual(len(opened), 6)
        self.assertEqual(payload["scan"]["messages_read"], 5)
        self.assertEqual(self.header_reads(), 0)
        self.assert_read_only()


# --------------------------------------------------------------------------- #
# OL-26 — doctor on Windows (PRD 12.8, annex B.8, PRD 15.3)
# --------------------------------------------------------------------------- #


class OutlookDoctorTests(_OutlookCommandCase):
    def doctor(self, fake: fk.FakeOutlook, scope: str | None = None, **overrides) -> dict:
        """`doctor --json` over ``fake`` (exit 0); returns the checks by name."""
        self.use(fake, scope if scope is not None else "")
        if scope is None:
            (self.home / "config.toml").unlink()
        backend = _backend(fake, **overrides)
        self.addCleanup(backend.close)
        code, stdout, stderr = self.run_main(["doctor", "--json"], backend)
        self.assertEqual(code, 0, stdout + stderr)
        payload = json.loads(stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual([check["name"] for check in payload["checks"]], list(_OUTLOOK_DOCTOR_CHECKS))
        self.assertEqual(fake.mutations.total, 0)
        self.assertFalse(fake.call_log.members() & {("Connector", name) for name in _DISPATCH_NAMES})
        return {check["name"]: check for check in payload["checks"]}

    def test_doctor_all_checks_pass_on_the_default_profile(self) -> None:
        """Annex B.8: every check of the default profile passes; the strategy is com_readonly."""
        checks = self.doctor(fk.FakeOutlook.default(), _scope_toml("ana.perez@example.com"))
        for name, check in checks.items():
            with self.subTest(check=name):
                self.assertTrue(check["ok"], check)
        self.assertTrue(checks["readonly_strategy"]["detail"].startswith("com_readonly: "))
        self.assertIn(fk.DEFAULT_VERSION, checks["outlook"]["detail"])
        self.assertTrue(
            checks["config"]["detail"].startswith(
                "ana.perez@example.com → Exchange (ana.perez@example.com) ("
            )
        )

    def test_doctor_stores_lists_candidates_and_excluded_stores(self) -> None:
        """Annex B.8 / RF-34: `stores` lists candidates (label, type) and excluded (label, path, reason)."""
        checks = self.doctor(fk.FakeOutlook.store_matrix())
        detail = checks["stores"]["detail"]
        self.assertTrue(checks["stores"]["ok"])
        for label, _email, _local in _MATRIX_CANDIDATES.values():
            kind = label.split(" ", 1)[0]
            self.assertIn(f"{label} [{kind}]", detail)
        self.assertIn(
            "PST (Archivo 2019) at \\\\nas01\\backup\\archivo2019.pst [network_path]", detail
        )
        self.assertIn("Exchange shared (Soporte) [shared_mailbox]", detail)

    def test_ol_26_01_pywin32_failure_leaves_dependents_not_evaluated(self) -> None:
        """OL-26.01: pywin32 fails ⇒ outlook, stores, readonly_strategy and config resolution not evaluated."""
        fake = fk.FakeOutlook.default()
        checks = self.doctor(fake, _scope_toml("ana.perez@example.com"), pywin32=False)
        self.assertFalse(checks["pywin32"]["ok"])
        self.assertIn("E_DEPENDENCY_MISSING", checks["pywin32"]["detail"])
        self.assertEqual(checks["outlook"], {"name": "outlook", "ok": False, "detail": "not evaluated: pywin32 failed"})
        for name in ("stores", "readonly_strategy"):
            self.assertEqual(checks[name]["detail"], "not evaluated: outlook failed")
            self.assertFalse(checks[name]["ok"])
        self.assertEqual(checks["config"]["detail"], "not evaluated: stores failed")
        self.assertFalse(checks["config"]["ok"])
        for name in ("python", "home", "object_model_guard", "state", "lock"):
            self.assertTrue(checks[name]["ok"], checks[name])
        self.assertEqual(len(fake.call_log), 0)  # Outlook was never contacted

    def test_ol_26_02_outlook_closed_fails_outlook_and_exits_0(self) -> None:
        """OL-26.02: Outlook closed ⇒ outlook ok=false (never launched), exit 0, text report too."""
        fake = run_cli.build_fake("not_running")
        checks = self.doctor(fake)
        self.assertFalse(checks["outlook"]["ok"])
        self.assertIn("E_OUTLOOK_NOT_RUNNING", checks["outlook"]["detail"])
        self.assertIn(HINT_NOT_RUNNING, checks["outlook"]["detail"])
        for name in ("stores", "readonly_strategy"):
            self.assertEqual(checks[name]["detail"], "not evaluated: outlook failed")
        self.assertEqual(
            [entry.member for entry in fake.call_log], ["GetActiveObject"]
        )
        backend = _backend(fake)
        self.addCleanup(backend.close)
        code, stdout, _stderr = self.run_main(["doctor"], backend)
        self.assertEqual(code, 0)
        self.assertIn("[FAIL] outlook", stdout)
        self.assertIn("read-only with respect to Outlook", stdout)

    def test_ol_26_03_no_blocks_and_stores_failed_is_config_ok_unknown(self) -> None:
        """OL-26.03: no blocks and stores failed ⇒ config ok=true, `available accounts: unknown (stores failed)`."""
        expected = "0 account block(s) declared; available accounts: unknown (stores failed)"
        broken = fk.FakeOutlook.default()
        broken.fail_next(fk.E_UNEXPECTED, kind="NameSpace", member="Stores")
        for label, fake in (("stores error", broken), ("outlook closed", run_cli.build_fake("not_running"))):
            with self.subTest(case=label):
                checks = self.doctor(fake)
                self.assertFalse(checks["stores"]["ok"])
                self.assertTrue(checks["config"]["ok"], checks["config"])
                self.assertEqual(checks["config"]["detail"], f"no config.toml (optional); {expected}")

    def test_ol_26_04_declared_excluded_account_warns_in_config_detail(self) -> None:
        """OL-26.04: declared excluded account ⇒ W_STORE_EXCLUDED in the config detail, still ok=true."""
        checks = self.doctor(
            fk.FakeOutlook.store_matrix(), _scope_toml("ana@example.com", "PST (Archivo 2019)")
        )
        config = checks["config"]
        self.assertTrue(config["ok"], config)
        self.assertIn("ana@example.com → Exchange (ana@example.com) (", config["detail"])
        self.assertIn(
            OutlookStoreExcludedWarningTests._UNC, config["detail"]
        )
        only_excluded = self.doctor(
            fk.FakeOutlook.default(), _scope_toml("Exchange shared (Soporte)")
        )["config"]
        self.assertTrue(only_excluded["ok"], only_excluded)
        self.assertEqual(only_excluded["detail"], OutlookStoreExcludedWarningTests._SHARED)


class OutlookNotRunningTests(_OutlookCommandCase):
    """Exit 6 end to end (PRD 12.6, 21.1; annex B.7): Outlook closed, never launched."""

    def test_exit_6_for_every_data_command_while_doctor_still_exits_0(self) -> None:
        """PRD 12.6: every data command ⇒ E_OUTLOOK_NOT_RUNNING (exit 6); doctor diagnoses it with exit 0."""
        fake = self.use(run_cli.build_fake("not_running"), _scope_toml("ana.perez@example.com"))
        uid = fake.item("normal").entry_id
        commands = (
            ("mailboxes",),
            ("search",),
            ("search", "--from", "*@example.com", "--since", "1w", "--unread"),
            ("search", "--text", "factura", "--to", "ana", "--cc", "x", "--since", "1d"),
            ("new",),
            ("new", "--peek", "--limit", "5"),
            ("show", uid),
        )
        for argv in commands:
            with self.subTest(argv=argv):
                error = self.run_error(6, "E_OUTLOOK_NOT_RUNNING", *argv)
                self.assertEqual(error["hint"], HINT_NOT_RUNNING)
        # Only GetActiveObject, once per command; nothing written for `new`.
        self.assertEqual([entry.member for entry in fake.call_log], ["GetActiveObject"] * len(commands))
        self.assertFalse((self.home / "state.json").exists())
        log = (self.home / "logs" / "mailquery.log").read_text(encoding="utf-8")
        self.assertEqual(log.count("code=E_OUTLOOK_NOT_RUNNING"), len(commands))
        # The uid format is still checked first: a malformed uid is E_USAGE (exit 2).
        self.run_error(2, "E_USAGE", "show", uid.lower())
        self.assertEqual(len(fake.call_log), len(commands))

        # doctor: outlook fails with the same error and hint, the rest is diagnosed, exit 0.
        for argv in (("doctor", "--json"), ("doctor",)):
            backend = _backend(fake)
            self.addCleanup(backend.close)
            code, stdout, stderr = self.run_main(list(argv), backend)
            with self.subTest(argv=argv):
                self.assertEqual((code, stderr), (0, ""))
                if argv == ("doctor",):
                    self.assertIn("[FAIL] outlook", stdout)
                    self.assertIn("Result: 7/11 checks passed (4 failed)", stdout)
                    continue
                checks = {check["name"]: check for check in json.loads(stdout)["checks"]}
                self.assertEqual(list(checks), list(_OUTLOOK_DOCTOR_CHECKS))
                self.assertFalse(checks["outlook"]["ok"])
                self.assertIn("E_OUTLOOK_NOT_RUNNING", checks["outlook"]["detail"])
                self.assertIn(HINT_NOT_RUNNING, checks["outlook"]["detail"])
                expected_failed = {
                    "outlook": None,
                    "stores": "not evaluated: outlook failed",
                    "readonly_strategy": "not evaluated: outlook failed",
                    "config": "not evaluated: stores failed",
                }
                for name, check in checks.items():
                    self.assertIs(check["ok"], name not in expected_failed, check)
                    if expected_failed.get(name):
                        self.assertEqual(check["detail"], expected_failed[name])
        self.assertEqual(fake.mutations.total, 0)
        self.assertFalse({entry.member for entry in fake.call_log} - {"GetActiveObject"})


# --------------------------------------------------------------------------- #
# OL-27 — object_model_guard (annex B.6); injected registry and security_center
# --------------------------------------------------------------------------- #

_POLICY_KEY = r"Software\Policies\Microsoft\Office\16.0\Outlook\Security"


class OutlookObjectModelGuardTests(unittest.TestCase):
    def guard(self, policy: dict[str, int] | None, center: fk.FakeSecurityCenter) -> dict:
        """The `object_model_guard` check with ``policy`` values under the Outlook policy key."""
        registry = fk.FakeRegistry.outlook(16)
        for name, value in (policy or {}).items():
            registry.set(fk.HKCU, _POLICY_KEY, name, value)
        fake = fk.FakeOutlook.default()
        backend = _backend(fake, registry=registry, security_center=center)
        self.addCleanup(backend.close)
        checks = {check["name"]: check for check in backend.doctor_checks()}
        self.assertEqual(
            list(checks), ["pywin32", "outlook", "stores", "readonly_strategy", "object_model_guard"]
        )
        return checks["object_model_guard"]

    @staticmethod
    def policy(**values: int) -> dict[str, int]:
        return {"AdminSecurityMode": 3, **values}

    def test_ol_27_01_policy_that_always_prompts_or_denies_fails(self) -> None:
        """OL-27.01: a policy that always prompts or denies programmatic access ⇒ fails."""
        cases = {
            "prompt": (self.policy(PromptOOMAddressInformationAccess=1), "prompt user"),
            "deny": (self.policy(PromptOOMAddressInformationAccess=0), "automatically deny"),
            "address book deny": (
                self.policy(PromptOOMAddressInformationAccess=2, PromptOOMAddressBookAccess=0),
                "automatically deny",
            ),
        }
        for label, (policy, wording) in cases.items():
            with self.subTest(case=label):
                check = self.guard(policy, fk.FakeSecurityCenter.active())
                self.assertFalse(check["ok"], check)
                self.assertIn(wording, check["detail"])

    def test_ol_27_02_policy_that_always_approves_passes(self) -> None:
        """OL-27.02: a policy that always approves ⇒ passes (even without an antivirus)."""
        check = self.guard(self.policy(PromptOOMAddressInformationAccess=2), fk.FakeSecurityCenter.none())
        self.assertTrue(check["ok"], check)
        self.assertIn("PromptOOMAddressInformationAccess=2 (automatically approve)", check["detail"])

    def test_ol_27_03_no_policy_and_active_antivirus_passes(self) -> None:
        """OL-27.03: no deciding policy and an active antivirus ⇒ passes."""
        cases = {
            "no policy": None,
            "prompt values without AdminSecurityMode 3": {"PromptOOMAddressInformationAccess": 1},
            "prompt based on computer security": self.policy(PromptOOMAddressInformationAccess=3),
        }
        for label, policy in cases.items():
            with self.subTest(case=label):
                center = fk.FakeSecurityCenter.active()
                check = self.guard(policy, center)
                self.assertTrue(check["ok"], check)
                self.assertIn("Fake Defender", check["detail"])
                self.assertEqual(center.queries, 1)

    def test_ol_27_04_no_policy_and_no_antivirus_fails(self) -> None:
        """OL-27.04: no deciding policy and no active antivirus ⇒ fails."""
        for label, center in (("none", fk.FakeSecurityCenter.none()), ("inactive", fk.FakeSecurityCenter.inactive())):
            with self.subTest(case=label):
                check = self.guard(None, center)
                self.assertFalse(check["ok"], check)
                self.assertIn("no active antivirus", check["detail"])

    def test_ol_27_05_unqueryable_antivirus_is_not_evaluated(self) -> None:
        """OL-27.05: no deciding policy, SecurityCenter2 unavailable ⇒ `not evaluated: SecurityCenter2 unavailable`."""
        check = self.guard(None, fk.FakeSecurityCenter.unavailable())
        self.assertEqual(
            check,
            {"name": "object_model_guard", "ok": False, "detail": "not evaluated: SecurityCenter2 unavailable"},
        )

    def test_ol_27_06_deciding_policy_never_queries_the_antivirus(self) -> None:
        """OL-27.06: with a deciding policy the antivirus is not queried."""
        for value in (0, 1, 2):
            with self.subTest(value=value):
                center = fk.FakeSecurityCenter.unavailable()
                self.guard(self.policy(PromptOOMAddressInformationAccess=value), center)
                self.assertEqual(center.queries, 0)


# --------------------------------------------------------------------------- #
# M10 — Outlook attachments (UT-OL-ATT-01..04, TC-09)
# --------------------------------------------------------------------------- #

#: Declared account of the attachment fixtures (the fake's cached Exchange account).
_ATTACHMENT_SCOPE = '[scope."ana.perez@example.com"]\n'
#: Decoded bytes of the ``local`` attachment of ``FakeOutlook.attachments_matrix``.
_LOCAL_CONTENT = b"%PDF-1.4\nFactura de octubre 2026\n"
_EXPECTED_DIR = Path(__file__).resolve().parent / "fixtures" / "expected"
_ISO_RE = __import__("re").compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}")


def _attachment_uid(fake: fk.FakeOutlook, key: str) -> str:
    """Native EntryID of one attachment fixture item."""
    return fake.item(key).entry_id


_MESSAGE_DIR_RE = __import__("re").compile(r"(/attachments/[a-z0-9_]+/)([^/]+)")


def _normalize_golden(value: object, root: Path) -> object:
    """Run-independent view of an Outlook payload (same rules as the TC-02 goldens)."""
    if isinstance(value, dict):
        return {
            key: _normalize_golden(item, root)
            for key, item in value.items()
            if key not in ("generated_at", "duration_ms")
        }
    if isinstance(value, list):
        return [_normalize_golden(item, root) for item in value]
    if isinstance(value, str):
        text = _ISO_RE.sub("<ISO>", value)
        text = text.replace(str(root), "<ROOT>").replace("\\", "/")
        # The message directory is a native id on macOS and the stable 32-hex
        # fallback when the Windows path budget is exceeded (D9): placeholder it.
        return _MESSAGE_DIR_RE.sub(r"\1<MESSAGE_DIR>", text)
    return value


def _assert_outlook_golden(
    case: unittest.TestCase, name: str, payload: dict, root: Path
) -> None:
    """Compare a normalized payload with ``expected/outlook/<name>``."""
    normalized = _normalize_golden(payload, root)
    path = _EXPECTED_DIR / "outlook" / name
    if os.environ.get("MAILQUERY_UPDATE_GOLDENS") == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(normalized, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return
    case.assertTrue(path.is_file(), f"missing golden {path}")
    expected = json.loads(path.read_text(encoding="utf-8"))
    case.assertEqual(normalized, expected, f"golden mismatch: {path.name}")


class _AttachmentCase(_OutlookCommandCase):
    """Commands and backend operations over the M10 attachment fixture profile."""

    def attachments_fake(self) -> fk.FakeOutlook:
        return self.use(fk.FakeOutlook.attachments_matrix(), _ATTACHMENT_SCOPE)

    def backend(self) -> Any:
        backend = _backend(self.fake, tmp_root=self.home / "tmp")
        self.addCleanup(backend.close)
        return backend

    def metadata(self, key: str) -> list[dict[str, Any]]:
        return list(self.backend().attachments(_attachment_uid(self.fake, key)))

    def staging_root(self) -> Path:
        return self.home / "tmp" / "staging"

    def assert_staging_clean(self) -> None:
        root = self.staging_root()
        leftovers = list(root.iterdir()) if root.is_dir() else []
        self.assertEqual(leftovers, [], f"staging leftovers: {leftovers}")

    def assert_cache_empty(self) -> None:
        cache = self.home / "attachments"
        files = [path for path in cache.rglob("*") if path.is_file()] if cache.is_dir() else []
        self.assertEqual(files, [])


class OutlookAttachmentMetadataTests(_AttachmentCase):
    """UT-OL-ATT-01: metadata, index and availability (AC-07/AC-15)."""

    def test_ut_ol_att_01_01_show_and_attachment_share_index_and_name(self) -> None:
        """UT-OL-ATT-01.01: show and attachment share index 1..N and the original name."""
        self.attachments_fake()
        uid = _attachment_uid(self.fake, "two_same")
        shown = self.run_json("show", uid)["message"]["attachments"]
        self.assertEqual(
            [(entry["index"], entry["name"]) for entry in shown],
            [(1, "recibo.pdf"), (2, "recibo.pdf"), (3, "otros.pdf")],
        )
        self.assertEqual(set(shown[0]), {"index", "name", "cached_path"})
        recovered = []
        for index in (1, 2, 3):
            record = self.run_json("attachment", uid, "--index", str(index))["attachments"][0]
            recovered.append((record["index"], record["original_name"]))
        self.assertEqual(recovered, [(1, "recibo.pdf"), (2, "recibo.pdf"), (3, "otros.pdf")])
        self.assertEqual(
            [entry["sanitized_name"] for entry in
             self.run_json("attachment", uid, "--all")["attachments"]],
            ["01_recibo.pdf", "02_recibo.pdf", "03_otros.pdf"],
        )
        # Hidden attachments are never listed nor indexed.
        hidden = self.run_json("show", _attachment_uid(self.fake, "hidden"))["message"]["attachments"]
        self.assertEqual([(entry["index"], entry["name"]) for entry in hidden], [(1, "visible.pdf")])
        self.assertEqual(
            [entry["original_name"] for entry in
             self.run_json("attachment", _attachment_uid(self.fake, "hidden"), "--all")["attachments"]],
            ["visible.pdf"],
        )

    def test_ut_ol_att_01_02_local_attachment_has_a_stable_size_and_is_extracted(self) -> None:
        """UT-OL-ATT-01.02: a local attachment exposes its local size and is recovered."""
        self.attachments_fake()
        rows = self.metadata("local")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["index"], 1)
        self.assertEqual(rows[0]["name"], "factura-2026-10.pdf")
        self.assertEqual(rows[0]["size_bytes"], len(_LOCAL_CONTENT))
        self.assertIsNone(rows[0]["unavailable_reason"])
        record = self.run_json(
            "attachment", _attachment_uid(self.fake, "local"), "--index", "1"
        )["attachments"][0]
        self.assertFalse(record["cached"])
        self.assertEqual(record["size_bytes"], len(_LOCAL_CONTENT))
        self.assertEqual(
            record["sha256"],
            "752502404021825e55659c1f00deca846ba1405df9c1eb5b0a0c7ccfd51613f9",
        )
        published = Path(record["path"])
        self.assertTrue(published.is_file())
        self.assertEqual(published.read_bytes(), _LOCAL_CONTENT)

    def test_ut_ol_att_01_03_not_downloaded_is_unavailable_without_downloading(self) -> None:
        """UT-OL-ATT-01.03: a by-reference attachment ⇒ unavailable (not_downloaded), no download."""
        self.attachments_fake()
        uid = _attachment_uid(self.fake, "by_reference")
        rows = self.metadata("by_reference")
        self.assertEqual(rows[0]["unavailable_reason"], "not_downloaded")
        self.assertIsNone(rows[0]["size_bytes"])
        self.fake.call_log.clear()
        error = self.run_error(3, "E_ATTACHMENT_UNAVAILABLE", "attachment", uid, "--index", "1")
        self.assertIn("is not available in the local store", error["message"])
        self.assertIn("downloads the attachment", error["hint"])
        self.assertEqual(self.fake.call_log.count(kind="Attachment", member="SaveAsFile"), 0)
        self.assertEqual(self.fake.call_log.count(member="MarkForDownload"), 0)
        self.assertFalse(
            {member for _kind, member in self.fake.call_log.members()} & {"MarkForDownload"}
        )
        self.assert_cache_empty()
        self.assert_staging_clean()

    def test_ut_ol_att_01_04_smime_is_unreadable_and_show_returns_empty(self) -> None:
        """UT-OL-ATT-01.04: S/MIME ⇒ show ``[]``, attachment ⇒ E_ATTACHMENT_UNREADABLE(smime)."""
        self.attachments_fake()
        uid = _attachment_uid(self.fake, "smime")
        self.fake.call_log.clear()
        payload = self.run_json("show", uid)
        self.assertEqual(payload["message"]["attachments"], [])
        self.assertIn(_SMIME_ENCRYPTED, payload["warnings"])
        self.assertNotIn("W_ATTACHMENTS_UNAVAILABLE", " ".join(payload["warnings"]))
        self.assertEqual(self.fake.call_log.count(member="Attachments"), 0)
        error = self.run_error(3, "E_ATTACHMENT_UNREADABLE", "attachment", uid, "--index", "1")
        self.assertIn("S/MIME protected", error["message"])
        self.assertIn("S/MIME", error["hint"])
        self.assert_cache_empty()

    def test_ut_ol_att_01_05_corrupt_unreadable_and_unsupported_reasons(self) -> None:
        """UT-OL-ATT-01.05: corrupt/unreadable ⇒ unreadable; embedded/OLE ⇒ unsupported."""
        self.attachments_fake()
        for key, code in (
            ("corrupt", "E_ATTACHMENT_UNREADABLE"),
            ("unopenable", "E_ATTACHMENT_UNREADABLE"),
            ("embedded", "E_ATTACHMENT_UNAVAILABLE"),
            ("ole", "E_ATTACHMENT_UNAVAILABLE"),
        ):
            with self.subTest(item=key):
                error = self.run_error(3, code, "attachment", _attachment_uid(self.fake, key), "--index", "1")
                if key == "corrupt":
                    self.assertIn("corrupt or unreadable", error["message"])
                if key == "unopenable":
                    self.assertIn("cannot be read", error["message"])
                if key in ("embedded", "ole"):
                    self.assertIn("cannot be recovered", error["message"])
        self.assert_cache_empty()
        self.assert_staging_clean()

    def test_ut_ol_att_01_06_metadata_reads_only_local_properties(self) -> None:
        """UT-OL-ATT-01.06: listing metadata records no download or network member."""
        self.attachments_fake()
        self.fake.call_log.clear()
        for key in ("local", "two_same", "hidden", "header_only", "smime", "by_reference"):
            with self.subTest(item=key):
                try:
                    self.metadata(key)
                except Exception:  # noqa: BLE001 - the message-level signal is expected
                    pass
        members = {member for _kind, member in self.fake.call_log.members()}
        self.assertNotIn("SaveAsFile", members)
        self.assertNotIn("MarkForDownload", members)
        self.assertFalse(members & {"Download", "GetTemporaryFilePath"})
        self.assert_cache_empty()
        self.assert_staging_clean()

    def test_ut_ol_att_01_07_header_only_show_is_empty_with_the_warning(self) -> None:
        """UT-OL-ATT-01.07: header-only with attachments ⇒ ``[]`` + W_ATTACHMENTS_UNAVAILABLE."""
        self.attachments_fake()
        uid = _attachment_uid(self.fake, "header_only")
        payload = self.run_json("show", uid)
        self.assertEqual(payload["message"]["attachments"], [])
        warnings = " ".join(payload["warnings"])
        self.assertIn("W_ATTACHMENTS_UNAVAILABLE", warnings)
        self.assertIn("W_BODY_NOT_LOCAL", warnings)
        self.assertNotIn("E_USAGE", warnings)
        self.assertFalse([entry for entry in payload["message"]["attachments"]])


class OutlookAttachmentMaterializationTests(_AttachmentCase):
    """UT-OL-ATT-02: COM materialization, staging and cleanup (AC-10/AC-12, §15)."""

    def test_ut_ol_att_02_01_local_attachment_is_materialized_in_staging(self) -> None:
        """UT-OL-ATT-02.01: SaveAsFile writes a 0600 regular file under a 0700 staging session."""
        self.attachments_fake()
        backend = self.backend()
        uid = _attachment_uid(self.fake, "local")
        stream = backend.attachment_stream(uid, 1)
        first = next(stream)
        self.assertTrue(first)
        root = self.staging_root()
        sessions = [path for path in root.iterdir() if path.is_dir()]
        self.assertEqual(len(sessions), 1)
        session = sessions[0]
        self.assertTrue(session.name.startswith("outlook-"))
        if os.name == "posix":
            self.assertEqual(session.stat().st_mode & 0o777, 0o700)
        files = list(session.iterdir())
        self.assertEqual(len(files), 1)
        self.assertFalse(files[0].is_symlink())
        self.assertTrue(files[0].is_file())
        if os.name == "posix":
            self.assertEqual(files[0].stat().st_mode & 0o777, 0o600)
        data = first + b"".join(stream)
        stream.close()
        self.assertEqual(data, _LOCAL_CONTENT)
        self.assert_staging_clean()
        # The command materializes again, validates and publishes under the cache.
        record = self.run_json("attachment", uid, "--index", "1")["attachments"][0]
        published = Path(record["path"])
        self.assertEqual(published.read_bytes(), _LOCAL_CONTENT)
        self.assertEqual(published.parent.parent.name, "outlook")
        self.assertEqual(self.fake.mutations.total, 0)
        self.assert_staging_clean()

    def test_ut_ol_att_02_02_invalid_materialized_path_is_rejected(self) -> None:
        """UT-OL-ATT-02.02: a symlink or a path outside staging ⇒ unavailable (unsupported)."""
        self.attachments_fake()
        from mailquery.backends import outlook as outlook_mod

        uid = _attachment_uid(self.fake, "invalid_staging")
        error = self.run_error(3, "E_ATTACHMENT_UNAVAILABLE", "attachment", uid, "--index", "1")
        self.assertIn("cannot be recovered", error["message"])
        self.assert_cache_empty()
        self.assert_staging_clean()

        outside = self.home / "outside.bin"
        backend = self.backend()
        with mock.patch.object(
            outlook_mod, "_create_staging_file", staticmethod(lambda session: outside)
        ):
            with self.assertRaises(Exception) as caught:
                list(backend.attachment_stream(_attachment_uid(self.fake, "local"), 1))
        self.assertEqual(getattr(caught.exception, "code", None), "E_ATTACHMENT_UNAVAILABLE")
        self.assertFalse(outside.exists())
        self.assert_staging_clean()

    def test_ut_ol_att_02_03_executable_content_blocks_the_message(self) -> None:
        """UT-OL-ATT-02.03: MZ in the materialized file ⇒ message blocked, temp removed."""
        self.attachments_fake()
        error = self.run_error(
            4, "E_ATTACHMENT_BLOCKED", "attachment", _attachment_uid(self.fake, "executable"), "--index", "1"
        )
        self.assertIn("executable content", error["message"])
        self.assertNotIn("\x00", error["message"])
        self.assert_cache_empty()
        self.assert_staging_clean()

    def test_ut_ol_att_02_04_temp_is_removed_on_failure_and_cancellation(self) -> None:
        """UT-OL-ATT-02.04: the staging file is removed when extraction fails or is closed early."""
        self.attachments_fake()
        self.run_error(3, "E_ATTACHMENT_UNREADABLE", "attachment", _attachment_uid(self.fake, "corrupt"), "--index", "1")
        self.assert_cache_empty()
        self.assert_staging_clean()
        backend = self.backend()
        stream = backend.attachment_stream(_attachment_uid(self.fake, "local"), 1)
        next(stream)
        self.assertTrue(any(self.staging_root().iterdir()))
        stream.close()
        self.assert_staging_clean()

    def test_ut_ol_att_02_05_whitelist_gains_only_save_as_file(self) -> None:
        """UT-OL-ATT-02.05: the COM whitelist only adds SaveAsFile (plus local Size/Type)."""
        from mailquery.backends import outlook_com

        self.assertIn("SaveAsFile", outlook_com.READONLY_MEMBERS["Attachment"])
        self.assertIn("SaveAsFile", outlook_com.READONLY_METHODS)
        self.assertEqual(
            set(outlook_com.READONLY_MEMBERS["Attachment"]),
            {"FileName", "DisplayName", "PropertyAccessor", "Size", "Type", "SaveAsFile"},
        )
        self.assertNotIn("GetTemporaryFilePath", outlook_com.READONLY_MEMBERS["Attachment"])
        fake = self.attachments_fake()
        app = _app(fake)
        spec = fake.item("local")
        item = app.Session.GetItemFromID(spec.entry_id, spec.folder.store.store_id)
        attachment = item.Attachments.Item(1)
        _assert_internal(self, lambda: attachment.Delete)
        _assert_internal(self, lambda: attachment.GetTemporaryFilePath)
        _assert_internal(self, lambda: attachment.SaveAs)
        self.assertEqual(fake.call_log.count(action="forbidden"), 0)

    def test_ut_ol_att_02_06_object_model_guard_is_not_extended(self) -> None:
        """UT-OL-ATT-02.06: the OMG check is unchanged and does not gate materialization."""
        self.attachments_fake()
        checks = {check["name"]: check for check in self.run_json("doctor", "--json")["checks"]}
        self.assertTrue(checks["object_model_guard"]["ok"])
        self.assertNotIn("materialization", checks["object_model_guard"]["detail"])
        record = self.run_json(
            "attachment", _attachment_uid(self.fake, "local"), "--index", "1"
        )["attachments"][0]
        self.assertFalse(record["cached"])
        self.assertTrue(Path(record["path"]).is_file())


class OutlookAttachmentErrorTests(_AttachmentCase):
    """UT-OL-ATT-03: materialization errors, timeouts and reasons (AC-15/AC-17)."""

    def test_ut_ol_att_03_01_access_denied_is_permission_error(self) -> None:
        """UT-OL-ATT-03.01: E_ACCESSDENIED in SaveAsFile ⇒ E_PERMISSION (exit 3)."""
        self.attachments_fake()
        error = self.run_error(
            3, "E_PERMISSION", "attachment", _attachment_uid(self.fake, "denied"), "--index", "1"
        )
        self.assertIn("Outlook", error["message"])
        self.assert_cache_empty()
        self.assert_staging_clean()

    def test_ut_ol_att_03_02_persistent_transient_rejection_is_client_busy(self) -> None:
        """UT-OL-ATT-03.02: a persistent transient rejection ⇒ E_CLIENT_BUSY (exit 5)."""
        self.attachments_fake()
        self.fake.reject_next(times=2, kind="Attachment", member="SaveAsFile")
        error = self.run_error(
            5, "E_CLIENT_BUSY", "attachment", _attachment_uid(self.fake, "local"), "--index", "1"
        )
        self.assertTrue(error["hint"].strip())
        self.assertEqual(self.fake.call_log.count(kind="Attachment", member="SaveAsFile"), 2)
        self.assert_cache_empty()
        self.assert_staging_clean()

    def test_ut_ol_att_03_03_hung_com_call_is_client_timeout(self) -> None:
        """UT-OL-ATT-03.03: a SaveAsFile call over the 30 s watchdog ⇒ E_CLIENT_TIMEOUT (exit 3)."""
        uid = _attachment_uid(fk.FakeOutlook.attachments_matrix(), "local")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        home = root / ".mailquery"
        home.mkdir()
        (home / "config.toml").write_text(_ATTACHMENT_SCOPE, encoding="utf-8")
        env = dict(os.environ)
        env["HOME"] = env["USERPROFILE"] = str(root)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env.pop("PYTHONPATH", None)
        started = time.monotonic()
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(_REPO_ROOT / "tests" / "fakes" / "run_cli.py"),
                "--scenario",
                "attachments_matrix",
                "--home",
                str(home),
                "--timeout",
                "0.2",
                "--hang",
                "Attachment.SaveAsFile",
                "--hang-timeout",
                "60",
                "--",
                "attachment",
                uid,
                "--index",
                "1",
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(root),
            timeout=120,
        )
        elapsed = time.monotonic() - started
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertLess(elapsed, 45.0)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["command"], "attachment")
        self.assertEqual(payload["error"]["code"], "E_CLIENT_TIMEOUT")
        self.assertIn("doctor", payload["error"]["hint"])
        self.assertFalse((home / "attachments").exists())
        # A later invocation sweeps the orphan session of the killed process.
        from mailquery import cli

        backend = _backend(fk.FakeOutlook.attachments_matrix(), tmp_root=home / "tmp")
        self.addCleanup(backend.close)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["attachment", uid, "--index", "1"], home=home, backend=backend)
        self.assertEqual(code, 0, out.getvalue() + err.getvalue())
        self.assertEqual(list((home / "tmp" / "staging").iterdir()), [])

    def test_ut_ol_att_03_04_total_extraction_deadline_is_client_timeout(self) -> None:
        """UT-OL-ATT-03.04: the 120 s core deadline expires though each COM call is fast."""
        from mailquery.attachments.engine import AttachmentsEngine
        from mailquery.config import load_config
        from mailquery.plugins import wrap_driver

        self.attachments_fake()
        backend = self.backend()
        config = load_config(self.home)
        wrapped = wrap_driver(backend, driver="outlook")

        class _Clock:
            """Monotonic clock that jumps after the watchdog-free COM calls."""

            def __init__(self) -> None:
                self.calls = 0

            def __call__(self) -> float:
                self.calls += 1
                return 0.0 if self.calls <= 2 else 20.0

        engine = AttachmentsEngine(
            self.home, config.attachments, wrapped, clock=_Clock()
        )
        with self.assertRaises(Exception) as caught:
            engine.recover(
                prefixed_uid(_attachment_uid(self.fake, "local"), "outlook"),
                [1],
                deadline=lambda: 10.0,
            )
        self.assertEqual(getattr(caught.exception, "code", None), "E_CLIENT_TIMEOUT")
        self.assertEqual(getattr(caught.exception, "exit_code", None), 3)
        # An aborted extraction leaves the generator suspended: closing the
        # backend removes its staging session (and the next run sweeps orphans).
        backend.close()
        self.assert_cache_empty()
        self.assert_staging_clean()

    def test_ut_ol_att_03_05_all_with_a_failure_returns_no_partial_results(self) -> None:
        """UT-OL-ATT-03.05: a failure in ``--all`` writes nothing (no partial results)."""
        self.attachments_fake()
        error = self.run_error(
            3,
            "E_ATTACHMENT_UNREADABLE",
            "attachment",
            _attachment_uid(self.fake, "partial_failure"),
            "--all",
        )
        self.assertIn("corrupt or unreadable", error["message"])
        self.assert_cache_empty()
        self.assert_staging_clean()

    def test_ut_ol_att_03_06_empty_attachment_is_published_with_zero_size(self) -> None:
        """UT-OL-ATT-03.06: a 0-byte attachment is materialized and published with size 0."""
        self.attachments_fake()
        record = self.run_json(
            "attachment", _attachment_uid(self.fake, "empty"), "--index", "1"
        )["attachments"][0]
        self.assertEqual(record["size_bytes"], 0)
        self.assertEqual(
            record["sha256"],
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        )
        self.assertTrue(Path(record["path"]).is_file())
        self.assertEqual(Path(record["path"]).read_bytes(), b"")


class OutlookAttachmentReadOnlyTests(_AttachmentCase):
    """UT-OL-ATT-04: read-only boundary and log (AC-19, RNF-13)."""

    def _exercise(self) -> None:
        self.run_json("attachment", _attachment_uid(self.fake, "local"), "--index", "1")
        self.run_json("attachment", _attachment_uid(self.fake, "local"), "--index", "1")
        self.run_error(4, "E_ATTACHMENT_BLOCKED", "attachment", _attachment_uid(self.fake, "executable"), "--index", "1")
        self.run_error(3, "E_ATTACHMENT_UNAVAILABLE", "attachment", _attachment_uid(self.fake, "by_reference"), "--index", "1")
        self.run_error(3, "E_ATTACHMENT_UNREADABLE", "attachment", _attachment_uid(self.fake, "corrupt"), "--index", "1")

    def test_ut_ol_att_04_01_extractions_never_mutate_the_mailbox(self) -> None:
        """UT-OL-ATT-04.01: 0 mutations/assignments; only whitelisted members are invoked."""
        from mailquery.backends import outlook_com

        self.attachments_fake()
        self._exercise()
        self.assertEqual(self.fake.mutations.assignments, 0)
        self.assertEqual(self.fake.mutations.total, 0, self.fake.mutations.events)
        self.assertEqual(self.fake.call_log.count(action="forbidden"), 0)
        invoked = {
            (entry.kind, entry.member)
            for entry in self.fake.call_log
            if entry.kind != "Connector"
        }
        for kind, member in invoked:
            self.assertIn(member, outlook_com.READONLY_MEMBERS[kind], (kind, member))
        self.assertIn(("Attachment", "SaveAsFile"), self.fake.call_log.members())

    def test_ut_ol_att_04_02_writes_stay_under_the_app_home(self) -> None:
        """UT-OL-ATT-04.02: all files this class writes are inside ``<home>``."""
        self.attachments_fake()
        before = set(self.root.rglob("*"))
        self._exercise()
        after = set(self.root.rglob("*"))
        for path in after - before:
            self.assertTrue(
                path == self.home or self.home in path.parents,
                f"write outside the app home: {path}",
            )
        self.assertTrue(any((self.home / "attachments").rglob("*.pdf")))
        self.assert_staging_clean()

    def test_ut_ol_att_04_03_log_has_no_pii(self) -> None:
        """UT-OL-ATT-04.03: the log records no uids, EntryIDs, names, paths or accounts."""
        self.attachments_fake()
        uid = _attachment_uid(self.fake, "local")
        self.run_json("attachment", uid, "--index", "1")
        log = (self.home / "logs" / "mailquery.log").read_text(encoding="utf-8")
        self.assertNotIn(uid, log)
        self.assertNotIn("factura-2026-10", log)
        self.assertNotIn("ana.perez@example.com", log)
        self.assertNotIn(str(self.home), log)
        self.assertNotIn("attachments/outlook", log)

    def test_ut_ol_att_04_04_event_end_keeps_the_attachment_counts(self) -> None:
        """UT-OL-ATT-04.04: ``event=end`` of attachment keeps count/cached/bytes/duration_ms."""
        self.attachments_fake()
        self.run_json("attachment", _attachment_uid(self.fake, "local"), "--index", "1")
        log = (self.home / "logs" / "mailquery.log").read_text(encoding="utf-8")
        line = next(
            row for row in log.splitlines()
            if "event=end command=attachment" in row
        )
        row = line
        self.assertIn("exit_code=0", line)
        self.assertIn("count=1", line)
        self.assertIn("cached=0", line)
        self.assertIn(f"bytes={len(_LOCAL_CONTENT)}", line)
        self.assertRegex(row, "duration_ms=\\d+")


class OutlookAttachmentGoldenTests(unittest.TestCase):
    """TC-09: new Outlook attachment goldens (over the fake; existing show goldens untouched)."""

    def setUp(self) -> None:
        from mailquery import cli

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.addCleanup(cli._close_logging_handlers)
        self.root = Path(tmp.name)
        self.home = self.root / ".mailquery"
        self.home.mkdir()
        (self.home / "config.toml").write_text(_ATTACHMENT_SCOPE, encoding="utf-8")
        self.fake = fk.FakeOutlook.attachments_matrix()

    def run_payload(self, *argv: str) -> tuple[int, dict]:
        from mailquery import cli

        backend = _backend(self.fake, tmp_root=self.home / "tmp")
        self.addCleanup(backend.close)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(list(argv), home=self.home, backend=backend)
        self.assertTrue(out.getvalue(), err.getvalue())
        return code, json.loads(out.getvalue())

    def golden(self, name: str, payload: dict) -> None:
        _assert_outlook_golden(self, name, payload, self.root)

    def test_tc_09_01_attachment_saved(self) -> None:
        """TC-09.01: first extraction of a local attachment (golden, cached:false)."""
        code, payload = self.run_payload(
            "attachment", _attachment_uid(self.fake, "local"), "--index", "1"
        )
        self.assertEqual(code, 0)
        self.assertFalse(payload["attachments"][0]["cached"])
        self.golden("attachment_saved.json", payload)

    def test_tc_09_02_attachment_cached_after_the_seeding_run(self) -> None:
        """TC-09.02: the second run reports the seeded cache (golden, cached:true)."""
        uid = _attachment_uid(self.fake, "local")
        first_code, first = self.run_payload("attachment", uid, "--index", "1")
        self.assertEqual(first_code, 0)
        self.assertFalse(first["attachments"][0]["cached"])  # documented seed
        code, payload = self.run_payload("attachment", uid, "--index", "1")
        self.assertEqual(code, 0)
        self.assertTrue(payload["attachments"][0]["cached"])
        self.assertEqual(
            payload["attachments"][0]["sha256"], first["attachments"][0]["sha256"]
        )
        self.golden("attachment_cached.json", payload)

    def test_tc_09_03_attachment_unavailable_not_downloaded(self) -> None:
        """TC-09.03: a by-reference attachment is unavailable (golden, exit 3)."""
        code, payload = self.run_payload(
            "attachment", _attachment_uid(self.fake, "by_reference"), "--index", "1"
        )
        self.assertEqual(code, 3)
        self.assertEqual(payload["error"]["code"], "E_ATTACHMENT_UNAVAILABLE")
        self.golden("attachment_unavailable.json", payload)

    def test_tc_09_04_attachment_blocked_executable_content(self) -> None:
        """TC-09.04: executable content blocks the message (golden, exit 4)."""
        code, payload = self.run_payload(
            "attachment", _attachment_uid(self.fake, "executable"), "--index", "1"
        )
        self.assertEqual(code, 4)
        self.assertEqual(payload["error"]["code"], "E_ATTACHMENT_BLOCKED")
        self.golden("attachment_blocked.json", payload)

    def test_tc_09_05_existing_show_goldens_keep_the_c8_shape(self) -> None:
        """TC-09.05: ``show.attachments`` keeps ``{index, name, cached_path}``; no golden rewrite."""
        for key in ("local", "hidden", "smime"):
            with self.subTest(item=key):
                code, payload = self.run_payload("show", _attachment_uid(self.fake, key))
                self.assertEqual(code, 0)
                attachments = payload["message"]["attachments"]
                for entry in attachments:
                    self.assertEqual(set(entry), {"index", "name", "cached_path"})
                if key == "smime":
                    self.assertEqual(attachments, [])
                    self.assertNotIn(
                        "W_ATTACHMENTS_UNAVAILABLE", " ".join(payload["warnings"])
                    )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

"""Unit tests for the backend interface and its implementations (PRD 9.3, plan 4.3)."""

from __future__ import annotations

import ast
import inspect
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from typing import Any

from mailquery.backends.apple_mail import AppleMailBackend
from mailquery.backends.base import MailBackend
from mailquery.errors import MailqueryError
from tests.fixtures.make_fixtures import (
    ACCOUNT_ICLOUD,
    EXTENDED_MAILBOX_URLS,
    MAILBOX_ICLOUD_ARCHIVO,
    MAILBOX_ICLOUD_CLIENTES_FACTURAS,
    MAILBOX_ICLOUD_FACTURAS,
    MAILBOX_ICLOUD_INBOX,
    MAILBOX_ICLOUD_PROYECTOS_FACTURAS,
    MAILBOX_ICLOUD_PROYECTOS_INBOX,
    MAILBOX_ICLOUD_SLASH_NAME,
    MAILBOX_URLS,
    build_store,
)

# Operations and metadata declared by the backend protocol v1 (C1; PRD-v2.1 §6.1).
EXPECTED_ABSTRACT_OPERATIONS = frozenset(
    {
        "driver",
        "plugin_api",
        "capabilities",
        "describe",
        "accounts",
        "labels_available",
        "mailboxes",
        "excluded_stores",
        "resolve_mailbox",
        "query",
        "membership",
        "duplicate_counts",
        "recipients",
        "attachment_names",
        "find_message",
        "load_body",
        "parse_uid",
        "parse_native_id",
        "doctor_checks",
        "close",
    }
)
#: Concrete members added by C1 on top of the abstract ones.
EXPECTED_CONCRETE_OPERATIONS = frozenset({"native_order", "attachments", "attachment_stream"})
EXPECTED_OPERATIONS = EXPECTED_ABSTRACT_OPERATIONS | EXPECTED_CONCRETE_OPERATIONS


class MailBackendInterfaceTest(unittest.TestCase):
    def test_ut_be_03_01_declares_exactly_the_prd_operations(self) -> None:
        """UT-BE-03.01: MailBackend declares exactly the protocol v1 operations (C1)."""
        self.assertEqual(set(MailBackend.__abstractmethods__), EXPECTED_ABSTRACT_OPERATIONS)
        public = {
            member
            for member, _ in inspect.getmembers(MailBackend)
            if not member.startswith("_")
        }
        self.assertEqual(public, EXPECTED_OPERATIONS)
        query_params = list(inspect.signature(MailBackend.query).parameters)
        self.assertEqual(
            query_params[1:],
            [
                "mailbox_ids",
                "since",
                "until",
                "unread",
                "flagged",
                "has_attachments",
                "order",
            ],
        )

    def test_ut_be_03_02_incomplete_subclass_cannot_be_instantiated(self) -> None:
        """UT-BE-03.02: a subclass missing operations does not instantiate."""

        class Incomplete(MailBackend):
            name = "incomplete"

            def close(self) -> None:
                return None

        with self.assertRaises(TypeError):
            Incomplete()
        with self.assertRaises(TypeError):
            MailBackend()


class BackendResolveContractMixin:
    """UT-BE-04.04/.05: folder resolution every backend must show (PRD 9.3, 15.3).

    Mix into a ``unittest.TestCase`` and implement the hooks. The query cases
    (.01-.03) are added by :class:`BackendContractMixin`.
    """

    def make_backend(self) -> MailBackend:
        """A backend over the contract data set (closed by the mixin)."""
        raise NotImplementedError

    def contract_account(self) -> str:
        """``account_uuid`` of the account holding the folders of the resolve cases."""
        raise NotImplementedError

    def contract_resolve_cases(self) -> list[tuple[str, Any]]:
        """``(ref, expected mailbox id)`` pairs for UT-BE-04.04."""
        raise NotImplementedError

    def contract_unknown_refs(self) -> list[str]:
        """References that match no folder of the account (UT-BE-04.05)."""
        raise NotImplementedError

    def setUp(self) -> None:  # noqa: N802 - unittest hook
        super().setUp()
        self.backend = self.make_backend()
        self.addCleanup(self.backend.close)

    def test_ut_be_04_04_resolve_mailbox_by_inbox_name_path_and_url(self) -> None:
        """UT-BE-04.04: INBOX alias, name, path and URL; path/URL beat a name; first wins."""
        account = self.contract_account()
        for ref, expected_id in self.contract_resolve_cases():
            with self.subTest(ref=ref):
                row = self.backend.resolve_mailbox(account, ref)
                self.assertIsNotNone(row)
                self.assertEqual(row["id"], expected_id)

    def test_ut_be_04_05_resolve_unknown_mailbox_is_none(self) -> None:
        """UT-BE-04.05: a reference that matches no folder gives None."""
        account = self.contract_account()
        for ref in self.contract_unknown_refs():
            with self.subTest(ref=ref):
                self.assertIsNone(self.backend.resolve_mailbox(account, ref))


class BackendContractMixin(BackendResolveContractMixin):
    """UT-BE-04: behavior every backend must show (PRD 9.3, 15.3, RF-12, RF-13).

    Mix into a ``unittest.TestCase`` and implement the hooks. The Apple Mail
    fixture runs it in W2; the Outlook fake runs the resolve cases from W3-T04
    and the whole contract from W3-T05.
    """

    def all_ids(self) -> list[Any]:
        return [row["id"] for row in self.backend.mailboxes()]

    def dated_rows(self) -> list[dict]:
        """Rows of every folder with a usable ``date_received``, oldest first."""
        rows = [
            row
            for row in self.backend.query(self.all_ids(), order="asc")
            if row["date_received"] is not None
            and 0 < row["date_received"] < 4_000_000_000
        ]
        self.assertGreater(len(rows), 3)
        return rows

    def test_ut_be_04_01_since_includes_the_exact_second(self) -> None:
        """UT-BE-04.01: query(since=...) includes the exact second."""
        rows = self.dated_rows()
        boundary = rows[len(rows) // 2]
        moment = boundary["date_received"]
        got = self.backend.query(self.all_ids(), since=moment)
        self.assertIn(boundary["uid"], [row["uid"] for row in got])
        self.assertTrue(all(row["date_received"] >= moment for row in got))
        later = self.backend.query(self.all_ids(), since=moment + 1)
        self.assertNotIn(boundary["uid"], [row["uid"] for row in later])

    def test_ut_be_04_02_until_excludes_the_exact_second(self) -> None:
        """UT-BE-04.02: query(until=...) excludes the exact second."""
        rows = self.dated_rows()
        boundary = rows[len(rows) // 2]
        moment = boundary["date_received"]
        got = self.backend.query(self.all_ids(), until=moment)
        self.assertNotIn(boundary["uid"], [row["uid"] for row in got])
        self.assertTrue(all(row["date_received"] < moment for row in got))
        later = self.backend.query(self.all_ids(), until=moment + 1)
        self.assertIn(boundary["uid"], [row["uid"] for row in later])

    def test_ut_be_04_03_unread_keeps_only_unread_messages(self) -> None:
        """UT-BE-04.03: query(unread=True) returns exactly the unread messages."""
        everything = self.backend.query(self.all_ids())
        expected = sorted(row["uid"] for row in everything if not row["read"])
        self.assertTrue(expected)
        self.assertLess(len(expected), len(everything))
        got = self.backend.query(self.all_ids(), unread=True)
        self.assertEqual(sorted(row["uid"] for row in got), expected)


class AppleMailBackendContractTest(BackendContractMixin, unittest.TestCase):
    """UT-BE-04 against the synthetic Apple Mail store (extended: folders 20-23)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.fx = build_store(extended=True)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.fx.cleanup()

    def make_backend(self) -> MailBackend:
        return AppleMailBackend(
            mail_root=self.fx.mail_root,
            accounts_db=self.fx.accounts_db,
            tmp_root=self.fx.home / "tmp",
        )

    def contract_account(self) -> str:
        return ACCOUNT_ICLOUD

    def contract_resolve_cases(self) -> list[tuple[str, Any]]:
        urls = {**MAILBOX_URLS, **EXTENDED_MAILBOX_URLS}
        return [
            ("INBOX", MAILBOX_ICLOUD_INBOX),
            ("inbox", MAILBOX_ICLOUD_INBOX),
            # name (unique)
            ("Archivo", MAILBOX_ICLOUD_ARCHIVO),
            ("archivo", MAILBOX_ICLOUD_ARCHIVO),
            # three folders are named Facturas: the first of mailboxes() wins
            ("Facturas", MAILBOX_ICLOUD_FACTURAS),
            # path (nested folders with the same name)
            ("Proyectos/Facturas", MAILBOX_ICLOUD_PROYECTOS_FACTURAS),
            ("Clientes/Facturas", MAILBOX_ICLOUD_CLIENTES_FACTURAS),
            # folder 23 is named "Proyectos/Inbox" and folder 20 has that path
            ("Proyectos/Inbox", MAILBOX_ICLOUD_PROYECTOS_INBOX),
            # URL (exact URL of each folder, including the %2F one)
            (urls[MAILBOX_ICLOUD_ARCHIVO], MAILBOX_ICLOUD_ARCHIVO),
            (urls[MAILBOX_ICLOUD_CLIENTES_FACTURAS], MAILBOX_ICLOUD_CLIENTES_FACTURAS),
            (urls[MAILBOX_ICLOUD_PROYECTOS_INBOX], MAILBOX_ICLOUD_PROYECTOS_INBOX),
            (urls[MAILBOX_ICLOUD_SLASH_NAME], MAILBOX_ICLOUD_SLASH_NAME),
        ]

    def contract_unknown_refs(self) -> list[str]:
        return ["Does not exist", "Proyectos/Missing", "", "   "]

    def test_same_name_folders_follow_the_order_of_mailboxes(self) -> None:
        """The first-wins rule uses the order of mailboxes(), here 2, 21, 22."""
        ids = [
            row["id"]
            for row in self.backend.mailboxes()
            if row["name"] == "Facturas" and row["account_uuid"] == ACCOUNT_ICLOUD
        ]
        self.assertEqual(
            ids,
            [
                MAILBOX_ICLOUD_FACTURAS,
                MAILBOX_ICLOUD_PROYECTOS_FACTURAS,
                MAILBOX_ICLOUD_CLIENTES_FACTURAS,
            ],
        )

    def test_backend_identity_and_apple_mail_specifics(self) -> None:
        """driver, excluded_stores, labels_available and describe of the adapter."""
        self.assertEqual(self.backend.driver, "apple_mail")
        self.assertEqual(self.backend.excluded_stores(), [])
        self.assertTrue(self.backend.labels_available)
        info = self.backend.describe()
        self.assertEqual(info["version"], "V10")
        self.assertIn(info["strategy"], ("live_ro", "copy_ro"))
        self.assertTrue(info["schema_ok"])

    def test_parse_uid_is_static_and_offline(self) -> None:
        """AppleMailBackend.parse_uid: integers only, E_USAGE otherwise."""
        self.assertEqual(AppleMailBackend.parse_uid("2714"), 2714)
        self.assertEqual(AppleMailBackend.parse_uid("-5"), -5)
        with self.assertRaises(MailqueryError) as context:
            AppleMailBackend.parse_uid("abc")
        self.assertEqual(context.exception.code, "E_USAGE")
        self.assertIn("invalid uid 'abc': expected an integer", context.exception.message)

    def test_doctor_checks_names_and_order(self) -> None:
        """doctor_checks returns the five Apple Mail checks, all ok on the fixture."""
        checks = self.backend.doctor_checks()
        self.assertEqual(
            [check["name"] for check in checks],
            ["store", "envelope_index", "schema", "readonly_strategy", "accounts_db"],
        )
        self.assertTrue(all(check["ok"] for check in checks), checks)


class OutlookBackendContractTest(BackendContractMixin, unittest.TestCase):
    """UT-BE-04 against the Outlook fake (folder matrix plus a top-level "Facturas")."""

    def make_backend(self) -> MailBackend:
        from mailquery.backends import get_backend
        from tests.fakes.outlook import FakeOutlook

        self.fake = FakeOutlook.folder_matrix()
        # Its path "Facturas" equals the name of INBOX/Facturas, listed earlier.
        self.fake.store("es").add_folder("Facturas", key="es.top_facturas")
        # Same name in two subfolders, no folder has it as path.
        self.fake.folder("es.proyectos").add_folder("Pendientes", key="es.proyectos_pendientes")
        self.fake.folder("es.archivo").add_folder("Pendientes", key="es.archivo_pendientes")
        # Some read messages, so that query(unread=True) is a strict subset (UT-BE-04.03).
        self.fake.item("es_factura").read = True
        self.fake.item("de_inbox_message").read = True
        return get_backend(
            platform="win32",
            outlook_app=self.fake,
            registry=self.fake.registry,
            security_center=self.fake.security_center,
        )

    def contract_account(self) -> str:
        return self.fake.store("es").uuid

    def ids_by_path(self) -> dict[str, Any]:
        account = self.contract_account()
        return {
            row["path"]: row["id"]
            for row in self.backend.mailboxes()
            if row["account_uuid"] == account
        }

    def urls_by_path(self) -> dict[str, str]:
        account = self.contract_account()
        return {
            row["path"]: row["url"]
            for row in self.backend.mailboxes()
            if row["account_uuid"] == account
        }

    def contract_resolve_cases(self) -> list[tuple[str, Any]]:
        ids = self.ids_by_path()
        urls = self.urls_by_path()
        return [
            ("INBOX", ids["INBOX"]),
            ("inbox", ids["INBOX"]),
            # name (unique)
            ("Archivo", ids["Archivo"]),
            ("archivo", ids["Archivo"]),
            # three folders are named Facturas: the exact path of the top-level
            # one beats the name, and by name the first of mailboxes() wins
            ("Facturas", ids["Facturas"]),
            ("FACTURAS", ids["Facturas"]),
            # two subfolders are named Pendientes: the first of mailboxes() wins
            ("Pendientes", ids["Proyectos/Pendientes"]),
            ("pendientes", ids["Proyectos/Pendientes"]),
            ("Archivo/Pendientes", ids["Archivo/Pendientes"]),
            # path (nested folders with the same name)
            ("INBOX/Facturas", ids["INBOX/Facturas"]),
            ("Archivo/Facturas", ids["Archivo/Facturas"]),
            ("archivo/FACTURAS", ids["Archivo/Facturas"]),
            ("Proyectos/Inbox", ids["Proyectos/Inbox"]),
            # encoded name/path as listed
            ("Clientes%2FProveedores", ids["Clientes%2FProveedores"]),
            ("100%25 reales", ids["100%25 Reales"]),
            ("facturación ñ", ids["Facturación ñ"]),
            # URL (exact URL of each folder, also decoded and in another case)
            (urls["Archivo/Facturas"], ids["Archivo/Facturas"]),
            (urls["Clientes%2FProveedores"], ids["Clientes%2FProveedores"]),
            (urls["Facturación ñ"], ids["Facturación ñ"]),
            (urls["Facturación ñ"].lower(), ids["Facturación ñ"]),
            (f"outlook://{self.contract_account()}/Facturación ñ", ids["Facturación ñ"]),
            (urls["INBOX/Facturas"], ids["INBOX/Facturas"]),
        ]

    def contract_unknown_refs(self) -> list[str]:
        de_inbox = f"outlook://{self.fake.store('de').uuid}/INBOX"
        return [
            "Does not exist",
            "Proyectos/Missing",
            "",
            "   ",
            "Rechnungen",  # a folder of another account
            de_inbox,
            "Calendario",  # not a mail folder
            "Correo sin leer",  # search folder
            "Problemas de sincronización",  # hidden sync folder
        ]

    def test_same_name_folders_follow_the_order_of_mailboxes(self) -> None:
        """The first-wins rule uses the depth-first order of mailboxes()."""
        paths = [
            row["path"]
            for row in self.backend.mailboxes()
            if row["name"] == "Facturas" and row["account_uuid"] == self.contract_account()
        ]
        self.assertEqual(paths, ["INBOX/Facturas", "Archivo/Facturas", "Facturas"])
        self.assertEqual(
            self.backend.resolve_mailbox(self.contract_account(), "facturas")["path"], "Facturas"
        )
        paths = [
            row["path"]
            for row in self.backend.mailboxes()
            if row["name"] == "Pendientes" and row["account_uuid"] == self.contract_account()
        ]
        self.assertEqual(paths, ["Proyectos/Pendientes", "Archivo/Pendientes"])

    def test_parse_uid_is_static_and_offline(self) -> None:
        """OutlookBackend.parse_uid: uppercase hex EntryIDs only, E_USAGE otherwise (PRD 12.4)."""
        from mailquery.backends.outlook import OutlookBackend

        entry_id = self.fake.item("es_inbox_message").entry_id
        self.assertEqual(OutlookBackend.parse_uid(entry_id), entry_id)
        for raw in ("", "00ab", "0x00AB", " 00AB", "00AB ", "00-AB", "Z1"):
            with self.subTest(raw=raw):
                with self.assertRaises(MailqueryError) as context:
                    OutlookBackend.parse_uid(raw)
                self.assertEqual(context.exception.code, "E_USAGE")
                self.assertIn(
                    "expected an uppercase hexadecimal EntryID", context.exception.message
                )
        self.assertEqual(self.fake.call_log.count(), 0)


SRC_ROOT =Path(__file__).resolve().parents[1] / "src" / "mailquery"
_WINDOWS_STDLIB_OK = {"winreg", "msvcrt", "_winapi", "ctypes"}
_COM_MODULES = {"win32com", "pythoncom", "pywintypes"}


def _source_files() -> list[Path]:
    return sorted(SRC_ROOT.rglob("*.py"))


def _imported_roots(path: Path) -> list[tuple[str, int]]:
    """Return (top-level module, line) for every import statement in a file."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((alias.name.split(".")[0], node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.append((node.module.split(".")[0], node.lineno))
    return found


def _imported_modules(path: Path) -> list[str]:
    """Return the full dotted names imported by a file (``from a import b`` => a, a.b)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.append(node.module)
            found.extend(f"{node.module}.{alias.name}" for alias in node.names)
    return found


class GetBackendSelectionTest(unittest.TestCase):
    def test_ut_be_01_01_win32_selects_outlook(self) -> None:
        """UT-BE-01.01: win32 yields the Outlook backend, wired to the injected client."""
        from mailquery.backends import get_backend
        from mailquery.backends.outlook import OutlookBackend
        from tests.fakes.outlook import FakeOutlook

        fake = FakeOutlook.default()
        backend = get_backend(
            platform="win32",
            outlook_app=fake,
            registry=fake.registry,
            security_center=fake.security_center,
        )
        self.addCleanup(backend.close)
        self.assertIsInstance(backend, OutlookBackend)
        self.assertEqual(backend.driver, "outlook")
        self.assertTrue(backend.labels_available)
        self.assertIn(
            "Exchange (ana.perez@example.com)",
            [row["label"] for row in backend.accounts()],
        )
        self.assertEqual(fake.call_log.count(member="GetActiveObject"), 1)

    def test_ut_be_01_02_non_win32_platforms_select_apple_mail(self) -> None:
        """UT-BE-01.02: any platform other than win32 yields the Apple Mail backend."""
        from mailquery.backends import get_backend

        for platform in ("darwin", "linux", "plan9-made-up"):
            with self.subTest(platform=platform):
                backend = get_backend(platform=platform)
                self.assertIsInstance(backend, AppleMailBackend)
                self.assertEqual(backend.driver, "apple_mail")

    def test_ut_be_01_02_apple_mail_kwargs_are_passed_through(self) -> None:
        """UT-BE-01.02: mail_root, accounts_db and tmp_root reach AppleMailBackend."""
        from mailquery.backends import get_backend

        backend = get_backend(
            platform="linux",
            mail_root=Path("/m/root"),
            accounts_db=Path("/a/db"),
            tmp_root=Path("/t/root"),
        )
        self.assertEqual(backend._mail_root, Path("/m/root"))
        self.assertEqual(backend._accounts_db, Path("/a/db"))

    def test_ut_be_01_02_win32_imports_outlook_lazily(self) -> None:
        """UT-BE-01.02: win32 goes through the lazy import of backends.outlook."""
        from mailquery.backends import get_backend

        if (SRC_ROOT / "backends" / "outlook.py").exists():
            return  # selection of Outlook is covered by W3-T03 (UT-BE-01.01)
        with self.assertRaises(ImportError):
            get_backend(platform="win32")


class ImportBoundaryTest(unittest.TestCase):
    def test_ut_be_02_01_no_win32com_outside_win32(self) -> None:
        """UT-BE-02.01: outside win32, importing everything never loads win32com."""
        script = textwrap.dedent(
            """
            import importlib, importlib.abc, pkgutil, sys

            class Blocker(importlib.abc.MetaPathFinder):
                def find_spec(self, name, path=None, target=None):
                    if name.split(".")[0] in ("win32com", "pythoncom", "pywintypes"):
                        raise ImportError("blocked: " + name)
                    return None

            sys.meta_path.insert(0, Blocker())
            import mailquery
            for info in pkgutil.walk_packages(mailquery.__path__, "mailquery."):
                importlib.import_module(info.name)
            from mailquery.backends import get_backend
            for platform in ("darwin", "linux"):
                get_backend(platform=platform)
            bad = [m for m in sys.modules if m.split(".")[0] in ("win32com", "pythoncom")]
            assert not bad, bad
            print("OK")
            """
        )
        with tempfile.TemporaryDirectory() as home:
            env = dict(os.environ)
            env.update(
                HOME=home,
                USERPROFILE=home,
                PYTHONPATH=str(SRC_ROOT.parent),
                PYTHONDONTWRITEBYTECODE="1",
            )
            result = subprocess.run(
                [sys.executable, "-c", script],
                env=env,
                capture_output=True,
                text=True,
                cwd=home,
                timeout=60,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("OK", result.stdout)

    def test_ut_be_02_02_only_outlook_com_imports_win32com(self) -> None:
        """UT-BE-02.02: only outlook_com.py imports win32com / pythoncom."""
        offenders = []
        for path in _source_files():
            if path.name == "outlook_com.py":
                continue
            for root, line in _imported_roots(path):
                if root in _COM_MODULES:
                    offenders.append(f"{path.name}:{line} imports {root}")
        self.assertEqual(offenders, [])

    def test_ut_be_02_03_outlook_com_imports_only_stdlib_and_pywin32(self) -> None:
        """UT-BE-02.03: outlook_com.py imports nothing outside stdlib and pywin32."""
        path = SRC_ROOT / "backends" / "outlook_com.py"
        if not path.exists():
            return  # created in W3; the check applies as soon as it exists
        allowed = set(sys.stdlib_module_names) | _COM_MODULES | _WINDOWS_STDLIB_OK | {"mailquery"}
        offenders = [
            f"line {line}: {root}"
            for root, line in _imported_roots(path)
            if root not in allowed
        ]
        self.assertEqual(offenders, [])

    def test_ut_be_02_04_nobody_invokes_osascript_or_applescript(self) -> None:
        """UT-BE-02.04: no module references osascript or AppleScript."""
        offenders = []
        for path in _source_files():
            text = path.read_text(encoding="utf-8").lower()
            for needle in ("osascript", "applescript"):
                if needle in text:
                    offenders.append(f"{path.name}: {needle}")
        self.assertEqual(offenders, [])

    def test_ut_be_02_05_search_and_config_have_no_sql_com_or_store_imports(self) -> None:
        """UT-BE-02.05: search.py/config.py hold no SQL/COM nor import store, emlx, accounts."""
        forbidden_modules = {"mailquery.store", "mailquery.emlx", "mailquery.accounts"}
        offenders = []
        for name in ("search.py", "config.py"):
            path = SRC_ROOT / name
            for module in _imported_modules(path):
                if module in forbidden_modules:
                    offenders.append(f"{name}: imports {module}")
            for root, line in _imported_roots(path):
                if root in _COM_MODULES | {"sqlite3"}:
                    offenders.append(f"{name}:{line}: imports {root}")
            text = path.read_text(encoding="utf-8")
            for keyword in ("SELECT ", "FROM messages", "INSERT INTO", "PRAGMA "):
                if keyword in text:
                    offenders.append(f"{name}: SQL text {keyword.strip()!r}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()

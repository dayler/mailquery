"""UT-ACT-01..04: active-content markers in PDF, OLE and ZIP bytes.

The tests build their samples in a temporary directory through
``tests/fixtures/active_content_samples.py`` and call the detector on the
resulting paths. They never open a real attachment and never decompress one.
"""

from __future__ import annotations

import io
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from mailquery.attachments import active_content
from mailquery.attachments.active_content import (
    ACTIVE_CONTENT_TYPES,
    active_content_types,
)

from tests.fixtures import active_content_samples as samples
from tests.test_cli import (
    _ATTACHMENT_PLUGIN_LABEL,
    _ATTACHMENT_PLUGIN_UID,
    ATTACHMENT_PLUGIN_DRIVER,
    AttachmentTestBase,
    _attachment_scope,
)

_PDF_ONLY = ("pdf-javascript",)
_MACROS_ONLY = ("office-macros",)
_ARCHIVE_ONLY = ("archive-executable",)


def _representative_cases(
    root: Path,
) -> list[tuple[str, Path, tuple[str, ...]]]:
    """Build one sample per detector rule and return ``(label, path, expected)``."""
    return [
        (
            "pdf/javascript",
            samples.write_pdf(root, "case_javascript.pdf", b"/JavaScript "),
            _PDF_ONLY,
        ),
        (
            "pdf/js_escaped",
            samples.write_pdf(root, "case_escaped.pdf", b"/#4A#53 "),
            _PDF_ONLY,
        ),
        (
            "pdf/clean",
            samples.write_pdf(root, "case_clean.pdf", b"<< /Type /Catalog >>"),
            (),
        ),
        (
            "pdf/late_header",
            samples.write_pdf(root, "case_late.pdf", b"/JS ", offset=1024),
            (),
        ),
        (
            "ole/macros",
            samples.write_ole(
                root, "case_macros.doc", samples.VBA_PROJECT_UTF16LE
            ),
            _MACROS_ONLY,
        ),
        ("ole/clean", samples.write_ole(root, "case_clean.doc", b"\x01\x02"), ()),
        (
            "zip/macros",
            samples.write_zip(
                root, "case_macros.xlsm", [("xl/vbaProject.bin", b"\x00" * 8)]
            ),
            _MACROS_ONLY,
        ),
        (
            "zip/executable",
            samples.write_zip(
                root, "case_exe.zip", [("docs/factura.pdf.exe", b"")]
            ),
            _ARCHIVE_ONLY,
        ),
        (
            "zip/encrypted",
            samples.write_zip(
                root, "case_encrypted.zip", [("setup.exe", b"")], encrypted=True
            ),
            _ARCHIVE_ONLY,
        ),
        (
            "zip/macros_and_executable",
            samples.write_zip(
                root,
                "case_both.zip",
                [("vbaProject.bin", b""), ("tool.exe", b"")],
            ),
            ("office-macros", "archive-executable"),
        ),
        (
            "zip/clean",
            samples.write_zip(
                root, "case_clean.zip", [("docs/factura.pdf", b"%PDF-1.7\n")]
            ),
            (),
        ),
        (
            "zip/broken",
            samples.write_sample(
                root, "case_broken.zip", b"PK\x03\x04" + b"\x00" * 64
            ),
            (),
        ),
    ]


class ActiveContentTestCase(unittest.TestCase):
    """Shared temporary directory for the detector samples."""

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)


class PdfJavascriptTests(ActiveContentTestCase):
    """UT-ACT-01: ``pdf-javascript`` markers."""

    def test_ut_act_01_01_names_and_delimiters_are_detected(self) -> None:
        """UT-ACT-01.01: /JavaScript, /JS and /Launch followed by space, <<, ( or EOF."""
        for name in (b"/JavaScript", b"/JS", b"/Launch"):
            for delimiter in (b" ", b"<<", b"(", b""):
                with self.subTest(name=name, delimiter=delimiter):
                    path = samples.write_pdf(
                        self.root, "marker.pdf", name + delimiter
                    )
                    self.assertEqual(active_content_types(path), _PDF_ONLY)

    def test_ut_act_01_02_hex_escaped_names_are_detected(self) -> None:
        """UT-ACT-01.02: #xx escapes in the PDF name are decoded before comparing."""
        for marker in (b"/J#61vaScript ", b"/#4A#53 ", b"/L#61unch "):
            with self.subTest(marker=marker):
                path = samples.write_pdf(self.root, "escaped.pdf", marker)
                self.assertEqual(active_content_types(path), _PDF_ONLY)

    def test_ut_act_01_03_longer_names_and_lowercase_do_not_count(self) -> None:
        """UT-ACT-01.03: /JavaScriptX, /JSON, /Launcher and lowercase do not count."""
        for marker in (
            b"/JavaScriptX ",
            b"/JSON ",
            b"/Launcher ",
            b"/javascript ",
        ):
            with self.subTest(marker=marker):
                path = samples.write_pdf(self.root, "other.pdf", marker)
                self.assertEqual(active_content_types(path), ())

    def test_ut_act_01_04_late_header_is_not_a_pdf(self) -> None:
        """UT-ACT-01.04: %PDF- starting after byte 1024 is not a PDF header."""
        path = samples.write_pdf(
            self.root, "late.pdf", b"/JS ", offset=active_content.PDF_HEADER_BYTES
        )
        self.assertEqual(active_content_types(path), ())

    def test_ut_act_01_05_pdf_without_active_names_has_no_markers(self) -> None:
        """UT-ACT-01.05: a PDF without the active names reports nothing."""
        path = samples.write_pdf(
            self.root, "plain.pdf", b"1 0 obj\n<< /Type /Catalog >>\nendobj\n"
        )
        self.assertEqual(active_content_types(path), ())

    def test_ut_act_01_06_header_ending_on_byte_1024_is_detected(self) -> None:
        """UT-ACT-01.06: %PDF- whose last byte is byte 1024 still counts as a PDF."""
        path = samples.write_pdf(self.root, "boundary.pdf", b"/JS ", offset=1019)
        raw = path.read_bytes()
        header_start = raw.index(b"%PDF-")
        self.assertEqual(header_start, 1019)
        self.assertEqual(
            header_start + len(b"%PDF-"), active_content.PDF_HEADER_BYTES
        )
        self.assertEqual(active_content_types(path), _PDF_ONLY)

    def test_ut_act_01_07_invalid_escape_and_end_of_file(self) -> None:
        """UT-ACT-01.07: invalid #xx is not decoded; /JS at EOF has no delimiter."""
        invalid = samples.write_pdf(
            self.root, "invalid_escape.pdf", b"/J#zzavaScript "
        )
        self.assertEqual(active_content_types(invalid), ())
        at_eof = samples.write_pdf(self.root, "at_eof.pdf", b"/JS")
        self.assertEqual(active_content_types(at_eof), _PDF_ONLY)


class OfficeMacrosTests(ActiveContentTestCase):
    """UT-ACT-02: ``office-macros`` markers."""

    def test_ut_act_02_01_ole_with_vba_project_is_detected(self) -> None:
        """UT-ACT-02.01: OLE containers with the UTF-16LE stream name are detected."""
        for name in ("legacy.doc", "legacy.xls"):
            with self.subTest(name=name):
                path = samples.write_ole(
                    self.root, name, samples.VBA_PROJECT_UTF16LE
                )
                self.assertEqual(active_content_types(path), _MACROS_ONLY)

    def test_ut_act_02_02_ole_markers_need_signature_and_utf16(self) -> None:
        """UT-ACT-02.02: plain OLE, ASCII name and non-OLE bytes are not macros."""
        cases = {
            "ole_without_name.doc": samples.ole_bytes(b"\x01\x02\x03"),
            "ole_ascii_name.doc": samples.ole_bytes(b"_VBA_PROJECT"),
            "no_ole_signature.bin": samples.ole_bytes(
                samples.VBA_PROJECT_UTF16LE, with_signature=False
            ),
        }
        for name, payload in cases.items():
            with self.subTest(name=name):
                path = samples.write_sample(self.root, name, payload)
                self.assertEqual(active_content_types(path), ())

    def test_ut_act_02_03_zip_with_vba_project_is_detected(self) -> None:
        """UT-ACT-02.03: vbaProject.bin in a folder or at the root is detected."""
        in_folder = samples.write_zip(
            self.root, "macros.xlsm", [("xl/vbaProject.bin", b"\x00" * 8)]
        )
        self.assertEqual(active_content_types(in_folder), _MACROS_ONLY)
        at_root = samples.write_zip(
            self.root, "macros_root.zip", [("vbaProject.bin", b"\x00" * 8)]
        )
        self.assertEqual(active_content_types(at_root), _MACROS_ONLY)

    def test_ut_act_02_04_office_documents_without_macros_are_clean(self) -> None:
        """UT-ACT-02.04: docx, xlsx and pptx with own .bin entries report nothing."""
        documents = {
            "plain.docx": [
                ("[Content_Types].xml", b"<Types/>"),
                ("word/document.xml", b"<w:document/>"),
                ("word/embeddings/oleObject1.bin", b"\x00" * 8),
            ],
            "plain.xlsx": [
                ("xl/workbook.xml", b"<workbook/>"),
                ("xl/embeddings/oleObject1.bin", b"\x00" * 8),
            ],
            "plain.pptx": [
                ("ppt/presentation.xml", b"<p:presentation/>"),
                ("ppt/embeddings/oleObject1.bin", b"\x00" * 8),
            ],
        }
        for name, entries in documents.items():
            with self.subTest(name=name):
                path = samples.write_zip(self.root, name, entries)
                self.assertEqual(active_content_types(path), ())


class ArchiveExecutableTests(ActiveContentTestCase):
    """UT-ACT-03: ``archive-executable`` markers."""

    def test_ut_act_03_01_chained_and_simple_extensions_are_detected(self) -> None:
        """UT-ACT-03.01: docs/factura.pdf.exe and run.bat are detected."""
        for entries in (
            [("docs/factura.pdf.exe", b"")],
            [("run.bat", b"")],
        ):
            with self.subTest(entries=entries):
                path = samples.write_zip(self.root, "payloads.zip", entries)
                self.assertEqual(active_content_types(path), _ARCHIVE_ONLY)

    def test_ut_act_03_02_encrypted_zip_is_detected(self) -> None:
        """UT-ACT-03.02: an encrypted ZIP with an .exe entry is detected."""
        path = samples.write_zip(
            self.root, "encrypted.zip", [("setup.exe", b"")], encrypted=True
        )
        raw = path.read_bytes()
        local_flag = struct.unpack_from("<H", raw, 6)[0]
        central_offset = raw.index(b"PK\x01\x02")
        central_flag = struct.unpack_from("<H", raw, central_offset + 8)[0]
        self.assertEqual(local_flag & 0x0001, 0x0001)
        self.assertEqual(central_flag & 0x0001, 0x0001)
        with zipfile.ZipFile(path) as archive:
            self.assertEqual(archive.namelist(), ["setup.exe"])
        self.assertEqual(active_content_types(path), _ARCHIVE_ONLY)

    def test_ut_act_03_03_backslash_separator_uses_the_last_segment(self) -> None:
        """UT-ACT-03.03: dir\\x.scr splits on the backslash to get the last segment."""
        path = samples.write_zip(self.root, "backslash.zip", [("dir\\x.scr", b"")])
        self.assertEqual(active_content_types(path), _ARCHIVE_ONLY)

    def test_ut_act_03_04_innocuous_entries_are_clean(self) -> None:
        """UT-ACT-03.04: only PDF, only .bin, or harmless .. and : names report nothing."""
        cases = {
            "only_pdf.zip": [("docs/factura.pdf", b"%PDF-1.7\n")],
            "only_bin.zip": [("data/oleObject1.bin", b"\x00" * 8)],
            "harmless_names.zip": [("../readme.txt", b"a"), ("notes:final.txt", b"b")],
        }
        for name, entries in cases.items():
            with self.subTest(name=name):
                path = samples.write_zip(self.root, name, entries)
                self.assertEqual(active_content_types(path), ())

    def test_ut_act_03_05_broken_central_directory_is_clean(self) -> None:
        """UT-ACT-03.05: a PK\\x03\\x04 prefix with an unreadable directory reports nothing."""
        path = samples.write_sample(
            self.root, "broken.zip", b"PK\x03\x04" + b"\x00" * 64
        )
        self.assertEqual(active_content_types(path), ())

    def test_ut_act_03_06_uppercase_extension_is_detected(self) -> None:
        """UT-ACT-03.06: RUN.EXE is detected because the catalog ignores case."""
        path = samples.write_zip(self.root, "uppercase.zip", [("RUN.EXE", b"")])
        self.assertEqual(active_content_types(path), _ARCHIVE_ONLY)

    def test_ut_act_03_07_directory_entry_is_not_an_executable(self) -> None:
        """UT-ACT-03.07: payload.exe/ has an empty last segment and does not count."""
        path = samples.write_zip(
            self.root, "directory.zip", [("payload.exe/", b"")]
        )
        self.assertEqual(active_content_types(path), ())

    def test_ut_act_03_08_zipfile_failures_are_swallowed(self) -> None:
        """UT-ACT-03.08: a ZipFile exception other than BadZipFile reports nothing."""
        path = samples.write_zip(self.root, "valid.zip", [("run.bat", b"")])
        for error in (ValueError("bad directory"), OSError("unreadable")):
            with self.subTest(error=type(error).__name__):
                with mock.patch.object(
                    active_content.zipfile, "ZipFile", side_effect=error
                ):
                    self.assertEqual(active_content_types(path), ())


class DetectorPropertiesTests(ActiveContentTestCase):
    """UT-ACT-04: detector properties."""

    def test_ut_act_04_01_types_follow_the_canonical_order(self) -> None:
        """UT-ACT-04.01: a ZIP with macros and an executable reports both in order."""
        path = samples.write_zip(
            self.root,
            "both.zip",
            [("vbaProject.bin", b""), ("tool.exe", b"")],
        )
        self.assertEqual(
            active_content_types(path), ("office-macros", "archive-executable")
        )
        self.assertEqual(
            ACTIVE_CONTENT_TYPES,
            ("pdf-javascript", "office-macros", "archive-executable"),
        )

    def test_ut_act_04_02_detector_never_decompresses(self) -> None:
        """UT-ACT-04.02: ZipFile.open, read and extract are never called."""
        cases = _representative_cases(self.root)
        with (
            mock.patch.object(
                zipfile.ZipFile,
                "open",
                side_effect=AssertionError("ZipFile.open must not be called"),
            ) as opened,
            mock.patch.object(
                zipfile.ZipFile,
                "read",
                side_effect=AssertionError("ZipFile.read must not be called"),
            ) as read,
            mock.patch.object(
                zipfile.ZipFile,
                "extract",
                side_effect=AssertionError("ZipFile.extract must not be called"),
            ) as extracted,
        ):
            for label, path, expected in cases:
                with self.subTest(label=label):
                    self.assertEqual(active_content_types(path), expected)
        opened.assert_not_called()
        read.assert_not_called()
        extracted.assert_not_called()

    def test_ut_act_04_03_empty_and_missing_files_are_clean(self) -> None:
        """UT-ACT-04.03: an empty file and a missing path return () without raising."""
        empty = samples.write_sample(self.root, "empty.bin", b"")
        self.assertEqual(active_content_types(empty), ())
        self.assertEqual(active_content_types(self.root / "missing.bin"), ())

    def test_ut_act_04_04_result_is_deterministic(self) -> None:
        """UT-ACT-04.04: two calls on the same file return the same result."""
        path = samples.write_zip(
            self.root,
            "deterministic.zip",
            [("vbaProject.bin", b""), ("docs/invoice.pdf.exe", b"")],
        )
        first = active_content_types(path)
        second = active_content_types(path)
        self.assertEqual(first, second)
        self.assertEqual(first, ("office-macros", "archive-executable"))


def _zip_bytes(entries: list[tuple[str, bytes]]) -> bytes:
    """Build a ZIP archive in memory."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, payload in entries:
            archive.writestr(name, payload)
    return buffer.getvalue()


_PDF_WITH_JAVASCRIPT = samples.pdf_bytes(b"/JavaScript ")
_ZIP_WITH_EXECUTABLE = _zip_bytes([("factura.pdf.exe", b"")])


def _rows(*names: str, payloads: dict[int, bytes]) -> list[dict[str, object]]:
    """Metadata rows with the byte length of each payload."""
    return [
        {
            "index": index,
            "name": name,
            "size_bytes": len(payloads[index]),
            "native_order_key": str(index),
            "unavailable_reason": None,
        }
        for index, name in enumerate(names, start=1)
    ]


class AttachmentActiveContentWarningTests(AttachmentTestBase):
    """UT-ACT-05: ``W_ATTACHMENT_ACTIVE_CONTENT`` in the ``attachment`` response."""

    UID = "apple_mail:83143"

    def _active_backend(self, **kwargs):
        rows = kwargs.pop(
            "attachments",
            _rows(
                "factura.pdf",
                "docs.zip",
                payloads={1: _PDF_WITH_JAVASCRIPT, 2: _ZIP_WITH_EXECUTABLE},
            ),
        )
        return self.attachment_backend(
            attachments=rows,
            stream_chunks={
                1: [_PDF_WITH_JAVASCRIPT],
                2: [_ZIP_WITH_EXECUTABLE],
            },
            **kwargs,
        )

    def test_ut_act_05_01_one_warning_per_attachment_and_type_in_order(self) -> None:
        """UT-ACT-05.01: a PDF with JavaScript and a ZIP with an executable warn in order."""
        backend = self._active_backend()
        code, stdout, stderr = self.run_attachment(
            ["attachment", self.UID, "--all"], backend
        )
        self.assertEqual((code, stderr), (0, ""))
        payload = self.json_object(stdout)
        self.assertEqual(
            payload["warnings"],
            [
                "W_ATTACHMENT_ACTIVE_CONTENT: attachment 1 contains pdf-javascript "
                f"in {self.UID}",
                "W_ATTACHMENT_ACTIVE_CONTENT: attachment 2 contains archive-executable "
                f"in {self.UID}",
            ],
        )
        self.assertEqual(payload["count"], 2)
        for entry in payload["attachments"]:
            self.assertTrue(Path(entry["path"]).is_file())

    def test_ut_act_05_02_warnings_repeat_when_served_from_the_cache(self) -> None:
        """UT-ACT-05.02: the second run serves the cache and emits the same warnings."""
        backend = self._active_backend()
        self.run_attachment(["attachment", self.UID, "--all"], backend)
        code, stdout, stderr = self.run_attachment(
            ["attachment", self.UID, "--all"], backend
        )
        self.assertEqual((code, stderr), (0, ""))
        payload = self.json_object(stdout)
        self.assertEqual(
            [entry["cached"] for entry in payload["attachments"]], [True, True]
        )
        self.assertEqual(
            [warning.split(": ", 1)[1] for warning in payload["warnings"]],
            [
                f"attachment 1 contains pdf-javascript in {self.UID}",
                f"attachment 2 contains archive-executable in {self.UID}",
            ],
        )

    def test_ut_act_05_03_no_file_names_and_no_warning_without_markers(self) -> None:
        """UT-ACT-05.03: the detail carries no file names; a clean attachment warns nothing."""
        backend = self._active_backend()
        _code, stdout, _stderr = self.run_attachment(
            ["attachment", self.UID, "--all"], backend
        )
        warnings = self.json_object(stdout)["warnings"]
        for forbidden in ("factura.pdf", "docs.zip", "factura", "docs"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, "\n".join(warnings))

        clean = b"%PDF-1.7\n1 0 obj << /Type /Catalog >> endobj\n"
        clean_backend = self.attachment_backend(
            attachments=[
                {
                    "index": 1,
                    "name": "notes.pdf",
                    "size_bytes": len(clean),
                    "native_order_key": "1",
                    "unavailable_reason": None,
                }
            ],
            stream_chunks={1: [clean]},
        )
        code, stdout, _stderr = self.run_attachment(
            ["attachment", self.UID, "--index", "1"], clean_backend
        )
        self.assertEqual(code, 0)
        self.assertEqual(self.json_object(stdout)["warnings"], [])

    def test_ut_act_05_04_blocked_attachment_never_reaches_the_warning(self) -> None:
        """UT-ACT-05.04: a catalog-blocked attachment keeps E_ATTACHMENT_BLOCKED (exit 4)."""
        backend = self.attachment_backend(
            attachments=[
                {
                    "index": 1,
                    "name": "install.sh",
                    "size_bytes": 17,
                    "native_order_key": "1",
                    "unavailable_reason": None,
                }
            ]
        )
        self.assert_error(
            4,
            self.run_attachment(["attachment", self.UID, "--index", "1"], backend),
            "E_ATTACHMENT_BLOCKED",
            "attachment",
        )

    def test_ut_act_05_05_remote_driver_warns_like_a_local_one(self) -> None:
        """UT-ACT-05.05: a ``"remote"`` plugin emits the same warning as a local driver."""
        capabilities = {
            "network": True,
            "readonly": "promise",
            "body_local": False,
            "attachments": "remote",
            "native_order": "text",
        }
        backend = self.plugin_backend(
            native_uid=_ATTACHMENT_PLUGIN_UID,
            capabilities=capabilities,
            attachments=_rows(
                "factura.pdf", payloads={1: _PDF_WITH_JAVASCRIPT}
            ),
            stream_chunks={1: [_PDF_WITH_JAVASCRIPT]},
        )
        uid = f"{ATTACHMENT_PLUGIN_DRIVER}:{_ATTACHMENT_PLUGIN_UID}"
        _entry, result = self.run_plugin(
            ["attachment", uid, "--index", "1"],
            backend,
            config=_attachment_scope(
                driver=ATTACHMENT_PLUGIN_DRIVER, account=_ATTACHMENT_PLUGIN_LABEL
            ),
        )
        code, stdout, stderr = result
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(
            self.json_object(stdout)["warnings"],
            [f"W_ATTACHMENT_ACTIVE_CONTENT: attachment 1 contains pdf-javascript in {uid}"],
        )

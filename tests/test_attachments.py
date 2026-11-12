"""UT-ATT-01..05: attachment blocking, sanitization and cache paths.

Pure-core tests for the attachment policy: the dangerous-extension catalog,
the name rules (PRD §10.3.1 point 1), the magic-byte rules (PRD §10.3.1 point 2), the
whole-message screening order, the deterministic ``sanitized_name`` (PRD §10.3.3),
the cache path and the availability reasons (AC-09/AC-10/AC-11/AC-15).

Nothing here writes files or opens cached paths: these tests cover the
policy that the cache/staging engine and ``show``/``attachment`` consume.
"""

from __future__ import annotations

import ast
import contextlib
import errno
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path
from unittest import mock

import mailquery.attachments.cache as attachment_cache
from mailquery.attachments import (
    BLOCKED_CODE,
    CATALOG,
    CONTENT_BLOCK_DETAIL,
    CONTENT_INSPECTION_BYTES,
    DANGEROUS_EXTENSIONS,
    DISPLAY_NAME_MAX_BYTES,
    MAX_EXTENSION_BYTES,
    MAX_NAME_BYTES,
    MAX_SANITIZED_BYTES,
    NAME_BLOCK_DETAIL,
    UNAVAILABLE_CODE,
    UNREADABLE_CODE,
    WINDOWS_PATH_BUDGET_BYTES,
    AttachmentsEngine,
    attachment_path,
    cache_root,
    cached_path,
    classify_content,
    classify_name,
    dangerous_extension,
    display_name,
    is_dangerous_extension,
    is_reserved_name,
    message_dir,
    normalize_name,
    read_first_block,
    sanitize_name,
    screen_content,
    screen_names,
    truncate_utf8,
)
from mailquery.config import AttachmentsConfig
from mailquery.errors import MailqueryError
from mailquery.uid import stable_identifier

from tests.fakes.attachment_driver import (
    DriverFailure,
    FakeAttachment,
    FakeAttachmentDriver,
    chunks_of,
)
from tests.fixtures import attachment_samples as samples

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
ATTACHMENTS_ROOT = SRC_ROOT / "mailquery" / "attachments"

_CONTROL_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co"})
_DANGEROUS_FILE_REASONS = frozenset(
    {
        "control_character",
        "path_separator",
        "parent_segment",
        "drive_prefix",
        "alternate_data_stream",
        "dangerous_extension",
        "reserved_name",
    }
)


def _has_control(text: str) -> bool:
    return any(unicodedata.category(char) in _CONTROL_CATEGORIES for char in text)


def _imported_roots(path: Path) -> list[tuple[str, int]]:
    """Return ``(top-level module, line)`` for every absolute import of ``path``."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((alias.name.split(".")[0], node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.append((node.module.split(".")[0], node.lineno))
    return found


def _imported_modules(path: Path) -> list[str]:
    """Return every absolute dotted module imported by ``path``."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.append(node.module)
            found.extend(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def _screen_message(
    rows: list[dict],
    requested: list[int] | None,
    streams: dict[int, bytes],
) -> "object":
    """Model the engine order names -> content (limits live between them in the engine)."""

    def open_stream(index: int):
        return [streams[index]]

    names = screen_names(rows)
    if names.failed:
        return names
    return screen_content(rows, requested, open_stream)


class AttachmentNameBlockingTests(unittest.TestCase):
    """UT-ATT-01: name blocking (PRD §10.3.1 point 1, §10.3.2, AC-10)."""

    def test_ut_att_01_01_catalog_blocks_every_extension_by_category(self) -> None:
        """UT-ATT-01.01: every PRD §10.3.2 extension blocks, per category."""
        self.assertEqual(set(CATALOG), set(samples.EXPECTED_CATALOG))
        expected_all: set[str] = set()
        for category, extensions in samples.EXPECTED_CATALOG.items():
            self.assertEqual(CATALOG[category], extensions)
            expected_all.update(extensions)
            for extension in extensions:
                with self.subTest(category=category, extension=extension):
                    decision = classify_name(f"invoice{extension}")
                    self.assertTrue(decision.blocked)
                    self.assertEqual(decision.reason, "dangerous_extension")
                    self.assertEqual(decision.extension, extension)
                    self.assertEqual(decision.category, category)
                    self.assertEqual(decision.detail, NAME_BLOCK_DETAIL)
                    self.assertEqual(
                        dangerous_extension(f"invoice{extension}"),
                        (extension, category),
                    )
                    self.assertTrue(is_dangerous_extension(f"INVOICE{extension.upper()}"))
        self.assertEqual(DANGEROUS_EXTENSIONS, frozenset(expected_all))
        self.assertEqual(len(DANGEROUS_EXTENSIONS), 82)

    def test_ut_att_01_02_chained_extensions_block(self) -> None:
        """UT-ATT-01.02: ``factura.pdf.exe`` and ``reporte.pdf.bat.cmd`` block."""
        for name in samples.CHAINED_EXTENSION_NAMES:
            with self.subTest(name=name):
                decision = classify_name(name)
                self.assertTrue(decision.blocked)
                self.assertEqual(decision.reason, "dangerous_extension")
                self.assertIn(decision.extension, DANGEROUS_EXTENSIONS)

    def test_ut_att_01_03_traversal_drive_prefix_and_ads_block(self) -> None:
        """UT-ATT-01.03: separators, ``..`` segments, ``C:`` and any ``:`` block."""
        for name, expected_reason in samples.TRAVERSAL_NAMES.items():
            with self.subTest(name=name):
                decision = classify_name(name)
                self.assertTrue(decision.blocked)
                self.assertEqual(decision.reason, expected_reason)
                self.assertIn(decision.reason, _DANGEROUS_FILE_REASONS)

    def test_ut_att_01_04_raw_control_characters_block(self) -> None:
        """UT-ATT-01.04: NUL and ``Cc``/``Cf``/``Cs``/``Co`` in the raw form block."""
        for name, description in samples.CONTROL_NAMES.items():
            with self.subTest(category=description):
                decision = classify_name(name)
                self.assertTrue(decision.blocked)
                self.assertEqual(decision.reason, "control_character")
                self.assertEqual(decision.detail, NAME_BLOCK_DETAIL)

    def test_ut_att_01_05_windows_reserved_names_block(self) -> None:
        """UT-ATT-01.05: CON/PRN/AUX/NUL/COM1..9/LPT1..9 (root before first dot)."""
        for name in samples.RESERVED_NAMES:
            with self.subTest(name=name):
                decision = classify_name(name)
                self.assertTrue(decision.blocked)
                self.assertEqual(decision.reason, "reserved_name")
                self.assertTrue(is_reserved_name(name))
        for name in samples.NON_RESERVED_NAMES:
            with self.subTest(name=name):
                self.assertFalse(classify_name(name).blocked)
                self.assertFalse(is_reserved_name(name))

    def test_ut_att_01_06_nfkc_variants_normalize_once_into_a_rule(self) -> None:
        """UT-ATT-01.06: fullwidth/ligature variants normalize once into a rule."""
        for name, expected_reason in samples.NFKC_NAMES.items():
            with self.subTest(name=name):
                decision = classify_name(name)
                self.assertTrue(decision.blocked)
                self.assertEqual(decision.reason, expected_reason)
                self.assertEqual(decision.normalized_name, unicodedata.normalize("NFKC", name))
        # A single NFKC pass is applied: the reported form is exactly one pass.
        fullwidth = "\uff23\uff2f\uff2e"
        self.assertEqual(normalize_name(fullwidth), "CON")
        self.assertEqual(classify_name(fullwidth).normalized_name, "CON")
        ligature = "e\ufb03cient.pdf"
        single_pass = unicodedata.normalize("NFKC", ligature)
        self.assertEqual(single_pass, "efficient.pdf")
        decision = classify_name(ligature)
        self.assertFalse(decision.blocked)
        self.assertEqual(decision.normalized_name, single_pass)

    def test_ut_att_01_07_safe_names_are_allowed(self) -> None:
        """UT-ATT-01.07: the PRD §10.3.2/§10.3.3 allowed examples pass the name screen."""
        for name in samples.SAFE_NAMES:
            with self.subTest(name=name):
                decision = classify_name(name)
                self.assertFalse(decision.blocked)
                self.assertIsNone(decision.reason)
                self.assertIsNone(decision.detail)
                self.assertIsNone(decision.category)
                self.assertEqual(decision.normalized_name, unicodedata.normalize("NFKC", name))

    def test_ut_att_01_08_empty_or_blank_names_do_not_block(self) -> None:
        """UT-ATT-01.08: empty/space-only/dot-only names defer to sanitization."""
        for name in ("", " ", "   ", "...", ". .", " . . "):
            with self.subTest(name=name):
                decision = classify_name(name)
                self.assertFalse(decision.blocked)
                self.assertIsNone(decision.reason)
                self.assertEqual(sanitize_name(name, 1), "01_attachment")

    def test_ut_att_01_09_attachments_package_imports_only_stdlib_and_mailquery(self) -> None:
        """UT-ATT-01.09: ``attachments/**`` uses stdlib + own package only (RNF-12)."""
        files = sorted(ATTACHMENTS_ROOT.rglob("*.py"))
        self.assertTrue(files, f"no sources found under {ATTACHMENTS_ROOT}")
        allowed = set(sys.stdlib_module_names) | {"mailquery"}
        offenders: list[str] = []
        for path in files:
            for root, line in _imported_roots(path):
                if root not in allowed:
                    offenders.append(f"{path.name}:{line} imports {root}")
            # The pure core must not reach into cache/command/backend modules.
            forbidden = {
                "mailquery.backends",
                "mailquery.cli",
                "mailquery.config",
                "mailquery.emlx",
                "mailquery.plugins",
                "mailquery.search",
                "mailquery.state",
                "mailquery.store",
            }
            for module in _imported_modules(path):
                if module in forbidden:
                    offenders.append(f"{path.name} imports {module}")
        self.assertEqual(offenders, [])


class AttachmentContentBlockingTests(unittest.TestCase):
    """UT-ATT-02: magic-byte blocking (PRD §10.3.1 point 2, AC-10)."""

    def test_ut_att_02_01_magic_bytes_of_executables_block(self) -> None:
        """UT-ATT-02.01: MZ, ELF, the four Mach-O variants, universal and ``#!`` block."""
        for name, (data, expected_signature) in samples.BLOCKED_CONTENT_SAMPLES.items():
            with self.subTest(sample=name):
                decision = classify_content(data)
                self.assertTrue(decision.blocked)
                self.assertEqual(decision.reason, "executable_content")
                self.assertEqual(decision.signature, expected_signature)
                self.assertEqual(decision.detail, CONTENT_BLOCK_DETAIL)
        rows = samples.entries("presupuesto.pdf")
        stream = screen_content(rows, [1], lambda index: [samples.mz_bytes()])
        self.assertTrue(stream.blocked)
        self.assertEqual(stream.code, BLOCKED_CODE)
        self.assertEqual(stream.index, 1)
        self.assertEqual(stream.name, "presupuesto.pdf")
        self.assertEqual(stream.detail, CONTENT_BLOCK_DETAIL)

    def test_ut_att_02_02_signature_only_counts_at_offset_zero_and_reads_512(self) -> None:
        """UT-ATT-02.02: signature at offset 8 does not block; at most 512 bytes read."""
        self.assertFalse(classify_content(b"\x00" * 8 + samples.mz_bytes()).blocked)
        self.assertFalse(classify_content(samples.pdf_bytes() + samples.mz_bytes()).blocked)
        rows = samples.entries("invoice.pdf")
        decision = screen_content(
            rows,
            [1],
            lambda index: [b"%PDF-1.7\n", b"\x00" * 8, b"MZ\x90\x00"],
        )
        self.assertTrue(decision.ok, decision)
        counting = samples.CountingStream(samples.pdf_bytes() + b"\x00" * 4096, chunk_size=1)
        block = read_first_block(counting)
        self.assertEqual(len(block), CONTENT_INSPECTION_BYTES)
        self.assertEqual(counting.bytes_yielded, CONTENT_INSPECTION_BYTES)
        self.assertTrue(counting.closed)
        self.assertEqual(read_first_block([b"%PDF"]), b"%PDF")
        self.assertEqual(read_first_block([b""]), b"")
        self.assertEqual(len(read_first_block([b"A" * 2048])), CONTENT_INSPECTION_BYTES)

    def test_ut_att_02_03_empty_stream_is_valid(self) -> None:
        """UT-ATT-02.03: a zero-byte stream has no signature and passes."""
        self.assertFalse(classify_content(samples.empty_bytes()).blocked)
        self.assertIsNone(classify_content(samples.empty_bytes()).signature)
        self.assertEqual(read_first_block(iter([])), b"")
        rows = samples.entries("empty.txt")
        decision = screen_content(rows, [1], lambda index: [samples.empty_bytes()])
        self.assertTrue(decision.ok, decision)

    def test_ut_att_02_04_non_blocklisted_formats_pass(self) -> None:
        """UT-ATT-02.04: PDF, ZIP, OLE, PNG and text are not in the catalog."""
        rows = samples.entries(*(f"sample-{name}" for name in samples.SAFE_CONTENT_SAMPLES))
        for name, data in samples.SAFE_CONTENT_SAMPLES.items():
            with self.subTest(sample=name):
                decision = classify_content(data)
                self.assertFalse(decision.blocked)
                self.assertIsNone(decision.signature)
        decision = screen_content(
            rows,
            None,
            lambda index: [list(samples.SAFE_CONTENT_SAMPLES.values())[index - 1]],
        )
        self.assertTrue(decision.ok, decision)

    def test_ut_att_02_05_unreadable_stream_is_unreadable_not_blocked(self) -> None:
        """UT-ATT-02.05: a stream that cannot be read is ``E_ATTACHMENT_UNREADABLE``."""
        rows = samples.entries("presupuesto.pdf")

        def broken_open(index: int):
            raise OSError("cannot open attachment stream")

        decision = screen_content(rows, [1], broken_open)
        self.assertFalse(decision.ok)
        self.assertFalse(decision.blocked)
        self.assertEqual(decision.code, UNREADABLE_CODE)
        self.assertEqual(decision.reason, "unreadable")
        self.assertEqual((decision.index, decision.name), (1, "presupuesto.pdf"))

        def broken_iteration(index: int):
            yield b"%PDF-1.7"
            raise RuntimeError("stream blew up")

        decision = screen_content(rows, [1], broken_iteration)
        self.assertEqual(decision.code, UNREADABLE_CODE)
        self.assertEqual(decision.reason, "unreadable")

        def wrong_type(index: int):
            yield "not bytes"  # type: ignore[misc]

        decision = screen_content(rows, [1], wrong_type)
        self.assertEqual(decision.code, UNREADABLE_CODE)


class AttachmentMessageScreeningTests(unittest.TestCase):
    """UT-ATT-03: whole-message screening (PRD §10.3.1, RF-48, AC-09)."""

    def test_ut_att_03_01_hostile_name_blocks_whole_message(self) -> None:
        """UT-ATT-03.01: safe or hostile ``--index`` and ``--all`` all block."""
        rows = samples.entries("Factura Octubre 2026.pdf", "notas.txt", "CON.fdp.exe")
        streams = {
            1: samples.pdf_bytes(),
            2: samples.text_bytes(),
            3: samples.pdf_bytes(),
        }
        for requested in ([1], [3], None):
            with self.subTest(requested=requested):
                decision = _screen_message(rows, requested, streams)
                self.assertTrue(decision.blocked)
                self.assertEqual(decision.code, BLOCKED_CODE)
                self.assertEqual(decision.index, 3)
                self.assertEqual(decision.name, "CON.fdp.exe")
                self.assertEqual(decision.detail, NAME_BLOCK_DETAIL)

    def test_ut_att_03_02_content_block_in_one_requested_blocks_the_rest(self) -> None:
        """UT-ATT-03.02: executable content of one requested blocks all requested."""
        rows = samples.entries("safe.pdf", "hostile.pdf", "other.pdf")
        streams = {
            1: samples.pdf_bytes(),
            2: samples.mz_bytes(),
            3: samples.pdf_bytes(),
        }
        decision = _screen_message(rows, [1, 2, 3], streams)
        self.assertTrue(decision.blocked)
        self.assertEqual((decision.index, decision.name), (2, "hostile.pdf"))
        self.assertEqual(decision.detail, CONTENT_BLOCK_DETAIL)
        # Requesting only safe attachments does not inspect the hostile content.
        decision = _screen_message(rows, [1, 3], streams)
        self.assertTrue(decision.ok, decision)
        self.assertTrue(_screen_message(rows, [2], streams).blocked)

    def test_ut_att_03_03_block_decision_names_the_attachment_without_controls(self) -> None:
        """UT-ATT-03.03: index/name are reported and the message has no controls."""
        hostile = "../Users/.ssh/CON.\u202efdp.exe"
        rows = samples.entries("safe.pdf", "notes.txt", hostile)
        decision = _screen_message(rows, None, {1: samples.pdf_bytes(), 2: samples.text_bytes(), 3: samples.pdf_bytes()})
        self.assertEqual((decision.index, decision.name), (3, hostile))
        message = f"attachment {decision.index} ('{display_name(decision.name)}') {decision.detail}"
        self.assertEqual(
            message,
            "attachment 3 ('CON.fdp.exe') has a dangerous filename pattern",
        )
        self.assertFalse(_has_control(message))
        self.assertNotIn("\u202e", message)
        self.assertNotIn("/", message)
        self.assertNotIn("..", message)
        long_name = "a" * 300 + ".pdf"
        shown = display_name(long_name)
        self.assertLessEqual(len(shown.encode("utf-8")), DISPLAY_NAME_MAX_BYTES)
        shown.encode("utf-8")  # no split character: still valid UTF-8

    def test_ut_att_03_04_all_safe_returns_the_requested_extraction_plan(self) -> None:
        """UT-ATT-03.04: all-safe message yields the plan for the requested indexes."""
        rows = samples.entries("factura.pdf", "notas.txt", "presupuesto.docx")
        streams = {
            1: samples.pdf_bytes(),
            2: samples.text_bytes(),
            3: samples.pdf_bytes(),
        }
        opened: list[int] = []

        def open_stream(index: int):
            opened.append(index)
            return [streams[index]]

        names = screen_names(rows)
        self.assertTrue(names.ok, names)
        decision = screen_content(rows, [1, 3], open_stream)
        self.assertTrue(decision.ok, decision)
        self.assertEqual(opened, [1, 3])
        requested = [1, 3]
        plan = [
            {
                "index": index,
                "original_name": rows[index - 1]["name"],
                "sanitized_name": sanitize_name(rows[index - 1]["name"], index),
            }
            for index in requested
        ]
        self.assertEqual(
            plan,
            [
                {"index": 1, "original_name": "factura.pdf", "sanitized_name": "01_factura.pdf"},
                {"index": 3, "original_name": "presupuesto.docx", "sanitized_name": "03_presupuesto.docx"},
            ],
        )

    def test_ut_att_03_05_unrequested_content_is_not_inspected(self) -> None:
        """UT-ATT-03.05: only the requested indexes are opened for content."""
        rows = samples.entries("unrequested.pdf", "requested.pdf")
        rows[0]["unavailable_reason"] = None
        opened: list[int] = []

        def open_stream(index: int):
            opened.append(index)
            return [samples.mz_bytes() if index == 1 else samples.pdf_bytes()]

        decision = screen_content(rows, [2], open_stream)
        self.assertTrue(decision.ok, decision)
        self.assertEqual(opened, [2])
        # An unrequested unavailable attachment is not evaluated either.
        rows[0]["unavailable_reason"] = "not_local"
        opened.clear()
        decision = screen_content(rows, [2], open_stream)
        self.assertTrue(decision.ok, decision)
        self.assertEqual(opened, [2])

    def test_ut_att_03_06_screening_never_opens_or_writes_paths(self) -> None:
        """UT-ATT-03.06: name/content screening and path math touch no file."""
        rows = samples.entries("Factura Octubre 2026.pdf", "reporte_2026.xlsx")
        mutators = {
            "builtins.open": mock.DEFAULT,
            "io.open": mock.DEFAULT,
            "os.open": mock.DEFAULT,
            "os.mkdir": mock.DEFAULT,
            "os.makedirs": mock.DEFAULT,
            "os.remove": mock.DEFAULT,
            "os.rename": mock.DEFAULT,
            "os.replace": mock.DEFAULT,
            "os.symlink": mock.DEFAULT,
            "pathlib.Path.open": mock.DEFAULT,
            "pathlib.Path.mkdir": mock.DEFAULT,
            "pathlib.Path.touch": mock.DEFAULT,
            "pathlib.Path.write_bytes": mock.DEFAULT,
            "pathlib.Path.write_text": mock.DEFAULT,
        }
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            with contextlib.ExitStack() as stack:
                for target in mutators:
                    stack.enter_context(
                        mock.patch(target, side_effect=AssertionError(f"{target} must not be called"))
                    )
                self.assertTrue(screen_names(rows).ok)
                self.assertTrue(
                    screen_content(rows, None, lambda index: [samples.pdf_bytes()]).ok
                )
                sanitized = sanitize_name(rows[0]["name"], 1)
                display_name(rows[0]["name"])
                message_dir(home, "apple_mail:83143")
                attachment_path(home, "apple_mail:83143", sanitized)
            self.assertEqual(list(home.iterdir()), [])


class AttachmentSanitizeAndPathTests(unittest.TestCase):
    """UT-ATT-04: ``sanitized_name`` and cache path (PRD §10.3.3, AC-11)."""

    def test_ut_att_04_01_normative_examples(self) -> None:
        """UT-ATT-04.01: `` invoice.pdf `` => 01_invoice.pdf; the PRD §10.3.3 examples."""
        for original, index, expected in samples.SANITIZE_CASES:
            with self.subTest(original=original, index=index):
                self.assertEqual(sanitize_name(original, index), expected)

    def test_ut_att_04_02_nfkc_trim_dotfiles_and_substitutions(self) -> None:
        """UT-ATT-04.02: NFKC, trim/dotfile removal, non-collapsing substitutions."""
        self.assertEqual(sanitize_name("re\u0301sume\u0301.pdf", 1), "01_résumé.pdf")
        self.assertEqual(sanitize_name("\uff26\uff41\uff43\uff54\uff55\uff52\uff41.pdf", 1), "01_Factura.pdf")
        self.assertEqual(sanitize_name("  invoice.pdf  ", 1), "01_invoice.pdf")
        self.assertEqual(sanitize_name("invoice.pdf...", 1), "01_invoice.pdf")
        self.assertEqual(sanitize_name(".env", 1), "01_env")
        self.assertEqual(sanitize_name("..config", 1), "01_config")
        self.assertEqual(sanitize_name(".hidden.txt", 1), "01_hidden.txt")
        self.assertEqual(
            sanitize_name('a<b>c:d"e/f\\g|h?i*j k.pdf', 1),
            "01_a_b_c_d_e_f_g_h_i_j_k.pdf",
        )
        # Replacements are not collapsed.
        self.assertEqual(sanitize_name("a  b<>c.pdf", 1), "01_a__b__c.pdf")
        for name in ("", "   ", "...", ". ."):
            with self.subTest(name=name):
                self.assertEqual(sanitize_name(name, 1), "01_attachment")

    def test_ut_att_04_03_byte_limits_and_prefix_budget(self) -> None:
        """UT-ATT-04.03: extension <= 20, name <= 150, final <= 153, index >= 100."""
        long_extension = sanitize_name("x." + "e" * 100, 1)
        extension = long_extension[long_extension.index(".") :]
        self.assertEqual(extension, "." + "e" * (MAX_EXTENSION_BYTES - 1))
        self.assertLessEqual(len(extension.encode("utf-8")), MAX_EXTENSION_BYTES)

        multibyte_extension = sanitize_name("x." + "é" * 20, 1)
        extension = multibyte_extension[multibyte_extension.index(".") :]
        self.assertEqual(extension, "." + "é" * 9)  # 1 + 9*2 = 19 bytes, no split
        self.assertLessEqual(len(extension.encode("utf-8")), MAX_EXTENSION_BYTES)
        extension.encode("utf-8")

        long_root = sanitize_name("é" * 100 + ".pdf", 1)
        self.assertEqual(long_root, "01_" + "é" * 73 + ".pdf")
        self.assertEqual(len(long_root.encode("utf-8")), MAX_SANITIZED_BYTES)
        name_without_prefix = long_root[3:]
        self.assertEqual(len(name_without_prefix.encode("utf-8")), MAX_NAME_BYTES)

        ascii_root = "a" * 300 + ".pdf"
        final_100 = sanitize_name(ascii_root, 100)
        final_1000 = sanitize_name(ascii_root, 1000)
        self.assertTrue(final_100.startswith("100_"))
        self.assertTrue(final_1000.startswith("1000_"))
        self.assertEqual(len(final_100.encode("utf-8")), MAX_SANITIZED_BYTES)
        self.assertEqual(len(final_1000.encode("utf-8")), MAX_SANITIZED_BYTES)
        self.assertEqual(len(final_100[4:].encode("utf-8")), MAX_NAME_BYTES - 1)
        self.assertEqual(len(final_1000[5:].encode("utf-8")), MAX_NAME_BYTES - 2)

    def test_ut_att_04_04_deterministic_and_never_double_prefixed(self) -> None:
        """UT-ATT-04.04: same input => same name; the path does not re-add ``NN_``."""
        first = sanitize_name("Factura Octubre 2026.pdf", 2)
        second = sanitize_name("Factura Octubre 2026.pdf", 2)
        self.assertEqual(first, "02_Factura_Octubre_2026.pdf")
        self.assertEqual(first, second)
        with tempfile.TemporaryDirectory() as tmp:
            path = attachment_path(Path(tmp), "apple_mail:83143", first)
            self.assertEqual(path.name, first)
            self.assertEqual(str(path).count("02_"), 1)
            self.assertEqual(truncate_utf8("123456789", 5), "12345")
            self.assertEqual(truncate_utf8("ééé", 3), "é")
            self.assertEqual(truncate_utf8("abc", 0), "")

    def test_ut_att_04_05_cache_path_has_a_single_nn_prefix(self) -> None:
        """UT-ATT-04.05: ``<home>/attachments/<driver>/<native_id>/<sanitized_name>``."""
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            sanitized = sanitize_name(" invoice.pdf ", 1)
            path = attachment_path(home, "apple_mail:83143", sanitized)
            self.assertEqual(cache_root(home), home / "attachments")
            self.assertEqual(
                path,
                home / "attachments" / "apple_mail" / "83143" / "01_invoice.pdf",
            )
            self.assertEqual(path.parent, message_dir(home, "apple_mail:83143"))
            self.assertEqual(path.name, "01_invoice.pdf")
            self.assertEqual(str(path).count("01_"), 1)

    def test_ut_att_04_06_long_path_and_component_fall_back_to_stable_id(self) -> None:
        """UT-ATT-04.06: long path/native id => 32-hex ``SHA-256(uid)`` component."""
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            long_uid = "apple_mail:" + "a" * 600
            expected = home / "attachments" / "apple_mail" / stable_identifier(long_uid)
            self.assertEqual(message_dir(home, long_uid), expected)
            self.assertEqual(
                attachment_path(home, long_uid, sanitize_name("invoice.pdf", 1)),
                expected / "01_invoice.pdf",
            )
            identifier = stable_identifier(long_uid)
            self.assertRegex(identifier, r"^[0-9a-f]{32}$")
            self.assertEqual(identifier, hashlib.sha256(long_uid.encode("utf-8")).hexdigest()[:32])
            self.assertNotIn(".", identifier)
            self.assertNotIn(" ", identifier)

            # Windows uses the conservative 240-byte path budget.
            windows_home = Path("/tmp") / ("h" * 170)
            self.assertGreater(
                len(str(windows_home / "attachments" / "apple_mail" / "83143").encode("utf-8"))
                + 1
                + MAX_SANITIZED_BYTES,
                WINDOWS_PATH_BUDGET_BYTES,
            )
            windows_dir = message_dir(windows_home, "apple_mail:83143", platform="win32")
            self.assertEqual(windows_dir.name, stable_identifier("apple_mail:83143"))
            self.assertEqual(
                message_dir(windows_home, "apple_mail:83143", platform="win32"),
                windows_dir,
            )
            # The reserved filename budget is what makes the directory choice stable.
            self.assertEqual(
                attachment_path(
                    windows_home, "apple_mail:83143", "02_Factura.pdf", platform="win32"
                ).parent,
                windows_dir,
            )
            # Short paths keep the native id on every platform.
            short_home = Path("/") / "mq"
            self.assertEqual(
                message_dir(short_home, "apple_mail:83143").name,
                "83143",
            )
            self.assertEqual(
                attachment_path(short_home, "apple_mail:83143", "01_invoice.pdf").parent.name,
                "83143",
            )
            # A POSIX path over the real PATH_MAX also falls back.
            deep_home = Path(tmp) / "/".join(["a" * 200] * 20)
            self.assertEqual(
                message_dir(deep_home, "apple_mail:83143").name,
                stable_identifier("apple_mail:83143"),
            )

    def test_ut_att_04_07_index_prefixes(self) -> None:
        """UT-ATT-04.07: indexes 1, 9, 99, 100 and 1000 use ``NN_``/``NNN_``."""
        cases = {
            1: "01_",
            9: "09_",
            99: "99_",
            100: "100_",
            1000: "1000_",
        }
        name = "a" * 300 + ".pdf"
        for index, prefix in cases.items():
            with self.subTest(index=index):
                sanitized = sanitize_name(name, index)
                self.assertTrue(sanitized.startswith(prefix))
                self.assertLessEqual(len(sanitized.encode("utf-8")), MAX_SANITIZED_BYTES)
                self.assertLessEqual(
                    len(sanitized[len(prefix) :].encode("utf-8")), MAX_NAME_BYTES
                )


class AttachmentAvailabilityTests(unittest.TestCase):
    """UT-ATT-05: availability and stream errors (PRD §12.11 rows 8/14, AC-15)."""

    def test_ut_att_05_01_unavailable_reasons_map_to_unavailable(self) -> None:
        """UT-ATT-05.01: ``not_local``/``not_downloaded``/``unsupported``/``network``."""
        for reason in ("not_local", "not_downloaded", "unsupported", "network"):
            rows = [samples.entry(1, "Factura Octubre 2026.pdf", unavailable_reason=reason)]
            opened: list[int] = []

            def open_stream(index: int, _opened=opened):
                _opened.append(index)
                return [samples.pdf_bytes()]

            decision = screen_content(rows, [1], open_stream)
            with self.subTest(reason=reason):
                self.assertFalse(decision.blocked)
                self.assertEqual(decision.code, UNAVAILABLE_CODE)
                self.assertEqual(decision.reason, reason)
                self.assertEqual((decision.index, decision.name), (1, "Factura Octubre 2026.pdf"))
                self.assertEqual(opened, [])

    def test_ut_att_05_02_unreadable_reasons_and_empty_lists(self) -> None:
        """UT-ATT-05.02: corrupt/S/MIME/unreadable reasons; an empty list is not a block."""
        for reason in ("corrupt", "smime", "unreadable"):
            rows = [samples.entry(1, "documento.pdf", unavailable_reason=reason)]
            decision = screen_content(rows, [1], lambda index: [samples.pdf_bytes()])
            with self.subTest(reason=reason):
                self.assertFalse(decision.blocked)
                self.assertEqual(decision.code, UNREADABLE_CODE)
                self.assertEqual(decision.reason, reason)
                self.assertEqual((decision.index, decision.name), (1, "documento.pdf"))
        # The driver may propagate the reason with an empty list; the screen
        # functions must not turn "no entries" into a block or an error.
        self.assertTrue(screen_names([]).ok)
        self.assertTrue(screen_content([], [], lambda index: [samples.pdf_bytes()]).ok)
        self.assertTrue(screen_content([], None, lambda index: [samples.pdf_bytes()]).ok)

    def test_ut_att_05_03_stream_read_error_is_unreadable(self) -> None:
        """UT-ATT-05.03: a requested stream read error is ``E_ATTACHMENT_UNREADABLE``."""
        rows = samples.entries("presupuesto.pdf")

        def permission_error(index: int):
            raise PermissionError("read denied")

        decision = screen_content(rows, [1], permission_error)
        self.assertFalse(decision.blocked)
        self.assertEqual(decision.code, UNREADABLE_CODE)
        self.assertEqual(decision.reason, "unreadable")
        self.assertEqual((decision.index, decision.name), (1, "presupuesto.pdf"))

        def fails_after_first_chunk(index: int):
            yield samples.pdf_bytes()[:8]
            raise OSError("device disappeared")

        self.assertEqual(screen_content(rows, [1], fails_after_first_chunk).code, UNREADABLE_CODE)

    def test_ut_att_05_04_empty_attachment_list_is_not_a_block(self) -> None:
        """UT-ATT-05.04: ``attachments: []`` is "no attachments", never a block."""
        decision = screen_names([])
        self.assertTrue(decision.ok)
        self.assertIsNone(decision.code)
        self.assertFalse(decision.blocked)
        self.assertFalse(decision.failed)
        self.assertTrue(screen_content([], [], lambda index: []).ok)

    def test_ut_att_05_05_unrequested_availability_reasons_are_not_evaluated(self) -> None:
        """UT-ATT-05.05: an unrequested unavailable attachment is ignored."""
        rows = [
            samples.entry(1, "factura.pdf"),
            samples.entry(2, "notas.pdf", unavailable_reason="not_local"),
        ]
        opened: list[int] = []

        def open_stream(index: int):
            opened.append(index)
            return [samples.pdf_bytes()]

        self.assertTrue(screen_content(rows, [1], open_stream).ok)
        self.assertEqual(opened, [1])
        decision = screen_content(
            rows, None, lambda index: [samples.pdf_bytes()]
        )
        self.assertEqual(decision.code, UNAVAILABLE_CODE)
        self.assertEqual((decision.index, decision.name), (2, "notas.pdf"))
        self.assertEqual(decision.reason, "not_local")


# ---------------------------------------------------------------------------
# Attachment engine helpers: temporary application homes, cache seeding and asserts.
# ---------------------------------------------------------------------------

#: One MiB as fixed by PRD §15.6 (1 MB = 1.048.576 bytes).
MIB = 1_048_576


class FakeClock:
    """Injectable monotonic clock for the engine ``deadline`` tests."""

    def __init__(self, now: float = 0.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _new_home(tmp: str) -> Path:
    return Path(tmp) / "home"


def _engine(
    home: Path,
    driver: object,
    *,
    config: AttachmentsConfig | None = None,
    clock: "FakeClock | None" = None,
) -> AttachmentsEngine:
    return AttachmentsEngine(home, config or AttachmentsConfig(), driver, clock=clock)


def _cache_file(home: Path, uid: str, original_name: str, index: int) -> Path:
    return attachment_path(home, uid, sanitize_name(original_name, index))


def _seed_cache(
    home: Path,
    uid: str,
    original_name: str,
    index: int,
    data: bytes,
    *,
    registered: bool = True,
) -> Path:
    """Seed a cache file; ``registered`` also records it in the manifest (CR-01)."""
    path = _cache_file(home, uid, original_name, index)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if registered:
        _register(home, uid, index, path.name, len(data), _sha256(data))
    return path


def _link_directory(link: Path, target: Path) -> bool:
    """Create a directory symlink, or a junction on Windows without the privilege."""
    try:
        link.symlink_to(target, target_is_directory=True)
        return True
    except (OSError, NotImplementedError):
        pass
    if os.name != "nt":  # pragma: no cover - POSIX always allows symlinks here
        return False
    try:
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    except (ImportError, OSError):  # pragma: no cover - very restricted hosts
        return False
    return True


def _manifest_path(home: Path, uid: str) -> Path:
    return message_dir(home, uid) / attachment_cache.MANIFEST_NAME


def _read_manifest(home: Path, uid: str) -> dict[str, dict[str, object]]:
    path = _manifest_path(home, uid)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))["entries"]


def _register(
    home: Path, uid: str, index: int, sanitized_name: str, size: int, digest: str
) -> None:
    path = _manifest_path(home, uid)
    path.parent.mkdir(parents=True, exist_ok=True)
    entries = _read_manifest(home, uid)
    entries[str(index)] = {
        "sanitized_name": sanitized_name,
        "size_bytes": size,
        "sha256": digest,
    }
    path.write_text(
        json.dumps({"version": attachment_cache.MANIFEST_VERSION, "entries": entries}),
        encoding="utf-8",
    )


def _tree_files(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _staging_files(home: Path) -> list[Path]:
    root = home / "tmp" / "staging"
    if not root.exists():
        return []
    return [path for path in root.rglob("*") if path.is_file()]


def _staging_sessions(home: Path) -> list[Path]:
    root = home / "tmp" / "staging"
    if not root.exists():
        return []
    return [path for path in root.iterdir() if path.is_dir()]


def _mode(path: Path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _cache_files(home: Path) -> list[Path]:
    """Cached attachment files (the per-message manifest is not an attachment)."""
    return [
        path
        for path in (home / "attachments").rglob("*")
        if path.is_file() and path.name != attachment_cache.MANIFEST_NAME
    ]


def _assert_no_staging(test: unittest.TestCase, home: Path) -> None:
    test.assertEqual(_staging_files(home), [])
    test.assertEqual(_staging_sessions(home), [])


class AttachmentLimitTests(unittest.TestCase):
    """UT-ATT-06: ``[attachments]`` limits (AC-13, RF-49, PRD §12.11 row 12)."""

    def test_ut_att_06_01_boundary_is_strictly_greater_in_mib(self) -> None:
        """UT-ATT-06.01 B: the exact limit passes; one byte more exceeds ."""
        with tempfile.TemporaryDirectory(prefix="mailquery-m07-") as tmp:
            home = _new_home(tmp)
            exact = b"a" * MIB
            driver = FakeAttachmentDriver([FakeAttachment("factura.pdf", data=exact)])
            engine = _engine(
                home,
                driver,
                config=AttachmentsConfig(max_file_size_mb=1, max_total_size_mb=2),
            )
            records = engine.recover("fake:1", [1])
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["size_bytes"], MIB)
            self.assertEqual(records[0]["sha256"], _sha256(exact))
            self.assertEqual(
                _cache_file(home, "fake:1", "factura.pdf", 1).read_bytes(), exact
            )
        with tempfile.TemporaryDirectory(prefix="mailquery-m07-") as tmp:
            home = _new_home(tmp)
            driver = FakeAttachmentDriver(
                [FakeAttachment("factura.pdf", data=b"a", known_size=MIB + 1)]
            )
            engine = _engine(
                home,
                driver,
                config=AttachmentsConfig(max_file_size_mb=1, max_total_size_mb=2),
            )
            with self.assertRaises(MailqueryError) as caught:
                engine.recover("fake:1", [1])
            self.assertEqual(caught.exception.code, "E_ATTACHMENT_TOO_LARGE")
            self.assertEqual(caught.exception.exit_code, 4)
            self.assertEqual(driver.stream_opens, [])
            self.assertFalse((home / "attachments").exists())

    def test_ut_att_06_02_known_file_size_fails_before_writing(self) -> None:
        """UT-ATT-06.02 N: a known oversized file fails before writing anything."""
        with tempfile.TemporaryDirectory(prefix="mailquery-m07-") as tmp:
            home = _new_home(tmp)
            driver = FakeAttachmentDriver(
                [FakeAttachment("big.pdf", data=b"x", known_size=2 * MIB)]
            )
            engine = _engine(
                home,
                driver,
                config=AttachmentsConfig(max_file_size_mb=1, max_total_size_mb=10),
            )
            with self.assertRaises(MailqueryError) as caught:
                engine.recover("fake:1", [1])
            self.assertEqual(caught.exception.code, "E_ATTACHMENT_TOO_LARGE")
            self.assertEqual(caught.exception.exit_code, 4)
            for fragment in ("max_file_size_mb=1", "attachment 1", "'big.pdf'", "MiB"):
                self.assertIn(fragment, caught.exception.message)
            self.assertIn("max_file_size_mb in ~/.mailquery/config.toml", caught.exception.hint)
            self.assertFalse((home / "attachments").exists())
            self.assertEqual(driver.stream_opens, [])
            _assert_no_staging(self, home)

    def test_ut_att_06_03_total_counts_cache_hits_with_real_size(self) -> None:
        """UT-ATT-06.03 N: ``max_total_size_mb`` counts real sizes of cache hits."""
        with tempfile.TemporaryDirectory(prefix="mailquery-m07-") as tmp:
            home = _new_home(tmp)
            hit_data = b"h" * (MIB + MIB // 2)
            seeded = _seed_cache(home, "fake:1", "uno.pdf", 1, hit_data)
            driver = FakeAttachmentDriver(
                [
                    FakeAttachment("uno.pdf", data=hit_data),
                    FakeAttachment("dos.pdf", data=b"d" * MIB),
                ]
            )
            engine = _engine(
                home,
                driver,
                config=AttachmentsConfig(max_file_size_mb=10, max_total_size_mb=2),
            )
            with self.assertRaises(MailqueryError) as caught:
                engine.recover("fake:1", None)
            self.assertEqual(caught.exception.code, "E_ATTACHMENT_TOO_LARGE")
            self.assertIn("max_total_size_mb=2", caught.exception.message)
            self.assertIn("attachment(s) total", caught.exception.message)
            self.assertIn("--index", caught.exception.hint)
            self.assertEqual(seeded.read_bytes(), hit_data)
            self.assertEqual(_cache_files(home), [seeded])
            self.assertEqual(driver.opens(2), 0)

    def test_ut_att_06_04_max_count_only_applies_to_all_and_counts_hits(self) -> None:
        """UT-ATT-06.04 N: ``max_count`` only applies to ``--all`` and counts hits."""
        with tempfile.TemporaryDirectory(prefix="mailquery-m07-") as tmp:
            home = _new_home(tmp)
            first = b"1" * 32
            _seed_cache(home, "fake:1", "uno.pdf", 1, first)
            driver = FakeAttachmentDriver(
                [
                    FakeAttachment("uno.pdf", data=first),
                    FakeAttachment("dos.pdf", data=b"2" * 32),
                ]
            )
            config = AttachmentsConfig(max_count=1)
            with self.assertRaises(MailqueryError) as caught:
                _engine(home, driver, config=config).recover("fake:1", None)
            self.assertEqual(caught.exception.code, "E_ATTACHMENT_TOO_LARGE")
            self.assertIn("max_count=1", caught.exception.message)
            self.assertIn("2 attachment(s)", caught.exception.message)
            self.assertEqual(driver.stream_opens, [])
            records = _engine(home, driver, config=config).recover("fake:1", [2])
            self.assertEqual(len(records), 1)
            self.assertFalse(records[0]["cached"])

    def test_ut_att_06_05_unknown_size_aborts_during_streaming_and_keeps_cache(self) -> None:
        """UT-ATT-06.05 N: an unknown size that exceeds aborts, cleans staging and keeps cache."""
        with tempfile.TemporaryDirectory(prefix="mailquery-m07-") as tmp:
            home = _new_home(tmp)
            previous = b"previous-cache"
            seeded = _seed_cache(home, "fake:1", "big.pdf", 1, previous)
            driver = FakeAttachmentDriver(
                [
                    FakeAttachment(
                        "big.pdf",
                        chunks=[b"a" * MIB, b"b"],
                        known_size=None,
                    )
                ]
            )
            engine = _engine(
                home,
                driver,
                config=AttachmentsConfig(max_file_size_mb=1, max_total_size_mb=10),
            )
            with self.assertRaises(MailqueryError) as caught:
                engine.recover("fake:1", [1], force=True)
            self.assertEqual(caught.exception.code, "E_ATTACHMENT_TOO_LARGE")
            self.assertIn("max_file_size_mb=1", caught.exception.message)
            self.assertEqual(seeded.read_bytes(), previous)
            self.assertEqual(_cache_files(home), [seeded])
            _assert_no_staging(self, home)

    def test_ut_att_06_06_limit_messages_and_hints(self) -> None:
        """UT-ATT-06.06 P: the PRD §12.11 templates include limit, index and name."""
        cases = (
            (
                "file",
                [FakeAttachment("big.pdf", data=b"", known_size=2 * MIB)],
                [1],
                AttachmentsConfig(max_file_size_mb=1, max_total_size_mb=10),
                "max_file_size_mb=1",
                False,
            ),
            (
                "total",
                [
                    FakeAttachment("uno.pdf", data=b"x" * MIB),
                    FakeAttachment("dos.pdf", data=b"y" * MIB),
                ],
                None,
                AttachmentsConfig(max_file_size_mb=1, max_total_size_mb=1),
                "max_total_size_mb=1",
                True,
            ),
            (
                "count",
                [
                    FakeAttachment("uno.pdf", data=b"x"),
                    FakeAttachment("dos.pdf", data=b"y"),
                ],
                None,
                AttachmentsConfig(max_count=1),
                "max_count=1",
                True,
            ),
        )
        for label, attachments, indices, config, fragment, wants_index_hint in cases:
            with self.subTest(label), tempfile.TemporaryDirectory(
                prefix="mailquery-m07-"
            ) as tmp:
                home = _new_home(tmp)
                driver = FakeAttachmentDriver(attachments)
                with self.assertRaises(MailqueryError) as caught:
                    _engine(home, driver, config=config).recover("fake:1", indices)
                error = caught.exception
                self.assertEqual(error.code, "E_ATTACHMENT_TOO_LARGE")
                self.assertIn(fragment, error.message)
                if label != "count":
                    self.assertIn("MiB", error.message)
                self.assertEqual("--index" in error.hint, wants_index_hint)

    def test_ut_att_06_07_blocked_name_precedes_known_size_limit(self) -> None:
        """UT-ATT-06.07 N: names are evaluated before limits (PRD §12.11 rows 11-12)."""
        with tempfile.TemporaryDirectory(prefix="mailquery-m07-") as tmp:
            home = _new_home(tmp)
            driver = FakeAttachmentDriver(
                [
                    FakeAttachment("evil.exe", data=b"harmless"),
                    FakeAttachment("big.pdf", data=b"", known_size=2 * MIB),
                ]
            )
            engine = _engine(
                home,
                driver,
                config=AttachmentsConfig(max_file_size_mb=1, max_total_size_mb=10),
            )
            with self.assertRaises(MailqueryError) as caught:
                engine.recover("fake:1", [2])
            self.assertEqual(caught.exception.code, "E_ATTACHMENT_BLOCKED")
            self.assertEqual(caught.exception.exit_code, 4)
            self.assertIn("evil.exe", caught.exception.message)
            self.assertIn("dangerous filename pattern", caught.exception.message)
            self.assertEqual(driver.stream_opens, [])
            self.assertFalse((home / "attachments").exists())


class AttachmentStagingTests(unittest.TestCase):
    """UT-ATT-07: staging and atomic publication (AC-12, RNF-14)."""

    def test_ut_att_07_01_staging_is_private_and_cache_appears_only_on_publish(self) -> None:
        """UT-ATT-07.01 P: the first extraction writes first in ``tmp/staging``."""
        with tempfile.TemporaryDirectory(prefix="mailquery-m07-") as tmp:
            home = _new_home(tmp)
            payload = b"%PDF-1.7\n" + b"x" * 2048
            target = _cache_file(home, "fake:1", "factura.pdf", 1)
            observed: dict[str, object] = {}

            def hook(index: int, number: int) -> None:
                if index != 1:
                    return
                sessions = _staging_sessions(home)
                if not sessions:
                    return
                staged = [path for path in sessions[0].rglob("*") if path.is_file()]
                observed["session_mode"] = _mode(sessions[0])
                observed["file_mode"] = _mode(staged[0]) if staged else None
                observed["published"] = target.exists()

            driver = FakeAttachmentDriver(
                [FakeAttachment("factura.pdf", data=payload)], on_chunk=hook
            )
            records = _engine(home, driver).recover("fake:1", [1])
            if os.name == "posix":
                self.assertEqual(observed["session_mode"], 0o700)
                self.assertEqual(observed["file_mode"], 0o600)
            self.assertFalse(observed["published"])
            self.assertFalse(records[0]["cached"])
            self.assertTrue(records[0]["saved"])
            self.assertEqual(target.read_bytes(), payload)
            _assert_no_staging(self, home)

    def test_ut_att_07_02_abort_before_publication_leaves_no_files(self) -> None:
        """UT-ATT-07.02 N: content, limit or read aborts leave no partial cache/staging."""
        cases = (
            (
                "content",
                FakeAttachment("factura.pdf", data=samples.mz_bytes()),
                None,
                "E_ATTACHMENT_BLOCKED",
            ),
            (
                "metadata_reason",
                FakeAttachment("factura.pdf", data=b"ok", unavailable_reason="not_local"),
                None,
                "E_ATTACHMENT_UNAVAILABLE",
            ),
            (
                "driver_permission",
                FakeAttachment("factura.pdf", data=b"ok"),
                {"open:1": DriverFailure("permission")},
                "E_PERMISSION",
            ),
            (
                "read_during_extraction",
                FakeAttachment(
                    "factura.pdf",
                    chunks=[b"%PDF-1.7" + b"x" * 600, b"y" * 400],
                ),
                {
                    "read:1": OSError("device disappeared"),
                    "read_after:1": 1,
                },
                "E_ATTACHMENT_UNREADABLE",
            ),
        )
        for label, attachment, failures, expected_code in cases:
            with self.subTest(label), tempfile.TemporaryDirectory(
                prefix="mailquery-m07-"
            ) as tmp:
                home = _new_home(tmp)
                previous = b"previous-cache"
                seeded = _seed_cache(home, "fake:1", "factura.pdf", 1, previous)
                driver = FakeAttachmentDriver([attachment], failures=failures)
                with self.assertRaises(MailqueryError) as caught:
                    _engine(home, driver).recover("fake:1", [1], force=True)
                self.assertEqual(caught.exception.code, expected_code)
                self.assertEqual(seeded.read_bytes(), previous)
                self.assertEqual(_cache_files(home), [seeded])
                _assert_no_staging(self, home)

    def test_ut_att_07_03_replace_failure_is_io_without_publication(self) -> None:
        """UT-ATT-07.03 N: an ``os.replace`` failure is ``E_IO`` without publication."""
        with tempfile.TemporaryDirectory(prefix="mailquery-m07-") as tmp:
            home = _new_home(tmp)
            driver = FakeAttachmentDriver([FakeAttachment("factura.pdf", data=b"new")])
            with mock.patch.object(
                attachment_cache,
                "_atomic_replace",
                side_effect=OSError(errno.EIO, "Input/output error"),
            ):
                with self.assertRaises(MailqueryError) as caught:
                    _engine(home, driver).recover("fake:1", [1])
            self.assertEqual(caught.exception.code, "E_IO")
            self.assertEqual(caught.exception.exit_code, 3)
            self.assertFalse(_cache_file(home, "fake:1", "factura.pdf", 1).exists())
            self.assertEqual(_cache_files(home), [])
            _assert_no_staging(self, home)

    def test_ut_att_07_04_success_publishes_every_requested_file(self) -> None:
        """UT-ATT-07.04 P: a correct extraction publishes all files with size and SHA-256."""
        with tempfile.TemporaryDirectory(prefix="mailquery-m07-") as tmp:
            home = _new_home(tmp)
            first = b"%PDF-1.7\n" + b"a" * 700
            second = "Factura de octubre: 12,50 €\n".encode("utf-8")
            driver = FakeAttachmentDriver(
                [
                    FakeAttachment("factura.pdf", data=first),
                    FakeAttachment("notas.txt", data=second),
                ]
            )
            records = _engine(home, driver).recover("fake:1", None)
            self.assertEqual([record["index"] for record in records], [1, 2])
            for record, payload in zip(records, (first, second)):
                self.assertTrue(record["saved"])
                self.assertFalse(record["cached"])
                path = Path(record["path"])
                self.assertTrue(path.is_file())
                self.assertEqual(path.read_bytes(), payload)
                self.assertEqual(record["size_bytes"], len(payload))
                self.assertEqual(record["sha256"], _sha256(payload))
            _assert_no_staging(self, home)

    def test_ut_att_07_05_failed_replace_keeps_previous_file_and_retry_works(self) -> None:
        """UT-ATT-07.05 B: a failed publication keeps the old file intact and retry works."""
        with tempfile.TemporaryDirectory(prefix="mailquery-m07-") as tmp:
            home = _new_home(tmp)
            previous = b"previous-cache"
            seeded = _seed_cache(home, "fake:1", "factura.pdf", 1, previous)
            replacement = b"replacement-bytes"
            driver = FakeAttachmentDriver(
                [FakeAttachment("factura.pdf", data=replacement)]
            )
            with mock.patch.object(
                attachment_cache,
                "_atomic_replace",
                side_effect=OSError(errno.EIO, "Input/output error"),
            ):
                with self.assertRaises(MailqueryError) as caught:
                    _engine(home, driver).recover("fake:1", [1], force=True)
            self.assertEqual(caught.exception.code, "E_IO")
            self.assertEqual(seeded.read_bytes(), previous)
            self.assertEqual(_cache_files(home), [seeded])
            _assert_no_staging(self, home)
            records = _engine(home, driver).recover("fake:1", [1], force=True)
            self.assertFalse(records[0]["cached"])
            self.assertEqual(seeded.read_bytes(), replacement)

    def test_ut_att_07_06_permission_errors_are_mapped_without_partials(self) -> None:
        """UT-ATT-07.06 N: ``EACCES`` in cache dir or staging file is ``E_PERMISSION``."""
        with tempfile.TemporaryDirectory(prefix="mailquery-m07-") as tmp:
            home = _new_home(tmp)
            driver = FakeAttachmentDriver([FakeAttachment("factura.pdf", data=b"ok")])
            real_ensure = attachment_cache._ensure_private_dir

            def deny_cache(path: Path) -> None:
                if "attachments" in str(path):
                    raise PermissionError(errno.EACCES, "Permission denied")
                real_ensure(path)

            with mock.patch.object(
                attachment_cache, "_ensure_private_dir", side_effect=deny_cache
            ):
                with self.assertRaises(MailqueryError) as caught:
                    _engine(home, driver).recover("fake:1", [1])
            self.assertEqual(caught.exception.code, "E_PERMISSION")
            self.assertEqual(caught.exception.exit_code, 3)
            self.assertEqual(_cache_files(home), [])
            _assert_no_staging(self, home)
        with tempfile.TemporaryDirectory(prefix="mailquery-m07-") as tmp:
            home = _new_home(tmp)
            driver = FakeAttachmentDriver([FakeAttachment("factura.pdf", data=b"ok")])
            with mock.patch.object(
                attachment_cache,
                "_create_staging_file",
                side_effect=PermissionError(errno.EACCES, "Permission denied"),
            ):
                with self.assertRaises(MailqueryError) as caught:
                    _engine(home, driver).recover("fake:1", [1])
            self.assertEqual(caught.exception.code, "E_PERMISSION")
            self.assertEqual(_cache_files(home), [])
            _assert_no_staging(self, home)

    def test_ut_att_07_07_enospc_is_io_without_partials(self) -> None:
        """UT-ATT-07.07 N: ``ENOSPC`` while writing staging is ``E_IO`` without partials."""
        with tempfile.TemporaryDirectory(prefix="mailquery-m07-") as tmp:
            home = _new_home(tmp)
            driver = FakeAttachmentDriver([FakeAttachment("factura.pdf", data=b"ok")])
            with mock.patch.object(
                attachment_cache,
                "_write_chunk",
                side_effect=OSError(errno.ENOSPC, "No space left on device"),
            ):
                with self.assertRaises(MailqueryError) as caught:
                    _engine(home, driver).recover("fake:1", [1])
            self.assertEqual(caught.exception.code, "E_IO")
            self.assertEqual(caught.exception.exit_code, 3)
            self.assertEqual(_cache_files(home), [])
            _assert_no_staging(self, home)


class AttachmentCacheTests(unittest.TestCase):
    """UT-ATT-08: cache hits, ``--force`` and expected size (AC-12/AC-20)."""

    def test_ut_att_08_01_cache_hit_returns_existing_file_without_reextracting(self) -> None:
        """UT-ATT-08.01 P: the second invocation is a hit with the file's size and SHA-256."""
        with tempfile.TemporaryDirectory(prefix="mailquery-m07-") as tmp:
            home = _new_home(tmp)
            payload = b"cached-payload"
            driver = FakeAttachmentDriver([FakeAttachment("factura.pdf", data=payload)])
            first = _engine(home, driver).recover("fake:1", [1])
            self.assertFalse(first[0]["cached"])
            opens_after_first = driver.opens(1)
            with mock.patch.object(
                attachment_cache,
                "_atomic_replace",
                side_effect=AssertionError("a cache hit must not publish"),
            ):
                second = _engine(home, driver).recover("fake:1", [1])
            self.assertTrue(second[0]["cached"])
            self.assertTrue(second[0]["saved"])
            self.assertEqual(second[0]["size_bytes"], len(payload))
            self.assertEqual(second[0]["sha256"], _sha256(payload))
            self.assertEqual(second[0]["path"], first[0]["path"])
            self.assertEqual(driver.opens(1), opens_after_first)

    def test_ut_att_08_02_force_reextracts_and_replaces(self) -> None:
        """UT-ATT-08.02 P: ``--force`` re-extracts and returns ``cached: false``."""
        with tempfile.TemporaryDirectory(prefix="mailquery-m07-") as tmp:
            home = _new_home(tmp)
            target_name = "factura.pdf"
            target = _seed_cache(home, "fake:1", target_name, 1, b"old-bytes")
            driver = FakeAttachmentDriver([FakeAttachment(target_name, data=b"new-bytes")])
            opens_before = driver.opens(1)
            records = _engine(home, driver).recover("fake:1", [1], force=True)
            self.assertFalse(records[0]["cached"])
            self.assertEqual(target.read_bytes(), b"new-bytes")
            self.assertEqual(records[0]["sha256"], _sha256(b"new-bytes"))
            self.assertGreater(driver.opens(1), opens_before)

    def test_ut_att_08_03_driver_expected_size_is_not_compared(self) -> None:
        """UT-ATT-08.03 B: a registered file is a hit even if the driver size differs (CR-01).

        Regression of the Outlook defect: ``Attachment.Size`` includes MAPI
        overhead, so the driver's size never equals the decoded bytes.
        """
        with tempfile.TemporaryDirectory(prefix="mailquery-m07-") as tmp:
            home = _new_home(tmp)
            payload = b"x" * 1000
            driver = FakeAttachmentDriver(
                [FakeAttachment("factura.pdf", data=payload, known_size=len(payload) + 3749)]
            )
            first = _engine(home, driver).recover("fake:1", [1])
            self.assertFalse(first[0]["cached"])
            self.assertEqual(first[0]["size_bytes"], len(payload))
            opens = driver.opens(1)
            second = _engine(home, driver).recover("fake:1", [1])
            self.assertTrue(second[0]["cached"])
            self.assertEqual(second[0]["sha256"], _sha256(payload))
            self.assertEqual(driver.opens(1), opens)

    def test_ut_att_08_04_blocked_message_never_serves_cache(self) -> None:
        """UT-ATT-08.04 P: a blocked message serves no cache even if files exist."""
        with tempfile.TemporaryDirectory(prefix="mailquery-m07-") as tmp:
            home = _new_home(tmp)
            seeded = _seed_cache(home, "fake:1", "evil.exe", 1, b"previous")
            safe = _seed_cache(home, "fake:1", "factura.pdf", 2, b"safe-cache")
            driver = FakeAttachmentDriver(
                [
                    FakeAttachment("evil.exe", data=b"harmless"),
                    FakeAttachment("factura.pdf", data=b"safe"),
                ]
            )
            with self.assertRaises(MailqueryError) as caught:
                _engine(home, driver).recover("fake:1", [2])
            self.assertEqual(caught.exception.code, "E_ATTACHMENT_BLOCKED")
            self.assertEqual(seeded.read_bytes(), b"previous")
            self.assertEqual(safe.read_bytes(), b"safe-cache")
            self.assertEqual(driver.stream_opens, [])

    def test_ut_att_08_05_non_regular_cache_entry_is_a_miss(self) -> None:
        """UT-ATT-08.05 N: a symlink or directory cache entry is a miss; links are not followed."""
        with tempfile.TemporaryDirectory(prefix="mailquery-m07-") as tmp:
            home = _new_home(tmp)
            home.mkdir(parents=True)
            victim = home / "victim.txt"
            victim.write_bytes(b"victim-bytes")
            link = _cache_file(home, "fake:1", "factura.pdf", 1)
            link.parent.mkdir(parents=True)
            try:
                link.symlink_to(victim)
            except (OSError, NotImplementedError):  # pragma: no cover - Windows privileges
                self.skipTest("symlinks are not available on this host")
            driver = FakeAttachmentDriver([FakeAttachment("factura.pdf", data=b"new")])
            records = _engine(home, driver).recover("fake:1", [1])
            self.assertFalse(records[0]["cached"])
            self.assertEqual(victim.read_bytes(), b"victim-bytes")
            self.assertFalse(link.is_symlink())
            self.assertEqual(link.read_bytes(), b"new")
        with tempfile.TemporaryDirectory(prefix="mailquery-m07-") as tmp:
            home = _new_home(tmp)
            directory = _cache_file(home, "fake:1", "factura.pdf", 1)
            directory.mkdir(parents=True)
            driver = FakeAttachmentDriver([FakeAttachment("factura.pdf", data=b"new")])
            with self.assertRaises(MailqueryError) as caught:
                _engine(home, driver).recover("fake:1", [1])
            self.assertEqual(caught.exception.code, "E_IO")
            self.assertTrue(directory.is_dir())
            self.assertEqual(list(directory.iterdir()), [])

    def test_ut_att_08_06_published_path_is_the_frozen_cache_layout(self) -> None:
        """UT-ATT-08.06 P: the published path is the deterministic cache path (no double prefix)."""
        with tempfile.TemporaryDirectory(prefix="mailquery-m07-") as tmp:
            home = _new_home(tmp)
            uid = "fake:abc"
            self.assertIsNone(cached_path(home, uid, "factura.pdf", 1))
            driver = FakeAttachmentDriver([FakeAttachment("factura.pdf", data=b"data")])
            records = _engine(home, driver).recover(uid, [1])
            expected = home / "attachments" / "fake" / "abc" / "01_factura.pdf"
            self.assertEqual(records[0]["sanitized_name"], "01_factura.pdf")
            self.assertEqual(records[0]["sanitized_name"].count("01_"), 1)
            self.assertTrue(os.path.isabs(records[0]["path"]))
            self.assertEqual(Path(records[0]["path"]), expected)
            self.assertEqual(Path(records[0]["path"]).parent, message_dir(home, uid))
            self.assertEqual(cached_path(home, uid, "factura.pdf", 1), expected)
            expected.unlink()
            self.assertIsNone(cached_path(home, uid, "factura.pdf", 1))


class AttachmentManifestTests(unittest.TestCase):
    """UT-ATT-12: per-message manifest and unverified entries (CR-01, RF-45, RF-51)."""

    def test_ut_att_12_01_publication_registers_name_size_and_sha256(self) -> None:
        """UT-ATT-12.01 P: each published file is registered; other entries are kept."""
        with tempfile.TemporaryDirectory(prefix="mailquery-cr01-") as tmp:
            home = _new_home(tmp)
            other = _seed_cache(home, "fake:1", "dos.pdf", 2, b"two")
            driver = FakeAttachmentDriver(
                [
                    FakeAttachment("uno.pdf", data=b"one"),
                    FakeAttachment("dos.pdf", data=b"two"),
                ]
            )
            _engine(home, driver).recover("fake:1", [1])
            manifest_path = _manifest_path(home, "fake:1")
            document = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(document["version"], attachment_cache.MANIFEST_VERSION)
            self.assertEqual(
                document["entries"]["1"],
                {"sanitized_name": "01_uno.pdf", "size_bytes": 3, "sha256": _sha256(b"one")},
            )
            self.assertEqual(document["entries"]["2"]["sanitized_name"], other.name)
            if os.name == "posix":
                self.assertEqual(_mode(manifest_path), 0o600)
            _assert_no_staging(self, home)

    def test_ut_att_12_02_unregistered_file_is_replaced_and_registered(self) -> None:
        """UT-ATT-12.02 N: a file without manifest entry is never served; it is replaced."""
        with tempfile.TemporaryDirectory(prefix="mailquery-cr01-") as tmp:
            home = _new_home(tmp)
            seeded = _seed_cache(
                home, "fake:1", "factura.pdf", 1, b"planted", registered=False
            )
            driver = FakeAttachmentDriver([FakeAttachment("factura.pdf", data=b"real")])
            records = _engine(home, driver).recover("fake:1", [1])
            self.assertFalse(records[0]["cached"])
            self.assertEqual(seeded.read_bytes(), b"real")
            self.assertEqual(_read_manifest(home, "fake:1")["1"]["sha256"], _sha256(b"real"))
            again = _engine(home, driver).recover("fake:1", [1])
            self.assertTrue(again[0]["cached"])

    def test_ut_att_12_03_sha256_mismatch_with_same_size_is_replaced(self) -> None:
        """UT-ATT-12.03 N: a substituted file of the same size is detected by SHA-256."""
        with tempfile.TemporaryDirectory(prefix="mailquery-cr01-") as tmp:
            home = _new_home(tmp)
            driver = FakeAttachmentDriver([FakeAttachment("factura.pdf", data=b"original")])
            first = _engine(home, driver).recover("fake:1", [1])
            target = Path(first[0]["path"])
            target.write_bytes(b"tampered")  # same length, different content
            opens = driver.opens(1)
            records = _engine(home, driver).recover("fake:1", [1])
            self.assertFalse(records[0]["cached"])
            self.assertEqual(target.read_bytes(), b"original")
            self.assertEqual(records[0]["sha256"], _sha256(b"original"))
            self.assertGreater(driver.opens(1), opens)

    def test_ut_att_12_04_size_mismatch_is_unverified_without_hashing(self) -> None:
        """UT-ATT-12.04 B: a registered size mismatch is a miss before any hash is computed."""
        with tempfile.TemporaryDirectory(prefix="mailquery-cr01-") as tmp:
            home = _new_home(tmp)
            driver = FakeAttachmentDriver([FakeAttachment("factura.pdf", data=b"original")])
            first = _engine(home, driver).recover("fake:1", [1])
            Path(first[0]["path"]).write_bytes(b"truncated-and-longer")
            cache = attachment_cache.AttachmentCache(home, "fake:1")
            with mock.patch.object(
                attachment_cache, "_hash_file", side_effect=AssertionError("hashed")
            ):
                self.assertIsNone(cache.lookup("factura.pdf", 1))
            records = _engine(home, driver).recover("fake:1", [1])
            self.assertFalse(records[0]["cached"])
            self.assertEqual(Path(records[0]["path"]).read_bytes(), b"original")

    def test_ut_att_12_05_unverified_file_is_removed_when_recovery_fails(self) -> None:
        """UT-ATT-12.05 N: a failed re-extraction removes the unverified file and its entry."""
        cases = (
            ("blocked", FakeAttachment("factura.pdf", data=samples.mz_bytes()), None,
             "E_ATTACHMENT_BLOCKED"),
            ("unavailable", FakeAttachment("factura.pdf", data=b"ok"),
             {"open:1": DriverFailure("not_local")}, "E_ATTACHMENT_UNAVAILABLE"),
        )
        for label, attachment, failures, code in cases:
            for force in (False, True):
                with self.subTest(label, force=force), tempfile.TemporaryDirectory(
                    prefix="mailquery-cr01-"
                ) as tmp:
                    home = _new_home(tmp)
                    seeded = _seed_cache(
                        home, "fake:1", "factura.pdf", 1, b"planted", registered=False
                    )
                    _register(home, "fake:1", 1, seeded.name, 7, "0" * 64)  # stale entry
                    kept = _seed_cache(home, "fake:1", "otro.pdf", 2, b"kept")
                    driver = FakeAttachmentDriver(
                        [attachment, FakeAttachment("otro.pdf", data=b"kept")],
                        failures=failures,
                    )
                    with self.assertRaises(MailqueryError) as caught:
                        _engine(home, driver).recover("fake:1", [1], force=force)
                    self.assertEqual(caught.exception.code, code)
                    self.assertFalse(seeded.exists())
                    self.assertEqual(kept.read_bytes(), b"kept")
                    self.assertEqual(sorted(_read_manifest(home, "fake:1")), ["2"])
                    _assert_no_staging(self, home)

    def test_ut_att_12_06_registered_file_survives_failed_force(self) -> None:
        """UT-ATT-12.06 N: ``--force`` that fails keeps a registered file and its entry."""
        with tempfile.TemporaryDirectory(prefix="mailquery-cr01-") as tmp:
            home = _new_home(tmp)
            seeded = _seed_cache(home, "fake:1", "factura.pdf", 1, b"verified")
            driver = FakeAttachmentDriver(
                [FakeAttachment("factura.pdf", data=samples.mz_bytes())]
            )
            with self.assertRaises(MailqueryError):
                _engine(home, driver).recover("fake:1", [1], force=True)
            self.assertEqual(seeded.read_bytes(), b"verified")
            self.assertEqual(_read_manifest(home, "fake:1")["1"]["sha256"], _sha256(b"verified"))

    def test_ut_att_12_07_invalid_manifest_makes_every_file_unverified(self) -> None:
        """UT-ATT-12.07 N: an unparsable, wrong-version or malformed manifest is not trusted."""
        documents = (
            "{not json",
            json.dumps({"version": 99, "entries": {}}),
            json.dumps({"version": 1, "entries": {"1": {"sanitized_name": "01_factura.pdf",
                                                         "size_bytes": 4, "sha256": "XYZ"}}}),
            json.dumps({"version": 1, "entries": {"1": {"sanitized_name": "01_factura.pdf",
                                                         "size_bytes": True,
                                                         "sha256": _sha256(b"data")}}}),
        )
        for document in documents:
            with self.subTest(document=document[:24]), tempfile.TemporaryDirectory(
                prefix="mailquery-cr01-"
            ) as tmp:
                home = _new_home(tmp)
                _seed_cache(home, "fake:1", "factura.pdf", 1, b"data", registered=False)
                _manifest_path(home, "fake:1").write_text(document, encoding="utf-8")
                driver = FakeAttachmentDriver([FakeAttachment("factura.pdf", data=b"data")])
                records = _engine(home, driver).recover("fake:1", [1])
                self.assertFalse(records[0]["cached"])
                self.assertEqual(_read_manifest(home, "fake:1")["1"]["sha256"], _sha256(b"data"))

    def test_ut_att_12_08_entry_with_another_name_is_unverified(self) -> None:
        """UT-ATT-12.08 N: an entry registered under another sanitized name is not a hit."""
        with tempfile.TemporaryDirectory(prefix="mailquery-cr01-") as tmp:
            home = _new_home(tmp)
            seeded = _seed_cache(home, "fake:1", "factura.pdf", 1, b"data", registered=False)
            _register(home, "fake:1", 1, "01_other.pdf", 4, _sha256(b"data"))
            cache = attachment_cache.AttachmentCache(home, "fake:1")
            self.assertIsNone(cache.lookup("factura.pdf", 1))
            self.assertTrue(seeded.exists())

    def test_ut_att_12_09_linked_manifest_is_ignored(self) -> None:
        """UT-ATT-12.09 N: a symlinked manifest is not read and is replaced, not followed."""
        with tempfile.TemporaryDirectory(prefix="mailquery-cr01-") as tmp:
            home = _new_home(tmp)
            _seed_cache(home, "fake:1", "factura.pdf", 1, b"data", registered=False)
            outside = Path(tmp) / "outside.json"
            outside.write_text(
                json.dumps({"version": 1, "entries": {"1": {
                    "sanitized_name": "01_factura.pdf", "size_bytes": 4,
                    "sha256": _sha256(b"data")}}}),
                encoding="utf-8",
            )
            snapshot = outside.read_bytes()
            try:
                _manifest_path(home, "fake:1").symlink_to(outside)
            except (OSError, NotImplementedError):  # pragma: no cover - Windows privileges
                self.skipTest("symlinks are not available on this host")
            driver = FakeAttachmentDriver([FakeAttachment("factura.pdf", data=b"data")])
            records = _engine(home, driver).recover("fake:1", [1])
            self.assertFalse(records[0]["cached"])
            self.assertEqual(outside.read_bytes(), snapshot)
            self.assertFalse(_manifest_path(home, "fake:1").is_symlink())

    def test_ut_att_12_10_linked_message_directory_is_refused(self) -> None:
        """UT-ATT-12.10 N: a symlinked message or driver directory is ``E_IO``; nothing is written."""
        for level in ("message", "driver"):
            with self.subTest(level), tempfile.TemporaryDirectory(
                prefix="mailquery-cr01-"
            ) as tmp:
                home = _new_home(tmp)
                outside = Path(tmp) / "outside"
                outside.mkdir()
                directory = message_dir(home, "fake:1")
                link = directory if level == "message" else directory.parent
                link.parent.mkdir(parents=True, exist_ok=True)
                if not _link_directory(link, outside):  # pragma: no cover
                    self.skipTest("directory links are not available on this host")
                driver = FakeAttachmentDriver([FakeAttachment("factura.pdf", data=b"data")])
                with self.assertRaises(MailqueryError) as caught:
                    _engine(home, driver).recover("fake:1", [1])
                self.assertEqual(caught.exception.code, "E_IO")
                self.assertEqual(caught.exception.exit_code, 3)
                self.assertEqual(list(outside.rglob("*")), [])
                _assert_no_staging(self, home)

    def test_ut_att_12_11_linked_directory_is_never_a_hit_nor_cleaned(self) -> None:
        """UT-ATT-12.11 N: through a linked message directory nothing is served or removed."""
        with tempfile.TemporaryDirectory(prefix="mailquery-cr01-") as tmp:
            home = _new_home(tmp)
            outside = Path(tmp) / "outside"
            outside.mkdir()
            planted = outside / "01_factura.pdf"
            planted.write_bytes(b"data")
            directory = message_dir(home, "fake:1")
            directory.parent.mkdir(parents=True)
            if not _link_directory(directory, outside):  # pragma: no cover
                self.skipTest("directory links are not available on this host")
            (outside / attachment_cache.MANIFEST_NAME).write_text(
                json.dumps({"version": 1, "entries": {"1": {
                    "sanitized_name": "01_factura.pdf", "size_bytes": 4,
                    "sha256": _sha256(b"data")}}}),
                encoding="utf-8",
            )
            cache = attachment_cache.AttachmentCache(home, "fake:1")
            self.assertFalse(cache.directories_are_real())
            self.assertEqual(cache.read_manifest(), {})
            self.assertIsNone(cache.lookup("factura.pdf", 1))
            self.assertFalse(cache.discard_unverified("factura.pdf", 1))
            self.assertTrue(planted.exists())

    def test_ut_att_12_12_unverified_directory_is_never_removed(self) -> None:
        """UT-ATT-12.12 N: a directory at the cache path is kept (no recursive removal)."""
        with tempfile.TemporaryDirectory(prefix="mailquery-cr01-") as tmp:
            home = _new_home(tmp)
            directory = _cache_file(home, "fake:1", "factura.pdf", 1)
            directory.mkdir(parents=True)
            (directory / "inside.txt").write_bytes(b"inside")
            driver = FakeAttachmentDriver([FakeAttachment("factura.pdf", data=b"new")])
            with self.assertRaises(MailqueryError) as caught:
                _engine(home, driver).recover("fake:1", [1])
            self.assertEqual(caught.exception.code, "E_IO")
            self.assertEqual((directory / "inside.txt").read_bytes(), b"inside")

    def test_ut_att_12_13_locked_unverified_file_is_io_and_never_served(self) -> None:
        """UT-ATT-12.13 N: a replace refused by the OS (file open on Windows) is ``E_IO``."""
        with tempfile.TemporaryDirectory(prefix="mailquery-cr01-") as tmp:
            home = _new_home(tmp)
            seeded = _seed_cache(home, "fake:1", "factura.pdf", 1, b"old", registered=False)
            driver = FakeAttachmentDriver([FakeAttachment("factura.pdf", data=b"new")])
            sharing = OSError(errno.EIO, "The process cannot access the file")
            with mock.patch.object(attachment_cache, "_atomic_replace", side_effect=sharing), \
                    mock.patch.object(
                        attachment_cache.AttachmentCache, "discard_unverified", return_value=False
                    ):
                with self.assertRaises(MailqueryError) as caught:
                    _engine(home, driver).recover("fake:1", [1])
            self.assertEqual(caught.exception.code, "E_IO")
            self.assertEqual(seeded.read_bytes(), b"old")
            self.assertNotIn("1", _read_manifest(home, "fake:1"))
            _assert_no_staging(self, home)
            records = _engine(home, driver).recover("fake:1", [1])
            self.assertFalse(records[0]["cached"])
            self.assertEqual(seeded.read_bytes(), b"new")

    def test_ut_att_12_14_manifest_write_failure_is_best_effort(self) -> None:
        """UT-ATT-12.14 B: a published file whose entry could not be written is re-extracted."""
        with tempfile.TemporaryDirectory(prefix="mailquery-cr01-") as tmp:
            home = _new_home(tmp)
            driver = FakeAttachmentDriver([FakeAttachment("factura.pdf", data=b"data")])
            with mock.patch.object(
                attachment_cache.AttachmentCache,
                "write_manifest",
                side_effect=MailqueryError("E_IO", "disk full", "free space", "io"),
            ):
                records = _engine(home, driver).recover("fake:1", [1])
            self.assertFalse(records[0]["cached"])
            self.assertTrue(Path(records[0]["path"]).is_file())
            self.assertEqual(_read_manifest(home, "fake:1"), {})
            again = _engine(home, driver).recover("fake:1", [1])
            self.assertFalse(again[0]["cached"])
            third = _engine(home, driver).recover("fake:1", [1])
            self.assertTrue(third[0]["cached"])

    def test_ut_att_12_15_show_cached_path_only_checks_the_file(self) -> None:
        """UT-ATT-12.15 P: ``cached_path`` (show, option 1a) never reads file or manifest."""
        with tempfile.TemporaryDirectory(prefix="mailquery-cr01-") as tmp:
            home = _new_home(tmp)
            seeded = _seed_cache(home, "fake:1", "factura.pdf", 1, b"x", registered=False)
            with mock.patch.object(
                attachment_cache, "_open_no_follow", side_effect=AssertionError("read")
            ), mock.patch("builtins.open", side_effect=AssertionError("read")):
                self.assertEqual(cached_path(home, "fake:1", "factura.pdf", 1), seeded)


class AttachmentPermissionTests(unittest.TestCase):
    """UT-ATT-09: cache/staging permissions (AC-12, RNF-13)."""

    def test_ut_att_09_01_posix_modes_are_private(self) -> None:
        """UT-ATT-09.01 P: directories are 0700 and files 0600 without ``+x``."""
        if os.name != "posix":  # pragma: no cover - Windows hosts
            self.skipTest("POSIX file modes only")
        with tempfile.TemporaryDirectory(prefix="mailquery-m07-") as tmp:
            home = _new_home(tmp)
            observed: dict[str, int] = {}

            def hook(index: int, number: int) -> None:
                sessions = _staging_sessions(home)
                if not sessions:
                    return
                staged = [path for path in sessions[0].rglob("*") if path.is_file()]
                if staged:
                    observed["session"] = _mode(sessions[0])
                    observed["file"] = _mode(staged[0])

            driver = FakeAttachmentDriver(
                [FakeAttachment("factura.pdf", data=b"payload")], on_chunk=hook
            )
            _engine(home, driver).recover("fake:1", [1])
            for directory in (
                home,
                home / "tmp",
                home / "tmp" / "staging",
                home / "attachments",
                home / "attachments" / "fake",
                message_dir(home, "fake:1"),
            ):
                self.assertEqual(_mode(directory), 0o700, directory)
            target = _cache_file(home, "fake:1", "factura.pdf", 1)
            self.assertEqual(_mode(target), 0o600)
            self.assertEqual(_mode(target) & 0o111, 0)
            self.assertEqual(observed["session"], 0o700)
            self.assertEqual(observed["file"], 0o600)

    def test_ut_att_09_02_windows_inherits_profile_acl_without_relaxing(self) -> None:
        """UT-ATT-09.02 P: on Windows the profile ACL is inherited and never relaxed."""
        with tempfile.TemporaryDirectory(prefix="mailquery-m07-") as tmp:
            home = _new_home(tmp)
            driver = FakeAttachmentDriver([FakeAttachment("factura.pdf", data=b"payload")])
            with mock.patch.object(
                attachment_cache, "_SECURE_PERMISSIONS", False
            ), mock.patch.object(attachment_cache.os, "chmod") as chmod:
                records = _engine(home, driver).recover("fake:1", [1])
            chmod.assert_not_called()
            self.assertTrue(Path(records[0]["path"]).is_file())
            self.assertEqual(Path(records[0]["path"]).read_bytes(), b"payload")

    def test_ut_att_09_03_previous_cache_survives_failed_reextraction(self) -> None:
        """UT-ATT-09.03 N: a cached file keeps its hash and size if extraction fails."""
        with tempfile.TemporaryDirectory(prefix="mailquery-m07-") as tmp:
            home = _new_home(tmp)
            previous = b"previous-cache-bytes"
            seeded = _seed_cache(home, "fake:1", "factura.pdf", 1, previous)
            driver = FakeAttachmentDriver(
                [FakeAttachment("factura.pdf", data=samples.mz_bytes())]
            )
            with self.assertRaises(MailqueryError) as caught:
                _engine(home, driver).recover("fake:1", [1], force=True)
            self.assertEqual(caught.exception.code, "E_ATTACHMENT_BLOCKED")
            self.assertEqual(seeded.read_bytes(), previous)
            self.assertEqual(seeded.stat().st_size, len(previous))
            self.assertEqual(_sha256(seeded.read_bytes()), _sha256(previous))
            self.assertEqual(cached_path(home, "fake:1", "factura.pdf", 1), seeded)
            _assert_no_staging(self, home)


class AttachmentEphemeralCacheTests(unittest.TestCase):
    """UT-ATT-10: ephemeral cache and concurrent deletion (AC-20, RF-51)."""

    def test_ut_att_10_01_empty_cache_is_not_an_error(self) -> None:
        """UT-ATT-10.01 P: a missing or empty cache is extracted, not an error."""
        with tempfile.TemporaryDirectory(prefix="mailquery-m07-") as tmp:
            home = _new_home(tmp)
            self.assertIsNone(cached_path(home, "fake:1", "uno.pdf", 1))
            driver = FakeAttachmentDriver(
                [
                    FakeAttachment("uno.pdf", data=b"one"),
                    FakeAttachment("dos.pdf", data=b"two"),
                ]
            )
            records = _engine(home, driver).recover("fake:1", None)
            self.assertEqual(len(records), 2)
            self.assertEqual([record["cached"] for record in records], [False, False])
            self.assertTrue(all(Path(record["path"]).is_file() for record in records))

    def test_ut_att_10_02_deleted_cache_file_is_re_extracted_once(self) -> None:
        """UT-ATT-10.02 P: a file deleted before or during the run is re-extracted once."""
        with tempfile.TemporaryDirectory(prefix="mailquery-m07-") as tmp:
            home = _new_home(tmp)
            target = _cache_file(home, "fake:1", "factura.pdf", 1)
            driver = FakeAttachmentDriver([FakeAttachment("factura.pdf", data=b"payload")])
            _engine(home, driver).recover("fake:1", [1])
            target.unlink()
            opens_before = driver.opens(1)
            records = _engine(home, driver).recover("fake:1", [1])
            self.assertFalse(records[0]["cached"])
            self.assertTrue(target.is_file())
            self.assertEqual(driver.opens(1) - opens_before, 2)
        with tempfile.TemporaryDirectory(prefix="mailquery-m07-") as tmp:
            home = _new_home(tmp)
            one = FakeAttachment("uno.pdf", data=b"one")
            two = FakeAttachment("dos.pdf", data=b"two")
            driver = FakeAttachmentDriver([one, two])
            _engine(home, driver).recover("fake:1", None)
            _cache_file(home, "fake:1", "dos.pdf", 2).unlink()

            def hook(index: int, number: int) -> None:
                if index != 2:
                    return
                _cache_file(home, "fake:1", "dos.pdf", 2).unlink(missing_ok=True)
                _cache_file(home, "fake:1", "uno.pdf", 1).unlink(missing_ok=True)

            racing = FakeAttachmentDriver([one, two], on_chunk=hook)
            records = _engine(home, racing).recover("fake:1", None)
            self.assertEqual([record["cached"] for record in records], [False, False])
            self.assertTrue(all(Path(record["path"]).is_file() for record in records))
            self.assertEqual(racing.opens(1), 2)

    def test_ut_att_10_03_reextraction_after_deletion_failure_is_unavailable(self) -> None:
        """UT-ATT-10.03 N: a failed re-extraction after deletion is ``E_ATTACHMENT_UNAVAILABLE``."""
        with tempfile.TemporaryDirectory(prefix="mailquery-m07-") as tmp:
            home = _new_home(tmp)
            target = _cache_file(home, "fake:1", "factura.pdf", 1)
            driver = FakeAttachmentDriver([FakeAttachment("factura.pdf", data=b"payload")])
            _engine(home, driver).recover("fake:1", [1])
            target.unlink()
            driver.failures["open:1"] = DriverFailure("not_local")
            with self.assertRaises(MailqueryError) as caught:
                _engine(home, driver).recover("fake:1", [1])
            self.assertEqual(caught.exception.code, "E_ATTACHMENT_UNAVAILABLE")
            self.assertFalse(target.exists())

    def test_ut_att_10_04_cache_is_never_swept_or_inspected(self) -> None:
        """UT-ATT-10.04 N: no sweep, purge or content inspection of the cache."""
        with tempfile.TemporaryDirectory(prefix="mailquery-m07-") as tmp:
            home = _new_home(tmp)
            home.mkdir(parents=True)
            unrelated = home / "attachments" / "other" / "xyz" / "01_keep.pdf"
            unrelated.parent.mkdir(parents=True)
            unrelated.write_bytes(b"keep")
            plugin_tmp = home / "tmp" / "plugin-fake" / "data.bin"
            plugin_tmp.parent.mkdir(parents=True)
            plugin_tmp.write_bytes(b"plugin")
            config = home / "config.toml"
            config.write_text("[attachments]\nmax_count = 50\n", encoding="utf-8")
            state = home / "state.json"
            state.write_text('{"schema": 2}\n', encoding="utf-8")
            snapshot = {path: path.read_bytes() for path in (unrelated, plugin_tmp, config, state)}
            driver = FakeAttachmentDriver([FakeAttachment("factura.pdf", data=b"payload")])
            _engine(home, driver).recover("fake:1", [1])
            for path, data in snapshot.items():
                self.assertEqual(path.read_bytes(), data, path)
            self.assertTrue(unrelated.is_file())
            self.assertTrue(plugin_tmp.is_file())

    def test_ut_att_10_05_plugin_lifecycle_keeps_cache_bytes(self) -> None:
        """UT-ATT-10.05 P: DP-03 keeps config, state and cache bytes across plugin updates."""
        with tempfile.TemporaryDirectory(prefix="mailquery-m07-") as tmp:
            home = _new_home(tmp)
            home.mkdir(parents=True)
            config = home / "config.toml"
            config.write_text("[attachments]\nmax_count = 50\n", encoding="utf-8")
            state = home / "state.json"
            state.write_text('{"schema": 2}\n', encoding="utf-8")
            driver = FakeAttachmentDriver([FakeAttachment("factura.pdf", data=b"payload")])
            _engine(home, driver).recover("fake:1", [1])
            cache_snapshot = _tree_files(home / "attachments")
            config_bytes = config.read_bytes()
            state_bytes = state.read_bytes()
            driver.version = "0.2.0"  # plugin update within API 1
            records = _engine(home, driver).recover("fake:1", [1])
            self.assertTrue(records[0]["cached"])
            self.assertEqual(_tree_files(home / "attachments"), cache_snapshot)
            self.assertEqual(config.read_bytes(), config_bytes)
            self.assertEqual(state.read_bytes(), state_bytes)
            self.assertTrue(_cache_file(home, "fake:1", "factura.pdf", 1).is_file())


class AttachmentDriverReasonTests(unittest.TestCase):
    """UT-ATT-11: driver reasons and errors during extraction (AC-15)."""

    def test_ut_att_11_01_unavailable_reasons_map_to_unavailable(self) -> None:
        """UT-ATT-11.01 N: unavailability reasons map to ``E_ATTACHMENT_UNAVAILABLE``."""
        cases = (
            ("not_local", "is not available in the local store"),
            ("not_downloaded", "is not available in the local store"),
            ("unsupported", "cannot be recovered by driver 'fake'"),
            ("network", "could not be retrieved from its origin"),
        )
        for reason, fragment in cases:
            with self.subTest(reason), tempfile.TemporaryDirectory(
                prefix="mailquery-m07-"
            ) as tmp:
                home = _new_home(tmp)
                driver = FakeAttachmentDriver(
                    [FakeAttachment("factura.pdf", data=b"ok")],
                    failures={"open:1": DriverFailure(reason)},
                )
                with self.assertRaises(MailqueryError) as caught:
                    _engine(home, driver).recover("fake:1", [1])
                self.assertEqual(caught.exception.code, "E_ATTACHMENT_UNAVAILABLE")
                self.assertEqual(caught.exception.exit_code, 3)
                self.assertIn(fragment, caught.exception.message)
                self.assertTrue(caught.exception.hint)
                self.assertEqual(_cache_files(home), [])
                _assert_no_staging(self, home)
        with tempfile.TemporaryDirectory(prefix="mailquery-m07-") as tmp:
            home = _new_home(tmp)
            driver = FakeAttachmentDriver(
                [FakeAttachment("factura.pdf", data=b"ok", unavailable_reason="not_local")]
            )
            with self.assertRaises(MailqueryError) as caught:
                _engine(home, driver).recover("fake:1", [1])
            self.assertEqual(caught.exception.code, "E_ATTACHMENT_UNAVAILABLE")
            self.assertIn("is not available in the local store", caught.exception.message)

    def test_ut_att_11_02_unreadable_and_smime_reasons(self) -> None:
        """UT-ATT-11.02 N: corrupt/S/MIME/read failures are ``E_ATTACHMENT_UNREADABLE``."""
        cases = (
            ("corrupt", "is corrupt or unreadable"),
            ("unreadable", "is corrupt or unreadable"),
            ("smime", "is S/MIME protected and cannot be extracted"),
        )
        for reason, fragment in cases:
            with self.subTest(reason), tempfile.TemporaryDirectory(
                prefix="mailquery-m07-"
            ) as tmp:
                home = _new_home(tmp)
                driver = FakeAttachmentDriver(
                    [FakeAttachment("factura.pdf", data=b"ok")],
                    failures={"open:1": DriverFailure(reason)},
                )
                with self.assertRaises(MailqueryError) as caught:
                    _engine(home, driver).recover("fake:1", [1])
                self.assertEqual(caught.exception.code, "E_ATTACHMENT_UNREADABLE")
                self.assertEqual(caught.exception.exit_code, 3)
                self.assertIn(fragment, caught.exception.message)
                if reason == "smime":
                    self.assertIn("S/MIME", caught.exception.hint)
                self.assertEqual(_cache_files(home), [])
        with tempfile.TemporaryDirectory(prefix="mailquery-m07-") as tmp:
            home = _new_home(tmp)
            driver = FakeAttachmentDriver(
                [FakeAttachment("factura.pdf", data=b"ok")],
                failures={
                    "read:1": OSError("device disappeared"),
                    "read_after:1": 0,
                },
            )
            with self.assertRaises(MailqueryError) as caught:
                _engine(home, driver).recover("fake:1", [1])
            self.assertEqual(caught.exception.code, "E_ATTACHMENT_UNREADABLE")
            self.assertIn("is corrupt or unreadable", caught.exception.message)
        with tempfile.TemporaryDirectory(prefix="mailquery-m07-") as tmp:
            home = _new_home(tmp)
            driver = FakeAttachmentDriver(
                [FakeAttachment("factura.pdf", data=b"ok", unavailable_reason="corrupt")]
            )
            with self.assertRaises(MailqueryError) as caught:
                _engine(home, driver).recover("fake:1", [1])
            self.assertEqual(caught.exception.code, "E_ATTACHMENT_UNREADABLE")
        with tempfile.TemporaryDirectory(prefix="mailquery-m07-") as tmp:
            home = _new_home(tmp)
            driver = FakeAttachmentDriver([])
            self.assertEqual(_engine(home, driver).recover("fake:1", None), [])

    def test_ut_att_11_03_driver_errors_propagate_with_their_code(self) -> None:
        """UT-ATT-11.03 N: driver permission/busy/failed errors keep their code and exit."""
        cases = (
            (DriverFailure("permission"), "E_PERMISSION", 3),
            (DriverFailure("busy"), "E_CLIENT_BUSY", 5),
            (DriverFailure("boom"), "E_PLUGIN_FAILED", 3),
        )
        for failure, code, exit_code in cases:
            with self.subTest(code), tempfile.TemporaryDirectory(
                prefix="mailquery-m07-"
            ) as tmp:
                home = _new_home(tmp)
                driver = FakeAttachmentDriver(
                    [FakeAttachment("factura.pdf", data=b"ok")],
                    failures={"open:1": failure},
                )
                with self.assertRaises(MailqueryError) as caught:
                    _engine(home, driver).recover("fake:1", [1])
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(caught.exception.exit_code, exit_code)
        with tempfile.TemporaryDirectory(prefix="mailquery-m07-") as tmp:
            home = _new_home(tmp)
            wrapped = MailqueryError(
                "E_PLUGIN_FAILED", "attachment reading failed", "run doctor", "plugin failed"
            )
            driver = FakeAttachmentDriver(
                [FakeAttachment("factura.pdf", data=b"ok")],
                failures={"open:1": wrapped},
            )
            with self.assertRaises(MailqueryError) as caught:
                _engine(home, driver).recover("fake:1", [1])
            self.assertIs(caught.exception, wrapped)

    def test_ut_att_11_04_all_failure_has_no_partial_results(self) -> None:
        """UT-ATT-11.04 P: one failing attachment of ``--all`` leaves no partial results."""
        with tempfile.TemporaryDirectory(prefix="mailquery-m07-") as tmp:
            home = _new_home(tmp)
            cached = b"cached-one"
            seeded = _seed_cache(home, "fake:1", "uno.pdf", 1, cached)
            driver = FakeAttachmentDriver(
                [
                    FakeAttachment("uno.pdf", data=cached),
                    FakeAttachment("dos.pdf", data=b"two"),
                ],
                failures={"open:2": DriverFailure("not_local")},
            )
            entries = driver.attachments("1")
            with self.assertRaises(MailqueryError) as caught:
                _engine(home, driver).recover("fake:1", None, entries=entries)
            self.assertEqual(caught.exception.code, "E_ATTACHMENT_UNAVAILABLE")
            self.assertEqual(driver.metadata_calls(), 1)
            self.assertEqual(seeded.read_bytes(), cached)
            self.assertEqual(_cache_files(home), [seeded])
            _assert_no_staging(self, home)

    def test_ut_att_11_05_all_reports_first_failure_in_index_order(self) -> None:
        """UT-ATT-11.05 N: ``--all`` reports the first failing index, not the last one."""
        with tempfile.TemporaryDirectory(prefix="mailquery-m07-") as tmp:
            home = _new_home(tmp)
            driver = FakeAttachmentDriver(
                [
                    FakeAttachment("uno.pdf", data=b"one"),
                    FakeAttachment("dos.pdf", data=b"two"),
                    FakeAttachment("tres.pdf", data=b"three"),
                ],
                failures={
                    "open:2": DriverFailure("not_local"),
                    "open:3": DriverFailure("corrupt"),
                },
            )
            with self.assertRaises(MailqueryError) as caught:
                _engine(home, driver).recover("fake:1", None)
            self.assertEqual(caught.exception.code, "E_ATTACHMENT_UNAVAILABLE")
            self.assertIn("attachment 2", caught.exception.message)
            self.assertNotIn("attachment 3", caught.exception.message)
        with tempfile.TemporaryDirectory(prefix="mailquery-m07-") as tmp:
            home = _new_home(tmp)
            payload = b"x" * 20
            driver = FakeAttachmentDriver(
                [
                    FakeAttachment("uno.pdf", data=payload, chunks=chunks_of(payload, 10)),
                    FakeAttachment("dos.pdf", data=payload, chunks=chunks_of(payload, 10)),
                    FakeAttachment("tres.pdf", data=payload, chunks=chunks_of(payload, 10)),
                ],
                failures={
                    "read:2": DriverFailure("not_local"),
                    "read_after:2": 1,
                    "read:3": DriverFailure("corrupt"),
                    "read_after:3": 1,
                },
            )
            with self.assertRaises(MailqueryError) as caught:
                _engine(home, driver).recover("fake:1", None)
            self.assertEqual(caught.exception.code, "E_ATTACHMENT_UNAVAILABLE")
            self.assertIn("attachment 2", caught.exception.message)

    def test_ut_att_11_06_deadline_expiry_is_client_timeout(self) -> None:
        """UT-ATT-11.06 N: the injected extraction deadline expires as ``E_CLIENT_TIMEOUT``."""
        with tempfile.TemporaryDirectory(prefix="mailquery-m07-") as tmp:
            home = _new_home(tmp)
            clock = FakeClock(now=100.0)
            payload = b"x" * 4000

            def hook(index: int, number: int) -> None:
                clock.advance(100.0)

            driver = FakeAttachmentDriver(
                [FakeAttachment("factura.pdf", data=payload)], on_chunk=hook
            )
            engine = _engine(home, driver, clock=clock)
            with self.assertRaises(MailqueryError) as caught:
                engine.recover(
                    "fake:1", [1], deadline=lambda: clock.now + 120.0
                )
            self.assertEqual(caught.exception.code, "E_CLIENT_TIMEOUT")
            self.assertEqual(caught.exception.exit_code, 3)
            self.assertIn("did not respond within the timeout", caught.exception.message)
            self.assertEqual(_cache_files(home), [])
            _assert_no_staging(self, home)


if __name__ == "__main__":
    unittest.main()

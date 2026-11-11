"""UT-ATT-01..05: attachment blocking, sanitization and cache paths (M06).

Pure-core tests for the attachment milestone: the dangerous-extension catalog,
the name rules (§10.3.1 point 1), the magic-byte rules (§10.3.1 point 2), the
whole-message screening order, the deterministic ``sanitized_name`` (§10.3.3),
the cache path and the availability reasons (AC-09/AC-10/AC-11/AC-15).

Nothing here writes files or opens cached paths: the milestone delivers the
policy that M07 (cache/staging) and M08 (``show``/``attachment``) consume.
"""

from __future__ import annotations

import ast
import contextlib
import hashlib
import re
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path
from unittest import mock

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
    attachment_path,
    cache_root,
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
from mailquery.uid import stable_identifier

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
    """Model the M07 order names -> content (limits live between them in M07)."""

    def open_stream(index: int):
        return [streams[index]]

    names = screen_names(rows)
    if names.failed:
        return names
    return screen_content(rows, requested, open_stream)


class AttachmentNameBlockingTests(unittest.TestCase):
    """UT-ATT-01: name blocking (§10.3.1 point 1, §10.3.2, AC-10)."""

    def test_ut_att_01_01_catalog_blocks_every_extension_by_category(self) -> None:
        """UT-ATT-01.01: every §10.3.2 extension blocks, per category."""
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
        """UT-ATT-01.07: the §10.3.2/§10.3.3 allowed examples pass the name screen."""
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
    """UT-ATT-02: magic-byte blocking (§10.3.1 point 2, AC-10)."""

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
    """UT-ATT-03: whole-message screening (§10.3.1, RF-48, AC-09)."""

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
    """UT-ATT-04: ``sanitized_name`` and cache path (§10.3.3, AC-11)."""

    def test_ut_att_04_01_normative_examples(self) -> None:
        """UT-ATT-04.01: `` invoice.pdf `` => 01_invoice.pdf; the §10.3.3 examples."""
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

            # Windows uses the conservative 240-byte path budget (D9).
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
            # A POSIX path over the real PATH_MAX also falls back (D9).
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
    """UT-ATT-05: availability and stream errors (§11.3 rows 8/14, AC-15)."""

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


if __name__ == "__main__":
    unittest.main()

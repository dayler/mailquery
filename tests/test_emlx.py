"""Tests for :mod:`mailquery.emlx` (PRD 9.5 and 17).

Everything runs against the synthetic fixture built by
``tests/fixtures/make_fixtures.py``; the real ``~/Library/Mail`` store is never
touched. ``resolve_path`` is exercised through a minimal fake store, so this
module does not depend on ``mailquery.store``; one canary test uses the real
store.
"""

from __future__ import annotations

import plistlib
import shutil
import tempfile
import unittest
from email.utils import parsedate_to_datetime
from pathlib import Path
from types import SimpleNamespace

from mailquery.emlx import (
    HEADER_NAMES,
    EmlxMessage,
    html_to_text,
    parse_emlx,
    resolve_path,
)
from tests.fixtures.make_fixtures import (
    ACCOUNT_ICLOUD,
    MAILBOX_ICLOUD_FACTURAS,
    MAILBOX_ICLOUD_INBOX,
    VERSION_UUID,
    _mailbox_dir,
    build_store,
    emlx_relative_path,
)


class _FakeStore:
    """Minimal ``EnvelopeStore`` stand-in for ``resolve_path``.

    ``resolve_path`` only needs ``.version.version_uuid`` and
    ``.mailbox_dir(mailbox)``, so tests never depend on ``store.py``.
    """

    def __init__(self, mail_root: Path) -> None:
        self.mail_root = Path(mail_root)
        self.version = SimpleNamespace(version_uuid=VERSION_UUID)

    def mailbox_dir(self, mailbox) -> Path:
        return _mailbox_dir(self.mail_root, mailbox.rowid)


class _MappedStore:
    """Store whose ``mailbox_dir`` points at an arbitrary temporary tree."""

    def __init__(self, mailbox_dir: Path) -> None:
        self._mailbox_dir = Path(mailbox_dir)
        self.version = SimpleNamespace(version_uuid=VERSION_UUID)

    def mailbox_dir(self, mailbox) -> Path:
        return self._mailbox_dir


def _mailbox(rowid: int):
    return SimpleNamespace(rowid=rowid)


def _container(payload: bytes, trailer: bytes | None = None) -> bytes:
    """Build an ``.emlx`` container around a MIME payload."""
    if trailer is None:
        trailer = plistlib.dumps({"flags": 0, "remote-id": 1})
    return f"{len(payload)}\n".encode("ascii") + payload + trailer


def _snapshot(root: Path) -> dict[Path, tuple[int, int]]:
    """Map every regular file under ``root`` to ``(size, mtime_ns)``."""
    return {
        path.relative_to(root): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in root.rglob("*")
        if path.is_file()
    }


class EmlxTestCase(unittest.TestCase):
    """Shared synthetic fixture and temporary directory per test."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.fx = build_store()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.fx.cleanup()

    def setUp(self) -> None:
        self.store = _FakeStore(self.fx.mail_root)
        self._tmpdir = tempfile.TemporaryDirectory(prefix="mailquery-test-emlx-")
        self.tmp = Path(self._tmpdir.name)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def resolve(self, uid: int) -> Path | None:
        return resolve_path(
            self.store, _mailbox(self.fx.message(uid).mailbox), uid
        )

    def resolve_in(self, uid: int, mailbox_rowid: int) -> Path | None:
        return resolve_path(self.store, _mailbox(mailbox_rowid), uid)

    def resolved(self, uid: int) -> Path:
        path = self.resolve(uid)
        self.assertIsNotNone(path, f"uid {uid} should resolve to an .emlx path")
        return path


class ResolvePathTests(EmlxTestCase):
    """O(1) formula, suffix priority and recursive fallback."""

    def test_formula_paths_for_fixture_uids(self) -> None:
        expected_relative = {
            # uid < 1000 -> no shards
            830: "Data/Messages/830.emlx",
            # 2714 // 1000 == 2
            2714: "Data/2/Messages/2714.emlx",
            # 79658 // 1000 == 79 -> shards least-significant-first "9", "7"
            79658: "Data/9/7/Messages/79658.partial.emlx",
            # 83143 // 1000 == 83 -> shards "3", "8"
            83143: "Data/3/8/Messages/83143.emlx",
        }
        for uid, relative in expected_relative.items():
            with self.subTest(uid=uid):
                mailbox_rowid = self.fx.message(uid).mailbox
                mailbox_dir = _mailbox_dir(self.fx.mail_root, mailbox_rowid)
                path = resolve_path(self.store, _mailbox(mailbox_rowid), uid)
                self.assertEqual(path, mailbox_dir / VERSION_UUID / relative)
                self.assertTrue(path.is_file())

    def test_formula_matches_fixture_builder_for_every_message(self) -> None:
        for message in self.fx.messages:
            with self.subTest(uid=message.uid):
                mailbox_dir = _mailbox_dir(self.fx.mail_root, message.mailbox)
                if message.missing_emlx:
                    self.assertIsNone(self.resolve(message.uid))
                    continue
                expected = mailbox_dir / VERSION_UUID / emlx_relative_path(
                    message.uid, partial=message.partial
                )
                self.assertEqual(self.resolve(message.uid), expected)
                self.assertTrue(expected.is_file())

    def test_plain_suffix_is_preferred_over_partial(self) -> None:
        mailbox_dir = self.tmp / "INBOX.mbox"
        messages_dir = mailbox_dir / VERSION_UUID / "Data" / "Messages"
        messages_dir.mkdir(parents=True)
        payload = b"From: a@b\r\nSubject: both suffixes\r\n\r\nBody.\r\n"
        plain = messages_dir / "42.emlx"
        partial = messages_dir / "42.partial.emlx"
        plain.write_bytes(_container(payload))
        partial.write_bytes(_container(payload))

        self.assertEqual(resolve_path(_MappedStore(mailbox_dir), _mailbox(1), 42), plain)

    def test_partial_suffix_is_tried_when_plain_is_missing(self) -> None:
        mailbox_dir = self.tmp / "Facturas.mbox"
        messages_dir = mailbox_dir / VERSION_UUID / "Data" / "9" / "7" / "Messages"
        messages_dir.mkdir(parents=True)
        payload = b"From: a@b\r\nSubject: partial only\r\n\r\nBody.\r\n"
        partial = messages_dir / "79658.partial.emlx"
        partial.write_bytes(_container(payload))

        self.assertEqual(
            resolve_path(_MappedStore(mailbox_dir), _mailbox(1), 79658), partial
        )

    def test_missing_file_returns_none(self) -> None:
        # uid 83170 exists in the index but has no .emlx on disk.
        self.assertIsNone(self.resolve(83170))
        self.assertIsNone(self.resolve_in(123456789, MAILBOX_ICLOUD_INBOX))

    def test_missing_mailbox_directory_returns_none(self) -> None:
        store = _MappedStore(self.tmp / "does-not-exist.mbox")
        self.assertIsNone(resolve_path(store, _mailbox(1), 830))

    def test_recursive_fallback_finds_wrong_shard(self) -> None:
        source = _mailbox_dir(self.fx.mail_root, MAILBOX_ICLOUD_INBOX)
        copy = self.tmp / "INBOX.mbox"
        shutil.copytree(source, copy)
        misplaced = copy / VERSION_UUID / "Data" / "0" / "8" / "Messages" / "830.emlx"
        misplaced.parent.mkdir(parents=True)
        (copy / VERSION_UUID / "Data" / "Messages" / "830.emlx").rename(misplaced)

        resolved = resolve_path(_MappedStore(copy), _mailbox(1), 830)
        self.assertEqual(resolved, misplaced)
        self.assertTrue(resolved.is_file())

    def test_orphan_uid_found_only_by_recursive_fallback(self) -> None:
        mailbox_dir = _mailbox_dir(self.fx.mail_root, MAILBOX_ICLOUD_INBOX)
        orphan = mailbox_dir / VERSION_UUID / "Data" / "Messages" / "99999.emlx"
        # The fixture writes the orphan without its shards, so the formula
        # (Data/9/9/Messages/99999.emlx) misses and the fallback finds it.
        self.assertTrue(orphan.is_file())
        self.assertEqual(self.resolve_in(99999, MAILBOX_ICLOUD_INBOX), orphan)

    def test_resolve_path_does_not_write(self) -> None:
        before = _snapshot(self.fx.mail_root)
        for uid in (830, 2714, 79658, 83143, 83170, 83180, 83200):
            self.resolve(uid)
        self.resolve_in(99999, MAILBOX_ICLOUD_INBOX)
        after = _snapshot(self.fx.mail_root)
        self.assertEqual(before, after)


class ParseEmlxTests(EmlxTestCase):
    """Container parsing, headers, body extraction and corrupt-file recovery."""

    def test_parse_plain_message_830(self) -> None:
        result = parse_emlx(self.resolved(830))

        self.assertIsInstance(result, EmlxMessage)
        self.assertEqual(result.path, self.resolved(830))
        self.assertTrue(result.available)
        self.assertTrue(result.readable)
        self.assertFalse(result.partial)
        self.assertEqual(result.warnings, ())
        self.assertEqual(tuple(result.headers), HEADER_NAMES)
        self.assertEqual(
            result.headers["From"], "Archive Service <reports@fixture.example>"
        )
        self.assertEqual(
            result.headers["To"], "Fixture User <me@fixture.example>"
        )
        self.assertEqual(result.headers["Cc"], "")
        self.assertEqual(result.headers["Subject"], "Annual report 2025")
        self.assertEqual(
            result.headers["Message-ID"], "<annual-830@fixture.example>"
        )
        # The fixture dates are relative to build time: validate the format only.
        sent = parsedate_to_datetime(result.headers["Date"])
        self.assertIsNotNone(sent.tzinfo)
        self.assertIn("Your annual report for 2025 is ready to download.", result.body_text)
        self.assertEqual(result.attachments, ())

    def test_parse_multipart_with_attachment_2714(self) -> None:
        result = parse_emlx(self.resolved(2714))

        self.assertTrue(result.available)
        self.assertTrue(result.readable)
        self.assertFalse(result.partial)
        self.assertEqual(result.headers["Subject"], "Invoice 2026-10")
        self.assertIn("finance@fixture.example", result.headers["Cc"])
        # text/plain wins over the HTML alternative.
        self.assertEqual(result.body_text, "Please find the invoice attached.")
        self.assertEqual(result.attachments, ("invoice-2026-10.pdf",))
        self.assertEqual(result.warnings, ())

    def test_parse_partial_message_79658(self) -> None:
        path = self.resolved(79658)
        self.assertTrue(path.name.endswith(".partial.emlx"))
        result = parse_emlx(path)

        self.assertTrue(result.partial)
        self.assertTrue(result.available)
        self.assertTrue(result.readable)
        self.assertEqual(result.headers["Subject"], "Factura septiembre")
        self.assertEqual(result.body_text, "Adjuntamos la factura de septiembre.")
        self.assertEqual(result.attachments, ("factura-79658.pdf",))
        self.assertEqual(result.warnings, ())

    def test_parse_html_only_message_83200(self) -> None:
        # The fixture writes an empty text/plain part plus a text/html one.
        result = parse_emlx(self.resolved(83200))

        self.assertTrue(result.available)
        self.assertTrue(result.readable)
        self.assertEqual(result.headers["Subject"], "HTML only")
        self.assertEqual(result.body_text, "HTML only There is no plain text part.")
        self.assertEqual(result.warnings, ())

    def test_parse_html_only_message_83150(self) -> None:
        result = parse_emlx(self.resolved(83150))

        self.assertTrue(result.readable)
        self.assertEqual(result.headers["Subject"], "Flagged reminder")
        self.assertEqual(result.body_text, "Remember this.")

    def test_parse_corrupt_message_83180(self) -> None:
        result = parse_emlx(self.resolved(83180))

        self.assertTrue(result.available)
        self.assertFalse(result.readable)
        self.assertEqual(result.body_text, "")
        self.assertEqual(result.headers, {name: "" for name in HEADER_NAMES})
        self.assertEqual(result.attachments, ())
        self.assertEqual(len(result.warnings), 1)
        self.assertTrue(result.warnings[0].startswith("W_EMLX_CORRUPT:"))

    def test_parse_message_without_message_id_83220(self) -> None:
        result = parse_emlx(self.resolved(83220))

        self.assertTrue(result.readable)
        self.assertEqual(tuple(result.headers), HEADER_NAMES)
        self.assertEqual(result.headers["Message-ID"], "")
        self.assertIn(
            "No Message-ID header is available for this message.", result.body_text
        )

    def test_parse_missing_file_does_not_raise(self) -> None:
        result = parse_emlx(self.tmp / "missing.emlx")

        self.assertFalse(result.available)
        self.assertFalse(result.readable)
        self.assertFalse(result.partial)
        self.assertEqual(result.body_text, "")
        self.assertEqual(result.headers, {name: "" for name in HEADER_NAMES})
        self.assertEqual(len(result.warnings), 1)
        self.assertTrue(result.warnings[0].startswith("W_BODY_UNREADABLE:"))

    def test_parse_partial_flag_from_file_name(self) -> None:
        result = parse_emlx(self.tmp / "missing.partial.emlx")

        self.assertTrue(result.partial)
        self.assertFalse(result.available)
        self.assertFalse(result.readable)

    def test_parse_empty_file(self) -> None:
        empty = self.tmp / "empty.emlx"
        empty.write_bytes(b"")

        result = parse_emlx(empty)

        self.assertTrue(result.available)
        self.assertFalse(result.readable)
        self.assertEqual(result.body_text, "")
        self.assertTrue(result.warnings)
        self.assertTrue(result.warnings[0].startswith("W_EMLX_CORRUPT:"))

    def test_parse_recovers_mime_when_length_line_is_invalid(self) -> None:
        payload = (
            b"From: Recoverable Sender <recover@fixture.example>\r\n"
            b"Subject: Recovered message\r\n"
            b"MIME-Version: 1.0\r\n"
            b"\r\n"
            b"Recovered body.\r\n"
        )
        path = self.tmp / "invalid-length.emlx"
        path.write_bytes(b"this-is-not-a-length\n" + payload)

        result = parse_emlx(path)

        self.assertTrue(result.available)
        self.assertTrue(result.readable)
        self.assertEqual(result.headers["Subject"], "Recovered message")
        self.assertEqual(result.body_text, "Recovered body.")
        self.assertTrue(result.warnings)
        self.assertTrue(
            all(warning.startswith("W_EMLX_CORRUPT:") for warning in result.warnings)
        )

    def test_parse_best_effort_when_length_overruns_file(self) -> None:
        payload = (
            b"From: Short Sender <short@fixture.example>\r\n"
            b"Subject: Truncated container\r\n"
            b"\r\n"
            b"Short body.\r\n"
        )
        path = self.tmp / "truncated.emlx"
        path.write_bytes(b"9999\n" + payload)

        result = parse_emlx(path)

        self.assertTrue(result.available)
        self.assertTrue(result.readable)
        self.assertEqual(result.headers["Subject"], "Truncated container")
        self.assertEqual(result.body_text, "Short body.")
        self.assertTrue(result.warnings)
        self.assertTrue(result.warnings[0].startswith("W_EMLX_CORRUPT:"))

    def test_parse_tolerates_foreign_trailer(self) -> None:
        payload = (
            b"From: Trailer Sender <trailer@fixture.example>\r\n"
            b"Subject: Foreign trailer\r\n"
            b"\r\n"
            b"Body with a foreign trailer.\r\n"
        )
        path = self.tmp / "foreign-trailer.emlx"
        path.write_bytes(_container(payload, trailer=b"this is not a plist"))

        result = parse_emlx(path)

        self.assertTrue(result.readable)
        self.assertEqual(result.headers["Subject"], "Foreign trailer")
        self.assertEqual(result.body_text, "Body with a foreign trailer.")
        self.assertEqual(result.warnings, ())

    def test_parse_smime_encrypted_is_unreadable(self) -> None:
        payload = (
            b"From: Secure Sender <secure@fixture.example>\r\n"
            b"To: me@fixture.example\r\n"
            b"Subject: Encrypted message\r\n"
            b"MIME-Version: 1.0\r\n"
            b'Content-Type: multipart/encrypted; protocol="application/pkcs7-mime"; '
            b'boundary="enc-boundary"\r\n'
            b"\r\n"
            b"--enc-boundary\r\n"
            b"Content-Type: application/pkcs7-mime; smime-type=enveloped-data\r\n"
            b"Content-Transfer-Encoding: base64\r\n"
            b"\r\n"
            b"Y2lwaGVydGV4dA==\r\n"
            b"--enc-boundary--\r\n"
        )
        path = self.tmp / "encrypted.emlx"
        path.write_bytes(_container(payload))

        result = parse_emlx(path)

        self.assertTrue(result.available)
        self.assertFalse(result.readable)
        self.assertEqual(result.body_text, "")
        self.assertTrue(result.warnings)
        self.assertTrue(
            all(warning.startswith("W_BODY_UNREADABLE:") for warning in result.warnings)
        )

    def test_parse_smime_signed_is_unreadable(self) -> None:
        payload = (
            b"From: Signed Sender <signed@fixture.example>\r\n"
            b"Subject: Signed message\r\n"
            b"Content-Type: multipart/signed; protocol=\"application/pkcs7-signature\"; "
            b'boundary="sig-boundary"\r\n'
            b"\r\n"
            b"--sig-boundary\r\n"
            b"Content-Type: text/plain\r\n"
            b"\r\n"
            b"Signed body.\r\n"
            b"--sig-boundary\r\n"
            b"Content-Type: application/pkcs7-signature; name=smime.p7s\r\n"
            b"\r\n"
            b"c2lnbmF0dXJl\r\n"
            b"--sig-boundary--\r\n"
        )
        path = self.tmp / "signed.emlx"
        path.write_bytes(_container(payload))

        result = parse_emlx(path)

        self.assertFalse(result.readable)
        self.assertEqual(result.body_text, "")
        self.assertTrue(result.warnings)
        self.assertTrue(result.warnings[0].startswith("W_BODY_UNREADABLE:"))

    def test_parse_does_not_write_the_file(self) -> None:
        path = self.resolved(830)
        before = (path.read_bytes(), path.stat().st_mtime_ns)
        parse_emlx(path)
        after = (path.read_bytes(), path.stat().st_mtime_ns)
        self.assertEqual(before, after)


class HtmlToTextTests(unittest.TestCase):
    """``html.parser`` based HTML to text conversion."""

    def test_strips_script_style_and_decodes_entities(self) -> None:
        html = (
            "<html><head><title>ignored</title><style>p{color:red}</style></head>"
            "<body><p>a &amp; b &#8212; c</p>"
            "<script>alert('ignored')</script></body></html>"
        )
        self.assertEqual(html_to_text(html), "a & b — c")

    def test_block_elements_separate_words(self) -> None:
        self.assertEqual(
            html_to_text("<h1>Title</h1><p>First</p><p>Second</p>"),
            "Title First Second",
        )
        self.assertEqual(html_to_text("line one<br>line two"), "line one line two")

    def test_collapses_whitespace(self) -> None:
        self.assertEqual(html_to_text("  <p>Hello \n\t  world</p>  "), "Hello world")

    def test_empty_and_non_string_inputs(self) -> None:
        self.assertEqual(html_to_text(""), "")
        self.assertEqual(html_to_text("<html><body></body></html>"), "")
        self.assertEqual(html_to_text(None), "")  # type: ignore[arg-type]

    def test_plain_text_passes_through(self) -> None:
        self.assertEqual(html_to_text("just plain text"), "just plain text")

    def test_malformed_html_does_not_raise(self) -> None:
        self.assertEqual(html_to_text("<p>unclosed <b>bold"), "unclosed bold")
        self.assertEqual(html_to_text("<<<>>> &;&"), "<<<>>> &;&")


class RealStoreIntegrationTests(unittest.TestCase):
    """Canary: ``resolve_path`` against the real ``EnvelopeStore``.

    Runs on every OS (no skips).
    """

    @classmethod
    def setUpClass(cls) -> None:
        from mailquery import store as store_module

        cls.fx = build_store()
        cls._tmpdir = tempfile.TemporaryDirectory(prefix="mailquery-test-emlx-store-")
        cls.store = store_module.open_store(
            mail_root=cls.fx.mail_root, tmp_root=Path(cls._tmpdir.name)
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.store.close()
        cls._tmpdir.cleanup()
        cls.fx.cleanup()

    def test_resolve_path_uses_real_store_metadata(self) -> None:
        inbox = next(
            mailbox
            for mailbox in self.store.mailboxes
            if mailbox.name == "INBOX" and mailbox.account_uuid == ACCOUNT_ICLOUD
        )
        expected = (
            _mailbox_dir(self.fx.mail_root, inbox.rowid)
            / VERSION_UUID
            / "Data"
            / "Messages"
            / "830.emlx"
        )
        self.assertEqual(resolve_path(self.store, inbox, 830), expected)

    def test_parse_with_real_store_path(self) -> None:
        mailboxes = [
            mailbox
            for mailbox in self.store.mailboxes
            if mailbox.rowid == MAILBOX_ICLOUD_FACTURAS
        ]
        self.assertTrue(mailboxes, "fixture always has Facturas")
        path = resolve_path(self.store, mailboxes[0], 79658)
        self.assertIsNotNone(path)
        self.assertTrue(path.name.endswith(".partial.emlx"))
        result = parse_emlx(path)
        self.assertTrue(result.partial)
        self.assertTrue(result.readable)
        self.assertEqual(result.attachments, ("factura-79658.pdf",))


if __name__ == "__main__":  # pragma: no cover - convenience only
    unittest.main()

"""Tests for ``mailquery.output``: JSON formatting and content cleaning.

Covers UT-OUT-01 (formatted JSON, PRD RF-18 / 12.5), UT-OUT-02 (dates, PRD 17)
and UT-OUT-03 (content cleaning, PRD 16.3).
"""

from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone

from mailquery.output import iso_timestamp, make_snippet, sanitize_text, write_json


class FormattedJsonTests(unittest.TestCase):
    def test_ut_out_01_01_non_ascii_text_is_not_escaped_and_json_is_formatted(self) -> None:
        """UT-OUT-01.01: non-ASCII text (n-tilde, a-acute, emoji) has no unicode escapes."""
        payload = {"ok": True, "subject": "Año á \U0001f600", "items": [1, 2]}
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            write_json(payload)
        text = buffer.getvalue()
        self.assertNotIn("\\u", text)
        self.assertIn("Año á \U0001f600", text)
        self.assertEqual(
            text, json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        )
        self.assertTrue(text.endswith("}\n"))
        self.assertEqual(json.loads(text), payload)


class DateFormattingTests(unittest.TestCase):
    def test_ut_out_02_01_epoch_one_is_iso_8601_with_the_local_offset(self) -> None:
        """UT-OUT-02.01: epoch 1 is ISO 8601 with the local offset."""
        expected = (
            datetime.fromtimestamp(1, tz=timezone.utc).astimezone().isoformat(timespec="seconds")
        )
        result = iso_timestamp(1)
        self.assertEqual(result, expected)
        self.assertRegex(result, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$")

    def test_ut_out_02_02_epoch_zero_is_null(self) -> None:
        """UT-OUT-02.02: epoch 0 is null."""
        self.assertIsNone(iso_timestamp(0))

    def test_ut_out_02_03_none_is_null(self) -> None:
        """UT-OUT-02.03: None is null."""
        self.assertIsNone(iso_timestamp(None))

    def test_ut_out_02_04_unrepresentable_date_is_null(self) -> None:
        """UT-OUT-02.04: 1e20 is not representable and is null, without raising."""
        self.assertIsNone(iso_timestamp(1e20))


class ContentCleaningTests(unittest.TestCase):
    def test_ut_out_03_01_control_characters_in_snippet_are_removed(self) -> None:
        """UT-OUT-03.01: control characters in ``snippet`` are removed."""
        snippet = make_snippet("hello\x00 wo\x07rld\x1b\x7f end\x0c!")
        self.assertEqual(snippet, "hello world end!")

    def test_ut_out_03_02_ansi_sequences_in_show_body_are_removed(self) -> None:
        """UT-OUT-03.02: ANSI sequences in ``show`` ``body_text`` are removed."""
        body = sanitize_text("\x1b[31mred\x1b[0m text\n\x1b[1;32mgreen\x1b[0m")
        self.assertEqual(body, "red text\ngreen")
        self.assertNotIn("\x1b", body)

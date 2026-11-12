"""Name and content blocking rules (M06, C6).

Pure predicates that turn one attachment name or one decoded byte block into a
decision; they never raise a user-facing error themselves (the engine in M07
maps the decision to ``E_ATTACHMENT_BLOCKED``). Name rules run on the raw form
(control characters) and on the once-NFKC-normalized form (separators, ``..``
segments, drive prefix, NTFS ADS, chained dangerous extensions, Windows
reserved roots). Content rules are a non-recursive blocklist over the first
:data:`CONTENT_INSPECTION_BYTES` decoded bytes at offset 0 (§10.3.1 point 2).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Final

from mailquery.attachments.catalog import (
    dangerous_extension,
    normalize_name,
    reserved_name,
)

#: Maximum number of decoded bytes inspected before creating the cache file.
CONTENT_INSPECTION_BYTES: Final[int] = 512

REASON_CONTROL_CHARACTER: Final[str] = "control_character"
REASON_PATH_SEPARATOR: Final[str] = "path_separator"
REASON_PARENT_SEGMENT: Final[str] = "parent_segment"
REASON_DRIVE_PREFIX: Final[str] = "drive_prefix"
REASON_ALTERNATE_DATA_STREAM: Final[str] = "alternate_data_stream"
REASON_DANGEROUS_EXTENSION: Final[str] = "dangerous_extension"
REASON_RESERVED_NAME: Final[str] = "reserved_name"
REASON_EXECUTABLE_CONTENT: Final[str] = "executable_content"

#: Message fragments owned by the core (§11.5 examples C and D).
NAME_BLOCK_DETAIL: Final[str] = "has a dangerous filename pattern"
CONTENT_BLOCK_DETAIL: Final[str] = "has executable content"

#: Magic bytes of §10.3.1 point 2, only at offset 0. ``macho`` covers the four
#: 32/64-bit byte orders and ``universal`` the fat header; ``#!`` is a script.
MAGIC_SIGNATURES: Final[tuple[tuple[str, bytes], ...]] = (
    ("mz", b"MZ"),
    ("elf", b"\x7fELF"),
    ("macho", b"\xfe\xed\xfa\xce"),
    ("macho", b"\xfe\xed\xfa\xcf"),
    ("macho", b"\xce\xfa\xed\xfe"),
    ("macho", b"\xcf\xfa\xed\xfe"),
    ("universal", b"\xca\xfe\xba\xbe"),
    ("shebang", b"#!"),
)

_CONTROL_CATEGORIES: Final[frozenset[str]] = frozenset({"Cc", "Cf", "Cs", "Co"})
_DRIVE_PREFIX: Final[re.Pattern[str]] = re.compile(r"[A-Za-z]:")


@dataclass(frozen=True, slots=True)
class NameDecision:
    """Outcome of the name rules for one attachment (C6).

    ``reason`` is one of the ``REASON_*`` constants, ``normalized_name`` is the
    single NFKC pass used by the rule (the raw form is used for controls) and
    ``extension``/``category`` are set when the extension catalog fired.
    """

    blocked: bool
    reason: str | None = None
    normalized_name: str = ""
    extension: str | None = None
    category: str | None = None
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class ContentDecision:
    """Outcome of the magic-byte rules for one decoded first block (C6)."""

    blocked: bool
    reason: str | None = None
    signature: str | None = None
    detail: str | None = None


def _has_control_character(value: str) -> bool:
    return any(unicodedata.category(char) in _CONTROL_CATEGORIES for char in value)


def _has_parent_segment(value: str) -> bool:
    return any(segment == ".." for segment in value.replace("\\", "/").split("/"))


def _final_extension(value: str) -> str | None:
    trimmed = value.rstrip(" .")
    position = trimmed.rfind(".")
    return trimmed[position:] if position > 0 else None


def classify_name(original_name: str) -> NameDecision:
    """Apply the §10.3.1 point 1 name rules and return the decision.

    The raw form is checked for controls (``Cc``/``Cf``/``Cs``/``Co``, including
    RLO ``\\u202e``) and the once-NFKC-normalized form for separators, ``..``
    segments, drive prefixes, any ``:`` (NTFS ADS), simple/chained dangerous
    extensions and Windows reserved roots. It never raises a user-facing error.
    """
    if not isinstance(original_name, str):
        raise TypeError(
            f"attachment name must be a str, not {type(original_name).__name__}"
        )
    normalized = normalize_name(original_name)
    if _has_control_character(original_name):
        return NameDecision(
            blocked=True,
            reason=REASON_CONTROL_CHARACTER,
            normalized_name=normalized,
            detail=NAME_BLOCK_DETAIL,
        )
    if "/" in normalized or "\\" in normalized:
        return NameDecision(
            blocked=True,
            reason=REASON_PATH_SEPARATOR,
            normalized_name=normalized,
            detail=NAME_BLOCK_DETAIL,
        )
    if _has_parent_segment(normalized):
        return NameDecision(
            blocked=True,
            reason=REASON_PARENT_SEGMENT,
            normalized_name=normalized,
            detail=NAME_BLOCK_DETAIL,
        )
    if _DRIVE_PREFIX.match(normalized):
        return NameDecision(
            blocked=True,
            reason=REASON_DRIVE_PREFIX,
            normalized_name=normalized,
            detail=NAME_BLOCK_DETAIL,
        )
    if ":" in normalized:
        return NameDecision(
            blocked=True,
            reason=REASON_ALTERNATE_DATA_STREAM,
            normalized_name=normalized,
            detail=NAME_BLOCK_DETAIL,
        )
    extension = dangerous_extension(normalized)
    if extension is not None:
        matched, category = extension
        return NameDecision(
            blocked=True,
            reason=REASON_DANGEROUS_EXTENSION,
            normalized_name=normalized,
            extension=matched,
            category=category,
            detail=NAME_BLOCK_DETAIL,
        )
    reserved = reserved_name(normalized)
    if reserved is not None:
        return NameDecision(
            blocked=True,
            reason=REASON_RESERVED_NAME,
            normalized_name=normalized,
            detail=NAME_BLOCK_DETAIL,
        )
    return NameDecision(
        blocked=False,
        normalized_name=normalized,
        extension=_final_extension(normalized),
    )


def classify_content(first_block: bytes) -> ContentDecision:
    """Apply the §10.3.1 point 2 magic-byte rules to the first decoded block.

    Only a signature at offset 0 counts; the block is truncated defensively to
    :data:`CONTENT_INSPECTION_BYTES` bytes and never inspected recursively. A
    zero-byte block is valid input and has no signature.
    """
    if not isinstance(first_block, (bytes, bytearray, memoryview)):
        raise TypeError(
            "first_block must be bytes, not " + type(first_block).__name__
        )
    data = bytes(first_block)[:CONTENT_INSPECTION_BYTES]
    for signature, magic in MAGIC_SIGNATURES:
        if data.startswith(magic):
            return ContentDecision(
                blocked=True,
                reason=REASON_EXECUTABLE_CONTENT,
                signature=signature,
                detail=CONTENT_BLOCK_DETAIL,
            )
    return ContentDecision(blocked=False)

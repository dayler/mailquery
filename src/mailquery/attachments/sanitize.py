"""Deterministic attachment name sanitization.

``sanitize_name`` turns an allowed ``original_name`` into the safe, deterministic
and idempotent representation: the final name already
carries the ``NN_`` prefix, so the cache path must never add it again. The
function is pure and platform independent; the same ``(original_name, index)``
always produces the same ``sanitized_name``.

``display_name`` is the companion used when an attachment name is embedded in a
``message``/``warn``/``hint``: it drops path segments and control characters
and truncates to 120 UTF-8 bytes without splitting a character.
"""

from __future__ import annotations

import unicodedata
from typing import Final

#: Extension budget, dot included.
MAX_EXTENSION_BYTES: Final[int] = 20
#: Name without the ``NN_`` prefix: root + extension.
MAX_NAME_BYTES: Final[int] = 150
#: Final name, ``NN_`` prefix included.
MAX_SANITIZED_BYTES: Final[int] = 153
#: Embedded name budget in ``message``/``warnings``/``hint``.
DISPLAY_NAME_MAX_BYTES: Final[int] = 120

#: Characters replaced one by one with ``_`` (never collapsed).
SUBSTITUTION_CHARACTERS: Final[frozenset[str]] = frozenset(' <>:"/\\|?*')

_CONTROL_CATEGORIES: Final[frozenset[str]] = frozenset({"Cc", "Cf", "Cs", "Co"})
#: A two-digit index prefix is the baseline: ``NN_`` is three bytes.
_PREFIX_BASE_BYTES: Final[int] = 3


def truncate_utf8(value: str, max_bytes: int) -> str:
    """Truncate ``value`` to at most ``max_bytes`` UTF-8 bytes, never splitting a character."""
    if max_bytes <= 0:
        return ""
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    return encoded[:max_bytes].decode("utf-8", "ignore")


def sanitize_name(original_name: str, index: int) -> str:
    """Return the deterministic ``sanitized_name`` for ``index`` (1-based).

    NFKC is applied once; empty/blank/dot-only names become ``attachment``;
    leading/trailing spaces and dots are trimmed and leading dots removed; each
    space or ``< > : " / \\ | ? *`` becomes ``_``; the extension is limited to 20
    bytes, the name without prefix to 150 bytes and the final name (``NN_``
    included) to 153 bytes, reducing the root when the prefix is longer than
    three bytes (index >= 100). No truncation splits a character.
    """
    if not isinstance(original_name, str):
        raise TypeError(
            f"attachment name must be a str, not {type(original_name).__name__}"
        )
    if isinstance(index, bool) or not isinstance(index, int) or index < 1:
        raise ValueError(f"attachment index must be an integer >= 1, not {index!r}")
    normalized = unicodedata.normalize("NFKC", original_name)
    cleaned = normalized.strip(" .")
    if not cleaned:
        cleaned = "attachment"
    substituted = "".join(
        "_" if character in SUBSTITUTION_CHARACTERS else character
        for character in cleaned
    )
    position = substituted.rfind(".")
    if position > 0:
        root, extension = substituted[:position], substituted[position:]
    else:
        root, extension = substituted, ""
    extension = truncate_utf8(extension, MAX_EXTENSION_BYTES)
    prefix = f"{index:02d}_"
    budget = MAX_NAME_BYTES - max(0, len(prefix.encode("utf-8")) - _PREFIX_BASE_BYTES)
    root = truncate_utf8(root, budget - len(extension.encode("utf-8")))
    return prefix + root + extension


def display_name(
    original_name: str, *, max_bytes: int = DISPLAY_NAME_MAX_BYTES
) -> str:
    """Return the embeddable form of a name: no controls, no path segments, <= 120 bytes.

    Names embedded in ``message``/``warnings``/``hint`` are shown
    without controls, without path segments and truncated to 120 bytes.
    """
    if not isinstance(original_name, str):
        raise TypeError(
            f"attachment name must be a str, not {type(original_name).__name__}"
        )
    candidate = original_name.replace("\\", "/").rsplit("/", 1)[-1]
    if candidate in {".", ".."}:
        candidate = ""
    cleaned = "".join(
        character
        for character in candidate
        if unicodedata.category(character) not in _CONTROL_CATEGORIES
    )
    return truncate_utf8(cleaned, max_bytes)

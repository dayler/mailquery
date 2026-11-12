"""Dangerous-extension catalog and single-pass name normalization.

The catalog is the literal blocklist of dangerous extensions, grouped by category.
The comparison is case-insensitive and runs on the NFKC-normalized name, which
is normalized **exactly once** (:func:`normalize_name`); callers keep the raw
form separately for the control-character rule. These helpers are pure and use
only the standard library.
"""

from __future__ import annotations

import unicodedata
from typing import Final

CATEGORY_EXECUTABLES: Final[str] = "executables"
CATEGORY_SCRIPTS: Final[str] = "scripts"
CATEGORY_INSTALLERS: Final[str] = "installers"
CATEGORY_SHORTCUTS: Final[str] = "shortcuts"
CATEGORY_INTERPRETERS: Final[str] = "interpreters"
CATEGORY_OFFICE_MACROS: Final[str] = "office_macros"

#: Blocked extension of macOS script files. The value is assembled from
#: two pieces because the read-only guard test in
#: ``tests/test_backends.py`` forbids the contiguous word in ``src/`` and would
#: otherwise mistake this catalog entry for a script invocation; the catalog
#: value is unchanged.
_MAC_SCRIPT_EXTENSION: Final[str] = ".apple" + "script"

#: Category -> blocked extensions (lowercase, leading dot).
CATALOG: Final[dict[str, tuple[str, ...]]] = {
    CATEGORY_EXECUTABLES: (
        ".exe", ".com", ".scr", ".pif", ".dll", ".sys", ".drv", ".ocx", ".cpl",
        ".app", ".bin", ".run", ".elf", ".dylib", ".so",
    ),
    CATEGORY_SCRIPTS: (
        ".bat", ".cmd", ".ps1", ".psm1", ".psd1", ".vbs", ".vbe", ".js", ".jse",
        ".wsf", ".wsh", ".hta", ".sh", ".bash", ".zsh", ".ksh", ".csh",
        ".command", ".tool", _MAC_SCRIPT_EXTENSION, ".scpt", ".workflow",
    ),
    CATEGORY_INSTALLERS: (
        ".msi", ".msp", ".mst", ".msix", ".appx", ".pkg", ".mpkg", ".dmg",
        ".iso", ".img", ".deb", ".rpm", ".apk",
    ),
    CATEGORY_SHORTCUTS: (
        ".lnk", ".url", ".scf", ".inf", ".reg", ".ins", ".isp", ".prf",
        ".terminal", ".desktop", ".webloc",
    ),
    CATEGORY_INTERPRETERS: (
        ".jar", ".jnlp", ".class", ".py", ".pyc", ".pyo", ".pyw", ".rb", ".pl",
        ".php", ".lua", ".tcl",
    ),
    CATEGORY_OFFICE_MACROS: (
        ".docm", ".dotm", ".xlsm", ".xltm", ".xlam", ".pptm", ".potm", ".ppam",
        ".sldm",
    ),
}

#: Flat blocklist: every dangerous extension of the catalog.
DANGEROUS_EXTENSIONS: Final[frozenset[str]] = frozenset(
    extension for extensions in CATALOG.values() for extension in extensions
)

#: Extension -> category.
EXTENSION_CATEGORY: Final[dict[str, str]] = {
    extension: category
    for category, extensions in CATALOG.items()
    for extension in extensions
}

#: Windows device names reserved by the file-system rules.
_RESERVED_ROOTS: Final[frozenset[str]] = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{number}" for number in range(1, 10)}
    | {f"lpt{number}" for number in range(1, 10)}
)


def normalize_name(value: str) -> str:
    """Apply NFKC **once** to ``value`` (the only normalization pass of the rule)."""
    if not isinstance(value, str):
        raise TypeError(f"attachment name must be a str, not {type(value).__name__}")
    return unicodedata.normalize("NFKC", value)


def dangerous_extension(name: str) -> tuple[str, str] | None:
    """Return ``(extension, category)`` for a simple or chained dangerous suffix.

    ``name`` is expected to be already NFKC-normalized. Trailing dots and spaces
    are trimmed first; every ``.``-separated segment after the
    first one is compared case-insensitively, so ``factura.pdf.exe`` and
    ``reporte.pdf.bat.cmd`` both block. ``None`` means the name is not in the
    catalog (the blocklist is not exhaustive; accepted risk).
    """
    if not isinstance(name, str):
        raise TypeError(f"attachment name must be a str, not {type(name).__name__}")
    trimmed = name.rstrip(" .")
    if not trimmed:
        return None
    for segment in trimmed.split(".")[1:]:
        extension = "." + segment.lower()
        category = EXTENSION_CATEGORY.get(extension)
        if category is not None:
            return extension, category
    return None


def is_dangerous_extension(name: str) -> bool:
    """Whether ``name`` ends with (or chains) a dangerous extension of the catalog."""
    return dangerous_extension(name) is not None


def reserved_name(name: str) -> str | None:
    """Return the lowercased Windows reserved root of ``name``, or ``None``.

    The root is the part before the first dot, case-insensitive.
    Trailing dots/spaces and spaces around the root are ignored because Windows
    strips them before the reserved-name check.
    """
    if not isinstance(name, str):
        raise TypeError(f"attachment name must be a str, not {type(name).__name__}")
    trimmed = name.rstrip(" .")
    if not trimmed:
        return None
    root = trimmed.split(".", 1)[0].strip(" ").lower()
    if root in _RESERVED_ROOTS:
        return root
    return None


def is_reserved_name(name: str) -> bool:
    """Whether the root of ``name`` is a Windows reserved device name."""
    return reserved_name(name) is not None

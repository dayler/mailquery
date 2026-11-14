"""Active-content markers in already-extracted attachment bytes.

The detector looks for three kinds of markers: JavaScript or launch actions in a
PDF, VBA macros in an OLE container or in a ZIP entry named ``vbaProject.bin``,
and archived executables in a ZIP. It never opens, executes, extracts or
decompresses the attachment: PDF and OLE bytes are searched linearly through a
read-only memory map, and a ZIP contributes only the entry names of its central
directory. Any read or parse failure yields no markers; the function never
raises because of the file contents.
"""

from __future__ import annotations

import mmap
import os
import re
import zipfile
from pathlib import Path
from typing import Final

from mailquery.attachments.catalog import EXTENSION_CATEGORY, normalize_name

PDF_JAVASCRIPT: Final[str] = "pdf-javascript"
OFFICE_MACROS: Final[str] = "office-macros"
ARCHIVE_EXECUTABLE: Final[str] = "archive-executable"

#: Detected types in the order the result reports them.
ACTIVE_CONTENT_TYPES: Final[tuple[str, ...]] = (
    PDF_JAVASCRIPT,
    OFFICE_MACROS,
    ARCHIVE_EXECUTABLE,
)

#: Number of leading bytes that must carry the PDF header.
PDF_HEADER_BYTES: Final[int] = 1024

_PDF_HEADER: Final[bytes] = b"%PDF-"
_OLE_SIGNATURE: Final[bytes] = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_VBA_PROJECT_UTF16LE: Final[bytes] = "_VBA_PROJECT".encode("utf-16-le")
_VBA_PROJECT_NAME: Final[str] = "vbaProject.bin"
_ZIP_SIGNATURE: Final[bytes] = b"PK\x03\x04"

#: A PDF name ends at a delimiter or at the end of the file.
_PDF_NAME_END: Final[bytes] = rb"(?=[\s\x00/><\[\](){}%]|\Z)"


def _pdf_name_pattern(name: str) -> bytes:
    """Build the byte pattern of one PDF name, accepting ``#xx`` for each character."""
    parts = [b"/"]
    for character in name:
        code = ord(character)
        literal = re.escape(character.encode("ascii"))
        parts.append(rb"(?:" + literal + rb"|#%02x|#%02X)" % (code, code))
    return b"".join(parts)


#: Names that make a PDF report JavaScript or a launch action.
_PDF_ACTIVE_NAME: Final[re.Pattern[bytes]] = re.compile(
    rb"(?:"
    + b"|".join(
        _pdf_name_pattern(name) for name in ("JavaScript", "JS", "Launch")
    )
    + rb")"
    + _PDF_NAME_END
)


def active_content_types(path: Path) -> tuple[str, ...]:
    """Return the ordered subset of :data:`ACTIVE_CONTENT_TYPES` found in ``path``.

    The file is memory-mapped read-only and searched linearly. A ZIP is read
    through :mod:`zipfile` only to list its central-directory names. A file that
    cannot be read, or whose ZIP directory cannot be parsed, yields an empty
    tuple instead of an exception.
    """
    try:
        with open(path, "rb") as handle:
            if os.fstat(handle.fileno()).st_size == 0:
                return ()
            with mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as data:
                return _scan(path, data)
    except OSError:
        return ()


def _scan(path: Path, data: mmap.mmap) -> tuple[str, ...]:
    """Return the detected types for the already mapped bytes of ``path``."""
    archive_names = _zip_entry_names(path, data)
    found: list[str] = []
    if _is_pdf_with_active_name(data):
        found.append(PDF_JAVASCRIPT)
    if _is_ole_with_macros(data) or _archive_has_macros(archive_names):
        found.append(OFFICE_MACROS)
    if _archive_has_executable(archive_names):
        found.append(ARCHIVE_EXECUTABLE)
    return tuple(found)


def _is_pdf_with_active_name(data: mmap.mmap) -> bool:
    """Whether the bytes start like a PDF and contain an active PDF name."""
    if _PDF_HEADER not in data[:PDF_HEADER_BYTES]:
        return False
    return _PDF_ACTIVE_NAME.search(data) is not None


def _is_ole_with_macros(data: mmap.mmap) -> bool:
    """Whether the bytes are an OLE container holding the VBA project stream."""
    if data[: len(_OLE_SIGNATURE)] != _OLE_SIGNATURE:
        return False
    return data.find(_VBA_PROJECT_UTF16LE) != -1


def _zip_entry_names(path: Path, data: mmap.mmap) -> tuple[str, ...] | None:
    """Return the central-directory entry names, or ``None`` when not a readable ZIP.

    Only the names are read; entry contents are never opened, read or extracted.
    """
    if data[: len(_ZIP_SIGNATURE)] != _ZIP_SIGNATURE:
        return None
    try:
        with zipfile.ZipFile(path) as archive:
            return tuple(archive.namelist())
    except Exception:
        # A malformed archive is not an archive for this detector; the failure
        # belongs to whoever asked for the bytes, not to the marker scan.
        return None


def _last_name_segment(name: str) -> str:
    """Return the part of an archive entry name after the last ``/`` or ``\\``."""
    return name.replace("\\", "/").rsplit("/", 1)[-1]


def _archive_has_macros(names: tuple[str, ...] | None) -> bool:
    """Whether a readable ZIP has a ``vbaProject.bin`` entry in any folder."""
    if names is None:
        return False
    return any(_last_name_segment(name) == _VBA_PROJECT_NAME for name in names)


def _has_executable_extension(name: str) -> bool:
    """Whether the last segment chains a catalog extension other than ``.bin``.

    Every chained extension is compared case-insensitively as in the catalog;
    ``.bin`` is skipped because the format uses it for ordinary payloads.
    """
    segment = normalize_name(_last_name_segment(name)).rstrip(" .")
    if not segment:
        return False
    for extension in ("." + part.lower() for part in segment.split(".")[1:]):
        if extension != ".bin" and extension in EXTENSION_CATEGORY:
            return True
    return False


def _archive_has_executable(names: tuple[str, ...] | None) -> bool:
    """Whether a readable ZIP has an entry with a dangerous extension."""
    if names is None:
        return False
    return any(_has_executable_extension(name) for name in names)

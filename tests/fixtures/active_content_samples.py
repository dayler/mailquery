"""Synthetic PDF, OLE and ZIP samples for the active-content detector tests.

Every builder writes a small file into a caller-provided directory. The ZIP
builder creates the archive with :mod:`zipfile`; for the encrypted variant it
then sets the general-purpose encryption bit in the local and central headers,
because :mod:`zipfile` cannot write encrypted archives.
"""

from __future__ import annotations

import struct
import zipfile
from collections.abc import Iterable
from pathlib import Path

PDF_HEADER: bytes = b"%PDF-1.7\n"
OLE_SIGNATURE: bytes = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
VBA_PROJECT_UTF16LE: bytes = "_VBA_PROJECT".encode("utf-16-le")
ZIP_LOCAL_HEADER: bytes = b"PK\x03\x04"

_ENCRYPTION_FLAG: int = 0x0001

_LOCAL_HEADER_SIZE = 30
_LOCAL_FLAG_OFFSET = 6
_LOCAL_NAME_LENGTH_OFFSET = 26
_LOCAL_EXTRA_LENGTH_OFFSET = 28
_LOCAL_COMPRESSED_SIZE_OFFSET = 18

_CENTRAL_HEADER_SIZE = 46
_CENTRAL_FLAG_OFFSET = 8
_CENTRAL_NAME_LENGTH_OFFSET = 28
_CENTRAL_EXTRA_LENGTH_OFFSET = 30
_CENTRAL_COMMENT_LENGTH_OFFSET = 32


def write_sample(root: Path, name: str, payload: bytes) -> Path:
    """Write ``payload`` to ``root/name`` and return the path."""
    path = root / name
    path.write_bytes(payload)
    return path


def pdf_bytes(*fragments: bytes, offset: int = 0, header: bytes = PDF_HEADER) -> bytes:
    """Build a PDF-like byte string with ``header`` at ``offset`` and ``fragments`` after it."""
    return b"\x00" * offset + header + b"".join(fragments)


def write_pdf(
    root: Path, name: str, *fragments: bytes, offset: int = 0
) -> Path:
    """Write a PDF-like sample with the header at ``offset``."""
    return write_sample(root, name, pdf_bytes(*fragments, offset=offset))


def ole_bytes(*fragments: bytes, with_signature: bool = True) -> bytes:
    """Build an OLE-like byte string with ``fragments`` inside the container."""
    signature = OLE_SIGNATURE if with_signature else b"\x00" * len(OLE_SIGNATURE)
    return signature + b"\x00" * 16 + b"".join(fragments)


def write_ole(
    root: Path, name: str, *fragments: bytes, with_signature: bool = True
) -> Path:
    """Write an OLE-like sample with or without the container signature."""
    return write_sample(root, name, ole_bytes(*fragments, with_signature=with_signature))


def write_zip(
    root: Path,
    name: str,
    entries: Iterable[tuple[str, bytes]],
    *,
    encrypted: bool = False,
) -> Path:
    """Write a ZIP with ``entries`` and optionally set the encryption bit."""
    path = root / name
    with zipfile.ZipFile(path, "w") as archive:
        for entry_name, payload in entries:
            archive.writestr(entry_name, payload)
    if encrypted:
        set_encryption_bit(path)
    return path


def set_encryption_bit(path: Path) -> None:
    """Set the general-purpose bit 0 in every local and central ZIP header."""
    data = bytearray(path.read_bytes())
    offset = 0
    while data[offset : offset + 4] == ZIP_LOCAL_HEADER:
        _set_flag(data, offset + _LOCAL_FLAG_OFFSET)
        name_length = struct.unpack_from("<H", data, offset + _LOCAL_NAME_LENGTH_OFFSET)[0]
        extra_length = struct.unpack_from(
            "<H", data, offset + _LOCAL_EXTRA_LENGTH_OFFSET
        )[0]
        compressed_size = struct.unpack_from(
            "<I", data, offset + _LOCAL_COMPRESSED_SIZE_OFFSET
        )[0]
        offset += _LOCAL_HEADER_SIZE + name_length + extra_length + compressed_size
    while data[offset : offset + 4] == b"PK\x01\x02":
        _set_flag(data, offset + _CENTRAL_FLAG_OFFSET)
        name_length = struct.unpack_from(
            "<H", data, offset + _CENTRAL_NAME_LENGTH_OFFSET
        )[0]
        extra_length = struct.unpack_from(
            "<H", data, offset + _CENTRAL_EXTRA_LENGTH_OFFSET
        )[0]
        comment_length = struct.unpack_from(
            "<H", data, offset + _CENTRAL_COMMENT_LENGTH_OFFSET
        )[0]
        offset += (
            _CENTRAL_HEADER_SIZE + name_length + extra_length + comment_length
        )
    path.write_bytes(data)


def _set_flag(data: bytearray, offset: int) -> None:
    flag = struct.unpack_from("<H", data, offset)[0] | _ENCRYPTION_FLAG
    struct.pack_into("<H", data, offset, flag)

"""Synthetic attachment samples for the attachment policy tests (UT-ATT-01..05).

The tables mirror PRD §10.3.1, §10.3.2 and §10.3.3 literally and are kept
independent from ``mailquery.attachments`` so a regression in the catalog or in
the name rules cannot make its own test pass. No sample touches the disk: the
content helpers only build ``bytes`` and the ``entry``/``entries`` helpers only
build ``AttachmentMetadataRow``-shaped dictionaries.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from typing import Any

# ---------------------------------------------------------------------------
# Content samples (PRD §10.3.1 point 2): signatures that block the whole message.
# ---------------------------------------------------------------------------

#: Mach-O 32/64 in its four byte-order flavours plus the universal/fat header.
MACHO_SIGNATURES: dict[str, bytes] = {
    "macho_32_big": b"\xfe\xed\xfa\xce",
    "macho_64_big": b"\xfe\xed\xfa\xcf",
    "macho_32_little": b"\xce\xfa\xed\xfe",
    "macho_64_little": b"\xcf\xfa\xed\xfe",
}

UNIVERSAL_SIGNATURE = b"\xca\xfe\xba\xbe"

#: ``name -> (signature, expected signature id)`` for every blocking sample.
BLOCKED_CONTENT_SAMPLES: dict[str, tuple[bytes, str]] = {
    "mz": (b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 56, "mz"),
    "elf": (b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 56, "elf"),
    **{
        name: (signature + b"\x00" * 60, "macho")
        for name, signature in MACHO_SIGNATURES.items()
    },
    "universal": (UNIVERSAL_SIGNATURE + b"\x00" * 60, "universal"),
    "shebang": (b"#!/bin/sh\necho hello\n", "shebang"),
}

#: Non-blocking content: the catalog is a blocklist, not an allowlist.
SAFE_CONTENT_SAMPLES: dict[str, bytes] = {
    "pdf": b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<< /Type /Catalog >>\nendobj\n",
    "zip": b"PK\x03\x04\x14\x00\x00\x00\x08\x00" + b"\x00" * 40,
    "ole": b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 40,
    "png": b"\x89PNG\r\n\x1a\n" + b"\x00" * 40,
    "text": "Factura de octubre: importe 12,50 €\n".encode("utf-8"),
}


def mz_bytes() -> bytes:
    """Return the shortest MZ-like executable sample."""
    return BLOCKED_CONTENT_SAMPLES["mz"][0]


def elf_bytes() -> bytes:
    """Return the shortest ELF-like executable sample."""
    return BLOCKED_CONTENT_SAMPLES["elf"][0]


def macho_bytes(signature: bytes = MACHO_SIGNATURES["macho_64_little"]) -> bytes:
    """Return a Mach-O sample for ``signature`` (the four flavours are in MACHO_SIGNATURES)."""
    return signature + b"\x00" * 60


def universal_bytes() -> bytes:
    """Return the shortest universal (fat) Mach-O sample."""
    return BLOCKED_CONTENT_SAMPLES["universal"][0]


def shebang_bytes() -> bytes:
    """Return a sample whose first two bytes are ``#!``."""
    return BLOCKED_CONTENT_SAMPLES["shebang"][0]


def pdf_bytes() -> bytes:
    """Return a minimal PDF header sample."""
    return SAFE_CONTENT_SAMPLES["pdf"]


def zip_bytes() -> bytes:
    """Return a minimal ZIP header sample."""
    return SAFE_CONTENT_SAMPLES["zip"]


def ole_bytes() -> bytes:
    """Return a minimal OLE (legacy Office) header sample."""
    return SAFE_CONTENT_SAMPLES["ole"]


def png_bytes() -> bytes:
    """Return a minimal PNG signature sample."""
    return SAFE_CONTENT_SAMPLES["png"]


def text_bytes() -> bytes:
    """Return a non-empty plain-text sample."""
    return SAFE_CONTENT_SAMPLES["text"]


def empty_bytes() -> bytes:
    """Return the zero-byte stream that PRD §10.3.1 declares valid."""
    return b""


# ---------------------------------------------------------------------------
# Name samples (PRD §10.3.1 point 1 and §10.3.2).
# ---------------------------------------------------------------------------

#: The dangerous-extension catalog of PRD §10.3.2, category by category (literal copy).
EXPECTED_CATALOG: dict[str, tuple[str, ...]] = {
    "executables": (
        ".exe", ".com", ".scr", ".pif", ".dll", ".sys", ".drv", ".ocx", ".cpl",
        ".app", ".bin", ".run", ".elf", ".dylib", ".so",
    ),
    "scripts": (
        ".bat", ".cmd", ".ps1", ".psm1", ".psd1", ".vbs", ".vbe", ".js", ".jse",
        ".wsf", ".wsh", ".hta", ".sh", ".bash", ".zsh", ".ksh", ".csh",
        ".command", ".tool", ".applescript", ".scpt", ".workflow",
    ),
    "installers": (
        ".msi", ".msp", ".mst", ".msix", ".appx", ".pkg", ".mpkg", ".dmg",
        ".iso", ".img", ".deb", ".rpm", ".apk",
    ),
    "shortcuts": (
        ".lnk", ".url", ".scf", ".inf", ".reg", ".ins", ".isp", ".prf",
        ".terminal", ".desktop", ".webloc",
    ),
    "interpreters": (
        ".jar", ".jnlp", ".class", ".py", ".pyc", ".pyo", ".pyw", ".rb", ".pl",
        ".php", ".lua", ".tcl",
    ),
    "office_macros": (
        ".docm", ".dotm", ".xlsm", ".xltm", ".xlam", ".pptm", ".potm", ".ppam",
        ".sldm",
    ),
}

#: Simple names that must be blocked by the extension catalog.
DANGEROUS_EXTENSION_NAMES: tuple[str, ...] = tuple(
    f"invoice{extension}"
    for extensions in EXPECTED_CATALOG.values()
    for extension in extensions
)

#: Chained extensions: the final one or any intermediate segment blocks (PRD §10.3.1).
CHAINED_EXTENSION_NAMES: tuple[str, ...] = (
    "factura.pdf.exe",
    "reporte.pdf.bat.cmd",
    "INVOICE.PDF.EXE",
    "informe.pdf.exe.",
    "informe.pdf.exe ",
    "reporte.pdf.bat.cmd...",
    "reporte.exe.txt",
)

#: ``name -> expected reason`` for traversal, drive prefix and NTFS ADS.
TRAVERSAL_NAMES: dict[str, str] = {
    "..": "parent_segment",
    "../evil.pdf": "path_separator",
    "a/b.pdf": "path_separator",
    "a\\b.pdf": "path_separator",
    "..\\evil.pdf": "path_separator",
    "C:evil.pdf": "drive_prefix",
    "C:\\evil.pdf": "path_separator",
    ":evil.pdf": "alternate_data_stream",
    "factura.pdf:ads": "alternate_data_stream",
    "invoice:stream": "alternate_data_stream",
}

#: Control characters, one per Unicode category of the rule (raw form).
CONTROL_NAMES: dict[str, str] = {
    "\x00evil.pdf": "Cc (NUL)",
    "invoice\x01.pdf": "Cc (SOH)",
    "invoice\x7f.pdf": "Cc (DEL)",
    "invoice\u202e.exe": "Cf (RLO)",
    "invoice\u200e.pdf": "Cf (LRM)",
    "invoice\u200b.pdf": "Cf (ZWSP)",
    "invoice\u00ad.pdf": "Cf (soft hyphen)",
    "invoice\ud800.pdf": "Cs (lone surrogate)",
    "invoice\ue000.pdf": "Co (private use)",
}

#: Windows-reserved device names, any casing, with harmless extensions (PRD §10.3.1).
RESERVED_NAMES: tuple[str, ...] = (
    "CON", "con", "PRN", "AUX", "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
    "CON.txt", "con.pdf", "nul.docx", "COM1.tar.gz", "LPT9.docx", "CON.",
    "CON ",
)

#: Names that are not reserved once the root is compared literally.
NON_RESERVED_NAMES: tuple[str, ...] = (
    "CONSOLE.pdf", "COM10.txt", "LPT0.txt", "com1x.pdf", "auxiliar.docx",
)

#: NFKC variants that normalize into a name rule (PRD §10.3.1, one normalization pass).
NFKC_NAMES: dict[str, str] = {
    "\uff23\uff2f\uff2e": "reserved_name",
    "\uff43\uff4f\uff4e.\uff54\uff58\uff54": "reserved_name",
    "reporte.\uff45\uff58\uff45": "dangerous_extension",
    "factura.pdf.\uff25\uff38\uff25": "dangerous_extension",
    "\uff23\uff1aevil.pdf": "drive_prefix",
}

#: Names explicitly allowed by PRD §10.3.2/§10.3.3 (no rule fires).
SAFE_NAMES: tuple[str, ...] = (
    "Factura Octubre 2026.pdf",
    "présupuesto #3.docx",
    "reporte_2026.xlsx",
    "factura.pdf",
    "notas.txt",
    "archive.tar.gz",
    "photo.JPG",
)

#: ``(original_name, index, expected_sanitized_name)`` for PRD §10.3.3.
SANITIZE_CASES: tuple[tuple[str, int, str], ...] = (
    (" invoice.pdf ", 1, "01_invoice.pdf"),
    ("Factura Octubre 2026.pdf", 2, "02_Factura_Octubre_2026.pdf"),
    ("présupuesto #3.docx", 3, "03_présupuesto_#3.docx"),
)

#: Names whose display form removes path segments and controls (note PRD §10.3.3).
DISPLAY_NAME_CASES: tuple[tuple[str, str], ...] = (
    ("Factura Octubre 2026.pdf", "Factura Octubre 2026.pdf"),
    ("../Users/.ssh/CON.\u202efdp.exe", "CON.fdp.exe"),
    ("C:\\Windows\\evil.pdf", "evil.pdf"),
    ("invoice\u200b.pdf", "invoice.pdf"),
)


# ---------------------------------------------------------------------------
# Metadata helpers.
# ---------------------------------------------------------------------------


def entry(
    index: int,
    name: str,
    *,
    size_bytes: int | None = None,
    unavailable_reason: str | None = None,
) -> dict[str, Any]:
    """Build an ``AttachmentMetadataRow``-shaped dict."""
    return {
        "index": index,
        "name": name,
        "size_bytes": size_bytes,
        "native_order_key": str(index),
        "unavailable_reason": unavailable_reason,
    }


def entries(*names: str) -> list[dict[str, Any]]:
    """Build a 1..N ordered list of metadata rows from attachment names."""
    return [entry(index, name) for index, name in enumerate(names, start=1)]


def metadata_entries(names: Sequence[str]) -> list[dict[str, Any]]:
    """Like :func:`entries` for a product of ``itertools`` (``list`` input)."""
    return entries(*names)


# ---------------------------------------------------------------------------
# Streams.
# ---------------------------------------------------------------------------


def chunks(data: bytes, size: int = 1) -> Iterator[bytes]:
    """Split ``data`` into chunks of ``size`` bytes (default: one byte each)."""
    for offset in range(0, len(data), size):
        yield data[offset : offset + size]


class CountingStream:
    """Iterator that records how many bytes were yielded and how often it was opened."""

    def __init__(self, data: bytes, chunk_size: int = 1) -> None:
        self._data = data
        self._chunk_size = chunk_size
        self.bytes_yielded = 0
        self.chunks_yielded = 0
        self.closed = False

    def __iter__(self) -> "CountingStream":
        return self

    def __next__(self) -> bytes:
        start = self.bytes_yielded
        chunk = self._data[start : start + self._chunk_size]
        if not chunk:
            raise StopIteration
        self.bytes_yielded += len(chunk)
        self.chunks_yielded += 1
        return chunk

    def close(self) -> None:
        self.closed = True


def stream_of(data: bytes) -> Iterable[bytes]:
    """Return a one-chunk iterable for ``data`` (the smallest valid stream)."""
    return [data]

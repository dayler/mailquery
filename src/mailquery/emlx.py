"""``.emlx`` path resolution and MIME parsing (PRD 9.5, 17).

Resolves ``uid -> path`` with an O(1) formula (version uuid + decimal shards),
falls back to a recursive search only when the formula misses, and parses the
``.emlx`` container: length line, RFC 5322/MIME payload and plist trailer.

Never writes anything and never triggers an attachment download.
"""

from __future__ import annotations

from dataclasses import dataclass
from email import message_from_bytes, policy
from email.message import Message
from html.parser import HTMLParser
from pathlib import Path
import plistlib
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mailquery.store import EnvelopeStore, Mailbox


#: Header names copied from the MIME block into :class:`EmlxMessage.headers`.
HEADER_NAMES: tuple[str, ...] = ("From", "To", "Cc", "Subject", "Date", "Message-ID")

#: Warning codes shared with the CLI JSON contract (INTERFACES section 4).
W_EMLX_MISSING = "W_EMLX_MISSING"
W_EMLX_CORRUPT = "W_EMLX_CORRUPT"
W_BODY_UNREADABLE = "W_BODY_UNREADABLE"
W_HTML_NO_TEXT = "W_HTML_NO_TEXT"

#: Suffixes tried by the O(1) formula, in priority order.
_EMLX_SUFFIXES: tuple[str, ...] = (".emlx", ".partial.emlx")

#: Markers that start an ``.emlx`` plist trailer (XML and binary plists).
_PLIST_MARKERS: tuple[bytes, ...] = (b"<?xml", b"bplist00")

#: Tags whose text content is not part of the visible body.
_SKIP_TAGS = frozenset(
    {"head", "title", "script", "style", "noscript", "template", "svg", "math"}
)

#: Tags that visually separate text; they become whitespace before collapsing.
_BLOCK_TAGS = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "caption",
        "dd",
        "div",
        "dl",
        "dt",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
        "ul",
    }
)


@dataclass(frozen=True)
class EmlxMessage:
    """Parsed representation of one ``.emlx`` file."""

    path: Path
    partial: bool
    headers: dict[str, str]
    body_text: str
    attachments: tuple[str, ...]
    available: bool
    readable: bool
    warnings: tuple[str, ...] = ()


def resolve_path(store: "EnvelopeStore", mailbox: "Mailbox", uid: int) -> Path | None:
    """Return the ``.emlx``/``.partial.emlx`` path for ``uid`` or ``None``.

    The primary lookup is the O(1) formula::

        <mailbox_dir>/<version_uuid>/Data/<shards>/Messages/<uid>.emlx

    where ``<shards>`` are the decimal digits of ``uid // 1000`` from the least
    significant to the most significant (so ``uid < 1000`` has no shards). The
    ``.partial.emlx`` variant is tried second.

    A recursive search runs **only** when the formula misses, and the result is
    ``None`` when no file exists. This function never writes anything.
    """
    mailbox_dir = Path(store.mailbox_dir(mailbox))
    version_uuid = _version_uuid(store)
    data_dir = mailbox_dir / version_uuid / "Data" / Path(*_shard_parts(uid))
    for suffix in _EMLX_SUFFIXES:
        candidate = data_dir / "Messages" / f"{uid}{suffix}"
        if candidate.is_file():
            return candidate
    return _search_recursively(mailbox_dir, uid)


def parse_emlx(path: Path) -> EmlxMessage:
    """Parse an ``.emlx`` file without modifying it.

    The container is ``<length line>`` + ``<length>`` bytes of RFC 5322/MIME
    payload + an optional plist trailer. Corrupt or unreadable files never
    raise: they come back with ``readable=False`` and a warning, recovered as
    far as possible (the MIME block up to the plist trailer, best effort).
    """
    path = Path(path)
    partial = path.name.endswith(".partial.emlx")
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError as exc:
        detail = exc.strerror or str(exc) or exc.__class__.__name__
        return _unparsed(
            path,
            partial,
            (_warning(W_BODY_UNREADABLE, f"cannot read .emlx file ({detail})"),),
            available=False,
        )

    if not data:
        return _unparsed(
            path,
            partial,
            (_warning(W_EMLX_CORRUPT, "empty .emlx file"),),
        )

    warnings: list[str] = []
    payload, trailer, clean = _split_container(data)
    # The trailer is parsed tolerantly: a missing or foreign one is fine.
    _parse_trailer(trailer)
    if not clean:
        _add_warning(
            warnings,
            W_EMLX_CORRUPT,
            "malformed .emlx length line; recovered the MIME block best effort",
        )
    if not payload:
        _add_warning(warnings, W_EMLX_CORRUPT, "no MIME payload found")
        return _unparsed(path, partial, tuple(warnings))

    message = _parse_message(payload)
    if message is None:
        _add_warning(warnings, W_EMLX_CORRUPT, "MIME payload could not be parsed")
        return _unparsed(path, partial, tuple(warnings))

    headers = _extract_headers(message)
    attachments = _attachment_names(message)

    smime = _smime_kind(message)
    if smime is not None:
        _add_warning(
            warnings,
            W_BODY_UNREADABLE,
            f"S/MIME {smime} content is not supported",
        )
        return EmlxMessage(
            path=path,
            partial=partial,
            headers=headers,
            body_text="",
            attachments=attachments,
            available=True,
            readable=False,
            warnings=tuple(warnings),
        )

    if not message.keys():
        _add_warning(warnings, W_EMLX_CORRUPT, "MIME payload has no headers")
        return EmlxMessage(
            path=path,
            partial=partial,
            headers=headers,
            body_text="",
            attachments=attachments,
            available=True,
            readable=False,
            warnings=tuple(warnings),
        )

    body_text = _extract_body_text(message, warnings)
    return EmlxMessage(
        path=path,
        partial=partial,
        headers=headers,
        body_text=body_text,
        attachments=attachments,
        available=True,
        readable=True,
        warnings=tuple(warnings),
    )


def html_to_text(html: str) -> str:
    """Convert HTML to plain text using ``html.parser``.

    Script/style/head content is dropped, character references are decoded,
    block-level elements become whitespace and runs of whitespace collapse to a
    single space. The result is used for snippets and for ``--text`` search.
    """
    if not isinstance(html, str) or not html:
        return ""
    extractor = _HtmlTextExtractor()
    try:
        extractor.feed(html)
        extractor.close()
    except Exception:  # pragma: no cover - HTMLParser is tolerant; never crash
        pass
    return extractor.text()


# --------------------------------------------------------------------------- #
# Path resolution internals
# --------------------------------------------------------------------------- #


def _version_uuid(store: "EnvelopeStore") -> str:
    """Return ``store.version.version_uuid`` (the ``StoreVersion`` attribute).

    This is the only supported location: ``EnvelopeStore`` exposes the
    :class:`mailquery.store.StoreVersion` passed to its constructor as the
    public ``.version`` attribute (confirmed contract).
    """
    return str(store.version.version_uuid)


def _shard_parts(uid: int) -> tuple[str, ...]:
    """Return the decimal shards of ``uid // 1000``, least significant first.

    ``830 -> ()``, ``2714 -> ("2",)``, ``79658 -> ("9", "7")``.
    """
    if uid < 1000:
        return ()
    return tuple(reversed(str(uid // 1000)))


def _search_recursively(mailbox_dir: Path, uid: int) -> Path | None:
    """Recursive fallback used only when the O(1) formula misses."""
    try:
        for suffix in _EMLX_SUFFIXES:
            matches = sorted(
                candidate
                for candidate in mailbox_dir.rglob(f"{uid}{suffix}")
                if candidate.is_file()
            )
            if matches:
                return matches[0]
    except OSError:  # unreadable/absent mailbox directories are simply a miss
        return None
    return None


# --------------------------------------------------------------------------- #
# Container internals
# --------------------------------------------------------------------------- #


def _split_container(data: bytes) -> tuple[bytes, bytes, bool]:
    """Split raw ``.emlx`` bytes into ``(payload, trailer, clean)``.

    ``clean`` is False when the length line is invalid or the declared length
    overruns the file; the payload is still recovered best effort (MIME block up
    to the plist trailer) so callers can report what they could read.
    """
    line_end = data.find(b"\n")
    if line_end == -1:
        return b"", b"", False
    first_line = data[:line_end].strip()
    try:
        length = int(first_line)
    except ValueError:
        length = None

    if length is not None and length > 0:
        start = line_end + 1
        end = start + length
        if end <= len(data):
            return data[start:end], data[end:], True
        payload, trailer = _split_trailer(data[start:])
        return payload, trailer, False

    # Missing/non-numeric/zero length line: recover the MIME block itself.
    block = data if _looks_like_header_line(first_line) else data[line_end + 1 :]
    payload, trailer = _split_trailer(block)
    return payload, trailer, False


def _split_trailer(data: bytes) -> tuple[bytes, bytes]:
    """Split off a trailing plist, returning ``(payload, trailer)``."""
    best = -1
    for marker in _PLIST_MARKERS:
        search_end = len(data)
        while True:
            index = data.rfind(marker, 0, search_end)
            if index < 0:
                break
            try:
                plistlib.loads(data[index:])
            except Exception:
                search_end = index
                continue
            best = max(best, index)
            break
    if best < 0:
        return data, b""
    return data[:best], data[best:]


def _looks_like_header_line(line: bytes) -> bool:
    """True when a line looks like an RFC 5322 header (``Name: value``)."""
    if b":" not in line:
        return False
    name = line.split(b":", 1)[0].strip()
    if not name or b" " in name or b"\t" in name:
        return False
    return all(33 <= byte <= 126 for byte in name)


def _parse_trailer(trailer: bytes) -> dict | None:
    """Parse the plist trailer tolerantly; foreign/absent trailers yield None."""
    if not trailer.strip():
        return None
    try:
        parsed = plistlib.loads(trailer)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


# --------------------------------------------------------------------------- #
# MIME internals
# --------------------------------------------------------------------------- #


def _parse_message(payload: bytes) -> Message | None:
    try:
        return message_from_bytes(payload, policy=policy.default)
    except Exception:  # pragma: no cover - defensive: corrupt MIME never crashes
        return None


def _extract_headers(message: Message) -> dict[str, str]:
    headers: dict[str, str] = {}
    for name in HEADER_NAMES:
        value = ""
        try:
            header = message.get(name)
        except Exception:  # pragma: no cover - corrupt header objects
            header = None
        if header is not None:
            value = _clean_text(str(header)).strip()
        headers[name] = value
    return headers


def _extract_body_text(message: Message, warnings: list[str]) -> str:
    plain_parts: list[str] = []
    html_parts: list[str] = []
    for part in _iter_content_parts(message):
        content_type = part.get_content_type()
        if content_type == "text/plain":
            text = _decode_part(part)
            if text.strip():
                plain_parts.append(text.strip())
        elif content_type == "text/html":
            raw = _decode_part(part)
            if raw.strip():
                html_parts.append(raw)

    if plain_parts:
        return "\n".join(plain_parts)
    if html_parts:
        converted = [text for text in (html_to_text(raw) for raw in html_parts) if text]
        if converted:
            return "\n".join(converted)
        _add_warning(warnings, W_HTML_NO_TEXT, "HTML body produced no plain text")
    return ""


def _iter_content_parts(message: Message) -> Iterator[Message]:
    """Yield text parts that can carry the message body (attachments excluded)."""
    for part in message.walk():
        try:
            if part.is_multipart():
                continue
            if part.get_content_maintype() != "text":
                continue
            if part.is_attachment() or part.get_filename() is not None:
                continue
        except Exception:  # pragma: no cover - tolerate broken part metadata
            continue
        yield part


def _decode_part(part: Message) -> str:
    try:
        raw = part.get_payload(decode=True)
    except Exception:
        raw = None
    if raw is None:
        payload = part.get_payload()
        return payload if isinstance(payload, str) else ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return raw.decode(charset, errors="replace")
    except (LookupError, UnicodeError):
        return raw.decode("utf-8", errors="replace")


def _attachment_names(message: Message) -> tuple[str, ...]:
    names: list[str] = []
    for part in message.walk():
        try:
            if part.is_multipart():
                continue
            filename = part.get_filename()
        except Exception:  # pragma: no cover - tolerate broken part metadata
            continue
        if not filename:
            continue
        name = _clean_text(str(filename)).strip()
        if name and name not in names:
            names.append(name)
    return tuple(names)


def _smime_kind(message: Message) -> str | None:
    """Return ``"encrypted"``/``"signed"`` for S/MIME payloads, else ``None``."""
    content_type = message.get_content_type().lower()
    raw_content_type = str(message.get("Content-Type", "")).lower()
    if content_type == "multipart/encrypted":
        return "encrypted"
    if content_type == "multipart/signed":
        return "signed"
    try:
        smime_type = message.get_param("smime-type")
    except Exception:  # pragma: no cover - corrupt Content-Type parameters
        smime_type = None
    if smime_type:
        return "encrypted" if "enveloped" in str(smime_type).lower() else "signed"
    if "pkcs7" in content_type or "pkcs7" in raw_content_type:
        return "signed"
    return None


# --------------------------------------------------------------------------- #
# Result helpers
# --------------------------------------------------------------------------- #


def _warning(code: str, detail: str) -> str:
    return f"{code}: {detail}"


def _add_warning(warnings: list[str], code: str, detail: str) -> None:
    """Append one ``"<CODE>: <detail>"`` warning per code (no duplicates)."""
    if any(warning.startswith(f"{code}:") for warning in warnings):
        return
    warnings.append(_warning(code, detail))


def _clean_text(value: str) -> str:
    """Replace undecodable 8-bit header bytes (lone surrogates) safely."""
    try:
        return value.encode("utf-8", "surrogateescape").decode("utf-8", "replace")
    except UnicodeError:  # pragma: no cover - defensive
        return value.encode("utf-8", "replace").decode("utf-8", "replace")


def _empty_headers() -> dict[str, str]:
    return {name: "" for name in HEADER_NAMES}


def _unparsed(
    path: Path,
    partial: bool,
    warnings: tuple[str, ...],
    *,
    available: bool = True,
) -> EmlxMessage:
    return EmlxMessage(
        path=path,
        partial=partial,
        headers=_empty_headers(),
        body_text="",
        attachments=(),
        available=available,
        readable=False,
        warnings=warnings,
    )


# --------------------------------------------------------------------------- #
# HTML to text
# --------------------------------------------------------------------------- #


class _HtmlTextExtractor(HTMLParser):
    """Collect visible text while dropping non-content elements."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag in _BLOCK_TAGS:
            self._chunks.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            if self._skip_depth:
                self._skip_depth -= 1
        elif tag in _BLOCK_TAGS:
            self._chunks.append(" ")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self._chunks.append(data)

    def text(self) -> str:
        return " ".join("".join(self._chunks).split())

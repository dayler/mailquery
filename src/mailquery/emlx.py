"""``.emlx`` path resolution and MIME parsing (PRD 9.5, 17).

Resolves ``uid -> path`` with an O(1) formula (version uuid + decimal shards),
falls back to a recursive search only when the formula misses, and parses the
``.emlx`` container: length line, RFC 5322/MIME payload and plist trailer.

Never writes anything and never triggers an attachment download.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from email import message_from_bytes, policy
from email.message import Message
from pathlib import Path
import plistlib
from typing import TYPE_CHECKING, Iterable, Iterator

from mailquery.output import html_to_text

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
    """Original names of the attachment parts, one entry per part (M09, RF-43).

    A message may carry two attachments with the same name; the ``index`` of
    ``show``/``attachment`` is the part position, so names are not deduplicated
    (the 2.0.1 ``show`` deduplicated them, but the indexed contract needs every
    part to keep a stable position).
    """
    names: list[str] = []
    for _part_path, part in _iter_leaf_parts(message):
        name = _attachment_part_name(part)
        if name:
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
# Attachment parts (M09: C1 ``attachments``/``attachment_stream`` support)
# --------------------------------------------------------------------------- #

#: Chunk size used to hand decoded attachment bytes to the core (M09-T03).
ATTACHMENT_CHUNK_SIZE: int = 64 * 1024


class AttachmentReadError(Exception):
    """A local attachment cannot be read; ``reason`` follows PRD-v2.1 §11.7.

    ``not_local`` / ``unsupported`` map to ``E_ATTACHMENT_UNAVAILABLE`` and
    ``corrupt`` / ``unreadable`` to ``E_ATTACHMENT_UNREADABLE`` (the core builds
    the user-facing error from the ``reason``). ``emlx`` never writes anything.
    """

    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = str(reason)
        super().__init__(detail or self.reason)


@dataclass(frozen=True)
class EmlxAttachment:
    """Ordered attachment metadata of one ``.emlx`` (M09, RF-43/RF-46/RF-47).

    ``index`` is the 1-based part position shared by ``show`` and ``attachment``;
    ``native_order_key`` is that position as text (Apple Mail orders attachments
    numerically, C1); ``size_bytes`` is the decoded size (or the externalized
    file size) when known; ``unavailable_reason`` is ``None`` for a local
    attachment, ``corrupt`` for an undecodable MIME part and ``unsupported`` for
    an externalized part whose file is not verifiable (PRD-v2.1 §15).
    ``part_path`` is the multipart position used to find externalized files.
    """

    index: int
    name: str
    size_bytes: int | None
    native_order_key: str
    unavailable_reason: str | None = None
    external_path: Path | None = None
    part_path: tuple[int, ...] = ()


@dataclass(frozen=True)
class EmlxAttachments:
    """Result of :func:`parse_attachments` (M09)."""

    path: Path
    partial: bool
    readable: bool
    smime: str | None
    items: tuple[EmlxAttachment, ...] = ()
    available: bool = True


def parse_attachments(path: Path, *, native_uid: int | None = None) -> EmlxAttachments:
    """Attachment metadata of one ``.emlx``/``.partial.emlx`` (never writes).

    A readable body lists one item per MIME part with a filename, in part order.
    ``.partial.emlx`` messages externalize their attachments: each item is
    resolved against the Apple Mail layout (best effort, PRD-v2.1 §15) and is
    ``unsupported`` when the file cannot be verified. Corrupt base64 payloads
    are ``corrupt``. An absent or unparseable file comes back with
    ``readable=False`` (the adapter falls back to the ``Envelope Index`` names).
    """
    message, partial, smime, readable = _attachment_context(path)
    if message is None or not readable or smime is not None:
        return EmlxAttachments(
            path=path,
            partial=partial,
            readable=readable,
            smime=smime,
            items=(),
            available=message is not None,
        )
    items = _attachment_items(message, path, partial=partial, native_uid=native_uid)
    return EmlxAttachments(
        path=path,
        partial=partial,
        readable=True,
        smime=None,
        items=items,
        available=True,
    )


def attachment_stream(
    path: Path, index: int, *, native_uid: int | None = None
) -> Iterator[bytes]:
    """Decoded bytes of the attachment ``index`` (1-based) in chunks (M09-T03).

    Inline payloads are base64/quoted-printable-decoded; externalized parts of a
    ``.partial.emlx`` stream the raw file found by :func:`external_attachment_path`.
    A missing/unverifiable external file raises ``unsupported``; a payload that
    cannot be decoded raises ``corrupt``. The file is only ever read.
    """
    message, partial, smime, readable = _attachment_context(path)
    if message is None or not readable:
        raise AttachmentReadError("unreadable", "the .emlx cannot be read")
    if smime is not None:
        raise AttachmentReadError("smime", "the message is S/MIME protected")
    target = _attachment_target(message, int(index))
    if target is None:
        raise AttachmentReadError("not_local", "the attachment index does not exist")
    part_path, part, name = target
    if partial:
        external = external_attachment_path(path, native_uid, part_path, name)
        if external is None:
            raise AttachmentReadError(
                "unsupported", "the externalized attachment cannot be verified"
            )
        yield from _chunks_of_file(external)
        return
    try:
        payload = _decode_attachment_part(part)
    except Exception as exc:
        raise AttachmentReadError("corrupt", "the attachment payload cannot be decoded") from exc
    for start in range(0, len(payload), ATTACHMENT_CHUNK_SIZE):
        yield payload[start : start + ATTACHMENT_CHUNK_SIZE]


def external_attachment_path(
    message_path: Path,
    native_uid: int | None,
    part_path: Iterable[int],
    name: str,
) -> Path | None:
    """Best-effort location of an externalized ``.partial.emlx`` attachment.

    Apple Mail keeps the parts under ``Data/<shards>/Attachments/<uid>/<part>/``
    next to ``Messages/`` ([partial-emlx-converter layout]); the layout is not
    verified in production (PRD-v2.1 §15), so several candidates are tried and a
    miss means ``unsupported``. Only regular files are accepted (no symlinks).
    """
    if native_uid is None or not name:
        return None
    data_dir = Path(message_path).parent.parent
    pieces = [str(piece) for piece in part_path]
    base = data_dir / "Attachments" / str(native_uid)
    candidates: list[Path] = []
    if pieces:
        candidates.append(base.joinpath(*pieces) / name)
        candidates.append(base / ".".join(pieces) / name)
    candidates.append(base / name)
    candidates.append(data_dir / "Messages" / "Attachments" / str(native_uid) / name)
    for candidate in candidates:
        try:
            if candidate.is_file() and not candidate.is_symlink():
                return candidate
        except OSError:  # pragma: no cover - unreadable directories are a miss
            continue
    return None


# -- internals --------------------------------------------------------------- #


def _attachment_context(
    path: Path,
) -> tuple[Message | None, bool, str | None, bool]:
    """Read and parse the MIME block: ``(message, partial, smime, readable)``."""
    path = Path(path)
    partial = path.name.endswith(".partial.emlx")
    try:
        data = path.read_bytes()
    except OSError:
        return None, partial, None, False
    if not data:
        return None, partial, None, False
    payload, _trailer, _clean = _split_container(data)
    if not payload:
        return None, partial, None, False
    message = _parse_message(payload)
    if message is None:
        return None, partial, None, False
    smime = _smime_kind(message)
    readable = smime is None and bool(message.keys())
    return message, partial, smime, readable


def _iter_leaf_parts(
    message: Message, prefix: tuple[int, ...] = ()
) -> Iterator[tuple[tuple[int, ...], Message]]:
    """Leaf MIME parts with their 1-based multipart position (Apple Mail layout)."""
    try:
        multipart = message.is_multipart()
    except Exception:  # pragma: no cover - tolerate broken part metadata
        multipart = False
    if not multipart:
        yield prefix, message
        return
    payload = message.get_payload()
    if not isinstance(payload, list):  # pragma: no cover - defensive
        return
    for position, child in enumerate(payload, start=1):
        yield from _iter_leaf_parts(child, prefix + (position,))


def _attachment_part_name(part: Message) -> str:
    try:
        filename = part.get_filename()
    except Exception:  # pragma: no cover - tolerate broken part metadata
        return ""
    if not filename:
        return ""
    return _clean_text(str(filename)).strip()


def _attachment_identity(message: Message) -> Iterable[tuple[tuple[int, ...], Message, str]]:
    """``(part_path, part, original_name)`` of every attachment part, in order."""
    for part_path, part in _iter_leaf_parts(message):
        name = _attachment_part_name(part)
        if name:
            yield part_path, part, name


def _attachment_items(
    message: Message,
    path: Path,
    *,
    partial: bool,
    native_uid: int | None,
) -> tuple[EmlxAttachment, ...]:
    """Build the ordered attachment items of a readable message (M09)."""
    items: list[EmlxAttachment] = []
    for part_path, part, name in _attachment_identity(message):
        index = len(items) + 1
        if partial:
            external = external_attachment_path(path, native_uid, part_path, name)
            size: int | None = None
            reason = "unsupported"
            if external is not None:
                try:
                    size = external.stat().st_size
                    reason = None
                except OSError:  # pragma: no cover - the file vanished mid-run
                    external = None
            items.append(
                EmlxAttachment(
                    index=index,
                    name=name,
                    size_bytes=size,
                    native_order_key=str(index),
                    unavailable_reason=reason,
                    external_path=external,
                    part_path=part_path,
                )
            )
            continue
        try:
            decoded = _decode_attachment_part(part)
        except Exception:  # noqa: BLE001 - undecodable MIME/base64 is ``corrupt``
            items.append(
                EmlxAttachment(
                    index=index,
                    name=name,
                    size_bytes=None,
                    native_order_key=str(index),
                    unavailable_reason="corrupt",
                    part_path=part_path,
                )
            )
            continue
        items.append(
            EmlxAttachment(
                index=index,
                name=name,
                size_bytes=len(decoded),
                native_order_key=str(index),
                part_path=part_path,
            )
        )
    return tuple(items)


def _attachment_target(
    message: Message, index: int
) -> tuple[tuple[int, ...], Message, str] | None:
    """The ``(part_path, part, name)`` of attachment ``index`` (1-based), if any."""
    if index < 1:
        return None
    for position, (part_path, part, name) in enumerate(
        _attachment_identity(message), start=1
    ):
        if position == index:
            return part_path, part, name
    return None


def _decode_attachment_part(part: Message) -> bytes:
    """Decoded payload of one part; a corrupt base64 payload raises ``ValueError``."""
    encoding = str(part.get("Content-Transfer-Encoding") or "").strip().lower()
    if encoding == "base64":
        raw = part.get_payload()
        if not isinstance(raw, str):  # pragma: no cover - a multipart part
            raise ValueError("base64 attachment part without a string payload")
        compact = "".join(raw.split())
        if not compact:
            return b""
        # Strict validation: Python's e-mail decoder tolerates invalid base64 and
        # would return garbage, hiding a corrupt part (M09 ``corrupt`` reason).
        return base64.b64decode(compact, validate=True)
    payload = part.get_payload(decode=True)
    if payload is None:
        raise ValueError("the attachment part cannot be decoded")
    if isinstance(payload, str):  # pragma: no cover - defensive
        return payload.encode("utf-8", errors="replace")
    return payload


def _chunks_of_file(path: Path) -> Iterator[bytes]:
    """Read a local file in chunks, read-only; I/O errors become ``unsupported``."""
    try:
        with open(path, "rb") as handle:
            while True:
                chunk = handle.read(ATTACHMENT_CHUNK_SIZE)
                if not chunk:
                    return
                yield chunk
    except OSError as exc:
        raise AttachmentReadError(
            "unsupported", "the externalized attachment file cannot be read"
        ) from exc


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

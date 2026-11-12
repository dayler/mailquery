"""Whole-message attachment screening.

Implements the pure half of the attachment screening order: ``screen_names``
evaluates **all** attachment names of the message (it runs before the engine's
size limits) and
``screen_content`` inspects only the requested attachments' first decoded block
(it runs after the limits and during extraction). A name hit blocks the whole
message before any size check; a content hit blocks it without partial
extraction. Availability reasons surfaced by the driver metadata map to the
core attachment codes. Neither function writes files nor opens cached paths.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Final

from mailquery.attachments.blocking import (
    CONTENT_INSPECTION_BYTES,
    classify_content,
    classify_name,
)

#: Error codes owned by the core; the engine turns them into ``MailqueryError``.
BLOCKED_CODE: Final[str] = "E_ATTACHMENT_BLOCKED"
UNREADABLE_CODE: Final[str] = "E_ATTACHMENT_UNREADABLE"
UNAVAILABLE_CODE: Final[str] = "E_ATTACHMENT_UNAVAILABLE"
#: ``reason`` of a stream read failure (closed enum of the attachment operations).
REASON_READ_ERROR: Final[str] = "unreadable"
#: Driver ``reason`` values that map to ``E_ATTACHMENT_UNAVAILABLE``.
UNAVAILABLE_REASONS: Final[frozenset[str]] = frozenset(
    {"not_local", "not_downloaded", "unsupported", "network"}
)
#: Driver ``reason`` values that map to ``E_ATTACHMENT_UNREADABLE``.
UNREADABLE_REASONS: Final[frozenset[str]] = frozenset({"corrupt", "smime", "unreadable"})


@dataclass(frozen=True, slots=True)
class ScreenDecision:
    """Outcome of one screening step.

    ``code`` is ``None`` on success or one of the three attachment codes;
    ``reason`` is a name/content reason for a block, the driver reason for
    availability/unreadability or ``"unreadable"`` for a stream read error;
    ``index``/``name`` identify the causing attachment and ``detail`` is the
    message fragment for a block (``has a dangerous filename pattern`` or
    ``has executable content``). The engine builds the user-facing error from it.
    """

    code: str | None = None
    reason: str | None = None
    index: int | None = None
    name: str | None = None
    detail: str | None = None

    @property
    def ok(self) -> bool:
        """Whether the screen found nothing to report."""
        return self.code is None

    @property
    def failed(self) -> bool:
        """Whether the screen returned one of the attachment error codes."""
        return self.code is not None

    @property
    def blocked(self) -> bool:
        """Whether the whole message is blocked (``E_ATTACHMENT_BLOCKED``)."""
        return self.code == BLOCKED_CODE


def read_first_block(stream: Iterable[bytes]) -> bytes:
    """Read at most :data:`CONTENT_INSPECTION_BYTES` bytes and close the stream.

    Stops as soon as the inspection window is full (a one-byte-chunk stream is
    consumed exactly 512 times) and closes the iterator when it supports
    ``close()``. Read errors propagate: ``screen_content`` maps them to
    ``E_ATTACHMENT_UNREADABLE``.
    """
    iterator = iter(stream)
    block = bytearray()
    try:
        while len(block) < CONTENT_INSPECTION_BYTES:
            try:
                chunk = next(iterator)
            except StopIteration:
                break
            block.extend(chunk)
        return bytes(block[:CONTENT_INSPECTION_BYTES])
    finally:
        close = getattr(iterator, "close", None)
        if close is not None:
            try:
                close()
            except Exception:  # pragma: no cover - cleanup must not mask a decision
                pass


def screen_names(entries: Iterable[Mapping[str, object]]) -> ScreenDecision:
    """Evaluate the names of **all** attachments, in index order.

    Runs before the engine's size limits and regardless of the requested ``--index``: a
    single dangerous name blocks the whole message. An empty list
    is a valid message without attachments: it does not block and it is never
    reported as "no attachments" here (the command reports that case).
    """
    for index, row in _ordered(entries):
        name = _name_of(row)
        decision = classify_name(name)
        if decision.blocked:
            return ScreenDecision(
                code=BLOCKED_CODE,
                reason=decision.reason,
                index=index,
                name=name,
                detail=decision.detail,
            )
    return ScreenDecision()


def screen_content(
    entries: Iterable[Mapping[str, object]],
    requested_indices: Iterable[int] | None,
    open_stream: Callable[[int], Iterable[bytes]],
) -> ScreenDecision:
    """Inspect the first decoded block of the requested attachments.

    ``requested_indices`` is ``--index N`` (``[N]``) or ``--all`` (``None`` for
    every index); only those streams are opened. Blocking content has global
    precedence over unreadable/unavailable faults (content blocking is checked
    before availability); among those faults the first one in index order is
    returned. ``open_stream`` receives a 1-based index and must
    be safe to call again for extraction (the engine opens a fresh stream for it).
    """
    ordered = _ordered(entries)
    by_index = {index: row for index, row in ordered}
    requested = _requested(ordered, requested_indices)
    first_fault: ScreenDecision | None = None
    for index in requested:
        row = by_index[index]
        name = _name_of(row)
        unavailable_reason = row.get("unavailable_reason")
        if unavailable_reason:
            reason = str(unavailable_reason)
            code = (
                UNREADABLE_CODE if reason in UNREADABLE_REASONS else UNAVAILABLE_CODE
            )
            if first_fault is None:
                first_fault = ScreenDecision(code=code, reason=reason, index=index, name=name)
            continue
        try:
            block = read_first_block(open_stream(index))
        except Exception:
            if first_fault is None:
                first_fault = ScreenDecision(
                    code=UNREADABLE_CODE,
                    reason=REASON_READ_ERROR,
                    index=index,
                    name=name,
                )
            continue
        decision = classify_content(block)
        if decision.blocked:
            return ScreenDecision(
                code=BLOCKED_CODE,
                reason=decision.reason,
                index=index,
                name=name,
                detail=decision.detail,
            )
    return first_fault if first_fault is not None else ScreenDecision()


def _ordered(
    entries: Iterable[Mapping[str, object]],
) -> list[tuple[int, Mapping[str, object]]]:
    ordered: list[tuple[int, Mapping[str, object]]] = []
    for row in entries:
        raw_index = row.get("index")
        if isinstance(raw_index, bool) or not isinstance(raw_index, int) or raw_index < 1:
            raise ValueError(
                "attachment metadata rows need a 1-based integer 'index'"
            )
        ordered.append((raw_index, row))
    ordered.sort(key=lambda pair: pair[0])
    return ordered


def _name_of(row: Mapping[str, object]) -> str:
    name = row.get("name", "")
    return name if isinstance(name, str) else str(name)


def _requested(
    ordered: Iterable[tuple[int, Mapping[str, object]]],
    requested_indices: Iterable[int] | None,
) -> list[int]:
    if requested_indices is None:
        return [index for index, _row in ordered]
    requested: set[int] = set()
    for value in requested_indices:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError("requested attachment indexes must be integers >= 1")
        requested.add(value)
    available = {index for index, _row in ordered}
    missing = sorted(requested - available)
    if missing:
        raise ValueError(
            "requested attachment index(es) not in the metadata list: "
            + ", ".join(str(index) for index in missing)
        )
    return sorted(requested)

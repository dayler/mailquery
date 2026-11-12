"""Attachment recovery engine: limits, cache hits, staging and publication (M07, C7).

This module completes the attachment policy started in M06 and is the contract
M08–M10 consume (PRD-v2.1 RF-43/RF-45–RF-49/RF-51, §10.3, §10.4, §11.2,
§11.3 rows 11–15, AC-12/AC-13/AC-15/AC-20). It owns, in this order:

1. the **name screen of every attachment of the message** (M06 ``screen_names``,
   before serving any cache hit);
2. the **limits with known sizes** (``max_count`` only for ``--all``, including
   cache hits; ``max_file_size_mb``; ``max_total_size_mb``; 1 MiB = 1 048 576
   bytes; strictly greater exceeds);
3. the **cache lookup** (regular file, expected size match) used to report
   ``cached: true`` and to count real hit sizes;
4. the **first-block content screen of the attachments that will be extracted**
   (M06 ``screen_content``), mapped with the §11.7 core templates;
5. the **staging extraction** (opaque files under ``tmp/staging``, hash and
   *magic bytes* already validated) and the **atomic publication**
   (``os.replace`` per file) into ``~/.mailquery/attachments/``.

Nothing is written before step 4 succeeds for every requested attachment; a
failure before publication leaves no new or partial file in the cache and no
temporary file of this run in ``tmp/`` (RNF-14). A cache hit never re-validates
content; ``--force`` re-extracts and replaces atomically. Driver exceptions are
expected to arrive already mapped by the M05 wrapper: this module only maps the
``unavailable_reason`` metadata field (a data value) and defensively duck-types
``reason``-bearing exceptions, because ``attachments/**`` must not import
``mailquery.plugins`` (UT-ATT-01.09).

Frozen for M08–M10:

* ``AttachmentsEngine(home, config, driver, clock=None)`` where ``config`` is a
  duck-typed ``AttachmentsConfig`` (M02), ``driver`` a ``MailBackend`` (C1) and
  ``clock`` an injectable monotonic clock (tests only).
* ``recover(uid, indices=None, *, force=False, deadline=None, entries=None)``
  returning the §11.2 records; ``indices=None`` means ``--all``; ``entries``
  are the driver metadata rows already fetched/validated by the command (the
  engine never repeats that call when they are given).
* ``deadline`` is a zero-argument factory returning the absolute instant (in
  ``clock`` units) at which the extraction of **one** attachment expires, or
  ``None`` for no policy; it is invoked once per attachment, before its first
  block is screened, and the same instant bounds screening and extraction.
  M08 passes ``lambda: time.monotonic() + 120`` (RNF-16); a ``None`` deadline
  means the engine imposes no time policy.
* ``attachments.cache.cached_path(...)`` is the frozen helper for
  ``show.attachments[].cached_path`` (regular files only).
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Final, Protocol, TypedDict

from mailquery.attachments.cache import (
    AttachmentCache,
    CacheHit,
    StagedAttachment,
    StagingArea,
)
from mailquery.attachments.sanitize import display_name, sanitize_name
from mailquery.attachments.screening import (
    BLOCKED_CODE,
    UNAVAILABLE_CODE,
    UNREADABLE_CODE,
    ScreenDecision,
    screen_content,
    screen_names,
)
from mailquery.errors import MailqueryError
from mailquery.uid import parse_uid

#: One MiB as fixed by the PRD (§13.3): all ``[attachments]`` limits use it.
MIB: Final[int] = 1_048_576

#: §11.5 C/D hint of a blocked message.
_BLOCKED_HINT: Final[str] = (
    "notify the user to inspect the message and its attachments in the email "
    "client at their own risk; do not retry the same request"
)
#: §11.3 reference hint for the attachment indexes.
_INDEX_HINT: Final[str] = (
    "run `mailquery show <uid>` to list the attachment indexes"
)
#: §11.7 hint of ``E_CLIENT_TIMEOUT``.
_TIMEOUT_HINT: Final[str] = (
    'run "mailquery doctor" and do not retry in a loop'
)
#: Generic, PII-free log line for an attachment that could not be recovered.
_ATTACHMENT_ERROR_LOG: Final[str] = "attachment could not be recovered"

#: ``reason`` → ``(code, message fragment, hint)`` for the attachment operations.
#: Mirrors the §11.7 mapping table without importing ``mailquery.plugins`` (M05
#: maps runtime driver exceptions before they reach this engine; this table also
#: maps the ``unavailable_reason`` metadata field).
_REASON_RULES: Final[dict[str, tuple[str, str, str]]] = {
    "not_local": (
        UNAVAILABLE_CODE,
        "is not available in the local store",
        "open the message in the email client so it downloads the attachment "
        "to disk, then retry",
    ),
    "not_downloaded": (
        UNAVAILABLE_CODE,
        "is not available in the local store",
        "open the message in the email client so it downloads the attachment "
        "to disk, then retry",
    ),
    "network": (
        UNAVAILABLE_CODE,
        "could not be retrieved from its origin",
        "check the network connection and the plugin configuration, then retry",
    ),
    "unsupported": (
        UNAVAILABLE_CODE,
        "cannot be recovered by driver '{driver}'",
        "install or declare a driver that can recover this attachment",
    ),
    "corrupt": (
        UNREADABLE_CODE,
        "is corrupt or unreadable",
        "inspect the message and its attachments in the email client",
    ),
    "unreadable": (
        UNREADABLE_CODE,
        "is corrupt or unreadable",
        "inspect the message and its attachments in the email client",
    ),
    "smime": (
        UNREADABLE_CODE,
        "is S/MIME protected and cannot be extracted",
        "S/MIME attachments cannot be extracted",
    ),
    "permission": (
        "E_PERMISSION",
        "cannot be read: permission denied",
        "check the permissions of the local store and retry",
    ),
    "auth": (
        "E_PERMISSION",
        "cannot be read: permission denied",
        "check the permissions of the local store and retry",
    ),
    "busy": (
        "E_CLIENT_BUSY",
        "is temporarily unavailable",
        "retry once",
    ),
    "timeout": (
        "E_CLIENT_TIMEOUT",
        "did not respond within the timeout",
        _TIMEOUT_HINT,
    ),
    "invalid_uid": ("E_USAGE", "could not be resolved", _INDEX_HINT),
    "not_found": ("E_USAGE", "was not found", _INDEX_HINT),
}

#: PII-free ``log_message`` per error code (never uid, name, path or account).
_ERROR_LOG: Final[dict[str, str]] = {
    UNAVAILABLE_CODE: "attachment is unavailable",
    UNREADABLE_CODE: "attachment is corrupt or unreadable",
    "E_PERMISSION": "attachment cannot be read: permission denied",
    "E_CLIENT_BUSY": "attachment is temporarily unavailable",
    "E_CLIENT_TIMEOUT": "attachment did not respond within the timeout",
    "E_PLUGIN_FAILED": _ATTACHMENT_ERROR_LOG,
    "E_USAGE": "attachment index or message not found",
}


class AttachmentResult(TypedDict):
    """One ``attachment`` JSON record (§11.2): ``saved`` is always true on success."""

    index: int
    original_name: str
    sanitized_name: str
    saved: bool
    cached: bool
    path: str
    size_bytes: int
    sha256: str


class AttachmentLimits(Protocol):
    """Duck-typed ``config.AttachmentsConfig`` (M02/C2); the engine imports no config."""

    max_file_size_mb: int
    max_total_size_mb: int
    max_count: int


class AttachmentDriver(Protocol):
    """Duck-typed ``MailBackend`` attachment surface (C1); no backend import."""

    driver: str

    def parse_native_id(self, native_id: str) -> object: ...

    def attachments(self, uid: object) -> Iterable[Mapping[str, object]]: ...

    def attachment_stream(self, uid: object, index: int) -> Iterable[bytes]: ...


#: Zero-argument factory returning the deadline of one attachment (clock units).
DeadlineFactory = Callable[[], float | None]


class _DeadlineExpired(Exception):
    """Internal marker raised when an injected extraction deadline has expired."""


class _Deadlines:
    """Per-attachment deadline bookkeeping with an injectable clock."""

    def __init__(
        self,
        factory: DeadlineFactory | None,
        clock: Callable[[], float],
    ) -> None:
        self._factory = factory
        self._clock = clock
        self._instants: dict[int, float | None] = {}
        self._faults: dict[int, Exception] = {}

    def start(self, index: int) -> None:
        """Record the extraction deadline of ``index`` (once, before screening)."""
        if self._factory is None or index in self._instants:
            return
        self._instants[index] = self._factory()

    def check(self, index: int) -> None:
        """Raise :class:`_DeadlineExpired` when the attachment budget is spent."""
        instant = self._instants.get(index)
        if instant is not None and self._clock() >= instant:
            raise _DeadlineExpired()

    def wrap(self, index: int, stream: Iterable[bytes]) -> Iterator[bytes]:
        """Yield the driver chunks after checking the deadline of each one."""
        try:
            for chunk in stream:
                self.check(index)
                yield chunk
        except (GeneratorExit, StopIteration):
            raise
        except Exception as exc:  # recorded so the screen can map the real reason
            self._faults[index] = exc
            raise

    def note(self, index: int, exc: Exception) -> None:
        """Record a driver exception raised while opening the stream."""
        self._faults[index] = exc

    def fault(self, index: int | None) -> Exception | None:
        """The recorded driver exception of ``index`` (``None`` when clean)."""
        if index is None:
            return None
        return self._faults.get(index)


class AttachmentsEngine:
    """Limits, staging, cache and atomic publication for one loaded driver (M07).

    The engine does not open the store and does not decide validation rows 1–10
    (§11.3): the command resolves the uid, the driver and the message first and
    may pass the already validated metadata rows through ``entries``.
    """

    def __init__(
        self,
        home: str | Path,
        config: AttachmentLimits,
        driver: AttachmentDriver,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._home = Path(home)
        self._config = config
        self._driver = driver
        self._clock = time.monotonic if clock is None else clock
        self._driver_name = str(getattr(driver, "driver", "") or "unknown")

    @property
    def home(self) -> Path:
        """The application home (``~/.mailquery``)."""
        return self._home

    @property
    def driver(self) -> object:
        """The loaded driver this engine extracts from."""
        return self._driver

    # -- public operation --------------------------------------------------- #

    def recover(
        self,
        uid: str,
        indices: Sequence[int] | None = None,
        *,
        force: bool = False,
        deadline: DeadlineFactory | None = None,
        entries: Iterable[Mapping[str, object]] | None = None,
    ) -> list[AttachmentResult]:
        """Recover the requested attachments of one message into the cache.

        ``uid`` is the canonical ``"<driver>:<native_id>"`` string; ``indices``
        is ``None`` for ``--all`` or the ``--index`` 1-based positions. With
        ``entries`` the engine skips its own metadata call (the command already
        fetched and mapped the rows). Returns one §11.2 record per requested
        attachment in index order, or raises :class:`MailqueryError`; a failure
        never returns partial records and never leaves staging files.
        """
        parsed = parse_uid(uid)
        canonical = parsed.uid
        legacy_uid = self._legacy_uid(canonical, parsed.native_id)
        raw_entries = (
            self._metadata(canonical, legacy_uid) if entries is None else entries
        )
        rows = _normalize_entries(raw_entries)
        by_index = {row["index"]: row for row in rows}
        requested = _requested_indices(rows, indices, canonical)

        names = screen_names(rows)
        if names.failed:
            raise self._screen_error(canonical, names)

        max_count = int(self._config.max_count)
        if indices is None and len(rows) > max_count:
            raise _max_count_error(canonical, len(rows), max_count)
        max_file_bytes = int(self._config.max_file_size_mb) * MIB
        max_total_bytes = int(self._config.max_total_size_mb) * MIB

        cache = AttachmentCache(self._home, canonical)
        sanitized = {
            index: sanitize_name(by_index[index]["name"], index) for index in requested
        }
        expected: dict[int, int | None] = {
            index: by_index[index]["size_bytes"] for index in requested
        }

        hits: dict[int, CacheHit] = {}
        if not force:
            for index in requested:
                row = by_index[index]
                hit = cache.lookup(
                    row["name"], index, expected_size=row["size_bytes"]
                )
                if hit is not None:
                    hits[index] = hit

        for index in requested:
            known = hits[index].size_bytes if index in hits else expected[index]
            if known is not None and known > max_file_bytes:
                raise _max_file_error(
                    canonical,
                    index,
                    by_index[index]["name"],
                    int(self._config.max_file_size_mb),
                    known,
                )

        misses = [index for index in requested if index not in hits]
        total_lower = sum(hit.size_bytes for hit in hits.values())
        total_lower += sum(
            expected[index] for index in misses if expected[index] is not None
        )
        if total_lower > max_total_bytes:
            raise _max_total_error(
                canonical,
                len(requested),
                int(self._config.max_total_size_mb),
                total_lower,
            )

        tracker = _Deadlines(deadline, self._clock)
        staging: StagingArea = cache.staging()
        staged: dict[int, StagedAttachment] = {}
        records: dict[int, AttachmentResult] = {}
        final_sizes: dict[int, int] = {
            index: hit.size_bytes for index, hit in hits.items()
        }
        pending: set[int] = set(misses)

        def projected_total(current_index: int, current_written: int) -> int:
            total = sum(final_sizes.values()) + current_written
            for other in pending:
                if other == current_index:
                    continue
                known = expected.get(other)
                if known is not None:
                    total += known
            return total

        def open_stream(index: int) -> Iterator[bytes]:
            tracker.start(index)
            try:
                stream = self._driver.attachment_stream(legacy_uid, index)
            except Exception as exc:
                tracker.note(index, exc)
                raise
            return tracker.wrap(index, stream)

        def screen(indices_to_screen: Sequence[int]) -> None:
            if not indices_to_screen:
                return
            decision = screen_content(rows, indices_to_screen, open_stream)
            if decision.failed:
                raise self._screen_error(
                    canonical, decision, by_index, tracker
                )

        def extract(index: int) -> StagedAttachment:
            row = by_index[index]
            staged_file = staging.new_file()
            written = 0
            try:
                tracker.start(index)
                tracker.check(index)
                for chunk in tracker.wrap(
                    index, self._driver.attachment_stream(legacy_uid, index)
                ):
                    if not chunk:
                        continue
                    staged_file.append(chunk)
                    written += len(chunk)
                    if written > max_file_bytes:
                        raise _max_file_error(
                            canonical,
                            index,
                            row["name"],
                            int(self._config.max_file_size_mb),
                            written,
                        )
                    total = projected_total(index, written)
                    if total > max_total_bytes:
                        raise _max_total_error(
                            canonical,
                            len(requested),
                            int(self._config.max_total_size_mb),
                            total,
                        )
            except _DeadlineExpired:
                raise _timeout_error(canonical, index, row["name"]) from None
            except MailqueryError:
                raise
            except Exception as exc:
                mapped = self._driver_error(canonical, index, row["name"], exc)
                if mapped is not None:
                    raise mapped from exc
                raise
            staged_file.finish()
            final_sizes[index] = written
            pending.discard(index)
            expected.pop(index, None)
            return staged_file

        try:
            screen(misses)
            for index in misses:
                staged[index] = extract(index)

            # The external cron may delete a cached file while this run is
            # extracting the other attachments: verify the hits once, near the
            # end, and re-extract a vanished/mutated one a single time (RF-51).
            broken = [
                index for index in sorted(hits) if not cache.verify(hits[index])
            ]
            if broken:
                screen(broken)
                for index in broken:
                    hits.pop(index)
                    final_sizes.pop(index, None)
                    expected[index] = by_index[index]["size_bytes"]
                    pending.add(index)
                    staged[index] = extract(index)

            for index in sorted(staged):
                target = cache.publish(
                    staged[index], by_index[index]["name"], index
                )
                records[index] = _extracted_record(
                    by_index[index], sanitized[index], staged[index], target
                )
            for index, hit in hits.items():
                records[index] = _hit_record(
                    by_index[index], sanitized[index], hit
                )
            return [records[index] for index in requested]
        finally:
            staging.close()

    # -- driver access ------------------------------------------------------ #

    def _legacy_uid(self, canonical: str, native_id: str) -> object:
        """Native uid handed to the driver operations (C1)."""
        try:
            return self._driver.parse_native_id(native_id)
        except MailqueryError:
            raise
        except Exception as exc:
            mapped = self._driver_error(canonical, None, "", exc)
            if mapped is not None:
                raise mapped from exc
            raise

    def _metadata(
        self, canonical: str, legacy_uid: object
    ) -> Iterable[Mapping[str, object]]:
        """Driver attachment metadata (C1); the command normally supplies it."""
        try:
            return self._driver.attachments(legacy_uid)
        except MailqueryError:
            raise
        except Exception as exc:
            mapped = self._driver_error(canonical, None, "", exc)
            if mapped is not None:
                raise mapped from exc
            raise

    def _driver_error(
        self,
        uid: str,
        index: int | None,
        name: str,
        exc: Exception,
    ) -> MailqueryError | None:
        """Map a driver exception to the §11.7 attachment code (defensive)."""
        if isinstance(exc, MailqueryError):
            return exc
        if isinstance(exc, _DeadlineExpired):
            return _timeout_error(uid, index, name)
        reason = _reason_of(exc)
        if reason is not None:
            return _reason_error(uid, self._driver_name, index, name, reason)
        if isinstance(exc, TimeoutError):
            return _timeout_error(uid, index, name)
        if isinstance(exc, PermissionError):
            return _reason_error(uid, self._driver_name, index, name, "permission")
        if isinstance(exc, OSError):
            return _reason_error(uid, self._driver_name, index, name, "unreadable")
        return None

    def _screen_error(
        self,
        uid: str,
        decision: ScreenDecision,
        by_index: Mapping[int, Mapping[str, object]] | None = None,
        tracker: _Deadlines | None = None,
    ) -> MailqueryError:
        """Build the user-facing error of a failed M06 screen decision."""
        index = decision.index
        name = decision.name or ""
        if decision.code == BLOCKED_CODE:
            return _blocked_error(uid, index, name, decision.detail or "")
        fault = tracker.fault(index) if tracker is not None else None
        if fault is not None:
            mapped = self._driver_error(uid, index, name, fault)
            if mapped is not None:
                return mapped
        if index is not None and by_index is not None:
            row = by_index.get(index)
            if row is not None and not name:
                name = str(row["name"])
        return _reason_error(
            uid, self._driver_name, index, name, decision.reason or "unreadable"
        )


# --------------------------------------------------------------------------- #
# Metadata validation and request resolution
# --------------------------------------------------------------------------- #


def _normalize_entries(
    entries: Iterable[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Validate the C1 metadata rows and return them sorted by 1-based index."""
    normalized: list[dict[str, object]] = []
    seen: set[int] = set()
    for row in entries:
        if not isinstance(row, Mapping):
            raise _invalid_metadata()
        index = row.get("index")
        name = row.get("name")
        if isinstance(index, bool) or not isinstance(index, int) or index < 1:
            raise _invalid_metadata()
        if not isinstance(name, str):
            raise _invalid_metadata()
        if index in seen:
            raise _invalid_metadata()
        size = row.get("size_bytes")
        if size is not None and (
            isinstance(size, bool) or not isinstance(size, int) or size < 0
        ):
            raise _invalid_metadata()
        reason = row.get("unavailable_reason")
        if reason is not None and not isinstance(reason, str):
            raise _invalid_metadata()
        seen.add(index)
        normalized.append(
            {
                "index": index,
                "name": name,
                "size_bytes": size,
                "native_order_key": str(row.get("native_order_key", "")),
                "unavailable_reason": reason,
            }
        )
    normalized.sort(key=lambda row: int(row["index"]))
    return normalized


def _invalid_metadata() -> MailqueryError:
    return MailqueryError(
        "E_PLUGIN_FAILED",
        "the driver returned invalid attachment metadata",
        'run "mailquery doctor" and check the driver entry for details',
        "invalid attachment metadata",
    )


def _requested_indices(
    rows: Sequence[Mapping[str, object]],
    indices: Sequence[int] | None,
    uid: str,
) -> list[int]:
    """Resolve ``--index``/``--all`` against the metadata indexes (§11.3 row 10)."""
    available = [int(row["index"]) for row in rows]
    if indices is None:
        return available
    values: set[int] = set()
    for value in indices:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise MailqueryError(
                "E_USAGE",
                "invalid --index: expected a positive integer (1 or greater)",
                _INDEX_HINT,
                "attachment index out of range",
            )
        values.add(value)
    if not values:
        raise MailqueryError(
            "E_USAGE",
            "attachment requires exactly one of --index or --all",
            _INDEX_HINT,
            "attachment index out of range",
        )
    missing = sorted(values - set(available))
    if missing:
        raise _out_of_range_error(uid, missing[0], len(available))
    return sorted(values)


# --------------------------------------------------------------------------- #
# Records and user-facing errors
# --------------------------------------------------------------------------- #


def _hit_record(
    row: Mapping[str, object],
    sanitized_name: str,
    hit: CacheHit,
) -> AttachmentResult:
    return AttachmentResult(
        index=int(row["index"]),
        original_name=str(row["name"]),
        sanitized_name=sanitized_name,
        saved=True,
        cached=True,
        path=_absolute(hit.path),
        size_bytes=hit.size_bytes,
        sha256=hit.sha256,
    )


def _extracted_record(
    row: Mapping[str, object],
    sanitized_name: str,
    staged: StagedAttachment,
    target: Path,
) -> AttachmentResult:
    return AttachmentResult(
        index=int(row["index"]),
        original_name=str(row["name"]),
        sanitized_name=sanitized_name,
        saved=True,
        cached=False,
        path=_absolute(target),
        size_bytes=staged.size_bytes,
        sha256=staged.sha256,
    )


def _absolute(path: Path) -> str:
    return os.path.abspath(os.fspath(path))


def _mib_ceil(size_bytes: int) -> int:
    return (size_bytes + MIB - 1) // MIB


def _reason_of(exc: Exception) -> str | None:
    """Duck-typed ``PluginError.reason`` (M05); no ``mailquery.plugins`` import."""
    reason = getattr(exc, "reason", None)
    if reason is None:
        return None
    value = getattr(reason, "value", reason)
    return value if isinstance(value, str) else str(value)


def _reason_error(
    uid: str,
    driver_name: str,
    index: int | None,
    name: str,
    reason: str,
) -> MailqueryError:
    rule = _REASON_RULES.get(reason)
    if index is None:
        stem = f"attachments of message {uid}"
    else:
        shown = display_name(name) if name else ""
        stem = f"attachment {index} ('{shown}') of message {uid}"
    if rule is None:
        return MailqueryError(
            "E_PLUGIN_FAILED",
            f"{stem} could not be recovered: the driver returned an unexpected error",
            'run "mailquery doctor" and check the driver entry for details',
            _ATTACHMENT_ERROR_LOG,
        )
    code, fragment, hint = rule
    return MailqueryError(
        code,
        f"{stem} {fragment.format(driver=driver_name)}",
        hint,
        _ERROR_LOG.get(code, _ATTACHMENT_ERROR_LOG),
    )


def _blocked_error(
    uid: str,
    index: int | None,
    name: str,
    detail: str,
) -> MailqueryError:
    if index is None:
        message = f"message {uid} was blocked: {detail}"
    else:
        shown = display_name(name) if name else ""
        message = f"message {uid} was blocked: attachment {index} ('{shown}') {detail}"
    return MailqueryError(
        BLOCKED_CODE,
        message,
        _BLOCKED_HINT,
        f"message blocked: attachment {detail}".strip(),
    )


def _max_file_error(
    uid: str,
    index: int,
    name: str,
    limit_mb: int,
    size_bytes: int,
) -> MailqueryError:
    return MailqueryError(
        "E_ATTACHMENT_TOO_LARGE",
        f"message {uid} exceeds max_file_size_mb={limit_mb}: "
        f"attachment {index} ('{display_name(name)}') is "
        f"{_mib_ceil(size_bytes)} MiB",
        "raise max_file_size_mb in ~/.mailquery/config.toml and retry",
        f"message exceeds max_file_size_mb={limit_mb}",
    )


def _max_total_error(
    uid: str,
    count: int,
    limit_mb: int,
    total_bytes: int,
) -> MailqueryError:
    return MailqueryError(
        "E_ATTACHMENT_TOO_LARGE",
        f"message {uid} exceeds max_total_size_mb={limit_mb}: "
        f"{count} attachment(s) total {_mib_ceil(total_bytes)} MiB",
        "recover attachments one by one with --index, or raise "
        "max_total_size_mb in ~/.mailquery/config.toml",
        f"message exceeds max_total_size_mb={limit_mb}",
    )


def _max_count_error(uid: str, count: int, limit: int) -> MailqueryError:
    return MailqueryError(
        "E_ATTACHMENT_TOO_LARGE",
        f"message {uid} exceeds max_count={limit}: {count} attachment(s)",
        "recover attachments one by one with --index, or raise max_count in "
        "~/.mailquery/config.toml",
        f"message exceeds max_count={limit}",
    )


def _timeout_error(uid: str, index: int | None, name: str) -> MailqueryError:
    if index is None:
        message = f"attachments of message {uid} did not respond within the timeout"
    else:
        message = (
            f"attachment {index} ('{display_name(name)}') of message {uid} "
            "did not respond within the timeout"
        )
    return MailqueryError(
        "E_CLIENT_TIMEOUT",
        message,
        _TIMEOUT_HINT,
        "attachment did not respond within the timeout",
    )


def _out_of_range_error(uid: str, index: int, count: int) -> MailqueryError:
    return MailqueryError(
        "E_USAGE",
        f"attachment index {index} is out of range: message {uid} has "
        f"{count} attachment(s) (valid: 1..{count})",
        f"run `mailquery show {uid}` to list the attachment indexes",
        "attachment index out of range",
    )


__all__ = [
    "AttachmentDriver",
    "AttachmentLimits",
    "AttachmentResult",
    "AttachmentsEngine",
    "DeadlineFactory",
    "MIB",
]

"""Search, new-mail, show and mailboxes queries.

Applies the configured scope (declared accounts only,
INBOX always included), deduplicates by ``global_message_id`` with INBOX
priority, bounds content scans (``--text``) and assembles the JSON message
objects. This module renders no JSON: it returns plain dictionaries that the
CLI wraps with ``ok``/``command``/``generated_at``.

Everything backend-specific goes through :class:`mailquery.backends.base.MailBackend`:
this module holds no SQL and no COM, never opens a database, a
``.emlx`` file or a mail client on its own, and never writes anything.
"""

from __future__ import annotations

import re
import time
import unicodedata
import dataclasses
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import cmp_to_key
from typing import TYPE_CHECKING, Any, Callable, Iterable, Mapping, Sequence

from mailquery import config as config_module
from mailquery import output
from mailquery import uid as uid_module
from mailquery.attachments import classify_name
from mailquery.attachments.cache import cached_path as attachment_cached_path
from mailquery.backends.base import ExcludedStoreError
from mailquery.errors import MailqueryError
from mailquery.plugins import wrap_driver
from mailquery.state import Cursor, EmittedUid

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mailquery.backends.base import AccountRow, BodyRow, MailBackend, MailboxRow
    from mailquery.config import Config
    from mailquery.state import StateStore

#: Built-in drivers: their ``show`` attachment fallback predates the
#: ``attachments`` metadata operation; the API 1 ``attachments`` call is
#: preferred for every driver once it is implemented.
_INTERNAL_DRIVERS = frozenset({"apple_mail", "outlook"})


# Limits fixed by the product contract.
SEARCH_MAX_LIMIT = 200
NEW_MAX_LIMIT = 500
MAX_SCAN_HARD_LIMIT = 50_000

# Stable warning strings ("warnings[]").
NO_ACCOUNTS_WARNING = (
    "W_NO_ACCOUNTS: no accounts are declared in config.toml; nothing is observed"
)
LABELS_UNAVAILABLE_WARNING = (
    "W_ACCOUNT_LABELS_UNAVAILABLE: account labels are unavailable; UUIDs are shown instead"
)
_ATTACHMENTS_UNAVAILABLE_WARNING = (
    "W_ATTACHMENTS_UNAVAILABLE: attachment names come from the envelope index; "
    "the message body could not be read"
)
FIRST_RUN_WARNING_TEMPLATE = (
    "W_FIRST_RUN: first run: emitted the messages received in the last "
    "{lookback} before the newest message"
)

# Relative-time parsing.
_RELATIVE_UNITS = {
    "min": 60,
    "h": 60 * 60,
    "d": 24 * 60 * 60,
    "w": 7 * 24 * 60 * 60,
    "mo": 30 * 24 * 60 * 60,
    "y": 365 * 24 * 60 * 60,
}
_RELATIVE_PATTERN = re.compile(r"^(\d+)(min|h|d|w|mo|y)$")
_WILDCARD_SPLIT = re.compile(r"([*?])")


@dataclass(frozen=True)
class Filters:
    """Validated CLI filters for ``search``."""

    subject: tuple[str, ...] = ()
    text: tuple[str, ...] = ()
    from_: tuple[str, ...] = ()
    to: tuple[str, ...] = ()
    cc: tuple[str, ...] = ()
    since: float | None = None
    until: float | None = None
    unread: bool = False
    flagged: bool = False
    has_attachments: bool = False
    include_mailboxes: tuple[str, ...] = ()
    limit: int | None = None


@dataclass(frozen=True)
class ScanStats:
    mode: str
    candidates: int
    messages_read: int
    duration_ms: int


@dataclass
class _DriverRun:
    """One driver participating in a command: its backend and its resolved scope.

    ``allowed_ids`` and ``mailbox_map`` start with the declared accounts' folders
    and grow with the ``--include-mailbox`` folders that belong to this driver;
    ``label_map`` is filled after the candidate rows of the driver are
    known (dedupe/display only need it for those rows).
    """

    driver: str
    backend: "MailBackend"
    accounts: "dict[str, AccountRow]"
    mailbox_map: "dict[Any, MailboxRow]"
    allowed_ids: frozenset[Any]
    label_map: "dict[Any, set[Any]]" = field(default_factory=dict)



# --------------------------------------------------------------------------- #
# Time values and wildcards (pure helpers, exported)
# --------------------------------------------------------------------------- #


def parse_relative_time(value: str, now: datetime | None = None) -> float:
    """Parse an ISO date or relative value into Unix seconds (E_BAD_TIME).

    Accepted inputs are ISO 8601 values (``2026-11-01``,
    ``2026-11-01T22:54:03-04:00``), the keywords ``now``/``today``/
    ``yesterday`` and the relative offsets ``30min``, ``24h``, ``7d``, ``1w``,
    ``2w``, ``1mo``, ``2mo``, ``6mo`` and ``1y``. Dates without a time are
    interpreted as local midnight; relative values are computed against
    ``now`` (local time by default). Invalid values raise ``E_BAD_TIME``.
    """
    reference = now if now is not None else datetime.now()
    text = "" if value is None else str(value).strip()
    if not text:
        raise _bad_time(value)

    lowered = text.lower()
    if lowered == "now":
        return float(reference.timestamp())
    if lowered == "today":
        return float(_local_midnight(reference).timestamp())
    if lowered == "yesterday":
        return float((_local_midnight(reference) - timedelta(days=1)).timestamp())

    relative = _RELATIVE_PATTERN.match(lowered)
    if relative is not None:
        amount = int(relative.group(1))
        unit = relative.group(2)
        return float(reference.timestamp() - amount * _RELATIVE_UNITS[unit])

    parsed = _parse_iso_datetime(text)
    if parsed is None:
        raise _bad_time(value)
    return float(parsed.timestamp())


def wildcard_to_regex(pattern: str) -> str:
    """Translate ``*``/``?`` wildcards into a case-insensitive regex string.

    Everything that is not a wildcard is escaped with :func:`re.escape`, so the
    result can be fed to :func:`re.search` (with ``re.IGNORECASE``) without any
    further quoting. Without wildcards the result is a plain escaped substring.
    """
    pieces: list[str] = []
    for chunk in _WILDCARD_SPLIT.split("" if pattern is None else str(pattern)):
        if chunk == "*":
            pieces.append(".*")
        elif chunk == "?":
            pieces.append(".")
        elif chunk:
            pieces.append(re.escape(chunk))
    return "".join(pieces)


def matches(pattern: str, text: str) -> bool:
    """Case-insensitive wildcard/substring match against untrusted text.

    ``*`` matches any sequence and ``?`` any single character; a pattern
    without wildcards is a plain substring. Both sides are Unicode-normalized
    (NFKD, combining marks removed, casefolded) so accented and unaccented
    spellings of the same word match each other.
    """
    if pattern is None:
        return True
    raw_pattern = str(pattern)
    if not raw_pattern:
        return True
    expression = wildcard_to_regex(_fold(raw_pattern))
    return re.search(expression, _fold(text or ""), re.IGNORECASE) is not None


# --------------------------------------------------------------------------- #
# Driver pool (multi-driver engine)
# --------------------------------------------------------------------------- #


def _native_driver(backend: "MailBackend | None", native: str | None) -> str:
    """Native driver name of the command (injected backend or the platform)."""
    if native:
        return str(native)
    driver = _driver(backend) if backend is not None else ""
    return driver or str(uid_module.platform_native_driver())


def _driver_pool(
    backend: "MailBackend | None",
    drivers: "Mapping[str, MailBackend] | None",
    native: str | None,
) -> tuple[str, "dict[str, MailBackend]"]:
    """Native driver name and every backend the caller opened for this command.

    ``backend`` is the platform driver (``None`` when the config does not declare
    it); ``drivers`` maps the other declared drivers. The order is the caller's:
    native first, then the mapping order. Every backend is wrapped with the
    driver-call wrapper, so all metadata operations are mapped and bounded by the
    metadata deadline (the wrapper is idempotent: wrapping twice is a no-op).
    """
    native_name = _native_driver(backend, native)
    pool: dict[str, Any] = {}
    if backend is not None:
        key = _driver(backend) or native_name
        pool[key] = wrap_driver(
            backend, driver=key, internal=key in _INTERNAL_DRIVERS
        )
    for name, driver_backend in (drivers or {}).items():
        key = str(name)
        if key not in pool:
            pool[key] = wrap_driver(
                driver_backend, driver=key, internal=key in _INTERNAL_DRIVERS
            )
    return native_name, pool


def _scopes_by_driver(resolved: Sequence[Any]) -> "dict[str, list[Any]]":
    """Resolved scopes grouped by driver, in ``[scope]`` block order."""
    groups: dict[str, list[Any]] = {}
    for scope in resolved:
        groups.setdefault(str(getattr(scope, "driver", "") or ""), []).append(scope)
    return groups


def _driver_runs(
    groups: "Mapping[str, Sequence[Any]]", pool: "Mapping[str, MailBackend]"
) -> "dict[str, _DriverRun]":
    """Backend, accounts and folders of every driver that declares an account."""
    runs: dict[str, _DriverRun] = {}
    for driver, scopes in groups.items():
        backend = pool.get(driver)
        if backend is None:
            raise uid_module.driver_unknown(driver)
        runs[driver] = _DriverRun(
            driver=driver,
            backend=backend,
            accounts=_accounts_by_uuid(backend),
            mailbox_map=_mailbox_map(backend, scopes),
            allowed_ids=frozenset(
                mailbox["id"]
                for scope in scopes
                for mailbox in getattr(scope, "mailboxes", ()) or ()
            ),
        )
    return runs


def _apply_include_mailboxes(
    runs: "Mapping[str, _DriverRun]",
    includes: "Sequence[tuple[str, MailboxRow]]",
) -> None:
    """Add the ``--include-mailbox`` folders to the run of their own driver."""
    for driver, mailbox in includes:
        run = runs.get(driver)
        if run is None:  # pragma: no cover - includes resolve inside declared scopes
            continue
        run.allowed_ids = frozenset((*run.allowed_ids, mailbox["id"]))
        run.mailbox_map.setdefault(mailbox["id"], mailbox)


def _include_rows(
    includes: "Sequence[tuple[str, MailboxRow]]",
) -> "tuple[MailboxRow, ...]":
    """The included mailboxes as rows (the shape ``_require_bounded_scan`` wants)."""
    return tuple(mailbox for _driver, mailbox in includes)


def _run_backends(runs: "Mapping[str, _DriverRun]") -> "dict[str, MailBackend]":
    return {driver: run.backend for driver, run in runs.items()}


def _page_recipients(
    page: Sequence[dict], runs: "Mapping[str, _DriverRun]"
) -> "dict[str, dict[Any, Any]]":
    """To/Cc of the page rows, fetched once per driver."""
    grouped: dict[str, list[dict]] = {}
    for row in page:
        grouped.setdefault(str(row["_mq_driver"]), []).append(row)
    return {
        driver: runs[driver].backend.recipients([row["uid"] for row in rows])
        for driver, rows in grouped.items()
    }


def _activation_warnings(
    backends: "Iterable[MailBackend]", excluded: Sequence[dict]
) -> list[str]:
    """Scope warnings of the run: excluded stores first, then labels (deduplicated)."""
    warnings = [_store_excluded_warning(entry) for entry in excluded]
    for backend in backends:
        warnings.extend(_labels_warnings(backend))
    return list(dict.fromkeys(warnings))


def _driver_output_order(
    config: "Config",
    native: str,
    groups: "Mapping[str, Sequence[Any]]",
    pool: "Mapping[str, MailBackend]",
) -> list[str]:
    """Drivers in the order their ``[scope]`` blocks first appear."""
    order: list[str] = []
    for entry in config.scopes:
        driver = str(entry.driver or native)
        if driver not in order and (driver in groups or driver in pool):
            order.append(driver)
    for driver in groups:
        if driver not in order:
            order.append(driver)
    if not config.scopes and native in pool and native not in order:
        order.insert(0, native)
    return order


def _merge_ordered(
    canonical: "Mapping[str, Sequence[dict]]",
    backends: "Mapping[str, MailBackend]",
    *,
    descending: bool,
) -> list[dict]:
    """Merge per-driver lists in the total order.

    Rows are tagged with their driver (``_mq_driver``, internal only) because the
    merged page is built with the backend and scope of each row's driver. The
    sort is stable: rows equal in ``(date_received, driver, native_order_key)``
    keep the per-driver backend order (deterministic; the uid is never compared).
    """
    merged: list[dict] = []
    for driver, rows in canonical.items():
        for row in rows:
            tagged = dict(row)
            tagged["_mq_driver"] = driver
            merged.append(tagged)

    def compare(left: dict, right: dict) -> int:
        return _compare_total_order(left, right, backends, descending=descending)

    merged.sort(key=cmp_to_key(compare))
    return merged


def _compare_total_order(
    left: dict,
    right: dict,
    backends: "Mapping[str, MailBackend]",
    *,
    descending: bool,
) -> int:
    """Compare two tagged rows in the total order of the command."""
    left_date, right_date = _date_key(left), _date_key(right)
    if left_date != right_date:
        return _direction(left_date > right_date, descending)
    left_driver, right_driver = str(left["_mq_driver"]), str(right["_mq_driver"])
    if left_driver != right_driver:
        return -1 if left_driver < right_driver else 1
    backend = backends[left_driver]
    left_key = _native_order_key(backend, left)
    right_key = _native_order_key(backend, right)
    if left_key == right_key:
        return 0
    return _direction(left_key > right_key, descending)


def _direction(is_greater: bool, descending: bool) -> int:
    """``-1`` when the left value sorts first according to the direction."""
    if descending:
        return -1 if is_greater else 1
    return 1 if is_greater else -1


# --------------------------------------------------------------------------- #
# Public commands
# --------------------------------------------------------------------------- #


def run_search(
    backend: "MailBackend | None",
    config: "Config",
    filters: Filters,
    *,
    drivers: "Mapping[str, MailBackend] | None" = None,
    native: str | None = None,
) -> dict:
    """Return ``{"count", "messages", "truncated", "scan", "warnings"}``.

    The scope is the set of accounts declared in ``config.toml`` (INBOX always
    included) plus their ``mailbox_list`` folders and the ``--include-mailbox``
    folders of this run. Every declared driver is queried with the same filters;
    the per-driver results are deduplicated inside their driver,
    merged with the total order ``(date_received DESC, driver ASC,
    native_order_key DESC)`` and paginated after the merge.
    """
    started = time.perf_counter()
    native_name, pool = _driver_pool(backend, drivers, native)

    excluded: list[dict] = []
    resolved = _resolved_scope(config, backend, excluded, drivers=drivers, native=native_name)
    runs = _driver_runs(_scopes_by_driver(resolved), pool)

    text_terms = _filter_terms(filters.text)
    mode = "text" if text_terms else "metadata"
    opens_recipients = {
        driver: _recipients_open_items(run.backend) for driver, run in runs.items()
    }
    opens_any = any(opens_recipients.values())
    content_flags = _content_flags(filters, opens_any)
    warning_backends = (
        [run.backend for run in runs.values()] if runs else list(pool.values())
    )
    scope_warnings = _activation_warnings(warning_backends, excluded)

    includes = _include_entries(
        backend, resolved, filters.include_mailboxes, drivers=drivers, native=native_name
    )
    if not resolved and not includes:
        return _empty_search_result(
            mode, started, [NO_ACCOUNTS_WARNING, *scope_warnings]
        )
    _apply_include_mailboxes(runs, includes)
    if not any(run.allowed_ids for run in runs.values()):
        return _empty_search_result(mode, started, scope_warnings)

    if content_flags:
        _require_bounded_scan(
            resolved, _include_rows(includes), filters, content_flags, opens_any
        )

    warnings: list[str] = list(scope_warnings)
    opened_before = {
        driver: _items_opened(run.backend) for driver, run in runs.items()
    }
    pending: list[tuple[_DriverRun, list[dict]]] = []
    candidates = 0
    for driver, run in runs.items():
        ids = sorted(run.allowed_ids)
        if not ids:
            pending.append((run, []))
            continue
        rows = run.backend.query(
            ids,
            since=filters.since,
            until=filters.until,
            unread=filters.unread,
            flagged=filters.flagged,
            has_attachments=filters.has_attachments,
            order="desc",
        )
        # On Windows --to/--cc open every candidate: they are applied after the
        # max_scan check and the candidates are counted before them.
        rows = _apply_pattern_filters(
            rows, filters, run.backend, recipients=not opens_recipients[driver]
        )
        candidates += len(rows)
        pending.append((run, rows))

    # The multi-driver bound is the sum of every driver's candidates: one
    # budget for the merged command.
    if content_flags:
        max_scan = _effective_max_scan(config)
        if candidates > max_scan:
            raise _scan_too_large(content_flags, candidates, max_scan, opens_any)

    canonical: dict[str, list[dict]] = {}
    scan_reads: dict[str, int] = {driver: 0 for driver in runs}
    for run, rows in pending:
        driver_backend = run.backend
        recipient_terms = (
            (_filter_terms(filters.to), _filter_terms(filters.cc))
            if opens_recipients[run.driver]
            else ((), ())
        )
        if text_terms:
            rows, scan_warnings, scan_reads[run.driver] = _scan_bodies(
                driver_backend, rows, text_terms, recipient_terms
            )
            warnings.extend(scan_warnings)
        elif any(recipient_terms):
            rows = _filter_recipients(rows, *recipient_terms, driver_backend)
        run.label_map = driver_backend.membership([row["uid"] for row in rows])
        duplicate_counts = driver_backend.duplicate_counts(run.allowed_ids)
        canonical[run.driver] = _dedupe(
            rows, run.mailbox_map, run.label_map, duplicate_counts, driver_backend
        )

    merged = _merge_ordered(canonical, _run_backends(runs), descending=True)
    limit = _search_limit(config, filters.limit)
    page = merged[:limit]
    truncated = len(merged) > limit
    if truncated:
        warnings.append(_truncated_warning(len(merged) - limit))

    recipients = _page_recipients(page, runs)
    messages, body_warnings, reads = _build_messages(
        page, runs, recipients, cached_bodies=bool(text_terms)
    )
    warnings.extend(body_warnings)
    messages_read = 0
    for driver, run in runs.items():
        before = opened_before[driver]
        if before is not None:
            messages_read += _items_opened(run.backend) - before
        else:
            messages_read += scan_reads.get(driver, 0) + reads.get(driver, 0)

    return {
        "count": len(messages),
        "truncated": truncated,
        "hint": _search_hint(truncated),
        "messages": messages,
        "scan": _scan_dict(mode, candidates, messages_read, started),
        "warnings": warnings,
    }


def run_new(
    backend: "MailBackend | None",
    config: "Config",
    state_store: "StateStore",
    *,
    peek: bool = False,
    limit: int | None = None,
    clock: Callable[[], float] | None = None,
    drivers: "Mapping[str, MailBackend] | None" = None,
    native: str | None = None,
) -> dict:
    """Return ``{"count", "messages", "truncated", "scan", "cursor", "warnings"}``.

    Messages with a null, non-positive or future ``date_received`` (relative to
    ``clock``, Unix seconds, ``time.time`` by default) never enter ``new`` and
    never move the cursor.

    The cursor is global (one ``last_date_received``/``last_uid``): every
    declared driver is queried with the same watermark and lookback and each one
    contributes its deduplicated messages to the merged ascending order
    ``(date_received ASC, driver ASC, native_order_key ASC)``.
    The first run emits the window ``[D - lookback, D]`` over the merged set
    (``D`` = newest valid date of the merged set, the newest ``limit`` of them)
    and reports ``W_FIRST_RUN`` last. Later runs emit, in arrival order, the
    messages received since ``cursor - lookback`` whose prefixed uid is not in
    the ring. ``peek`` never writes state.
    """
    started = time.perf_counter()
    now = float(clock()) if clock is not None else time.time()
    native_name, pool = _driver_pool(backend, drivers, native)

    excluded: list[dict] = []
    resolved = _resolved_scope(config, backend, excluded, drivers=drivers, native=native_name)
    runs = _driver_runs(_scopes_by_driver(resolved), pool)

    app_state = state_store.load()
    previous = app_state.cursor
    previous_payload = _cursor_payload(previous)
    limit_value = _new_limit(config, limit)
    lookback_seconds = int(config.new.lookback_seconds)
    first_run = previous is None
    first_run_warnings = (
        [FIRST_RUN_WARNING_TEMPLATE.format(lookback=config.new.lookback)]
        if first_run
        else []
    )

    # Scope warnings of any run come first; W_FIRST_RUN is always last.
    scope_warnings: list[str] = [] if resolved else [NO_ACCOUNTS_WARNING]
    warning_backends = (
        [run.backend for run in runs.values()] if runs else list(pool.values())
    )
    scope_warnings.extend(_activation_warnings(warning_backends, excluded))
    if not resolved or not any(run.allowed_ids for run in runs.values()):
        return _new_result(
            started,
            scope_warnings + first_run_warnings,
            previous_payload,
            previous_payload,
            candidates=0,
            messages_read=0,
        )

    ring: set = set()
    if previous is None:
        newest_date: int | None = None
        for run in runs.values():
            if not run.allowed_ids:
                continue
            newest = _newest_scoped_message(
                run.backend, sorted(run.allowed_ids), now
            )
            if newest is not None and (newest_date is None or newest[0] > newest_date):
                newest_date = int(newest[0])
        if newest_date is None:
            return _new_result(
                started,
                scope_warnings + first_run_warnings,
                None,
                None,
                candidates=0,
                messages_read=0,
            )
        threshold = newest_date - lookback_seconds
    else:
        threshold = int(previous.last_date_received) - lookback_seconds
        ring = set(app_state.emitted_uids)

    opened_before = {driver: _items_opened(run.backend) for driver, run in runs.items()}
    canonical: dict[str, list[dict]] = {}
    candidates = 0
    for driver, run in runs.items():
        ids = sorted(run.allowed_ids)
        rows = run.backend.query(ids, since=threshold, order="asc") if ids else []
        rows = [
            row
            for row in rows
            if _has_valid_date(row, now)
            and _prefixed_uid(run.backend, row["uid"]) not in ring
        ]
        candidates += len(rows)
        run.label_map = run.backend.membership([row["uid"] for row in rows])
        duplicate_counts = run.backend.duplicate_counts(run.allowed_ids)
        canonical[driver] = _dedupe(
            rows, run.mailbox_map, run.label_map, duplicate_counts, run.backend
        )

    merged = _merge_ordered(canonical, _run_backends(runs), descending=False)
    warnings: list[str] = list(scope_warnings)
    truncated = len(merged) > limit_value
    if first_run:
        # --limit keeps the most recent messages of the window.
        page = merged[-limit_value:]
    else:
        page = merged[:limit_value]
    if truncated:
        warnings.append(_truncated_warning(len(merged) - limit_value))

    recipients = _page_recipients(page, runs)
    messages, body_warnings, reads = _build_messages(
        page, runs, recipients, cached_bodies=False
    )
    warnings.extend(body_warnings)
    warnings.extend(first_run_warnings)
    messages_read = 0
    for driver, run in runs.items():
        before = opened_before[driver]
        if before is not None:
            messages_read += _items_opened(run.backend) - before
        else:
            messages_read += reads.get(driver, 0)

    if peek or not page:
        current_payload = previous_payload
    else:
        emitted = [
            EmittedUid(
                date_received=_date_key(row),
                driver=str(row["_mq_driver"]),
                native_order_key=_native_order_key(
                    runs[str(row["_mq_driver"])].backend, row
                ),
                uid=_prefixed_uid(runs[str(row["_mq_driver"])].backend, row["uid"]),
            )
            for row in page
        ]
        new_state = state_store.record_new(
            app_state, emitted, lookback_seconds, command="new"
        )
        state_store.save(new_state)
        current_payload = _cursor_payload(new_state.cursor)

    return {
        "count": len(messages),
        "truncated": truncated,
        "hint": _new_hint(truncated),
        "messages": messages,
        "scan": _scan_dict("metadata", candidates, messages_read, started),
        "cursor": {"previous": previous_payload, "current": current_payload},
        "warnings": warnings,
    }


def run_show(
    backend: "MailBackend | None",
    config: "Config",
    uid: Any,
    *,
    driver: str | None = None,
    drivers: "Mapping[str, MailBackend] | None" = None,
    native: str | None = None,
) -> dict:
    """Return ``{"message", "warnings"}`` for one uid of a declared account.

    The driver of the uid prefix is the one that serves ``show``: the
    core splits the prefix, resolves only that driver's ``[scope]`` blocks and
    calls its ``find_message``/``load_body`` plus the API 1 ``attachments``
    operation (the core composes ``{index, name, cached_path}``; ``show`` never
    writes). A uid in an undeclared account (or with no declared accounts)
    raises ``E_ACCOUNT_NOT_IN_SCOPE``. A uid that does not exist, or is deleted,
    raises ``E_USAGE`` with an actionable hint. A uid whose store is excluded
    (Outlook) raises ``E_ACCOUNT_NOT_IN_SCOPE`` with the reason, declared or not.
    """
    native_name, pool = _driver_pool(backend, drivers, native)
    target = str(driver or (backend is not None and _driver(backend)) or native_name)
    target_backend = pool.get(target)
    if target_backend is None:  # pragma: no cover - the CLI opens the target driver
        raise uid_module.driver_unknown(target)

    target_config = _config_for_driver(config, target, native_name)
    excluded: list[dict] = []
    resolved = _resolved_scope(target_config, target_backend, excluded, native=target)
    accounts = _accounts_by_uuid(target_backend)
    declared = {_scope_account_uuid(scope) for scope in resolved}
    show_uid = uid_module.format_uid(target, str(uid))

    try:
        found = target_backend.find_message(uid)
    except ExcludedStoreError as exc:
        raise _excluded_store_error(show_uid, exc.entry) from None
    # A backend may word the not-found hint itself (Outlook points to excluded_stores).
    not_found_hint = getattr(target_backend, "not_found_hint", None)
    if found is None:
        raise _message_not_found(show_uid, not_found_hint)
    row, mailbox = found
    account_uuid = mailbox["account_uuid"] if mailbox is not None else ""
    if not account_uuid:
        raise _message_not_found(show_uid, not_found_hint)
    if account_uuid not in declared:
        raise MailqueryError(
            "E_ACCOUNT_NOT_IN_SCOPE",
            f"message uid {show_uid} belongs to account {account_uuid!r}, "
            "which is not declared in config.toml",
            "only accounts declared with a [scope.<account>] block are read; "
            "declare the account in ~/.mailquery/config.toml",
            "the message belongs to an account that is not declared",
        )
    recipients = target_backend.recipients([uid])
    to_list, cc_list = _recipient_lists(recipients, uid)

    body = target_backend.load_body(row)
    warnings = _activation_warnings([target_backend], excluded) + list(body["warnings"])

    body_readable = bool(body["readable"])
    body_text = ""
    body_truncated = False
    if body_readable:
        cleaned = output.sanitize_text(body["body_text"] or "")
        body_truncated = len(cleaned) > output.SHOW_BODY_MAX_CHARS
        body_text = cleaned[: output.SHOW_BODY_MAX_CHARS]
        if body_truncated:
            warnings.append(
                "W_BODY_TRUNCATED: the body was truncated to "
                f"{output.SHOW_BODY_MAX_CHARS} characters"
            )

    attachments = _show_attachments(
        target_backend,
        config,
        show_uid,
        uid,
        target,
        row,
        body,
        body_readable,
        warnings,
    )

    partial = bool(body["partial"])
    headers = _show_headers(body["headers"], row, to_list, cc_list)

    message = {
        "uid": _prefixed_uid(target_backend, row["uid"]),
        "message_id": row.get("message_id") or "",
        "subject": row.get("subject") or "",
        "from": {
            "name": row.get("sender_name") or "",
            "address": row.get("sender_address") or "",
        },
        "to": to_list,
        "cc": cc_list,
        "date_sent": output.iso_timestamp(row.get("date_sent")),
        "date_received": output.iso_timestamp(row.get("date_received")),
        "mailbox": _mailbox_payload(accounts, mailbox),
        "is_read": bool(row.get("read")),
        "is_flagged": bool(row.get("flagged")),
        "has_attachments": bool(row.get("has_attachments")),
        "size_bytes": int(row.get("size") or 0),
        "headers": headers,
        "body_text": body_text,
        "body_truncated": body_truncated,
        "attachments": attachments,
        "partial": partial,
        "readable": body_readable,
        "source": {
            "emlx_path": body["source"]["emlx_path"],
            "partial": bool(body["source"]["partial"]),
        },
    }
    return {"message": message, "warnings": warnings}


def run_mailboxes(
    backend: "MailBackend | None",
    config: "Config",
    *,
    drivers: "Mapping[str, MailBackend] | None" = None,
    native: str | None = None,
) -> dict:
    """Return ``{"accounts", "mailboxes", "excluded_stores", "warnings"}``.

    Drivers are concatenated in the order their ``[scope]`` blocks first appear
    in the config: ``accounts[]`` of each driver (declared
    first, with their ``declared`` flag), then every folder of the driver with
    its counters and ``included`` flag, then its ``excluded_stores[]``. The
    native driver stays out of a command whose config declares only other
    drivers; with no ``[scope]`` blocks at all it is listed with every account
    undeclared (2.0.1 behavior: discovery and ``W_NO_ACCOUNTS``).
    """
    native_name, pool = _driver_pool(backend, drivers, native)
    excluded: list[dict] = []
    resolved = _resolved_scope(config, backend, excluded, drivers=drivers, native=native_name)
    groups = _scopes_by_driver(resolved)
    order = _driver_output_order(config, native_name, groups, pool)

    warnings: list[str] = []
    if not resolved:
        warnings.append(NO_ACCOUNTS_WARNING)
    warnings.extend(_activation_warnings([pool[driver] for driver in order], excluded))

    accounts: list[dict] = []
    mailboxes: list[dict] = []
    excluded_stores: list[dict] = []
    seen_accounts: set[tuple[str, str]] = set()
    for driver in order:
        driver_backend = pool.get(driver)
        if driver_backend is None:  # pragma: no cover - pool holds every driver in order
            continue
        accounts_by_uuid = _accounts_by_uuid(driver_backend)
        backend_mailboxes = list(driver_backend.mailboxes())
        scopes = groups.get(driver, ())
        declared_ids = {_scope_account_uuid(scope) for scope in scopes}
        allowed_ids = {
            mailbox["id"]
            for scope in scopes
            for mailbox in getattr(scope, "mailboxes", ()) or ()
        }
        for scope in scopes:
            uuid = _scope_account_uuid(scope)
            key = (driver, uuid)
            if not uuid or key in seen_accounts:
                continue
            seen_accounts.add(key)
            account = _account_payload(accounts_by_uuid, uuid)
            account["declared"] = True
            accounts.append(account)
        for mailbox in backend_mailboxes:
            uuid = mailbox["account_uuid"]
            key = (driver, str(uuid or ""))
            if not uuid or key in seen_accounts:
                continue
            seen_accounts.add(key)
            account = _account_payload(accounts_by_uuid, uuid)
            account["declared"] = uuid in declared_ids
            accounts.append(account)
        mailboxes.extend(
            {
                "account": _account_payload(accounts_by_uuid, mailbox["account_uuid"]),
                "name": mailbox["name"],
                "path": mailbox["path"],
                "url": mailbox["url"],
                "total": int(mailbox["total"]),
                "unread": int(mailbox["unread"]),
                "included": mailbox["id"] in allowed_ids,
            }
            for mailbox in backend_mailboxes
        )
        excluded_stores.extend(driver_backend.excluded_stores())

    return {
        "accounts": accounts,
        "mailboxes": mailboxes,
        "excluded_stores": excluded_stores,
        "warnings": warnings,
    }


# --------------------------------------------------------------------------- #
# Backend access
# --------------------------------------------------------------------------- #


def _accounts_by_uuid(backend: "MailBackend") -> "dict[str, AccountRow]":
    return {account["uuid"]: account for account in backend.accounts()}


def _mailbox_map(backend: "MailBackend", resolved: Sequence[Any]) -> "dict[Any, MailboxRow]":
    """Folders by ``id``; only the declared accounts' folders are used (scope, dedupe,
    display), so a backend may list only those (Outlook reads no other store)."""
    declared = list(dict.fromkeys(_scope_account_uuid(scope) for scope in resolved))
    return {
        mailbox["id"]: mailbox
        for mailbox in config_module.listed_mailboxes(backend, [uuid for uuid in declared if uuid])
    }


def _has_valid_date(row: dict, now: float) -> bool:
    """``0 < date_received <= now``: null, non-positive and future dates never enter ``new``."""
    value = row.get("date_received")
    return value is not None and 0 < value <= now


def _newest_scoped_message(
    backend: "MailBackend", mailbox_ids: Sequence[Any], now: float
) -> tuple[int, Any] | None:
    """``(date_received, uid)`` of the newest message with a valid date."""
    for row in backend.query(mailbox_ids, order="desc"):
        if _has_valid_date(row, now):
            return int(row["date_received"]), row["uid"]
    return None


# --------------------------------------------------------------------------- #
# Scope resolution
# --------------------------------------------------------------------------- #


def _resolved_scope(
    config: "Config",
    backend: "MailBackend | None",
    excluded: list[dict] | None = None,
    *,
    drivers: "Mapping[str, MailBackend] | None" = None,
    native: str | None = None,
) -> list[Any]:
    """Resolve ``[scope.*]`` accounts through :mod:`mailquery.config`.

    ``excluded`` receives the entry of each declared account that is an
    excluded store (Outlook). ``drivers`` maps the other declared
    backends and ``native`` names the platform driver.

    The catalog handed to :mod:`mailquery.config` uses the wrapped drivers,
    so the ``accounts``/``mailboxes``/``resolve_mailbox`` calls of the scope
    resolution are mapped and bounded too.
    """
    native_name, pool = _driver_pool(backend, drivers, native)
    native_backend = pool.get(native_name)
    other_backends = {
        name: instance for name, instance in pool.items() if name != native_name
    }
    resolved = config_module.resolve_scope(
        config,
        native_backend,
        excluded=excluded,
        drivers=other_backends,
        native=native_name,
    )
    return list(resolved or ())


def _scope_account_uuid(scope: Any) -> str:
    return str(getattr(scope, "account_uuid", "") or "")


def _scope_mailboxes(
    resolved: Sequence[Any], extra: Iterable["MailboxRow"] = ()
) -> tuple["MailboxRow", ...]:
    """Return the resolved mailboxes in order, without duplicates."""
    unique: dict[Any, "MailboxRow"] = {}
    for scope in resolved:
        for mailbox in getattr(scope, "mailboxes", ()) or ():
            unique.setdefault(mailbox["id"], mailbox)
    for mailbox in extra:
        unique.setdefault(mailbox["id"], mailbox)
    return tuple(unique.values())


def _include_entries(
    backend: "MailBackend | None",
    resolved: Sequence[Any],
    references: Sequence[str],
    *,
    drivers: "Mapping[str, MailBackend] | None" = None,
    native: str | None = None,
) -> "tuple[tuple[str, MailboxRow], ...]":
    """Resolve ``--include-mailbox`` refs inside the declared accounts.

    Values may be repeated or comma-separated, and each item is a folder name,
    path or URL as shown by ``mailquery mailboxes``. The result is a sequence of
    ``(driver, mailbox)`` pairs: with more than one driver the same folder id may
    belong to two drivers, so the driver is part of the identity. A folder that
    only exists in an undeclared account raises ``E_ACCOUNT_NOT_IN_SCOPE``; a
    folder that does not exist in any declared account raises
    ``E_MAILBOX_NOT_FOUND``.
    """
    if not references:
        return ()
    _native_name, pool = _driver_pool(backend, drivers, native)
    declared = {
        (str(getattr(scope, "driver", "") or ""), _scope_account_uuid(scope))
        for scope in resolved
    }
    selected: list[tuple[str, MailboxRow]] = []
    seen: set[tuple[str, Any]] = set()
    for raw in references:
        if raw is None:
            continue
        for reference in str(raw).split(","):
            reference = reference.strip()
            if not reference:
                continue
            found = _resolve_reference(pool, resolved, reference)
            if found is not None:
                driver, mailbox = found
                key = (driver, mailbox["id"])
                if key not in seen:
                    seen.add(key)
                    selected.append((driver, mailbox))
                continue
            elsewhere = _find_reference_outside_scope(pool, declared, reference)
            if elsewhere is not None:
                driver, account_uuid = elsewhere
                raise MailqueryError(
                    "E_ACCOUNT_NOT_IN_SCOPE",
                    f"mailbox {reference!r} belongs to account "
                    f"{account_uuid!r}, which is not declared in config.toml",
                    "only accounts declared with a [scope.<account>] block are "
                    "read; declare the account in ~/.mailquery/config.toml or "
                    "drop --include-mailbox",
                    "an included mailbox belongs to an account that is not declared",
                )
            raise _include_mailbox_not_found(pool, resolved, reference)
    return tuple(selected)


def _resolve_include_mailboxes(
    backend: "MailBackend | None",
    resolved: Sequence[Any],
    references: Sequence[str],
    *,
    drivers: "Mapping[str, MailBackend] | None" = None,
    native: str | None = None,
) -> tuple["MailboxRow", ...]:
    """The included mailboxes as rows (compatibility wrapper around ``_include_entries``)."""
    return tuple(
        mailbox
        for _driver, mailbox in _include_entries(
            backend, resolved, references, drivers=drivers, native=native
        )
    )


def _resolve_reference(
    pool: "Mapping[str, MailBackend]", resolved: Sequence[Any], reference: str
) -> "tuple[str, MailboxRow] | None":
    for scope in resolved:
        driver = str(getattr(scope, "driver", "") or "")
        account_uuid = _scope_account_uuid(scope)
        if not account_uuid:
            continue
        backend = pool.get(driver)
        if backend is None:  # pragma: no cover - every resolved driver is opened
            continue
        try:
            mailbox = backend.resolve_mailbox(account_uuid, reference)
        except MailqueryError:
            raise
        except Exception:
            mailbox = None
        if mailbox is not None:
            return driver, mailbox
    return None


def _find_reference_outside_scope(
    pool: "Mapping[str, MailBackend]",
    declared: "set[tuple[str, str]]",
    reference: str,
) -> "tuple[str, str] | None":
    for driver, backend in pool.items():
        driver_declared = {
            account_uuid for scope_driver, account_uuid in declared if scope_driver == driver
        }
        seen: set[str] = set()
        for mailbox in config_module.listed_mailboxes(backend):
            account_uuid = mailbox["account_uuid"]
            if not account_uuid or account_uuid in driver_declared or account_uuid in seen:
                continue
            seen.add(account_uuid)
            try:
                candidate = backend.resolve_mailbox(account_uuid, reference)
            except MailqueryError:
                raise
            except Exception:
                candidate = None
            if candidate is not None:
                return driver, account_uuid
    return None


def _include_mailbox_not_found(
    pool: "Mapping[str, MailBackend]", resolved: Sequence[Any], reference: str
) -> MailqueryError:
    """``E_MAILBOX_NOT_FOUND`` with the folders of every declared account.

    The single-driver hint keeps the 2.0.1 wording (the config helper); with
    several drivers each declared account is prefixed with its driver.
    """
    drivers = list(
        dict.fromkeys(str(getattr(scope, "driver", "") or "") for scope in resolved)
    )
    if len(drivers) == 1:
        ordered = dict.fromkeys(_scope_account_uuid(scope) for scope in resolved)
        return config_module.include_mailbox_not_found(
            reference, [uuid for uuid in ordered if uuid], pool[drivers[0]]
        )
    parts: list[str] = []
    for driver in drivers:
        backend = pool[driver]
        accounts = _accounts_by_uuid(backend)
        backend_mailboxes = config_module.listed_mailboxes(backend)
        for scope in resolved:
            if str(getattr(scope, "driver", "") or "") != driver:
                continue
            account_uuid = _scope_account_uuid(scope)
            if not account_uuid:
                continue
            account = accounts.get(account_uuid) or {}
            label = str(account.get("label") or account_uuid)
            folders = sorted(
                {
                    str(mailbox["path"] or mailbox["name"])
                    for mailbox in backend_mailboxes
                    if mailbox["account_uuid"] == account_uuid
                }
            )
            parts.append(f"[{driver}] {label}: {', '.join(folders) or '(no folders)'}")
    return MailqueryError(
        "E_MAILBOX_NOT_FOUND",
        f"mailbox {reference!r} was not found in the declared accounts",
        f"valid folders: {'; '.join(parts)}; run `mailquery mailboxes` to list "
        "names, paths and URLs",
        "an included mailbox was not found in the declared accounts",
    )


def _recipients_open_items(backend: "MailBackend") -> bool:
    """Whether evaluating ``--to``/``--cc`` opens every item (Outlook)."""
    return bool(getattr(backend, "recipients_open_items", False))


def _items_opened(backend: "MailBackend") -> int | None:
    """Items the backend opened so far (Outlook), or ``None`` (Apple Mail).

    With it, ``scan.messages_read`` is the number of items opened;
    without it, the bodies read (``_was_read``).
    """
    opened = getattr(backend, "items_opened", None)
    return None if opened is None else int(opened)


def _content_flags(filters: Filters, opens_recipients: bool) -> tuple[str, ...]:
    """Flags that force reading message content: ``--text``, and ``--to``/``--cc``
    where the recipients are read from each item."""
    flags: list[str] = []
    if _filter_terms(filters.text):
        flags.append("--text")
    if opens_recipients:
        if _filter_terms(filters.to):
            flags.append("--to")
        if _filter_terms(filters.cc):
            flags.append("--cc")
    return tuple(flags)


def _flag_names(flags: Sequence[str]) -> str:
    if len(flags) == 1:
        return flags[0]
    return ", ".join(flags[:-1]) + " and " + flags[-1]


def _require_bounded_scan(
    resolved: Sequence[Any],
    include: Sequence["MailboxRow"],
    filters: Filters,
    content_flags: Sequence[str] = ("--text",),
    opens_recipients: bool = False,
) -> None:
    """Reject content-reading queries without a narrowing filter.

    Validated once for every flag in ``content_flags``. Where ``--to``/``--cc``
    open every item they do not narrow, and the error names the flags that
    force reading content and lists only the filters that narrow.
    """
    has_filter = bool(
        filters.since is not None
        or filters.until is not None
        or _filter_terms(filters.subject, split=True)
        or _filter_terms(filters.from_)
        or (
            not opens_recipients
            and (_filter_terms(filters.to) or _filter_terms(filters.cc))
        )
    )
    has_extra_folder = any(
        not mailbox["is_inbox"] for mailbox in _scope_mailboxes(resolved)
    ) or any(not mailbox["is_inbox"] for mailbox in include)
    if has_filter or has_extra_folder:
        return
    if not opens_recipients:
        raise MailqueryError(
            "E_UNBOUNDED_SCAN",
            "--text without a narrowing filter would read every message in the scope",
            "add --since, --until, --from, --to, --cc, --subject or "
            "--include-mailbox (for example: mailquery search --text invoice --since 30d)",
        )
    example = (
        "mailquery search --text invoice --since 30d" if "--text" in content_flags else "--since 30d"
    )
    raise MailqueryError(
        "E_UNBOUNDED_SCAN",
        f"{_flag_names(content_flags)} without a narrowing filter would read every "
        "message in the scope",
        f"add --since, --until, --from, --subject or --include-mailbox (for example: {example})",
    )


def _scan_too_large(
    content_flags: Sequence[str], candidates: int, max_scan: int, opens_recipients: bool
) -> MailqueryError:
    """``E_SCAN_TOO_LARGE``; the hint lists only the filters that narrow."""
    if not opens_recipients:
        return MailqueryError(
            "E_SCAN_TOO_LARGE",
            f"--text would read {candidates} messages, above the configured "
            f"maximum of {max_scan}",
            "narrow the query with --since, --until, --from, --to, --cc or "
            "--subject, or raise [search].max_scan (maximum 50000)",
        )
    return MailqueryError(
        "E_SCAN_TOO_LARGE",
        f"{_flag_names(content_flags)} would read {candidates} messages, above the "
        f"configured maximum of {max_scan}",
        "narrow the query with --since, --until, --from or --subject, or raise "
        "[search].max_scan (maximum 50000)",
    )


def _recipient_lists(
    recipients: dict[Any, dict[str, list[dict]]], uid: Any
) -> tuple[list[dict], list[dict]]:
    bucket = recipients.get(uid, {})
    to_list = [dict(entry) for entry in bucket.get("to", [])]
    cc_list = [dict(entry) for entry in bucket.get("cc", [])]
    return to_list, cc_list


# --------------------------------------------------------------------------- #
# Filtering, scan and dedupe
# --------------------------------------------------------------------------- #


def _apply_pattern_filters(
    rows: list[dict],
    filters: Filters,
    backend: "MailBackend",
    *,
    recipients: bool = True,
) -> list[dict]:
    """Apply the wildcard/substring filters (accent- and case-insensitive).

    Without ``recipients`` the ``--to``/``--cc`` filters are left to the caller.
    """
    if not rows:
        return []
    subject_terms = _filter_terms(filters.subject, split=True)
    from_terms = _filter_terms(filters.from_)
    to_terms = _filter_terms(filters.to) if recipients else ()
    cc_terms = _filter_terms(filters.cc) if recipients else ()

    if subject_terms:
        rows = [
            row
            for row in rows
            if _matches_all_terms(subject_terms, row["subject"])
        ]
    if from_terms:
        rows = [
            row
            for row in rows
            if _terms_match_any(from_terms, [_sender_haystack(row)])
        ]
    if rows and (to_terms or cc_terms):
        rows = _filter_recipients(rows, to_terms, cc_terms, backend)
    return rows


def _filter_recipients(
    rows: list[dict],
    to_terms: Sequence[str],
    cc_terms: Sequence[str],
    backend: "MailBackend",
) -> list[dict]:
    """Keep the rows whose To and Cc match ``to_terms`` and ``cc_terms``."""
    if not rows:
        return []
    recipients = backend.recipients([row["uid"] for row in rows])
    if to_terms:
        rows = [
            row
            for row in rows
            if _terms_match_any(
                to_terms, _recipient_haystacks(recipients, row["uid"], "to")
            )
        ]
    if rows and cc_terms:
        rows = [
            row
            for row in rows
            if _terms_match_any(
                cc_terms, _recipient_haystacks(recipients, row["uid"], "cc")
            )
        ]
    return rows


def _scan_bodies(
    backend: "MailBackend",
    rows: list[dict],
    terms: Sequence[str],
    recipient_terms: tuple[Sequence[str], Sequence[str]] = ((), ()),
) -> tuple[list[dict], list[str], int]:
    """Bounded ``--text`` scan: read the candidate rows in order and match.

    With ``recipient_terms`` (``--to``, ``--cc`` where they open each item),
    each row's recipients are checked first and its body is read only if they
    match, so the item is opened once.
    """
    matched: list[dict] = []
    warnings: list[str] = []
    messages_read = 0
    load = _body_loader(backend)
    for row in rows:
        if any(recipient_terms) and not _filter_recipients([row], *recipient_terms, backend):
            continue
        body = load(row)
        warnings.extend(body["warnings"])
        if _was_read(body):
            messages_read += 1
        if not body["available"] or not body["readable"]:
            continue
        body_text = body["body_text"] or ""
        if not _matches_all_terms(terms, body_text):
            continue
        matched_row = dict(row)
        matched_row["_body_text"] = body_text
        matched_row["_body_partial"] = bool(body["partial"])
        matched.append(matched_row)
    return matched, warnings, messages_read


def _was_read(body: "BodyRow") -> bool:
    """Whether loading the body touched a message (a located file or a read item)."""
    return body["source"]["emlx_path"] is not None or bool(body["available"])


def _dedupe(
    rows: list[dict],
    mailbox_map: dict[Any, "MailboxRow"],
    label_map: dict[Any, set[Any]],
    duplicate_counts: dict[Any, int],
    backend: "MailBackend",
) -> list[dict]:
    """Dedupe by the global message key (INBOX > normal folder > aggregate).

    The canonical copy is chosen by that mailbox priority, and the result
    is returned in the total order ``(date_received DESC, driver
    ASC, native_order_key DESC)``. Messages without a usable
    ``global_message_id`` are unique.
    """
    if not rows:
        return []
    inbox_ids = {rowid for rowid, mailbox in mailbox_map.items() if mailbox["is_inbox"]}
    aggregate_ids = {
        rowid for rowid, mailbox in mailbox_map.items() if mailbox["is_aggregate"]
    }
    groups: dict[tuple[str, Any], list[dict]] = {}
    for row in rows:
        global_id = int(row.get("global_message_id") or 0)
        key = ("global", global_id) if global_id else ("uid", row["uid"])
        groups.setdefault(key, []).append(row)

    canonical: list[dict] = []
    for (kind, _identifier), group in groups.items():
        chosen = dict(
            min(
                group,
                key=lambda row: _dedupe_sort_key(
                    row, inbox_ids, aggregate_ids, label_map, backend
                ),
            )
        )
        if kind == "global":
            global_id = int(chosen.get("global_message_id") or 0)
            chosen["duplicate_count"] = int(
                duplicate_counts.get(global_id, len(group))
            )
        else:
            chosen["duplicate_count"] = 1
        canonical.append(chosen)
    return _ordered(canonical, backend, descending=True)


def _dedupe_sort_key(
    row: dict,
    inbox_ids: set[Any],
    aggregate_ids: set[Any],
    label_map: dict[Any, set[Any]],
    backend: "MailBackend",
) -> tuple[int, int, Any]:
    return (
        _mailbox_priority_for_row(row, inbox_ids, aggregate_ids, label_map),
        _date_key(row),
        _native_order_key(backend, row),
    )


def _mailbox_priority_for_row(
    row: dict,
    inbox_ids: set[Any],
    aggregate_ids: set[Any],
    label_map: dict[Any, set[Any]],
) -> int:
    mailbox_id = row["mailbox_id"]
    if mailbox_id in inbox_ids:
        return 0
    if label_map.get(row["uid"], set()) & inbox_ids:
        return 0
    if mailbox_id in aggregate_ids:
        return 2
    return 1


# --------------------------------------------------------------------------- #
# Message assembly
# --------------------------------------------------------------------------- #


def _build_messages(
    page: Sequence[dict],
    runs: "Mapping[str, _DriverRun]",
    recipients: "Mapping[str, dict[Any, Any]]",
    *,
    cached_bodies: bool,
) -> tuple[list[dict], list[str], "dict[str, int]"]:
    """Build the merged page, reading only the returned page of each driver.

    The body always comes from the message's physical mailbox (a Gmail message
    labelled INBOX is stored under ``[Gmail]/All Mail``), while the reported
    ``mailbox`` is the effective in-scope one (INBOX). ``messages_read`` is
    returned per driver so the caller can combine it with the ``items_opened``
    hook of a driver that opens items instead of bodies (Outlook).
    """
    messages: list[dict] = []
    warnings: list[str] = []
    messages_read: dict[str, int] = {driver: 0 for driver in runs}
    for row in page:
        driver = str(row["_mq_driver"])
        run = runs[driver]
        display_mailbox = _display_mailbox(
            row, run.mailbox_map, run.allowed_ids, run.label_map
        )
        to_list, cc_list = _recipient_lists(recipients.get(driver, {}), row["uid"])
        if cached_bodies and "_body_text" in row:
            snippet, body_fields = _body_from_cached(row)
        else:
            snippet, body_fields, body = _body_fields(run.backend, row)
            warnings.extend(body["warnings"])
            if _was_read(body):
                messages_read[driver] += 1
        messages.append(
            _message_payload(
                run.accounts,
                row,
                display_mailbox,
                to_list,
                cc_list,
                snippet,
                body_fields,
                driver,
            )
        )
    return messages, warnings, messages_read


def _config_for_driver(config: "Config", driver: str, native: str) -> "Config":
    """The config with only the ``[scope]`` blocks of ``driver`` (show dispatch)."""
    scopes = tuple(
        entry for entry in config.scopes if str(entry.driver or native) == driver
    )
    if len(scopes) == len(config.scopes):
        return config
    return dataclasses.replace(config, scopes=scopes)


def _show_attachments(
    backend: "MailBackend",
    config: "Config",
    show_uid: str,
    native_uid: Any,
    driver: str,
    row: dict,
    body: dict,
    body_readable: bool,
    warnings: list[str],
) -> list[dict]:
    """``show.attachments``: one entry per attachment of the message.

    ``{"index", "name", "cached_path"}`` with the original name and the stable
    1..N index of the driver. ``cached_path`` is computed with the cache helper
    from the sanitized name and is ``null`` when the name is not safe or the
    cached entry is not a regular file; ``show`` never creates, opens or reads
    a cache entry. A driver with ``attachments: "none"`` returns ``[]``.

    The API 1 ``attachments(uid)`` operation is the source of truth for every
    driver that implements it. Until then a built-in driver falls back
    to the 2.0.1 sources (MIME names of a readable body, the envelope index for
    an unreadable non-S/MIME body). A driver may signal an S/MIME or unreadable
    message by raising the attachment-protocol error from ``attachments()``:
    ``show`` then returns ``[]`` and keeps only the body
    warning, without ``W_ATTACHMENTS_UNAVAILABLE``.
    """
    capabilities = getattr(backend, "capabilities", None) or {}
    if str(capabilities.get("attachments", "local")) == "none":
        return []
    entries = _driver_attachments(backend, native_uid)
    smime = (not body_readable) and _is_smime_body(body)
    if not body_readable and smime:
        names: list[tuple[int, str]] = []
    elif body_readable:
        names = (
            _metadata_pairs(entries)
            if entries is not None
            else _body_pairs(body)
        )
    else:
        names = _unreadable_names(
            backend, native_uid, row, entries, warnings, driver in _INTERNAL_DRIVERS
        )
    return [
        {
            "index": index,
            "name": name,
            "cached_path": _show_cached_path(config.home, show_uid, index, name),
        }
        for index, name in names
    ]


def _driver_attachments(
    backend: "MailBackend", native_uid: Any
) -> list[Mapping[str, Any]] | None:
    """Metadata rows of the driver, or ``None`` when it only has the 2.0.1 fallback.

    A protocol error from ``attachments()`` (S/MIME/unreadable message) becomes
    an empty list for ``show``: the body warning already explains it.
    """
    try:
        entries = backend.attachments(native_uid)
    except NotImplementedError:
        return None
    except MailqueryError as exc:
        if exc.code == "E_ATTACHMENT_UNREADABLE":
            return []
        raise
    return [entry for entry in (entries or []) if isinstance(entry, Mapping)]


def _metadata_pairs(
    entries: Iterable[Mapping[str, Any]] | None,
) -> list[tuple[int, str]]:
    """Ordered ``(index, original name)`` pairs of the driver metadata rows."""
    pairs = [
        (int(entry.get("index") or position), str(entry.get("name") or ""))
        for position, entry in enumerate(entries or [], start=1)
    ]
    return sorted(pairs, key=lambda pair: pair[0])


def _body_pairs(body: dict) -> list[tuple[int, str]]:
    """``(index, name)`` pairs from the MIME names of a readable body (2.0.1)."""
    return [
        (index, str(entry.get("name") or ""))
        for index, entry in enumerate(body.get("attachments") or (), start=1)
    ]


def _unreadable_names(
    backend: "MailBackend",
    native_uid: Any,
    row: dict,
    entries: Iterable[Mapping[str, Any]] | None,
    warnings: list[str],
    internal: bool,
) -> list[tuple[int, str]]:
    """Attachment names of an unreadable non-S/MIME body."""
    if not internal:
        return _metadata_pairs(entries)
    hook = getattr(backend, "unreadable_attachments", None)
    if callable(hook):
        hook_names, hook_warning = hook(row)
        if hook_warning:
            warnings.append(str(hook_warning))
        if entries is not None:
            return _metadata_pairs(entries)
        return [
            (index, str(name))
            for index, name in enumerate(hook_names or (), start=1)
        ]
    if entries is not None:
        names = _metadata_pairs(entries)
        if names:
            warnings.append(_ATTACHMENTS_UNAVAILABLE_WARNING)
        return names
    stored = [str(name) for name in (backend.attachment_names(native_uid) or ())]
    if stored:
        warnings.append(_ATTACHMENTS_UNAVAILABLE_WARNING)
    return [
        (index, str(name)) for index, name in enumerate(stored, start=1)
    ]


def _is_smime_body(body: dict) -> bool:
    """Whether the 2.0.1 body warnings mark the message as S/MIME."""
    return any(
        "S/MIME" in str(warning) for warning in (body.get("warnings") or ())
    )


def _show_cached_path(
    home: Any, show_uid: str, index: int, name: str
) -> str | None:
    """``cached_path`` of one attachment: safe name plus a regular cache file only."""
    try:
        if classify_name(name).blocked:
            return None
        path = attachment_cached_path(home, show_uid, name, index)
    except (OSError, ValueError):  # pragma: no cover - defensive, no writes happen
        return None
    return None if path is None else str(path)


def _message_payload(
    accounts: "dict[str, AccountRow]",
    row: dict,
    mailbox: "MailboxRow | None",
    to_list: list[dict],
    cc_list: list[dict],
    snippet: str,
    body_fields: dict,
    driver: str,
) -> dict:
    return {
        "uid": uid_module.format_uid(driver, str(row["uid"])),
        "message_id": row.get("message_id") or "",
        "duplicate_count": int(row.get("duplicate_count", 1)),
        "subject": row.get("subject") or "",
        "from": {
            "name": row.get("sender_name") or "",
            "address": row.get("sender_address") or "",
        },
        "to": to_list,
        "cc": cc_list,
        "date_sent": output.iso_timestamp(row.get("date_sent")),
        "date_received": output.iso_timestamp(row.get("date_received")),
        "mailbox": _mailbox_payload(accounts, mailbox),
        "is_read": bool(row.get("read")),
        "is_flagged": bool(row.get("flagged")),
        "has_attachments": bool(row.get("has_attachments")),
        "size_bytes": int(row.get("size") or 0),
        "snippet": snippet,
        "body": body_fields,
    }


def _display_mailbox(
    row: dict,
    mailbox_map: dict[Any, "MailboxRow"],
    allowed_ids: frozenset[Any] | None,
    label_map: dict[Any, set[Any]],
) -> "MailboxRow | None":
    """Pick the mailbox reported for a message.

    A message included through a label (Gmail INBOX lives physically in
    ``[Gmail]/All Mail``) is reported as the in-scope label mailbox (INBOX),
    which is what a search scoped to INBOX should show.
    """
    mailbox_id = row["mailbox_id"]
    direct = mailbox_map.get(mailbox_id)
    if allowed_ids is None or direct is None:
        return direct
    if mailbox_id in allowed_ids:
        return direct
    candidates = [
        mailbox_map[label_id]
        for label_id in label_map.get(row["uid"], set())
        if label_id in allowed_ids and label_id in mailbox_map
    ]
    if candidates:
        return min(candidates, key=_mailbox_priority)
    return direct


def _mailbox_priority(mailbox: "MailboxRow") -> int:
    if mailbox["is_inbox"]:
        return 0
    if mailbox["is_aggregate"]:
        return 2
    return 1


def _mailbox_payload(
    accounts: "dict[str, AccountRow]", mailbox: "MailboxRow | None"
) -> dict:
    if mailbox is None:  # pragma: no cover - defensive, the backend maps every row
        return {
            "account": {"uuid": "", "label": "", "email": None},
            "name": "",
            "path": "",
            "url": "",
        }
    return {
        "account": _account_payload(accounts, mailbox["account_uuid"]),
        "name": mailbox["name"],
        "path": mailbox["path"],
        "url": mailbox["url"],
    }


def _account_payload(accounts: "dict[str, AccountRow]", uuid: str) -> dict:
    account_uuid = str(uuid or "")
    entry = accounts.get(account_uuid) if account_uuid else None
    if entry is not None:
        return {
            "uuid": account_uuid,
            "label": str(entry["label"] or account_uuid),
            "email": entry["email"],
        }
    return {"uuid": account_uuid, "label": account_uuid, "email": None}


def _store_excluded_warning(entry: dict) -> str:
    """``W_STORE_EXCLUDED: <label> at <path> is excluded: <reason>`` (no `` at`` without path)."""
    return f"W_STORE_EXCLUDED: {_store_where(entry)} is excluded: {entry.get('reason')}"


def _store_where(entry: dict) -> str:
    """``<label> at <path>`` of an excluded store, or just ``<label>`` when it has no path."""
    where = str(entry.get("label") or "")
    if entry.get("path"):
        where += f" at {entry['path']}"
    return where


def _labels_warnings(backend: "MailBackend") -> list[str]:
    """``W_ACCOUNT_LABELS_UNAVAILABLE`` for data commands."""
    return [] if backend.labels_available else [LABELS_UNAVAILABLE_WARNING]


# --------------------------------------------------------------------------- #
# Bodies
# --------------------------------------------------------------------------- #


def _body_fields(
    backend: "MailBackend", row: dict
) -> tuple[str, dict, "BodyRow"]:
    """Return ``(snippet, body, loaded)`` for a message."""
    loaded = _body_loader(backend)(row)
    body_text = loaded["body_text"] or ""
    snippet = output.make_snippet(body_text) if body_text else ""
    fields = {
        "available": bool(loaded["available"]),
        "readable": bool(loaded["readable"]),
        "partial": bool(loaded["partial"]),
        "truncated": _snippet_truncated(body_text),
    }
    return snippet, fields, loaded


def _body_loader(backend: "MailBackend") -> Callable[[dict], "BodyRow"]:
    """``load_body``, or the backend's body-only ``load_snippet`` when it has one.

    ``search``/``new`` use only the body; ``show`` always calls ``load_body``
    (attachments and headers).
    """
    loader = getattr(backend, "load_snippet", None)
    return loader if callable(loader) else backend.load_body


def _body_from_cached(row: dict) -> tuple[str, dict]:
    body_text = str(row.get("_body_text") or "")
    snippet = output.make_snippet(body_text) if body_text else ""
    return snippet, {
        "available": True,
        "readable": True,
        "partial": bool(row.get("_body_partial", False)),
        "truncated": _snippet_truncated(body_text),
    }


def _snippet_truncated(body_text: str) -> bool:
    if not body_text:
        return False
    single_line = " ".join(output.sanitize_text(body_text).split())
    return len(single_line) > output.SNIPPET_CHARS


def _show_headers(
    raw_headers: dict, row: dict, to_list: list[dict], cc_list: list[dict]
) -> dict[str, str]:
    sender = _format_address(row.get("sender_name"), row.get("sender_address"))
    to_value = ", ".join(
        _format_address(entry.get("name"), entry.get("address")) for entry in to_list
    )
    cc_value = ", ".join(
        _format_address(entry.get("name"), entry.get("address")) for entry in cc_list
    )
    date_value = output.iso_timestamp(
        row.get("date_sent") or row.get("date_received")
    ) or ""
    return {
        "From": _header_lookup(raw_headers, "From") or sender,
        "To": _header_lookup(raw_headers, "To") or to_value,
        "Cc": _header_lookup(raw_headers, "Cc") or cc_value,
        "Subject": _header_lookup(raw_headers, "Subject") or str(row.get("subject") or ""),
        "Date": _header_lookup(raw_headers, "Date") or date_value,
        "Message-ID": _header_lookup(raw_headers, "Message-ID")
        or str(row.get("message_id") or ""),
    }


def _header_lookup(headers: dict, name: str) -> str:
    wanted = name.lower()
    for key, value in headers.items():
        if str(key).strip().lower() == wanted:
            if value is None:
                return ""
            return str(value)
    return ""


def _format_address(name: str | None, address: str | None) -> str:
    clean_name = str(name or "").strip()
    clean_address = str(address or "").strip()
    if clean_name and clean_address:
        return f"{clean_name} <{clean_address}>"
    return clean_address or clean_name


# --------------------------------------------------------------------------- #
# ``new`` helpers
# --------------------------------------------------------------------------- #


def _new_result(
    started: float,
    warnings: Sequence[str],
    previous_payload: dict | None,
    current_payload: dict | None,
    *,
    candidates: int,
    messages_read: int,
) -> dict:
    return {
        "count": 0,
        "truncated": False,
        "hint": None,
        "messages": [],
        "scan": _scan_dict("metadata", candidates, messages_read, started),
        "cursor": {"previous": previous_payload, "current": current_payload},
        "warnings": list(warnings),
    }


def _cursor_payload(cursor: Cursor | None) -> dict | None:
    if cursor is None:
        return None
    return {
        "last_date_received": int(cursor.last_date_received),
        "last_uid": cursor.last_uid,
        "lookback_seconds": int(cursor.lookback_seconds),
    }


# --------------------------------------------------------------------------- #
# Limits, patterns and small utilities
# --------------------------------------------------------------------------- #


def _search_limit(config: "Config", limit: int | None) -> int:
    raw = limit if limit is not None else getattr(config.search, "default_limit", 20)
    return _bounded_limit(raw, SEARCH_MAX_LIMIT, 20)


def _new_limit(config: "Config", limit: int | None) -> int:
    raw = limit if limit is not None else getattr(config.new, "default_limit", 100)
    return _bounded_limit(raw, NEW_MAX_LIMIT, 100)


def _bounded_limit(raw: Any, maximum: int, fallback: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = fallback
    return max(1, min(value, maximum))


def _effective_max_scan(config: "Config") -> int:
    try:
        value = int(getattr(config.search, "max_scan", 5000))
    except (TypeError, ValueError):  # pragma: no cover - validated by config
        return 5000
    return max(1, min(value, MAX_SCAN_HARD_LIMIT))


def _filter_terms(values: Iterable[str], *, split: bool = False) -> tuple[str, ...]:
    """Expand filter values into AND terms.

    With ``split`` (``--subject``) every value is split on whitespace and each
    word is an AND term, with or without wildcards. Without it (``--text``,
    ``--from``, ``--to``, ``--cc``) the whole value is one pattern. Repeated
    CLI flags are ANDed too because every value contributes terms; an empty
    value contributes none.
    """
    terms: list[str] = []
    for value in values or ():
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        if split:
            terms.extend(part for part in text.split() if part)
        else:
            terms.append(text)
    return tuple(terms)


def _matches_all_terms(terms: Sequence[str], text: str) -> bool:
    return all(matches(term, text) for term in terms)


def _terms_match_any(terms: Sequence[str], texts: Sequence[str]) -> bool:
    pool = [text for text in texts if text is not None]
    if not pool:
        return False
    return all(any(matches(term, text) for text in pool) for term in terms)


def _sender_haystack(row: dict) -> str:
    return _format_address(row.get("sender_name"), row.get("sender_address"))


def _recipient_haystacks(
    recipients: dict[Any, dict[str, list[dict]]], uid: Any, kind: str
) -> list[str]:
    bucket = recipients.get(uid, {})
    return [
        _format_address(entry.get("name"), entry.get("address"))
        for entry in bucket.get(kind, [])
    ]


def _date_key(row: dict) -> int:
    value = row.get("date_received")
    return int(value) if value is not None else 0


def _driver(backend: "MailBackend") -> str:
    """Driver name of a backend (``driver`` in protocol v1)."""
    return str(getattr(backend, "driver", "") or "")


def _prefixed_uid(backend: "MailBackend", uid: Any) -> str:
    """``"<driver>:<native_id>"`` of a native uid.

    The core is the only place that builds the emitted uid; the adapters keep
    exchanging their native uid (``int`` on Apple Mail, upper-case hex on Outlook).
    """
    try:
        return uid_module.format_uid(_driver(backend), str(uid))
    except MailqueryError:  # pragma: no cover - adapters always emit valid native ids
        return str(uid)


def _native_order_key(backend: "MailBackend", row: dict) -> int | str:
    """Typed native order key of a row.

    The driver reports ``native_order_key`` as a string; the core compares it as
    an integer when the capability ``native_order`` is ``numeric`` (Apple Mail)
    and as text otherwise (Outlook and plugins). The uid is never compared as text.
    """
    raw = str(row.get("native_order_key", ""))
    if str(getattr(backend, "native_order", "text")) == "numeric":
        try:
            return int(raw)
        except (TypeError, ValueError):  # pragma: no cover - the contract fixes the shape
            return 0
    return raw


def _ordered(
    rows: Sequence[dict], backend: "MailBackend", *, descending: bool
) -> list[dict]:
    """Sort rows in the driver's total order.

    ``descending`` is ``search``/``show`` (``date DESC, driver ASC, key DESC``);
    ``ascending`` is ``new`` (``date ASC, driver ASC, key ASC``). Three stable
    sorts keep the two directions without needing an invertible text key.
    """
    ordered = list(rows)
    ordered.sort(key=lambda row: _native_order_key(backend, row), reverse=descending)
    driver = _driver(backend)
    ordered.sort(key=lambda _row: driver)
    ordered.sort(key=_date_key, reverse=descending)
    return ordered


def _fold(text: str) -> str:
    """Normalize text for accent- and case-insensitive matching."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    without_marks = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return without_marks.casefold()


def _local_midnight(reference: datetime) -> datetime:
    return reference.replace(hour=0, minute=0, second=0, microsecond=0)


def _parse_iso_datetime(text: str) -> datetime | None:
    candidate = text.strip()
    if not candidate:
        return None
    if candidate.endswith(("Z", "z")):
        candidate = candidate[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(candidate)
    except ValueError:
        return None


def _scan_dict(
    mode: str, candidates: int, messages_read: int, started: float
) -> dict:
    return {
        "mode": mode,
        "candidates": int(candidates),
        "messages_read": int(messages_read),
        "duration_ms": int(round((time.perf_counter() - started) * 1000)),
    }


def _empty_search_result(mode: str, started: float, warnings: Sequence[str]) -> dict:
    return {
        "count": 0,
        "truncated": False,
        "hint": None,
        "messages": [],
        "scan": _scan_dict(mode, 0, 0, started),
        "warnings": list(warnings),
    }


def _truncated_warning(remaining: int) -> str:
    return (
        f"W_RESULTS_TRUNCATED: {remaining} more messages match; refine the "
        "filters or raise --limit"
    )


def _search_hint(truncated: bool) -> str | None:
    if not truncated:
        return None
    return f"refine the filters or raise --limit (max {SEARCH_MAX_LIMIT})"


def _new_hint(truncated: bool) -> str | None:
    if not truncated:
        return None
    return f"raise --limit (max {NEW_MAX_LIMIT}) or process the mail across several runs"


def _bad_time(value: Any) -> MailqueryError:
    from mailquery.errors import bad_time

    return bad_time("" if value is None else value)


def _excluded_store_error(uid: Any, entry: dict) -> MailqueryError:
    """``E_ACCOUNT_NOT_IN_SCOPE`` for a uid of an excluded store."""
    where = _store_where(entry)
    return MailqueryError(
        "E_ACCOUNT_NOT_IN_SCOPE",
        f"message uid {uid} belongs to {where}, which is excluded: {entry.get('reason')}",
        "excluded stores are never read; see excluded_stores in `mailquery mailboxes` "
        "for the reason",
        f"the message belongs to an excluded store: {entry.get('reason')}",
    )


def _message_not_found(uid: Any, hint: str | None = None) -> MailqueryError:
    """``E_USAGE`` for a uid ``show`` cannot find; ``hint`` overrides the Apple Mail one."""
    from mailquery.errors import usage_error

    return usage_error(
        f"message uid {uid!r} was not found",
        hint
        or "run `mailquery search` to find the uid; deleted messages and orphan "
        ".emlx files are not shown",
        "message uid was not found",
    )



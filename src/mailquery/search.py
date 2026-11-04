"""Search, new-mail, show and mailboxes queries (PRD 9.3, 9.4, 12).

Applies the configured scope (declared accounts only,
INBOX always included), deduplicates by ``global_message_id`` with INBOX
priority, bounds content scans (``--text``) and assembles the JSON message
objects. This module renders no JSON: it returns plain dictionaries that the
CLI wraps with ``ok``/``command``/``generated_at``.

Everything backend-specific goes through :class:`mailquery.backends.base.MailBackend`
(PRD 9.3): this module holds no SQL and no COM, never opens a database, a
``.emlx`` file or a mail client on its own, and never writes anything.
"""

from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Callable, Iterable, Sequence

from mailquery import config as config_module
from mailquery import output
from mailquery.backends.base import ExcludedStoreError
from mailquery.errors import MailqueryError
from mailquery.state import Cursor

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mailquery.backends.base import AccountRow, BodyRow, MailBackend, MailboxRow
    from mailquery.config import Config
    from mailquery.state import StateStore

# Limits fixed by the product contract (PRD 15.6).
SEARCH_MAX_LIMIT = 200
NEW_MAX_LIMIT = 500
MAX_SCAN_HARD_LIMIT = 50_000

# Stable warning strings (PRD 12.5 "warnings[]").
NO_ACCOUNTS_WARNING = (
    "W_NO_ACCOUNTS: no accounts are declared in config.toml; nothing is observed"
)
LABELS_UNAVAILABLE_WARNING = (
    "W_ACCOUNT_LABELS_UNAVAILABLE: account labels are unavailable; UUIDs are shown instead"
)
FIRST_RUN_WARNING_TEMPLATE = (
    "W_FIRST_RUN: first run: emitted the messages received in the last "
    "{lookback} before the newest message"
)

# Relative-time parsing (PRD 12.2 / RF-12).
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
# Public commands
# --------------------------------------------------------------------------- #


def run_search(
    backend: "MailBackend",
    config: "Config",
    filters: Filters,
) -> dict:
    """Return ``{"count", "messages", "truncated", "scan", "warnings"}``.

    The scope is the set of accounts declared in ``config.toml`` (INBOX always
    included) plus their ``mailbox_list`` folders and the ``--include-mailbox``
    folders of this run. Metadata filters are applied first, then the optional
    ``--text`` bounded body scan, then dedupe by the global message key and
    pagination.
    """
    started = time.perf_counter()
    accounts = _accounts_by_uuid(backend)
    mailbox_map = _mailbox_map(backend)

    excluded: list[dict] = []
    resolved = _resolved_scope(config, backend, excluded)
    text_terms = _filter_terms(filters.text)
    mode = "text" if text_terms else "metadata"
    scope_warnings = _scope_warnings(backend, excluded)

    include = _resolve_include_mailboxes(backend, resolved, filters.include_mailboxes)
    if not resolved and not include:
        return _empty_search_result(mode, started, [NO_ACCOUNTS_WARNING, *scope_warnings])

    scope_mailboxes = _scope_mailboxes(resolved, include)
    allowed_ids = frozenset(mailbox["id"] for mailbox in scope_mailboxes)
    if not allowed_ids:
        return _empty_search_result(mode, started, scope_warnings)

    if text_terms:
        _require_bounded_scan(resolved, include, filters)

    warnings: list[str] = list(scope_warnings)

    rows = backend.query(
        sorted(allowed_ids),
        since=filters.since,
        until=filters.until,
        unread=filters.unread,
        flagged=filters.flagged,
        has_attachments=filters.has_attachments,
        order="desc",
    )
    rows = _apply_pattern_filters(rows, filters, backend)
    candidates = len(rows)
    messages_read = 0

    if text_terms:
        max_scan = _effective_max_scan(config)
        if candidates > max_scan:
            raise MailqueryError(
                "E_SCAN_TOO_LARGE",
                f"--text would read {candidates} messages, above the configured "
                f"maximum of {max_scan}",
                "narrow the query with --since, --until, --from, --to, --cc or "
                "--subject, or raise [search].max_scan (maximum 50000)",
            )
        rows, scan_warnings, messages_read = _scan_bodies(backend, rows, text_terms)
        warnings.extend(scan_warnings)

    label_map = backend.membership([row["uid"] for row in rows])
    duplicate_counts = backend.duplicate_counts(allowed_ids)
    canonical = _dedupe(rows, mailbox_map, label_map, duplicate_counts)

    limit = _search_limit(config, filters.limit)
    page = canonical[:limit]
    truncated = len(canonical) > limit
    if truncated:
        warnings.append(_truncated_warning(len(canonical) - limit))

    recipients = backend.recipients([row["uid"] for row in page])
    messages, body_warnings, page_reads = _build_messages(
        backend,
        accounts,
        page,
        mailbox_map,
        allowed_ids,
        label_map,
        recipients,
        cached_bodies=bool(text_terms),
    )
    warnings.extend(body_warnings)
    messages_read += page_reads

    return {
        "count": len(messages),
        "truncated": truncated,
        "hint": _search_hint(truncated),
        "messages": messages,
        "scan": _scan_dict(mode, candidates, messages_read, started),
        "warnings": warnings,
    }


def run_new(
    backend: "MailBackend",
    config: "Config",
    state_store: "StateStore",
    *,
    peek: bool = False,
    limit: int | None = None,
    clock: Callable[[], float] | None = None,
) -> dict:
    """Return ``{"count", "messages", "truncated", "scan", "cursor", "warnings"}``.

    Messages with a null, non-positive or future ``date_received`` (relative to
    ``clock``, Unix seconds, ``time.time`` by default) never enter ``new`` and
    never move the cursor (PRD 12.3, 17).

    The first run (no persisted cursor) emits, in ascending order, the messages
    received in ``[D - lookback, D]`` (``D`` = date of the newest valid message
    of the scope), keeps the newest ``limit`` of them and reports
    ``W_FIRST_RUN`` last. Later runs emit, in arrival order, the messages
    received since ``cursor - lookback`` that are not in the ring. Both use the
    ``[new].lookback`` of the current config, advance the cursor to the last
    emitted message and append the emitted uids to the ring. ``peek`` never
    writes state.
    """
    started = time.perf_counter()
    now = float(clock()) if clock is not None else time.time()
    accounts = _accounts_by_uuid(backend)
    mailbox_map = _mailbox_map(backend)

    excluded: list[dict] = []
    resolved = _resolved_scope(config, backend, excluded)
    scope_mailboxes = _scope_mailboxes(resolved)
    allowed_ids = frozenset(mailbox["id"] for mailbox in scope_mailboxes)

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
    scope_warnings.extend(_scope_warnings(backend, excluded))
    if not resolved or not allowed_ids:
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
        newest = _newest_scoped_message(backend, sorted(allowed_ids), now)
        if newest is None:
            return _new_result(
                started,
                scope_warnings + first_run_warnings,
                None,
                None,
                candidates=0,
                messages_read=0,
            )
        threshold = int(newest[0]) - lookback_seconds
    else:
        threshold = int(previous.last_date_received) - lookback_seconds
        ring = set(app_state.emitted_uids)

    rows = backend.query(sorted(allowed_ids), since=threshold, order="asc")
    rows = [
        row
        for row in rows
        if _has_valid_date(row, now) and row["uid"] not in ring
    ]
    candidates = len(rows)

    label_map = backend.membership([row["uid"] for row in rows])
    duplicate_counts = backend.duplicate_counts(allowed_ids)
    canonical = _dedupe(rows, mailbox_map, label_map, duplicate_counts)
    canonical.sort(key=lambda row: (_date_key(row), row["uid"]))

    warnings: list[str] = list(scope_warnings)
    truncated = len(canonical) > limit_value
    if first_run:
        # --limit keeps the most recent messages of the window (PRD 12.3).
        page = canonical[-limit_value:]
    else:
        page = canonical[:limit_value]
    if truncated:
        warnings.append(_truncated_warning(len(canonical) - limit_value))

    recipients = backend.recipients([row["uid"] for row in page])
    messages, body_warnings, page_reads = _build_messages(
        backend,
        accounts,
        page,
        mailbox_map,
        allowed_ids,
        label_map,
        recipients,
        cached_bodies=False,
    )
    warnings.extend(body_warnings)
    warnings.extend(first_run_warnings)

    if peek or not page:
        current_payload = previous_payload
    else:
        emitted = [(_date_key(row), row["uid"]) for row in page]
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
        "scan": _scan_dict("metadata", candidates, page_reads, started),
        "cursor": {"previous": previous_payload, "current": current_payload},
        "warnings": warnings,
    }


def run_show(backend: "MailBackend", config: "Config", uid: Any) -> dict:
    """Return ``{"message", "warnings"}`` for one uid of a declared account.

    ``[scope]`` is resolved exactly as ``search`` does, so a block or a
    ``mailbox_list`` folder that does not resolve fails with the same error.
    The message may be in any folder of a declared account (PRD 12.4); a uid in
    an undeclared account (or with no declared accounts) raises
    ``E_ACCOUNT_NOT_IN_SCOPE``. A uid that does not exist, or is deleted,
    raises ``E_USAGE`` with an actionable hint, as PRD 12 has no specific
    "message not found" code. A uid whose store is excluded (Outlook) raises
    ``E_ACCOUNT_NOT_IN_SCOPE`` with the reason, declared or not.
    """
    accounts = _accounts_by_uuid(backend)

    excluded: list[dict] = []
    resolved = _resolved_scope(config, backend, excluded)
    declared = {_scope_account_uuid(scope) for scope in resolved}

    try:
        found = backend.find_message(uid)
    except ExcludedStoreError as exc:
        raise _excluded_store_error(uid, exc.entry) from None
    # A backend may word the not-found hint itself (Outlook points to excluded_stores).
    not_found_hint = getattr(backend, "not_found_hint", None)
    if found is None:
        raise _message_not_found(uid, not_found_hint)
    row, mailbox = found
    account_uuid = mailbox["account_uuid"] if mailbox is not None else ""
    if not account_uuid:
        raise _message_not_found(uid, not_found_hint)
    if account_uuid not in declared:
        raise MailqueryError(
            "E_ACCOUNT_NOT_IN_SCOPE",
            f"message uid {uid} belongs to account {account_uuid!r}, "
            "which is not declared in config.toml",
            "only accounts declared with a [scope.<account>] block are read; "
            "declare the account in ~/.mailquery/config.toml",
            "the message belongs to an account that is not declared",
        )
    recipients = backend.recipients([uid])
    to_list, cc_list = _recipient_lists(recipients, uid)

    body = backend.load_body(row)
    warnings = _scope_warnings(backend, excluded) + list(body["warnings"])

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

    # An unreadable body (S/MIME included) never contributes MIME attachment
    # names: they come from the backend's metadata (PRD 12.10).
    attachment_names = (
        [str(entry["name"]) for entry in body["attachments"]] if body_readable else []
    )
    # Outlook cannot read the names without the item: its hook applies the
    # Windows rule of PRD 12.10 (``has_attachments``, S/MIME excepted).
    unreadable_attachments = (
        None if body_readable else getattr(backend, "unreadable_attachments", None)
    )
    if unreadable_attachments is not None:
        attachment_names, attachments_warning = unreadable_attachments(row)
        if attachments_warning:
            warnings.append(attachments_warning)
    elif not attachment_names:
        stored_names = backend.attachment_names(uid)
        if stored_names:
            attachment_names = stored_names
            if not body_readable:
                warnings.append(
                    "W_ATTACHMENTS_UNAVAILABLE: attachment names come from the "
                    "envelope index; the message body could not be read"
                )

    partial = bool(body["partial"])
    headers = _show_headers(body["headers"], row, to_list, cc_list)

    message = {
        "uid": row["uid"],
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
        "attachments": [{"name": str(name)} for name in attachment_names],
        "partial": partial,
        "readable": body_readable,
        "source": {
            "emlx_path": body["source"]["emlx_path"],
            "partial": bool(body["source"]["partial"]),
        },
    }
    return {"message": message, "warnings": warnings}


def run_mailboxes(backend: "MailBackend", config: "Config") -> dict:
    """Return ``{"accounts", "mailboxes", "excluded_stores", "warnings"}``.

    ``accounts[]`` lists the accounts of the backend with their resolved
    labels and a ``declared`` flag; ``mailboxes[]`` lists every folder with the
    counters the backend computed and an ``included`` flag (declared account +
    INBOX + configured ``mailbox_list`` folders).
    """
    accounts_by_uuid = _accounts_by_uuid(backend)
    backend_mailboxes = list(backend.mailboxes())
    excluded: list[dict] = []
    resolved = _resolved_scope(config, backend, excluded)
    scope_mailboxes = _scope_mailboxes(resolved)
    allowed_ids = {mailbox["id"] for mailbox in scope_mailboxes}
    declared_ids = {_scope_account_uuid(scope) for scope in resolved}

    warnings: list[str] = []
    if not resolved:
        warnings.append(NO_ACCOUNTS_WARNING)
    warnings.extend(_scope_warnings(backend, excluded))

    accounts: list[dict] = []
    seen_accounts: set[str] = set()
    for scope in resolved:
        uuid = _scope_account_uuid(scope)
        if not uuid or uuid in seen_accounts:
            continue
        seen_accounts.add(uuid)
        account = _account_payload(accounts_by_uuid, uuid)
        account["declared"] = True
        accounts.append(account)
    for mailbox in backend_mailboxes:
        uuid = mailbox["account_uuid"]
        if not uuid or uuid in seen_accounts:
            continue
        seen_accounts.add(uuid)
        account = _account_payload(accounts_by_uuid, uuid)
        account["declared"] = uuid in declared_ids
        accounts.append(account)

    mailboxes = [
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
    ]
    return {
        "accounts": accounts,
        "mailboxes": mailboxes,
        "excluded_stores": list(backend.excluded_stores()),
        "warnings": warnings,
    }


# --------------------------------------------------------------------------- #
# Backend access
# --------------------------------------------------------------------------- #


def _accounts_by_uuid(backend: "MailBackend") -> "dict[str, AccountRow]":
    return {account["uuid"]: account for account in backend.accounts()}


def _mailbox_map(backend: "MailBackend") -> "dict[Any, MailboxRow]":
    return {mailbox["id"]: mailbox for mailbox in config_module.listed_mailboxes(backend)}


def _has_valid_date(row: dict, now: float) -> bool:
    """``0 < date_received <= now``: null, non-positive and future dates never enter ``new``."""
    value = row.get("date_received")
    return value is not None and 0 < value <= now


def _newest_scoped_message(
    backend: "MailBackend", mailbox_ids: Sequence[Any], now: float
) -> tuple[int, Any] | None:
    """``(date_received, uid)`` of the newest message with a valid date (PRD 12.3)."""
    for row in backend.query(mailbox_ids, order="desc"):
        if _has_valid_date(row, now):
            return int(row["date_received"]), row["uid"]
    return None


# --------------------------------------------------------------------------- #
# Scope resolution
# --------------------------------------------------------------------------- #


def _resolved_scope(
    config: "Config", backend: "MailBackend", excluded: list[dict] | None = None
) -> list[Any]:
    """Resolve ``[scope.*]`` accounts through :mod:`mailquery.config`.

    ``excluded`` receives the entry of each declared account that is an
    excluded store (Outlook, PRD 15.3).
    """
    resolved = config_module.resolve_scope(config, backend, excluded=excluded)
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


def _resolve_include_mailboxes(
    backend: "MailBackend",
    resolved: Sequence[Any],
    references: Sequence[str],
) -> tuple["MailboxRow", ...]:
    """Resolve ``--include-mailbox`` refs inside the declared accounts.

    Values may be repeated or comma-separated, and each item is a folder name,
    path or URL as shown by ``mailquery mailboxes``. A folder that only exists
    in an undeclared account raises ``E_ACCOUNT_NOT_IN_SCOPE``; a folder that
    does not exist in any declared account raises ``E_MAILBOX_NOT_FOUND``.
    """
    if not references:
        return ()
    declared = {_scope_account_uuid(scope) for scope in resolved}
    selected: list["MailboxRow"] = []
    seen: set[Any] = set()
    for raw in references:
        if raw is None:
            continue
        for reference in str(raw).split(","):
            reference = reference.strip()
            if not reference:
                continue
            mailbox = _resolve_reference(backend, resolved, reference)
            if mailbox is not None:
                if mailbox["id"] not in seen:
                    seen.add(mailbox["id"])
                    selected.append(mailbox)
                continue
            elsewhere = _find_reference_outside_scope(backend, declared, reference)
            if elsewhere is not None:
                raise MailqueryError(
                    "E_ACCOUNT_NOT_IN_SCOPE",
                    f"mailbox {reference!r} belongs to account "
                    f"{elsewhere['account_uuid']!r}, which is not declared in config.toml",
                    "only accounts declared with a [scope.<account>] block are "
                    "read; declare the account in ~/.mailquery/config.toml or "
                    "drop --include-mailbox",
                    "an included mailbox belongs to an account that is not declared",
                )
            # The hint lists the folders of all declared accounts, in block order.
            ordered = dict.fromkeys(_scope_account_uuid(scope) for scope in resolved)
            raise config_module.include_mailbox_not_found(
                reference, [uuid for uuid in ordered if uuid], backend
            )
    return tuple(selected)


def _resolve_reference(
    backend: "MailBackend", resolved: Sequence[Any], reference: str
) -> "MailboxRow | None":
    for scope in resolved:
        account_uuid = _scope_account_uuid(scope)
        if not account_uuid:
            continue
        try:
            mailbox = backend.resolve_mailbox(account_uuid, reference)
        except MailqueryError:
            raise
        except Exception:
            mailbox = None
        if mailbox is not None:
            return mailbox
    return None


def _find_reference_outside_scope(
    backend: "MailBackend", declared: set[str], reference: str
) -> "MailboxRow | None":
    seen: set[str] = set()
    for mailbox in config_module.listed_mailboxes(backend):
        account_uuid = mailbox["account_uuid"]
        if not account_uuid or account_uuid in declared or account_uuid in seen:
            continue
        seen.add(account_uuid)
        try:
            candidate = backend.resolve_mailbox(account_uuid, reference)
        except MailqueryError:
            raise
        except Exception:
            candidate = None
        if candidate is not None:
            return candidate
    return None


def _require_bounded_scan(
    resolved: Sequence[Any], include: Sequence["MailboxRow"], filters: Filters
) -> None:
    """Reject ``--text`` queries without a narrowing filter (RF-17)."""
    has_filter = bool(
        filters.since is not None
        or filters.until is not None
        or _filter_terms(filters.subject, split=True)
        or _filter_terms(filters.from_)
        or _filter_terms(filters.to)
        or _filter_terms(filters.cc)
    )
    has_extra_folder = any(
        not mailbox["is_inbox"] for mailbox in _scope_mailboxes(resolved)
    ) or any(not mailbox["is_inbox"] for mailbox in include)
    if has_filter or has_extra_folder:
        return
    raise MailqueryError(
        "E_UNBOUNDED_SCAN",
        "--text without a narrowing filter would read every message in the scope",
        "add --since, --until, --from, --to, --cc, --subject or "
        "--include-mailbox (for example: mailquery search --text invoice --since 30d)",
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
) -> list[dict]:
    """Apply the wildcard/substring filters (accent- and case-insensitive)."""
    if not rows:
        return []
    subject_terms = _filter_terms(filters.subject, split=True)
    from_terms = _filter_terms(filters.from_)
    to_terms = _filter_terms(filters.to)
    cc_terms = _filter_terms(filters.cc)

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
) -> tuple[list[dict], list[str], int]:
    """Bounded ``--text`` scan: read the candidate rows in order and match."""
    matched: list[dict] = []
    warnings: list[str] = []
    messages_read = 0
    for row in rows:
        body = backend.load_body(row)
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
) -> list[dict]:
    """Dedupe by the global message key (INBOX > normal folder > aggregate).

    The canonical copy is chosen with the PRD Anexo B ordering, and the result
    is returned in the documented total order ``(date_received DESC, ROWID
    DESC)``. Messages without a usable ``global_message_id`` are unique.
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
        chosen = dict(min(group, key=lambda row: _dedupe_sort_key(row, inbox_ids, aggregate_ids, label_map)))
        if kind == "global":
            global_id = int(chosen.get("global_message_id") or 0)
            chosen["duplicate_count"] = int(
                duplicate_counts.get(global_id, len(group))
            )
        else:
            chosen["duplicate_count"] = 1
        canonical.append(chosen)
    canonical.sort(key=lambda row: (_date_key(row), row["uid"]), reverse=True)
    return canonical


def _dedupe_sort_key(
    row: dict,
    inbox_ids: set[Any],
    aggregate_ids: set[Any],
    label_map: dict[Any, set[Any]],
) -> tuple[int, int, Any]:
    return (
        _mailbox_priority_for_row(row, inbox_ids, aggregate_ids, label_map),
        _date_key(row),
        row["uid"],
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
    backend: "MailBackend",
    accounts: "dict[str, AccountRow]",
    page: Sequence[dict],
    mailbox_map: dict[Any, "MailboxRow"],
    allowed_ids: frozenset[Any],
    label_map: dict[Any, set[Any]],
    recipients: dict[Any, dict[str, list[dict]]],
    *,
    cached_bodies: bool,
) -> tuple[list[dict], list[str], int]:
    """Build the page message objects, reading only the returned page.

    The body always comes from the message's physical mailbox (a Gmail message
    labelled INBOX is stored under ``[Gmail]/All Mail``), while the reported
    ``mailbox`` is the effective in-scope one (INBOX).
    """
    messages: list[dict] = []
    warnings: list[str] = []
    messages_read = 0
    for row in page:
        display_mailbox = _display_mailbox(row, mailbox_map, allowed_ids, label_map)
        to_list, cc_list = _recipient_lists(recipients, row["uid"])
        if cached_bodies and "_body_text" in row:
            snippet, body_fields = _body_from_cached(row)
        else:
            snippet, body_fields, body = _body_fields(backend, row)
            warnings.extend(body["warnings"])
            if _was_read(body):
                messages_read += 1
        messages.append(
            _message_payload(
                accounts, row, display_mailbox, to_list, cc_list, snippet, body_fields
            )
        )
    return messages, warnings, messages_read


def _message_payload(
    accounts: "dict[str, AccountRow]",
    row: dict,
    mailbox: "MailboxRow | None",
    to_list: list[dict],
    cc_list: list[dict],
    snippet: str,
    body_fields: dict,
) -> dict:
    return {
        "uid": row["uid"],
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


def _scope_warnings(backend: "MailBackend", excluded: Sequence[dict]) -> list[str]:
    """Scope warnings after ``W_NO_ACCOUNTS`` (PRD 12.3 step 6).

    ``W_STORE_EXCLUDED`` for each declared account that is an excluded store
    (PRD 15.3), then ``W_ACCOUNT_LABELS_UNAVAILABLE`` (Annex A.5.2).
    """
    return [_store_excluded_warning(entry) for entry in excluded] + _labels_warnings(backend)


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
    """``W_ACCOUNT_LABELS_UNAVAILABLE`` for data commands (Annex A.5.2)."""
    return [] if backend.labels_available else [LABELS_UNAVAILABLE_WARNING]


# --------------------------------------------------------------------------- #
# Bodies
# --------------------------------------------------------------------------- #


def _body_fields(
    backend: "MailBackend", row: dict
) -> tuple[str, dict, "BodyRow"]:
    """Return ``(snippet, body, loaded)`` for a message."""
    loaded = backend.load_body(row)
    body_text = loaded["body_text"] or ""
    snippet = output.make_snippet(body_text) if body_text else ""
    fields = {
        "available": bool(loaded["available"]),
        "readable": bool(loaded["readable"]),
        "partial": bool(loaded["partial"]),
        "truncated": _snippet_truncated(body_text),
    }
    return snippet, fields, loaded


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
    """Expand filter values into AND terms (PRD 12.2).

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
    """``E_ACCOUNT_NOT_IN_SCOPE`` for a uid of an excluded store (PRD 12.4)."""
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



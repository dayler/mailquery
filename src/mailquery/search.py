"""Search, new-mail, show and mailboxes queries (PRD 9.3, 9.4, 12).

Builds the SQL filters, applies the configured scope (declared accounts only,
INBOX always included), deduplicates by ``global_message_id`` with INBOX
priority, bounds content scans (``--text``) and assembles the JSON message
objects. This module renders no JSON: it returns plain dictionaries that the
CLI wraps with ``ok``/``command``/``generated_at``.

The ``Envelope Index`` is only ever queried through the read-only connection
that :class:`mailquery.store.EnvelopeStore` already opened; this module never
opens a database or a ``.emlx`` file on its own and never writes anything.
"""

from __future__ import annotations

import re
import sqlite3
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Iterable, Sequence

from mailquery import config as config_module
from mailquery import emlx, output
from mailquery.errors import MailqueryError
from mailquery.state import MAX_EMITTED_UIDS, AppState, Cursor

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mailquery.accounts import AccountLabels
    from mailquery.config import Config
    from mailquery.state import StateStore
    from mailquery.store import EnvelopeStore, Mailbox

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
FIRST_RUN_WARNING = (
    "W_FIRST_RUN: first run baseline established; no messages were emitted"
)

# Pattern columns used by the feature-detected SELECT; the order is fixed.
_ROW_COLUMNS = (
    "uid",
    "global_message_id",
    "subject",
    "sender_name",
    "sender_address",
    "date_sent",
    "date_received",
    "mailbox_id",
    "read",
    "flagged",
    "size",
    "message_id",
    "has_attachments",
)

_PLACEHOLDER_CHUNK = 500

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
    store: "EnvelopeStore",
    config: "Config",
    labels: "AccountLabels",
    filters: Filters,
) -> dict:
    """Return ``{"count", "messages", "truncated", "scan", "warnings"}``.

    The scope is the set of accounts declared in ``config.toml`` (INBOX always
    included) plus their ``mailbox_list`` folders and the ``--include-mailbox``
    folders of this run. Metadata filters are applied first, then the optional
    ``--text`` bounded body scan, then dedupe by ``global_message_id`` and
    pagination.
    """
    started = time.perf_counter()
    connection = _sql_connection(store)
    tables = _table_names(connection)
    mailbox_map = {mailbox.rowid: mailbox for mailbox in store.mailboxes}

    resolved = _resolved_scope(config, store, labels)
    text_terms = _filter_terms(filters.text)
    mode = "text" if text_terms else "metadata"

    include = _resolve_include_mailboxes(store, resolved, filters.include_mailboxes)
    if not resolved and not include:
        return _empty_search_result(mode, started, [NO_ACCOUNTS_WARNING])

    scope_mailboxes = _scope_mailboxes(resolved, include)
    allowed_ids = frozenset(mailbox.rowid for mailbox in scope_mailboxes)
    if not allowed_ids:
        return _empty_search_result(mode, started, [])

    if text_terms:
        _require_bounded_scan(resolved, include, filters)

    warnings: list[str] = []

    rows = _fetch_rows(
        connection,
        tables,
        sorted(allowed_ids),
        since=filters.since,
        until=filters.until,
        unread=filters.unread,
        flagged=filters.flagged,
        has_attachments=filters.has_attachments,
        order="desc",
    )
    rows = _apply_pattern_filters(rows, filters, connection, tables)
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
        rows, scan_warnings, messages_read = _scan_bodies(
            store, rows, mailbox_map, text_terms
        )
        warnings.extend(scan_warnings)

    label_map = _fetch_label_mailboxes(
        connection, tables, [row["uid"] for row in rows]
    )
    duplicate_counts = _fetch_duplicate_counts(connection, tables, allowed_ids)
    canonical = _dedupe(rows, mailbox_map, label_map, duplicate_counts)

    limit = _search_limit(config, filters.limit)
    page = canonical[:limit]
    truncated = len(canonical) > limit
    if truncated:
        warnings.append(_truncated_warning(len(canonical) - limit))

    recipients = _fetch_recipients(
        connection, tables, [row["uid"] for row in page]
    )
    messages, body_warnings, page_reads = _build_messages(
        store,
        labels,
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
    store: "EnvelopeStore",
    config: "Config",
    labels: "AccountLabels",
    state_store: "StateStore",
    *,
    peek: bool = False,
    limit: int | None = None,
) -> dict:
    """Return ``{"count", "messages", "truncated", "scan", "cursor", "warnings"}``.

    The first run (no persisted cursor) is a baseline: it emits nothing, moves
    the cursor to the newest message of the scope, seeds the emitted-uid ring
    with the lookback window and reports ``W_FIRST_RUN``. Later runs emit, in
    arrival order, the messages received since ``cursor - lookback`` that are
    not in the ring, advance the cursor to the last emitted message and append
    the emitted uids to the ring. ``peek`` never writes state.
    """
    started = time.perf_counter()
    connection = _sql_connection(store)
    tables = _table_names(connection)
    mailbox_map = {mailbox.rowid: mailbox for mailbox in store.mailboxes}

    resolved = _resolved_scope(config, store, labels)
    scope_mailboxes = _scope_mailboxes(resolved)
    allowed_ids = frozenset(mailbox.rowid for mailbox in scope_mailboxes)

    app_state = state_store.load()
    previous = app_state.cursor
    previous_payload = _cursor_payload(previous)
    limit_value = _new_limit(config, limit)

    if not resolved:
        return _new_result(
            started,
            [NO_ACCOUNTS_WARNING],
            previous_payload,
            previous_payload,
            candidates=0,
            messages_read=0,
        )
    if not allowed_ids:
        return _new_result(
            started,
            [],
            previous_payload,
            previous_payload,
            candidates=0,
            messages_read=0,
        )

    if previous is None:
        return _run_new_baseline(
            store,
            config,
            labels,
            state_store,
            connection,
            tables,
            mailbox_map,
            allowed_ids,
            app_state,
            peek,
            started,
        )

    threshold = int(previous.last_date_received) - int(previous.lookback_seconds)
    rows = _fetch_rows(
        connection,
        tables,
        sorted(allowed_ids),
        since=threshold,
        order="asc",
    )
    ring = {int(uid) for uid in app_state.emitted_uids}
    rows = [row for row in rows if int(row["uid"]) not in ring]
    candidates = len(rows)

    label_map = _fetch_label_mailboxes(
        connection, tables, [row["uid"] for row in rows]
    )
    duplicate_counts = _fetch_duplicate_counts(connection, tables, allowed_ids)
    canonical = _dedupe(rows, mailbox_map, label_map, duplicate_counts)
    canonical.sort(key=lambda row: (_date_key(row), int(row["uid"])))

    page = canonical[:limit_value]
    truncated = len(canonical) > limit_value
    warnings: list[str] = []
    if truncated:
        warnings.append(_truncated_warning(len(canonical) - limit_value))

    recipients = _fetch_recipients(
        connection, tables, [row["uid"] for row in page]
    )
    messages, body_warnings, page_reads = _build_messages(
        store,
        labels,
        page,
        mailbox_map,
        allowed_ids,
        label_map,
        recipients,
        cached_bodies=False,
    )
    warnings.extend(body_warnings)

    if peek:
        current_payload = previous_payload
    elif page:
        emitted = [(_date_key(row), int(row["uid"])) for row in page]
        new_state = state_store.record_new(app_state, emitted, command="new")
        state_store.save(new_state)
        current_payload = _cursor_payload(new_state.cursor)
    else:
        current_payload = previous_payload

    return {
        "count": len(messages),
        "truncated": truncated,
        "hint": _new_hint(truncated),
        "messages": messages,
        "scan": _scan_dict("metadata", candidates, page_reads, started),
        "cursor": {"previous": previous_payload, "current": current_payload},
        "warnings": warnings,
    }


def run_show(store: "EnvelopeStore", labels: "AccountLabels", uid: int) -> dict:
    """Return ``{"message", "warnings"}`` for one uid.

    ``show`` has no configured scope: it looks the uid up across the whole
    store (deleted messages and orphan ``.emlx`` files are not shown). A uid
    that cannot be found raises ``E_USAGE`` with an actionable hint, as PRD 12
    has no specific "message not found" code.
    """
    connection = _sql_connection(store)
    tables = _table_names(connection)
    mailbox_map = {mailbox.rowid: mailbox for mailbox in store.mailboxes}

    try:
        target_uid = int(uid)
    except (TypeError, ValueError):
        raise _message_not_found(uid) from None
    if target_uid < 0:
        raise _message_not_found(uid)

    rows = _fetch_rows(connection, tables, (), uid=target_uid)
    if not rows:
        raise _message_not_found(target_uid)
    row = rows[0]
    mailbox = mailbox_map.get(int(row["mailbox_id"]))
    recipients = _fetch_recipients(connection, tables, [target_uid])
    to_list, cc_list = _recipient_lists(recipients, target_uid)

    parsed, path, warnings = _load_emlx(store, mailbox, target_uid)

    body_text = ""
    body_truncated = False
    if parsed is not None and bool(getattr(parsed, "readable", False)):
        cleaned = output.sanitize_text(parsed.body_text or "")
        body_truncated = len(cleaned) > output.SHOW_BODY_MAX_CHARS
        body_text = cleaned[: output.SHOW_BODY_MAX_CHARS]
        if body_truncated:
            warnings.append(
                "W_BODY_TRUNCATED: the body was truncated to "
                f"{output.SHOW_BODY_MAX_CHARS} characters"
            )

    attachment_names = (
        list(getattr(parsed, "attachments", ()) or ()) if parsed is not None else []
    )
    if not attachment_names:
        stored_names = _fetch_attachment_names(connection, tables, target_uid)
        if stored_names:
            attachment_names = stored_names
            if parsed is None or not bool(getattr(parsed, "readable", False)):
                warnings.append(
                    "W_ATTACHMENTS_UNAVAILABLE: attachment names come from the "
                    "envelope index; the message body could not be read"
                )

    partial = bool(getattr(parsed, "partial", False)) if parsed is not None else False
    readable = bool(getattr(parsed, "readable", False)) if parsed is not None else False
    headers = _show_headers(parsed, row, to_list, cc_list)

    message = {
        "uid": int(row["uid"]),
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
        "mailbox": _mailbox_payload(labels, mailbox),
        "is_read": bool(row.get("read")),
        "is_flagged": bool(row.get("flagged")),
        "has_attachments": bool(row.get("has_attachments")),
        "size_bytes": int(row.get("size") or 0),
        "headers": headers,
        "body_text": body_text,
        "body_truncated": body_truncated,
        "attachments": [{"name": str(name)} for name in attachment_names],
        "partial": partial,
        "readable": readable,
        "source": {
            "emlx_path": str(path) if path is not None else None,
            "partial": partial,
        },
    }
    return {"message": message, "warnings": warnings}


def run_mailboxes(
    store: "EnvelopeStore", config: "Config", labels: "AccountLabels"
) -> dict:
    """Return ``{"accounts", "mailboxes", "warnings"}``.

    ``accounts[]`` lists the accounts present in the store with their resolved
    labels and a ``declared`` flag; ``mailboxes[]`` lists every folder with the
    recalculated totals/unread counters that :mod:`mailquery.store` already
    computed and an ``included`` flag (declared account + INBOX + configured
    ``mailbox_list`` folders).
    """
    resolved = _resolved_scope(config, store, labels)
    scope_mailboxes = _scope_mailboxes(resolved)
    allowed_ids = {mailbox.rowid for mailbox in scope_mailboxes}
    declared_ids = {_scope_account_uuid(scope) for scope in resolved}

    warnings: list[str] = []
    if not resolved:
        warnings.append(NO_ACCOUNTS_WARNING)
    if not _labels_available(labels):
        warnings.append(LABELS_UNAVAILABLE_WARNING)

    accounts: list[dict] = []
    seen_accounts: set[str] = set()
    for scope in resolved:
        uuid = _scope_account_uuid(scope)
        if not uuid or uuid in seen_accounts:
            continue
        seen_accounts.add(uuid)
        account = _account_payload(labels, uuid)
        account["declared"] = True
        accounts.append(account)
    for mailbox in store.mailboxes:
        uuid = mailbox.account_uuid
        if not uuid or uuid in seen_accounts:
            continue
        seen_accounts.add(uuid)
        account = _account_payload(labels, uuid)
        account["declared"] = uuid in declared_ids
        accounts.append(account)

    mailboxes = [
        {
            "account": _account_payload(labels, mailbox.account_uuid),
            "name": mailbox.name,
            "path": mailbox.path,
            "url": mailbox.url,
            "total": int(mailbox.message_count),
            "unread": int(mailbox.unread_count),
            "included": mailbox.rowid in allowed_ids,
        }
        for mailbox in store.mailboxes
    ]
    return {"accounts": accounts, "mailboxes": mailboxes, "warnings": warnings}


# --------------------------------------------------------------------------- #
# Scope resolution
# --------------------------------------------------------------------------- #


def _resolved_scope(
    config: "Config", store: "EnvelopeStore", labels: "AccountLabels"
) -> list[Any]:
    """Resolve ``[scope.*]`` accounts through :mod:`mailquery.config`."""
    resolved = config_module.resolve_scope(config, store, labels)
    return list(resolved or ())


def _scope_account_uuid(scope: Any) -> str:
    return str(getattr(scope, "account_uuid", "") or "")


def _scope_mailboxes(
    resolved: Sequence[Any], extra: Iterable["Mailbox"] = ()
) -> tuple["Mailbox", ...]:
    """Return the resolved mailboxes in order, without duplicates."""
    unique: dict[int, "Mailbox"] = {}
    for scope in resolved:
        for mailbox in getattr(scope, "mailboxes", ()) or ():
            unique.setdefault(int(mailbox.rowid), mailbox)
    for mailbox in extra:
        unique.setdefault(int(mailbox.rowid), mailbox)
    return tuple(unique.values())


def _resolve_include_mailboxes(
    store: "EnvelopeStore",
    resolved: Sequence[Any],
    references: Sequence[str],
) -> tuple["Mailbox", ...]:
    """Resolve ``--include-mailbox`` refs inside the declared accounts.

    Values may be repeated or comma-separated, and each item is a folder name,
    path or URL as shown by ``mailquery mailboxes``. A folder that only exists
    in an undeclared account raises ``E_ACCOUNT_NOT_IN_SCOPE``; a folder that
    does not exist in any declared account raises ``E_MAILBOX_NOT_FOUND``.
    """
    if not references:
        return ()
    declared = {_scope_account_uuid(scope) for scope in resolved}
    selected: list["Mailbox"] = []
    seen: set[int] = set()
    for raw in references:
        if raw is None:
            continue
        for reference in str(raw).split(","):
            reference = reference.strip()
            if not reference:
                continue
            mailbox = _resolve_reference(store, resolved, reference)
            if mailbox is not None:
                if int(mailbox.rowid) not in seen:
                    seen.add(int(mailbox.rowid))
                    selected.append(mailbox)
                continue
            elsewhere = _find_reference_outside_scope(store, declared, reference)
            if elsewhere is not None:
                raise MailqueryError(
                    "E_ACCOUNT_NOT_IN_SCOPE",
                    f"mailbox {reference!r} belongs to account "
                    f"{elsewhere.account_uuid!r}, which is not declared in config.toml",
                    "only accounts declared with a [scope.<account>] block are "
                    "read; declare the account in ~/.mailquery/config.toml or "
                    "drop --include-mailbox",
                )
            raise MailqueryError(
                "E_MAILBOX_NOT_FOUND",
                f"mailbox {reference!r} was not found in the declared accounts",
                "run `mailquery mailboxes` to list the available folders and "
                "their exact name/path/url",
            )
    return tuple(selected)


def _resolve_reference(
    store: "EnvelopeStore", resolved: Sequence[Any], reference: str
) -> "Mailbox | None":
    for scope in resolved:
        account_uuid = _scope_account_uuid(scope)
        if not account_uuid:
            continue
        try:
            mailbox = store.resolve_mailbox(account_uuid, reference)
        except MailqueryError:
            raise
        except Exception:
            mailbox = None
        if mailbox is not None:
            return mailbox
    return None


def _find_reference_outside_scope(
    store: "EnvelopeStore", declared: set[str], reference: str
) -> "Mailbox | None":
    seen: set[str] = set()
    for mailbox in store.mailboxes:
        account_uuid = mailbox.account_uuid
        if not account_uuid or account_uuid in declared or account_uuid in seen:
            continue
        seen.add(account_uuid)
        try:
            candidate = store.resolve_mailbox(account_uuid, reference)
        except MailqueryError:
            raise
        except Exception:
            candidate = None
        if candidate is not None:
            return candidate
    return None


def _require_bounded_scan(
    resolved: Sequence[Any], include: Sequence["Mailbox"], filters: Filters
) -> None:
    """Reject ``--text`` queries without a narrowing filter (RF-17)."""
    has_filter = bool(
        filters.since is not None
        or filters.until is not None
        or filters.subject
        or filters.from_
        or filters.to
        or filters.cc
    )
    has_extra_folder = any(
        not bool(getattr(mailbox, "is_inbox", False))
        for mailbox in _scope_mailboxes(resolved)
    ) or any(not bool(getattr(mailbox, "is_inbox", False)) for mailbox in include)
    if has_filter or has_extra_folder:
        return
    raise MailqueryError(
        "E_UNBOUNDED_SCAN",
        "--text without a narrowing filter would read every message in the scope",
        "add --since, --until, --from, --to, --cc, --subject or "
        "--include-mailbox (for example: mailquery search --text invoice --since 30d)",
    )


# --------------------------------------------------------------------------- #
# SQL access (through the read-only EnvelopeStore connection)
# --------------------------------------------------------------------------- #


def _sql_connection(store: "EnvelopeStore") -> sqlite3.Connection:
    """Return the read-only connection owned by the store."""
    connection = getattr(store, "connection", None)
    if connection is None:
        raise MailqueryError(
            "E_INTERNAL",
            "the mail store does not expose a SQLite connection",
            "internal error: EnvelopeStore must keep its read-only connection "
            "as the .connection attribute",
        )
    return connection


def _table_names(connection: sqlite3.Connection) -> frozenset[str]:
    """Feature-detect the tables present in the Envelope Index."""
    try:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
        ).fetchall()
    except sqlite3.Error:
        return frozenset()
    names: set[str] = set()
    for row in rows:
        try:
            names.add(str(row[0]))
        except (IndexError, TypeError):  # pragma: no cover - defensive
            continue
    return frozenset(names)


def _scope_predicate(
    mailbox_ids: Iterable[int], tables: frozenset[str], alias: str = "m"
) -> tuple[str, list[Any]]:
    """Return the scope ``WHERE`` fragment: direct mailbox or label membership."""
    ids = list(dict.fromkeys(int(rowid) for rowid in mailbox_ids))
    if not ids:
        return "", []
    placeholders = ", ".join("?" for _ in ids)
    clause = f"({alias}.mailbox IN ({placeholders})"
    params: list[Any] = list(ids)
    if "labels" in tables:
        clause += (
            f" OR EXISTS (SELECT 1 FROM labels l WHERE l.message_id = "
            f"{alias}.ROWID AND l.mailbox_id IN ({placeholders}))"
        )
        params.extend(ids)
    return clause + ")", params


def _select_sql(tables: frozenset[str]) -> str:
    """Build the feature-detected metadata SELECT (columns in _ROW_COLUMNS)."""
    joins: list[str] = []
    if "subjects" in tables:
        subject_expression = "COALESCE(sub.subject, '')"
        joins.append("LEFT JOIN subjects sub ON sub.ROWID = m.subject")
    else:  # pragma: no cover - store validates the schema first
        subject_expression = "''"
    if "addresses" in tables:
        sender_name_expression = "COALESCE(sender.comment, '')"
        sender_address_expression = "COALESCE(sender.address, '')"
        joins.append("LEFT JOIN addresses sender ON sender.ROWID = m.sender")
    else:  # pragma: no cover - store validates the schema first
        sender_name_expression = "''"
        sender_address_expression = "''"
    if "message_global_data" in tables:
        message_id_expression = (
            "COALESCE((SELECT mgd.message_id_header FROM message_global_data "
            "mgd WHERE mgd.ROWID = m.global_message_id LIMIT 1), '')"
        )
    else:  # pragma: no cover - store validates the schema first
        message_id_expression = "''"
    if "attachments" in tables:
        has_attachments_expression = (
            "EXISTS (SELECT 1 FROM attachments att WHERE att.message = m.ROWID)"
        )
    else:  # pragma: no cover - store validates the schema first
        has_attachments_expression = "0"

    columns = ",\n       ".join(
        (
            "m.ROWID",
            "COALESCE(m.global_message_id, 0)",
            subject_expression,
            sender_name_expression,
            sender_address_expression,
            "m.date_sent",
            "m.date_received",
            "m.mailbox",
            "COALESCE(m.read, 0)",
            "COALESCE(m.flagged, 0)",
            "COALESCE(m.size, 0)",
            message_id_expression,
            has_attachments_expression,
        )
    )
    return f"SELECT {columns}\nFROM messages m\n{' '.join(joins)}"


def _fetch_rows(
    connection: sqlite3.Connection,
    tables: frozenset[str],
    mailbox_ids: Sequence[int],
    *,
    since: float | None = None,
    until: float | None = None,
    unread: bool = False,
    flagged: bool = False,
    has_attachments: bool = False,
    order: str = "desc",
    uid: int | None = None,
) -> list[dict]:
    """Execute the metadata query and return plain row dictionaries."""
    where: list[str] = ["m.deleted = 0"]
    params: list[Any] = []
    if uid is not None:
        where.append("m.ROWID = ?")
        params.append(int(uid))
    else:
        scope_sql, scope_params = _scope_predicate(mailbox_ids, tables)
        if not scope_sql:
            return []
        where.append(scope_sql)
        params.extend(scope_params)
    if since is not None:
        where.append("m.date_received IS NOT NULL AND m.date_received >= ?")
        params.append(float(since))
    if until is not None:
        where.append("m.date_received IS NOT NULL AND m.date_received < ?")
        params.append(float(until))
    if unread:
        where.append("COALESCE(m.read, 0) = 0")
    if flagged:
        where.append("COALESCE(m.flagged, 0) = 1")
    if has_attachments:
        if "attachments" not in tables:  # pragma: no cover - schema validated
            return []
        where.append("EXISTS (SELECT 1 FROM attachments att2 WHERE att2.message = m.ROWID)")
    order_sql = (
        "m.date_received DESC, m.ROWID DESC"
        if order == "desc"
        else "m.date_received ASC, m.ROWID ASC"
    )
    sql = f"{_select_sql(tables)}\nWHERE {' AND '.join(where)}\nORDER BY {order_sql}"
    try:
        cursor = connection.execute(sql, params)
        values = cursor.fetchall()
    except sqlite3.Error as exc:
        raise _query_error(exc) from exc
    return [_row_dict(value) for value in values]


def _row_dict(values: Sequence[Any]) -> dict:
    data = dict(zip(_ROW_COLUMNS, values))
    return {
        "uid": int(data["uid"]),
        "global_message_id": int(data["global_message_id"] or 0),
        "subject": str(data["subject"] or ""),
        "sender_name": str(data["sender_name"] or ""),
        "sender_address": str(data["sender_address"] or ""),
        "date_sent": data["date_sent"],
        "date_received": data["date_received"],
        "mailbox_id": int(data["mailbox_id"] or 0),
        "read": int(data["read"] or 0),
        "flagged": int(data["flagged"] or 0),
        "size": int(data["size"] or 0),
        "message_id": str(data["message_id"] or ""),
        "has_attachments": bool(data["has_attachments"]),
    }


def _fetch_recipients(
    connection: sqlite3.Connection,
    tables: frozenset[str],
    uids: Sequence[int],
) -> dict[int, dict[str, list[dict]]]:
    """Return ``{uid: {"to": [...], "cc": [...]}}`` for the requested uids."""
    if not uids or "recipients" not in tables or "addresses" not in tables:
        return {}
    unique = list(dict.fromkeys(int(uid) for uid in uids))
    result: dict[int, dict[str, list[dict]]] = {}
    for chunk in _chunks(unique, _PLACEHOLDER_CHUNK):
        placeholders = ", ".join("?" for _ in chunk)
        sql = (
            "SELECT r.message, r.type, COALESCE(a.address, ''), "
            "COALESCE(a.comment, '') "
            "FROM recipients r JOIN addresses a ON a.ROWID = r.address "
            f"WHERE r.message IN ({placeholders}) "
            "ORDER BY r.message, COALESCE(r.position, 0)"
        )
        try:
            rows = connection.execute(sql, chunk).fetchall()
        except sqlite3.Error as exc:  # pragma: no cover - schema validated
            raise _query_error(exc) from exc
        for message_uid, recipient_type, address, name in rows:
            bucket = result.setdefault(
                int(message_uid), {"to": [], "cc": []}
            )
            entry = {"name": str(name or ""), "address": str(address or "")}
            kind = 0 if recipient_type is None else int(recipient_type)
            if kind == 1:
                bucket["cc"].append(entry)
            elif kind == 0:
                bucket["to"].append(entry)
    return result


def _recipient_lists(
    recipients: dict[int, dict[str, list[dict]]], uid: int
) -> tuple[list[dict], list[dict]]:
    bucket = recipients.get(int(uid), {})
    to_list = [dict(entry) for entry in bucket.get("to", [])]
    cc_list = [dict(entry) for entry in bucket.get("cc", [])]
    return to_list, cc_list


def _fetch_attachment_names(
    connection: sqlite3.Connection, tables: frozenset[str], uid: int
) -> list[str]:
    if "attachments" not in tables:  # pragma: no cover - schema validated
        return []
    sql = (
        "SELECT COALESCE(name, '') FROM attachments WHERE message = ? "
        "ORDER BY ROWID"
    )
    try:
        rows = connection.execute(sql, (int(uid),)).fetchall()
    except sqlite3.Error as exc:  # pragma: no cover - schema validated
        raise _query_error(exc) from exc
    return [str(row[0]) for row in rows if row[0]]


def _fetch_label_mailboxes(
    connection: sqlite3.Connection,
    tables: frozenset[str],
    uids: Sequence[int],
) -> dict[int, set[int]]:
    """Return ``{message_uid: {mailbox_id, ...}}`` for the label memberships."""
    if not uids or "labels" not in tables:
        return {}
    unique = list(dict.fromkeys(int(uid) for uid in uids))
    result: dict[int, set[int]] = {}
    for chunk in _chunks(unique, _PLACEHOLDER_CHUNK):
        placeholders = ", ".join("?" for _ in chunk)
        sql = (
            f"SELECT l.message_id, l.mailbox_id FROM labels l "
            f"WHERE l.message_id IN ({placeholders})"
        )
        try:
            rows = connection.execute(sql, chunk).fetchall()
        except sqlite3.Error as exc:  # pragma: no cover - schema validated
            raise _query_error(exc) from exc
        for message_uid, mailbox_id in rows:
            result.setdefault(int(message_uid), set()).add(int(mailbox_id))
    return result


def _fetch_duplicate_counts(
    connection: sqlite3.Connection,
    tables: frozenset[str],
    mailbox_ids: Iterable[int],
) -> dict[int, int]:
    """Count, in the scope, the copies of each ``global_message_id``."""
    clause, params = _scope_predicate(mailbox_ids, tables)
    if not clause:
        return {}
    sql = (
        "SELECT m.global_message_id, COUNT(*) FROM messages m "
        f"WHERE m.deleted = 0 AND {clause} GROUP BY m.global_message_id"
    )
    counts: dict[int, int] = {}
    try:
        rows = connection.execute(sql, params).fetchall()
    except sqlite3.Error as exc:  # pragma: no cover - schema validated
        raise _query_error(exc) from exc
    for global_id, count in rows:
        if global_id:
            counts[int(global_id)] = int(count)
    return counts


def _newest_scoped_message(
    connection: sqlite3.Connection,
    tables: frozenset[str],
    mailbox_ids: Iterable[int],
) -> tuple[int, int] | None:
    """Return ``(date_received, uid)`` of the newest message of the scope."""
    clause, params = _scope_predicate(mailbox_ids, tables)
    if not clause:
        return None
    sql = (
        "SELECT m.ROWID, m.date_received FROM messages m "
        f"WHERE m.deleted = 0 AND {clause} AND m.date_received IS NOT NULL "
        "ORDER BY m.date_received DESC, m.ROWID DESC LIMIT 1"
    )
    try:
        row = connection.execute(sql, params).fetchone()
    except sqlite3.Error as exc:  # pragma: no cover - schema validated
        raise _query_error(exc) from exc
    if row is None:
        return None
    return int(row[1]), int(row[0])


def _ring_uid_seed(
    connection: sqlite3.Connection,
    tables: frozenset[str],
    mailbox_ids: Iterable[int],
    end_date: int,
    lookback_seconds: int,
) -> tuple[int, ...]:
    """Seed the emitted-uid ring with the uids of the baseline window."""
    clause, params = _scope_predicate(mailbox_ids, tables)
    if not clause:
        return ()
    start_date = int(end_date) - int(lookback_seconds)
    sql = (
        "SELECT m.ROWID FROM messages m "
        f"WHERE m.deleted = 0 AND {clause} AND m.date_received IS NOT NULL "
        "AND m.date_received >= ? AND m.date_received <= ? "
        "ORDER BY m.date_received DESC, m.ROWID DESC LIMIT ?"
    )
    try:
        rows = connection.execute(
            sql, params + [start_date, int(end_date), int(MAX_EMITTED_UIDS)]
        ).fetchall()
    except sqlite3.Error as exc:  # pragma: no cover - schema validated
        raise _query_error(exc) from exc
    return tuple(int(row[0]) for row in reversed(rows))


# --------------------------------------------------------------------------- #
# Filtering, scan and dedupe
# --------------------------------------------------------------------------- #


def _apply_pattern_filters(
    rows: list[dict],
    filters: Filters,
    connection: sqlite3.Connection,
    tables: frozenset[str],
) -> list[dict]:
    """Apply the wildcard/substring filters (accent- and case-insensitive)."""
    if not rows:
        return []
    subject_terms = _filter_terms(filters.subject)
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
        recipients = _fetch_recipients(
            connection, tables, [row["uid"] for row in rows]
        )
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
    store: "EnvelopeStore",
    rows: list[dict],
    mailbox_map: dict[int, "Mailbox"],
    terms: Sequence[str],
) -> tuple[list[dict], list[str], int]:
    """Bounded ``--text`` scan: parse the candidate rows in order and match."""
    matched: list[dict] = []
    warnings: list[str] = []
    messages_read = 0
    for row in rows:
        mailbox = mailbox_map.get(int(row["mailbox_id"]))
        parsed, path, load_warnings = _load_emlx(store, mailbox, int(row["uid"]))
        warnings.extend(load_warnings)
        if path is not None:
            messages_read += 1
        if parsed is None:
            continue
        if not bool(getattr(parsed, "available", True)):
            continue
        if not bool(getattr(parsed, "readable", True)):
            continue
        body_text = parsed.body_text or ""
        if not _matches_all_terms(terms, body_text):
            continue
        matched_row = dict(row)
        matched_row["_body_text"] = body_text
        matched_row["_body_partial"] = bool(getattr(parsed, "partial", False))
        matched.append(matched_row)
    return matched, warnings, messages_read


def _dedupe(
    rows: list[dict],
    mailbox_map: dict[int, "Mailbox"],
    label_map: dict[int, set[int]],
    duplicate_counts: dict[int, int],
) -> list[dict]:
    """Dedupe by ``global_message_id`` (INBOX > normal folder > aggregate).

    The canonical copy is chosen with the PRD Anexo B ordering, and the result
    is returned in the documented total order ``(date_received DESC, ROWID
    DESC)``. Messages without a usable ``global_message_id`` are unique.
    """
    if not rows:
        return []
    inbox_ids = {
        rowid
        for rowid, mailbox in mailbox_map.items()
        if bool(getattr(mailbox, "is_inbox", False))
    }
    aggregate_ids = {
        rowid
        for rowid, mailbox in mailbox_map.items()
        if bool(getattr(mailbox, "is_aggregate", False))
    }
    groups: dict[tuple[str, int], list[dict]] = {}
    for row in rows:
        global_id = int(row.get("global_message_id") or 0)
        key = ("global", global_id) if global_id else ("uid", int(row["uid"]))
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
    canonical.sort(key=lambda row: (_date_key(row), int(row["uid"])), reverse=True)
    return canonical


def _dedupe_sort_key(
    row: dict,
    inbox_ids: set[int],
    aggregate_ids: set[int],
    label_map: dict[int, set[int]],
) -> tuple[int, int, int]:
    return (
        _mailbox_priority_for_row(row, inbox_ids, aggregate_ids, label_map),
        _date_key(row),
        int(row["uid"]),
    )


def _mailbox_priority_for_row(
    row: dict,
    inbox_ids: set[int],
    aggregate_ids: set[int],
    label_map: dict[int, set[int]],
) -> int:
    mailbox_id = int(row["mailbox_id"])
    if mailbox_id in inbox_ids:
        return 0
    if label_map.get(int(row["uid"]), set()) & inbox_ids:
        return 0
    if mailbox_id in aggregate_ids:
        return 2
    return 1


# --------------------------------------------------------------------------- #
# Message assembly
# --------------------------------------------------------------------------- #


def _build_messages(
    store: "EnvelopeStore",
    labels: "AccountLabels",
    page: Sequence[dict],
    mailbox_map: dict[int, "Mailbox"],
    allowed_ids: frozenset[int],
    label_map: dict[int, set[int]],
    recipients: dict[int, dict[str, list[dict]]],
    *,
    cached_bodies: bool,
) -> tuple[list[dict], list[str], int]:
    """Build the page message objects, parsing only the returned page.

    The ``.emlx`` file always lives under the message's physical mailbox (a
    Gmail message labelled INBOX is stored under ``[Gmail]/All Mail``), while
    the reported ``mailbox`` is the effective in-scope one (INBOX).
    """
    messages: list[dict] = []
    warnings: list[str] = []
    messages_read = 0
    for row in page:
        uid = int(row["uid"])
        display_mailbox = _display_mailbox(row, mailbox_map, allowed_ids, label_map)
        physical_mailbox = mailbox_map.get(int(row["mailbox_id"]))
        to_list, cc_list = _recipient_lists(recipients, uid)
        if cached_bodies and "_body_text" in row:
            snippet, body_fields = _body_from_cached(row)
        else:
            snippet, body_fields, _parsed, path, body_warnings = _body_fields(
                store, physical_mailbox, uid
            )
            warnings.extend(body_warnings)
            if path is not None:
                messages_read += 1
        messages.append(
            _message_payload(
                labels, row, display_mailbox, to_list, cc_list, snippet, body_fields
            )
        )
    return messages, warnings, messages_read


def _message_payload(
    labels: "AccountLabels",
    row: dict,
    mailbox: "Mailbox | None",
    to_list: list[dict],
    cc_list: list[dict],
    snippet: str,
    body_fields: dict,
) -> dict:
    return {
        "uid": int(row["uid"]),
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
        "mailbox": _mailbox_payload(labels, mailbox),
        "is_read": bool(row.get("read")),
        "is_flagged": bool(row.get("flagged")),
        "has_attachments": bool(row.get("has_attachments")),
        "size_bytes": int(row.get("size") or 0),
        "snippet": snippet,
        "body": body_fields,
    }


def _display_mailbox(
    row: dict,
    mailbox_map: dict[int, "Mailbox"],
    allowed_ids: frozenset[int] | None,
    label_map: dict[int, set[int]],
) -> "Mailbox | None":
    """Pick the mailbox reported for a message.

    A message included through a label (Gmail INBOX lives physically in
    ``[Gmail]/All Mail``) is reported as the in-scope label mailbox (INBOX),
    which is what a search scoped to INBOX should show.
    """
    mailbox_id = int(row["mailbox_id"])
    direct = mailbox_map.get(mailbox_id)
    if allowed_ids is None or direct is None:
        return direct
    if mailbox_id in allowed_ids:
        return direct
    candidates = [
        mailbox_map[label_id]
        for label_id in label_map.get(int(row["uid"]), set())
        if label_id in allowed_ids and label_id in mailbox_map
    ]
    if candidates:
        return min(candidates, key=_mailbox_priority)
    return direct


def _mailbox_priority(mailbox: "Mailbox") -> int:
    if bool(getattr(mailbox, "is_inbox", False)):
        return 0
    if bool(getattr(mailbox, "is_aggregate", False)):
        return 2
    return 1


def _mailbox_payload(labels: "AccountLabels", mailbox: "Mailbox | None") -> dict:
    if mailbox is None:  # pragma: no cover - defensive, the store maps every row
        return {
            "account": {"uuid": "", "label": "", "email": None},
            "name": "",
            "path": "",
            "url": "",
        }
    return {
        "account": _account_payload(labels, mailbox.account_uuid),
        "name": mailbox.name,
        "path": mailbox.path,
        "url": mailbox.url,
    }


def _account_payload(labels: "AccountLabels", uuid: str) -> dict:
    account_uuid = str(uuid or "")
    if account_uuid and _labels_available(labels):
        try:
            entry = labels.get(account_uuid)
        except Exception:  # pragma: no cover - labels module degrades itself
            entry = None
        if entry is not None:
            return {
                "uuid": str(getattr(entry, "uuid", account_uuid) or account_uuid),
                "label": str(getattr(entry, "label", "") or account_uuid),
                "email": getattr(entry, "email", None),
            }
    label = account_uuid
    if account_uuid and labels is not None:
        try:
            label = str(labels.label_for(account_uuid) or account_uuid)
        except Exception:  # pragma: no cover - labels module degrades itself
            label = account_uuid
    return {"uuid": account_uuid, "label": label, "email": None}


def _labels_available(labels: "AccountLabels | None") -> bool:
    if labels is None:
        return False
    try:
        return bool(labels.available)
    except Exception:  # pragma: no cover - labels module degrades itself
        return False


# --------------------------------------------------------------------------- #
# ``.emlx`` bodies
# --------------------------------------------------------------------------- #


def _load_emlx(
    store: "EnvelopeStore", mailbox: "Mailbox | None", uid: int
) -> tuple[Any, Any, list[str]]:
    """Resolve and parse one ``.emlx``, turning failures into warnings."""
    warnings: list[str] = []
    if mailbox is None:  # pragma: no cover - defensive, the store maps every row
        warnings.append(f"W_EMLX_UNREADABLE: no mailbox information for uid {uid}")
        return None, None, warnings
    try:
        path = emlx.resolve_path(store, mailbox, uid)
    except Exception as exc:
        warnings.append(
            f"W_EMLX_UNREADABLE: cannot resolve the .emlx path for uid {uid} "
            f"({type(exc).__name__})"
        )
        return None, None, warnings
    if path is None:
        warnings.append(f"W_EMLX_MISSING: no .emlx file for uid {uid}")
        return None, None, warnings
    try:
        parsed = emlx.parse_emlx(path)
    except Exception as exc:
        warnings.append(
            f"W_EMLX_UNREADABLE: cannot read the .emlx for uid {uid} "
            f"({type(exc).__name__})"
        )
        return None, path, warnings
    for warning in getattr(parsed, "warnings", ()) or ():
        if warning:
            warnings.append(str(warning))
    if not bool(getattr(parsed, "available", True)) and not _has_warning(
        warnings, "W_EMLX_UNREADABLE", "W_EMLX_MISSING"
    ):
        warnings.append(f"W_EMLX_UNREADABLE: the .emlx for uid {uid} is not available")
    if not bool(getattr(parsed, "readable", True)) and not _has_warning(
        warnings, "W_EMLX_CORRUPT"
    ):
        warnings.append(f"W_EMLX_CORRUPT: the .emlx for uid {uid} could not be parsed")
    return parsed, path, warnings


def _body_fields(
    store: "EnvelopeStore", mailbox: "Mailbox | None", uid: int
) -> tuple[str, dict, Any, Any, list[str]]:
    """Return ``(snippet, body, parsed, path, warnings)`` for a message."""
    parsed, path, warnings = _load_emlx(store, mailbox, uid)
    if parsed is None:
        partial = bool(path is not None and str(path).endswith(".partial.emlx"))
        return "", _unavailable_body(partial), None, path, warnings
    body_text = parsed.body_text or ""
    snippet = output.make_snippet(body_text) if body_text else ""
    fields = {
        "available": bool(getattr(parsed, "available", True)),
        "partial": bool(getattr(parsed, "partial", False)),
        "truncated": _snippet_truncated(body_text),
    }
    return snippet, fields, parsed, path, warnings


def _body_from_cached(row: dict) -> tuple[str, dict]:
    body_text = str(row.get("_body_text") or "")
    snippet = output.make_snippet(body_text) if body_text else ""
    return snippet, {
        "available": True,
        "partial": bool(row.get("_body_partial", False)),
        "truncated": _snippet_truncated(body_text),
    }


def _unavailable_body(partial: bool) -> dict:
    return {"available": False, "partial": bool(partial), "truncated": False}


def _snippet_truncated(body_text: str) -> bool:
    if not body_text:
        return False
    single_line = " ".join(output.sanitize_text(body_text).split())
    return len(single_line) > output.SNIPPET_CHARS


def _show_headers(
    parsed: Any, row: dict, to_list: list[dict], cc_list: list[dict]
) -> dict[str, str]:
    raw_headers = dict(getattr(parsed, "headers", {}) or {}) if parsed is not None else {}
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


def _run_new_baseline(
    store: "EnvelopeStore",
    config: "Config",
    labels: "AccountLabels",
    state_store: "StateStore",
    connection: sqlite3.Connection,
    tables: frozenset[str],
    mailbox_map: dict[int, "Mailbox"],
    allowed_ids: frozenset[int],
    app_state: AppState,
    peek: bool,
    started: float,
) -> dict:
    """First run: emit nothing, set the cursor to the newest scoped message."""
    warnings = [FIRST_RUN_WARNING]
    lookback = int(getattr(config.new, "lookback_seconds", 600) or 600)
    newest = _newest_scoped_message(connection, tables, sorted(allowed_ids))
    if newest is None:
        return _new_result(
            started,
            warnings,
            None,
            None,
            candidates=0,
            messages_read=0,
        )
    date_received, uid = newest
    baseline = Cursor(
        last_date_received=int(date_received),
        last_uid=int(uid),
        lookback_seconds=lookback,
    )
    if peek:
        return _new_result(
            started,
            warnings,
            None,
            None,
            candidates=0,
            messages_read=0,
        )
    seed = _ring_uid_seed(
        connection, tables, sorted(allowed_ids), int(date_received), lookback
    )
    seeded_state = AppState(cursor=baseline, emitted_uids=seed)
    new_state = state_store.record_new(seeded_state, [], command="new")
    state_store.save(new_state)
    current_payload = _cursor_payload(new_state.cursor)
    return {
        "count": 0,
        "truncated": False,
        "hint": None,
        "messages": [],
        "scan": _scan_dict("metadata", len(seed), 0, started),
        "cursor": {"previous": None, "current": current_payload},
        "warnings": warnings,
    }


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
        "last_uid": int(cursor.last_uid),
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


def _filter_terms(values: Iterable[str]) -> tuple[str, ...]:
    """Expand filter values into AND terms.

    A value without ``*``/``?`` is split on whitespace so each word is an AND
    term; a value with wildcards stays a single pattern (phrases are allowed).
    Repeated CLI flags are ANDed too because every value contributes terms.
    """
    terms: list[str] = []
    for value in values or ():
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        if "*" in text or "?" in text:
            terms.append(text)
        else:
            terms.extend(part for part in text.split() if part)
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
    recipients: dict[int, dict[str, list[dict]]], uid: int, kind: str
) -> list[str]:
    bucket = recipients.get(int(uid), {})
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


def _chunks(items: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


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
    return f"refina los filtros o sube --limit (máx. {SEARCH_MAX_LIMIT})"


def _new_hint(truncated: bool) -> str | None:
    if not truncated:
        return None
    return f"sube --limit (máx. {NEW_MAX_LIMIT}) o procesa el correo en varias corridas"


def _has_warning(warnings: Sequence[str], *codes: str) -> bool:
    return any(
        any(str(warning).startswith(code) for code in codes) for warning in warnings
    )


def _bad_time(value: Any) -> MailqueryError:
    from mailquery.errors import bad_time

    return bad_time("" if value is None else value)


def _message_not_found(uid: Any) -> MailqueryError:
    from mailquery.errors import usage_error

    return usage_error(
        f"message uid {uid!r} was not found",
        "run `mailquery search` to find the uid; deleted messages and orphan "
        ".emlx files are not shown",
    )


def _query_error(exc: sqlite3.Error) -> MailqueryError:
    message = str(exc).lower()
    if "locked" in message or "busy" in message:
        return MailqueryError(
            "E_DB_BUSY",
            "the Envelope Index is locked by another process",
            "retry the command (the harness should only retry exit code 5)",
        )
    return MailqueryError(
        "E_INTERNAL",
        f"the Envelope Index query failed: {exc}",
        "run `mailquery doctor` and check that the Mail store schema is supported",
    )

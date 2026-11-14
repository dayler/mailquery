"""Apple Mail backend: adapter over ``store.py``, ``emlx.py`` and ``accounts.py``.

Holds the SQL and the Apple-Mail-specific helpers that used to live in
``search.py``. The adapter adds no behavior of its own:
the queries, their ordering, the warnings and the retry through
:func:`mailquery.store.run_query` are the ones the CLI has always used. The
``Envelope Index`` is only queried through the read-only connection owned by
:class:`mailquery.store.EnvelopeStore`; nothing here opens a ``.emlx`` for
writing or writes anywhere.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Sequence

from mailquery import emlx
from mailquery.accounts import AccountLabels
from mailquery.backends.base import (
    AccountRow,
    BodyRow,
    HeaderRow,
    MailBackend,
    MailboxRow,
    MessageRow,
)
from mailquery.errors import MailqueryError, error_detail, usage_error
from mailquery.plugins import PLUGIN_API, Capabilities
from mailquery.store import (
    detect_version,
    open_store,
    probe_envelope_index,
    run_query,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mailquery.store import EnvelopeStore, Mailbox

BACKEND_NAME = "apple_mail"

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

# Apple Mail uids are plain integers.
_UID_PATTERN = re.compile(r"[+-]?[0-9]+")


# --------------------------------------------------------------------------- #
# Backend
# --------------------------------------------------------------------------- #


class AppleMailBackend(MailBackend):
    """``MailBackend`` over the Apple Mail ``Envelope Index`` and ``.emlx`` files.

    Pass an already open ``store`` (and ``labels``) or the locations
    (``mail_root``, ``accounts_db``, ``tmp_root``): then the store and the labels
    are opened lazily, on first use, with the same functions the CLI used. The
    backend owns its store: :meth:`close` closes it.
    """

    driver = BACKEND_NAME
    plugin_api = PLUGIN_API
    capabilities: Capabilities = {
        "network": False,
        "readonly": "structural",
        "body_local": True,
        "attachments": "local",
        "native_order": "numeric",
    }

    def __init__(
        self,
        store: "EnvelopeStore | None" = None,
        labels: AccountLabels | None = None,
        *,
        mail_root: Path | None = None,
        accounts_db: Path | None = None,
        tmp_root: Path | None = None,
    ) -> None:
        self._store = store
        self._labels = labels
        self._mail_root = Path(mail_root) if mail_root is not None else None
        self._accounts_db = Path(accounts_db) if accounts_db is not None else None
        self._tmp_root = Path(tmp_root) if tmp_root is not None else None
        self._tables: frozenset[str] | None = None

    # -- lazily opened collaborators ---------------------------------------- #

    @property
    def store(self) -> "EnvelopeStore":
        """The read-only :class:`EnvelopeStore` (opened on first use)."""
        if self._store is None:
            self._store = open_store(mail_root=self._mail_root, tmp_root=self._tmp_root)
        return self._store

    @property
    def labels(self) -> AccountLabels:
        """The account label resolver (created on first use)."""
        if self._labels is None:
            self._labels = AccountLabels(self._accounts_db, tmp_dir=self._tmp_root)
        return self._labels

    @property
    def connection(self) -> sqlite3.Connection:
        """The read-only connection owned by the store (read on every use)."""
        return _sql_connection(self.store)

    @property
    def tables(self) -> frozenset[str]:
        """Tables present in the Envelope Index (feature detection, cached)."""
        if self._tables is None:
            self._tables = _table_names(self.connection)
        return self._tables

    def prepare(self) -> None:
        """Validate the connection and feature-detect the tables now.

        ``search.py`` calls it first so a broken or locked store fails before
        anything else runs, exactly as before the move.
        """
        self.tables

    # -- MailBackend -------------------------------------------------------- #

    def describe(self) -> dict[str, Any]:
        """Version and strategy data for the connection log line and ``doctor``."""
        store = self.store
        version = getattr(store, "version", None)
        fingerprint = store.fingerprint()
        schema_ok = all(fingerprint.values()) if isinstance(fingerprint, dict) else True
        return {
            "backend": BACKEND_NAME,
            "version": getattr(version, "version", "-") if version is not None else "-",
            "mail_root": str(getattr(version, "mail_root", "")) if version is not None else "",
            "strategy": getattr(store, "strategy", "-"),
            "schema_ok": schema_ok,
        }

    def accounts(self) -> list[AccountRow]:
        """Every label entry of the accounts database, then the store-only accounts.

        Label matching and the "known accounts" lists use all the entries, while
        UUID matching uses the accounts that have folders: ``store_index`` is
        the position of the account among those (``None`` if it has none) and
        ``labelled`` tells whether a label entry exists for it.
        """
        store_accounts: dict[str, str] = {}
        for mailbox in self.store.mailboxes:
            if mailbox.account_uuid and mailbox.account_uuid not in store_accounts:
                store_accounts[mailbox.account_uuid] = mailbox.account_kind
        index = {uuid: position for position, uuid in enumerate(store_accounts)}
        rows: list[AccountRow] = []
        labelled: set[str] = set()
        if self.labels_available:
            for entry in self.labels.all():
                if entry.uuid in labelled:
                    continue
                labelled.add(entry.uuid)
                rows.append(
                    {
                        "uuid": entry.uuid,
                        "label": entry.label or entry.uuid,
                        "email": entry.email,
                        "local": bool(entry.local),
                        "store_index": index.get(entry.uuid),
                        "labelled": True,
                    }
                )
        for uuid, kind in store_accounts.items():
            if uuid in labelled:
                continue
            # ``get`` also matches case variants of the uuid.
            entry = self.labels.get(uuid) if self.labels_available else None
            rows.append(
                {
                    "uuid": uuid,
                    "label": (entry.label or uuid) if entry is not None else uuid,
                    "email": entry.email if entry is not None else None,
                    "local": bool(entry.local) if entry is not None else kind == "local",
                    "store_index": index[uuid],
                    "labelled": False,
                }
            )
        return rows

    @property
    def labels_available(self) -> bool:
        try:
            return bool(self.labels.available)
        except Exception:  # pragma: no cover - labels module degrades itself
            return False

    def mailboxes(self) -> list[MailboxRow]:
        return [_mailbox_row(mailbox) for mailbox in self.store.mailboxes]

    def excluded_stores(self) -> list[dict[str, Any]]:
        return []

    def resolve_mailbox(self, account_uuid: str, ref: str) -> MailboxRow | None:
        mailbox = self.store.resolve_mailbox(account_uuid, ref)
        return _mailbox_row(mailbox) if mailbox is not None else None

    def query(
        self,
        mailbox_ids: Sequence[Any],
        since: float | None = None,
        until: float | None = None,
        unread: bool = False,
        flagged: bool = False,
        has_attachments: bool = False,
        order: str = "desc",
    ) -> list[MessageRow]:
        return _fetch_rows(
            self.connection,
            self.tables,
            mailbox_ids,
            since=since,
            until=until,
            unread=unread,
            flagged=flagged,
            has_attachments=has_attachments,
            order=order,
        )

    def membership(self, uids: Sequence[Any]) -> dict[Any, set[Any]]:
        """Label memberships per uid (Gmail labels); the physical folder is in the row."""
        return _fetch_label_mailboxes(self.connection, self.tables, uids)

    def duplicate_counts(self, mailbox_ids: Sequence[Any]) -> dict[Any, int]:
        return _fetch_duplicate_counts(self.connection, self.tables, mailbox_ids)

    def recipients(self, uids: Sequence[Any]) -> dict[Any, Any]:
        return _fetch_recipients(self.connection, self.tables, uids)

    def attachment_names(self, uid: Any) -> list[str]:
        return _fetch_attachment_names(self.connection, self.tables, uid)

    def find_message(self, uid: Any) -> tuple[MessageRow, MailboxRow | None] | None:
        rows = _fetch_rows(self.connection, self.tables, (), uid=int(uid))
        if not rows:
            return None
        row = rows[0]
        mailbox = self._physical_mailbox(row)
        return row, (_mailbox_row(mailbox) if mailbox is not None else None)

    def load_body(self, row: MessageRow) -> BodyRow:
        """Parse the ``.emlx`` of the message's physical folder (never downloads)."""
        parsed, path, warnings = _load_emlx(
            self.store, self._physical_mailbox(row), int(row["uid"])
        )
        if parsed is None:
            partial = bool(path is not None and str(path).endswith(".partial.emlx"))
            return {
                "available": False,
                "readable": False,
                "partial": partial,
                "headers": {},
                "body_text": "",
                "attachments": [],
                "source": {
                    "emlx_path": str(path) if path is not None else None,
                    "partial": partial,
                },
                "warnings": warnings,
                "hidden_chars": 0,
                "authentication_results": None,
                "reply_to": None,
            }
        partial = bool(getattr(parsed, "partial", False))
        readable = bool(getattr(parsed, "readable", True))
        return {
            "available": bool(getattr(parsed, "available", True)),
            "readable": readable,
            "partial": partial,
            "headers": dict(getattr(parsed, "headers", {}) or {}),
            "body_text": parsed.body_text or "",
            "attachments": (
                [{"name": str(name)} for name in getattr(parsed, "attachments", ()) or ()]
                if readable
                else []
            ),
            "source": {"emlx_path": str(path), "partial": partial},
            "warnings": warnings,
            "hidden_chars": int(getattr(parsed, "hidden_chars", 0) or 0),
            "authentication_results": getattr(parsed, "authentication_results", None),
            "reply_to": getattr(parsed, "reply_to", None),
        }

    def load_headers(self, row: MessageRow) -> HeaderRow:
        """Read only the header block of the message's ``.emlx``.

        Resolves the file of the message's physical folder like :meth:`load_body`
        and reads its headers without parsing the body. A file that cannot be
        resolved or read yields empty headers with ``read=False``.
        """
        mailbox = self._physical_mailbox(row)
        if mailbox is None:
            return _missing_headers()
        try:
            path = emlx.resolve_path(self.store, mailbox, int(row["uid"]))
        except Exception:
            return _missing_headers()
        if path is None:
            return _missing_headers()
        parsed = emlx.parse_emlx_headers(path)
        return {
            "headers": dict(parsed.headers),
            "authentication_results": parsed.authentication_results,
            "reply_to": parsed.reply_to,
            "read": bool(parsed.read),
        }

    def attachments(self, uid: Any) -> list[dict[str, Any]]:
        """Ordered attachment metadata of one message.

        A readable ``.emlx`` lists one row per MIME attachment part (index 1..N
        in part order, original name, decoded size and availability). S/MIME
        messages (encrypted or signed) raise ``E_ATTACHMENT_UNREADABLE`` — a
        message-level signal: ``show`` returns ``[]`` and ``attachment`` reports
        it before "no attachments". A missing or unreadable body falls back to
        the ``Envelope Index`` names, with ``unavailable_reason="not_local"``.
        ``.partial.emlx`` parts are externalized: their file is resolved
        best-effort (``unsupported`` when it cannot be verified). Never writes:
        only reads the store.
        """
        native_uid = _native_uid(uid)
        found = self.find_message(native_uid)
        if found is None:
            return []
        row, _mailbox = found
        path = _emlx_path(self.store, self._physical_mailbox(row), native_uid)
        if path is None:
            return _stored_attachment_rows(self.connection, self.tables, native_uid)
        parsed = emlx.parse_attachments(path, native_uid=native_uid)
        if parsed.smime is not None:
            raise _smime_unreadable(native_uid)
        if not parsed.readable:
            return _stored_attachment_rows(self.connection, self.tables, native_uid)
        return [
            {
                "index": item.index,
                "name": item.name,
                "size_bytes": item.size_bytes,
                "native_order_key": item.native_order_key,
                "unavailable_reason": item.unavailable_reason,
            }
            for item in parsed.items
        ]

    def attachment_stream(self, uid: Any, index: int) -> Iterable[bytes]:
        """Decoded bytes of attachment ``index`` of one message.

        Reads the local ``.emlx`` (or the verifiable externalized file of a
        ``.partial.emlx``) and yields decoded chunks; never writes and never
        triggers a download. A read failure raises
        :class:`mailquery.emlx.AttachmentReadError`, whose ``reason`` the core
        maps to ``E_ATTACHMENT_UNAVAILABLE``/``E_ATTACHMENT_UNREADABLE``.
        """
        native_uid = _native_uid(uid)
        found = self.find_message(native_uid)
        if found is None:
            raise emlx.AttachmentReadError("not_local", "the message does not exist")
        row, _mailbox = found
        path = _emlx_path(self.store, self._physical_mailbox(row), native_uid)
        if path is None:
            raise emlx.AttachmentReadError("not_local", "the .emlx file is missing")
        yield from emlx.attachment_stream(path, int(index), native_uid=native_uid)

    @staticmethod
    def parse_uid(raw: Any) -> int:
        """Validate the ``show`` uid of Apple Mail: an integer.

        Pure and offline: ``cli`` calls it before it creates the home, reads the
        config or opens the store. ``0`` and negative integers are valid uids
        that simply do not exist (``show`` reports them as not found).
        """
        text = raw if isinstance(raw, str) else str(raw)
        if _UID_PATTERN.fullmatch(text) is None:
            raise usage_error(
                f"invalid uid {raw!r}: expected an integer",
                "uids are integers; run `mailquery search` to find the uid of a message",
                "invalid uid: expected an integer",
            )
        return int(text)

    @staticmethod
    def parse_native_id(native_id: str) -> int:
        """Validate the native part of a prefixed uid: an integer.

        Pure and offline. The core splits ``"<driver>:<native_id>"`` at the first
        ``:`` and hands only ``native_id`` to the adapter; ``0`` and negative
        integers are valid uids that simply do not exist.
        """
        if not isinstance(native_id, str) or _UID_PATTERN.fullmatch(native_id) is None:
            raise usage_error(
                f"invalid uid part {native_id!r}: expected an integer",
                "Apple Mail uids are integers; run `mailquery search` to find the uid "
                "of a message",
                "invalid uid part: expected an integer",
            )
        return int(native_id)

    def doctor_checks(self) -> list[dict[str, Any]]:
        """``store``, ``envelope_index``, ``schema``, ``readonly_strategy``, ``accounts_db``.

        Dependencies: ``envelope_index`` needs
        ``store``; ``schema`` and ``readonly_strategy`` need ``envelope_index``.
        The store opened for the checks is closed before returning; the
        resolution of ``[scope]`` blocks (``config``) is a common check.
        """
        checks: list[dict[str, Any]] = []

        def record(name: str, ok: bool, detail: str) -> None:
            checks.append({"name": name, "ok": bool(ok), "detail": str(detail)})

        mail_root = self._mail_root
        if mail_root is None and self._store is not None:
            mail_root = getattr(getattr(self._store, "version", None), "mail_root", None)

        # store ------------------------------------------------------------------
        version = None
        try:
            version = detect_version(mail_root)
            record("store", True, f"{version.version} at {version.mail_root}")
        except Exception as exc:  # noqa: BLE001 - diagnostics only
            record("store", False, error_detail(exc))

        # envelope_index ---------------------------------------------------------
        envelope_ok = False
        if version is None:
            record("envelope_index", False, "not evaluated: store failed")
        else:
            try:
                probe_envelope_index(version, tmp_root=self._tmp_root)
                envelope_ok = True
                record("envelope_index", True, str(version.envelope_index))
            except Exception as exc:  # noqa: BLE001 - diagnostics only
                record("envelope_index", False, error_detail(exc))

        # schema + readonly_strategy --------------------------------------------
        if not envelope_ok:
            record("schema", False, "not evaluated: envelope_index failed")
            record("readonly_strategy", False, "not evaluated: envelope_index failed")
        else:
            store = None
            store_open_error: Exception | None = None
            try:
                store = open_store(mail_root=mail_root, tmp_root=self._tmp_root)
            except Exception as exc:  # noqa: BLE001 - diagnostics only
                store_open_error = exc

            if store is None:
                detail = error_detail(store_open_error) if store_open_error else "store is not open"
                record("schema", False, detail)
                record("readonly_strategy", False, detail)
            else:
                try:
                    fingerprint = store.fingerprint()
                    missing = [table for table, present in fingerprint.items() if not present]
                    if missing:
                        record("schema", False, f"missing tables: {', '.join(missing)}")
                    else:
                        record("schema", True, "all required tables present")
                except Exception as exc:  # noqa: BLE001 - diagnostics only
                    record("schema", False, error_detail(exc))
                strategy = getattr(store, "strategy", None) or _infer_readonly_strategy(version)
                record(
                    "readonly_strategy",
                    True,
                    f"{strategy}: Envelope Index opened read-only (mode=ro, query_only=ON)",
                )
                try:
                    store.close()
                except Exception:  # noqa: BLE001 - best effort
                    pass

        # accounts_db ------------------------------------------------------------
        try:
            labels = self._labels or AccountLabels(self._accounts_db, tmp_dir=self._tmp_root)
            if labels.available:
                count = len(labels.all())
                record("accounts_db", True, f"{count} account label(s) available")
            else:
                record(
                    "accounts_db",
                    False,
                    "Accounts4.sqlite unavailable; only UUID account identifiers work",
                )
        except Exception as exc:  # noqa: BLE001 - diagnostics only
            record("accounts_db", False, error_detail(exc))

        return checks

    def close(self) -> None:
        """Close the store's SQLite connection (and its temporary copy)."""
        if self._store is not None:
            self._store.close()

    # -- internals ---------------------------------------------------------- #

    def _physical_mailbox(self, row: MessageRow) -> "Mailbox | None":
        wanted = int(row["mailbox_id"])
        for candidate in self.store.mailboxes:
            if candidate.rowid == wanted:
                return candidate
        return None


# --------------------------------------------------------------------------- #
# Helpers of the adapter
# --------------------------------------------------------------------------- #


def _mailbox_row(mailbox: "Mailbox") -> MailboxRow:
    return {
        "id": mailbox.rowid,
        "account_uuid": mailbox.account_uuid,
        "name": mailbox.name,
        "path": mailbox.path,
        "url": mailbox.url,
        "is_inbox": bool(mailbox.is_inbox),
        "is_aggregate": bool(mailbox.is_aggregate),
        "total": int(mailbox.message_count),
        "unread": int(mailbox.unread_count),
    }


def _infer_readonly_strategy(version: Any) -> str:
    if version is None:
        return "unknown"
    try:
        shm = Path(f"{version.envelope_index}-shm")
        return "live_ro" if shm.exists() else "copy_ro"
    except Exception:  # pragma: no cover - defensive
        return "unknown"


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
        rows = run_query(
            connection,
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')",
        )
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
        values = run_query(connection, sql, params)
    except sqlite3.Error as exc:
        raise _query_error(exc) from exc
    return [_row_dict(value) for value in values]


def _row_dict(values: Sequence[Any]) -> dict:
    data = dict(zip(_ROW_COLUMNS, values))
    uid = int(data["uid"])
    return {
        "uid": uid,
        "native_order_key": str(uid),
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
            rows = run_query(connection, sql, chunk)
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
        rows = run_query(connection, sql, (int(uid),))
    except sqlite3.Error as exc:  # pragma: no cover - schema validated
        raise _query_error(exc) from exc
    return [str(row[0]) for row in rows if row[0]]


def _native_uid(uid: Any) -> int:
    """Native uid handed by the core (an ``int`` for Apple Mail)."""
    return uid if isinstance(uid, int) and not isinstance(uid, bool) else int(uid)


def _emlx_path(
    store: "EnvelopeStore", mailbox: "Mailbox | None", native_uid: int
) -> Path | None:
    """``.emlx`` path of one message; resolution failures are a miss."""
    if mailbox is None:  # pragma: no cover - the store maps every message row
        return None
    try:
        return emlx.resolve_path(store, mailbox, native_uid)
    except Exception:  # noqa: BLE001 - an unreadable store path is not local
        return None


def _stored_attachment_rows(
    connection: sqlite3.Connection, tables: frozenset[str], native_uid: int
) -> list[dict[str, Any]]:
    """``Envelope Index`` attachment names when the body cannot be read.

    The core reports them as ``not_local``: the names are known but the bytes
    cannot be recovered locally; ``show`` keeps ``W_ATTACHMENTS_UNAVAILABLE``.
    """
    names = _fetch_attachment_names(connection, tables, native_uid)
    return [
        {
            "index": index,
            "name": name,
            "size_bytes": None,
            "native_order_key": str(index),
            "unavailable_reason": "not_local",
        }
        for index, name in enumerate(names, start=1)
    ]


def _smime_unreadable(native_uid: int) -> MailqueryError:
    """``E_ATTACHMENT_UNREADABLE`` message-level signal of S/MIME messages."""
    return MailqueryError(
        "E_ATTACHMENT_UNREADABLE",
        f"message uid {native_uid} is S/MIME protected and cannot be extracted",
        "S/MIME attachments cannot be extracted",
        "message is S/MIME protected",
    )


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
            rows = run_query(connection, sql, chunk)
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
        rows = run_query(connection, sql, params)
    except sqlite3.Error as exc:  # pragma: no cover - schema validated
        raise _query_error(exc) from exc
    for global_id, count in rows:
        if global_id:
            counts[int(global_id)] = int(count)
    return counts


# --------------------------------------------------------------------------- #
# ``.emlx`` bodies
# --------------------------------------------------------------------------- #


def _load_emlx(
    store: "EnvelopeStore", mailbox: "Mailbox | None", uid: int
) -> tuple[Any, Any, list[str]]:
    """Resolve and parse one ``.emlx``, turning failures into warnings."""
    warnings: list[str] = []
    if mailbox is None:  # pragma: no cover - defensive, the store maps every row
        warnings.append(f"W_BODY_UNREADABLE: no mailbox information for uid {uid}")
        return None, None, warnings
    try:
        path = emlx.resolve_path(store, mailbox, uid)
    except Exception as exc:
        warnings.append(
            f"W_BODY_UNREADABLE: cannot resolve the .emlx path for uid {uid} "
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
            f"W_BODY_UNREADABLE: cannot read the .emlx for uid {uid} "
            f"({type(exc).__name__})"
        )
        return None, path, warnings
    for warning in getattr(parsed, "warnings", ()) or ():
        if warning:
            warnings.append(str(warning))
    if not bool(getattr(parsed, "available", True)) and not _has_warning(
        warnings, "W_BODY_UNREADABLE", "W_EMLX_MISSING"
    ):
        warnings.append(f"W_BODY_UNREADABLE: the .emlx for uid {uid} is not available")
    if not bool(getattr(parsed, "readable", True)) and not _has_warning(
        warnings, "W_EMLX_CORRUPT", "W_BODY_UNREADABLE"
    ):
        warnings.append(f"W_EMLX_CORRUPT: the .emlx for uid {uid} could not be parsed")
    return parsed, path, warnings


def _missing_headers() -> HeaderRow:
    """Header row of a message whose ``.emlx`` cannot be resolved."""
    return {
        "headers": {name: "" for name in emlx.HEADER_NAMES},
        "authentication_results": None,
        "reply_to": None,
        "read": False,
    }


# --------------------------------------------------------------------------- #
# Small utilities
# --------------------------------------------------------------------------- #


def _chunks(items: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _has_warning(warnings: Sequence[str], *codes: str) -> bool:
    return any(
        any(str(warning).startswith(code) for code in codes) for warning in warnings
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

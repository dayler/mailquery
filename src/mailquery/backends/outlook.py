"""Classic Outlook backend (Windows).

Implemented: the connection (``describe``), ``name``, ``labels_available``,
``parse_uid`` and ``parse_native_id`` (uid validation), ``close``, the watchdog
``bind_command`` hook, the stores of the profile (``accounts``,
``excluded_stores``), their folders (``mailboxes``, ``resolve_mailbox``), their
items (``query``, ``membership``, ``duplicate_counts``, ``recipients``,
``attachment_names``, ``find_message``) and their bodies (``load_body`` plus the
``show`` hooks ``not_found_hint`` and ``unreadable_attachments``). Folder
counters are read only by ``mailboxes`` (core hook
``mailboxes_without_counters``). The ``search`` hooks ``recipients_open_items``,
``items_opened`` and ``load_snippet`` serve the bounded ``--text``/``--to``/``--cc``
scan. ``doctor_checks`` and the watchdog hook ``bind_doctor_timeout`` serve
``doctor``. ``attachments``/``attachment_stream`` implement the backend attachment
protocol: ordered local metadata, availability
reasons and the COM materialization exception (``Attachment.SaveAsFile`` into the
core staging, always removed). Every COM access goes through
:mod:`mailquery.backends.outlook_com` (the only module that imports pywin32),
so this module imports on any OS.
"""

from __future__ import annotations

import math
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence
from urllib.parse import quote, unquote

from mailquery import output
from mailquery.backends import outlook_com
from mailquery.backends.base import (
    AttachmentMetadataRow,
    BodyRow,
    ExcludedStoreError,
    MailBackend,
    MailboxRow,
    MessageRow,
    AccountRow,
    Uid,
)
from mailquery.errors import MailqueryError, error_detail, usage_error
from mailquery.plugins import PLUGIN_API, Capabilities

BACKEND_NAME = "outlook"
STRATEGY = "com_readonly"

_UID_PATTERN = re.compile(r"[0-9A-F]+")

# OlAccountType
OL_EXCHANGE = 0
OL_IMAP = 1
OL_POP3 = 2
OL_HTTP = 3
OL_EAS = 4
OL_OTHER_ACCOUNT = 5
#: Label prefix of each account type; unknown types are "Other".
ACCOUNT_KINDS = {
    OL_EXCHANGE: "Exchange",
    OL_IMAP: "IMAP",
    OL_POP3: "POP3",
    OL_HTTP: "HTTP",
    OL_EAS: "EAS",
    OL_OTHER_ACCOUNT: "Other",
}
#: Account types whose delivery store is a local data file (candidates unless on the network).
FILE_ACCOUNT_TYPES = frozenset({OL_IMAP, OL_POP3, OL_EAS})

# OlExchangeStoreType
OL_EXCHANGE_MAILBOX = 1  # delegate / shared mailbox
OL_EXCHANGE_PUBLIC_FOLDER = 2
OL_NOT_EXCHANGE = 3

PROPTAG = "http://schemas.microsoft.com/mapi/proptag/0x"
PR_RECORD_KEY = PROPTAG + "0FF90102"
PR_FOLDER_TYPE = PROPTAG + "36010003"
PR_MESSAGE_FLAGS = PROPTAG + "0E070003"
PR_MSG_STATUS = PROPTAG + "0E170003"
# Item properties.
PR_LONGTERM_ENTRYID_FROM_TABLE = PROPTAG + "66700102"
PR_MESSAGE_DELIVERY_TIME = PROPTAG + "0E060040"
PR_CLIENT_SUBMIT_TIME = PROPTAG + "00390040"
PR_SUBJECT = PROPTAG + "0037001F"
PR_SENDER_NAME = PROPTAG + "0C1A001F"
PR_SENDER_SMTP_ADDRESS = PROPTAG + "5D01001F"
PR_SENDER_EMAIL_ADDRESS = PROPTAG + "0C1F001F"
PR_SENDER_ADDRTYPE = PROPTAG + "0C1E001F"
PR_FLAG_STATUS = PROPTAG + "10900003"
PR_MESSAGE_SIZE = PROPTAG + "0E080003"
PR_INTERNET_MESSAGE_ID = PROPTAG + "1035001F"
PR_HASATTACH = PROPTAG + "0E1B000B"
PID_LID_SMART_NO_ATTACH = (
    "http://schemas.microsoft.com/mapi/id/{00062008-0000-0000-C000-000000000046}/8514000B"
)
PR_SMTP_ADDRESS = PROPTAG + "39FE001F"
PR_ADDRTYPE = PROPTAG + "3002001F"
PR_EMAIL_ADDRESS = PROPTAG + "3003001F"
PR_ATTACHMENT_HIDDEN = PROPTAG + "7FFE000B"
PR_TRANSPORT_MESSAGE_HEADERS = PROPTAG + "007D001F"

#: Headers of ``show``, read from the transport headers when present.
SHOW_HEADER_NAMES = ("From", "To", "Cc", "Subject", "Date", "Message-ID")
#: Warnings of ``load_body`` and ``show``.
SMIME_ENCRYPTED_WARNING = "W_BODY_UNREADABLE: S/MIME encrypted content is not supported"
SMIME_SIGNED_WARNING = "W_BODY_UNREADABLE: S/MIME signed content is not supported"
HTML_NO_TEXT_WARNING = "W_HTML_NO_TEXT: HTML body produced no plain text"
ATTACHMENTS_UNAVAILABLE_WARNING = (
    "W_ATTACHMENTS_UNAVAILABLE: the message has attachments, but their names cannot "
    "be read because the item could not be read"
)
#: Hint of ``show`` when a uid is not found.
NOT_FOUND_HINT = (
    "run `mailquery search` to find the uid; a message of a store that is not read "
    "is not found: see excluded_stores in `mailquery mailboxes`"
)

#: Columns added to an item table, in this order, after the default ones; the
#: same properties (except the table-only long-term EntryID) are read from an
#: opened item by ``find_message``.
MESSAGE_COLUMNS = (
    PR_LONGTERM_ENTRYID_FROM_TABLE,
    PR_MESSAGE_DELIVERY_TIME,
    PR_CLIENT_SUBMIT_TIME,
    PR_SUBJECT,
    PR_SENDER_NAME,
    PR_SENDER_SMTP_ADDRESS,
    PR_SENDER_EMAIL_ADDRESS,
    PR_SENDER_ADDRTYPE,
    PR_MESSAGE_FLAGS,
    PR_FLAG_STATUS,
    PR_MESSAGE_SIZE,
    PR_INTERNET_MESSAGE_ID,
    PR_HASATTACH,
    PID_LID_SMART_NO_ATTACH,
    PR_MSG_STATUS,
)
#: Columns of the Message-ID count of ``duplicate_counts``.
DEDUPE_COLUMNS = (PR_INTERNET_MESSAGE_ID, PR_MSG_STATUS)
#: Columns of the folder counters of ``mailboxes``.
COUNTER_COLUMNS = (PR_MESSAGE_FLAGS, PR_MSG_STATUS)
#: Rows per ``Table.GetArray`` call (bulk read).
TABLE_CHUNK_ROWS = 1000

# Folder counters (read-only folder properties; equal to the item table rows and
# their unread ones, verified on the host).
PR_CONTENT_COUNT = PROPTAG + "36020003"
PR_CONTENT_UNREAD = PROPTAG + "36030003"
PR_MESSAGE_CLASS = PROPTAG + "001A001F"
#: DASL restriction matching the searchable classes of :func:`is_searchable_class`
#: (``=`` and ``LIKE`` on the class are case-insensitive, verified on the host).
SEARCHABLE_CLASS_RESTRICTION = (
    f"(\"{PR_MESSAGE_CLASS}\" = 'IPM.Note' OR \"{PR_MESSAGE_CLASS}\" LIKE 'IPM.Note.%' OR "
    f"\"{PR_MESSAGE_CLASS}\" = 'IPM.Schedule.Meeting' OR "
    f"\"{PR_MESSAGE_CLASS}\" LIKE 'IPM.Schedule.Meeting.%')"
)
#: Rows of a searchable class (Outlook keeps this positive restriction cached, so
#: counting it is cheap even on a large folder; ``NOT``/``<>`` restrictions are
#: evaluated again on every call: verified on the host).
SEARCHABLE_CLASS_FILTER = "@SQL=" + SEARCHABLE_CLASS_RESTRICTION
#: Rows of a searchable class whose ``PR_MSG_STATUS`` can hold the IMAP deletion mark
#: (DASL has no bit test; Python classifies these rows).
DELETION_CANDIDATES_FILTER = (
    f"@SQL={SEARCHABLE_CLASS_RESTRICTION} AND \"{PR_MSG_STATUS}\" >= 8"
)
#: Rows that may not be searchable: another class, or a ``PR_MSG_STATUS`` that can
#: hold the IMAP deletion mark (only for a folder with rows of other classes).
COUNTER_EXCEPTIONS_FILTER = (
    f"@SQL=(NOT {SEARCHABLE_CLASS_RESTRICTION}) OR "
    f"\"{PR_MSG_STATUS}\" >= 8"  # MSGSTATUS_DELMARKED: every value with the bit is >= 8
)

UNKNOWN_LABEL = "unknown"

# OlDefaultFolders: the inbox and the hidden sync folders, found by function.
OL_FOLDER_INBOX = 6
OL_FOLDER_CONFLICTS = 19
OL_FOLDER_SYNC_ISSUES = 20
OL_FOLDER_LOCAL_FAILURES = 21
OL_FOLDER_SERVER_FAILURES = 22
HIDDEN_DEFAULT_FOLDERS = (
    OL_FOLDER_CONFLICTS,
    OL_FOLDER_SYNC_ISSUES,
    OL_FOLDER_LOCAL_FAILURES,
    OL_FOLDER_SERVER_FAILURES,
)
OL_MAIL_ITEM = 0  # OlItemType of a mail folder (Folder.DefaultItemType)
FOLDER_SEARCH = 2  # PR_FOLDER_TYPE of a search folder
OL_USER_ITEMS = 0  # OlTableContents

#: Default columns of ``Folder.GetTable``; added ones follow them.
TABLE_DEFAULT_COLUMNS = ("EntryID", "Subject", "CreationTime", "LastModificationTime", "MessageClass")
_MESSAGE_CLASS_COLUMN = TABLE_DEFAULT_COLUMNS.index("MessageClass")
MSGFLAG_READ = 0x1
MSGSTATUS_DELMARKED = 0x8
FLAG_STATUS_FLAGGED = 2  # PR_FLAG_STATUS: 1 = completed, 2 = flagged
OL_HEADER_ONLY = 0  # Item.DownloadState
OL_TO = 1  # Recipient.Type (3 = Bcc, never reported)
OL_CC = 2

#: GetItemFromID failures meaning "no such item" and "the item cannot be opened".
ITEM_NOT_FOUND_HRESULTS = frozenset(
    {outlook_com.MAPI_E_NOT_FOUND, outlook_com.MAPI_E_INVALID_ENTRYID}
)
ITEM_UNOPENABLE_HRESULTS = frozenset({outlook_com.E_FAIL})

# OlDownloadState: only a full item keeps the attachment bytes in the local store.
OL_HEADER_ONLY = 0
OL_FULL_ITEM = 1
# OlAttachmentType: a by-value attachment is a copy of the file stored in the item;
# the other values are references, embedded messages or OLE objects (Microsoft docs).
OL_BY_VALUE = 1
OL_BY_REFERENCE = 4
OL_EMBEDDED_ITEM = 5
OL_OLE = 6
#: Staging directory under ``<home>/tmp`` shared with the core.
STAGING_DIR_NAME = "staging"
#: Bytes per chunk yielded by ``attachment_stream``.
_ATTACHMENT_CHUNK_BYTES = 64 * 1024
#: Templates of the attachment protocol errors of this driver.
_ATTACHMENT_SMIME_HINT = "S/MIME attachments cannot be extracted"
_DOWNLOAD_HINT = (
    "open the message in Outlook so it downloads the attachment, then retry"
)
#: A store's identifier inside an EntryID: 16 bytes from offset 4.
ENTRYID_STORE_KEY = slice(4, 20)
#: Margins of the DASL date pre-filter: Outlook ignores seconds, so it is
#: widened by whole minutes and the exact cut is done in Python.
FILTER_MARGIN_BEFORE = timedelta(minutes=1)
FILTER_MARGIN_AFTER = timedelta(minutes=2)
#: Opened items kept per command (the first ones opened, which are the newest
#: candidates in ``search`` order), so the page's recipients and bodies open each
#: item once. The maximum ``--limit`` fits.
ITEM_CACHE_SIZE = 200
_UNIX_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

INBOX = "INBOX"
URL_SCHEME = "outlook://"


#: Backend checks of ``doctor``, in report order.
DOCTOR_CHECKS = ("pywin32", "outlook", "stores", "readonly_strategy", "object_model_guard")
#: Checks that need Outlook, in evaluation order.
DOCTOR_COM_CHECKS = ("outlook", "readonly_strategy", "stores")
#: Direct dependency of each check; the others are independent.
DOCTOR_DEPENDENCIES = {"outlook": "pywin32", "readonly_strategy": "outlook", "stores": "outlook"}


def _not_evaluated(name: str, dependency: str) -> dict[str, Any]:
    return {"name": name, "ok": False, "detail": f"not evaluated: {dependency} failed"}


def _error_with_hint(exc: MailqueryError) -> str:
    """``CODE: message (hint: ...)``: the doctor detail of a detection error."""
    detail = error_detail(exc)
    return f"{detail} (hint: {exc.hint})" if exc.hint else detail


@dataclass
class StoreInfo:
    """One store of the profile, classified as candidate or excluded (only store-level data).

    ``reason`` is ``None`` for a candidate, else the ``excluded_stores`` reason.
    ``uuid`` is ``None`` only for an ``unavailable`` store (its ``PR_RECORD_KEY``
    could not be read). ``store`` is the proxy of a candidate store (``None``
    for an excluded one: nothing below store level is ever read from it).
    """

    position: int
    label: str
    path: str | None
    reason: str | None = None
    uuid: str | None = None
    record_key: bytes | None = None
    email: str | None = None
    kind: str | None = None
    local: bool = False
    store: outlook_com.ReadOnlyCom | None = None
    store_id: str | None = None

    def excluded_entry(self) -> dict[str, Any]:
        return {"label": self.label, "path": self.path, "reason": self.reason}


def is_searchable_class(message_class: Any) -> bool:
    """Mail (``IPM.Note`` and ``IPM.Note.*``, S/MIME included) or a meeting item.

    Every ``IPM.Schedule.Meeting.*`` class counts (requests, cancellations,
    responses); receipts (``IPM.Report.*``), tasks, posts and the rest do not.
    """
    if not isinstance(message_class, str):
        return False
    folded = message_class.casefold()
    return (
        folded == "ipm.note"
        or folded.startswith("ipm.note.")
        or folded == "ipm.schedule.meeting"
        or folded.startswith("ipm.schedule.meeting.")
    )


def is_smime_class(message_class: Any) -> bool:
    """S/MIME encrypted or signed mail (``IPM.Note.SMIME`` and ``IPM.Note.SMIME.*``)."""
    if not isinstance(message_class, str):
        return False
    folded = message_class.casefold()
    return folded == "ipm.note.smime" or folded.startswith("ipm.note.smime.")


def encode_segment(name: str) -> str:
    """A folder name as a ``path`` segment: ``%`` ⇒ ``%25``, then ``/`` ⇒ ``%2F``."""
    return name.replace("%", "%25").replace("/", "%2F")


def folder_url(account_uuid: str, names: Sequence[str]) -> str:
    """``outlook://<uuid>/<path>`` with each decoded segment percent-encoded (RFC 3986, UTF-8)."""
    return URL_SCHEME + account_uuid + "/" + "/".join(quote(name, safe="") for name in names)


def is_network_path(path: str) -> bool:
    """UNC path or a drive letter whose ``GetDriveTypeW`` is ``DRIVE_REMOTE``."""
    if path.startswith("\\\\"):
        return True
    if len(path) >= 2 and path[1] == ":":
        return outlook_com.get_drive_type(path[:2] + "\\") == outlook_com.DRIVE_REMOTE
    return False


class OutlookBackend(MailBackend):
    """Outlook through the read-only COM proxy; nothing is opened until first use.

    ``outlook_app``, ``registry``, ``security_center`` and ``pywin32`` are the
    test injection points (``outlook_app`` is the connector that
    stands in for ``win32com.client``). ``tmp_root`` is ``<home>/tmp``, where the
    pywin32 cache lives (``<tmp_root>/gen_py``); ``watchdog`` replaces the
    process-wide COM watchdog.
    """

    driver = BACKEND_NAME
    plugin_api = PLUGIN_API
    capabilities: Capabilities = {
        "network": False,
        "readonly": "structural",
        "body_local": True,
        "attachments": "local",
        "native_order": "text",
    }

    def __init__(
        self,
        *,
        outlook_app: Any = None,
        registry: Any = None,
        security_center: Any = None,
        pywin32: bool | None = None,
        tmp_root: Path | None = None,
        watchdog: outlook_com.Watchdog | None = None,
    ) -> None:
        self._outlook_app = outlook_app
        self._registry = registry
        self._security_center = security_center
        self._pywin32 = pywin32
        self._tmp_root = Path(tmp_root) if tmp_root is not None else None
        self._watchdog = watchdog if watchdog is not None else outlook_com.WATCHDOG
        self._application: outlook_com.ReadOnlyCom | None = None
        self._stores: list[StoreInfo] | None = None
        #: Listed folders of each candidate store walked so far, by store position.
        self._store_folders: dict[int, list[MailboxRow]] = {}
        #: Folder proxy of each listed mailbox, by its ``id`` (the folder ``EntryID``).
        self._folder_objects: dict[str, outlook_com.ReadOnlyCom] = {}
        #: ``(total, unread)`` of each listed mailbox counted so far, by its ``id``.
        self._counters: dict[str, tuple[int, int]] = {}
        #: Folder ``id`` of each uid returned by ``query``/``find_message``.
        self._uid_folders: dict[str, str] = {}
        #: Dedupe key of each Internet Message-ID (``global_message_id`` > 0).
        self._message_keys: dict[str, int] = {}
        #: ``GetItemFromID`` result (item or :data:`_UNOPENABLE`) of the first
        #: :data:`ITEM_CACHE_SIZE` uids opened, plus the last one opened.
        self._items: dict[str, Any] = {}
        self._last_item: tuple[str, Any] | None = None
        #: Uids whose item was opened (``scan.messages_read``).
        self._opened: set[str] = set()
        #: ``recipients`` result of each uid read so far.
        self._recipient_cache: dict[str, dict[str, list[dict[str, str]]]] = {}
        #: ``doctor`` progress: finished checks by name and the running one.
        self._doctor_done: dict[str, dict[str, Any]] = {}
        self._doctor_running: str | None = None
        #: Attachment staging sessions of this instance, removed on ``close`` too
        #: (an aborted extraction may leave the generator suspended before its
        #: ``finally`` runs; the next run sweeps them as well).
        self._attachment_sessions: set[Path] = set()

    # -- connection ---------------------------------------------------------- #

    def bind_command(self, command: str) -> None:
        """Name the running command for the COM watchdog (its timeout JSON reports it)."""
        self._watchdog.command = command

    def _app(self) -> outlook_com.ReadOnlyCom:
        """The read-only Application proxy; detection runs on first use."""
        if self._application is None:
            gen_path = self._tmp_root / "gen_py" if self._tmp_root is not None else None
            self._application = outlook_com.connect(
                outlook_app=self._outlook_app,
                registry=self._registry,
                pywin32=self._pywin32,
                gen_path=gen_path,
                watchdog=self._watchdog,
            )
        return self._application

    # -- stores -------------------------------------------------------------- #

    def _profile(self) -> list[StoreInfo]:
        """Every store of the profile in ``NameSpace.Stores`` order, classified once."""
        if self._stores is None:
            session = self._app().Session
            delivery = _delivery_accounts(session)
            stores = session.Stores
            self._stores = [
                _classify_store(stores, position, delivery)
                for position in range(1, stores.Count + 1)
            ]
        return self._stores

    # -- folders ------------------------------------------------------------- #

    def _folders(self, account_uuids: Sequence[str] | None = None) -> list[MailboxRow]:
        """Listed folders of the candidate stores (all, or those of ``account_uuids``).

        Each store is walked once per backend, and only when one of its folders
        is needed (excluded stores never). Walking reads no item table:
        ``total``/``unread`` are ``None`` here and only :meth:`mailboxes` counts
        them.
        """
        wanted = (
            None
            if account_uuids is None
            else {str(uuid).casefold() for uuid in account_uuids if uuid}
        )
        rows: list[MailboxRow] = []
        for info in self._profile():
            if info.reason is not None or info.store is None or info.uuid is None:
                continue
            if wanted is None or info.uuid.casefold() in wanted:
                rows.extend(self._walked(info))
        return rows

    def _walked(self, info: StoreInfo) -> list[MailboxRow]:
        """Listed folders of one candidate store, walked on first use."""
        rows = self._store_folders.get(info.position)
        if rows is None:
            rows = []
            assert info.store is not None and info.uuid is not None
            _walk_store(info.uuid, info.store, rows, self._folder_objects)
            self._store_folders[info.position] = rows
        return rows

    def _folder_object(self, mailbox_id: Any) -> outlook_com.ReadOnlyCom | None:
        """Folder proxy of a listed mailbox ``id``; walks every candidate store if unknown."""
        folder = self._folder_objects.get(mailbox_id)
        if folder is None:
            self._folders()
            folder = self._folder_objects.get(mailbox_id)
        return folder

    # -- items --------------------------------------------------------------- #

    def _message_key(self, message_id: Any) -> int:
        """Dedupe key of an Internet Message-ID; ``0`` (unique) when missing or empty."""
        text = _text(message_id)
        if not text:
            return 0
        return self._message_keys.setdefault(text, len(self._message_keys) + 1)

    def _message_row(
        self, uid: str, props: dict[str, Any], mailbox_id: str, message_class: Any
    ) -> MessageRow:
        """Common-model row from the item properties (a table row or an opened item)."""
        message_id = _text(props.get(PR_INTERNET_MESSAGE_ID))
        return MessageRow(
            uid=uid,
            native_order_key=uid,
            global_message_id=self._message_key(message_id),
            subject=_text(props.get(PR_SUBJECT)),
            sender_name=_text(props.get(PR_SENDER_NAME)),
            sender_address=_smtp_address(
                props.get(PR_SENDER_SMTP_ADDRESS),
                props.get(PR_SENDER_EMAIL_ADDRESS),
                props.get(PR_SENDER_ADDRTYPE),
            ),
            date_sent=_utc_epoch(props.get(PR_CLIENT_SUBMIT_TIME)),
            date_received=_utc_epoch(props.get(PR_MESSAGE_DELIVERY_TIME)),
            mailbox_id=mailbox_id,
            read=1 if _as_int(props.get(PR_MESSAGE_FLAGS)) & MSGFLAG_READ else 0,
            flagged=1 if props.get(PR_FLAG_STATUS) == FLAG_STATUS_FLAGGED else 0,
            size=_as_int(props.get(PR_MESSAGE_SIZE)),
            message_id=message_id,
            has_attachments=props.get(PR_HASATTACH) is True
            and props.get(PID_LID_SMART_NO_ATTACH) is not True,
            message_class=_text(message_class),
        )

    def _store_of(self, uid: str, *, candidate: bool) -> StoreInfo | None:
        """Candidate (or excluded) store whose ``PR_RECORD_KEY`` is in the uid.

        Only store-level data is compared; an unreadable store has no record key
        and never matches (its uids are "not found").
        """
        try:
            key = bytes.fromhex(uid)[ENTRYID_STORE_KEY]
        except ValueError:
            return None
        if len(key) != 16:
            return None
        for info in self._profile():
            if (info.reason is None) == candidate and info.record_key == key:
                return info
        return None

    def _open_item(self, uid: str, info: StoreInfo | None = None) -> Any:
        """``GetItemFromID`` on the uid's candidate store.

        ``None`` when the store or the item does not exist, :data:`_UNOPENABLE`
        when the item exists but cannot be opened; other COM errors propagate.
        Each uid is opened once per command while it stays cached (the first
        :data:`ITEM_CACHE_SIZE` uids and the last one).
        """
        if uid in self._items:
            return self._items[uid]
        if self._last_item is not None and self._last_item[0] == uid:
            return self._last_item[1]
        info = info if info is not None else self._store_of(uid, candidate=True)
        if info is None or not info.store_id:
            return None
        try:
            item = self._app().Session.GetItemFromID(uid, info.store_id)
        except outlook_com.ComCallError as exc:
            if exc.hresult in ITEM_NOT_FOUND_HRESULTS:
                return None
            if exc.hresult not in ITEM_UNOPENABLE_HRESULTS:
                raise
            item = _UNOPENABLE
        else:
            self._opened.add(uid)
        if len(self._items) < ITEM_CACHE_SIZE:
            self._items[uid] = item
        self._last_item = (uid, item)
        return item

    def _find_in_tables(
        self, uid: str, listed: dict[str, MailboxRow]
    ) -> tuple[MessageRow, MailboxRow] | None:
        """Row of an item that cannot be opened, from the tables of its store's listed folders."""
        for mailbox_id, mailbox in listed.items():
            folder = self._folder_objects.get(mailbox_id)
            if folder is None:
                continue
            for message_class, props in _table_rows(folder, "", MESSAGE_COLUMNS):
                if _hex(props[PR_LONGTERM_ENTRYID_FROM_TABLE]) != uid:
                    continue
                if not _is_searchable(message_class, props):
                    return None
                self._uid_folders[uid] = mailbox_id
                row = self._message_row(uid, props, mailbox_id, message_class)
                return row, MailboxRow(**mailbox)
        return None

    # -- backend protocol ---------------------------------------------------- #

    def describe(self) -> dict[str, Any]:
        """Version and strategy for the connection log line (connects to Outlook)."""
        return {
            "backend": BACKEND_NAME,
            "version": self._app().Version,
            "strategy": STRATEGY,
            "schema_ok": True,
        }

    def accounts(self) -> list[AccountRow]:
        """Every store of the profile as an account row, in profile order.

        Candidates are ``{uuid, label, email, local}`` (``local``: a PST, which
        belongs to no account). Excluded stores come too, with the extra key
        ``excluded`` holding their :meth:`excluded_stores` entry, so that a
        ``[scope]`` key can resolve to them; an ``unavailable`` one
        has ``uuid: None`` and resolves by label only.
        """
        rows: list[AccountRow] = []
        for info in self._profile():
            row: AccountRow = {
                "uuid": info.uuid,  # None only for an unavailable (excluded) store
                "label": info.label,
                "email": info.email,
                "local": info.local,
            }
            if info.reason is not None:
                row["excluded"] = info.excluded_entry()
            rows.append(row)
        return rows

    @property
    def labels_available(self) -> bool:
        return True

    def mailboxes(self) -> list[MailboxRow]:
        """Mail folders of the candidate stores: stores in profile order, folders depth-first.

        ``id`` is the folder ``EntryID``; ``total``/``unread`` count the
        searchable items read from the folder table, once per
        folder and backend.
        """
        rows: list[MailboxRow] = []
        for row in self._folders():
            counters = self._counters.get(row["id"])
            if counters is None:
                counters = _count_searchable(self._folder_objects[row["id"]])
                self._counters[row["id"]] = counters
            rows.append(MailboxRow(**{**row, "total": counters[0], "unread": counters[1]}))
        return rows

    def excluded_stores(self) -> list[dict[str, Any]]:
        """``[{label, path, reason}]`` of the excluded stores, in profile order."""
        return [info.excluded_entry() for info in self._profile() if info.reason is not None]

    def resolve_mailbox(self, account_uuid: str, ref: str) -> MailboxRow | None:
        """Folder of one account for ``ref``, case-insensitive, or ``None``.

        ``INBOX`` is always the store's inbox (``None`` for a store without
        one); otherwise an exact ``path`` or URL (also percent-decoded) beats a
        ``name``, and among several name matches the first of ``mailboxes()``
        wins. References are compared with the listed (encoded) form.
        """
        needle = str(ref or "").strip()
        if not needle:
            return None
        folded = needle.casefold()
        account = str(account_uuid or "").casefold()
        candidates = [
            row for row in self._folders([account]) if row["account_uuid"].casefold() == account
        ]
        found: MailboxRow | None = None
        if folded == INBOX.casefold():
            found = next((row for row in candidates if row["is_inbox"]), None)
        else:
            found = next(
                (
                    row
                    for row in candidates
                    if folded
                    in (row["path"].casefold(), row["url"].casefold(), unquote(row["url"]).casefold())
                ),
                None,
            ) or next((row for row in candidates if folded == row["name"].casefold()), None)
        return MailboxRow(**found) if found is not None else None

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
        """Searchable items of the folders, read from ``Folder.GetTable``.

        No item is opened. ``uid`` is the permanent EntryID, dates come
        from the MAPI UTC properties; the DASL date pre-filter is widened
        by whole minutes and ``since`` (inclusive) / ``until`` (exclusive) are cut
        to the second here. Total order ``(date_received, uid)``, ``uid``
        compared as a string; ``order="desc"`` reverses it.
        """
        filter_text = _date_filter(since, until)
        rows: list[MessageRow] = []
        for mailbox_id in dict.fromkeys(mailbox_ids):
            folder = self._folder_object(mailbox_id)
            if folder is None:
                continue
            for message_class, props in _table_rows(folder, filter_text, MESSAGE_COLUMNS):
                if not _is_searchable(message_class, props):
                    continue
                uid = _hex(props[PR_LONGTERM_ENTRYID_FROM_TABLE])
                if not uid:
                    continue
                row = self._message_row(uid, props, mailbox_id, message_class)
                received = row["date_received"]
                if since is not None and (received is None or received < since):
                    continue
                if until is not None and (received is None or received >= until):
                    continue
                if (unread and row["read"]) or (flagged and not row["flagged"]):
                    continue
                if has_attachments and not row["has_attachments"]:
                    continue
                self._uid_folders[uid] = mailbox_id
                rows.append(row)
        rows.sort(key=_order_key, reverse=order == "desc")
        return rows

    def membership(self, uids: Sequence[Uid]) -> dict[Uid, set[Any]]:
        """The folder of each known uid: an Outlook item lives in exactly one folder."""
        return {
            uid: {self._uid_folders[uid]} for uid in dict.fromkeys(uids) if uid in self._uid_folders
        }

    def duplicate_counts(self, mailbox_ids: Sequence[Any]) -> dict[Any, int]:
        """Searchable copies per Internet Message-ID in the folders.

        A missing or empty Message-ID has no key: the message is unique.
        """
        counts: dict[int, int] = {}
        for mailbox_id in dict.fromkeys(mailbox_ids):
            folder = self._folder_object(mailbox_id)
            if folder is None:
                continue
            for message_class, props in _table_rows(folder, "", DEDUPE_COLUMNS):
                if not _is_searchable(message_class, props):
                    continue
                key = self._message_key(props[PR_INTERNET_MESSAGE_ID])
                if key:
                    counts[key] = counts.get(key, 0) + 1
        return counts

    def recipients(self, uids: Sequence[Uid]) -> dict[Uid, Any]:
        """``{uid: {"to": [...], "cc": [...]}}`` from each opened item.

        The address is the SMTP address the item carries (``PR_SMTP_ADDRESS``,
        else ``PR_EMAIL_ADDRESS`` only when the address type is SMTP), never an
        Exchange DN and never the address book; without one it is ``""`` and the
        name is kept. Bcc is not reported. Items that cannot be found or opened
        are left out. Each item's recipients are read once per command.
        """
        result: dict[Uid, Any] = {}
        for uid in dict.fromkeys(uids):
            cached = self._recipient_cache.get(str(uid))
            if cached is not None:
                result[uid] = cached
                continue
            item = self._open_item(str(uid))
            if item is None or item is _UNOPENABLE:
                continue
            bucket: dict[str, list[dict[str, str]]] = {"to": [], "cc": []}
            recipients = item.Recipients
            for position in range(1, recipients.Count + 1):
                recipient = recipients.Item(position)
                kind = recipient.Type
                if kind not in (OL_TO, OL_CC):
                    continue
                entry = {
                    "name": _text(recipient.Name),
                    "address": _recipient_address(recipient.PropertyAccessor),
                }
                bucket["to" if kind == OL_TO else "cc"].append(entry)
            self._recipient_cache[str(uid)] = bucket
            result[uid] = bucket
        return result

    def attachment_names(self, uid: Uid) -> list[str]:
        """Names of the visible attachments of one item (hidden ones are never listed).

        Nothing is read from an S/MIME item or a header-only one (its content is
        not local), nor from one that cannot be found or opened: ``[]``.
        """
        item = self._open_item(str(uid))
        if item is None or item is _UNOPENABLE:
            return []
        if is_smime_class(item.MessageClass) or item.DownloadState == OL_HEADER_ONLY:
            return []
        return _visible_attachment_names(item)

    def attachments(self, uid: Uid) -> list[AttachmentMetadataRow]:
        """Ordered attachment metadata of one message.

        Only **local properties** of the item are read (``Attachments``,
        ``FileName``/``DisplayName``, ``Size`` and ``Type``): nothing is downloaded
        and no network is used. ``index`` is the 1-based order of the visible
        attachments (hidden ones are never listed) and is shared by ``show`` and
        ``attachment``; ``native_order_key`` is the index as upper-case hex text.

        Availability, according to the attachment type (``OlAttachmentType``):
        a by-value copy is local; a by-reference attachment is not stored in the
        message and would have to be fetched from its origin ⇒ ``not_downloaded``;
        a web reference/embedded message/OLE object is not a recoverable file ⇒
        ``unsupported``. ``size_bytes`` is ``None`` when it is not local.

        A message-level signal is raised as the
        ``E_ATTACHMENT_UNREADABLE`` protocol error: S/MIME, an unopenable item, or
        a not fully downloaded item that reports attachments (its names cannot be
        read without downloading). ``show`` turns it into ``attachments: []``;
        ``attachment`` propagates it before the “no attachments” check.
        """
        item = self._attachment_item(uid)
        if is_smime_class(item.MessageClass):
            raise _attachment_unreadable_error(
                "the message is S/MIME protected and cannot be extracted",
                _ATTACHMENT_SMIME_HINT,
            )
        if item.DownloadState != OL_FULL_ITEM:
            if _attachment_signal(item):
                raise _attachment_unreadable_error(
                    "the attachments are not available in the local store and "
                    "cannot be listed without downloading the message",
                    _DOWNLOAD_HINT,
                )
            return []
        rows: list[AttachmentMetadataRow] = []
        for index, attachment in enumerate(_visible_attachments(item), start=1):
            name = _text(attachment.FileName) or _text(attachment.DisplayName)
            reason = _attachment_unavailable_reason(attachment)
            rows.append(
                AttachmentMetadataRow(
                    index=index,
                    name=name,
                    size_bytes=None if reason is not None else _attachment_size(attachment),
                    native_order_key=f"{index:04X}",
                    unavailable_reason=reason,
                )
            )
        return rows

    def attachment_stream(self, uid: Uid, index: int) -> Iterator[bytes]:
        """Decoded bytes of attachment ``index`` of one message.

        Outlook has no local byte stream: the attachment is a COM object of an
        already-downloaded item. The single writing operation of the read-only
        proxy (``Attachment.SaveAsFile``) copies it to an opaque
        ``0600`` file inside a private ``0700`` session directory under
        ``<home>/tmp/staging``; this method validates that the materialized path is
        a regular file inside the session (a symlink or an unexpected directory is
        ``E_ATTACHMENT_UNAVAILABLE``/``unsupported``), yields the bytes in
        chunks and always removes the file and the session (also on errors,
        ``GeneratorExit`` and timeouts). It never resolves a reference and never
        downloads: unavailable attachments are refused before touching COM.
        """
        item = self._attachment_item(uid)
        if is_smime_class(item.MessageClass):
            raise _attachment_unreadable_error(
                "the message is S/MIME protected and cannot be extracted",
                _ATTACHMENT_SMIME_HINT,
            )
        if item.DownloadState != OL_FULL_ITEM:
            raise _attachment_unavailable_error(
                "not_downloaded",
                "the attachment is not available in the local store",
                _DOWNLOAD_HINT,
            )
        visible = _visible_attachments(item)
        position = int(index)
        if not 1 <= position <= len(visible):
            raise usage_error(
                f"attachment index {position} is out of range",
                "run `mailquery show` to list the attachment indexes",
                "attachment index out of range",
            )
        attachment = visible[position - 1]
        reason = _attachment_unavailable_reason(attachment)
        if reason is not None:
            raise _attachment_unavailable_error(
                reason,
                "the attachment is not available in the local store"
                if reason == "not_downloaded"
                else "the attachment cannot be recovered from the local store",
                _DOWNLOAD_HINT
                if reason == "not_downloaded"
                else "the attachment type cannot be materialized from the local store",
            )
        session = self._attachment_staging()
        path: Path | None = None
        try:
            path = _create_staging_file(session)
            _materialize(attachment, path, session)
            with path.open("rb") as handle:
                while True:
                    chunk = handle.read(_ATTACHMENT_CHUNK_BYTES)
                    if not chunk:
                        break
                    yield chunk
        finally:
            if path is not None:
                _unlink_quietly(path)
            shutil.rmtree(session, ignore_errors=True)
            self._attachment_sessions.discard(session)

    def _attachment_item(self, uid: Uid) -> Any:
        """Opened item for the attachment operations; protocol errors when unusable."""
        text = str(uid)
        info = self._store_of(text, candidate=True)
        if info is None:
            excluded = self._store_of(text, candidate=False)
            if excluded is not None:
                raise ExcludedStoreError(excluded.excluded_entry())
            raise usage_error(
                "the message was not found", "run `mailquery search` to find the uid"
            )
        item = self._open_item(text, info)
        if item is None:
            raise usage_error(
                "the message was not found", "run `mailquery search` to find the uid"
            )
        if item is _UNOPENABLE:
            raise _attachment_unreadable_error(
                "the message cannot be read",
                "open the message in Outlook and retry; run `mailquery doctor` if it persists",
            )
        return item

    def _attachment_staging(self) -> Path:
        """Private ``0700`` session directory under ``<home>/tmp/staging``."""
        tmp_root = self._tmp_root
        if tmp_root is None:  # pragma: no cover - cli always passes <home>/tmp
            raise MailqueryError(
                "E_INTERNAL",
                "the Outlook backend has no staging directory (tmp_root is not set)",
                "run `mailquery doctor` and report this bug with the log file",
            )
        root = Path(tmp_root) / STAGING_DIR_NAME
        try:
            root.mkdir(parents=True, exist_ok=True)
            if os.name != "nt":
                os.chmod(root, 0o700)
            # Remove only this driver's own sessions left by a crashed/hung run
            # (the core sweeps its own session-* directories).
            for leftover in root.glob("outlook-*"):
                if leftover.is_dir() and not leftover.is_symlink():
                    shutil.rmtree(leftover, ignore_errors=True)
            session = Path(tempfile.mkdtemp(prefix="outlook-", dir=root))
            self._attachment_sessions.add(session)
            return session
        except PermissionError as exc:
            raise MailqueryError(
                "E_PERMISSION",
                "cannot create the attachment staging directory",
                "check the permissions of ~/.mailquery/tmp",
                "cannot create the attachment staging directory",
            ) from exc
        except OSError as exc:
            raise MailqueryError(
                "E_IO",
                f"cannot create the attachment staging directory ({exc.strerror or exc})",
                "check the free space and permissions of ~/.mailquery/tmp",
                "cannot create the attachment staging directory",
            ) from exc

    def find_message(self, uid: Uid) -> tuple[MessageRow, MailboxRow | None] | None:
        """Row and listed folder of a uid of a candidate store, or ``None``.

        The store comes from the EntryID (bytes 4..20 = ``PR_RECORD_KEY``).
        A uid of an excluded store raises :class:`ExcludedStoreError`
        without opening anything of that store. Not found, not a searchable item,
        IMAP-deleted or outside the listed folders (hidden, calendar...) ⇒
        ``None``. An item that exists but cannot be opened gets its row from the
        folder tables of its store.
        """
        text = str(uid)
        info = self._store_of(text, candidate=True)
        if info is None:
            excluded = self._store_of(text, candidate=False)
            if excluded is not None:
                raise ExcludedStoreError(excluded.excluded_entry())
            return None
        listed = {row["id"]: row for row in self._walked(info)}
        item = self._open_item(text, info)
        if item is None:
            return None
        if item is _UNOPENABLE:
            return self._find_in_tables(text, listed)
        folder_id = item.Parent.EntryID
        mailbox = listed.get(folder_id)
        message_class = item.MessageClass
        if mailbox is None or not is_searchable_class(message_class):
            return None
        accessor = item.PropertyAccessor
        props = {schema: _get_property(accessor, schema) for schema in MESSAGE_COLUMNS[1:]}
        if _as_int(props[PR_MSG_STATUS]) & MSGSTATUS_DELMARKED:
            return None
        self._uid_folders[text] = folder_id
        return self._message_row(text, props, folder_id, message_class), MailboxRow(**mailbox)

    def load_body(self, row: MessageRow) -> BodyRow:
        """Body of one item, in this order (never downloads).

        1. S/MIME (the row's ``MessageClass``) ⇒ ``available=True``,
           ``readable=False`` and the S/MIME warning, without opening the item.
        2. Item not found or that cannot be opened ⇒ ``W_BODY_UNREADABLE``.
        3. Header-only item (``DownloadState``) ⇒ ``W_BODY_NOT_LOCAL``; nothing
           else of the item is read.
        4. ``Body``; if empty, ``HTMLBody`` converted to text (a meeting item has
           no ``HTMLBody``: no HTML); HTML without text ⇒ ``W_HTML_NO_TEXT``.
        5. Names of the visible attachments and the transport headers (missing
           for internal mail: ``{}``, and ``show`` synthesizes them).

        ``partial`` and ``source.partial`` are always ``False`` and
        ``source.emlx_path`` ``None``.
        """
        return self._load_body(row, details=True)

    def _load_body(self, row: MessageRow, *, details: bool) -> BodyRow:
        """:meth:`load_body`; without ``details`` no attachment or header is read."""
        uid = str(row.get("uid") or "")
        message_class = row.get("message_class")
        if is_smime_class(message_class):
            return _smime_body(message_class)
        item = self._open_item(uid) if uid else None
        if item is None:
            return _unavailable_body(f"W_BODY_UNREADABLE: the Outlook item for uid {uid} was not found")
        if item is _UNOPENABLE:
            return _unavailable_body(_unopenable_warning(uid))
        if message_class is None:
            message_class = item.MessageClass
            if is_smime_class(message_class):
                return _smime_body(message_class)
        try:
            if item.DownloadState == OL_HEADER_ONLY:
                return _unavailable_body(
                    f"W_BODY_NOT_LOCAL: only the headers of uid {uid} are stored locally; "
                    "the body is never downloaded"
                )
            body_text, warnings = _item_text(item)
            attachments: list[dict[str, str]] = []
            headers: dict[str, str] = {}
            if details:
                attachments = [{"name": name} for name in _visible_attachment_names(item)]
                headers = _parse_headers(
                    _get_property(item.PropertyAccessor, PR_TRANSPORT_MESSAGE_HEADERS)
                )
        except outlook_com.ComCallError as exc:
            if exc.hresult in ITEM_UNOPENABLE_HRESULTS:
                return _unavailable_body(_unopenable_warning(uid))
            raise
        return _body(True, True, headers, body_text, attachments, warnings)

    # -- core hooks (looked up with getattr; outside the backend protocol) --- #

    def mailboxes_without_counters(
        self, account_uuids: Sequence[str] | None = None
    ) -> list[MailboxRow]:
        """:meth:`mailboxes` without counting: ``total``/``unread`` are ``None``.

        ``config.listed_mailboxes`` uses it for everything but the ``mailboxes``
        command (scope resolution, dedupe, display), so ``search``, ``new`` and
        ``show`` read no table of a folder outside the query.
        With ``account_uuids`` only the folders of those accounts are listed (and
        only their stores are walked): the callers that need nothing else.
        """
        return [MailboxRow(**row) for row in self._folders(account_uuids)]

    #: Hint of the ``message uid … was not found`` error of ``show``.
    not_found_hint = NOT_FOUND_HINT

    #: Evaluating ``--to``/``--cc`` opens every candidate item: on Windows they are
    #: bounded like ``--text`` and do not narrow.
    recipients_open_items = True

    @property
    def items_opened(self) -> int:
        """Distinct items opened so far (``scan.messages_read``)."""
        return len(self._opened)

    def load_snippet(self, row: MessageRow) -> BodyRow:
        """:meth:`load_body` for ``search``/``new``: the body only.

        Attachment names and transport headers are only needed by ``show``
        (``attachments: []``, ``headers: {}``).
        """
        return self._load_body(row, details=False)

    def unreadable_attachments(self, row: MessageRow) -> tuple[list[str], str | None]:
        """``show`` attachments of an item whose body could not be read.

        Names cannot be read without the item: ``[]``, with
        ``W_ATTACHMENTS_UNAVAILABLE`` only when ``has_attachments`` is true and the
        item is not S/MIME (whose technical ``smime.p7m`` is no real attachment).
        No COM call is made.
        """
        if row.get("has_attachments") and not is_smime_class(row.get("message_class")):
            return [], ATTACHMENTS_UNAVAILABLE_WARNING
        return [], None

    @staticmethod
    def parse_uid(raw: Any) -> str:
        """Validate the ``show`` uid of Outlook: an uppercase hex EntryID.

        Pure and offline: ``cli`` calls it before it creates the home, reads the
        config or connects to Outlook.
        """
        text = raw if isinstance(raw, str) else str(raw)
        if _UID_PATTERN.fullmatch(text) is None:
            raise usage_error(
                f"invalid uid {raw!r}: expected an uppercase hexadecimal EntryID",
                "uids are uppercase hexadecimal EntryIDs; run `mailquery search` "
                "to find the uid of a message",
                "invalid uid: expected an uppercase hexadecimal EntryID",
            )
        return text

    @staticmethod
    def parse_native_id(native_id: str) -> str:
        """Validate the native part of a prefixed uid: an uppercase hex EntryID.

        Pure and offline. The core splits ``"<driver>:<native_id>"`` at the first
        ``:`` and hands only ``native_id`` to the adapter.
        """
        if not isinstance(native_id, str) or _UID_PATTERN.fullmatch(native_id) is None:
            raise usage_error(
                f"invalid uid part {native_id!r}: expected an uppercase hexadecimal EntryID",
                "Outlook uids are uppercase hexadecimal EntryIDs; run `mailquery search` "
                "to find the uid of a message",
                "invalid uid part: expected an uppercase hexadecimal EntryID",
            )
        return native_id

    def doctor_checks(self) -> list[dict[str, Any]]:
        """``pywin32``, ``outlook``, ``stores``, ``readonly_strategy``, ``object_model_guard``.

        Returned in :data:`DOCTOR_CHECKS` order; evaluated in this order: the
        checks that never call Outlook first (``pywin32``, ``object_model_guard``),
        then ``outlook``, ``readonly_strategy`` (no COM call) and ``stores``.
        A check whose direct dependency failed is ``not evaluated: <dependency>
        failed``. Outlook is never launched. The progress is kept so
        that a COM timeout can complete the report (:meth:`bind_doctor_timeout`).
        """
        self._doctor_done = {}
        self._doctor_running = None
        self._doctor_step("pywin32", self._check_pywin32)
        self._doctor_step("object_model_guard", self._check_object_model_guard)
        for name in DOCTOR_COM_CHECKS:
            failed = self._doctor_failed_dependency(name)
            if failed is not None:
                self._doctor_done[name] = _not_evaluated(name, failed)
            else:
                self._doctor_step(name, getattr(self, f"_check_{name}"))
        return [self._doctor_done[name] for name in DOCTOR_CHECKS]

    def bind_doctor_timeout(
        self, finish: Callable[[list[dict[str, Any]] | None, str], None]
    ) -> None:
        """COM timeout in ``doctor``: the watchdog calls ``finish``.

        ``finish(backend_checks, detail)`` gets the backend checks completed
        (the running check ``ok=false`` with ``detail``, its dependents
        ``not evaluated``), or ``None`` when no backend check was running (the
        timeout hit the CLI's ``config`` resolution); it must write the report
        and end the process with exit 0.
        """
        self._watchdog.doctor_handler = lambda _seconds: finish(
            self._doctor_interrupted(), outlook_com.DOCTOR_TIMEOUT_DETAIL
        )

    def _doctor_step(self, name: str, check: Callable[[], tuple[bool, str]]) -> None:
        self._doctor_running = name
        try:
            ok, detail = check()
        except MailqueryError as exc:
            ok, detail = False, _error_with_hint(exc)
        except Exception as exc:  # noqa: BLE001 - diagnostics only
            ok, detail = False, error_detail(exc)
        finally:
            self._doctor_running = None
        self._doctor_done[name] = {"name": name, "ok": bool(ok), "detail": str(detail)}

    def _doctor_failed_dependency(self, name: str) -> str | None:
        dependency = DOCTOR_DEPENDENCIES.get(name)
        if dependency is None:
            return None
        done = self._doctor_done.get(dependency)
        return None if done is not None and done["ok"] else dependency

    def _doctor_interrupted(self) -> list[dict[str, Any]] | None:
        """The backend checks after a timeout in the running one, or ``None``."""
        running = self._doctor_running
        if running is None:
            return None
        done = dict(self._doctor_done)
        done[running] = {
            "name": running,
            "ok": False,
            "detail": outlook_com.DOCTOR_TIMEOUT_DETAIL,
        }
        for name in ("pywin32", "object_model_guard") + DOCTOR_COM_CHECKS:
            if name not in done:
                dependency = DOCTOR_DEPENDENCIES.get(name) or running
                done[name] = _not_evaluated(name, dependency)
        return [done[name] for name in DOCTOR_CHECKS]

    def _gen_path(self) -> Path:
        if self._tmp_root is not None:
            return self._tmp_root / "gen_py"
        from mailquery.config import app_home

        return app_home() / "tmp" / "gen_py"

    def _check_pywin32(self) -> tuple[bool, str]:
        """pywin32 importable by this interpreter (fixed by the ``pywin32`` seam)."""
        if self._pywin32 is False:
            raise outlook_com.dependency_missing()
        if self._pywin32 is None and self._outlook_app is None:
            outlook_com.import_pywin32(self._gen_path())
        return True, "win32com importable"

    def _check_outlook(self) -> tuple[bool, str]:
        """Registered, >= 16.0, running and reachable; only ``GetActiveObject``."""
        version = self._app().Version
        return True, f"classic Outlook {version} running (attached with GetActiveObject)"

    def _check_readonly_strategy(self) -> tuple[bool, str]:
        """``com_readonly`` without any COM call: proxy, no launch, confined pywin32 cache."""
        gen_path = self._gen_path()
        if not isinstance(self._application, outlook_com.ReadOnlyCom):
            return False, f"{STRATEGY}: the Outlook connection is not behind the read-only proxy"
        if self._outlook_app is None:
            current = outlook_com.pywin32_gen_path()
            if current is None or Path(current) != gen_path:
                return False, f"{STRATEGY}: the pywin32 cache is not confined to {gen_path}"
        return True, (
            f"{STRATEGY}: read-only whitelist proxy active, attached with GetActiveObject "
            f"(Outlook is never launched), pywin32 cache confined to {gen_path}"
        )

    def _check_stores(self) -> tuple[bool, str]:
        """Candidate stores (label and type) and excluded ones (label, path, reason)."""
        stores = self._profile()
        candidates = [f"{info.label} [{info.kind}]" for info in stores if info.reason is None]
        excluded = [
            (f"{info.label} at {info.path}" if info.path else info.label) + f" [{info.reason}]"
            for info in stores
            if info.reason is not None
        ]
        return True, (
            f"{len(candidates)} candidate(s): {', '.join(candidates) or 'none'}; "
            f"{len(excluded)} excluded: {', '.join(excluded) or 'none'}"
        )

    def _check_object_model_guard(self) -> tuple[bool, str]:
        """A deciding Object Model Guard policy, else an active antivirus (SecurityCenter2)."""
        registry = self._registry if self._registry is not None else outlook_com.WinRegistry()
        policy = outlook_com.oom_policy(registry)
        if policy is not None:
            name, value = policy
            setting = outlook_com.OOM_SETTING_NAMES[value]
            if value == outlook_com.OOM_APPROVE:
                return True, f"Outlook security policy {name}={value} ({setting})"
            effect = (
                "programmatic access is refused"
                if value == outlook_com.OOM_DENY
                else "Outlook always shows a security prompt to programmatic access"
            )
            return False, f"Outlook security policy {name}={value} ({setting}): {effect}"
        center = self._security_center
        if center is None:
            center = outlook_com.WmiSecurityCenter(self._gen_path())
        try:
            products = center.antivirus_products()
        except OSError:
            return False, "not evaluated: SecurityCenter2 unavailable"
        active = outlook_com.active_antivirus(products)
        if active:
            names = ", ".join(active)
            return True, f"no Outlook security policy decides; active antivirus: {names}"
        return False, (
            "no Outlook security policy decides and no active antivirus: Outlook shows a "
            "security prompt to programmatic access"
        )

    def close(self) -> None:
        """Drop the COM references (Outlook itself is never closed)."""
        self._store_folders = {}
        self._folder_objects = {}
        self._counters = {}
        self._uid_folders = {}
        self._message_keys = {}
        self._items = {}
        self._last_item = None
        self._opened = set()
        self._recipient_cache = {}
        self._stores = None
        self._application = None
        for session in list(self._attachment_sessions):
            shutil.rmtree(session, ignore_errors=True)
        self._attachment_sessions.clear()


# --------------------------------------------------------------------------- #
# Store classification
# --------------------------------------------------------------------------- #


def _delivery_accounts(session: outlook_com.ReadOnlyCom) -> dict[str, tuple[int, str]]:
    """``StoreID`` of each account's delivery store -> ``(AccountType, SmtpAddress)``.

    Candidates are identified through ``Account.DeliveryStore`` and not through
    ``ExchangeStoreType`` (a second account's mailbox has type 4).
    An account whose delivery store cannot be read is skipped: that store is
    classified ``unavailable`` on its own. With two accounts delivering to the
    same store, the first one names it.
    """
    found: dict[str, tuple[int, str]] = {}
    accounts = session.Accounts
    for position in range(1, accounts.Count + 1):
        try:
            account = accounts.Item(position)
            delivery = account.DeliveryStore
            store_id = delivery.StoreID if delivery is not None else None
            if not store_id:
                continue
            account_type = account.AccountType
            smtp = account.SmtpAddress or ""
        except outlook_com.ComCallError:
            continue
        found.setdefault(store_id, (account_type, smtp))
    return found


def _classify_store(
    stores: outlook_com.ReadOnlyCom, position: int, delivery: dict[str, tuple[int, str]]
) -> StoreInfo:
    """Classify ``Stores.Item(position)`` reading only store-level properties.

    Any COM error (or a malformed ``PR_RECORD_KEY``) makes the store
    ``unavailable``, labelled with its ``DisplayName`` and ``FilePath`` if they
    were read before the failure; it never blocks the other stores.
    """
    import uuid as uuid_module  # lazy: only needed when reading stores

    name: str | None = None
    path: str | None = None
    try:
        store = stores.Item(position)
        name = store.DisplayName or None
        file_path = store.FilePath or ""
        path = file_path or None
        store_id = store.StoreID
        store_type = store.ExchangeStoreType
        record_key = bytes(store.PropertyAccessor.GetProperty(PR_RECORD_KEY))
        info = StoreInfo(
            position=position,
            label=name or UNKNOWN_LABEL,
            path=None,
            uuid=str(uuid_module.UUID(bytes=record_key)).upper(),
            record_key=record_key,
        )
        account = delivery.get(store_id) if store_id else None
        if account is not None:
            _classify_delivery_store(info, store, account, file_path)
        else:
            _classify_other_store(info, name or "", store_type, file_path)
    except (outlook_com.ComCallError, TypeError, ValueError):
        return StoreInfo(
            position=position, label=name or UNKNOWN_LABEL, path=path, reason="unavailable"
        )
    if info.reason is None:
        info.store = store
        info.store_id = store_id
    return info


def _classify_delivery_store(
    info: StoreInfo, store: outlook_com.ReadOnlyCom, account: tuple[int, str], file_path: str
) -> None:
    """Delivery store of an account: labelled ``<type> (<smtp>)``."""
    account_type, smtp = account
    kind = ACCOUNT_KINDS.get(account_type, ACCOUNT_KINDS[OL_OTHER_ACCOUNT])
    info.label = f"{kind} ({smtp})"
    info.email = smtp or None
    info.kind = kind
    if account_type == OL_EXCHANGE:
        if not store.IsCachedExchange:
            info.reason = "online_mode"
    elif account_type in FILE_ACCOUNT_TYPES:
        # A POP3 account's PST is labelled as the account, never `PST (...)`.
        info.path = file_path or None
        if file_path and is_network_path(file_path):
            info.reason = "network_path"
    else:
        info.path = file_path or None
        info.reason = "unsupported_account_type"


def _classify_other_store(info: StoreInfo, name: str, store_type: int, file_path: str) -> None:
    """A store that is no account's delivery store: PST or excluded Exchange store."""
    if store_type == OL_EXCHANGE_PUBLIC_FOLDER:
        info.label = f"Public Folders ({name})"
        info.reason = "public_folders"
    elif store_type == OL_EXCHANGE_MAILBOX:
        info.label = f"Exchange shared ({name})"
        info.reason = "shared_mailbox"
    elif store_type == OL_NOT_EXCHANGE and file_path:
        info.label = f"PST ({name})"
        info.kind = "PST"
        info.local = True
        info.path = file_path
        if is_network_path(file_path):
            info.reason = "network_path"
    else:
        # Another Exchange store without a local copy (online archive, Microsoft
        # 365 group), or a store with no data file: its own display name.
        info.label = name or UNKNOWN_LABEL
        info.reason = "online_mode"


# --------------------------------------------------------------------------- #
# Folders
# --------------------------------------------------------------------------- #


def _default_folder_id(store: outlook_com.ReadOnlyCom, folder_type: int) -> str | None:
    """``EntryID`` of a default folder of the store, ``None`` when it does not exist."""
    try:
        folder = store.GetDefaultFolder(folder_type)
        return (folder.EntryID or None) if folder is not None else None
    except outlook_com.ComCallError:
        return None


def _walk_store(
    account_uuid: str,
    store: outlook_com.ReadOnlyCom,
    rows: list[MailboxRow],
    objects: dict[str, outlook_com.ReadOnlyCom],
) -> None:
    """Append the listed folders of one candidate store, depth-first from its root.

    The inbox and the sync folders are identified by function
    (``GetDefaultFolder``), never by name, so it works in any language; the
    sync folders and their whole subtrees are skipped without being read.
    """
    inbox_id = _default_folder_id(store, OL_FOLDER_INBOX)
    hidden = {
        entry_id
        for entry_id in (_default_folder_id(store, kind) for kind in HIDDEN_DEFAULT_FOLDERS)
        if entry_id is not None
    }
    _walk_folder(account_uuid, store.GetRootFolder(), [], inbox_id, hidden, rows, objects)


def _walk_folder(
    account_uuid: str,
    folder: outlook_com.ReadOnlyCom,
    names: list[str],
    inbox_id: str | None,
    hidden: set[str],
    rows: list[MailboxRow],
    objects: dict[str, outlook_com.ReadOnlyCom],
) -> None:
    """Depth-first in enumeration order; ``names`` are the decoded segments of ``folder``."""
    children = folder.Folders
    for position in range(1, children.Count + 1):
        child = children.Item(position)
        entry_id = child.EntryID
        if entry_id in hidden:
            continue
        is_inbox = inbox_id is not None and entry_id == inbox_id
        child_names = [*names, INBOX if is_inbox else (child.Name or "")]
        if _is_mail_folder(child):
            path = "/".join(encode_segment(name) for name in child_names)
            rows.append(
                MailboxRow(
                    id=entry_id,
                    account_uuid=account_uuid,
                    name=encode_segment(child_names[-1]),
                    path=path,
                    url=folder_url(account_uuid, child_names),
                    is_inbox=is_inbox,
                    is_aggregate=False,
                    total=None,  # type: ignore[typeddict-item]  # counted by mailboxes()
                    unread=None,  # type: ignore[typeddict-item]
                )
            )
            objects[entry_id] = child
        _walk_folder(account_uuid, child, child_names, inbox_id, hidden, rows, objects)


def _is_mail_folder(folder: outlook_com.ReadOnlyCom) -> bool:
    """A mail folder (``DefaultItemType`` olMailItem) that is not a search folder."""
    if folder.DefaultItemType != OL_MAIL_ITEM:
        return False
    try:
        folder_type = folder.PropertyAccessor.GetProperty(PR_FOLDER_TYPE)
    except outlook_com.ComCallError as exc:
        if exc.hresult == outlook_com.MAPI_E_NOT_FOUND:
            return True  # no folder type: a generic folder
        raise
    return folder_type != FOLDER_SEARCH


def _as_int(value: Any) -> int:
    return value if isinstance(value, int) else 0


def _count_int(value: Any) -> int | None:
    """A folder counter property: a non-negative ``int``, else ``None``."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _count_searchable(folder: outlook_com.ReadOnlyCom) -> tuple[int, int]:
    """``(total, unread)`` of the searchable items of a folder; no item opened.

    The folder's own counters (``PR_CONTENT_COUNT``/``PR_CONTENT_UNREAD``, one
    read each; equal to the rows of its item table and their unread ones,
    verified on the host) minus the rows that are not searchable. When every
    row has a searchable class (row count of :data:`SEARCHABLE_CLASS_FILTER`),
    only the rows of :data:`DELETION_CANDIDATES_FILTER` are read; otherwise
    those of :data:`COUNTER_EXCEPTIONS_FILTER` (class not searchable, or a
    status that may hold the IMAP deletion mark). Rows read are classified
    exactly in Python. Without readable counters, every row of the table is
    classified. An empty folder reads no table.
    """
    accessor = folder.PropertyAccessor
    count = _count_int(_get_property(accessor, PR_CONTENT_COUNT))
    unread = _count_int(_get_property(accessor, PR_CONTENT_UNREAD))
    if count is None or unread is None:
        total, unread_total, _skipped, _skipped_unread = _tally_rows(folder, "")
        return total, unread_total
    if count == 0:
        return 0, 0
    searchable_class = folder.GetTable(SEARCHABLE_CLASS_FILTER, OL_USER_ITEMS).GetRowCount()
    if searchable_class == count:
        # Every row has a searchable class: only the IMAP deletion mark can exclude one.
        _total, _unread, skipped, skipped_unread = _tally_rows(folder, DELETION_CANDIDATES_FILTER)
    else:
        _total, _unread, skipped, skipped_unread = _tally_rows(folder, COUNTER_EXCEPTIONS_FILTER)
    return max(count - skipped, 0), max(unread - skipped_unread, 0)


def _tally_rows(folder: outlook_com.ReadOnlyCom, filter_text: str) -> tuple[int, int, int, int]:
    """``(searchable, searchable unread, other, other unread)`` rows of a folder table."""
    total = unread = skipped = skipped_unread = 0
    for message_class, props in _table_rows(folder, filter_text, COUNTER_COLUMNS):
        is_unread = not _as_int(props[PR_MESSAGE_FLAGS]) & MSGFLAG_READ
        if _is_searchable(message_class, props):
            total += 1
            unread += is_unread
        else:
            skipped += 1
            skipped_unread += is_unread
    return total, unread, skipped, skipped_unread


# --------------------------------------------------------------------------- #
# Items
# --------------------------------------------------------------------------- #

#: ``_open_item`` result for an item that exists but cannot be opened.
_UNOPENABLE = object()


def _table_rows(
    folder: outlook_com.ReadOnlyCom, filter_text: str, columns: Sequence[str]
) -> Iterator[tuple[Any, dict[str, Any]]]:
    """``(MessageClass, {column: value})`` of each row of ``folder.GetTable`` with ``columns`` added.

    ``Columns.Add`` only changes the in-memory view of the table. A property
    missing in a row is ``None``.
    """
    table = folder.GetTable(filter_text, OL_USER_ITEMS)
    table_columns = table.Columns
    for column in columns:
        table_columns.Add(column)
    first = len(TABLE_DEFAULT_COLUMNS)
    while True:
        # Rows in bulk: one call per TABLE_CHUNK_ROWS rows; past the end Outlook returns ().
        chunk = table.GetArray(TABLE_CHUNK_ROWS)
        if not chunk:
            break
        for values in chunk:
            yield values[_MESSAGE_CLASS_COLUMN], dict(zip(columns, values[first:]))
        if len(chunk) < TABLE_CHUNK_ROWS:
            break


def _is_searchable(message_class: Any, props: dict[str, Any]) -> bool:
    """Searchable class (mail or meeting) and not marked deleted by IMAP."""
    return is_searchable_class(message_class) and not (
        _as_int(props.get(PR_MSG_STATUS)) & MSGSTATUS_DELMARKED
    )


def _hex(value: Any) -> str:
    """Binary property as uppercase hex (``""`` when missing)."""
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex().upper()
    return ""


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _smtp_address(smtp: Any, email: Any, addrtype: Any) -> str:
    """The SMTP address an item carries; never an Exchange DN.

    ``PR_*_SMTP_ADDRESS`` first; else ``PR_*_EMAIL_ADDRESS`` only when the
    address type is ``SMTP``; else ``""``.
    """
    if _text(smtp):
        return smtp
    if _text(addrtype).upper() == "SMTP" and _text(email):
        return email
    return ""


def _get_property(accessor: outlook_com.ReadOnlyCom, schema: str) -> Any:
    """``PropertyAccessor.GetProperty``; a missing property (``MAPI_E_NOT_FOUND``) is ``None``."""
    try:
        return accessor.GetProperty(schema)
    except outlook_com.ComCallError as exc:
        if exc.hresult == outlook_com.MAPI_E_NOT_FOUND:
            return None
        raise


def _recipient_address(accessor: outlook_com.ReadOnlyCom) -> str:
    """SMTP address of a recipient from its own properties (no address book)."""
    smtp = _get_property(accessor, PR_SMTP_ADDRESS)
    if _text(smtp):
        return smtp
    addrtype = _get_property(accessor, PR_ADDRTYPE)
    if _text(addrtype).upper() != "SMTP":
        return ""
    return _smtp_address(None, _get_property(accessor, PR_EMAIL_ADDRESS), addrtype)


def _visible_attachment_names(item: outlook_com.ReadOnlyCom) -> list[str]:
    """``FileName`` (else ``DisplayName``) of each attachment not marked hidden."""
    names: list[str] = []
    attachments = item.Attachments
    for position in range(1, attachments.Count + 1):
        attachment = attachments.Item(position)
        if _get_property(attachment.PropertyAccessor, PR_ATTACHMENT_HIDDEN) is True:
            continue
        name = _text(attachment.FileName) or _text(attachment.DisplayName)
        if name:
            names.append(name)
    return names


def _attachment_unreadable_error(message: str, hint: str) -> MailqueryError:
    """``E_ATTACHMENT_UNREADABLE``: the message-level attachment signal."""
    return MailqueryError(
        "E_ATTACHMENT_UNREADABLE", message, hint, "the attachment is S/MIME or unreadable"
    )


def _attachment_unavailable_error(
    reason: str, message: str, hint: str
) -> MailqueryError:
    """``E_ATTACHMENT_UNAVAILABLE`` of one attachment reason."""
    return MailqueryError(
        "E_ATTACHMENT_UNAVAILABLE",
        message,
        hint,
        f"the attachment is unavailable: {reason}",
    )


def _attachment_signal(item: outlook_com.ReadOnlyCom) -> bool:
    """Whether the item reports attachments (``PR_HASATTACH``; no content is read)."""
    return _get_property(item.PropertyAccessor, PR_HASATTACH) is True


def _visible_attachments(item: outlook_com.ReadOnlyCom) -> list[Any]:
    """Attachment objects of the message in order, without the hidden ones.

    The OOM index is only used to enumerate the collection: the reported
    ``index`` is the 1-based position of the visible list (shared by ``show``
    and ``attachment``), as the core contract requires.
    """
    attachments = item.Attachments
    visible: list[Any] = []
    for position in range(1, int(attachments.Count) + 1):
        attachment = attachments.Item(position)
        if _get_property(attachment.PropertyAccessor, PR_ATTACHMENT_HIDDEN) is True:
            continue
        visible.append(attachment)
    return visible


def _attachment_unavailable_reason(attachment: Any) -> str | None:
    """Local availability of one attachment from its ``OlAttachmentType``.

    A by-value attachment is a copy of the file stored in the item (local). The
    other types are not content of the message: a by-reference attachment points
    to a file outside the store and would have to be fetched from its origin
    (``not_downloaded``); an embedded message or an OLE object is not a
    recoverable file (``unsupported``). When the type cannot be read without
    downloading, the safest reason is ``not_downloaded``.
    """
    try:
        attachment_type = int(attachment.Type)
    except outlook_com.ComCallError:
        return "not_downloaded"
    if attachment_type == OL_BY_VALUE:
        return None
    if attachment_type == OL_BY_REFERENCE:
        return "not_downloaded"
    return "unsupported"


def _attachment_size(attachment: Any) -> int | None:
    """Expected size of a local attachment from its ``Size`` property, or ``None``.

    ``Attachment.Size`` (``PR_ATTACH_SIZE``) includes the MAPI property overhead,
    so it is an upper-bound estimate of the decoded bytes, never their exact
    count. The core only uses it for the limits checked before extraction; cache
    hits are verified against the per-message manifest.
    """
    try:
        size = int(attachment.Size)
    except (outlook_com.ComCallError, TypeError, ValueError):
        return None
    return size if size >= 0 else None


def _create_staging_file(session: Path) -> Path:
    """Opaque ``0600`` file inside the driver's private staging session."""
    try:
        descriptor, name = tempfile.mkstemp(
            prefix="attachment-", suffix=".bin", dir=session
        )
    except PermissionError as exc:
        raise MailqueryError(
            "E_PERMISSION",
            "cannot create the attachment staging file",
            "check the permissions of ~/.mailquery/tmp",
            "cannot create the attachment staging file",
        ) from exc
    except OSError as exc:
        raise MailqueryError(
            "E_IO",
            f"cannot create the attachment staging file ({exc.strerror or exc})",
            "check the free space and permissions of ~/.mailquery/tmp",
            "cannot create the attachment staging file",
        ) from exc
    os.close(descriptor)
    path = Path(name)
    if os.name != "nt":
        try:
            os.chmod(path, 0o600)
        except OSError as exc:  # pragma: no cover - best effort on foreign filesystems
            raise MailqueryError(
                "E_PERMISSION",
                "cannot protect the attachment staging file",
                "check the permissions of ~/.mailquery/tmp",
                "cannot protect the attachment staging file",
            ) from exc
    return path


def _materialize(
    attachment: Any, path: Path, session: Path
) -> None:
    """``Attachment.SaveAsFile`` into ``path`` and the staging path validation.

    The only writing operation of the read-only COM proxy (COM exception for
    attachments). A COM failure that meant "not in the local store" is
    ``E_ATTACHMENT_UNAVAILABLE``/``not_downloaded``; any other failure is
    ``E_ATTACHMENT_UNREADABLE``/``corrupt``. The materialized path must be a
    regular file inside the staging session: a symlink, a directory or a path
    outside the session is ``E_ATTACHMENT_UNAVAILABLE``/``unsupported``,
    before the bytes are read.
    """
    try:
        attachment.SaveAsFile(str(path))
    except outlook_com.ComCallError as exc:
        if exc.hresult in ITEM_NOT_FOUND_HRESULTS or exc.hresult == outlook_com.MAPI_E_NOT_FOUND:
            raise _attachment_unavailable_error(
                "not_downloaded",
                "the attachment is not available in the local store",
                _DOWNLOAD_HINT,
            ) from exc
        raise _attachment_unreadable_error(
            "the attachment is corrupt or unreadable",
            "the attachment is corrupt and cannot be recovered",
        ) from exc
    try:
        materialized = path.is_file() and not path.is_symlink()
        inside = path.resolve().parent == session.resolve()
    except OSError:  # pragma: no cover - defensive, the path was just created
        materialized, inside = False, False
    if not materialized or not inside:
        raise _attachment_unavailable_error(
            "unsupported",
            "the attachment cannot be recovered from the local store",
            "restart Outlook and retry; run `mailquery doctor` if it persists",
        )


def _unlink_quietly(path: Path) -> None:
    """Remove the staging file; a failure to clean up never masks the result."""
    try:
        path.unlink()
    except OSError:  # pragma: no cover - the file may already be gone
        pass


def _item_text(item: outlook_com.ReadOnlyCom) -> tuple[str, list[str]]:
    """Plain ``Body``; if empty, ``HTMLBody`` converted with the common code.

    A MeetingItem has no ``HTMLBody`` (``AttributeError`` under dynamic
    dispatch, verified on the host): it counts as no HTML. HTML that yields no
    text gives ``""`` and ``W_HTML_NO_TEXT``.
    """
    text = _text(item.Body).strip()
    if text:
        return text, []
    try:
        html = _text(item.HTMLBody)
    except AttributeError:
        html = ""
    if not html.strip():
        return "", []
    converted = output.html_to_text(html)
    if converted:
        return converted, []
    return "", [HTML_NO_TEXT_WARNING]


def _parse_headers(raw: Any) -> dict[str, str]:
    """From/To/Cc/Subject/Date/Message-ID of ``PR_TRANSPORT_MESSAGE_HEADERS``.

    ``{}`` when the item has none (internal mail): ``show`` then synthesizes
    them from the item's properties and recipients.
    """
    text = _text(raw)
    if not text.strip():
        return {}
    from email import policy as email_policy  # lazy: ~15 ms, only needed by show
    from email.parser import HeaderParser

    try:
        parsed = HeaderParser(policy=email_policy.default).parsestr(text)
    except Exception:  # noqa: BLE001 - malformed headers never break show
        return {}
    headers: dict[str, str] = {}
    for name in SHOW_HEADER_NAMES:
        try:
            value = parsed.get(name)
        except Exception:  # noqa: BLE001 - a malformed header is treated as missing
            value = None
        headers[name] = str(value).strip() if value is not None else ""
    return headers


def _body(
    available: bool,
    readable: bool,
    headers: dict[str, str],
    body_text: str,
    attachments: list[dict[str, str]],
    warnings: list[str],
) -> BodyRow:
    """A ``load_body`` result: ``partial`` always false, no ``.emlx``."""
    return {
        "available": available,
        "readable": readable,
        "partial": False,
        "headers": headers,
        "body_text": body_text,
        "attachments": attachments,  # type: ignore[typeddict-item]
        "source": {"emlx_path": None, "partial": False},
        "warnings": warnings,
    }


def _unavailable_body(warning: str) -> BodyRow:
    """Header-only, missing or unopenable item: ``false/false/false`` and the reason."""
    return _body(False, False, {}, "", [], [warning])


def _smime_body(message_class: Any) -> BodyRow:
    """S/MIME item: ``true/false/false`` without reading any content."""
    signed = "signed" in _text(message_class).casefold()
    return _body(
        True, False, {}, "", [], [SMIME_SIGNED_WARNING if signed else SMIME_ENCRYPTED_WARNING]
    )


def _unopenable_warning(uid: str) -> str:
    return f"W_BODY_UNREADABLE: the Outlook item for uid {uid} cannot be opened"


def _utc_epoch(value: Any) -> int | None:
    """Unix seconds of a MAPI time property, whose wall clock is UTC."""
    if not isinstance(value, datetime):
        return None
    try:
        return math.floor(value.replace(tzinfo=timezone.utc).timestamp())
    except (OverflowError, OSError, ValueError):
        return None


def _dasl_time(epoch: float, margin: timedelta) -> str | None:
    """``YYYY-MM-DD HH:MM`` (UTC) of ``epoch + margin``; ``None`` outside the MAPI date range."""
    try:
        moment = _UNIX_EPOCH + timedelta(seconds=math.floor(epoch)) + margin
    except (OverflowError, ValueError):
        return None
    if not 1601 <= moment.year <= 4500:
        return None
    return moment.strftime("%Y-%m-%d %H:%M")


def _date_filter(since: float | None, until: float | None) -> str:
    """DASL pre-filter on the delivery time, at minute granularity and widened.

    DASL compares in UTC (verified on the host). ``""`` without
    dates; a bound outside the MAPI date range is simply not pre-filtered.
    """
    clauses: list[str] = []
    if since is not None:
        start = _dasl_time(since, -FILTER_MARGIN_BEFORE)
        if start is not None:
            clauses.append(f"\"{PR_MESSAGE_DELIVERY_TIME}\" >= '{start}'")
    if until is not None:
        end = _dasl_time(until, FILTER_MARGIN_AFTER)
        if end is not None:
            clauses.append(f"\"{PR_MESSAGE_DELIVERY_TIME}\" < '{end}'")
    return "@SQL=" + " AND ".join(clauses) if clauses else ""


def _order_key(row: MessageRow) -> tuple[bool, int, str]:
    """``(date_received, uid)``; a row without date sorts first, like SQL ``NULL``."""
    received = row["date_received"]
    return received is not None, int(received or 0), str(row["uid"])

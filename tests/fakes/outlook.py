"""In-memory fake of the classic Outlook Object Model (plan 7.5, annex B.10).

The fake implements **only** the OOM members the Outlook backend uses (the
read-only whitelist ``OOM_MEMBERS``, fixed by the W3 design note) and stands in
for ``win32com.client`` as the *connector* passed as ``get_backend(outlook_app=...)``:
production code calls ``outlook_app.GetActiveObject("Outlook.Application")``
and wraps the returned Application in its read-only proxy.

Observability:

* ``FakeOutlook.call_log`` records every member read or invoked, with the object
  kind (``CallEntry(kind, member, action, args)``; actions ``get``, ``call``,
  ``set``, ``forbidden``, ``unknown``).
* ``FakeOutlook.mutations`` counts assignments and forbidden calls (``Delete``,
  ``Move``, ``Folders.Add``, ``AddressEntry``, ``Dispatch``...); tests assert
  ``mutations.total == 0``. Assignments are recorded and never applied.
* Members outside the whitelist raise ``AttributeError`` (as dynamic dispatch
  does for an unknown name) and are logged as ``unknown``.

COM errors are raised as :class:`com_error`, which has the shape of
``pywintypes.com_error`` (``args == (hresult, strerror, excepinfo, argerror)``,
signed 32-bit ``hresult``, the real code in ``excepinfo[5]`` when ``hresult`` is
``DISP_E_EXCEPTION``). The backend recognises both by duck typing; see
:func:`hresult_of`. Nothing here imports pywin32.
"""

from __future__ import annotations

import hashlib
import os
import re
import threading
import uuid as _uuid
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone, tzinfo
from email.utils import format_datetime
from typing import Any, Callable, Iterator, Sequence

# --------------------------------------------------------------------------- #
# HRESULTs (unsigned values; pywin32 reports them signed, see to_signed)
# --------------------------------------------------------------------------- #

DISP_E_EXCEPTION = 0x80020009
DISP_E_BADINDEX = 0x8002000B
RPC_E_CALL_REJECTED = 0x80010001
RPC_E_SERVERCALL_RETRYLATER = 0x8001010A
E_ACCESSDENIED = 0x80070005
E_INVALIDARG = 0x80070057
E_FAIL = 0x80004005
E_UNEXPECTED = 0x8000FFFF
MK_E_UNAVAILABLE = 0x800401E3
CO_E_CLASSSTRING = 0x800401F3
MAPI_E_NOT_FOUND = 0x8004010F
MAPI_E_LOGON_FAILED = 0x80040111
MAPI_E_NETWORK_ERROR = 0x80040115
MAPI_E_FAILONEPROVIDER = 0x8004011D

#: Bytes the real ``Attachment.Size`` (``PR_ATTACH_SIZE``) adds to the decoded
#: content: the MAPI property overhead measured on a real host (18848 reported
#: for a 15099-byte file). The fake reproduces it so a test can never assume
#: ``Size`` equals the recovered bytes (CR-01).
MAPI_SIZE_OVERHEAD = 3749

_HRESULT_TEXT = {
    DISP_E_EXCEPTION: "Exception occurred.",
    DISP_E_BADINDEX: "Invalid index.",
    RPC_E_CALL_REJECTED: "Call was rejected by callee.",
    RPC_E_SERVERCALL_RETRYLATER: "The message filter indicated that the application is busy.",
    E_ACCESSDENIED: "Access is denied.",
    E_INVALIDARG: "The parameter is incorrect.",
    E_FAIL: "Unspecified error",
    E_UNEXPECTED: "Catastrophic failure",
    MK_E_UNAVAILABLE: "Operation unavailable",
    CO_E_CLASSSTRING: "Invalid class string",
    MAPI_E_NOT_FOUND: "The property or object could not be found.",
    MAPI_E_LOGON_FAILED: "The attempt to log on to Microsoft Exchange has failed.",
    MAPI_E_NETWORK_ERROR: "Network error.",
    MAPI_E_FAILONEPROVIDER: "The information store could not be opened.",
}

# --------------------------------------------------------------------------- #
# OOM constants
# --------------------------------------------------------------------------- #

PROG_ID = "Outlook.Application"
DEFAULT_VERSION = "16.0.0.20430"

OL_FOLDER_DELETED = 3
OL_FOLDER_SENT = 5
OL_FOLDER_INBOX = 6
OL_FOLDER_CALENDAR = 9
OL_FOLDER_CONTACTS = 10
OL_FOLDER_TASKS = 13
OL_FOLDER_CONFLICTS = 19
OL_FOLDER_SYNC_ISSUES = 20
OL_FOLDER_LOCAL_FAILURES = 21
OL_FOLDER_SERVER_FAILURES = 22
SYNC_FOLDER_IDS = (
    OL_FOLDER_CONFLICTS,
    OL_FOLDER_SYNC_ISSUES,
    OL_FOLDER_LOCAL_FAILURES,
    OL_FOLDER_SERVER_FAILURES,
)

OL_MAIL_ITEM = 0
OL_APPOINTMENT_ITEM = 1
OL_CONTACT_ITEM = 2
OL_TASK_ITEM = 3
OL_JOURNAL_ITEM = 4
OL_NOTE_ITEM = 5
OL_POST_ITEM = 6

OL_PRIMARY_EXCHANGE_MAILBOX = 0
OL_EXCHANGE_MAILBOX = 1
OL_EXCHANGE_PUBLIC_FOLDER = 2
OL_NOT_EXCHANGE = 3
OL_ADDITIONAL_EXCHANGE_MAILBOX = 4

OL_EXCHANGE = 0
OL_IMAP = 1
OL_POP3 = 2
OL_HTTP = 3
OL_EAS = 4
OL_OTHER_ACCOUNT = 5

OL_HEADER_ONLY = 0
OL_FULL_ITEM = 1
# OlAttachmentType (Microsoft docs): a by-value attachment is a copy of the file
# stored in the item; the other values are links, embedded messages or OLE objects.
OL_BY_VALUE = 1
OL_BY_REFERENCE = 4
OL_EMBEDDED_ITEM = 5
OL_OLE = 6

OL_TO = 1
OL_CC = 2
OL_BCC = 3

OL_USER_ITEMS = 0
OL_HIDDEN_ITEMS = 1

FOLDER_GENERIC = 1
FOLDER_SEARCH = 2

DRIVE_NO_ROOT_DIR = 1
DRIVE_REMOVABLE = 2
DRIVE_FIXED = 3
DRIVE_REMOTE = 4

MSGFLAG_READ = 0x1
MSGFLAG_HASATTACH = 0x10
MSGSTATUS_DELMARKED = 0x8
FLAG_STATUS_COMPLETE = 1
FLAG_STATUS_FLAGGED = 2

# Registry (plan 4.4, PRD 12.6)
HKCR = "HKCR"
HKCU = "HKCU"
HKLM = "HKLM"
CURVER_KEY = r"Outlook.Application\CurVer"

# --------------------------------------------------------------------------- #
# MAPI schema names
# --------------------------------------------------------------------------- #

PROPTAG_PREFIX = "http://schemas.microsoft.com/mapi/proptag/0x"


def proptag(tag: int) -> str:
    """DASL schema name of a MAPI property tag (the ``0x`` is mandatory)."""
    return f"{PROPTAG_PREFIX}{tag:08X}"


PR_SUBJECT = proptag(0x0037001F)
PR_CLIENT_SUBMIT_TIME = proptag(0x00390040)
PR_TRANSPORT_MESSAGE_HEADERS = proptag(0x007D001F)
PR_MESSAGE_CLASS = proptag(0x001A001F)
PR_SENDER_NAME = proptag(0x0C1A001F)
PR_SENDER_ADDRTYPE = proptag(0x0C1E001F)
PR_SENDER_EMAIL_ADDRESS = proptag(0x0C1F001F)
PR_MESSAGE_DELIVERY_TIME = proptag(0x0E060040)
PR_MESSAGE_FLAGS = proptag(0x0E070003)
PR_MESSAGE_SIZE = proptag(0x0E080003)
PR_MSG_STATUS = proptag(0x0E170003)
PR_HASATTACH = proptag(0x0E1B000B)
PR_ENTRYID = proptag(0x0FFF0102)
PR_RECORD_KEY = proptag(0x0FF90102)
PR_FLAG_STATUS = proptag(0x10900003)
PR_INTERNET_MESSAGE_ID = proptag(0x1035001F)
PR_DISPLAY_NAME = proptag(0x3001001F)
PR_ADDRTYPE = proptag(0x3002001F)
PR_EMAIL_ADDRESS = proptag(0x3003001F)
PR_FOLDER_TYPE = proptag(0x36010003)
PR_CONTENT_COUNT = proptag(0x36020003)
PR_CONTENT_UNREAD = proptag(0x36030003)
PR_ATTACH_LONG_FILENAME = proptag(0x3707001F)
PR_SMTP_ADDRESS = proptag(0x39FE001F)
PR_SENDER_SMTP_ADDRESS = proptag(0x5D01001F)
PR_LONGTERM_ENTRYID_FROM_TABLE = proptag(0x66700102)
PR_ATTACHMENT_HIDDEN = proptag(0x7FFE000B)
PID_LID_SMART_NO_ATTACH = (
    "http://schemas.microsoft.com/mapi/id/{00062008-0000-0000-C000-000000000046}/8514000B"
)

DATE_PROPERTIES = frozenset({PR_MESSAGE_DELIVERY_TIME, PR_CLIENT_SUBMIT_TIME})

DEFAULT_COLUMNS = ("EntryID", "Subject", "CreationTime", "LastModificationTime", "MessageClass")
_BUILTIN_COLUMNS = {
    name.lower(): name for name in (*DEFAULT_COLUMNS, "ReceivedTime", "SentOn")
}

# --------------------------------------------------------------------------- #
# Read-only whitelist: {kind: {member: returned kind or None}} (W3 design note)
# --------------------------------------------------------------------------- #

OOM_MEMBERS: dict[str, dict[str, str | None]] = {
    "Application": {"Version": None, "Session": "NameSpace"},
    "NameSpace": {"Stores": "Stores", "Accounts": "Accounts", "GetItemFromID": "Item"},
    "Stores": {"Count": None, "Item": "Store"},
    "Store": {
        "DisplayName": None,
        "ExchangeStoreType": None,
        "IsCachedExchange": None,
        "FilePath": None,
        "StoreID": None,
        "PropertyAccessor": "PropertyAccessor",
        "GetRootFolder": "Folder",
        "GetDefaultFolder": "Folder",
    },
    "Accounts": {"Count": None, "Item": "Account"},
    "Account": {"AccountType": None, "SmtpAddress": None, "DeliveryStore": "Store"},
    "Folders": {"Count": None, "Item": "Folder"},
    "Folder": {
        "Name": None,
        "EntryID": None,
        "DefaultItemType": None,
        "Folders": "Folders",
        "PropertyAccessor": "PropertyAccessor",
        "GetTable": "Table",
    },
    "Table": {
        "Columns": "Columns",
        "EndOfTable": None,
        "GetNextRow": "Row",
        "GetRowCount": None,
        "GetArray": None,
    },
    "Columns": {"Add": "Column"},
    "Column": {},
    "Row": {"GetValues": None},
    "PropertyAccessor": {"GetProperty": None},
    "Item": {
        "MessageClass": None,
        "EntryID": None,
        "Parent": "Folder",
        "DownloadState": None,
        "Body": None,
        "HTMLBody": None,
        "Attachments": "Attachments",
        "Recipients": "Recipients",
        "PropertyAccessor": "PropertyAccessor",
    },
    "Attachments": {"Count": None, "Item": "Attachment"},
    "Attachment": {
        "FileName": None,
        "DisplayName": None,
        "PropertyAccessor": "PropertyAccessor",
        # M10 COM exception (PRD §4): Size/Type are local metadata and
        # SaveAsFile is the single allowed materialization operation.
        "Size": None,
        "Type": None,
        "SaveAsFile": None,
    },
    "Recipients": {"Count": None, "Item": "Recipient"},
    "Recipient": {"Name": None, "Type": None, "PropertyAccessor": "PropertyAccessor"},
}

# Mutating / unsafe OOM members: touching any of them (outside a kind that
# whitelists it, such as ``Columns.Add``) counts as a forbidden call.
FORBIDDEN_MEMBERS = frozenset(
    {
        "Add", "AddressEntry", "ClearConversationIndex", "Close", "Copy", "CreateItem",
        "CreateObject", "Delete", "DeleteProperties", "DeleteProperty", "Display",
        "Dispatch", "DispatchEx", "EnsureDispatch", "Forward", "GetExchangeDistributionList",
        "GetExchangeUser", "Logoff", "Logon", "MarkAsTask", "MarkForDownload", "Move",
        "PrintOut", "Quit", "Remove", "RemoveAll", "Reply", "ReplyAll", "Resolve",
        "ResolveAll", "Save", "SaveAs", "Send", "SetProperties", "SetProperty",
        "ShowCategoriesDialog",
    }
)
_FORBIDDEN_LOWER = frozenset(name.lower() for name in FORBIDDEN_MEMBERS)


# --------------------------------------------------------------------------- #
# COM errors
# --------------------------------------------------------------------------- #


def to_signed(hresult: int) -> int:
    """Signed 32-bit form of an HRESULT, as pywin32 reports it."""
    value = hresult & 0xFFFFFFFF
    return value - (1 << 32) if value & 0x80000000 else value


class com_error(Exception):  # noqa: N801 - same name as pywintypes.com_error
    """Stand-in for ``pywintypes.com_error`` with the same attributes and ``args``."""

    def __init__(
        self,
        hresult: int,
        strerror: str | None = None,
        excepinfo: tuple | None = None,
        argerror: int | None = None,
    ) -> None:
        super().__init__(hresult, strerror, excepinfo, argerror)
        self.hresult = hresult
        self.strerror = strerror
        self.excepinfo = excepinfo
        self.argerror = argerror


def make_com_error(hresult: int, *, wrapped: bool = False, text: str | None = None) -> com_error:
    """Build a COM error: direct ``hresult``, or ``DISP_E_EXCEPTION`` + ``excepinfo[5]``."""
    code = hresult & 0xFFFFFFFF
    message = text or _HRESULT_TEXT.get(code, "Unknown error")
    if wrapped:
        return com_error(
            to_signed(DISP_E_EXCEPTION),
            _HRESULT_TEXT[DISP_E_EXCEPTION],
            (0, "Microsoft Outlook", message, None, 0, to_signed(code)),
            None,
        )
    return com_error(to_signed(code), message, None, None)


def hresult_of(exc: BaseException) -> int | None:
    """Reference HRESULT extraction (unsigned) for real and fake COM errors.

    Duck typing: ``hresult`` attribute (or ``args[0]``); a ``DISP_E_EXCEPTION``
    is unwrapped to ``excepinfo[5]``. Returns ``None`` for non-COM exceptions.
    """
    value = getattr(exc, "hresult", None)
    if not isinstance(value, int) or isinstance(value, bool):
        args = getattr(exc, "args", ())
        value = args[0] if args and isinstance(args[0], int) and not isinstance(args[0], bool) else None
    if value is None:
        return None
    value &= 0xFFFFFFFF
    info = getattr(exc, "excepinfo", None)
    if info is None:
        args = getattr(exc, "args", ())
        info = args[2] if len(args) > 2 else None
    if value == DISP_E_EXCEPTION and info and len(info) > 5 and isinstance(info[5], int) and info[5]:
        value = info[5] & 0xFFFFFFFF
    return value


class FakeFilterError(ValueError):
    """``Folder.GetTable`` got a filter outside the grammar the fake supports."""


# --------------------------------------------------------------------------- #
# Call log and mutation counters
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CallEntry:
    """One member access: object kind, member name as written, action and call args."""

    kind: str
    member: str
    action: str
    args: tuple = ()


class CallLog:
    """Ordered record of every OOM member read or invoked on the fake."""

    def __init__(self) -> None:
        self.entries: list[CallEntry] = []
        self._lock = threading.Lock()

    def record(self, kind: str, member: str, action: str, args: tuple = ()) -> None:
        with self._lock:
            self.entries.append(CallEntry(kind, member, action, tuple(args)))

    def __iter__(self) -> Iterator[CallEntry]:
        return iter(list(self.entries))

    def __len__(self) -> int:
        return len(self.entries)

    def members(self, action: str | None = None) -> set[tuple[str, str]]:
        """``{(kind, member)}`` of the entries (optionally of one action)."""
        return {(e.kind, e.member) for e in self.entries if action is None or e.action == action}

    def count(
        self, *, kind: str | None = None, member: str | None = None, action: str | None = None
    ) -> int:
        return sum(
            1
            for e in self.entries
            if (kind is None or e.kind == kind)
            and (member is None or e.member == member)
            and (action is None or e.action == action)
        )

    def clear(self) -> None:
        with self._lock:
            self.entries.clear()


class Mutations:
    """Counters that a read-only backend must leave at zero."""

    def __init__(self) -> None:
        self.assignments = 0
        self.forbidden_calls = 0
        self.events: list[tuple[str, str, str]] = []

    @property
    def total(self) -> int:
        return self.assignments + self.forbidden_calls

    def assignment(self, kind: str, member: str) -> None:
        self.assignments += 1
        self.events.append((kind, member, "set"))

    def forbidden(self, kind: str, member: str) -> None:
        self.forbidden_calls += 1
        self.events.append((kind, member, "forbidden"))


@dataclass
class _Rule:
    kind: str | None
    member: str | None
    error: tuple[int, bool] | None
    hang: bool
    timeout: float
    times: int
    skip: int


class _Runtime:
    """Shared state of one fake profile: log, counters, failure and hang rules."""

    def __init__(self) -> None:
        self.log = CallLog()
        self.mutations = Mutations()
        self.rules: list[_Rule] = []
        self.release_event = threading.Event()
        self.hangs = 0

    def forbidden(self, kind: str, member: str) -> None:
        self.log.record(kind, member, "forbidden")
        self.mutations.forbidden(kind, member)

    def before(self, kind: str, member: str) -> None:
        """Apply the first pending rule that matches this access (fail or hang)."""
        for rule in self.rules:
            if rule.times <= 0:
                continue
            if rule.kind is None and kind == "Connector":
                continue
            if rule.kind is not None and rule.kind != kind:
                continue
            if rule.member is not None and rule.member.lower() != member.lower():
                continue
            if rule.skip > 0:
                rule.skip -= 1
                return
            rule.times -= 1
            if rule.hang:
                self.hangs += 1
                self.release_event.wait(rule.timeout)
                return
            assert rule.error is not None
            hresult, wrapped = rule.error
            raise make_com_error(hresult, wrapped=wrapped)


def _forbidden_callable(*_args: Any, **_kwargs: Any) -> None:
    """What a forbidden member returns: calling it does nothing."""
    return None


# --------------------------------------------------------------------------- #
# Schema names and table filters
# --------------------------------------------------------------------------- #

_MISSING = object()
_PROPTAG_RE = re.compile(
    r"^http://schemas\.microsoft\.com/mapi/proptag/0x([0-9a-f]{8})$", re.IGNORECASE
)
_NAMED_ID_RE = re.compile(
    r"^http://schemas\.microsoft\.com/mapi/id/\{([0-9a-f-]{36})\}/([0-9a-f]{8})$", re.IGNORECASE
)
_TOKEN_RE = re.compile(
    r"""\s*(?:(?P<lpar>\()|(?P<rpar>\))|"(?P<prop>[^"]+)"|'(?P<str>[^']*)'"""
    r"""|(?P<int>-?\d+)|(?P<op>>=|<=|<>|=|<|>)|(?P<word>[A-Za-z]+))"""
)
_DATE_LITERAL_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")


def canonical_schema(name: Any) -> str | None:
    """Canonical DASL schema name, ``None`` for a built-in column name.

    A malformed schema name (e.g. a proptag without ``0x``) raises
    ``E_INVALIDARG`` like Outlook does.
    """
    if not isinstance(name, str):
        raise make_com_error(E_INVALIDARG)
    match = _PROPTAG_RE.match(name)
    if match:
        return PROPTAG_PREFIX + match.group(1).upper()
    match = _NAMED_ID_RE.match(name)
    if match:
        return (
            f"http://schemas.microsoft.com/mapi/id/{{{match.group(1).upper()}}}/"
            f"{match.group(2).upper()}"
        )
    if name.lower().startswith(("http://", "urn:")):
        raise make_com_error(E_INVALIDARG)
    return None


_OPS: dict[str, Callable[[datetime, datetime], bool]] = {
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    "=": lambda a, b: a == b,
    "<>": lambda a, b: a != b,
}


Predicate = Callable[["ItemSpec"], bool]


def _tokens(body: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    position = 0
    while position < len(body):
        if body[position:].strip() == "":
            break
        match = _TOKEN_RE.match(body, position)
        if match is None or match.end() == position:
            raise FakeFilterError(f"unsupported filter syntax at {body[position:]!r}")
        kind = match.lastgroup
        assert kind is not None
        value = match.group(kind)
        if kind == "word":
            value = value.upper()
            if value not in ("AND", "OR", "NOT", "LIKE"):
                raise FakeFilterError(f"unsupported filter keyword: {value!r}")
        tokens.append((kind, value))
        position = match.end()
    return tokens


def _like(pattern: str) -> re.Pattern[str]:
    """DASL ``LIKE``: ``%`` is any sequence; case-insensitive (verified on the host)."""
    return re.compile(
        "^" + ".*".join(re.escape(part) for part in pattern.split("%")) + "$", re.IGNORECASE
    )


def _comparison(schema: str, op: str, kind: str, literal: str) -> Predicate:
    """One ``"<property>" <op> <literal>`` restriction; a missing property never matches."""
    if schema in DATE_PROPERTIES:
        if kind != "str" or op == "LIKE" or not _DATE_LITERAL_RE.match(literal):
            raise FakeFilterError(f"unsupported date comparison: {op} {literal!r}")
        moment = datetime.strptime(literal, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        compare = _OPS[op]

        def date_test(item: "ItemSpec") -> bool:
            current = item.mapi(schema)
            # Outlook ignores seconds in date restrictions (P-7).
            return current is not _MISSING and compare(
                current.replace(second=0, microsecond=0), moment
            )

        return date_test
    if schema == PR_MESSAGE_CLASS:
        if kind != "str" or op not in ("=", "<>", "LIKE"):
            raise FakeFilterError(f"unsupported MessageClass comparison: {op} {literal!r}")
        if op == "LIKE":
            pattern = _like(literal)
            return lambda item: pattern.match(item.message_class or "") is not None
        folded = literal.casefold()
        if op == "=":
            return lambda item: item.message_class.casefold() == folded
        return lambda item: item.message_class.casefold() != folded
    if schema == PR_MSG_STATUS:
        if kind != "int" or op == "LIKE":
            raise FakeFilterError(f"unsupported PR_MSG_STATUS comparison: {op} {literal!r}")
        number = int(literal)
        compare = _OPS[op]
        return lambda item: compare(item.msg_status, number)
    raise FakeFilterError(f"unsupported filter property: {schema!r}")


class _FilterParser:
    """``expr := term (OR term)*; term := factor (AND factor)*;
    factor := NOT factor | ( expr ) | "<prop>" <op> <literal>``."""

    def __init__(self, tokens: list[tuple[str, str]]) -> None:
        self.tokens = tokens
        self.position = 0

    def peek(self) -> tuple[str, str] | None:
        return self.tokens[self.position] if self.position < len(self.tokens) else None

    def take(self) -> tuple[str, str]:
        token = self.peek()
        if token is None:
            raise FakeFilterError("unexpected end of filter")
        self.position += 1
        return token

    def expr(self) -> Predicate:
        parts = [self.term()]
        while self.peek() == ("word", "OR"):
            self.take()
            parts.append(self.term())
        return parts[0] if len(parts) == 1 else (lambda item: any(p(item) for p in parts))

    def term(self) -> Predicate:
        parts = [self.factor()]
        while self.peek() == ("word", "AND"):
            self.take()
            parts.append(self.factor())
        return parts[0] if len(parts) == 1 else (lambda item: all(p(item) for p in parts))

    def factor(self) -> Predicate:
        kind, value = self.take()
        if (kind, value) == ("word", "NOT"):
            inner = self.factor()
            return lambda item: not inner(item)
        if kind == "lpar":
            inner = self.expr()
            if self.take()[0] != "rpar":
                raise FakeFilterError("unbalanced parentheses in filter")
            return inner
        if kind != "prop":
            raise FakeFilterError(f"unsupported filter clause at {value!r}")
        schema = canonical_schema(value)
        op_kind, op = self.take()
        if not (op_kind == "op" or (op_kind, op) == ("word", "LIKE")):
            raise FakeFilterError(f"unsupported filter operator: {op!r}")
        literal_kind, literal = self.take()
        if literal_kind not in ("str", "int"):
            raise FakeFilterError(f"unsupported filter value: {literal!r}")
        return _comparison(schema or value, op, literal_kind, literal)


def parse_filter(text: Any) -> Predicate:
    """Parse the DASL grammar the backend sends (design note 5 and its "Performance" section).

    ``""`` (no filter) or ``@SQL=`` + a boolean expression (``NOT``, ``AND``, ``OR``,
    parentheses) of restrictions on: the delivery/submit time
    (``'YYYY-MM-DD HH:MM'`` UTC, seconds ignored), ``PR_MESSAGE_CLASS`` (``=``,
    ``<>`` and ``LIKE`` with ``%``, case-insensitive) and ``PR_MSG_STATUS``
    (integer comparisons). A restriction on a missing property is false.
    Anything else raises :class:`FakeFilterError`.
    """
    if text is None or text == "":
        return lambda item: True
    if not isinstance(text, str) or not text.startswith("@SQL="):
        raise FakeFilterError(f"unsupported filter (only @SQL=): {text!r}")
    parser = _FilterParser(_tokens(text[len("@SQL="):]))
    predicate = parser.expr()
    if parser.peek() is not None:
        raise FakeFilterError(f"unsupported filter syntax at {parser.peek()!r}")
    return predicate


def _matches(item: "ItemSpec", predicate: Predicate) -> bool:
    return predicate(item)


# --------------------------------------------------------------------------- #
# Time zone for the date converter (no tzdata on Windows)
# --------------------------------------------------------------------------- #


class FakeZone(tzinfo):
    """Fixed or DST zone defined by UTC transition instants (pure Python)."""

    def __init__(
        self,
        name: str,
        standard_hours: float,
        dst_hours: float | None = None,
        dst_periods: Sequence[tuple[datetime, datetime]] = (),
    ) -> None:
        self._name = name
        self._std = timedelta(hours=standard_hours)
        self._dst = timedelta(hours=dst_hours if dst_hours is not None else standard_hours)
        self._periods = [
            (start.astimezone(timezone.utc).replace(tzinfo=None),
             end.astimezone(timezone.utc).replace(tzinfo=None))
            for start, end in dst_periods
        ]

    @classmethod
    def utc(cls) -> "FakeZone":
        return cls("UTC", 0)

    @classmethod
    def fixed(cls, hours: float, name: str | None = None) -> "FakeZone":
        return cls(name or f"UTC{hours:+g}", hours)

    @classmethod
    def santiago(cls) -> "FakeZone":
        """Chile-like zone: -04:00, -03:00 in summer (transitions at 04:00/03:00 UTC)."""
        utc = timezone.utc
        return cls(
            "Test/Santiago",
            -4,
            -3,
            (
                (datetime(2025, 9, 7, 4, tzinfo=utc), datetime(2026, 4, 5, 3, tzinfo=utc)),
                (datetime(2026, 9, 6, 4, tzinfo=utc), datetime(2027, 4, 4, 3, tzinfo=utc)),
            ),
        )

    def _in_dst(self, utc_naive: datetime) -> bool:
        return any(start <= utc_naive < end for start, end in self._periods)

    def utcoffset(self, dt: datetime | None) -> timedelta:
        if dt is None or not self._periods:
            return self._std
        local = dt.replace(tzinfo=None)
        dst_ok = self._in_dst(local - self._dst)
        std_ok = not self._in_dst(local - self._std)
        if dst_ok and std_ok:  # repeated hour
            return self._dst if dt.fold == 0 else self._std
        if dst_ok:
            return self._dst
        return self._std

    def dst(self, dt: datetime | None) -> timedelta:
        return self.utcoffset(dt) - self._std

    def tzname(self, dt: datetime | None) -> str:
        return self._name

    def fromutc(self, dt: datetime) -> datetime:
        utc_naive = dt.replace(tzinfo=None)
        offset = self._dst if self._in_dst(utc_naive) else self._std
        result = (utc_naive + offset).replace(tzinfo=self)
        if self.utcoffset(result) != offset:
            result = result.replace(fold=1)
        return result

    def __repr__(self) -> str:
        return f"FakeZone({self._name!r})"


# --------------------------------------------------------------------------- #
# Registry and SecurityCenter2 doubles (plan 4.2)
# --------------------------------------------------------------------------- #


class FakeRegistry:
    """``get_value(hive, key, name="")`` over a dict; missing ⇒ ``FileNotFoundError``."""

    def __init__(self, values: dict[tuple[str, str, str], Any] | None = None) -> None:
        self._values: dict[tuple[str, str, str], Any] = {}
        self.reads: list[tuple[str, str, str]] = []
        for (hive, key, name), value in (values or {}).items():
            self.set(hive, key, name, value)

    @staticmethod
    def _norm(hive: str, key: str, name: str) -> tuple[str, str, str]:
        return hive.upper(), key.strip("\\").lower(), name.lower()

    def set(self, hive: str, key: str, name: str, value: Any) -> "FakeRegistry":
        self._values[self._norm(hive, key, name)] = value
        return self

    def get_value(self, hive: str, key: str, name: str = "") -> Any:
        self.reads.append((hive, key, name))
        try:
            return self._values[self._norm(hive, key, name)]
        except KeyError:
            raise FileNotFoundError(2, "The system cannot find the file specified") from None

    @classmethod
    def outlook(cls, major: int = 16) -> "FakeRegistry":
        """Outlook registered with ``CurVer = Outlook.Application.<major>``."""
        return cls({(HKCR, CURVER_KEY, ""): f"Outlook.Application.{major}"})

    @classmethod
    def unregistered(cls) -> "FakeRegistry":
        return cls()


class FakeSecurityCenter:
    """``antivirus_products()`` like WMI ``root\\SecurityCenter2`` ``AntiVirusProduct``."""

    ACTIVE_STATE = 0x061000  # bit 0x1000: real-time protection on
    INACTIVE_STATE = 0x060000

    def __init__(self, products: Sequence[dict[str, Any]] = (), available: bool = True) -> None:
        self.products = [dict(p) for p in products]
        self.available = available
        self.queries = 0

    def antivirus_products(self) -> list[dict[str, Any]]:
        self.queries += 1
        if not self.available:
            raise OSError("SecurityCenter2 unavailable")
        return [dict(p) for p in self.products]

    @classmethod
    def active(cls) -> "FakeSecurityCenter":
        return cls([{"displayName": "Fake Defender", "productState": cls.ACTIVE_STATE}])

    @classmethod
    def inactive(cls) -> "FakeSecurityCenter":
        return cls([{"displayName": "Fake Defender", "productState": cls.INACTIVE_STATE}])

    @classmethod
    def none(cls) -> "FakeSecurityCenter":
        return cls([])

    @classmethod
    def unavailable(cls) -> "FakeSecurityCenter":
        return cls([], available=False)


# --------------------------------------------------------------------------- #
# Data model of a profile (test side)
# --------------------------------------------------------------------------- #

AUTO: Any = object()  # "generate a sensible value" for message_id / headers


@dataclass(eq=False)
class AttachmentSpec:
    name: str
    hidden: bool | None = None  # None: PR_ATTACHMENT_HIDDEN absent (visible)
    display_name: str | None = None
    #: Decoded bytes written by ``SaveAsFile`` (M10); an empty attachment is valid.
    content: bytes = b""
    #: Local size reported by the ``Size`` property; ``None`` derives it from
    #: ``content`` plus :data:`MAPI_SIZE_OVERHEAD`, like real Outlook (CR-01).
    size: int | None = None
    #: OlAttachmentType of the attachment (a by-value copy unless a test says otherwise).
    attachment_type: int = OL_BY_VALUE
    #: HRESULT raised by ``SaveAsFile`` (permission, corrupt, not downloaded...).
    save_error: int | None = None
    #: Materialization shape instead of a regular file: ``"symlink"`` or ``"directory"``.
    save_as: str | None = None


@dataclass(eq=False)
class RecipientSpec:
    name: str
    smtp: str | None
    type: int = OL_TO
    addrtype: str = "SMTP"
    email: str | None = None


@dataclass(eq=False)
class ItemSpec:
    key: str
    message_class: str = "IPM.Note"
    subject: str = ""
    sender_name: str = ""
    sender_smtp: str | None = None
    sender_email: str | None = None
    sender_addrtype: str = "SMTP"
    received: datetime | None = None
    sent: datetime | None = None
    read: bool = False
    flag_status: int = 0
    size: int = 2048
    message_id: Any = AUTO  # None: missing; "": empty
    headers: Any = AUTO  # None: no transport headers (internal mail)
    body: str = ""
    html: str = ""
    attachments: list[AttachmentSpec] = field(default_factory=list)
    recipients: list[RecipientSpec] = field(default_factory=list)
    msg_status: int = 0
    download_state: int = OL_FULL_ITEM
    openable: bool = True
    entry_id: str = ""
    short_id: str = ""
    folder: "FolderSpec | None" = None

    @property
    def kind(self) -> str:
        cls = self.message_class.lower()
        if cls.startswith("ipm.note"):
            return "mail"
        if cls.startswith("ipm.schedule.meeting"):
            return "meeting"
        if cls.startswith("ipm.report"):
            return "report"
        if cls.startswith("ipm.task"):
            return "task"
        if cls.startswith("ipm.post"):
            return "post"
        return "other"

    @property
    def pr_hasattach(self) -> bool:
        return bool(self.attachments)

    @property
    def smart_no_attach(self) -> bool:
        return not any(a.hidden is not True for a in self.attachments)

    @property
    def has_attachments(self) -> bool:
        """Visible attachments only (PR_HASATTACH and not PidLidSmartNoAttach)."""
        return self.pr_hasattach and not self.smart_no_attach

    def mapi(self, schema: str) -> Any:
        """Value of a canonical schema name, or ``_MISSING``."""
        sender_email = self.sender_email
        if sender_email is None and self.sender_addrtype.upper() == "SMTP":
            sender_email = self.sender_smtp
        values = {
            PR_SUBJECT: self.subject,
            PR_SENDER_NAME: self.sender_name,
            PR_SENDER_SMTP_ADDRESS: self.sender_smtp,
            PR_SENDER_EMAIL_ADDRESS: sender_email,
            PR_SENDER_ADDRTYPE: self.sender_addrtype,
            PR_MESSAGE_DELIVERY_TIME: self.received,
            PR_CLIENT_SUBMIT_TIME: self.sent,
            PR_MESSAGE_FLAGS: (MSGFLAG_READ if self.read else 0)
            | (MSGFLAG_HASATTACH if self.pr_hasattach else 0),
            PR_FLAG_STATUS: self.flag_status,
            PR_MESSAGE_SIZE: self.size,
            PR_INTERNET_MESSAGE_ID: self.message_id,
            PR_HASATTACH: self.pr_hasattach,
            PID_LID_SMART_NO_ATTACH: self.smart_no_attach,
            PR_MSG_STATUS: self.msg_status,
            PR_TRANSPORT_MESSAGE_HEADERS: self.headers,
            PR_MESSAGE_CLASS: self.message_class,
        }
        if schema in (PR_LONGTERM_ENTRYID_FROM_TABLE, PR_ENTRYID):
            return memoryview(bytes.fromhex(self.entry_id))
        value = values.get(schema)
        return _MISSING if value is None else value


@dataclass(eq=False)
class FolderSpec:
    key: str | None
    name: str
    store: "StoreSpec"
    parent: "FolderSpec | None"
    item_type: int = OL_MAIL_ITEM
    folder_type: int = FOLDER_GENERIC
    entry_id: str = ""
    children: list["FolderSpec"] = field(default_factory=list)
    items: list[ItemSpec] = field(default_factory=list)
    content_counters: bool = True  # False: PR_CONTENT_COUNT/PR_CONTENT_UNREAD missing

    def add_folder(self, name: str, **kwargs: Any) -> "FolderSpec":
        return self.store.add_folder(name, parent=self, **kwargs)

    def add_message(self, key: str, **fields: Any) -> ItemSpec:
        return self.store.owner._add_item(self, key, **fields)

    def walk(self) -> list["FolderSpec"]:
        out: list[FolderSpec] = []
        for child in self.children:
            out.append(child)
            out.extend(child.walk())
        return out


@dataclass(eq=False)
class AccountSpec:
    account_type: int
    smtp: str
    store: "StoreSpec"


LOCALES: dict[str, dict[str, str]] = {
    "en": {
        "inbox": "Inbox", "deleted": "Deleted Items", "sent": "Sent Items",
        "calendar": "Calendar", "contacts": "Contacts", "tasks": "Tasks",
        "sync": "Sync Issues", "conflicts": "Conflicts", "local": "Local Failures",
        "server": "Server Failures",
    },
    "es": {
        "inbox": "Bandeja de entrada", "deleted": "Elementos eliminados",
        "sent": "Elementos enviados", "calendar": "Calendario", "contacts": "Contactos",
        "tasks": "Tareas", "sync": "Problemas de sincronización", "conflicts": "Conflictos",
        "local": "Errores locales", "server": "Errores del servidor",
    },
    "de": {
        "inbox": "Posteingang", "deleted": "Gelöschte Elemente", "sent": "Gesendete Elemente",
        "calendar": "Kalender", "contacts": "Kontakte", "tasks": "Aufgaben",
        "sync": "Synchronisierungsprobleme", "conflicts": "Konflikte",
        "local": "Lokale Fehler", "server": "Serverfehler",
    },
}

_EXCHANGE_TYPES = (
    OL_PRIMARY_EXCHANGE_MAILBOX,
    OL_EXCHANGE_MAILBOX,
    OL_EXCHANGE_PUBLIC_FOLDER,
    OL_ADDITIONAL_EXCHANGE_MAILBOX,
)


def _digest(size: int, *parts: Any) -> bytes:
    seed = "|".join(str(p) for p in parts)
    out = b""
    counter = 0
    while len(out) < size:
        out += hashlib.sha256(f"{seed}#{counter}".encode("utf-8")).digest()
        counter += 1
    return out[:size]


@dataclass(eq=False)
class StoreSpec:
    key: str
    display_name: str
    store_type: int
    cached: bool
    file_path: str
    record_key: bytes
    owner: "FakeOutlook"
    unavailable: str | None = None  # None, "named" or "unnamed"
    entry_bytes: int = 70
    store_id: str = ""
    root: FolderSpec | None = None
    default_folders: dict[int, FolderSpec] = field(default_factory=dict)

    @property
    def uuid(self) -> str:
        """``account.uuid`` expected by the backend (design note 3)."""
        return str(_uuid.UUID(bytes=self.record_key)).upper()

    @property
    def inbox(self) -> FolderSpec | None:
        return self.default_folders.get(OL_FOLDER_INBOX)

    def walk(self) -> list[FolderSpec]:
        return self.root.walk() if self.root is not None else []

    def add_folder(
        self,
        name: str,
        *,
        parent: FolderSpec | None = None,
        key: str | None = None,
        item_type: int = OL_MAIL_ITEM,
        folder_type: int = FOLDER_GENERIC,
        default_id: int | None = None,
    ) -> FolderSpec:
        assert self.root is not None
        parent = parent if parent is not None else self.root
        folder = FolderSpec(key, name, self, parent, item_type, folder_type)
        folder.entry_id = self.owner._entry_id(self, "folder", 46 if self.entry_bytes > 24 else 24)
        parent.children.append(folder)
        if key is not None:
            self.owner._register_folder(key, folder)
        if default_id is not None:
            self.default_folders[default_id] = folder
        return folder

    def add_standard_folders(self, locale: str = "en", *, inbox: bool = True) -> None:
        names = LOCALES[locale]
        prefix = self.key
        if inbox:
            self.add_folder(names["inbox"], key=f"{prefix}:inbox", default_id=OL_FOLDER_INBOX)
        self.add_folder(names["deleted"], key=f"{prefix}:deleted", default_id=OL_FOLDER_DELETED)
        self.add_folder(names["sent"], key=f"{prefix}:sent", default_id=OL_FOLDER_SENT)
        self.add_folder(
            names["calendar"], key=f"{prefix}:calendar", item_type=OL_APPOINTMENT_ITEM,
            default_id=OL_FOLDER_CALENDAR,
        )
        self.add_folder(
            names["contacts"], key=f"{prefix}:contacts", item_type=OL_CONTACT_ITEM,
            default_id=OL_FOLDER_CONTACTS,
        )
        self.add_folder(
            names["tasks"], key=f"{prefix}:tasks", item_type=OL_TASK_ITEM,
            default_id=OL_FOLDER_TASKS,
        )
        sync = self.add_folder(
            names["sync"], key=f"{prefix}:sync", default_id=OL_FOLDER_SYNC_ISSUES
        )
        for role, default_id in (
            ("conflicts", OL_FOLDER_CONFLICTS),
            ("local", OL_FOLDER_LOCAL_FAILURES),
            ("server", OL_FOLDER_SERVER_FAILURES),
        ):
            sync.add_folder(names[role], key=f"{prefix}:{role}", default_id=default_id)


# --------------------------------------------------------------------------- #
# COM-facing objects (only the whitelisted members)
# --------------------------------------------------------------------------- #


class _ComObject:
    """Base of the fake COM objects: logs every member access by kind.

    Members are resolved case-insensitively (like ``IDispatch``) and logged as
    written. Properties are ``_get_<Member>`` and methods ``_call_<Member>``.
    """

    _KIND = ""
    _PROPS: tuple[str, ...] = ()
    _METHODS: tuple[str, ...] = ()
    _LOOKUP: dict[str, tuple[str, str]] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        lookup = {name.lower(): (name, "prop") for name in cls._PROPS}
        lookup.update({name.lower(): (name, "method") for name in cls._METHODS})
        cls._LOOKUP = lookup

    @classmethod
    def member_names(cls) -> tuple[str, ...]:
        return tuple(cls._PROPS) + tuple(cls._METHODS)

    def __init__(self, runtime: _Runtime) -> None:
        object.__setattr__(self, "_rt", runtime)

    def __getattribute__(self, name: str) -> Any:
        if name.startswith("_"):
            return object.__getattribute__(self, name)
        cls = type(self)
        rt: _Runtime = object.__getattribute__(self, "_rt")
        kind = cls._KIND
        found = cls._LOOKUP.get(name.lower())
        if found is None:
            if name.lower() in _FORBIDDEN_LOWER:
                rt.forbidden(kind, name)
                return _forbidden_callable
            rt.log.record(kind, name, "unknown")
            raise AttributeError(f"<unknown>.{name}")
        canonical, role = found
        if role == "prop":
            rt.log.record(kind, name, "get")
            rt.before(kind, canonical)
            return object.__getattribute__(self, "_get_" + canonical)()
        implementation = object.__getattribute__(self, "_call_" + canonical)

        def method(*args: Any) -> Any:
            rt.log.record(kind, name, "call", args)
            rt.before(kind, canonical)
            return implementation(*args)

        return method

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return
        rt: _Runtime = object.__getattribute__(self, "_rt")
        rt.log.record(type(self)._KIND, name, "set", (value,))
        rt.mutations.assignment(type(self)._KIND, name)

    def __delattr__(self, name: str) -> None:
        rt: _Runtime = object.__getattribute__(self, "_rt")
        rt.log.record(type(self)._KIND, name, "set", ())
        rt.mutations.assignment(type(self)._KIND, name)

    def __repr__(self) -> str:
        return f"<Fake{type(self)._KIND}>"


def _check_index(index: Any, size: int) -> int:
    if not isinstance(index, int) or isinstance(index, bool):
        raise TypeError("the Outlook fake supports integer collection indexes only")
    if not 1 <= index <= size:
        raise make_com_error(DISP_E_BADINDEX)
    return index - 1


class FakePropertyAccessor(_ComObject):
    _KIND = "PropertyAccessor"
    _METHODS = ("GetProperty",)

    def __init__(self, runtime: _Runtime, getter: Callable[[str], Any]) -> None:
        super().__init__(runtime)
        self._getter = getter

    def _call_GetProperty(self, schema_name: Any) -> Any:
        schema = canonical_schema(schema_name)
        if schema is None:
            raise make_com_error(E_INVALIDARG)
        value = self._getter(schema)
        if value is _MISSING or value is None:
            raise make_com_error(MAPI_E_NOT_FOUND, wrapped=True)
        return value


class FakeApplication(_ComObject):
    _KIND = "Application"
    _PROPS = ("Version", "Session")

    def __init__(self, runtime: _Runtime, owner: "FakeOutlook") -> None:
        super().__init__(runtime)
        self._owner = owner

    def _get_Version(self) -> str:
        return self._owner.version

    def _get_Session(self) -> "FakeNameSpace":
        return FakeNameSpace(self._rt, self._owner)


class FakeNameSpace(_ComObject):
    _KIND = "NameSpace"
    _PROPS = ("Stores", "Accounts")
    _METHODS = ("GetItemFromID",)

    def __init__(self, runtime: _Runtime, owner: "FakeOutlook") -> None:
        super().__init__(runtime)
        self._owner = owner

    def _get_Stores(self) -> "FakeStores":
        return FakeStores(self._rt, self._owner)

    def _get_Accounts(self) -> "FakeAccounts":
        return FakeAccounts(self._rt, self._owner)

    def _call_GetItemFromID(self, entry_id: Any, store_id: Any = None) -> "FakeItem":
        spec = self._owner.find_item(entry_id)
        if spec is None or (
            store_id not in (None, "") and str(store_id).upper() != spec.folder.store.store_id
        ):
            raise make_com_error(MAPI_E_NOT_FOUND, wrapped=True)
        if not spec.openable:
            raise make_com_error(E_FAIL, wrapped=True, text="Outlook cannot open this item.")
        return FakeItem(self._rt, spec)


class FakeStores(_ComObject):
    _KIND = "Stores"
    _PROPS = ("Count",)
    _METHODS = ("Item",)

    def __init__(self, runtime: _Runtime, owner: "FakeOutlook") -> None:
        super().__init__(runtime)
        self._owner = owner

    def _get_Count(self) -> int:
        return len(self._owner.stores)

    def _call_Item(self, index: Any) -> "FakeStore":
        return FakeStore(self._rt, self._owner.stores[_check_index(index, len(self._owner.stores))])


class FakeStore(_ComObject):
    _KIND = "Store"
    _PROPS = (
        "DisplayName", "ExchangeStoreType", "IsCachedExchange", "FilePath", "StoreID",
        "PropertyAccessor",
    )
    _METHODS = ("GetRootFolder", "GetDefaultFolder")

    def __init__(self, runtime: _Runtime, spec: StoreSpec) -> None:
        super().__init__(runtime)
        self._spec = spec

    def _available(self, member: str) -> None:
        mode = self._spec.unavailable
        if mode == "unnamed" or (mode == "named" and member != "DisplayName"):
            raise make_com_error(MAPI_E_LOGON_FAILED, wrapped=True)

    def _get_DisplayName(self) -> str:
        self._available("DisplayName")
        return self._spec.display_name

    def _get_ExchangeStoreType(self) -> int:
        self._available("ExchangeStoreType")
        return self._spec.store_type

    def _get_IsCachedExchange(self) -> bool:
        self._available("IsCachedExchange")
        return self._spec.cached

    def _get_FilePath(self) -> str:
        self._available("FilePath")
        return self._spec.file_path

    def _get_StoreID(self) -> str:
        self._available("StoreID")
        return self._spec.store_id

    def _get_PropertyAccessor(self) -> FakePropertyAccessor:
        self._available("PropertyAccessor")
        record_key = self._spec.record_key
        return FakePropertyAccessor(
            self._rt,
            lambda schema: memoryview(record_key) if schema == PR_RECORD_KEY else _MISSING,
        )

    def _call_GetRootFolder(self) -> "FakeFolder":
        self._available("GetRootFolder")
        assert self._spec.root is not None
        return FakeFolder(self._rt, self._spec.root)

    def _call_GetDefaultFolder(self, folder_type: Any) -> "FakeFolder":
        self._available("GetDefaultFolder")
        folder = self._spec.default_folders.get(folder_type)
        if folder is None:
            raise make_com_error(MAPI_E_NOT_FOUND, wrapped=True)
        return FakeFolder(self._rt, folder)


class FakeAccounts(_ComObject):
    _KIND = "Accounts"
    _PROPS = ("Count",)
    _METHODS = ("Item",)

    def __init__(self, runtime: _Runtime, owner: "FakeOutlook") -> None:
        super().__init__(runtime)
        self._owner = owner

    def _get_Count(self) -> int:
        return len(self._owner.accounts)

    def _call_Item(self, index: Any) -> "FakeAccount":
        accounts = self._owner.accounts
        return FakeAccount(self._rt, accounts[_check_index(index, len(accounts))])


class FakeAccount(_ComObject):
    _KIND = "Account"
    _PROPS = ("AccountType", "SmtpAddress", "DeliveryStore")

    def __init__(self, runtime: _Runtime, spec: AccountSpec) -> None:
        super().__init__(runtime)
        self._spec = spec

    def _get_AccountType(self) -> int:
        return self._spec.account_type

    def _get_SmtpAddress(self) -> str:
        return self._spec.smtp

    def _get_DeliveryStore(self) -> FakeStore:
        return FakeStore(self._rt, self._spec.store)


class FakeFolders(_ComObject):
    _KIND = "Folders"
    _PROPS = ("Count",)
    _METHODS = ("Item",)

    def __init__(self, runtime: _Runtime, spec: FolderSpec) -> None:
        super().__init__(runtime)
        self._spec = spec

    def _get_Count(self) -> int:
        return len(self._spec.children)

    def _call_Item(self, index: Any) -> "FakeFolder":
        children = self._spec.children
        return FakeFolder(self._rt, children[_check_index(index, len(children))])


class FakeFolder(_ComObject):
    _KIND = "Folder"
    _PROPS = ("Name", "EntryID", "DefaultItemType", "Folders", "PropertyAccessor")
    _METHODS = ("GetTable",)

    def __init__(self, runtime: _Runtime, spec: FolderSpec) -> None:
        super().__init__(runtime)
        self._spec = spec

    def _get_Name(self) -> str:
        return self._spec.name

    def _get_EntryID(self) -> str:
        return self._spec.entry_id

    def _get_DefaultItemType(self) -> int:
        return self._spec.item_type

    def _get_Folders(self) -> FakeFolders:
        return FakeFolders(self._rt, self._spec)

    def _get_PropertyAccessor(self) -> FakePropertyAccessor:
        spec = self._spec

        def getter(schema: str) -> Any:
            if schema == PR_FOLDER_TYPE:
                return spec.folder_type
            if spec.content_counters and schema == PR_CONTENT_COUNT:
                return len(spec.items)  # every user item: the rows of its table
            if spec.content_counters and schema == PR_CONTENT_UNREAD:
                return sum(1 for item in spec.items if not item.read)
            return _MISSING

        return FakePropertyAccessor(self._rt, getter)

    def _call_GetTable(self, filter_text: Any = "", table_contents: Any = OL_USER_ITEMS) -> "FakeTable":
        clauses = parse_filter(filter_text)
        rows = (
            [item for item in self._spec.items if _matches(item, clauses)]
            if table_contents == OL_USER_ITEMS
            else []
        )
        return FakeTable(self._rt, rows, self._spec.store.owner.zone)


class FakeColumn(_ComObject):
    _KIND = "Column"


class FakeColumns(_ComObject):
    _KIND = "Columns"
    _METHODS = ("Add",)

    def __init__(self, runtime: _Runtime, table: "FakeTable") -> None:
        super().__init__(runtime)
        self._table = table

    def _call_Add(self, name: Any) -> FakeColumn:
        schema = canonical_schema(name)
        if schema is None:
            builtin = _BUILTIN_COLUMNS.get(str(name).lower())
            if builtin is None:
                raise make_com_error(E_INVALIDARG)
            schema = builtin
        self._table._columns.append(schema)
        return FakeColumn(self._rt)


class FakeTable(_ComObject):
    _KIND = "Table"
    _PROPS = ("Columns", "EndOfTable")
    _METHODS = ("GetNextRow", "GetRowCount", "GetArray")

    def __init__(self, runtime: _Runtime, rows: list[ItemSpec], zone: tzinfo) -> None:
        super().__init__(runtime)
        self._rows = rows
        self._cursor = 0
        self._columns: list[str] = list(DEFAULT_COLUMNS)
        self._zone = zone

    def _get_Columns(self) -> FakeColumns:
        return FakeColumns(self._rt, self)

    def _get_EndOfTable(self) -> bool:
        return self._cursor >= len(self._rows)

    def _call_GetRowCount(self) -> int:
        return len(self._rows)

    def _call_GetNextRow(self) -> "FakeRow | None":
        if self._cursor >= len(self._rows):
            return None
        item = self._rows[self._cursor]
        self._cursor += 1
        return FakeRow(self._rt, self, item)

    def _call_GetArray(self, max_rows: Any) -> "list[tuple] | tuple":
        """The next ``max_rows`` rows as a list of value tuples (verified on the host).

        Like ``GetNextRow``, it advances the cursor; past the end it returns ``()``.
        """
        if not isinstance(max_rows, int) or isinstance(max_rows, bool) or max_rows < 1:
            raise make_com_error(E_INVALIDARG)
        chunk = self._rows[self._cursor:self._cursor + max_rows]
        if not chunk:
            return ()
        self._cursor += len(chunk)
        return [tuple(self._value(item, column) for column in self._columns) for item in chunk]

    def _value(self, item: ItemSpec, column: str) -> Any:
        if column.startswith("http://"):
            value = item.mapi(column)
            return None if value is _MISSING else value
        if column == "EntryID":
            return item.short_id
        if column == "Subject":
            return item.subject
        if column == "MessageClass":
            return item.message_class
        if column == "SentOn":
            moment = item.sent
        else:  # CreationTime, LastModificationTime, ReceivedTime
            moment = item.received
        if moment is None:
            return None
        # Built-in time columns: local wall clock labelled as UTC (P-5).
        return moment.astimezone(self._zone).replace(tzinfo=timezone.utc)


class FakeRow(_ComObject):
    _KIND = "Row"
    _METHODS = ("GetValues",)

    def __init__(self, runtime: _Runtime, table: FakeTable, item: ItemSpec) -> None:
        super().__init__(runtime)
        self._table = table
        self._item = item

    def _call_GetValues(self) -> tuple:
        return tuple(self._table._value(self._item, column) for column in self._table._columns)


class FakeAttachments(_ComObject):
    _KIND = "Attachments"
    _PROPS = ("Count",)
    _METHODS = ("Item",)

    def __init__(self, runtime: _Runtime, spec: ItemSpec) -> None:
        super().__init__(runtime)
        self._spec = spec

    def _get_Count(self) -> int:
        return len(self._spec.attachments)

    def _call_Item(self, index: Any) -> "FakeAttachment":
        attachments = self._spec.attachments
        return FakeAttachment(self._rt, attachments[_check_index(index, len(attachments))])


class FakeAttachment(_ComObject):
    _KIND = "Attachment"
    _PROPS = ("FileName", "DisplayName", "PropertyAccessor", "Size", "Type")
    _METHODS = ("SaveAsFile",)

    def __init__(self, runtime: _Runtime, spec: AttachmentSpec) -> None:
        super().__init__(runtime)
        self._spec = spec

    def _get_FileName(self) -> str:
        return self._spec.name

    def _get_DisplayName(self) -> str:
        return self._spec.display_name or self._spec.name

    def _get_Size(self) -> int:
        if self._spec.size is not None:
            return int(self._spec.size)
        return len(self._spec.content) + MAPI_SIZE_OVERHEAD

    def _get_Type(self) -> int:
        return int(self._spec.attachment_type)

    def _call_SaveAsFile(self, path: Any) -> None:
        """Materialize the local attachment into ``path`` (the M10 COM exception).

        Stands in for ``Attachment.SaveAsFile``: writes the decoded bytes to the
        backend-provided staging path, or raises the configured COM error. The
        mailbox mutation counters stay at zero: this is an explicit, whitelisted
        copy of an already-downloaded attachment, not a change to the store.
        """
        spec = self._spec
        if spec.save_error is not None:
            raise make_com_error(spec.save_error, wrapped=True)
        target = Path(str(path))
        if spec.save_as == "directory":
            target.mkdir(parents=True, exist_ok=True)
            return
        if spec.save_as == "symlink":
            outside = target.parent / "materialized-outside.bin"
            outside.write_bytes(spec.content)
            if target.is_symlink() or target.exists():
                target.unlink()
            os.symlink(outside, target)
            return
        target.write_bytes(spec.content)

    def _get_PropertyAccessor(self) -> FakePropertyAccessor:
        spec = self._spec
        values = {
            PR_ATTACHMENT_HIDDEN: spec.hidden,
            PR_ATTACH_LONG_FILENAME: spec.name,
            PR_DISPLAY_NAME: spec.display_name or spec.name,
        }
        return FakePropertyAccessor(self._rt, lambda schema: values.get(schema, _MISSING))


class FakeRecipients(_ComObject):
    _KIND = "Recipients"
    _PROPS = ("Count",)
    _METHODS = ("Item",)

    def __init__(self, runtime: _Runtime, spec: ItemSpec) -> None:
        super().__init__(runtime)
        self._spec = spec

    def _get_Count(self) -> int:
        return len(self._spec.recipients)

    def _call_Item(self, index: Any) -> "FakeRecipient":
        recipients = self._spec.recipients
        return FakeRecipient(self._rt, recipients[_check_index(index, len(recipients))])


class FakeRecipient(_ComObject):
    _KIND = "Recipient"
    _PROPS = ("Name", "Type", "PropertyAccessor")

    def __init__(self, runtime: _Runtime, spec: RecipientSpec) -> None:
        super().__init__(runtime)
        self._spec = spec

    def _get_Name(self) -> str:
        return self._spec.name

    def _get_Type(self) -> int:
        return self._spec.type

    def _get_PropertyAccessor(self) -> FakePropertyAccessor:
        spec = self._spec
        email = spec.email
        if email is None and spec.addrtype.upper() == "SMTP":
            email = spec.smtp
        values = {
            PR_SMTP_ADDRESS: spec.smtp,
            PR_ADDRTYPE: spec.addrtype,
            PR_EMAIL_ADDRESS: email,
            PR_DISPLAY_NAME: spec.name,
        }
        return FakePropertyAccessor(self._rt, lambda schema: values.get(schema, _MISSING))


class FakeItem(_ComObject):
    """Any item opened with ``GetItemFromID`` (MailItem, MeetingItem, ReportItem...)."""

    _KIND = "Item"
    _PROPS = (
        "MessageClass", "EntryID", "Parent", "DownloadState", "Body", "HTMLBody",
        "Attachments", "Recipients", "PropertyAccessor",
    )

    def __init__(self, runtime: _Runtime, spec: ItemSpec) -> None:
        super().__init__(runtime)
        self._spec = spec

    def _get_MessageClass(self) -> str:
        return self._spec.message_class

    def _get_EntryID(self) -> str:
        return self._spec.entry_id

    def _get_Parent(self) -> FakeFolder:
        assert self._spec.folder is not None
        return FakeFolder(self._rt, self._spec.folder)

    def _get_DownloadState(self) -> int:
        return self._spec.download_state

    def _get_Body(self) -> str:
        return self._spec.body

    def _get_HTMLBody(self) -> str:
        # MeetingItem, ReportItem and TaskItem have no HTMLBody (verified on the host).
        if self._spec.kind not in ("mail", "post"):
            raise AttributeError("<unknown>.HTMLBody")
        return self._spec.html

    def _get_Attachments(self) -> FakeAttachments:
        return FakeAttachments(self._rt, self._spec)

    def _get_Recipients(self) -> FakeRecipients:
        return FakeRecipients(self._rt, self._spec)

    def _get_PropertyAccessor(self) -> FakePropertyAccessor:
        return FakePropertyAccessor(self._rt, self._spec.mapi)


COM_CLASSES: dict[str, type[_ComObject]] = {
    cls._KIND: cls
    for cls in (
        FakeApplication, FakeNameSpace, FakeStores, FakeStore, FakeAccounts, FakeAccount,
        FakeFolders, FakeFolder, FakeTable, FakeColumns, FakeColumn, FakeRow,
        FakePropertyAccessor, FakeItem, FakeAttachments, FakeAttachment, FakeRecipients,
        FakeRecipient,
    )
}


# --------------------------------------------------------------------------- #
# The fake profile / connector
# --------------------------------------------------------------------------- #


def _utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


_OST_DIR = "C:\\Users\\ana\\AppData\\Local\\Microsoft\\Outlook\\"
_PST_DIR = "C:\\Users\\ana\\Documents\\Outlook Files\\"
_BASE_DATE = _utc(2026, 10, 15, 12, 0, 0)


class FakeOutlook:
    """A running classic Outlook with one profile, built in memory.

    It is the connector passed as ``get_backend(outlook_app=...)``; ``registry``,
    ``security_center``, ``zone`` and :meth:`drive_type` are the other seams.
    """

    def __init__(
        self,
        *,
        running: bool = True,
        version: str = DEFAULT_VERSION,
        registry: FakeRegistry | None = None,
        security_center: FakeSecurityCenter | None = None,
        zone: tzinfo | None = None,
    ) -> None:
        self._rt = _Runtime()
        self.running = running
        self.version = version
        self.registry = registry if registry is not None else FakeRegistry.outlook(16)
        self.security_center = (
            security_center if security_center is not None else FakeSecurityCenter.active()
        )
        self.zone: tzinfo = zone if zone is not None else FakeZone.utc()
        self.drive_types: dict[str, int] = {"C:": DRIVE_FIXED}
        self.stores: list[StoreSpec] = []
        self.accounts: list[AccountSpec] = []
        self.items: dict[str, ItemSpec] = {}
        self.folders: dict[str, FolderSpec] = {}
        self._counter = 0

    # -- observability ------------------------------------------------------ #

    @property
    def call_log(self) -> CallLog:
        return self._rt.log

    @property
    def mutations(self) -> Mutations:
        return self._rt.mutations

    @property
    def hangs(self) -> int:
        return self._rt.hangs

    # -- connector (win32com.client subset) --------------------------------- #

    def GetActiveObject(self, prog_id: str) -> FakeApplication:  # noqa: N802 - COM name
        self._rt.log.record("Connector", "GetActiveObject", "call", (prog_id,))
        self._rt.before("Connector", "GetActiveObject")
        if prog_id != PROG_ID:
            raise make_com_error(CO_E_CLASSSTRING)
        if not self.running:
            raise make_com_error(MK_E_UNAVAILABLE)
        return FakeApplication(self._rt, self)

    @property
    def Dispatch(self) -> Callable[..., None]:  # noqa: N802 - forbidden COM entry point
        self._rt.forbidden("Connector", "Dispatch")
        return _forbidden_callable

    @property
    def DispatchEx(self) -> Callable[..., None]:  # noqa: N802
        self._rt.forbidden("Connector", "DispatchEx")
        return _forbidden_callable

    @property
    def EnsureDispatch(self) -> Callable[..., None]:  # noqa: N802
        self._rt.forbidden("Connector", "EnsureDispatch")
        return _forbidden_callable

    # -- other seams --------------------------------------------------------- #

    def drive_type(self, root: str) -> int:
        """``GetDriveTypeW`` stand-in: UNC ⇒ remote; else by drive letter."""
        text = str(root)
        if text.startswith("\\\\"):
            return DRIVE_REMOTE
        return self.drive_types.get(text[:2].upper(), DRIVE_NO_ROOT_DIR)

    # -- failure injection --------------------------------------------------- #

    def fail_next(
        self,
        error: int,
        *,
        kind: str | None = None,
        member: str | None = None,
        times: int = 1,
        skip: int = 0,
        wrapped: bool = False,
    ) -> None:
        """Raise ``error`` (an HRESULT) on the next matching OOM access(es).

        ``kind``/``member`` ``None`` match any OOM object/member (never the
        connector unless ``kind="Connector"``); ``skip`` lets that many matching
        accesses through first.
        """
        self._rt.rules.append(_Rule(kind, member, (error, wrapped), False, 0.0, times, skip))

    def reject_next(
        self,
        times: int = 1,
        *,
        hresult: int = RPC_E_CALL_REJECTED,
        kind: str | None = None,
        member: str | None = None,
    ) -> None:
        """Transient rejection (``RPC_E_CALL_REJECTED`` by default) ``times`` times."""
        self.fail_next(hresult, kind=kind, member=member, times=times)

    def hang_next(
        self,
        *,
        kind: str | None = None,
        member: str | None = None,
        timeout: float = 60.0,
        skip: int = 0,
    ) -> None:
        """Block the next matching access until :meth:`release` or ``timeout`` seconds."""
        self._rt.release_event.clear()
        self._rt.rules.append(_Rule(kind, member, None, True, timeout, 1, skip))

    def release(self) -> None:
        self._rt.release_event.set()

    # -- lookup --------------------------------------------------------------- #

    def store(self, key: str) -> StoreSpec:
        for spec in self.stores:
            if spec.key == key:
                return spec
        raise KeyError(key)

    def folder(self, key: str) -> FolderSpec:
        return self.folders[key]

    def item(self, key: str) -> ItemSpec:
        return self.items[key]

    def account_for(self, store_key: str) -> AccountSpec | None:
        for account in self.accounts:
            if account.store.key == store_key:
                return account
        return None

    def find_item(self, entry_id: Any) -> ItemSpec | None:
        wanted = str(entry_id).upper()
        for spec in self.items.values():
            if wanted in (spec.entry_id, spec.short_id):
                return spec
        return None

    # -- changes made by the user in Outlook ----------------------------------- #

    def move_item(self, key: str, folder: FolderSpec) -> ItemSpec:
        """Move an item to ``folder`` as the user would: its EntryID changes (annex B.4)."""
        spec = self.items[key]
        if spec.folder is not None:
            spec.folder.items.remove(spec)
        store = folder.store
        index = self._next()
        spec.entry_id = self._entry_id(store, "item", store.entry_bytes)
        spec.short_id = _digest(24, "short", store.key, key, index).hex().upper()
        spec.folder = folder
        folder.items.append(spec)
        return spec

    # -- builders ------------------------------------------------------------- #

    def _next(self) -> int:
        self._counter += 1
        return self._counter

    def _entry_id(self, store: StoreSpec, role: str, size: int) -> str:
        unique = _digest(size - 20, role, store.key, self._next())
        return ("00000000" + store.record_key.hex() + unique.hex()).upper()

    def _register_folder(self, key: str, folder: FolderSpec) -> None:
        if key in self.folders:
            raise ValueError(f"duplicate folder key {key!r}")
        self.folders[key] = folder

    def add_store(
        self,
        key: str,
        display_name: str,
        *,
        store_type: int = OL_NOT_EXCHANGE,
        cached: bool = False,
        file_path: str = "",
        record_key: bytes | None = None,
        unavailable: str | None = None,
        entry_bytes: int | None = None,
    ) -> StoreSpec:
        if any(spec.key == key for spec in self.stores):
            raise ValueError(f"duplicate store key {key!r}")
        record_key = record_key if record_key is not None else _digest(16, "record-key", key)
        spec = StoreSpec(
            key=key,
            display_name=display_name,
            store_type=store_type,
            cached=cached,
            file_path=file_path,
            record_key=record_key,
            owner=self,
            unavailable=unavailable,
            entry_bytes=entry_bytes or (70 if store_type in _EXCHANGE_TYPES else 24),
        )
        spec.store_id = (
            "0000000038A1BB1005E5101AA1BB08002B2A56C20000454D534D44422E444C4C00000000"
            + record_key.hex().upper()
            + _digest(40, "store-id", key).hex().upper()
        )
        spec.root = FolderSpec(None, "Top of Information Store", spec, None)
        spec.root.entry_id = self._entry_id(spec, "root", 46 if spec.entry_bytes > 24 else 24)
        self.stores.append(spec)
        return spec

    def add_account(self, store: StoreSpec, account_type: int, smtp: str) -> AccountSpec:
        account = AccountSpec(account_type, smtp, store)
        self.accounts.append(account)
        return account

    def add_exchange_account(
        self,
        key: str,
        smtp: str,
        *,
        cached: bool = True,
        locale: str = "en",
        record_key: bytes | None = None,
    ) -> StoreSpec:
        """Delivery store of an Exchange account (type 0 for the first, 4 after: host values)."""
        first = not any(a.account_type == OL_EXCHANGE for a in self.accounts)
        store = self.add_store(
            key,
            smtp,
            store_type=OL_PRIMARY_EXCHANGE_MAILBOX if first else OL_ADDITIONAL_EXCHANGE_MAILBOX,
            cached=cached,
            file_path=f"{_OST_DIR}{smtp}.ost" if cached else "",
            record_key=record_key,
        )
        store.add_standard_folders(locale)
        self.add_account(store, OL_EXCHANGE, smtp)
        return store

    def _file_account(
        self, key: str, smtp: str, account_type: int, file_path: str, locale: str
    ) -> StoreSpec:
        store = self.add_store(key, smtp, file_path=file_path)
        store.add_standard_folders(locale)
        self.add_account(store, account_type, smtp)
        return store

    def add_imap_account(self, key: str, smtp: str, *, file_path: str | None = None, locale: str = "en") -> StoreSpec:
        return self._file_account(key, smtp, OL_IMAP, file_path or f"{_OST_DIR}{smtp}.ost", locale)

    def add_pop3_account(self, key: str, smtp: str, *, file_path: str | None = None, locale: str = "en") -> StoreSpec:
        return self._file_account(key, smtp, OL_POP3, file_path or f"{_PST_DIR}{smtp}.pst", locale)

    def add_eas_account(self, key: str, smtp: str, *, file_path: str | None = None, locale: str = "en") -> StoreSpec:
        return self._file_account(key, smtp, OL_EAS, file_path or f"{_OST_DIR}{smtp}.ost", locale)

    def add_other_account(
        self, key: str, smtp: str, *, account_type: int = OL_HTTP, file_path: str | None = None
    ) -> StoreSpec:
        return self._file_account(key, smtp, account_type, file_path or f"{_PST_DIR}{smtp}.pst", "en")

    def add_pst(
        self, key: str, display_name: str, file_path: str, *, with_inbox: bool = True, locale: str = "en"
    ) -> StoreSpec:
        store = self.add_store(key, display_name, file_path=file_path)
        if with_inbox:
            store.add_standard_folders(locale)
        else:
            store.add_folder(LOCALES[locale]["deleted"], key=f"{key}:deleted", default_id=OL_FOLDER_DELETED)
        return store

    def add_shared_mailbox(self, key: str, display_name: str, *, record_key: bytes | None = None) -> StoreSpec:
        store = self.add_store(key, display_name, store_type=OL_EXCHANGE_MAILBOX, record_key=record_key)
        store.add_standard_folders("en")
        return store

    def add_public_folders(self, key: str, display_name: str) -> StoreSpec:
        store = self.add_store(key, display_name, store_type=OL_EXCHANGE_PUBLIC_FOLDER)
        store.add_folder("All Public Folders", key=f"{key}:all", item_type=OL_POST_ITEM)
        return store

    def add_online_store(self, key: str, display_name: str) -> StoreSpec:
        """Another Exchange store without local copy (online archive, M365 group)."""
        store = self.add_store(key, display_name, store_type=OL_ADDITIONAL_EXCHANGE_MAILBOX)
        store.add_standard_folders("en")
        return store

    def add_unavailable_store(self, key: str, display_name: str | None = None) -> StoreSpec:
        """A store whose properties cannot be read (``DisplayName`` readable if given)."""
        return self.add_store(
            key,
            display_name or "",
            store_type=OL_EXCHANGE_MAILBOX,
            unavailable="named" if display_name else "unnamed",
        )

    def _add_item(
        self,
        folder: FolderSpec,
        key: str,
        *,
        sender: tuple[str, str | None] | None = None,
        to: Sequence[tuple[str, str | None]] = (),
        cc: Sequence[tuple[str, str | None]] = (),
        **fields: Any,
    ) -> ItemSpec:
        if key in self.items:
            raise ValueError(f"duplicate item key {key!r}")
        spec = ItemSpec(key=key, **fields)
        index = self._next()
        if sender is not None:
            spec.sender_name, spec.sender_smtp = sender
        spec.recipients.extend(RecipientSpec(n, a, OL_TO) for n, a in to)
        spec.recipients.extend(RecipientSpec(n, a, OL_CC) for n, a in cc)
        if spec.received is None:
            spec.received = _BASE_DATE + timedelta(hours=index)
        if spec.sent is None:
            spec.sent = spec.received - timedelta(seconds=6)
        if spec.message_id is AUTO:
            spec.message_id = f"<{key}.{index}@example.test>"
        if spec.headers is AUTO:
            spec.headers = _transport_headers(spec)
        store = folder.store
        spec.entry_id = self._entry_id(store, "item", store.entry_bytes)
        spec.short_id = _digest(24, "short", store.key, key, index).hex().upper()
        spec.folder = folder
        folder.items.append(spec)
        self.items[key] = spec
        return spec

    # -- named scenarios ------------------------------------------------------- #

    @classmethod
    def default(cls) -> "FakeOutlook":
        """TC-02 golden profile: one cached Exchange account and an excluded shared mailbox.

        INBOX holds a normal message with a visible attachment, a header-only one
        and an S/MIME encrypted one. Every value is fixed (goldens).
        """
        fake = cls()
        exchange = fake.add_exchange_account(
            "exchange",
            "ana.perez@example.com",
            record_key=bytes.fromhex("D70DBCF61C2A4B6E9A51E0C3B2A49F10"),
        )
        me = ("Ana Pérez", "ana.perez@example.com")
        inbox = exchange.inbox
        assert inbox is not None
        inbox.add_message(
            "normal",
            subject="Factura octubre 2026",
            sender=("Proveedor SA", "facturas@proveedor.example"),
            to=[me],
            received=_utc(2026, 11, 2, 13, 54, 9),
            sent=_utc(2026, 11, 2, 13, 54, 3),
            size=48213,
            message_id="<factura-2026-10@proveedor.example>",
            body="Estimado cliente, adjuntamos la factura de octubre.\r\n",
            html="<p>Estimado cliente, adjuntamos la factura de octubre.</p>",
            attachments=[AttachmentSpec("factura-2026-10.pdf")],
        )
        inbox.add_message(
            "header_only",
            subject="Informe semanal",
            sender=("Equipo de datos", "datos@example.com"),
            to=[me],
            received=_utc(2026, 11, 1, 9, 0, 0),
            sent=_utc(2026, 11, 1, 8, 59, 50),
            read=True,
            size=3120,
            message_id="<informe-44@example.com>",
            download_state=OL_HEADER_ONLY,
        )
        inbox.add_message(
            "smime_encrypted",
            message_class="IPM.Note.SMIME",
            subject="Contrato confidencial",
            sender=("Legal", "legal@example.com"),
            to=[me],
            received=_utc(2026, 10, 31, 18, 30, 0),
            sent=_utc(2026, 10, 31, 18, 29, 55),
            size=95104,
            message_id="<contrato-7@example.com>",
            attachments=[AttachmentSpec("smime.p7m")],
        )
        shared = fake.add_shared_mailbox(
            "shared", "Soporte", record_key=bytes.fromhex("1D95A7C2E4F6081A2B3C4D5E6F708192")
        )
        assert shared.inbox is not None
        shared.inbox.add_message(
            "shared_message",
            subject="Ticket 1234",
            sender=("Cliente", "cliente@example.org"),
            to=[("Soporte", "soporte@example.com")],
            received=_utc(2026, 11, 2, 10, 0, 0),
        )
        return fake

    @classmethod
    def store_matrix(cls) -> "FakeOutlook":
        """Every candidate and excluded store kind of annex B.3, each with a message."""
        fake = cls()
        fake.drive_types.update({"E:": DRIVE_REMOVABLE, "Z:": DRIVE_REMOTE})
        fake.add_exchange_account("exchange_cached", "ana@example.com")
        fake.add_exchange_account("exchange_online", "bruno@example.com", cached=False)
        fake.add_shared_mailbox("shared", "Soporte")
        fake.add_public_folders("public", "Public Folders - ana@example.com")
        fake.add_imap_account("imap", "carla@example.org")
        fake.add_pop3_account("pop3", "diego@example.net")
        fake.add_eas_account("eas", "elena@outlook.example")
        fake.add_pst("pst", "Archivo 2024", f"{_PST_DIR}archivo2024.pst")
        no_inbox = fake.add_pst("pst_no_inbox", "Notas", f"{_PST_DIR}notas.pst", with_inbox=False)
        fake.add_pst("pst_removable", "Respaldo USB", "E:\\respaldo\\usb.pst")
        fake.add_pst("pst_unc", "Archivo 2019", "\\\\nas01\\backup\\archivo2019.pst")
        fake.add_pst("pst_mapped", "Archivo 2018", "Z:\\archivo2018.pst")
        fake.add_other_account("other_type", "fede@example.com")
        fake.add_online_store("exchange_archive", "Archivo en línea - ana@example.com")
        fake.add_unavailable_store("unavailable_named", "Buzón remoto")
        fake.add_unavailable_store("unavailable_unnamed")
        no_inbox.add_folder("Proyectos", key="pst_no_inbox:proyectos")
        for spec in fake.stores:
            if spec.unavailable is not None:
                continue
            target = spec.inbox or next(
                f for f in spec.walk() if f.item_type in (OL_MAIL_ITEM, OL_POST_ITEM)
                and f.key != f"{spec.key}:deleted"
            )
            target.add_message(
                f"{spec.key}_message",
                subject=f"Mensaje en {spec.key}",
                sender=("Remitente", "remitente@example.com"),
                to=[("Destino", "destino@example.com")],
            )
        return fake

    @classmethod
    def folder_matrix(cls) -> "FakeOutlook":
        """Localized INBOX (es, de), hidden sync folders, special and tricky folder names."""
        fake = cls()
        es = fake.add_exchange_account("es", "lucia@example.es", locale="es")
        inbox = es.inbox
        assert inbox is not None
        inbox.add_message("es_inbox_message", subject="Hola", sender=("A", "a@example.es"))
        facturas = inbox.add_folder("Facturas", key="es.facturas")
        facturas.add_message("es_factura", subject="Factura", sender=("B", "b@example.es"))
        proyectos = es.add_folder("Proyectos", key="es.proyectos")
        proyectos.add_folder("Inbox", key="es.proyectos_inbox").add_message(
            "es_proyectos_inbox", subject="No es la bandeja", sender=("C", "c@example.es")
        )
        es.add_folder("Clientes/Proveedores", key="es.slash").add_message(
            "es_slash", subject="Barra", sender=("D", "d@example.es")
        )
        es.add_folder("100% Reales", key="es.percent")
        es.add_folder("Facturación ñ", key="es.nonascii").add_message(
            "es_nonascii", subject="Acentos", sender=("E", "e@example.es")
        )
        archivo = es.add_folder("Archivo", key="es.archivo")
        archivo.add_folder("Facturas", key="es.archivo_facturas").add_message(
            "es_archivo_factura", subject="Factura antigua", sender=("F", "f@example.es")
        )
        es.add_folder("Correo sin leer", key="es.search", folder_type=FOLDER_SEARCH)
        es.default_folders[OL_FOLDER_CONFLICTS].add_message(
            "in_hidden_folder", subject="Conflicto", sender=("G", "g@example.es")
        )
        es.default_folders[OL_FOLDER_LOCAL_FAILURES].add_folder(
            "Antiguos", key="es.hidden_sub"
        ).add_message("in_hidden_subfolder", subject="Error local", sender=("H", "h@example.es"))
        de = fake.add_exchange_account("de", "jonas@example.de", locale="de")
        assert de.inbox is not None
        de.inbox.add_message("de_inbox_message", subject="Hallo", sender=("I", "i@example.de"))
        de.inbox.add_folder("Rechnungen", key="de.rechnungen").add_message(
            "de_rechnung", subject="Rechnung", sender=("J", "j@example.de")
        )
        return fake

    @classmethod
    def item_matrix(cls, now: datetime | None = None) -> "FakeOutlook":
        """Every item case of annex B.4 in one cached Exchange account.

        ``facturas_recent`` is received 3 days before ``now`` (default: the real
        current time), so recipes with ``--since 1mo`` find it (TC-04).
        """
        now = now if now is not None else datetime.now(timezone.utc).replace(microsecond=0)
        fake = cls()
        store = fake.add_exchange_account("exchange", "ana@example.com")
        inbox = store.inbox
        assert inbox is not None
        facturas = inbox.add_folder("Facturas", key="facturas")
        me = ("Ana", "ana@example.com")
        dn = "/O=EXAMPLE/OU=EXCHANGE ADMINISTRATIVE GROUP (FYDIBOHF23SPDLT)/CN=RECIPIENTS/CN="

        def add(key: str, **fields: Any) -> ItemSpec:
            fields.setdefault("subject", key.replace("_", " ").capitalize())
            fields.setdefault("sender", ("Remitente", "remitente@example.com"))
            fields.setdefault("to", [me])
            fields.setdefault("body", f"Cuerpo de {key}.\r\n")
            fields.setdefault("html", f"<p>Cuerpo de {key}.</p>")
            folder = fields.pop("folder", inbox)
            return folder.add_message(key, **fields)

        add("normal", cc=[("Copia", "copia@example.com")])
        add("smime_encrypted", message_class="IPM.Note.SMIME", body="", html="",
            attachments=[AttachmentSpec("smime.p7m")])
        add("smime_signed", message_class="IPM.Note.SMIME.MultipartSigned",
            body="Texto firmado.\r\n", attachments=[AttachmentSpec("smime.p7s")])
        add("header_only", download_state=OL_HEADER_ONLY, body="", html="")
        add("meeting_request", message_class="IPM.Schedule.Meeting.Request",
            body="Reunión de planificación.\r\n", html="")
        add("delivery_receipt", message_class="IPM.Report.IPM.Note.DR", html="")
        add("task", message_class="IPM.Task", html="")
        add("imap_deleted", msg_status=MSGSTATUS_DELMARKED)
        add("html_only", body="", html="<p>Solo <b>HTML</b></p>")
        add("html_no_text", body="", html="<html><body><img src=\"cid:logo\"></body></html>")
        add("no_message_id", message_id=None)
        add("empty_message_id", message_id="")
        add("internal_no_headers", headers=None, sender_addrtype="EX",
            sender_email=dn + "COLEGA", sender=("Colega", "colega@example.com"))
        add("no_smtp", sender_addrtype="EX", sender_email=dn + "SINSMTP",
            sender=("Sin SMTP", None),
            to=[],
            )
        fake.item("no_smtp").recipients.append(
            RecipientSpec("Destino sin SMTP", None, OL_TO, "EX", dn + "DESTINO")
        )
        add("exchange_dn", sender_addrtype="EX", sender_email=dn + "JEFE",
            sender=("Jefe", "jefe@example.com"))
        add("flagged", flag_status=FLAG_STATUS_FLAGGED)
        add("flagged_completed", flag_status=FLAG_STATUS_COMPLETE)
        add("visible_attachment", attachments=[AttachmentSpec("contrato.pdf")])
        add("hidden_attachment", attachments=[AttachmentSpec("image001.png", hidden=True)])
        add("unopenable_with_attachments", openable=False,
            attachments=[AttachmentSpec("informe.xlsx")])
        add("unopenable_without_attachments", openable=False)
        add("duplicate_inbox", message_id="<duplicado-1@example.com>")
        add("duplicate_facturas", message_id="<duplicado-1@example.com>", folder=facturas)
        add("facturas_recent", subject="Factura noviembre", folder=facturas,
            received=now - timedelta(days=3), attachments=[AttachmentSpec("factura-11.pdf")])
        add("same_date_a", received=_utc(2026, 10, 20, 8, 0, 0))
        add("same_date_b", received=_utc(2026, 10, 20, 8, 0, 0))
        add("dst_before", received=_utc(2026, 9, 6, 3, 30, 0))
        add("dst_after", received=_utc(2026, 9, 6, 4, 30, 0))
        return fake


    @classmethod
    def attachments_matrix(cls) -> "FakeOutlook":
        """Every attachment case of annex B.4 in one cached Exchange account (M10).

        Deterministic (fixed dates, EntryIDs derived from the fixed record key and
        the creation order) so the TC-09 goldens are stable. Only the ``local``
        item is materializable; the other cases exercise availability reasons,
        S/MIME/unreadable signals and the COM materialization exceptions.
        """
        fake = cls()
        exchange = fake.add_exchange_account(
            "exchange",
            "ana.perez@example.com",
            record_key=bytes.fromhex("D70DBCF61C2A4B6E9A51E0C3B2A49F10"),
        )
        inbox = exchange.inbox
        assert inbox is not None
        me = ("Ana Pérez", "ana.perez@example.com")

        def add(key: str, **fields: Any) -> ItemSpec:
            fields.setdefault("subject", key.replace("_", " ").capitalize())
            fields.setdefault("sender", ("Proveedor SA", "facturas@proveedor.example"))
            fields.setdefault("to", [me])
            fields.setdefault("received", _utc(2026, 11, 2, 13, 54, 9))
            fields.setdefault("sent", _utc(2026, 11, 2, 13, 54, 3))
            fields.setdefault("body", f"Cuerpo de {key}.\r\n")
            return inbox.add_message(key, **fields)

        add(
            "local",
            attachments=[
                AttachmentSpec(
                    "factura-2026-10.pdf",
                    content=b"%PDF-1.4\nFactura de octubre 2026\n",
                )
            ],
        )
        add(
            "two_same",
            attachments=[
                AttachmentSpec("recibo.pdf", content=b"recibo-A"),
                AttachmentSpec("recibo.pdf", content=b"recibo-B"),
                AttachmentSpec("otros.pdf", content=b"otros"),
            ],
        )
        add(
            "hidden",
            attachments=[
                AttachmentSpec("image001.png", hidden=True, content=b"PNG"),
                AttachmentSpec("visible.pdf", content=b"%PDF-1.4 visible"),
            ],
        )
        add(
            "header_only",
            download_state=OL_HEADER_ONLY,
            attachments=[AttachmentSpec("no-descargado.pdf", content=b"")],
        )
        add(
            "smime",
            message_class="IPM.Note.SMIME",
            body="",
            html="",
            attachments=[AttachmentSpec("smime.p7m", content=b"smime")],
        )
        add(
            "unopenable",
            openable=False,
            attachments=[AttachmentSpec("informe.xlsx", content=b"xlsx")],
        )
        add(
            "by_reference",
            attachments=[
                AttachmentSpec(
                    "enlace.pdf", attachment_type=OL_BY_REFERENCE, size=0
                )
            ],
        )
        add(
            "embedded",
            attachments=[
                AttachmentSpec(
                    "mensaje-adjunto.msg", attachment_type=OL_EMBEDDED_ITEM, size=0
                )
            ],
        )
        add(
            "ole",
            attachments=[AttachmentSpec("objeto.doc", attachment_type=OL_OLE, size=0)],
        )
        add("empty", attachments=[AttachmentSpec("vacio.txt", content=b"")])
        add(
            "executable",
            attachments=[
                AttachmentSpec("presupuesto.pdf", content=b"MZ\x90\x00 ejecutable")
            ],
        )
        add(
            "denied",
            attachments=[
                AttachmentSpec(
                    "privado.pdf", content=b"%PDF-1.4", save_error=E_ACCESSDENIED
                )
            ],
        )
        add(
            "corrupt",
            attachments=[
                AttachmentSpec("roto.pdf", content=b"%PDF-1.4", save_error=E_FAIL)
            ],
        )
        add(
            "partial_failure",
            attachments=[
                AttachmentSpec("bueno.pdf", content=b"%PDF-1.4 bueno"),
                AttachmentSpec(
                    "malo.pdf", content=b"%PDF-1.4 malo", save_error=E_FAIL
                ),
            ],
        )
        add(
            "gone",
            attachments=[
                AttachmentSpec(
                    "perdido.pdf", content=b"%PDF-1.4", save_error=MAPI_E_NOT_FOUND
                )
            ],
        )
        add(
            "invalid_staging",
            attachments=[
                AttachmentSpec(
                    "enlace-sucio.pdf",
                    content=b"%PDF-1.4",
                    save_as="symlink",
                )
            ],
        )
        add("no_attachments")
        return fake


def _transport_headers(spec: ItemSpec) -> str:
    def address(name: str, smtp: str | None) -> str:
        return f"{name} <{smtp}>" if smtp else name

    to = ", ".join(address(r.name, r.smtp) for r in spec.recipients if r.type == OL_TO)
    cc = ", ".join(address(r.name, r.smtp) for r in spec.recipients if r.type == OL_CC)
    lines = [
        "Received: from mx.example.test by mailbox.example.test",
        f"From: {address(spec.sender_name, spec.sender_smtp)}",
        f"To: {to}",
    ]
    if cc:
        lines.append(f"Cc: {cc}")
    lines.append(f"Subject: {spec.subject}")
    if spec.sent is not None:
        lines.append(f"Date: {format_datetime(spec.sent)}")
    if spec.message_id:
        lines.append(f"Message-ID: {spec.message_id}")
    return "\r\n".join(lines) + "\r\n\r\n"


def _with(fake: FakeOutlook, **changes: Any) -> FakeOutlook:
    for name, value in changes.items():
        setattr(fake, name, value)
    return fake


# Scenario name -> builder (used by run_cli and tests).
SCENARIOS: dict[str, Callable[[], FakeOutlook]] = {
    "default": FakeOutlook.default,
    "store_matrix": FakeOutlook.store_matrix,
    "folder_matrix": FakeOutlook.folder_matrix,
    "item_matrix": FakeOutlook.item_matrix,
    "attachments_matrix": FakeOutlook.attachments_matrix,
    "not_running": lambda: _with(FakeOutlook.default(), running=False),
    "unregistered": lambda: _with(FakeOutlook.default(), registry=FakeRegistry.unregistered()),
    "old_version": lambda: _with(FakeOutlook.default(), registry=FakeRegistry.outlook(15)),
}

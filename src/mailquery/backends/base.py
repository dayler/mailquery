"""Abstract mail backend interface (PRD 9.3) and common-model row types (PRD 11.1).

``search.py`` and ``config.py`` depend only on :class:`MailBackend`. Rows are
plain ``dict`` values typed with ``TypedDict``; the message-row keys are the
ones ``search.py`` uses today (no field renames in W2, plan 4.3).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, NotRequired, Sequence, TypedDict

# A uid is an ``int`` (Apple Mail) or an upper-case hex ``str`` (Outlook).
Uid = int | str


class StateUidError(ValueError):
    """An invalid ``state.json`` uid (PRD 11.2); each backend owns the wording.

    ``cursor_detail`` is the ``E_STATE_CORRUPT`` detail when the uid is
    ``cursor.last_uid``; ``ring_detail`` when it is an ``emitted_uids`` item.
    """

    def __init__(self, cursor_detail: str, ring_detail: str) -> None:
        super().__init__(cursor_detail)
        self.cursor_detail = cursor_detail
        self.ring_detail = ring_detail


class ExcludedStoreError(LookupError):
    """``find_message``: the uid belongs to an excluded store (PRD 12.4, annex B.4).

    ``entry`` is that store's ``excluded_stores()`` entry ``{label, path, reason}``;
    the core reports it as ``E_ACCOUNT_NOT_IN_SCOPE`` with the reason. Only a
    backend that excludes stores (Outlook) raises it.
    """

    def __init__(self, entry: dict[str, Any]) -> None:
        super().__init__(entry.get("reason"))
        self.entry = entry


class AccountRow(TypedDict):
    """Candidate account (PRD 9.3 ``accounts()``)."""

    uuid: str
    label: str
    email: str | None
    local: bool
    # Optional extras of backends whose label source differs from their store
    # (Apple Mail): position among the accounts that have folders (``None`` when
    # the account has none) and whether a label entry exists for it.
    store_index: NotRequired[int | None]
    labelled: NotRequired[bool]
    # Outlook only: the row is an excluded store, not a candidate; the value is
    # its ``excluded_stores()`` entry ``{label, path, reason}``. ``[scope]`` keys
    # resolve against these rows too, so a declared account that is excluded is
    # reported instead of being unknown (PRD 15.3). ``uuid`` is ``None`` when the
    # store could not be read (reason ``unavailable``).
    excluded: NotRequired[dict[str, Any]]


class MailboxRow(TypedDict):
    """Mailbox/folder (PRD 9.3 ``mailboxes()``); ``id`` is never exposed in JSON."""

    id: Any
    account_uuid: str
    name: str
    path: str
    url: str
    is_inbox: bool
    is_aggregate: bool
    total: int
    unread: int


class MessageRow(TypedDict, total=False):
    """Message metadata row, with the keys currently produced for ``search.py``."""

    uid: Uid
    global_message_id: int
    subject: str
    sender_name: str
    sender_address: str
    date_sent: float | None
    date_received: float | None
    mailbox_id: Any
    read: int
    flagged: int
    size: int
    message_id: str
    has_attachments: bool
    # Outlook only: the item's MessageClass, so that ``load_body`` knows an
    # S/MIME item without opening it (annex B.4).
    message_class: str


class AttachmentRow(TypedDict):
    """Attachment entry of a body (PRD 11.1)."""

    name: str


class BodySource(TypedDict):
    """Where the body came from (Outlook: ``partial=False``, ``emlx_path=None``)."""

    emlx_path: str | None
    partial: bool


class BodyRow(TypedDict):
    """Result of ``load_body`` (PRD 9.3)."""

    available: bool
    readable: bool
    partial: bool
    headers: dict[str, str]
    body_text: str
    attachments: list[AttachmentRow]
    source: BodySource
    warnings: list[str]


class MailBackend(ABC):
    """Operations every backend implements (PRD 9.3)."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Backend identifier: ``"apple_mail"`` or ``"outlook"``."""

    @abstractmethod
    def describe(self) -> dict[str, Any]:
        """Version data for logs and ``doctor``."""

    @abstractmethod
    def accounts(self) -> list[AccountRow]:
        """Candidate accounts ``{uuid, label, email, local}``; base of ``[scope]`` resolution."""

    @property
    @abstractmethod
    def labels_available(self) -> bool:
        """Whether account labels are available (always ``True`` on Outlook)."""

    @abstractmethod
    def mailboxes(self) -> Sequence[MailboxRow]:
        """Folders ``{id, account_uuid, name, path, url, is_inbox, is_aggregate, total, unread}``.

        Counters are searchable items, without deleted ones.
        """

    @abstractmethod
    def excluded_stores(self) -> list[dict[str, Any]]:
        """Excluded stores ``[{label, path, reason}]``; always ``[]`` on Apple Mail."""

    @abstractmethod
    def resolve_mailbox(self, account_uuid: str, ref: str) -> MailboxRow | None:
        """Folder for ``ref`` (name, path, URL or ``INBOX`` alias, case-insensitive) or ``None``."""

    @abstractmethod
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
        """Metadata rows of the common model, in total order ``(date_received, uid)``."""

    @abstractmethod
    def membership(self, uids: Sequence[Uid]) -> dict[Uid, set[Any]]:
        """Folders each uid belongs to (for dedupe and the result ``mailbox``)."""

    @abstractmethod
    def duplicate_counts(self, mailbox_ids: Sequence[Any]) -> dict[Any, int]:
        """Copies per global message key (for ``duplicate_count``)."""

    @abstractmethod
    def recipients(self, uids: Sequence[Uid]) -> dict[Uid, Any]:
        """Recipients (to/cc) per uid."""

    @abstractmethod
    def attachment_names(self, uid: Uid) -> list[str]:
        """Attachment names of one message."""

    @abstractmethod
    def find_message(self, uid: Uid) -> tuple[MessageRow, MailboxRow | None] | None:
        """Message row and its folder, or ``None``; the core checks the account is declared.

        Raises :class:`ExcludedStoreError` when the uid identifies an excluded store.
        """

    @abstractmethod
    def load_body(self, row: MessageRow) -> BodyRow:
        """``{available, readable, partial, headers, body_text, attachments, source, warnings}``.

        Never triggers downloads; S/MIME yields ``readable=False`` without reading content.
        """

    @abstractmethod
    def parse_uid(self, text: Any) -> Uid:
        """Backend uid from user text (int on Apple Mail, upper-case hex on Outlook) or ``E_USAGE``."""

    @abstractmethod
    def doctor_checks(self) -> list[dict[str, Any]]:
        """Backend environment checks for ``doctor`` (common ones are added by ``cli.py``)."""

    @abstractmethod
    def close(self) -> None:
        """Release the SQLite connection or COM references."""

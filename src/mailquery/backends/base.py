"""Backend protocol v1 (C1) and common-model row types.

``search.py`` and ``config.py`` depend only on :class:`MailBackend`. Rows are
plain ``dict`` values typed with ``TypedDict``; the message-row keys are the
ones ``search.py`` uses today (no field renames in W2, plan 4.3).

C1 (PRD-v2.1 §6.1 RF-38, plan §5.1) freezes the contract every driver
implements: ``driver``, ``plugin_api`` and ``capabilities`` metadata, the native
part of the uid and its order key, and the attachment metadata/stream operations
consumed by M06–M10. The contract uid is the opaque prefixed ``str`` of
:mod:`mailquery.uid`; the built-in adapters still exchange the legacy native uid
(``int`` for Apple Mail, upper-case hex ``str`` for Outlook) until M03, so the
transitional :data:`LegacyUid` alias keeps their values and signatures honest.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any, NotRequired, Sequence, TypedDict

from mailquery.plugins import Capabilities

#: Contract uid: an opaque ``"<driver>:<native_id>"`` string (RF-40).
Uid = str

#: Transitional alias for the native uid the built-in adapters exchange until M03.
LegacyUid = int | str


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
    """Message metadata row, with the keys currently produced for ``search.py``.

    Every listing row carries ``native_order_key`` (contract C1): a string the
    core compares as an integer when the driver capability ``native_order`` is
    ``numeric`` and as text when it is ``text`` (PRD-v2.1 §10.2 point 7).
    """

    uid: LegacyUid
    native_order_key: str
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


class AttachmentMetadataRow(TypedDict):
    """Ordered attachment metadata a driver returns for one message (C1, RF-43/RF-47).

    ``index`` is the 1-based, stable position shared by ``show`` and
    ``attachment``; ``size_bytes`` is the expected size when the driver knows it
    (``None`` otherwise); ``native_order_key`` orders attachments within the
    message; ``unavailable_reason`` is one of the §11.7 reasons when the
    attachment cannot be recovered (``None`` when it is available).
    """

    index: int
    name: str
    size_bytes: int | None
    native_order_key: str
    unavailable_reason: str | None


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
    """Backend protocol v1: operations and metadata every driver implements (C1, PRD 9.3)."""

    #: Contract metadata (RF-38). Built-in adapters override them with class attributes.
    @property
    @abstractmethod
    def driver(self) -> str:
        """Driver identifier: ``"apple_mail"``, ``"outlook"`` or the plugin's name."""

    @property
    @abstractmethod
    def plugin_api(self) -> int:
        """Plugin API version implemented by the driver; always ``1`` (C1)."""

    @property
    @abstractmethod
    def capabilities(self) -> Capabilities:
        """Declared capability map ``{network, readonly, body_local, attachments, native_order}``."""

    @property
    def native_order(self) -> str:
        """Native ordering mode of the driver: ``numeric`` or ``text`` (C1)."""
        return str(self.capabilities["native_order"])

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
        """Metadata rows of the common model; each row carries ``native_order_key`` (C1)."""

    @abstractmethod
    def membership(self, uids: Sequence[LegacyUid]) -> dict[LegacyUid, set[Any]]:
        """Folders each uid belongs to (for dedupe and the result ``mailbox``)."""

    @abstractmethod
    def duplicate_counts(self, mailbox_ids: Sequence[Any]) -> dict[Any, int]:
        """Copies per global message key (for ``duplicate_count``)."""

    @abstractmethod
    def recipients(self, uids: Sequence[LegacyUid]) -> dict[LegacyUid, Any]:
        """Recipients (to/cc) per uid."""

    @abstractmethod
    def attachment_names(self, uid: LegacyUid) -> list[str]:
        """Attachment names of one message."""

    @abstractmethod
    def find_message(
        self, uid: LegacyUid
    ) -> tuple[MessageRow, MailboxRow | None] | None:
        """Message row and its folder, or ``None``; the core checks the account is declared.

        Raises :class:`ExcludedStoreError` when the uid identifies an excluded store.
        """

    @abstractmethod
    def load_body(self, row: MessageRow) -> BodyRow:
        """``{available, readable, partial, headers, body_text, attachments, source, warnings}``.

        Never triggers downloads; S/MIME yields ``readable=False`` without reading content.
        """

    @abstractmethod
    def parse_uid(self, text: Any) -> LegacyUid:
        """Legacy backend uid from user text (int on Apple Mail, upper-case hex on Outlook).

        Transitional until M03 (the core parses the prefixed uid with
        :mod:`mailquery.uid`); raises ``E_USAGE`` on invalid input.
        """

    @abstractmethod
    def parse_native_id(self, native_id: str) -> LegacyUid:
        """Validate the native part of a prefixed uid and return the legacy uid (C1, RF-40).

        Pure and offline: it never opens the client or the store, so the core can
        validate a uid before creating the home or reading the config.
        """

    def attachments(self, uid: LegacyUid) -> list[AttachmentMetadataRow]:
        """Ordered attachment metadata of one message (C1, RF-43/RF-47).

        Implemented by the adapters in M09/M10; plugins must provide it (API 1).
        """
        raise NotImplementedError("the driver does not implement attachment metadata")

    def attachment_stream(self, uid: LegacyUid, index: int) -> Iterator[bytes]:
        """Decoded bytes of the attachment ``index`` (1-based) of one message (C1).

        Implemented by the adapters in M09/M10; plugins must provide it (API 1).
        The core never lets the driver write to the attachment cache.
        """
        raise NotImplementedError("the driver does not implement attachment streams")

    @abstractmethod
    def doctor_checks(self) -> list[dict[str, Any]]:
        """Backend environment checks for ``doctor`` (common ones are added by ``cli.py``)."""

    @abstractmethod
    def close(self) -> None:
        """Release the SQLite connection or COM references."""

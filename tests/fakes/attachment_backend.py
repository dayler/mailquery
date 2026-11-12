"""In-memory attachment backend double for the ``attachment`` command.

The double is a duck-typed API 1 backend the CLI can inject through
``cli.main(..., backend=...)`` (native path) or through an injected
:class:`~tests.fakes.plugin.FakeEntryPoint` (declared plugin path). It provides
the attachment surface with controllable data:

* capabilities (``attachments`` ``local``/``remote``/``none``),
* ordered attachment metadata (index, name, size, ``unavailable_reason``),
* decoded attachment streams (bytes per index, delays, injected errors),
* message existence, body readability and body warnings,
* the message-level S/MIME/unreadable signal: ``attachments()`` raises the
  protocol error (``PluginError(reason=smime|unreadable)`` or, for a built-in
  driver, ``MailqueryError E_ATTACHMENT_UNREADABLE``) exactly as the convention
  documented in ``docs/INTERFACES.md`` requires.

Pure Python: no filesystem writes, no network, no mail client access.
"""

from __future__ import annotations

import time
from typing import Any, Iterable, Iterator, Mapping, Sequence

from mailquery.errors import MailqueryError
from mailquery.plugins import PLUGIN_API, PluginError, Reason

#: Default driver of the double (a built-in name so the native path is valid).
DRIVER = "apple_mail"
#: Default external driver name of the double (valid ``[a-z0-9_]{1,64}``).
PLUGIN_DRIVER = "graph"

#: Account and mailbox identifiers of the double (opaque and stable).
ACCOUNT_UUID = "attachment-account"
ACCOUNT_LABEL = "iCloud (attachment@fixture.example)"
MAILBOX_ID = 1
#: Native uid of the double (an integer for ``apple_mail``).
NATIVE_UID = 83143
MESSAGE_ID = "<attachment-83143@fixture.example>"

#: Default ordered attachment metadata (the three attachments of PRD §12.5 example A).
DEFAULT_ATTACHMENTS: list[dict[str, Any]] = [
    {
        "index": 1,
        "name": "factura.pdf",
        "size_bytes": 17,
        "native_order_key": "1",
        "unavailable_reason": None,
    },
    {
        "index": 2,
        "name": "Factura Octubre 2026.pdf",
        "size_bytes": 17,
        "native_order_key": "2",
        "unavailable_reason": None,
    },
    {
        "index": 3,
        "name": "recibo.pdf",
        "size_bytes": 17,
        "native_order_key": "3",
        "unavailable_reason": None,
    },
]

#: Default capability map: a local, read-only, body-local built-in driver.
CAPABILITIES: dict[str, Any] = {
    "network": False,
    "readonly": "structural",
    "body_local": True,
    "attachments": "local",
    "native_order": "numeric",
}

#: Bytes the double streams for each attachment by default (size does not matter).
DEFAULT_CHUNKS: dict[int, list[bytes]] = {
    1: [b"fake attachment 1"],
    2: [b"fake attachment 2"],
    3: [b"fake attachment 3"],
}


class FakeAttachmentBackend:
    """Duck-typed ``MailBackend`` covering the CLI ``show``/``attachment`` paths."""

    driver = DRIVER
    plugin_api = PLUGIN_API
    capabilities = dict(CAPABILITIES)
    native_order = "numeric"
    labels_available = True

    def __init__(
        self,
        *,
        driver: str | None = None,
        capabilities: Mapping[str, Any] | None = None,
        native_uid: int | str = NATIVE_UID,
        account_uuid: str = ACCOUNT_UUID,
        account_label: str = ACCOUNT_LABEL,
        account_email: str | None = "attachment@fixture.example",
        mailbox_id: int = MAILBOX_ID,
        attachments: Sequence[Mapping[str, Any]] | None = None,
        missing: bool = False,
        attachments_error: BaseException | None = None,
        stream_errors: Mapping[int, BaseException] | None = None,
        stream_chunks: Mapping[int, Sequence[bytes]] | None = None,
        stream_delay: float = 0.0,
        body_readable: bool = True,
        body_warnings: Sequence[str] | None = None,
        body_attachments: Sequence[str] | None = None,
        stored_attachment_names: Sequence[str] | None = None,
        unreadable_attachment_names: Sequence[str] | None = None,
        unreadable_attachment_warning: str | None = None,
        body_text: str = "Fake body with attachments.",
        message_size: int = 1024,
    ) -> None:
        self.driver = str(driver or DRIVER)
        self._capabilities = dict(CAPABILITIES if capabilities is None else capabilities)
        self.native_order = str(self._capabilities.get("native_order", "numeric"))
        self.native_uid = native_uid
        self.account_uuid = account_uuid
        self.account_label = account_label
        self.account_email = account_email
        self.mailbox_id = mailbox_id
        self._attachments = [
            dict(entry)
            for entry in (
                DEFAULT_ATTACHMENTS if attachments is None else attachments
            )
        ]
        self.missing = bool(missing)
        self.attachments_error = attachments_error
        self.stream_errors = dict(stream_errors or {})
        self.stream_chunks = {
            int(index): list(chunks)
            for index, chunks in (stream_chunks or DEFAULT_CHUNKS).items()
        }
        self.stream_delay = float(stream_delay)
        self.body_readable = bool(body_readable)
        self.body_warnings = list(body_warnings or ())
        self.body_attachments = list(body_attachments or ())
        self.stored_attachment_names = list(stored_attachment_names or ())
        self.unreadable_attachment_names = list(unreadable_attachment_names or ())
        self.unreadable_attachment_warning = unreadable_attachment_warning
        self.body_text = body_text
        self.message_size = int(message_size)
        self.closed = False
        self.calls: list[str] = []
        self.stream_calls: list[int] = []
        self.opened_native_ids: list[Any] = []

    # -- metadata --------------------------------------------------------- #

    @property
    def capabilities(self) -> dict[str, Any]:  # type: ignore[override]
        return dict(self._capabilities)

    def describe(self) -> dict[str, Any]:
        return {}

    def parse_uid(self, raw: Any) -> Any:
        return self.parse_native_id(str(raw))

    def parse_native_id(self, native_id: str) -> Any:
        """Accept the native uid form of the double's driver (int or opaque text)."""
        if self._capabilities.get("native_order") == "numeric":
            text = str(native_id)
            if not text.lstrip("+").isdigit():
                raise MailqueryError(
                    "E_USAGE",
                    f"invalid uid part {text!r}: expected an integer",
                )
            return int(text)
        if not native_id:
            raise PluginError(Reason.INVALID_UID, "expected a non-empty native id")
        return native_id

    # -- accounts and mailboxes ------------------------------------------- #

    def accounts(self) -> list[dict[str, Any]]:
        self.calls.append("accounts")
        return [
            {
                "uuid": self.account_uuid,
                "label": self.account_label,
                "email": self.account_email,
                "local": True,
                "store_index": 0,
                "labelled": True,
            }
        ]

    def mailboxes(self) -> list[dict[str, Any]]:
        self.calls.append("mailboxes")
        return [self._mailbox()]

    def excluded_stores(self) -> list[dict[str, Any]]:
        self.calls.append("excluded_stores")
        return []

    def resolve_mailbox(self, account_uuid: str, ref: str) -> dict[str, Any] | None:
        self.calls.append("resolve_mailbox")
        mailbox = self._mailbox()
        if str(account_uuid) != self.account_uuid:
            return None
        needle = str(ref).strip().casefold()
        if needle in (
            str(mailbox["name"]).casefold(),
            str(mailbox["path"]).casefold(),
            str(mailbox["url"]).casefold(),
        ):
            return mailbox
        return None

    def _mailbox(self) -> dict[str, Any]:
        return {
            "id": self.mailbox_id,
            "account_uuid": self.account_uuid,
            "name": "INBOX",
            "path": "INBOX",
            "url": "imap://attachment-account/INBOX",
            "is_inbox": True,
            "is_aggregate": False,
            "total": 1,
            "unread": 0,
        }

    # -- message operations ------------------------------------------------ #

    def _row(self) -> dict[str, Any]:
        return {
            "uid": self.native_uid,
            "global_message_id": 1,
            "subject": "Fake attachments message",
            "sender_name": "Fake Sender",
            "sender_address": "sender@fixture.example",
            "date_sent": 1_700_000_000.0,
            "date_received": 1_700_000_000.0,
            "mailbox_id": self.mailbox_id,
            "read": 0,
            "flagged": 0,
            "size": self.message_size,
            "message_id": MESSAGE_ID,
            "has_attachments": bool(self._attachments),
            "native_order_key": str(self.native_uid),
        }

    def find_message(
        self, uid: Any
    ) -> tuple[dict[str, Any], dict[str, Any] | None] | None:
        self.calls.append("find_message")
        if self.missing or str(uid) != str(self.native_uid):
            return None
        return self._row(), self._mailbox()

    def load_body(self, row: dict[str, Any]) -> dict[str, Any]:
        self.calls.append("load_body")
        return {
            "available": True,
            "readable": self.body_readable,
            "partial": False,
            "headers": {"Subject": row.get("subject", "")},
            "body_text": self.body_text if self.body_readable else "",
            "attachments": (
                (
                    [{"name": name} for name in self.body_attachments]
                    if self.body_attachments
                    else [{"name": str(entry["name"])} for entry in self._attachments]
                )
                if self.body_readable
                else []
            ),
            "source": {"emlx_path": None, "partial": False},
            "warnings": list(self.body_warnings),
        }

    def recipients(self, uids: Sequence[Any]) -> dict[Any, Any]:
        self.calls.append("recipients")
        return {
            str(uid): {"to": [{"name": "Fake User", "address": "me@fixture.example"}], "cc": []}
            for uid in uids
        }

    def attachment_names(self, uid: Any) -> list[str]:
        self.calls.append("attachment_names")
        if self.stored_attachment_names:
            return list(self.stored_attachment_names)
        return [str(entry["name"]) for entry in self._attachments]

    def unreadable_attachments(
        self, row: dict[str, Any]
    ) -> tuple[list[str], str | None]:
        self.calls.append("unreadable_attachments")
        return list(self.unreadable_attachment_names), self.unreadable_attachment_warning

    def query(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        """Listing operation of the protocol (not exercised by the attachment tests)."""
        self.calls.append("query")
        return []

    # -- attachment operations -------------------------------------------- #

    def attachments(self, uid: Any) -> list[dict[str, Any]]:
        self.calls.append("attachments")
        self.opened_native_ids.append(uid)
        if self.attachments_error is not None:
            raise self.attachments_error
        return [dict(entry) for entry in self._attachments]

    def attachment_stream(self, uid: Any, index: int) -> Iterator[bytes]:
        self.calls.append("attachment_stream")
        self.stream_calls.append(int(index))
        error = self.stream_errors.get(int(index))
        if error is not None:
            raise error
        chunks = self.stream_chunks.get(int(index), [b"fake attachment %d" % index])

        def generate() -> Iterator[bytes]:
            if self.stream_delay:
                time.sleep(self.stream_delay)
            for chunk in chunks:
                yield chunk

        return generate()

    def close(self) -> None:
        self.closed = True

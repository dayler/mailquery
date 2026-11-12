"""Installable-looking plugin double for the API 1 contract.

The double represents an external backend whose author only imports the public
package :mod:`mailquery.plugins` (PRD §9.2): it must not import
``mailquery.backends`` nor the store. Tests inject its metadata through
:class:`FakeEntryPoint` so the registry and ``--version`` can be exercised
without ``pip install`` (CI never installs the package).

The double also provides the data operations the multi-driver engine needs
(``accounts``, ``mailboxes``, ``query``, ``find_message``, ``load_body`` and
``attachments``) and :func:`plugin_factory`, an entry-point target that
builds one instance per command so tests can hand it rows relative to the
fixture clock. It also supports configurable failures, per-operation delays
(hangs for the metadata deadline of every command) and invalid return values (the
plugin wrapper must turn them into ``E_PLUGIN_FAILED``). Pure Python: no pywin32, no
network, no filesystem writes.
"""

from __future__ import annotations

import time
from typing import Any, Iterator, Mapping, Sequence

from mailquery.plugins import PLUGIN_API, PluginContext, PluginError, Reason

#: Driver name of the double; a valid external ``[a-z0-9_]{1,64}`` name.
DRIVER = "graph"

#: Version the entry point metadata advertises for the double.
VERSION = "0.1.0"

#: Account and mailbox identifiers of the double (opaque and stable, RF-36).
ACCOUNT_UUID = "graph-account"
ACCOUNT_LABEL = "Graph (user@example.com)"
MAILBOX_ID = "graph-inbox"
MAILBOX_URL = "graph://graph-account/INBOX"

#: A valid capability map for a remote, read-only, network plugin (API 1).
CAPABILITIES: dict[str, Any] = {
    "network": True,
    "readonly": "promise",
    "body_local": False,
    "attachments": "remote",
    "native_order": "text",
}

#: Attachment metadata the double returns by default (RF-43/RF-47 contract).
DEFAULT_ATTACHMENTS: list[dict[str, Any]] = [
    {
        "index": 1,
        "name": "factura.pdf",
        "size_bytes": 12,
        "native_order_key": "B",
        "unavailable_reason": None,
    },
    {
        "index": 2,
        "name": "reporte.txt",
        "size_bytes": None,
        "native_order_key": "A",
        "unavailable_reason": "network",
    },
]

#: Default account rows of ``accounts`` (opaque label/uuid for a plugin).
DEFAULT_ACCOUNTS: list[dict[str, Any]] = [
    {
        "uuid": ACCOUNT_UUID,
        "label": ACCOUNT_LABEL,
        "email": None,
        "local": False,
    }
]

#: Default folder rows of ``mailboxes`` (one INBOX for the account).
DEFAULT_MAILBOXES: list[dict[str, Any]] = [
    {
        "id": MAILBOX_ID,
        "account_uuid": ACCOUNT_UUID,
        "name": "INBOX",
        "path": "INBOX",
        "url": MAILBOX_URL,
        "is_inbox": True,
        "is_aggregate": False,
        "total": 1,
        "unread": 1,
    }
]

#: Default rows of ``query``: a tiny common-model row with the protocol ordering key.
DEFAULT_ROWS: list[dict[str, Any]] = [
    {
        "uid": "B",
        "global_message_id": 1,
        "subject": "Plugin message",
        "sender_name": "Plugin",
        "sender_address": "plugin@example.com",
        "date_sent": 1_700_000_000.0,
        "date_received": 1_700_000_000.0,
        "mailbox_id": MAILBOX_ID,
        "read": 0,
        "flagged": 0,
        "size": 10,
        "message_id": "<plugin@example.com>",
        "has_attachments": True,
        "native_order_key": "B",
    }
]


class FakePluginBackend:
    """Duck-typed backend implementing API 1 with only the public contract package."""

    driver = DRIVER
    plugin_api = PLUGIN_API
    capabilities = dict(CAPABILITIES)
    native_order = "text"
    labels_available = True

    def __init__(
        self,
        context: PluginContext | None = None,
        *,
        rows: Sequence[dict[str, Any]] | None = None,
        accounts: Sequence[dict[str, Any]] | None = None,
        mailboxes: Sequence[dict[str, Any]] | None = None,
        attachments: Sequence[dict[str, Any]] | None = None,
        capabilities: Mapping[str, Any] | None = None,
        failures: dict[str, BaseException] | None = None,
        delays: Mapping[str, float] | None = None,
        results: Mapping[str, Any] | None = None,
        stream_chunks: Sequence[bytes] | None = None,
    ) -> None:
        self.context = context
        self.rows = [dict(row) for row in (DEFAULT_ROWS if rows is None else rows)]
        self._accounts = [
            dict(entry) for entry in (DEFAULT_ACCOUNTS if accounts is None else accounts)
        ]
        self._mailboxes = [
            dict(entry) for entry in (DEFAULT_MAILBOXES if mailboxes is None else mailboxes)
        ]
        self._attachments = [
            dict(entry) for entry in (DEFAULT_ATTACHMENTS if attachments is None else attachments)
        ]
        self.capabilities = dict(self.capabilities if capabilities is None else capabilities)
        self.native_order = str(self.capabilities.get("native_order", "text"))
        self.failures = dict(failures or {})
        #: Per-operation delay in seconds (timeout tests; the call blocks).
        self.delays = dict(delays or {})
        #: Per-operation return value override (invalid-return tests).
        self.results = dict(results or {})
        self.stream_chunks = list(stream_chunks or [b"plugin-bytes"])
        self.closed = False
        self.calls: list[str] = []
        #: Keyword arguments of every ``query`` call (cursor/merge tests).
        self.queries: list[dict[str, Any]] = []

    # -- contract metadata -------------------------------------------------- #

    @staticmethod
    def parse_uid(raw: Any) -> str:
        """Native id of a plugin message: an opaque string (RF-40)."""
        text = raw if isinstance(raw, str) else str(raw)
        if not text:
            raise PluginError(Reason.INVALID_UID, "empty uid")
        return text

    @staticmethod
    def parse_native_id(native_id: str) -> str:
        """Validate the native part of a prefixed uid (RF-40); opaque non-empty text."""
        if not isinstance(native_id, str) or not native_id:
            raise PluginError(Reason.INVALID_UID, "expected a non-empty native id")
        return native_id

    def describe(self) -> dict[str, Any]:
        return {"backend": self.driver, "version": VERSION, "strategy": "plugin", "schema_ok": True}

    # -- the operations of protocol v1 -------------------------------------- #

    def accounts(self) -> list[dict[str, Any]]:
        self.calls.append("accounts")
        return self._fail("accounts", [dict(entry) for entry in self._accounts])

    def mailboxes(self) -> Sequence[dict[str, Any]]:
        self.calls.append("mailboxes")
        return self._fail("mailboxes", [dict(entry) for entry in self._mailboxes])

    def excluded_stores(self) -> list[dict[str, Any]]:
        self.calls.append("excluded_stores")
        return self._fail("excluded_stores", [])

    def resolve_mailbox(self, account_uuid: str, ref: str) -> dict[str, Any] | None:
        self.calls.append("resolve_mailbox")
        needle = str(ref).strip().casefold()
        for entry in self._mailboxes:
            if str(entry["account_uuid"]) != str(account_uuid):
                continue
            if needle in (
                str(entry["name"]).casefold(),
                str(entry["path"]).casefold(),
                str(entry["url"]).casefold(),
            ):
                self._fail("resolve_mailbox", None)
                return dict(entry)
        return self._fail("resolve_mailbox", None)

    def query(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append("query")
        self.queries.append({"args": args, "kwargs": dict(kwargs)})
        rows = [dict(row) for row in self.rows]
        mailbox_ids = args[0] if args else kwargs.get("mailbox_ids")
        if mailbox_ids is not None:
            allowed = set(mailbox_ids)
            rows = [row for row in rows if row.get("mailbox_id") in allowed]
        since = kwargs.get("since")
        if since is not None:
            rows = [row for row in rows if float(row.get("date_received") or 0) >= float(since)]
        until = kwargs.get("until")
        if until is not None:
            rows = [row for row in rows if float(row.get("date_received") or 0) < float(until)]
        if kwargs.get("unread"):
            rows = [row for row in rows if not row.get("read")]
        if kwargs.get("flagged"):
            rows = [row for row in rows if row.get("flagged")]
        if kwargs.get("has_attachments"):
            rows = [row for row in rows if row.get("has_attachments")]
        order = str(kwargs.get("order", "desc"))
        rows.sort(
            key=lambda row: (
                float(row.get("date_received") or 0),
                str(row.get("native_order_key") or ""),
            ),
            reverse=order == "desc",
        )
        return self._fail("query", rows)

    def membership(self, uids: Sequence[str]) -> dict[str, set[Any]]:
        self.calls.append("membership")
        return self._fail("membership", {str(uid): set() for uid in uids})

    def duplicate_counts(self, mailbox_ids: Sequence[Any]) -> dict[Any, int]:
        self.calls.append("duplicate_counts")
        return self._fail("duplicate_counts", {})

    def recipients(self, uids: Sequence[str]) -> dict[str, Any]:
        self.calls.append("recipients")
        return self._fail(
            "recipients",
            {
                str(uid): {
                    "to": [{"name": "Plugin User", "address": "user@example.com"}],
                    "cc": [],
                }
                for uid in uids
            },
        )

    def attachment_names(self, uid: str) -> list[str]:
        self.calls.append("attachment_names")
        return self._fail("attachment_names", [entry["name"] for entry in self._attachments])

    def find_message(self, uid: str) -> tuple[dict[str, Any], dict[str, Any] | None] | None:
        self.calls.append("find_message")
        self._fail("find_message", None)
        for row in self.rows:
            if str(row.get("uid")) != str(uid):
                continue
            mailbox = self._mailbox_of(row)
            return dict(row), mailbox
        return None

    def load_body(self, row: dict[str, Any]) -> dict[str, Any]:
        """Body of the double: readable text unless the row marks it unavailable.

        Row keys (multi-driver tests only): ``body_text``, ``readable``, ``available``,
        ``partial``, ``headers`` and ``warnings``.
        """
        self.calls.append("load_body")
        readable = bool(row.get("readable", True))
        partial = bool(row.get("partial", False))
        available = bool(row.get("available", readable))
        return self._fail(
            "load_body",
            {
                "available": available,
                "readable": readable,
                "partial": partial,
                "headers": dict(row.get("headers") or {}),
                "body_text": str(row.get("body_text", "Plugin body")) if readable else "",
                "attachments": [],
                "source": {"emlx_path": None, "partial": partial},
                "warnings": list(row.get("warnings") or ()),
            },
        )

    def attachments(self, uid: str) -> list[dict[str, Any]]:
        """Ordered attachment metadata: index, name, size and reason."""
        self.calls.append("attachments")
        return self._fail("attachments", [dict(entry) for entry in self._attachments])

    def attachment_stream(self, uid: str, index: int) -> Iterator[bytes]:
        """Decoded bytes of one attachment (never written by the plugin)."""
        self.calls.append("attachment_stream")
        self._fail("attachment_stream", None)
        return iter(self.stream_chunks)

    def doctor_checks(self) -> list[dict[str, Any]]:
        self.calls.append("doctor_checks")
        return self._fail("doctor_checks", [])

    def close(self) -> None:
        self.closed = True

    # -- internals ---------------------------------------------------------- #

    def _mailbox_of(self, row: dict[str, Any]) -> dict[str, Any] | None:
        mailbox_id = row.get("mailbox_id")
        for entry in self._mailboxes:
            if entry["id"] == mailbox_id:
                return dict(entry)
        return dict(self._mailboxes[0]) if self._mailboxes else None

    def _fail(self, operation: str, value: Any) -> Any:
        delay = self.delays.get(operation)
        if delay:
            time.sleep(float(delay))
        failure = self.failures.get(operation)
        if failure is not None:
            raise failure
        if operation in self.results:
            return self.results[operation]
        return value


def plugin_class(**attributes: Any) -> type[FakePluginBackend]:
    """Subclass of the double with metadata overridden (valid or deliberately invalid)."""
    attributes.setdefault("__module__", __name__)
    return type("ConfiguredPlugin", (FakePluginBackend,), attributes)


def plugin_factory(**instance_kwargs: Any) -> Any:
    """Entry-point target that builds a fresh double per command (multi-driver goldens).

    The returned callable carries the plugin metadata the registry validates
    (``driver``/``plugin_api``/``capabilities``) and receives the
    :class:`PluginContext` the core passes to every plugin instance. It lets a
    test configure the double's rows/mailboxes without ``pip install``.
    """
    declared_capabilities = instance_kwargs.pop("capabilities", None)
    capabilities = dict(CAPABILITIES if declared_capabilities is None else declared_capabilities)

    def factory(context: PluginContext | None = None) -> FakePluginBackend:
        return FakePluginBackend(context, capabilities=capabilities, **instance_kwargs)

    factory.driver = DRIVER  # type: ignore[attr-defined]
    factory.plugin_api = PLUGIN_API  # type: ignore[attr-defined]
    factory.capabilities = capabilities  # type: ignore[attr-defined]
    factory.native_order = capabilities["native_order"]  # type: ignore[attr-defined]
    return factory


class FakeEntryPoint:
    """``importlib.metadata.EntryPoint`` look-alike with injectable metadata.

    ``load()`` returns the injected plugin object (or raises ``import_error``) and
    counts calls, so the tests can prove that listing and ``--version`` never
    import a plugin module. ``version`` stands in for the distribution version.
    """

    group = "mailquery.backends"

    def __init__(
        self,
        name: str,
        value: str | None = None,
        *,
        plugin: Any = None,
        version: str = VERSION,
        import_error: BaseException | None = None,
    ) -> None:
        self.name = name
        self.value = value if value is not None else f"{__name__}:{FakePluginBackend.__name__}"
        self.plugin = plugin
        self.version = version
        self.import_error = import_error
        self.load_calls = 0

    def load(self) -> Any:
        self.load_calls += 1
        if self.import_error is not None:
            raise self.import_error
        if self.plugin is not None:
            return self.plugin
        module_name, _, attribute = self.value.partition(":")
        module = __import__(module_name, fromlist=["_"])
        target: Any = module
        for part in attribute.split("."):
            target = getattr(target, part)
        return target

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"FakeEntryPoint({self.name!r}, {self.value!r})"


#: Canonical entry point values of the built-in backends (what pyproject declares).
INTERNAL_TARGETS = {
    "apple_mail": "mailquery.backends.apple_mail:AppleMailBackend",
    "outlook": "mailquery.backends.outlook:OutlookBackend",
}


def internal_entry_points() -> list[FakeEntryPoint]:
    """Entry points ``importlib.metadata`` would return for an installed mailquery."""
    return [
        FakeEntryPoint(name, target, version=VERSION)
        for name, target in INTERNAL_TARGETS.items()
    ]


__all__ = [
    "ACCOUNT_LABEL",
    "ACCOUNT_UUID",
    "CAPABILITIES",
    "DEFAULT_ACCOUNTS",
    "DEFAULT_ATTACHMENTS",
    "DEFAULT_MAILBOXES",
    "DEFAULT_ROWS",
    "DRIVER",
    "FakeEntryPoint",
    "FakePluginBackend",
    "INTERNAL_TARGETS",
    "MAILBOX_ID",
    "PLUGIN_API",
    "PluginContext",
    "PluginError",
    "Reason",
    "VERSION",
    "internal_entry_points",
    "plugin_class",
    "plugin_factory",
]

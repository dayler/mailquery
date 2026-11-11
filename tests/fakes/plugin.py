"""Installable-looking plugin double for the API 1 contract (M01; extended by M05).

The double represents an external backend whose author only imports the public
package :mod:`mailquery.plugins` (PRD-v2.1 §9.3, plan §7.4): it must not import
``mailquery.backends`` nor the store. Tests inject its metadata through
:class:`FakeEntryPoint` so the registry and ``--version`` can be exercised
without ``pip install`` (CI never installs the package; plan §7.5).

Pure Python: no pywin32, no network, no filesystem writes.
"""

from __future__ import annotations

from typing import Any, Iterator, Sequence

from mailquery.plugins import PLUGIN_API, PluginContext, PluginError, Reason

#: Driver name of the double; a valid external ``[a-z0-9_]{1,64}`` name.
DRIVER = "graph"

#: Version the entry point metadata advertises for the double.
VERSION = "0.1.0"

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

#: Default rows of ``query``: a tiny common-model row with the C1 ordering key.
DEFAULT_ROWS: list[dict[str, Any]] = [
    {
        "uid": "B",
        "global_message_id": 1,
        "subject": "Plugin message",
        "sender_name": "Plugin",
        "sender_address": "plugin@example.com",
        "date_sent": 1_700_000_000.0,
        "date_received": 1_700_000_000.0,
        "mailbox_id": "folder-1",
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
        attachments: Sequence[dict[str, Any]] | None = None,
        failures: dict[str, BaseException] | None = None,
        stream_chunks: Sequence[bytes] | None = None,
    ) -> None:
        self.context = context
        self.rows = [dict(row) for row in (DEFAULT_ROWS if rows is None else rows)]
        self._attachments = [
            dict(entry) for entry in (DEFAULT_ATTACHMENTS if attachments is None else attachments)
        ]
        self.failures = dict(failures or {})
        self.stream_chunks = list(stream_chunks or [b"plugin-bytes"])
        self.closed = False
        self.calls: list[str] = []

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

    # -- the operations of protocol v1 (M01 freezes the names) -------------- #

    def accounts(self) -> list[dict[str, Any]]:
        self.calls.append("accounts")
        return self._fail("accounts", [])

    def mailboxes(self) -> Sequence[dict[str, Any]]:
        self.calls.append("mailboxes")
        return self._fail("mailboxes", [])

    def excluded_stores(self) -> list[dict[str, Any]]:
        self.calls.append("excluded_stores")
        return self._fail("excluded_stores", [])

    def resolve_mailbox(self, account_uuid: str, ref: str) -> dict[str, Any] | None:
        self.calls.append("resolve_mailbox")
        return self._fail("resolve_mailbox", None)

    def query(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append("query")
        return self._fail("query", [dict(row) for row in self.rows])

    def membership(self, uids: Sequence[str]) -> dict[str, set[Any]]:
        self.calls.append("membership")
        return self._fail("membership", {str(uid): set() for uid in uids})

    def duplicate_counts(self, mailbox_ids: Sequence[Any]) -> dict[Any, int]:
        self.calls.append("duplicate_counts")
        return self._fail("duplicate_counts", {})

    def recipients(self, uids: Sequence[str]) -> dict[str, Any]:
        self.calls.append("recipients")
        return self._fail("recipients", {})

    def attachment_names(self, uid: str) -> list[str]:
        self.calls.append("attachment_names")
        return self._fail("attachment_names", [entry["name"] for entry in self._attachments])

    def find_message(self, uid: str) -> tuple[dict[str, Any], dict[str, Any] | None] | None:
        self.calls.append("find_message")
        return self._fail("find_message", None)

    def load_body(self, row: dict[str, Any]) -> dict[str, Any]:
        self.calls.append("load_body")
        return self._fail(
            "load_body",
            {
                "available": False,
                "readable": False,
                "partial": False,
                "headers": {},
                "body_text": "",
                "attachments": [],
                "source": {"emlx_path": None, "partial": False},
                "warnings": [],
            },
        )

    def attachments(self, uid: str) -> list[dict[str, Any]]:
        """Ordered attachment metadata (M06–M10 consume it): index, name, size and reason."""
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

    def _fail(self, operation: str, value: Any) -> Any:
        failure = self.failures.get(operation)
        if failure is not None:
            raise failure
        return value


def plugin_class(**attributes: Any) -> type[FakePluginBackend]:
    """Subclass of the double with metadata overridden (valid or deliberately invalid)."""
    attributes.setdefault("__module__", __name__)
    return type("ConfiguredPlugin", (FakePluginBackend,), attributes)


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
    "CAPABILITIES",
    "DEFAULT_ATTACHMENTS",
    "DEFAULT_ROWS",
    "DRIVER",
    "FakeEntryPoint",
    "FakePluginBackend",
    "INTERNAL_TARGETS",
    "PluginContext",
    "PluginError",
    "Reason",
    "VERSION",
    "internal_entry_points",
    "plugin_class",
]

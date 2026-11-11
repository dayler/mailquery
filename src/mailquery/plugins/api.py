"""Public plugin API 1 (PRD-v2.1 §6.1 RF-38, §9.3; plan §5.1 C1).

This module is the frozen core surface an external backend plugin needs: the
``PLUGIN_API`` version, the closed ``Reason`` enum, :class:`PluginError` (the
plugin brings ``reason``/``hint``/``detail``/``log_message``; the core owns
``code``/``exit``), :class:`PluginContext` (``home`` and ``tmp_dir``) and the
capability/driver-metadata types the registry validates.

M05 adds the **core-side** error protocol (PRD-v2.1 §11.7, RF-50) that every
driver call goes through: :func:`call_driver` (single wrapper: deadline,
``reason``→``code``/``exit`` mapping, sanitization, invalid-return detection)
and :func:`wrap_driver` (the transparent proxy the query engine uses). The
``code``/``exit`` always belong to the closed core set; a plugin only supplies
a closed ``reason`` plus sanitized ``hint``/``detail``/``log_message``. An
unmapped plugin failure is ``E_PLUGIN_FAILED`` (exit 3), never ``E_INTERNAL``;
a core failure stays ``E_INTERNAL`` (exit 1). Timeouts are tested with an
injectable deadline (``METADATA_TIMEOUT_SECONDS``): external plugins run in a
daemon worker thread, the built-in drivers run inline (their SQLite/COM objects
are thread-affine) and their elapsed time is checked on return; Outlook keeps
its COM watchdog (RNF-16, plan D3).

An external plugin must import only this package from mailquery. It must not
import the backends, the store or any other internal module (PRD-v2.1 §9.3,
RNF-12). The backend protocol itself (operations and exact signatures) is
documented in ``docs/INTERFACES.md`` and implemented by ``MailBackend``.
"""

from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Final, Literal, NotRequired, TypedDict, TypeVar

from mailquery import output
from mailquery.errors import MailqueryError

#: Version of the plugin contract; closed for the 3.x line (ADR-27).
PLUGIN_API: Final[int] = 1

#: ``importlib.metadata`` entry point group every backend registers in (RF-35).
ENTRY_POINT_GROUP: Final[str] = "mailquery.backends"

#: Driver names are file-system and log safe: ``<driver>.toml``, ``logs/<driver>.log``.
DRIVER_NAME_PATTERN: Final[re.Pattern[str]] = re.compile(r"[a-z0-9_]{1,64}")
DRIVER_NAME_MAX_LENGTH: Final[int] = 64

#: Built-in driver names; an external plugin may not reuse them (RF-35).
RESERVED_DRIVER_NAMES: Final[frozenset[str]] = frozenset({"apple_mail", "outlook"})

#: Capability keys every plugin must declare (RF-38); closed set.
CAPABILITY_KEYS: Final[tuple[str, ...]] = (
    "network",
    "readonly",
    "body_local",
    "attachments",
    "native_order",
)

READONLY_MODES: Final[frozenset[str]] = frozenset({"structural", "promise"})
ATTACHMENTS_MODES: Final[frozenset[str]] = frozenset({"local", "remote", "none"})
NATIVE_ORDERS: Final[frozenset[str]] = frozenset({"numeric", "text"})

#: Metadata deadline per driver operation (RNF-16). Read on every call so a test
#: can inject a short deadline with ``mock.patch`` and never wait 30 s.
METADATA_TIMEOUT_SECONDS: Final[float] = 30.0

#: Extraction deadline per attachment (RNF-16, implemented by M08).
EXTRACTION_TIMEOUT_SECONDS: Final[float] = 120.0

#: UTF-8 byte limits of the plugin-owned error fields (§11.7, T02).
HINT_MAX_BYTES: Final[int] = 300
DETAIL_MAX_BYTES: Final[int] = 200
LOG_MESSAGE_MAX_BYTES: Final[int] = 200

#: Every driver operation that crosses the core/plugin boundary (protocol v1).
METADATA_OPERATIONS: Final[frozenset[str]] = frozenset(
    {
        "accounts",
        "mailboxes",
        "mailboxes_without_counters",
        "excluded_stores",
        "resolve_mailbox",
        "query",
        "membership",
        "duplicate_counts",
        "recipients",
        "attachment_names",
        "find_message",
        "load_body",
        "load_snippet",
        "parse_uid",
        "parse_native_id",
        "attachments",
        "attachment_stream",
        "unreadable_attachments",
    }
)

#: Operations whose ``reason`` uses the attachment context of §11.7.
ATTACHMENT_OPERATIONS: Final[frozenset[str]] = frozenset(
    {"attachment_names", "attachments", "attachment_stream", "unreadable_attachments"}
)

ReadOnlyMode = Literal["structural", "promise"]
AttachmentsMode = Literal["local", "remote", "none"]
NativeOrder = Literal["numeric", "text"]


class Reason(str, Enum):
    """Closed ``reason`` enum of the plugin error protocol (PRD-v2.1 §11.7)."""

    INVALID_UID = "invalid_uid"
    NOT_FOUND = "not_found"
    NOT_LOCAL = "not_local"
    NOT_DOWNLOADED = "not_downloaded"
    UNSUPPORTED = "unsupported"
    CORRUPT = "corrupt"
    SMIME = "smime"
    UNREADABLE = "unreadable"
    NETWORK = "network"
    PERMISSION = "permission"
    AUTH = "auth"
    BUSY = "busy"
    TIMEOUT = "timeout"


class Capabilities(TypedDict):
    """Capability map every driver declares (RF-38, AC-02)."""

    network: bool
    readonly: ReadOnlyMode
    body_local: bool
    attachments: AttachmentsMode
    native_order: NativeOrder


class DriverMetadata(TypedDict):
    """Metadata of one installed driver, resolved without opening the mail client.

    ``internal`` is added by the registry: built-in drivers (``apple_mail``,
    ``outlook``) are filtered by platform for ``--version`` (DP-02); external
    plugins are always listed.
    """

    driver: str
    plugin_api: int
    version: str
    capabilities: Capabilities
    internal: NotRequired[bool]


@dataclass(frozen=True, slots=True)
class PluginContext:
    """Paths the core hands to a plugin; the plugin owns its files (RF-39)."""

    home: Path
    tmp_dir: Path


class PluginError(Exception):
    """Failure raised by a plugin: ``reason`` is closed, ``code``/``exit`` are the core's.

    ``hint`` (English, ≤ 300 bytes), ``detail`` (≤ 200 bytes) and ``log_message``
    (≤ 200 bytes) must not contain PII, uids, paths or accounts; the core
    sanitizes them and never lets the plugin choose the error ``code``/``exit``
    (PRD-v2.1 §11.7, RF-50).
    """

    def __init__(
        self,
        reason: Reason | str,
        hint: str = "",
        detail: str = "",
        log_message: str = "",
    ) -> None:
        self.reason: Reason | str = _normalize_reason(reason)
        self.hint = hint
        self.detail = detail
        self.log_message = log_message
        text = detail or hint or _reason_value(self.reason)
        super().__init__(text)

    def __str__(self) -> str:  # pragma: no cover - trivial formatting
        return _reason_value(self.reason)


def _normalize_reason(reason: Reason | str) -> Reason | str:
    """Enum member when possible; an unknown value is kept for the core to map to a failure."""
    if isinstance(reason, Reason):
        return reason
    try:
        return Reason(reason)
    except ValueError:
        return reason


def _reason_value(reason: Reason | str) -> str:
    return reason.value if isinstance(reason, Reason) else str(reason)


# --------------------------------------------------------------------------- #
# Core-owned error protocol (M05, PRD-v2.1 §11.7, RF-50, RNF-15/RNF-16)
# --------------------------------------------------------------------------- #

#: Closed ``reason`` -> core ``code`` map for attachment operations (§11.7).
_ATTACHMENT_REASON_CODES: Final[dict[str, str]] = {
    "invalid_uid": "E_USAGE",
    "not_found": "E_USAGE",
    "not_local": "E_ATTACHMENT_UNAVAILABLE",
    "not_downloaded": "E_ATTACHMENT_UNAVAILABLE",
    "unsupported": "E_ATTACHMENT_UNAVAILABLE",
    "network": "E_ATTACHMENT_UNAVAILABLE",
    "corrupt": "E_ATTACHMENT_UNREADABLE",
    "smime": "E_ATTACHMENT_UNREADABLE",
    "unreadable": "E_ATTACHMENT_UNREADABLE",
    "permission": "E_PERMISSION",
    "auth": "E_PERMISSION",
    "busy": "E_CLIENT_BUSY",
    "timeout": "E_CLIENT_TIMEOUT",
}

#: Closed ``reason`` -> core ``code`` map for every other operation (§11.7).
_METADATA_REASON_CODES: Final[dict[str, str]] = {
    **_ATTACHMENT_REASON_CODES,
    "not_local": "E_PLUGIN_FAILED",
    "not_downloaded": "E_PLUGIN_FAILED",
    "unsupported": "E_PLUGIN_FAILED",
    "network": "E_PLUGIN_FAILED",
    "corrupt": "E_PLUGIN_FAILED",
    "smime": "E_PLUGIN_FAILED",
    "unreadable": "E_PLUGIN_FAILED",
}

#: Core-owned English message templates per reason (§11.7). The plugin never words it.
#: ``invalid_uid``/``not_found`` have no motive template in §11.7; the core words
#: their ``E_USAGE`` message itself.
_MESSAGE_TEMPLATES: Final[dict[str, str]] = {
    "invalid_uid": "invalid message id",
    "not_found": "message was not found",
    "not_local": "not available in the local store",
    "not_downloaded": "could not be retrieved from its origin",
    "network": "could not be retrieved from its origin",
    "unsupported": "cannot be recovered by driver '<driver>'",
    "corrupt": "is corrupt or unreadable",
    "unreadable": "is corrupt or unreadable",
    "smime": "is S/MIME protected and cannot be extracted",
    "permission": "cannot be read: permission denied",
    "auth": "cannot be read: permission denied",
    "busy": "is temporarily unavailable",
    "timeout": "did not respond within the timeout",
}

#: Default hint of an attachment motive when the plugin brings none (§11.7).
_REASON_HINTS: Final[dict[str, str]] = {
    "not_local": (
        "open the message in the mail client so it downloads the attachment, then retry"
    ),
    "not_downloaded": (
        "open the message in the mail client so it downloads the attachment, then retry"
    ),
    "network": "check the network connection and the plugin configuration, then retry",
    "unsupported": "install or declare a driver that can recover this attachment",
    "smime": "S/MIME attachments cannot be extracted",
    "corrupt": "the attachment is corrupt and cannot be recovered",
    "unreadable": "the attachment cannot be read; open it in the mail client",
}

#: Default actionable hint per core code (English; §11.7 hint column).
_CODE_HINTS: Final[dict[str, str]] = {
    "E_PLUGIN_FAILED": 'run "mailquery doctor" and check the driver entry for details',
    "E_CLIENT_TIMEOUT": (
        'run "mailquery doctor" and check the driver; do not retry in a loop'
    ),
    "E_CLIENT_BUSY": "retry once",
    "E_PERMISSION": "grant the required permissions or review the plugin configuration",
    "E_USAGE": "check the message id and retry",
    "E_ATTACHMENT_UNAVAILABLE": (
        "check the attachment and the driver configuration, then retry"
    ),
    "E_ATTACHMENT_UNREADABLE": "inspect the attachment in the mail client",
}

#: Control characters (C0/C1), format characters and bidi overrides never reach an error.
_STRIP_CONTROLS: Final[re.Pattern[str]] = re.compile(
    "[\x00-\x1f\x7f-\x9f\u00ad\u061c\u200b-\u200f\u202a-\u202e\u2066-\u2069]"
)

_T = TypeVar("_T")


class _DeadlineExceeded(Exception):
    """Internal marker: the daemon worker did not finish before the deadline."""


def sanitize_error_field(value: Any, max_bytes: int) -> str:
    """Sanitize one plugin-owned error field (PRD-v2.1 §11.7, T02).

    Removes ANSI escapes, C0/C1 controls (newlines and tabs included), format
    characters and bidi overrides, then truncates to ``max_bytes`` UTF-8 bytes
    without splitting a character. Non-string values become ``""`` (the core
    never crashes on an invalid field).
    """
    if not isinstance(value, str) or not value:
        return ""
    try:
        cleaned = output.sanitize_text(value)
    except Exception:  # noqa: BLE001 - a broken plugin string must not crash the core
        return ""
    cleaned = _STRIP_CONTROLS.sub("", cleaned)
    # Scrub lone surrogates: they cannot be encoded (a plugin can hand any str).
    cleaned = cleaned.encode("utf-8", "replace").decode("utf-8")
    encoded = cleaned.encode("utf-8")
    if max_bytes <= 0:
        return ""
    if len(encoded) <= max_bytes:
        return cleaned
    return encoded[:max_bytes].decode("utf-8", "ignore")


def _reason_text(reason: Any) -> str | None:
    """The closed ``reason`` value, or ``None`` when the plugin sent something invalid."""
    if isinstance(reason, Reason):
        return reason.value
    if isinstance(reason, str):
        return reason
    return None


def _code_for_reason(reason: str | None, *, attachments: bool) -> str:
    if reason is None:
        return "E_PLUGIN_FAILED"
    table = _ATTACHMENT_REASON_CODES if attachments else _METADATA_REASON_CODES
    return table.get(reason, "E_PLUGIN_FAILED")


def _message_template(reason: str | None, driver: str) -> str | None:
    if reason is None:
        return None
    template = _MESSAGE_TEMPLATES.get(reason)
    return None if template is None else template.replace("<driver>", driver)


def _default_hint(reason: str | None, code: str, *, attachments: bool) -> str:
    if attachments and reason in _REASON_HINTS:
        return _REASON_HINTS[reason]
    return _CODE_HINTS.get(code, _CODE_HINTS["E_PLUGIN_FAILED"])


def _plugin_failed(
    driver: str,
    *,
    detail: str = "",
    hint: str = "",
    log_message: str = "",
) -> MailqueryError:
    """``E_PLUGIN_FAILED`` for an unmapped failure; the core never trusts plugin text."""
    message = f"driver '{driver}' failed"
    if detail:
        message = f"{message}: {detail}"
    return MailqueryError(
        "E_PLUGIN_FAILED",
        message,
        hint or _CODE_HINTS["E_PLUGIN_FAILED"],
        log_message or f"driver '{driver}' failed",
    )


def _invalid_result(driver: str, operation: str) -> MailqueryError:
    """The plugin returned a value outside the protocol: ``E_PLUGIN_FAILED``."""
    return MailqueryError(
        "E_PLUGIN_FAILED",
        f"driver '{driver}' returned an invalid result for {operation}",
        _CODE_HINTS["E_PLUGIN_FAILED"],
        f"driver '{driver}' returned an invalid {operation} result",
    )


def _timeout_error(driver: str) -> MailqueryError:
    """The driver exceeded the metadata deadline: ``E_CLIENT_TIMEOUT`` (exit 3)."""
    message = _MESSAGE_TEMPLATES["timeout"]
    return MailqueryError(
        "E_CLIENT_TIMEOUT",
        message,
        _CODE_HINTS["E_CLIENT_TIMEOUT"],
        f"driver '{driver}' did not respond within the timeout",
    )


def map_plugin_error(
    exc: PluginError, *, driver: str, attachments: bool
) -> MailqueryError:
    """Translate a plugin :class:`PluginError` to a core-owned error (§11.7).

    The core owns ``code``/``exit`` and the message template; the plugin only
    contributes its closed ``reason`` plus the sanitized ``hint``/``detail``/
    ``log_message``. An unknown/invalid reason is ``E_PLUGIN_FAILED``; the
    error object never carries the plugin ``code``/``exit`` (UT-ERR-01).
    """
    reason = _reason_text(getattr(exc, "reason", None))
    detail = sanitize_error_field(getattr(exc, "detail", ""), DETAIL_MAX_BYTES)
    plugin_hint = sanitize_error_field(getattr(exc, "hint", ""), HINT_MAX_BYTES)
    plugin_log = sanitize_error_field(
        getattr(exc, "log_message", ""), LOG_MESSAGE_MAX_BYTES
    )
    code = _code_for_reason(reason, attachments=attachments)
    template = _message_template(reason, driver)
    if template is None:
        return _plugin_failed(
            driver, detail=detail, hint=plugin_hint, log_message=plugin_log
        )
    message = f"{template}: {detail}" if detail else template
    return MailqueryError(
        code,
        message,
        plugin_hint or _default_hint(reason, code, attachments=attachments),
        # Never log hint/detail: the plugin's sanitized log_message or the template.
        plugin_log or template,
    )


def _run_with_deadline(call: Callable[[], _T], deadline: float) -> _T:
    """Run ``call`` in a daemon thread and wait at most ``deadline`` seconds.

    A plugin thread that does not answer cannot be killed (PRD-v2.1 §15 lists it
    as an accepted risk): it is a daemon, so the process exits anyway, and the
    command fails without partial results. The worker re-raises the plugin's own
    exception in the caller thread.
    """
    outcome: dict[str, Any] = {}
    done = threading.Event()

    def target() -> None:
        try:
            outcome["value"] = call()
        except BaseException as exc:  # noqa: BLE001 - re-raised in the caller thread
            outcome["error"] = exc
            outcome["traceback"] = exc.__traceback__
        finally:
            done.set()

    worker = threading.Thread(
        target=target, name="mailquery-driver-call", daemon=True
    )
    worker.start()
    if not done.wait(max(0.0, float(deadline))):
        raise _DeadlineExceeded
    if "error" in outcome:
        error = outcome["error"]
        raise error.with_traceback(outcome.get("traceback"))
    return outcome["value"]


def _check_elapsed(driver: str, started: float, deadline: float) -> None:
    """Native drivers run inline: report the timeout after the call returns.

    The built-in SQLite/COM objects are thread-affine, so moving them to a
    worker thread would break every command; RNF-16's hard guarantee is kept for
    external plugins (daemon thread) and Outlook keeps its COM watchdog.
    """
    if time.monotonic() - started > deadline:
        raise _timeout_error(driver)


def _valid_mapping(value: Any) -> bool:
    return isinstance(value, Mapping)


def _valid_mapping_rows(value: Any) -> bool:
    return isinstance(value, (list, tuple)) and all(
        isinstance(row, Mapping) for row in value
    )


def _valid_name_list(value: Any) -> bool:
    return isinstance(value, (list, tuple)) and all(
        isinstance(name, str) for name in value
    )


def _valid_str(value: Any) -> bool:
    return isinstance(value, str)


def _valid_optional_mapping(value: Any) -> bool:
    return value is None or isinstance(value, Mapping)


def _valid_find_message(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        return False
    row, mailbox = value
    return isinstance(row, Mapping) and (
        mailbox is None or isinstance(mailbox, Mapping)
    )


def _valid_attachments(value: Any) -> bool:
    if not isinstance(value, (list, tuple)):
        return False
    for entry in value:
        if not isinstance(entry, Mapping):
            return False
        index = entry.get("index")
        if not isinstance(index, int) or isinstance(index, bool):
            return False
        if not isinstance(entry.get("name"), str):
            return False
        size = entry.get("size_bytes")
        if size is not None and (not isinstance(size, int) or isinstance(size, bool)):
            return False
        if not isinstance(entry.get("native_order_key", ""), str):
            return False
        unavailable = entry.get("unavailable_reason")
        if unavailable is not None and not isinstance(unavailable, str):
            return False
    return True


def _valid_body(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    if not all(isinstance(value.get(key), bool) for key in ("available", "readable", "partial")):
        return False
    if not isinstance(value.get("headers"), Mapping):
        return False
    if not isinstance(value.get("body_text"), str):
        return False
    if not isinstance(value.get("source"), Mapping):
        return False
    if not isinstance(value.get("warnings"), (list, tuple)):
        return False
    attachments = value.get("attachments")
    if not isinstance(attachments, (list, tuple)):
        return False
    return all(
        isinstance(entry, Mapping) and isinstance(entry.get("name"), str)
        for entry in attachments
    )


#: Return-value validators of the protocol operations (UT-ERR-03.02). External
#: drivers must return these shapes; invalid data is ``E_PLUGIN_FAILED``.
_RESULT_VALIDATORS: Final[dict[str, Callable[[Any], bool]]] = {
    "accounts": _valid_mapping_rows,
    "mailboxes": _valid_mapping_rows,
    "mailboxes_without_counters": _valid_mapping_rows,
    "excluded_stores": _valid_mapping_rows,
    "resolve_mailbox": _valid_optional_mapping,
    "query": _valid_mapping_rows,
    "membership": _valid_mapping,
    "duplicate_counts": _valid_mapping,
    "recipients": _valid_mapping,
    "attachment_names": _valid_name_list,
    "find_message": _valid_find_message,
    "load_body": _valid_body,
    "load_snippet": _valid_body,
    "parse_uid": _valid_str,
    "parse_native_id": _valid_str,
    "attachments": _valid_attachments,
}


def _validate_result(operation: str, value: Any, driver: str) -> None:
    validator = _RESULT_VALIDATORS.get(operation)
    if validator is not None and not validator(value):
        raise _invalid_result(driver, operation)


def call_driver(
    operation: str,
    call: Callable[[], _T],
    *,
    driver: str,
    internal: bool | None = None,
    timeout: float | None = None,
) -> _T:
    """Single wrapper for every driver operation (M05-T01/T03; C5).

    The ``code``/``exit`` belong to the closed core set: a :class:`PluginError`
    is mapped by ``reason`` and operation context (attachment vs. the rest), an
    unmapped plugin exception or an invalid return is ``E_PLUGIN_FAILED`` (exit
    3), and a core failure of a built-in driver is re-raised untouched so the
    CLI keeps reporting ``E_INTERNAL`` (exit 1). ``internal`` defaults to the
    built-in driver names; ``timeout`` defaults to
    :data:`METADATA_TIMEOUT_SECONDS`, read at call time so tests can inject a
    short deadline.
    """
    is_internal = (
        driver in RESERVED_DRIVER_NAMES if internal is None else bool(internal)
    )
    deadline = METADATA_TIMEOUT_SECONDS if timeout is None else float(timeout)
    if is_internal:
        # Inline call: the built-in SQLite/COM objects are thread-affine (known
        # limit of RNF-16, documented in INTERFACES); Outlook keeps RF-33.
        started = time.monotonic()
        value = call()
        _check_elapsed(driver, started, deadline)
        return value
    try:
        value = _run_with_deadline(call, deadline)
    except _DeadlineExceeded:
        raise _timeout_error(driver) from None
    except PluginError as exc:
        raise map_plugin_error(
            exc, driver=driver, attachments=operation in ATTACHMENT_OPERATIONS
        ) from exc
    except Exception as exc:  # noqa: BLE001 - an unmapped plugin failure is not E_INTERNAL
        raise _plugin_failed(driver) from exc
    _validate_result(operation, value, driver)
    return value


class _DriverCallProxy:
    """Transparent proxy routing every protocol operation through :func:`call_driver`."""

    __slots__ = ("_backend", "_driver_name", "_internal", "_timeout")

    def __init__(
        self,
        backend: Any,
        *,
        driver: str,
        internal: bool,
        timeout: float | None = None,
    ) -> None:
        self._backend = backend
        self._driver_name = driver
        self._internal = internal
        self._timeout = timeout

    @property
    def driver(self) -> str:
        return self._driver_name

    def __getattr__(self, name: str) -> Any:
        backend = object.__getattribute__(self, "_backend")
        value = getattr(backend, name)
        if name not in METADATA_OPERATIONS or not callable(value):
            return value
        driver = object.__getattribute__(self, "_driver_name")
        internal = object.__getattribute__(self, "_internal")
        timeout = object.__getattribute__(self, "_timeout")

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            return call_driver(
                name,
                lambda: value(*args, **kwargs),
                driver=driver,
                internal=internal,
                timeout=timeout,
            )

        return wrapped

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"DriverCallProxy(driver={self._driver_name!r})"


def wrap_driver(
    backend: Any,
    *,
    driver: str | None = None,
    internal: bool | None = None,
    timeout: float | None = None,
) -> Any:
    """Wrap a backend so every operation goes through :func:`call_driver`.

    The query engine wraps the drivers of its pool once; wrapping an already
    wrapped backend is a no-op. ``internal`` defaults to the built-in names.
    """
    if isinstance(backend, _DriverCallProxy):
        return backend
    name = str(driver if driver is not None else getattr(backend, "driver", "") or "")
    if internal is None:
        internal = name in RESERVED_DRIVER_NAMES
    return _DriverCallProxy(
        backend, driver=name, internal=bool(internal), timeout=timeout
    )


__all__ = [
    "ATTACHMENT_OPERATIONS",
    "ATTACHMENTS_MODES",
    "CAPABILITY_KEYS",
    "Capabilities",
    "DETAIL_MAX_BYTES",
    "DRIVER_NAME_MAX_LENGTH",
    "DRIVER_NAME_PATTERN",
    "DriverMetadata",
    "ENTRY_POINT_GROUP",
    "EXTRACTION_TIMEOUT_SECONDS",
    "HINT_MAX_BYTES",
    "LOG_MESSAGE_MAX_BYTES",
    "METADATA_OPERATIONS",
    "METADATA_TIMEOUT_SECONDS",
    "NATIVE_ORDERS",
    "NativeOrder",
    "PLUGIN_API",
    "PluginContext",
    "PluginError",
    "READONLY_MODES",
    "RESERVED_DRIVER_NAMES",
    "Reason",
    "AttachmentsMode",
    "ReadOnlyMode",
    "call_driver",
    "map_plugin_error",
    "sanitize_error_field",
    "wrap_driver",
]

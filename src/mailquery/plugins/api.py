"""Public plugin API 1 (PRD-v2.1 §6.1 RF-38, §9.3; plan §5.1 C1).

This module is the frozen core surface an external backend plugin needs: the
``PLUGIN_API`` version, the closed ``Reason`` enum, :class:`PluginError` (the
plugin brings ``reason``/``hint``/``detail``/``log_message``; the core owns
``code``/``exit``), :class:`PluginContext` (``home`` and ``tmp_dir``) and the
capability/driver-metadata types the registry validates.

An external plugin must import only this package from mailquery. It must not
import the backends, the store or any other internal module (PRD-v2.1 §9.3,
RNF-12). The backend protocol itself (operations and exact signatures) is
documented in ``docs/INTERFACES.md`` and implemented by ``MailBackend``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Final, Literal, NotRequired, TypedDict

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


__all__ = [
    "ATTACHMENTS_MODES",
    "CAPABILITY_KEYS",
    "Capabilities",
    "DRIVER_NAME_MAX_LENGTH",
    "DRIVER_NAME_PATTERN",
    "DriverMetadata",
    "ENTRY_POINT_GROUP",
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
]

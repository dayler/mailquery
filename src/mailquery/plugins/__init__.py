"""Public plugin API of mailquery (API 1, PRD-v2.1 §9.3).

An external backend plugin imports only this package from the core::

    from mailquery.plugins import PluginContext, PluginError, Reason

The backend protocol (operations and exact signatures) is documented in
``docs/INTERFACES.md``; this package holds only the contract values, errors and
metadata types (plan §5.1 C1) plus the core-side error protocol of M05
(``call_driver``/``wrap_driver``, used by the core — not by plugins).
"""

from __future__ import annotations

from mailquery.plugins.api import (
    ATTACHMENT_OPERATIONS,
    ATTACHMENTS_MODES,
    CAPABILITY_KEYS,
    DETAIL_MAX_BYTES,
    DRIVER_NAME_MAX_LENGTH,
    DRIVER_NAME_PATTERN,
    ENTRY_POINT_GROUP,
    EXTRACTION_TIMEOUT_SECONDS,
    HINT_MAX_BYTES,
    LOG_MESSAGE_MAX_BYTES,
    METADATA_OPERATIONS,
    METADATA_TIMEOUT_SECONDS,
    NATIVE_ORDERS,
    PLUGIN_API,
    READONLY_MODES,
    RESERVED_DRIVER_NAMES,
    AttachmentsMode,
    Capabilities,
    DriverMetadata,
    NativeOrder,
    PluginContext,
    PluginError,
    ReadOnlyMode,
    Reason,
    call_driver,
    map_plugin_error,
    sanitize_error_field,
    wrap_driver,
)

__all__ = [
    "ATTACHMENT_OPERATIONS",
    "ATTACHMENTS_MODES",
    "CAPABILITY_KEYS",
    "DETAIL_MAX_BYTES",
    "DRIVER_NAME_MAX_LENGTH",
    "DRIVER_NAME_PATTERN",
    "ENTRY_POINT_GROUP",
    "EXTRACTION_TIMEOUT_SECONDS",
    "HINT_MAX_BYTES",
    "LOG_MESSAGE_MAX_BYTES",
    "METADATA_OPERATIONS",
    "METADATA_TIMEOUT_SECONDS",
    "NATIVE_ORDERS",
    "PLUGIN_API",
    "READONLY_MODES",
    "RESERVED_DRIVER_NAMES",
    "AttachmentsMode",
    "Capabilities",
    "DriverMetadata",
    "NativeOrder",
    "PluginContext",
    "PluginError",
    "ReadOnlyMode",
    "Reason",
    "call_driver",
    "map_plugin_error",
    "sanitize_error_field",
    "wrap_driver",
]

"""Public plugin API of mailquery (API 1, PRD-v2.1 §9.3).

An external backend plugin imports only this package from the core::

    from mailquery.plugins import PluginContext, PluginError, Reason

The backend protocol (operations and exact signatures) is documented in
``docs/INTERFACES.md``; this package holds only the contract values, errors and
metadata types (plan §5.1 C1).
"""

from __future__ import annotations

from mailquery.plugins.api import (
    ATTACHMENTS_MODES,
    CAPABILITY_KEYS,
    DRIVER_NAME_MAX_LENGTH,
    DRIVER_NAME_PATTERN,
    ENTRY_POINT_GROUP,
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
)

__all__ = [
    "ATTACHMENTS_MODES",
    "CAPABILITY_KEYS",
    "DRIVER_NAME_MAX_LENGTH",
    "DRIVER_NAME_PATTERN",
    "ENTRY_POINT_GROUP",
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
]

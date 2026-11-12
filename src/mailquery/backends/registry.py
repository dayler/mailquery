"""Backend registry: entry-point discovery, contract validation and lazy loading.

The registry is the only place that knows how drivers are discovered:

* it discovers the ``mailquery.backends`` entry point group with
  :mod:`importlib.metadata` and merges a static fallback for the built-in
  backends, so the package works from ``src/`` without ``pip install`` (CI and
  development);
* it lists drivers and their versions from distribution metadata **without
  importing** plugin modules (``--version`` must not import plugins);
* it validates ``driver``, ``plugin_api`` and the capability map of each driver
  and detects reserved names and duplicates; violations are
  ``E_PLUGIN_INCOMPATIBLE`` (exit 3) and an unknown driver is
  ``E_DRIVER_UNKNOWN`` (exit 2);
* it imports a driver's module only when that one driver is loaded (lazy load):
  the core loads only drivers declared in ``config.toml`` or referenced by a uid;
* built-in drivers are listed from a static metadata table, so their metadata
  never imports ``mailquery.backends.apple_mail`` / ``outlook``.

The module imports only the standard library and the ``mailquery`` package:
it never imports a backend implementation, the store or the CLI.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

import mailquery
from mailquery.plugins import (
    ATTACHMENTS_MODES,
    CAPABILITY_KEYS,
    DRIVER_NAME_PATTERN,
    ENTRY_POINT_GROUP,
    NATIVE_ORDERS,
    PLUGIN_API,
    READONLY_MODES,
    RESERVED_DRIVER_NAMES,
    Capabilities,
    DriverMetadata,
    PluginContext,
)
from mailquery.errors import MailqueryError

#: Canonical entry point target of each built-in driver (also declared in pyproject.toml).
INTERNAL_TARGETS: Final[dict[str, str]] = {
    "apple_mail": "mailquery.backends.apple_mail:AppleMailBackend",
    "outlook": "mailquery.backends.outlook:OutlookBackend",
}

#: Capability maps declared by the built-in drivers.
INTERNAL_CAPABILITIES: Final[dict[str, Capabilities]] = {
    "apple_mail": {
        "network": False,
        "readonly": "structural",
        "body_local": True,
        "attachments": "local",
        "native_order": "numeric",
    },
    "outlook": {
        "network": False,
        "readonly": "structural",
        "body_local": True,
        "attachments": "local",
        "native_order": "text",
    },
}


@dataclass(frozen=True)
class RawDriver:
    """One discovered driver before validation: name, target and distribution metadata."""

    name: str
    value: str
    version: str
    internal: bool
    entry_point: Any = None


def package_version() -> str:
    """Version of the installed ``mailquery`` distribution, or ``__version__`` in development."""
    try:
        return importlib.metadata.version("mailquery")
    except Exception:  # noqa: BLE001 - missing/broken distribution metadata falls back
        return mailquery.__version__


def installed_entry_points() -> tuple[Any, ...]:
    """Entry points of :data:`ENTRY_POINT_GROUP`; empty when metadata is unavailable.

    Module-level seam: tests inject the group here so no ``pip install`` is needed.
    """
    try:
        return tuple(importlib.metadata.entry_points(group=ENTRY_POINT_GROUP))
    except Exception:  # noqa: BLE001 - a broken distribution list must not break --version
        return ()


def _entry_point_version(entry_point: Any) -> str:
    """Distribution version of an entry point, without importing its module."""
    version = getattr(entry_point, "version", None)
    if isinstance(version, str) and version:
        return version
    distribution = getattr(entry_point, "dist", None)
    if distribution is not None:
        try:
            version = distribution.version
        except Exception:  # noqa: BLE001 - a hand-made EntryPoint has no distribution
            version = None
        if isinstance(version, str) and version:
            return version
    return package_version()


def _internal_available(driver: str, platform: str) -> bool:
    """List an internal driver only on the platform it serves for ``--version``."""
    if driver == "outlook":
        return platform == "win32"
    return platform != "win32"


def _driver_unknown(driver: str, installed: Sequence[str]) -> MailqueryError:
    names = ", ".join(installed) if installed else "none"
    return MailqueryError(
        "E_DRIVER_UNKNOWN",
        f"unknown driver {driver!r}",
        f"installed drivers: {names}; install the plugin with "
        "`pipx inject mailquery <package>`; driver names must match [a-z0-9_]{1,64}",
        "unknown driver",
    )


def _plugin_incompatible(message: str, hint: str) -> MailqueryError:
    return MailqueryError(
        "E_PLUGIN_INCOMPATIBLE",
        message,
        hint,
        "incompatible plugin",
    )


class BackendRegistry:
    """Discovery, validation and lazy loading of the installed backend drivers."""

    def __init__(
        self,
        *,
        platform: str | None = None,
        entry_points: Iterable[Any] | None = None,
    ) -> None:
        self.platform = platform if platform is not None else sys.platform
        self._provided_entry_points: tuple[Any, ...] | None = (
            None if entry_points is None else tuple(entry_points)
        )
        self._raw: list[RawDriver] | None = None
        self._loaded: dict[str, Any] = {}

    # -- discovery (never imports a driver) --------------------------------- #

    def entries(self) -> list[RawDriver]:
        """All raw entries: discovered group plus the static fallback of the built-ins."""
        if self._raw is not None:
            return list(self._raw)
        raw: list[RawDriver] = []
        seen: set[str] = set()
        for entry_point in self._entry_point_objects():
            name = str(getattr(entry_point, "name", ""))
            value = str(getattr(entry_point, "value", ""))
            internal = INTERNAL_TARGETS.get(name) == value
            raw.append(
                RawDriver(
                    name=name,
                    value=value,
                    version=package_version() if internal else _entry_point_version(entry_point),
                    internal=internal,
                    entry_point=entry_point,
                )
            )
            seen.add(name)
        for name, target in INTERNAL_TARGETS.items():
            if name in seen:
                continue
            raw.append(
                RawDriver(
                    name=name,
                    value=target,
                    version=package_version(),
                    internal=True,
                    entry_point=None,
                )
            )
        self._raw = raw
        return list(raw)

    def installed(self) -> list[str]:
        """Sorted driver names of the group (metadata only; no validation, no imports)."""
        return sorted({entry.name for entry in self.entries()})

    def is_installed(self, driver: str) -> bool:
        """Whether ``driver`` is present in the group (no import)."""
        return any(entry.name == driver for entry in self.entries())

    def versions(self, *, platform: str | None = None) -> list[tuple[str, str]]:
        """``(driver, version)`` pairs for ``--version``: alphabetical, internals filtered by OS."""
        current = platform if platform is not None else self.platform
        versions: dict[str, str] = {}
        for entry in self.entries():
            if entry.internal and not _internal_available(entry.name, current):
                continue
            versions.setdefault(entry.name, entry.version)
        return sorted(versions.items())

    # -- validation and loading --------------------------------------------- #

    def declared(self, drivers: Iterable[str]) -> list[DriverMetadata]:
        """Validated metadata of the given drivers, in the requested order."""
        return [self.info(driver) for driver in drivers]

    def info(self, driver: str) -> DriverMetadata:
        """Validated metadata of one driver; loads only that plugin module, once."""
        candidates = [entry for entry in self.entries() if entry.name == driver]
        if not candidates:
            raise _driver_unknown(driver, self.installed())
        self._validate_driver_name(driver)
        if len(candidates) > 1:
            raise _plugin_incompatible(
                f"duplicate driver {driver!r}: {len(candidates)} entry points declare it",
                "each driver name must be unique; uninstall the duplicated plugin",
            )
        entry = candidates[0]
        if entry.internal:
            return self._internal_metadata(entry)
        if driver in RESERVED_DRIVER_NAMES:
            raise _plugin_incompatible(
                f"driver name {driver!r} is reserved for the built-in backend",
                "choose a driver name outside 'apple_mail' and 'outlook'",
            )
        plugin = self._load_raw(entry)
        return self._plugin_metadata(entry, plugin)

    def load(self, driver: str) -> Any:
        """Import the driver object (class or factory) of one driver only."""
        self.info(driver)
        if driver in self._loaded:
            return self._loaded[driver]
        entry = next(candidate for candidate in self.entries() if candidate.name == driver)
        return self._load_raw(entry)

    def open(self, driver: str, *, context: PluginContext | None = None) -> Any:
        """Load and instantiate one declared driver (API 1 entry-point convention).

        The entry point is a class or a factory. An external driver is invoked
        with one positional :class:`PluginContext` (``home``/``tmp_dir``); the
        built-in drivers are instantiated without arguments. An entry point that
        already returns a backend instance is used as is. A constructor failure
        is ``E_PLUGIN_INCOMPATIBLE`` (exit 3): the driver was declared but could
        not start, and the command must fail without partial results.
        """
        metadata = self.info(driver)
        loaded = self.load(driver)
        if not isinstance(loaded, type) and hasattr(loaded, "query"):
            return loaded
        try:
            if metadata.get("internal"):
                return loaded() if isinstance(loaded, type) else loaded
            if context is not None:
                return loaded(context)
            return loaded()
        except MailqueryError:
            raise
        except Exception as exc:  # noqa: BLE001 - the driver could not start
            raise _plugin_incompatible(
                f"driver {driver!r} failed to start: {type(exc).__name__}",
                "reinstall or upgrade the plugin and run `mailquery doctor`",
            ) from exc

    def open_drivers(
        self,
        drivers: Iterable[str],
        *,
        context: PluginContext | None = None,
    ) -> dict[str, Any]:
        """Load and instantiate the given declared drivers, in the requested order."""
        opened: dict[str, Any] = {}
        for driver in drivers:
            name = str(driver)
            opened[name] = self.open(name, context=context)
        return opened

    # -- internals ---------------------------------------------------------- #

    def _entry_point_objects(self) -> tuple[Any, ...]:
        if self._provided_entry_points is not None:
            return self._provided_entry_points
        return installed_entry_points()

    @staticmethod
    def _validate_driver_name(driver: str) -> None:
        if DRIVER_NAME_PATTERN.fullmatch(driver) is None:
            raise _plugin_incompatible(
                f"invalid driver name {driver!r}: expected [a-z0-9_]{{1,64}}",
                "driver must match [a-z0-9_]{1,64}; it also names <driver>.toml, "
                "logs/<driver>.log and tmp/plugin-<driver>/",
            )

    def _internal_metadata(self, entry: RawDriver) -> DriverMetadata:
        capabilities = dict(INTERNAL_CAPABILITIES[entry.name])
        return DriverMetadata(
            driver=entry.name,
            plugin_api=PLUGIN_API,
            version=entry.version,
            capabilities=capabilities,  # type: ignore[typeddict-item]
            internal=True,
        )

    def _load_raw(self, entry: RawDriver) -> Any:
        if entry.name in self._loaded:
            return self._loaded[entry.name]
        try:
            if entry.internal or entry.entry_point is None:
                loaded = _import_target(entry.value)
            else:
                loaded = entry.entry_point.load()
        except ImportError as exc:
            raise _plugin_incompatible(
                f"driver {entry.name!r} cannot be imported: {exc}",
                "a dependency of the plugin is missing; reinstall or upgrade the plugin",
            ) from exc
        except Exception as exc:  # noqa: BLE001 - any import-time failure is a plugin failure
            raise _plugin_incompatible(
                f"driver {entry.name!r} failed to import: {type(exc).__name__}: {exc}",
                "reinstall or upgrade the plugin and run `mailquery doctor`",
            ) from exc
        self._loaded[entry.name] = loaded
        return loaded

    def _plugin_metadata(self, entry: RawDriver, plugin: Any) -> DriverMetadata:
        declared_driver = getattr(plugin, "driver", None)
        if declared_driver != entry.name:
            raise _plugin_incompatible(
                f"driver {entry.name!r} declares driver={declared_driver!r}",
                f"the entry point name and the declared driver must both be {entry.name!r}",
            )
        plugin_api = getattr(plugin, "plugin_api", None)
        if not (isinstance(plugin_api, int) and not isinstance(plugin_api, bool)):
            raise _plugin_incompatible(
                f"driver {entry.name!r} declares no valid plugin_api ({plugin_api!r})",
                f"expected 1, found {plugin_api!r}; update or reinstall the plugin",
            )
        if plugin_api != PLUGIN_API:
            raise _plugin_incompatible(
                f"driver {entry.name!r} declares plugin_api={plugin_api!r}; "
                f"this mailquery implements plugin_api={PLUGIN_API}",
                f"expected 1, found {plugin_api!r}; update or reinstall the plugin",
            )
        capabilities = _validated_capabilities(entry.name, getattr(plugin, "capabilities", None))
        return DriverMetadata(
            driver=entry.name,
            plugin_api=PLUGIN_API,
            version=entry.version,
            capabilities=capabilities,
            internal=False,
        )


def _import_target(target: str) -> Any:
    """Import ``"module:attribute"`` without importing any other driver."""
    module_name, separator, attribute = target.partition(":")
    if not module_name or not separator or not attribute:
        raise ImportError(
            f"invalid entry point target {target!r}: expected 'module:attribute'"
        )
    module = importlib.import_module(module_name)
    loaded: Any = module
    for part in attribute.split("."):
        loaded = getattr(loaded, part)
    return loaded


def _validated_capabilities(driver: str, capabilities: Any) -> Capabilities:
    """Validate the closed capability map of one driver."""
    hint = (
        "declare network, readonly, body_local, attachments and native_order "
        "with the values of the API 1 contract"
    )
    if not isinstance(capabilities, Mapping):
        raise _plugin_incompatible(
            f"driver {driver!r} declares no capability map", hint
        )
    missing = [key for key in CAPABILITY_KEYS if key not in capabilities]
    if missing:
        raise _plugin_incompatible(
            f"driver {driver!r} is missing capability {missing[0]!r}", hint
        )
    unknown = [key for key in capabilities if key not in CAPABILITY_KEYS]
    if unknown:
        raise _plugin_incompatible(
            f"driver {driver!r} declares unknown capability {unknown[0]!r}", hint
        )
    network = capabilities["network"]
    body_local = capabilities["body_local"]
    if not isinstance(network, bool):
        raise _plugin_incompatible(
            f"driver {driver!r} declares invalid capability network={network!r}",
            "network must be a boolean",
        )
    if not isinstance(body_local, bool):
        raise _plugin_incompatible(
            f"driver {driver!r} declares invalid capability body_local={body_local!r}",
            "body_local must be a boolean",
        )
    readonly = capabilities["readonly"]
    if not isinstance(readonly, str) or readonly not in READONLY_MODES:
        raise _plugin_incompatible(
            f"driver {driver!r} declares invalid capability readonly={readonly!r}",
            "readonly must be 'structural' or 'promise'",
        )
    attachments = capabilities["attachments"]
    if not isinstance(attachments, str) or attachments not in ATTACHMENTS_MODES:
        raise _plugin_incompatible(
            f"driver {driver!r} declares invalid capability attachments={attachments!r}",
            "attachments must be 'local', 'remote' or 'none'",
        )
    native_order = capabilities["native_order"]
    if not isinstance(native_order, str) or native_order not in NATIVE_ORDERS:
        raise _plugin_incompatible(
            f"driver {driver!r} declares invalid capability native_order={native_order!r}",
            "native_order must be 'numeric' or 'text'",
        )
    if attachments == "remote" and not network:
        raise _plugin_incompatible(
            f"driver {driver!r} declares attachments='remote' without network=true",
            "attachments='remote' requires network=true",
        )
    if body_local is False and not network:
        raise _plugin_incompatible(
            f"driver {driver!r} declares body_local=false without network=true",
            "body_local=false requires network=true",
        )
    return Capabilities(
        network=network,
        readonly=readonly,
        body_local=body_local,
        attachments=attachments,
        native_order=native_order,
    )


__all__ = [
    "BackendRegistry",
    "ENTRY_POINT_GROUP",
    "INTERNAL_CAPABILITIES",
    "INTERNAL_TARGETS",
    "RawDriver",
    "installed_entry_points",
    "package_version",
]

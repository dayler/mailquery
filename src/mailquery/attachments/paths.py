"""Attachment cache paths.

``message_dir``/``attachment_path`` build the deterministic
``~/.mailquery/attachments/<driver>/<native_id>/<sanitized_name>`` path
without touching the disk. When the path (or the ``<native_id>``
component) would exceed the platform limit, the component is replaced by the
stable 32-hex identifier of ``SHA-256(uid UTF-8)`` exposed by
:func:`mailquery.uid.stable_identifier` (conservative 240-byte path budget on
Windows, the real POSIX component/``PATH_MAX`` limits elsewhere).

``message_dir`` reserves the maximum ``sanitized_name`` budget when it decides
between ``<native_id>`` and the stable identifier, so the directory choice is
stable for every attachment of the message and ``attachment_path`` always
returns a child of ``message_dir``. The path functions perform no I/O beyond
``stat``/``pathconf`` to learn the platform limits.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Final

from mailquery.attachments.sanitize import MAX_SANITIZED_BYTES
from mailquery.uid import split_uid, stable_identifier

#: Directory under the application home that holds the attachment cache.
ATTACHMENTS_DIR_NAME: Final[str] = "attachments"
#: Conservative full-path budget on Windows.
WINDOWS_PATH_BUDGET_BYTES: Final[int] = 240
#: Per-component limit used when ``pathconf`` is unavailable.
POSIX_COMPONENT_MAX_FALLBACK: Final[int] = 255
#: Full-path limit used when ``pathconf`` is unavailable.
POSIX_PATH_MAX_FALLBACK: Final[int] = 4096
_WINDOWS_COMPONENT_MAX_BYTES: Final[int] = 255


def cache_root(home: str | Path) -> Path:
    """Return ``<home>/attachments`` (the cache root; nothing is created)."""
    return Path(home) / ATTACHMENTS_DIR_NAME


def path_limits(home: str | Path, *, platform: str | None = None) -> tuple[int, int]:
    """Return ``(component_max_bytes, path_max_bytes)`` for the platform of ``home``.

    ``platform`` is a test injection point (defaults to ``sys.platform``): on
    ``win32`` the conservative 240-byte path budget and the 255-byte component
    limit apply; elsewhere the real ``PC_NAME_MAX``/``PC_PATH_MAX`` of the
    filesystem that contains ``home`` are used.
    """
    current = sys.platform if platform is None else platform
    if current == "win32":
        return _WINDOWS_COMPONENT_MAX_BYTES, WINDOWS_PATH_BUDGET_BYTES
    anchor = _existing_ancestor(Path(home))
    component_max = _pathconf(anchor, "PC_NAME_MAX", POSIX_COMPONENT_MAX_FALLBACK)
    path_max = _pathconf(anchor, "PC_PATH_MAX", POSIX_PATH_MAX_FALLBACK)
    return component_max, path_max


def message_dir(
    home: str | Path, uid: str, *, platform: str | None = None
) -> Path:
    """Return the attachment directory of ``uid`` without creating it.

    ``uid`` is the canonical ``"<driver>:<native_id>"`` string; a legacy
    unprefixed uid resolves with the native driver. ``<native_id>`` is replaced
    by :func:`stable_identifier` when the component or the full path (reserving
    the maximum sanitized filename) would exceed the platform limit.
    """
    driver, native_id, canonical_uid = _split(uid)
    base = cache_root(home) / driver
    component_max, path_max = path_limits(home, platform=platform)
    if _fits(base, native_id, component_max, path_max):
        component = native_id
    else:
        component = stable_identifier(canonical_uid)
    return base / component


def attachment_path(
    home: str | Path,
    uid: str,
    sanitized_name: str,
    *,
    platform: str | None = None,
) -> Path:
    """Return the cache path of one attachment: ``message_dir / sanitized_name``.

    ``sanitized_name`` is the already-prefixed result of
    :func:`mailquery.attachments.sanitize.sanitize_name`; this function never
    prepends ``NN_`` again (no double prefix) and only joins it to the message
    directory.
    """
    if not isinstance(sanitized_name, str) or not sanitized_name:
        raise ValueError("sanitized_name must be a non-empty string")
    if any(character in sanitized_name for character in ("/", "\\", "\x00")):
        raise ValueError("sanitized_name must be a single path component")
    if len(sanitized_name.encode("utf-8")) > MAX_SANITIZED_BYTES:
        raise ValueError(
            f"sanitized_name exceeds the {MAX_SANITIZED_BYTES}-byte budget"
        )
    return message_dir(home, uid, platform=platform) / sanitized_name


def _split(uid: str) -> tuple[str, str, str]:
    if not isinstance(uid, str) or not uid:
        raise ValueError("uid must be a non-empty string")
    driver, native_id = split_uid(uid)
    if not driver or not native_id:
        raise ValueError(f"uid {uid!r} has an empty driver or native id")
    canonical = uid if ":" in uid else f"{driver}:{native_id}"
    return driver, native_id, canonical


def _fits(base: Path, native_id: str, component_max: int, path_max: int) -> bool:
    if len(native_id.encode("utf-8")) > component_max:
        return False
    # The directory decision reserves the longest possible sanitized filename so
    # every attachment of the message shares the same directory.
    reserved = (
        len(str(base / native_id).encode("utf-8")) + 1 + MAX_SANITIZED_BYTES
    )
    return reserved <= path_max


def _existing_ancestor(path: Path) -> str:
    candidate = path
    while True:
        try:
            if candidate.exists():
                return str(candidate)
        except OSError:
            pass
        parent = candidate.parent
        if parent == candidate:
            return str(candidate)
        candidate = parent


def _pathconf(anchor: str, name: str, fallback: int) -> int:
    try:
        return int(os.pathconf(anchor, name))
    except (AttributeError, OSError, ValueError):
        return fallback

"""Prefixed message ``uid`` format: ``"<driver>:<native_id>"``.

The core owns the format: every emitted
uid is an opaque ``str``; the prefix is split at the **first** ``:`` and only the
``<native_id>`` is handed to the driver. The plugin validates its own part with
``parse_native_id``; this module validates syntax, the installed-driver check
and the legacy unprefixed input resolved with the platform's native driver.

Everything here is pure and side-effect free: it is safe to call before the
application home exists, before ``config.toml`` is read and before the store is
opened.
"""

from __future__ import annotations

import hashlib
import re
import sys
from dataclasses import dataclass
from typing import Callable, Final

from mailquery.errors import MailqueryError

DRIVER_NAME_MAX_LENGTH: Final[int] = 64
NATIVE_ID_MAX_LENGTH: Final[int] = 1024

DRIVER_PATTERN: Final[re.Pattern[str]] = re.compile(r"[a-z0-9_]{1,64}")
NATIVE_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9._=-]{1,1024}")

_STABLE_IDENTIFIER_CHARS: Final[int] = 32

_UID_HINT = (
    "run `mailquery search` to find the uid of a message; a legacy unprefixed uid "
    "is accepted for the platform's native driver"
)


@dataclass(frozen=True, slots=True)
class ParsedUid:
    """A validated uid split into its driver prefix and native id."""

    driver: str
    native_id: str

    @property
    def uid(self) -> str:
        """The canonical ``"<driver>:<native_id>"`` string."""
        return f"{self.driver}:{self.native_id}"


def platform_native_driver(platform: str | None = None) -> str:
    """Driver of the platform's native backend: ``outlook`` on win32, ``apple_mail`` elsewhere."""
    current = sys.platform if platform is None else platform
    return "outlook" if current == "win32" else "apple_mail"


def is_valid_driver(value: object) -> bool:
    """Whether ``value`` is a valid driver name (``[a-z0-9_]{1,64}``)."""
    return isinstance(value, str) and DRIVER_PATTERN.fullmatch(value) is not None


def is_valid_native_id(value: object) -> bool:
    """Whether ``value`` is a valid native id (charset, no leading dot, no ``..``)."""
    if not isinstance(value, str):
        return False
    if NATIVE_ID_PATTERN.fullmatch(value) is None:
        return False
    return not value.startswith(".") and ".." not in value


def split_uid(text: str, *, native_driver: str | None = None) -> tuple[str, str]:
    """Split ``text`` at the first ``:``; an unprefixed value uses the native driver.

    No validation is performed: ``split_uid("a:b:c") == ("a", "b:c")`` and the
    native part is then rejected by :func:`parse_uid` because of the ``:``.
    """
    if not isinstance(text, str):
        raise _invalid_uid(text, "expected a string")
    if ":" in text:
        driver, native_id = text.split(":", 1)
        return driver, native_id
    return (native_driver or platform_native_driver(), text)


def format_uid(driver: object, native_id: object) -> str:
    """Return ``"<driver>:<native_id>"`` after validating both components."""
    if not is_valid_driver(driver):
        raise _invalid_uid(
            f"{driver!r}:{native_id!r}",
            f"invalid driver {driver!r}: expected [a-z0-9_]{{1,{DRIVER_NAME_MAX_LENGTH}}}",
        )
    if not is_valid_native_id(native_id):
        raise _invalid_native_id(native_id)
    return f"{driver}:{native_id}"


def parse_uid(
    text: object,
    *,
    native_driver: str | None = None,
    is_installed: Callable[[str], bool] | None = None,
) -> ParsedUid:
    """Validate a user-supplied uid and return its driver and native id.

    ``native_driver`` overrides the platform's native driver for the legacy
    unprefixed form (tests and non-standard hosts). ``is_installed`` is the
    registry check (``E_DRIVER_UNKNOWN``); omit it for pure syntax validation.
    """
    driver, native_id = split_uid(text, native_driver=native_driver)
    if not is_valid_driver(driver):
        raise _invalid_uid(
            text,
            f"invalid driver {driver!r}: expected [a-z0-9_]{{1,{DRIVER_NAME_MAX_LENGTH}}}",
        )
    if not is_valid_native_id(native_id):
        raise _invalid_native_id(native_id, text=text)
    if is_installed is not None and not is_installed(driver):
        raise driver_unknown(driver)
    return ParsedUid(driver=driver, native_id=native_id)


def stable_identifier(uid: str) -> str:
    """Stable 32-hex path identifier: first 32 chars of ``SHA-256(uid UTF-8)``.

    The attachment cache uses it when ``<native_id>`` or the cache path exceeds the file-system
    limits; it is deterministic across platforms.
    """
    if not isinstance(uid, str) or not uid:
        raise _invalid_uid(uid, "expected a non-empty uid string")
    digest = hashlib.sha256(uid.encode("utf-8")).hexdigest()
    return digest[:_STABLE_IDENTIFIER_CHARS]


def driver_unknown(driver: str) -> MailqueryError:
    """``E_DRIVER_UNKNOWN`` (exit 2): the prefix is not an installed driver."""
    return MailqueryError(
        "E_DRIVER_UNKNOWN",
        f"unknown driver {driver!r}",
        "install the driver plugin with `pipx inject mailquery <package>` and declare "
        "its account in ~/.mailquery/config.toml; driver names must match [a-z0-9_]{1,64}",
        "unknown driver",
    )


def _invalid_uid(value: object, reason: str) -> MailqueryError:
    return MailqueryError(
        "E_USAGE",
        f"invalid uid {value!r}: {reason}",
        _UID_HINT,
        "invalid uid",
    )


def _invalid_native_id(value: object, *, text: object | None = None) -> MailqueryError:
    shown = value if text is None else text
    return MailqueryError(
        "E_USAGE",
        f"invalid uid {shown!r}: expected '<driver>:<native_id>' with a native id "
        "matching [A-Za-z0-9._=-]{1,1024} (no leading dot, no '..', no spaces)",
        _UID_HINT,
        "invalid uid",
    )


__all__ = [
    "DRIVER_NAME_MAX_LENGTH",
    "DRIVER_PATTERN",
    "NATIVE_ID_MAX_LENGTH",
    "NATIVE_ID_PATTERN",
    "ParsedUid",
    "driver_unknown",
    "format_uid",
    "is_valid_driver",
    "is_valid_native_id",
    "parse_uid",
    "platform_native_driver",
    "split_uid",
    "stable_identifier",
]

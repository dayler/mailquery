"""COM access to classic Outlook.

This is the ONLY module that imports ``win32com``, ``pythoncom`` or
``pywintypes``, and it does so lazily inside functions: importing it on Linux or
macOS never touches pywin32.

What it provides:

* Client detection (:func:`connect`), in this order: pywin32
  importable, ``HKCR\\Outlook.Application\\CurVer`` registered and >= 16.0, then a
  running instance obtained with ``GetActiveObject`` only. Outlook is never
  launched.
* The pywin32 cache confined to ``<home>/tmp/gen_py`` (``win32com.__gen_path__``
  set before ``win32com.client`` is imported; dynamic dispatch).
* :class:`ReadOnlyCom`, the read-only proxy with the explicit whitelist
  :data:`READONLY_MEMBERS`.
* The COM watchdog (:class:`Watchdog`): one daemon thread; every COM call made
  through the proxy is bounded by :data:`CALL_TIMEOUT_SECONDS`.
* COM error mapping: one retry after 100 ms for transient
  rejections, then ``E_CLIENT_BUSY``; ``E_ACCESSDENIED`` is ``E_PERMISSION``;
  anything else is :class:`ComCallError` (``E_INTERNAL`` carrying the HRESULT,
  which the backend may catch for the expected cases).
* Read-only helpers outside the OOM: registry (:class:`WinRegistry`), drive type
  (:func:`get_drive_type`) and the SecurityCenter2 antivirus query
  (:class:`WmiSecurityCenter`).

Test seams: the ``outlook_app`` connector, the
``registry`` and ``security_center`` objects, the ``pywin32`` flag, the
module-level :data:`CALL_TIMEOUT_SECONDS` and :func:`get_drive_type`.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from contextlib import contextmanager
from datetime import date, datetime
from datetime import time as dt_time
from pathlib import Path
from typing import Any, Callable, Iterator

from mailquery.errors import MailqueryError
from mailquery.logging_setup import get_logger

# --------------------------------------------------------------------------- #
# Constants and seams
# --------------------------------------------------------------------------- #

PROG_ID = "Outlook.Application"
MIN_MAJOR_VERSION = 16

#: Deadline of one COM call, in seconds (patched by tests and run_cli).
CALL_TIMEOUT_SECONDS = 30.0
#: Delay before the single retry of a transient rejection.
RETRY_DELAY_SECONDS = 0.1

HKCR = "HKCR"
HKCU = "HKCU"
HKLM = "HKLM"
CURVER_KEY = r"Outlook.Application\CurVer"

# HRESULTs (unsigned).
RPC_E_CALL_REJECTED = 0x80010001
RPC_E_SERVERCALL_RETRYLATER = 0x8001010A
E_ACCESSDENIED = 0x80070005
DISP_E_EXCEPTION = 0x80020009
MK_E_UNAVAILABLE = 0x800401E3
CO_E_CLASSSTRING = 0x800401F3
MAPI_E_NOT_FOUND = 0x8004010F
MAPI_E_INVALID_ENTRYID = 0x80040107
E_FAIL = 0x80004005
DISP_E_UNKNOWNNAME = 0x80020006
TRANSIENT_HRESULTS = frozenset({RPC_E_CALL_REJECTED, RPC_E_SERVERCALL_RETRYLATER})

# IDispatch::Invoke flags (oaidl.h) of the direct calls of the proxy.
DISPATCH_METHOD = 0x1
DISPATCH_PROPERTYGET = 0x2
#: Kinds whose COM class differs per object (MailItem, MeetingItem, ReportItem...):
#: their DISPIDs are looked up per object, not per kind.
PER_OBJECT_DISPID_KINDS = frozenset({"Item"})

# GetDriveTypeW results.
DRIVE_UNKNOWN = 0
DRIVE_NO_ROOT_DIR = 1
DRIVE_REMOVABLE = 2
DRIVE_FIXED = 3
DRIVE_REMOTE = 4

#: Detail of the running ``doctor`` check when a COM call times out.
DOCTOR_TIMEOUT_DETAIL = (
    "timeout after 30 s: Outlook did not respond (possible security prompt)"
)

# Outlook Object Model Guard policies. Group
# Policy values of Outlook 2016+ (user configuration); the PromptOOM* values apply
# only with AdminSecurityMode = 3 ("use Outlook Security Group Policy").
OOM_POLICY_KEY = r"Software\Policies\Microsoft\Office\16.0\Outlook\Security"
ADMIN_SECURITY_MODE = "AdminSecurityMode"
ADMIN_SECURITY_MODE_GROUP_POLICY = 3
PROMPT_OOM_ADDRESS_INFORMATION = "PromptOOMAddressInformationAccess"
PROMPT_OOM_ADDRESS_BOOK = "PromptOOMAddressBookAccess"
OOM_DENY = 0  # automatically deny
OOM_PROMPT = 1  # prompt user
OOM_APPROVE = 2  # automatically approve (3 = prompt based on computer security)
OOM_SETTING_NAMES = {
    OOM_DENY: "automatically deny",
    OOM_PROMPT: "prompt user",
    OOM_APPROVE: "automatically approve",
}
#: ``AntiVirusProduct.productState`` bit set while real-time protection is on.
ANTIVIRUS_ENABLED_BIT = 0x1000

HINT_DEPENDENCY = "pipx reinstall mailquery"
HINT_UNSUPPORTED = (
    "install classic Outlook (version 16.0 or later); the new Outlook is not supported"
)
HINT_NOT_RUNNING = "open classic Outlook with the same user, without elevation, and retry"
HINT_BUSY = "Outlook is busy (an open dialog or a long operation); wait a moment and retry"
HINT_PERMISSION = (
    "Outlook denied programmatic access; check the Outlook security policies "
    "with `mailquery doctor`"
)
HINT_TIMEOUT = (
    "Outlook may be showing a security prompt or a dialog; check the Outlook "
    "window and run `mailquery doctor`"
)
HINT_INTERNAL = (
    "run `mailquery doctor` and check ~/.mailquery/logs/mailquery.log for details"
)
HINT_READONLY = (
    "this is a mailquery bug: the read-only proxy blocked an Outlook member; "
    "report it with ~/.mailquery/logs/mailquery.log"
)

# --------------------------------------------------------------------------- #
# Read-only whitelist
# --------------------------------------------------------------------------- #

#: ``{kind: {member: returned kind or None}}``. A member whose entry names a kind
#: returns a proxy of that kind; ``None`` is a scalar returned as is. Exact-case
#: match; anything else, every assignment and every ``_``/dunder name is
#: ``E_INTERNAL`` before reaching COM. Collections are read with ``Count`` and
#: ``Item(i)`` only. The address book (``AddressEntry``, ``GetExchangeUser``...)
#: is never whitelisted.
READONLY_MEMBERS: dict[str, dict[str, str | None]] = {
    "Application": {"Version": None, "Session": "NameSpace"},
    "NameSpace": {"Stores": "Stores", "Accounts": "Accounts", "GetItemFromID": "Item"},
    "Stores": {"Count": None, "Item": "Store"},
    "Store": {
        "DisplayName": None,
        "ExchangeStoreType": None,
        "IsCachedExchange": None,
        "FilePath": None,
        "StoreID": None,
        "PropertyAccessor": "PropertyAccessor",
        "GetRootFolder": "Folder",
        "GetDefaultFolder": "Folder",
    },
    "Accounts": {"Count": None, "Item": "Account"},
    "Account": {"AccountType": None, "SmtpAddress": None, "DeliveryStore": "Store"},
    "Folders": {"Count": None, "Item": "Folder"},
    "Folder": {
        "Name": None,
        "EntryID": None,
        "DefaultItemType": None,
        "Folders": "Folders",
        "PropertyAccessor": "PropertyAccessor",
        "GetTable": "Table",
    },
    "Table": {
        "Columns": "Columns",
        "EndOfTable": None,
        "GetNextRow": "Row",
        "GetRowCount": None,
        "GetArray": None,  # rows as a list of value tuples (bulk read of the in-memory view)
    },
    "Columns": {"Add": "Column"},  # in-memory table view only; Folders.Add stays forbidden
    "Column": {},
    "Row": {"GetValues": None},
    "PropertyAccessor": {"GetProperty": None},
    "Item": {
        "MessageClass": None,
        "EntryID": None,
        "Parent": "Folder",
        "DownloadState": None,
        "Body": None,
        "HTMLBody": None,
        "Attachments": "Attachments",
        "Recipients": "Recipients",
        "PropertyAccessor": "PropertyAccessor",
    },
    "Attachments": {"Count": None, "Item": "Attachment"},
    "Attachment": {
        "FileName": None,
        "DisplayName": None,
        "PropertyAccessor": "PropertyAccessor",
        # COM exception for attachments: ``SaveAsFile`` is the only writing operation
        # the read-only proxy allows, used for an already-downloaded local attachment.
        "Size": None,
        "Type": None,
        "SaveAsFile": None,
    },
    "Recipients": {"Count": None, "Item": "Recipient"},
    "Recipient": {"Name": None, "Type": None, "PropertyAccessor": "PropertyAccessor"},
}

#: Whitelisted members that are methods (invoked); the others are properties.
READONLY_METHODS = frozenset(
    {
        "GetItemFromID",
        "Item",
        "GetRootFolder",
        "GetDefaultFolder",
        "GetTable",
        "GetNextRow",
        "GetRowCount",
        "GetArray",
        "Add",
        "GetValues",
        "GetProperty",
        "SaveAsFile",
    }
)

#: Values returned unwrapped by scalar members (pywintypes datetimes are datetimes).
_SCALAR_TYPES = (
    str, bytes, bytearray, memoryview, bool, int, float, complex, datetime, date, dt_time,
    type(None),
)

# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #


class ComCallError(MailqueryError):
    """A COM failure the proxy does not map itself: ``E_INTERNAL`` with its HRESULT.

    The backend catches the expected ones (missing property, item not found,
    unavailable store) by ``hresult``; anything uncaught reaches the CLI as
    ``E_INTERNAL`` with a hint.
    """

    def __init__(self, hresult: int | None) -> None:
        self.hresult = hresult
        text = f"0x{hresult:08X}" if hresult is not None else "unknown"
        super().__init__(
            "E_INTERNAL",
            f"unexpected Outlook COM error (HRESULT {text})",
            HINT_INTERNAL,
        )


def dependency_missing() -> MailqueryError:
    return MailqueryError(
        "E_DEPENDENCY_MISSING",
        "pywin32 cannot be imported by the mailquery interpreter",
        HINT_DEPENDENCY,
    )


def client_unsupported(message: str) -> MailqueryError:
    return MailqueryError("E_CLIENT_UNSUPPORTED", message, HINT_UNSUPPORTED)


def outlook_not_running() -> MailqueryError:
    return MailqueryError(
        "E_OUTLOOK_NOT_RUNNING",
        "classic Outlook is not running (mailquery never launches it)",
        HINT_NOT_RUNNING,
    )


def client_busy() -> MailqueryError:
    return MailqueryError(
        "E_CLIENT_BUSY", "Outlook rejected the call because it is busy", HINT_BUSY
    )


def permission_denied() -> MailqueryError:
    return MailqueryError(
        "E_PERMISSION", "Outlook denied access to its object model", HINT_PERMISSION
    )


def client_timeout(seconds: float) -> MailqueryError:
    return MailqueryError(
        "E_CLIENT_TIMEOUT",
        f"Outlook did not respond within {seconds:g} s (possible security prompt)",
        HINT_TIMEOUT,
    )


def readonly_violation(kind: str, name: str, reason: str) -> MailqueryError:
    """``E_INTERNAL`` for a member the proxy refuses (raised before reaching COM)."""
    return MailqueryError(
        "E_INTERNAL",
        f"read-only proxy refused {kind}.{name}: {reason}",
        HINT_READONLY,
    )


def is_com_error(exc: BaseException) -> bool:
    """``pywintypes.com_error`` or the fake's ``com_error`` (duck typing by class name)."""
    return any(cls.__name__ == "com_error" for cls in type(exc).__mro__)


def hresult_of(exc: BaseException) -> int | None:
    """Unsigned HRESULT of a COM error; ``DISP_E_EXCEPTION`` is unwrapped to ``excepinfo[5]``.

    pywin32 reports HRESULTs as signed 32-bit ints with
    ``args == (hresult, strerror, excepinfo, argerror)``; the fake does the same.
    """
    value = getattr(exc, "hresult", None)
    if not isinstance(value, int) or isinstance(value, bool):
        args = getattr(exc, "args", ())
        value = (
            args[0] if args and isinstance(args[0], int) and not isinstance(args[0], bool) else None
        )
    if value is None:
        return None
    value &= 0xFFFFFFFF
    info = getattr(exc, "excepinfo", None)
    if info is None:
        args = getattr(exc, "args", ())
        info = args[2] if len(args) > 2 else None
    if (
        value == DISP_E_EXCEPTION
        and info
        and len(info) > 5
        and isinstance(info[5], int)
        and info[5]
    ):
        value = info[5] & 0xFFFFFFFF
    return value


def map_com_error(exc: BaseException) -> MailqueryError:
    """Final mapping of a COM error, after any retry."""
    code = hresult_of(exc)
    if code in TRANSIENT_HRESULTS:
        return client_busy()
    if code == E_ACCESSDENIED:
        return permission_denied()
    return ComCallError(code)


# --------------------------------------------------------------------------- #
# Watchdog
# --------------------------------------------------------------------------- #

ExpireHandler = Callable[["Watchdog", float], None]


class Watchdog:
    """One daemon thread bounding every COM call.

    The proxy arms a deadline of :data:`CALL_TIMEOUT_SECONDS` (or ``timeout``)
    when a COM call starts and disarms it when the call returns, so Python time
    between calls never counts. When a deadline expires, ``on_expire(self,
    seconds)`` runs in the watchdog thread; the default handler
    (:func:`default_on_expire`) ends the process.

    ``command`` is the running command (set by the backend's ``bind_command``);
    ``doctor_handler`` is the doctor-mode hook: when ``command`` is
    ``"doctor"`` and it is set, the default handler calls
    ``doctor_handler(seconds)`` instead, which must complete the report and end
    the process with exit 0 (``OutlookBackend.bind_doctor_timeout``).
    """

    def __init__(
        self, *, timeout: float | None = None, on_expire: ExpireHandler | None = None
    ) -> None:
        self._timeout = timeout
        self._on_expire = on_expire
        self._cond = threading.Condition()
        self._deadline: float | None = None
        self._armed_seconds = 0.0
        self._thread: threading.Thread | None = None
        self.command: str | None = None
        self.doctor_handler: Callable[[float], None] | None = None

    @property
    def seconds(self) -> float:
        """Deadline of the next call (read at arm time, so the module seam can be patched)."""
        return float(self._timeout if self._timeout is not None else CALL_TIMEOUT_SECONDS)

    @property
    def armed(self) -> bool:
        with self._cond:
            return self._deadline is not None

    @property
    def doctor_mode(self) -> bool:
        return self.command == "doctor"

    def arm(self) -> None:
        with self._cond:
            seconds = self.seconds
            self._armed_seconds = seconds
            self._deadline = time.monotonic() + seconds
            if self._thread is None:
                self._thread = threading.Thread(
                    target=self._run, name="mailquery-com-watchdog", daemon=True
                )
                self._thread.start()
            self._cond.notify_all()

    def disarm(self) -> None:
        with self._cond:
            self._deadline = None
            self._cond.notify_all()

    @contextmanager
    def guard(self) -> Iterator[None]:
        """Arm for the duration of one COM call."""
        self.arm()
        try:
            yield
        finally:
            self.disarm()

    def _run(self) -> None:
        while True:
            with self._cond:
                while True:
                    if self._deadline is None:
                        self._cond.wait()
                        continue
                    remaining = self._deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    self._cond.wait(remaining)
                self._deadline = None
                seconds = self._armed_seconds
            handler = self._on_expire or default_on_expire
            try:
                handler(self, seconds)
            except Exception:  # noqa: BLE001 - the watchdog thread must survive
                get_logger("mailquery.outlook").exception("event=watchdog_error")


def default_on_expire(watchdog: Watchdog, seconds: float) -> None:
    """Watchdog expiry outside ``doctor``: report ``E_CLIENT_TIMEOUT`` and ``os._exit(3)``.

    Writes the error JSON (stdout) and its summary (stderr) exactly as the CLI
    does, logs the error, flushes stdout, stderr and the log, and ends the
    process: the main thread is blocked inside COM and cannot be interrupted.
    """
    if watchdog.doctor_mode and watchdog.doctor_handler is not None:
        watchdog.doctor_handler(seconds)  # completes the doctor report, os._exit(0)
        return
    error = client_timeout(seconds)
    command = watchdog.command or "-"
    try:
        from mailquery import cli  # lazy: the CLI owns the error rendering

        try:
            cli._report_error(error, command)
        finally:
            cli._log_error(get_logger("mailquery.cli"), command, error)
    finally:
        _flush_everything()
        os._exit(error.exit_code)


def _flush_everything() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except Exception:  # noqa: BLE001 - best effort before os._exit
            pass
    for handler in logging.getLogger("mailquery").handlers:
        try:
            handler.flush()
        except Exception:  # noqa: BLE001
            pass


#: The process-wide watchdog (a single daemon thread).
WATCHDOG = Watchdog()


def call_com(watchdog: Watchdog, call: Callable[[], Any]) -> Any:
    """Run one COM call under the watchdog with the retry and the COM error mapping."""
    retried = False
    while True:
        try:
            with watchdog.guard():
                return call()
        except Exception as exc:
            if not is_com_error(exc):
                raise
            if hresult_of(exc) in TRANSIENT_HRESULTS and not retried:
                retried = True
                time.sleep(RETRY_DELAY_SECONDS)
                continue
            raise map_com_error(exc) from exc


# --------------------------------------------------------------------------- #
# Read-only proxy
# --------------------------------------------------------------------------- #


class ReadOnlyCom:
    """Read-only proxy over one Outlook COM object of a given whitelist ``kind``.

    Only the members of ``READONLY_MEMBERS[kind]`` pass, with exact case.
    Properties are read when accessed and methods when called, each one under
    the watchdog and the retry policy; the returned COM objects are proxies
    too. Everything else, every assignment or deletion and every private or
    dunder name raises ``E_INTERNAL`` before the COM object is touched. The only
    name answered by the proxy itself is ``__class__`` (the proxy class), so that
    ``isinstance`` checks keep working. A pywin32 object is called through its
    ``IDispatch`` directly (:func:`_direct_member`); any other target (the
    in-memory fake) through ``getattr``. The whitelist check is the same.
    """

    __slots__ = ("_mq_target", "_mq_kind", "_mq_watchdog", "_mq_dispatch", "_mq_dispids")

    def __init__(self, target: Any, kind: str, watchdog: Watchdog) -> None:
        object.__setattr__(self, "_mq_target", target)
        object.__setattr__(self, "_mq_kind", kind)
        object.__setattr__(self, "_mq_watchdog", watchdog)
        dispatch = _raw_dispatch(target)
        object.__setattr__(self, "_mq_dispatch", dispatch)
        per_object = dispatch is not None and kind in PER_OBJECT_DISPID_KINDS
        object.__setattr__(self, "_mq_dispids", {} if per_object else _KIND_DISPIDS)

    def __getattribute__(self, name: str) -> Any:
        if name == "__class__":
            return ReadOnlyCom
        kind = object.__getattribute__(self, "_mq_kind")
        if name.startswith("_"):
            raise readonly_violation(kind, name, "private and special names are not allowed")
        members = READONLY_MEMBERS.get(kind, {})
        if name not in members:
            raise readonly_violation(kind, name, "not in the read-only whitelist")
        target = object.__getattribute__(self, "_mq_target")
        watchdog = object.__getattribute__(self, "_mq_watchdog")
        dispatch = object.__getattribute__(self, "_mq_dispatch")
        result_kind = members[name]
        if dispatch is not None:
            return _direct_member(
                dispatch, kind, name, object.__getattribute__(self, "_mq_dispids"),
                result_kind, watchdog,
            )
        if name in READONLY_METHODS:

            def method(*args: Any, **kwargs: Any) -> Any:
                value = call_com(watchdog, lambda: getattr(target, name)(*args, **kwargs))
                return _wrap(value, result_kind, watchdog)

            return method
        value = call_com(watchdog, lambda: getattr(target, name))
        return _wrap(value, result_kind, watchdog)

    def __setattr__(self, name: str, value: Any) -> None:
        raise readonly_violation(object.__getattribute__(self, "_mq_kind"), name, "assignment")

    def __delattr__(self, name: str) -> None:
        raise readonly_violation(object.__getattribute__(self, "_mq_kind"), name, "deletion")

    def __repr__(self) -> str:
        return f"<ReadOnlyCom {object.__getattribute__(self, '_mq_kind')}>"


#: DISPID of each ``(kind, member)`` already looked up (one COM class per kind,
#: except :data:`PER_OBJECT_DISPID_KINDS`). Process-wide: DISPIDs are fixed by the
#: Outlook type library.
_KIND_DISPIDS: dict[Any, int] = {}


def _raw_dispatch(target: Any) -> Any:
    """The ``PyIDispatch`` behind a pywin32 object, or ``None`` (the in-memory fake).

    pywin32's dynamic ``CDispatch`` fetches type information for every new object
    and looks names up through it: several cross-process round trips per
    member. The proxy calls ``IDispatch::Invoke`` directly instead (one round
    trip), with the DISPID looked up once (verified on the host).
    """
    if type(target).__name__ == "PyIDispatch":
        return target
    inner = getattr(target, "_oleobj_", None)
    return inner if type(inner).__name__ == "PyIDispatch" else None


def _direct_member(
    dispatch: Any,
    kind: str,
    name: str,
    dispids: dict[Any, int],
    result_kind: str | None,
    watchdog: Watchdog,
) -> Any:
    """A whitelisted member through ``IDispatch::Invoke`` (property GET or method call).

    An unknown name (``DISP_E_UNKNOWNNAME``) is ``AttributeError``, as pywin32's
    dynamic dispatch reports it (e.g. ``HTMLBody`` of a MeetingItem).
    """
    key = name if dispids is not _KIND_DISPIDS else (kind, name)

    def dispid() -> int:
        found = dispids.get(key)
        if found is None:
            try:
                found = dispatch.GetIDsOfNames(name)
            except Exception as exc:
                if is_com_error(exc) and hresult_of(exc) == DISP_E_UNKNOWNNAME:
                    raise AttributeError(f"{kind}.{name}") from None
                raise
            dispids[key] = found
        return found

    if name in READONLY_METHODS:

        def method(*args: Any) -> Any:
            value = call_com(
                watchdog,
                lambda: dispatch.Invoke(
                    dispid(), 0, DISPATCH_METHOD | DISPATCH_PROPERTYGET, True, *args
                ),
            )
            return _wrap(value, result_kind, watchdog)

        return method
    value = call_com(
        watchdog, lambda: dispatch.Invoke(dispid(), 0, DISPATCH_PROPERTYGET, True)
    )
    return _wrap(value, result_kind, watchdog)


def _wrap(value: Any, kind: str | None, watchdog: Watchdog) -> Any:
    """Proxy a returned COM object; scalars (and tuples of scalars) pass as they are."""
    if kind is not None:
        return None if value is None else ReadOnlyCom(value, kind, watchdog)
    if isinstance(value, (tuple, list)):
        return type(value)(_wrap(item, None, watchdog) for item in value)
    if isinstance(value, _SCALAR_TYPES):
        return value
    # An unexpected object from a scalar member: proxied with no member allowed.
    return ReadOnlyCom(value, "Opaque", watchdog)


# --------------------------------------------------------------------------- #
# Detection and connection
# --------------------------------------------------------------------------- #


def import_pywin32(gen_path: Path) -> Any:
    """Import pywin32 with its cache confined to ``gen_path``; return ``win32com.client``.

    ``win32com.__gen_path__`` (and the ``win32com.gen_py`` package path) are set
    before ``win32com.client`` is imported, so the generated-code cache never
    goes to ``%TEMP%``. Dispatch stays dynamic. Any import
    failure is ``E_DEPENDENCY_MISSING``.
    """
    try:
        import win32com
    except ImportError as exc:
        raise dependency_missing() from exc
    target = Path(gen_path)
    target.mkdir(parents=True, exist_ok=True)
    win32com.__gen_path__ = str(target)
    gen_py = sys.modules.get("win32com.gen_py")
    if gen_py is not None and hasattr(gen_py, "__path__"):
        gen_py.__path__ = [str(target)]
    try:
        import pythoncom  # noqa: F401 - initialises COM for this thread
        import pywintypes  # noqa: F401
        import win32com.client
    except ImportError as exc:
        raise dependency_missing() from exc
    return win32com.client


class WinRegistry:
    """Read-only registry access with ``winreg`` (``get_value`` like the fake)."""

    def get_value(self, hive: str, key: str, name: str = "") -> Any:
        try:
            import winreg
        except ImportError as exc:  # not Windows
            raise FileNotFoundError(2, "no Windows registry") from exc
        roots = {
            HKCR: winreg.HKEY_CLASSES_ROOT,
            HKCU: winreg.HKEY_CURRENT_USER,
            HKLM: winreg.HKEY_LOCAL_MACHINE,
        }
        with winreg.OpenKey(roots[hive.upper()], key, 0, winreg.KEY_READ) as handle:
            value, _kind = winreg.QueryValueEx(handle, name)
        return value


def pywin32_gen_path() -> str | None:
    """``win32com.__gen_path__`` if pywin32 is already imported (never imports it)."""
    module = sys.modules.get("win32com")
    value = getattr(module, "__gen_path__", None) if module is not None else None
    return str(value) if value is not None else None


def _policy_dword(registry: Any, name: str) -> int | None:
    try:
        value = registry.get_value(HKCU, OOM_POLICY_KEY, name)
    except OSError:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def oom_policy(registry: Any) -> tuple[str, int] | None:
    """The Outlook security policy that decides programmatic access, or ``None``.

    Read-only. Only with ``AdminSecurityMode = 3`` do the ``PromptOOM*`` values
    apply. ``PromptOOMAddressInformationAccess`` covers what mailquery reads
    (addresses, recipients, bodies, MAPI properties): deny (0) or prompt (1)
    decide, then a deny of ``PromptOOMAddressBookAccess`` (Outlook then denies
    every program), then approve (2). Missing values and 3 ("prompt based on
    computer security") decide nothing.
    """
    if _policy_dword(registry, ADMIN_SECURITY_MODE) != ADMIN_SECURITY_MODE_GROUP_POLICY:
        return None
    information = _policy_dword(registry, PROMPT_OOM_ADDRESS_INFORMATION)
    if information in (OOM_DENY, OOM_PROMPT):
        return PROMPT_OOM_ADDRESS_INFORMATION, int(information)
    if _policy_dword(registry, PROMPT_OOM_ADDRESS_BOOK) == OOM_DENY:
        return PROMPT_OOM_ADDRESS_BOOK, OOM_DENY
    if information == OOM_APPROVE:
        return PROMPT_OOM_ADDRESS_INFORMATION, OOM_APPROVE
    return None


def active_antivirus(products: list[dict[str, Any]]) -> list[str]:
    """Display names of the SecurityCenter2 antivirus products whose protection is on."""
    names = []
    for product in products:
        try:
            state = int(product.get("productState", 0))
        except (TypeError, ValueError):
            continue
        if state & ANTIVIRUS_ENABLED_BIT:
            names.append(str(product.get("displayName") or "unknown"))
    return names


def outlook_major_version(registry: Any) -> int | None:
    """Major version from ``HKCR\\Outlook.Application\\CurVer`` (``None`` if not registered)."""
    try:
        value = registry.get_value(HKCR, CURVER_KEY, "")
    except OSError:
        return None
    if not isinstance(value, str):
        return None
    try:
        return int(value.rsplit(".", 1)[-1])
    except ValueError:
        return None


def check_registration(registry: Any) -> int:
    """Second detection step: registered and >= 16.0, else ``E_CLIENT_UNSUPPORTED``."""
    major = outlook_major_version(registry)
    if major is None:
        raise client_unsupported("classic Outlook is not registered in COM")
    if major < MIN_MAJOR_VERSION:
        raise client_unsupported(
            f"classic Outlook {major}.0 is not supported (16.0 or later is required)"
        )
    return major


def connect(
    *,
    outlook_app: Any = None,
    registry: Any = None,
    pywin32: bool | None = None,
    gen_path: Path | None = None,
    watchdog: Watchdog | None = None,
) -> ReadOnlyCom:
    """Detect classic Outlook and return the read-only Application proxy.

    ``outlook_app`` is the connector (``GetActiveObject(prog_id)``); without it,
    pywin32's ``win32com.client`` is imported (cache in ``gen_path``) and used.
    ``pywin32`` fixes the result of the pywin32 check (default: ``True`` with an
    injected connector, else the real import). Never ``Dispatch``/``DispatchEx``
    or ``EnsureDispatch``: Outlook is never launched.
    """
    guard = watchdog if watchdog is not None else WATCHDOG
    if pywin32 is False:
        raise dependency_missing()
    connector = outlook_app
    if connector is None:
        if gen_path is None:
            from mailquery.config import app_home

            gen_path = app_home() / "tmp" / "gen_py"
        connector = import_pywin32(gen_path)
    check_registration(registry if registry is not None else WinRegistry())
    try:
        application = call_com(guard, lambda: connector.GetActiveObject(PROG_ID))
    except ComCallError as exc:
        if exc.hresult == MK_E_UNAVAILABLE:
            raise outlook_not_running() from exc
        if exc.hresult == CO_E_CLASSSTRING:
            raise client_unsupported("classic Outlook is not registered in COM") from exc
        raise
    if application is None:
        raise outlook_not_running()
    return ReadOnlyCom(application, "Application", guard)


# --------------------------------------------------------------------------- #
# Read-only helpers outside the OOM
# --------------------------------------------------------------------------- #


def get_drive_type(root: str) -> int:
    """``GetDriveTypeW`` of a drive root such as ``"Z:\\\\"`` (``DRIVE_REMOTE`` = 4).

    Used to detect network PSTs; a removable disk is local. Outside
    Windows it returns ``DRIVE_UNKNOWN``.
    """
    import ctypes

    windll = getattr(ctypes, "windll", None)
    if windll is None:
        return DRIVE_UNKNOWN
    return int(windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(str(root))))


class WmiSecurityCenter:
    """Read-only WMI query of ``root\\SecurityCenter2`` ``AntiVirusProduct``.

    Same interface as the injected ``security_center`` of the tests:
    :meth:`antivirus_products` returns ``[{"displayName", "productState"}]`` and
    raises ``OSError`` when SecurityCenter2 cannot be queried (e.g. on Windows
    Server). It does not go through the OOM whitelist: it never talks to Outlook.
    """

    MONIKER = "winmgmts:{impersonationLevel=impersonate}!\\\\.\\root\\SecurityCenter2"
    QUERY = "SELECT displayName, productState FROM AntiVirusProduct"

    def __init__(self, gen_path: Path) -> None:
        self._gen_path = Path(gen_path)

    def antivirus_products(self) -> list[dict[str, Any]]:
        try:
            client = import_pywin32(self._gen_path)
            service = client.GetObject(self.MONIKER)
            products = []
            for product in service.ExecQuery(self.QUERY):
                products.append(
                    {
                        "displayName": str(product.displayName),
                        "productState": int(product.productState),
                    }
                )
            return products
        except MailqueryError as exc:
            raise OSError(f"SecurityCenter2 unavailable: {exc.message}") from exc
        except Exception as exc:  # noqa: BLE001 - any COM/WMI failure means "unavailable"
            raise OSError(f"SecurityCenter2 unavailable: {type(exc).__name__}") from exc

"""Error hierarchy and stable exit codes for mailquery.

Every user-facing failure is represented by a :class:`MailqueryError` carrying
a stable ``E_*`` code (the contract consumed by the agent harness), a human
message and an actionable hint. The CLI maps each error to its exit code
and renders it as a JSON object on ``stdout``.
"""

from __future__ import annotations

from typing import Final

# Exit code -> error codes. Exit 0 means success.
_EXIT_ERRORS: Final[dict[int, tuple[str, ...]]] = {
    1: ("E_INTERNAL",),
    2: (
        "E_USAGE",
        "E_CONFIG_INVALID",
        "E_CONFIG_ACCOUNT_UNKNOWN",
        "E_ACCOUNT_AMBIGUOUS",
        "E_ACCOUNT_LABELS_UNAVAILABLE",
        "E_ACCOUNT_NOT_IN_SCOPE",
        "E_MAILBOX_NOT_FOUND",
        "E_BAD_TIME",
        "E_BAD_FILTER",
        "E_DRIVER_UNKNOWN",
        "E_ATTACHMENTS_DISABLED",
    ),
    3: (
        "E_STORE_NOT_FOUND",
        "E_SCHEMA_UNSUPPORTED",
        "E_PERMISSION",
        "E_STATE_CORRUPT",
        "E_CLIENT_UNSUPPORTED",
        "E_DEPENDENCY_MISSING",
        "E_CLIENT_TIMEOUT",
        "E_PLUGIN_INCOMPATIBLE",
        "E_PLUGIN_FAILED",
        "E_ATTACHMENT_UNAVAILABLE",
        "E_ATTACHMENT_UNREADABLE",
        "E_IO",
    ),
    4: (
        "E_UNBOUNDED_SCAN",
        "E_SCAN_TOO_LARGE",
        "E_ATTACHMENT_BLOCKED",
        "E_ATTACHMENT_TOO_LARGE",
    ),
    5: ("E_LOCKED", "E_DB_BUSY", "E_CLIENT_BUSY"),
    6: ("E_OUTLOOK_NOT_RUNNING",),
}

CODE_EXIT: Final[dict[str, int]] = {
    code: exit_code for exit_code, codes in _EXIT_ERRORS.items() for code in codes
}


def exit_code_for(code: str) -> int:
    """Return the documented exit code for an ``E_*`` code.

    Unknown codes are internal errors (exit 1).
    """
    return CODE_EXIT.get(code, 1)


class MailqueryError(Exception):
    """A documented, user-facing mailquery failure.

    ``code`` is the stable machine-readable identifier, ``message`` the short
    explanation and ``hint`` an actionable suggestion shown to the harness.
    ``log_message`` is the same text without the data that must not reach the log
    (paths, folders, accounts, terms, uids...); the log writes it when present
    and ``message`` otherwise.
    """

    def __init__(
        self,
        code: str,
        message: str,
        hint: str = "",
        log_message: str | None = None,
    ) -> None:
        self.code = code if code in CODE_EXIT else "E_INTERNAL"
        self.message = message
        self.hint = hint
        self.log_message = log_message
        super().__init__(message)

    @property
    def exit_code(self) -> int:
        return CODE_EXIT[self.code]

    def __str__(self) -> str:  # pragma: no cover - trivial formatting
        if self.hint:
            return f"{self.code}: {self.message} (hint: {self.hint})"
        return f"{self.code}: {self.message}"

    def to_payload(self, command: str) -> dict:
        """Render this error as the JSON error contract."""
        return {
            "ok": False,
            "command": command,
            "error": {
                "code": self.code,
                "message": self.message,
                "hint": self.hint,
            },
        }


def usage_error(message: str, hint: str = "", log_message: str | None = None) -> MailqueryError:
    return MailqueryError("E_USAGE", message, hint, log_message)


def config_error(message: str, hint: str = "", log_message: str | None = None) -> MailqueryError:
    return MailqueryError("E_CONFIG_INVALID", message, hint, log_message)


def bad_time(value: str) -> MailqueryError:
    return MailqueryError(
        "E_BAD_TIME",
        f"invalid time value: {value!r}",
        "use ISO 8601 (2026-11-01) or a relative value: 30min, 24h, 7d, 2w, "
        "1mo, 6mo, 1y, today, yesterday, now",
    )


def bad_filter(message: str, hint: str = "") -> MailqueryError:
    return MailqueryError("E_BAD_FILTER", message, hint)


def error_detail(exc: Exception) -> str:
    """One-line ``doctor`` detail for an exception: ``CODE: message`` or ``Type: text``."""
    if isinstance(exc, MailqueryError):
        return f"{exc.code}: {exc.message}"
    text = str(exc).strip()
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__

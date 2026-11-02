"""Error hierarchy and stable exit codes for mailquery.

Every user-facing failure is represented by a :class:`MailqueryError` carrying
a stable ``E_*`` code (the contract consumed by the agent harness), a human
message and an actionable hint. The CLI maps each error to its exit code
(PRD section 12.6) and renders it as a JSON object on ``stdout``.
"""

from __future__ import annotations

from typing import Final

# Exit code -> error codes (PRD 12.6). Exit code 0 means success and has no code.
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
    ),
    3: ("E_STORE_NOT_FOUND", "E_SCHEMA_UNSUPPORTED", "E_PERMISSION", "E_STATE_CORRUPT"),
    4: ("E_UNBOUNDED_SCAN", "E_SCAN_TOO_LARGE"),
    5: ("E_LOCKED", "E_DB_BUSY"),
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
    """

    def __init__(self, code: str, message: str, hint: str = "") -> None:
        self.code = code if code in CODE_EXIT else "E_INTERNAL"
        self.message = message
        self.hint = hint
        super().__init__(message)

    @property
    def exit_code(self) -> int:
        return CODE_EXIT[self.code]

    def __str__(self) -> str:  # pragma: no cover - trivial formatting
        if self.hint:
            return f"{self.code}: {self.message} (hint: {self.hint})"
        return f"{self.code}: {self.message}"

    def to_payload(self, command: str) -> dict:
        """Render this error as the JSON error contract (PRD 12.5)."""
        return {
            "ok": False,
            "command": command,
            "error": {
                "code": self.code,
                "message": self.message,
                "hint": self.hint,
            },
        }


def usage_error(message: str, hint: str = "") -> MailqueryError:
    return MailqueryError("E_USAGE", message, hint)


def config_error(message: str, hint: str = "") -> MailqueryError:
    return MailqueryError("E_CONFIG_INVALID", message, hint)


def bad_time(value: str) -> MailqueryError:
    return MailqueryError(
        "E_BAD_TIME",
        f"invalid time value: {value!r}",
        "use ISO 8601 (2026-11-01) or a relative value: 30min, 24h, 7d, 2w, "
        "1mo, 6mo, 1y, today, yesterday, now",
    )


def bad_filter(message: str, hint: str = "") -> MailqueryError:
    return MailqueryError("E_BAD_FILTER", message, hint)

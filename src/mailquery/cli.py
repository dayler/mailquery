"""Command line interface: argument parsing, dispatch, JSON contract, exit codes.

Only this module writes to ``stdout``/``stderr``. It parses ``argv`` with
``argparse`` (``-h``/``--help`` is the documented non-JSON exception), loads
the configuration, sets up logging, takes the run lock, dispatches one of the
five commands and renders either success or a JSON error object (PRD 12).
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import logging
import os
import platform
import shutil
import stat
import sys
import textwrap
import time
from pathlib import Path
from typing import Any, Sequence

from mailquery import __version__
from mailquery.accounts import AccountLabels
from mailquery.config import (
    APP_HOME_SUBDIRS,
    DEFAULT_LOG_LEVEL,
    DEFAULT_LOOKBACK,
    DEFAULT_MAX_SIZE_MB,
    LOG_LEVELS,
    MAX_NEW_LIMIT,
    MAX_SEARCH_LIMIT,
    Config,
    app_home,
    ensure_app_home,
    load_config,
    resolve_scope,
)
from mailquery.errors import MailqueryError
from mailquery.logging_setup import get_logger, setup_logging
from mailquery.output import configure_streams, now_iso, write_json
from mailquery.search import (
    Filters,
    parse_relative_time,
    parse_uid,
    run_mailboxes,
    run_new,
    run_search,
    run_show,
)
from mailquery.state import RunLock, StateStore
from mailquery.store import detect_version, open_store, probe_envelope_index

COMMANDS = ("doctor", "mailboxes", "search", "new", "show")
# The only backend implemented at W0 (RF-26); logged as ``backend=`` (PRD 14).
BACKEND_NAME = "apple_mail"
DOCTOR_CHECK_NAMES = (
    "python",
    "home",
    "store",
    "envelope_index",
    "schema",
    "readonly_strategy",
    "accounts_db",
    "config",
    "state",
    "lock",
)

_LOCK_FILENAME = "mailquery.lock"
_PAYLOAD_RESERVED_KEYS = ("ok", "command", "generated_at")

_ROOT_EPILOG = """\
Examples:
  mailquery doctor                     environment and read-only preflight
  mailquery mailboxes                  accounts, folders and included flags
  mailquery search --since 1w --unread
  mailquery search --text "*factura*" --since 1mo
  mailquery new --peek
  mailquery show 83143

Configuration: ~/.mailquery/config.toml (optional; see README.md)
Output: one JSON object on stdout for every command, in UTF-8 (this help,
        --version and the default doctor report are the only non-JSON output);
        logs go to ~/.mailquery/logs/mailquery.log
Exit codes: 0 ok | 2 usage or config error | 3 environment error
            | 4 rejected query | 5 busy or transient error | 6 mail client not running
"""

_DOCTOR_EPILOG = """\
Examples:
  mailquery doctor
  mailquery doctor --json
  mailquery --log-level debug doctor

Notes:
  Prints a human-readable report by default; --json emits the machine-readable
  payload. Always exits 0 when the diagnosis can run; failures are reported as
  checks with ok = false, plus a Result line with the failed count.
"""

_MAILBOXES_EPILOG = """\
Examples:
  mailquery mailboxes

Notes:
  A folder is included when its account is declared in ~/.mailquery/config.toml
  and the folder is INBOX or listed in mailbox_list. Counters are recalculated
  from the mail store because the mail client's own counters are not reliable.
"""

_SEARCH_EPILOG = """\
Matching:
  Patterns are case- and accent-insensitive; * matches any sequence and ? one
  character; without wildcards the value is matched as a substring anywhere in
  the text. A pattern is not anchored: factura* also matches "la factura".
  --subject: words separated by spaces are AND terms, with or without wildcards.
  --text, --from, --to and --cc: the whole value is one pattern, spaces included.
  Repeating a flag is AND too. An empty value does not filter.

Examples:
  mailquery search --since 1w
  mailquery search --since 2w --unread
  mailquery search --from "*@bank.com*" --since 2mo
  mailquery search --text "*factura*" --since 1mo --has-attachments

Notes:
  --text needs a narrowing filter: --since, --until, --subject, --from or an extra
  folder (one other than INBOX in mailbox_list or --include-mailbox). --to and --cc
  narrow on macOS but not on Windows, where checking them opens every message (they
  are validated like --text). An empty value does not narrow. Without a narrowing
  filter the query fails with E_UNBOUNDED_SCAN (exit 4); with more than
  [search].max_scan candidates after the filters, with E_SCAN_TOO_LARGE (exit 4).
  --include-mailbox takes folders of declared accounts; INBOX is the inbox of the
  first declared account.
"""

_NEW_EPILOG = """\
Examples:
  mailquery new
  mailquery new --peek
  mailquery new --limit 200

Notes:
  The first run (no saved cursor) emits, oldest first, the messages received in the
  last [new].lookback before the newest message of the scope (at least that one) and
  adds W_FIRST_RUN; with a smaller --limit, the most recent ones. Later runs emit what
  arrived after the cursor. --peek never writes the state.
  Messages with a null, invalid or future date are ignored until their date is valid.
  Accounts or folders added to config.toml do not emit their history: use search.
"""

_SHOW_EPILOG = """\
Examples:
  mailquery show 83143

Notes:
  The body is truncated to 20,000 characters; headers and attachment names are
  included. Only messages of accounts declared in config.toml can be shown; use
  the uid reported by search or new.
"""


class _HelpFormatter(argparse.RawDescriptionHelpFormatter):
    """Readable, width-aware help that preserves description/epilog lines."""

    def __init__(self, prog: str) -> None:
        super().__init__(prog, width=_help_width(), max_help_position=30)

    def _format_action(self, action: argparse.Action) -> str:
        # Do not render the bare "<command>" placeholder line for the subparsers
        # action: the "Commands:" section lists the real commands only.
        if isinstance(action, argparse._SubParsersAction):
            return "".join(self._format_action(sub) for sub in action._get_subactions())
        return super()._format_action(action)


def _help_width() -> int:
    """Return a stable help width between 80 and 100 columns."""
    try:
        columns = shutil.get_terminal_size(fallback=(100, 24)).columns
    except OSError:  # pragma: no cover - exotic environments
        columns = 100
    return max(80, min(columns, 100))


def _style_parser(parser: argparse.ArgumentParser, *, root: bool) -> None:
    """Give argparse groups human-friendly titles."""
    parser._optionals.title = "Global options" if root else "Options"  # noqa: SLF001
    parser._positionals.title = "Commands" if root else "Arguments"  # noqa: SLF001


class _ArgumentParser(argparse.ArgumentParser):
    """Parser that turns usage failures into the JSON error contract.

    ``-h``/``--help`` prints the formatted plain-text help (exit code 0); any
    other usage failure raises :class:`MailqueryError` with ``E_USAGE``
    (exit 2).
    """

    def error(self, message: str) -> None:  # type: ignore[override]
        raise MailqueryError(
            "E_USAGE",
            f"invalid command line: {message}",
            'run "mailquery --help" to see the available commands and options',
        )


def _version_line() -> str:
    """Return the ``--version`` line (RF-31, PRD 12.9) without touching any backend."""
    if sys.platform == "win32":
        backend = "outlook"
        system = f"Windows {platform.version()} {platform.machine()}"
    elif sys.platform == "darwin":
        backend = "apple_mail"
        system = f"macOS {platform.mac_ver()[0]} {platform.machine()}"
    else:
        backend = "apple_mail"
        system = f"{platform.system()} {platform.release()} {platform.machine()}"
    return (
        f"mailquery {__version__} (backend {backend}; "
        f"Python {platform.python_version()}; {system})"
    )


class _VersionAction(argparse.Action):
    """Print the version line and exit 0 as soon as the option is parsed."""

    def __init__(self, option_strings: Sequence[str], dest: str, **kwargs: Any) -> None:
        super().__init__(option_strings, dest, nargs=0, default=argparse.SUPPRESS, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None) -> None:  # type: ignore[override]
        sys.stdout.write(_version_line() + "\n")
        sys.stdout.flush()
        parser.exit(0)


def build_parser() -> argparse.ArgumentParser:
    """Build the ``mailquery`` argparse parser with all subcommands."""
    parser = _ArgumentParser(
        prog="mailquery",
        description="Read-only CLI to read and search local mail "
        "(Apple Mail on macOS, classic Outlook on Windows).",
        epilog=_ROOT_EPILOG,
        formatter_class=_HelpFormatter,
        allow_abbrev=False,
    )
    _style_parser(parser, root=True)
    parser.add_argument(
        "-v",
        "--version",
        action=_VersionAction,
        help="print the version, backend, Python and platform, then exit",
    )
    parser.add_argument(
        "--log-level",
        metavar="LEVEL",
        choices=LOG_LEVELS,
        default=None,
        help="minimum log level: error, warning, info or debug "
        "(overrides [logging].level; default: info)",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        metavar="<command>",
        required=True,
    )

    diagnosis = subparsers.add_parser(
        "doctor",
        help="diagnose the environment and verify the read-only guarantee",
        description="Diagnose the environment and verify the read-only guarantee.",
        epilog=_DOCTOR_EPILOG,
        formatter_class=_HelpFormatter,
    )
    diagnosis.set_defaults(command="doctor")
    _style_parser(diagnosis, root=False)
    diagnosis.add_argument(
        "--json",
        action="store_true",
        help="print the machine-readable JSON payload instead of the human report",
    )

    mailboxes_parser = subparsers.add_parser(
        "mailboxes",
        help="list accounts, folders, counters and included folders",
        description="List accounts, folders, counters and whether they are included "
        "in the configured scope.",
        epilog=_MAILBOXES_EPILOG,
        formatter_class=_HelpFormatter,
    )
    mailboxes_parser.set_defaults(command="mailboxes")
    _style_parser(mailboxes_parser, root=False)

    search_parser = subparsers.add_parser(
        "search",
        help="search messages by subject, body, sender, date or state",
        description="Search messages by subject, body, sender, recipient, date or state.",
        epilog=_SEARCH_EPILOG,
        formatter_class=_HelpFormatter,
    )
    search_parser.set_defaults(command="search")
    _style_parser(search_parser, root=False)
    search_parser.add_argument(
        "--subject",
        action="append",
        metavar="PATTERN",
        help="subject filter: substring or wildcards * and ?; words separated by spaces "
        "are AND; repeatable (AND)",
    )
    search_parser.add_argument(
        "--text",
        action="append",
        metavar="PATTERN",
        help="body text filter: substring or wildcards; the whole value is one pattern; "
        "repeatable (AND)",
    )
    search_parser.add_argument(
        "--from",
        dest="from_",
        action="append",
        metavar="PATTERN",
        help="sender name or address filter: substring or wildcards; the whole value is "
        "one pattern; repeatable (AND)",
    )
    search_parser.add_argument(
        "--to",
        action="append",
        metavar="PATTERN",
        help="recipient name or address filter: substring or wildcards; the whole value "
        "is one pattern; repeatable (AND)",
    )
    search_parser.add_argument(
        "--cc",
        action="append",
        metavar="PATTERN",
        help="cc name or address filter: substring or wildcards; the whole value is "
        "one pattern; repeatable (AND)",
    )
    search_parser.add_argument(
        "--since",
        metavar="TIME",
        help="received at or after TIME (inclusive): ISO 8601, 7d, 2w, 1mo, today...",
    )
    search_parser.add_argument(
        "--until",
        metavar="TIME",
        help="received before TIME (exclusive): ISO 8601, 7d, 2w, 1mo, today...",
    )
    search_parser.add_argument("--unread", action="store_true", help="only unread messages")
    search_parser.add_argument("--flagged", action="store_true", help="only flagged messages")
    search_parser.add_argument(
        "--has-attachments",
        action="store_true",
        help="only messages that have attachments",
    )
    search_parser.add_argument(
        "--include-mailbox",
        action="append",
        metavar="LIST",
        help="extra folder of a declared account for this run (name, path or URL; "
        "INBOX is an alias); repeatable or comma-separated",
    )
    search_parser.add_argument(
        "--limit",
        type=int,
        metavar="N",
        help=f"maximum number of results (default: [search].default_limit; max {MAX_SEARCH_LIMIT})",
    )

    new_parser = subparsers.add_parser(
        "new",
        help="messages received since the last run (cursor)",
        description="List messages received since the last run, using the stored cursor.",
        epilog=_NEW_EPILOG,
        formatter_class=_HelpFormatter,
    )
    new_parser.set_defaults(command="new")
    _style_parser(new_parser, root=False)
    new_parser.add_argument(
        "--peek",
        action="store_true",
        help="return the new messages without advancing the cursor",
    )
    new_parser.add_argument(
        "--limit",
        type=int,
        metavar="N",
        help=f"maximum number of messages in this run "
        f"(default: [new].default_limit; max {MAX_NEW_LIMIT})",
    )

    show_parser = subparsers.add_parser(
        "show",
        help="show one message by uid",
        description="Show the full detail of one message by uid.",
        epilog=_SHOW_EPILOG,
        formatter_class=_HelpFormatter,
    )
    show_parser.set_defaults(command="show")
    _style_parser(show_parser, root=False)
    # The format is validated by search.parse_uid in main(), not by argparse (PRD 12.4).
    show_parser.add_argument("uid", metavar="UID", help="message uid (see `mailquery search`)")

    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    home: Path | None = None,
    mail_root: Path | None = None,
    accounts_db: Path | None = None,
) -> int:
    """Run one command and return the process exit code (never raises).

    ``home``, ``mail_root`` and ``accounts_db`` are test-only injection points;
    they are not CLI flags nor environment variables of the public contract.
    """
    configure_streams()
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    try:
        args = build_parser().parse_args(raw_argv)
    except SystemExit as exc:  # --help / argparse exits
        return _system_exit_code(exc)
    except MailqueryError as exc:
        return _report_error(exc, _guess_command(raw_argv))

    command = str(args.command)
    if command == "show":
        # Before the home is created, the config is read or the store is opened.
        try:
            args.uid = parse_uid(args.uid)
        except MailqueryError as exc:
            return _report_error(exc, command)
    try:
        home_path = Path(home) if home is not None else app_home()
    except (OSError, RuntimeError) as exc:
        error = MailqueryError(
            "E_PERMISSION",
            f"cannot resolve the application home: {exc}",
            "make sure HOME points to a writable directory",
            log_message="cannot resolve the application home",
        )
        return _report_error(error, command)

    if command == "doctor":
        return _run_doctor(
            home_path,
            mail_root,
            accounts_db,
            args.log_level,
            json_output=bool(getattr(args, "json", False)),
        )
    return _run_command(args, home_path, mail_root, accounts_db)


# --------------------------------------------------------------------------- #
# Successful command execution
# --------------------------------------------------------------------------- #


def _run_command(
    args: argparse.Namespace,
    home_path: Path,
    mail_root: Path | None,
    accounts_db: Path | None,
) -> int:
    command = str(args.command)
    try:
        ensure_app_home(home_path)
    except OSError as exc:
        error = MailqueryError(
            "E_PERMISSION",
            f"cannot create the application home {home_path}: {exc.strerror or exc}",
            "check write permissions on the home directory and its parent "
            "(mode 0700 is required)",
            log_message="cannot create the application home",
        )
        return _report_error(error, command)

    try:
        config = load_config(home_path)
    except MailqueryError as exc:
        _log_error(_best_effort_logger(home_path, args.log_level), command, exc)
        return _report_error(exc, command)

    level = args.log_level or config.logging.level
    try:
        _close_logging_handlers()
        setup_logging(home_path, level, config.logging.max_size_mb)
    except OSError as exc:
        error = MailqueryError(
            "E_PERMISSION",
            f"cannot write logs under {home_path}: {exc.strerror or exc}",
            "check permissions of the application home and its logs directory",
            log_message="cannot write logs under the application home",
        )
        return _report_error(error, command)

    logger = get_logger("mailquery.cli")
    logger.info("event=start command=%s backend=%s", command, BACKEND_NAME)
    started = time.perf_counter()
    try:
        payload = _execute(args, config, home_path, mail_root, accounts_db)
        if not isinstance(payload, dict):
            raise MailqueryError(
                "E_INTERNAL",
                "the command returned an invalid payload",
                "run `mailquery doctor` and check the technical log",
            )
        payload = _with_count(payload)
    except MailqueryError as exc:
        _log_error(logger, command, exc)
        return _report_error(exc, command)
    except Exception as exc:  # noqa: BLE001 - the CLI must never raise
        logger.exception("event=internal_error command=%s", command)
        error = MailqueryError(
            "E_INTERNAL",
            f"unexpected internal error: {type(exc).__name__}",
            "run `mailquery doctor` and check "
            "~/.mailquery/logs/mailquery.log for the traceback",
        )
        return _report_error(error, command)

    write_json(_success_payload(command, payload))
    duration_ms = int((time.perf_counter() - started) * 1000)
    warnings = payload.get("warnings") or ()
    raw_scan = payload.get("scan")
    scan: dict[str, Any] = raw_scan if isinstance(raw_scan, dict) else {}
    logger.info(
        "event=end command=%s exit_code=0 count=%s truncated=%s warnings=%d "
        "warning_codes=%s mode=%s candidates=%s messages_read=%s duration_ms=%d",
        command,
        payload.get("count", 0),
        bool(payload.get("truncated", False)),
        len(warnings),
        ",".join(_warning_code(warning) for warning in warnings) or "-",
        scan.get("mode", "-"),
        scan.get("candidates", "-"),
        scan.get("messages_read", "-"),
        duration_ms,
    )
    return 0


def _execute(
    args: argparse.Namespace,
    config: Config,
    home_path: Path,
    mail_root: Path | None,
    accounts_db: Path | None,
) -> dict:
    command = str(args.command)
    filters: Filters | None = None
    new_limit: int | None = None
    if command == "search":
        filters = _build_filters(args)
    elif command == "new":
        new_limit = _validate_limit(args.limit, MAX_NEW_LIMIT)

    with RunLock(home_path):
        store = open_store(mail_root=mail_root, tmp_root=home_path / "tmp")
        try:
            _log_store_connection(store)
            labels = AccountLabels(accounts_db, tmp_dir=home_path / "tmp")
            if command == "mailboxes":
                payload = run_mailboxes(store, config, labels)
            elif command == "search":
                payload = run_search(store, config, labels, filters)  # type: ignore[arg-type]
            elif command == "new":
                state_store = StateStore(home_path)
                payload = run_new(
                    store,
                    config,
                    labels,
                    state_store,
                    peek=bool(args.peek),
                    limit=new_limit,
                )
            elif command == "show":
                payload = run_show(store, config, labels, int(args.uid))
            else:  # pragma: no cover - argparse prevents this
                raise MailqueryError(
                    "E_USAGE",
                    f"unknown command: {command}",
                    'run "mailquery --help" to see the available commands',
                )
        finally:
            try:
                store.close()
            except Exception:  # noqa: BLE001 - closing must never mask the result
                pass
    return payload


def _log_store_connection(store: Any) -> None:
    """Log the connection strategy and store version (best effort, never fails)."""
    try:
        version = getattr(store, "version", None)
        version_name = getattr(version, "version", "-") if version is not None else "-"
        fingerprint = store.fingerprint()
        schema_ok = all(fingerprint.values()) if isinstance(fingerprint, dict) else True
        get_logger("mailquery.store").info(
            "strategy=%s version=%s schema_ok=%s",
            getattr(store, "strategy", "-"),
            version_name,
            str(schema_ok).lower(),
        )
    except Exception:  # noqa: BLE001 - diagnostic logging must never break a command
        pass


def _build_filters(args: argparse.Namespace) -> Filters:
    limit = _validate_limit(args.limit, MAX_SEARCH_LIMIT)
    include = _parse_include_mailboxes(args.include_mailbox)
    since = parse_relative_time(args.since) if args.since is not None else None
    until = parse_relative_time(args.until) if args.until is not None else None
    return Filters(
        subject=tuple(args.subject or ()),
        text=tuple(args.text or ()),
        from_=tuple(args.from_ or ()),
        to=tuple(args.to or ()),
        cc=tuple(args.cc or ()),
        since=since,
        until=until,
        unread=bool(args.unread),
        flagged=bool(args.flagged),
        has_attachments=bool(args.has_attachments),
        include_mailboxes=include,
        limit=limit,
    )


def _validate_limit(value: int | None, maximum: int) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise MailqueryError(
            "E_USAGE",
            f"invalid --limit value: {value!r}",
            f"valid range: 1..{maximum}",
        )
    return value


def _parse_include_mailboxes(values: Sequence[str] | None) -> tuple[str, ...]:
    refs: list[str] = []
    for raw in values or ():
        if not isinstance(raw, str):  # pragma: no cover - argparse guarantees str
            continue
        for part in raw.split(","):
            cleaned = part.strip()
            if cleaned:
                refs.append(cleaned)
    if values and not refs:
        raise MailqueryError(
            "E_USAGE",
            "--include-mailbox requires at least one mailbox",
            "pass a mailbox name, path or URL, e.g. --include-mailbox Facturas",
        )
    return tuple(refs)


def _with_count(payload: dict) -> dict:
    if "count" in payload:
        return payload
    messages = payload.get("messages")
    if isinstance(messages, list):
        merged = dict(payload)
        merged["count"] = len(messages)
        return merged
    return payload


def _success_payload(command: str, payload: dict) -> dict:
    merged: dict[str, Any] = {
        "ok": True,
        "command": command,
        "generated_at": now_iso(),
    }
    for key, value in payload.items():
        if key in _PAYLOAD_RESERVED_KEYS:
            continue
        merged[key] = value
    merged.setdefault("warnings", [])
    return merged


# --------------------------------------------------------------------------- #
# Doctor
# --------------------------------------------------------------------------- #


def _run_doctor(
    home_path: Path,
    mail_root: Path | None,
    accounts_db: Path | None,
    log_level: str | None,
    *,
    json_output: bool = False,
) -> int:
    level, max_size_mb = _doctor_log_settings(home_path, log_level)
    logger = _best_effort_logger(home_path, level, max_size_mb)
    try:
        checks = _collect_doctor_checks(home_path, mail_root, accounts_db)
    except Exception as exc:  # noqa: BLE001 - doctor never raises
        checks = [{"name": "doctor", "ok": False, "detail": _detail(exc)}]
    payload = {
        "ok": True,
        "command": "doctor",
        "generated_at": now_iso(),
        "checks": checks,
        "warnings": [],
    }
    if json_output:
        write_json(payload)
    else:
        sys.stdout.write(_render_doctor_report(payload) + "\n")
        sys.stdout.flush()
    if logger is not None:
        passed = sum(1 for check in checks if check.get("ok"))
        logger.info(
            "event=end command=doctor exit_code=0 checks=%d/%d",
            passed,
            len(checks),
        )
    return 0


def _render_doctor_report(payload: dict) -> str:
    """Render the doctor payload as a human-readable report in help style."""
    checks = [check for check in payload.get("checks") or [] if isinstance(check, dict)]
    warnings = [str(warning) for warning in payload.get("warnings") or []]
    width = _help_width()
    name_width = min(20, max((len(str(check.get("name", ""))) for check in checks), default=0))

    lines = [
        "mailquery doctor - environment and read-only preflight",
        f"Generated at: {payload.get('generated_at', now_iso())}",
        "",
        "Checks:",
    ]
    passed = 0
    for check in checks:
        ok = bool(check.get("ok"))
        passed += 1 if ok else 0
        status = "[ok]  " if ok else "[FAIL]"
        name = str(check.get("name", ""))
        detail = str(check.get("detail", "")).replace("\n", " ").strip()
        prefix = f"  {status} {name.ljust(name_width)}  "
        wrapped = textwrap.wrap(detail, width=max(20, width - len(prefix))) or [""]
        lines.append(prefix + wrapped[0])
        for extra in wrapped[1:]:
            lines.append(" " * len(prefix) + extra)

    total = len(checks)
    failed = total - passed
    result = f"{passed}/{total} checks passed"
    if failed:
        result += f" ({failed} failed)"
    lines.extend(["", f"Result: {result}"])
    if warnings:
        lines.extend(["", "Warnings:"])
        lines.extend(f"  - {warning}" for warning in warnings)
    lines.extend(
        [
            "",
            "Notes:",
            "  This report is read-only with respect to Apple Mail.",
            "  mailquery writes only its own logs and temporaries under ~/.mailquery.",
            "  Use `mailquery doctor --json` for the machine-readable payload.",
        ]
    )
    return "\n".join(lines)


def _collect_doctor_checks(
    home_path: Path,
    mail_root: Path | None,
    accounts_db: Path | None,
) -> list[dict]:
    checks: list[dict] = []

    def record(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)})

    # python -----------------------------------------------------------------
    version_text = ".".join(str(part) for part in sys.version_info[:3])
    record("python", sys.version_info >= (3, 11), version_text)

    # home -------------------------------------------------------------------
    try:
        ensure_app_home(home_path)
        problems: list[str] = []
        windows = sys.platform == "win32"
        for name in (None,) + tuple(APP_HOME_SUBDIRS):
            directory = home_path if name is None else home_path / name
            if not directory.is_dir():
                problems.append(f"missing {directory.name or directory}")
                continue
            if windows:
                continue  # POSIX modes are meaningless on Windows (D-04)
            mode = stat.S_IMODE(directory.stat().st_mode)
            if mode != 0o700:
                problems.append(f"{directory.name or directory} mode={oct(mode)}")
        if windows and not problems:
            # Windows: the home must exist and be writable (probe file, D-04).
            probe = home_path / "tmp" / f".doctor-probe-{os.getpid()}"
            try:
                probe.write_bytes(b"")
                probe.unlink()
            except OSError as exc:
                problems.append(f"not writable: {exc.strerror or exc}")
        if problems:
            record("home", False, "; ".join(problems))
        elif windows:
            record("home", True, f"{home_path} (writable)")
        else:
            record("home", True, f"{home_path} (mode 0700)")
    except OSError as exc:
        record("home", False, f"cannot create {home_path}: {exc.strerror or exc}")

    # store ------------------------------------------------------------------
    version = None
    version_error: Exception | None = None
    try:
        version = detect_version(mail_root)
        record("store", True, f"{version.version} at {version.mail_root}")
    except Exception as exc:  # noqa: BLE001 - diagnostics only
        version_error = exc
        record("store", False, _detail(exc))

    # envelope_index ---------------------------------------------------------
    envelope_ok = False
    if version is None:
        record("envelope_index", False, "not evaluated: store failed")
    else:
        try:
            probe_envelope_index(version, tmp_root=home_path / "tmp")
            envelope_ok = True
            record("envelope_index", True, str(version.envelope_index))
        except Exception as exc:  # noqa: BLE001 - diagnostics only
            record("envelope_index", False, _detail(exc))

    # schema + readonly_strategy --------------------------------------------
    store = None
    schema_ok = False
    if not envelope_ok:
        record("schema", False, "not evaluated: envelope_index failed")
        record("readonly_strategy", False, "not evaluated: envelope_index failed")
    else:
        store_open_error: Exception | None = None
        try:
            store = open_store(mail_root=mail_root, tmp_root=home_path / "tmp")
        except Exception as exc:  # noqa: BLE001 - diagnostics only
            store_open_error = exc

        if store is None:
            detail = _detail(store_open_error) if store_open_error else "store is not open"
            record("schema", False, detail)
            record("readonly_strategy", False, detail)
        else:
            try:
                fingerprint = store.fingerprint()
                missing = [table for table, present in fingerprint.items() if not present]
                if missing:
                    record("schema", False, f"missing tables: {', '.join(missing)}")
                else:
                    schema_ok = True
                    record("schema", True, "all required tables present")
            except Exception as exc:  # noqa: BLE001 - diagnostics only
                record("schema", False, _detail(exc))
            strategy = getattr(store, "strategy", None) or _infer_readonly_strategy(version)
            record(
                "readonly_strategy",
                True,
                f"{strategy}: Envelope Index opened read-only (mode=ro, query_only=ON)",
            )

    # accounts_db ------------------------------------------------------------
    labels_obj: AccountLabels | None = None
    try:
        labels = AccountLabels(accounts_db, tmp_dir=home_path / "tmp")
        labels_obj = labels
        if labels.available:
            count = len(labels.all())
            record("accounts_db", True, f"{count} account label(s) available")
        else:
            record(
                "accounts_db",
                False,
                "Accounts4.sqlite unavailable; only UUID account identifiers work",
            )
    except Exception as exc:  # noqa: BLE001 - diagnostics only
        record("accounts_db", False, _detail(exc))

    # config -----------------------------------------------------------------
    try:
        config = load_config(home_path)
        config_path = home_path / "config.toml"
        if not config.has_scopes:
            if config_path.is_file():
                prefix = "config.toml exists but declares no [scope.*] blocks"
            else:
                prefix = "no config.toml (optional)"
            if not schema_ok:
                detail = (
                    f"{prefix}; 0 account block(s) declared; available accounts: unknown "
                    "(schema failed)"
                )
            elif labels_obj is not None and labels_obj.available:
                labels = labels_obj.all()
                if labels:
                    available = ", ".join(label.label for label in labels)
                    detail = (
                        f"{prefix}; 0 account block(s) declared; available: {available} "
                        "(declare one in config.toml to observe it; commands return "
                        "W_NO_ACCOUNTS)"
                    )
                else:
                    detail = (
                        f"{prefix}; 0 account block(s) declared; no visible accounts "
                        "found (commands return W_NO_ACCOUNTS)"
                    )
            else:
                detail = (
                    f"{prefix}; 0 account block(s) declared; available accounts: unknown "
                    "(Accounts4.sqlite unavailable)"
                )
            record("config", True, detail)
        else:
            problems: list[str] = []
            lines: list[str] = []
            if not schema_ok or store is None:
                problems.append("not evaluated: schema failed")
            elif labels_obj is None:
                problems.append(
                    "cannot resolve account blocks: account labels are unavailable"
                )
            else:
                for entry in config.scopes:
                    try:
                        resolved = resolve_scope(
                            replace(config, scopes=(entry,)), store, labels_obj
                        )
                    except MailqueryError as exc:
                        hint = f" (hint: {exc.hint})" if exc.hint else ""
                        problems.append(f"{entry.key}: {exc.code}: {exc.message}{hint}")
                        continue
                    except Exception as exc:  # noqa: BLE001 - diagnostics only
                        problems.append(f"{entry.key}: {_detail(exc)}")
                        continue
                    for scope in resolved:
                        folders = [
                            mailbox.path for mailbox in scope.mailboxes if not mailbox.is_inbox
                        ]
                        lines.append(
                            f"{entry.key} \u2192 {scope.account_label} ({scope.account_uuid}): "
                            + ", ".join(["INBOX"] + folders)
                        )
            if problems:
                record("config", False, "; ".join(problems))
            else:
                record("config", True, "; ".join(lines))
    except Exception as exc:  # noqa: BLE001 - diagnostics only
        record("config", False, _detail(exc))

    if store is not None:
        try:
            store.close()
        except Exception:  # noqa: BLE001 - best effort
            pass

    # state ------------------------------------------------------------------
    try:
        state = StateStore(home_path).load()
        if state.cursor is None:
            try:
                lookback = load_config(home_path).new.lookback
            except Exception:  # noqa: BLE001 - config problems are reported by `config`
                lookback = DEFAULT_LOOKBACK
            record(
                "state",
                True,
                "no state yet; the next new run is a first run and emits the messages "
                f"received in the last {lookback} before the newest message",
            )
        else:
            record(
                "state",
                True,
                "cursor last_date_received={} last_uid={}".format(
                    state.cursor.last_date_received,
                    state.cursor.last_uid,
                ),
            )
    except Exception as exc:  # noqa: BLE001 - diagnostics only
        record("state", False, _detail(exc))

    # lock -------------------------------------------------------------------
    lock_path = home_path / "locks" / _LOCK_FILENAME
    try:
        lock = RunLock(home_path)
        lock.acquire()
        try:
            record("lock", True, f"available: {lock_path}")
        finally:
            lock.release()
    except MailqueryError as exc:
        if exc.code == "E_LOCKED":
            record("lock", False, f"held by another mailquery process: {lock_path}")
        else:
            record("lock", False, _detail(exc))
    except Exception as exc:  # noqa: BLE001 - diagnostics only
        record("lock", False, _detail(exc))

    return checks


def _infer_readonly_strategy(version: Any) -> str:
    if version is None:
        return "unknown"
    try:
        shm = Path(f"{version.envelope_index}-shm")
        return "live_ro" if shm.exists() else "copy_ro"
    except Exception:  # pragma: no cover - defensive
        return "unknown"


# --------------------------------------------------------------------------- #
# Rendering, logging and small helpers
# --------------------------------------------------------------------------- #


def _report_error(error: MailqueryError, command: str | None) -> int:
    write_json(error.to_payload(command or "-"))
    sys.stderr.write(f"mailquery: {error.code}: {error.message}\n")
    if error.hint:
        sys.stderr.write(f"mailquery: hint: {error.hint}\n")
    sys.stderr.flush()
    return error.exit_code


def _log_error(logger: Any, command: str, error: MailqueryError) -> None:
    if logger is None:
        return
    # Never log message/hint: they may contain account emails, folders or paths.
    # ``log_message`` is the text without that data (PRD 14); fall back to the
    # plain message only when the error carries no sanitized variant.
    logger.error(
        "event=error command=%s code=%s message=%s",
        command,
        error.code,
        error.log_message if error.log_message is not None else error.message,
    )


def _warning_code(warning: Any) -> str:
    """Return the ``W_*`` code of a rendered warning, without its detail."""
    return str(warning).split(":", 1)[0].strip()


def _best_effort_logger(
    home_path: Path,
    level: str | None,
    max_size_mb: int = DEFAULT_MAX_SIZE_MB,
) -> Any:
    try:
        ensure_app_home(home_path)
        _close_logging_handlers()
        setup_logging(home_path, level or DEFAULT_LOG_LEVEL, max_size_mb)
    except Exception:  # noqa: BLE001 - logging is never fatal
        return None
    return get_logger("mailquery.cli")


def _doctor_log_settings(home_path: Path, log_level: str | None) -> tuple[str, int]:
    """Resolve doctor logging settings: flag > config > defaults."""
    try:
        config = load_config(home_path)
    except Exception:  # noqa: BLE001 - doctor diagnoses broken configs itself
        return log_level or DEFAULT_LOG_LEVEL, DEFAULT_MAX_SIZE_MB
    return (
        log_level or config.logging.level,
        config.logging.max_size_mb,
    )


def _close_logging_handlers() -> None:
    """Close handlers before reconfiguring logging.

    ``mailquery.main`` may run several times in one process (tests, embedding);
    ``logging_setup.setup_logging`` clears the handler list, so closing the
    previous file handler first avoids leaking descriptors and ``ResourceWarning``
    noise on ``stderr``.
    """
    logger = logging.getLogger("mailquery")
    for handler in list(logger.handlers):
        try:
            handler.close()
        except Exception:  # noqa: BLE001 - closing is best effort
            pass
    logger.handlers.clear()


def _detail(exc: Exception) -> str:
    if isinstance(exc, MailqueryError):
        return f"{exc.code}: {exc.message}"
    text = str(exc).strip()
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__


def _system_exit_code(exc: SystemExit) -> int:
    code = exc.code
    if code is None:
        return 0
    if isinstance(code, int):
        return code
    return 1


def _guess_command(argv: Sequence[str]) -> str:
    for token in argv:
        if token in COMMANDS:
            return token
    return "-"

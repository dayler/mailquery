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
import stat
import sys
import textwrap
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from mailquery import __version__
from mailquery import uid as uid_module
from mailquery.backends import backend_class, get_backend
from mailquery.backends.registry import BackendRegistry, package_version
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
    declared_drivers,
    driver_in_scope,
    ensure_app_home,
    load_config,
    resolve_scope,
)
from mailquery.errors import MailqueryError, error_detail
from mailquery.logging_setup import get_logger, setup_logging
from mailquery.output import configure_streams, now_iso, write_json
from mailquery.search import (
    Filters,
    _store_excluded_warning,
    parse_relative_time,
    run_mailboxes,
    run_new,
    run_search,
    run_show,
)
from mailquery.state import RunLock, StateStore

COMMANDS = ("doctor", "mailboxes", "search", "new", "show")
# Backend check that the resolution of the ``[scope]`` blocks depends on, by
# backend name (PRD 12.8; annex A.7 and B.8).
_RESOLUTION_DEPENDENCY = {"apple_mail": "schema", "outlook": "stores"}
#: Mail client named by the doctor text report, by backend name.
_CLIENT_NAMES = {"apple_mail": "Apple Mail", "outlook": "Outlook"}

_LOCK_FILENAME = "mailquery.lock"
_PAYLOAD_RESERVED_KEYS = ("ok", "command", "generated_at")

_ROOT_EPILOG = """\
Examples:
  mailquery doctor                     environment and read-only preflight
  mailquery mailboxes                  accounts, folders and included flags
  mailquery search --since 1w --unread
  mailquery search --text "*invoice*" --since 1mo
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
  the text. A pattern is not anchored: invoice* also matches "the invoice".
  --subject: words separated by spaces are AND terms, with or without wildcards.
  --text, --from, --to and --cc: the whole value is one pattern, spaces included.
  Repeating a flag is AND too. An empty value does not filter.

Examples:
  mailquery search --since 1w
  mailquery search --since 2w --unread
  mailquery search --from "*@bank.com*" --since 2mo
  mailquery search --text "*invoice*" --since 1mo --has-attachments

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
        import shutil  # lazy: pulls bz2/lzma/zstd, only needed for help width

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
    import platform  # lazy: pulls _wmi on Windows, only needed for --version

    if sys.platform == "win32":
        backend = "outlook"
        system = f"Windows {platform.version()} {platform.machine()}"
    elif sys.platform == "darwin":
        backend = "apple_mail"
        system = f"macOS {platform.mac_ver()[0]} {platform.machine()}"
    else:
        backend = "apple_mail"
        system = f"{platform.system()} {platform.release()} {platform.machine()}"
    drivers = ", ".join(
        f"{driver} {version}"
        for driver, version in BackendRegistry().versions(platform=sys.platform)
    )
    return (
        f"mailquery {__version__} (backend {backend}; "
        f"Python {platform.python_version()}; {system}; drivers: {drivers})"
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
    # The format is validated by AppleMailBackend.parse_uid in main(), not by argparse (PRD 12.4).
    show_parser.add_argument("uid", metavar="UID", help="message uid (see `mailquery search`)")

    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    home: Path | None = None,
    mail_root: Path | None = None,
    accounts_db: Path | None = None,
    backend: Any = None,
) -> int:
    """Run one command and return the process exit code (never raises).

    ``home``, ``mail_root``, ``accounts_db`` and ``backend`` are test-only
    injection points; they are not CLI flags nor environment variables of the
    public contract. ``mail_root`` or ``accounts_db`` select Apple Mail on any
    OS; ``backend`` is an already built instance (the Outlook fake); otherwise
    the backend of the platform is selected (RF-26).
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
        # Before the home is created, the config is read or the store is opened:
        # generic uid syntax plus the installed driver (PRD-v2.1 §11.3 row 2) and,
        # for the native driver, its ``parse_native_id`` (pure, offline).
        try:
            args.uid, args.uid_driver = _parse_show_uid(
                args.uid, mail_root, accounts_db, backend
            )
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
            backend,
            args.log_level,
            json_output=bool(getattr(args, "json", False)),
        )
    return _run_command(args, home_path, mail_root, accounts_db, backend)


def _native_driver_name(
    mail_root: Path | None, accounts_db: Path | None, backend: Any
) -> str:
    """Driver of the backend this command would use, without opening anything."""
    if backend is not None:
        return str(getattr(backend, "driver", "") or "")
    return str(
        getattr(
            backend_class(platform=_platform_override(mail_root, accounts_db)),
            "driver",
            "",
        )
        or ""
    )


def _native_id_parser(
    mail_root: Path | None, accounts_db: Path | None, backend: Any
):
    """``parse_native_id`` of the backend this command would use (pure, offline)."""
    if backend is not None:
        return backend.parse_native_id
    return backend_class(
        platform=_platform_override(mail_root, accounts_db)
    ).parse_native_id


def _parse_show_uid(
    raw: Any,
    mail_root: Path | None,
    accounts_db: Path | None,
    backend: Any,
) -> tuple[Any, str]:
    """Validate the ``show`` uid before creating the home (PRD-v2.1 §11.3 row 2, AC-05).

    Returns ``(native_uid_or_None, driver)``: the native uid of the platform
    driver (ready for the backend) or ``None`` when the prefix belongs to another
    installed driver (its native part is validated after the scope check).
    """
    native_driver = _native_driver_name(mail_root, accounts_db, backend)
    registry_is_installed = BackendRegistry().is_installed

    def is_installed(driver: str) -> bool:
        # An injected backend (tests, the Outlook fake) is available by definition.
        return driver == native_driver or registry_is_installed(driver)

    parsed = uid_module.parse_uid(
        raw,
        native_driver=native_driver or None,
        is_installed=is_installed,
    )
    native: Any = None
    if parsed.driver == native_driver:
        native = _native_id_parser(mail_root, accounts_db, backend)(parsed.native_id)
    return native, parsed.driver


def _require_show_driver_in_scope(
    args: argparse.Namespace,
    config: Config,
    mail_root: Path | None,
    accounts_db: Path | None,
    backend: Any,
) -> None:
    """``show``: the uid's driver must be declared in ``[scope]`` (RF-36).

    Runs after ``config.toml`` is read and before the backend is built: an
    installed driver with no ``[scope]`` block is ``E_ACCOUNT_NOT_IN_SCOPE``
    (exit 2) without loading it. In this milestone only the platform's native
    driver serves ``show``; M04 extends the dispatch to every declared driver.
    """
    driver = str(getattr(args, "uid_driver", "") or "")
    native_driver = _native_driver_name(mail_root, accounts_db, backend)
    if not driver_in_scope(config, driver, native=native_driver or None):
        raise MailqueryError(
            "E_ACCOUNT_NOT_IN_SCOPE",
            f"driver {driver!r} is installed but no [scope] block declares it",
            f'declare an account for the driver in ~/.mailquery/config.toml, e.g. '
            f'[scope."{driver}:<account>"]; the driver stays out of scope until then',
            "driver out of scope",
        )
    if driver != native_driver:
        raise uid_module.driver_unknown(driver)


def _platform_override(mail_root: Path | None, accounts_db: Path | None) -> str | None:
    """Apple Mail on any OS when a test passes its store locations (plan 4.2)."""
    return "darwin" if (mail_root is not None or accounts_db is not None) else None


def _make_backend(
    home_path: Path, mail_root: Path | None, accounts_db: Path | None, backend: Any
) -> Any:
    """The injected backend, or the one of the platform (built lazily, nothing opened)."""
    if backend is not None:
        return backend
    return get_backend(
        platform=_platform_override(mail_root, accounts_db),
        mail_root=mail_root,
        accounts_db=accounts_db,
        tmp_root=home_path / "tmp",
    )


def _bind_command(backend: Any, command: str) -> None:
    """Tell a backend which command runs (Outlook's D-03 watchdog reports it on a timeout)."""
    bind = getattr(backend, "bind_command", None)
    if callable(bind):
        bind(command)


def _close_backend(backend: Any) -> None:
    """Release the backend; closing must never mask the result."""
    if backend is None:
        return
    try:
        backend.close()
    except Exception:  # noqa: BLE001 - best effort
        pass


# --------------------------------------------------------------------------- #
# Successful command execution
# --------------------------------------------------------------------------- #


def _run_command(
    args: argparse.Namespace,
    home_path: Path,
    mail_root: Path | None,
    accounts_db: Path | None,
    backend: Any = None,
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
    started = time.perf_counter()
    selected = None
    try:
        if command == "show":
            _require_show_driver_in_scope(
                args, config, mail_root, accounts_db, backend
            )
        selected = _make_backend(home_path, mail_root, accounts_db, backend)
        _bind_command(selected, command)
        logger.info("event=start command=%s backend=%s", command, selected.driver)
        payload = _execute(args, config, home_path, selected)
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
    finally:
        _close_backend(selected)

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
    backend: Any,
) -> dict:
    command = str(args.command)
    filters: Filters | None = None
    new_limit: int | None = None
    if command == "search":
        filters = _build_filters(args)
    elif command == "new":
        new_limit = _validate_limit(args.limit, MAX_NEW_LIMIT)

    with RunLock(home_path):
        _log_backend_connection(backend)
        if command == "mailboxes":
            payload = run_mailboxes(backend, config)
        elif command == "search":
            payload = run_search(backend, config, filters)  # type: ignore[arg-type]
        elif command == "new":
            state_store = StateStore(home_path, BackendRegistry().is_installed)
            payload = run_new(
                backend,
                config,
                state_store,
                peek=bool(args.peek),
                limit=new_limit,
            )
        elif command == "show":
            if args.uid is None:  # pragma: no cover - only the native driver serves show yet
                raise uid_module.driver_unknown(
                    str(getattr(args, "uid_driver", ""))
                )
            payload = run_show(backend, config, args.uid)
        else:  # pragma: no cover - argparse prevents this
            raise MailqueryError(
                "E_USAGE",
                f"unknown command: {command}",
                'run "mailquery --help" to see the available commands',
            )
    return payload


def _log_backend_connection(backend: Any) -> None:
    """Open the backend and log its strategy and version (a failure to log is ignored).

    The store errors of the client (not found, permission, unsupported schema)
    surface here, as they did when the CLI opened the store itself.
    """
    try:
        info = backend.describe()
    except MailqueryError:
        raise
    except Exception:  # noqa: BLE001 - diagnostic logging must never break a command
        return
    try:
        get_logger("mailquery.store").info(
            "strategy=%s version=%s schema_ok=%s",
            info.get("strategy", "-"),
            info.get("version", "-"),
            str(info.get("schema_ok", True)).lower(),
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
            "pass a mailbox name, path or URL, e.g. --include-mailbox Invoices",
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
    backend: Any,
    log_level: str | None,
    *,
    json_output: bool = False,
) -> int:
    level, max_size_mb = _doctor_log_settings(home_path, log_level)
    logger = _best_effort_logger(home_path, level, max_size_mb)
    selected = None
    run = _DoctorRun(home_path)
    client = _CLIENT_NAMES["apple_mail"]
    try:
        selected = _make_backend(home_path, mail_root, accounts_db, backend)
        client = _CLIENT_NAMES.get(str(getattr(selected, "driver", "")), client)
        _bind_command(selected, "doctor")
        _bind_doctor_timeout(selected, run, json_output, logger, client)
        registry = BackendRegistry()
        checks = _collect_doctor_checks(home_path, selected, run, registry=registry)
    except Exception as exc:  # noqa: BLE001 - doctor never raises
        checks = [{"name": "doctor", "ok": False, "detail": error_detail(exc)}]
    finally:
        _close_backend(selected)
    _emit_doctor_report(checks, json_output, logger, client)
    return 0


def _bind_doctor_timeout(
    backend: Any, run: "_DoctorRun", json_output: bool, logger: Any, client: str
) -> None:
    """D-03 in ``doctor`` (Outlook): on a COM timeout, complete the report and exit 0.

    The hook runs in the watchdog thread while the main thread is blocked in
    COM: it completes the checks per PRD 12.8 (the running check with the
    timeout text, its dependents ``not evaluated``), writes the report in the
    ``checks[]`` order, flushes and ends the process with ``os._exit(0)``.
    """
    bind = getattr(backend, "bind_doctor_timeout", None)
    if not callable(bind):
        return

    def finish(backend_checks: list[dict] | None, detail: str) -> None:
        try:
            checks = run.after_timeout(backend, backend_checks, detail)
            _emit_doctor_report(checks, json_output, logger, client)
        finally:
            for stream in (sys.stdout, sys.stderr):
                try:
                    stream.flush()
                except Exception:  # noqa: BLE001 - best effort before os._exit
                    pass
            for handler in logging.getLogger("mailquery").handlers:
                try:
                    handler.flush()
                except Exception:  # noqa: BLE001 - best effort before os._exit
                    pass
            os._exit(0)

    bind(finish)


def _emit_doctor_report(
    checks: list[dict], json_output: bool, logger: Any, client: str
) -> None:
    """Write the doctor payload (JSON or text report) and log the end line."""
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
        sys.stdout.write(_render_doctor_report(payload, client=client) + "\n")
        sys.stdout.flush()
    if logger is not None:
        passed = sum(1 for check in checks if check.get("ok"))
        logger.info(
            "event=end command=doctor exit_code=0 checks=%d/%d",
            passed,
            len(checks),
        )


def _render_doctor_report(payload: dict, *, client: str = "Apple Mail") -> str:
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
            f"  This report is read-only with respect to {client}.",
            "  mailquery writes only its own logs and temporaries under ~/.mailquery.",
            "  Use `mailquery doctor --json` for the machine-readable payload.",
        ]
    )
    return "\n".join(lines)


class _DoctorRun:
    """Progress of one ``doctor`` run, shared with the D-03 timeout hook.

    ``checks`` holds the finished common checks by name, ``backend_checks`` the
    backend's once they are done and ``config`` the parsed ``config.toml``.
    """

    def __init__(self, home_path: Path) -> None:
        self.home_path = home_path
        self.checks: dict[str, dict] = {}
        self.backend_checks: list[dict] | None = None
        self.config: Config | None = None
        self.config_error: Exception | None = None

    def record(self, name: str, ok: bool, detail: str) -> None:
        self.checks[name] = {"name": name, "ok": bool(ok), "detail": str(detail)}

    def ordered(self) -> list[dict]:
        """Common checks around the backend's, in the order of PRD 12.8."""
        result = [
            self.checks[name] for name in ("python", "home", "driver") if name in self.checks
        ]
        result.extend(self.backend_checks or [])
        result.extend(
            self.checks[name] for name in ("config", "state", "lock") if name in self.checks
        )
        return result

    def after_timeout(
        self, backend: Any, backend_checks: list[dict] | None, detail: str
    ) -> list[dict]:
        """The report after a COM timeout (PRD 12.8), without calling the mail client again.

        With ``backend_checks`` the timeout hit a backend check: the ``config``
        resolution then depends on a failed check and is ``not evaluated``.
        Without them it hit the ``config`` resolution, which takes ``detail``.
        """
        if backend_checks is not None:
            self.backend_checks = [dict(check) for check in backend_checks]
            _record_config_check(self, backend)
        else:
            self.record("config", False, detail)
        return self.ordered()


def _collect_doctor_checks(
    home_path: Path,
    backend: Any,
    run: _DoctorRun | None = None,
    *,
    registry: BackendRegistry | None = None,
) -> list[dict]:
    """Common checks plus ``backend.doctor_checks()``, in the order of PRD 12.8.

    Evaluation order (D-03): the checks that never call the mail client first
    (``python``, ``home``, ``config`` syntax, ``driver``, ``state``, ``lock``),
    then the backend checks and last the ``config`` resolution.
    """
    run = run if run is not None else _DoctorRun(home_path)
    registry = registry if registry is not None else BackendRegistry()

    # python -----------------------------------------------------------------
    version_text = ".".join(str(part) for part in sys.version_info[:3])
    run.record("python", sys.version_info >= (3, 11), version_text)

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
            run.record("home", False, "; ".join(problems))
        elif windows:
            run.record("home", True, f"{home_path} (writable)")
        else:
            run.record("home", True, f"{home_path} (mode 0700)")
    except OSError as exc:
        run.record("home", False, f"cannot create {home_path}: {exc.strerror or exc}")

    # config syntax (always validated; reported by the config check) -----------
    try:
        run.config = load_config(home_path, registry=registry)
    except Exception as exc:  # noqa: BLE001 - diagnostics only
        run.config_error = exc

    # driver (declared drivers: installed, plugin_api=1, valid capabilities) ---
    _record_driver_check(run, backend, registry)

    # state ------------------------------------------------------------------
    try:
        state_store = StateStore(home_path, registry.is_installed)
        state = state_store.load()
        info = state_store.load_info
        lookback = run.config.new.lookback if run.config is not None else DEFAULT_LOOKBACK
        if not info.exists:
            run.record(
                "state",
                True,
                "no state yet; the next new run is a first run and emits the messages "
                f"received in the last {lookback} before the newest message",
            )
        else:
            schema_label = (
                "schema: 1 (migration pending)"
                if info.migration_pending
                else "schema: 2"
            )
            if state.cursor is None:
                detail = f"{schema_label}; no cursor yet"
            else:
                detail = "{}; cursor last_date_received={} last_uid={}".format(
                    schema_label,
                    state.cursor.last_date_received,
                    state.cursor.last_uid,
                )
            if info.pruned_emitted_uids:
                detail += (
                    "; pruned {} emitted uid(s) of uninstalled drivers: {}".format(
                        info.pruned_emitted_uids,
                        ", ".join(info.pruned_drivers),
                    )
                )
            run.record("state", True, detail)
    except Exception as exc:  # noqa: BLE001 - diagnostics only
        run.record("state", False, error_detail(exc))

    # lock -------------------------------------------------------------------
    lock_path = home_path / "locks" / _LOCK_FILENAME
    try:
        lock = RunLock(home_path)
        lock.acquire()
        try:
            run.record("lock", True, f"available: {lock_path}")
        finally:
            lock.release()
    except MailqueryError as exc:
        if exc.code == "E_LOCKED":
            run.record("lock", False, f"held by another mailquery process: {lock_path}")
        else:
            run.record("lock", False, error_detail(exc))
    except Exception as exc:  # noqa: BLE001 - diagnostics only
        run.record("lock", False, error_detail(exc))

    # backend checks (store/pywin32, ..., accounts_db/object_model_guard) ------
    try:
        backend_checks = [dict(check) for check in backend.doctor_checks()]
    except Exception as exc:  # noqa: BLE001 - diagnostics only
        backend_checks = [{"name": "backend", "ok": False, "detail": error_detail(exc)}]
    run.backend_checks = backend_checks

    # config resolution --------------------------------------------------------
    _record_config_check(run, backend)
    return run.ordered()


def _backend_driver_name(backend: Any) -> str:
    """Driver of the backend under diagnosis (protocol v1 ``driver``; tolerant of doubles)."""
    driver = getattr(backend, "driver", None)
    return str(driver) if driver else ""


def _bool_text(value: Any) -> str:
    """``true``/``false`` for the doctor detail (PRD-v2.1 §11.6)."""
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)


def _format_driver_metadata(metadata: dict[str, Any]) -> str:
    """One ``driver`` detail entry: api, package version and the capability map (§11.6)."""
    capabilities = metadata.get("capabilities") or {}
    return (
        f"{metadata.get('driver')} (api={metadata.get('plugin_api')}; "
        f"pkg {metadata.get('version')}; "
        f"network={_bool_text(capabilities.get('network'))}; "
        f"readonly={capabilities.get('readonly', 'unknown')}; "
        f"body_local={_bool_text(capabilities.get('body_local'))}; "
        f"attachments={capabilities.get('attachments', 'unknown')}; "
        f"native_order={capabilities.get('native_order', 'unknown')})"
    )


def _driver_failure_detail(driver: str, exc: Exception) -> str:
    """Failure entry of the ``driver`` check: reason and hint of the error (§11.6)."""
    if isinstance(exc, MailqueryError):
        hint = f" (hint: {exc.hint})" if exc.hint else ""
        return f"{driver}: {exc.code}: {exc.message}{hint}"
    return f"{driver}: {error_detail(exc)}"


def _backend_driver_metadata(backend: Any) -> dict[str, Any]:
    """Metadata of a backend that the registry does not know (injected test doubles)."""
    capabilities = getattr(backend, "capabilities", None)
    return {
        "driver": _backend_driver_name(backend),
        "plugin_api": getattr(backend, "plugin_api", None),
        "version": package_version(),
        "capabilities": dict(capabilities) if isinstance(capabilities, Mapping) else {},
    }


def _native_driver_metadata(backend: Any, registry: BackendRegistry) -> dict[str, Any]:
    """Metadata of the native driver: from the registry, or from the injected instance."""
    driver = _backend_driver_name(backend)
    if driver and registry.is_installed(driver):
        return registry.info(driver)
    return _backend_driver_metadata(backend)


def _record_driver_check(run: _DoctorRun, backend: Any, registry: BackendRegistry) -> None:
    """``driver``: every declared driver is installed with a valid API 1 contract (§11.6).

    The native driver of the platform (the backend under diagnosis) is listed
    first when a ``[scope]`` block has no prefix; the explicitly declared drivers
    follow in config order. An invalid config is reported by the ``config``
    check, so this one validates only the native driver and says that the
    declared drivers are unknown. Without any ``[scope]`` block only the native
    driver is validated and the detail says ``no declared drivers``.
    """
    native = _backend_driver_name(backend)
    details: list[str] = []
    ok = True
    if run.config_error is not None:
        drivers = (native,) if native else ()
        suffix = "declared drivers: unknown (config failed)"
    else:
        config = run.config if run.config is not None else Config(home=run.home_path)
        drivers = declared_drivers(config, native=native)
        if not config.has_scopes:
            drivers = (native,) if native else ()
            suffix = "no declared drivers"
        else:
            suffix = ""
    for driver in drivers:
        try:
            if driver == native:
                metadata = _native_driver_metadata(backend, registry)
            else:
                metadata = registry.info(driver)
        except Exception as exc:  # noqa: BLE001 - diagnostics only
            ok = False
            details.append(_driver_failure_detail(driver, exc))
        else:
            details.append(_format_driver_metadata(metadata))
    if suffix:
        details.append(suffix)
    run.record("driver", ok, "; ".join(details) or "no declared drivers")


def _record_config_check(run: _DoctorRun, backend: Any) -> None:
    """``config``: syntax plus the resolution of the ``[scope]`` blocks (PRD 12.8, RF-25).

    The resolution depends first on the ``driver`` check (M02) and then on a
    check of the backend (annex A.7 / B.8); when one failed, the mail client is
    not called and the detail says ``not evaluated: <check> failed``. Blocks of
    a driver other than the native one keep their account resolution for the
    multi-driver phase, so they are only reported as declared. A declared
    account that resolves to an excluded store (Outlook) adds
    ``W_STORE_EXCLUDED`` to the detail, which keeps ``ok=true`` (PRD 15.3).
    """
    by_name = {str(check.get("name")): check for check in run.backend_checks or []}
    dependency = _RESOLUTION_DEPENDENCY.get(str(getattr(backend, "driver", "")))
    dependency_ok = dependency is None or bool(by_name.get(dependency, {}).get("ok"))
    driver_check = run.checks.get("driver")
    driver_ok = bool(driver_check.get("ok")) if driver_check is not None else True
    first_failure = None
    if not driver_ok:
        first_failure = "driver"
    elif not dependency_ok:
        first_failure = dependency
    native = _backend_driver_name(backend)
    try:
        if run.config_error is not None:
            raise run.config_error
        config = run.config if run.config is not None else load_config(run.home_path)
        config_path = run.home_path / "config.toml"
        if not config.has_scopes:
            if config_path.is_file():
                prefix = "config.toml exists but declares no [scope.*] blocks"
            else:
                prefix = "no config.toml (optional)"
            if first_failure is not None:
                detail = (
                    f"{prefix}; 0 account block(s) declared; available accounts: unknown "
                    f"({first_failure} failed)"
                )
            elif backend.labels_available:
                accounts = [
                    a
                    for a in backend.accounts()
                    if a.get("labelled", True) and a.get("excluded") is None
                ]
                if accounts:
                    available = ", ".join(account["label"] for account in accounts)
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
            run.record("config", True, detail)
        else:
            problems = []
            lines: list[str] = []
            excluded: list[dict] = []
            if first_failure is not None:
                problems.append(f"not evaluated: {first_failure} failed")
            else:
                for entry in config.scopes:
                    if entry.driver is not None and entry.driver != native:
                        # M04 resolves the accounts of every declared driver; in
                        # this phase the ``driver`` check already validated it.
                        lines.append(f"{entry.key} → declared for driver {entry.driver}")
                        continue
                    try:
                        resolved = resolve_scope(
                            replace(config, scopes=(entry,)), backend, excluded=excluded
                        )
                    except MailqueryError as exc:
                        hint = f" (hint: {exc.hint})" if exc.hint else ""
                        problems.append(f"{entry.key}: {exc.code}: {exc.message}{hint}")
                        continue
                    except Exception as exc:  # noqa: BLE001 - diagnostics only
                        problems.append(f"{entry.key}: {error_detail(exc)}")
                        continue
                    for scope in resolved:
                        folders = [
                            mailbox["path"]
                            for mailbox in scope.mailboxes
                            if not mailbox["is_inbox"]
                        ]
                        lines.append(
                            f"{entry.key} → {scope.account_label} ({scope.account_uuid}): "
                            + ", ".join(["INBOX"] + folders)
                        )
            # W_STORE_EXCLUDED of each declared excluded store, once (PRD 15.3).
            lines.extend(_store_excluded_warning(entry) for entry in excluded)
            if problems:
                run.record("config", False, "; ".join(problems))
            else:
                run.record("config", True, "; ".join(lines))
    except Exception as exc:  # noqa: BLE001 - diagnostics only
        run.record("config", False, error_detail(exc))


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
    text = error.log_message if error.log_message is not None else error.message
    if error.code == "E_INTERNAL" and error.__traceback__ is not None:
        # PRD 14: an E_INTERNAL (a COM failure included) also logs its traceback.
        # Only the frames and the exception type: the message is already sanitized above.
        import traceback  # lazy: only needed when logging an E_INTERNAL

        frames = "".join(traceback.format_tb(error.__traceback__)).rstrip("\n")
        kind = f"{type(error).__module__}.{type(error).__qualname__}"
        logger.error(
            "event=error command=%s code=%s message=%s\n"
            "Traceback (most recent call last):\n%s\n%s",
            command,
            error.code,
            text,
            frames,
            kind,
        )
        return
    logger.error("event=error command=%s code=%s message=%s", command, error.code, text)


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

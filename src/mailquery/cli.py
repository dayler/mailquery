"""Command line interface: argument parsing, dispatch, JSON contract, exit codes.

Only this module writes to ``stdout``/``stderr``. It parses ``argv`` with
``argparse`` (``-h``/``--help`` is the documented non-JSON exception), loads
the configuration, sets up logging, takes the run lock, dispatches one of the
five commands and renders either success or a JSON error object (PRD 12).
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import stat
import sys
import time
from pathlib import Path
from typing import Any, Sequence

from mailquery.accounts import AccountLabels
from mailquery.config import (
    APP_HOME_SUBDIRS,
    DEFAULT_LOG_LEVEL,
    DEFAULT_RETENTION_DAYS,
    LOG_LEVELS,
    MAX_NEW_LIMIT,
    MAX_SEARCH_LIMIT,
    Config,
    app_home,
    ensure_app_home,
    load_config,
)
from mailquery.errors import MailqueryError
from mailquery.logging_setup import get_logger, setup_logging
from mailquery.output import now_iso, write_json
from mailquery.search import (
    Filters,
    parse_relative_time,
    run_mailboxes,
    run_new,
    run_search,
    run_show,
)
from mailquery.state import RunLock, StateStore
from mailquery.store import detect_version, open_store

COMMANDS = ("doctor", "mailboxes", "search", "new", "show")
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
Output: one JSON object on stdout for every command (this help is the only
        non-JSON output); logs go to ~/.mailquery/logs/mailquery.log
Exit codes: 0 ok | 2 usage or config error | 3 environment error
            | 4 rejected query | 5 busy or transient error
"""

_DOCTOR_EPILOG = """\
Examples:
  mailquery doctor
  mailquery doctor --log-level debug

Notes:
  Always exits 0 when the diagnosis can run; failures are reported as
  individual checks (checks[].ok = false) in the JSON payload.
"""

_MAILBOXES_EPILOG = """\
Examples:
  mailquery mailboxes

Notes:
  A folder is included when its account is declared in ~/.mailquery/config.toml
  and the folder is INBOX or listed in mailbox_list. Counters are recalculated
  from the Envelope Index because Mail's own counters are not reliable.
"""

_SEARCH_EPILOG = """\
Matching:
  Patterns are case-insensitive; * matches any sequence and ? one character;
  without wildcards the value is matched as a substring. A value without
  wildcards is split on spaces into AND terms; a value with wildcards stays a
  single pattern.

Examples:
  mailquery search --since 1w
  mailquery search --since 2w --unread
  mailquery search --from "*@bank.com*" --since 2mo
  mailquery search --text "*factura*" --since 1mo --has-attachments

Notes:
  --text requires a narrowing filter (date, sender, subject or an extra folder)
  and refuses to scan more than [search].max_scan candidates.
"""

_NEW_EPILOG = """\
Examples:
  mailquery new
  mailquery new --peek
  mailquery new --limit 200

Notes:
  The first run is a baseline: it emits nothing, sets the cursor to the newest
  scoped message and reports W_FIRST_RUN. --peek never advances the cursor.
"""

_SHOW_EPILOG = """\
Examples:
  mailquery show 83143

Notes:
  The body is truncated to 20,000 characters; headers and attachment names are
  included, and .partial.emlx messages are flagged with partial: true.
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


def build_parser() -> argparse.ArgumentParser:
    """Build the ``mailquery`` argparse parser with all subcommands."""
    parser = _ArgumentParser(
        prog="mailquery",
        description="Read-only CLI to read and search Apple Mail.",
        epilog=_ROOT_EPILOG,
        formatter_class=_HelpFormatter,
        allow_abbrev=False,
    )
    _style_parser(parser, root=True)
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
        help="subject filter: substring or wildcards * and ?; repeatable (AND)",
    )
    search_parser.add_argument(
        "--text",
        action="append",
        metavar="PATTERN",
        help="body text filter: substring or wildcards; repeatable (AND)",
    )
    search_parser.add_argument(
        "--from",
        dest="from_",
        action="append",
        metavar="PATTERN",
        help="sender name or address filter: substring or wildcards; repeatable (AND)",
    )
    search_parser.add_argument(
        "--to",
        action="append",
        metavar="PATTERN",
        help="recipient name or address filter: substring or wildcards; repeatable (AND)",
    )
    search_parser.add_argument(
        "--cc",
        action="append",
        metavar="PATTERN",
        help="cc name or address filter: substring or wildcards; repeatable (AND)",
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
        help="extra folder to include in this run (name, path or URL); "
        "repeatable or comma-separated",
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
    show_parser.add_argument("uid", metavar="UID", type=int, help="message uid (see `mailquery search`)")

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
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    try:
        args = build_parser().parse_args(raw_argv)
    except SystemExit as exc:  # --help / argparse exits
        return _system_exit_code(exc)
    except MailqueryError as exc:
        return _report_error(exc, _guess_command(raw_argv))

    command = str(args.command)
    try:
        home_path = Path(home) if home is not None else app_home()
    except (OSError, RuntimeError) as exc:
        error = MailqueryError(
            "E_PERMISSION",
            f"cannot resolve the application home: {exc}",
            "make sure HOME points to a writable directory",
        )
        return _report_error(error, command)

    if command == "doctor":
        return _run_doctor(home_path, mail_root, accounts_db, args.log_level)
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
        setup_logging(home_path, level, config.logging.retention_days)
    except OSError as exc:
        error = MailqueryError(
            "E_PERMISSION",
            f"cannot write logs under {home_path}: {exc.strerror or exc}",
            "check permissions of the application home and its logs directory",
        )
        return _report_error(error, command)

    logger = get_logger("mailquery.cli")
    logger.info("event=start command=%s", command)
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
    raw_scan = payload.get("scan")
    scan: dict[str, Any] = raw_scan if isinstance(raw_scan, dict) else {}
    logger.info(
        "event=end command=%s exit_code=0 count=%s truncated=%s warnings=%d "
        "mode=%s candidates=%s messages_read=%s duration_ms=%d",
        command,
        payload.get("count", 0),
        bool(payload.get("truncated", False)),
        len(payload.get("warnings") or ()),
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
                payload = run_show(store, labels, int(args.uid))
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
            schema_ok,
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
) -> int:
    level, retention = _doctor_log_settings(home_path, log_level)
    logger = _best_effort_logger(home_path, level, retention)
    try:
        checks = _collect_doctor_checks(home_path, mail_root, accounts_db)
    except Exception as exc:  # noqa: BLE001 - doctor never raises
        checks = [{"name": "doctor", "ok": False, "detail": _detail(exc)}]
    write_json(
        {
            "ok": True,
            "command": "doctor",
            "generated_at": now_iso(),
            "checks": checks,
            "warnings": [],
        }
    )
    if logger is not None:
        passed = sum(1 for check in checks if check.get("ok"))
        logger.info(
            "event=end command=doctor exit_code=0 checks=%d/%d",
            passed,
            len(checks),
        )
    return 0


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
        for name in (None,) + tuple(APP_HOME_SUBDIRS):
            directory = home_path if name is None else home_path / name
            if not directory.is_dir():
                problems.append(f"missing {directory.name or directory}")
                continue
            mode = stat.S_IMODE(directory.stat().st_mode)
            if mode != 0o700:
                problems.append(f"{directory.name or directory} mode={oct(mode)}")
        if problems:
            record("home", False, "; ".join(problems))
        else:
            record("home", True, f"{home_path} (mode 0700)")
    except OSError as exc:
        record("home", False, f"cannot create {home_path}: {exc.strerror or exc}")

    # store ------------------------------------------------------------------
    version = None
    try:
        version = detect_version(mail_root)
        record("store", True, f"{version.version} at {version.mail_root}")
    except Exception as exc:  # noqa: BLE001 - diagnostics only
        record("store", False, _detail(exc))

    # envelope_index ---------------------------------------------------------
    try:
        if version is None:
            raise MailqueryError(
                "E_STORE_NOT_FOUND",
                "Mail store not detected",
                "open Apple Mail once; mailquery only reads the existing store",
            )
        index_path = version.envelope_index
        if not index_path.exists():
            raise MailqueryError(
                "E_STORE_NOT_FOUND",
                f"missing Envelope Index: {index_path}",
                "open Apple Mail once so the store is created",
            )
        if not os.access(index_path, os.R_OK):
            raise MailqueryError(
                "E_PERMISSION",
                f"Envelope Index is not readable: {index_path}",
                "grant Full Disk Access to the application running mailquery",
            )
        record("envelope_index", True, str(index_path))
    except Exception as exc:  # noqa: BLE001 - diagnostics only
        record("envelope_index", False, _detail(exc))

    # schema + readonly_strategy --------------------------------------------
    store = None
    store_open_error: Exception | None = None
    try:
        store = open_store(mail_root=mail_root, tmp_root=home_path / "tmp")
    except Exception as exc:  # noqa: BLE001 - diagnostics only
        store_open_error = exc

    if store is None:
        detail = _detail(store_open_error) if store_open_error else "store is not open"
        record("schema", False, detail)
    else:
        try:
            fingerprint = store.fingerprint()
            missing = [table for table, present in fingerprint.items() if not present]
            if missing:
                record("schema", False, f"missing tables: {', '.join(missing)}")
            else:
                record("schema", True, "all required tables present")
        except Exception as exc:  # noqa: BLE001 - diagnostics only
            record("schema", False, _detail(exc))

    if store is None:
        detail = _detail(store_open_error) if store_open_error else "store is not open"
        record("readonly_strategy", False, detail)
    else:
        strategy = getattr(store, "strategy", None) or _infer_readonly_strategy(version)
        record(
            "readonly_strategy",
            True,
            f"{strategy}: Envelope Index opened read-only (mode=ro, query_only=ON)",
        )
        try:
            store.close()
        except Exception:  # noqa: BLE001 - best effort
            pass

    # accounts_db ------------------------------------------------------------
    try:
        labels = AccountLabels(accounts_db, tmp_dir=home_path / "tmp")
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
        if config.has_scopes:
            declared = ", ".join(entry.key for entry in config.scopes)
            record("config", True, f"{len(config.scopes)} account block(s): {declared}")
        else:
            record(
                "config",
                True,
                "no config.toml or no [scope.*] blocks; no accounts declared "
                "(commands return W_NO_ACCOUNTS)",
            )
    except Exception as exc:  # noqa: BLE001 - diagnostics only
        record("config", False, _detail(exc))

    # state ------------------------------------------------------------------
    try:
        state = StateStore(home_path).load()
        if state.cursor is None:
            record("state", True, "no cursor yet (the first `new` run baselines)")
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
    # Never log message/hint: they may contain account emails or folder names.
    logger.error("event=error command=%s code=%s", command, error.code)


def _best_effort_logger(
    home_path: Path,
    level: str | None,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> Any:
    try:
        ensure_app_home(home_path)
        _close_logging_handlers()
        setup_logging(home_path, level or DEFAULT_LOG_LEVEL, retention_days)
    except Exception:  # noqa: BLE001 - logging is never fatal
        return None
    return get_logger("mailquery.cli")


def _doctor_log_settings(home_path: Path, log_level: str | None) -> tuple[str, int]:
    """Resolve doctor logging settings: flag > config > defaults."""
    try:
        config = load_config(home_path)
    except Exception:  # noqa: BLE001 - doctor diagnoses broken configs itself
        return log_level or DEFAULT_LOG_LEVEL, DEFAULT_RETENTION_DAYS
    return (
        log_level or config.logging.level,
        config.logging.retention_days,
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

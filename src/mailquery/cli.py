"""Command line interface: argument parsing, dispatch, JSON contract, exit codes.

Only this module writes to ``stdout``/``stderr``. It parses ``argv`` with
``argparse`` (``-h``/``--help`` is the documented non-JSON exception), loads
the configuration, sets up logging, takes the run lock, dispatches one of the
six commands and renders either success or a JSON error object.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import logging
import os
import re
import stat
import sys
import textwrap
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from mailquery import __version__
from mailquery import uid as uid_module
from mailquery.attachments import W_ATTACHMENT_ACTIVE_CONTENT, active_content_types
from mailquery.attachments.engine import AttachmentsEngine
from mailquery.attachments.paths import message_dir
from mailquery.backends import backend_class, get_backend
from mailquery.backends.base import ExcludedStoreError
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
    ensure_app_home,
    load_config,
    require_driver_in_scope,
    resolve_scope,
)
from mailquery.errors import MailqueryError, error_detail
from mailquery.logging_setup import get_logger, setup_logging
from mailquery.output import (
    CONTENT_NOTICE,
    configure_streams,
    now_iso,
    sanitize_text,
    write_json,
)
from mailquery.plugins import (
    PluginContext,
    call_driver,
    wrap_driver,
)
from mailquery.plugins.api import AttachmentStreamGuard, RESERVED_DRIVER_NAMES
from mailquery.search import (
    GROUP_KEYS,
    GROUP_MAX_KEYS,
    GROUP_MAX_LIMIT,
    MAILBOX_FIELDS,
    SEARCH_ROW_FIELDS,
    SHOW_FIELDS,
    Filters,
    _config_for_driver,
    _excluded_store_error,
    _resolved_scope,
    _scope_account_uuid,
    _store_excluded_warning,
    parse_relative_time,
    run_mailboxes,
    run_new,
    run_search,
    run_show,
)
from mailquery.state import RunLock, StateStore

COMMANDS = ("doctor", "mailboxes", "search", "new", "show", "attachment")
# Backend check that the resolution of the ``[scope]`` blocks depends on, by
# backend name.
_RESOLUTION_DEPENDENCY = {"apple_mail": "schema", "outlook": "stores"}
#: Mail client named by the doctor text report, by backend name.
_CLIENT_NAMES = {"apple_mail": "Apple Mail", "outlook": "Outlook"}
#: Check names the core owns in the ``plugins`` section of ``doctor``.
_DOCTOR_PLUGIN_RESERVED_CHECKS = frozenset({"config", "plugin"})
#: ``detail`` of a check skipped because a check it depends on failed.
_NOT_EVALUATED_DETAIL = re.compile(r"^not evaluated: .+ failed$")

_LOCK_FILENAME = "mailquery.lock"
_PAYLOAD_RESERVED_KEYS = ("ok", "command", "generated_at")
#: Commands whose successful response carries the fixed untrusted-content notice.
_CONTENT_NOTICE_COMMANDS = frozenset({"search", "new", "show", "attachment"})
#: Field names accepted by ``--fields`` in ``search``/``new`` and in ``show``.
_SEARCH_FIELDS = (*SEARCH_ROW_FIELDS, "all")
_SHOW_FIELDS = (*SHOW_FIELDS, "all")
_SEARCH_FIELDS_TEXT = ", ".join(_SEARCH_FIELDS)
_SHOW_FIELDS_TEXT = ", ".join(_SHOW_FIELDS)
#: Field names accepted by ``--fields`` in ``mailboxes`` (no ``all``).
_MAILBOX_FIELDS = MAILBOX_FIELDS
_MAILBOX_FIELDS_TEXT = ", ".join(_MAILBOX_FIELDS)
_SEARCH_FIELDS_BLOCK = textwrap.fill(
    "Valid fields: " + _SEARCH_FIELDS_TEXT,
    width=92,
    initial_indent="  ",
    subsequent_indent="  ",
)
_SHOW_FIELDS_BLOCK = textwrap.fill(
    "Valid fields: " + _SHOW_FIELDS_TEXT,
    width=92,
    initial_indent="  ",
    subsequent_indent="  ",
)
#: Grouping keys of ``search --group-by``, in the order its error hint lists them.
_SEARCH_GROUP_KEYS_TEXT = ", ".join(GROUP_KEYS)

_ROOT_EPILOG = """\
Examples:
  mailquery doctor                     environment and read-only diagnosis
  mailquery mailboxes                  accounts, folders and included flags
  mailquery search --since 1w --unread
  mailquery search --text "*invoice*" --since 1mo
  mailquery new --peek
  mailquery show 83143
  mailquery attachment apple_mail:83143 --all

Configuration: ~/.mailquery/config.toml (optional; see README.md)
Output: one JSON object on stdout for every command, in UTF-8 (this help,
        --version and the default doctor report are the only non-JSON output);
        logs go to ~/.mailquery/logs/mailquery.log
Exit codes: 0 ok | 2 usage or config error | 3 environment error
            | 4 rejected query or blocked attachments | 5 busy or transient error
            | 6 mail client not running
"""

_ATTACHMENT_EPILOG = """\
Examples:
  mailquery show apple_mail:83143
  mailquery attachment apple_mail:83143 --index 1
  mailquery attachment apple_mail:83143 --all

Notes:
  - If any attachment of the message matches a dangerous filename pattern, a blocked
    extension or executable content, the whole message is blocked: the command fails
    with E_ATTACHMENT_BLOCKED (exit 4) and no file is written (both --index and --all).
  - Attachments that cannot be recovered fail with E_ATTACHMENT_UNAVAILABLE (exit 3);
    corrupt or S/MIME attachments fail with E_ATTACHMENT_UNREADABLE (exit 3).
  - Files are saved with mode 0600 under
    ~/.mailquery/attachments/<driver>/<native_id>/<index:02d>_<sanitized_name>.
"""

_ATTACHMENT_USAGE = "mailquery attachment [-h] (--index N | --all) [--force] <uid>"

_DOCTOR_EPILOG = """\
Examples:
  mailquery doctor
  mailquery doctor --json
  mailquery doctor --json --failures
  mailquery --log-level debug doctor

Notes:
  Prints a human-readable report by default; --json emits the machine-readable
  payload. Always exits 0 when the diagnosis can run; failures are reported as
  checks with ok = false, plus a Result line with the failed count. With
  --failures only the checks that fail (and the ones not evaluated) are shown.
  Declared external plugins add their own checks under a Plugins section.
"""

_MAILBOXES_EPILOG = """\
Examples:
  mailquery mailboxes
  mailquery mailboxes --fields name,url
  mailquery mailboxes --fields total,unread

Notes:
  Each account lists its folders once, and a folder is included when its account
  is declared in ~/.mailquery/config.toml and the folder is INBOX or listed in
  mailbox_list. Every folder shows its path and whether it is included; name, url,
  total and unread are added only when requested with --fields. Counters are
  calculated from the mail store only with --fields total or unread, because the
  mail client's own counters are not reliable.
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
  mailquery search --since 6mo --subject factura --group-by domain,month --limit 1
  mailquery search --unread --count

Notes:
  --text needs a narrowing filter: --since, --until, --subject, --from or an extra
  folder (one other than INBOX in mailbox_list or --include-mailbox). --to and --cc
  narrow on macOS but not on Windows, where checking them opens every message (they
  are validated like --text). An empty value does not narrow. Without a narrowing
  filter the query fails with E_UNBOUNDED_SCAN (exit 4); with more than
  [search].max_scan candidates after the filters, with E_SCAN_TOO_LARGE (exit 4).
  --include-mailbox takes folders of declared accounts; INBOX is the inbox of the
  first declared account.
  URLs in the subject, the names, the headers and the body are neutralized by
  default ([content].url_display = "keep" keeps the exact text); --strip-links
  replaces every URL with [link omitted]. The filters always compare the original
  text, so the results are the same in every mode.
  --fields adds fields to the default row (uid, subject, from, date_received,
  is_read, has_attachments), comma-separated or with the option repeated; --fields
  all returns the full row.
  --group-by groups the results by one or two keys (from, domain, mailbox, account,
  day, week, month) and returns groups[] instead of messages[]; each group has its
  keys, count and newest messages. With --group-by, --limit is the messages per
  group (0 to 50, 5 by default) and at most 50 groups are returned.
  --count returns only the number of matching messages, without messages or
  truncated; it cannot be combined with --fields, --group-by or --limit.
  When search finds no messages, hint says how many folders and accounts were
  searched and how to widen the scope.
""" + _SEARCH_FIELDS_BLOCK + """
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
  URLs and link signals follow the message processing of search: the URLs are
  neutralized by default ([content].url_display = "keep" keeps the exact text) and
  --strip-links replaces them with [link omitted].
  --fields adds fields to the default row (uid, subject, from, date_received,
  is_read, has_attachments), comma-separated or with the option repeated; --fields
  all returns the full row.
""" + _SEARCH_FIELDS_BLOCK + """
"""

_SHOW_EPILOG = """\
Examples:
  mailquery show 83143
  mailquery show 83143 --fields attachments

Notes:
  The body is truncated to 20,000 characters; headers and attachment names are
  included. Only messages of accounts declared in config.toml can be shown; use
  the uid reported by search or new.
  The URLs of the subject, the names, the headers and the body are neutralized by
  default ([content].url_display = "keep" keeps the exact text) and --strip-links
  replaces them with [link omitted].
  --fields selects the fields of message (uid is always included), comma-separated
  or with the option repeated; without it, or with --fields all, the whole message
  is returned.
""" + _SHOW_FIELDS_BLOCK + """
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


class _AttachmentHelpFormatter(_HelpFormatter):
    """Attachment help: 17-column help texts with literal line wraps."""

    def __init__(self, prog: str) -> None:
        argparse.RawDescriptionHelpFormatter.__init__(
            self, prog, width=_help_width(), max_help_position=17
        )

    def _split_lines(self, text: str, width: int) -> list[str]:
        # The attachment help has fixed line breaks: preserve the explicit
        # newlines and do not re-wrap (every line stays under 100 cols).
        return text.splitlines()

    def _format_action(self, action: argparse.Action) -> str:
        if isinstance(action, argparse._SubParsersAction):
            return super()._format_action(action)
        # Keep the help column at 17 even with short invocations (``<uid>``,
        # ``--all``).
        self._action_max_length = max(self._action_max_length, 15)
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
    """Return the ``--version`` line without touching any backend."""
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
    diagnosis.add_argument(
        "--failures",
        action="store_true",
        help="show only the checks that fail and the ones not evaluated",
    )

    mailboxes_parser = subparsers.add_parser(
        "mailboxes",
        help="list accounts and their folders (counters with --fields)",
        description="List accounts and their folders, and whether they are included\n"
        "in the configured scope. Counters are calculated only with --fields total\n"
        "or unread.",
        epilog=_MAILBOXES_EPILOG,
        formatter_class=_HelpFormatter,
    )
    mailboxes_parser.set_defaults(command="mailboxes")
    _style_parser(mailboxes_parser, root=False)
    mailboxes_parser.add_argument(
        "--fields",
        action="append",
        metavar="LIST",
        help="adds name, url, total and unread to every folder; comma-separated "
        f"or repeatable: {_MAILBOX_FIELDS_TEXT}",
    )

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
    search_parser.add_argument(
        "--strip-links",
        action="store_true",
        help="replace every URL with [link omitted] (overrides [content].url_display)",
    )
    search_parser.add_argument(
        "--fields",
        action="append",
        metavar="LIST",
        help="adds fields to the default row (uid, subject, from, date_received, "
        "is_read, has_attachments); comma-separated or repeatable; all adds the full "
        "row",
    )
    search_parser.add_argument(
        "--group-by",
        action="append",
        metavar="KEYS",
        help="groups the results by up to two keys, comma-separated or repeatable: "
        "from, domain, mailbox, account, day, week, month",
    )
    search_parser.add_argument(
        "--count",
        action="store_true",
        help="returns only the number of matching messages, without messages",
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
    new_parser.add_argument(
        "--strip-links",
        action="store_true",
        help="replace every URL with [link omitted] (overrides [content].url_display)",
    )
    new_parser.add_argument(
        "--fields",
        action="append",
        metavar="LIST",
        help="adds fields to the default row (uid, subject, from, date_received, "
        "is_read, has_attachments); comma-separated or repeatable; all adds the full "
        "row",
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
    show_parser.add_argument(
        "--strip-links",
        action="store_true",
        help="replace every URL with [link omitted] (overrides [content].url_display)",
    )
    show_parser.add_argument(
        "--fields",
        action="append",
        metavar="LIST",
        help="selects the fields of message (uid is always included); "
        "comma-separated or repeatable; all selects every field",
    )
    # The uid format is validated in main() by _parse_command_uid, not by argparse.
    show_parser.add_argument("uid", metavar="UID", help="message uid (see `mailquery search`)")

    attachment_parser = subparsers.add_parser(
        "attachment",
        help="recover local attachments of one message",
        description="Recover local attachments of one message into "
        "~/.mailquery/attachments/.",
        epilog=_ATTACHMENT_EPILOG,
        formatter_class=_AttachmentHelpFormatter,
        allow_abbrev=False,
    )
    attachment_parser.set_defaults(command="attachment")
    attachment_parser.usage = _ATTACHMENT_USAGE
    _style_parser(attachment_parser, root=False)
    attachment_parser._positionals.title = "Positional arguments"  # noqa: SLF001
    # ``--index``/``--all`` are mutually exclusive and the value is validated in
    # main() to keep the literal error texts.
    attachment_parser.add_argument(
        "--index",
        metavar="N",
        help="1-based attachment index to recover (as shown by `mailquery show <uid>`)",
    )
    attachment_parser.add_argument(
        "--all",
        action="store_true",
        help="recover all attachments of the message; if any is blocked the whole "
        "message fails",
    )
    attachment_parser.add_argument(
        "--force",
        action="store_true",
        help="re-extract from the driver and overwrite existing cached files",
    )
    attachment_parser.add_argument(
        "uid",
        metavar="<uid>",
        help="message uid (as returned by search, new or show, e.g. apple_mail:83143;\n"
        "the legacy unprefixed uid is accepted for the native driver)",
    )

    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    home: Path | None = None,
    mail_root: Path | None = None,
    accounts_db: Path | None = None,
    backend: Any = None,
) -> int:
    """Run one command, return the process exit code and release log handlers.

    The log file handler must not outlive the run: on Windows an open handle
    blocks deleting the run's temporary home (test cleanup), and in-process
    callers would leak descriptors.
    """
    try:
        return _main(
            argv,
            home=home,
            mail_root=mail_root,
            accounts_db=accounts_db,
            backend=backend,
        )
    finally:
        _close_logging_handlers()


def _main(
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
    the backend of the platform is selected.
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
    if command in ("search", "new", "show", "mailboxes"):
        # Before the home exists, the config is read or the store is opened.
        try:
            args.fields_selection = _fields_selection(args, command)
        except MailqueryError as exc:
            return _report_error(exc, command)
    if command == "search":
        # --group-by/--count and their --limit range, before the home exists too.
        try:
            args.group_keys, args.count_only = _grouping_selection(args)
        except MailqueryError as exc:
            return _report_error(exc, command)
    registry = BackendRegistry()
    if command == "attachment":
        # Exactly one of --index/--all and a positive --index,
        # before the home exists, the config is read or the store is opened.
        try:
            args.attachment_indices = _attachment_selection(args)
        except MailqueryError as exc:
            return _report_error(exc, command)
    if command in ("show", "attachment"):
        # Before the home is created, the config is read or the store is opened:
        # generic uid syntax plus the installed driver and,
        # for the native driver, its ``parse_native_id`` (pure, offline).
        try:
            args.uid, args.uid_driver, args.uid_native_id = _parse_command_uid(
                args.uid, mail_root, accounts_db, backend, registry
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
            failures=bool(getattr(args, "failures", False)),
        )
    return _run_command(
        args, home_path, mail_root, accounts_db, backend, registry
    )


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


def _parse_command_uid(
    raw: Any,
    mail_root: Path | None,
    accounts_db: Path | None,
    backend: Any,
    registry: BackendRegistry,
) -> tuple[Any, str, str]:
    """Validate the command uid before creating the home.

    Returns ``(native_uid_or_None, driver, native_id)``: the native uid of the
    platform driver (ready for the backend) or ``None`` when the prefix belongs
    to another installed driver (its native part is validated after the scope
    check and after loading the declared driver).
    """
    native_driver = _native_driver_name(mail_root, accounts_db, backend)
    registry_is_installed = registry.is_installed

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
    return native, parsed.driver, parsed.native_id


def _require_command_driver_in_scope(
    args: argparse.Namespace, config: Config, native_name: str
) -> None:
    """``show``/``attachment``: the uid's driver must be declared in ``[scope]``.

    Runs after ``config.toml`` is read and before any driver is opened: an
    installed driver with no ``[scope]`` block is ``E_ACCOUNT_NOT_IN_SCOPE``
    (exit 2) without loading it. A config with no blocks at all keeps the 2.0.1
    path: the native driver is opened and ``run_show`` rejects the message.
    """
    driver = str(getattr(args, "uid_driver", "") or "")
    if not config.scopes and driver == native_name:
        return
    require_driver_in_scope(config, driver, native=native_name or None)


def _platform_override(mail_root: Path | None, accounts_db: Path | None) -> str | None:
    """Apple Mail on any OS when a test passes its store locations."""
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
    """Tell a backend which command runs (Outlook's COM watchdog reports it on a timeout)."""
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


def _declared_driver_names(config: "Config", native_name: str) -> tuple[str, ...]:
    """Declared drivers of the command, with the native fallback of a config with no blocks.

    Only the declared drivers are opened; a config with no ``[scope]`` block keeps
    the 2.0.1 behavior (the native driver is the default driver, used for
    discovery and ``W_NO_ACCOUNTS``). The order is the one of
    ``config.declared_drivers`` (native first, then the explicit blocks).
    """
    declared = declared_drivers(config, native=native_name or None)
    if declared:
        return tuple(declared)
    return (native_name,) if native_name else ()


def _open_drivers(
    names: Sequence[str],
    command: str,
    *,
    home_path: Path,
    mail_root: Path | None,
    accounts_db: Path | None,
    backend: Any,
    native_name: str,
    registry: BackendRegistry,
    describe: bool = True,
) -> dict[str, Any]:
    """Open the drivers the command consults.

    The native driver is the injected/platform backend; every other declared
    driver is loaded and instantiated by the registry (API 1: the entry point is
    a class or a factory invoked with one positional ``PluginContext``). Drivers
    are opened before ``event=start`` and closed by the caller in a ``finally``;
    a declared driver that does not load aborts the command here, without
    partial results.
    """
    opened: dict[str, Any] = {}
    plugins: list[str] = []
    for name in names:
        if name == native_name:
            opened[name] = _make_backend(home_path, mail_root, accounts_db, backend)
        else:
            plugins.append(name)
    if plugins:
        context = PluginContext(home=home_path, tmp_dir=home_path / "tmp")
        opened.update(registry.open_drivers(plugins, context=context))
    for instance in opened.values():
        _bind_command(instance, command)
        if describe:
            _log_backend_connection(instance)
    return opened


def _validate_command_native_id(
    args: argparse.Namespace, opened: Mapping[str, Any], native_name: str
) -> None:
    """Validate the native part of a plugin ``show``/``attachment`` uid with the parser.

    The plugin receives only ``<native_id>`` and validates it with
    ``parse_native_id``; the CLI runs that check after loading the declared
    driver and hands the result to ``run_show``. The call
    goes through the ``call_driver`` wrapper: a plugin ``reason`` (``invalid_uid``,
    ``not_found``, ...) becomes the core code/exit and an unmapped failure is
    ``E_PLUGIN_FAILED``, never ``E_INTERNAL``.
    """
    driver = str(getattr(args, "uid_driver", "") or "")
    if not driver or driver == native_name:
        return
    instance = opened.get(driver)
    parser = getattr(instance, "parse_native_id", None)
    if callable(parser):
        native_id = str(getattr(args, "uid_native_id", ""))
        args.uid = call_driver(
            "parse_native_id",
            lambda: parser(native_id),
            driver=driver,
        )
    else:  # pragma: no cover - the API 1 contract requires parse_native_id
        args.uid = str(getattr(args, "uid_native_id", ""))


def _run_command(
    args: argparse.Namespace,
    home_path: Path,
    mail_root: Path | None,
    accounts_db: Path | None,
    backend: Any = None,
    registry: BackendRegistry | None = None,
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

    registry = registry if registry is not None else BackendRegistry()
    try:
        config = load_config(home_path, registry=registry)
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
    native_name = _native_driver_name(mail_root, accounts_db, backend)
    opened: dict[str, Any] = {}
    try:
        if command == "show":
            _require_command_driver_in_scope(args, config, native_name)
        if command == "attachment":
            _require_attachments_enabled(config)
            _require_command_driver_in_scope(args, config, native_name)
        with RunLock(home_path):
            if command in ("show", "attachment"):
                names = (str(getattr(args, "uid_driver", "") or native_name),)
            else:
                names = _declared_driver_names(config, native_name)
            opened = _open_drivers(
                names,
                command,
                home_path=home_path,
                mail_root=mail_root,
                accounts_db=accounts_db,
                backend=backend,
                native_name=native_name,
                registry=registry,
                describe=command != "attachment",
            )
            if command == "attachment":
                # The loaded driver must be able to materialize
                # attachments before any store is opened.
                _require_attachment_capabilities(
                    opened.get(str(getattr(args, "uid_driver", "") or native_name)),
                    str(getattr(args, "uid_driver", "") or native_name),
                )
                _log_backend_connection(
                    opened.get(str(getattr(args, "uid_driver", "") or native_name))
                )
                _validate_command_native_id(args, opened, native_name)
            if command == "show":
                _validate_command_native_id(args, opened, native_name)
            logger.info(
                "event=start command=%s backend=%s drivers=%s",
                command,
                native_name or "-",
                ",".join(_declared_driver_names(config, native_name)) or "-",
            )
            selected = opened.get(native_name)
            drivers = {
                name: instance
                for name, instance in opened.items()
                if name != native_name
            }
            payload = _execute(
                args,
                config,
                home_path,
                selected,
                drivers=drivers,
                native=native_name,
                registry=registry,
            )
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
        for instance in opened.values():
            _close_backend(instance)

    write_json(_success_payload(command, payload))
    duration_ms = int((time.perf_counter() - started) * 1000)
    if command == "attachment":
        attachments = payload.get("attachments") or ()
        logger.info(
            "event=end command=attachment exit_code=0 count=%d cached=%d bytes=%d "
            "duration_ms=%d",
            len(attachments),
            sum(1 for entry in attachments if entry.get("cached")),
            sum(int(entry.get("size_bytes") or 0) for entry in attachments),
            duration_ms,
        )
        return 0
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
    *,
    drivers: "Mapping[str, Any] | None" = None,
    native: str | None = None,
    registry: BackendRegistry | None = None,
) -> dict:
    command = str(args.command)
    fields = getattr(args, "fields_selection", None)
    filters: Filters | None = None
    new_limit: int | None = None
    if command == "search":
        group_keys = tuple(getattr(args, "group_keys", ()) or ())
        filters = _build_filters(args, group_by=group_keys)
    elif command == "new":
        new_limit = _validate_limit(args.limit, MAX_NEW_LIMIT)

    mapping = dict(drivers or {})
    extra: dict[str, Any] = {}
    if mapping:
        extra["drivers"] = mapping
    if backend is None:
        extra["native"] = native
    state_validator = (
        registry.is_installed
        if registry is not None
        else BackendRegistry().is_installed
    )
    if command == "attachment":
        payload = _run_attachment(
            args, config, home_path, backend, mapping, native
        )
    elif command == "mailboxes":
        payload = run_mailboxes(backend, config, fields=fields, **extra)
    elif command == "search":
        payload = run_search(
            backend,
            config,
            filters,  # type: ignore[arg-type]
            url_mode=_url_mode(config, args),
            fields=fields,
            group_by=group_keys,
            count=bool(getattr(args, "count_only", False)),
            **extra,
        )
    elif command == "new":
        state_store = StateStore(home_path, state_validator)
        payload = run_new(
            backend,
            config,
            state_store,
            peek=bool(args.peek),
            limit=new_limit,
            url_mode=_url_mode(config, args),
            fields=fields,
            **extra,
        )
    elif command == "show":
        uid_driver = str(getattr(args, "uid_driver", "") or "")
        if backend is None or uid_driver != str(native or ""):
            payload = run_show(
                backend,
                config,
                args.uid,
                driver=uid_driver or None,
                drivers=mapping or None,
                native=native,
                url_mode=_url_mode(config, args),
                fields=fields,
            )
        else:
            payload = run_show(
                backend,
                config,
                args.uid,
                url_mode=_url_mode(config, args),
                fields=fields,
            )
    else:  # pragma: no cover - argparse prevents this
        raise MailqueryError(
            "E_USAGE",
            f"unknown command: {command}",
            'run "mailquery --help" to see the available commands',
        )
    return payload


def _url_mode(config: Config, args: argparse.Namespace) -> str:
    """Effective URL display mode of ``search``, ``new`` and ``show``.

    ``--strip-links`` wins over ``[content].url_display``, which wins over the
    ``neutralize`` default already carried by the config.
    """
    if bool(getattr(args, "strip_links", False)):
        return "strip"
    return config.content.url_display


def _fields_selection(
    args: argparse.Namespace, command: str
) -> tuple[str, ...] | None:
    """Validate ``--fields`` and return the selected names, or ``None``.

    Each value is split on commas and the surrounding spaces of every name are
    stripped; names are compared case-sensitively. An unknown or empty name is
    ``E_USAGE`` with the valid field list of the command.
    """
    raw = getattr(args, "fields", None)
    if raw is None:
        return None
    if command == "mailboxes":
        valid = _MAILBOX_FIELDS
    else:
        valid = _SEARCH_FIELDS if command in ("search", "new") else _SHOW_FIELDS
    selected: list[str] = []
    for value in raw:
        for item in str(value).split(","):
            name = item.strip()
            if name not in valid:
                raise MailqueryError(
                    "E_USAGE",
                    f"unknown field '{name}' in --fields",
                    f"valid fields: {', '.join(valid)}",
                    "invalid --fields value",
                )
            if name not in selected:
                selected.append(name)
    return tuple(selected)


def _grouping_selection(
    args: argparse.Namespace,
) -> tuple[tuple[str, ...], bool]:
    """Validate ``--group-by``, ``--count`` and their ``--limit`` range.

    Returns the grouping keys in the requested order, without duplicates, and
    whether the command only counts messages. Every ``--group-by`` value is
    split on commas, the spaces around each key are stripped and the keys are
    compared case-sensitively. An unknown or empty key, a repeated key, more
    than two keys, ``--count`` combined with another output option and a
    ``--limit`` outside 0 to 50 with ``--group-by`` are ``E_USAGE``.
    """
    keys: list[str] = []
    for value in getattr(args, "group_by", None) or ():
        for item in str(value).split(","):
            key = item.strip()
            if key not in GROUP_KEYS:
                raise MailqueryError(
                    "E_USAGE",
                    f"unknown key '{key}' in --group-by",
                    f"valid keys: {_SEARCH_GROUP_KEYS_TEXT}; at most two",
                    "invalid --group-by value",
                )
            if key in keys:
                raise MailqueryError(
                    "E_USAGE",
                    f"duplicate key '{key}' in --group-by",
                    f"valid keys: {_SEARCH_GROUP_KEYS_TEXT}; at most two",
                    "invalid --group-by value",
                )
            keys.append(key)
    if len(keys) > GROUP_MAX_KEYS:
        raise MailqueryError(
            "E_USAGE",
            "--group-by accepts at most two keys",
            f"valid keys: {_SEARCH_GROUP_KEYS_TEXT}; at most two",
            "invalid --group-by value",
        )
    only_count = bool(getattr(args, "count", False))
    limit = getattr(args, "limit", None)
    if only_count and (
        getattr(args, "fields", None) is not None or keys or limit is not None
    ):
        raise MailqueryError(
            "E_USAGE",
            "--count cannot be combined with --fields, --group-by or --limit",
            "use --count alone, or drop it to list the messages",
            "invalid --count combination",
        )
    if keys and limit is not None and not 0 <= int(limit) <= GROUP_MAX_LIMIT:
        raise MailqueryError(
            "E_USAGE",
            f"invalid --limit {int(limit)} with --group-by: expected 0 to 50",
            "use --limit between 0 and 50 messages per group",
            "invalid --limit value",
        )
    return tuple(keys), only_count


def _attachment_selection(args: argparse.Namespace) -> list[int] | None:
    """Exactly one of ``--index``/``--all`` and a positive integer index."""
    has_index = getattr(args, "index", None) is not None
    if has_index == bool(getattr(args, "all", False)):
        raise MailqueryError(
            "E_USAGE",
            "attachment requires exactly one of --index or --all",
            "pass --index N to recover one attachment or --all to recover all of them",
            "attachment arguments are invalid",
        )
    if not has_index:
        return None
    raw = str(args.index)
    if not raw.isascii() or not raw.isdigit() or int(raw) < 1:
        raise MailqueryError(
            "E_USAGE",
            f"invalid --index {raw}: expected a positive integer (1 or greater)",
            "run `mailquery show <uid>` to list the attachment indexes",
            "invalid attachment index",
        )
    return [int(raw)]


def _require_attachments_enabled(config: Config) -> None:
    """``[attachments].enabled`` only gates the ``attachment`` command."""
    if config.attachments.enabled:
        return
    raise MailqueryError(
        "E_ATTACHMENTS_DISABLED",
        "attachment recovery is disabled: [attachments].enabled = false",
        "set [attachments].enabled = true in ~/.mailquery/config.toml to allow "
        "attachment recovery",
        "attachment recovery is disabled",
    )


def _require_attachment_capabilities(instance: Any, driver: str) -> None:
    """Only a driver that can materialize attachments may continue."""
    capabilities = getattr(instance, "capabilities", None) or {}
    mode = str(capabilities.get("attachments", "local"))
    if mode != "none":
        return
    raise MailqueryError(
        "E_ATTACHMENT_UNAVAILABLE",
        f"attachment recovery is unsupported by driver {driver!r}",
        'install or declare a driver with attachments = "local" or "remote" in the '
        "[scope] blocks of ~/.mailquery/config.toml",
        "attachment recovery is unsupported by the driver",
    )


def _attachment_timeout(config: Config) -> float:
    """Per-attachment extraction budget in seconds (``[attachments].timeout_seconds``)."""
    return float(config.attachments.timeout_seconds)


def _attachment_stream_guard(driver: str) -> AttachmentStreamGuard | None:
    """Bound the attachment stream of an external driver (``None`` for built-ins).

    The built-in drivers keep their SQLite/COM objects in the calling thread and
    are only checked between blocks; an external plugin is waited on in a
    worker thread with the remaining per-attachment budget.
    """
    if driver in RESERVED_DRIVER_NAMES:
        return None
    return AttachmentStreamGuard(driver)


def _attachment_not_found(uid: str) -> MailqueryError:
    """``E_USAGE`` for an attachment uid that does not resolve to a visible message."""
    return MailqueryError(
        "E_USAGE",
        f"message uid {uid} was not found",
        "run `mailquery search` to find the uid; deleted messages and orphan "
        ".emlx files are not shown",
        "message uid was not found",
    )


def _attachment_out_of_range(uid: str, index: int, count: int) -> MailqueryError:
    """``E_USAGE`` for an attachment index outside ``1..count`` of the message."""
    return MailqueryError(
        "E_USAGE",
        f"attachment index {index} is out of range: message {uid} has "
        f"{count} attachment(s) (valid: 1..{count})",
        f"run `mailquery show {uid}` to list the attachment indexes",
        "attachment index out of range",
    )


def _attachment_instance(
    args: argparse.Namespace, backend: Any, drivers: Mapping[str, Any]
) -> Any:
    """The already opened driver of the uid prefix (native backend or declared plugin)."""
    driver = str(getattr(args, "uid_driver", "") or "")
    if backend is not None and str(getattr(backend, "driver", "") or "") == driver:
        return backend
    instance = drivers.get(driver)
    if instance is None:  # pragma: no cover - the CLI always opens the target driver
        raise uid_module.driver_unknown(driver)
    return instance


def _run_attachment(
    args: argparse.Namespace,
    config: Config,
    home_path: Path,
    backend: Any,
    drivers: Mapping[str, Any],
    native: str | None,
) -> dict:
    """Run the ``attachment`` command on the opened driver of the uid.

    The CLI resolves the account/scope, checks the message and its attachment
    indexes and hands the extraction to ``AttachmentsEngine`` with the
    configured per-attachment budget (``[attachments].timeout_seconds``). The
    success payload carries ``uid``, ``output_dir``, ``count``, ``attachments``
    and ``warnings``; the engine returns one record per requested attachment and
    every delivered file is scanned for active-content markers afterwards, so
    the warning never consumes the extraction budget.
    """
    driver = str(getattr(args, "uid_driver", "") or "")
    native_uid = getattr(args, "uid", None)
    show_uid = uid_module.format_uid(
        driver, str(getattr(args, "uid_native_id", ""))
    )
    instance = _attachment_instance(args, backend, drivers)
    wrapped = wrap_driver(instance, driver=driver)
    target_config = _config_for_driver(config, driver, str(native or driver))
    excluded: list[dict] = []
    resolved = _resolved_scope(target_config, wrapped, excluded, native=driver)
    declared = {_scope_account_uuid(scope) for scope in resolved}
    try:
        found = wrapped.find_message(native_uid)
    except ExcludedStoreError as exc:
        raise _excluded_store_error(show_uid, exc.entry) from None
    if found is None:
        raise _attachment_not_found(show_uid)
    _row, mailbox = found
    account_uuid = mailbox["account_uuid"] if mailbox is not None else ""
    if not account_uuid:
        raise _attachment_not_found(show_uid)
    if account_uuid not in declared:
        raise MailqueryError(
            "E_ACCOUNT_NOT_IN_SCOPE",
            f"message uid {show_uid} belongs to account {account_uuid!r}, "
            "which is not declared in config.toml",
            "only accounts declared with a [scope.<account>] block are read; "
            "declare the account in ~/.mailquery/config.toml",
            "the message belongs to an account that is not declared",
        )
    # The driver may raise the protocol error when the message is S/MIME or
    # unreadable; the ``wrap_driver`` wrapper maps it to a core error.
    entries = list(wrapped.attachments(native_uid) or [])
    if not entries:
        raise MailqueryError(
            "E_USAGE",
            f"message {show_uid} has no attachments",
            "the message does not have any attachment to recover",
            "the message has no attachments",
        )
    indices = getattr(args, "attachment_indices", None)
    if indices is not None:
        available = {
            int(entry.get("index"))
            for entry in entries
            if isinstance(entry, Mapping) and entry.get("index") is not None
        }
        for value in indices:
            if value not in available:
                raise _attachment_out_of_range(show_uid, value, len(entries))
    engine = AttachmentsEngine(
        home_path,
        config.attachments,
        wrapped,
        stream_guard=_attachment_stream_guard(driver),
    )
    timeout = _attachment_timeout(config)
    deadline = lambda: time.monotonic() + timeout  # noqa: E731
    records = engine.recover(
        show_uid,
        indices,
        force=bool(getattr(args, "force", False)),
        deadline=deadline,
        entries=entries,
    )
    payload_entries = [
        {
            "index": int(record["index"]),
            "original_name": sanitize_text(str(record["original_name"])),
            "sanitized_name": str(record["sanitized_name"]),
            "saved": bool(record["saved"]),
            "cached": bool(record["cached"]),
            "path": str(record["path"]),
            "size_bytes": int(record["size_bytes"]),
            "sha256": str(record["sha256"]),
        }
        for record in records
    ]
    warnings = [
        W_ATTACHMENT_ACTIVE_CONTENT.format(
            index=int(record["index"]), kind=kind, uid=show_uid
        )
        for record in records
        for kind in active_content_types(Path(str(record["path"])))
    ]
    return {
        "uid": show_uid,
        "output_dir": str(message_dir(home_path, show_uid)),
        "count": len(payload_entries),
        "attachments": payload_entries,
        "warnings": warnings,
    }


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


def _build_filters(
    args: argparse.Namespace, *, group_by: Sequence[str] = ()
) -> Filters:
    """Build the filters of ``search``; with grouping, ``--limit`` is per group.

    ``--group-by`` validates its own ``--limit`` range (0 to 50) before the
    home exists, so the flat 1 to 200 range does not apply to it.
    """
    if group_by:
        limit = None if args.limit is None else int(args.limit)
    else:
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
    """Wrap a command payload with the success keys, the notice and sanitized warnings.

    The fixed content notice follows ``generated_at`` for the commands that
    return message content. Every warning string loses terminal escapes and
    invisible characters; warnings never carry content beyond the identifier
    they cite.
    """
    merged: dict[str, Any] = {
        "ok": True,
        "command": command,
        "generated_at": now_iso(),
    }
    if command in _CONTENT_NOTICE_COMMANDS:
        merged["content_notice"] = CONTENT_NOTICE
    for key, value in payload.items():
        if key in _PAYLOAD_RESERVED_KEYS:
            continue
        merged[key] = value
    merged.setdefault("warnings", [])
    merged["warnings"] = [
        sanitize_text(str(warning)) for warning in (merged.get("warnings") or ())
    ]
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
    failures: bool = False,
) -> int:
    level, max_size_mb = _doctor_log_settings(home_path, log_level)
    logger = _best_effort_logger(home_path, level, max_size_mb)
    selected = None
    run = _DoctorRun(home_path)
    client = _CLIENT_NAMES["apple_mail"]
    checks: list[dict] = []
    try:
        selected = _make_backend(home_path, mail_root, accounts_db, backend)
        client = _CLIENT_NAMES.get(str(getattr(selected, "driver", "")), client)
        _bind_command(selected, "doctor")
        _bind_doctor_timeout(selected, run, json_output, logger, client, failures)
        registry = BackendRegistry()
        checks = _collect_doctor_checks(home_path, selected, run, registry=registry)
    except Exception as exc:  # noqa: BLE001 - doctor never raises
        checks = [{"name": "doctor", "ok": False, "detail": error_detail(exc)}]
    finally:
        _close_backend(selected)
    _emit_doctor_report(
        checks, list(run.plugins), json_output, logger, client, failures=failures
    )
    return 0


def _bind_doctor_timeout(
    backend: Any,
    run: "_DoctorRun",
    json_output: bool,
    logger: Any,
    client: str,
    failures: bool = False,
) -> None:
    """``doctor`` (Outlook): on a COM timeout, complete the report and exit 0.

    The hook runs in the watchdog thread while the main thread is blocked in
    COM: it completes the checks (the running check with the
    timeout text, its dependents ``not evaluated``), writes the report in the
    ``checks[]`` order, flushes and ends the process with ``os._exit(0)``. The
    plugin sections were already calculated, so the report keeps them whole.
    """
    bind = getattr(backend, "bind_doctor_timeout", None)
    if not callable(bind):
        return

    def finish(backend_checks: list[dict] | None, detail: str) -> None:
        try:
            checks = run.after_timeout(backend, backend_checks, detail)
            _emit_doctor_report(
                checks,
                list(run.plugins),
                json_output,
                logger,
                client,
                failures=failures,
            )
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
    checks: list[dict],
    plugins: list[dict],
    json_output: bool,
    logger: Any,
    client: str,
    *,
    failures: bool = False,
) -> None:
    """Write the doctor payload (JSON or text report) and log the end line.

    With ``failures`` the payload keeps only the checks that fail and the ones
    not evaluated, plus the ``not_evaluated`` names after ``checks``; the same
    filtering applies to every plugin section. Checks and plugins are always
    calculated whole, so ``failures`` only changes what is shown.
    """
    total_checks, passed_checks = _doctor_totals(checks, plugins)
    if failures:
        kept_checks, not_evaluated = _filter_doctor_checks(checks)
        kept_plugins = _filter_doctor_plugins(plugins)
        payload = _success_payload(
            "doctor",
            {
                "checks": kept_checks,
                "not_evaluated": not_evaluated,
                "plugins": kept_plugins,
                "warnings": [],
            },
        )
    else:
        payload = _success_payload(
            "doctor", {"checks": checks, "plugins": plugins, "warnings": []}
        )
    if json_output:
        write_json(payload)
    else:
        sys.stdout.write(
            _render_doctor_report(
                payload,
                client=client,
                failures=failures,
                totals=(passed_checks, total_checks),
            )
            + "\n"
        )
        sys.stdout.flush()
    if logger is not None:
        logger.info(
            "event=end command=doctor exit_code=0 checks=%d/%d",
            passed_checks,
            total_checks,
        )


def _doctor_totals(checks: list[dict], plugins: list[dict]) -> tuple[int, int]:
    """Total and passed checks of the whole report, plugin checks included."""
    every = list(checks) + [
        check
        for plugin in plugins
        for check in (plugin.get("checks") or [])
        if isinstance(check, dict)
    ]
    return len(every), sum(1 for check in every if check.get("ok"))


def _filter_doctor_checks(checks: list[dict]) -> tuple[list[dict], list[str]]:
    """Split ``checks`` into the failing ones and the names of the not evaluated.

    A check whose ``detail`` is exactly ``not evaluated: <check> failed`` was
    skipped because a check it depends on failed; any other ``ok: false`` check
    (a real failure or ``not evaluated: <concrete cause>``) is kept.
    """
    failing: list[dict] = []
    not_evaluated: list[str] = []
    for check in checks:
        if check.get("ok"):
            continue
        detail = str(check.get("detail", ""))
        if _NOT_EVALUATED_DETAIL.match(detail):
            not_evaluated.append(str(check.get("name", "")))
        else:
            failing.append(check)
    return failing, not_evaluated


def _filter_doctor_plugins(plugins: list[dict]) -> list[dict]:
    """Keep the plugins with a failing check or with a check not evaluated."""
    kept: list[dict] = []
    for plugin in plugins:
        failing, not_evaluated = _filter_doctor_checks(plugin.get("checks") or [])
        if not failing and not not_evaluated:
            continue
        kept.append(
            {
                "driver": plugin.get("driver", ""),
                "checks": failing,
                "not_evaluated": not_evaluated,
            }
        )
    return kept


def _render_doctor_report(
    payload: dict,
    *,
    client: str = "Apple Mail",
    failures: bool = False,
    totals: tuple[int, int] | None = None,
) -> str:
    """Render the doctor payload as a human-readable report in help style."""
    checks = [check for check in payload.get("checks") or [] if isinstance(check, dict)]
    plugins = [
        plugin for plugin in payload.get("plugins") or [] if isinstance(plugin, dict)
    ]
    warnings = [str(warning) for warning in payload.get("warnings") or []]
    width = _help_width()
    every_check = list(checks) + [
        check
        for plugin in plugins
        for check in (plugin.get("checks") or [])
        if isinstance(check, dict)
    ]
    name_width = min(
        20, max((len(str(check.get("name", ""))) for check in every_check), default=0)
    )

    lines = [
        "mailquery doctor - environment and read-only diagnosis",
        f"Generated at: {payload.get('generated_at', now_iso())}",
        "",
    ]
    if failures:
        lines.extend(
            _render_failure_sections(
                payload, checks, plugins, name_width=name_width, width=width
            )
        )
    else:
        lines.append("Checks:")
        lines.extend(_render_check_rows(checks, name_width=name_width, width=width))
        for plugin in plugins:
            lines.append("")
            lines.append("Plugins:")
            lines.append(f"  {plugin.get('driver', '')}")
            lines.extend(
                _render_check_rows(
                    plugin.get("checks") or [],
                    name_width=name_width,
                    width=width,
                    indent="    ",
                )
            )

    if totals is None:
        passed = sum(1 for check in every_check if check.get("ok"))
        total = len(every_check)
    else:
        passed, total = totals
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


def _render_failure_sections(
    payload: dict,
    checks: list[dict],
    plugins: list[dict],
    *,
    name_width: int,
    width: int,
) -> list[str]:
    """Sections of ``doctor --failures``: only failures and the not evaluated line."""
    sections: list[list[str]] = []
    top_rows = _render_check_rows(checks, name_width=name_width, width=width)
    top_not_evaluated = [str(name) for name in payload.get("not_evaluated") or []]
    if top_not_evaluated:
        top_rows.append(f"not evaluated: {', '.join(top_not_evaluated)}")
    if top_rows:
        sections.append(["Checks:", *top_rows])
    for plugin in plugins:
        rows = _render_check_rows(
            plugin.get("checks") or [], name_width=name_width, width=width, indent="    "
        )
        names = [str(name) for name in plugin.get("not_evaluated") or []]
        if names:
            rows.append(f"    not evaluated: {', '.join(names)}")
        if rows:
            sections.append(["Plugins:", f"  {plugin.get('driver', '')}", *rows])
    if not sections:
        return ["Checks:", "all checks passed"]
    joined: list[str] = []
    for index, section in enumerate(sections):
        if index:
            joined.append("")
        joined.extend(section)
    return joined


def _render_check_rows(
    checks: list[dict],
    *,
    name_width: int,
    width: int,
    indent: str = "  ",
) -> list[str]:
    """One aligned row per check, wrapping ``detail`` to the help width."""
    rows: list[str] = []
    for check in checks:
        if not isinstance(check, dict):
            continue
        ok = bool(check.get("ok"))
        status = "[ok]  " if ok else "[FAIL]"
        name = str(check.get("name", ""))
        detail = str(check.get("detail", "")).replace("\n", " ").strip()
        prefix = f"{indent}{status} {name.ljust(name_width)}  "
        wrapped = textwrap.wrap(detail, width=max(20, width - len(prefix))) or [""]
        rows.append(prefix + wrapped[0])
        for extra in wrapped[1:]:
            rows.append(" " * len(prefix) + extra)
    return rows


class _DoctorRun:
    """Progress of one ``doctor`` run, shared with the COM timeout hook.

    ``checks`` holds the finished common checks by name, ``backend_checks`` the
    backend's once they are done, ``config`` the parsed ``config.toml``,
    ``driver_ok`` the outcome of the ``driver`` check per declared driver and
    ``plugins`` the plugin sections, calculated before the backend checks so a
    COM timeout still reports them whole.
    """

    def __init__(self, home_path: Path) -> None:
        self.home_path = home_path
        self.checks: dict[str, dict] = {}
        self.backend_checks: list[dict] | None = None
        self.config: Config | None = None
        self.config_error: Exception | None = None
        self.driver_ok: dict[str, bool] = {}
        self.plugins: list[dict] = []

    def record(self, name: str, ok: bool, detail: str) -> None:
        self.checks[name] = {"name": name, "ok": bool(ok), "detail": str(detail)}

    def ordered(self) -> list[dict]:
        """``python``, ``home``, ``driver``, the backend's, then ``config``, ``state``, ``lock``."""
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
        """The report after a COM timeout, without calling the mail client again.

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
    """Common checks plus ``backend.doctor_checks()``, in report order.

    Evaluation order: the checks that never call the mail client first
    (``python``, ``home``, ``config`` syntax, ``driver``, ``state``, ``lock``),
    then the plugin sections (each plugin call has its own deadline) and last
    the backend checks and the ``config`` resolution.
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
                continue  # POSIX modes are meaningless on Windows
            mode = stat.S_IMODE(directory.stat().st_mode)
            if mode != 0o700:
                problems.append(f"{directory.name or directory} mode={oct(mode)}")
        if windows and not problems:
            # Windows: the home must exist and be writable (probe file).
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

    # plugins (before the backend checks: each plugin call has its own deadline)
    run.plugins = _collect_plugin_sections(run, backend, registry)

    # backend checks (store/pywin32, ..., accounts_db/object_model_guard) ------
    try:
        backend_checks = [dict(check) for check in backend.doctor_checks()]
    except Exception as exc:  # noqa: BLE001 - diagnostics only
        backend_checks = [{"name": "backend", "ok": False, "detail": error_detail(exc)}]
    run.backend_checks = backend_checks

    # config resolution --------------------------------------------------------
    _record_config_check(run, backend)
    return run.ordered()


def _collect_plugin_sections(
    run: _DoctorRun, backend: Any, registry: BackendRegistry
) -> list[dict]:
    """One ``{"driver", "checks"}`` section per external driver declared in ``[scope]``.

    The order is the first block of each driver. A plugin that did not pass the
    common ``driver`` check is not opened: its only check is ``config`` with
    ``not evaluated: driver failed``. A plugin that cannot be opened, whose
    ``doctor_checks()`` fails (exception, invalid result or timeout) or whose
    ``config`` blocks do not resolve reports ``ok: false`` and the rest of the
    report is unchanged. Every plugin is closed when its section is done.
    """
    if run.config is None:
        return []
    native = _backend_driver_name(backend)
    sections: list[dict] = []
    for driver in declared_drivers(run.config, native=native or None):
        if driver == native:
            continue
        if not run.driver_ok.get(driver, True):
            checks = [
                {"name": "config", "ok": False, "detail": "not evaluated: driver failed"}
            ]
        else:
            checks = _plugin_checks(run.home_path, run.config, driver, registry)
        sections.append({"driver": driver, "checks": checks})
    return sections


def _plugin_checks(
    home_path: Path, config: Config, driver: str, registry: BackendRegistry
) -> list[dict]:
    """Checks of one declared plugin: its ``doctor_checks()``, then ``config``."""
    checks: list[dict] = []
    instance: Any = None
    context = PluginContext(home=home_path, tmp_dir=home_path / "tmp")
    try:
        instance = registry.open_drivers([driver], context=context)[driver]
    except Exception as exc:  # noqa: BLE001 - diagnostics only
        checks.append(
            {"name": "plugin", "ok": False, "detail": _plugin_failure_detail(driver, exc)}
        )
        checks.append(
            {"name": "config", "ok": False, "detail": "not evaluated: plugin failed"}
        )
        return checks
    try:
        returned = call_driver(
            "doctor_checks", lambda: instance.doctor_checks(), driver=driver
        )
    except Exception as exc:  # noqa: BLE001 - diagnostics only
        checks.append(
            {"name": "plugin", "ok": False, "detail": _plugin_failure_detail(driver, exc)}
        )
    else:
        if _valid_doctor_checks(returned):
            checks.extend(
                {
                    "name": item["name"],
                    "ok": item["ok"],
                    "detail": item["detail"],
                }
                for item in returned
            )
        else:
            checks.append(
                {
                    "name": "plugin",
                    "ok": False,
                    "detail": (
                        f"E_PLUGIN_FAILED: driver '{driver}' returned an invalid "
                        "result for doctor_checks"
                    ),
                }
            )
    try:
        checks.append(_plugin_config_check(config, driver, instance))
    finally:
        _close_backend(instance)
    return checks


def _valid_doctor_checks(value: Any) -> bool:
    """Whether ``doctor_checks()`` returned a list of valid plugin checks.

    Every item is a mapping with exactly ``name``, ``ok`` and ``detail``; the
    name is unique in the plugin, is not one of the names the core owns and the
    detail is one line.
    """
    if not isinstance(value, (list, tuple)):
        return False
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, Mapping) or set(item) != {"name", "ok", "detail"}:
            return False
        name = item["name"]
        if not isinstance(name, str) or name in _DOCTOR_PLUGIN_RESERVED_CHECKS:
            return False
        if name in seen:
            return False
        seen.add(name)
        if not isinstance(item["ok"], bool):
            return False
        detail = item["detail"]
        if not isinstance(detail, str) or "\n" in detail or "\r" in detail:
            return False
    return True


def _plugin_failure_detail(driver: str, exc: Exception) -> str:
    """One-line detail of a failing plugin check: ``E_PLUGIN_FAILED: …`` or the timeout."""
    if isinstance(exc, MailqueryError):
        if exc.code == "E_CLIENT_TIMEOUT":
            return f"timeout after 30 s: plugin '{driver}' did not respond"
        hint = f" (hint: {exc.hint})" if exc.hint else ""
        return f"E_PLUGIN_FAILED: {exc.message}{hint}"
    return f"E_PLUGIN_FAILED: {error_detail(exc)}"


def _plugin_config_check(config: Config, driver: str, instance: Any) -> dict:
    """``config`` of one plugin: resolve its ``[scope]`` blocks with its own API.

    The detail and the errors use the format of the native ``config`` check
    (``<key> → <label> (<uuid>): INBOX, …`` or ``<key>: <code>: <message>
    (hint: …)``). The ``accounts``/``mailboxes``/``resolve_mailbox`` calls go
    through the driver wrapper, so each one has the plugin deadline.
    """
    try:
        wrapped = wrap_driver(instance, driver=driver)
        filtered = _config_for_driver(config, driver, driver)
        problems: list[str] = []
        lines: list[str] = []
        for entry in filtered.scopes:
            try:
                resolved = resolve_scope(
                    replace(filtered, scopes=(entry,)), wrapped, native=driver
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
        if problems:
            return {"name": "config", "ok": False, "detail": "; ".join(problems)}
        detail = "; ".join(lines) or f"0 account block(s) declared for driver {driver}"
        return {"name": "config", "ok": True, "detail": detail}
    except Exception as exc:  # noqa: BLE001 - diagnostics only
        return {"name": "config", "ok": False, "detail": error_detail(exc)}


def _backend_driver_name(backend: Any) -> str:
    """Driver of the backend under diagnosis (protocol v1 ``driver``; tolerant of doubles)."""
    driver = getattr(backend, "driver", None)
    return str(driver) if driver else ""


def _bool_text(value: Any) -> str:
    """``true``/``false`` for the doctor detail."""
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)


def _format_driver_metadata(metadata: dict[str, Any]) -> str:
    """One ``driver`` detail entry: api, package version and the capability map."""
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
    """Failure entry of the ``driver`` check: reason and hint of the error."""
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
    """``driver``: every declared driver is installed with a valid API 1 contract.

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
        driver_ok = True
        try:
            if driver == native:
                metadata = _native_driver_metadata(backend, registry)
            else:
                metadata = registry.info(driver)
        except Exception as exc:  # noqa: BLE001 - diagnostics only
            driver_ok = False
            ok = False
            details.append(_driver_failure_detail(driver, exc))
        else:
            details.append(_format_driver_metadata(metadata))
        run.driver_ok[driver] = driver_ok
    if suffix:
        details.append(suffix)
    run.record("driver", ok, "; ".join(details) or "no declared drivers")


def _record_config_check(run: _DoctorRun, backend: Any) -> None:
    """``config``: syntax plus the resolution of the ``[scope]`` blocks.

    The resolution depends first on the ``driver`` check and then on a
    check of the backend; when one failed, the mail client is
    not called and the detail says ``not evaluated: <check> failed``. Blocks of
    a driver other than the native one are not resolved here (their plugin
    section resolves them), so a config with only plugin blocks reports
    ``0 account block(s) declared for driver <native>`` with ``ok=true``. A
    declared account that resolves to an excluded store (Outlook) adds
    ``W_STORE_EXCLUDED`` to the detail, which keeps ``ok=true``.
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
                        # Blocks of another driver are resolved by that plugin's
                        # own ``config`` check; the native check never lists them.
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
            # W_STORE_EXCLUDED of each declared excluded store, once.
            lines.extend(_store_excluded_warning(entry) for entry in excluded)
            if problems:
                run.record("config", False, "; ".join(problems))
            elif lines:
                run.record("config", True, "; ".join(lines))
            else:
                # Every block belongs to another driver: the native check
                # declares none and the plugin sections resolve them.
                run.record(
                    "config", True, f"0 account block(s) declared for driver {native}"
                )
    except Exception as exc:  # noqa: BLE001 - diagnostics only
        run.record("config", False, error_detail(exc))


# --------------------------------------------------------------------------- #
# Rendering, logging and small helpers
# --------------------------------------------------------------------------- #


def _report_error(error: MailqueryError, command: str | None) -> int:
    """Write the error JSON and the human summary, both with the sanitized texts."""
    payload = error.to_payload(command or "-")
    write_json(payload)
    message = payload["error"]["message"]
    hint = payload["error"]["hint"]
    sys.stderr.write(f"mailquery: {error.code}: {message}\n")
    if hint:
        sys.stderr.write(f"mailquery: hint: {hint}\n")
    sys.stderr.flush()
    return error.exit_code


def _log_error(logger: Any, command: str, error: MailqueryError) -> None:
    if logger is None:
        return
    # Never log message/hint: they may contain account emails, folders or paths.
    # ``log_message`` is the text without that data; fall back to the
    # plain message only when the error carries no sanitized variant.
    text = error.log_message if error.log_message is not None else error.message
    if error.code == "E_INTERNAL" and error.__traceback__ is not None:
        # An E_INTERNAL (a COM failure included) also logs its traceback.
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

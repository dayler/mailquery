"""MCP server over stdio: protocol, generated tools and child-process calls.

The server speaks the subset of MCP that a tool server needs (``initialize``,
``ping``, ``tools/list`` and ``tools/call``) with the standard library. Tools
are generated from the CLI parser, and every call runs ``mailquery <command>``
as a child process, so the CLI remains the only execution path. Nothing that
is not a protocol message is written to the output stream.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence, TextIO

from mailquery import __version__
from mailquery.errors import MailqueryError
from mailquery.logging_setup import get_logger, log_event
from mailquery.output import dumps_json

#: Protocol versions the server accepts, oldest first.
PROTOCOL_VERSIONS = ("2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25")
LATEST_PROTOCOL_VERSION = PROTOCOL_VERSIONS[-1]

#: Tools exposed by the server, in ``tools/list`` order.
TOOL_NAMES = ("search", "new", "show", "attachment", "mailboxes", "doctor")

#: Parameters that are not exposed, by tool.
_HIDDEN_PARAMETERS: dict[str, frozenset[str]] = {
    "doctor": frozenset({"json"}),
    "show": frozenset({"show_native_id"}),
}

#: ``--show-native-id`` and ``--help`` are never part of a schema.
_SKIPPED_ACTIONS = frozenset({"help", "show_native_id", "json"})

_MAX_WINDOWS_COMMAND_LINE = 32_767
_DEFAULT_ARG_MAX = 131_072

_INTERNAL_MESSAGE = "the command did not write a JSON object"
_INTERNAL_HINT = "run `mailquery doctor` and check the mailquery log"

_PARSER: argparse.ArgumentParser | None = None
_DEFINITIONS: dict[str, dict] | None = None


@dataclass(frozen=True)
class ToolOutcome:
    """Result of one child process: captured stdout, exit code and duration."""

    stdout: str
    exit_code: int
    duration_ms: int


class ToolRunner(Protocol):
    """Executes one CLI invocation and returns its captured result."""

    def run(self, argv: Sequence[str]) -> ToolOutcome:
        """Run ``argv`` and return its outcome without a shell."""


class SubprocessToolRunner:
    """Real runner: one child process per call, without a shell."""

    def run(self, argv: Sequence[str]) -> ToolOutcome:
        """Launch ``argv`` with empty stdin, captured stdout and discarded stderr."""
        started = time.perf_counter()
        kwargs: dict[str, Any] = {
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.DEVNULL,
            "text": True,
            "encoding": "utf-8",
            "cwd": os.getcwd(),
            "env": dict(os.environ),
            "check": False,
        }
        if sys.platform == "win32":  # pragma: no cover - exercised on Windows only
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        completed = subprocess.run(list(argv), **kwargs)
        duration_ms = int((time.perf_counter() - started) * 1000)
        return ToolOutcome(
            stdout=completed.stdout or "",
            exit_code=int(completed.returncode),
            duration_ms=duration_ms,
        )


def serve(stdin: TextIO, stdout: TextIO, *, runner: ToolRunner) -> int:
    """Serve MCP messages from ``stdin`` until EOF, writing replies to ``stdout``."""
    parser = _default_parser()
    while True:
        try:
            line = _read_line(stdin)
        except UnicodeDecodeError:
            _write_message(stdout, _rpc_error(None, -32700, "Parse error"))
            continue
        if line is None:
            return 0
        for reply in _handle_line(line, parser, runner):
            _write_message(stdout, reply)


def tool_definitions(parser: argparse.ArgumentParser) -> list[dict]:
    """Return the JSON schema of every exposed tool, in ``tools/list`` order."""
    root_log_level = next(
        (action for action in parser._actions if action.dest == "log_level"), None
    )
    subparsers = _subparsers(parser)
    definitions = []
    for tool in TOOL_NAMES:
        subparser = subparsers.get(tool)
        if subparser is None:  # pragma: no cover - the CLI always defines them
            continue
        definitions.append(_tool_definition(tool, subparser, root_log_level))
    return definitions


def build_argv(tool: str, arguments: Mapping[str, Any]) -> list[str]:
    """Translate one ``tools/call`` argument map into CLI arguments.

    Raises :class:`MailqueryError` ``E_USAGE`` when a parameter is unknown, has
    the wrong type, contains NUL or makes the command line exceed the platform
    limit. The caller prepends the interpreter and ``-P -m mailquery``.
    """
    if tool not in TOOL_NAMES:
        raise _usage(tool, "", f"unknown tool {tool!r}")
    if not isinstance(arguments, Mapping):
        raise _usage(tool, "", "arguments must be an object")
    schema = _definitions()[tool]["inputSchema"]
    properties: dict[str, dict] = schema["properties"]
    argv: list[str] = []
    longest_key = ""
    longest_size = 0
    log_level = arguments.get("log_level")
    if log_level is not None:
        _validate_parameter(tool, "log_level", log_level, properties["log_level"])
        argv.append(f"--log-level={log_level}")
    argv.append(tool)
    required = schema.get("required") or []
    for name in properties:
        if name == "log_level":
            continue
        if name == "uid":
            continue
        if tool == "doctor" and name == "failures":
            continue
        if name not in arguments:
            continue
        value = arguments[name]
        _validate_parameter(tool, name, value, properties[name])
        size = len(str(value))
        if size > longest_size:
            longest_key, longest_size = name, size
        if properties[name]["type"] == "boolean":
            if value:
                argv.append(f"--{name.replace('_', '-')}")
            continue
        if properties[name]["type"] == "array":
            for element in value:
                argv.append(f"--{name.replace('_', '-')}={element}")
            continue
        argv.append(f"--{name.replace('_', '-')}={value}")
    for name in arguments:
        if name not in properties:
            raise _usage(tool, name, f"unknown parameter {name!r}")
    if "uid" in required:
        if "uid" not in arguments:
            raise _usage(tool, "uid", "the uid parameter is required")
        _validate_parameter(tool, "uid", arguments["uid"], properties["uid"])
        uid = str(arguments["uid"])
        if len(uid) > longest_size:
            longest_key, longest_size = "uid", len(uid)
        argv.append("--")
        argv.append(uid)
    if tool == "doctor":
        argv = _with_doctor_json(tool, arguments, argv)
    _check_argv_length(tool, argv, longest_key)
    return argv


def _with_doctor_json(
    tool: str, arguments: Mapping[str, Any], argv: list[str]
) -> list[str]:
    """Insert ``--json`` and ``--failures`` in the doctor argument list."""
    index = argv.index(tool) + 1
    flags = ["--json"]
    if arguments.get("failures"):
        flags.append("--failures")
    return [*argv[:index], *flags, *argv[index:]]


def _tool_definition(
    tool: str,
    subparser: argparse.ArgumentParser,
    root_log_level: argparse.Action | None,
) -> dict:
    """Build one tool definition from a CLI subparser."""
    properties: dict[str, dict] = {}
    required: list[str] = []
    if root_log_level is not None:
        properties["log_level"] = {
            "type": "string",
            "enum": list(root_log_level.choices or ()),
            "description": root_log_level.help or "",
        }
    hidden = _HIDDEN_PARAMETERS.get(tool, frozenset())
    uid_action = None
    for action in subparser._actions:
        if isinstance(action, argparse._HelpAction):
            continue
        name = _option_name(action)
        if name is not None:
            if name in _SKIPPED_ACTIONS or name in hidden:
                continue
            properties[name] = _parameter_schema(tool, name, action)
        elif action.dest == "uid":
            uid_action = action
    if uid_action is not None:
        properties["uid"] = {
            "type": "string",
            "description": uid_action.help or "",
        }
        required.append("uid")
    return {
        "name": tool,
        "description": subparser.description or "",
        "inputSchema": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
    }


def _option_name(action: argparse.Action) -> str | None:
    """Return the parameter name of an option, from its first long flag."""
    for option in action.option_strings:
        if option.startswith("--"):
            return option[2:].replace("-", "_")
    return None


def _parameter_schema(tool: str, name: str, action: argparse.Action) -> dict:
    """Return the JSON schema of one CLI option."""
    schema: dict[str, Any] = {
        "type": "string",
        "description": action.help or "",
    }
    if isinstance(action, argparse._StoreTrueAction) or isinstance(
        action, argparse._StoreFalseAction
    ):
        schema["type"] = "boolean"
        return schema
    if action.type is int or (tool == "attachment" and name == "index"):
        schema["type"] = "integer"
        return schema
    if action.choices:
        schema["enum"] = list(action.choices)
        return schema
    if isinstance(action, argparse._AppendAction):
        schema["type"] = "array"
        schema["items"] = {"type": "string"}
        return schema
    return schema


def _validate_parameter(tool: str, name: str, value: Any, schema: dict) -> None:
    """Validate one argument against its schema, raising ``E_USAGE``."""
    if isinstance(value, str) and "\x00" in value:
        raise _usage(tool, name, f"the parameter {name!r} contains a NUL character")
    expected = schema.get("type", "string")
    if expected == "boolean":
        if not isinstance(value, bool):
            raise _usage(tool, name, f"the parameter {name!r} must be a boolean")
        return
    if expected == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise _usage(tool, name, f"the parameter {name!r} must be an integer")
        return
    if expected == "array":
        if not isinstance(value, list) or any(
            not isinstance(element, str) for element in value
        ):
            raise _usage(
                tool, name, f"the parameter {name!r} must be an array of strings"
            )
        for element in value:
            if "\x00" in element:
                raise _usage(
                    tool, name, f"the parameter {name!r} contains a NUL character"
                )
        return
    if not isinstance(value, str):
        raise _usage(tool, name, f"the parameter {name!r} must be a string")
    enum = schema.get("enum")
    if enum is not None and value not in enum:
        raise _usage(
            tool,
            name,
            f"the parameter {name!r} must be one of: {', '.join(map(str, enum))}",
        )


def _check_argv_length(tool: str, argv: Sequence[str], longest_key: str) -> None:
    """Reject an argv above the platform limit before any child is launched."""
    message = _argv_too_long_message(longest_key)
    if sys.platform == "win32":  # pragma: no cover - exercised on Windows only
        line = subprocess.list2cmdline([sys.executable, "-P", "-m", "mailquery", *argv])
        if len(line) > _MAX_WINDOWS_COMMAND_LINE:
            raise _usage(tool, longest_key, message)
        return
    limit = _arg_max()
    total = sum(len(argument.encode("utf-8")) + 1 for argument in argv)
    total += len(sys.executable.encode("utf-8")) + len(b"-P") + len(b"-m") + len(
        b"mailquery"
    )
    for key, value in os.environ.items():
        total += len(key.encode("utf-8")) + len(value.encode("utf-8")) + 2
    if total > limit:
        raise _usage(tool, longest_key, message)


def _argv_too_long_message(longest_key: str) -> str:
    """Return the usage hint for an oversized command line."""
    if longest_key:
        return f"the command line is too long; shorten the parameter {longest_key!r}"
    return "the command line is too long; shorten the arguments"


def _arg_max() -> int:
    """Return the POSIX argument size limit, or a conservative default."""
    try:
        return int(os.sysconf("SC_ARG_MAX"))
    except (AttributeError, OSError, ValueError):  # pragma: no cover - platform specific
        return _DEFAULT_ARG_MAX


def _usage(tool: str, parameter: str, message: str) -> MailqueryError:
    """Build the ``E_USAGE`` error of a rejected parameter."""
    hint = f"the parameter {parameter!r} is not accepted" if parameter else message
    return MailqueryError("E_USAGE", message, hint)


def _handle_line(
    line: str, parser: argparse.ArgumentParser, runner: ToolRunner
) -> list[dict]:
    """Handle one JSON-RPC line and return the replies to write."""
    try:
        message = json.loads(line)
    except (ValueError, TypeError):
        return [_rpc_error(None, -32700, "Parse error")]
    if isinstance(message, list):
        if not message:
            return [_rpc_error(None, -32600, "Invalid Request")]
        replies: list[dict] = []
        for element in message:
            if not isinstance(element, dict):
                replies.append(_rpc_error(None, -32600, "Invalid Request"))
                continue
            reply = _handle_message(element, parser, runner)
            if reply is not None:
                replies.append(reply)
        return [replies] if replies else []
    if not isinstance(message, dict):
        return [_rpc_error(None, -32600, "Invalid Request")]
    reply = _handle_message(message, parser, runner)
    return [] if reply is None else [reply]


def _handle_message(
    message: dict, parser: argparse.ArgumentParser, runner: ToolRunner
) -> dict | None:
    """Handle one JSON-RPC object; notifications return ``None``."""
    has_id = "id" in message
    request_id = message.get("id")
    method = message.get("method")
    if not isinstance(method, str):
        return _rpc_error(request_id if has_id else None, -32600, "Invalid Request")
    if method == "initialize":
        if not has_id:
            return None
        return _result(request_id, _initialize(message.get("params")))
    if method == "ping":
        if not has_id:
            return None
        return _result(request_id, {})
    if method == "tools/list":
        if not has_id:
            return None
        return _result(request_id, {"tools": tool_definitions(parser)})
    if method == "tools/call":
        if not has_id:
            return None
        return _tools_call(request_id, message.get("params"), parser, runner)
    if method.startswith("notifications/") or not has_id:
        return None
    return _rpc_error(request_id, -32601, "Method not found")


def _initialize(params: Any) -> dict:
    """Return the ``initialize`` result for the requested protocol version."""
    requested = params.get("protocolVersion") if isinstance(params, dict) else None
    version = requested if requested in PROTOCOL_VERSIONS else LATEST_PROTOCOL_VERSION
    return {
        "protocolVersion": version,
        "capabilities": {"tools": {}},
        "serverInfo": {"name": "mailquery", "version": __version__},
    }


def _tools_call(
    request_id: Any,
    params: Any,
    parser: argparse.ArgumentParser,
    runner: ToolRunner,
) -> dict:
    """Handle ``tools/call``: validate, run one child and wrap its JSON."""
    if not isinstance(params, dict):
        return _rpc_error(request_id, -32602, "Invalid params")
    name = params.get("name")
    if not isinstance(name, str) or name not in TOOL_NAMES:
        return _rpc_error(request_id, -32602, "Invalid params")
    arguments = params.get("arguments", {})
    if not isinstance(arguments, dict):
        return _rpc_error(request_id, -32602, "Invalid params")
    try:
        cli_arguments = build_argv(name, arguments)
    except MailqueryError as exc:
        return _result(request_id, _error_result(name, exc))
    argv = [sys.executable, "-P", "-m", "mailquery", *cli_arguments]
    started = time.perf_counter()
    try:
        outcome = runner.run(argv)
    except Exception:  # noqa: BLE001 - a launch failure is a call failure
        outcome = ToolOutcome(
            stdout="",
            exit_code=1,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        _log_call(name, outcome)
        return _result(request_id, _internal_result(name, outcome))
    _log_call(name, outcome)
    text = outcome.stdout[:-1] if outcome.stdout.endswith("\n") else outcome.stdout
    try:
        payload = json.loads(text)
    except (ValueError, TypeError):
        payload = None
    if not isinstance(payload, dict):
        return _result(request_id, _internal_result(name, outcome))
    return _result(
        request_id,
        {
            "content": [{"type": "text", "text": text}],
            "isError": outcome.exit_code != 0,
        },
    )


def _log_call(tool: str, outcome: ToolOutcome) -> None:
    """Log one completed tool call with its tool, exit code and duration."""
    log_event(
        get_logger("mailquery.mcp"),
        logging.INFO,
        (
            ("event", "call"),
            ("tool", tool),
            ("exit_code", outcome.exit_code),
            ("duration_ms", outcome.duration_ms),
        ),
    )


def _internal_result(tool: str, outcome: ToolOutcome) -> dict:
    """Return the ``E_INTERNAL`` tool result for a child that broke the contract."""
    error = MailqueryError("E_INTERNAL", _INTERNAL_MESSAGE, _INTERNAL_HINT)
    return _error_result(tool, error)


def _error_result(tool: str, error: MailqueryError) -> dict:
    """Wrap a mailquery error as a tool result with the CLI JSON format."""
    return {
        "content": [{"type": "text", "text": dumps_json(error.to_payload(tool))}],
        "isError": True,
    }


def _result(request_id: Any, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _rpc_error(request_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _read_line(stdin: TextIO) -> str | None:
    """Read one UTF-8 line and strip its line ending; ``None`` at EOF.

    The raw buffer is read when the stream exposes one, so an invalid line
    cannot discard the bytes of the lines that follow it.
    """
    buffer = getattr(stdin, "buffer", None)
    if buffer is not None:
        data = buffer.readline()
        if data == b"":
            return None
        if data.endswith(b"\r\n"):
            data = data[:-2]
        elif data.endswith(b"\n"):
            data = data[:-1]
        return data.decode("utf-8")
    line = stdin.readline()
    if line == "":
        return None
    if line.endswith("\r\n"):
        return line[:-2]
    if line.endswith("\n"):
        return line[:-1]
    return line


def _write_message(stdout: TextIO, message: dict) -> None:
    """Write one compact UTF-8 JSON message followed by LF and flush it."""
    stdout.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n")
    stdout.flush()


def _subparsers(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    return {}


def _default_parser() -> argparse.ArgumentParser:
    global _PARSER
    if _PARSER is None:
        from mailquery.cli import build_parser

        _PARSER = build_parser()
    return _PARSER


def _definitions() -> dict[str, dict]:
    global _DEFINITIONS
    if _DEFINITIONS is None:
        _DEFINITIONS = {tool["name"]: tool for tool in tool_definitions(_default_parser())}
    return _DEFINITIONS

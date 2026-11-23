"""Tests for the MCP server over stdio: protocol, tools, arguments and calls.

Covers UT-MCP-01 to UT-MCP-08 with an in-process server and a substituted tool
runner. The real subprocess runner is exercised with ``subprocess.run``
replaced; the process-level cases (UT-MCP-09 to UT-MCP-12) live in the same
file and require ``mailquery mcp serve``.
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from mailquery import __version__, cli as cli_mod, mcp_server
from mailquery.errors import MailqueryError
from mailquery.mcp_server import (
    LATEST_PROTOCOL_VERSION,
    PROTOCOL_VERSIONS,
    TOOL_NAMES,
    SubprocessToolRunner,
    ToolOutcome,
    build_argv,
    serve,
    tool_definitions,
)
from mailquery.output import dumps_json

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TOOL_NAMES = ("search", "new", "show", "attachment", "mailboxes", "doctor")


class RecordingRunner:
    """Substituted runner that records every argv and returns a fixed outcome."""

    def __init__(self, stdout: str = '{"ok": true}\n', exit_code: int = 0) -> None:
        self.stdout = stdout
        self.exit_code = exit_code
        self.calls: list[list[str]] = []

    def run(self, argv):
        self.calls.append(list(argv))
        return ToolOutcome(self.stdout, self.exit_code, 1)


class SequenceRunner:
    """Runner that returns one prepared outcome per call."""

    def __init__(self, outcomes) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[list[str]] = []

    def run(self, argv):
        self.calls.append(list(argv))
        if self.outcomes:
            return self.outcomes.pop(0)
        return ToolOutcome('{"ok": true}\n', 0, 1)


class OrderedRunner:
    """Runner that records when each call starts and ends."""

    def __init__(self) -> None:
        self.events: list[str] = []

    def run(self, argv):
        self.events.append("start")
        time.sleep(0.01)
        self.events.append("end")
        return ToolOutcome('{"ok": true}\n', 0, 1)


def _session_text(text: str, runner=None):
    """Serve raw protocol text and return the exit code, replies and raw output."""
    stdout = io.StringIO()
    code = serve(io.StringIO(text), stdout, runner=runner or RecordingRunner())
    raw = stdout.getvalue()
    replies = [json.loads(line) for line in raw.splitlines()] if raw else []
    return code, replies, raw


def _session(messages, runner=None):
    text = "".join(json.dumps(message) + "\n" for message in messages)
    return _session_text(text, runner)


def _request(request_id, method, params=None):
    message = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        message["params"] = params
    return message


def _call(name, arguments=None, request_id=1):
    params = {"name": name}
    if arguments is not None:
        params["arguments"] = arguments
    return _request(request_id, "tools/call", params)


def _tool_text(reply) -> str:
    return reply["result"]["content"][0]["text"]


def _tool_json(reply) -> dict:
    return json.loads(_tool_text(reply))


def _error_payload(tool: str, code: str = "E_USAGE") -> dict:
    return MailqueryError(code, "message", "hint").to_payload(tool)


class _ServerCase(unittest.TestCase):
    def assert_single_line(self, raw: str) -> None:
        self.assertTrue(raw.endswith("\n"), raw)
        self.assertEqual(len(raw.splitlines()), 1, raw)
        self.assertNotIn("\r", raw)


class TransportTests(_ServerCase):
    """UT-MCP-01 — transport and JSON-RPC messages."""

    def test_ut_mcp_01_01_response_is_one_json_object_line(self) -> None:
        """UT-MCP-01.01: one JSON-RPC 2.0 object per line and nothing else on stdout."""
        code, replies, raw = _session([_request(1, "ping")])
        self.assertEqual(code, 0)
        self.assertEqual(replies, [{"jsonrpc": "2.0", "id": 1, "result": {}}])
        self.assert_single_line(raw)

    def test_ut_mcp_01_02_crlf_line_is_handled_like_lf(self) -> None:
        """UT-MCP-01.02: a CRLF-terminated line is handled like an LF one."""
        message = json.dumps(_request(2, "ping")) + "\r\n"
        code, replies, _ = _session_text(message)
        self.assertEqual(code, 0)
        self.assertEqual(replies[0]["id"], 2)

    def test_ut_mcp_01_03_parse_error_and_invalid_utf8(self) -> None:
        """UT-MCP-01.03: invalid JSON or invalid UTF-8 ⇒ -32700 with null id."""
        _, replies, _ = _session_text("not json\n")
        self.assertEqual(replies[0]["error"]["code"], -32700)
        self.assertIsNone(replies[0]["id"])
        raw = io.BytesIO(b"\xff\n")
        stdin = io.TextIOWrapper(raw, encoding="utf-8", errors="strict", newline="")
        stdout = io.StringIO()
        code = serve(stdin, stdout, runner=RecordingRunner())
        reply = json.loads(stdout.getvalue().splitlines()[0])
        self.assertEqual(code, 0)
        self.assertEqual(reply["error"]["code"], -32700)
        self.assertIsNone(reply["id"])

    def test_ut_mcp_01_04_request_without_method_and_empty_batch(self) -> None:
        """UT-MCP-01.04: a request without method and an empty array ⇒ -32600."""
        _, replies, _ = _session([{"jsonrpc": "2.0", "id": 3}])
        self.assertEqual(replies[0]["error"]["code"], -32600)
        self.assertEqual(replies[0]["id"], 3)
        _, replies, _ = _session([[]])
        self.assertEqual(replies[0]["error"]["code"], -32600)
        self.assertIsNone(replies[0]["id"])

    def test_ut_mcp_01_05_unknown_method_returns_32601(self) -> None:
        """UT-MCP-01.05: an unknown method ⇒ -32601 with the request id."""
        _, replies, _ = _session([_request(7, "unknown/method")])
        self.assertEqual(replies[0]["error"]["code"], -32601)
        self.assertEqual(replies[0]["id"], 7)

    def test_ut_mcp_01_06_batches_and_their_order(self) -> None:
        """UT-MCP-01.06: batch replies keep the order; notifications-only batches are silent."""
        batch = [_request(1, "ping"), _request(2, "ping")]
        _, replies, raw = _session([batch])
        self._assert_batch(replies, [1, 2])
        _, replies, raw = _session([[{"jsonrpc": "2.0", "method": "notifications/initialized"}]])
        self.assertEqual((replies, raw), ([], ""))
        _, replies, _ = _session([[1]])
        self.assertEqual(replies[0][0]["error"]["code"], -32600)
        self.assertIsNone(replies[0][0]["id"])

    def _assert_batch(self, replies, ids) -> None:
        self.assertIsInstance(replies, list)
        self.assertEqual(len(replies), 1)
        self.assertEqual([reply["id"] for reply in replies[0]], ids)

    def test_ut_mcp_01_07_notifications_get_no_response(self) -> None:
        """UT-MCP-01.07: known and unknown notifications produce no response."""
        messages = [
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "method": "notifications/cancelled"},
            {"jsonrpc": "2.0", "method": "notifications/other"},
        ]
        code, replies, raw = _session(messages)
        self.assertEqual((code, replies, raw), (0, [], ""))

    def test_ut_mcp_01_08_tools_list_before_initialize_matches_after(self) -> None:
        """UT-MCP-01.08: tools/list before initialize returns the same result."""
        _, before, _ = _session([_request(1, "tools/list")])
        _, after, _ = _session([_request(1, "initialize", {}), _request(2, "tools/list")])
        self.assertEqual(before[0]["result"], after[1]["result"])

    def test_ut_mcp_01_09_byte_streams_write_lf_only(self) -> None:
        """UT-MCP-01.09: streams built from bytes write LF without CR on any platform."""
        raw_in = io.BytesIO(
            (json.dumps(_request(1, "ping")) + "\n" + json.dumps(_request(2, "ping")) + "\n").encode()
        )
        stdin = io.TextIOWrapper(raw_in, encoding="utf-8", newline="")
        raw_out = io.BytesIO()
        stdout = io.TextIOWrapper(raw_out, encoding="utf-8", newline="")
        code = serve(stdin, stdout, runner=RecordingRunner())
        stdout.flush()
        self.assertEqual(code, 0)
        data = raw_out.getvalue()
        self.assertNotIn(b"\r", data)
        self.assertTrue(data.endswith(b"\n"))
        self.assertEqual(len(data.splitlines()), 2)


class InitializeTests(_ServerCase):
    """UT-MCP-02 — initialize and ping."""

    def initialize(self, params):
        _, replies, _ = _session([_request(1, "initialize", params)])
        return replies[0]["result"]

    def test_ut_mcp_02_01_server_info_and_capabilities(self) -> None:
        """UT-MCP-02.01: serverInfo and capabilities.tools without listChanged."""
        result = self.initialize({"protocolVersion": "2025-06-18"})
        self.assertEqual(result["serverInfo"], {"name": "mailquery", "version": __version__})
        self.assertEqual(result["capabilities"], {"tools": {}})
        self.assertNotIn("listChanged", result["capabilities"]["tools"])

    def test_ut_mcp_02_02_supported_versions_are_echoed(self) -> None:
        """UT-MCP-02.02: every supported version is echoed back."""
        for version in PROTOCOL_VERSIONS:
            with self.subTest(version=version):
                self.assertEqual(self.initialize({"protocolVersion": version})["protocolVersion"], version)

    def test_ut_mcp_02_03_unsupported_or_missing_version_uses_latest(self) -> None:
        """UT-MCP-02.03: an unsupported or missing version ⇒ the latest supported."""
        for params in ({"protocolVersion": "1999-01-01"}, {}):
            with self.subTest(params=params):
                self.assertEqual(self.initialize(params)["protocolVersion"], LATEST_PROTOCOL_VERSION)

    def test_ut_mcp_02_04_ping_returns_an_empty_result(self) -> None:
        """UT-MCP-02.04: ping returns an empty result object."""
        _, replies, _ = _session([_request(4, "ping")])
        self.assertEqual(replies[0]["result"], {})

    def test_ut_mcp_02_05_tools_are_version_independent(self) -> None:
        """UT-MCP-02.05: tools/list and tools/call content does not depend on the version."""
        results = []
        for version in PROTOCOL_VERSIONS:
            _, replies, _ = _session(
                [
                    _request(1, "initialize", {"protocolVersion": version}),
                    _request(2, "tools/list"),
                    _call("search", {"since": "1w"}, request_id=3),
                ]
            )
            results.append((replies[1]["result"], replies[2]["result"]))
        for other in results[1:]:
            self.assertEqual(other, results[0])


class ToolDefinitionTests(_ServerCase):
    """UT-MCP-03 — tools in tools/list."""

    def setUp(self) -> None:
        self.parser = cli_mod.build_parser()
        self.defs = {tool["name"]: tool for tool in tool_definitions(self.parser)}

    def test_ut_mcp_03_01_exactly_six_tools_in_order(self) -> None:
        """UT-MCP-03.01: exactly the six tools, in the documented order."""
        self.assertEqual(tuple(tool["name"] for tool in tool_definitions(self.parser)), _TOOL_NAMES)
        self.assertNotIn("mcp", self.defs)

    def test_ut_mcp_03_02_descriptions_come_from_the_parser(self) -> None:
        """UT-MCP-03.02: tool and parameter descriptions come from the subparser."""
        subparsers = cli_mod.build_parser()._actions
        choices = next(
            action.choices for action in subparsers if isinstance(action, argparse._SubParsersAction)
        )
        for tool, definition in self.defs.items():
            self.assertEqual(definition["description"], choices[tool].description)
            for name, schema in definition["inputSchema"]["properties"].items():
                if name in ("log_level", "uid"):
                    continue
                option = f"--{name.replace('_', '-')}"
                action = next(
                    action for action in choices[tool]._actions if option in action.option_strings
                )
                self.assertEqual(schema["description"], action.help or "")

    def test_ut_mcp_03_03_option_names_use_underscores(self) -> None:
        """UT-MCP-03.03: long options become parameters without dashes."""
        properties = self.defs["search"]["inputSchema"]["properties"]
        for name in ("include_mailbox", "has_attachments", "strip_links", "group_by", "from"):
            with self.subTest(name=name):
                self.assertIn(name, properties)

    def test_ut_mcp_03_04_parameter_types(self) -> None:
        """UT-MCP-03.04: flags, integers, enums, arrays and strings keep their types."""
        search = self.defs["search"]["inputSchema"]["properties"]
        self.assertEqual(search["unread"]["type"], "boolean")
        self.assertEqual(search["limit"]["type"], "integer")
        self.assertEqual(self.defs["attachment"]["inputSchema"]["properties"]["index"]["type"], "integer")
        self.assertEqual(search["fields"]["type"], "array")
        self.assertEqual(search["fields"]["items"], {"type": "string"})
        self.assertEqual(
            self.defs["mailboxes"]["inputSchema"]["properties"]["fields"]["type"], "array"
        )
        self.assertEqual(search["log_level"]["enum"], ["error", "warning", "info", "debug"])

    def test_ut_mcp_03_05_log_level_is_optional_everywhere(self) -> None:
        """UT-MCP-03.05: log_level is an optional string with the root enum on every tool."""
        for name, definition in self.defs.items():
            with self.subTest(tool=name):
                schema = definition["inputSchema"]
                self.assertIn("log_level", schema["properties"])
                self.assertNotIn("log_level", schema["required"])
                self.assertEqual(schema["properties"]["log_level"]["type"], "string")
                self.assertEqual(schema["properties"]["log_level"]["enum"], ["error", "warning", "info", "debug"])

    def test_ut_mcp_03_06_excluded_parameters(self) -> None:
        """UT-MCP-03.06: no json for doctor, no show_native_id for show, no help anywhere."""
        self.assertNotIn("json", self.defs["doctor"]["inputSchema"]["properties"])
        self.assertNotIn("show_native_id", self.defs["show"]["inputSchema"]["properties"])
        for definition in self.defs.values():
            self.assertNotIn("help", definition["inputSchema"]["properties"])

    def test_ut_mcp_03_07_required_uid_and_closed_schemas(self) -> None:
        """UT-MCP-03.07: uid is required in show/attachment; no extra properties anywhere."""
        for tool in ("show", "attachment"):
            with self.subTest(tool=tool):
                self.assertEqual(self.defs[tool]["inputSchema"]["required"], ["uid"])
        for definition in self.defs.values():
            self.assertFalse(definition["inputSchema"]["additionalProperties"])

    def test_ut_mcp_03_08_a_new_parser_option_appears_in_its_tool(self) -> None:
        """UT-MCP-03.08: adding an option to a test parser adds the parameter."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        search = subparsers.add_parser("search", description="Search.")
        search.add_argument("--new-flag", action="store_true", help="A new flag.")
        definitions = tool_definitions(parser)
        self.assertEqual(len(definitions), 1)
        self.assertEqual(
            definitions[0]["inputSchema"]["properties"]["new_flag"],
            {"type": "boolean", "description": "A new flag."},
        )


class ArgumentTests(_ServerCase):
    """UT-MCP-04 — CLI arguments."""

    def test_ut_mcp_04_01_executor_receives_the_full_argv(self) -> None:
        """UT-MCP-04.01: the executor receives the interpreter and -P -m mailquery."""
        runner = RecordingRunner()
        _session([_call("search", {"since": "1w"})], runner)
        self.assertEqual(runner.calls[0][:6], [sys.executable, "-P", "-m", "mailquery", "search", "--since=1w"])

    def test_ut_mcp_04_02_log_level_precedes_the_command(self) -> None:
        """UT-MCP-04.02: log_level goes before the command name."""
        runner = RecordingRunner()
        _session([_call("search", {"log_level": "debug", "since": "1w"})], runner)
        self.assertEqual(runner.calls[0][4:], ["--log-level=debug", "search", "--since=1w"])

    def test_ut_mcp_04_03_values_arrays_and_booleans(self) -> None:
        """UT-MCP-04.03: --option=value, one option per array element and flags."""
        self.assertEqual(
            build_argv("search", {"fields": ["a", "b"], "unread": True, "strip_links": False}),
            ["search", "--unread", "--fields=a", "--fields=b"],
        )

    def test_ut_mcp_04_04_uid_goes_last_after_double_dash(self) -> None:
        """UT-MCP-04.04: uid is the last argument, after --."""
        self.assertEqual(
            build_argv("show", {"uid": "-weird-uid"}), ["show", "--", "-weird-uid"]
        )

    def test_ut_mcp_04_05_doctor_always_gets_json(self) -> None:
        """UT-MCP-04.05: doctor always passes --json and adds --failures on request."""
        self.assertEqual(build_argv("doctor", {}), ["doctor", "--json"])
        self.assertEqual(build_argv("doctor", {"failures": True}), ["doctor", "--json", "--failures"])

    def test_ut_mcp_04_06_search_example(self) -> None:
        """UT-MCP-04.06: the documented search call maps to its CLI equivalent."""
        self.assertEqual(
            build_argv("search", {"since": "1w", "unread": True, "fields": ["snippet"]}),
            ["search", "--since=1w", "--unread", "--fields=snippet"],
        )

    def test_ut_mcp_04_07_a_value_starting_with_dash_stays_a_value(self) -> None:
        """UT-MCP-04.07: a subject starting with '-' is passed as --subject=<value>."""
        self.assertEqual(
            build_argv("search", {"subject": ["-invoice"]}), ["search", "--subject=-invoice"]
        )

    def test_ut_mcp_04_08_attachment_index_and_uid(self) -> None:
        """UT-MCP-04.08: attachment index becomes --index and uid goes last."""
        self.assertEqual(
            build_argv("attachment", {"index": 2, "uid": "apple_mail:83143"}),
            ["attachment", "--index=2", "--", "apple_mail:83143"],
        )


class ResultTests(_ServerCase):
    """UT-MCP-05 — result of a call."""

    def test_ut_mcp_05_01_success_text_and_is_error_false(self) -> None:
        """UT-MCP-05.01: exit 0 ⇒ one text block without the final newline, isError false."""
        raw = '{"ok": true, "command": "search"}\n'
        _, replies, _ = _session([_call("search", {})], RecordingRunner(raw, 0))
        result = replies[0]["result"]
        self.assertEqual(result["content"], [{"type": "text", "text": raw[:-1]}])
        self.assertFalse(result["isError"])

    def test_ut_mcp_05_02_error_exit_keeps_the_text_and_sets_is_error(self) -> None:
        """UT-MCP-05.02: a non-zero exit keeps the child text and sets isError."""
        raw = '{"ok": false, "command": "search", "error": {"code": "E_USAGE"}}\n'
        _, replies, _ = _session([_call("search", {})], RecordingRunner(raw, 2))
        result = replies[0]["result"]
        self.assertEqual(result["content"][0]["text"], raw[:-1])
        self.assertTrue(result["isError"])

    def test_ut_mcp_05_03_invalid_child_output_is_internal(self) -> None:
        """UT-MCP-05.03: empty, non-JSON, two objects or an array ⇒ E_INTERNAL."""
        for raw in ("", "not json\n", '{"a": 1}\n{"b": 2}\n', "[1]\n"):
            with self.subTest(raw=raw):
                _, replies, _ = _session([_call("search", {})], RecordingRunner(raw, 0))
                payload = _tool_json(replies[0])
                self.assertEqual(payload["error"]["code"], "E_INTERNAL")
                self.assertEqual(payload["error"]["message"], "the command did not write a JSON object")
                self.assertEqual(payload["error"]["hint"], "run `mailquery doctor` and check the mailquery log")
                self.assertEqual(payload["command"], "search")
                self.assertTrue(replies[0]["result"]["isError"])

    def test_ut_mcp_05_04_launch_failure_is_internal(self) -> None:
        """UT-MCP-05.04: a child that cannot be launched ⇒ E_INTERNAL."""
        class FailingRunner:
            def run(self, argv):
                raise OSError("cannot launch")

        _, replies, _ = _session([_call("search", {})], FailingRunner())
        self.assertEqual(_tool_json(replies[0])["error"]["code"], "E_INTERNAL")
        self.assertTrue(replies[0]["result"]["isError"])

    def test_ut_mcp_05_05_next_call_succeeds_after_internal(self) -> None:
        """UT-MCP-05.05: after an E_INTERNAL the next call is served normally."""
        runner = SequenceRunner(
            [ToolOutcome("not json\n", 0, 1), ToolOutcome('{"ok": true}\n', 0, 1)]
        )
        _, replies, _ = _session([_call("search", {}, 1), _call("search", {}, 2)], runner)
        self.assertEqual(_tool_json(replies[0])["error"]["code"], "E_INTERNAL")
        self.assertFalse(replies[1]["result"]["isError"])

    def test_ut_mcp_05_06_internal_json_has_the_cli_format(self) -> None:
        """UT-MCP-05.06: the E_INTERNAL JSON keeps the CLI keys, order and format."""
        _, replies, _ = _session([_call("attachment", {"uid": "apple_mail:1"})], RecordingRunner("", 0))
        text = _tool_text(replies[0])
        expected = dumps_json(
            MailqueryError(
                "E_INTERNAL",
                "the command did not write a JSON object",
                "run `mailquery doctor` and check the mailquery log",
            ).to_payload("attachment")
        )
        self.assertEqual(text, expected)
        self.assertEqual(list(json.loads(text)), ["ok", "command", "error"])

    def test_ut_mcp_05_07_real_runner_launches_without_shell(self) -> None:
        """UT-MCP-05.07: subprocess.run gets no shell, empty stdin, captured stdout and discarded stderr."""
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="{}\n", stderr=None)
        with mock.patch.object(subprocess, "run", return_value=completed) as run:
            outcome = SubprocessToolRunner().run(["mailquery", "search"])
        self.assertEqual(outcome.stdout, "{}\n")
        kwargs = run.call_args.kwargs
        self.assertNotIn("shell", kwargs)
        self.assertIs(kwargs["stdin"], subprocess.PIPE)
        self.assertNotIn("input", kwargs)
        self.assertIs(kwargs["stdout"], subprocess.PIPE)
        self.assertIs(kwargs["stderr"], subprocess.DEVNULL)
        self.assertEqual(kwargs["cwd"], os.getcwd())
        self.assertEqual(kwargs["env"], dict(os.environ))
        self.assertEqual(outcome.exit_code, 0)


class ValidationTests(_ServerCase):
    """UT-MCP-06 — validation before the child process."""

    def test_ut_mcp_06_01_unknown_parameter_is_usage_without_a_child(self) -> None:
        """UT-MCP-06.01: an unknown parameter ⇒ E_USAGE naming it, without a child."""
        runner = RecordingRunner()
        _, replies, _ = _session([_call("search", {"bogus": 1})], runner)
        payload = _tool_json(replies[0])
        self.assertEqual(payload["error"]["code"], "E_USAGE")
        self.assertEqual(payload["command"], "search")
        self.assertIn("bogus", payload["error"]["hint"])
        self.assertTrue(replies[0]["result"]["isError"])
        self.assertEqual(runner.calls, [])

    def test_ut_mcp_06_02_wrong_types_are_usage(self) -> None:
        """UT-MCP-06.02: integer, boolean and array values with the wrong JSON type."""
        cases = (
            ("search", {"limit": "3"}),
            ("search", {"unread": "true"}),
            ("search", {"fields": [1]}),
        )
        for tool, arguments in cases:
            with self.subTest(arguments=arguments):
                runner = RecordingRunner()
                _, replies, _ = _session([_call(tool, arguments)], runner)
                payload = _tool_json(replies[0])
                self.assertEqual(payload["error"]["code"], "E_USAGE")
                self.assertTrue(payload["error"]["hint"])
                self.assertEqual(runner.calls, [])

    def test_ut_mcp_06_03_missing_uid_is_usage(self) -> None:
        """UT-MCP-06.03: show or attachment without uid ⇒ E_USAGE."""
        for tool in ("show", "attachment"):
            with self.subTest(tool=tool):
                runner = RecordingRunner()
                _, replies, _ = _session([_call(tool, {})], runner)
                payload = _tool_json(replies[0])
                self.assertEqual(payload["error"]["code"], "E_USAGE")
                self.assertIn("uid", payload["error"]["hint"])
                self.assertEqual(runner.calls, [])

    def test_ut_mcp_06_04_show_native_id_is_rejected(self) -> None:
        """UT-MCP-06.04: show with show_native_id ⇒ E_USAGE."""
        _, replies, _ = _session([_call("show", {"uid": "apple_mail:1", "show_native_id": True})])
        self.assertEqual(_tool_json(replies[0])["error"]["code"], "E_USAGE")

    def test_ut_mcp_06_05_nul_character_is_rejected(self) -> None:
        """UT-MCP-06.05: a value with NUL ⇒ E_USAGE."""
        _, replies, _ = _session([_call("search", {"since": "1w\x00"})])
        self.assertEqual(_tool_json(replies[0])["error"]["code"], "E_USAGE")

    def test_ut_mcp_06_06_argv_over_the_platform_limit_is_rejected(self) -> None:
        """UT-MCP-06.06: an argv above the platform limit ⇒ E_USAGE without a child."""
        runner = RecordingRunner()
        limit = 32_767 if sys.platform == "win32" else mcp_server._arg_max()
        _, replies, _ = _session([_call("search", {"since": "x" * (limit + 1_000_000)})], runner)
        payload = _tool_json(replies[0])
        self.assertEqual(payload["error"]["code"], "E_USAGE")
        self.assertIn("since", payload["error"]["hint"])
        self.assertEqual(runner.calls, [])

    def test_ut_mcp_06_07_unknown_tool_is_32602(self) -> None:
        """UT-MCP-06.07: tools/call with an unknown tool ⇒ JSON-RPC -32602."""
        _, replies, _ = _session([_call("not-a-tool", {})])
        self.assertEqual(replies[0]["error"]["code"], -32602)

    def test_ut_mcp_06_08_usage_json_has_the_cli_format(self) -> None:
        """UT-MCP-06.08: the E_USAGE JSON keeps the CLI keys, order and format."""
        _, replies, _ = _session([_call("search", {"bogus": 1})])
        text = _tool_text(replies[0])
        parsed = json.loads(text)
        self.assertEqual(list(parsed), ["ok", "command", "error"])
        self.assertEqual(list(parsed["error"]), ["code", "message", "hint"])
        self.assertEqual(text, dumps_json(parsed))


class OrderingTests(_ServerCase):
    """UT-MCP-07 — serial calls and shutdown."""

    def test_ut_mcp_07_01_calls_are_serial_in_order(self) -> None:
        """UT-MCP-07.01: two calls are answered in order and the second starts after the first ends."""
        runner = OrderedRunner()
        _, replies, _ = _session([_call("search", {}, 1), _call("search", {}, 2)], runner)
        self.assertEqual([reply["id"] for reply in replies], [1, 2])
        self.assertEqual(runner.events, ["start", "end", "start", "end"])

    def test_ut_mcp_07_02_ping_and_tools_list_wait_for_the_call(self) -> None:
        """UT-MCP-07.02: ping and tools/list written during a call answer after it."""
        started = threading.Event()
        release = threading.Event()

        class BlockingRunner:
            def run(self, argv):
                started.set()
                release.wait(5)
                return ToolOutcome('{"ok": true}\n', 0, 1)

        class StagedStdin:
            def __init__(self) -> None:
                self.stage = 0

            def readline(self):
                if self.stage == 0:
                    self.stage = 1
                    return json.dumps(_call("search", {}, 1)) + "\n"
                if self.stage == 1:
                    self.stage = 2
                    started.wait(5)
                    return json.dumps(_request(2, "ping")) + "\n"
                if self.stage == 2:
                    self.stage = 3
                    return json.dumps(_request(3, "tools/list")) + "\n"
                return ""

        stdout = io.StringIO()
        result: dict = {}

        def run() -> None:
            result["code"] = serve(StagedStdin(), stdout, runner=BlockingRunner())

        thread = threading.Thread(target=run)
        thread.start()
        started.wait(5)
        self.assertEqual(stdout.getvalue(), "")
        release.set()
        thread.join(5)
        self.assertFalse(thread.is_alive())
        replies = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual([reply["id"] for reply in replies], [1, 2, 3])
        self.assertEqual(result["code"], 0)

    def test_ut_mcp_07_03_eof_with_a_call_in_progress(self) -> None:
        """UT-MCP-07.03: EOF with a call in progress answers it and serve returns 0."""
        code, replies, _ = _session([_call("search", {})])
        self.assertEqual(code, 0)
        self.assertEqual(len(replies), 1)

    def test_ut_mcp_07_04_nothing_is_written_to_stderr(self) -> None:
        """UT-MCP-07.04: the session writes nothing to stderr."""
        stderr = io.StringIO()
        with mock.patch.object(sys, "stderr", stderr):
            _session([_call("search", {}), _request(2, "ping")])
        self.assertEqual(stderr.getvalue(), "")


class ImportTests(_ServerCase):
    """UT-MCP-08 — dependencies and imports."""

    def test_ut_mcp_08_01_only_stdlib_and_mailquery_imports(self) -> None:
        """UT-MCP-08.01: mcp_server.py imports only standard-library modules and mailquery."""
        tree = ast.parse((_REPO_ROOT / "src" / "mailquery" / "mcp_server.py").read_text(encoding="utf-8"))
        roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
        stdlib = set(sys.stdlib_module_names)
        for root in roots:
            with self.subTest(module=root):
                self.assertTrue(root in stdlib or root == "mailquery", root)

    def test_ut_mcp_08_02_dependencies_do_not_change(self) -> None:
        """UT-MCP-08.02: [project].dependencies is exactly the baseline list."""
        with (_REPO_ROOT / "pyproject.toml").open("rb") as handle:
            data = tomllib.load(handle)
        self.assertEqual(
            data["project"]["dependencies"],
            ["css-inline~=0.23.1", 'pywin32; sys_platform == "win32"'],
        )

    def test_ut_mcp_08_03_import_and_definitions_load_no_entry_points(self) -> None:
        """UT-MCP-08.03: importing and generating tools does not load plugins or drivers."""
        import importlib

        from mailquery import mcp_server

        def fail(*args, **kwargs):
            raise AssertionError("entry points must not be read")

        with mock.patch("importlib.metadata.entry_points", side_effect=fail):
            module = importlib.reload(mcp_server)
            definitions = module.tool_definitions(cli_mod.build_parser())
        self.assertEqual([tool["name"] for tool in definitions], list(_TOOL_NAMES))


if __name__ == "__main__":  # pragma: no cover - manual runs
    unittest.main()


# --------------------------------------------------------------------------- #
# UT-MCP-09 to UT-MCP-12 — the real server and child processes
# --------------------------------------------------------------------------- #

_SERVER_SCRIPT = [sys.executable, "-B", "-P", "-m", "mailquery"]


def _process_env(home: Path, extra: dict | None = None) -> dict:
    env = dict(os.environ)
    env["HOME"] = env["USERPROFILE"] = str(home)
    env["PYTHONPATH"] = str(_REPO_ROOT / "src")
    env.pop("PYTHONWARNINGS", None)
    if extra:
        env.update(extra)
    return env


def _write_config(home: Path, text: str) -> None:
    app_home = home / ".mailquery"
    app_home.mkdir(parents=True, exist_ok=True)
    (app_home / "config.toml").write_text(text, encoding="utf-8")


class _ProcessCase(unittest.TestCase):
    """One temporary HOME per case and helpers for real server subprocesses."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="mailquery-mcp-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()

    def start(self, *, args=(), env=None, cwd=None):
        proc = subprocess.Popen(
            [*_SERVER_SCRIPT, *args, "mcp", "serve"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=env or _process_env(self.home),
            cwd=str(cwd or _REPO_ROOT),
        )
        self.addCleanup(self._terminate, proc)
        return proc

    def _terminate(self, proc) -> None:
        if proc.poll() is None:
            proc.kill()
            proc.communicate()
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            try:
                if stream is not None and not stream.closed:
                    stream.close()
            except OSError:
                pass

    def request(self, proc, request_id, method, params=None) -> dict:
        message = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            message["params"] = params
        proc.stdin.write(json.dumps(message) + "\n")
        proc.stdin.flush()
        line = proc.stdout.readline()
        self.assertTrue(line, "the server closed stdout")
        return json.loads(line)

    def call(self, proc, tool, arguments=None, request_id=1) -> dict:
        return self.request(
            proc, request_id, "tools/call", {"name": tool, "arguments": arguments or {}}
        )

    def tool_payload(self, reply) -> dict:
        return json.loads(reply["result"]["content"][0]["text"])

    def stop(self, proc) -> tuple[int, str]:
        proc.stdin.close()
        code = proc.wait(timeout=120)
        return code, proc.stderr.read()

    def run_cli(self, *argv, env=None, cwd=None):
        return subprocess.run(
            [*_SERVER_SCRIPT, *argv],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env or _process_env(self.home),
            cwd=str(cwd or _REPO_ROOT),
            timeout=120,
        )


class RealServerTests(_ProcessCase):
    """UT-MCP-09 — the real server process."""

    def test_ut_mcp_09_01_starts_without_config(self) -> None:
        """UT-MCP-09.01: without config.toml the server answers initialize and tools/list."""
        proc = self.start()
        initialized = self.request(proc, 1, "initialize", {})
        self.assertEqual(initialized["result"]["serverInfo"]["name"], "mailquery")
        tools = self.request(proc, 2, "tools/list")
        self.assertEqual(len(tools["result"]["tools"]), 6)
        self.assertEqual(self.stop(proc)[0], 0)

    def test_ut_mcp_09_02_invalid_config_is_fixed_without_restart(self) -> None:
        """UT-MCP-09.02: an invalid config is reported and fixed without restarting."""
        _write_config(self.home, "broken = = toml\n")
        proc = self.start()
        self.request(proc, 1, "initialize", {})
        self.assertEqual(len(self.request(proc, 2, "tools/list")["result"]["tools"]), 6)
        reply = self.call(proc, "search", {"since": "bogus"}, 3)
        self.assertTrue(reply["result"]["isError"])
        self.assertEqual(self.tool_payload(reply)["error"]["code"], "E_CONFIG_INVALID")
        _write_config(self.home, "")
        reply = self.call(proc, "search", {"since": "bogus"}, 4)
        self.assertNotEqual(self.tool_payload(reply)["error"]["code"], "E_CONFIG_INVALID")
        self.assertEqual(self.stop(proc)[0], 0)

    def test_ut_mcp_09_03_real_executor_matches_the_cli(self) -> None:
        """UT-MCP-09.03: search --since=bogus matches the CLI, also with a local json.py."""
        cwd = self.root / "cwd"
        cwd.mkdir()
        (cwd / "json.py").write_text("raise RuntimeError('shadow json')\n", encoding="utf-8")
        direct = self.run_cli("search", "--since=bogus", cwd=cwd)
        self.assertNotEqual(direct.returncode, 0, direct.stderr)
        expected = json.loads(direct.stdout)
        expected.pop("generated_at", None)
        proc = self.start(cwd=cwd)
        self.request(proc, 1, "initialize", {})
        reply = self.call(proc, "search", {"since": "bogus"}, 2)
        self.assertTrue(reply["result"]["isError"])
        observed = self.tool_payload(reply)
        observed.pop("generated_at", None)
        self.assertEqual(observed, expected)
        self.assertEqual(self.stop(proc)[0], 0)

    def test_ut_mcp_09_04_closing_stdin_with_a_call_in_progress(self) -> None:
        """UT-MCP-09.04: closing stdin during a call answers it and exits 0 with empty stderr."""
        proc = self.start()
        self.request(proc, 1, "initialize", {})
        proc.stdin.write(
            json.dumps(_call("search", {"since": "1w"}, 2)) + "\n"
        )
        proc.stdin.flush()
        proc.stdin.close()
        reply = json.loads(proc.stdout.readline())
        self.assertEqual(reply["id"], 2)
        code = proc.wait(timeout=120)
        self.assertEqual(code, 0)
        self.assertEqual(proc.stderr.read(), "")

    def test_ut_mcp_09_05_stdout_lines_end_in_lf(self) -> None:
        """UT-MCP-09.05: every stdout line ends in LF without CR."""
        proc = self.start()
        self.request(proc, 1, "initialize", {})
        self.request(proc, 2, "tools/list")
        self.call(proc, "search", {"since": "bogus"}, 3)
        self.stop(proc)
        # The child sessions were consumed line by line; a raw run checks the bytes.
        raw = subprocess.run(
            [*_SERVER_SCRIPT, "mcp", "serve"],
            input=json.dumps(_request(1, "ping")) + "\n",
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=_process_env(self.home),
            cwd=str(_REPO_ROOT),
        )
        self.assertEqual(raw.returncode, 0)
        self.assertNotIn("\r", raw.stdout)
        for line in raw.stdout.splitlines(keepends=True):
            self.assertTrue(line.endswith("\n"))

    def test_ut_mcp_09_06_cross_option_validation_happens_in_the_child(self) -> None:
        """UT-MCP-09.06: attachment with index and all returns the CLI E_USAGE."""
        proc = self.start()
        self.request(proc, 1, "initialize", {})
        reply = self.call(proc, "attachment", {"uid": "apple_mail:1", "index": 1, "all": True}, 2)
        self.assertTrue(reply["result"]["isError"])
        observed = self.tool_payload(reply)
        self.assertEqual(observed["error"]["code"], "E_USAGE")
        direct = self.run_cli("attachment", "apple_mail:1", "--index", "1", "--all")
        expected = json.loads(direct.stdout)
        self.assertEqual(observed["error"], expected["error"])
        self.assertEqual(self.stop(proc)[0], 0)

    def test_ut_mcp_09_07_two_servers_share_the_same_home(self) -> None:
        """UT-MCP-09.07: two servers on the same HOME answer independently."""
        first = self.start()
        second = self.start()
        for index, proc in enumerate((first, second), start=1):
            with self.subTest(server=index):
                self.assertEqual(
                    self.request(proc, 1, "initialize", {})["result"]["serverInfo"]["name"],
                    "mailquery",
                )
                self.assertEqual(len(self.request(proc, 2, "tools/list")["result"]["tools"]), 6)
        self.assertEqual(self.stop(first)[0], 0)
        self.assertEqual(self.stop(second)[0], 0)


class FailingPluginTests(_ProcessCase):
    """UT-MCP-10 — a plugin that cannot be loaded does not break the server."""

    def test_ut_mcp_10_01_server_starts_with_a_broken_plugin_installed(self) -> None:
        """UT-MCP-10.01: a failing plugin still leaves initialize and tools/list working."""
        plugin_root = self.root / "plugin"
        plugin_root.mkdir()
        (plugin_root / "mq_broken_plugin.py").write_text(
            "raise ImportError('broken plugin')\n", encoding="utf-8"
        )
        dist_info = plugin_root / "graph-0.1.0.dist-info"
        dist_info.mkdir()
        (dist_info / "METADATA").write_text(
            "Metadata-Version: 2.1\nName: graph\nVersion: 0.1.0\n", encoding="utf-8"
        )
        (dist_info / "entry_points.txt").write_text(
            "[mailquery.backends]\ngraph = mq_broken_plugin:Broken\n", encoding="utf-8"
        )
        env = _process_env(self.home)
        env["PYTHONPATH"] = os.pathsep.join([str(_REPO_ROOT / "src"), str(plugin_root)])
        proc = self.start(env=env)
        self.assertEqual(self.request(proc, 1, "initialize", {})["result"]["serverInfo"]["name"], "mailquery")
        self.assertEqual(len(self.request(proc, 2, "tools/list")["result"]["tools"]), 6)
        self.assertEqual(self.stop(proc)[0], 0)


class ServerLogTests(_ProcessCase):
    """UT-MCP-11 — the server log."""

    def log_text(self, name: str = "mailquery.log") -> str:
        path = self.home / ".mailquery" / "logs" / name
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def test_ut_mcp_11_01_start_call_and_end_lines(self) -> None:
        """UT-MCP-11.01: start, one call line per call and end are logged."""
        proc = self.start()
        self.request(proc, 1, "initialize", {})
        self.call(proc, "search", {"since": "bogus"}, 2)
        self.assertEqual(self.stop(proc)[0], 0)
        text = self.log_text()
        self.assertIn("event=start command=mcp", text)
        self.assertRegex(text, r"event=call tool=search exit_code=\d+ duration_ms=\d+")
        self.assertIn("event=end command=mcp", text)

    def test_ut_mcp_11_02_parameter_values_are_not_logged(self) -> None:
        """UT-MCP-11.02: the server log never contains a parameter value."""
        proc = self.start()
        self.request(proc, 1, "initialize", {})
        self.call(proc, "search", {"subject": ["SECRET-SMOKE-VALUE"]}, 2)
        self.stop(proc)
        self.assertNotIn("SECRET-SMOKE-VALUE", self.log_text())

    def test_ut_mcp_11_03_the_log_file_is_not_open_between_events(self) -> None:
        """UT-MCP-11.03: the active log can be renamed between two events."""
        proc = self.start()
        self.request(proc, 1, "initialize", {})
        log = self.home / ".mailquery" / "logs" / "mailquery.log"
        moved = log.with_name("mailquery.log.moved")
        log.rename(moved)
        self.request(proc, 2, "tools/list")
        self.assertEqual(self.stop(proc)[0], 0)
        self.assertTrue(moved.is_file())
        self.assertIn("event=end command=mcp", self.log_text())

    def test_ut_mcp_11_04_level_json_and_the_config_snapshot(self) -> None:
        """UT-MCP-11.04: --log-level, JSON output and the config read once at start."""
        _write_config(self.home, '[logging]\njson = true\n')
        proc = self.start(args=("--log-level", "debug"))
        self.request(proc, 1, "initialize", {})
        _write_config(self.home, '[logging]\njson = false\n')
        self.call(proc, "search", {"since": "bogus"}, 2)
        self.assertEqual(self.stop(proc)[0], 0)
        jsonl = self.log_text("mailquery.jsonl")
        self.assertIn('"event": "start"', jsonl)
        self.assertIn('"event": "end"', jsonl)
        text_log = self.log_text()
        self.assertNotIn("event=start command=mcp", text_log)
        events = [
            json.loads(line)["fields"]["event"]
            for line in jsonl.splitlines()
            if "event" in json.loads(line)["fields"]
        ]
        self.assertIn("start", events)
        self.assertIn("call", events)
        self.assertIn("end", events)

    def test_ut_mcp_11_05_a_log_write_failure_does_not_break_the_server(self) -> None:
        """UT-MCP-11.05: a log failure is silent and the server keeps answering."""
        app_home = self.home / ".mailquery"
        app_home.mkdir()
        (app_home / "logs").write_text("not a directory", encoding="utf-8")
        proc = self.start()
        self.assertEqual(self.request(proc, 1, "initialize", {})["id"], 1)
        self.assertEqual(len(self.request(proc, 2, "tools/list")["result"]["tools"]), 6)
        code, stderr = self.stop(proc)
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")


class RotationTests(_ProcessCase):
    """UT-MCP-12 — rotation with the server running."""

    def _preload(self, path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)

    def test_ut_mcp_12_01_text_rotation(self) -> None:
        """UT-MCP-12.01: text rotation leaves event=call in the new active file."""
        _write_config(self.home, "[logging]\nmax_size_mb = 1\n")
        log = self.home / ".mailquery" / "logs" / "mailquery.log"
        self._preload(log, b"x" * (1024 * 1024 - 64))
        proc = self.start()
        self.request(proc, 1, "initialize", {})
        self.call(proc, "search", {"since": "bogus"}, 2)
        self.assertEqual(self.stop(proc)[0], 0)
        self.assertTrue((log.parent / "mailquery.log.1").is_file())
        self.assertIn("event=call tool=search", log.read_text(encoding="utf-8"))

    def test_ut_mcp_12_02_json_rotation(self) -> None:
        """UT-MCP-12.02: JSON rotation leaves event=call in the new active file."""
        _write_config(self.home, "[logging]\nmax_size_mb = 1\njson = true\n")
        log = self.home / ".mailquery" / "logs" / "mailquery.jsonl"
        pad = "x" * (1024 * 1024 - 80)
        self._preload(log, (json.dumps({"pad": pad}) + "\n").encode("utf-8"))
        proc = self.start()
        self.request(proc, 1, "initialize", {})
        self.call(proc, "search", {"since": "bogus"}, 2)
        self.assertEqual(self.stop(proc)[0], 0)
        self.assertTrue((log.parent / "mailquery.jsonl.1").is_file())
        payloads = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        self.assertTrue(any(payload.get("fields", {}).get("event") == "call" for payload in payloads))

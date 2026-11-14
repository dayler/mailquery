"""UT-RMT-01..05 and DOC-09: ``attachment`` from ``"remote"`` drivers and hard timeouts.

The command is driven end to end with the in-memory plugin double
(``tests/fakes/attachment_backend.py``) installed as a fake entry point, short
injected budgets through ``cli._attachment_timeout`` and events that release
every blocked plugin thread when each case ends. No case waits a real 60 s or
30 s budget, opens a network connection or writes outside the temporary home.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from mailquery import cli as cli_mod
from mailquery.attachments.cache import MANIFEST_NAME
from mailquery.attachments.engine import AttachmentsEngine, MIB
from mailquery.attachments.paths import message_dir
from mailquery.backends import outlook_com
from mailquery.backends.registry import BackendRegistry
from mailquery.config import AttachmentsConfig
from mailquery.errors import MailqueryError
from mailquery.plugins import (
    EXTRACTION_TIMEOUT_SECONDS,
    RESERVED_DRIVER_NAMES,
    PluginError,
    Reason,
    wrap_driver,
)
from mailquery.plugins import api as plugins_api

from tests.fakes import attachment_backend as fake_attachment
from tests.fakes.attachment_backend import FakeAttachmentBackend
from tests.fakes.attachment_driver import FakeAttachment, FakeAttachmentDriver
from tests.fakes.plugin import (
    ACCOUNT_LABEL as PLUGIN_ACCOUNT_LABEL,
    FakeEntryPoint,
    FakePluginBackend,
    internal_entry_points,
)
from tests.fixtures.make_fixtures import build_store, write_config

_DRIVER = fake_attachment.PLUGIN_DRIVER
_NATIVE_UID = "abc123"
_UID = f"{_DRIVER}:{_NATIVE_UID}"
_LABEL = fake_attachment.ACCOUNT_LABEL
_CONFIG = f'[scope."{_DRIVER}:{_LABEL}"]\n'
_LOCAL_DRIVER = "localfake"
_LOCAL_UID = f"{_LOCAL_DRIVER}:{_NATIVE_UID}"

_REMOTE_CAPABILITIES = {
    "network": True,
    "readonly": "promise",
    "body_local": False,
    "attachments": "remote",
    "native_order": "text",
}
_LOCAL_CAPABILITIES = {
    "network": False,
    "readonly": "promise",
    "body_local": True,
    "attachments": "local",
    "native_order": "text",
}
_NONE_CAPABILITIES = {**_REMOTE_CAPABILITIES, "attachments": "none"}

_UNSUPPORTED_HINT = (
    'install or declare a driver with attachments = "local" or "remote" in the '
    "[scope] blocks of ~/.mailquery/config.toml"
)
_TIMEOUT_HINT = (
    "raise [attachments].timeout_seconds in ~/.mailquery/config.toml if the "
    'driver is slow; run "mailquery doctor" and do not retry in a loop'
)
_DOCS_ROOT = Path(__file__).resolve().parents[1]
_README = _DOCS_ROOT / "README.md"
_README_ES = _DOCS_ROOT / "README.es.md"
_SKILL = _DOCS_ROOT / "skills" / "mailquery" / "SKILL.md"


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class _RemoteCase(unittest.TestCase):
    """Temporary home, plugin registry and CLI runner shared by the group."""

    def setUp(self) -> None:
        self.fx = build_store()
        self.addCleanup(self.fx.cleanup)
        self.addCleanup(cli_mod._close_logging_handlers)

    def backend(self, **kwargs) -> FakeAttachmentBackend:
        kwargs.setdefault("driver", _DRIVER)
        kwargs.setdefault("native_uid", _NATIVE_UID)
        kwargs.setdefault("capabilities", dict(_REMOTE_CAPABILITIES))
        kwargs.setdefault("account_label", _LABEL)
        return FakeAttachmentBackend(**kwargs)

    def registry(self, backend: object):
        entry = FakeEntryPoint(str(getattr(backend, "driver", _DRIVER)), plugin=backend)
        registry = BackendRegistry(
            entry_points=[*internal_entry_points(), entry]
        )
        return entry, registry

    def run_attachment(
        self,
        argv: list[str],
        backend: object,
        *,
        config: str | None = _CONFIG,
        registry: BackendRegistry | None = None,
    ):
        if config is not None:
            write_config(self.fx.home, config)
        if registry is None:
            registry = self.registry(backend)[1]
        native = str(getattr(backend, "driver", "")) in RESERVED_DRIVER_NAMES
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            mock.patch.object(
                cli_mod, "BackendRegistry", lambda *args, **kwargs: registry
            ),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            code = cli_mod.main(
                argv,
                home=self.fx.home,
                mail_root=self.fx.mail_root,
                accounts_db=self.fx.accounts_db,
                backend=backend if native else None,
            )
        return code, stdout.getvalue(), stderr.getvalue()

    def payload(self, stdout: str) -> dict:
        self.assertTrue(stdout.endswith("}\n"), f"expected one JSON object: {stdout!r}")
        parsed = json.loads(stdout)
        self.assertEqual(
            stdout, json.dumps(parsed, ensure_ascii=False, indent=2) + "\n"
        )
        return parsed

    def assert_error(
        self, code: int, result, expected: str
    ) -> dict:
        exit_code, stdout, stderr = result
        self.assertEqual(exit_code, code)
        payload = self.payload(stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], expected)
        self.assertIn(expected, stderr)
        return payload

    def cache_files(self) -> list[Path]:
        root = self.fx.home / "attachments"
        return [
            path
            for path in root.rglob("*")
            if path.is_file() and path.name != MANIFEST_NAME
        ]

    def manifest_entries(self, uid: str) -> dict:
        path = message_dir(self.fx.home, uid) / MANIFEST_NAME
        return json.loads(path.read_text(encoding="utf-8"))["entries"]

    def clear_cache(self) -> None:
        """Remove the attachment cache and staging of previous sub-cases."""
        shutil.rmtree(self.fx.home / "attachments", ignore_errors=True)
        shutil.rmtree(self.fx.home / "tmp" / "staging", ignore_errors=True)

    def assert_no_cache(self) -> None:
        self.assertFalse((self.fx.home / "attachments").exists())
        staging = self.fx.home / "tmp" / "staging"
        self.assertFalse(staging.exists() and any(staging.iterdir()))


# --------------------------------------------------------------------------- #
# UT-RMT-01 — extraction from a ``"remote"`` plugin
# --------------------------------------------------------------------------- #


class RemoteExtractionTests(_RemoteCase):
    """UT-RMT-01: ``"remote"`` extracts with the same engine as ``"local"``."""

    def test_ut_rmt_01_01_remote_plugin_extracts_one_attachment(self) -> None:
        """UT-RMT-01.01: ``--index`` returns the attachment contract and caches the file."""
        backend = self.backend()
        code, stdout, stderr = self.run_attachment(
            ["attachment", _UID, "--index", "1"], backend
        )
        self.assertEqual((code, stderr), (0, ""))
        payload = self.payload(stdout)
        self.assertEqual(payload["uid"], _UID)
        self.assertEqual(payload["output_dir"], str(message_dir(self.fx.home, _UID)))
        self.assertEqual(payload["count"], 1)
        self.assertIn("content_notice", payload)
        record = payload["attachments"][0]
        self.assertEqual(record["index"], 1)
        self.assertEqual(record["original_name"], "factura.pdf")
        self.assertTrue(record["saved"])
        self.assertFalse(record["cached"])
        self.assertEqual(record["size_bytes"], len(b"fake attachment 1"))
        self.assertEqual(record["sha256"], _sha256(b"fake attachment 1"))
        self.assertEqual(Path(record["path"]).read_bytes(), b"fake attachment 1")
        self.assertEqual(payload["warnings"], [])
        self.assertEqual(len(self.cache_files()), 1)
        self.assertEqual(self.manifest_entries(_UID)["1"]["sha256"], record["sha256"])

    def test_ut_rmt_01_02_all_blocking_and_limits_match_a_local_driver(self) -> None:
        """UT-RMT-01.02: ``--all``, name/content blocking and limits behave as ``"local"``."""
        remote = self.backend()
        code, stdout, stderr = self.run_attachment(
            ["attachment", _UID, "--all"], remote
        )
        self.assertEqual((code, stderr), (0, ""))
        payload = self.payload(stdout)
        self.assertEqual(payload["count"], 3)
        self.assertEqual(
            [entry["index"] for entry in payload["attachments"]], [1, 2, 3]
        )
        self.assertEqual(remote.block_requests.get(1), 2)

        scenarios = {
            "blocked-name": (
                dict(
                    attachments=[
                        {
                            "index": 1,
                            "name": "install.sh",
                            "size_bytes": 17,
                            "native_order_key": "1",
                            "unavailable_reason": None,
                        }
                    ]
                ),
                ["attachment", _UID, "--index", "1"],
                4,
                "E_ATTACHMENT_BLOCKED",
            ),
            "blocked-content": (
                dict(stream_chunks={1: [b"MZ" + b"\x00" * 510]}),
                ["attachment", _UID, "--index", "1"],
                4,
                "E_ATTACHMENT_BLOCKED",
            ),
            "size-limit": (
                dict(
                    attachments=[
                        {
                            "index": 1,
                            "name": "factura.pdf",
                            "size_bytes": 2 * MIB,
                            "native_order_key": "1",
                            "unavailable_reason": None,
                        }
                    ]
                ),
                ["attachment", _UID, "--index", "1"],
                4,
                "E_ATTACHMENT_TOO_LARGE",
            ),
            "count-limit": (
                dict(),
                ["attachment", _UID, "--all"],
                4,
                "E_ATTACHMENT_TOO_LARGE",
            ),
        }
        limits = (
            "[attachments]\nmax_file_size_mb = 1\nmax_total_size_mb = 2\n"
            "max_count = 1\n"
        )
        for label, (kwargs, argv, exit_code, error) in scenarios.items():
            with self.subTest(label=label):
                for driver, capabilities in (
                    (_DRIVER, _REMOTE_CAPABILITIES),
                    (_LOCAL_DRIVER, _LOCAL_CAPABILITIES),
                ):
                    self.clear_cache()
                    config = f'[scope."{driver}:{_LABEL}"]\n'
                    if label in ("size-limit", "count-limit"):
                        config += limits
                    backend = self.backend(
                        driver=driver, capabilities=dict(capabilities), **kwargs
                    )
                    uid = f"{driver}:{_NATIVE_UID}"
                    driver_argv = [uid if value == _UID else value for value in argv]
                    result = self.run_attachment(
                        driver_argv, backend, config=config
                    )
                    payload = self.assert_error(exit_code, result, error)
                    self.assertIn("attachment", payload["error"]["message"])

    def test_ut_rmt_01_03_cache_hit_asks_no_bytes_and_force_asks_again(self) -> None:
        """UT-RMT-01.03: the second run is ``cached: true`` without stream calls; ``--force`` reasks."""
        backend = self.backend()
        self.run_attachment(["attachment", _UID, "--index", "1"], backend)
        first_calls = len(backend.stream_calls)
        self.assertGreater(first_calls, 0)

        code, stdout, stderr = self.run_attachment(
            ["attachment", _UID, "--index", "1"], backend
        )
        self.assertEqual((code, stderr), (0, ""))
        cached = self.payload(stdout)["attachments"][0]
        self.assertTrue(cached["cached"])
        self.assertEqual(len(backend.stream_calls), first_calls)

        code, stdout, stderr = self.run_attachment(
            ["attachment", _UID, "--index", "1", "--force"], backend
        )
        self.assertEqual((code, stderr), (0, ""))
        forced = self.payload(stdout)["attachments"][0]
        self.assertFalse(forced["cached"])
        self.assertGreater(len(backend.stream_calls), first_calls)

    def test_ut_rmt_01_04_the_core_opens_no_connections(self) -> None:
        """UT-RMT-01.04: no ``socket`` is created during a ``"remote"`` extraction."""
        backend = self.backend()
        with mock.patch(
            "socket.socket", side_effect=AssertionError("the core must not open a socket")
        ):
            code, stdout, stderr = self.run_attachment(
                ["attachment", _UID, "--all"], backend
            )
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(self.payload(stdout)["count"], 3)

    def test_ut_rmt_01_05_manifest_equals_the_local_one(self) -> None:
        """UT-RMT-01.05: the manifest of equivalent bytes matches the ``"local"`` driver."""
        remote = self.backend()
        self.run_attachment(["attachment", _UID, "--all"], remote)
        local = self.backend(
            driver=_LOCAL_DRIVER, capabilities=dict(_LOCAL_CAPABILITIES)
        )
        self.run_attachment(
            ["attachment", _LOCAL_UID, "--all"],
            local,
            config=f'[scope."{_LOCAL_DRIVER}:{_LABEL}"]\n',
        )
        self.assertEqual(
            self.manifest_entries(_UID), self.manifest_entries(_LOCAL_UID)
        )


# --------------------------------------------------------------------------- #
# UT-RMT-02 — origin failures of a ``"remote"`` plugin
# --------------------------------------------------------------------------- #


class RemoteFailureTests(_RemoteCase):
    """UT-RMT-02: origin reasons map to ``E_ATTACHMENT_UNAVAILABLE``."""

    def test_ut_rmt_02_01_network_reason_is_unavailable_with_its_template(self) -> None:
        """UT-RMT-02.01: ``reason: network`` ⇒ E_ATTACHMENT_UNAVAILABLE (3), never unsupported."""
        backend = self.backend(
            stream_errors={1: PluginError(Reason.NETWORK)}
        )
        payload = self.assert_error(
            3,
            self.run_attachment(["attachment", _UID, "--index", "1"], backend),
            "E_ATTACHMENT_UNAVAILABLE",
        )
        self.assertEqual(
            payload["error"]["message"],
            "attachment 1 ('factura.pdf') of message "
            f"{_UID} could not be retrieved from its origin",
        )
        self.assertEqual(
            payload["error"]["hint"],
            "check the network connection and the plugin configuration, then retry",
        )
        self.assertNotIn("unsupported", payload["error"]["message"].lower())

    def test_ut_rmt_02_02_not_local_reason_uses_its_template(self) -> None:
        """UT-RMT-02.02: ``reason: not_local`` ⇒ E_ATTACHMENT_UNAVAILABLE with its hint."""
        backend = self.backend(
            stream_errors={1: PluginError(Reason.NOT_LOCAL)}
        )
        payload = self.assert_error(
            3,
            self.run_attachment(["attachment", _UID, "--index", "1"], backend),
            "E_ATTACHMENT_UNAVAILABLE",
        )
        self.assertIn("is not available in the local store", payload["error"]["message"])
        self.assertIn("downloads the attachment", payload["error"]["hint"])

    def test_ut_rmt_02_03_staging_and_cache_stay_clean(self) -> None:
        """UT-RMT-02.03: a failed origin leaves clean staging and no cache file."""
        backend = self.backend(
            stream_errors={1: PluginError(Reason.NETWORK)}
        )
        self.assert_error(
            3,
            self.run_attachment(["attachment", _UID, "--all"], backend),
            "E_ATTACHMENT_UNAVAILABLE",
        )
        self.assert_no_cache()

    def test_ut_rmt_02_04_all_reports_the_first_failure_in_index_order(self) -> None:
        """UT-RMT-02.04: ``--all`` with failures on 2 and 3 reports attachment 2."""
        backend = self.backend(
            stream_errors={
                2: PluginError(Reason.NETWORK),
                3: PluginError(Reason.NETWORK),
            }
        )
        payload = self.assert_error(
            3,
            self.run_attachment(["attachment", _UID, "--all"], backend),
            "E_ATTACHMENT_UNAVAILABLE",
        )
        self.assertIn("attachment 2", payload["error"]["message"])
        self.assertNotIn("attachment 3", payload["error"]["message"])
        self.assert_no_cache()

    def test_ut_rmt_02_05_network_in_the_second_block_is_not_a_timeout(self) -> None:
        """UT-RMT-02.05: a network failure while delivering a later block keeps its template."""
        backend = self.backend(
            attachments=[
                {
                    "index": 1,
                    "name": "factura.pdf",
                    "size_bytes": 1024,
                    "native_order_key": "1",
                    "unavailable_reason": None,
                }
            ],
            stream_chunks={1: [b"a" * 512, b"b" * 512]},
            stream_errors_at={1: (1, PluginError(Reason.NETWORK))},
        )
        payload = self.assert_error(
            3,
            self.run_attachment(["attachment", _UID, "--index", "1"], backend),
            "E_ATTACHMENT_UNAVAILABLE",
        )
        self.assertIn("could not be retrieved from its origin", payload["error"]["message"])
        self.assert_not_timeout(payload)
        self.assert_no_cache()

    def assert_not_timeout(self, payload: dict) -> None:
        self.assertNotEqual(payload["error"]["code"], "E_CLIENT_TIMEOUT")
        self.assertNotIn("did not respond within the timeout", payload["error"]["message"])


# --------------------------------------------------------------------------- #
# UT-RMT-03 — ``attachments: "none"`` is still rejected
# --------------------------------------------------------------------------- #


class RemoteCapabilityTests(_RemoteCase):
    """UT-RMT-03: only ``"none"`` is rejected, with the new hint."""

    def test_ut_rmt_03_01_none_driver_is_rejected_before_the_store(self) -> None:
        """UT-RMT-03.01: ``"none"`` ⇒ E_ATTACHMENT_UNAVAILABLE (unsupported) with the hint."""
        backend = self.backend(capabilities=dict(_NONE_CAPABILITIES))
        payload = self.assert_error(
            3,
            self.run_attachment(["attachment", _UID, "--index", "1"], backend),
            "E_ATTACHMENT_UNAVAILABLE",
        )
        self.assertIn("unsupported", payload["error"]["message"].lower())
        self.assertEqual(payload["error"]["hint"], _UNSUPPORTED_HINT)
        self.assertNotIn("find_message", backend.calls)
        self.assert_no_cache()


# --------------------------------------------------------------------------- #
# UT-RMT-04 — hard cut of an external plugin stream
# --------------------------------------------------------------------------- #


class RemoteHardCutTests(_RemoteCase):
    """UT-RMT-04: the attachment budget cuts the wait even if the plugin is blocked."""

    def _blocked_run(
        self,
        backend: FakeAttachmentBackend,
        argv: list[str],
        *,
        budget: float,
    ):
        with mock.patch.object(
            cli_mod, "_attachment_timeout", return_value=budget
        ):
            started = time.monotonic()
            result = self.run_attachment(argv, backend)
            elapsed = time.monotonic() - started
        return result, elapsed

    def test_ut_rmt_04_01_block_before_the_first_block_is_a_hard_timeout(self) -> None:
        """UT-RMT-04.01: a plugin blocked before its first block ⇒ E_CLIENT_TIMEOUT at the budget."""
        gate = threading.Event()
        backend = self.backend(stream_gates={1: (0, gate)})
        try:
            result, elapsed = self._blocked_run(
                backend, ["attachment", _UID, "--index", "1"], budget=1.0
            )
            self.assertLess(elapsed, 2.0)
            payload = self.assert_error(3, result, "E_CLIENT_TIMEOUT")
            self.assertEqual(
                payload["error"]["message"],
                "attachment 1 ('factura.pdf') of message "
                f"{_UID} did not respond within the timeout",
            )
            self.assertEqual(payload["error"]["hint"], _TIMEOUT_HINT)
            self.assert_no_cache()
            self.assertEqual(backend.block_requests.get(1), 1)
        finally:
            gate.set()

    def test_ut_rmt_04_02_block_between_two_blocks_is_a_hard_timeout(self) -> None:
        """UT-RMT-04.02: a plugin blocked after its first block ⇒ E_CLIENT_TIMEOUT."""
        gate = threading.Event()
        backend = self.backend(
            stream_chunks={1: [b"a" * 512, b"b" * 512]},
            stream_gates={1: (1, gate)},
        )
        try:
            result, elapsed = self._blocked_run(
                backend, ["attachment", _UID, "--index", "1"], budget=1.0
            )
            self.assertLess(elapsed, 2.0)
            payload = self.assert_error(3, result, "E_CLIENT_TIMEOUT")
            self.assertIn("did not respond within the timeout", payload["error"]["message"])
            self.assertEqual(payload["error"]["hint"], _TIMEOUT_HINT)
            self.assert_no_cache()
            self.assertEqual(backend.block_requests.get(1), 3)
        finally:
            gate.set()

    def test_ut_rmt_04_03_all_reports_the_first_blocked_attachment(self) -> None:
        """UT-RMT-04.03: ``--all`` with attachments 2 and 3 blocked reports 2."""
        gate_two, gate_three = threading.Event(), threading.Event()
        backend = self.backend(
            stream_gates={2: (0, gate_two), 3: (0, gate_three)},
            stream_chunks={1: [b"a" * 512], 2: [b"b" * 512], 3: [b"c" * 512]},
        )
        try:
            result, _elapsed = self._blocked_run(
                backend, ["attachment", _UID, "--all"], budget=1.0
            )
            payload = self.assert_error(3, result, "E_CLIENT_TIMEOUT")
            self.assertIn("attachment 2", payload["error"]["message"])
            self.assertNotIn("attachment 3", payload["error"]["message"])
            self.assert_no_cache()
        finally:
            gate_two.set()
            gate_three.set()

    def test_ut_rmt_04_04_staging_clean_and_plugin_thread_released(self) -> None:
        """UT-RMT-04.04: clean staging/cache and no blocked plugin thread left behind."""
        gate = threading.Event()
        backend = self.backend(stream_gates={1: (0, gate)})
        try:
            result, _elapsed = self._blocked_run(
                backend, ["attachment", _UID, "--index", "1"], budget=0.5
            )
            self.assert_error(3, result, "E_CLIENT_TIMEOUT")
            self.assert_no_cache()
            self.assertEqual(self.cache_files(), [])
        finally:
            gate.set()
        self.assertTrue(gate.is_set())

    def test_ut_rmt_04_05_stream_creation_is_not_bounded_by_the_metadata_cap(self) -> None:
        """UT-RMT-04.05: a slow stream creation succeeds when it fits the attachment budget."""
        class _SlowCreateBackend(FakeAttachmentBackend):
            def attachment_stream(self, uid, index):
                time.sleep(0.15)
                return super().attachment_stream(uid, index)

        backend = _SlowCreateBackend(
            driver=_DRIVER,
            native_uid=_NATIVE_UID,
            capabilities=dict(_REMOTE_CAPABILITIES),
            account_label=_LABEL,
        )
        with mock.patch.object(plugins_api, "METADATA_TIMEOUT_SECONDS", 0.05):
            result, elapsed = self._blocked_run(
                backend, ["attachment", _UID, "--index", "1"], budget=2.0
            )
        code, stdout, stderr = result
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(self.payload(stdout)["count"], 1)
        self.assertGreaterEqual(elapsed, 0.15)

    def test_ut_rmt_04_06_expired_deadline_empty_stream_and_failing_close(self) -> None:
        """UT-RMT-04.06: no request after expiry, empty stream succeeds and a failing close is quiet."""
        clock = _FakeClock(now=100.0)

        def advance(_index: int, _number: int) -> None:
            clock.advance(100.0)

        driver = FakeAttachmentDriver(
            [FakeAttachment("factura.pdf", chunks=[b"a" * 512, b"b" * 512])],
            on_chunk=advance,
        )
        with tempfile.TemporaryDirectory(prefix="mailquery-rmt-") as tmp:
            home = Path(tmp) / "home"
            self.assert_expired_without_new_request(home, driver, clock)

        with tempfile.TemporaryDirectory(prefix="mailquery-rmt-") as tmp:
            home = Path(tmp) / "home"
            empty = FakeAttachmentDriver([FakeAttachment("empty.dat", data=b"")])
            records = AttachmentsEngine(home, AttachmentsConfig(), empty).recover(
                "fake:1", [1]
            )
            self.assertEqual(records[0]["size_bytes"], 0)
            self.assertTrue(Path(records[0]["path"]).is_file())

        with tempfile.TemporaryDirectory(prefix="mailquery-rmt-") as tmp:
            home = Path(tmp) / "home"
            close_clock = _FakeClock(now=100.0)
            driver = _ClosingDriver(close_clock)
            engine = AttachmentsEngine(
                home, AttachmentsConfig(), driver, clock=close_clock
            )
            with self.assertRaises(MailqueryError) as caught:
                engine.recover(
                    "fake:1", [1], deadline=lambda: close_clock.now + 10.0
                )
            self.assertEqual(caught.exception.code, "E_CLIENT_TIMEOUT")

    def assert_expired_without_new_request(self, home, driver, clock) -> None:
        chunks: list[int] = []

        def advance(_index: int, number: int) -> None:
            chunks.append(number)
            clock.advance(100.0)

        driver.on_chunk = advance
        engine = AttachmentsEngine(home, AttachmentsConfig(), driver, clock=clock)
        with self.assertRaises(MailqueryError) as caught:
            engine.recover("fake:1", [1], deadline=lambda: clock.now + 10.0)
        self.assertEqual(caught.exception.code, "E_CLIENT_TIMEOUT")
        # The expired budget never asks the driver for the following block: only
        # the first block of the content screen was requested.
        self.assertEqual(driver.opens(1), 1)
        self.assertEqual(chunks, [0])


class _FakeClock:
    """Monotonic clock the tests advance between driver chunks."""

    def __init__(self, now: float = 0.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _ClosingDriver:
    """Driver whose stream iterator raises from ``close()`` after the deadline."""

    driver = "fake"

    def __init__(self, clock: _FakeClock) -> None:
        self._clock = clock
        self.requested = 0

    def parse_native_id(self, native_id: str) -> str:
        return native_id

    def attachments(self, uid: str):
        return [
            {
                "index": 1,
                "name": "factura.pdf",
                "size_bytes": 1024,
                "native_order_key": "1",
                "unavailable_reason": None,
            }
        ]

    def attachment_stream(self, uid: str, index: int):
        return _ClosingIterator(self._clock)


class _ClosingIterator:
    """Iterator that yields one block, advances the clock and fails on close."""

    def __init__(self, clock: _FakeClock) -> None:
        self._clock = clock
        self._yielded = False
        self.requests = 0

    def __iter__(self) -> "_ClosingIterator":
        return self

    def __next__(self) -> bytes:
        self.requests += 1
        if self._yielded:
            raise StopIteration
        self._yielded = True
        self._clock.advance(100.0)
        return b"a" * 512

    def close(self) -> None:
        raise RuntimeError("the plugin iterator failed to close")


# --------------------------------------------------------------------------- #
# UT-RMT-05 — untouched caps, native drivers and what does not consume the budget
# --------------------------------------------------------------------------- #


class RemoteBudgetScopeTests(_RemoteCase):
    """UT-RMT-05: metadata/COM caps, native checks and exceptions to the budget."""

    def test_ut_rmt_05_01_metadata_and_com_caps_ignore_the_attachment_budget(self) -> None:
        """UT-RMT-05.01: the metadata deadline stays fixed for 10 and 600 seconds."""
        self.assertEqual(plugins_api.METADATA_TIMEOUT_SECONDS, 30.0)
        self.assertEqual(EXTRACTION_TIMEOUT_SECONDS, 60.0)
        self.assertEqual(outlook_com.CALL_TIMEOUT_SECONDS, 30.0)
        for value in (10, 600):
            with self.subTest(timeout_seconds=value):
                backend = FakePluginBackend(delays={"find_message": 0.1})
                entry = FakeEntryPoint(_DRIVER, plugin=backend)
                registry = BackendRegistry(
                    entry_points=[*internal_entry_points(), entry]
                )
                config = (
                    f'[scope."{_DRIVER}:{PLUGIN_ACCOUNT_LABEL}"]\n'
                    f"[attachments]\ntimeout_seconds = {value}\n"
                )
                with mock.patch.object(
                    plugins_api, "METADATA_TIMEOUT_SECONDS", 0.05
                ):
                    payload = self.assert_error(
                        3,
                        self.run_attachment(
                            ["attachment", _UID, "--index", "1"],
                            backend,
                            config=config,
                            registry=registry,
                        ),
                        "E_CLIENT_TIMEOUT",
                    )
                self.assertEqual(
                    payload["error"]["hint"],
                    'run "mailquery doctor" and check the driver; do not retry in a loop',
                )
                self.assertNotEqual(payload["error"]["hint"], _TIMEOUT_HINT)

    def test_ut_rmt_05_02_native_drivers_check_between_blocks_inline(self) -> None:
        """UT-RMT-05.02: Apple Mail and Outlook are checked between blocks in the main thread."""
        for name in ("apple_mail", "outlook"):
            with self.subTest(driver=name):
                clock = _FakeClock(now=100.0)
                creator: list[str] = []

                class _InlineDriver(FakeAttachmentDriver):
                    def attachment_stream(self, uid, index):
                        creator.append(threading.current_thread().name)
                        return super().attachment_stream(uid, index)

                driver = _InlineDriver(
                    [FakeAttachment("factura.pdf", chunks=[b"a" * 512, b"b" * 512])],
                    on_chunk=lambda _index, _number: clock.advance(3.0),
                )
                driver.driver = name
                wrapped = wrap_driver(driver, driver=name)
                with tempfile.TemporaryDirectory(prefix="mailquery-rmt-") as tmp:
                    home = Path(tmp) / "home"
                    engine = AttachmentsEngine(
                        home, AttachmentsConfig(), wrapped, clock=clock
                    )
                    with self.assertRaises(MailqueryError) as caught:
                        engine.recover(
                            "fake:1", [1], deadline=lambda: clock.now + 5.0
                        )
                self.assertEqual(caught.exception.code, "E_CLIENT_TIMEOUT")
                self.assertGreaterEqual(len(creator), 2)
                self.assertEqual(
                    creator, [threading.current_thread().name] * len(creator)
                )

    def test_ut_rmt_05_03_cache_hit_and_active_content_do_not_consume_the_budget(self) -> None:
        """UT-RMT-05.03: a cache hit never invokes the deadline factory; A7 runs outside it."""
        with tempfile.TemporaryDirectory(prefix="mailquery-rmt-") as tmp:
            home = Path(tmp) / "home"
            driver = FakeAttachmentDriver(
                [FakeAttachment("factura.pdf", data=b"cached bytes")]
            )
            engine = AttachmentsEngine(home, AttachmentsConfig(), driver)
            engine.recover("fake:1", [1])
            factory = mock.Mock(
                side_effect=AssertionError("a cache hit must not consume the budget")
            )
            records = engine.recover("fake:1", [1], deadline=factory)
            factory.assert_not_called()
            self.assertTrue(records[0]["cached"])

        marker = b"%PDF-1.7\n/JavaScript "
        backend = FakeAttachmentBackend(
            attachments=[
                {
                    "index": 1,
                    "name": "factura.pdf",
                    "size_bytes": len(marker),
                    "native_order_key": "1",
                    "unavailable_reason": None,
                }
            ],
            stream_chunks={1: [marker]},
        )
        config = (
            '[scope."apple_mail:iCloud (attachment@fixture.example)"]\n'
        )
        self.run_attachment(
            ["attachment", "apple_mail:83143", "--index", "1"],
            backend,
            config=config,
        )
        slow_detector = mock.Mock(
            side_effect=lambda path: ("pdf-javascript",)
        )
        with (
            mock.patch.object(cli_mod, "_attachment_timeout", return_value=0.0),
            mock.patch.object(cli_mod, "active_content_types", slow_detector),
        ):
            code, stdout, stderr = self.run_attachment(
                ["attachment", "apple_mail:83143", "--index", "1"],
                backend,
                config=config,
            )
        self.assertEqual((code, stderr), (0, ""))
        payload = self.payload(stdout)
        self.assertTrue(payload["attachments"][0]["cached"])
        self.assertEqual(
            payload["warnings"],
            [
                "W_ATTACHMENT_ACTIVE_CONTENT: attachment 1 contains pdf-javascript "
                "in apple_mail:83143"
            ],
        )
        slow_detector.assert_called()

    def test_ut_rmt_05_04_cli_passes_the_configured_budget(self) -> None:
        """UT-RMT-05.04: ``cli`` hands ``[attachments].timeout_seconds`` to the engine."""
        backend = self.backend()
        config = _CONFIG + "[attachments]\ntimeout_seconds = 180\n"
        seen: dict[str, float] = {}
        original = AttachmentsEngine.recover

        def spy(self, uid, indices=None, *, force=False, deadline=None, entries=None):
            seen["budget"] = deadline() - time.monotonic()
            return original(
                self, uid, indices, force=force, deadline=deadline, entries=entries
            )

        with mock.patch.object(AttachmentsEngine, "recover", spy):
            code, stdout, stderr = self.run_attachment(
                ["attachment", _UID, "--index", "1"], backend, config=config
            )
        self.assertEqual((code, stderr), (0, ""))
        self.assertGreaterEqual(seen["budget"], 178.0)
        self.assertLessEqual(seen["budget"], 180.5)

    def test_ut_rmt_05_05_the_outlook_com_timeout_keeps_its_message_and_hint(self) -> None:
        """UT-RMT-05.05: a COM watchdog timeout before the budget keeps the RF-33 text."""
        with mock.patch.object(outlook_com, "CALL_TIMEOUT_SECONDS", 0.05):
            backend = self.backend(
                driver="outlook",
                native_uid=83143,
                capabilities={
                    "network": False,
                    "readonly": "structural",
                    "body_local": True,
                    "attachments": "local",
                    "native_order": "numeric",
                },
                stream_errors={1: outlook_com.client_timeout(0.05)},
            )
            with mock.patch.object(cli_mod, "_attachment_timeout", return_value=10.0):
                payload = self.assert_error(
                    3,
                    self.run_attachment(
                        ["attachment", "outlook:83143", "--index", "1"],
                        backend,
                        config=f'[scope."outlook:{_LABEL}"]\n',
                    ),
                    "E_CLIENT_TIMEOUT",
                )
        self.assertIn("Outlook did not respond within 0.05 s", payload["error"]["message"])
        self.assertIn("security prompt", payload["error"]["hint"])
        self.assertNotEqual(payload["error"]["hint"], _TIMEOUT_HINT)
        self.assert_no_cache()


# --------------------------------------------------------------------------- #
# DOC-09 — README and skill documentation of F2 and A7
# --------------------------------------------------------------------------- #


class AttachmentDocumentationTests(unittest.TestCase):
    """DOC-09: the READMEs and the skill document ``"remote"`` and A7."""

    def test_doc_09_01_readmes_document_timeout_remote_and_active_content(self) -> None:
        """DOC-09.01: both READMEs document the timeout, ``"remote"`` drivers and A7."""
        for path in (_README, _README_ES):
            text = _read(path)
            with self.subTest(readme=path.name):
                self.assertIn("timeout_seconds", text)
                self.assertRegex(text, r"(?i)10\s*(?:\.\.|–|-|to)\s*600")
                self.assertRegex(text, r"(?i)60\s*(?:s\b|seconds|segundos|por defecto|default)")
                self.assertIn('attachments: "remote"', text)
                self.assertIn("W_ATTACHMENT_ACTIVE_CONTENT", text)

    def test_doc_09_02_skill_names_active_content_in_security_rules(self) -> None:
        """DOC-09.02: the skill states the A7 rule and no longer denies remote attachments."""
        text = _read(_SKILL)
        security = text.split("## Security rules", 1)[1]
        self.assertIn("W_ATTACHMENT_ACTIVE_CONTENT", security)
        show_section = text.split("## `show` and `attachment`", 1)[1].split(
            "## Examples", 1
        )[0]
        self.assertRegex(show_section, r'(?i)attachments:\s*"remote"')
        self.assertRegex(show_section, r"(?i)recover")
        stale = re.search(
            r'(?i)remote[^.\n]{0,120}(?:cannot be recovered|not (?:available|supported|recoverable))',
            text,
        )
        self.assertIsNone(stale, stale.group(0) if stale else "")


if __name__ == "__main__":
    unittest.main()

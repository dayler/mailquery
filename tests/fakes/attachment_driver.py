"""In-memory attachment driver double for the UT-ATT-06..11 engine tests (M07).

The double stands in for a ``MailBackend`` (C1) at the attachment boundary
fixed by ``backends/base.py``: it exposes ``driver``, ``parse_native_id``,
``attachments(uid)`` and ``attachment_stream(uid, index)`` and never touches
the application home, the attachment cache or the staging area (the core owns
every byte written; PRD RF-47/RNF-13). Every reachable failure is
injected from the test:

* metadata failures through ``FakeAttachmentDriver(metadata_error=...)`` or
  ``failures={"metadata": exc}``;
* stream opening failures through ``failures={"open:<index>": exc}``;
* stream read failures (before the first/after the n-th chunk) through
  ``failures={"read:<index>": exc, "read_after:<index>": n}``;
* fake clocks and concurrent deletions through the ``on_chunk`` hook, which
  runs before every yielded chunk.

``DriverFailure`` is duck-typed like ``mailquery.plugins.PluginError``: it only
carries a ``reason`` (and optional ``hint``/``detail``) so the M07 engine can be
tested without importing ``mailquery.plugins`` (UT-ATT-01.09 keeps
``attachments/**`` free of that package). The double is pure in-memory: it
writes nothing and reads nothing.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from typing import Any, Final

#: Driver name of the double; a valid external ``[a-z0-9_]{1,64}`` name.
DRIVER: Final[str] = "fake"

#: Sentinels for the metadata size of an attachment.
_AUTO: Final[object] = object()

#: Capabilities of a local, offline, read-only driver (API 1).
CAPABILITIES: dict[str, Any] = {
    "network": False,
    "readonly": "structural",
    "body_local": True,
    "attachments": "local",
    "native_order": "text",
}


class DriverFailure(Exception):
    """Duck-typed ``PluginError``: only ``reason``/``hint``/``detail`` (M05 contract)."""

    def __init__(self, reason: str, hint: str = "", detail: str = "") -> None:
        self.reason = reason
        self.hint = hint
        self.detail = detail
        super().__init__(reason)


class FakeAttachment:
    """One attachment of the fake message: decoded chunks and metadata size.

    ``known_size`` defaults to the total chunk length (the driver knows it);
    pass ``known_size=None`` to model an attachment whose size is unknown until
    it is streamed, or an explicit integer to model a mismatching expected size.
    """

    def __init__(
        self,
        name: str,
        *,
        data: bytes = b"",
        chunks: Sequence[bytes] | None = None,
        known_size: int | None | object = _AUTO,
        unavailable_reason: str | None = None,
    ) -> None:
        self.name = name
        self.chunks = list(chunks) if chunks is not None else ([data] if data else [])
        if known_size is _AUTO:
            self.known_size: int | None = sum(len(chunk) for chunk in self.chunks)
        else:
            self.known_size = known_size  # type: ignore[assignment]
        self.unavailable_reason = unavailable_reason

    @property
    def data(self) -> bytes:
        """All decoded bytes of the attachment."""
        return b"".join(self.chunks)


def chunks_of(data: bytes, size: int) -> list[bytes]:
    """Split ``data`` into chunks of at most ``size`` bytes."""
    if size < 1:
        raise ValueError("chunk size must be >= 1")
    return [data[offset : offset + size] for offset in range(0, len(data), size)] or [b""]


class FakeAttachmentDriver:
    """Duck-typed ``MailBackend`` (attachment operations only), all failures injectable."""

    driver = DRIVER
    plugin_api = 1
    capabilities = dict(CAPABILITIES)
    native_order = "text"
    version = "0.1.0"
    labels_available = True

    def __init__(
        self,
        attachments: Sequence[FakeAttachment] = (),
        *,
        failures: dict[str, BaseException] | None = None,
        metadata_error: BaseException | None = None,
        on_chunk: Callable[[int, int], None] | None = None,
    ) -> None:
        self._attachments = list(attachments)
        self.failures = dict(failures or {})
        self.metadata_error = metadata_error
        self.on_chunk = on_chunk
        #: Operations observed; ``("attachments", uid)`` / ``("attachment_stream", index)``.
        self.calls: list[tuple[Any, ...]] = []
        #: Indexes whose stream was opened, in order (a fresh stream per call).
        self.stream_opens: list[int] = []

    # -- contract metadata -------------------------------------------------- #

    @staticmethod
    def parse_native_id(native_id: str) -> str:
        """A plugin native id is an opaque non-empty string (RF-40)."""
        if not isinstance(native_id, str) or not native_id:
            raise DriverFailure("invalid_uid", "empty native id")
        return native_id

    def describe(self) -> dict[str, Any]:
        return {
            "backend": self.driver,
            "version": self.version,
            "strategy": "plugin",
            "schema_ok": True,
        }

    # -- attachment operations (C1) ----------------------------------------- #

    def attachments(self, uid: str) -> list[dict[str, Any]]:
        """Ordered ``AttachmentMetadataRow`` list (1..N) of the fake message."""
        self.calls.append(("attachments", uid))
        if self.metadata_error is not None:
            raise self.metadata_error
        failure = self.failures.get("metadata")
        if failure is not None:
            raise failure
        return [
            {
                "index": index,
                "name": attachment.name,
                "size_bytes": attachment.known_size,
                "native_order_key": str(index),
                "unavailable_reason": attachment.unavailable_reason,
            }
            for index, attachment in enumerate(self._attachments, start=1)
        ]

    def attachment_stream(self, uid: str, index: int) -> Iterator[bytes]:
        """Decoded bytes of ``index``; failures are injected by the test."""
        self.calls.append(("attachment_stream", index))
        self.stream_opens.append(index)
        failure = self.failures.get(f"open:{index}")
        if failure is not None:
            raise failure
        return self._stream(index)

    # -- observability ------------------------------------------------------ #

    def metadata_calls(self) -> int:
        """Number of ``attachments()`` calls (one per ``show``/``recover``)."""
        return sum(1 for call in self.calls if call[0] == "attachments")

    def opens(self, index: int) -> int:
        """Number of streams opened for ``index`` (screening and extraction both count)."""
        return self.stream_opens.count(index)

    # -- internals ---------------------------------------------------------- #

    def _stream(self, index: int) -> Iterator[bytes]:
        attachment = self._attachments[index - 1]
        failure = self.failures.get(f"read:{index}")
        fail_after = self.failures.get(f"read_after:{index}")
        after = fail_after if isinstance(fail_after, int) else None
        try:
            for number, chunk in enumerate(attachment.chunks):
                if self.on_chunk is not None:
                    self.on_chunk(index, number)
                if failure is not None and (after is None or number == after):
                    raise failure
                yield chunk
        finally:
            pass

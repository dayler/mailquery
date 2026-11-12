"""Attachment cache, staging area and atomic publication (M07, C7).

Filesystem half of the attachment milestone (PRD-v2.1 RF-45/RF-47/RF-51,
§10.1, §10.4, §11.3 row 15, RNF-13/RNF-14). :class:`AttachmentCache` owns the
read side (cache hit detection, ``sha256`` of the served file, the regular-file
rule of ``show``) and the publication side (private directories, ``os.replace``
of a staged file). :class:`StagingArea` owns the core staging directory under
``~/.mailquery/tmp/staging/``: opaque session and file names, ``0700``
directories and ``0600`` files on POSIX, removal in ``finally`` and cleanup of
the core's own orphan sessions (never plugin directories nor backend caches).

Nothing here decides policy or composes user-facing messages beyond mapping
filesystem failures to ``E_IO``/``E_PERMISSION`` (DP-01; §11.3 row 15): the
engine decides limits, screening and cache semantics.

Permissions: ``_SECURE_PERMISSIONS`` is ``False`` on Windows, where the profile
ACL is inherited and never relaxed (RNF-13); tests patch it to exercise the
Windows branch on POSIX. The test seams ``_chmod``, ``_ensure_private_dir``,
``_create_staging_file``, ``_write_chunk`` and ``_atomic_replace`` exist so a
failure can be injected without patching the ``os`` module globally.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from mailquery.attachments.paths import attachment_path, message_dir
from mailquery.attachments.sanitize import sanitize_name
from mailquery.errors import MailqueryError

#: Name of the core staging directory under ``~/.mailquery/tmp`` (§10.1).
STAGING_DIR_NAME: Final[str] = "staging"
_SESSION_PREFIX: Final[str] = "session-"
_FILE_SUFFIX: Final[str] = ".part"
_HASH_CHUNK_BYTES: Final[int] = 1024 * 1024

#: POSIX permissions are applied only where the platform supports them (RNF-13).
_SECURE_PERMISSIONS: bool = os.name != "nt"


@dataclass(frozen=True, slots=True)
class CacheHit:
    """A regular cached file that can be served without re-extraction (RF-45)."""

    path: Path
    size_bytes: int
    sha256: str


def cached_path(
    home: str | Path,
    uid: str,
    original_name: str,
    index: int,
    *,
    platform: str | None = None,
) -> Path | None:
    """Return the served cache path of one attachment, or ``None`` (RF-43, C7).

    Frozen contract for M08: ``show`` computes ``message.attachments[].cached_path``
    with this function. The path is the deterministic
    ``<home>/attachments/<driver>/<native_id>/<sanitized_name>`` built by M06;
    it is returned only when the entry is a **regular file** (``lstat``-based, so
    a symlink, directory or device is not cache). The name-safety rule
    (``classify_name``) belongs to ``show``, not to this helper, and nothing is
    created, opened or read.
    """
    path = attachment_path(
        home, uid, sanitize_name(original_name, index), platform=platform
    )
    return path if _is_regular_file(path) else None


class StagedAttachment:
    """One opaque file inside the core staging session, hashed while written."""

    def __init__(self, path: Path, handle: object | None = None) -> None:
        self._path = path
        self._handle = handle
        self.size_bytes = 0
        self._hash = hashlib.sha256()
        self._finished = False

    @property
    def path(self) -> Path:
        """Absolute path of the staged file (internal to the session)."""
        return self._path

    @property
    def sha256(self) -> str:
        """SHA-256 of the bytes written so far (complete after ``finish``)."""
        return self._hash.hexdigest()

    def append(self, chunk: bytes) -> None:
        """Write one decoded chunk, updating the size and the SHA-256."""
        if not chunk:
            return
        try:
            _write_chunk(self._handle, chunk)
        except OSError as exc:
            raise _map_os_error(exc, "cannot write the attachment staging file") from exc
        self._hash.update(chunk)
        self.size_bytes += len(chunk)

    def finish(self) -> None:
        """Flush, fsync and close the staged file (mode ``0600`` on POSIX)."""
        if self._finished:
            return
        handle = self._handle
        self._handle = None
        if handle is not None:
            try:
                handle.flush()  # type: ignore[attr-defined]
                os.fsync(handle.fileno())  # type: ignore[attr-defined]
                handle.close()  # type: ignore[attr-defined]
            except OSError as exc:
                raise _map_os_error(
                    exc, "cannot write the attachment staging file"
                ) from exc
        _chmod(self._path, 0o600)
        self._finished = True

    def publish(self, target: Path) -> None:
        """Atomically move the finished file to ``target`` (RF-45, RNF-14)."""
        self.finish()
        _reject_non_regular_target(target)
        try:
            _atomic_replace(self._path, target)
        except OSError as exc:
            raise _map_os_error(
                exc, "cannot publish the attachment to the cache"
            ) from exc
        _chmod(target, 0o600)

    def discard(self) -> None:
        """Best-effort removal of an unpublished staging file."""
        handle = self._handle
        self._handle = None
        if handle is not None:
            try:
                handle.close()  # type: ignore[attr-defined]
            except OSError:  # pragma: no cover - cleanup must not mask a failure
                pass
        try:
            self._path.unlink(missing_ok=True)
        except OSError:  # pragma: no cover - cleanup must not mask a failure
            pass


class StagingArea:
    """Core staging session under ``<home>/tmp/staging`` (M07; §10.1, RNF-14).

    The root is created lazily on the first staged file, so a pure cache-hit
    invocation writes nothing. Each run gets one opaque session directory
    (``0700``); ``close`` removes the session and any file still inside it.
    When the root is touched, entries left by a crashed previous run are
    removed: only the core's own staging directory is swept (never
    ``tmp/plugin-<driver>/`` nor a backend cache).
    """

    def __init__(self, home: str | Path) -> None:
        self._home = Path(home)
        self._root: Path | None = None
        self._session: Path | None = None
        self._files: list[StagedAttachment] = []

    def __enter__(self) -> "StagingArea":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    @property
    def session(self) -> Path | None:
        """The current session directory (``None`` until the first staged file)."""
        return self._session

    def _ensure(self) -> Path:
        if self._session is not None:
            return self._session
        root = self._home / "tmp" / STAGING_DIR_NAME
        try:
            _ensure_private_dir(root)
            session = Path(tempfile.mkdtemp(prefix=_SESSION_PREFIX, dir=root))
        except OSError as exc:
            raise _map_os_error(
                exc, "cannot create the attachment staging area"
            ) from exc
        _chmod(session, 0o700)
        self._root = root
        self._session = session
        _discard_orphan_sessions(root, session)
        return session

    def new_file(self) -> StagedAttachment:
        """Create an opaque session/``0600``-file and return its writer."""
        session = self._ensure()
        try:
            descriptor, name = _create_staging_file(session)
            handle = os.fdopen(descriptor, "wb")
        except OSError as exc:
            raise _map_os_error(
                exc, "cannot create the attachment staging file"
            ) from exc
        path = Path(name)
        _chmod(path, 0o600)
        staged = StagedAttachment(path, handle)
        self._files.append(staged)
        return staged

    def close(self) -> None:
        """Discard unpublished files and remove this run's session directory."""
        for staged in self._files:
            staged.discard()
        self._files.clear()
        session = self._session
        self._session = None
        if session is not None:
            shutil.rmtree(session, ignore_errors=True)


class AttachmentCache:
    """Read side and publication side of ``~/.mailquery/attachments`` (RF-45, C7).

    ``uid`` is the canonical ``"<driver>:<native_id>"`` string (C3); the path is
    always the M06 ``message_dir``/``attachment_path`` result, so the layout is
    deterministic and shared with ``show``. No function here creates anything
    until :meth:`ensure_message_dir` (publication) or :meth:`staging` is used.
    """

    def __init__(
        self,
        home: str | Path,
        uid: str,
        *,
        platform: str | None = None,
    ) -> None:
        self._home = Path(home)
        self._uid = uid
        self._platform = platform

    @property
    def home(self) -> Path:
        """The application home passed to the constructor."""
        return self._home

    @property
    def uid(self) -> str:
        """The canonical uid of the message."""
        return self._uid

    def message_dir(self) -> Path:
        """The message cache directory (nothing is created)."""
        return message_dir(self._home, self._uid, platform=self._platform)

    def path_for(self, original_name: str, index: int) -> Path:
        """The final cache path of one attachment (nothing is created)."""
        return attachment_path(
            self._home,
            self._uid,
            sanitize_name(original_name, index),
            platform=self._platform,
        )

    def lookup(
        self,
        original_name: str,
        index: int,
        *,
        expected_size: int | None = None,
    ) -> CacheHit | None:
        """Return the served file as a hit, or ``None`` for a miss (RF-45).

        A hit requires a regular file (``lstat``: symlink, directory or device
        are misses) and, when the driver knows it, the expected size. The
        ``sha256`` is read from the existing file. Any filesystem error while
        probing/hashing the cache is a miss too (best-effort cache, RF-51), so
        a file deleted by the external cron is re-extracted once.
        """
        path = self.path_for(original_name, index)
        try:
            info = os.stat(path, follow_symlinks=False)
        except OSError:
            return None
        if not stat.S_ISREG(info.st_mode):
            return None
        if expected_size is not None and info.st_size != expected_size:
            return None
        try:
            digest, size = _hash_file(path)
        except OSError:
            return None
        if size != info.st_size:
            return None
        return CacheHit(path=path, size_bytes=size, sha256=digest)

    def verify(self, hit: CacheHit) -> bool:
        """Re-check a hit before serving it (tolerates concurrent deletion, RF-51)."""
        try:
            info = os.stat(hit.path, follow_symlinks=False)
        except OSError:
            return False
        return stat.S_ISREG(info.st_mode) and info.st_size == hit.size_bytes

    def ensure_message_dir(self) -> Path:
        """Create the private ``0700`` message directory before publication."""
        directory = self.message_dir()
        try:
            _ensure_private_dir(directory)
        except OSError as exc:
            raise _map_os_error(
                exc, "cannot create the attachment cache directory"
            ) from exc
        return directory

    def staging(self) -> StagingArea:
        """Return a fresh staging session writer for this invocation."""
        return StagingArea(self._home)

    def publish(self, staged: StagedAttachment, original_name: str, index: int) -> Path:
        """Publish a staged file under the deterministic cache name (atomic)."""
        directory = self.ensure_message_dir()
        target = directory / sanitize_name(original_name, index)
        staged.publish(target)
        return target


# --------------------------------------------------------------------------- #
# Low-level filesystem helpers (test seams)
# --------------------------------------------------------------------------- #


def _chmod(path: Path, mode: int) -> None:
    """Apply a POSIX mode; on Windows the profile ACL is inherited (RNF-13)."""
    if not _SECURE_PERMISSIONS:
        return
    try:
        os.chmod(path, mode)
    except OSError:  # pragma: no cover - best effort on foreign filesystems
        pass


def _ensure_private_dir(directory: Path) -> None:
    """Create ``directory`` and any missing parent with mode ``0700`` (POSIX)."""
    missing: list[Path] = []
    current = directory
    while True:
        try:
            current.lstat()
        except FileNotFoundError:
            missing.append(current)
            parent = current.parent
            if parent == current:
                break
            current = parent
            continue
        except OSError:
            missing.append(current)
        break
    for path in reversed(missing):
        path.mkdir(mode=0o700, exist_ok=True)
    _chmod(directory, 0o700)


def _create_staging_file(directory: Path) -> tuple[int, str]:
    """Create one opaque staging file (``mkstemp``) inside the session."""
    return tempfile.mkstemp(prefix="", suffix=_FILE_SUFFIX, dir=directory)


def _write_chunk(handle: object, chunk: bytes) -> None:
    """Write one chunk to the staging handle (test seam for ``ENOSPC``)."""
    handle.write(chunk)  # type: ignore[attr-defined]


def _reject_non_regular_target(target: Path) -> None:
    """A directory (or other non-regular entry) at the cache path is an I/O failure.

    ``os.replace`` onto a directory raises ``IsADirectoryError`` on POSIX but
    ``PermissionError`` on Windows; DP-01 keeps ``E_PERMISSION`` for permission
    problems, so classify a directory explicitly as ``E_IO``.
    """
    try:
        info = os.lstat(target)
    except FileNotFoundError:
        return
    except OSError:  # pragma: no cover - let os.replace report the failure
        return
    if stat.S_ISDIR(info.st_mode):
        raise MailqueryError(
            "E_IO",
            "cannot publish the attachment to the cache: the cache path is a directory",
            "remove the directory from ~/.mailquery/attachments and retry",
            "cannot publish: cache path is a directory",
        )


def _atomic_replace(source: Path, target: Path) -> None:
    """Atomically publish ``source`` at ``target`` (same-file-system ``os.replace``)."""
    os.replace(source, target)


def _discard_orphan_sessions(root: Path, keep: Path) -> None:
    """Remove the core's own staging sessions left by a crashed previous run."""
    try:
        entries = list(root.iterdir())
    except OSError:  # pragma: no cover - root was just created
        return
    for entry in entries:
        if entry == keep:
            continue
        try:
            if entry.is_dir() and not entry.is_symlink():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink(missing_ok=True)
        except OSError:  # pragma: no cover - cleanup must not mask a failure
            pass


def _is_regular_file(path: Path) -> bool:
    try:
        info = os.stat(path, follow_symlinks=False)
    except OSError:
        return False
    return stat.S_ISREG(info.st_mode)


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(_HASH_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _map_os_error(exc: OSError, operation: str) -> MailqueryError:
    """Map a filesystem failure to ``E_PERMISSION``/``E_IO`` (DP-01, §11.3 row 15)."""
    if isinstance(exc, PermissionError):
        return MailqueryError(
            "E_PERMISSION",
            f"{operation}: permission denied",
            "check that ~/.mailquery is writable by the current user, then retry",
            operation,
        )
    detail = exc.strerror or str(exc)
    return MailqueryError(
        "E_IO",
        f"{operation}: {detail}",
        "check free space and permissions under ~/.mailquery, then retry",
        operation,
    )


__all__ = [
    "AttachmentCache",
    "CacheHit",
    "STAGING_DIR_NAME",
    "StagedAttachment",
    "StagingArea",
    "cached_path",
]

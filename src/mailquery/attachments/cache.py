"""Attachment cache, staging area and atomic publication.

Filesystem half of the attachment core. :class:`AttachmentCache` owns the
read side (cache hit detection, ``sha256`` of the served file, the regular-file
rule of ``show``) and the publication side (private directories, ``os.replace``
of a staged file, the per-message manifest).

Cache hits are validated against the **per-message manifest**
``<message_dir>/.manifest.json``: every published attachment is registered
with its ``sanitized_name``, ``size_bytes`` and the
``sha256`` computed while it was staged (bytes that already passed the name and
content screen). A hit is a regular file at the deterministic path whose entry
matches name, size and SHA-256; the driver's expected size is never compared
(Outlook reports ``Attachment.Size`` with MAPI overhead). Every other entry at
the path is *unverified*: it is never served and the engine replaces or removes
it. The message directory and its parents up to ``attachments/`` must be real
directories (never a symlink or junction). :class:`StagingArea` owns the core
staging directory under
``~/.mailquery/tmp/staging/``: opaque session and file names, ``0700``
directories and ``0600`` files on POSIX, removal in ``finally`` and cleanup of
the core's own orphan sessions (never plugin directories nor backend caches).

Nothing here decides policy or composes user-facing messages beyond mapping
filesystem failures to ``E_IO``/``E_PERMISSION``: the
engine decides limits, screening and cache semantics.

Permissions: ``_SECURE_PERMISSIONS`` is ``False`` on Windows, where the profile
ACL is inherited and never relaxed; tests patch it to exercise the
Windows branch on POSIX. The test seams ``_chmod``, ``_ensure_private_dir``,
``_create_staging_file``, ``_write_chunk`` and ``_atomic_replace`` exist so a
failure can be injected without patching the ``os`` module globally.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from mailquery.attachments.paths import attachment_path, cache_root, message_dir
from mailquery.attachments.sanitize import sanitize_name
from mailquery.errors import MailqueryError

#: Name of the core staging directory under ``~/.mailquery/tmp``.
STAGING_DIR_NAME: Final[str] = "staging"
_SESSION_PREFIX: Final[str] = "session-"
_FILE_SUFFIX: Final[str] = ".part"
_HASH_CHUNK_BYTES: Final[int] = 1024 * 1024

#: Per-message manifest of the published attachments. Sanitized names
#: always start with ``NN_``, so the leading dot never collides with one.
MANIFEST_NAME: Final[str] = ".manifest.json"
MANIFEST_VERSION: Final[int] = 1
#: A manifest larger than this is not trusted (treated as missing).
_MANIFEST_MAX_BYTES: Final[int] = 1024 * 1024
_SHA256_HEX: Final[re.Pattern[str]] = re.compile(r"[0-9a-f]{64}")
#: ``IO_REPARSE_TAG_NAME_SURROGATE`` bit: symlinks and junctions on Windows.
_NAME_SURROGATE_BIT: Final[int] = 0x20000000

#: POSIX permissions are applied only where the platform supports them.
_SECURE_PERMISSIONS: bool = os.name != "nt"


@dataclass(frozen=True, slots=True)
class CacheHit:
    """A verified cached file that can be served without re-extraction."""

    path: Path
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    """One registered attachment of the per-message manifest."""

    sanitized_name: str
    size_bytes: int
    sha256: str


#: Parsed manifest: 1-based attachment index → its registered entry.
Manifest = dict[int, ManifestEntry]


def cached_path(
    home: str | Path,
    uid: str,
    original_name: str,
    index: int,
    *,
    platform: str | None = None,
) -> Path | None:
    """Return the served cache path of one attachment, or ``None``.

    Stable contract: ``show`` computes ``message.attachments[].cached_path``
    with this function. The path is the deterministic
    ``<home>/attachments/<driver>/<native_id>/<sanitized_name>`` built by ``paths``;
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
        """Atomically move the finished file to ``target``."""
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
    """Core staging session under ``<home>/tmp/staging``.

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
    """Read side and publication side of ``~/.mailquery/attachments``.

    ``uid`` is the canonical ``"<driver>:<native_id>"`` string; the path is
    always the ``message_dir``/``attachment_path`` result, so the layout is
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

    def manifest_path(self) -> Path:
        """The per-message manifest path (nothing is created)."""
        return self.message_dir() / MANIFEST_NAME

    def read_manifest(self) -> Manifest:
        """Return the valid entries of the message manifest (never raises).

        A missing, oversized, non-regular (symlink, directory) or unparsable
        manifest, or one under a message directory that is not real, is an
        empty manifest: every cached file of the message is then unverified.
        Individually malformed entries are dropped.
        """
        if not self.directories_are_real():
            return {}
        path = self.manifest_path()
        try:
            info = os.stat(path, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or info.st_size > _MANIFEST_MAX_BYTES:
                return {}
            with _open_no_follow(path) as handle:
                document = json.loads(handle.read(_MANIFEST_MAX_BYTES + 1))
        except (OSError, ValueError):
            return {}
        return _parse_manifest(document)

    def lookup(
        self,
        original_name: str,
        index: int,
        manifest: Manifest | None = None,
    ) -> CacheHit | None:
        """Return the cached file as a verified hit, or ``None`` for a miss.

        A hit requires real message directories, a regular file at the
        deterministic path (``lstat``: symlink, directory or device are misses)
        and a manifest entry with the same ``sanitized_name``, the same size
        and the same SHA-256 as the file. The driver's expected size is never
        compared. Any filesystem error while probing/hashing the cache is a
        miss too (best-effort cache), so a file deleted by the external
        cron is re-extracted once.
        """
        if manifest is None:
            manifest = self.read_manifest()
        entry = manifest.get(index)
        path = self.path_for(original_name, index)
        if entry is None or entry.sanitized_name != path.name:
            return None
        if not self.directories_are_real():
            return None
        try:
            info = os.stat(path, follow_symlinks=False)
        except OSError:
            return None
        if not stat.S_ISREG(info.st_mode) or info.st_size != entry.size_bytes:
            return None
        try:
            digest, size = _hash_file(path)
        except OSError:
            return None
        if size != info.st_size or digest != entry.sha256:
            return None
        return CacheHit(path=path, size_bytes=size, sha256=digest)

    def occupied(self, original_name: str, index: int) -> bool:
        """Whether anything (file, link, directory...) exists at the cache path."""
        try:
            os.stat(self.path_for(original_name, index), follow_symlinks=False)
        except OSError:
            return False
        return True

    def verify(self, hit: CacheHit) -> bool:
        """Re-check a hit before serving it (tolerates concurrent deletion)."""
        try:
            info = os.stat(hit.path, follow_symlinks=False)
        except OSError:
            return False
        return stat.S_ISREG(info.st_mode) and info.st_size == hit.size_bytes

    def directories_are_real(self) -> bool:
        """Whether ``attachments/`` down to the message directory has no link.

        Missing directories are fine (they are created on publication); an
        existing component that is a symlink, a Windows junction or not a
        directory makes the whole message cache unusable.
        """
        root = cache_root(self._home)
        directory = self.message_dir()
        try:
            relative = directory.relative_to(root)
        except ValueError:  # pragma: no cover - message_dir is always under root
            return False
        current = root
        for part in ("", *relative.parts):
            if part:
                current = current / part
            try:
                info = os.stat(current, follow_symlinks=False)
            except FileNotFoundError:
                return True
            except OSError:
                return False
            if not _is_real_directory(info):
                return False
        return True

    def ensure_message_dir(self) -> Path:
        """Create the private ``0700`` message directory before publication.

        Refuses (``E_IO``) a cache directory that is a symlink, a junction or
        not a directory, before and after creating the missing components, so
        nothing is ever published through a link.
        """
        directory = self.message_dir()
        if not self.directories_are_real():
            raise _linked_directory_error()
        try:
            _ensure_private_dir(directory)
        except OSError as exc:
            raise _map_os_error(
                exc, "cannot create the attachment cache directory"
            ) from exc
        if not self.directories_are_real():
            raise _linked_directory_error()
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

    def write_manifest(self, staging: StagingArea, manifest: Manifest) -> None:
        """Atomically replace the message manifest with ``manifest``.

        The document is staged (``0600``) and published with ``os.replace``
        like an attachment. An empty manifest removes the file instead.
        Errors propagate mapped to ``E_IO``/``E_PERMISSION``; the engine treats
        this write as best-effort.
        """
        if not manifest:
            path = self.manifest_path()
            if self.directories_are_real():
                try:
                    info = os.stat(path, follow_symlinks=False)
                except OSError:
                    return
                if not stat.S_ISDIR(info.st_mode):
                    try:
                        os.unlink(path)
                    except OSError as exc:
                        raise _map_os_error(
                            exc, "cannot update the attachment cache manifest"
                        ) from exc
            return
        document = {
            "version": MANIFEST_VERSION,
            "entries": {
                str(index): {
                    "sanitized_name": entry.sanitized_name,
                    "size_bytes": entry.size_bytes,
                    "sha256": entry.sha256,
                }
                for index, entry in sorted(manifest.items())
            },
        }
        payload = (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode(
            "utf-8"
        )
        directory = self.ensure_message_dir()
        staged = staging.new_file()
        staged.append(payload)
        staged.publish(directory / MANIFEST_NAME)

    def discard_unverified(self, original_name: str, index: int) -> bool:
        """Best-effort removal of an unverified entry at the cache path.

        Only a regular file or a link is removed (``os.unlink`` removes the link
        itself, never its target); a directory is never removed recursively.
        Nothing is removed under a message directory that is not real. Returns
        whether the entry was removed; never raises.
        """
        if not self.directories_are_real():
            return False
        path = self.path_for(original_name, index)
        try:
            info = os.stat(path, follow_symlinks=False)
        except OSError:
            return False
        link = _is_link(info)
        if stat.S_ISDIR(info.st_mode) and not link:
            return False
        try:
            os.unlink(path)
        except OSError:
            if not link:
                return False
            try:  # a Windows directory symlink or junction is removed with rmdir
                os.rmdir(path)
            except OSError:
                return False
        return True


# --------------------------------------------------------------------------- #
# Low-level filesystem helpers (test seams)
# --------------------------------------------------------------------------- #


def _chmod(path: Path, mode: int) -> None:
    """Apply a POSIX mode; on Windows the profile ACL is inherited."""
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
    ``PermissionError`` on Windows; ``E_PERMISSION`` is kept for permission
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


def _is_link(info: os.stat_result) -> bool:
    """A symlink, or a Windows name-surrogate reparse point (symlink/junction)."""
    if stat.S_ISLNK(info.st_mode):
        return True
    tag = getattr(info, "st_reparse_tag", 0) or 0
    return bool(tag & _NAME_SURROGATE_BIT)


def _is_real_directory(info: os.stat_result) -> bool:
    return stat.S_ISDIR(info.st_mode) and not _is_link(info)


def _linked_directory_error() -> MailqueryError:
    return MailqueryError(
        "E_IO",
        "cannot use the attachment cache: a cache directory is a link or not a directory",
        "remove the link from ~/.mailquery/attachments and retry",
        "cache directory is a link or not a directory",
    )


def _open_no_follow(path: Path):  # type: ignore[no-untyped-def]
    """Open ``path`` for binary reading without following a final symlink (POSIX)."""
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    return os.fdopen(descriptor, "rb")


def _parse_manifest(document: object) -> Manifest:
    """Validate a manifest document; malformed entries are dropped."""
    if not isinstance(document, Mapping):
        return {}
    if document.get("version") != MANIFEST_VERSION:
        return {}
    entries = document.get("entries")
    if not isinstance(entries, Mapping):
        return {}
    manifest: Manifest = {}
    for key, value in entries.items():
        if (
            not isinstance(key, str)
            or not (key.isascii() and key.isdigit())
            or not isinstance(value, Mapping)
        ):
            continue
        index = int(key)
        name = value.get("sanitized_name")
        size = value.get("size_bytes")
        digest = value.get("sha256")
        if index < 1 or not isinstance(name, str) or not name:
            continue
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            continue
        if not isinstance(digest, str) or not _SHA256_HEX.fullmatch(digest):
            continue
        manifest[index] = ManifestEntry(name, size, digest)
    return manifest


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with _open_no_follow(path) as handle:
        while True:
            chunk = handle.read(_HASH_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _map_os_error(exc: OSError, operation: str) -> MailqueryError:
    """Map a filesystem failure to ``E_PERMISSION``/``E_IO``."""
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
    "MANIFEST_NAME",
    "MANIFEST_VERSION",
    "Manifest",
    "ManifestEntry",
    "STAGING_DIR_NAME",
    "StagedAttachment",
    "StagingArea",
    "cached_path",
]

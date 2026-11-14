"""Attachment core: catalog, blocking, sanitization, paths, screening and engine.

Public API of the attachment core. The policy layer (catalog, blocking,
sanitization, paths, screening) is pure: it never writes files, never reads the
cache and never opens a path. The active-content detector reads the bytes of an
already-extracted attachment without opening, executing or decompressing it. On
top of them sit the filesystem engine (:class:`AttachmentsEngine`) and the
cache/staging layer (:class:`AttachmentCache`, :class:`StagingArea`), consumed
by the ``show`` and ``attachment`` commands and by the backend adapters. Only
stdlib and the mailquery package are imported.
"""

from __future__ import annotations

from mailquery.attachments.active_content import (
    ACTIVE_CONTENT_TYPES,
    active_content_types,
)
from mailquery.attachments.blocking import (
    CONTENT_BLOCK_DETAIL,
    CONTENT_INSPECTION_BYTES,
    MAGIC_SIGNATURES,
    NAME_BLOCK_DETAIL,
    REASON_ALTERNATE_DATA_STREAM,
    REASON_CONTROL_CHARACTER,
    REASON_DANGEROUS_EXTENSION,
    REASON_DRIVE_PREFIX,
    REASON_EXECUTABLE_CONTENT,
    REASON_PARENT_SEGMENT,
    REASON_PATH_SEPARATOR,
    REASON_RESERVED_NAME,
    ContentDecision,
    NameDecision,
    classify_content,
    classify_name,
)
from mailquery.attachments.cache import (
    STAGING_DIR_NAME,
    AttachmentCache,
    CacheHit,
    StagedAttachment,
    StagingArea,
    cached_path,
)
from mailquery.attachments.catalog import (
    CATALOG,
    CATEGORY_EXECUTABLES,
    CATEGORY_INSTALLERS,
    CATEGORY_INTERPRETERS,
    CATEGORY_OFFICE_MACROS,
    CATEGORY_SCRIPTS,
    CATEGORY_SHORTCUTS,
    DANGEROUS_EXTENSIONS,
    EXTENSION_CATEGORY,
    dangerous_extension,
    is_dangerous_extension,
    is_reserved_name,
    normalize_name,
    reserved_name,
)
from mailquery.attachments.engine import (
    MIB,
    AttachmentDriver,
    AttachmentLimits,
    AttachmentResult,
    AttachmentsEngine,
    DeadlineFactory,
)
from mailquery.attachments.paths import (
    ATTACHMENTS_DIR_NAME,
    POSIX_COMPONENT_MAX_FALLBACK,
    POSIX_PATH_MAX_FALLBACK,
    WINDOWS_PATH_BUDGET_BYTES,
    attachment_path,
    cache_root,
    message_dir,
    path_limits,
)
from mailquery.attachments.sanitize import (
    DISPLAY_NAME_MAX_BYTES,
    MAX_EXTENSION_BYTES,
    MAX_NAME_BYTES,
    MAX_SANITIZED_BYTES,
    SUBSTITUTION_CHARACTERS,
    display_name,
    sanitize_name,
    truncate_utf8,
)
from mailquery.attachments.screening import (
    BLOCKED_CODE,
    REASON_READ_ERROR,
    UNAVAILABLE_CODE,
    UNAVAILABLE_REASONS,
    UNREADABLE_CODE,
    UNREADABLE_REASONS,
    ScreenDecision,
    read_first_block,
    screen_content,
    screen_names,
)

#: Active-content warning of ``attachment``: one per delivered attachment and type.
W_ATTACHMENT_ACTIVE_CONTENT = (
    "W_ATTACHMENT_ACTIVE_CONTENT: attachment {index} contains {kind} in {uid}"
)

__all__ = [
    # active content
    "ACTIVE_CONTENT_TYPES",
    "W_ATTACHMENT_ACTIVE_CONTENT",
    "active_content_types",
    # catalog
    "CATALOG",
    "CATEGORY_EXECUTABLES",
    "CATEGORY_INSTALLERS",
    "CATEGORY_INTERPRETERS",
    "CATEGORY_OFFICE_MACROS",
    "CATEGORY_SCRIPTS",
    "CATEGORY_SHORTCUTS",
    "DANGEROUS_EXTENSIONS",
    "EXTENSION_CATEGORY",
    "dangerous_extension",
    "is_dangerous_extension",
    "is_reserved_name",
    "normalize_name",
    "reserved_name",
    # blocking
    "CONTENT_BLOCK_DETAIL",
    "CONTENT_INSPECTION_BYTES",
    "MAGIC_SIGNATURES",
    "NAME_BLOCK_DETAIL",
    "REASON_ALTERNATE_DATA_STREAM",
    "REASON_CONTROL_CHARACTER",
    "REASON_DANGEROUS_EXTENSION",
    "REASON_DRIVE_PREFIX",
    "REASON_EXECUTABLE_CONTENT",
    "REASON_PARENT_SEGMENT",
    "REASON_PATH_SEPARATOR",
    "REASON_RESERVED_NAME",
    "ContentDecision",
    "NameDecision",
    "classify_content",
    "classify_name",
    # sanitize
    "DISPLAY_NAME_MAX_BYTES",
    "MAX_EXTENSION_BYTES",
    "MAX_NAME_BYTES",
    "MAX_SANITIZED_BYTES",
    "SUBSTITUTION_CHARACTERS",
    "display_name",
    "sanitize_name",
    "truncate_utf8",
    # paths
    "ATTACHMENTS_DIR_NAME",
    "POSIX_COMPONENT_MAX_FALLBACK",
    "POSIX_PATH_MAX_FALLBACK",
    "WINDOWS_PATH_BUDGET_BYTES",
    "attachment_path",
    "cache_root",
    "message_dir",
    "path_limits",
    # screening
    "BLOCKED_CODE",
    "REASON_READ_ERROR",
    "UNAVAILABLE_CODE",
    "UNAVAILABLE_REASONS",
    "UNREADABLE_CODE",
    "UNREADABLE_REASONS",
    "ScreenDecision",
    "read_first_block",
    "screen_content",
    "screen_names",
    # cache/staging
    "STAGING_DIR_NAME",
    "AttachmentCache",
    "CacheHit",
    "StagedAttachment",
    "StagingArea",
    "cached_path",
    # engine
    "MIB",
    "AttachmentDriver",
    "AttachmentLimits",
    "AttachmentResult",
    "AttachmentsEngine",
    "DeadlineFactory",
]

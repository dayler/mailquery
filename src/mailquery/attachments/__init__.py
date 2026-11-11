"""Pure attachment core: catalog, blocking, sanitization, paths and screening.

Public API of milestone M06 (C6, PRD-v2.1 §10.3). Everything here is pure
stdlib code that decides policy; it never writes files, never reads the cache
and never opens a path. The consumers are M07 (cache/staging engine) and M08
(``show``/``attachment`` command).
"""

from __future__ import annotations

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

__all__ = [
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
]

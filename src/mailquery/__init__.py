"""mailquery - read-only CLI access to Apple Mail.

The package never writes to the Apple Mail store: it only opens the
``Envelope Index`` database in SQLite read-only mode and reads ``.emlx``
files with ``open(path, "rb")``. All state, logs, locks and temporaries live
under ``~/.mailquery``.
"""

from __future__ import annotations

__version__ = "1.3.2"

__all__ = ["__version__"]

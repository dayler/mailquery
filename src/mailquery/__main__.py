"""Entry point for ``python3 -m mailquery``."""

from __future__ import annotations

import sys

from mailquery.cli import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

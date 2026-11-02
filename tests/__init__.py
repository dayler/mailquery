"""Test package for mailquery.

Makes the ``src/`` layout importable without installing the package:

    python3 -m unittest discover -s tests -t . -v
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

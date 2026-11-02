"""Command line interface: argument parsing, dispatch, JSON contract, exit codes.

Only this module writes to ``stdout``/``stderr``. It parses ``argv`` with
``argparse`` (``-h``/``--help`` is the documented non-JSON exception), loads
the configuration, sets up logging, takes the run lock, dispatches one of the
five commands and renders either success or a JSON error object (PRD 12).
"""

from __future__ import annotations

import argparse
from typing import Sequence


def build_parser() -> argparse.ArgumentParser:
    """Build the ``mailquery`` argparse parser with all subcommands."""
    raise NotImplementedError


def main(argv: Sequence[str] | None = None) -> int:
    """Run one command and return the process exit code (never raises)."""
    raise NotImplementedError

"""Subprocess launcher: build the Outlook fake and run ``cli.main(argv, backend=...)``.

Used by the timeout tests (OL-04), which need ``cli`` in its own process because
the D-03 watchdog ends the process with ``os._exit``. Usage::

    python tests/fakes/run_cli.py [--scenario NAME] [--home DIR] [--timeout SECONDS]
                                  [--hang first|Kind.Member] [--hang-timeout SECONDS]
                                  -- <mailquery arguments>
    python tests/fakes/run_cli.py --list-scenarios

The caller sets ``HOME`` and ``USERPROFILE`` to a temporary directory (plan 7.1).
``--timeout`` patches ``outlook_com.CALL_TIMEOUT_SECONDS`` and the fake's
``drive_type`` replaces ``outlook_com.get_drive_type`` (seams of the W3 design
note); ``--hang`` blocks the first OOM access (``first``) or the first access to
``Kind.Member`` (e.g. ``NameSpace.Stores``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _path in (str(_REPO_ROOT / "src"), str(_REPO_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from tests.fakes.outlook import SCENARIOS, FakeOutlook  # noqa: E402


def parse_args(argv: Sequence[str]) -> tuple[argparse.Namespace, list[str]]:
    """Split launcher options from the ``mailquery`` arguments (after ``--``)."""
    items = list(argv)
    if "--" in items:
        cut = items.index("--")
        own, cli_argv = items[:cut], items[cut + 1:]
    else:
        own, cli_argv = items, []
    parser = argparse.ArgumentParser(prog="run_cli.py")
    parser.add_argument("--scenario", default="default")
    parser.add_argument("--home", default=None)
    parser.add_argument("--timeout", type=float, default=None)
    parser.add_argument("--hang", default=None)
    parser.add_argument("--hang-timeout", type=float, default=60.0)
    parser.add_argument("--list-scenarios", action="store_true")
    return parser.parse_args(own), cli_argv


def build_fake(
    scenario: str, *, hang: str | None = None, hang_timeout: float = 60.0
) -> FakeOutlook:
    """Fake of the named scenario, with an optional hang on the first matching access."""
    try:
        builder = SCENARIOS[scenario]
    except KeyError:
        raise ValueError(f"unknown scenario {scenario!r}; known: {sorted(SCENARIOS)}") from None
    fake = builder()
    if hang:
        if hang == "first":
            fake.hang_next(timeout=hang_timeout)
        else:
            kind, _, member = hang.partition(".")
            if not kind or not member:
                raise ValueError(f"--hang expects 'first' or 'Kind.Member', got {hang!r}")
            fake.hang_next(kind=kind, member=member, timeout=hang_timeout)
    return fake


def main(argv: Sequence[str] | None = None) -> int:
    options, cli_argv = parse_args(sys.argv[1:] if argv is None else argv)
    if options.list_scenarios:
        print(json.dumps(sorted(SCENARIOS)))
        return 0
    fake = build_fake(options.scenario, hang=options.hang, hang_timeout=options.hang_timeout)

    from mailquery import cli
    from mailquery.backends import get_backend
    from mailquery.backends import outlook_com

    outlook_com.get_drive_type = fake.drive_type
    if options.timeout is not None:
        outlook_com.CALL_TIMEOUT_SECONDS = options.timeout
    backend = get_backend(
        platform="win32",
        outlook_app=fake,
        registry=fake.registry,
        security_center=fake.security_center,
        pywin32=True,
    )
    home = Path(options.home) if options.home else None
    return cli.main(cli_argv, home=home, backend=backend)


if __name__ == "__main__":
    sys.exit(main())

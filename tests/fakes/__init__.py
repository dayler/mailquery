"""Test doubles that stand in for a mail client (plan 4.1, 7.5).

* ``outlook`` - in-memory fake of the Outlook Object Model, injected below the
  production read-only proxy through ``get_backend(outlook_app=...)``.
* ``run_cli`` - subprocess launcher that builds the fake and calls
  ``cli.main(argv, backend=...)`` (timeout tests, OL-04).

Pure Python: no pywin32 import, runs on Linux, macOS and Windows.
"""

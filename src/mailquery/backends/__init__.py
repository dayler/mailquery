"""Mail backends (Apple Mail, Outlook) behind the common ``MailBackend`` interface."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mailquery.accounts import AccountLabels
    from mailquery.backends.base import MailBackend
    from mailquery.store import EnvelopeStore


def backend_class(*, platform: str | None = None) -> "type[MailBackend]":
    """Backend class that :func:`get_backend` would build for ``platform``.

    Nothing is instantiated or opened, so static members such as
    ``parse_uid`` can be used before the mail client is touched (PRD 12.4).
    """
    current = sys.platform if platform is None else platform
    if current == "win32":
        from mailquery.backends.outlook import OutlookBackend

        return OutlookBackend
    from mailquery.backends.apple_mail import AppleMailBackend

    return AppleMailBackend


def get_backend(
    *,
    platform: str | None = None,
    outlook_app: Any = None,
    registry: Any = None,
    security_center: Any = None,
    pywin32: bool | None = None,
    store: "EnvelopeStore | None" = None,
    labels: "AccountLabels | None" = None,
    mail_root: Path | None = None,
    accounts_db: Path | None = None,
    tmp_root: Path | None = None,
) -> "MailBackend":
    """Select the backend by platform (RF-26): ``win32`` is Outlook, anything else Apple Mail.

    The Outlook module is imported lazily and only for ``win32``, so no other platform
    ever imports ``win32com``. ``outlook_app``, ``registry``, ``security_center`` and
    ``pywin32`` are test injection points for Outlook; ``store``, ``labels``,
    ``mail_root`` and ``accounts_db`` are for Apple Mail. ``tmp_root``
    (``<home>/tmp``) holds Apple Mail's temporary copies and Outlook's pywin32
    cache (``<tmp_root>/gen_py``).
    """
    current = sys.platform if platform is None else platform
    if current == "win32":
        from mailquery.backends.outlook import OutlookBackend

        return OutlookBackend(
            outlook_app=outlook_app,
            registry=registry,
            security_center=security_center,
            pywin32=pywin32,
            tmp_root=tmp_root,
        )
    from mailquery.backends.apple_mail import AppleMailBackend

    return AppleMailBackend(
        store,
        labels,
        mail_root=mail_root,
        accounts_db=accounts_db,
        tmp_root=tmp_root,
    )

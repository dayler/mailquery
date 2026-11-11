"""Synthetic Apple Mail store used by the test suite.

Builds, under a temporary directory, the pieces mailquery reads from a real
mail installation:

``<root>/Mail/PersistenceInfo.plist``            version metadata
``<root>/Mail/V10/MailData/Envelope Index``      minimal Envelope Index (SQLite)
``<root>/Mail/V10/<account-uuid>/<x>.mbox/...``  on-disk mailbox tree with .emlx
``<root>/Library/Accounts/Accounts4.sqlite``     minimal accounts database
``<root>/home``                                  app home (~/.mailquery equivalent)

Nothing here touches the real ``~/Library/Mail`` or ``~/Library/Accounts``.

The fixture data deliberately includes localized, non-English content: German and
Spanish Outlook folder names (``tests/fakes/outlook.py``), accented subjects and
``Facturación ñ``-style folder names. They are test vectors for Outlook localization,
accent-insensitive matching and percent-encoded URLs, not user-facing language; do not
translate them without replacing that coverage.
"""

from __future__ import annotations

import plistlib
import sqlite3
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import format_datetime, formataddr
from pathlib import Path

VERSION = "V10"
VERSION_UUID = "11111111-2222-4333-8444-555555555555"

ACCOUNT_ICLOUD = "AAAAAAAA-0000-4000-8000-000000000001"
ACCOUNT_GMAIL = "BBBBBBBB-0000-4000-8000-000000000002"
ACCOUNT_LOCAL = "CCCCCCCC-0000-4000-8000-000000000003"

ICLOUD_LABEL = "iCloud (fixture@icloud.com)"
GMAIL_LABEL = "Gmail (fixture@gmail.com)"
LOCAL_LABEL = "On My Device"

MAILBOX_ICLOUD_INBOX = 1
MAILBOX_ICLOUD_FACTURAS = 2
MAILBOX_ICLOUD_ARCHIVO = 3
MAILBOX_GMAIL_INBOX = 5
MAILBOX_GMAIL_ALL_MAIL = 6
MAILBOX_GMAIL_IMPORTANT = 7
MAILBOX_LOCAL_RECOVERED = 8

MAILBOX_URLS: dict[int, str] = {
    MAILBOX_ICLOUD_INBOX: f"imap://{ACCOUNT_ICLOUD}/INBOX",
    MAILBOX_ICLOUD_FACTURAS: f"imap://{ACCOUNT_ICLOUD}/Facturas",
    MAILBOX_ICLOUD_ARCHIVO: f"imap://{ACCOUNT_ICLOUD}/Archivo",
    MAILBOX_GMAIL_INBOX: f"imap://{ACCOUNT_GMAIL}/INBOX",
    MAILBOX_GMAIL_ALL_MAIL: f"imap://{ACCOUNT_GMAIL}/%5BGmail%5D/All%20Mail",
    MAILBOX_GMAIL_IMPORTANT: f"imap://{ACCOUNT_GMAIL}/%5BGmail%5D/Important",
    MAILBOX_LOCAL_RECOVERED: f"local://{ACCOUNT_LOCAL}/Recovered%20Messages",
}

# Extra mailboxes created only by ``build_store(extended=True)``.
MAILBOX_ICLOUD_PROYECTOS_INBOX = 20
MAILBOX_ICLOUD_PROYECTOS_FACTURAS = 21
MAILBOX_ICLOUD_CLIENTES_FACTURAS = 22
# B-27: a top-level folder whose *name* ("Proyectos/Inbox", slash encoded as %2F)
# equals the *path* of MAILBOX_ICLOUD_PROYECTOS_INBOX. It holds no messages.
MAILBOX_ICLOUD_SLASH_NAME = 23

EXTENDED_MAILBOX_URLS: dict[int, str] = {
    MAILBOX_ICLOUD_PROYECTOS_INBOX: f"imap://{ACCOUNT_ICLOUD}/Proyectos/Inbox",
    MAILBOX_ICLOUD_PROYECTOS_FACTURAS: f"imap://{ACCOUNT_ICLOUD}/Proyectos/Facturas",
    MAILBOX_ICLOUD_CLIENTES_FACTURAS: f"imap://{ACCOUNT_ICLOUD}/Clientes/Facturas",
    MAILBOX_ICLOUD_SLASH_NAME: f"imap://{ACCOUNT_ICLOUD}/Proyectos%2FInbox",
}

# mailboxes.total_count is deliberately wrong for the Gmail INBOX (real Mail
# reports unreliable counters); mailquery must recalculate it.
FAKE_COUNTERS: dict[int, tuple[int, int]] = {
    MAILBOX_GMAIL_INBOX: (36, 0),
    MAILBOX_ICLOUD_INBOX: (9999, 9999),
}

ME = ("Fixture User", "me@fixture.example")


@dataclass(frozen=True)
class FixtureMessage:
    """One row of the synthetic ``messages`` table plus its .emlx payload."""

    uid: int
    mailbox: int
    subject: str
    sender: tuple[str, str]
    to: tuple[tuple[str, str], ...] = (ME,)
    cc: tuple[tuple[str, str], ...] = ()
    age: timedelta = timedelta(days=1)
    read: bool = True
    flagged: bool = False
    deleted: bool = False
    size: int = 4096
    body: str | None = None
    html: str | None = None
    attachment_names: tuple[str, ...] = ()
    partial: bool = False
    missing_emlx: bool = False
    corrupt_emlx: bool = False
    message_id_header: str | None = None
    global_id: int = 0
    labels: tuple[int, ...] = ()
    extra_note: str = ""
    # "encrypted" (pkcs7-mime enveloped-data) or "signed" (multipart/signed).
    smime: str | None = None
    # attachments rows without a MIME part in the .emlx (DB-only).
    attachment_rows: tuple[str, ...] = ()
    # When True, date_received/date_sent in the DB come from ``date_value``
    # (None -> NULL) instead of now - age. The .emlx still uses ``age``.
    date_override: bool = False
    date_value: float | int | None = None


DEFAULT_MESSAGES: tuple[FixtureMessage, ...] = (
    FixtureMessage(
        uid=830,
        mailbox=MAILBOX_ICLOUD_INBOX,
        subject="Annual report 2025",
        sender=("Archive Service", "reports@fixture.example"),
        age=timedelta(days=120),
        body="Your annual report for 2025 is ready to download.",
        global_id=1,
        message_id_header="<annual-830@fixture.example>",
    ),
    FixtureMessage(
        uid=2714,
        mailbox=MAILBOX_ICLOUD_INBOX,
        subject="Invoice 2026-10",
        sender=("Billing Team", "billing@fixture.example"),
        to=(ME,),
        cc=(("Finance", "finance@fixture.example"),),
        age=timedelta(days=2),
        read=False,
        size=123456,
        body="Please find the invoice attached.",
        html="<html><body><p>Please find the invoice <b>attached</b>.</p></body></html>",
        attachment_names=("invoice-2026-10.pdf",),
        global_id=2,
        message_id_header="<invoice-2714@fixture.example>",
    ),
    FixtureMessage(
        uid=79658,
        mailbox=MAILBOX_ICLOUD_FACTURAS,
        subject="Factura septiembre",
        sender=("Contabilidad", "facturas@fixture.example"),
        age=timedelta(days=10),
        partial=True,
        body="Adjuntamos la factura de septiembre.",
        attachment_names=("factura-79658.pdf",),
        global_id=3,
        message_id_header="<factura-79658@fixture.example>",
    ),
    FixtureMessage(
        uid=83142,
        mailbox=MAILBOX_GMAIL_ALL_MAIL,
        subject="Shared duplicate",
        sender=("Shared Sender", "shared@fixture.example"),
        age=timedelta(hours=1),
        body="Duplicate body from the archive.",
        global_id=4,
        message_id_header="<duplicate-4@fixture.example>",
    ),
    FixtureMessage(
        uid=83143,
        mailbox=MAILBOX_ICLOUD_INBOX,
        subject="Shared duplicate",
        sender=("Shared Sender", "shared@fixture.example"),
        age=timedelta(minutes=59),
        read=False,
        body="Duplicate body from the inbox.",
        global_id=4,
        message_id_header="<duplicate-4@fixture.example>",
    ),
    FixtureMessage(
        uid=83150,
        mailbox=MAILBOX_ICLOUD_INBOX,
        subject="Flagged reminder",
        sender=("Reminders", "reminders@fixture.example"),
        age=timedelta(minutes=30),
        read=False,
        flagged=True,
        html="<html><body><p>Remember <b>this</b>.</p></body></html>",
        global_id=5,
        message_id_header="<flagged-83150@fixture.example>",
    ),
    FixtureMessage(
        uid=83160,
        mailbox=MAILBOX_GMAIL_ALL_MAIL,
        subject="Gmail labelled",
        sender=("Gmail Sender", "gmail@fixture.example"),
        age=timedelta(minutes=20),
        body="Label membership comes from the labels table.",
        global_id=6,
        labels=(MAILBOX_GMAIL_INBOX,),
        message_id_header="<gmail-83160@fixture.example>",
    ),
    FixtureMessage(
        uid=83170,
        mailbox=MAILBOX_ICLOUD_INBOX,
        subject="Missing body",
        sender=("Ghost", "ghost@fixture.example"),
        age=timedelta(minutes=15),
        missing_emlx=True,
        global_id=7,
        message_id_header="<missing-83170@fixture.example>",
    ),
    FixtureMessage(
        uid=83180,
        mailbox=MAILBOX_ICLOUD_ARCHIVO,
        subject="Corrupt body",
        sender=("Broken", "broken@fixture.example"),
        age=timedelta(days=12),
        corrupt_emlx=True,
        global_id=8,
        message_id_header="<corrupt-83180@fixture.example>",
    ),
    FixtureMessage(
        uid=83190,
        mailbox=MAILBOX_ICLOUD_INBOX,
        subject="Very old mail",
        sender=("Old Timer", "old@fixture.example"),
        age=timedelta(days=730),
        body="Ancient message from years ago.",
        global_id=9,
        message_id_header="<old-83190@fixture.example>",
    ),
    FixtureMessage(
        uid=83200,
        mailbox=MAILBOX_ICLOUD_INBOX,
        subject="HTML only",
        sender=("Html Sender", "html@fixture.example"),
        age=timedelta(days=5),
        html="<html><body><h1>HTML only</h1><p>There is no plain text part.</p></body></html>",
        global_id=10,
        message_id_header="<html-83200@fixture.example>",
    ),
    FixtureMessage(
        uid=83210,
        mailbox=MAILBOX_GMAIL_ALL_MAIL,
        subject="Gmail unread with photo",
        sender=("Photo Sender", "photo@fixture.example"),
        age=timedelta(days=1),
        read=False,
        body="Photo attached.",
        attachment_names=("photo.jpg",),
        global_id=11,
        labels=(MAILBOX_GMAIL_INBOX,),
        message_id_header="<photo-83210@fixture.example>",
    ),
    FixtureMessage(
        uid=83220,
        mailbox=MAILBOX_ICLOUD_INBOX,
        subject="No global header",
        sender=("Headerless", "headerless@fixture.example"),
        age=timedelta(days=3),
        body="No Message-ID header is available for this message.",
        global_id=12,
        message_id_header=None,
    ),
)

# Extended-store uids (build_store(extended=True)); none collide with the defaults.
UID_PROYECTOS_INBOX = 90101
UID_PROYECTOS_FACTURAS = 90102
UID_CLIENTES_FACTURAS = 90103
UID_SMIME_ENCRYPTED = 90110
UID_SMIME_SIGNED = 90111
UID_MISSING_EMLX_ATTACH = 90120
UID_DELETED = 90130
UID_GLOBAL_ZERO = 90140
UID_DUP_FOLDER = 90150  # iCloud/Facturas
UID_DUP_AGGREGATE = 90151  # Gmail/[Gmail]/All Mail, same global_id/Message-ID
UID_DATE_NULL = 90160
UID_DATE_ZERO = 90161
UID_DATE_HUGE = 90162  # date_received = 1e20
UID_DATE_FUTURE = 90163  # now + 30 days

EXTENDED_MESSAGES: tuple[FixtureMessage, ...] = (
    FixtureMessage(
        uid=UID_PROYECTOS_INBOX,
        mailbox=MAILBOX_ICLOUD_PROYECTOS_INBOX,
        subject="Proyectos inbox item",
        sender=("Projects", "projects@fixture.example"),
        age=timedelta(days=4),
        body="Message in the nested Proyectos/Inbox folder.",
        global_id=101,
        message_id_header="<proyectos-inbox-90101@fixture.example>",
    ),
    FixtureMessage(
        uid=UID_PROYECTOS_FACTURAS,
        mailbox=MAILBOX_ICLOUD_PROYECTOS_FACTURAS,
        subject="Proyectos facturas item",
        sender=("Projects", "projects@fixture.example"),
        age=timedelta(days=6),
        body="Same folder name, path Proyectos/Facturas.",
        global_id=102,
        message_id_header="<proyectos-facturas-90102@fixture.example>",
    ),
    FixtureMessage(
        uid=UID_CLIENTES_FACTURAS,
        mailbox=MAILBOX_ICLOUD_CLIENTES_FACTURAS,
        subject="Clientes facturas item",
        sender=("Clients", "clients@fixture.example"),
        age=timedelta(days=7),
        body="Same folder name, path Clientes/Facturas.",
        global_id=103,
        message_id_header="<clientes-facturas-90103@fixture.example>",
    ),
    FixtureMessage(
        uid=UID_SMIME_ENCRYPTED,
        mailbox=MAILBOX_ICLOUD_INBOX,
        subject="Encrypted S/MIME",
        sender=("Secure", "secure@fixture.example"),
        age=timedelta(days=8),
        smime="encrypted",
        attachment_rows=("smime.p7m",),
        global_id=110,
        message_id_header="<smime-enc-90110@fixture.example>",
    ),
    FixtureMessage(
        uid=UID_SMIME_SIGNED,
        mailbox=MAILBOX_ICLOUD_INBOX,
        subject="Signed S/MIME",
        sender=("Signer", "signer@fixture.example"),
        age=timedelta(days=9),
        smime="signed",
        body="This message is signed.",
        global_id=111,
        message_id_header="<smime-sig-90111@fixture.example>",
    ),
    FixtureMessage(
        uid=UID_MISSING_EMLX_ATTACH,
        mailbox=MAILBOX_ICLOUD_INBOX,
        subject="Missing emlx with attachment row",
        sender=("Ghost", "ghost@fixture.example"),
        age=timedelta(days=11),
        missing_emlx=True,
        attachment_names=("ghost.pdf",),
        global_id=120,
        message_id_header="<missing-attach-90120@fixture.example>",
    ),
    FixtureMessage(
        uid=UID_DELETED,
        mailbox=MAILBOX_ICLOUD_INBOX,
        subject="Deleted message",
        sender=("Deleted", "deleted@fixture.example"),
        age=timedelta(days=13),
        deleted=True,
        body="This message is flagged deleted.",
        global_id=130,
        message_id_header="<deleted-90130@fixture.example>",
    ),
    FixtureMessage(
        uid=UID_GLOBAL_ZERO,
        mailbox=MAILBOX_ICLOUD_INBOX,
        subject="Global id zero",
        sender=("Zero", "zero@fixture.example"),
        age=timedelta(days=14),
        body="global_message_id is 0 for this message.",
        global_id=0,
        message_id_header="<global-zero-90140@fixture.example>",
    ),
    FixtureMessage(
        uid=UID_DUP_FOLDER,
        mailbox=MAILBOX_ICLOUD_FACTURAS,
        subject="Aggregate duplicate",
        sender=("Dup", "dup@fixture.example"),
        age=timedelta(days=15),
        body="Copy in a normal folder.",
        global_id=150,
        message_id_header="<aggregate-dup-150@fixture.example>",
    ),
    FixtureMessage(
        uid=UID_DUP_AGGREGATE,
        mailbox=MAILBOX_GMAIL_ALL_MAIL,
        subject="Aggregate duplicate",
        sender=("Dup", "dup@fixture.example"),
        age=timedelta(days=15),
        body="Copy in the aggregate mailbox.",
        global_id=150,
        message_id_header="<aggregate-dup-150@fixture.example>",
    ),
    FixtureMessage(
        uid=UID_DATE_NULL,
        mailbox=MAILBOX_ICLOUD_INBOX,
        subject="Date received NULL",
        sender=("Dates", "dates@fixture.example"),
        age=timedelta(days=16),
        body="date_received is NULL.",
        date_override=True,
        date_value=None,
        global_id=160,
        message_id_header="<date-null-90160@fixture.example>",
    ),
    FixtureMessage(
        uid=UID_DATE_ZERO,
        mailbox=MAILBOX_ICLOUD_INBOX,
        subject="Date received zero",
        sender=("Dates", "dates@fixture.example"),
        age=timedelta(days=16),
        body="date_received is 0.",
        date_override=True,
        date_value=0,
        global_id=161,
        message_id_header="<date-zero-90161@fixture.example>",
    ),
    FixtureMessage(
        uid=UID_DATE_HUGE,
        mailbox=MAILBOX_ICLOUD_INBOX,
        subject="Date received huge",
        sender=("Dates", "dates@fixture.example"),
        age=timedelta(days=16),
        body="date_received is 1e20.",
        date_override=True,
        date_value=1e20,
        global_id=162,
        message_id_header="<date-huge-90162@fixture.example>",
    ),
    FixtureMessage(
        uid=UID_DATE_FUTURE,
        mailbox=MAILBOX_ICLOUD_INBOX,
        subject="Date received future",
        sender=("Dates", "dates@fixture.example"),
        age=timedelta(days=-30),
        body="date_received is 30 days after the fixture clock.",
        global_id=163,
        message_id_header="<date-future-90163@fixture.example>",
    ),
)

# A uid that exists on disk but has no row in the Envelope Index (orphan .emlx).
ORPHAN_UID = 99999

# .emlx whose first line is not a valid length and whose payload is not MIME.
CORRUPT_EMLX_BYTES = b"this-is-not-a-length\nnot a valid mime payload\x00\x01"

# M02: the fixture config carries a valid ``[attachments]`` table with the
# documented defaults (parsing coverage; it changes no output) and the account
# blocks keep the 2.0.1 unprefixed form (regression: same behavior).
ATTACHMENTS_CONFIG = """\
[attachments]
enabled = true
max_file_size_mb = 100
max_total_size_mb = 200
max_count = 50
"""

DEFAULT_CONFIG = f"""\
# Synthetic fixture configuration (all three accounts declared).
{ATTACHMENTS_CONFIG}
[scope."{ICLOUD_LABEL}"]
mailbox_list = ["Facturas", "Archivo"]

[scope."{GMAIL_LABEL}"]

[scope."{LOCAL_LABEL}"]
"""

#: Same accounts declared with the explicit driver prefix (M02, RF-36).
PREFIXED_CONFIG = f"""\
{ATTACHMENTS_CONFIG}
[scope."apple_mail:{ICLOUD_LABEL}"]
mailbox_list = ["Facturas"]

[scope."apple_mail:{GMAIL_LABEL}"]
"""


@dataclass(frozen=True)
class FixturePaths:
    """Paths and metadata of a built synthetic Mail store.

    ``build_store(extended=True)`` additionally exposes (uids are module
    constants ``UID_*``; use ``message(uid)`` for details):

    * ``mailboxes``: ``iCloud/Proyectos/Inbox`` (20), ``iCloud/Proyectos/Facturas``
      (21), ``iCloud/Clientes/Facturas`` (22; same name as 21 and as
      ``iCloud/Facturas``, different paths) and ``iCloud/Proyectos%2FInbox`` (23;
      top-level folder whose name equals the path of 20; no messages, B-27).
    * 90101/90102/90103: one message in each of mailboxes 20/21/22.
    * 90110 encrypted S/MIME (pkcs7-mime, ``attachments`` row ``smime.p7m``);
      90111 signed S/MIME (multipart/signed, no ``attachments`` row).
    * 90120: ``.emlx`` absent on disk but an ``attachments`` row exists.
    * 90130: deleted (flags bit 2, ``deleted=1``).
    * 90140: ``global_message_id`` 0 (no ``message_global_data`` row).
    * 90150 (iCloud/Facturas) and 90151 (Gmail/All Mail): duplicate pair,
      same global_message_id 150 and Message-ID.
    * 90160 date_received NULL, 90161 = 0, 90162 = 1e20, 90163 = now + 30 days.
    * ``wal_path`` / ``shm_path``: the Envelope Index is in WAL journal mode and
      both ``Envelope Index-wal`` and ``Envelope Index-shm`` exist on disk.
    """

    root: Path
    mail_root: Path
    home: Path
    accounts_db: Path
    envelope_index: Path
    version_uuid: str
    now: datetime
    mailboxes: dict[str, int] = field(default_factory=dict)
    messages: tuple[FixtureMessage, ...] = ()
    extended: bool = False
    # Extended store only (None otherwise): the WAL-mode Envelope Index sidecars.
    wal_path: Path | None = None
    shm_path: Path | None = None

    def cleanup(self) -> None:
        import shutil

        shutil.rmtree(self.root, ignore_errors=True)

    def message(self, uid: int) -> FixtureMessage:
        for message in self.messages:
            if message.uid == uid:
                return message
        raise KeyError(uid)


def build_store(
    root: str | Path | None = None, *, now: datetime | None = None, extended: bool = False
) -> FixturePaths:
    """Build a complete synthetic Mail store and return its paths.

    When ``root`` is ``None`` a new temporary directory is created (the caller
    owns it and can call :meth:`FixturePaths.cleanup`). ``extended=True`` adds
    the edge-case data documented on :class:`FixturePaths`.
    """
    if now is None:
        now = datetime.now()
    root_path = Path(root) if root is not None else Path(tempfile.mkdtemp(prefix="mailquery-fixture-"))
    root_path.mkdir(parents=True, exist_ok=True)

    mail_root = root_path / "Mail"
    home = root_path / "home"
    accounts_db = root_path / "Library" / "Accounts" / "Accounts4.sqlite"
    version_dir = mail_root / VERSION
    data_dir = version_dir / "MailData"
    envelope_index = data_dir / "Envelope Index"

    for directory in (home, data_dir, accounts_db.parent):
        directory.mkdir(parents=True, exist_ok=True)

    _write_persistence_info(mail_root)
    messages = DEFAULT_MESSAGES + EXTENDED_MESSAGES if extended else DEFAULT_MESSAGES
    for message in messages:
        _write_emlx_files(mail_root, message, now)
    _write_orphan_emlx(mail_root, now)
    _write_envelope_index(envelope_index, messages, now, extended=extended)
    _write_accounts_db(accounts_db)
    wal_path = shm_path = None
    if extended:
        wal_path, shm_path = _make_wal_variant(envelope_index)

    mailboxes = {
        "iCloud/INBOX": MAILBOX_ICLOUD_INBOX,
        "iCloud/Facturas": MAILBOX_ICLOUD_FACTURAS,
        "iCloud/Archivo": MAILBOX_ICLOUD_ARCHIVO,
        "Gmail/INBOX": MAILBOX_GMAIL_INBOX,
        "Gmail/All Mail": MAILBOX_GMAIL_ALL_MAIL,
        "Gmail/Important": MAILBOX_GMAIL_IMPORTANT,
        "Local/Recovered Messages": MAILBOX_LOCAL_RECOVERED,
    }
    if extended:
        mailboxes.update(
            {
                "iCloud/Proyectos/Inbox": MAILBOX_ICLOUD_PROYECTOS_INBOX,
                "iCloud/Proyectos/Facturas": MAILBOX_ICLOUD_PROYECTOS_FACTURAS,
                "iCloud/Clientes/Facturas": MAILBOX_ICLOUD_CLIENTES_FACTURAS,
                "iCloud/Proyectos%2FInbox": MAILBOX_ICLOUD_SLASH_NAME,
            }
        )
    return FixturePaths(
        root=root_path,
        mail_root=mail_root,
        home=home,
        accounts_db=accounts_db,
        envelope_index=envelope_index,
        version_uuid=VERSION_UUID,
        now=now,
        mailboxes=mailboxes,
        messages=messages,
        extended=extended,
        wal_path=wal_path,
        shm_path=shm_path,
    )


def write_config(home: Path, content: str = DEFAULT_CONFIG, filename: str = "config.toml") -> Path:
    """Write a ``config.toml`` under the fixture app home."""
    home = Path(home)
    home.mkdir(parents=True, exist_ok=True)
    path = home / filename
    path.write_text(content, encoding="utf-8")
    return path


def write_state(home: Path, payload: dict, filename: str = "state.json") -> Path:
    """Write a raw ``state.json`` under the fixture app home (for cursor tests)."""
    import json

    home = Path(home)
    home.mkdir(parents=True, exist_ok=True)
    path = home / filename
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #


def _mailbox_segments(rowid: int) -> tuple[str, tuple[str, ...]]:
    """Return ``(account_uuid, path_segments)`` for a mailbox rowid."""
    from urllib.parse import unquote, urlsplit

    url = MAILBOX_URLS.get(rowid) or EXTENDED_MAILBOX_URLS[rowid]
    parts = urlsplit(url)
    account_uuid = parts.netloc
    segments = tuple(unquote(segment) for segment in parts.path.split("/") if segment)
    return account_uuid, segments


def _mailbox_dir(mail_root: Path, rowid: int) -> Path:
    account_uuid, segments = _mailbox_segments(rowid)
    path = mail_root / VERSION / account_uuid
    for segment in segments:
        path = path / f"{segment}.mbox"
    return path


def emlx_shard_parts(uid: int) -> tuple[str, ...]:
    """Return the decimal shard segments for a uid (least significant first).

    ``830 -> ()``, ``2714 -> ("2",)``, ``79658 -> ("9", "7")``.
    """
    if uid < 1000:
        return ()
    return tuple(reversed(str(uid // 1000)))


def emlx_relative_path(uid: int, *, partial: bool = False) -> Path:
    """Return the formula path for a uid relative to its mailbox directory.

    ``Data/<shards>/Messages/<uid>.emlx`` (``Data/Messages/`` when uid < 1000).
    """
    path = Path("Data")
    for shard in emlx_shard_parts(uid):
        path = path / shard
    path = path / "Messages"
    suffix = ".partial.emlx" if partial else ".emlx"
    return path / f"{uid}{suffix}"


def _write_persistence_info(mail_root: Path) -> None:
    payload = {
        "LastUsedVersionDirectoryName": VERSION,
        "VersionDirectoryIdentifiers": {VERSION: VERSION_UUID},
    }
    (mail_root / "PersistenceInfo.plist").write_bytes(plistlib.dumps(payload))


def _emlx_bytes(message: FixtureMessage, received: datetime) -> bytes:
    if message.corrupt_emlx:
        return CORRUPT_EMLX_BYTES
    email = EmailMessage()
    email["From"] = formataddr(message.sender)
    email["To"] = ", ".join(formataddr(entry) for entry in message.to)
    if message.cc:
        email["Cc"] = ", ".join(formataddr(entry) for entry in message.cc)
    email["Subject"] = message.subject
    email["Date"] = format_datetime(received.astimezone())
    header = message.message_id_header
    if header:
        email["Message-ID"] = header
    body = message.body
    if body is None and message.html is not None:
        body = ""
    if message.smime == "encrypted":
        email.set_content(
            b"synthetic enveloped-data",
            maintype="application",
            subtype="pkcs7-mime",
            filename="smime.p7m",
            params={"smime-type": "enveloped-data"},
        )
    else:
        email.set_content(body if body is not None else "")
    if message.html is not None:
        email.add_alternative(message.html, subtype="html")
    if message.smime == "signed":
        email.add_attachment(
            b"synthetic signature",
            maintype="application",
            subtype="pkcs7-signature",
            filename="smime.p7s",
            disposition="inline",
        )
        del email["Content-Type"]
        email["Content-Type"] = 'multipart/signed; protocol="application/pkcs7-signature"; micalg=sha-256'
    for name in message.attachment_names:
        email.add_attachment(
            b"synthetic attachment payload",
            maintype="application",
            subtype="octet-stream",
            filename=name,
        )
    payload = email.as_bytes(policy=SMTP)
    trailer = plistlib.dumps(
        {
            "flags": _flags(message),
            "date-received": int(received.timestamp()),
            "conversation-id": message.global_id,
            "remote-id": message.uid,
        }
    )
    return f"{len(payload)}\n".encode("ascii") + payload + trailer


def _flags(message: FixtureMessage) -> int:
    flags = 0
    if message.read:
        flags |= 1
    if message.deleted:
        flags |= 2
    if message.flagged:
        flags |= 16
    return flags


def _write_emlx_files(mail_root: Path, message: FixtureMessage, now: datetime) -> None:
    if message.missing_emlx:
        return
    received = now - message.age
    mailbox_dir = _mailbox_dir(mail_root, message.mailbox)
    target = mailbox_dir / VERSION_UUID / emlx_relative_path(message.uid, partial=message.partial)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(_emlx_bytes(message, received))
    if message.partial and message.attachment_names:
        attachments_dir = (
            mailbox_dir / VERSION_UUID / "Data" / Path(*emlx_shard_parts(message.uid)) / "Attachments" / str(message.uid)
        )
        if not emlx_shard_parts(message.uid):
            attachments_dir = mailbox_dir / VERSION_UUID / "Data" / "Attachments" / str(message.uid)
        attachments_dir.mkdir(parents=True, exist_ok=True)
        for name in message.attachment_names:
            (attachments_dir / name).write_bytes(b"synthetic externalized attachment\n")


def _write_orphan_emlx(mail_root: Path, now: datetime) -> None:
    mailbox_dir = _mailbox_dir(mail_root, MAILBOX_ICLOUD_INBOX)
    target = mailbox_dir / VERSION_UUID / "Data" / "Messages" / f"{ORPHAN_UID}.emlx"
    target.parent.mkdir(parents=True, exist_ok=True)
    message = FixtureMessage(
        uid=ORPHAN_UID,
        mailbox=MAILBOX_ICLOUD_INBOX,
        subject="Orphan",
        sender=("Orphan", "orphan@fixture.example"),
        body="Orphan .emlx with no row in the Envelope Index.",
        global_id=0,
        message_id_header="<orphan@fixture.example>",
    )
    target.write_bytes(_emlx_bytes(message, now))


_ENVELOPE_SCHEMA = """
CREATE TABLE messages (
    ROWID INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL DEFAULT 0,
    global_message_id INTEGER NOT NULL,
    sender INTEGER,
    subject INTEGER NOT NULL,
    date_sent INTEGER,
    date_received INTEGER,
    mailbox INTEGER NOT NULL,
    flags INTEGER NOT NULL DEFAULT 0,
    read INTEGER NOT NULL DEFAULT 0,
    flagged INTEGER NOT NULL DEFAULT 0,
    deleted INTEGER NOT NULL DEFAULT 0,
    size INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE subjects (
    ROWID INTEGER PRIMARY KEY AUTOINCREMENT,
    subject TEXT COLLATE RTRIM NOT NULL,
    UNIQUE(subject) ON CONFLICT ABORT
);
CREATE TABLE addresses (
    ROWID INTEGER PRIMARY KEY AUTOINCREMENT,
    address TEXT COLLATE NOCASE NOT NULL,
    comment TEXT COLLATE BINARY NOT NULL,
    UNIQUE(address, comment) ON CONFLICT ABORT
);
CREATE TABLE recipients (
    ROWID INTEGER PRIMARY KEY,
    message INTEGER NOT NULL,
    address INTEGER NOT NULL,
    type INTEGER,
    position INTEGER,
    UNIQUE(message, type, position) ON CONFLICT ABORT
);
CREATE TABLE mailboxes (
    ROWID INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT COLLATE BINARY NOT NULL,
    total_count INTEGER NOT NULL DEFAULT 0,
    unread_count INTEGER NOT NULL DEFAULT 0,
    deleted_count INTEGER NOT NULL DEFAULT 0,
    unseen_count INTEGER NOT NULL DEFAULT 0,
    source INTEGER,
    UNIQUE(url) ON CONFLICT ABORT
);
CREATE TABLE labels (
    message_id INTEGER REFERENCES messages(ROWID) ON DELETE CASCADE,
    mailbox_id INTEGER REFERENCES mailboxes(ROWID) ON DELETE CASCADE,
    PRIMARY KEY(message_id, mailbox_id)
) WITHOUT ROWID;
CREATE TABLE attachments (
    ROWID INTEGER PRIMARY KEY AUTOINCREMENT,
    message INTEGER NOT NULL,
    attachment_id TEXT COLLATE BINARY,
    name TEXT COLLATE BINARY,
    UNIQUE(message, attachment_id) ON CONFLICT ABORT
);
CREATE TABLE message_global_data (
    ROWID INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER,
    message_id_header TEXT COLLATE BINARY,
    UNIQUE(message_id) ON CONFLICT ABORT
);
"""


def _write_envelope_index(
    path: Path, messages: tuple[FixtureMessage, ...], now: datetime, *, extended: bool = False
) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(_ENVELOPE_SCHEMA)
        _insert_mailboxes(connection, extended)
        address_cache: dict[tuple[str, str], int] = {}
        subject_cache: dict[str, int] = {}
        message_id_cache: dict[str, int] = {}
        global_ids = sorted({message.global_id for message in messages if message.global_id})
        for global_id in global_ids:
            header = next(
                (m.message_id_header for m in messages if m.global_id == global_id and m.message_id_header),
                None,
            )
            message_id = 100_000 + global_id
            message_id_cache[str(global_id)] = message_id
            connection.execute(
                "INSERT INTO message_global_data (ROWID, message_id, message_id_header) VALUES (?, ?, ?)",
                (global_id, message_id, header),
            )
        for message in messages:
            received = int((now - message.age).timestamp())
            sent = received - 30
            if message.date_override:
                received = sent = message.date_value
            subject_id = subject_cache.get(message.subject)
            if subject_id is None:
                cursor = connection.execute(
                    "INSERT INTO subjects (subject) VALUES (?)", (message.subject,)
                )
                subject_id = int(cursor.lastrowid)
                subject_cache[message.subject] = subject_id
            sender_id = _address_id(connection, address_cache, message.sender[0], message.sender[1])
            connection.execute(
                """
                INSERT INTO messages (
                    ROWID, message_id, global_message_id, sender, subject, date_sent,
                    date_received, mailbox, flags, read, flagged, deleted, size
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.uid,
                    message_id_cache.get(str(message.global_id), message.uid),
                    message.global_id,
                    sender_id,
                    subject_id,
                    sent,
                    received,
                    message.mailbox,
                    _flags(message),
                    1 if message.read else 0,
                    1 if message.flagged else 0,
                    1 if message.deleted else 0,
                    message.size,
                ),
            )
            for position, (name, address) in enumerate(message.to):
                _insert_recipient(connection, address_cache, message.uid, name, address, 0, position)
            for position, (name, address) in enumerate(message.cc):
                _insert_recipient(connection, address_cache, message.uid, name, address, 1, position)
            for label_mailbox in message.labels:
                connection.execute(
                    "INSERT INTO labels (message_id, mailbox_id) VALUES (?, ?)",
                    (message.uid, label_mailbox),
                )
            for name in message.attachment_names + message.attachment_rows:
                connection.execute(
                    "INSERT INTO attachments (message, attachment_id, name) VALUES (?, ?, ?)",
                    (message.uid, f"att-{message.uid}-{name}", name),
                )
        connection.commit()
    finally:
        connection.close()


def _make_wal_variant(envelope_index: Path) -> tuple[Path, Path]:
    """Put the Envelope Index in WAL mode and leave ``-wal``/``-shm`` on disk."""
    connection = sqlite3.connect(envelope_index)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
    finally:
        connection.close()
    wal = envelope_index.with_name(envelope_index.name + "-wal")
    shm = envelope_index.with_name(envelope_index.name + "-shm")
    # SQLite removes the sidecars on a clean close; recreate them empty (valid:
    # SQLite reinitialises both on the next open).
    wal.touch()
    shm.touch()
    return wal, shm


def _insert_mailboxes(connection: sqlite3.Connection, extended: bool = False) -> None:
    urls = {**MAILBOX_URLS, **EXTENDED_MAILBOX_URLS} if extended else MAILBOX_URLS
    for rowid, url in urls.items():
        total, unread = FAKE_COUNTERS.get(rowid, (0, 0))
        source = MAILBOX_GMAIL_ALL_MAIL if rowid == MAILBOX_GMAIL_INBOX else None
        connection.execute(
            "INSERT INTO mailboxes (ROWID, url, total_count, unread_count, source) VALUES (?, ?, ?, ?, ?)",
            (rowid, url, total, unread, source),
        )


def _address_id(
    connection: sqlite3.Connection,
    cache: dict[tuple[str, str], int],
    name: str,
    address: str,
) -> int:
    key = (name, address)
    if key in cache:
        return cache[key]
    cursor = connection.execute(
        "INSERT INTO addresses (address, comment) VALUES (?, ?)", (address, name)
    )
    rowid = int(cursor.lastrowid)
    cache[key] = rowid
    return rowid


def _insert_recipient(
    connection: sqlite3.Connection,
    cache: dict[tuple[str, str], int],
    message_uid: int,
    name: str,
    address: str,
    recipient_type: int,
    position: int,
) -> None:
    address_id = _address_id(connection, cache, name, address)
    connection.execute(
        "INSERT INTO recipients (message, address, type, position) VALUES (?, ?, ?, ?)",
        (message_uid, address_id, recipient_type, position),
    )


_ACCOUNTS_SCHEMA = """
CREATE TABLE ZACCOUNT (
    Z_PK INTEGER PRIMARY KEY,
    Z_ENT INTEGER,
    Z_OPT INTEGER,
    ZACTIVE INTEGER,
    ZAUTHENTICATED INTEGER,
    ZSUPPORTSAUTHENTICATION INTEGER,
    ZVISIBLE INTEGER,
    ZACCOUNTTYPE INTEGER,
    ZPARENTACCOUNT INTEGER,
    ZACCOUNTDESCRIPTION VARCHAR,
    ZAUTHENTICATIONTYPE VARCHAR,
    ZCREDENTIALTYPE VARCHAR,
    ZIDENTIFIER VARCHAR,
    ZMODIFICATIONID VARCHAR,
    ZOWNINGBUNDLEID VARCHAR,
    ZUSERNAME VARCHAR,
    ZDATACLASSPROPERTIES BLOB
);
CREATE TABLE ZACCOUNTTYPE (
    Z_PK INTEGER PRIMARY KEY,
    ZOBSOLETE INTEGER,
    ZSUPPORTSAUTHENTICATION INTEGER,
    ZSUPPORTSMULTIPLEACCOUNTS INTEGER,
    ZVISIBILITY INTEGER,
    ZACCOUNTTYPEDESCRIPTION VARCHAR,
    ZCREDENTIALPROTECTIONPOLICY VARCHAR,
    ZCREDENTIALTYPE VARCHAR,
    ZIDENTIFIER VARCHAR,
    ZOWNINGBUNDLEID VARCHAR
);
"""

_ACCOUNT_TYPES = (
    (4, "com.apple.account.Google", "Gmail"),
    (40, "com.apple.account.IMAP", "IMAP"),
    (52, "com.apple.account.AppleAccount", "iCloud"),
    (53, "com.apple.account.OnMyDevice", "On My Device"),
    (33, "com.apple.account.AppleIDAuthentication", "Apple ID"),
)


def _write_accounts_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(_ACCOUNTS_SCHEMA)
        for pk, identifier, description in _ACCOUNT_TYPES:
            connection.execute(
                "INSERT INTO ZACCOUNTTYPE (Z_PK, ZIDENTIFIER, ZACCOUNTTYPEDESCRIPTION) VALUES (?, ?, ?)",
                (pk, identifier, description),
            )
        accounts = (
            # (Z_PK, type, parent, description, username, identifier)
            (10, 52, None, "iCloud", "fixture@icloud.com", "PARENT-ICLOUD"),
            (1, 40, 10, None, None, ACCOUNT_ICLOUD),
            (20, 4, None, "Gmail", "fixture@gmail.com", "PARENT-GMAIL"),
            (2, 40, 20, None, None, ACCOUNT_GMAIL),
            (3, 53, None, "On My Mac", None, ACCOUNT_LOCAL),
            (30, 33, None, None, "fixture@apple.id", "NOT-A-MAIL-ACCOUNT"),
        )
        connection.executemany(
            """
            INSERT INTO ZACCOUNT (
                Z_PK, ZACCOUNTTYPE, ZPARENTACCOUNT, ZACCOUNTDESCRIPTION,
                ZUSERNAME, ZIDENTIFIER
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (pk, account_type, parent, description, username, identifier)
                for pk, account_type, parent, description, username, identifier in accounts
            ],
        )
        connection.commit()
    finally:
        connection.close()

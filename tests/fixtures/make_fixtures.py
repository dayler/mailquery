"""Synthetic Apple Mail store used by the test suite.

Builds, under a temporary directory, the pieces mailquery reads from a real
mail installation:

``<root>/Mail/PersistenceInfo.plist``            version metadata
``<root>/Mail/V10/MailData/Envelope Index``      minimal Envelope Index (SQLite)
``<root>/Mail/V10/<account-uuid>/<x>.mbox/...``  on-disk mailbox tree with .emlx
``<root>/Library/Accounts/Accounts4.sqlite``     minimal accounts database
``<root>/home``                                  app home (~/.mailquery equivalent)

Nothing here touches the real ``~/Library/Mail`` or ``~/Library/Accounts``.
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

# A uid that exists on disk but has no row in the Envelope Index (orphan .emlx).
ORPHAN_UID = 99999

# .emlx whose first line is not a valid length and whose payload is not MIME.
CORRUPT_EMLX_BYTES = b"this-is-not-a-length\nnot a valid mime payload\x00\x01"

DEFAULT_CONFIG = f"""\
# Synthetic fixture configuration (all three accounts declared).
[scope."{ICLOUD_LABEL}"]
mailbox_list = ["Facturas", "Archivo"]

[scope."{GMAIL_LABEL}"]

[scope."{LOCAL_LABEL}"]
"""


@dataclass(frozen=True)
class FixturePaths:
    """Paths and metadata of a built synthetic Mail store."""

    root: Path
    mail_root: Path
    home: Path
    accounts_db: Path
    envelope_index: Path
    version_uuid: str
    now: datetime
    mailboxes: dict[str, int] = field(default_factory=dict)
    messages: tuple[FixtureMessage, ...] = ()

    def cleanup(self) -> None:
        import shutil

        shutil.rmtree(self.root, ignore_errors=True)

    def message(self, uid: int) -> FixtureMessage:
        for message in self.messages:
            if message.uid == uid:
                return message
        raise KeyError(uid)


def build_store(root: str | Path | None = None, *, now: datetime | None = None) -> FixturePaths:
    """Build a complete synthetic Mail store and return its paths.

    When ``root`` is ``None`` a new temporary directory is created (the caller
    owns it and can call :meth:`FixturePaths.cleanup`).
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
    messages = DEFAULT_MESSAGES
    for message in messages:
        _write_emlx_files(mail_root, message, now)
    _write_orphan_emlx(mail_root, now)
    _write_envelope_index(envelope_index, messages, now)
    _write_accounts_db(accounts_db)

    mailboxes = {
        "iCloud/INBOX": MAILBOX_ICLOUD_INBOX,
        "iCloud/Facturas": MAILBOX_ICLOUD_FACTURAS,
        "iCloud/Archivo": MAILBOX_ICLOUD_ARCHIVO,
        "Gmail/INBOX": MAILBOX_GMAIL_INBOX,
        "Gmail/All Mail": MAILBOX_GMAIL_ALL_MAIL,
        "Gmail/Important": MAILBOX_GMAIL_IMPORTANT,
        "Local/Recovered Messages": MAILBOX_LOCAL_RECOVERED,
    }
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

    url = MAILBOX_URLS[rowid]
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
    email.set_content(body if body is not None else "")
    if message.html is not None:
        email.add_alternative(message.html, subtype="html")
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


def _write_envelope_index(path: Path, messages: tuple[FixtureMessage, ...], now: datetime) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(_ENVELOPE_SCHEMA)
        _insert_mailboxes(connection)
        address_cache: dict[tuple[str, str], int] = {}
        subject_cache: dict[str, int] = {}
        message_id_cache: dict[str, int] = {}
        global_ids = sorted({message.global_id for message in messages})
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
            for name in message.attachment_names:
                connection.execute(
                    "INSERT INTO attachments (message, attachment_id, name) VALUES (?, ?, ?)",
                    (message.uid, f"att-{message.uid}-{name}", name),
                )
        connection.commit()
    finally:
        connection.close()


def _insert_mailboxes(connection: sqlite3.Connection) -> None:
    for rowid, url in MAILBOX_URLS.items():
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

# mailquery

> [English](README.md) · [Español](README.es.md)

`mailquery` is a command-line tool (Python, standard library only except
`pywin32` on Windows) that **reads and searches local mail without modifying
anything**: Apple Mail on macOS and classic Outlook on Windows. It is meant for
an agent harness to invoke it **on demand** and consume its output.

- **One JSON object per run** on `stdout` (there is no `--format`).
  Exceptions: `--help`, `--version` and the `doctor` text report.
- **Read-only** (invariant I-1): it does not mark as read, move, delete, send,
  download bodies from the server or **launch** Mail.app or Outlook. It only
  writes inside `~/.mailquery` (state, logs, locks, staging and the attachment
  cache).
- **No network, no daemon and no scheduler** from the core: the harness decides
  when to run it. External backend plugins declare their own capabilities
  (`network`, `readonly`, `body_local`, `attachments`, `native_order`) and
  `doctor` shows them.
- **Same commands and same JSON on both platforms.** On macOS read-only access is
  structural (SQLite and `.emlx` opened read-only); on Windows it is enforced by a
  whitelist proxy over Outlook's object model.
- **Opaque `uid` string:** every message id is `"<driver>:<native_id>"`, for the
  built-in drivers and for plugins. The legacy unprefixed uid is accepted on
  input for the platform's native driver.

The attachment and multi-driver features are part of the **future, not-yet-released
3.0.0**; this branch keeps the package version at `2.0.1` and publishes nothing.

References: [`docs/PRD-v2.1.md`](docs/PRD-v2.1.md) (delta contract),
[`docs/recipes/`](docs/recipes/) (recipes for the harness),
[`docs/config.example.toml`](docs/config.example.toml) and
[`docs/INTERFACES.md`](docs/INTERFACES.md) (development and tests),
[`docs/PERFORMANCE-BACKLOG.md`](docs/PERFORMANCE-BACKLOG.md) (pending performance work)
and [`skills/README.md`](skills/README.md) (skill for harnesses).

## Requirements

| Requirement | macOS | Windows |
|-------------|-------|---------|
| System | macOS with Apple Mail (store `V9`/`V10`/`V11`) | Windows 10/11 x64 with **classic** Outlook 16.0 **open** |
| Python | ≥ 3.11 (the one used by `pipx`) | ≥ 3.11 (the one used by `pipx`) |
| `pipx` | `brew install pipx && pipx ensurepath` | `python -m pip install --user pipx && python -m pipx ensurepath` |
| Dependencies | None | `pywin32` (installed by `pipx`) |
| Permissions | **Full Disk Access** (FDA) | Same session and same integrity level as Outlook |

The new Outlook (`olk`), Outlook on the web, Outlook for Mac and other clients
are not supported. Linux is only used for development and CI.

## Install, upgrade and uninstall

```bash
pipx install .          # from the repository root (macOS or Windows)
mailquery --help
mailquery doctor        # creates ~/.mailquery and validates the environment
```

The installers automate `pipx` and seed `~/.mailquery/config.toml` from
[`docs/config.example.toml`](docs/config.example.toml) **only if it does not
exist** (the application never creates or modifies the configuration):

```bash
scripts/install.sh [--dry-run]          # macOS
```

```powershell
.\scripts\install.ps1 [-DryRun]         # Windows (or double-click install.bat)
```

Options: `--no-config`/`-NoConfig`, `--force-config`/`-ForceConfig` (keeps a
`.bak`), `--python`/`-Python`, `--from-git`/`-FromGit`. When it finishes,
`install.ps1` checks that `pywin32` imports from the `pipx` venv and that
`mailquery -v` shows `backend outlook`; if it fails, it points to
`pipx reinstall mailquery` and exits with a non-zero code.

**Backend plugins** are separate packages registered in the
`mailquery.backends` entry point group. Install one explicitly into the same
`pipx` environment (installing the plugin is the consent):

```bash
pipx inject mailquery <plugin-package>
mailquery doctor        # shows the driver and its declared capabilities
mailquery -v            # lists the installed drivers
```

```bash
git pull && pipx reinstall mailquery    # upgrade; then: mailquery doctor
pipx uninject mailquery <plugin-package>  # uninstall a plugin
pipx uninstall mailquery                # uninstall the command
rm -rf ~/.mailquery                     # optional: remove state, logs and cache
```

On Windows the optional removal is `Remove-Item -Recurse -Force $HOME\.mailquery`
(or `.\scripts\install.ps1 -Uninstall -Purge`). `pipx uninstall` does not touch
`~/.mailquery`. To run without installing, see
[`docs/INTERFACES.md` §8](docs/INTERFACES.md).

## Skill for AI harnesses (`skills/`)

The repository ships a skill ready for harnesses (DeepSeek Harness, Claude Code)
that teaches the agent to use the CLI: JSON contract, read-only rules and
untrusted bodies. It is not part of the Python package and is not needed to use
the app.

```bash
# macOS / Linux
./skills/install.sh
# Windows (PowerShell)
powershell -ExecutionPolicy Bypass -File skills\install.ps1
```

It detects the installed harnesses, shows a menu (each detected harness, a custom
path, or install in all) and copies `skills/mailquery/SKILL.md` into the harness
skill root. Non-interactive mode: `./skills/install.sh --harness dsh --scope
project`, `--all`, `--path DIR`, `--dry-run`, `--force`. Details in
[`skills/README.md`](skills/README.md).

## Running the tests

The tests run **from the repository clone** with Python ≥ 3.11; `tests/` is not
part of the package installed by `pipx`. They can run before or after installing:
the suite imports the code from `src/` and **does not use** the installed copy nor
touch the real `~/.mailquery` (every test uses a temporary `HOME`). Standard
library `unittest` only; `pytest` is not needed.

**Windows** (PowerShell, from the repository root):

```powershell
python -m pip install --user pywin32                      # once, as in CI
python -B -m unittest discover -s tests -t . -v           # full suite
python -B -m unittest discover -s tests -t . -k ol_02_05  # one case by ID
python -B -m unittest tests.test_outlook -v               # one module
```

**macOS** (Terminal, from the repository root; the system `python3` is older
than 3.11, so use the Homebrew one with `brew install python`):

```bash
python3 -B -m unittest discover -s tests -t . -v           # full suite
python3 -B -m unittest discover -s tests -t . -k st_03_01  # one case by ID
python3 -B -m unittest tests.test_store -v                 # one module
```

**Linux** (development and CI only; same commands as macOS with `python3` ≥ 3.11):

```bash
python3 -B -m unittest discover -s tests -t . -v
```

Expected result: `OK`, with skips (`skipped=N`) only where the test does not
apply to the machine:

| Test | Skipped when |
|------|--------------|
| `tests/test_smoke.py` (SMOKE-INSTALL, SMOKE-NEW, SMOKE-ATT-AM/OL) | Linux; Windows without classic Outlook open; macOS without an Apple Mail store (`V9`/`V10`/`V11`) under `~/Library/Mail` or without any account that exposes an included mailbox (e.g. only `On My Device`); `pipx` is not on the `PATH` |
| `InstallShTest` | `sh` is not on the `PATH` (usual in PowerShell) |
| `InstallPs1Test` | PowerShell (`pwsh`) is not available |
| `UT-INS-01`, `OL-05.02` | the OS is not Windows |

The SMOKE tests are the only ones that read the real mail client, always
read-only: they install `mailquery` with `pipx` into temporary directories (they
do not touch your installation), run the commands and check that the unread
counters do not change and that the PRD §19 timings are met. They take a few
minutes. On macOS the terminal app running them needs **Full Disk Access**. To
run only the SMOKE tests:

```bash
python -B -m unittest tests.test_smoke -v    # python3 on macOS
```

Conventions (case-ID names, goldens, fake Outlook, CI): see
[`docs/INTERFACES.md` §8](docs/INTERFACES.md).

## Getting started

```bash
mailquery doctor        # 1. preflight: environment, drivers, read-only, config, state, lock
mailquery mailboxes     # 2. accounts and folders, with the label the config will use
# 3. declare at least one account in ~/.mailquery/config.toml
mailquery doctor        # 4. validate again
mailquery search --since 1w
mailquery attachment apple_mail:83143 --index 1   # recover one local attachment
```

Without declared accounts, `search` and `new` return `count: 0` with
`W_NO_ACCOUNTS`: it is not an error, there is simply nothing to observe.

## Configuration (`~/.mailquery/config.toml`)

It is **optional** and its format is identical on both platforms. Only declared
accounts are read; inside each one, `INBOX` is always included and
`mailbox_list` adds extra folders. An unknown key gives `E_CONFIG_INVALID`
(exit 2). The account key may carry the driver prefix:
`[scope."<driver>:<account>"]`; with no prefix the platform's native driver is
used (`apple_mail` on macOS, `outlook` on Windows).

```toml
[scope."apple_mail:iCloud (you@icloud.com)"]              # explicit driver prefix
mailbox_list = ["Invoices"]

[scope."Exchange (you@company.com)"]                      # native driver (outlook on Windows)
mailbox_list = ["INBOX/Invoices"]
```

The account part is the label shown by `mailquery mailboxes`, the email if it is
unique, or the UUID (or a prefix of ≥ 8 characters); with spaces, dots or `@` it
must be quoted. A label that contains `:` must be declared with the explicit
driver prefix, because the first `:` separates the driver. A `[scope]` block of
a driver that is not installed fails with `E_DRIVER_UNKNOWN` (exit 2). All
properties (`[logging]`, `[search]`, `[new]`, `[attachments]`, accounts) are in
[`docs/config.example.toml`](docs/config.example.toml) and in PRD §15.
Precedence: CLI flags, `config.toml`, defaults. The 1.x daily log rotation was
replaced by `[logging].max_size_mb`; the retired key gives `E_CONFIG_INVALID`
with the hint `retention_days was replaced by max_size_mb`.

### Attachment recovery (`[attachments]`)

```toml
[attachments]
enabled = true                 # true | false (default true)
max_file_size_mb = 100         # 1..500, per attachment
max_total_size_mb = 200        # 1..1024 (>= max_file_size_mb), per run
max_count = 50                 # 1..500, only for --all (includes cache hits)
```

`enabled = false` makes `mailquery attachment` fail with
`E_ATTACHMENTS_DISABLED` (exit 2) before opening the store; `show` is not
affected. A value out of range (or `max_total_size_mb < max_file_size_mb`)
gives `E_CONFIG_INVALID` (exit 2). Limits are strict `>` comparisons with
1 MiB = 1,048,576 bytes; a run that exceeds them fails with
`E_ATTACHMENT_TOO_LARGE` (exit 4).

### Plugin configuration and logs

An external plugin may use `~/.mailquery/<driver>.toml` and
`~/.mailquery/logs/<driver>.log`; both are **optional** and owned by the plugin.
The core never reads, creates, rotates or deletes them. A plugin that needs
temporaries uses `~/.mailquery/tmp/plugin-<driver>/` (0700/0600) and cleans it
itself. Secrets must never be written to `config.toml` or `state.json`.

## Commands

Global options: `-h`/`--help` (also per command), `-v`/`--version` (only before
the subcommand) and `--log-level {error,warning,info,debug}`. There is no
`--format`, `--config`, `--home` or `--backend`. The examples are trimmed with
`…`; values always follow the current contract.

### `mailquery -v`

```text
$ mailquery -v          # no side effects: does not create ~/.mailquery nor open the client
mailquery 2.0.1 (backend outlook; Python 3.14.7; Windows 10.0.26200 AMD64; drivers: graph 0.1.0, outlook 2.0.1)
```

The line keeps `backend <native driver>` and adds `; drivers: <driver>
<version>, ...` inside the parentheses, in alphabetical order. Internal drivers
are listed only for the current platform (`apple_mail` on macOS, `outlook` on
Windows); external plugins are always listed. `--version` reads distribution
metadata only: it does not read `config.toml`, does not import plugins and does
not create `~/.mailquery`.

### `mailquery doctor [--json]`

Text report (with `--json`, the machine payload with `checks[]`). It exits 0 if
it can diagnose; a failed check is marked `[FAIL]` and never aborts. The common
checks are `python`, `home`, `driver`, `config`, `state` and `lock`. The
`driver` check validates every declared driver and shows its capabilities,
package version and API version. On macOS the checks are `python`, `home`,
`driver`, `store`, `envelope_index`, `schema`, `readonly_strategy`,
`accounts_db`, `config`, `state` and `lock`. Example:

```text
$ mailquery doctor
mailquery doctor - environment and read-only preflight

Checks:
  [ok]   python             3.14.7
  [ok]   home               …\.mailquery (writable)
  [ok]   driver             outlook (api=1; pkg 2.0.1; network=false; readonly=structural;
                            body_local=true; attachments=local; native_order=text)
  [ok]   pywin32             win32com importable
  [ok]   outlook             classic Outlook 16.0.0.20430 running (attached with GetActiveObject)
  [ok]   stores              1 candidate(s): Exchange (ana.perez@example.com) [Exchange]; 1
                             excluded: Exchange shared (Support) [shared_mailbox]
  [ok]   readonly_strategy   com_readonly: read-only whitelist proxy active, attached with …
  [ok]   object_model_guard  no Outlook security policy decides; active antivirus: Fake Defender
  [ok]   config              Exchange (ana.perez@example.com) → Exchange (ana.perez@example.com) (…): INBOX, Facturas
  [ok]   state               no state yet; the next new run is a first run and emits the messages
                             received in the last 10min before the newest message
  [ok]   lock                available: …\.mailquery\locks\mailquery.lock

Result: 11/11 checks passed
```

When a declared driver is incompatible, `driver` is `ok=false` and its
dependants report `not evaluated: driver failed`; `doctor` still exits 0.

### `mailquery mailboxes`

Accounts, folders, counters and whether they are included in the scope
(`included`). `excluded_stores` lists, on Windows only, the stores that are not
read and the reason (`shared_mailbox`, `public_folders`, `online_mode`,
`network_path`, `unsupported_account_type`, `unavailable`); on macOS it is `[]`.

```json
{
  "ok": true,
  "command": "mailboxes",
  "accounts": [{"uuid": "D70DBCF6-1C2A-4B6E-9A51-E0C3B2A49F10", "label": "Exchange (ana.perez@example.com)",
                "email": "ana.perez@example.com", "declared": true}],
  "mailboxes": [
    {"account": {…}, "name": "INBOX", "path": "INBOX",
     "url": "outlook://D70DBCF6-1C2A-4B6E-9A51-E0C3B2A49F10/INBOX", "total": 3, "unread": 2, "included": true},
    …
  ],
  "excluded_stores": [{"label": "Exchange shared (Support)", "path": null, "reason": "shared_mailbox"}],
  "warnings": []
}
```

### `mailquery search`

Filters: `--subject`, `--text`, `--from`, `--to`, `--cc`, `--since`, `--until`,
`--unread`, `--flagged`, `--has-attachments`, `--include-mailbox` and `--limit`
(default 20, max 200). Patterns are substrings with the wildcards `*` and `?`,
case- and accent-insensitive; in `--subject`, space-separated terms are AND.
Dates: ISO 8601 or relative (`30min`, `24h`, `7d`, `1w`, `1mo`, `1y`, `today`,
`yesterday`); `--since` is inclusive and `--until` exclusive.

Examples: `mailquery search --since 1w --unread` and
`mailquery search --text "*invoice*" --since 1mo --has-attachments`.

Output of `mailquery search --since 1w` (Windows; `uid` trimmed):

```json
{
  "ok": true,
  "command": "search",
  "count": 3,
  "truncated": false,
  "messages": [
    {
      "uid": "outlook:00000000D70DBCF61C2A4B6E9A51E0C3B2A49F10…",
      "subject": "October 2026 invoice",
      "from": {"name": "Supplier Inc", "address": "invoices@supplier.example"},
      "date_received": "2026-11-02T09:54:09-04:00",
      "has_attachments": true,
      "snippet": "Dear customer, please find the October invoice attached.",
      "body": {"available": true, "readable": true, "partial": false, "truncated": false},
      …
    },
    …
  ],
  "scan": {"mode": "metadata", "candidates": 3, "messages_read": 3, "duration_ms": 9},
  "warnings": ["W_BODY_NOT_LOCAL: only the headers of the message are stored locally; the body is never downloaded", …]
}
```

`--text` reads the body of every candidate, so it **requires narrowing** with
`--since`/`--until`, `--from`, `--subject` or an extra folder
(`--include-mailbox` or a `mailbox_list` folder other than INBOX); otherwise it
fails with `E_UNBOUNDED_SCAN` (exit 4). If more than `[search].max_scan`
candidates remain (default 5000), it fails with `E_SCAN_TOO_LARGE` (exit 4). On
Windows, `--to` and `--cc` **do not narrow** `--text` (checking them forces
opening every message); on macOS they do. `--include-mailbox` only accepts
folders of declared accounts. `scan.mode` is `metadata` or `text`.

### `mailquery new [--peek] [--limit N]`

Messages received since the last run, **only once**: it uses a global cursor
stored in `~/.mailquery/state.json` (default 100, max 500). `--peek` returns the
new messages without advancing the cursor or writing state. The **first run**
(no cursor) emits, in ascending order, the messages received in the
`[new].lookback` (default `10min`) before the newest one in the scope, at least
that one, and adds `W_FIRST_RUN`; later runs emit what arrived after the cursor.
Accounts or folders added later do not emit their history (use `search`).
Messages with a null or future date are ignored until their date is valid.

```json
{
  "ok": true,
  "command": "new",
  "count": 1,
  "messages": [ … ],
  "scan": {"mode": "metadata", "candidates": 1, "messages_read": 1, "duration_ms": 4},
  "cursor": {"previous": null,
             "current": {"last_date_received": 1793627649, "last_uid": "apple_mail:83143", "lookback_seconds": 600}},
  "warnings": ["W_FIRST_RUN: first run: emitted the messages received in the last 10min before the newest message"]
}
```

The next run, with no new mail, returns `"count": 0`, `"messages": []` and
`warnings: []`, with `cursor.previous` equal to `cursor.current`.

### `mailquery show <uid>`

Detail of one message: headers, `body_text` (truncated to 20,000 characters,
with `body_truncated` and `W_BODY_TRUNCATED`) and attachments. The `uid` is an
**opaque string** `"<driver>:<native_id>"`: pass it through as-is, no
arithmetic. The legacy unprefixed uid is accepted for the native driver. It only
shows messages from declared accounts (`E_ACCOUNT_NOT_IN_SCOPE` otherwise). An
invalid or missing uid gives `E_USAGE` (exit 2). `show` never writes to disk.

```bash
mailquery show apple_mail:2714
```

```json
{
  "ok": true,
  "command": "show",
  "message": {
    "uid": "apple_mail:2714",
    "subject": "Invoice 2026-10",
    "headers": {"From": "Billing Team <billing@fixture.example>", "Date": "Mon, 09 Nov 2026 20:36:13 -0400", …},
    "body_text": "Please find the invoice attached.",
    "body_truncated": false,
    "attachments": [
      {"index": 1, "name": "invoice-2026-10.pdf", "cached_path": null}
    ],
    "partial": false, "readable": true, "source": {"emlx_path": "/…/2714.emlx", "partial": false},
    …
  },
  "warnings": []
}
```

`attachments[]` carries `index` (the stable 1..N position shared with
`mailquery attachment`), `name` (the original file name) and `cached_path` (the
absolute cached file path, or `null` when there is no regular file in the cache
or the name is unsafe). A driver with `attachments: "none"` returns
`attachments: []`. In S/MIME, `show` returns `attachments: []` (the technical
`smime.p7m` name is never listed) and only the unreadable-body warning remains.

### `mailquery attachment <uid> (--index N | --all) [--force]`

Recovers attachments of one message from the **local** store into
`~/.mailquery/attachments/<driver>/<native_id>/<index:02d>_<sanitized_name>`
(directories 0700, files 0600 on POSIX) and returns the saved paths, names,
sizes and SHA-256. It never downloads from the server and never opens or
executes a file: it only copies decoded bytes.

```bash
mailquery attachment apple_mail:83301 --index 2
mailquery attachment apple_mail:83301 --all
mailquery attachment apple_mail:83301 --index 2 --force
```

| Option | Meaning |
|--------|---------|
| `<uid>` | `"<driver>:<native_id>"` or, on input, the legacy unprefixed uid of the native driver |
| `--index N` | 1-based index to recover (as shown by `show`); mutually exclusive with `--all` |
| `--all` | recover every attachment of the message |
| `--force` | ignore the cache, re-extract and replace the file atomically (`cached: false`) |

```json
{
  "ok": true,
  "command": "attachment",
  "uid": "apple_mail:83301",
  "output_dir": "/Users/you/.mailquery/attachments/apple_mail/83301",
  "count": 1,
  "attachments": [
    {"index": 2, "original_name": "Factura Octubre 2026.pdf",
     "sanitized_name": "02_Factura_Octubre_2026.pdf", "saved": true, "cached": false,
     "path": "/Users/you/.mailquery/attachments/apple_mail/83301/02_Factura_Octubre_2026.pdf",
     "size_bytes": 59, "sha256": "9ead96e0efdc3db6c3bee638bd4dc2e541a67a4f2bba812acf476d4527ce455e"}
  ],
  "warnings": []
}
```

- **The message is blocked as a whole.** If any attachment has a dangerous
  name, a dangerous extension or executable *magic bytes*, nothing is written:
  `E_ATTACHMENT_BLOCKED` (exit 4), both with `--index` and `--all`. The harness
  must not retry the same message and must not open the email's attachments.
- **Cache:** an existing regular file is served with `cached: true` and
  `saved: true` (same `size_bytes`/`sha256`); `--force` re-extracts it. A cache
  file that is not a regular file is treated as a miss. A file deleted by an
  external cleanup is a miss and is extracted once. Nothing is written outside
  `~/.mailquery/tmp/` (staging) and the cache; staging and cache live on the same
  file system and publication is atomic.
- **Limits:** `max_count` (only `--all`, including cache hits),
  `max_file_size_mb` and `max_total_size_mb` from `[attachments]`; exceeding them
  gives `E_ATTACHMENT_TOO_LARGE` (exit 4).
- **Availability:** an attachment that is not local (`not_local`,
  `not_downloaded`, `unsupported`, `network`) fails with
  `E_ATTACHMENT_UNAVAILABLE` (exit 3); corrupt or S/MIME content fails with
  `E_ATTACHMENT_UNREADABLE` (exit 3). An S/MIME message is never reported as
  “no attachments”.
- **Cleanup:** the cache is best-effort and not application state. There is no
  purge on start: use an external cron/cleanup if needed. The app tolerates
  concurrent deletions.

### `mailquery <command> --help`

Each subcommand documents its own options; `mailquery --help` lists the six
commands and the exit code line below.

## Body and warnings

`body.available` tells whether a local body exists and `body.readable` whether it
could be read. Warnings (`"W_CODE: reason"`) are not errors. On both platforms:
`W_NO_ACCOUNTS`, `W_FIRST_RUN`, `W_RESULTS_TRUNCATED`, `W_BODY_TRUNCATED`,
`W_HTML_NO_TEXT`, `W_BODY_UNREADABLE` (includes S/MIME) and
`W_ATTACHMENTS_UNAVAILABLE` (only for an unreadable **non-S/MIME** body; S/MIME
returns an empty attachment list and keeps only the body warning). macOS only:
`W_EMLX_MISSING`, `W_EMLX_CORRUPT` and `W_ACCOUNT_LABELS_UNAVAILABLE`. Windows
only: `W_BODY_NOT_LOCAL` (the item only has headers locally; it is never
downloaded) and `W_STORE_EXCLUDED`. Full catalogue: PRD §12.10.

## Exit codes

Errors are JSON on `stdout` too (`{"ok": false, "error": {"code", "message",
"hint"}}`) plus a summary on `stderr`. Retry **only on 5**; blocked attachments
are a rejection (4), not a transient error.

Line: `0 ok | 2 usage or config error | 3 environment error | 4 rejected query
or blocked attachments | 5 busy or transient error | 6 mail client not running`.

| Exit | Meaning | `E_*` codes |
|------|---------|-------------|
| 0 | Success (includes 0 results, `--help` and `--version`) | — |
| 1 | Unexpected internal error | `E_INTERNAL` |
| 2 | Invalid usage, uid or configuration | `E_USAGE`, `E_CONFIG_INVALID`, `E_CONFIG_ACCOUNT_UNKNOWN`, `E_ACCOUNT_AMBIGUOUS`, `E_ACCOUNT_LABELS_UNAVAILABLE`, `E_ACCOUNT_NOT_IN_SCOPE`, `E_MAILBOX_NOT_FOUND`, `E_BAD_TIME`, `E_BAD_FILTER`, `E_DRIVER_UNKNOWN`, `E_ATTACHMENTS_DISABLED` |
| 3 | Invalid environment or driver failure | `E_STORE_NOT_FOUND`, `E_SCHEMA_UNSUPPORTED`, `E_PERMISSION`, `E_STATE_CORRUPT`, `E_CLIENT_UNSUPPORTED`, `E_DEPENDENCY_MISSING`, `E_CLIENT_TIMEOUT`, `E_PLUGIN_INCOMPATIBLE`, `E_PLUGIN_FAILED`, `E_ATTACHMENT_UNAVAILABLE`, `E_ATTACHMENT_UNREADABLE`, `E_IO` |
| 4 | Rejected query or blocked attachments | `E_UNBOUNDED_SCAN`, `E_SCAN_TOO_LARGE`, `E_ATTACHMENT_BLOCKED`, `E_ATTACHMENT_TOO_LARGE` |
| 5 | Busy or transient | `E_LOCKED`, `E_DB_BUSY`, `E_CLIENT_BUSY` |
| 6 | Mail client not available | `E_OUTLOOK_NOT_RUNNING` |

```text
$ mailquery search --text "*invoice*"          # Outlook; no narrowing: exit 4
mailquery: E_UNBOUNDED_SCAN: --text without a narrowing filter would read every message in the scope
mailquery: hint: add --since, --until, --from, --subject or --include-mailbox (for example: mailquery search --text invoice --since 30d)
```

With Outlook closed, `mailquery search --since 1w` ends with exit 6 and
`E_OUTLOOK_NOT_RUNNING` (`classic Outlook is not running (mailquery never launches
it)`; hint: `open classic Outlook with the same user, without elevation, and
retry`).

## Plugin drivers and capabilities

Each driver — the built-ins `apple_mail` and `outlook` and every external plugin —
declares a unique `driver` name (`[a-z0-9_]{1,64}`), `plugin_api = 1` and the
capability map below. `doctor` prints it in the `driver` check; an incompatible
plugin fails with `E_PLUGIN_INCOMPATIBLE` (exit 3) and a runtime plugin failure
with `E_PLUGIN_FAILED` (exit 3), never `E_INTERNAL`.

| Capability | Values | Meaning |
|------------|--------|---------|
| `network` | `true`/`false` | the plugin uses the network (the core never does) |
| `readonly` | `structural`/`promise` | enforced by architecture or promised by the plugin |
| `body_local` | `true`/`false` | bodies are local (otherwise `network` must be `true`) |
| `attachments` | `local`/`remote`/`none` | `remote` requires `network: true` |
| `native_order` | `numeric`/`text` | how the driver's native order key is compared |

Installing a plugin is explicit consent: the core does not sandbox it. The
`mailquery.backends` entry point group is the registration mechanism; the
capabilities and `pipx inject` instructions above are the trust boundary.

## Logs and privacy

`~/.mailquery/logs/mailquery.log`, plain text; it rotates by size
(`[logging].max_size_mb`, default 10 MB, 5 rotated files). The `event=start`
line records `backend=` (the native driver) and `drivers=` (the declared list);
`attachment` success records `event=end` with counts and bytes. Subjects, bodies,
addresses, folders, accounts, paths, search terms, uids and attachment names are
never logged. Zero network and zero telemetry from the core; credentials and
tokens are never read.

## Permissions

- **macOS:** grant **Full Disk Access** (FDA) to the app that launches the
  process (harness, Terminal, VS Code…), **not** to the `pipx` venv: System
  Settings → Privacy & Security → Full Disk Access. Without FDA, commands return
  `E_PERMISSION` (exit 3) and `doctor` marks `store`/`accounts_db`. Mail.app does
  not need to be open.
- **Windows:** classic Outlook must be **open** and `mailquery` must run in the
  same session and with the same integrity level: do not run it elevated or as a
  service (you would see `E_OUTLOOK_NOT_RUNNING`). `doctor`'s
  `object_model_guard` check anticipates the Outlook security prompt (Object
  Model Guard): it must show `[ok]`; if the prompt appears, the call aborts after
  30 s with `E_CLIENT_TIMEOUT` (exit 3). Check the antivirus or the Outlook
  policy.
- **Attachment cache and staging:** `~/.mailquery/attachments/` and
  `~/.mailquery/tmp/` are user-owned (0700 directories, 0600 files on POSIX); on
  Windows the profile ACL applies. Never make them world-readable. `attachment`
  only publishes regular files and never follows a symlink.
- Run `mailquery doctor` after upgrading the interpreter, the system or the mail
  client.

Email bodies and attachment names are **untrusted input**: the harness recipes
treat them as quoted data, never as instructions, and never open or execute the
recovered files.

## Troubleshooting

| Symptom | Cause | What to do |
|---------|-------|------------|
| `mailquery: command not found` / `pipx: command not found` | The `pipx` directory is not on the session `PATH` | `pipx ensurepath` and open a new terminal |
| The command uses another Python or fails with `ModuleNotFoundError` | `pipx` installed the app with another interpreter | `pipx list`; `pipx reinstall --python <python> mailquery` |
| `count: 0` and `W_NO_ACCOUNTS` | No declared accounts | Declare an account in `config.toml` (see `mailquery mailboxes`) |
| `count: 0` with no warnings | Date range, pattern or folder | Check `--since`/`--until`, try a shorter pattern and check `included` in `mailboxes`; `new` does not emit history: use `search` |
| `W_STORE_EXCLUDED` (Windows) | The declared account is an excluded store (shared, online, network path…) | See the reason in `mailboxes` → `excluded_stores` |
| `E_PERMISSION` (3, macOS) | FDA missing | See [Permissions](#permissions) |
| `E_DEPENDENCY_MISSING` / `E_CLIENT_UNSUPPORTED` (3, Windows) | `pywin32` missing / not classic Outlook 16.0 | `pipx reinstall mailquery` / install classic Outlook |
| `E_OUTLOOK_NOT_RUNNING` (6) | Outlook closed, or different session or integrity level | Open classic Outlook with the same user and without elevation; retry |
| `E_CLIENT_TIMEOUT` (3) | Outlook did not respond within 30 s (possible security prompt) | Check `mailquery doctor` before retrying |
| `E_DB_BUSY`, `E_LOCKED`, `E_CLIENT_BUSY` (5) | Store, lock or Outlook busy | Retry once after a pause; do not run concurrent invocations |
| `E_STATE_CORRUPT` (3) | Damaged `state.json` (only affects `new`) | Rename it; the next `new` run is a first run and emits the `lookback` window again |
| `E_DRIVER_UNKNOWN` (2) | The driver prefix of a `[scope]` block or of the uid is not installed | `mailquery -v` lists installed drivers; `pipx inject mailquery <plugin-package>`; check the spelling `[a-z0-9_]{1,64}` |
| `E_PLUGIN_INCOMPATIBLE` / `E_PLUGIN_FAILED` (3) | The plugin does not satisfy API 1 or failed at runtime | Reinstall/upgrade the plugin; `mailquery doctor` shows the `driver` detail |
| `E_ATTACHMENTS_DISABLED` (2) | `[attachments].enabled = false` | Set `enabled = true` in `config.toml` |
| `E_ATTACHMENT_BLOCKED` (4) | A dangerous name, extension or executable content in **any** attachment of the message | Do not retry; the whole message is blocked. Inspect it in the mail client at your own risk |
| `E_ATTACHMENT_TOO_LARGE` (4) | An `[attachments]` limit was exceeded | Raise the limit or recover only one attachment with `--index` |
| `E_ATTACHMENT_UNAVAILABLE` (3) | The attachment is not local (`not_local`, `not_downloaded`, `unsupported`, `network`) | Open the message in the mail client so it downloads, or recover another message |
| `E_ATTACHMENT_UNREADABLE` (3) | The attachment is corrupt or S/MIME-protected | Inspect it in the mail client; S/MIME attachments cannot be extracted |
| `E_IO` (3) | I/O failure writing the cache or staging (space, quota, file system) | Check free space and permissions of `~/.mailquery`, then retry |
| `E_UNBOUNDED_SCAN` / `E_SCAN_TOO_LARGE` (4) | `--text` without narrowing / too many candidates | Add `--since` or another filter, or raise `search.max_scan` (max 50000) |
| `E_INTERNAL` (1) | Unexpected failure | Check `~/.mailquery/logs/mailquery.log` with `--log-level debug` |

## License

MIT. Copyright (c) 2026 Ariel Dayler Salzar Hinojosa. See
[`LICENSE`](LICENSE) for the full text.

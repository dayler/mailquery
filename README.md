# mailquery

> [English](README.md) · [Español](README.es.md)

`mailquery` is a command-line tool (Python, standard library only except
`pywin32` on Windows) that **reads and searches local mail without modifying
anything**: Apple Mail on macOS and classic Outlook on Windows. It is meant for
an agent harness to invoke it **on demand** and consume its output.

- **One JSON object per run** on `stdout` (there is no `--format`).
  Exceptions: `--help`, `--version` and the `doctor` text report.
- **Read-only** (invariant I-1): it does not mark as read, move, delete, send,
  download attachments or **launch** Mail.app or Outlook. It only writes inside
  `~/.mailquery` (state, logs, locks and temporaries).
- **No network, no daemon and no scheduler**: the harness decides when to run it.
- **Same commands and same JSON on both platforms.** On macOS read-only access is
  structural (SQLite and `.emlx` opened read-only); on Windows it is enforced by a
  whitelist proxy over Outlook's object model. The `uid` is an integer on macOS
  and a hexadecimal string on Windows.

References: [`docs/PRD.md`](docs/PRD.md) (product and contract),
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

```bash
git pull && pipx reinstall mailquery    # upgrade; then: mailquery doctor
pipx uninstall mailquery                # uninstall the command
rm -rf ~/.mailquery                     # optional: remove state, logs and configuration
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
| `tests/test_smoke.py` (SMOKE-INSTALL, SMOKE-NEW) | Linux; Windows without classic Outlook open; macOS without an Apple Mail store (`V9`/`V10`/`V11`) under `~/Library/Mail` or without any account that exposes an included mailbox (e.g. only `On My Device`); `pipx` is not on the `PATH` |
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
mailquery doctor        # 1. preflight: environment, read-only, config, state, lock
mailquery mailboxes     # 2. accounts and folders, with the label the config will use
# 3. declare at least one account in ~/.mailquery/config.toml
mailquery doctor        # 4. validate again
mailquery search --since 1w
```

Without declared accounts, `search` and `new` return `count: 0` with
`W_NO_ACCOUNTS`: it is not an error, there is simply nothing to observe.

## Configuration (`~/.mailquery/config.toml`)

It is **optional** and its format is identical on both platforms. Only declared
accounts are read; inside each one, `INBOX` is always included and
`mailbox_list` adds extra folders. An unknown key gives `E_CONFIG_INVALID`
(exit 2). Minimal example on macOS and its Windows equivalent:

```toml
[scope."iCloud (you@gmail.com)"]                      # macOS
mailbox_list = ["Invoices"]

[scope."Exchange (you@company.com)"]         # Windows
mailbox_list = ["INBOX/Invoices"]
```

Each block's key is the label shown by `mailquery mailboxes`, the email if it is
unique, or the UUID (or a prefix of ≥ 8 characters); with spaces, dots or `@` it
must be quoted. All properties (`[logging]`, `[search]`, `[new]`, accounts) are
in [`docs/config.example.toml`](docs/config.example.toml) and in PRD §15.
Precedence: CLI flags, `config.toml`, defaults. The 1.x daily log rotation was
replaced by `[logging].max_size_mb`; the retired key gives `E_CONFIG_INVALID`
with the hint `retention_days was replaced by max_size_mb`.

## Commands

Global options: `-h`/`--help` (also per command), `-v`/`--version` (only before
the subcommand) and `--log-level {error,warning,info,debug}`. There is no
`--format`, `--config`, `--home` or `--backend`. The examples below are based on
real 2.0.0 output, trimmed with `…`.

### `mailquery -v`

```text
$ mailquery -v          # no side effects: does not create ~/.mailquery nor open the client
mailquery 2.0.0 (backend outlook; Python 3.14.7; Windows 10.0.26200 AMD64)
```

### `mailquery doctor [--json]`

Text report (with `--json`, the machine payload with `checks[]`). It exits 0 if
it can diagnose; a failed check is marked `[FAIL]`. On macOS the checks are
`python`, `home`, `store`, `envelope_index`, `schema`, `readonly_strategy`,
`accounts_db`, `config`, `state` and `lock`. On Windows:

```text
$ mailquery doctor
mailquery doctor - environment and read-only preflight

Checks:
  [ok]   python              3.14.7
  [ok]   home                …\.mailquery (writable)
  [ok]   pywin32             win32com importable
  [ok]   outlook             classic Outlook 16.0.0.20430 running (attached with GetActiveObject)
  [ok]   stores              1 candidate(s): Exchange (ana.perez@example.com) [Exchange]; 1
                             excluded: Exchange shared (Support) [shared_mailbox]
  [ok]   readonly_strategy   com_readonly: read-only whitelist proxy active, attached with …
  [ok]   object_model_guard  no Outlook security policy decides; active antivirus: Fake Defender
  …
  [ok]   state               no state yet; the next new run is a first run and emits the messages
                             received in the last 10min before the newest message
  …

Result: 10/10 checks passed
```

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
      "uid": "00000000D70DBCF61C2A4B6E9A51E0C3B2A49F10…",
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
  "warnings": ["W_BODY_NOT_LOCAL: only the headers of uid 00000000D70DBCF6… are stored locally; the body is never downloaded", …]
}
```

`--text` reads the body of every candidate, so it **requires narrowing** with
`--since`/`--until`, `--from`, `--subject` or an extra folder
(`--include-mailbox` or a `mailbox_list` folder other than INBOX); otherwise it
fails with `E_UNBOUNDED_SCAN` (exit 4). If more than `[search].max_scan`
candidates remain (default 5000), it fails with `E_SCAN_TOO_LARGE` (exit 4). On
Windows, `--to` and `--cc` **do not narrow** `--text` (checking them forces
opening every message); on macOS they do. `--include-mailbox` only accepts
folders of declared accounts. `scan.mode` is `metadata` or `text`. On macOS,
`--text "*invoice*" --since 1mo` returns, among other fields,
`"scan": {"mode": "text", "candidates": 12, "messages_read": 11, …}` and
warnings such as `W_EMLX_MISSING: no .emlx file for uid 83170`.

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
             "current": {"last_date_received": 1793627649, "last_uid": "00000000D70D…", "lookback_seconds": 600}},
  "warnings": ["W_FIRST_RUN: first run: emitted the messages received in the last 10min before the newest message"]
}
```

The next run, with no new mail, returns `"count": 0`, `"messages": []` and
`warnings: []`, with `cursor.previous` equal to `cursor.current`.

### `mailquery show <uid>`

Detail of one message: headers, `body_text` (truncated to 20,000 characters,
with `body_truncated` and `W_BODY_TRUNCATED`) and attachment names. Treat the
`uid` as an **opaque token** (integer on macOS, uppercase hexadecimal string on
Windows): pass it through as-is, no arithmetic. It only shows messages from
declared accounts (`E_ACCOUNT_NOT_IN_SCOPE` otherwise). An invalid or missing uid
gives `E_USAGE` (exit 2).

```bash
mailquery show 00000000D70DBCF61C2A4B6E9A51E0C3B2A49F10…    # the full uid, as returned by search
```

```json
{
  "ok": true,
  "command": "show",
  "message": {
    "uid": "00000000D70DBCF6…",
    "subject": "October 2026 invoice",
    "headers": {"From": "Supplier Inc <invoices@supplier.example>", "Date": "Mon, 02 Nov 2026 13:54:03 +0000", …},
    "body_text": "Dear customer, please find the October invoice attached.",
    "body_truncated": false,
    "attachments": [{"name": "invoice-2026-10.pdf"}],
    "partial": false, "readable": true, "source": {"emlx_path": null, "partial": false},
    …
  },
  "warnings": []
}
```

### Body and warnings

`body.available` tells whether a local body exists and `body.readable` whether it
could be read. Warnings (`"W_CODE: reason"`) are not errors. On both platforms:
`W_NO_ACCOUNTS`, `W_FIRST_RUN`, `W_RESULTS_TRUNCATED`, `W_BODY_TRUNCATED`,
`W_HTML_NO_TEXT`, `W_BODY_UNREADABLE` (includes S/MIME) and
`W_ATTACHMENTS_UNAVAILABLE`. macOS only: `W_EMLX_MISSING`, `W_EMLX_CORRUPT` and
`W_ACCOUNT_LABELS_UNAVAILABLE`. Windows only: `W_BODY_NOT_LOCAL` (the item only
has headers locally; it is never downloaded) and `W_STORE_EXCLUDED`. Full
catalogue: PRD §12.10.

## Exit codes

Errors are JSON on `stdout` too (`{"ok": false, "error": {"code", "message",
"hint"}}`) plus a summary on `stderr`. Retry **only on 5**.

| Exit | Meaning | `E_*` codes |
|------|---------|-------------|
| 0 | Success (includes 0 results, `--help` and `--version`) | — |
| 1 | Unexpected internal error | `E_INTERNAL` |
| 2 | Invalid usage or configuration | `E_USAGE`, `E_CONFIG_INVALID`, `E_CONFIG_ACCOUNT_UNKNOWN`, `E_ACCOUNT_AMBIGUOUS`, `E_ACCOUNT_LABELS_UNAVAILABLE`, `E_ACCOUNT_NOT_IN_SCOPE`, `E_MAILBOX_NOT_FOUND`, `E_BAD_TIME`, `E_BAD_FILTER` |
| 3 | Invalid environment | `E_STORE_NOT_FOUND`, `E_SCHEMA_UNSUPPORTED`, `E_PERMISSION`, `E_STATE_CORRUPT`, `E_CLIENT_UNSUPPORTED`, `E_DEPENDENCY_MISSING`, `E_CLIENT_TIMEOUT` |
| 4 | Rejected query | `E_UNBOUNDED_SCAN`, `E_SCAN_TOO_LARGE` |
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

## Logs and privacy

`~/.mailquery/logs/mailquery.log`, plain text; it rotates by size
(`[logging].max_size_mb`, default 10 MB, 5 rotated files). Subjects, bodies,
addresses, folders, accounts, paths, search terms and message identifiers are
never logged. Zero network and zero telemetry; credentials and tokens are never
read.

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
- Run `mailquery doctor` after upgrading the interpreter, the system or the mail
  client.

Email bodies are **untrusted input**: the harness recipes treat them as quoted
data, never as instructions.

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
| `E_UNBOUNDED_SCAN` / `E_SCAN_TOO_LARGE` (4) | `--text` without narrowing / too many candidates | Add `--since` or another filter, or raise `search.max_scan` (max 50000) |
| `E_INTERNAL` (1) | Unexpected failure | Check `~/.mailquery/logs/mailquery.log` with `--log-level debug` |

## License

MIT. Copyright (c) 2026 Ariel Dayler Salzar Hinojosa. See
[`LICENSE`](LICENSE) for the full text.

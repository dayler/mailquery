# Skill for AI harnesses (`skills/`)

`mailquery` ships a *skill* ready for an AI harness (DeepSeek Harness or Claude Code):
[`skills/mailquery/SKILL.md`](mailquery/SKILL.md) describes the CLI, the JSON contract
and the usage rules (read-only, untrusted bodies). The skill is **not** part of the
Python package or the source code: only harnesses consume it.

## Installation

From the repository root:

```bash
# macOS / Linux
./skills/install.sh

# Windows (PowerShell)
powershell -ExecutionPolicy Bypass -File skills\install.ps1
```

Without arguments the script detects the installed harnesses and shows a menu:

- each detected harness (DeepSeek Harness, Claude Code);
- a custom path (copies to `<path>/mailquery/SKILL.md`);
- install in all detected harnesses.

To automate it or skip the menu:

```bash
./skills/install.sh --harness dsh --scope project
./skills/install.sh --all
./skills/install.sh --path ~/.config/other-harness/skills
./skills/install.sh --dry-run
./skills/install.sh --force          # overwrite a SKILL.md with different content
```

In PowerShell the equivalents are `-Harness dsh|claude|all`, `-Scope`, `-Path`,
`-DryRun` and `-Force`.

## Where it installs

| Harness | User (default) | Project (`--scope project`) |
|---------|----------------|------------------------------|
| DeepSeek Harness | `${DSH_HOME:-~/.dsh}/skills/mailquery/SKILL.md` | `./.dsh/skills/mailquery/SKILL.md` |
| Claude Code | `${CLAUDE_CONFIG_DIR:-~/.claude}/skills/mailquery/SKILL.md` | `./.claude/skills/mailquery/SKILL.md` |

DSH also discovers skills in `./.agents/skills` and `~/.agents/skills` (useful for
sharing them across harnesses); Claude Code only reads `~/.claude/skills` and
`.claude/skills`.

## Detection

- **DeepSeek Harness:** `$DSH_HOME` exists (or `~/.dsh`), or `dsh` is on `PATH`.
- **Claude Code:** `$CLAUDE_CONFIG_DIR` exists (or `~/.claude`), or `claude` is on
  `PATH`.
- If none is detected, the menu only offers a custom path and `--all` fails with
  instructions.

## Requirements for the skill to work

- `mailquery` installed and on `PATH` (`pipx install .` from the root; see the main
  README).
- macOS: Full Disk Access for the app that runs the harness.
- Windows: classic Outlook open with the same user; otherwise
  `E_OUTLOOK_NOT_RUNNING` (exit 6).
- At least one account declared in `~/.mailquery/config.toml`
  (`%USERPROFILE%\.mailquery\config.toml` on Windows), as a
  `[scope."<driver>:<account>"]` block (the prefix may be omitted for the native driver).
- External backend plugins are installed explicitly into the same pipx environment:
  `pipx inject mailquery <plugin-package>`. The skill then sees their drivers through
  `mailquery -v` and `mailquery doctor`, and `show`/`attachment` route the `uid` by its
  `<driver>:` prefix.

The skill documents the six commands (`doctor`, `mailboxes`, `search`, `new`, `show`,
`attachment`), the opaque `uid` string, `show.attachments` and the local attachment
recovery contract (blocked whole message, cache under `~/.mailquery/attachments/`, never
open or execute the recovered files).

## Verification

Restart the harness session so it discovers the skill, then run `mailquery doctor` and
`mailquery mailboxes`. In Claude Code invoke it with `/mailquery`; in DSH it appears in
the skill catalog. To check the new surface, compare `mailquery -v` (the `drivers:` part)
and `mailquery attachment --help` with `skills/mailquery/SKILL.md`.

## Maintenance

`skills/mailquery/SKILL.md` is the source of truth: edit it, re-run the installer
(`--force` if the destination already existed) and restart the session. The installed
copy is not committed: `.dsh/` is in `.gitignore`.

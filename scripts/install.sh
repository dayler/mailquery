#!/bin/sh
# ============================================================================
# mailquery deployment helper - macOS / Linux
#
# Installs (or reinstalls) the `mailquery` command with pipx and, when
# `~/.mailquery/config.toml` does not exist, creates it from
# `docs/config.example.toml`. The application never creates or modifies its
# configuration: only this installer seeds it, and only when missing.
#
# Requirements: macOS or Linux (Linux is for development/CI only), Python >= 3.11 and pipx
# (this script installs pipx when missing, via Homebrew or `python3 -m pip --user`).
#
# Backend plugins are separate packages installed explicitly into the same pipx
# environment: `pipx inject mailquery <plugin-package>`. Installing the plugin is the
# consent; the core never sandboxes it and `mailquery doctor` shows its capabilities.
# ============================================================================
set -eu
umask 077

SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd "$SCRIPT_DIR/.." && pwd)
TEMPLATE_FILE="$REPO_ROOT/docs/config.example.toml"
GIT_SPEC="git+https://github.com/dayler/mailquery.git"

HOME_DIR=${HOME:?HOME is not set}
CONFIG_DIR="$HOME_DIR/.mailquery"
CONFIG_FILE="$CONFIG_DIR/config.toml"

DRY_RUN=0
PRINT_CONFIG=0
NO_CONFIG=0
FORCE_CONFIG=0
FROM_GIT=0
UNINSTALL=0
PURGE=0
VERBOSE=0
PYTHON=""
CONFIG_CREATED=0

usage() {
    cat <<'EOF'
Usage: scripts/install.sh [options]

Install or reinstall the mailquery command with pipx and, when it does not
exist yet, create ~/.mailquery/config.toml from docs/config.example.toml
(including the documented [attachments] block). The application never
creates or modifies its configuration: only this installer seeds it.
Backend plugins: `pipx inject mailquery <plugin-package>` after installing.

Options:
  -h, --help        Show this help and exit.
  --dry-run         Print the plan without executing or writing anything.
  --print-config    Print the configuration template and exit.
  --no-config       Do not create ~/.mailquery/config.toml.
  --force-config    Overwrite config.toml (a timestamped backup is kept first).
  --python PATH     Python interpreter for pipx (e.g. python3.14).
  --from-git        Install from https://github.com/dayler/mailquery.git.
  --uninstall       Uninstall mailquery with pipx.
  --purge           With --uninstall, also remove ~/.mailquery.
  -v, --verbose     Show the executed commands.

Exit codes: 0 success, 1 failure, 2 usage error.
EOF
}

log() {
    printf '%s\n' "$*" >&2
}

verbose() {
    if [ "$VERBOSE" -eq 1 ]; then
        log "debug: $*"
    fi
}

fail() {
    log "error: $*"
    exit 1
}

run() {
    if [ "$VERBOSE" -eq 1 ]; then
        log "running: $*"
    fi
    "$@"
}

pipx_cmd() {
    if command -v pipx >/dev/null 2>&1; then
        pipx "$@"
    else
        PYTHON_BIN=${PYTHON:-python3}
        "$PYTHON_BIN" -m pipx "$@"
    fi
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        -h|--help)
            usage
            exit 0
            ;;
        --dry-run)
            DRY_RUN=1
            ;;
        --print-config)
            PRINT_CONFIG=1
            ;;
        --no-config)
            NO_CONFIG=1
            ;;
        --force-config)
            FORCE_CONFIG=1
            ;;
        --from-git)
            FROM_GIT=1
            ;;
        --uninstall)
            UNINSTALL=1
            ;;
        --purge)
            PURGE=1
            ;;
        -v|--verbose)
            VERBOSE=1
            ;;
        --python)
            if [ "$#" -lt 2 ]; then
                log "error: --python requires a value"
                exit 2
            fi
            PYTHON=$2
            shift
            ;;
        --python=*)
            PYTHON=${1#--python=}
            ;;
        *)
            log "error: unknown option: $1"
            usage >&2
            exit 2
            ;;
    esac
    shift
done

if [ "$PURGE" -eq 1 ] && [ "$UNINSTALL" -eq 0 ]; then
    log "error: --purge requires --uninstall"
    exit 2
fi
if [ "$FORCE_CONFIG" -eq 1 ] && [ "$NO_CONFIG" -eq 1 ]; then
    log "error: --force-config cannot be combined with --no-config"
    exit 2
fi

if [ "$PRINT_CONFIG" -eq 1 ]; then
    if [ ! -f "$TEMPLATE_FILE" ]; then
        fail "template not found: $TEMPLATE_FILE"
    fi
    cat "$TEMPLATE_FILE"
    exit 0
fi

if [ "$DRY_RUN" -eq 1 ]; then
    log "Deployment plan (dry-run; nothing will be executed):"
    if [ "$UNINSTALL" -eq 1 ]; then
        log "  1. pipx uninstall mailquery (when installed)"
        if [ "$PURGE" -eq 1 ]; then
            log "  2. rm -rf $CONFIG_DIR"
        fi
        exit 0
    fi
    if [ "$FROM_GIT" -eq 1 ]; then
        log "  1. check pipx (install it when missing) and run pipx ensurepath"
        log "  2. pipx install/reinstall from $GIT_SPEC"
    else
        log "  1. check pipx (install it when missing) and run pipx ensurepath"
        log "  2. pipx install/reinstall from $REPO_ROOT"
    fi
    if [ -n "$PYTHON" ]; then
        log "     interpreter: $PYTHON"
    fi
    log "  3. verify 'mailquery' is in PATH and run 'mailquery doctor' (macOS only)"
    if [ "$NO_CONFIG" -eq 1 ]; then
        log "  4. config: skipped (--no-config)"
    elif [ -e "$CONFIG_FILE" ] && [ "$FORCE_CONFIG" -eq 0 ]; then
        log "  4. config: $CONFIG_FILE already exists (it will not be overwritten)"
    elif [ -e "$CONFIG_FILE" ]; then
        log "  4. config: back up $CONFIG_FILE and copy the template"
    else
        log "  4. config: create $CONFIG_FILE from the template (0600)"
    fi
    log "  5. print next steps"
    exit 0
fi

OS=$(uname -s 2>/dev/null || echo unknown)
case "$OS" in
    Darwin)
        ;;
    Linux)
        log "warning: mailquery runs on macOS (Apple Mail) and Windows (Outlook); on Linux the install is for development/CI only."
        ;;
    *)
        log "warning: system '$OS' is not supported by the app (macOS and Windows only); the install may not be useful."
        ;;
esac

if [ "$UNINSTALL" -eq 1 ]; then
    if command -v pipx >/dev/null 2>&1 && pipx list 2>/dev/null | grep -q "package mailquery "; then
        run pipx uninstall mailquery
    else
        log "mailquery is not installed with pipx; nothing to uninstall."
    fi
    if [ "$PURGE" -eq 1 ]; then
        run rm -rf "$CONFIG_DIR"
        log "removed $CONFIG_DIR (--purge)"
    fi
    log "Uninstall complete."
    exit 0
fi

if ! command -v pipx >/dev/null 2>&1; then
    log "pipx not found; installing it..."
    if [ "$OS" = "Darwin" ] && command -v brew >/dev/null 2>&1; then
        run brew install pipx
    else
        PYTHON_BIN=${PYTHON:-python3}
        if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
            fail "could not find '$PYTHON_BIN'; install Python >= 3.11 or use --python"
        fi
        run "$PYTHON_BIN" -m pip install --user pipx
    fi
fi

if command -v pipx >/dev/null 2>&1; then
    if ! run pipx ensurepath >/dev/null 2>&1; then
        log "warning: 'pipx ensurepath' could not update PATH; check your shell manually"
    fi
else
    if ! run pipx_cmd ensurepath >/dev/null 2>&1; then
        log "warning: 'pipx ensurepath' could not update PATH; check your shell manually"
    fi
fi

if [ "$FROM_GIT" -eq 1 ]; then
    SPEC="$GIT_SPEC"
else
    SPEC="$REPO_ROOT"
fi

if pipx_cmd list 2>/dev/null | grep -q "package mailquery "; then
    if [ -n "$PYTHON" ]; then
        run pipx_cmd reinstall --python "$PYTHON" mailquery
    else
        run pipx_cmd reinstall mailquery
    fi
else
    if [ -n "$PYTHON" ]; then
        run pipx_cmd install --python "$PYTHON" "$SPEC"
    else
        run pipx_cmd install "$SPEC"
    fi
fi

if ! command -v mailquery >/dev/null 2>&1; then
    fail "mailquery is not in PATH; open a new terminal (pipx ensurepath) and retry"
fi
verbose "mailquery: $(command -v mailquery)"

if [ "$OS" = "Darwin" ]; then
    run mailquery --help >/dev/null
else
    log "warning: skipping 'mailquery --help' (the app requires macOS/Apple Mail)"
fi

if [ "$NO_CONFIG" -eq 1 ]; then
    log "config: skipped (--no-config)"
else
    if [ ! -f "$TEMPLATE_FILE" ]; then
        fail "template not found: $TEMPLATE_FILE"
    fi
    if [ -e "$CONFIG_FILE" ] && [ "$FORCE_CONFIG" -eq 0 ]; then
        log "config: $CONFIG_FILE already exists (not overwritten; use --force-config)"
    else
        if [ -e "$CONFIG_FILE" ]; then
            BACKUP_FILE="$CONFIG_FILE.bak-$(date +%Y%m%d%H%M%S)"
            run cp -p "$CONFIG_FILE" "$BACKUP_FILE"
            log "config: backup at $BACKUP_FILE"
        fi
        run mkdir -p "$CONFIG_DIR"
        run cp "$TEMPLATE_FILE" "$CONFIG_FILE"
        run chmod 600 "$CONFIG_FILE"
        CONFIG_CREATED=1
        log "config: created $CONFIG_FILE from the template (edit it to declare accounts)"
    fi
fi

if [ "$OS" = "Darwin" ]; then
    log "running 'mailquery doctor' (preflight)..."
    if ! mailquery doctor >/dev/null 2>&1; then
        log "warning: 'mailquery doctor' reported problems; run it without redirection to see the details"
    fi
else
    log "warning: 'mailquery doctor' is skipped outside macOS"
fi

log ""
log "Deployment complete."
if [ "$CONFIG_CREATED" -eq 1 ]; then
    log "  - Created ~/.mailquery/config.toml (no accounts declared yet)."
fi
log "  - Edit ~/.mailquery/config.toml and declare at least one account."
log "  - Verify: mailquery doctor && mailquery mailboxes"
log "  - Query:  mailquery search --since 1w"
log "  - Plugins: pipx inject mailquery <plugin-package> (declared by their driver)"
log "  - Attachments: mailquery attachment <uid> --index 1 (see the [attachments] block)"

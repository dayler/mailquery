#!/bin/sh
# Install the mailquery skill into a local AI harness (DeepSeek Harness or Claude Code).
#
# The source of truth is skills/mailquery/SKILL.md in this repository; this script only
# copies it into the harness skill root(s). It never touches mail or ~/.mailquery.
set -eu

SKILL_NAME="mailquery"
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SKILL_SRC="${SCRIPT_DIR}/${SKILL_NAME}/SKILL.md"

usage() {
    cat <<'EOF'
Install the mailquery skill into a local AI harness.

Usage: skills/install.sh [options]

Options:
  --harness dsh|claude|all   install into that harness (all = every detected one)
  --scope user|project       user-level (default) or the current project
  --path DIR                 custom skills root; installs DIR/mailquery/SKILL.md
  --all                      same as --harness all
  --force                    overwrite an existing SKILL.md with different content
  --dry-run                  print the targets without writing anything
  --menu                     show the menu even when stdin is not a terminal
  -h, --help                 show this help and exit

Without --harness, --all or --path the script auto-detects installed harnesses and
shows a menu (detected harnesses, a custom path, or install in all detected).

Harness roots (user scope):
  dsh      ${DSH_HOME:-$HOME/.dsh}/skills
  claude   ${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills

Project scope roots (relative to the current directory):
  dsh      ./.dsh/skills
  claude   ./.claude/skills

Run it from the repository root, e.g.:
  ./skills/install.sh
  ./skills/install.sh --harness dsh --scope project
EOF
}

say() { printf '%s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

harness="auto"
scope="user"
custom_path=""
force_menu=0
force=0
dry_run=0

while [ $# -gt 0 ]; do
    case "$1" in
        --harness)
            [ $# -ge 2 ] || die "--harness needs a value (dsh, claude or all)"
            harness=$2
            shift 2
            ;;
        --harness=*)
            harness=${1#*=}
            shift
            ;;
        --scope)
            [ $# -ge 2 ] || die "--scope needs a value (user or project)"
            scope=$2
            shift 2
            ;;
        --scope=*)
            scope=${1#*=}
            shift
            ;;
        --path)
            [ $# -ge 2 ] || die "--path needs a directory"
            custom_path=$2
            shift 2
            ;;
        --path=*)
            custom_path=${1#*=}
            shift
            ;;
        --all)
            harness="all"
            shift
            ;;
        --menu)
            force_menu=1
            shift
            ;;
        --force)
            force=1
            shift
            ;;
        --dry-run)
            dry_run=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            die "unknown option: $1 (try --help)"
            ;;
    esac
done

case "$harness" in
    dsh|claude|all|auto) ;;
    *) die "invalid --harness '$harness' (expected dsh, claude or all)" ;;
esac
case "$scope" in
    user|project) ;;
    *) die "invalid --scope '$scope' (expected user or project)" ;;
esac

[ -f "$SKILL_SRC" ] || die "skill source not found: $SKILL_SRC"

dsh_home=${DSH_HOME:-$HOME/.dsh}
claude_home=${CLAUDE_CONFIG_DIR:-$HOME/.claude}

dsh_detected=0
claude_detected=0
if [ -d "$dsh_home" ] || command -v dsh >/dev/null 2>&1; then
    dsh_detected=1
fi
if [ -d "$claude_home" ] || command -v claude >/dev/null 2>&1; then
    claude_detected=1
fi

root_for() { # harness
    case "$1" in
        dsh)
            if [ "$scope" = "project" ]; then
                printf '%s/.dsh/skills' "$PWD"
            else
                printf '%s/skills' "$dsh_home"
            fi
            ;;
        claude)
            if [ "$scope" = "project" ]; then
                printf '%s/.claude/skills' "$PWD"
            else
                printf '%s/skills' "$claude_home"
            fi
            ;;
        *) die "unknown harness: $1" ;;
    esac
}

install_skill() { # root
    root=$1
    target_dir="${root}/${SKILL_NAME}"
    target="${target_dir}/SKILL.md"
    if [ "$dry_run" -eq 1 ]; then
        say "would install: $target"
        return 0
    fi
    if ! mkdir -p "$target_dir"; then
        die "cannot create directory: $target_dir"
    fi
    if [ -f "$target" ]; then
        if cmp -s "$SKILL_SRC" "$target"; then
            say "up to date: $target"
            return 0
        fi
        if [ "$force" -eq 1 ]; then
            say "overwriting: $target"
        else
            die "already installed with different content: $target (use --force)"
        fi
    fi
    if ! cp "$SKILL_SRC" "$target"; then
        die "cannot copy the skill to: $target"
    fi
    say "installed: $target"
}

expand_custom_path() {
    case "$1" in
        "~") printf '%s' "$HOME" ;;
        "~/"*) printf '%s/%s' "$HOME" "${1#\~/}" ;;
        *) printf '%s' "$1" ;;
    esac
}

choose_from_menu() {
    count=0
    if [ "$dsh_detected" -eq 1 ]; then
        count=$((count + 1))
        dsh_option=$count
        say "  ${count}) DeepSeek Harness (dsh)   -> $(root_for dsh)"
    fi
    if [ "$claude_detected" -eq 1 ]; then
        count=$((count + 1))
        claude_option=$count
        say "  ${count}) Claude Code (claude)     -> $(root_for claude)"
    fi
    custom_option=$((count + 1))
    say "  ${custom_option}) Custom path (the skill is copied to <path>/mailquery/SKILL.md)"
    all_option=""
    if [ "$count" -gt 0 ]; then
        all_option=$((count + 2))
        say "  ${all_option}) Install in all detected harnesses"
    fi

    if [ "$count" -eq 0 ]; then
        say ""
        say "No harness detected (looked for $dsh_home and $claude_home)."
        default_option=$custom_option
    elif [ -n "$all_option" ]; then
        default_option=$all_option
    else
        default_option=1
    fi

    printf 'Select an option [%s]: ' "$default_option"
    read -r choice || die "no input"
    choice=${choice:-$default_option}
    case "$choice" in
        *[!0-9]*) die "invalid option: $choice" ;;
    esac

    if [ "$choice" -eq "$custom_option" ]; then
        printf 'Skills root directory: '
        read -r custom_path || die "no input"
        [ -n "$custom_path" ] || die "empty path"
        custom_path=$(expand_custom_path "$custom_path")
        install_skill "$custom_path"
        return 0
    fi
    if [ -n "$all_option" ] && [ "$choice" -eq "$all_option" ]; then
        for name in dsh claude; do
            case "$name" in
                dsh) [ "$dsh_detected" -eq 1 ] || continue ;;
                claude) [ "$claude_detected" -eq 1 ] || continue ;;
            esac
            install_skill "$(root_for "$name")"
        done
        return 0
    fi
    if [ -n "${dsh_option:-}" ] && [ "$choice" -eq "$dsh_option" ]; then
        install_skill "$(root_for dsh)"
        return 0
    fi
    if [ -n "${claude_option:-}" ] && [ "$choice" -eq "$claude_option" ]; then
        install_skill "$(root_for claude)"
        return 0
    fi
    die "invalid option: $choice"
}

if [ -n "$custom_path" ]; then
    custom_path=$(expand_custom_path "$custom_path")
    install_skill "$custom_path"
elif [ "$harness" = "all" ]; then
    if [ "$dsh_detected" -eq 0 ] && [ "$claude_detected" -eq 0 ]; then
        die "no harness detected (looked for $dsh_home and $claude_home); use --path DIR"
    fi
    [ "$dsh_detected" -eq 0 ] || install_skill "$(root_for dsh)"
    [ "$claude_detected" -eq 0 ] || install_skill "$(root_for claude)"
elif [ "$harness" != "auto" ]; then
    install_skill "$(root_for "$harness")"
elif [ "$force_menu" -eq 1 ] || [ -t 0 ]; then
    say "Detected harnesses:"
    choose_from_menu
else
    die "no interactive terminal: pass --harness, --all or --path (see --help)"
fi

if [ "$dry_run" -eq 0 ]; then
    if ! command -v mailquery >/dev/null 2>&1; then
        warn "the mailquery CLI is not on PATH; install it before using the skill (see README)"
    fi
    say ""
    say "Restart the harness session (or reload skills) so it discovers the skill."
fi

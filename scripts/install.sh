#!/bin/sh
# ============================================================================
# mailquery deployment helper — macOS / Linux
#
# Instala (o reinstala) el comando `mailquery` con pipx y, si
# `~/.mailquery/config.toml` no existe, lo crea a partir de
# `docs/config.example.toml`. La aplicación nunca crea ni modifica su
# configuración: solo este instalador la siembra, y solo si falta.
#
# Requisitos: macOS o Linux, Python >= 3.11 y pipx (el script lo instala si
# falta con Homebrew o `python3 -m pip --user`).
# ============================================================================
set -eu
umask 077

SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd "$SCRIPT_DIR/.." && pwd)
TEMPLATE_FILE="$REPO_ROOT/docs/config.example.toml"
GIT_SPEC="git+https://github.com/dayler/mailquery.git"

HOME_DIR=${HOME:?HOME no está definido}
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

Instala o reinstala el comando mailquery con pipx y, si no existe, crea
~/.mailquery/config.toml a partir de docs/config.example.toml. La aplicación
nunca crea ni modifica su configuración: solo este instalador la siembra.

Options:
  -h, --help        Muestra esta ayuda y termina.
  --dry-run         Imprime el plan sin ejecutar ni escribir nada.
  --print-config    Imprime la plantilla de configuración y termina.
  --no-config       No crea ~/.mailquery/config.toml.
  --force-config    Sobrescribe config.toml (antes guarda un backup).
  --python PATH     Intérprete de Python para pipx (p. ej. python3.14).
  --from-git        Instala desde https://github.com/dayler/mailquery.git.
  --uninstall       Desinstala mailquery con pipx.
  --purge           Con --uninstall, borra también ~/.mailquery.
  -v, --verbose     Muestra los comandos ejecutados.

Exit codes: 0 éxito, 1 fallo, 2 error de uso.
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
                log "error: --python requiere un valor"
                exit 2
            fi
            PYTHON=$2
            shift
            ;;
        --python=*)
            PYTHON=${1#--python=}
            ;;
        *)
            log "error: opción desconocida: $1"
            usage >&2
            exit 2
            ;;
    esac
    shift
done

if [ "$PURGE" -eq 1 ] && [ "$UNINSTALL" -eq 0 ]; then
    log "error: --purge requiere --uninstall"
    exit 2
fi
if [ "$FORCE_CONFIG" -eq 1 ] && [ "$NO_CONFIG" -eq 1 ]; then
    log "error: --force-config no se combina con --no-config"
    exit 2
fi

if [ "$PRINT_CONFIG" -eq 1 ]; then
    if [ ! -f "$TEMPLATE_FILE" ]; then
        fail "no existe la plantilla: $TEMPLATE_FILE"
    fi
    cat "$TEMPLATE_FILE"
    exit 0
fi

if [ "$DRY_RUN" -eq 1 ]; then
    log "Plan de despliegue (dry-run; no se ejecuta nada):"
    if [ "$UNINSTALL" -eq 1 ]; then
        log "  1. pipx uninstall mailquery (si está instalado)"
        if [ "$PURGE" -eq 1 ]; then
            log "  2. rm -rf $CONFIG_DIR"
        fi
        exit 0
    fi
    if [ "$FROM_GIT" -eq 1 ]; then
        log "  1. comprobar pipx (instalarlo si falta) y pipx ensurepath"
        log "  2. pipx install/reinstall con $GIT_SPEC"
    else
        log "  1. comprobar pipx (instalarlo si falta) y pipx ensurepath"
        log "  2. pipx install/reinstall desde $REPO_ROOT"
    fi
    if [ -n "$PYTHON" ]; then
        log "     intérprete: $PYTHON"
    fi
    log "  3. verificar 'mailquery' en PATH y ejecutar 'mailquery doctor' (solo macOS)"
    if [ "$NO_CONFIG" -eq 1 ]; then
        log "  4. config: omitida (--no-config)"
    elif [ -e "$CONFIG_FILE" ] && [ "$FORCE_CONFIG" -eq 0 ]; then
        log "  4. config: ya existe $CONFIG_FILE (no se sobrescribe)"
    elif [ -e "$CONFIG_FILE" ]; then
        log "  4. config: backup de $CONFIG_FILE y copia de la plantilla"
    else
        log "  4. config: crear $CONFIG_FILE desde la plantilla (0600)"
    fi
    log "  5. imprimir los siguientes pasos"
    exit 0
fi

OS=$(uname -s 2>/dev/null || echo unknown)
case "$OS" in
    Darwin)
        ;;
    Linux)
        log "aviso: mailquery solo opera en macOS con Apple Mail; en Linux la instalación sirve para desarrollo/CI."
        ;;
    *)
        log "aviso: sistema '$OS' no soportado por la app (solo macOS); la instalación puede no ser útil."
        ;;
esac

if [ "$UNINSTALL" -eq 1 ]; then
    if command -v pipx >/dev/null 2>&1 && pipx list 2>/dev/null | grep -q "package mailquery "; then
        run pipx uninstall mailquery
    else
        log "mailquery no está instalado con pipx; nada que desinstalar."
    fi
    if [ "$PURGE" -eq 1 ]; then
        run rm -rf "$CONFIG_DIR"
        log "borrado $CONFIG_DIR (--purge)"
    fi
    log "Desinstalación completada."
    exit 0
fi

if ! command -v pipx >/dev/null 2>&1; then
    log "pipx no encontrado; instalándolo..."
    if [ "$OS" = "Darwin" ] && command -v brew >/dev/null 2>&1; then
        run brew install pipx
    else
        PYTHON_BIN=${PYTHON:-python3}
        if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
            fail "no encontré '$PYTHON_BIN'; instala Python >= 3.11 o usa --python"
        fi
        run "$PYTHON_BIN" -m pip install --user pipx
    fi
fi

if command -v pipx >/dev/null 2>&1; then
    if ! run pipx ensurepath >/dev/null 2>&1; then
        log "aviso: 'pipx ensurepath' no pudo actualizar el PATH; revisa tu shell manualmente"
    fi
else
    if ! run pipx_cmd ensurepath >/dev/null 2>&1; then
        log "aviso: 'pipx ensurepath' no pudo actualizar el PATH; revisa tu shell manualmente"
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
    fail "mailquery no está en PATH; abre una terminal nueva (pipx ensurepath) y reejecuta"
fi
verbose "mailquery: $(command -v mailquery)"

if [ "$OS" = "Darwin" ]; then
    run mailquery --help >/dev/null
else
    log "aviso: se omite 'mailquery --help' (la app depende de macOS/Apple Mail)"
fi

if [ "$NO_CONFIG" -eq 1 ]; then
    log "config: omitida (--no-config)"
else
    if [ ! -f "$TEMPLATE_FILE" ]; then
        fail "no existe la plantilla: $TEMPLATE_FILE"
    fi
    if [ -e "$CONFIG_FILE" ] && [ "$FORCE_CONFIG" -eq 0 ]; then
        log "config: ya existe $CONFIG_FILE (no se sobrescribe; usa --force-config)"
    else
        if [ -e "$CONFIG_FILE" ]; then
            BACKUP_FILE="$CONFIG_FILE.bak-$(date +%Y%m%d%H%M%S)"
            run cp -p "$CONFIG_FILE" "$BACKUP_FILE"
            log "config: backup en $BACKUP_FILE"
        fi
        run mkdir -p "$CONFIG_DIR"
        run cp "$TEMPLATE_FILE" "$CONFIG_FILE"
        run chmod 600 "$CONFIG_FILE"
        CONFIG_CREATED=1
        log "config: creada $CONFIG_FILE desde la plantilla (edítala para declarar cuentas)"
    fi
fi

if [ "$OS" = "Darwin" ]; then
    log "ejecutando 'mailquery doctor' (preflight)..."
    if ! mailquery doctor >/dev/null 2>&1; then
        log "aviso: 'mailquery doctor' reportó problemas; ejecútalo sin redirección para ver el detalle"
    fi
else
    log "aviso: 'mailquery doctor' se omite fuera de macOS"
fi

log ""
log "Despliegue completado."
if [ "$CONFIG_CREATED" -eq 1 ]; then
    log "  - Se creó ~/.mailquery/config.toml (todavía sin cuentas declaradas)."
fi
log "  - Edita ~/.mailquery/config.toml y declara al menos una cuenta."
log "  - Verifica: mailquery doctor && mailquery mailboxes"
log "  - Consulta:  mailquery search --since 1w"

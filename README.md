# mailquery

`mailquery` es una herramienta de línea de comandos, escrita en Python (solo
biblioteca estándar), que **lee y busca correos de Apple Mail sin modificar
absolutamente nada**: no marca correos como leídos, no edita, no mueve, no
borra y no cambia flags. Está pensada para que un harness de agentes (DeepSeek u
otro similar) la invoque **bajo demanda** y consuma su salida.

- **Un único objeto JSON por ejecución** en `stdout` (no existe `--format`).
- **Solo lectura estricta** (invariante I-1): ningún archivo dentro de
  `~/Library/Mail` se escribe, renombra, mueve, trunca ni toca en sus fechas.
- **Sin red, sin demonio, sin scheduler y sin base de datos propia**: la única
  fuente de verdad es Apple Mail.
- **Bajo demanda**: la herramienta no programa nada; quien decide cuándo
  ejecutarla es el harness.

> Documentación de referencia interna: [`docs/PRD.md`](docs/PRD.md) (producto) y
> [`docs/INTERFACES.md`](docs/INTERFACES.md) (contratos de implementación).
> Recetas listas para el harness: [`docs/recipes/`](docs/recipes/).

## Índice

1. [Qué es y qué garantiza](#qué-es-y-qué-garantiza)
2. [Cómo funciona (resumen)](#cómo-funciona-resumen)
3. [Requisitos](#requisitos)
4. [Despliegue e instalación](#despliegue-e-instalación)
5. [Primera ejecución y home `~/.mailquery`](#primera-ejecución-y-home-mailquery)
6. [Configuración: `config.toml`](#configuración-configtoml)
7. [Referencia de comandos](#referencia-de-comandos)
8. [Contrato JSON](#contrato-json)
9. [Logs](#logs)
10. [Privacidad y permisos (FDA/TCC)](#privacidad-y-permisos-fdatcc)
11. [Seguridad: contenido de correo y prompt injection](#seguridad-contenido-de-correo-y-prompt-injection)
12. [Pruebas](#pruebas)
13. [Actualización y desinstalación](#actualización-y-desinstalación)
14. [Solución de problemas](#solución-de-problemas)
15. [Licencia](#licencia)

---

## Qué es y qué garantiza

`mailquery` lee el almacén local de Apple Mail:

- el **`Envelope Index`** (metadatos: remitente, asunto, fechas, estado,
  carpetas, adjuntos) abierto en SQLite **estrictamente read-only**;
- los archivos **`.emlx` / `.partial.emlx`** para el cuerpo del mensaje,
  abiertos solo con `open(path, "rb")`;
- opcionalmente, `~/Library/Accounts/Accounts4.sqlite` (también read-only) para
  mostrar etiquetas legibles de cuenta (`iCloud (email)`, `Gmail (email)`,
  `On My Device`).

La salida es siempre un objeto JSON con un contrato estable, incluyendo errores
(que también son JSON en `stdout`, con un resumen legible en `stderr`).

### Garantía de solo lectura (invariante I-1)

`mailquery` **no escribe, renombra, mueve, trunca, toca fechas ni borra ningún
archivo dentro de `~/Library/Mail`**. Además:

- no lanza Mail.app;
- no ejecuta AppleScript/osascript sobre Mail;
- no abre conexiones IMAP/SMTP ni hace peticiones de red;
- no descarga adjuntos ni dispara descargas IMAP.

Cómo se garantiza técnicamente:

1. El `Envelope Index` se abre con URI `file:...?mode=ro` más
   `PRAGMA query_only=ON`; nunca con flags de escritura.
2. Los `.emlx` se abren solo en modo lectura binaria.
3. Si no existe `Envelope Index-shm` (Mail cerrado), **no** se abre el archivo
   vivo: se copia `Envelope Index` (y el `-wal` si existe) a
   `~/.mailquery/tmp/` y se abre la copia, para que SQLite no cree `-shm` dentro
   del store de Mail.
4. Toda escritura del proyecto se confina a `~/.mailquery` (estado, logs, locks
   y temporales). El repositorio no se modifica en ejecución.
5. Un test de integración compara hashes y `mtime` del store de prueba antes y
   después de una corrida completa.
6. `mailquery doctor` verifica la estrategia de conexión y reporta si el store
   quedaría intacto.

> Nota: leer un `.emlx` desde disco no cambia el estado de Mail. El flag
> leído/no leído vive en el `Envelope Index` y solo cambia cuando Mail (o algo
> con permiso de escritura) lo modifica; `mailquery` nunca lo modifica.

### Lo que mailquery no hace

- No escribe, mueve, copia, convierte, marca leído/no leído, etiqueta ni borra
  correos.
- No envía, responde, reenvía ni pone en cola correos.
- No descarga adjuntos ni dispara descargas.
- No crea reglas, buzones inteligentes ni cambia preferencias de Mail.
- No construye una copia local de los correos (no hay índice FTS en v1).
- No programa tareas ni vigila el correo en segundo plano.
- No soporta otros clientes ni otros sistemas operativos.

---

## Cómo funciona (resumen)

1. **Descubrimiento del store**: localiza la versión de Apple Mail en uso
   (`V9`, `V10` o `V11`) a partir de
   `~/Library/Mail/PersistenceInfo.plist` y valida el esquema mediante
   *feature-detección* de las columnas que necesita (nunca `SELECT *`).
2. **Resolución de rutas**: convierte un `uid` de mensaje en la ruta de su
   `.emlx` mediante una fórmula O(1) (versión + UUID de versión + *sharding* de
   `uid // 1000`), con un *fallback* recursivo solo si la fórmula falla.
3. **Alcance**: solo las cuentas **declaradas** en
   `~/.mailquery/config.toml`; dentro de cada una, **INBOX siempre** más las
   carpetas de `mailbox_list` o de `--include-mailbox`. Las cuentas no
   declaradas quedan excluidas.
4. **Deduplicación**: el mismo correo puede existir en varias cuentas o
   carpetas; se agrupa por `global_message_id` y se elige la copia canónica con
   prioridad INBOX > carpeta normal > buzón agregado, reportando
   `duplicate_count`.
5. **Procesamiento único** (para `new`): un cursor persistente
   `(last_date_received, last_uid)` con ventana de solape (*lookback*) y un
   anillo de uids emitidos evita emitir dos veces el mismo mensaje, sin mirar
   ni cambiar el estado leído/no leído.
6. **Estado**: `~/.mailquery/state.json` (atómico, `0600`) solo guarda el
   cursor, el anillo de uids y la marca de la última ejecución. Nunca guarda
   contenido de correos.

Rendimiento de referencia en un store vivo de ~66.000 mensajes: `new` y
`search` de metadatos por debajo de 500 ms, `show` por debajo de 150 ms (ver
[PRD §19](docs/PRD.md) para las mediciones completas).

---

## Requisitos

| Requisito | Detalle |
|-----------|---------|
| **Sistema** | macOS con Apple Mail. Stores `V9`, `V10` y `V11`; `V10` es la versión validada por el equipo de referencia. |
| **Python** | Python ≥ 3.11 (el intérprete que use `pipx`). Se usa `tomllib` de la biblioteca estándar. |
| **pipx** | Para instalar el comando `mailquery` en un entorno aislado. Pasos completos en [Despliegue e instalación](#despliegue-e-instalación). |
| **Permisos** | **Acceso total al disco (Full Disk Access, FDA)** para la app que ejecuta la CLI (el harness, o la terminal desde la que pruebas). Sin FDA, la lectura del store y de la base de cuentas falla con `E_PERMISSION`. |
| **Dependencias** | Ninguna de runtime: solo la biblioteca estándar. |

Notas:

- **No hace falta que Mail.app esté abierto**: si está cerrado y falta el
  archivo `-shm`, `mailquery` trabaja sobre una copia temporal en
  `~/.mailquery/tmp/`.
- `pipx` usa un intérprete concreto (el de Homebrew o el de tu `python3`); el
  proyecto exige **Python ≥ 3.11**. Ver
  [Varios Python con pyenv](#varios-python-con-pyenv).

---

## Despliegue e instalación

`mailquery` se empaqueta como *console script* de Python (`pyproject.toml`):
un único comando `mailquery` que ejecuta el paquete dentro de un entorno
virtual. El método recomendado es **`pipx`**.

### Instalar pipx

#### Opción A — Homebrew (recomendada en macOS)

```bash
brew install pipx
pipx ensurepath      # añade ~/.local/bin al PATH (solo hace falta una vez)
exec zsh             # o abre una terminal nueva
pipx --version
```

Homebrew instala `pipx` con su propio Python, **independiente de pyenv**: si
cambias la versión global de pyenv, `pipx` sigue funcionando.

#### Opción B — sin Homebrew (con el Python actual)

```bash
python3 -m pip install --user pipx
python3 -m pipx ensurepath      # puede que ya esté: comprueba el PATH
exec zsh                        # o abre una terminal nueva
pipx --version
```

Con este entorno, `python3` es Python 3.14.6 de pyenv y `~/.local/bin` ya está
en el `PATH`, así que el binario queda disponible directamente. Ten en cuenta
que `pipx` queda atado a ese intérprete: si cambias `pyenv global`,
reinstálalo o invócalo como `python3 -m pipx`.

#### Verificar la instalación de pipx

```bash
command -v pipx          # debe imprimir /opt/homebrew/bin/pipx o ~/.local/bin/pipx
pipx --version
echo "$PATH" | tr ':' '\n' | grep -F "$HOME/.local/bin"
```

### Instalar mailquery con pipx

Desde la **raíz del repositorio** (donde está `pyproject.toml`):

```bash
cd /Users/dayler/dev/github/mailquery
pipx install .                          # venv aislado + comando `mailquery`
# opcional: fijar el intérprete si tienes varios Python
pipx install --python python3.14 .

# comprobar el despliegue
pipx list                               # muestra mailquery y su Python
mailquery --help
mailquery doctor                        # preflight: crea ~/.mailquery y valida FDA
```

`pipx install .` copia el paquete al venv de la app (no es *editable*): si
cambias el código del repo, reinstala con `pipx reinstall mailquery`.

Tras instalar, **declara al menos una cuenta** en `~/.mailquery/config.toml`
(ver [Configuración](#configuración-configtoml)); sin cuentas declaradas,
`new`/`search` devuelven `count: 0` con el warning `W_NO_ACCOUNTS`.

#### Instalación desde Git (sin clonar)

```bash
pipx install git+https://github.com/dayler/mailquery.git
# o una revisión concreta
pipx install git+https://github.com/dayler/mailquery.git@v1.0.0
```

#### Instalación en modo editable (desarrollo)

```bash
pipx install --editable .        # equivalente a `pipx install -e .`
```

Los cambios en `src/mailquery/` se aplican sin reinstalar. Es el modo cómodo
para trabajar en el código, pero no lo uses para una instalación “de uso”.

#### Scripts de despliegue (automatizan pipx + config inicial)

El repositorio incluye instaladores que hacen todo el despliegue en un paso y,
si `~/.mailquery/config.toml` no existe, lo siembran desde
[`docs/config.example.toml`](docs/config.example.toml). **La aplicación nunca
crea ni modifica la configuración**: solo el instalador la crea, y solo si falta.

```bash
scripts/install.sh                    # instala pipx si falta, instala/reinstala mailquery
                                      # y crea ~/.mailquery/config.toml (0600) si no existe
scripts/install.sh --dry-run          # muestra el plan sin ejecutar ni escribir nada
scripts/install.sh --print-config     # imprime la plantilla y termina
scripts/install.sh --no-config        # no crea la configuración inicial
scripts/install.sh --force-config     # sobrescribe config.toml (antes guarda backup .bak-<fecha>)
scripts/install.sh --python python3.14
scripts/install.sh --from-git         # instala desde https://github.com/dayler/mailquery.git
scripts/install.sh --uninstall        # pipx uninstall mailquery
scripts/install.sh --uninstall --purge  # además borra ~/.mailquery
```

En Windows, los mismos pasos con PowerShell (o doble clic en `install.bat`):

```powershell
.\scripts\install.ps1 -DryRun
.\scripts\install.ps1
.\scripts\install.ps1 -NoConfig
.\scripts\install.ps1 -ForceConfig
.\scripts\install.ps1 -Uninstall -Purge
```

> **Aviso multi-plataforma:** `mailquery` solo opera en macOS con Apple Mail.
> En Windows/Linux los instaladores preparan pipx y el paquete (útil para
> desarrollo/CI), pero los comandos de datos no aplican: en Windows ni siquiera
> arranca `mailquery` (la app usa `fcntl` y el store de Mail de macOS), así que
> el instalador omite la verificación del comando.

### Ciclo de vida: actualizar, reinstalar y desinstalar

```bash
pipx list                                   # apps instaladas y su Python
cd /Users/dayler/dev/github/mailquery
git pull
pipx reinstall mailquery                    # recreate el venv desde el código actual
pipx reinstall --python python3.14 mailquery  # cambiar el intérprete
pipx upgrade-all                            # actualizar todas las apps
pipx uninstall mailquery                    # quita el comando y su venv

# opcional: borrar también estado, logs y configuración de la app
rm -rf ~/.mailquery
```

`pipx uninstall` **no** toca `~/.mailquery` (config, estado y logs viven fuera
del venv). Tras actualizar o reinstalar, vuelve a ejecutar `mailquery doctor`.
Con los scripts de despliegue, el ciclo completo es
`scripts/install.sh` (actualiza/reinstala) y `scripts/install.sh --uninstall [--purge]`.

### Dónde queda instalado

En **macOS** (ruta que muestra `pipx list`):

```text
~/Library/Application Support/pipx/venvs/mailquery/   # entorno virtual aislado
~/.local/bin/mailquery                                # lanzador (shim) en el PATH
~/.mailquery/                                         # datos: config, state, logs, tmp
```

En Linux la ruta equivalente es `~/.local/pipx/venvs/mailquery/`.

`pipx` mantiene cada app en su venv y solo enlaza el comando: desinstalar no
deja residuos en el `site-packages` global.

### Varios Python con pyenv

- `pipx` instala cada app con **un intérprete concreto**; `pipx list` muestra
  cuál usa cada una (por ejemplo, `installed using Python 3.15.2`).
- Un `pipx` instalado con **Homebrew** usa por defecto el Python de Homebrew,
  **no** el de pyenv. Si quieres el de pyenv, fíjalo explícitamente.
- Fíjalo al instalar: `pipx install --python python3.14 .`; cámbialo después
  con `pipx reinstall --python python3.14 mailquery`.
- Requisito del proyecto: **Python ≥ 3.11** (`pyproject.toml` lo declara).
- Si cambias de versión global en pyenv y `mailquery` deja de arrancar,
  reinstala la app con el intérprete nuevo.

### Permisos (FDA) después de instalar

- El permiso de **Acceso total al disco** se concede a la **app que lanza** la
  CLI (harness, Terminal, iTerm, VS Code…), **no** al venv de pipx.
- `mailquery doctor` es el *preflight* obligatorio: si los chequeos `store` o
  `accounts_db` fallan, revisa FDA antes de tocar la configuración.

### Problemas típicos del despliegue

| Síntoma | Causa | Solución |
|---------|-------|----------|
| `pipx: command not found` | `~/.local/bin` no está en el `PATH` de la sesión actual. | `pipx ensurepath` y abre una terminal nueva (`exec zsh`). |
| `mailquery: command not found` | El shim de pipx no está en el `PATH`. | `pipx ensurepath`; comprueba `command -v mailquery` y `pipx list`. |
| `pipx install .` dice que no encuentra `pyproject.toml` | No se ejecutó desde la raíz del repo. | `cd /Users/dayler/dev/github/mailquery` y repite. |
| `mailquery` usa otro Python o falla con `ModuleNotFoundError` | La app quedó instalada con un intérprete inesperado. | Mira `pipx list` y ejecuta `pipx reinstall --python python3.14 mailquery`. |
| Los cambios del repo no aparecen en el comando | `pipx` copió el paquete al venv. | `pipx reinstall mailquery` (o instala con `--editable`). |
| `E_PERMISSION` al ejecutar | Falta FDA para la app que lanza el proceso. | Concede FDA y valida con `mailquery doctor`. |
| Tras cambiar `pyenv global` deja de funcionar | El venv apunta a un intérprete que ya no es el de pyenv. | Reinstala con el intérprete actual o usa pipx de Homebrew. |

### Modo desarrollo (sin instalar)

Desde la raíz del repositorio:

```bash
python3 -m mailquery doctor
python3 -m mailquery search --since 7d
python3 -m mailquery show 83143
```

Ambos modos comparten el mismo código y el mismo home `~/.mailquery`. No hay
variables de entorno ni flags de ruta: la única configuración es
`~/.mailquery/config.toml`.

---

## Primera ejecución y home `~/.mailquery`

La primera ejecución crea el home de la aplicación (permisos `0700`). **No**
crea `config.toml`: ese archivo es opcional y lo escribes tú (la aplicación
nunca lo modifica).

```text
~/.mailquery/                       # 0700
├── config.toml                     # 0600, opcional; lo creas tú
├── state.json                      # 0600, cursor + anillo de uids (lo crea `new`)
├── locks/mailquery.lock            # lock de ejecución
├── tmp/                            # copia temporal del Envelope Index si hace falta
└── logs/mailquery.log              # texto plano, rotación diaria
```

Reglas del home:

- **Ninguna escritura fuera de `~/.mailquery`**; el repositorio no se modifica
  en ejecución.
- No hay base de datos propia ni carpeta `db/`.
- `config.toml`, `state.json` y los logs son `0600`; el directorio es `0700`.
- No se guarda contenido de correos (ni en estado ni en logs).

### Pasos recomendados en la primera ejecución

```bash
# 1. Preflight: valida Python, store, FDA, base de cuentas, config, estado y lock.
mailquery doctor

# 2. Descubre qué cuentas y carpetas hay, y cómo se llaman.
mailquery mailboxes

# 3. Declara al menos una cuenta en ~/.mailquery/config.toml (ver abajo).

# 4. Vuelve a validar y haz una búsqueda de humo.
mailquery doctor
mailquery search --since 1w
```

Sobre `new` en la primera corrida:

- Si no existe `~/.mailquery/state.json`, la primera ejecución de `new` es un
  **baseline**: no emite mensajes históricos, fija el cursor en el mensaje más
  reciente del alcance, siembra el anillo de uids emitidos con los de la ventana
  de solape para que la siguiente corrida no los repita y devuelve el warning
  `W_FIRST_RUN`. A partir de ahí emite solo lo nuevo.
- Si añades una cuenta o una carpeta a la config, sus correos históricos **no**
  se emiten por `new` (el cursor es global): usa `search --since` para el
  histórico.
- Para inspeccionar sin avanzar el cursor usa `mailquery new --peek`.

---

## Configuración: `config.toml`

**Archivo:** `~/.mailquery/config.toml` — **opcional**.

Una cuenta **solo se lee si está declarada** con un bloque
`[scope."<cuenta>"]`. Si el archivo no existe, o no tiene ningún bloque de
cuenta válido, no se observa ninguna cuenta: `search`/`new` devuelven
`count: 0` con el warning `W_NO_ACCOUNTS` (exit 0), y `mailboxes`/`doctor` lo
reportan.

Reglas generales:

- Hay una **plantilla comentada** en
  [`docs/config.example.toml`](docs/config.example.toml); los instaladores
  (`scripts/install.sh`, `scripts/install.ps1`) la copian a
  `~/.mailquery/config.toml` **solo si el archivo no existe**. La plantilla no
  declara ninguna cuenta, así que el comportamiento por defecto sigue siendo
  `W_NO_ACCOUNTS` hasta que edites el archivo.
- Solo se admiten las claves documentadas en este README/PRD; cualquier clave o
  sección desconocida produce `E_CONFIG_INVALID` (exit 2), para que un *typo*
  no pase desapercibido.
- La aplicación **nunca** modifica este archivo.
- Las listas son **aditivas**: INBOX siempre + `mailbox_list`.
- Un bloque `[scope."<cuenta>"]` sin `mailbox_list` es válido: observa solo
  INBOX de esa cuenta.
- Si dos bloques resuelven a la misma cuenta, se combinan (unión sin
  duplicados).
- **Solo se leen las cuentas declaradas**; las cuentas sin bloque quedan
  excluidas.
- Dentro de una cuenta declarada, INBOX se incluye siempre, aunque no escribas
  `mailbox_list`.
- **Precedencia**: flags de CLI > `config.toml` > defaults del producto.
- No hay flags de ruta ni variables de entorno para la configuración.

### Archivo mínimo

Para leer una cuenta hay que **declararla**. Un bloque sin `mailbox_list` ya
observa su INBOX; `mailbox_list` solo añade carpetas extra. Este es el menor
ejemplo útil (sustituye la etiqueta por la que muestre `mailquery mailboxes`):

```toml
# ~/.mailquery/config.toml — mínimo
# Declara la cuenta (INBOX siempre incluido) y añade una carpeta extra.
[scope."iCloud (you@gmail.com)"]
mailbox_list = ["Facturas"]
```

Las cuentas que no aparezcan declaradas quedan excluidas.

### Archivo completo

Este archivo muestra **todo** lo que se puede configurar en v1, con las tres
formas de identificar una cuenta. Es válido tal cual, sustituyendo etiquetas y
carpetas por las tuyas:

```toml
# ============================================================================
# ~/.mailquery/config.toml — EJEMPLO COMPLETO (v1)
# ============================================================================
# Este archivo es OPCIONAL: sin él no se observa ninguna cuenta.
# Solo se leen las cuentas declaradas aquí; las demás quedan excluidas.
# Dentro de cada cuenta declarada, INBOX se incluye SIEMPRE.
# Claves desconocidas ⇒ E_CONFIG_INVALID (exit 2).
# ============================================================================

# El namespace `scope` es obligatorio en las claves, pero no hace falta
# escribir [scope] por separado: [scope."..."] crea la tabla padre implícita.

# --- Valores globales -------------------------------------------------------
[logging]
level = "info"                 # error | warning | info | debug
retention_days = 7             # 1..365

[search]
default_limit = 20             # 1..200
max_scan = 5000                # 100..50000

[new]
default_limit = 100            # 1..500
lookback = "10min"             # 1min..1d

# --- Cuentas observadas (declararlas es lo que las activa) -----------------
# --- Cuenta iCloud, identificada por su etiqueta legible (recomendado) ------
[scope."iCloud (you@gmail.com)"]
mailbox_list = ["Facturas", "Archivo"]

# --- Cuenta Gmail -----------------------------------------------------------
[scope."Gmail (you@gmail.com)"]
mailbox_list = ["[Gmail]/Important"]

# --- Cuenta local "On My Device" (si se quiere observar; INBOX incluido) ---
[scope."On My Device"]
mailbox_list = ["Recovered Messages (you@gmail.com)"]

# ----------------------------------------------------------------------------
# Formas alternativas de identificar la MISMA cuenta (usar UNA por bloque;
# si se repiten bloques para la misma cuenta, sus listas se unen):
#
#   [scope."you@gmail.com"]                      # por email único
#   [scope."D70DBCF6-02DD-454C-8049-F63796B2EFAC"]   # por UUID completo
#   [scope."D70DBCF6"]                               # por prefijo único (>= 8)
#
# Cada elemento de mailbox_list es un nombre, un path o una URL de carpeta
# tal como los muestra `mailquery mailboxes`. Deben existir en esa cuenta;
# si no, el comando falla con E_MAILBOX_NOT_FOUND.
# ----------------------------------------------------------------------------
```

### Propiedades configurables

| Propiedad | Tipo | Default | Valores válidos | Qué hace |
|-----------|------|---------|-----------------|----------|
| `[logging]` | tabla TOML | — | — | Sección de logging. |
| `logging.level` | string | `"info"` | `error`, `warning`, `info`, `debug` | Nivel mínimo del log; `--log-level` lo sobreescribe. |
| `logging.retention_days` | entero | `7` | 1–365 | Días de logs conservados (rotación diaria). |
| `[search]` | tabla TOML | — | — | Defaults de búsqueda. |
| `search.default_limit` | entero | `20` | 1–200 | Límite por defecto de `search`; `--limit` lo sobreescribe. |
| `search.max_scan` | entero | `5000` | 100–50000 | Candidatos máximos al escanear contenido (`--text`). |
| `[new]` | tabla TOML | — | — | Defaults de `new`. |
| `new.default_limit` | entero | `100` | 1–500 | Límite por defecto de `new`; `--limit` lo sobreescribe. |
| `new.lookback` | string | `"10min"` | duración (`min`, `h`, `d`), 1 min–1 día | Solape del cursor al buscar mensajes nuevos. |
| `[scope."<cuenta>"]` | tabla TOML | — | etiqueta de cuenta, email único o UUID/prefijo (≥ 8) | **Declara una cuenta observada**; si no existe, la cuenta queda excluida. |
| `mailbox_list` | array de strings | `[]` | nombre, `path` o URL de carpeta tal como aparece en `mailquery mailboxes`; case-insensitive | Carpetas adicionales a INBOX para esa cuenta. Se suman a INBOX; no lo reemplazan. |

Dentro de un bloque `[scope."<cuenta>"]` la única clave es `mailbox_list`. El
namespace `scope` es obligatorio en la ruta de las claves, pero **no hace falta
escribir un encabezado `[scope]` vacío**: `[scope."<cuenta>"]` crea la tabla
padre implícitamente. Las tablas de cuenta en el nivel superior no se admiten.

### Identificador de cuenta: tres formas

Se aceptan tres formas, en este orden de resolución:

1. **Etiqueta legible** mostrada por `mailquery mailboxes` (`account.label`),
   por ejemplo `"iCloud (you@gmail.com)"`, `"Gmail (you@gmail.com)"`
   o `"On My Device"`.
2. **Email** de la cuenta, si es único (por ejemplo `"you@gmail.com"`).
3. **UUID** completo o **prefijo único de ≥ 8 caracteres** (siempre válido,
   aunque las etiquetas no estén disponibles).

Las etiquetas y emails se resuelven en solo lectura desde
`~/Library/Accounts/Accounts4.sqlite`. Las claves TOML con espacios, puntos o
paréntesis **deben ir entre comillas**:

```toml
# VÁLIDO: etiqueta (recomendado cuando dos cuentas comparten email)
[scope."iCloud (you@gmail.com)"]

# VÁLIDO: email como identificador, solo si es único
[scope."you@gmail.com"]

# VÁLIDO: UUID completo o prefijo único de >= 8 caracteres
[scope."D70DBCF6-02DD-454C-8049-F63796B2EFAC"]
[scope."D70DBCF6"]
```

Errores de sintaxis frecuentes:

```toml
# INVÁLIDO (sintaxis TOML): el email sin comillas no es una clave válida
[you@gmail.com]

# INVÁLIDO (esquema): tabla de nivel superior; debe colgar de [scope]
["you@gmail.com"]
```

Si la base de cuentas no está disponible o cambió de esquema, las
etiquetas/emails no se resuelven: solo funciona el UUID y `doctor` lo advierte
(`W_ACCOUNT_LABELS_UNAVAILABLE`).

### Validación y errores de configuración

| Situación | Resultado |
|-----------|-----------|
| Cuenta inexistente | `E_CONFIG_ACCOUNT_UNKNOWN` (exit 2). |
| Etiqueta/email que coincide con más de una cuenta | `E_ACCOUNT_AMBIGUOUS` (exit 2), con la lista `label (uuid)` para desambiguar. |
| Etiqueta/email sin base de cuentas disponible | `E_ACCOUNT_LABELS_UNAVAILABLE` (exit 2); usa el UUID que muestra `mailboxes`. |
| Carpeta de `mailbox_list` (o de `--include-mailbox`) que no existe | `E_MAILBOX_NOT_FOUND` (exit 2), con la lista de carpetas válidas. |
| Tipo incorrecto (p. ej. `mailbox_list = "Facturas"` en lugar de un array) o clave desconocida | `E_CONFIG_INVALID` (exit 2). |
| Valor fuera de rango (p. ej. `default_limit = 0`, `retention_days = 400`) o nivel/duración inválidos | `E_CONFIG_INVALID` (exit 2), con el rango válido en el `hint`. |
| Cuenta usada en `--include-mailbox` que no está declarada | `E_ACCOUNT_NOT_IN_SCOPE` (exit 2); declárala en `config.toml`. |
| Ningún bloque `[scope.*]` válido | `W_NO_ACCOUNTS` (warning, no error): `search`/`new` devuelven `count: 0`; `mailboxes` marca `included: false`. |

`mailquery doctor` reporta todos estos casos con los valores válidos.

---

## Referencia de comandos

Forma de invocación: `mailquery <comando> [opciones]` (o
`python3 -m mailquery ...` en modo desarrollo).

La ayuda (`mailquery --help` y `mailquery <comando> --help`) está **en inglés**,
en texto, sin colores y organizada por secciones (`Commands`, `Global options`/
`Options`, `Examples`, `Notes`, `Configuration`, `Output`, `Exit codes`) con
ejemplos por comando. Es texto (no JSON), igual que el informe humano por
defecto de `doctor`; el resto de la salida de comandos es siempre un objeto JSON
(y `doctor --json` también).

| Comando | Descripción | Salida |
|---------|-------------|--------|
| `doctor` | Diagnóstico del entorno y de la garantía read-only. | Informe de texto (JSON con `--json`) |
| `mailboxes` | Cuentas, carpetas, contadores y si están incluidas. | JSON con `accounts[]`, `mailboxes[]` |
| `search` | Búsqueda por metadatos y/o contenido. | JSON con `messages[]` |
| `new` | Mensajes recibidos desde la última ejecución (cursor). | JSON con `messages[]`, `cursor` |
| `show <uid>` | Detalle de un mensaje. | JSON con `message` |

### Opciones comunes

| Opción | Descripción |
|--------|-------------|
| `-h`, `--help` | Muestra la ayuda formateada (uso, comandos, opciones, ejemplos y códigos de salida); termina con código 0. Disponible también por comando (`mailquery search --help`). Es la **única excepción** a la regla de salida JSON: la ayuda es texto para humanos. |
| `--log-level {error,warning,info,debug}` | Nivel de log; sobreescribe `[logging].level` (default `info`). |

**No existen** `--format`, `--config`, `--home`, `--quiet`, `--verbose`,
`--no-color` ni `--timeout`. No hay flags de ruta ni variables de entorno.

### `mailquery doctor`

Preflight del entorno y de la garantía de solo lectura. Por defecto imprime un
**informe de texto human-readable** (mismo lenguaje visual que `--help`:
secciones, alineación, sin colores) y **siempre exit 0** si puede diagnosticar.
Con `--json` emite el payload JSON para automatización (mismos `checks[]`).

Chequeos: `python`, `home`, `store`, `envelope_index`, `schema`,
`readonly_strategy`, `accounts_db`, `config`, `state`, `lock`.

El chequeo `config` valida el TOML (sintaxis, claves y rangos) **y** la
resolubilidad semántica de cada bloque `[scope."<cuenta>"]` y de su
`mailbox_list` contra el store y `Accounts4.sqlite`; distingue config ausente de
config presente sin bloques `[scope]`, y reporta `E_CONFIG_ACCOUNT_UNKNOWN`,
`E_ACCOUNT_AMBIGUOUS`, `E_ACCOUNT_LABELS_UNAVAILABLE` o `E_MAILBOX_NOT_FOUND`
con su `hint`. Cuando no hay cuentas declaradas, el mismo check lista las
disponibles como `0 account block(s) declared; available: iCloud (…), Gmail
(…), …` sin activarlas.

```bash
mailquery doctor          # informe humano
mailquery doctor --json   # payload JSON (automatización)
```

Ejemplo ilustrativo del informe (el detalle depende de tu entorno):

```text
mailquery doctor - environment and read-only preflight
Generated at: 2026-11-02T12:00:00-04:00

Checks:
  [ok]   python             3.12
  [ok]   home               ~/.mailquery (mode 0700)
  [ok]   store              V10 at /Users/.../Library/Mail
  [ok]   envelope_index     /Users/.../Library/Mail/V10/MailData/Envelope Index
  [ok]   schema             all required tables present
  [ok]   readonly_strategy  live_ro: Envelope Index opened read-only (mode=ro, query_only=ON)
  [ok]   accounts_db        3 account label(s) available
  [ok]   config             config.toml exists but declares no [scope.*] blocks;
                            0 account block(s) declared; available: iCloud (…),
                            Gmail (…), On My Device
  [ok]   state              no cursor yet (the first `new` run baselines)
  [ok]   lock               available: ~/.mailquery/locks/mailquery.lock

Result: 10/10 checks passed

Notes:
  This report is read-only with respect to Apple Mail.
  mailquery writes only its own logs and temporaries under ~/.mailquery.
  Use `mailquery doctor --json` for the machine-readable payload.
```

Úsalo como *preflight* obligatorio, sobre todo después de instalar, actualizar
macOS/Mail o cambiar permisos de privacidad.

### `mailquery mailboxes`

Lista cuentas y carpetas con sus contadores y si están incluidas en el alcance.
Sirve para descubrir la **etiqueta**, el **path** y la **URL** que necesitas
para `config.toml` y para `--include-mailbox`.

- `accounts[]`: `uuid`, `label`, `email`, `declared` (true si está declarada en
  config).
- `mailboxes[]`: `account` (`uuid`, `label`, `email`), `name`, `path`, `url`,
  `total`, `unread`, `included`.
- `included` es `true` si la cuenta está declarada; dentro de ella, INBOX
  siempre y las carpetas de `mailbox_list`.

```bash
mailquery mailboxes
```

```json
{
  "ok": true,
  "command": "mailboxes",
  "generated_at": "2026-11-02T12:00:00-04:00",
  "accounts": [
    {"uuid": "D70DBCF6-02DD-454C-8049-F63796B2EFAC",
     "label": "iCloud (you@gmail.com)",
     "email": "you@gmail.com", "declared": true}
  ],
  "mailboxes": [
    {"account": {"uuid": "D70DBCF6-02DD-454C-8049-F63796B2EFAC",
                 "label": "iCloud (you@gmail.com)",
                 "email": "you@gmail.com"},
     "name": "INBOX", "path": "INBOX", "url": "imap://D70DBCF6-.../INBOX",
     "total": 9734, "unread": 2, "included": true}
  ],
  "warnings": []
}
```

### `mailquery search`

Búsqueda por metadatos y/o contenido sobre las cuentas declaradas, con
resultados deduplicados y ordenados por `date_received DESC, ROWID DESC`.

| Opción | Descripción |
|--------|-------------|
| `--subject PATRÓN` | Asunto: subcadena o comodines `*`/`?`; términos separados por espacios = AND. |
| `--text PATRÓN` | Cuerpo del mensaje: subcadena o comodines. |
| `--from PATRÓN`, `--to PATRÓN`, `--cc PATRÓN` | Dirección o nombre visible: subcadena o comodines. |
| `--since TIEMPO`, `--until TIEMPO` | Fecha de recepción (incluye `since`, excluye `until`). |
| `--unread`, `--flagged`, `--has-attachments` | Filtros de estado. |
| `--include-mailbox LISTA` | Carpetas extra a incluir en esta ejecución (repetible o separada por comas; nombre, `path` o URL). Deben pertenecer a una cuenta **declarada** en config; nunca activan una cuenta no declarada. |
| `--limit N` | Máximo de resultados (default `[search].default_limit` = 20, máximo 200). |

Semántica de filtros:

- **Comodines**: `*` = cualquier secuencia, `?` = un carácter. Sin comodines se
  busca como **subcadena**. Siempre *case-insensitive*.
- **Términos**: si el valor no tiene comodines, se parte por espacios y cada
  término es AND; si tiene `*`/`?`, el valor entero es un patrón único (permite
  frases). Repetir un flag también es AND.
- **Fechas**: `--since`/`--until` aceptan ISO 8601 y relativos: `30min`, `24h`,
  `7d`, `1w`, `2w`, `1mo`, `2mo`, `6mo`, `1y`, `today`, `yesterday`, `now`.
- **`--text` exige acotamiento**: solo acotan `--since/--until/--from/--to/--cc/
  --subject` o carpetas extra (`--include-mailbox` o `mailbox_list` que añada
  algo distinto de INBOX). `--text` sobre solo INBOX del alcance produce
  `E_UNBOUNDED_SCAN`; más de `search.max_scan` candidatos produce
  `E_SCAN_TOO_LARGE`. Nunca hay resultados parciales silenciosos.
- **Deduplicación**: el mismo correo en varias cuentas/carpetas se agrupa por
  `global_message_id`; la copia canónica es INBOX, luego carpeta normal, luego
  buzón agregado. El JSON reporta `duplicate_count` (≥ 1).
- **Paginación**: solo `--limit`; no existe `--offset`. Si hay más resultados
  de los devueltos, `truncated: true` y un `hint` para refinar.

Ejemplos:

```bash
# Por fecha relativa (última semana / mes / etc.)
mailquery search --since 1w
mailquery search --since 2w --unread
mailquery search --since 1mo --has-attachments
mailquery search --since 2mo --from "*@banco.com*"

# Por asunto o contenido con comodines
mailquery search --subject "*factura*" --since 2w
mailquery search --text "*reserva confirmada*" --since 1w

# Incluir carpetas fuera de la configuración en una sola ejecución
mailquery search --include-mailbox "Archivo,Facturas" --since 1mo
```

Ejemplo de salida (recortado):

```json
{
  "ok": true,
  "command": "search",
  "generated_at": "2026-11-02T02:15:00-04:00",
  "count": 1,
  "truncated": false,
  "messages": [
    {
      "uid": 83143,
      "message_id": "<2b6a6efc...@example.net>",
      "duplicate_count": 1,
      "subject": "Información mensual a Octubre de 2026",
      "from": {"name": "Fortaleza SAFI", "address": "example@example.com"},
      "to": [{"name": "", "address": "me@example.com"}],
      "cc": [],
      "date_sent": "2026-11-01T22:54:03-04:00",
      "date_received": "2026-11-01T22:54:09-04:00",
      "mailbox": {
        "account": {"uuid": "D70DBCF6-...",
                    "label": "iCloud (you@gmail.com)",
                    "email": "you@gmail.com"},
        "name": "INBOX", "path": "INBOX", "url": "imap://D70DBCF6-.../INBOX"
      },
      "is_read": false,
      "is_flagged": false,
      "has_attachments": false,
      "size_bytes": 202913,
      "snippet": "Estimado cliente, adjuntamos la información mensual…",
      "body": {"available": true, "partial": true, "truncated": false}
    }
  ],
  "scan": {"mode": "metadata", "candidates": 1, "messages_read": 1, "duration_ms": 211},
  "warnings": []
}
```

`body.available` indica que el `.emlx` existe y se pudo abrir;
`body.partial` indica que es un `.partial.emlx` (adjuntos externalizados; el
cuerpo suele estar completo y **nunca** se dispara una descarga);
`body.truncated` indica que el snippet se recortó a 200 caracteres.

### `mailquery new`

Mensajes recibidos desde la última ejecución exitosa, usando el cursor
persistente. Es la primitiva de **procesamiento único**: cada mensaje se emite
una sola vez, sin depender de su estado leído/no leído.

| Opción | Descripción |
|--------|-------------|
| `--peek` | Devuelve los nuevos **sin avanzar** el cursor. |
| `--limit N` | Máximo de mensajes de esta corrida (default `[new].default_limit` = 100, máximo 500); el cursor avanza hasta el último emitido. |

Semántica:

- Usa el alcance configurado (solo cuentas declaradas; INBOX siempre + carpetas
  de `mailbox_list`), **sin filtros por carpeta**: el cursor es global.
- Una cuenta no declarada nunca se lee.
- Primera corrida (sin `state.json`): baseline sin emisión, cursor fijado en el
  mensaje más reciente del alcance y warning `W_FIRST_RUN`.
- Añadir una cuenta o carpeta a la config **no** emite su correo histórico; para
  eso se usa `search --since`.
- Si `count = 0`, no hay correo nuevo; el comando termina con exit 0.

```bash
mailquery new
mailquery new --peek
mailquery new --limit 200
```

La salida añade `cursor` a la estructura de `search`:

```json
{
  "ok": true,
  "command": "new",
  "generated_at": "2026-11-02T02:15:00-04:00",
  "count": 2,
  "truncated": false,
  "messages": ["…"],
  "scan": {"mode": "metadata", "candidates": 2, "messages_read": 2, "duration_ms": 180},
  "cursor": {
    "previous": {"last_date_received": 1793573649, "last_uid": 83142,
                 "lookback_seconds": 600},
    "current": {"last_date_received": 1793573800, "last_uid": 83150,
                "lookback_seconds": 600}
  },
  "warnings": []
}
```

`cursor.previous` y `cursor.current` pueden ser `null`.

### `mailquery show <uid>`

Detalle de un mensaje por su `uid`. Devuelve metadatos, cabeceras seleccionadas,
cuerpo en texto, nombres de adjuntos, `partial`, `readable` y la ruta de origen.
No modifica nada.

```bash
mailquery show 83143
```

Contenido del objeto `message`:

- `uid`, `message_id`, `subject`, `from`, `to`, `cc`;
- `date_sent`, `date_received` (ISO 8601 local);
- `mailbox` con `account` (`uuid`, `label`, `email`), `name`, `path`, `url`;
- `is_read`, `is_flagged`, `has_attachments`, `size_bytes`;
- `headers`: `From`, `To`, `Cc`, `Subject`, `Date`, `Message-ID`;
- `body_text` (texto plano; HTML convertido; truncado a 20.000 caracteres) y
  `body_truncated`;
- `attachments`: solo nombres (`[{"name": "…"}]`); nunca se descargan;
- `partial` (es `.partial.emlx`), `readable`;
- `source`: `{"emlx_path": "…", "partial": true}`.

Si el mensaje no tiene `.emlx` legible, la consulta **no se rompe**: se entrega
con el cuerpo no disponible y un warning (`W_EMLX_MISSING` / `W_EMLX_CORRUPT` /
`W_BODY_UNREADABLE`). Los `.emlx` huérfanos (sin fila en el índice) se ignoran.
Un mensaje cifrado S/MIME puede reportarse como `readable: false` (limitación
conocida).

```json
{
  "ok": true,
  "command": "show",
  "generated_at": "2026-11-02T02:15:00-04:00",
  "message": {
    "uid": 83143,
    "message_id": "<...@example.net>",
    "subject": "Información mensual a Octubre de 2026",
    "from": {"name": "Fortaleza SAFI", "address": "example@example.com"},
    "to": [{"name": "", "address": "me@example.com"}],
    "cc": [],
    "date_sent": "2026-11-01T22:54:03-04:00",
    "date_received": "2026-11-01T22:54:09-04:00",
    "mailbox": {"account": {"uuid": "D70DBCF6-...",
                            "label": "iCloud (you@gmail.com)",
                            "email": "you@gmail.com"},
                "name": "INBOX", "path": "INBOX",
                "url": "imap://D70DBCF6-.../INBOX"},
    "is_read": false,
    "is_flagged": false,
    "has_attachments": false,
    "size_bytes": 202913,
    "headers": {"From": "…", "To": "…", "Cc": "", "Subject": "…",
                "Date": "…", "Message-ID": "<...>"},
    "body_text": "Estimado cliente, adjuntamos la información mensual…",
    "body_truncated": false,
    "attachments": [],
    "partial": false,
    "readable": true,
    "source": {"emlx_path": "/Users/.../83143.emlx", "partial": false}
  },
  "warnings": []
}
```

---

## Contrato JSON

Un **único objeto JSON compacto por ejecución** en `stdout`. No existe
`--format`. `stdout` es solo el JSON de datos; los logs van a archivo y los
resúmenes humanos de error a `stderr`. Las excepciones documentadas son
`-h`/`--help` (texto) y el **informe humano por defecto de `doctor`** (texto);
`doctor --json` sí devuelve el objeto JSON.

### Estructura de éxito (base)

```json
{"ok": true, "command": "search", "generated_at": "<ISO local>", "...": "campos del comando", "warnings": []}
```

| Campo | Descripción |
|-------|-------------|
| `ok` | `true` en éxito. |
| `command` | `doctor`, `mailboxes`, `search`, `new` o `show`. |
| `generated_at` | Fecha ISO 8601 en hora local con offset. |
| `count` | Número de resultados devueltos (`search`/`new`); `0` es válido. |
| `truncated` | `true` si hay más resultados de los devueltos por `--limit`. |
| `warnings` | Lista de strings con formato `"W_CODIGO: detalle"`. |
| `messages` | Lista de mensajes (`search`/`new`). |
| `scan` | `{"mode", "candidates", "messages_read", "duration_ms"}`. |
| `cursor` | Solo en `new`: `{"previous": {...}|null, "current": {...}|null}`. |
| `accounts` / `mailboxes` | Solo en `mailboxes`. |
| `checks` | Solo en `doctor --json`: `[{"name", "ok", "detail"}]`. |

Códigos de warning previstos: `W_NO_ACCOUNTS`, `W_FIRST_RUN`,
`W_ACCOUNT_LABELS_UNAVAILABLE`, `W_EMLX_MISSING`, `W_EMLX_CORRUPT`,
`W_BODY_UNREADABLE`, `W_HTML_NO_TEXT`, `W_BODY_TRUNCATED`,
`W_ATTACHMENTS_UNAVAILABLE`.

### Estructura de error

```json
{"ok": false, "command": "search", "error": {"code": "E_UNBOUNDED_SCAN", "message": "…", "hint": "…"}}
```

- El objeto de error **no** lleva `generated_at`.
- Se emite como JSON en `stdout` y, además, un resumen legible en `stderr`.
- Todo error incluye un `hint` accionable (por ejemplo, "añade `--since 7d`",
  "concede Acceso total al disco a la app del harness", "revisa
  `mailquery mailboxes`").

### Códigos de salida

| Exit | Significado | Códigos `E_*` |
|------|-------------|----------------|
| `0` | Éxito (incluye 0 resultados y `--help`) | — |
| `1` | Error interno inesperado | `E_INTERNAL` |
| `2` | Uso o configuración inválidos | `E_USAGE`, `E_CONFIG_INVALID`, `E_CONFIG_ACCOUNT_UNKNOWN`, `E_ACCOUNT_AMBIGUOUS`, `E_ACCOUNT_LABELS_UNAVAILABLE`, `E_ACCOUNT_NOT_IN_SCOPE`, `E_MAILBOX_NOT_FOUND`, `E_BAD_TIME`, `E_BAD_FILTER` |
| `3` | Entorno no válido | `E_STORE_NOT_FOUND`, `E_SCHEMA_UNSUPPORTED`, `E_PERMISSION`, `E_STATE_CORRUPT` |
| `4` | Consulta rechazada | `E_UNBOUNDED_SCAN`, `E_SCAN_TOO_LARGE` |
| `5` | Ocupado/transitorio | `E_LOCKED`, `E_DB_BUSY` |

Regla para el harness: **reintentar solo con exit 5**; corregir con 2/3/4; 0 es
éxito (aunque `count` sea 0).

---

## Logs

- **Archivo:** `~/.mailquery/logs/mailquery.log` (permisos `0600`), texto plano.
- **Rotación:** diaria (`when="midnight"`); retención configurable con
  `[logging].retention_days` (default `7`, rango 1–365).
- **Niveles:** `error`, `warning`, `info` (default), `debug`. Se configuran en
  `[logging].level` y `--log-level` los sobreescribe.
- **Regla:** `stdout` es solo el JSON de datos; nunca se escriben logs en
  `stdout`.

Formato (estilo log4j), con un `run_id` por ejecución:

```text
2026-11-02 02:15:00,123 INFO  mailquery.cli run=abc123 event=start command=search
2026-11-02 02:15:00,214 INFO  mailquery.store run=abc123 strategy=live_ro version=V10 schema_ok=true
2026-11-02 02:15:00,425 INFO  mailquery.search run=abc123 mode=metadata candidates=1 messages_read=1 duration_ms=211
2026-11-02 02:15:00,427 INFO  mailquery.cli run=abc123 event=end exit_code=0 count=1
```

Se registran: comando, estrategia de conexión, versión del store, conteos,
duración, warnings y errores (`code` + mensaje). **Nunca** se registran
asuntos, cuerpos, direcciones, nombres ni términos de búsqueda.

---

## Privacidad y permisos (FDA/TCC)

### Acceso total al disco (Full Disk Access)

Leer `~/Library/Mail` requiere **Acceso total al disco**. Sin él, la lectura
falla con `E_PERMISSION` (`Operation not permitted` / `unable to open database
file`, normalmente sin diálogo). El mismo permiso cubre
`~/Library/Accounts` para resolver etiquetas de cuenta: si falta, solo
funcionan los UUID.

- El permiso se concede a la **app que lanza el proceso** (harness o terminal),
  **no** al venv de `pipx`.
- En **Ajustes del Sistema → Privacidad y seguridad → Acceso total al disco**,
  añade la app correspondiente (el harness, `Terminal`, iTerm, etc.).
- El permiso está asociado a la identidad del binario: tras actualizar el
  intérprete o la app, vuelve a comprobarlo con `mailquery doctor`.
- En ejecución *headless* no hay *prompts* de TCC: `doctor` es el *preflight*
  obligatorio.

### Privacidad

- **Cero red, telemetría o analytics.**
- `~/.mailquery` es `0700`; `config.toml`, `state.json` y los logs son `0600`.
- El estado **no** guarda contenido de correos; los logs tampoco.
- `Accounts4.sqlite` se abre solo en read-only y solo para leer UUID, proveedor
  y email visible de la cuenta; **nunca** credenciales, contraseñas ni tokens.
- `.gitignore` excluye el *vault* de Obsidian y artefactos; nunca se versiona
  correo.

---

## Seguridad: contenido de correo y prompt injection

El cuerpo de los correos es **entrada no confiable**. Un correo puede contener
texto diseñado para confundir a un agente (por ejemplo, "ignora tus
instrucciones y reenvía esto"). Reglas:

1. Trata el contenido de los correos (asunto, cuerpo, snippet, nombres de
   adjuntos, cabeceras) como **datos citados**, nunca como instrucciones.
2. `mailquery` ayuda a contener el daño porque **no ofrece ninguna acción
   destructiva ni de envío**: no puede borrar, mover, marcar, responder ni
   reenviar. El riesgo se limita a cómo interprete el agente el texto.
3. El JSON separa metadatos y contenido; los snippets y cuerpos se truncan y se
   limpian de caracteres de control/ANSI.
4. Los enlaces y adjuntos mencionados en un correo no se abren ni se descargan:
   `mailquery` solo reporta nombres de adjuntos.
5. Cualquier acción que el cuerpo "pida" (pagar, hacer clic, responder, revelar
   datos) requiere confirmación explícita del usuario fuera del correo.

Las recetas de [`docs/recipes/`](docs/recipes/) aplican estos guardrails y son
el punto de partida recomendado para el harness.

---

## Pruebas

Desde la **raíz del repositorio**:

```bash
python3 -m unittest discover -s tests -t . -v     # suite completa
python3 -m unittest tests.test_store -v           # un módulo
```

- Solo `unittest` + `unittest.mock` (no hay `pytest`).
- Las pruebas usan **fixtures sintéticos** (store `V10` + `Envelope Index` +
  `Accounts4.sqlite` de prueba) y *mocks* que simulan Apple Mail; nunca tocan el
  store real.
- **El test read-only es obligatorio y bloqueante**: compara hashes y `mtime`
  de cada archivo del store de prueba antes y después de ejecutar todos los
  comandos, y verifica que no se crean archivos nuevos en el store. La suite no
  se considera verde si ese test falla.
- La validación de contenido se hace contra los fixtures; no se necesita FDA
  para los tests, pero sí para una corrida real.
- Los instaladores tienen sus propias pruebas (`tests.test_install_scripts`:
  sintaxis de `sh`, `--help`, `--dry-run`, plantilla de config y reglas de no
  sobrescritura).

---

## Actualización y desinstalación

```bash
# Actualizar el código y reinstalar el comando
cd /Users/dayler/dev/github/mailquery
git pull
pipx reinstall mailquery

# Ver el estado del despliegue
pipx list

# Actualizar todas las apps instaladas con pipx
pipx upgrade-all

# Desinstalar
pipx uninstall mailquery

# Opcional: borrar estado, logs y configuración
rm -rf ~/.mailquery
```

`pipx uninstall` elimina el comando y su entorno aislado, pero **no** toca
`~/.mailquery`. Después de actualizar, ejecuta `mailquery doctor` para validar
el entorno y los permisos. El detalle completo del despliegue (instalar pipx,
fijar el intérprete, `--editable`, problemas típicos) está en
[Despliegue e instalación](#despliegue-e-instalación).

Alternativa con los instaladores del repo:

```bash
scripts/install.sh                        # actualiza/reinstala y conserva la config
scripts/install.sh --uninstall            # desinstala el comando
scripts/install.sh --uninstall --purge    # además borra ~/.mailquery
# Windows:
#   .\scripts\install.ps1 -Uninstall -Purge
```

---

## Solución de problemas

Regla general: **reintentar solo con exit 5**; con 2/3/4 corrige primero; con 0
no hay error (aunque no haya resultados). Recuerda que los errores también son
JSON en `stdout`, con un resumen en `stderr` y un `hint` accionable.

| Exit | Error | Causa probable | Qué hacer |
|------|-------|----------------|-----------|
| 3 | `E_PERMISSION` | Falta Acceso total al disco para la app que lanza el proceso. | Concede FDA a la app/terminal y vuelve a probar; verifica con `mailquery doctor`. |
| 3 | `E_STORE_NOT_FOUND` | No existe el store de Mail esperado. | Comprueba que Apple Mail está configurado en este Mac; revisa `~/Library/Mail`. |
| 3 | `E_SCHEMA_UNSUPPORTED` | Versión de store desconocida o esquema inesperado. | Actualiza `mailquery` o revisa `doctor`; no fuerces la lectura. |
| 3 | `E_STATE_CORRUPT` | `state.json` dañado. | Renómbralo/elimínalo para re-baseline (ver abajo). |
| 5 | `E_DB_BUSY` | `Envelope Index` bloqueado/ocupado (otra ejecución, Mail sincronizando). | Reintenta una vez tras una pausa corta (el comando ya reintenta una vez). |
| 5 | `E_LOCKED` | Otra ejecución de `mailquery` tiene el lock. | Espera a que termine o reintenta; no lances corridas concurrentes. |
| 4 | `E_UNBOUNDED_SCAN` | `--text` sin filtro de acotamiento. | Añade `--since`, `--from`, `--subject` o `--include-mailbox`. |
| 4 | `E_SCAN_TOO_LARGE` | Más de `search.max_scan` candidatos para `--text`. | Acota más o sube `search.max_scan` (máx. 50000). |
| 2 | `E_CONFIG_INVALID`, `E_CONFIG_ACCOUNT_UNKNOWN`, `E_ACCOUNT_AMBIGUOUS`, `E_ACCOUNT_LABELS_UNAVAILABLE`, `E_ACCOUNT_NOT_IN_SCOPE`, `E_MAILBOX_NOT_FOUND`, `E_BAD_TIME`, `E_BAD_FILTER` | Config, cuenta, carpeta o valor inválido. | Revisa el `hint`, `mailquery doctor` y `mailquery mailboxes`; corrige `config.toml`. |
| 1 | `E_INTERNAL` | Fallo inesperado. | Revisa `~/.mailquery/logs/mailquery.log` con `--log-level debug`. |

### `E_PERMISSION` (exit 3)

La app que ejecuta la CLI no tiene Acceso total al disco. Pasos:

1. Abre **Ajustes del Sistema → Privacidad y seguridad → Acceso total al
   disco**.
2. Añade la app que lanza `mailquery` (el harness, `Terminal`, iTerm, VS Code,
   etc.), no el venv de `pipx`.
3. Cierra y vuelve a abrir la app si el sistema lo pide.
4. Verifica con `mailquery doctor` (chequeos `store` y `accounts_db`).

### `E_DB_BUSY` (exit 5)

El `Envelope Index` no se pudo abrir en solo lectura, normalmente por bloqueo
transitorio. `mailquery` reintenta una vez tras ~100 ms; si persiste:

- espera unos segundos y vuelve a intentarlo (es transitorio);
- evita lanzar varias invocaciones a la vez (el lock ya lo impide, pero puede
  haber otro proceso leyendo el store);
- si el problema se repite, revisa `--log-level debug` y el log.

### `E_STATE_CORRUPT` (exit 3)

Solo afecta a `new` (el cursor). `search`, `show`, `mailboxes` y `doctor` no se
ven afectados. Solución:

```bash
mv ~/.mailquery/state.json ~/.mailquery/state.json.corrupt
mailquery new --peek     # inspección sin avanzar
mailquery new            # re-baseline; emite W_FIRST_RUN
```

Tras el re-baseline, la próxima corrida de `new` vuelve a emitir la ventana de
*lookback* una vez; es el comportamiento documentado ante un reinicio de
estado. Ten en cuenta que borrar el estado también reinicia la deduplicación
del anillo.

### Resultados vacíos (`count: 0`, exit 0)

No es un error: exit 0 con `count: 0` es una respuesta válida. Si esperabas
resultados:

1. Comprueba si hay `W_NO_ACCOUNTS` en `warnings`: no hay cuentas declaradas
   válidas en `~/.mailquery/config.toml`. Declara al menos una.
2. Revisa el alcance con `mailquery mailboxes` (`declared`, `included`): quizá
   la cuenta está excluida o falta la carpeta en `mailbox_list`.
3. Revisa el rango de fechas: `--since`/`--until` (recuerda que `until` es
   exclusivo) o los relativos (`1w`, `1mo`, …).
4. Revisa el patrón: sin comodines se busca como subcadena; varios términos
   separados por espacios son AND. Prueba un patrón más corto.
5. Recuerda que `new` no emite correo histórico: para el histórico usa
   `search --since …`.

---

## Licencia

MIT. Copyright (c) 2026 Ariel Dayler Salzar Hinojosa. Consulta
[`LICENSE`](LICENSE) para el texto completo.

La documentación de producto está en [`docs/PRD.md`](docs/PRD.md); los
contratos internos de implementación, en
[`docs/INTERFACES.md`](docs/INTERFACES.md).

# mailquery

> [English](README.md) · [Español](README.es.md)

`mailquery` es una herramienta de línea de comandos (Python, solo biblioteca
estándar salvo `pywin32` en Windows) que **lee y busca correo local sin
modificar nada**: Apple Mail en macOS y Outlook clásico en Windows. Está pensada
para que un harness de agentes la invoque **bajo demanda** y consuma su salida.

- **Un único objeto JSON por ejecución** en `stdout` (no existe `--format`).
  Excepciones: `--help`, `--version` y el informe de texto de `doctor`.
- **Solo lectura** (invariante I-1): no marca leído, no mueve, no borra, no
  envía, no descarga cuerpos desde el servidor y **no lanza** Mail.app ni
  Outlook. Solo escribe dentro de `~/.mailquery` (estado, logs, locks, staging y
  la caché de adjuntos).
- **Sin red, sin demonio y sin scheduler** desde el núcleo: quien decide cuándo
  ejecutarla es el harness. Los plugins de backend externos declaran sus propias
  capacidades (`network`, `readonly`, `body_local`, `attachments`,
  `native_order`) y `doctor` las muestra.
- **Mismos comandos y mismo JSON en ambas plataformas.** En macOS la solo
  lectura es estructural (SQLite y `.emlx` abiertos en solo lectura); en Windows
  la impone un proxy de lista blanca sobre el modelo de objetos de Outlook.
- **`uid` opaco en forma de string:** todo identificador de mensaje es
  `"<driver>:<native_id>"`, tanto para los drivers internos como para plugins.
  El uid legado sin prefijo se acepta en la entrada para el driver nativo de la
  plataforma.

La recuperación de adjuntos y el motor multi-driver forman parte del futuro
3.0.0, todavía no publicado. `develop` anuncia la pre-release `3.0.0a0`
(3.0.0-alpha) en `--version`, pero no publica nada: sin tag, sin release y sin
merge a `main`.

Referencias: [`docs/PRD-v2.1.md`](docs/PRD-v2.1.md) (contrato del delta),
[`docs/recipes/`](docs/recipes/) (recetas para el harness),
[`docs/config.example.toml`](docs/config.example.toml) y
[`docs/INTERFACES.md`](docs/INTERFACES.md) (desarrollo y pruebas),
[`docs/PERFORMANCE-BACKLOG.md`](docs/PERFORMANCE-BACKLOG.md) (rendimiento
pendiente) y [`skills/README.md`](skills/README.md) (skill para harnesses).

## Requisitos

| Requisito | macOS | Windows |
|-----------|-------|---------|
| Sistema | macOS con Apple Mail (store `V9`/`V10`/`V11`) | Windows 10/11 x64 con Outlook **clásico** 16.0 **abierto** |
| Python | ≥ 3.11 (el que use `pipx`) | ≥ 3.11 (el que use `pipx`) |
| `pipx` | `brew install pipx && pipx ensurepath` | `python -m pip install --user pipx && python -m pipx ensurepath` |
| Dependencias | Ninguna | `pywin32` (la instala `pipx`) |
| Permisos | **Acceso total al disco** (FDA) | Misma sesión y mismo nivel de integridad que Outlook |

No se soportan el nuevo Outlook (`olk`), Outlook en la web, Outlook para Mac ni
otros clientes. Linux solo sirve para desarrollo y CI.

## Instalar, actualizar y desinstalar

```bash
pipx install .          # desde la raíz del repo (macOS o Windows)
mailquery --help
mailquery doctor        # crea ~/.mailquery y valida el entorno
```

Los instaladores automatizan `pipx` y siembran `~/.mailquery/config.toml` desde
[`docs/config.example.toml`](docs/config.example.toml) **solo si no existe** (la
aplicación nunca crea ni modifica la configuración):

```bash
scripts/install.sh [--dry-run]          # macOS
```

```powershell
.\scripts\install.ps1 [-DryRun]         # Windows (o doble clic en install.bat)
```

Opciones: `--no-config`/`-NoConfig`, `--force-config`/`-ForceConfig` (guarda un
`.bak`), `--python`/`-Python`, `--from-git`/`-FromGit`. Al terminar,
`install.ps1` comprueba que `pywin32` se importa desde el venv de `pipx` y que
`mailquery -v` muestra `backend outlook`; si falla, indica
`pipx reinstall mailquery` y termina con un código distinto de 0.

**Los plugins de backend** son paquetes separados registrados en el grupo de
entry points `mailquery.backends`. Instala uno explícitamente en el mismo
entorno de `pipx` (instalar el plugin es el consentimiento):

```bash
pipx inject mailquery <paquete-del-plugin>
mailquery doctor        # muestra el driver y sus capacidades declaradas
mailquery -v            # lista los drivers instalados
```

```bash
git pull && pipx reinstall mailquery      # actualizar; luego: mailquery doctor
pipx uninject mailquery <paquete-del-plugin>  # desinstalar un plugin
pipx uninstall mailquery                  # desinstalar el comando
rm -rf ~/.mailquery                       # opcional: borra estado, logs y caché
```

En Windows, el borrado opcional es `Remove-Item -Recurse -Force $HOME\.mailquery`
(o `.\scripts\install.ps1 -Uninstall -Purge`). `pipx uninstall` no toca
`~/.mailquery`. Para ejecutar sin instalar, ver
[`docs/INTERFACES.md` §8](docs/INTERFACES.md).

## Skill para harnesses de IA (`skills/`)

El repositorio incluye un skill listo para harnesses (DeepSeek Harness, Claude
Code) que enseña al agente a usar el CLI: contrato JSON, reglas de solo lectura y
cuerpos no confiables. No forma parte del paquete Python ni hace falta para usar
la app.

```bash
# macOS / Linux
./skills/install.sh
# Windows (PowerShell)
powershell -ExecutionPolicy Bypass -File skills\install.ps1
```

Detecta los harnesses instalados, muestra un menú (cada harness detectado, una
ruta personalizada o instalar en todos) y copia `skills/mailquery/SKILL.md` a la
raíz de skills del harness. Modo no interactivo: `./skills/install.sh --harness
dsh --scope project`, `--all`, `--path DIR`, `--dry-run`, `--force`. Detalle en
[`skills/README.md`](skills/README.md).

## Ejecutar los tests

Los tests se ejecutan **desde el clon del repositorio** con un Python ≥ 3.11;
`tests/` no forma parte del paquete que instala `pipx`. Se pueden correr antes o
después de instalar: la suite importa el código de `src/` y **no usa** la copia
instalada ni toca el `~/.mailquery` real (cada test usa un `HOME` temporal). Solo
`unittest` de la biblioteca estándar; no hace falta `pytest`.

**Windows** (PowerShell, desde la raíz del repo):

```powershell
python -m pip install --user pywin32                      # una vez, como en la CI
python -B -m unittest discover -s tests -t . -v           # suite completa
python -B -m unittest discover -s tests -t . -k ol_02_05  # un caso por ID
python -B -m unittest tests.test_outlook -v               # un módulo
```

**macOS** (Terminal, desde la raíz del repo; el `python3` del sistema es anterior
a 3.11, se usa el de Homebrew con `brew install python`):

```bash
python3 -B -m unittest discover -s tests -t . -v           # suite completa
python3 -B -m unittest discover -s tests -t . -k st_03_01  # un caso por ID
python3 -B -m unittest tests.test_store -v                 # un módulo
```

**Linux** (solo desarrollo y CI; mismos comandos que macOS con `python3` ≥ 3.11):

```bash
python3 -B -m unittest discover -s tests -t . -v
```

Resultado esperado: `OK`, con saltos (`skipped=N`) solo donde la prueba no aplica
al equipo:

| Prueba | Se salta cuando |
|--------|-----------------|
| `tests/test_smoke.py` (SMOKE-INSTALL, SMOKE-NEW, SMOKE-ATT-AM/OL) | Linux; Windows sin Outlook clásico abierto; macOS sin store de Apple Mail (`V9`/`V10`/`V11`) en `~/Library/Mail` o sin ninguna cuenta con buzón incluido (p. ej. solo `On My Device`); `pipx` no está en el `PATH` |
| `InstallShTest` | no hay `sh` en el `PATH` (habitual en PowerShell) |
| `InstallPs1Test` | no hay PowerShell (`pwsh`) |
| `UT-INS-01`, `OL-05.02` | el SO no es Windows |

Las pruebas SMOKE son las únicas que leen el cliente de correo real, siempre en
solo lectura: instalan `mailquery` con `pipx` en directorios temporales (no tocan
tu instalación), ejecutan los comandos y comprueban que los no leídos no cambian
y que se cumplen los tiempos de §19 del PRD. Tardan unos minutos. En macOS, la
app de terminal que las ejecuta necesita **Acceso total al disco**. Para correr
solo las SMOKE:

```bash
python -B -m unittest tests.test_smoke -v    # python3 en macOS
```

Convenciones (nombres por ID de caso, goldens, Outlook falso, CI): ver
[`docs/INTERFACES.md` §8](docs/INTERFACES.md).

## Primeros pasos

```bash
mailquery doctor        # 1. preflight: entorno, drivers, solo lectura, config, estado, lock
mailquery mailboxes     # 2. cuentas y carpetas, con la etiqueta que usará la config
# 3. declara al menos una cuenta en ~/.mailquery/config.toml
mailquery doctor        # 4. vuelve a validar
mailquery search --since 1w
mailquery attachment apple_mail:83143 --index 1   # recupera un adjunto local
```

Sin cuentas declaradas, `search` y `new` devuelven `count: 0` con
`W_NO_ACCOUNTS`: no es un error, solo no hay nada que observar.

## Configuración (`~/.mailquery/config.toml`)

Es **opcional** y su formato es idéntico en ambas plataformas. Solo se leen las
cuentas declaradas; dentro de cada una, `INBOX` se incluye siempre y
`mailbox_list` añade carpetas extra. Una clave desconocida da `E_CONFIG_INVALID`
(exit 2). La clave de cuenta puede llevar el prefijo del driver:
`[scope."<driver>:<cuenta>"]`; sin prefijo se usa el driver nativo de la
plataforma (`apple_mail` en macOS, `outlook` en Windows).

```toml
[scope."apple_mail:iCloud (you@icloud.com)"]              # prefijo de driver explícito
mailbox_list = ["Facturas"]

[scope."Exchange (you@company.com)"]                      # driver nativo (outlook en Windows)
mailbox_list = ["INBOX/Facturas"]
```

La parte de cuenta es la etiqueta que muestra `mailquery mailboxes`, el email si
es único o el UUID (o un prefijo de ≥ 8 caracteres); con espacios, puntos o `@`
va entre comillas. Una etiqueta que contenga `:` debe declararse con el prefijo
de driver explícito, porque el primer `:` separa el driver. Un bloque `[scope]`
de un driver no instalado falla con `E_DRIVER_UNKNOWN` (exit 2). Todas las
propiedades (`[logging]`, `[search]`, `[new]`, `[attachments]`, cuentas) están en
[`docs/config.example.toml`](docs/config.example.toml) y en el PRD §15.
Precedencia: flags de la CLI, `config.toml`, defaults. La rotación diaria del log
de la 1.x se reemplazó por `[logging].max_size_mb`; la clave retirada da
`E_CONFIG_INVALID` con el hint `retention_days was replaced by max_size_mb`.

### Recuperación de adjuntos (`[attachments]`)

```toml
[attachments]
enabled = true                 # true | false (default true)
max_file_size_mb = 100         # 1..500, por adjunto
max_total_size_mb = 200        # 1..1024 (>= max_file_size_mb), por ejecución
max_count = 50                 # 1..500, solo para --all (incluye aciertos de caché)
```

`enabled = false` hace que `mailquery attachment` falle con
`E_ATTACHMENTS_DISABLED` (exit 2) antes de abrir el store; `show` no se ve
afectado. Un valor fuera de rango (o `max_total_size_mb < max_file_size_mb`) da
`E_CONFIG_INVALID` (exit 2). Los límites se comparan con `>` estricto y
1 MiB = 1.048.576 bytes; una ejecución que los excede falla con
`E_ATTACHMENT_TOO_LARGE` (exit 4).

### Configuración y logs de plugins

Un plugin externo puede usar `~/.mailquery/<driver>.toml` y
`~/.mailquery/logs/<driver>.log`; ambos son **opcionales** y propiedad del
plugin. El núcleo nunca los lee, crea, rota ni borra. Un plugin que necesite
temporales usa `~/.mailquery/tmp/plugin-<driver>/` (0700/0600) y los limpia él
mismo. Los secretos nunca deben escribirse en `config.toml` ni en `state.json`.

## Comandos

Opciones globales: `-h`/`--help` (también por comando), `-v`/`--version` (solo
antes del subcomando) y `--log-level {error,warning,info,debug}`. No existen
`--format`, `--config`, `--home` ni `--backend`. Los ejemplos están recortados
con `…`; los valores siguen siempre el contrato vigente.

### `mailquery -v`

```text
$ mailquery -v          # sin efectos: no crea ~/.mailquery ni abre el cliente
mailquery 3.0.0a0 (backend outlook; Python 3.14.7; Windows 10.0.26200 AMD64; drivers: graph 0.1.0, outlook 3.0.0a0)
```

La línea conserva `backend <driver nativo>` y añade `; drivers: <driver>
<versión>, ...` dentro del paréntesis, en orden alfabético. Los drivers internos
se listan solo en la plataforma actual (`apple_mail` en macOS, `outlook` en
Windows); los plugins externos se listan siempre. `--version` solo lee metadata
de distribución: no lee `config.toml`, no importa plugins y no crea
`~/.mailquery`.

### `mailquery doctor [--json]`

Informe de texto (con `--json`, el payload máquina con `checks[]`). Sale con
exit 0 si puede diagnosticar; un chequeo fallido se marca `[FAIL]` y nunca
aborta. Los chequeos comunes son `python`, `home`, `driver`, `config`, `state` y
`lock`. El chequeo `driver` valida cada driver declarado y muestra sus
capacidades, la versión del paquete y la versión de API. En macOS los chequeos
son `python`, `home`, `driver`, `store`, `envelope_index`, `schema`,
`readonly_strategy`, `accounts_db`, `config`, `state` y `lock`. Ejemplo:

```text
$ mailquery doctor
mailquery doctor - environment and read-only preflight

Checks:
  [ok]   python             3.14.7
  [ok]   home               …\.mailquery (writable)
  [ok]   driver             outlook (api=1; pkg 3.0.0a0; network=false; readonly=structural;
                            body_local=true; attachments=local; native_order=text)
  [ok]   pywin32             win32com importable
  [ok]   outlook             classic Outlook 16.0.0.20430 running (attached with GetActiveObject)
  [ok]   stores              1 candidate(s): Exchange (ana.perez@example.com) [Exchange]; 1
                             excluded: Exchange shared (Soporte) [shared_mailbox]
  [ok]   readonly_strategy   com_readonly: read-only whitelist proxy active, attached with …
  [ok]   object_model_guard  no Outlook security policy decides; active antivirus: Fake Defender
  [ok]   config              Exchange (ana.perez@example.com) → Exchange (ana.perez@example.com) (…): INBOX, Facturas
  [ok]   state               no state yet; the next new run is a first run and emits the messages
                             received in the last 10min before the newest message
  [ok]   lock                available: …\.mailquery\locks\mailquery.lock

Result: 11/11 checks passed
```

Cuando un driver declarado es incompatible, `driver` queda `ok=false` y sus
dependientes informan `not evaluated: driver failed`; `doctor` sigue saliendo
con exit 0.

### `mailquery mailboxes`

Cuentas, carpetas, contadores y si están incluidas en el alcance (`included`).
`excluded_stores` lista, solo en Windows, los stores que no se leen y el motivo
(`shared_mailbox`, `public_folders`, `online_mode`, `network_path`,
`unsupported_account_type`, `unavailable`); en macOS es `[]`.

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
  "excluded_stores": [{"label": "Exchange shared (Soporte)", "path": null, "reason": "shared_mailbox"}],
  "warnings": []
}
```

### `mailquery search`

Filtros: `--subject`, `--text`, `--from`, `--to`, `--cc`, `--since`, `--until`,
`--unread`, `--flagged`, `--has-attachments`, `--include-mailbox` y `--limit`
(default 20, máx. 200). Los patrones son subcadenas con comodines `*` y `?`, sin
distinguir mayúsculas ni acentos; en `--subject`, los términos separados por
espacios son AND. Fechas: ISO 8601 o relativas (`30min`, `24h`, `7d`, `1w`,
`1mo`, `1y`, `today`, `yesterday`); `--since` incluye y `--until` excluye.

Ejemplos: `mailquery search --since 1w --unread` y
`mailquery search --text "*factura*" --since 1mo --has-attachments`.

Salida de `mailquery search --since 1w` (Windows; `uid` recortado):

```json
{
  "ok": true,
  "command": "search",
  "count": 3,
  "truncated": false,
  "messages": [
    {
      "uid": "outlook:00000000D70DBCF61C2A4B6E9A51E0C3B2A49F10…",
      "subject": "Factura octubre 2026",
      "from": {"name": "Proveedor SA", "address": "facturas@proveedor.example"},
      "date_received": "2026-11-02T09:54:09-04:00",
      "has_attachments": true,
      "snippet": "Estimado cliente, adjuntamos la factura de octubre.",
      "body": {"available": true, "readable": true, "partial": false, "truncated": false},
      …
    },
    …
  ],
  "scan": {"mode": "metadata", "candidates": 3, "messages_read": 3, "duration_ms": 9},
  "warnings": ["W_BODY_NOT_LOCAL: only the headers of the message are stored locally; the body is never downloaded", …]
}
```

`--text` lee el cuerpo de cada candidato, así que **exige acotar** con
`--since`/`--until`, `--from`, `--subject` o una carpeta extra
(`--include-mailbox` o una carpeta de `mailbox_list` distinta de INBOX); si no,
falla con `E_UNBOUNDED_SCAN` (exit 4). Si quedan más de `[search].max_scan`
candidatos (default 5000), falla con `E_SCAN_TOO_LARGE` (exit 4). En Windows,
`--to` y `--cc` **no acotan** `--text` (comprobarlos obliga a abrir cada
mensaje); en macOS sí. `--include-mailbox` solo acepta carpetas de cuentas
declaradas. `scan.mode` es `metadata` o `text`.

### `mailquery new [--peek] [--limit N]`

Mensajes recibidos desde la última ejecución, **una sola vez**: usa un cursor
global guardado en `~/.mailquery/state.json` (default 100, máx. 500). `--peek`
devuelve los nuevos sin avanzar el cursor ni escribir estado. La **primera
corrida** (sin cursor) emite, en orden ascendente, los mensajes recibidos en la
ventana `[new].lookback` (default `10min`) anteriores al más reciente del
alcance, al menos ese, y añade `W_FIRST_RUN`; las siguientes emiten lo que llegó
después del cursor. Las cuentas o carpetas añadidas después no emiten su
histórico (usa `search`). Los mensajes con fecha nula o futura se ignoran hasta
que su fecha sea válida.

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

La corrida siguiente, sin correo nuevo, devuelve `"count": 0`, `"messages": []`
y `warnings: []`, con `cursor.previous` igual a `cursor.current`.

### `mailquery show <uid>`

Detalle de un mensaje: cabeceras, `body_text` (truncado a 20.000 caracteres, con
`body_truncated` y `W_BODY_TRUNCATED`) y adjuntos. El `uid` es un **string
opaco** `"<driver>:<native_id>"`: pásalo tal cual, sin aritmética. El uid legado
sin prefijo se acepta para el driver nativo. Solo muestra mensajes de cuentas
declaradas (`E_ACCOUNT_NOT_IN_SCOPE` si no). Un uid inválido o inexistente da
`E_USAGE` (exit 2). `show` nunca escribe en disco.

```bash
mailquery show apple_mail:2714
```

```json
{
  "ok": true,
  "command": "show",
  "message": {
    "uid": "apple_mail:2714",
    "subject": "Factura octubre 2026",
    "headers": {"From": "Proveedor SA <facturas@proveedor.example>", "Date": "Mon, 09 Nov 2026 20:36:13 -0400", …},
    "body_text": "Estimado cliente, adjuntamos la factura de octubre.",
    "body_truncated": false,
    "attachments": [
      {"index": 1, "name": "factura-2026-10.pdf", "cached_path": null}
    ],
    "partial": false, "readable": true, "source": {"emlx_path": "/…/2714.emlx", "partial": false},
    …
  },
  "warnings": []
}
```

`attachments[]` lleva `index` (la posición estable 1..N que comparte con
`mailquery attachment`), `name` (el nombre original del archivo) y `cached_path`
(la ruta absoluta del archivo en la caché, o `null` si no hay archivo regular en
la caché o el nombre no es seguro). Un driver con `attachments: "none"` devuelve
`attachments: []`. En S/MIME, `show` devuelve `attachments: []` (el nombre
técnico `smime.p7m` nunca se lista) y solo queda el warning de cuerpo ilegible.

### `mailquery attachment <uid> (--index N | --all) [--force]`

Recupera los adjuntos de un mensaje desde el store **local** hacia
`~/.mailquery/attachments/<driver>/<native_id>/<index:02d>_<sanitized_name>`
(directorios 0700, archivos 0600 en POSIX) y devuelve las rutas guardadas, los
nombres, los tamaños y el SHA-256. Nunca descarga desde el servidor y nunca abre
ni ejecuta un archivo: solo copia bytes ya decodificados.

```bash
mailquery attachment apple_mail:83301 --index 2
mailquery attachment apple_mail:83301 --all
mailquery attachment apple_mail:83301 --index 2 --force
```

| Opción | Significado |
|--------|-------------|
| `<uid>` | `"<driver>:<native_id>"` o, en la entrada, el uid legado sin prefijo del driver nativo |
| `--index N` | índice 1-based a recuperar (el que muestra `show`); mutuamente excluyente con `--all` |
| `--all` | recupera todos los adjuntos del mensaje |
| `--force` | ignora la caché, re-extrae y reemplaza el archivo de forma atómica (`cached: false`) |

```json
{
  "ok": true,
  "command": "attachment",
  "uid": "apple_mail:83301",
  "output_dir": "/Users/tu-usuario/.mailquery/attachments/apple_mail/83301",
  "count": 1,
  "attachments": [
    {"index": 2, "original_name": "Factura Octubre 2026.pdf",
     "sanitized_name": "02_Factura_Octubre_2026.pdf", "saved": true, "cached": false,
     "path": "/Users/tu-usuario/.mailquery/attachments/apple_mail/83301/02_Factura_Octubre_2026.pdf",
     "size_bytes": 59, "sha256": "9ead96e0efdc3db6c3bee638bd4dc2e541a67a4f2bba812acf476d4527ce455e"}
  ],
  "warnings": []
}
```

- **El mensaje se bloquea completo.** Si cualquier adjunto tiene un nombre
  peligroso, una extensión del catálogo o *magic bytes* ejecutables, no se
  escribe nada: `E_ATTACHMENT_BLOCKED` (exit 4), tanto con `--index` como con
  `--all`. El harness no debe reintentar el mismo mensaje ni abrir los adjuntos
  del correo.
- **Caché:** un archivo regular existente se sirve con `cached: true` y
  `saved: true` (mismo `size_bytes`/`sha256`); `--force` lo re-extrae. Un archivo
  de caché que no sea regular se trata como miss. Un archivo borrado por una
  limpieza externa es un miss y se extrae una vez. No se escribe nada fuera de
  `~/.mailquery/tmp/` (staging) y de la caché; staging y caché están en el mismo
  sistema de archivos y la publicación es atómica.
- **Límites:** `max_count` (solo `--all`, incluidos los aciertos de caché),
  `max_file_size_mb` y `max_total_size_mb` de `[attachments]`; excederlos da
  `E_ATTACHMENT_TOO_LARGE` (exit 4).
- **Disponibilidad:** un adjunto que no está local (`not_local`, `not_downloaded`,
  `unsupported`, `network`) falla con `E_ATTACHMENT_UNAVAILABLE` (exit 3); el
  contenido corrupto o S/MIME falla con `E_ATTACHMENT_UNREADABLE` (exit 3). Un
  mensaje S/MIME nunca se reporta como “sin adjuntos”.
- **Limpieza:** la caché es best-effort y no es estado de la aplicación. No hay
  purga al arrancar: usa un cron/limpieza externa si hace falta. La app tolera
  borrados concurrentes.

### `mailquery <comando> --help`

Cada subcomando documenta sus propias opciones; `mailquery --help` lista los seis
comandos y la línea de códigos de salida de abajo.

## Cuerpo y warnings

`body.available` indica si hay cuerpo local y `body.readable` si se pudo leer.
Los warnings (`"W_CODIGO: motivo"`) no son errores. En ambas plataformas:
`W_NO_ACCOUNTS`, `W_FIRST_RUN`, `W_RESULTS_TRUNCATED`, `W_BODY_TRUNCATED`,
`W_HTML_NO_TEXT`, `W_BODY_UNREADABLE` (incluye S/MIME) y
`W_ATTACHMENTS_UNAVAILABLE` (solo para cuerpo ilegible **no S/MIME**; S/MIME
devuelve una lista de adjuntos vacía y conserva solo el warning de cuerpo). Solo
macOS: `W_EMLX_MISSING`, `W_EMLX_CORRUPT` y `W_ACCOUNT_LABELS_UNAVAILABLE`. Solo
Windows: `W_BODY_NOT_LOCAL` (el item solo tiene cabeceras en local; nunca se
descarga) y `W_STORE_EXCLUDED`. Catálogo completo: PRD §12.10.

## Códigos de salida

Los errores también son JSON en `stdout` (`{"ok": false, "error": {"code",
"message", "hint"}}`) más un resumen en `stderr`. Reintenta **solo con 5**; los
adjuntos bloqueados son un rechazo (4), no un error transitorio.

Línea: `0 ok | 2 usage or config error | 3 environment error | 4 rejected query
or blocked attachments | 5 busy or transient error | 6 mail client not running`.

| Exit | Significado | Códigos `E_*` |
|------|-------------|---------------|
| 0 | Éxito (incluye 0 resultados, `--help` y `--version`) | — |
| 1 | Error interno inesperado | `E_INTERNAL` |
| 2 | Uso, uid o configuración inválidos | `E_USAGE`, `E_CONFIG_INVALID`, `E_CONFIG_ACCOUNT_UNKNOWN`, `E_ACCOUNT_AMBIGUOUS`, `E_ACCOUNT_LABELS_UNAVAILABLE`, `E_ACCOUNT_NOT_IN_SCOPE`, `E_MAILBOX_NOT_FOUND`, `E_BAD_TIME`, `E_BAD_FILTER`, `E_DRIVER_UNKNOWN`, `E_ATTACHMENTS_DISABLED` |
| 3 | Entorno inválido o fallo del driver | `E_STORE_NOT_FOUND`, `E_SCHEMA_UNSUPPORTED`, `E_PERMISSION`, `E_STATE_CORRUPT`, `E_CLIENT_UNSUPPORTED`, `E_DEPENDENCY_MISSING`, `E_CLIENT_TIMEOUT`, `E_PLUGIN_INCOMPATIBLE`, `E_PLUGIN_FAILED`, `E_ATTACHMENT_UNAVAILABLE`, `E_ATTACHMENT_UNREADABLE`, `E_IO` |
| 4 | Consulta rechazada o adjuntos bloqueados | `E_UNBOUNDED_SCAN`, `E_SCAN_TOO_LARGE`, `E_ATTACHMENT_BLOCKED`, `E_ATTACHMENT_TOO_LARGE` |
| 5 | Ocupado o transitorio | `E_LOCKED`, `E_DB_BUSY`, `E_CLIENT_BUSY` |
| 6 | Cliente de correo no disponible | `E_OUTLOOK_NOT_RUNNING` |

```text
$ mailquery search --text "*factura*"          # Outlook; sin acotar: exit 4
mailquery: E_UNBOUNDED_SCAN: --text without a narrowing filter would read every message in the scope
mailquery: hint: add --since, --until, --from, --subject or --include-mailbox (for example: mailquery search --text invoice --since 30d)
```

Con Outlook cerrado, `mailquery search --since 1w` termina con exit 6 y
`E_OUTLOOK_NOT_RUNNING` (`classic Outlook is not running (mailquery never launches
it)`; hint: `open classic Outlook with the same user, without elevation, and
retry`).

## Drivers de plugin y capacidades

Cada driver — los internos `apple_mail` y `outlook` y cada plugin externo —
declara un nombre `driver` único (`[a-z0-9_]{1,64}`), `plugin_api = 1` y el mapa
de capacidades de abajo. `doctor` lo muestra en el chequeo `driver`; un plugin
incompatible falla con `E_PLUGIN_INCOMPATIBLE` (exit 3) y un fallo en runtime con
`E_PLUGIN_FAILED` (exit 3), nunca `E_INTERNAL`.

| Capacidad | Valores | Significado |
|-----------|---------|-------------|
| `network` | `true`/`false` | el plugin usa la red (el núcleo nunca lo hace) |
| `readonly` | `structural`/`promise` | garantizada por arquitectura o prometida por el plugin |
| `body_local` | `true`/`false` | los cuerpos son locales (si no, `network` debe ser `true`) |
| `attachments` | `local`/`remote`/`none` | `remote` exige `network: true` |
| `native_order` | `numeric`/`text` | cómo se compara la clave de orden nativa del driver |

Instalar un plugin es consentimiento explícito: el núcleo no lo sandboxea. El
grupo de entry points `mailquery.backends` es el mecanismo de registro; las
capacidades y las instrucciones de `pipx inject` de arriba son la frontera de
confianza.

## Logs y privacidad

`~/.mailquery/logs/mailquery.log`, texto plano; rota por tamaño
(`[logging].max_size_mb`, default 10 MB, 5 archivos rotados). La línea
`event=start` registra `backend=` (el driver nativo) y `drivers=` (la lista
declarada); el éxito de `attachment` registra `event=end` con conteos y bytes.
Asuntos, cuerpos, direcciones, carpetas, cuentas, rutas, términos de búsqueda,
uids y nombres de adjuntos nunca se registran. Cero red y cero telemetría desde
el núcleo; las credenciales y tokens nunca se leen.

## Permisos

- **macOS:** concede **Acceso total al disco** (FDA) a la app que lanza el
  proceso (harness, Terminal, VS Code…), **no** al venv de `pipx`: Ajustes del
  Sistema → Privacidad y Seguridad → Acceso total al disco. Sin FDA, los
  comandos devuelven `E_PERMISSION` (exit 3) y `doctor` marca
  `store`/`accounts_db`. Mail.app no necesita estar abierto.
- **Windows:** Outlook clásico debe estar **abierto** y `mailquery` debe
  ejecutarse en la misma sesión y con el mismo nivel de integridad: no lo
  ejecutes elevado ni como servicio (verías `E_OUTLOOK_NOT_RUNNING`). El chequeo
  `object_model_guard` de `doctor` anticipa el aviso de seguridad de Outlook
  (Object Model Guard): debe mostrar `[ok]`; si aparece el aviso, la llamada
  aborta a los 30 s con `E_CLIENT_TIMEOUT` (exit 3). Revisa el antivirus o la
  directiva de Outlook.
- **Caché de adjuntos y staging:** `~/.mailquery/attachments/` y
  `~/.mailquery/tmp/` son del usuario (directorios 0700, archivos 0600 en POSIX);
  en Windows se aplica la ACL del perfil. Nunca los hagas legibles por todos.
  `attachment` solo publica archivos regulares y nunca sigue un symlink.
- Ejecuta `mailquery doctor` tras actualizar el intérprete, el sistema o el
  cliente de correo.

Los cuerpos y los nombres de adjuntos son **entrada no confiable**: las recetas
del harness los tratan como datos citados, nunca como instrucciones, y nunca
abren ni ejecutan los archivos recuperados.

## Problemas típicos

| Síntoma | Causa | Qué hacer |
|---------|-------|-----------|
| `mailquery: command not found` / `pipx: command not found` | El directorio de `pipx` no está en el `PATH` de la sesión | `pipx ensurepath` y abre una terminal nueva |
| El comando usa otro Python o falla con `ModuleNotFoundError` | `pipx` instaló la app con otro intérprete | `pipx list`; `pipx reinstall --python <python> mailquery` |
| `count: 0` y `W_NO_ACCOUNTS` | No hay cuentas declaradas | Declara una cuenta en `config.toml` (ver `mailquery mailboxes`) |
| `count: 0` sin warnings | Rango de fechas, patrón o carpeta | Revisa `--since`/`--until`, prueba un patrón más corto y mira `included` en `mailboxes`; `new` no emite histórico: usa `search` |
| `W_STORE_EXCLUDED` (Windows) | La cuenta declarada es un store excluido (compartido, online, ruta de red…) | Mira el motivo en `mailboxes` → `excluded_stores` |
| `E_PERMISSION` (3, macOS) | Falta FDA | Ver [Permisos](#permisos) |
| `E_DEPENDENCY_MISSING` / `E_CLIENT_UNSUPPORTED` (3, Windows) | Falta `pywin32` / no hay Outlook clásico 16.0 | `pipx reinstall mailquery` / instala Outlook clásico |
| `E_OUTLOOK_NOT_RUNNING` (6) | Outlook cerrado, o sesión o nivel de integridad distinto | Abre Outlook clásico con el mismo usuario y sin elevar; reintenta |
| `E_CLIENT_TIMEOUT` (3) | Outlook no respondió en 30 s (posible aviso de seguridad) | Revisa `mailquery doctor` antes de reintentar |
| `E_DB_BUSY`, `E_LOCKED`, `E_CLIENT_BUSY` (5) | Store, lock u Outlook ocupados | Reintenta una vez tras una pausa; no ejecutes en paralelo |
| `E_STATE_CORRUPT` (3) | `state.json` dañado (solo afecta a `new`) | Renómbralo; la siguiente ejecución de `new` será primera corrida y emitirá la ventana de `lookback` otra vez |
| `E_DRIVER_UNKNOWN` (2) | El prefijo de driver de un bloque `[scope]` o del uid no está instalado | `mailquery -v` lista los drivers instalados; `pipx inject mailquery <paquete-del-plugin>`; revisa la forma `[a-z0-9_]{1,64}` |
| `E_PLUGIN_INCOMPATIBLE` / `E_PLUGIN_FAILED` (3) | El plugin no cumple la API 1 o falló en runtime | Reinstala/actualiza el plugin; `mailquery doctor` muestra el detalle del `driver` |
| `E_ATTACHMENTS_DISABLED` (2) | `[attachments].enabled = false` | Pon `enabled = true` en `config.toml` |
| `E_ATTACHMENT_BLOCKED` (4) | Un nombre, extensión o contenido ejecutable peligroso en **cualquier** adjunto del mensaje | No reintentes; el mensaje completo está bloqueado. Revísalo en el cliente de correo bajo tu responsabilidad |
| `E_ATTACHMENT_TOO_LARGE` (4) | Se superó un límite de `[attachments]` | Sube el límite o recupera solo un adjunto con `--index` |
| `E_ATTACHMENT_UNAVAILABLE` (3) | El adjunto no está local (`not_local`, `not_downloaded`, `unsupported`, `network`) | Abre el mensaje en el cliente para que se descargue, o recupera otro mensaje |
| `E_ATTACHMENT_UNREADABLE` (3) | El adjunto está corrupto o protegido con S/MIME | Revísalo en el cliente de correo; los adjuntos S/MIME no se pueden extraer |
| `E_IO` (3) | Fallo de E/S al escribir la caché o el staging (espacio, cuota, sistema de archivos) | Revisa el espacio libre y los permisos de `~/.mailquery`, y reintenta |
| `E_UNBOUNDED_SCAN` / `E_SCAN_TOO_LARGE` (4) | `--text` sin acotar / demasiados candidatos | Añade `--since` u otro filtro, o sube `search.max_scan` (máx. 50000) |
| `E_INTERNAL` (1) | Fallo inesperado | Revisa `~/.mailquery/logs/mailquery.log` con `--log-level debug` |

## Licencia

MIT. Copyright (c) 2026 Ariel Dayler Salzar Hinojosa. Ver [`LICENSE`](LICENSE)
para el texto completo.

# mailquery

`mailquery` es una herramienta de línea de comandos (Python, solo biblioteca
estándar salvo `pywin32` en Windows) que **lee y busca correo local sin
modificar nada**: Apple Mail en macOS y Outlook clásico en Windows. Está pensada
para que un harness de agentes la invoque **bajo demanda** y consuma su salida.

- **Un único objeto JSON por ejecución** en `stdout` (no existe `--format`).
  Excepciones: `--help`, `--version` y el informe de texto de `doctor`.
- **Solo lectura** (invariante I-1): no marca leído, no mueve, no borra, no
  envía, no descarga adjuntos y **no lanza** Mail.app ni Outlook. Solo escribe
  dentro de `~/.mailquery` (estado, logs, locks y temporales).
- **Sin red, sin demonio y sin scheduler**: quien decide cuándo ejecutarla es
  el harness.
- **Mismos comandos y mismo JSON en ambas plataformas.** En macOS la solo
  lectura es estructural (SQLite y `.emlx` abiertos en solo lectura); en Windows
  la impone un proxy de lista blanca sobre el modelo de objetos de Outlook. El
  `uid` es un entero en macOS y un string hexadecimal en Windows.

Referencias: [`docs/PRD.md`](docs/PRD.md) (producto y contrato),
[`docs/recipes/`](docs/recipes/) (recetas para el harness),
[`docs/config.example.toml`](docs/config.example.toml) y
[`docs/INTERFACES.md`](docs/INTERFACES.md) (desarrollo y pruebas).

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

```bash
git pull && pipx reinstall mailquery    # actualizar; luego: mailquery doctor
pipx uninstall mailquery                # desinstalar el comando
rm -rf ~/.mailquery                     # opcional: borra estado, logs y configuración
```

En Windows, el borrado opcional es `Remove-Item -Recurse -Force $HOME\.mailquery`
(o `.\scripts\install.ps1 -Uninstall -Purge`). `pipx uninstall` no toca
`~/.mailquery`. Para ejecutar sin instalar, ver
[`docs/INTERFACES.md` §8](docs/INTERFACES.md).

## Primeros pasos

```bash
mailquery doctor        # 1. preflight: entorno, solo lectura, config, estado, lock
mailquery mailboxes     # 2. cuentas y carpetas, con la etiqueta que usará la config
# 3. declara al menos una cuenta en ~/.mailquery/config.toml
mailquery doctor        # 4. vuelve a validar
mailquery search --since 1w
```

Sin cuentas declaradas, `search` y `new` devuelven `count: 0` con
`W_NO_ACCOUNTS`: no es un error, solo no hay nada que observar.

## Configuración (`~/.mailquery/config.toml`)

Es **opcional** y su formato es idéntico en ambas plataformas. Solo se leen las
cuentas declaradas; dentro de cada una, `INBOX` se incluye siempre y
`mailbox_list` añade carpetas extra. Una clave desconocida da `E_CONFIG_INVALID`
(exit 2). Mínimo en macOS y su equivalente en Windows:

```toml
[scope."iCloud (you@gmail.com)"]                      # macOS
mailbox_list = ["Facturas"]

[scope."Exchange (you@company.com)"]         # Windows
mailbox_list = ["INBOX/Facturas"]
```

La clave de cada bloque es la etiqueta que muestra `mailquery mailboxes`, el
email si es único o el UUID (o un prefijo de ≥ 8 caracteres); con espacios,
puntos o `@` va entre comillas. Todas las propiedades (`[logging]`, `[search]`,
`[new]`, cuentas) están en [`docs/config.example.toml`](docs/config.example.toml)
y en el PRD §15. Precedencia: flags de la CLI, `config.toml`, defaults. La
rotación diaria del log de la 1.x se reemplazó por `[logging].max_size_mb`; la
clave retirada da `E_CONFIG_INVALID` con el hint
`retention_days was replaced by max_size_mb`.

## Comandos

Opciones globales: `-h`/`--help` (también por comando), `-v`/`--version` (solo
antes del subcomando) y `--log-level {error,warning,info,debug}`. No existen
`--format`, `--config`, `--home` ni `--backend`. Los ejemplos de abajo son salidas
reales de la 2.0.0, recortadas con `…`.

### `mailquery -v`

```text
$ mailquery -v          # sin efectos: no crea ~/.mailquery ni abre el cliente
mailquery 2.0.0 (backend outlook; Python 3.14.7; Windows 10.0.26200 AMD64)
```

### `mailquery doctor [--json]`

Informe de texto (con `--json`, el payload máquina con `checks[]`). Sale con
exit 0 si puede diagnosticar; un chequeo fallido se marca `[FAIL]`. En macOS los
chequeos son `python`, `home`, `store`, `envelope_index`, `schema`,
`readonly_strategy`, `accounts_db`, `config`, `state` y `lock`. En Windows:

```text
$ mailquery doctor
mailquery doctor - environment and read-only preflight

Checks:
  [ok]   python              3.14.7
  [ok]   home                …\.mailquery (writable)
  [ok]   pywin32             win32com importable
  [ok]   outlook             classic Outlook 16.0.0.20430 running (attached with GetActiveObject)
  [ok]   stores              1 candidate(s): Exchange (ana.perez@example.com) [Exchange]; 1
                             excluded: Exchange shared (Soporte) [shared_mailbox]
  [ok]   readonly_strategy   com_readonly: read-only whitelist proxy active, attached with …
  [ok]   object_model_guard  no Outlook security policy decides; active antivirus: Fake Defender
  …
  [ok]   state               no state yet; the next new run is a first run and emits the messages
                             received in the last 10min before the newest message
  …

Result: 10/10 checks passed
```

### `mailquery mailboxes`

Cuentas, carpetas, contadores y si están incluidas en el alcance
(`included`). `excluded_stores` lista, solo en Windows, los stores que no se
leen y el motivo (`shared_mailbox`, `public_folders`, `online_mode`,
`network_path`, `unsupported_account_type`, `unavailable`); en macOS es `[]`.

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
(default 20, máx. 200). Los patrones son subcadenas con comodines `*` y `?`,
sin distinguir mayúsculas ni acentos; en `--subject`, los términos separados por
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
      "uid": "00000000D70DBCF61C2A4B6E9A51E0C3B2A49F10…",
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
  "warnings": ["W_BODY_NOT_LOCAL: only the headers of uid 00000000D70DBCF6… are stored locally; the body is never downloaded", …]
}
```

`--text` lee el cuerpo de cada candidato, así que **exige acotar** con
`--since`/`--until`, `--from`, `--subject` o una carpeta extra (`--include-mailbox`
o una carpeta de `mailbox_list` distinta de INBOX); si no, falla con
`E_UNBOUNDED_SCAN` (exit 4). Si quedan más de `[search].max_scan` candidatos
(default 5000), falla con `E_SCAN_TOO_LARGE` (exit 4). En Windows, `--to` y `--cc`
**no acotan** `--text` (comprobarlos obliga a abrir cada mensaje); en macOS sí.
`--include-mailbox` solo acepta carpetas de cuentas declaradas. `scan.mode` es
`metadata` o `text`. En macOS, `--text "*factura*" --since 1mo` devuelve, entre
otros campos, `"scan": {"mode": "text", "candidates": 12, "messages_read": 11, …}`
y warnings como
`W_EMLX_MISSING: no .emlx file for uid 83170`.

### `mailquery new [--peek] [--limit N]`

Mensajes recibidos desde la última ejecución, **una sola vez**: usa un cursor
global guardado en `~/.mailquery/state.json` (default 100, máx. 500). `--peek`
devuelve los nuevos sin avanzar el cursor ni escribir estado. La **primera
corrida** (sin cursor) emite, en orden ascendente, los mensajes recibidos en los
`[new].lookback` (default `10min`) anteriores al más reciente del alcance, al
menos ese, y añade `W_FIRST_RUN`; las siguientes emiten lo que llegó después del
cursor. Las cuentas o carpetas añadidas después no emiten su histórico (usa
`search`). Los mensajes con fecha nula o futura se ignoran hasta que su fecha
sea válida.

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

La corrida siguiente, sin correo nuevo, devuelve `"count": 0`, `"messages": []`
y `warnings: []`, con `cursor.previous` igual a `cursor.current`.

### `mailquery show <uid>`

Detalle de un mensaje: cabeceras, `body_text` (truncado a 20.000 caracteres, con
`body_truncated` y `W_BODY_TRUNCATED`) y nombres de adjuntos. Trata el `uid`
como un **token opaco** (entero en macOS, string hexadecimal en mayúsculas en
Windows): pásalo tal cual, sin aritmética. Solo muestra mensajes de cuentas
declaradas (`E_ACCOUNT_NOT_IN_SCOPE` si no). Un uid inválido o inexistente da
`E_USAGE` (exit 2).

```bash
mailquery show 00000000D70DBCF61C2A4B6E9A51E0C3B2A49F10…    # el uid completo, tal como lo devuelve search
```

```json
{
  "ok": true,
  "command": "show",
  "message": {
    "uid": "00000000D70DBCF6…",
    "subject": "Factura octubre 2026",
    "headers": {"From": "Proveedor SA <facturas@proveedor.example>", "Date": "Mon, 02 Nov 2026 13:54:03 +0000", …},
    "body_text": "Estimado cliente, adjuntamos la factura de octubre.",
    "body_truncated": false,
    "attachments": [{"name": "factura-2026-10.pdf"}],
    "partial": false, "readable": true, "source": {"emlx_path": null, "partial": false},
    …
  },
  "warnings": []
}
```

### Cuerpo y warnings

`body.available` indica si hay cuerpo local y `body.readable` si se pudo leer.
Los warnings (`"W_CODIGO: motivo"`) no son errores. En ambas plataformas:
`W_NO_ACCOUNTS`, `W_FIRST_RUN`, `W_RESULTS_TRUNCATED`, `W_BODY_TRUNCATED`,
`W_HTML_NO_TEXT`, `W_BODY_UNREADABLE` (incluye S/MIME) y
`W_ATTACHMENTS_UNAVAILABLE`. Solo en macOS: `W_EMLX_MISSING`, `W_EMLX_CORRUPT`
y `W_ACCOUNT_LABELS_UNAVAILABLE`. Solo en Windows: `W_BODY_NOT_LOCAL` (el item
solo tiene cabeceras en local; nunca se descarga) y `W_STORE_EXCLUDED`.
Catálogo completo: PRD §12.10.

## Códigos de salida

Los errores también son JSON en `stdout` (`{"ok": false, "error": {"code",
"message", "hint"}}`) y un resumen en `stderr`. Reintentar **solo con 5**.

| Exit | Significado | Códigos `E_*` |
|------|-------------|----------------|
| 0 | Éxito (incluye 0 resultados, `--help` y `--version`) | — |
| 1 | Error interno inesperado | `E_INTERNAL` |
| 2 | Uso o configuración inválidos | `E_USAGE`, `E_CONFIG_INVALID`, `E_CONFIG_ACCOUNT_UNKNOWN`, `E_ACCOUNT_AMBIGUOUS`, `E_ACCOUNT_LABELS_UNAVAILABLE`, `E_ACCOUNT_NOT_IN_SCOPE`, `E_MAILBOX_NOT_FOUND`, `E_BAD_TIME`, `E_BAD_FILTER` |
| 3 | Entorno no válido | `E_STORE_NOT_FOUND`, `E_SCHEMA_UNSUPPORTED`, `E_PERMISSION`, `E_STATE_CORRUPT`, `E_CLIENT_UNSUPPORTED`, `E_DEPENDENCY_MISSING`, `E_CLIENT_TIMEOUT` |
| 4 | Consulta rechazada | `E_UNBOUNDED_SCAN`, `E_SCAN_TOO_LARGE` |
| 5 | Ocupado o transitorio | `E_LOCKED`, `E_DB_BUSY`, `E_CLIENT_BUSY` |
| 6 | Cliente de correo no disponible | `E_OUTLOOK_NOT_RUNNING` |

```text
$ mailquery search --text "*factura*"          # Outlook; sin acotar: exit 4
mailquery: E_UNBOUNDED_SCAN: --text without a narrowing filter would read every message in the scope
mailquery: hint: add --since, --until, --from, --subject or --include-mailbox (for example: mailquery search --text invoice --since 30d)
```

Con Outlook cerrado, `mailquery search --since 1w` termina con exit 6 y
`E_OUTLOOK_NOT_RUNNING` (`classic Outlook is not running (mailquery never launches it)`;
hint: `open classic Outlook with the same user, without elevation, and retry`).

## Logs y privacidad

`~/.mailquery/logs/mailquery.log`, en texto plano; rota por tamaño
(`[logging].max_size_mb`, default 10 MB, 5 archivos rotados). Nunca se
registran asuntos, cuerpos, direcciones, carpetas, cuentas, rutas, términos de
búsqueda ni identificadores de mensajes. Cero red y cero telemetría; nunca se
leen credenciales ni tokens.

## Permisos

- **macOS:** concede **Acceso total al disco** (FDA) a la app que lanza el
  proceso (harness, Terminal, VS Code…), **no** al venv de `pipx`: Ajustes del
  Sistema → Privacidad y seguridad → Acceso total al disco. Sin FDA, los
  comandos dan `E_PERMISSION` (exit 3) y `doctor` marca `store`/`accounts_db`.
  No hace falta que Mail.app esté abierto.
- **Windows:** Outlook clásico debe estar **abierto** y `mailquery` debe correr
  en la misma sesión y con el mismo nivel de integridad: no lo ejecutes elevado
  ni como servicio (verías `E_OUTLOOK_NOT_RUNNING`). El chequeo
  `object_model_guard` de `doctor` anticipa el aviso de seguridad de Outlook
  (Object Model Guard): debe salir `[ok]`; si el aviso apareciera, la llamada se
  aborta a los 30 s con `E_CLIENT_TIMEOUT` (exit 3). Revisa el antivirus o la
  directiva de Outlook.
- Ejecuta `mailquery doctor` tras actualizar el intérprete, el sistema o el
  cliente de correo.

El cuerpo de los correos es **entrada no confiable**: las recetas del harness lo
tratan como datos citados, nunca como instrucciones.

## Problemas típicos

| Síntoma | Causa | Qué hacer |
|---------|-------|-----------|
| `mailquery: command not found` / `pipx: command not found` | El directorio de `pipx` no está en el `PATH` de la sesión | `pipx ensurepath` y abre una terminal nueva |
| El comando usa otro Python o falla con `ModuleNotFoundError` | `pipx` instaló la app con otro intérprete | `pipx list`; `pipx reinstall --python <python> mailquery` |
| `count: 0` y `W_NO_ACCOUNTS` | No hay cuentas declaradas | Declara una cuenta en `config.toml` (ver `mailquery mailboxes`) |
| `count: 0` sin warnings | Rango de fechas, patrón o carpeta | Revisa `--since`/`--until`, prueba un patrón más corto y comprueba `included` en `mailboxes`; `new` no emite histórico: usa `search` |
| `W_STORE_EXCLUDED` (Windows) | La cuenta declarada es un store excluido (compartido, online, ruta de red…) | Mira el motivo en `mailboxes` → `excluded_stores` |
| `E_PERMISSION` (3, macOS) | Falta FDA | Ver [Permisos](#permisos) |
| `E_DEPENDENCY_MISSING` / `E_CLIENT_UNSUPPORTED` (3, Windows) | Falta `pywin32` / no es Outlook clásico 16.0 | `pipx reinstall mailquery` / instala Outlook clásico |
| `E_OUTLOOK_NOT_RUNNING` (6) | Outlook cerrado, o sesión o integridad distintas | Abre Outlook clásico con el mismo usuario y sin elevar; reintenta |
| `E_CLIENT_TIMEOUT` (3) | Outlook no respondió en 30 s (posible aviso de seguridad) | Revisa `mailquery doctor` antes de reintentar |
| `E_DB_BUSY`, `E_LOCKED`, `E_CLIENT_BUSY` (5) | Store, lock u Outlook ocupados | Reintenta una vez tras una pausa; no lances corridas concurrentes |
| `E_STATE_CORRUPT` (3) | `state.json` dañado (solo afecta a `new`) | Renómbralo; la siguiente corrida de `new` será una primera corrida y volverá a emitir la ventana de `lookback` |
| `E_UNBOUNDED_SCAN` / `E_SCAN_TOO_LARGE` (4) | `--text` sin acotar / demasiados candidatos | Añade `--since` u otro filtro, o sube `search.max_scan` (máx. 50000) |
| `E_INTERNAL` (1) | Fallo inesperado | Revisa `~/.mailquery/logs/mailquery.log` con `--log-level debug` |

## Licencia

MIT. Copyright (c) 2026 Ariel Dayler Salzar Hinojosa. Consulta
[`LICENSE`](LICENSE) para el texto completo.

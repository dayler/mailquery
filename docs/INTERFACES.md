# Interfaz interna y reglas de trabajo — mailquery v1

Documento de coordinación para el equipo de implementación. El **PRD** oficial
está en [`docs/PRD.md`](PRD.md) y manda sobre este documento; aquí se fijan los
contratos concretos entre módulos y el reparto de archivos para trabajar en
paralelo sin colisiones.

## 1. Layout del repositorio (layout `src/`)

```text
mailquery/                          # raíz del repo (https://github.com/dayler/mailquery)
├── README.md                       # instalación, FDA, ejemplos, contratos (español)
├── LICENSE                         # MIT (Ariel Dayler Salzar Hinojosa, 2026)
├── pyproject.toml                  # console script `mailquery`, sin dependencias runtime
├── .gitignore                      # .obsidian/, __pycache__/, fixtures generados
├── docs/
│   ├── PRD.md                      # PRD v0.9 (movido aquí)
│   ├── INTERFACES.md               # este documento
│   └── recipes/                    # recetas/preceptos para el harness
│       ├── 01-new-mail-digest.md
│       └── 02-search-invoices.md
├── src/mailquery/                  # paquete Python (código en inglés)
│   ├── __init__.py                 # __version__ = "1.0.0"
│   ├── __main__.py                 # python3 -m mailquery
│   ├── errors.py                   # MailqueryError + códigos E_* / exit codes
│   ├── output.py                   # JSON estable, snippets, fechas ISO, sanetización
│   ├── logging_setup.py            # log texto con rotación diaria
│   ├── config.py                   # config.toml + resolución de alcance
│   ├── accounts.py                 # etiquetas de cuenta (Accounts4.sqlite ro)
│   ├── store.py                    # Envelope Index ro + mapeo de mailboxes
│   ├── emlx.py                     # resolución uid->ruta + parseo .emlx
│   ├── search.py                   # search/new/show/mailboxes (no renderiza JSON)
│   ├── state.py                    # cursor + anillo + lock
│   └── cli.py                      # argparse, dispatch, stdout/stderr, exit codes
└── tests/
    ├── __init__.py                 # añade src/ a sys.path
    ├── fixtures/
    │   ├── __init__.py
    │   ├── make_fixtures.py        # store sintético V10 + Envelope Index + Accounts4
    │   └── expected/*.json         # goldens normalizados
    ├── mocks/                      # helpers unittest.mock (TCC, DB busy, esquema roto)
    ├── test_config.py
    ├── test_store.py
    ├── test_accounts.py
    ├── test_emlx.py
    ├── test_search.py
    ├── test_state.py
    ├── test_cli.py
    ├── test_readonly.py            # obligatorio y bloqueante
    └── test_integration.py
```

Reglas globales:

- **Código en inglés** (identificadores, comentarios, docstrings, mensajes de
  log, nombres de tests). **Documentación en español** (README, docs/, recetas).
- Solo **biblioteca estándar** de Python ≥ 3.11. Sin red, sin dependencias
  runtime, sin AppleScript/osascript, sin tocar `~/Library/Mail` en lectura de
  escritura. Invariante I-1 (PRD §4).
- Comando de tests (desde la raíz del repo):

  ```bash
  python3 -m unittest discover -s tests -t . -v
  python3 -m unittest tests.test_store -v          # un módulo
  ```

- **No ejecutar comandos git** (ramas, commits, merges, push): los gestiona el
  Lead. Tampoco ejecutar comandos que escriban en `~/.mailquery` real ni en
  `~/Library/Mail`.
- Cada persona escriba **solo** los archivos de su tarea. Si necesita cambiar
  una firma pública o el JSON, avisar al Lead antes de tocarla.
- No hay `pytest`: solo `unittest` + `unittest.mock`.

## 2. Dirección de dependencias (sin ciclos)

```text
errors  output  logging_setup        (base, sin imports internos)
      ↑       ↑
   accounts  state
      ↑        ↑
    store     config
      ↑        ↑
      emlx    search ──→ store, emlx, config, accounts, state, output, errors
                  ↑
                 cli ──→ todos
```

`config` importa `accounts`/`store` solo bajo `TYPE_CHECKING`; sus funciones
públicas reciben esos objetos como argumentos. `search` importa `store`, `emlx`,
`config`, `accounts`, `state`, `output` y `errors`. `cli` es el único que
escribe `stdout`/`stderr` y el único que decide exit codes.

## 3. Contratos de módulos (firmas estables)

Los stubs actuales en `src/mailquery/` son el contrato. Se pueden añadir helpers
privados (`_foo`) libremente; **no cambiar** las firmas públicas sin avisar.

### `errors.py`
`MailqueryError(code, message, hint="")` con `.code`, `.message`, `.hint`,
`.exit_code` y `.to_payload(command)`. `CODE_EXIT` mapea cada `E_*` al exit
documentado (PRD 12.6). Helpers: `usage_error`, `config_error`, `bad_time`,
`bad_filter`, `exit_code_for`.

### `output.py`
`dumps_json`, `write_json`, `iso_timestamp(epoch)`, `now_iso()`,
`sanitize_text(text, max_chars=None)`, `make_snippet(body_text, max_chars=200)`.
Fechas ISO 8601 en hora local con offset. JSON compacto (`separators=(",", ":")`,
`ensure_ascii=False`). `sanitize_text` quita ANSI y caracteres de control (deja
`\n` y `\t`). `make_snippet`: una línea, máximo 200 caracteres contando el `…`.

### `logging_setup.py`
`setup_logging(home, level="info", retention_days=7) -> run_id`.
`get_logger(name) -> LoggerAdapter` con `run_id` en el formato.
`~/.mailquery/logs/mailquery.log`, 0600, `TimedRotatingFileHandler(when="midnight",
backupCount=retention_days)`. **Nunca** logear asunto, cuerpo, direcciones,
nombres ni términos de búsqueda.

### `accounts.py`
`AccountLabel(uuid, label, email=None, provider=None, local=False)`.
`AccountLabels(db_path=None, tmp_dir=None)` con `.available`, `.all()`,
`.get(uuid)`, `.label_for(uuid)`; `default_accounts_db_path()`.
Etiqueta: cuenta IMAP/Exchange → `"{proveedor} ({email})"` usando el **padre**
(`ZPARENTACCOUNT` → `ZACCOUNTTYPE.ZACCOUNTTYPEDESCRIPTION` +
`ZACCOUNT.ZUSERNAME`); cuenta local (`On My Device`) → `"On My Device"`.
Lectura `file:...?mode=ro` + `PRAGMA query_only=ON`; si falta `-shm` copia a
`tmp_dir`; si la base no está, `.available=False` y `label_for()` devuelve el
UUID con warning. Feature-detección de columnas; nunca lee credenciales.

### `store.py`
`StoreVersion(mail_root, version, version_uuid, data_dir, envelope_index)`.
`Mailbox(rowid, url, name, path, account_uuid, account_kind, is_inbox,
is_aggregate, message_count, unread_count)`.
`EnvelopeStore(version, connection, strategy, tmp_dir=None)` con `.mailboxes`,
`.mailbox(rowid)`, `.mailbox_dir(mailbox)`, `.resolve_mailbox(account_uuid,
ref)`, `.fingerprint()`, `.close()`; `open_store(mail_root=None,
tmp_root=None)`; `detect_version(mail_root=None)`.
`REQUIRED_COLUMNS` es el fingerprint exacto que debe existir (ver stub).
Estrategias: `live_ro` (existe `-shm`) o `copy_ro` (se copia `Envelope Index` +
`-wal` a `tmp_root`). `mailbox.name` = último segmento del path decodificado;
`mailbox.path` = path completo decodificado (`[Gmail]/All Mail`); INBOX de
Gmail se marca `is_inbox=True`; `is_aggregate` = path que contiene `all mail`.
Contadores **recalculados** desde `messages` + `labels` (los de `mailboxes` no
son fiables). `mailbox_dir` = `mail_root/version/account_uuid/` + segmentos
`.mbox` (los `[` y `]` son literales, sin `glob`); NFC/NFD como fallback.

### `emlx.py`
`EmlxMessage(path, partial, headers, body_text, attachments, available,
readable, warnings)`.
`resolve_path(store, mailbox, uid) -> Path | None`: fórmula
`<mailbox_dir>/<version_uuid>/Data/<shards>/Messages/<uid>.emlx` (o
`.partial.emlx`), `shards` = dígitos de `uid // 1000` del menos al más
significativo (`uid < 1000` → `Data/Messages/`). Fallback recursivo solo si la
fórmula falla; si no existe → `None`. `parse_emlx(path)` lee con
`open(path, "rb")`, `int(line1.strip())`, payload MIME y trailer plist; texto
plano preferente, HTML→texto (`html_to_text`), nombres de adjuntos; corrupto →
`readable=False` + warning; `partial` por nombre `.partial.emlx`.

### `state.py`
`Cursor(last_date_received, last_uid, lookback_seconds=600)`,
`LastRun(command, at)`, `AppState(schema=1, updated_at="", last_run=None,
cursor=None, emitted_uids=())`.
`StateStore(home)` con `.path`, `.load()`, `.save(state)`, `.record_new(state,
emitted, command="new")`; `RunLock(home)` context manager (`acquire/release`).
`state.json` 0600, escritura `tmp + fsync + os.replace`; corrupción →
`E_STATE_CORRUPT`; anillo máximo 1.000 uids; sin PII.

### `config.py`
`LoggingConfig`, `SearchConfig`, `NewConfig`, `ScopeEntry`, `Config`,
`ResolvedScope(account_uuid, account_label, account_email, mailboxes)`.
`app_home()`, `ensure_app_home(home)`, `parse_duration(value)`,
`load_config(home=None)`, `resolve_scope(config, store, labels)`.
Validación estricta: cualquier clave/sección desconocida ⇒ `E_CONFIG_INVALID`.
`[scope."<cuenta>"]` declara una cuenta observada; INBOX siempre incluida;
`mailbox_list` aditivo. Resolver la cuenta por etiqueta → email único → UUID o
prefijo único ≥ 8 (errores `E_CONFIG_ACCOUNT_UNKNOWN`, `E_ACCOUNT_AMBIGUOUS`,
`E_ACCOUNT_LABELS_UNAVAILABLE`, `E_MAILBOX_NOT_FOUND`). `parse_duration`
min/h/d, 1 min–1 día (para `[new].lookback`).

### `search.py`
`Filters(...)`, `ScanStats`, `parse_relative_time(value, now=None)`,
`wildcard_to_regex(pattern)`, `matches(pattern, text)`,
`run_search(store, config, labels, filters)`,
`run_new(store, config, labels, state_store, *, peek=False, limit=None)`,
`run_show(store, labels, uid)`,
`run_mailboxes(store, config, labels)`.
Devuelven los campos de comando **sin** `ok`/`command`/`generated_at` (los
añade `cli`). Semántica de fechas: `--since` incluye, `--until` excluye.
Orden total: `search` = `(date_received DESC, ROWID DESC)`; `new` = ASCENDENTE
`(date_received ASC, uid ASC)` para que "el cursor avanza hasta el último
emitido" sea el más reciente (PRD 12.3). Dedupe por `global_message_id` con
prioridad INBOX > carpeta normal > buzón agregado; `duplicate_count` = copias
en el alcance (≥ 1); límites y `truncated`/`hint` según PRD 12.2/12.3.
`--text` obliga a acotamiento (ver §6) y máximo de candidatos (`[search].max_scan`).

### `cli.py`
`build_parser()`, `main(argv=None, *, home=None, mail_root=None,
accounts_db=None) -> int`. Los 3 kwargs son **solo para tests** (no son flags ni
variables de entorno del contrato). `-h/--help` en texto y exit 0; `--log-level`
global; JSON de error en `stdout` + resumen humano en `stderr`; exit codes
según `errors.CODE_EXIT`; lock automático; `doctor` devuelve exit 0 y muestra
un **informe de texto human-readable** por defecto (`--json` para el payload
máquina) aunque algún chequeo falle (decisión del usuario).

## 4. Contrato JSON

### Éxito (base)
```json
{"ok": true, "command": "search", "generated_at": "<ISO local>", "...": "campos del comando", "warnings": []}
```
Los warnings son strings `"W_CODIGO: detalle"`. Códigos previstos:
`W_NO_ACCOUNTS`, `W_FIRST_RUN`, `W_ACCOUNT_LABELS_UNAVAILABLE`,
`W_EMLX_MISSING`, `W_EMLX_CORRUPT`, `W_EMLX_UNREADABLE`, `W_HTML_NO_TEXT`,
`W_BODY_TRUNCATED`, `W_ATTACHMENTS_UNAVAILABLE`, `W_RESULTS_TRUNCATED`.

### `search`
```json
{"count": 1, "truncated": false, "hint": null,
 "messages": [<message>],
 "scan": {"mode": "metadata", "candidates": 1, "messages_read": 1, "duration_ms": 211}}
```
`hint` (RF-15) es `null`/ausente cuando `truncated=false`; cuando
`truncated=true` es un string accionable, p. ej. `"refina los filtros o sube
--limit (máx. 200)"`, y además se emite
`W_RESULTS_TRUNCATED: <N> more messages match; refine the filters or raise --limit`.

### `new`
Igual que `search` más:
```json
{"cursor": {"previous": {"last_date_received": 0, "last_uid": 0, "lookback_seconds": 600}, "current": {"...": 1}}}
```
`previous`/`current` pueden ser `null`.

### `show`
```json
{"message": {"uid": 83143, "message_id": "...", "subject": "...",
  "from": {"name": "", "address": ""}, "to": [{"name": "", "address": ""}],
  "cc": [], "date_sent": "<ISO>", "date_received": "<ISO>",
  "mailbox": {"account": {"uuid": "", "label": "", "email": ""},
              "name": "INBOX", "path": "INBOX", "url": "imap://..."},
  "is_read": false, "is_flagged": false, "has_attachments": false,
  "size_bytes": 202913,
  "headers": {"From": "", "To": "", "Cc": "", "Subject": "", "Date": "", "Message-ID": ""},
  "body_text": "", "body_truncated": false,
  "attachments": [{"name": "..."}],
  "partial": true, "readable": true,
  "source": {"emlx_path": "/...", "partial": true}}}
```

### `mailboxes`
```json
{"accounts": [{"uuid": "...", "label": "iCloud (x@y)", "email": "x@y", "declared": true}],
 "mailboxes": [{"account": {"uuid": "...", "label": "...", "email": "..."},
                "name": "INBOX", "path": "INBOX", "url": "imap://...",
                "total": 9734, "unread": 2, "included": true}]}
```

### `doctor`
Por defecto: **informe de texto human-readable** en `stdout` (mismo estilo que
`--help`: cabecera, `Checks:` alineado, `Result:` y `Notes:`, sin colores),
siempre exit 0 si puede diagnosticar. Con `--json`, payload máquina:

```json
{"checks": [{"name": "store", "ok": true, "detail": "V10 ..."}]}
```

Chequeos mínimos: `python`, `home`, `store`, `envelope_index`, `schema`,
`readonly_strategy`, `accounts_db`, `config`, `state`, `lock`. El chequeo
`config` valida el TOML y **la resolución de cada bloque `[scope]` y su
`mailbox_list`** contra el store y las etiquetas de cuenta (por entrada, con el
`code`/`hint` de cada error); distingue config ausente de config presente sin
`[scope]`.

### Error
```json
{"ok": false, "command": "search", "error": {"code": "E_UNBOUNDED_SCAN", "message": "...", "hint": "..."}}
```
Sin `generated_at` (contrato de error del PRD 12.5).

### Mensaje (`search`/`new`)
```json
{"uid": 83143, "message_id": "<...>", "duplicate_count": 1, "subject": "...",
 "from": {"name": "", "address": ""}, "to": [{"name": "", "address": ""}], "cc": [],
 "date_sent": "<ISO>|null", "date_received": "<ISO>|null",
 "mailbox": {"account": {"uuid": "", "label": "", "email": ""}, "name": "INBOX", "path": "INBOX", "url": "imap://..."},
 "is_read": false, "is_flagged": false, "has_attachments": false, "size_bytes": 0,
 "snippet": "", "body": {"available": true, "partial": false, "truncated": false}}
```
`message_id` = `message_global_data.message_id_header` (vacío `""` si falta).
`body.available` = existe y se pudo abrir el `.emlx`; `body.partial` = es
`.partial.emlx`; `body.truncated` = el snippet se recortó a 200.

## 5. Decisiones cerradas con el usuario (2026-11-02)

1. Layout `src/` + `docs/` dentro del repositorio.
2. Git flow emulado (`main` + `develop` + `feature/*` + `release/*`), push de
   `main` y `develop` al final.
3. Validación solo con fixtures sintéticos (nunca el store real).
4. Licencia MIT, titular `Ariel Dayler Salzar Hinojosa`, año 2026.
5. **Primera corrida de `new`** (sin `state.json`): baseline sin emisión; fija
   el cursor en el mensaje más reciente del alcance, siembra el anillo
   `emitted_uids` con los uids del alcance dentro de la ventana
   `[cursor_date - lookback, cursor_date]` (para que la siguiente corrida no
   los re-emita) y emite `W_FIRST_RUN`. Con cursor existente: candidatos
   `date_received >= cursor.last_date_received - lookback` menos el anillo,
   orden `(date_received, uid)`, límite de la corrida, cursor avanza hasta el
   último emitido y los uids emitidos entran al anillo; `--peek` no avanza el
   cursor ni escribe estado.
6. **Términos de filtro**: si el valor **no** tiene comodines, se parte por
   espacios y cada término es AND; si tiene `*`/`?`, el valor entero es un
   patrón único (permite frases). Repetir un flag también es AND.
7. **Acotamiento de `--text`**: solo acotan `--since/--until/--from/--to/--cc/
   --subject` o carpetas extra (`--include-mailbox` o `mailbox_list` que añada
   algo distinto de INBOX). `--text` sobre solo INBOX del alcance ⇒
   `E_UNBOUNDED_SCAN`; más de `max_scan` candidatos ⇒ `E_SCAN_TOO_LARGE`.
8. **`doctor`**: siempre exit 0 si puede diagnosticar; por defecto muestra un
   informe de texto human-readable (estilo `--help`) y con `--json` el detalle
   `checks[].ok/detail`.

## 6. Fixtures sintéticos (`tests/fixtures/make_fixtures.py`)

API estable:

```python
from tests.fixtures.make_fixtures import build_store, FixturePaths, write_config

fx = build_store()            # crea un directorio temporal; fx.root
fx = build_store(Path(tmp))   # idempotente si se reutiliza un root vacío
# fx: root, mail_root, home, accounts_db, envelope_index, version_uuid,
#     mailboxes (dict nombre->rowid), messages (lista FixtureMessage)
write_config(fx.home, '[scope."iCloud (fixture@icloud.com)"]\nmailbox_list = ["Facturas"]\n')
```

Contenido (suficiente para todos los tests):

- Versión `V10`, uuid `11111111-2222-4333-8444-555555555555`.
- Cuentas: iCloud IMAP (`AAAAAAAA-…0001` → `iCloud (fixture@icloud.com)`),
  Gmail IMAP (`BBBB…0002` → `Gmail (fixture@gmail.com)`), local
  (`CCCC…0003` → `On My Device`), con `Accounts4.sqlite` mínimo en
  `fx.accounts_db`.
- Mailboxes iCloud: `INBOX` (1), `Facturas` (2), `Archivo` (3).
  Gmail: `INBOX` (5, membresía por `labels`), `[Gmail]/All Mail` (6),
  `[Gmail]/Important` (7). Local: `Recovered Messages` (8).
- Mensajes (uids): 830 texto antiguo; 2714 texto+HTML+adjunto no leído;
  79658 `.partial.emlx` en Facturas; 83142 y 83143 duplicados del mismo
  `global_message_id` (INBOX gana); 83150 flagged; 83160 y 83210 en Gmail
  INBOX vía `labels`; 83170 sin `.emlx` (cuerpo no disponible); 83180
  `.emlx` corrupto; 83190 correo muy antiguo; 83200 solo HTML; 83220 sin
  `message_id_header`; 99999 `.emlx` huérfano sin fila.
- Fechas relativas a `datetime.now()` al construir el fixture.
- El `Envelope Index` usa **solo** las tablas/columnas de
  `store.REQUIRED_COLUMNS` (+ `mailboxes.source` y contadores falsos a
  propósito para probar el recálculo).

## 7. Reparto de propiedad de archivos

| Persona | Archivos (write scope) |
|---------|------------------------|
| Lead | raíz (README*, LICENSE, pyproject, .gitignore), docs/**, `src/mailquery/{__init__,__main__,errors,output,logging_setup}.py`, `tests/fixtures/make_fixtures.py`, integración y git |
| store-dev | `src/mailquery/store.py`, `src/mailquery/accounts.py`, `tests/test_store.py`, `tests/test_accounts.py` |
| emlx-dev | `src/mailquery/emlx.py`, `tests/test_emlx.py` |
| search-dev | `src/mailquery/search.py`, `tests/test_search.py` |
| cli-config-dev | `src/mailquery/config.py`, `src/mailquery/cli.py`, `tests/test_config.py`, `tests/test_cli.py` |
| state-fixtures-dev | `src/mailquery/state.py`, `tests/test_state.py`, `tests/mocks/**`, `tests/test_readonly.py`, `tests/test_integration.py`, `tests/fixtures/expected/**` |
| docs-dev | `README.md`, `docs/recipes/**` |

`README.md` lo escribe docs-dev (el Lead deja un borrador); el PRD no se toca.

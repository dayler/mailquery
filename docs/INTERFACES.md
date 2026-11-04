# Interfaz interna y reglas de trabajo — mailquery 2.0.0

Documento de coordinación para el equipo de implementación y guía de
desarrollo. El **PRD** oficial está en [`docs/PRD.md`](PRD.md) (v1.x) y manda
sobre este documento, junto con los anexos por backend
([`docs/backends/apple-mail.md`](backends/apple-mail.md) y
[`docs/backends/outlook-windows.md`](backends/outlook-windows.md)); aquí se
fijan los contratos concretos entre módulos, el layout del repositorio y las
reglas de trabajo (pruebas, fixtures, goldens, git, CI).

## 1. Layout del repositorio (layout `src/`)

```text
mailquery/                          # raíz del repo (https://github.com/dayler/mailquery)
├── README.md                       # instalación, FDA, ejemplos, contratos (español)
├── LICENSE                         # MIT (Ariel Dayler Salzar Hinojosa, 2026)
├── pyproject.toml                  # console script `mailquery`, sin dependencias runtime
├── .gitignore                      # .obsidian/, __pycache__/, fixtures generados
├── .github/workflows/tests.yml     # CI: suite en 3 SO × Python 3.11–3.14 + instaladores
├── docs/
│   ├── PRD.md                      # PRD v1.x: núcleo común a ambas plataformas
│   ├── backends/
│   │   ├── apple-mail.md           # anexo A: Apple Mail (macOS)
│   │   └── outlook-windows.md      # anexo B: Outlook clásico (Windows)
│   ├── INTERFACES.md               # este documento
│   ├── plans/                      # planes de implementación
│   └── recipes/                    # recetas/preceptos para el harness
│       ├── 01-new-mail-digest.md
│       └── 02-search-invoices.md
├── src/mailquery/                  # paquete Python (código en inglés)
│   ├── __init__.py                 # __version__
│   ├── __main__.py                 # python3 -m mailquery
│   ├── errors.py                   # MailqueryError + códigos E_* / exit codes
│   ├── output.py                   # JSON formateado, snippets, fechas ISO, sanetización, html_to_text
│   ├── logging_setup.py            # log texto con rotación por tamaño
│   ├── config.py                   # config.toml + resolución de alcance (vía MailBackend)
│   ├── search.py                   # search/new/show/mailboxes (no renderiza JSON; vía MailBackend)
│   ├── state.py                    # cursor + anillo + lock
│   ├── cli.py                      # argparse, dispatch, stdout/stderr, exit codes
│   ├── accounts.py                 # Apple Mail: etiquetas de cuenta (Accounts4.sqlite ro)
│   ├── store.py                    # Apple Mail: Envelope Index ro + mapeo de mailboxes
│   ├── emlx.py                     # Apple Mail: resolución uid->ruta + parseo .emlx
│   └── backends/
│       ├── __init__.py             # get_backend(...), backend_class(...)
│       ├── base.py                 # MailBackend (ABC), filas TypedDict, StateUidError, ExcludedStoreError
│       ├── apple_mail.py           # AppleMailBackend (SQL + helpers de Apple Mail)
│       ├── outlook.py              # OutlookBackend: stores, carpetas, items y cuerpos (sin win32com)
│       └── outlook_com.py          # único módulo que importa win32com: detección, proxy, vigilante
└── tests/
    ├── __init__.py                 # añade src/ a sys.path
    ├── fixtures/
    │   ├── __init__.py
    │   ├── make_fixtures.py        # store sintético V10 + Envelope Index + Accounts4
    │   └── expected/               # goldens normalizados: *.json (Apple Mail), outlook/*.json
    ├── mocks/                      # helpers unittest.mock (TCC, DB busy, esquema roto)
    ├── fakes/
    │   ├── outlook.py              # Outlook falso en memoria (OOM, CallLog, escenarios)
    │   └── run_cli.py              # lanzador en subprocess: fake + cli.main(argv, backend=…)
    ├── test_backends.py            # contrato de MailBackend, get_backend, AppleMailBackend
    ├── test_outlook.py             # backend Outlook sobre el fake (casos OL-*)
    ├── test_config.py
    ├── test_store.py
    ├── test_accounts.py
    ├── test_emlx.py
    ├── test_output.py
    ├── test_logging.py
    ├── test_search.py
    ├── test_state.py
    ├── test_cli.py
    ├── test_readonly.py            # obligatorio y bloqueante
    ├── test_integration.py         # flujos completos y goldens
    └── test_install_scripts.py     # instaladores (install.sh / install.ps1)
```

`outlook.py`, `outlook_com.py` y `tests/fakes/` llegan en la fase W3: con ellos
`get_backend(platform="win32")` da `mailboxes`, `search` (metadatos) y `show`;
`new`, `--text`/`--to`/`--cc` y `doctor` de Outlook son de la fase W4.

Reglas globales:

- **Código en inglés** (identificadores, comentarios, docstrings, mensajes de
  log, nombres de tests). **Documentación en español** (README, docs/, recetas).
- Solo **biblioteca estándar** de Python ≥ 3.11, con una excepción: `pywin32`
  (solo Windows), que **únicamente** puede importar
  `src/mailquery/backends/outlook_com.py`. Sin red, sin AppleScript/osascript,
  sin escribir nada en `~/Library/Mail` ni en el cliente de correo. Invariante
  I-1 (PRD §4).
- Pruebas: ver §8 (comandos, convención de nombres, fixtures, goldens y CI).

- **Git (D-01):** el orquestador crea la rama de cada fase y hace los commits;
  los subagentes que corren en paralelo trabajan en su propio worktree y el
  orquestador integra su trabajo en la rama de la fase. Los merges a `develop`
  y los tags los hace o autoriza el dueño tras la revisión del planificador.
- No ejecutar comandos que escriban en `~/.mailquery` real ni en
  `~/Library/Mail`.
- Cada persona escriba **solo** los archivos de su tarea. Si necesita cambiar
  una firma pública o el JSON, avisar al Lead antes de tocarla.
- No hay `pytest`: solo `unittest` + `unittest.mock`.

## 2. Dirección de dependencias (sin ciclos)

```text
errors  logging_setup  output          (base, sin imports internos)
   ↑          ↑           ↑
   │       backends/base (solo stdlib: MailBackend, StateUidError, ExcludedStoreError, Uid)
   │          ↑
   │       state (→ base, errors, output)      config (→ errors; MailBackend solo en TYPE_CHECKING)
   │          ↑                                   ↑
   │          │                                   │
accounts, store, emlx   (Apple Mail; → errors, logging_setup, output)
        ↑
backends/apple_mail (→ base, emlx, accounts, store, errors)
backends/outlook_com (→ errors, logging_setup; win32com/pythoncom/pywintypes perezosos;
                      config y cli solo dentro de funciones)
backends/outlook (→ base, outlook_com, output, errors)
        ↑
backends/__init__ ──→ apple_mail | outlook (import perezoso solo en win32)
        ↑
       cli ──→ backends, config, errors, logging_setup, output, search, state

search (→ config, output, errors, state, backends/base [ExcludedStoreError];
        MailBackend solo en TYPE_CHECKING)
   ↑
  cli
```

Reglas:

- `search.py` y `config.py` solo conocen la interfaz `MailBackend`
  (`backends/base.py`): no importan `store`, `emlx`, `accounts`, `apple_mail`
  ni `outlook*`, y no usan `sqlite3`.
- `store.py`, `emlx.py` y `accounts.py` (Apple Mail) solo los importa
  `backends/apple_mail.py`.
- `state.py` importa `StateUidError` y `Uid` de `backends/base.py` y recibe la
  validación de uids como argumento (`validate_uid`); no importa ningún
  backend concreto.
- `backends/__init__.py` elige el backend por plataforma e **importa
  `outlook` solo en `win32`** (import perezoso dentro de la función): ninguna
  otra plataforma importa jamás `win32com`.
- **Solo `backends/outlook_com.py` puede importar `win32com`**; `outlook.py` y
  el resto del paquete no.
- `cli` es el único que escribe `stdout`/`stderr`, el único que decide exit
  codes y el único que construye el backend (`get_backend`) y lo cierra.

## 3. Contratos de módulos (firmas estables)

El código actual en `src/mailquery/` es el contrato. Se pueden añadir helpers
privados (`_foo`) libremente; **no cambiar** las firmas públicas sin avisar.
Las filas que cruzan la interfaz de backend son `dict` tipados con
`TypedDict` y conservan los nombres de campo de `search.py` (PRD §9.3, §11.1).

### `errors.py`
`MailqueryError(code, message, hint="", log_message=None)` con `.code`,
`.message`, `.hint`, `.log_message`, `.exit_code` y `.to_payload(command)`.
`log_message` es el mismo texto sin los datos que el PRD §14 prohíbe en el log
(rutas, carpetas, cuentas, términos, uids); el log escribe `log_message` si
existe y `message` si no. Un código desconocido se degrada a `E_INTERNAL`.
`CODE_EXIT` mapea cada `E_*` al exit documentado (PRD §12.6, exits 0–6;
`E_OUTLOOK_NOT_RUNNING` = 6). Helpers: `usage_error(message, hint="",
log_message=None)`, `config_error(...)` (misma firma), `bad_time(value)`,
`bad_filter(message, hint="")`, `exit_code_for(code)` y
`error_detail(exc) -> str` (detalle de una línea para `doctor`:
`CODE: message` o `Tipo: texto`).

### `output.py`
`dumps_json(payload) -> str`, `write_json(payload)`, `configure_streams()`,
`iso_timestamp(epoch) -> str | None`, `now_iso()`,
`sanitize_text(text, *, max_chars=None)`, `make_snippet(body_text,
max_chars=200)` y `html_to_text(html) -> str` (código común: lo usan `emlx.py`
y el backend Outlook).

- `dumps_json`: JSON **formateado** (indentación de 2 espacios, un campo por
  línea, `ensure_ascii=False`); `write_json` añade un único LF final.
- `configure_streams()`: fuerza UTF-8 y LF en `stdout`/`stderr` (RF-32), también
  con pipes en Windows; `cli.main` la llama al empezar.
- `iso_timestamp`: ISO 8601 en hora local con offset; `None`, valores ≤ 0 o no
  representables dan `None`. La zona local es `LOCAL_ZONE` (`None` = la del
  sistema): punto de inyección **solo para tests**, porque en Windows no hay
  `TZ`/`tzset` (los tests de Outlook y los goldens `outlook/` fijan una zona).
- `sanitize_text` quita ANSI y caracteres de control (deja `\n` y `\t`).
  `make_snippet`: una línea, máximo 200 caracteres contando el `…`.

### `logging_setup.py`
`setup_logging(home, level="info", max_size_mb=10) -> run_id`,
`get_logger(name="mailquery") -> LoggerAdapter` con `run_id` en el formato y
`current_run_id()`. `~/.mailquery/logs/mailquery.log` (0600, directorio 0700),
**rotación por tamaño** (`RotatingFileHandler`, `maxBytes = max_size_mb` MiB,
5 archivos rotados fijos; `max_size_mb` viene de `[logging].max_size_mb`).
**Nunca** logear asunto, cuerpo, direcciones, nombres ni términos de búsqueda.

### `backends/base.py`
`Uid = int | str` (entero en Apple Mail, hex en mayúsculas en Outlook).
`StateUidError(cursor_detail, ring_detail)` (subclase de `ValueError`): uid
inválido de `state.json`; cada backend aporta sus textos de `E_STATE_CORRUPT`.
`ExcludedStoreError(entry)` (subclase de `LookupError`): la lanza
`find_message` cuando el uid es de un store excluido (solo Outlook); `entry` es
su entrada `{label, path, reason}` de `excluded_stores()` y `search.run_show`
la convierte en `E_ACCOUNT_NOT_IN_SCOPE` con el motivo (PRD §12.4).

Filas `TypedDict` (el `id` de `MailboxRow` nunca sale en el JSON):

- `AccountRow(uuid, label, email, local)` + opcionales `store_index`,
  `labelled` (solo Apple Mail) y `excluded` (solo Outlook: la fila es un store
  excluido y el valor es su entrada `{label, path, reason}`; `uuid` es `None`
  si el store no se pudo leer). Las claves de `[scope]` resuelven también
  contra estas filas para reportarlas con `W_STORE_EXCLUDED` (PRD §15.3).
- `MailboxRow(id, account_uuid, name, path, url, is_inbox, is_aggregate, total,
  unread)`.
- `MessageRow(uid, global_message_id, subject, sender_name, sender_address,
  date_sent, date_received, mailbox_id, read, flagged, size, message_id,
  has_attachments)` (`total=False`) + opcional `message_class` (solo Outlook:
  `load_body` reconoce un S/MIME sin abrir el item).
- `AttachmentRow(name)`, `BodySource(emlx_path, partial)` y `BodyRow(available,
  readable, partial, headers, body_text, attachments, source, warnings)`.

`MailBackend` (ABC; PRD §9.3). Todo backend implementa:

| Miembro | Devuelve |
|---------|----------|
| `name` (propiedad) | `"apple_mail"` o `"outlook"` |
| `describe()` | dict de versión para el log y `doctor` |
| `accounts()` | `list[AccountRow]`: cuentas candidatas, base de `[scope]` |
| `labels_available` (propiedad) | `bool`; siempre `True` en Outlook |
| `mailboxes()` | `Sequence[MailboxRow]` (contadores = items buscables, sin borrados) |
| `excluded_stores()` | `[{label, path, reason}]`; siempre `[]` en Apple Mail |
| `resolve_mailbox(account_uuid, ref)` | `MailboxRow` o `None` (nombre, path, URL o alias `INBOX`, sin distinguir mayúsculas) |
| `query(mailbox_ids, since=None, until=None, unread=False, flagged=False, has_attachments=False, order="desc")` | `list[MessageRow]` en orden total `(date_received, uid)` |
| `membership(uids)` | `dict[Uid, set]`: carpetas de cada uid (dedupe y `mailbox` del resultado) |
| `duplicate_counts(mailbox_ids)` | `dict`: copias por clave global (`duplicate_count`) |
| `recipients(uids)` | `dict[Uid, Any]`: to/cc por uid |
| `attachment_names(uid)` | `list[str]` |
| `find_message(uid)` | `(MessageRow, MailboxRow o None)` o `None`; el núcleo comprueba que la cuenta esté declarada; uid de un store excluido ⇒ `ExcludedStoreError` |
| `load_body(row)` | `BodyRow`; nunca dispara descargas; S/MIME ⇒ `readable=False` sin leer el contenido |
| `parse_uid(text)` | uid del backend o `E_USAGE`; **no abre el cliente** ni importa `win32com` |
| `doctor_checks()` | chequeos propios del backend (los comunes los añade `cli.py`) |
| `close()` | libera la conexión SQLite o las referencias COM |

### `backends/__init__.py`
`get_backend(*, platform=None, outlook_app=None, registry=None,
security_center=None, pywin32=None, store=None, labels=None, mail_root=None,
accounts_db=None, tmp_root=None) -> MailBackend`: `win32` ⇒ `OutlookBackend`,
cualquier otra plataforma ⇒ `AppleMailBackend` (RF-26). `outlook_app`,
`registry`, `security_center` y `pywin32` son puntos de inyección de **solo
tests** para Outlook; `store`, `labels`, `mail_root`, `accounts_db` y
`tmp_root` son de Apple Mail.
`backend_class(*, platform=None) -> type[MailBackend]`: la clase que
construiría `get_backend`, sin instanciar ni abrir nada (permite usar
`parse_uid` antes de tocar el cliente de correo, PRD §12.4).
`tmp_root` (`<home>/tmp`) sirve a ambos: copias temporales de Apple Mail y
caché de `pywin32` de Outlook (`<tmp_root>/gen_py`). `cli` siempre lo pasa.
`outlook_app` es un *conector* (cualquier objeto con
`GetActiveObject(prog_id)`), que sustituye a `win32com.client` **por debajo**
del proxy de producción; `pywin32` (`True`/`False`) fija el resultado del
import (por defecto `True` si hay `outlook_app`, si no se intenta el import
real).

**Ganchos opcionales del núcleo** (fuera de la superficie de PRD §9.3; el
núcleo los busca con `getattr` y Apple Mail no los tiene):

| Gancho | Lo usa | Para qué |
|--------|--------|----------|
| `bind_command(command)` | `cli` antes de ejecutar | Outlook: el vigilante D-03 informa el comando en `E_CLIENT_TIMEOUT` |
| `mailboxes_without_counters()` | `config.listed_mailboxes` | Outlook: carpetas sin leer las tablas de contadores (`total`/`unread` = `None`) |
| `not_found_hint` (atributo) | `search.run_show` | Outlook: el hint de `message uid … was not found` remite a `excluded_stores` |
| `unreadable_attachments(row)` | `search.run_show` | Outlook: `(nombres, warning)` de un item ilegible: `[]` y `W_ATTACHMENTS_UNAVAILABLE` solo si `has_attachments` y no es S/MIME (PRD §12.10) |

### `backends/outlook.py`
`OutlookBackend(*, outlook_app=None, registry=None, security_center=None,
pywin32=None, tmp_root=None, watchdog=None)`: lo construye `get_backend` en
`win32` (`watchdog` sustituye al vigilante global `outlook_com.WATCHDOG`; solo
tests). No abre nada hasta el primer uso; toda llamada COM pasa por
`outlook_com`. Implementa §9.3 según el anexo B:

- Stores (§B.3): el perfil se clasifica una sola vez leyendo solo propiedades
  del store; candidatos vía `Account.DeliveryStore`; `account.uuid` = los 16
  bytes de `PR_RECORD_KEY` en formato UUID. `accounts()` devuelve también los
  excluidos (con `excluded`); `excluded_stores()` los lista en orden del
  perfil. De un store excluido nunca se leen carpetas ni items.
- Carpetas (§B.3, §B.4): recorrido en profundidad desde `GetRootFolder`; INBOX
  y carpetas de sincronización por función (`GetDefaultFolder`); `id` = el
  `EntryID` de la carpeta. `mailboxes()` cuenta `total`/`unread` con una tabla
  por carpeta (una vez por instancia); `mailboxes_without_counters()` y
  `resolve_mailbox` no leen tablas.
- Items (§B.4): `query` con `Folder.GetTable` (uid = `EntryID` permanente,
  fechas UTC, prefiltro DASL ensanchado y corte exacto en Python);
  `find_message` identifica el store por los bytes 4..20 del `EntryID`;
  `load_body` nunca descarga (S/MIME y solo cabeceras sin leer contenido).
- `parse_uid(raw) -> str` (estático): hex en mayúsculas o `E_USAGE`; puro.
- `describe()` conecta y devuelve `{backend: "outlook", version, strategy:
  "com_readonly", schema_ok: True}` para el log.
- `doctor_checks()`: fase W4.

### `backends/outlook_com.py`
Único módulo que importa `win32com`/`pythoncom`/`pywintypes`, siempre dentro
de funciones (importarlo en Linux o macOS no toca `pywin32`).

- `connect(*, outlook_app=None, registry=None, pywin32=None, gen_path=None,
  watchdog=None) -> ReadOnlyCom`: detección en el orden de PRD §12.6
  (`E_DEPENDENCY_MISSING` → `E_CLIENT_UNSUPPORTED` → `E_OUTLOOK_NOT_RUNNING`),
  solo con `GetActiveObject`; `import_pywin32(gen_path)` fija
  `win32com.__gen_path__` antes de importar `win32com.client`.
- `READONLY_MEMBERS` (`{tipo: {miembro: tipo devuelto o None}}`) y
  `ReadOnlyCom(target, kind, watchdog)`: proxy de lista blanca; cualquier otro
  miembro, asignación o nombre `_`/dunder ⇒ `E_INTERNAL` sin tocar COM.
- `Watchdog` y `WATCHDOG` (D-03): plazo `CALL_TIMEOUT_SECONDS` (30 s, punto de
  inyección) por llamada; `call_com(watchdog, call)` arma el plazo y reintenta
  una vez a los 100 ms un rechazo transitorio.
- Errores (§B.7): `hresult_of(exc)`, `map_com_error(exc)` y
  `ComCallError(hresult)` (`E_INTERNAL` con el HRESULT; el backend captura los
  esperados por `hresult`). `cli` registra todo `E_INTERNAL`, también este,
  con su traceback (PRD §14).
- Fuera del OOM, de solo lectura: `WinRegistry`, `get_drive_type(root)`
  (punto de inyección para rutas de red) y `WmiSecurityCenter`.

### `backends/apple_mail.py`
`AppleMailBackend(store=None, labels=None, *, mail_root=None,
accounts_db=None, tmp_root=None)`. Con `store`/`labels` ya abiertos los usa; con
las rutas abre el `EnvelopeStore` y las `AccountLabels` de forma perezosa en el
primer uso. Es dueño del store: `close()` lo cierra. Aloja el SQL y los
helpers de Apple Mail que antes vivían en `search.py`, con el mismo orden,
warnings y reintento (`store.run_query`). Extras propios (fuera de la
interfaz): `store`, `labels`, `connection`, `tables` (propiedades),
`prepare()` (valida la conexión y detecta las tablas) y dos métodos estáticos:

- `parse_uid(raw) -> int`: entero (`E_USAGE` si no); puro y sin I/O.
- `check_state_uid(uid) -> None`: regla de `state.json` (PRD §11.2): entero
  JSON ≥ 1, `bool` excluido; si no, lanza `StateUidError` con los detalles de
  `E_STATE_CORRUPT` de Apple Mail. No comparte código ni error con `parse_uid`.

### `accounts.py` (Apple Mail)
`AccountLabel(uuid, label, email=None, provider=None, local=False)`.
`AccountLabels(db_path=None, tmp_dir=None)` con `.available`, `.all()`,
`.get(uuid)`, `.label_for(uuid)`; `default_accounts_db_path()`.
Etiqueta: cuenta IMAP/Exchange → `"{proveedor} ({email})"` usando el **padre**
(`ZPARENTACCOUNT` → `ZACCOUNTTYPE.ZACCOUNTTYPEDESCRIPTION` +
`ZACCOUNT.ZUSERNAME`); cuenta local (`On My Device`) → `"On My Device"`.
Lectura `file:...?mode=ro` + `PRAGMA query_only=ON`; si falta `-shm` copia a
`tmp_dir`; si la base no está, `.available=False` y `label_for()` devuelve el
UUID con warning. Feature-detección de columnas; nunca lee credenciales.

### `store.py` (Apple Mail)
`StoreVersion(mail_root, version, version_uuid, data_dir, envelope_index)`.
`Mailbox(rowid, url, name, path, account_uuid, account_kind, is_inbox,
is_aggregate, message_count, unread_count)`.
`EnvelopeStore(version, connection, strategy, tmp_dir=None)` con `.mailboxes`,
`.mailbox(rowid)`, `.mailbox_dir(mailbox)`, `.resolve_mailbox(account_uuid,
ref)`, `.fingerprint()`, `.close()`; `open_store(mail_root=None,
tmp_root=None)`; `detect_version(mail_root=None)`; `probe_envelope_index(...)`
y `run_query(...)` (reintento ante `E_DB_BUSY`).
`REQUIRED_COLUMNS` es el fingerprint exacto que debe existir.
Estrategias: `live_ro` (existe `-shm`) o `copy_ro` (se copia `Envelope Index` +
`-wal` a `tmp_root`). `mailbox.name` = último segmento del path decodificado;
`mailbox.path` = path completo decodificado (`[Gmail]/All Mail`); INBOX de
Gmail se marca `is_inbox=True`; `is_aggregate` = path que contiene `all mail`.
Contadores **recalculados** desde `messages` + `labels` (los de `mailboxes` no
son fiables). `mailbox_dir` = `mail_root/version/account_uuid/` + segmentos
`.mbox` (los `[` y `]` son literales, sin `glob`); NFC/NFD como fallback.

### `emlx.py` (Apple Mail)
`EmlxMessage(path, partial, headers, body_text, attachments, available,
readable, warnings)`.
`resolve_path(store, mailbox, uid) -> Path | None`: fórmula
`<mailbox_dir>/<version_uuid>/Data/<shards>/Messages/<uid>.emlx` (o
`.partial.emlx`), `shards` = dígitos de `uid // 1000` del menos al más
significativo (`uid < 1000` → `Data/Messages/`). Fallback recursivo solo si la
fórmula falla; si no existe → `None`. `parse_emlx(path)` lee con
`open(path, "rb")`, `int(line1.strip())`, payload MIME y trailer plist; texto
plano preferente, HTML→texto con `output.html_to_text`, nombres de adjuntos;
corrupto → `readable=False` + warning; `partial` por nombre `.partial.emlx`.

### `state.py`
`Cursor(last_date_received, last_uid, lookback_seconds=600)`,
`LastRun(command, at)`, `AppState(schema=1, updated_at="", last_run=None,
cursor=None, emitted_uids=())`. `last_uid` y `emitted_uids` son `Uid`
(`int` o `str`), opacos para este módulo.
`StateStore(home, validate_uid)` con `.home`, `.path`, `.load()`,
`.save(state)` y `.record_new(state, emitted, lookback_seconds,
command="new")`. `validate_uid` es el `check_state_uid` del backend (D-05):
devuelve `None` si el uid es válido o lanza `StateUidError`, y `load` lo
traduce a `E_STATE_CORRUPT`. `record_new` **solo calcula** el estado nuevo
(`emitted` = pares `(date_received, uid)`; el cursor solo avanza; anillo de
1.000 uids, el más reciente al final) y **no lo guarda**: `search.run_new`
llama a `save` salvo con `--peek`. `RunLock(home)` es un context manager
(`acquire/release`). `state.json` 0600, escritura `tmp + fsync +
os.replace`; corrupción → `E_STATE_CORRUPT`; sin PII.

### `config.py`
`LoggingConfig(level, max_size_mb)`, `SearchConfig(default_limit, max_scan)`,
`NewConfig(default_limit, lookback, lookback_seconds)`, `ScopeEntry(key,
mailbox_list)`, `Config(home, logging, search, new, scopes)`,
`ResolvedScope(account_uuid, account_label, account_email, mailboxes)`.
`app_home()`, `ensure_app_home(home)`, `parse_duration(value)`,
`load_config(home=None)`, `resolve_scope(config, backend, excluded=None) ->
list[ResolvedScope]` (usa solo `MailBackend`: `accounts()`, `labels_available`,
`resolve_mailbox` y las carpetas de `listed_mailboxes`; nunca el store). Una
clave que resuelve a un store excluido (fila de `accounts()` con `excluded`)
no se lee ni entra en el resultado; si se pasa una lista en `excluded`, se le
añade su entrada `{label, path, reason}` una sola vez, en el orden de los
bloques (para `W_STORE_EXCLUDED`, PRD §15.3).
`listed_mailboxes(backend) -> list[MailboxRow]`: las carpetas cuando solo
importa su identidad (alcance, dedupe, presentación, hints):
`mailboxes_without_counters()` si el backend lo ofrece, si no `mailboxes()`.
Solo el comando `mailboxes` necesita los contadores (PRD §19, §B.9).
`include_mailbox_not_found(ref, account_uuids, backend)`: `E_MAILBOX_NOT_FOUND`
de `--include-mailbox` con las carpetas de las cuentas declaradas.
Validación estricta: cualquier clave/sección desconocida ⇒ `E_CONFIG_INVALID`.
`[scope."<cuenta>"]` declara una cuenta observada; INBOX siempre incluida;
`mailbox_list` aditivo. Resolver la cuenta por etiqueta → email único → UUID o
prefijo único ≥ 8 (errores `E_CONFIG_ACCOUNT_UNKNOWN`, `E_ACCOUNT_AMBIGUOUS`,
`E_ACCOUNT_LABELS_UNAVAILABLE`, `E_MAILBOX_NOT_FOUND`). `parse_duration`
min/h/d, 1 min–1 día (para `[new].lookback`).

### `search.py`
`Filters(...)`, `ScanStats`, `parse_relative_time(value, now=None)`,
`wildcard_to_regex(pattern)`, `matches(pattern, text)`,
`run_search(backend, config, filters)`,
`run_new(backend, config, state_store, *, peek=False, limit=None, clock=None)`,
`run_show(backend, config, uid)`, `run_mailboxes(backend, config)`.
Solo usan la interfaz `MailBackend`. `uid` de `run_show` es el que ya devolvió
`backend.parse_uid` (`cli` la llama antes de crear el home, PRD §12.4);
`state_store` es un `StateStore` creado con el `check_state_uid` del backend.
Devuelven los campos de comando **sin** `ok`/`command`/`generated_at` (los
añade `cli`); `run_mailboxes` devuelve `accounts`, `mailboxes`,
`excluded_stores` y `warnings`. Semántica de fechas: `--since` incluye,
`--until` excluye. Orden total: `search` = `(date_received DESC, uid DESC)`;
`new` = ASCENDENTE `(date_received ASC, uid ASC)` para que "el cursor avanza
hasta el último emitido" sea el más reciente (PRD §12.3). Dedupe por clave
global con prioridad INBOX > carpeta normal > buzón agregado;
`duplicate_count` = copias en el alcance (≥ 1); límites y `truncated`/`hint`
según PRD §12.2/§12.3. `--text` obliga a acotamiento (ver §5) y máximo de
candidatos (`[search].max_scan`). Los mensajes con fecha nula, ≤ 0 o futura
(respecto de `clock`) no entran en `new` ni mueven el cursor.
**Primera corrida de `new`** (PRD §12.3): sin cursor guardado emite, en orden
ascendente y respetando `--limit`, los mensajes de `[D − lookback, D]` (`D` =
fecha del más reciente válido del alcance) y añade `W_FIRST_RUN` al final de
`warnings`; el cursor avanza al último emitido (no hay baseline vacío).
`[new].lookback` de la config actual aplica de inmediato.
**Warnings de alcance** (todas las corridas de `search`, `new`, `show` y
`mailboxes`), en este orden (PRD §12.3, paso 6): `W_NO_ACCOUNTS` (si no queda
ninguna cuenta declarada legible; no aplica a `show`), un
`W_STORE_EXCLUDED: <etiqueta> at <ruta> is excluded: <reason>` (sin
` at <ruta>` si `path` es `null`) por cada cuenta declarada que es un store
excluido (PRD §15.3) y `W_ACCOUNT_LABELS_UNAVAILABLE`; después los de la
corrida y, en `new`, `W_FIRST_RUN` al final. `run_show` convierte
`ExcludedStoreError` en `E_ACCOUNT_NOT_IN_SCOPE` con el motivo.

### `cli.py`
`build_parser()`, `main(argv=None, *, home=None, mail_root=None,
accounts_db=None, backend=None) -> int`. Los 4 kwargs son **solo para tests**
(no son flags ni variables de entorno del contrato): `mail_root` o
`accounts_db` ⇒ Apple Mail en cualquier SO; `backend` = instancia ya construida
(el Outlook falso, desde W3); sin ellos, el backend de la plataforma
(`get_backend`). `-h/--help` y `-v/--version` en texto y exit 0; `--log-level`
global; JSON de error en `stdout` + resumen humano en `stderr`; exit codes
según `errors.CODE_EXIT`; lock automático; `parse_uid` de `show` antes de crear
el home; `bind_command(command)` del backend si existe; todo `E_INTERNAL`
(también un `MailqueryError`, p. ej. `ComCallError`) se registra en el log con
su traceback (solo los frames y el tipo: el mensaje ya va saneado en la línea
`event=error`), el resto de códigos sin traceback (PRD §14); `doctor` devuelve exit 0 y muestra un **informe de texto
human-readable** por defecto (`--json` para el payload máquina) aunque algún
chequeo falle (decisión del usuario).

## 4. Contrato JSON

Resumen de coordinación; el contrato completo es el PRD §12.5. Los ejemplos
están compactados en una línea por brevedad: la salida real es JSON
**formateado** (2 espacios, `output.dumps_json`) y siempre UTF-8. Los ejemplos
con `uid` entero e `imap://` son los de Apple Mail; en Outlook `uid` es un
string hex y `mailbox.url` es `outlook://...` (PRD §12.5, tabla de diferencias).

### Éxito (base)
```json
{"ok": true, "command": "search", "generated_at": "<ISO local>", "...": "campos del comando", "warnings": []}
```
Los warnings son strings `"W_CODIGO: detalle"`; el catálogo es el PRD §12.10.
Comunes: `W_NO_ACCOUNTS`, `W_FIRST_RUN`, `W_RESULTS_TRUNCATED`,
`W_BODY_TRUNCATED`, `W_HTML_NO_TEXT`, `W_BODY_UNREADABLE` (sustituye al antiguo
`W_EMLX_UNREADABLE`), `W_ATTACHMENTS_UNAVAILABLE`. Solo Apple Mail:
`W_ACCOUNT_LABELS_UNAVAILABLE`, `W_EMLX_MISSING`, `W_EMLX_CORRUPT`. Solo
Outlook: `W_BODY_NOT_LOCAL`, `W_STORE_EXCLUDED`.

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
                "total": 9734, "unread": 2, "included": true}],
 "excluded_stores": []}
```
`excluded_stores` (`[{label, path, reason}]`) existe en ambas plataformas y es
siempre `[]` en Apple Mail. En Outlook lista los stores excluidos en el orden
del perfil (p. ej. `{"label": "Exchange shared (Soporte)", "path": null,
"reason": "shared_mailbox"}`); `accounts[]` y `mailboxes[]` solo traen
candidatos.

### `doctor`
Por defecto: **informe de texto human-readable** en `stdout` (mismo estilo que
`--help`: cabecera, `Checks:` alineado, `Result:` y `Notes:`, sin colores),
siempre exit 0 si puede diagnosticar. Con `--json`, payload máquina:

```json
{"checks": [{"name": "store", "ok": true, "detail": "V10 ..."}]}
```

Chequeos comunes (los añade `cli.py`): `python`, `home`, `config`, `state`,
`lock`. Los del backend (`MailBackend.doctor_checks()`) en Apple Mail son
`store`, `envelope_index`, `schema`, `readonly_strategy`, `accounts_db`; los de
Outlook están en el PRD §12.8. El chequeo
`config` valida el TOML y **la resolución de cada bloque `[scope]` y su
`mailbox_list`** contra el store y las etiquetas de cuenta (por entrada, con el
`code`/`hint` de cada error); distingue config ausente de config presente sin
`[scope]` y, cuando no hay cuentas declaradas, lista las disponibles con el
formato `0 account block(s) declared; available: <label>, ...` sin activarlas.

### Error
```json
{"ok": false, "command": "search", "error": {"code": "E_UNBOUNDED_SCAN", "message": "...", "hint": "..."}}
```
Sin `generated_at` (contrato de error del PRD §12.5).

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

## 5. Decisiones cerradas con el usuario (2026-11-02) — histórico

Registro de las decisiones de la v1.x. Siguen vigentes los puntos 1–4 y 6–8;
el punto 5 describía la primera corrida de `new` de la v1.x y **está
sustituido** por el PRD v1.x §12.3 y §23.3 (ver `search.py` en §3).

1. Layout `src/` + `docs/` dentro del repositorio.
2. Git flow emulado (`main` + `develop` + `feature/*` + `release/*`), push de
   `main` y `develop` al final.
3. Validación solo con fixtures sintéticos (nunca el store real).
4. Licencia MIT, titular `Ariel Dayler Salzar Hinojosa`, año 2026.
5. **(Sustituida, histórico v1.x)** Primera corrida de `new` (sin
   `state.json`): baseline sin emisión; fijaba el cursor en el mensaje más reciente del alcance, siembra el anillo
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

Sustituye al punto 5 (PRD §12.3): sin cursor guardado, `new` emite los
mensajes recibidos en `[D − lookback, D]` (`D` = el más reciente del alcance),
añade `W_FIRST_RUN` al final de `warnings` y avanza el cursor al último
emitido; el anillo de uids y `--peek` se comportan como en cualquier corrida.

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

`build_store(root=None, *, now=None, extended=False)`: con `extended=True` añade
los casos límite documentados en `FixturePaths` (constantes `UID_*` y
`MAILBOX_*` del módulo): carpetas anidadas y con el mismo nombre
(`iCloud/Proyectos/Inbox`, `iCloud/Proyectos/Facturas`,
`iCloud/Clientes/Facturas`, una carpeta cuyo nombre es la ruta de otra), S/MIME
cifrado y firmado, `.emlx` ausente con fila de adjuntos, mensaje borrado,
`global_message_id` 0, duplicados entre cuentas, fechas nulas/0/no
representables/futuras, y el `Envelope Index` en modo WAL con `-wal` y `-shm`.
`now` fija el reloj del fixture (las fechas son relativas a él).

## 7. Reparto de propiedad de archivos (histórico, v1.x)

Reparto del equipo de la v1.x, conservado como referencia; en 2.0.0 el
trabajo se divide por fases y tareas del plan de implementación
(`docs/plans/`), no por esta tabla. Los módulos nuevos de `backends/` los
asigna cada tarea del plan.

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

## 8. Desarrollo y pruebas

### 8.1 Modo desarrollo (sin instalar)

Desde la raíz del repositorio, el mismo código y el mismo home
`~/.mailquery` que la instalación con pipx:

```bash
python3 -m mailquery doctor
python3 -m mailquery search --since 7d
python3 -m mailquery show 83143
```

No hay variables de entorno ni flags de ruta: la única configuración es
`~/.mailquery/config.toml`. Las rutas y el backend inyectables de `cli.main`
(`home`, `mail_root`, `accounts_db`, `backend`) existen solo para las pruebas.

### 8.2 Ejecutar la suite

Desde la **raíz del repositorio** (`python3` en macOS/Linux, `python` en
Windows):

```bash
python -B -m unittest discover -s tests -t .                       # suite completa
python -B -m unittest discover -s tests -t . -k ol_02_05           # un caso por ID
python -B -m unittest tests.test_store -v                          # un módulo
```

- Solo `unittest` + `unittest.mock` (no hay `pytest`).
- Flujo de trabajo: se corre la suite completa una vez; si algo falla, se
  itera solo sobre ese caso (`-k <grupo>_<caso>` o su ruta completa) y, antes
  de cerrar, se vuelve a correr la suite completa.
- **Convención de nombres:** un método por caso, llamado
  `test_<grupo>_<caso>_<descripcion>` en minúsculas y con `_` (por ejemplo
  `test_ol_02_05_no_instance_is_exit_6`); el ID del caso va también en el
  docstring. Por eso `-k <grupo>_<caso>` selecciona un caso concreto. Un test
  renombrado no se duplica.
- Las expectativas que dependen del SO van **dentro** del test como
  aserciones condicionales; solo se permiten los saltos documentados en el
  plan (§7.7: `InstallShTest` sin `sh`, `InstallPs1Test` sin PowerShell,
  etc.). Fuera de esos saltos el número de tests es el mismo en los 3 SO.
- **El test read-only es obligatorio y bloqueante** (`tests/test_readonly.py`):
  compara hashes y `mtime` de cada archivo del store de prueba antes y después
  de ejecutar todos los comandos, y verifica que no se crean archivos nuevos
  en el store ni fuera de `~/.mailquery`. La suite no se considera verde si
  falla.
- Las pruebas **nunca** tocan el `~/.mailquery` real, `~/Library/Mail` ni el
  Outlook real: usan directorios temporales, el store sintético (§6) y, desde
  W3, el Outlook falso en memoria (`tests/fakes/`). Todo subprocess fija
  `HOME` y `USERPROFILE` a un directorio temporal. No se necesita Acceso total
  al disco para las pruebas, sí para una corrida real.
- Los instaladores tienen sus propias pruebas
  (`tests/test_install_scripts.py`: sintaxis de `sh`, `--help`, `--dry-run`,
  plantilla de config y reglas de no sobrescritura).
- `tests/test_backends.py` cubre el contrato de `MailBackend`, `get_backend`,
  `backend_class` y `AppleMailBackend`; `tests/test_output.py` y
  `tests/test_logging.py` cubren `output.py` y `logging_setup.py`.

### 8.3 Store sintético

`tests/fixtures/make_fixtures.py` construye un store de Apple Mail completo
(`Envelope Index` + `.emlx` + `Accounts4.sqlite`) en un directorio temporal;
API y contenido en §6 (`build_store()` para el store base,
`build_store(extended=True)` para los casos límite). Las fechas son relativas
a `datetime.now()` (o al `now` indicado), así que las pruebas no dependen de
fechas fijas.

### 8.4 Goldens

`tests/fixtures/expected/*.json` son las salidas normalizadas de los comandos
(`search_default`, `new_first_run`, `new_seeded`, `show_2714`, `mailboxes`,
`doctor`, errores, etc.) que compara `tests/test_integration.py`. Antes de
comparar se normalizan los valores variables (`generated_at`,
`duration_ms`, fechas ISO y epoch, ruta raíz temporal, separadores de ruta).
`tests/fixtures/expected/outlook/` (`mailboxes`, `search`, `show`,
`show_header_only`, `show_smime`; TC-02) son las del backend Outlook sobre
`FakeOutlook.default()`, con la misma normalización y una zona local fija
(`output.LOCAL_ZONE`, UTC−04:00); la config declara la cuenta Exchange y el
buzón compartido excluido.

### 8.5 Outlook falso (`tests/fakes/`)

`tests/fakes/outlook.py` implementa en memoria exactamente los miembros del
OOM de la lista blanca (`OOM_MEMBERS` == `outlook_com.READONLY_MEMBERS`); lo
demás da `AttributeError` y queda en el log. `FakeOutlook` es el conector que
se pasa como `get_backend(outlook_app=…)`, con `registry`, `security_center`,
`zone` y `drive_type` como otros puntos de inyección. Observabilidad:
`call_log` (`CallLog`: cada miembro leído o invocado, con tipo, acción y
argumentos) y `mutations` (asignaciones y miembros prohibidos; deben quedar en
0). Fallos: `fail_next`, `reject_next`, `hang_next`/`release`. Escenarios
(`SCENARIOS`): `default` (perfil de los goldens), `store_matrix`,
`folder_matrix`, `item_matrix` y variantes sin instancia, sin registrar y con
versión < 16. `tests/fakes/run_cli.py` ejecuta `cli.main` con el fake en un
subprocess (tests del vigilante, que termina el proceso con `os._exit`).

Para regenerarlos tras un cambio **intencional** del contrato:

```bash
MAILQUERY_UPDATE_GOLDENS=1 python -B -m unittest tests.test_integration
```

En PowerShell:
`$env:MAILQUERY_UPDATE_GOLDENS = "1"; python -B -m unittest tests.test_integration`.
Revisar el diff de los goldens antes de commitear: un golden solo cambia si el
PRD (§23.3) lo exige; regenerar no sustituye la revisión.

### 8.6 CI

`.github/workflows/tests.yml`:

- Job `unittest`: `ubuntu-latest`, `macos-latest` y `windows-latest` ×
  Python 3.11, 3.12, 3.13 y 3.14 (`fail-fast: false`). Ejecuta
  `python -m unittest discover -s tests -t . -v`; `pywin32` se instala solo en
  Windows. La suite completa debe pasar en los 3 SO (RNF-10).
- Job `install-scripts`: valida y ejecuta en seco los instaladores
  (`scripts/install.sh` en ubuntu y macOS, el instalador de PowerShell en
  Windows).

### 8.7 Git (D-01)

Rige la regla de git de la §1: el orquestador crea la rama de cada fase y
hace los commits; los merges a `develop` y los tags los hace o autoriza el
dueño tras la revisión del planificador.

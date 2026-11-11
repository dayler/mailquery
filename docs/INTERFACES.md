# Interfaz interna y reglas de trabajo — mailquery 2.0.1

Documento de coordinación para el equipo de implementación y guía de
desarrollo. El **PRD** oficial está en [`docs/PRD.md`](PRD.md) y manda sobre
este documento, junto con sus anexos (§24); aquí se fijan los contratos
concretos entre módulos, el layout del repositorio y las reglas de trabajo
(pruebas, fixtures, goldens, git, CI).

## 1. Layout del repositorio (layout `src/`)

```text
mailquery/                          # raíz del repo (https://github.com/dayler/mailquery)
├── README.md                       # instalación, FDA, ejemplos, contratos (español)
├── LICENSE                         # MIT (Ariel Dayler Salzar Hinojosa, 2026)
├── pyproject.toml                  # console script `mailquery`, entry points `mailquery.backends`, sin dependencias runtime
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
│   ├── errors.py                   # MailqueryError + 32 códigos E_* / exit codes
│   ├── uid.py                      # uid prefijado `<driver>:<native_id>`: formato, parseo y hash estable
│   ├── output.py                   # JSON formateado, snippets, fechas ISO, sanetización, html_to_text
│   ├── logging_setup.py            # log texto con rotación por tamaño
│   ├── config.py                   # config.toml + resolución de alcance (vía MailBackend)
│   ├── search.py                   # search/new/show/mailboxes (no renderiza JSON; vía MailBackend)
│   ├── state.py                    # cursor + anillo + lock
│   ├── cli.py                      # argparse, dispatch, stdout/stderr, exit codes
│   ├── accounts.py                 # Apple Mail: etiquetas de cuenta (Accounts4.sqlite ro)
│   ├── store.py                    # Apple Mail: Envelope Index ro + mapeo de mailboxes
│   ├── emlx.py                     # Apple Mail: resolución uid->ruta + parseo .emlx
│   ├── plugins/                    # API pública de plugin (API 1; lo único que importa un plugin externo)
│   │   ├── __init__.py             # reexporta la API 1 (estable)
│   │   └── api.py                  # PLUGIN_API, Reason, PluginError, PluginContext, capacidades
│   └── backends/
│       ├── __init__.py             # get_backend(...), backend_class(...), BackendRegistry
│       ├── registry.py             # descubrimiento/validación/carga perezosa de drivers (C1)
│       ├── base.py                 # MailBackend (protocolo v1), filas TypedDict, StateUidError, ExcludedStoreError
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
    │   ├── plugin.py               # doble de plugin API 1 + entry points inyectables (M01)
    │   └── run_cli.py              # lanzador en subprocess: fake + cli.main(argv, backend=…)
    ├── test_plugins.py             # UT-PL-01..04: API 1, registro de drivers, --version, ficheros de plugin
    ├── test_uid.py                 # UT-UID-01: formato y parseo del uid prefijado
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
    ├── test_install_scripts.py     # instaladores (install.sh / install.ps1; UT-INS-01)
    ├── test_packaging.py           # pyproject.toml, versión y entry points (TC-06, PKG-01)
    └── test_smoke.py               # SMOKE contra el cliente real, solo lectura; se salta donde no aplica
```

`outlook.py`, `outlook_com.py` y `tests/fakes/` llegan en la fase W3: con ellos
`get_backend(platform="win32")` da `mailboxes`, `search` (metadatos) y `show`.
La fase W4 completa Outlook: `new` (uids hex en `state.json`), `--text`,
`--to`/`--cc` acotados (RF-17), `doctor` (§B.8) y exit 6 de punta a punta; los
5 comandos tienen todos sus flags en ambos backends.

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
   │       backends/base (solo stdlib: MailBackend, StateUidError, ExcludedStoreError,
   │       │             Uid/LegacyUid, filas TypedDict; importa plugins/api)
   │       ↑
plugins/api, plugins/__init__ (SQL/CLIENTE ajenos al núcleo: PLUGIN_API, Reason,
   │       PluginError, PluginContext y tipos de capacidades; solo stdlib)
   │       ↑
   │    backends/registry (→ plugins/api, errors; importlib.metadata; sin importar
   │       │               implementaciones de backend, store ni cli)
   │       ↑
   │    backends/base
   │       ↑
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
- `plugins/**` (API pública de plugin) y `backends/registry.py` solo importan
  stdlib y el propio paquete; ninguno importa `store`, `emlx`, `accounts`,
  `search`, `config` ni una implementación de backend (RNF-12, UT-PL-04.04).
- `backends/registry.py` no importa `apple_mail` ni `outlook`: la carga es
  perezosa y solo importa el driver que se pide (`load`). El registro usa una
  tabla estática de metadata para los backends internos, de modo que listarlos
  (y `--version`) no importa sus módulos.
- `uid.py` importa solo `errors` y stdlib: se puede validar un `uid` antes de
  crear el home, leer `config.toml` o abrir el store.

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
`CODE_EXIT` mapea cada `E_*` al exit documentado. Catálogo vigente (32
códigos, PRD.md §12.6 + PRD-v2.1 §11.7): exit 1 `E_INTERNAL`; exit 2 11 códigos
(entre ellos `E_USAGE`, `E_DRIVER_UNKNOWN`, `E_ATTACHMENTS_DISABLED`); exit 3 12
códigos (entre ellos `E_PLUGIN_INCOMPATIBLE`, `E_PLUGIN_FAILED`,
`E_ATTACHMENT_UNAVAILABLE`, `E_ATTACHMENT_UNREADABLE`, `E_IO`); exit 4
`E_UNBOUNDED_SCAN`, `E_SCAN_TOO_LARGE`, `E_ATTACHMENT_BLOCKED`,
`E_ATTACHMENT_TOO_LARGE`; exit 5 `E_LOCKED`, `E_DB_BUSY`, `E_CLIENT_BUSY`; exit 6
`E_OUTLOOK_NOT_RUNNING`. `_EXIT_ERRORS` es la fuente única (UT-CLI-09.01 la
compara con la tabla completa). Helpers: `usage_error(message, hint="",
log_message=None)`, `config_error(...)` (misma firma), `bad_time(value)`,
`bad_filter(message, hint="")`, `exit_code_for(code)` y
`error_detail(exc) -> str` (detalle de una línea para `doctor`:
`CODE: message` o `Tipo: texto`). Un plugin nunca elige `code`/`exit`: aporta
`reason` (enum cerrado de `mailquery.plugins`) y el núcleo lo mapea (M05).

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

### `plugins/__init__.py` y `plugins/api.py`

API pública de plugin (API 1, C1; PRD-v2.1 §6.1 RF-38, §9.3). Es lo único que
un plugin externo importa de mailquery; `plugins/**` no importa backends ni el
store (RNF-12). `plugins/__init__.py` reexporta `plugins/api.py`:

- `PLUGIN_API = 1`: versión cerrada del contrato (`plugin_api`).
- `ENTRY_POINT_GROUP = "mailquery.backends"`: grupo de entry points del registro.
- `Reason(str, Enum)`: enum **cerrado** de `reason` con los valores de §11.7:
  `invalid_uid`, `not_found`, `not_local`, `not_downloaded`, `unsupported`,
  `corrupt`, `smime`, `unreadable`, `network`, `permission`, `auth`, `busy`,
  `timeout`.
- `PluginError(reason, hint="", detail="", log_message="")`: excepción del
  plugin; expone `.reason` (normalizado a `Reason` cuando es válido), `.hint`,
  `.detail`, `.log_message`. El plugin **nunca** elige `code`/`exit`: un
  `reason` desconocido se conserva para que el núcleo lo mapee a
  `E_PLUGIN_FAILED` (M05).
- `PluginContext(home, tmp_dir)`: dataclass congelado con las rutas que el
  núcleo entrega al plugin (`home` = `~/.mailquery`, `tmp_dir` =
  `~/.mailquery/tmp`).
- Tipos de capacidades: `Capabilities` (`TypedDict`) y los alias
  `ReadOnlyMode`, `AttachmentsMode`, `NativeOrder`; constantes
  `CAPABILITY_KEYS`, `READONLY_MODES`, `ATTACHMENTS_MODES`, `NATIVE_ORDERS`,
  `RESERVED_DRIVER_NAMES`, `DRIVER_NAME_PATTERN`, `DRIVER_NAME_MAX_LENGTH`.
- `DriverMetadata` (`TypedDict`): `driver`, `plugin_api`, `version`,
  `capabilities`, `internal` (este último lo añade el registro).

### `backends/registry.py`

`BackendRegistry(*, platform=None, entry_points=None)`: descubrimiento,
validación y carga perezosa de los drivers (C1, AC-01/AC-02). Descubre el grupo
`mailquery.backends` con `importlib.metadata` y fusiona un **fallback estático**
de `apple_mail`/`outlook` para desarrollo/CI sin `pip install`. `entry_points`
es la inyección de tests; con `None` usa `installed_entry_points()` (seam
parcheable, también usado por `--version`).

| Miembro | Contrato |
|---------|----------|
| `entries()` | `list[RawDriver]` (`name`, `value`, `version`, `internal`, `entry_point`): metadatos crudos, sin importar módulos |
| `installed()` | `list[str]` ordenada con los nombres del grupo (sin validar ni importar) |
| `is_installed(driver)` | `bool`; comprobación sin importar el módulo |
| `declared(drivers)` | `list[DriverMetadata]` validada en el orden pedido; driver no instalado ⇒ `E_DRIVER_UNKNOWN` (2) |
| `info(driver)` | `DriverMetadata` validada de un driver; importa solo ese plugin y una única vez |
| `load(driver)` | objeto del entry point (clase o factoría) de **un** driver; import fallido ⇒ `E_PLUGIN_INCOMPATIBLE` (3) |
| `versions(platform=None)` | `list[(driver, version)]` alfabética para `--version`; filtra los internos por plataforma (DP-02) |

Validación: `driver` debe cumplir `[a-z0-9_]{1,64}`, ser único (duplicado ⇒
`E_PLUGIN_INCOMPATIBLE`) y no ser un nombre reservado de un plugin; el objeto
cargado debe exponer `driver` (igual al nombre del entry point), `plugin_api = 1`
y un mapa de capacidades válido (si no ⇒ `E_PLUGIN_INCOMPATIBLE`, con
`expected 1, found <n>` en el hint). Metadata estática: `INTERNAL_TARGETS` y
`INTERNAL_CAPABILITIES`; versión con `package_version()` (metadata de la
distribución, o `mailquery.__version__` en desarrollo). `--version` usa
`versions()` y **no importa ningún módulo de plugin**. El grupo se declara en
`pyproject.toml` (`[project.entry-points."mailquery.backends"]`: `apple_mail =
"mailquery.backends.apple_mail:AppleMailBackend"` y `outlook =
"mailquery.backends.outlook:OutlookBackend"`); un plugin externo se registra en
el mismo grupo con `"<nombre> = <paquete>.<módulo>:<clase>"`.

### `backends/base.py`

Protocolo de backend v1 (C1). `Uid = str` es el uid de contrato
(`"<driver>:<native_id>"`); `LegacyUid = int | str` es el alias transitorio del
uid nativo que intercambian los adaptadores internos hasta M03 (entero en Apple
Mail, hex en mayúsculas en Outlook). `MessageRow` incluye `native_order_key: str`
en toda fila de listado: el núcleo lo compara como entero si la capacidad
`native_order` es `numeric` (Apple Mail) o como texto si es `text` (Outlook y
plugins por defecto), y nunca compara el texto del uid. `AttachmentRow(name)` se
mantiene para `BodyRow`; `AttachmentMetadataRow(index, name, size_bytes,
native_order_key, unavailable_reason)` es la lista ordenada de adjuntos (C1).
`StateUidError(cursor_detail, ring_detail)` (subclase de `ValueError`) y
`ExcludedStoreError(entry)` (subclase de `LookupError`) siguen igual.

`MailBackend` (ABC; PRD §9.3 y PRD-v2.1 §6.1 §9.3). Metadatos declarativos
(propiedades en la ABC, atributos de clase en los adaptadores y plugins):
`driver` (`str`), `plugin_api` (`int`, siempre `1`) y `capabilities`
(`Capabilities`); `native_order` es una propiedad concreta derivada
(`"numeric"`/`"text"`).

| Miembro | Devuelve |
|---------|----------|
| `driver` (propiedad) | `"apple_mail"`, `"outlook"` o el nombre del plugin |
| `plugin_api` (propiedad) | `1` (contrato C1) |
| `capabilities` (propiedad) | `{network, readonly, body_local, attachments, native_order}` |
| `native_order` (propiedad) | `capabilities["native_order"]`, `numeric` o `text` |
| `describe()` | dict de versión para el log y `doctor` |
| `accounts()` | `list[AccountRow]`: cuentas candidatas, base de `[scope]` |
| `labels_available` (propiedad) | `bool`; siempre `True` en Outlook |
| `mailboxes()` | `Sequence[MailboxRow]` (contadores = items buscables, sin borrados) |
| `excluded_stores()` | `[{label, path, reason}]`; siempre `[]` en Apple Mail |
| `resolve_mailbox(account_uuid, ref)` | `MailboxRow` o `None` (nombre, path, URL o alias `INBOX`, sin distinguir mayúsculas) |
| `query(mailbox_ids, since=None, until=None, unread=False, flagged=False, has_attachments=False, order="desc")` | `list[MessageRow]`; cada fila con `native_order_key` |
| `membership(uids)` | `dict[LegacyUid, set]`: carpetas de cada uid (dedupe y `mailbox`) |
| `duplicate_counts(mailbox_ids)` | `dict`: copias por clave global (`duplicate_count`) |
| `recipients(uids)` | `dict[LegacyUid, Any]`: to/cc por uid |
| `attachment_names(uid)` | `list[str]` |
| `find_message(uid)` | `(MessageRow, MailboxRow o None)` o `None`; uid de un store excluido ⇒ `ExcludedStoreError` |
| `load_body(row)` | `BodyRow`; nunca dispara descargas; S/MIME ⇒ `readable=False` |
| `parse_uid(text)` | uid legado del backend o `E_USAGE` (transitorio hasta M03) |
| `parse_native_id(native_id)` | **nuevo C1**: valida la parte nativa de un uid prefijado y devuelve el uid legado; puro y sin abrir cliente/store |
| `attachments(uid)` | **nuevo C1**: `list[AttachmentMetadataRow]` ordenada por `index` 1..N (M09/M10 la implementan; los plugins deben) |
| `attachment_stream(uid, index)` | **nuevo C1**: iterador de bytes **decodificados** del adjunto `index`; el plugin no escribe en la caché |
| `doctor_checks()` | chequeos propios del backend (los comunes los añade `cli.py`) |
| `close()` | libera la conexión SQLite o las referencias COM |

`parse_uid` y `parse_native_id` de los adaptadores son `@staticmethod` puros: el
núcleo puede validar antes de crear el home, leer la config o abrir el store.

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
Reexporta el registro C1: `BackendRegistry`, `DriverMetadata` y
`package_version` (también en `backends/registry.py`). Importar
`mailquery.backends` no importa ningún backend ni plugin.

### `uid.py`
Formato y parseo del uid prefijado (C1, AC-05). Puro y sin efectos: puede
validar antes de crear el home, leer `config.toml` o abrir el store.

`ParsedUid(driver, native_id)` (dataclass congelado) con la propiedad
`.uid = "<driver>:<native_id>"`.

- `parse_uid(text, *, native_driver=None, is_installed=None) -> ParsedUid`:
  split en el **primer** `:`; driver `[a-z0-9_]{1,64}`; `native_id`
  `[A-Za-z0-9._=-]{1,1024}`, sin punto inicial, sin `..` y sin espacios. Un
  uid sin prefijo se resuelve con el driver nativo del SO (`native_driver`
  permite forzarlo en tests): entero para Apple Mail, `EntryID` hex en
  mayúsculas para Outlook. Un formato inválido ⇒ `E_USAGE` (2); con
  `is_installed` (el registro), un driver válido no instalado ⇒
  `E_DRIVER_UNKNOWN` (2). Solo se entrega `<native_id>` al driver, que lo valida
  con `parse_native_id`.
- `split_uid(text, *, native_driver=None) -> (driver, native_id)`: split puro,
  sin validar (`"a:b:c"` ⇒ `("a", "b:c")`).
- `format_uid(driver, native_id) -> str`: construye y valida el uid.
- `is_valid_driver(value) -> bool`, `is_valid_native_id(value) -> bool`,
  `platform_native_driver(platform=None) -> str`, `driver_unknown(driver) ->
  MailqueryError`.
- `stable_identifier(uid) -> str`: 32 hex en minúsculas = primeros 32
  caracteres de `SHA-256(uid UTF-8)`; determinista entre plataformas. M06/M07
  lo usan cuando `<native_id>` o la ruta de caché exceden el límite del sistema
  de ficheros (§10.3.3).
- Constantes `DRIVER_PATTERN`, `NATIVE_ID_PATTERN`, `DRIVER_NAME_MAX_LENGTH`,
  `NATIVE_ID_MAX_LENGTH`.

**Ganchos opcionales del núcleo** (fuera de la superficie de PRD §9.3; el
núcleo los busca con `getattr` y Apple Mail no los tiene):

| Gancho | Lo usa | Para qué |
|--------|--------|----------|
| `bind_command(command)` | `cli` antes de ejecutar | Outlook: el vigilante D-03 informa el comando en `E_CLIENT_TIMEOUT` |
| `mailboxes_without_counters(account_uuids=None)` | `config.listed_mailboxes` | Outlook: carpetas sin contadores (`total`/`unread` = `None`); con `account_uuids` solo recorre los stores de esas cuentas |
| `not_found_hint` (atributo) | `search.run_show` | Outlook: el hint de `message uid … was not found` remite a `excluded_stores` |
| `unreadable_attachments(row)` | `search.run_show` | Outlook: `(nombres, warning)` de un item ilegible: `[]` y `W_ATTACHMENTS_UNAVAILABLE` solo si `has_attachments` y no es S/MIME (PRD §12.10) |
| `recipients_open_items` (atributo) | `search.run_search` | Outlook (`True`): `--to`/`--cc` abren cada item, así que se validan como `--text` (acotamiento y `max_scan`), no acotan y se aplican después de contar los candidatos (RF-17) |
| `items_opened` (propiedad) | `search.run_search`, `search.run_new` | Outlook: items distintos abiertos por la instancia; `scan.messages_read` = la diferencia durante el comando (en Apple Mail sigue siendo los cuerpos leídos) |
| `load_snippet(row)` | `search.run_search`, `search.run_new` | Outlook: `load_body` sin adjuntos ni cabeceras de transporte (solo los usa `show`; PRD §19) |
| `bind_doctor_timeout(finish)` | `cli._run_doctor` | Outlook (D-03): al vencer el plazo COM durante `doctor`, el vigilante llama a `finish(backend_checks, detail)` (ver `cli.py`) |

### `backends/outlook.py`
`OutlookBackend(*, outlook_app=None, registry=None, security_center=None,
pywin32=None, tmp_root=None, watchdog=None)`: lo construye `get_backend` en
`win32` (`watchdog` sustituye al vigilante global `outlook_com.WATCHDOG`; solo
tests). No abre nada hasta el primer uso; toda llamada COM pasa por
`outlook_com`. Declara `driver = "outlook"`, `plugin_api = 1` y capacidades
`network=false, readonly="structural", body_local=true, attachments="local",
native_order="text"`; cada fila de listado lleva `native_order_key = uid` (hex
en mayúsculas). `parse_uid` y `parse_native_id` validan el `EntryID` hexadecimal
en mayúsculas sin abrir COM. Implementa §9.3 según el anexo B:

- Stores (§B.3): el perfil se clasifica una sola vez leyendo solo propiedades
  del store; candidatos vía `Account.DeliveryStore`; `account.uuid` = los 16
  bytes de `PR_RECORD_KEY` en formato UUID. `accounts()` devuelve también los
  excluidos (con `excluded`); `excluded_stores()` los lista en orden del
  perfil. De un store excluido nunca se leen carpetas ni items.
- Carpetas (§B.3, §B.4): recorrido en profundidad desde `GetRootFolder`; INBOX
  y carpetas de sincronización por función (`GetDefaultFolder`); `id` = el
  `EntryID` de la carpeta. El árbol de cada store se recorre de forma perezosa,
  una vez por instancia. `mailboxes()` cuenta `total`/`unread` a partir de
  `PR_CONTENT_COUNT`/`PR_CONTENT_UNREAD` de la carpeta, un `GetRowCount` sobre
  el filtro de clases buscables y, solo si hace falta, las filas de excepción
  (clases no buscables o borrados IMAP) clasificadas en Python;
  `mailboxes_without_counters()` y `resolve_mailbox` no leen tablas. Las
  lecturas de tablas usan `Table.GetArray` por bloques de `TABLE_CHUNK_ROWS`.
- Items (§B.4): `query` con `Folder.GetTable` (uid = `EntryID` permanente,
  fechas UTC, prefiltro DASL ensanchado y corte exacto en Python);
  `find_message` identifica el store por los bytes 4..20 del `EntryID`;
  `load_body` nunca descarga (S/MIME y solo cabeceras sin leer contenido).
  Por comando, cada item se abre una vez mientras siga en caché (los 200
  primeros abiertos y el último) y los destinatarios de cada uid se leen una
  vez; `close()` vacía las cachés.
- `parse_uid(raw) -> str` (estático): hex en mayúsculas o `E_USAGE`; puro.
- `check_state_uid(uid) -> None` (estático): regla de `state.json` en Windows
  (PRD §11.2): string no vacío de hex en mayúsculas; un entero (uid de Apple
  Mail), minúsculas o `""` lanzan `StateUidError` con los detalles de
  `E_STATE_CORRUPT` de Outlook. Solo comparte con `parse_uid` la expresión
  hexadecimal (D-05).
- `describe()` conecta y devuelve `{backend: "outlook", version, strategy:
  "com_readonly", schema_ok: True}` para el log.
- `new`: lo resuelve el núcleo (`search.run_new`) con la interfaz común; el
  estado guarda uids hex validados por `check_state_uid`. Un mensaje movido
  por el usuario cambia de `EntryID` y se reemite una vez con su uid nuevo
  (PRD §12.3, §18).
- `doctor_checks() -> list[dict]`: `pywin32`, `outlook`, `stores`,
  `readonly_strategy` y `object_model_guard`, devueltos en el orden de PRD
  §12.8 (`DOCTOR_CHECKS`) y evaluados en el de D-03: primero los que no llaman
  a Outlook (`pywin32`, `object_model_guard`), después `outlook`,
  `readonly_strategy` (sin llamadas COM) y `stores` (`DOCTOR_COM_CHECKS`). Un
  chequeo cuya dependencia directa (`DOCTOR_DEPENDENCIES`, §B.8) falló sale
  `not evaluated: <dependencia> failed`; un error del chequeo sale en su
  `detail` con su hint. Nunca lanza Outlook (solo `GetActiveObject`).
  `object_model_guard` (§B.6) lee las directivas con `outlook_com.oom_policy`
  y, si ninguna decide, el antivirus (`security_center` inyectado o
  `outlook_com.WmiSecurityCenter`); si SecurityCenter2 no responde, `not
  evaluated: SecurityCenter2 unavailable`. `stores` resume
  `N candidate(s): <etiqueta> [<tipo>], …; M excluded: <etiqueta> at <ruta>
  [<motivo>], …`.
- `bind_doctor_timeout(finish)`: gancho de D-03 en `doctor`. El vigilante
  llama a `finish(backend_checks, detail)` con los chequeos del backend
  completados según PRD §12.8 (el que estaba en curso con `ok=false` y
  `outlook_com.DOCTOR_TIMEOUT_DETAIL`, sus dependientes `not evaluated`), o con
  `None` si no había ningún chequeo del backend en curso (el plazo venció en la
  resolución de `config`).

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
  miembro, asignación o nombre `_`/dunder ⇒ `E_INTERNAL` sin tocar COM. Sobre
  objetos de `pywin32` llama directamente a `IDispatch.Invoke` con el DISPID
  cacheado por tipo y miembro (por objeto en los `Item`), sin el coste de la
  información de tipos del dispatch dinámico; el fake sigue pasando por `getattr`.
- `Watchdog` y `WATCHDOG` (D-03): plazo `CALL_TIMEOUT_SECONDS` (30 s, punto de
  inyección) por llamada; `call_com(watchdog, call)` arma el plazo y reintenta
  una vez a los 100 ms un rechazo transitorio.
- Errores (§B.7): `hresult_of(exc)`, `map_com_error(exc)` y
  `ComCallError(hresult)` (`E_INTERNAL` con el HRESULT; el backend captura los
  esperados por `hresult`). `cli` registra todo `E_INTERNAL`, también este,
  con su traceback (PRD §14).
- Fuera del OOM, de solo lectura: `WinRegistry`, `get_drive_type(root)`
  (punto de inyección para rutas de red) y `WmiSecurityCenter(gen_path)`
  (consulta WMI de `root\SecurityCenter2`; `antivirus_products()` devuelve
  `[{displayName, productState}]` o lanza `OSError` si no se puede consultar;
  la misma interfaz que el `security_center` inyectado de los tests).
- `doctor` (§B.6, §B.8): `DOCTOR_TIMEOUT_DETAIL` (texto literal de PRD §12.8
  para el chequeo en curso al vencer el plazo); constantes de la política del
  Object Model Guard (`OOM_POLICY_KEY` en `HKCU`, `AdminSecurityMode`,
  `PromptOOMAddressInformationAccess`, `PromptOOMAddressBookAccess`,
  `OOM_DENY`/`OOM_PROMPT`/`OOM_APPROVE` y `OOM_SETTING_NAMES`);
  `oom_policy(registry) -> (nombre, valor) | None` (la directiva que decide:
  solo con `AdminSecurityMode = 3`; deniega o pregunta antes que aprueba; un
  valor ausente o 3 no decide); `active_antivirus(products) -> list[str]`
  (nombres con el bit `0x1000` de `productState`);
  `pywin32_gen_path() -> str | None` (`win32com.__gen_path__` si `pywin32` ya
  está importado; nunca lo importa).

### `backends/apple_mail.py`
`AppleMailBackend(store=None, labels=None, *, mail_root=None,
accounts_db=None, tmp_root=None)`. Con `store`/`labels` ya abiertos los usa; con
las rutas abre el `EnvelopeStore` y las `AccountLabels` de forma perezosa en el
primer uso. Es dueño del store: `close()` lo cierra. Aloja el SQL y los
helpers de Apple Mail que antes vivían en `search.py`, con el mismo orden,
warnings y reintento (`store.run_query`). Extras propios (fuera de la
interfaz): `store`, `labels`, `connection`, `tables` (propiedades),
`prepare()` (valida la conexión y detecta las tablas) y tres métodos estáticos:
`parse_uid`, `parse_native_id` (entero) y `check_state_uid` (transitorio hasta
M03). Declara `driver = "apple_mail"`, `plugin_api = 1` y capacidades
`network=false, readonly="structural", body_local=true, attachments="local",
native_order="numeric"`; cada fila de listado lleva `native_order_key = str(uid)`.
Los dos métodos estáticos de parseo:

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
`listed_mailboxes(backend, account_uuids=None) -> list[MailboxRow]`: las
carpetas cuando solo importa su identidad (alcance, dedupe, presentación,
hints): `mailboxes_without_counters(account_uuids)` si el backend lo ofrece,
si no `mailboxes()` (Apple Mail ignora `account_uuids`). `resolve_scope` y
`search` piden solo las cuentas declaradas.
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
Internos de `doctor` (no son API pública): `_DoctorRun(home_path)` guarda el
progreso de una corrida (chequeos comunes terminados, `backend_checks` y la
config ya leída) y lo comparte con el gancho de timeout; `.ordered()` los
devuelve en el orden de PRD §12.8 y `.after_timeout(backend, backend_checks,
detail)` completa el informe sin volver a llamar al cliente de correo.
`--version`/`-v` conserva el prefijo del PRD.md §12.9 y añade
`; drivers: <driver> <versión>, ...` dentro del paréntesis, alfabético: los
backends internos se filtran por plataforma (DP-02) y los plugins externos se
listan siempre; la línea usa `BackendRegistry.versions()` (metadata de
distribución, sin importar plugins) y no lee config ni escribe log. Es la única
superficie de `cli` que cambia en M01 (además de `selected.driver` en
`event=start`); el JSON de los comandos de datos no cambia.
`_collect_doctor_checks` evalúa en el orden de D-03 (`python`, `home`,
sintaxis de `config`, `state`, `lock`, los chequeos del backend y al final la
resolución de `config`); `_record_config_check` resuelve cada bloque (o
`not evaluated: <chequeo> failed` si falló su dependencia, `store` en Apple
Mail y `stores` en Outlook) y añade `W_STORE_EXCLUDED` al `detail` con
`ok=true` (PRD §15.3). `_bind_doctor_timeout` registra en el backend (si tiene
`bind_doctor_timeout`) un `finish` que escribe el informe con
`_emit_doctor_report(checks, json_output, logger, client)` (JSON o texto, más
la línea `event=end` del log), hace `flush` de `stdout`, `stderr` y el log y
termina con `os._exit(0)` (D-03).

## 4. Contrato JSON

> M01 **no cambia** el JSON de `search`/`new`/`show`/`mailboxes`/`doctor` ni los
> goldens: `native_order_key` es interno (viaja en la fila del backend, no se
> emite) y `--version` no es un golden. El `uid` sigue siendo el valor legado
> hasta M03; el formato prefijado se emite a partir de M03 con el contrato de
> `uid.py`.

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
`store`, `envelope_index`, `schema`, `readonly_strategy`, `accounts_db`; en
Outlook, `pywin32`, `outlook`, `stores`, `readonly_strategy` y
`object_model_guard` (PRD §12.8, §B.8; con Outlook cerrado, `outlook` falla
con `E_OUTLOOK_NOT_RUNNING` y su hint, sus dependientes salen `not evaluated`
y el exit sigue siendo 0). El chequeo
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
`show_header_only`, `show_smime`, `new_first_run` y `doctor`; TC-02) son las
del backend Outlook sobre `FakeOutlook.default()`, con la misma normalización y
una zona local fija (`output.LOCAL_ZONE`, UTC−04:00); la config declara la
cuenta Exchange y el buzón compartido excluido. El backend se construye con
`tmp_root=<home>/tmp` (como hace `cli`) y con el `registry` y el
`security_center` del fake, así que `doctor` es determinista.

`tests/test_integration.py` también ejecuta, en **ambos backends** (store
sintético con `DEFAULT_CONFIG` y `FakeOutlook.item_matrix()` con
`INBOX/Facturas` declarada), cada comando `mailquery` de los bloques de código
de `docs/recipes/` (TC-04, `<uid>` sustituido según el plan §7.4) y compara el
conjunto recursivo de claves JSON de `search`, `new`, `show`, `mailboxes`, un
error y `doctor --json` (TC-05).

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
versión < 16 (`not_running` es la base de los tests de exit 6:
cada comando de datos da `E_OUTLOOK_NOT_RUNNING` y `doctor` sale con exit 0).
`tests/fakes/run_cli.py` ejecuta `cli.main` con el fake en un subprocess
(tests del vigilante, que termina el proceso con `os._exit`). El gate de solo
lectura de Outlook (OL-30, `test_outlook.OutlookReadOnlyGateTests`) barre los
5 comandos con todos sus flags sobre todos los escenarios y exige miembros ⊆
lista blanca, 0 asignaciones, 0 mutaciones y ningún código que §B.7 excluye.

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

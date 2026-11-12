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
│       ├── base.py                 # MailBackend (protocolo v1), filas TypedDict, ExcludedStoreError
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
   │       backends/base (solo stdlib: MailBackend, ExcludedStoreError,
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
   │       state (→ base, errors, output)      config (→ errors, uid; `BackendRegistry` y
   │       │                                   MailBackend solo perezosos/TYPE_CHECKING)
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
- `config.py` importa `uid` (validación de nombres de driver) y usa
  `BackendRegistry.is_installed` para validar el prefijo de `[scope]`: importa
  `backends/registry.py` perezosamente (dentro de `load_config`) y solo cuando
  un bloque declara prefijo, así que un `config.toml` sin prefijos no crea el
  registro. No importa implementaciones de backend ni abre el store.
- `store.py`, `emlx.py` y `accounts.py` (Apple Mail) solo los importa
  `backends/apple_mail.py`.
- `state.py` importa `mailquery.uid` y `errors` (no `backends.base`) y recibe
  la comprobación de drivers instalados como argumento (`is_installed`, la del
  `BackendRegistry`); no importa ningún backend concreto.
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
  Desde M05 `plugins/api.py` importa además `errors` y `output` (módulos base,
  sin imports internos), y `search.py` importa el helper `plugins.wrap_driver`
  (envoltura de llamadas, no una implementación de backend).
- `backends/registry.py` no importa `apple_mail` ni `outlook`: la carga es
  perezosa y solo importa el driver que se pide (`load`). El registro usa una
  tabla estática de metadata para los backends internos, de modo que listarlos
  (y `--version`) no importa sus módulos.
- `uid.py` importa solo `errors` y stdlib: se puede validar un `uid` antes de
  crear el home, leer `config.toml` o abrir el store.
- `attachments/**` importa solo stdlib, `errors`, `uid` y sus propios módulos.
  M06 es puro (sin E/S) y M07 añade `engine.py`/`cache.py`, que toman
  `config.AttachmentsConfig` y `MailBackend` por duck typing: **no** importan
  `config`, `plugins`, `backends`, `cli`, `search`, `state`, `store` ni los
  adaptadores (UT-ATT-01.09). `cli`/`search` son los consumidores (M08).

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
`reason` (enum cerrado de `mailquery.plugins`) y el núcleo lo mapea (M05). El
protocolo de M05 vive en `plugins/api.py` (`call_driver`/`wrap_driver`) y se
detalla en la sección de `plugins/__init__.py` y `plugins/api.py`; ningún camino
de plugin produce `E_INTERNAL` (RF-50, §11.7) y el objeto `error` del JSON no
cambia: `{code, message, hint}`.

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
**M05 no cambia este módulo:** el `log_message` de un plugin se sanea antes, en
`plugins/api.py`, y el CLI lo registra en lugar del `message` (§12.1).

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

**Protocolo de errores de plugin y timeout de metadatos (M05, §11.7, RF-50,
RNF-15/16; C5).** El núcleo posee `code`, `exit` y la plantilla de `message`; el
plugin solo aporta `reason` (cerrado), `hint`, `detail` y `log_message`. Todo
paso por el módulo usa una única envoltura:

- `call_driver(operation, call, *, driver, internal=None, timeout=None) -> T`:
  ejecuta la operación, aplica el plazo y traduce los fallos. `operation` es el
  nombre del método de `MailBackend`. `internal` se deduce de los nombres
  nativos (`apple_mail`/`outlook`) y un plugin es siempre externo.
- `wrap_driver(backend, *, driver=None, internal=None, timeout=None)`: proxy
  transparente que enruta cada operación de `METADATA_OPERATIONS` por
  `call_driver`; envolver dos veces es no-op. Lo usa el pool de `search.py`.
- `map_plugin_error(exc, *, driver, attachments)` y
  `sanitize_error_field(value, max_bytes)` son las piezas puras (mapeo y
  saneado); `METADATA_OPERATIONS`/`ATTACHMENT_OPERATIONS` fijan el contexto.

Mapeo `reason` → código (exit de `errors.CODE_EXIT`): `invalid_uid`/`not_found`
⇒ `E_USAGE` (2) en ambos contextos; `not_local`/`not_downloaded`/`unsupported`/
`network` ⇒ `E_ATTACHMENT_UNAVAILABLE` (3) en operations de adjuntos y
`E_PLUGIN_FAILED` (3) en el resto; `corrupt`/`smime`/`unreadable` ⇒
`E_ATTACHMENT_UNREADABLE` (3) en adjuntos y `E_PLUGIN_FAILED` (3) en el resto;
`permission`/`auth` ⇒ `E_PERMISSION` (3); `busy` ⇒ `E_CLIENT_BUSY` (5);
`timeout` ⇒ `E_CLIENT_TIMEOUT` (3); cualquier otro `reason` (desconocido, vacío
o no string) ⇒ `E_PLUGIN_FAILED` (3). Un plugin no elige código: un atributo
`code`/`exit` suyo o un `MailqueryError` lanzado por el plugin se ignoran. Una
excepción no mapeada o un retorno inválido (validadores por operación: filas
`Mapping`, `native_id` string, adjuntos `{index:int, name:str, ...}`, `BodyRow`
con `attachments` lista, etc.) ⇒ `E_PLUGIN_FAILED` (3), nunca `E_INTERNAL`; un
fallo inesperado de un driver nativo se re-lanza y el CLI sigue dando
`E_INTERNAL` (1).

Plantillas de `message` (inglés, dueño: núcleo): `not available in the local
store`; `could not be retrieved from its origin`; `cannot be recovered by driver
'<driver>'`; `is corrupt or unreadable`; `is S/MIME protected and cannot be
extracted`; `cannot be read: permission denied`; `is temporarily unavailable`;
`did not respond within the timeout`. `invalid_uid`/`not_found` no tienen
plantilla de motivo en §11.7: el núcleo redacta `invalid message id` / `message
was not found` (su código es `E_USAGE`). El `detail` saneado, si existe, se añade
tras `": "`. `hint` = el del plugin saneado o el defecto del motivo/código
(`E_PLUGIN_FAILED` ⇒ `run "mailquery doctor" ...`; `E_CLIENT_BUSY` ⇒ retry once;
motivos de adjunto con su hint propio, p. ej. S/MIME).

Límites y saneado: `hint` ≤ 300 bytes, `detail` ≤ 200, `log_message` ≤ 200, en
UTF-8 y sin partir un carácter (`encode()[:N].decode("utf-8", "ignore")`); se
eliminan ANSI, controles C0/C1 (incluidos `\r`/`\n`/`\t`), formatos y bidi
(`\u202e`); un valor no string se ignora. `sanitize_text` de `output.py` se
reutiliza como primer paso.

Timeout: `METADATA_TIMEOUT_SECONDS = 30.0` (y `EXTRACTION_TIMEOUT_SECONDS = 120.0`
para M08), leídos en cada llamada para que un test inyecte un plazo corto con
`mock.patch`/`timeout=` (nunca se duermen 30 s). Un driver **externo** corre en
un hilo daemon con `Event.wait(deadline)`; al vencer ⇒ `E_CLIENT_TIMEOUT` (3),
sin reintento y sin resultados parciales (el hilo no se puede matar: riesgo
aceptado, PRD-v2.1 §15). Un driver **nativo** se ejecuta inline y se comprueba
el plazo al volver: sus conexiones SQLite/COM son thread-affine, así que no se
mueven a otro hilo; Outlook conserva además su watchdog COM de RF-33. Límite
conocido: una llamada nativa colgada no se aborta por este mecanismo.

Log (RNF-15, §12.1): el error de plugin lleva `log_message` saneado (o la
plantilla sin `detail`); el CLI registra ese texto en nivel `error` con `code=`
y nunca `hint`/`detail`, sin traceback (el traceback queda solo para
`E_INTERNAL`). No se añaden uids, nombres, rutas, cuentas, asuntos ni términos.

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
| `open(driver, *, context=None)` | instancia del driver ya cargado (M04, T01): el entry point externo se invoca con un `PluginContext` posicional; los internos, sin argumentos; un fallo del constructor ⇒ `E_PLUGIN_INCOMPATIBLE` (3) |
| `open_drivers(drivers, *, context=None)` | `dict[driver → instancia]` en el orden pedido; los abre el CLI antes de `event=start` |
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

**Convención de instanciación (API 1, M04):** el objeto del entry point es una
clase o una factoría; el núcleo lo invoca con **un** `PluginContext(home,
tmp_dir)` posicional (nunca con keywords ni con argumentos extra) y espera un
objeto que implemente `MailBackend`. Un entry point que ya devuelve una
instancia se usa tal cual; los drivers internos se instancian sin argumentos.
Solo se cargan los drivers declarados en `[scope]` (o el nativo cuando
corresponde); un driver declarado que no importa o no arranca aborta el comando
con `E_PLUGIN_INCOMPATIBLE` (3) y sin resultados parciales.

**M05 no cambia el registro:** la envoltura de llamadas (`call_driver`) vive en
`plugins/api.py` y se aplica al pool de `search.py` (`wrap_driver`, que incluye
también `accounts`/`mailboxes`/`resolve_mailbox` usados por la resolución de
alcance) y al `parse_native_id` de `show` en `cli.py`. La carga/import de un
plugin sigue siendo `E_PLUGIN_INCOMPATIBLE`; los fallos de runtime del driver ya
instanciado son `E_PLUGIN_FAILED` o el código mapeado por §11.7.

### `backends/base.py`

Protocolo de backend v1 (C1). `Uid = str` es el uid de contrato
(`"<driver>:<native_id>"`, la forma que emite el núcleo); `LegacyUid = int | str`
es el alias del uid nativo que intercambian los adaptadores internos (entero en
Apple Mail, hex en mayúsculas en Outlook) — M03 lo mantiene para no romper
M01/M02 (D1) y la prefijación ocurre solo en `search.py`/`cli.py`.
`MessageRow` incluye `native_order_key: str`
en toda fila de listado: el núcleo lo compara como entero si la capacidad
`native_order` es `numeric` (Apple Mail) o como texto si es `text` (Outlook y
plugins por defecto), y nunca compara el texto del uid. `AttachmentRow(name)` se
mantiene para `BodyRow`; `AttachmentMetadataRow(index, name, size_bytes,
native_order_key, unavailable_reason)` es la lista ordenada de adjuntos (C1).
`StateUidError` se retira en M03 (el estado valida sus uids en `state.py`);
`ExcludedStoreError(entry)` (subclase de `LookupError`) sigue igual.

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
| `parse_uid(text)` | uid legado del backend o `E_USAGE` (se mantiene hasta M04, D1; el núcleo de M03 ya no lo usa) |
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
- `parse_native_id(native_id) -> str` (estático, C1): valida la parte nativa de
  un uid prefijado (hex en mayúsculas) o `E_USAGE`; puro y offline.
- `check_state_uid` se retira en M03: los uids de `state.json` los valida el
  núcleo (`state.py` + `uid.py`), no el backend (PRD-v2.1 §10.2.5-6).
- `describe()` conecta y devuelve `{backend: "outlook", version, strategy:
  "com_readonly", schema_ok: True}` para el log.
- `new`: lo resuelve el núcleo (`search.run_new`) con la interfaz común; el
  estado guarda los uids prefijados `outlook:<EntryID>` de `schema: 2`. Un
  mensaje movido por el usuario cambia de `EntryID` y se reemite una vez con su
  uid nuevo (PRD §12.3, §18).
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
`prepare()` (valida la conexión y detecta las tablas) y dos métodos estáticos:
`parse_uid` (uid legado de entrada, hasta M04) y `parse_native_id` (entero). Declara `driver = "apple_mail"`, `plugin_api = 1` y capacidades
`network=false, readonly="structural", body_local=true, attachments="local",
native_order="numeric"`; cada fila de listado lleva `native_order_key = str(uid)`.
Los dos métodos estáticos de parseo:

- `parse_uid(raw) -> int`: uid legado de entrada, entero (`E_USAGE` si no);
  puro y sin I/O. Se mantiene hasta M04 (D1).
- `parse_native_id(native_id) -> int`: parte nativa de un uid prefijado,
  entero; puro y sin I/O. `show` lo usa antes de abrir el store.
- `check_state_uid` se retira en M03; la validación del estado vive en
  `state.py`.

**Adjuntos (M09, C9; RF-43/RF-46/RF-47, AC-09/AC-10/AC-11/AC-12/AC-15/AC-20).**
El adaptador implementa las dos operaciones del protocolo v1 además de
`parse_native_id`; no escribe en el store ni en la caché (solo abre el `.emlx`
en lectura) y nunca dispara descargas.

- `attachments(uid) -> list[AttachmentMetadataRow]`: un row por **parte MIME**
  con nombre, en orden de parte (1..N estable compartido con `show`); no se
  deduplican nombres repetidos. `size_bytes` es el tamaño **decodificado**
  (base64/QP) y `native_order_key = str(index)` (Apple Mail ordena
  numéricamente, C1). `unavailable_reason`: `None` si es local, `corrupt` si el
  payload no se puede decodificar (base64 estricto), `unsupported` si es una
  parte externalizada de `.partial.emlx` cuyo archivo no se puede verificar,
  `not_local` para los nombres del `Envelope Index` cuando el cuerpo falta o es
  ilegible **no S/MIME** (fallback 2.0.1). Un mensaje S/MIME (cifrado o firmado)
  lanza `MailqueryError E_ATTACHMENT_UNREADABLE` — la señal de mensaje de la
  convención C8/C9: `show` la captura y devuelve `[]` (D6) y `attachment` la
  propaga antes de "0 adjuntos" (fila 8 de §11.3); no se listan nombres del
  índice para S/MIME. Un mensaje sin adjuntos devuelve `[]` sin motivo.
- `attachment_stream(uid, index) -> Iterator[bytes]`: bytes **decodificados** en
  chunks de 64 KiB; las partes externalizadas de `.partial.emlx` se leen del
  archivo local cuando se puede localizar (best effort, PRD-v2.1 §15: layouts
  `Data/<shards>/Attachments/<uid>/<part>/<name>` y variantes junto a
  `Messages/`; nunca symlinks). Un fallo de lectura levanta
  `emlx.AttachmentReadError` con `reason` (`corrupt`, `not_local`,
  `unsupported`, `unreadable`) y el motor M07 lo mapea al código/exit de §11.7.
  `--all`/`--index` los decide el núcleo; el adaptador solo entrega el índice
  pedido. `load_body` sigue devolviendo `BodyRow.attachments` con **un nombre
  por parte** (mismo orden que `attachments()`), para que `show` y `attachment`
  compartan índices exactos.

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

**Adjuntos (M09).** Tipos `EmlxAttachment(index, name, size_bytes,
native_order_key, unavailable_reason, external_path, part_path)` y
`EmlxAttachments(path, partial, readable, smime, items, available)`; error
`AttachmentReadError(reason, detail)` (mapea a §11.7 vía el motor).
`parse_attachments(path, *, native_uid=None)`: lee el `.emlx` una vez, detecta
S/MIME y devuelve las partes con nombre en orden de multipart (1-based, sin
deduplicar); en `.partial.emlx` cada parte es externalizada y se resuelve con
`external_attachment_path(...)` (best effort; `unsupported` si no aparece).
`attachment_stream(path, index, *, native_uid=None)`: generador de chunks
decodificados (`ATTACHMENT_CHUNK_SIZE = 64 KiB`); base64 se valida de forma
estricta para distinguir `corrupt`. Todo es lectura pura (`open(..., "rb")`), no
hay escritura ni descarga; `_attachment_names` ya no deduplica (un nombre por
parte, M09) y `parse_emlx` conserva el comportamiento de 2.0.1 para el cuerpo.

### `state.py`
`state.json` **schema 2** (PRD-v2.1 §10.2.4-6, C3). Tipos:
`Cursor(last_date_received, last_uid, lookback_seconds=600)`,
`LastRun(command, at)`, `AppState(schema=2, updated_at="", last_run=None,
cursor=None, emitted_uids=())`, `EmittedUid(date_received, driver,
native_order_key, uid)` y `StateLoadInfo(exists, persisted_schema, migrated,
pruned_emitted_uids, pruned_drivers)` con `.migration_pending`. `last_uid` y
`emitted_uids` son strings prefijados `"<driver>:<native_id>"`; la forma se
valida con `mailquery.uid` y la instalación del driver con `is_installed`.

- `migrate_uid(value) -> str` (**función pura**, PRD-v2.1 §10.2.5, D8):
  determinista por tipo y sin depender del SO. Entero (no `bool`) ≥ 1 ⇒
  `apple_mail:<n>`; string hexadecimal en mayúsculas (`[0-9A-F]+`, incluido uno
  solo de dígitos) ⇒ `outlook:<HEX>`; `0`, negativos, `bool`, `None`, listas,
  minúsculas con letras y demás formatos ⇒ `E_STATE_CORRUPT` (exit 3) con el
  hint de renombrar el estado.
- `StateStore(home, is_installed)` con `.home`, `.path`, `.load()`,
  `.load_info` (metadata del último `load`), `.save(state)` y
  `.record_new(state, emitted, lookback_seconds, command="new")`.
  `is_installed(driver) -> bool` es la comprobación del `BackendRegistry`
  (`register.is_installed`; los dos backends internos figuran instalados en
  todo SO, así la migración por tipo es platform-neutral). `load`: `schema`
  requerido (1 o 2; ausente/`bool`/otro ⇒ `E_STATE_CORRUPT`); un schema 1 se
  **migra en memoria** y devuelve `AppState(schema=2, ...)`; un
  `cursor.last_uid` de un driver no instalado ⇒ `E_STATE_CORRUPT` con hint de
  reinstalar/renombrar; los ítems del anillo de drivers no instalados se
  **podan en silencio** y se informan en `load_info` (conteo + drivers, sin
  uids). `record_new` **solo calcula** el estado nuevo: `emitted` son
  `EmittedUid` con la clave total `(date_received, driver, native_order_key)`
  (PRD-v2.1 §10.2.7); el cursor solo avanza (nunca compara el uid como texto) y
  el anillo de 1.000 uids queda en orden total, el más reciente al final. **No
  guarda**: `search.run_new` llama a `save` salvo con `--peek` (un `--peek`
  migra en memoria y no escribe; la primera corrida de `new` no `--peek`
  persiste schema 2 con la escritura atómica). `RunLock(home)` no cambia.
  `state.json` 0600, `tmp + fsync + os.replace`; corrupción →
  `E_STATE_CORRUPT`; sin PII. El schema 1 no se vuelve a escribir jamás.

### `config.py`

Esquema cerrado de `config.toml`, resolución de alcance por driver y
`[attachments]` (PRD-v2.1 §6.1 RF-36, §6.2 RF-42/49, §13; C2).

Tipos: `LoggingConfig(level, max_size_mb)`, `SearchConfig(default_limit,
max_scan)`, `NewConfig(default_limit, lookback, lookback_seconds)`,
`AttachmentsConfig(enabled, max_file_size_mb, max_total_size_mb, max_count)`,
`ScopeEntry(key, mailbox_list, driver, account)`, `Config(home, logging,
search, new, attachments, scopes)` y `ResolvedScope(account_uuid,
account_label, account_email, mailboxes, driver)`.

- `AttachmentsConfig`: defaults `true`/`100`/`200`/`50`; rangos `1..500`,
  `1..1024` (`>= max_file_size_mb`) y `1..500`; una tabla ausente usa los
  defaults. MiB = 1.048.576 bytes (los límites los aplica M08).
- `ScopeEntry`: `driver` es el prefijo explícito del bloque (`None` = driver
  nativo del SO) y `account` la referencia dentro de ese driver (`None` en un
  bloque sin prefijo); `key` conserva la clave escrita y `account_ref` devuelve
  la referencia en ambas formas.
- `load_config(home=None, *, registry=None)`: `registry` (un
  `BackendRegistry`) valida el prefijo de driver; se crea perezosamente y solo
  si algún bloque declara prefijo. La clave se divide en el **primer** `:`
  (RF-36): prefijo vacío, con mayúsculas, guion o > 64 ⇒ `E_DRIVER_UNKNOWN`
  (exit 2); prefijo válido pero no instalado (`is_installed`) ⇒
  `E_DRIVER_UNKNOWN`; cuenta vacía tras el prefijo ⇒ `E_CONFIG_INVALID`. Una
  etiqueta de cuenta que contenga `:` debe declararse con el prefijo explícito
  (limitación documentada); sin prefijo el primer `:` se interpreta como
  separador de driver.
- `resolve_scope(config, backend, excluded=None, *, drivers=None, native=None)
  -> list[ResolvedScope]`: `backend`/`native` son el driver nativo (por
  defecto `backend.driver`) y `drivers` mapea los demás drivers declarados a su
  instancia. Un bloque sin prefijo resuelve contra el nativo; uno con prefijo
  dentro de las `accounts()` de su driver: formas del `PRD.md` §15.2 (etiqueta
  casefold → email único → UUID completo → prefijo de UUID ≥ 8) para los
  backends internos y `label`/`uuid` opacos exactos para plugins (sin prefijo
  de UUID). Bloques que resuelven a la misma `(driver, cuenta)` se combinan
  (unión de `mailbox_list`); INBOX va primero; un driver declarado sin backend
  disponible en la llamada ⇒ `E_DRIVER_UNKNOWN`; una clave que resuelve a un
  store excluido (fila de `accounts()` con `excluded`) no se lee y se reporta
  en `excluded` una sola vez (para `W_STORE_EXCLUDED`, PRD §15.3).
  `listed_mailboxes(backend, account_uuids=None)` y
  `include_mailbox_not_found(ref, account_uuids, backend)` no cambian.
- `declared_drivers(config, *, native=None) -> tuple[str, ...]`: drivers que
  declara `[scope]`, en orden de evaluación (el nativo primero si hay bloques
  sin prefijo; después los prefijos explícitos en orden de declaración, sin
  duplicados). `driver_in_scope(config, driver, *, native=None)` y
  `require_driver_in_scope(...)` exponen la comprobación de alcance para
  `show`/`attachment` (M03/M08): un driver instalado sin bloque ⇒
  `E_ACCOUNT_NOT_IN_SCOPE` (exit 2) con el hint de declarar la cuenta, sin
  cargarlo. Los comandos de datos no consultan un driver no declarado.
- Validación estricta: `[logging]`, `[search]`, `[new]`, `[attachments]` y
  `[scope."<driver>:<cuenta>"]`; cualquier clave/sección desconocida ⇒
  `E_CONFIG_INVALID` (exit 2). `parse_duration` min/h/d, 1 min–1 día.
`[scope.**]` sin prefijo conserva el comportamiento de 2.0.1 (regresión).

### `search.py`
`Filters(...)`, `ScanStats`, `parse_relative_time(value, now=None)`,
`wildcard_to_regex(pattern)`, `matches(pattern, text)`,
`run_search(backend, config, filters, *, drivers=None, native=None)`,
`run_new(backend, config, state_store, *, peek=False, limit=None, clock=None,
drivers=None, native=None)`,
`run_show(backend, config, uid, *, driver=None, drivers=None, native=None)`,
`run_mailboxes(backend, config, *, drivers=None, native=None)`.
Solo usan la interfaz `MailBackend`. `backend` es el driver nativo (puede ser
`None` cuando la config no lo declara); `drivers` es el mapping
`{driver: instancia}` de los demás drivers declarados que el CLI abrió y
`native` el nombre del driver nativo. Sin esos kwargs el comportamiento es el
de un solo driver (2.0.1/M03). **Todo uid emitido** (`search`, `new`, `show`,
`cursor.previous/current.last_uid` y `state.json`) es el string prefijado
`format_uid(driver, str(row["uid"]))`; los adaptadores siguen intercambiando el
uid nativo (D1) y el núcleo es el único que prefija. `uid` de `run_show` es el
uid **nativo** ya validado por `cli` (`parse_native_id` del driver del prefijo,
antes de abrir el store, PRD-v2.1 §11.3); los mensajes de error de `run_show`
(`E_USAGE`, `E_ACCOUNT_NOT_IN_SCOPE`) muestran el uid prefijado.
`state_store` es un `StateStore` creado con `is_installed` del registro.

**Motor multi-driver (M04, C4; PRD-v2.1 RF-37, §10.2.7-9).** Cada driver
declarado resuelve sus cuentas con `config.resolve_scope(..., drivers=,
native=)` y se consulta con los mismos filtros; la deduplicación por
`message_id` se hace **dentro** de cada driver (RF-07 del `PRD.md`, sin dedupe
cross-driver), y los resultados se fusionan con el orden total
`(date_received, driver, native_order_key)` — DESC en `search`/`show`, ASC en
`new`, `driver` siempre ASC — comparando el key como entero si la capacidad es
`numeric` y como texto si es `text`, nunca el uid. Las filas fusionadas llevan
el driver de forma interna (`_mq_driver`, no se emite); `--limit` se aplica
tras el merge, `truncated`/`hint` se calculan sobre el total fusionado,
`scan.candidates` y `scan.messages_read` suman por driver y el presupuesto de
`[search].max_scan` compara la **suma** de candidatos de todos los drivers.
`run_mailboxes` concatena los drivers en el orden de aparición de sus bloques
`[scope]` (`accounts[]`/`mailboxes[]`/`excluded_stores[]` por driver; un plugin
devuelve `excluded_stores: []`); el driver nativo sin bloques no aporta nada y,
sin ningún bloque `[scope]`, se conserva el listado 2.0.1 con `W_NO_ACCOUNTS`.
`run_show` despacha por el driver del prefijo: resuelve solo los bloques de ese
driver, llama a su `find_message`/`load_body` y a su operación `attachments()`
(API 1, C1) para componer `message.attachments[]` (M08, RF-43/AC-07):
`[{index, name, cached_path}]` con el nombre **original**, el índice estable
1..N del driver y `cached_path` calculado con `attachments.cache.cached_path`
(M07) — `null` si el nombre dispara `classify_name` (regla de nombre) o si la
entrada de caché no es un archivo regular. `show` **no crea, abre ni lee** la
caché ni escribe en disco; tampoco inspecciona contenido: un adjunto que
`attachment` bloquearía por *magic bytes* sigue mostrando `cached_path` si el
archivo regular existe. Capacidad `attachments: "none"` ⇒ `[]` sin llamar al
driver. Un driver remoto puede listar nombres (`show` solo calcula caché local,
que será `null` si no hay archivo). **Convención C8/C9 (S/MIME/ilegible):** el
driver puede propagar el motivo del mensaje lanzando el error de protocolo al
listar los adjuntos (`PluginError(reason=smime|unreadable)` en un plugin,
`MailqueryError E_ATTACHMENT_UNREADABLE` en un backend interno); `show` lo
captura ⇒ `attachments: []`, conserva el `W_BODY_*` de 2.0.1 y **no** añade
`W_ATTACHMENTS_UNAVAILABLE` (D6). Mientras un backend interno no implemente
`attachments()` (antes de M09/M10), `run_show` usa el fallback 2.0.1: nombres
MIME del cuerpo legible, nombres del `Envelope Index` con
`W_ATTACHMENTS_UNAVAILABLE` para un cuerpo ilegible no S/MIME, y `[]` para
S/MIME.

**Envoltura de llamadas (M05, C5).** `_driver_pool` envuelve cada backend con
`plugins.wrap_driver`, así que todas las operaciones de `MailBackend` pasan por
`call_driver` con el plazo de metadatos, incluidos los `accounts`/`mailboxes`/
`resolve_mailbox` de la resolución de alcance (a `config.resolve_scope` se le
pasa el catálogo ya envuelto). Un fallo de plugin sale con el código/exit de
§11.7 y nunca `E_INTERNAL`; un fallo inesperado de un driver nativo se propaga
intacto (el CLI lo convierte en `E_INTERNAL`). El plazo se comprueba tras la
llamada en los drivers nativos y con un hilo daemon en los externos (límite
conocido de RNF-16: ver la sección de `plugins/api.py`).
Devuelven los campos de comando **sin** `ok`/`command`/`generated_at` (los
añade `cli`); `run_mailboxes` devuelve `accounts`, `mailboxes`,
`excluded_stores` y `warnings`. Semántica de fechas: `--since` incluye,
`--until` excluye. Orden total de un driver (PRD-v2.1 §10.2.7): `search`/`show`
= `(date_received DESC, driver ASC, native_order_key DESC)`; `new` =
ASCENDENTE `(date_received ASC, driver ASC, native_order_key ASC)`; el key se
compara como entero si la capacidad es `numeric` (Apple Mail) o como texto si
es `text` (Outlook/plugins) y **nunca** se compara el texto del uid. En M03 el
comando abre un solo driver; M04 extiende el merge. El anillo de `new` filtra
por uid prefijado y el cursor avanza con esa misma clave total. Dedupe por clave
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
según `errors.CODE_EXIT`; lock automático; validación del uid de `show` **antes
de crear el home** (M03, PRD-v2.1 §11.3): `uid.parse_uid` con el driver nativo y
`BackendRegistry.is_installed` (un formato inválido ⇒ `E_USAGE`, un driver no
instalado ⇒ `E_DRIVER_UNKNOWN`), y `backend.parse_native_id` del driver nativo
(puro y offline, también antes del home; un backend inyectado cuenta como
disponible). Después de leer `config.toml` y antes de construir el backend,
`show` exige que el driver del prefijo aparezca en `[scope]`
(`driver_in_scope`/`require_driver_in_scope` de `config.py`): un driver
instalado sin bloque ⇒ `E_ACCOUNT_NOT_IN_SCOPE` sin cargarlo. **Ciclo de vida
multi-driver (M04, T01/T05/T06):** el comando crea **un** `BackendRegistry` y
lo comparte con `load_config(registry=)`, abre los drivers declarados
(`config.declared_drivers`, nativo primero) dentro del `RunLock` y antes de
`event=start`, y los cierra todos en un `finally` (best-effort: un fallo de
cierre no enmascara el resultado). El nativo solo se abre si la config tiene
bloques sin prefijo o si no hay ningún bloque `[scope]` (comportamiento 2.0.1);
un driver declarado que no carga aborta el comando sin resultados parciales.
`show` abre **solo** el driver del prefijo: si es el nativo pasa `args.uid` ya
validado; si es otro declarado lo carga con `registry.open_drivers`, valida la
parte nativa con su `parse_native_id` (`E_USAGE` si no cumple) y lo despacha con
`run_show(..., driver=, drivers=)`. Desde M05 ese `parse_native_id` de un plugin
pasa por `call_driver`: un `reason` `invalid_uid`/`not_found` ⇒ `E_USAGE` (2) y
un fallo no mapeado ⇒ `E_PLUGIN_FAILED` (3), nunca `E_INTERNAL`. El log de error
(`_log_error`) registra `error.log_message` en nivel `error` con `code=`; un
fallo de plugin no lleva traceback (solo `E_INTERNAL` lo lleva) y nunca se
registran `hint`/`detail`. Un driver interno no nativo declarado (p.
ej. `outlook:` en macOS) se instancia y falla de forma natural al consultar (el
registro lo considera instalado; DP-02 solo filtra `--version`). `new` crea
`StateStore(home, registry.is_installed)`.
`event=start` registra `command=... backend=<driver nativo> drivers=<lista
declarada separada por comas>` (el nativo primero; `-` si no hubiera ninguno):
`backend` es siempre el driver de la plataforma aunque no se abra, y nunca
incluye uids, `native_id`, cuentas, rutas, asuntos ni términos. El `event=end`
de `attachment` (solo en éxito; D7) registra `exit_code=0 count=<N>
cached=<M> bytes=<total> duration_ms=<ms>`; el resto de comandos conserva sus
campos actuales y un fallo registra `event=error` sin `event=end`.

**Comando `attachment` (M08, C8; PRD-v2.1 §11.2–11.5, AC-07/08/12/14/15/17/19).**
`mailquery attachment <uid> (--index N | --all) [--force]`. `--index` acepta
solo un entero positivo (se valida en `main` con el texto literal de §11.3, no
con el `type=int` de argparse) y `--index`/`--all` son mutuamente excluyentes
con el texto `attachment requires exactly one of --index or --all`. La ayuda
(`attachment --help`) reproduce literalmente §11.4 (usage, positional,
options, examples y notes; columnas alineadas a 17 y ≤ 100 columnas) y la
ayuda raíz lista los seis comandos con la línea de exits de §11.1.
`_run_command` implementa la precedencia de §11.3 filas 1–10 **antes** de
llamar al motor M07: (1) argumentos; (2) sintaxis del uid y driver instalado,
antes de crear el home; (3) config (incluye `[attachments]` y `[scope]`);
(4) `[attachments].enabled=false` solo para `attachment` ⇒
`E_ATTACHMENTS_DISABLED` (2); (5) el driver del prefijo debe estar declarado
(`E_ACCOUNT_NOT_IN_SCOPE` sin cargarlo), se abre y se comprueban sus
capacidades: `attachments: "none"` **y** `"remote"` ⇒
`E_ATTACHMENT_UNAVAILABLE` (`unsupported`, exit 3) antes de abrir el store (el
núcleo no puede materializar adjuntos remotos); (6) resolución de cuenta con
`config.resolve_scope` (el driver se envuelve antes con `plugins.wrap_driver`);
(7) `find_message` ⇒ `E_USAGE "message uid <uid> was not found"`; (8) la
llamada `attachments()` puede lanzar la señal S/MIME/ilegible de la convención
C8/C9 y el error de protocolo se propaga tal cual (`E_ATTACHMENT_UNREADABLE`,
exit 3, antes del caso “0 adjuntos”); (9) lista vacía ⇒ `E_USAGE "message <uid>
has no attachments"`; (10) índice fuera de rango ⇒ el texto del ejemplo G.
Después, `AttachmentsEngine.recover(...)` ejecuta las filas 11–15 con las filas
de metadatos ya obtenidas (`entries`), de modo que el driver no se consulta dos
veces; la CLI no reimplementa bloqueo, límites ni caché. El éxito es el JSON
de §11.2 con `uid` prefijado, `output_dir` absoluto (`message_dir`), `count`,
ocho campos por adjunto y `warnings: []`. El presupuesto de extracción es
`EXTRACTION_TIMEOUT_SECONDS` (120 s, RNF-16): se pasa al motor como factoría
`lambda: time.monotonic() + 120`, una por adjunto, y al vencer ⇒
`E_CLIENT_TIMEOUT` (3), sin reintento, staging limpio y sin archivos nuevos.
`show` no aplica `[attachments].enabled`.
`bind_command(command)` del backend si existe; todo `E_INTERNAL`
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
distribución, sin importar plugins) y no lee config ni escribe log. M01 cambia
`--version` (además de `selected.driver` en `event=start`); M02 añade el
`driver` check a `doctor` (orden y detalle en `### doctor`). El JSON de los
comandos de datos no cambia.
`_collect_doctor_checks(home_path, backend, run=None, *, registry=None)` evalúa
en el orden de D-03 (`python`, `home`, sintaxis de `config`, `driver`,
`state`, `lock`, los chequeos del backend y al final la resolución de
`config`); `registry` es el `BackendRegistry` del `driver` check, de la
validación de prefijos de `[scope]` y de `is_installed` del chequeo `state`
(`_run_doctor` crea uno y lo comparte). El chequeo `state` (M03) usa
`StateStore(home, registry.is_installed)` y el detalle conserva el de 2.0.1 con
el uid prefijado: sin fichero, el mensaje de primera corrida de siempre; con
fichero, `schema: 2; cursor last_date_received=<n> last_uid=<prefijado>` (o
`schema: 1 (migration pending); ...` mientras la migración no se haya
persistido, y `schema: <n>; no cursor yet` sin cursor); si el anillo podó uids,
añade `; pruned <N> emitted uid(s) of uninstalled drivers: <drivers>` (sin
uids). Un cursor de un driver no instalado deja el chequeo `ok=false` con
`E_STATE_CORRUPT`. `doctor` no escribe estado.
`_record_driver_check` (M02) valida el driver nativo (el backend en
diagnóstico) y cada driver declarado; el detalle y los sufijos son el contrato
de §11.6 (ver `### doctor`). `_record_config_check` resuelve cada bloque (o
`not evaluated: <chequeo> failed` si falló su dependencia: primero `driver`,
luego `store` en Apple Mail y `stores` en Outlook; los bloques de un driver
distinto del nativo solo se reportan como declarados, su resolución de cuentas
llega con el motor multi-driver de M04) y añade `W_STORE_EXCLUDED` al `detail`
con `ok=true` (PRD §15.3). `_bind_doctor_timeout` registra en el backend (si
tiene `bind_doctor_timeout`) un `finish` que escribe el informe con
`_emit_doctor_report(checks, json_output, logger, client)` (JSON o texto, más
la línea `event=end` del log), hace `flush` de `stdout`, `stderr` y el log y
termina con `os._exit(0)` (D-03).

### `attachments/` (M06, C6)

Núcleo **puro** de adjuntos (PRD-v2.1 §6.2 RF-43/RF-47/RF-48/RF-49, §10.3,
§11.3 filas 8–15, AC-09/AC-10/AC-11 y parte de AC-15). Es la política que
consumen M07 (límites/staging/caché) y M08 (`show`/`attachment`): **no escribe
en disco, no lee la caché y no abre rutas**. Solo stdlib y el propio paquete
(RNF-12). C6 congelado: catálogo de extensiones, reglas de bloqueo de
nombre/contenido, orden de evaluación, `sanitized_name` y rutas de caché.

Módulos: `catalog.py` (catálogo + NFKC), `blocking.py` (bloqueo de nombre y
*magic bytes*), `sanitize.py` (nombre sanitizado y nombre visible), `paths.py`
(rutas de caché) y `screening.py` (pantalla del mensaje completo). Todo se
reexporta desde `mailquery.attachments` (`__all__`).

#### Catálogo (§10.3.2)

`CATALOG: dict[str, tuple[str, ...]]` (categoría → extensiones, minúsculas y con
punto), `EXTENSION_CATEGORY: dict[str, str]` y `DANGEROUS_EXTENSIONS:
frozenset[str]`:

| Categoría | Extensiones |
|---|---|
| `executables` | `.exe .com .scr .pif .dll .sys .drv .ocx .cpl .app .bin .run .elf .dylib .so` |
| `scripts` | `.bat .cmd .ps1 .psm1 .psd1 .vbs .vbe .js .jse .wsf .wsh .hta .sh .bash .zsh .ksh .csh .command .tool .applescript .scpt .workflow` |
| `installers` | `.msi .msp .mst .msix .appx .pkg .mpkg .dmg .iso .img .deb .rpm .apk` |
| `shortcuts` | `.lnk .url .scf .inf .reg .ins .isp .prf .terminal .desktop .webloc` |
| `interpreters` | `.jar .jnlp .class .py .pyc .pyo .pyw .rb .pl .php .lua .tcl` |
| `office_macros` | `.docm .dotm .xlsm .xltm .xlam .pptm .potm .ppam .sldm` |

- `normalize_name(value) -> str` aplica **una sola vez**
  `unicodedata.normalize("NFKC", value)`; la forma cruda se conserva aparte para
  la regla de controles.
- `dangerous_extension(name) -> (extension, categoría) | None` recorta puntos y
  espacios finales y compara `case-insensitive` la extensión final y **todas las
  encadenadas** (`factura.pdf.exe`, `reporte.pdf.bat.cmd`); los helpers esperan
  un nombre ya normalizado. `is_dangerous_extension(name) -> bool`.
- `reserved_name(name) -> str | None` devuelve la raíz reservada de Windows
  (`con`, `prn`, `aux`, `nul`, `com1..9`, `lpt1..9`; parte antes del primer
  punto, `case-insensitive`, ignorando espacios/puntos finales);
  `is_reserved_name(name) -> bool`.

#### Bloqueo de nombre (§10.3.1 punto 1)

`classify_name(original_name) -> NameDecision`, puro y **sin lanzar error de
usuario** (el motor de M07 decide el `code`). `NameDecision(blocked, reason,
normalized_name, extension, category, detail)`; `detail` es
`NAME_BLOCK_DETAIL = "has a dangerous filename pattern"` (§11.5 ejemplo C).
Orden de reglas, la primera que dispara gana:

1. `Cc`/`Cf`/`Cs`/`Co` en la forma **cruda** (NUL y RLO `\u202e` incluidos) ⇒
   `reason="control_character"`.
2. `/` o `\` en la forma normalizada ⇒ `path_separator`.
3. segmento `..` ⇒ `parent_segment`.
4. prefijo de unidad `[A-Za-z]:` ⇒ `drive_prefix`.
5. cualquier `:` (evita NTFS ADS) ⇒ `alternate_data_stream`.
6. extensión simple o encadenada del catálogo ⇒ `dangerous_extension`
   (`extension`/`category` rellenos).
7. raíz reservada de Windows ⇒ `reserved_name`.

#### Bloqueo de contenido (§10.3.1 punto 2)

`classify_content(first_block: bytes) -> ContentDecision(blocked, reason,
signature, detail)`; `reason="executable_content"`, `detail =
CONTENT_BLOCK_DETAIL = "has executable content"` (§11.5 ejemplo D). Firmas
**solo en el offset 0** sobre una ventana de `CONTENT_INSPECTION_BYTES = 512`
bytes (`MAGIC_SIGNATURES`): `MZ`, `\x7fELF`, Mach-O `FE ED FA CE` /
`FE ED FA CF` / `CE FA ED FE` / `CF FA ED FE`, universal `CA FE BA BE` y `#!`.
No es recursiva: ZIP/OLE/PDF/imágenes y firmas fuera del offset 0 no se
inspeccionan (riesgo aceptado §15). Un flujo vacío (0 bytes) es válido y no
tiene firma.

#### Sanitización (§10.3.3) y nombre visible

`sanitize_name(original_name, index) -> str` (determinista, independiente de la
plataforma): NFKC única; vacío, solo espacios o solo puntos ⇒ `attachment`;
recorte de espacios/puntos en los extremos y eliminación de puntos iniciales
(dotfiles); cada espacio o `< > : " / \ | ? *` se sustituye por `_` **sin
colapsar**; la extensión es el sufijo del último punto (si no es el primer
carácter) limitada a `MAX_EXTENSION_BYTES = 20` bytes UTF-8; el nombre sin
prefijo mide ≤ `MAX_NAME_BYTES = 150` bytes y el final (prefijo `NN_` incluido)
≤ `MAX_SANITIZED_BYTES = 153`; con índice ≥ 100 el prefijo mide > 3 bytes y la
raíz se reduce en la diferencia. Ningún truncado parte un carácter. El
resultado **ya incluye** el prefijo `NN_`.

`display_name(original_name, *, max_bytes=120) -> str` es la forma embebible en
`message`/`warnings`/`hint`: sin segmentos de ruta, sin controles
(`Cc/Cf/Cs/Co`) y truncada a `DISPLAY_NAME_MAX_BYTES = 120` bytes UTF-8.
`truncate_utf8(value, max_bytes) -> str` es el truncado compartido sin partir
caracteres.

#### Rutas de caché (§10.3.3, D9)

- `cache_root(home) -> Path` = `<home>/attachments`.
- `message_dir(home, uid, *, platform=None) -> Path` =
  `<home>/attachments/<driver>/<native_id>`; `uid` es el canónico
  `"<driver>:<native_id>"` (C3) y el uid legado sin prefijo se resuelve con el
  driver nativo. Si el componente `<native_id>` o la ruta completa (reservando
  el presupuesto máximo de `sanitized_name`, 153 bytes) supera el límite, se
  sustituye `<native_id>` por `uid.stable_identifier(uid)` (32 hex en
  minúsculas = primeros 32 de `SHA-256(uid UTF-8)`). La reserva hace que el
  directorio elegido sea **el mismo para todos los adjuntos del mensaje**.
- `attachment_path(home, uid, sanitized_name, *, platform=None) -> Path` =
  `message_dir(...) / sanitized_name`; recibe el nombre **ya prefijado** y nunca
  antepone `NN_` otra vez (sin doble prefijo); exige un único componente de
  ruta de ≤ 153 bytes.
- `path_limits(home, *, platform=None) -> (component_max, path_max)`: en
  `win32`, 255 bytes de componente y el presupuesto conservador de
  `WINDOWS_PATH_BUDGET_BYTES = 240` de ruta; en POSIX, el `PC_NAME_MAX`/
  `PC_PATH_MAX` reales del sistema de archivos de `home` (fallback 255/4096).
  `platform` es **solo inyección de tests** (mismo patrón que `output.LOCAL_ZONE`).
- Ninguna función crea directorios ni abre archivos; M07 los crea con
  `0700`/`0600` y publica de forma atómica.

#### Pantalla del mensaje completo (§10.3.1, §11.3 filas 11–14)

`ScreenDecision(code, reason, index, name, detail)` con `ok` (`code is None`),
`failed` y `blocked`; `index`/`name` identifican el adjunto causante y `detail`
es el fragmento de mensaje del bloqueo. Códigos:
`BLOCKED_CODE="E_ATTACHMENT_BLOCKED"`, `UNREADABLE_CODE="E_ATTACHMENT_UNREADABLE"`,
`UNAVAILABLE_CODE="E_ATTACHMENT_UNAVAILABLE"` (M07/M08 los convierten en
`MailqueryError`).

- `screen_names(entries) -> ScreenDecision` evalúa los nombres de **todos** los
  adjuntos del mensaje, en orden de índice, y devuelve el primero que dispara
  una regla (**fila 11**, antes de los límites de M07). Se ejecuta con cualquier
  `--index`. Una lista vacía devuelve una decisión `ok`: no es un bloqueo ni se
  confunde con “sin adjuntos”.
- `screen_content(entries, requested_indices, open_stream) -> ScreenDecision`
  inspecciona **solo** los adjuntos solicitados (`--index N` ⇒ `[N]`; `--all` ⇒
  `None` = todos) y devuelve bloqueo (fila 13), `E_ATTACHMENT_UNREADABLE` (error
  de lectura del stream, fila 14) o `E_ATTACHMENT_UNAVAILABLE` con el motivo del
  driver (`unavailable_reason` de la fila de metadatos: `not_local`,
  `not_downloaded`, `unsupported`, `network`; `corrupt`/`smime`/`unreadable`
  ⇒ unreadable). Precedencia: un bloqueo (fila 13) gana sobre las faltas de la
  fila 14; entre faltas de la fila 14 se informa la primera en orden de índice.
  `open_stream(index)` debe poder llamarse de nuevo para la extracción (M06
  inspecciona y cierra su propio iterador; no entrega bytes parciales).
- `read_first_block(stream) -> bytes` lee como máximo
  `CONTENT_INSPECTION_BYTES = 512` y cierra el iterador; un flujo vacío devuelve
  `b""`. Los errores de lectura los traduce `screen_content` a unreadable.
- Frontera: la señal S/MIME/ilegible **del mensaje** (§11.3 fila 8, el driver
  propaga el motivo aunque la lista quede vacía) y “0 adjuntos” (fila 9) son de
  M08; M06 solo mapea el `unavailable_reason` de cada fila de metadatos. Las
  funciones no escriben ni abren rutas de caché/staging (lo verifica UT-ATT-03.06).

### `attachments/engine.py` y `attachments/cache.py` (M07, C7)

Motor de recuperación local: límites, aciertos de caché, staging y publicación
atómica (PRD-v2.1 RF-45/RF-47/RF-49/RF-51, §10.1, §10.4, §11.2, §11.3 filas
11–15, AC-12/AC-13/AC-15/AC-20 y RNF-13/RNF-14). Es el contrato **C7 congelado**
que consumen M08 (comando `attachment` y `show.attachments`) y los adaptadores
M09/M10. El motor no abre el store ni resuelve la cuenta; tampoco compone el
JSON: devuelve los registros de §11.2 y deja `uid`, `output_dir`, `count` y
`warnings[]` a `cli.py` (M08). Solo stdlib y el propio paquete: no importa
`mailquery.config`, `mailquery.plugins` ni `mailquery.backends` (el guard
UT-ATT-01.09 prohíbe `plugins` y los módulos de comando/backend).

#### API del motor (congelada)

```python
class AttachmentResult(TypedDict):
    index: int
    original_name: str
    sanitized_name: str
    saved: bool          # siempre True en un éxito (§11.2)
    cached: bool
    path: str            # ruta absoluta del archivo servido
    size_bytes: int
    sha256: str

class AttachmentsEngine:
    def __init__(
        self,
        home: str | Path,
        config: AttachmentLimits,          # config.AttachmentsConfig (M02), duck typing
        driver: AttachmentDriver,          # MailBackend cargado (C1), duck typing
        clock: Callable[[], float] | None = None,   # solo inyección de tests
    ) -> None: ...

    def recover(
        self,
        uid: str,
        indices: Sequence[int] | None = None,
        *,
        force: bool = False,
        deadline: Callable[[], float | None] | None = None,
        entries: Iterable[Mapping[str, object]] | None = None,
    ) -> list[AttachmentResult]: ...
```

- `uid` es el canónico `"<driver>:<native_id>"` (C3); el motor obtiene el uid
  legado para el driver con `driver.parse_native_id(<native_id>)`.
- `indices=None` ⇒ `--all`; `indices=[N]` ⇒ `--index N`. La validación de
  argumentos y del rango es de M08 (§11.3 filas 1, 10); el motor la repite de
  forma defensiva con `E_USAGE`.
- `entries` son las filas `AttachmentMetadataRow` (C1) que M08 ya obtuvo y
  mapeó con la envoltura de M05: pasándolas, el motor **no repite**
  `driver.attachments()`. Sin ellas (uso directo del motor o tests) el motor
  hace la llamada.
- `deadline` es una **factoría** que devuelve el instante absoluto (en unidades
  del `clock`) en que expira la extracción de **un** adjunto, o `None` sin
  límite. El motor la invoca una vez por adjunto, antes de leer su primer
  bloque, y el mismo instante acota la pantalla de contenido y la extracción.
  M08 pasa `lambda: time.monotonic() + 120` (RNF-16: 120 s por adjunto,
  también en `--all`); al vencer ⇒ `E_CLIENT_TIMEOUT` (exit 3), staging limpio
  y sin archivos nuevos. El motor **no** fija políticas de tiempo por sí solo.
- Resultado: un registro §11.2 por adjunto solicitado, en orden de índice y
  con `path` absoluto. Un fallo no devuelve registros parciales.
- `output_dir` de M08 = `attachments.paths.message_dir(home, uid)`. M08 ya
  validó las filas 7–10 (`find_message`, `attachments()`, “0 adjuntos”, rango
  del índice) y pasa esas filas en `entries`; el motor solo ejecuta 11–15.

#### Flujo interno (§11.3)

1. Metadatos (si `entries` no se pasó) y validación de forma; filas inválidas ⇒
   `E_PLUGIN_FAILED` (exit 3).
2. `screen_names(rows)`: nombres de **todo** el mensaje, antes de servir caché
   (fila 11) ⇒ `E_ATTACHMENT_BLOCKED` (exit 4).
3. `max_count` si `indices is None` (fila 12). Incluye los aciertos de caché;
   no aplica a `--index`.
4. Lookup de caché de cada adjunto solicitado (regular + tamaño esperado). El
   tamaño real de los aciertos cuenta para `max_total_size_mb`.
5. Límites con tamaño conocido (fila 12), por adjunto y acumulado ⇒
   `E_ATTACHMENT_TOO_LARGE` (exit 4) **antes de escribir**.
6. `screen_content(rows, misses, open_stream)`: primer bloque decodificado solo
   de los adjuntos que se van a extraer (fila 13/14); bloqueo ⇒
   `E_ATTACHMENT_BLOCKED`; ilegible/no disponible ⇒ su código. Los aciertos no
   se re-validan por contenido (RF-45, §10.3.1).
7. Extracción a staging de los misses: `magic bytes` ya validados, `sha256`
   incremental y corte por límite si el tamaño era desconocido (fila 13/14/15).
8. Verificación final de los aciertos: un archivo borrado o cambiado de tamaño
   durante la ejecución se re-extrae **una** vez (RF-51) con nueva pantalla de
   contenido; si la re-extracción falla, se devuelve el error del motivo.
9. Publicación atómica por archivo (`os.replace`) y registros §11.2.

Antes del paso 9 no queda ningún archivo nuevo ni parcial en la caché ni
temporales propios en `tmp/` (RNF-14). Un fallo de E/S a mitad de publicación
puede dejar archivos nuevos **completos** (riesgo aceptado §15); nunca
parciales. La caché previa se conserva si el aborto ocurre antes de publicar.

#### Semántica de caché y `--force` (RF-45, RF-51)

- Acierto: existe un archivo **regular** en la ruta determinista y (si el
  driver informa `size_bytes`) su tamaño coincide ⇒ `saved: true, cached: true`
  con `size_bytes`/`sha256` del archivo existente y **sin** re-extraer.
- Tamaño esperado distinto ⇒ miss y re-extracción.
- `--force` ignora la caché, re-extrae y reemplaza atómicamente
  (`cached: false`).
- Symlink, directorio o dispositivo en la ruta ⇒ miss; la publicación no sigue
  un symlink (`os.replace` sustituye el enlace) y un directorio destino no se
  puede reemplazar ⇒ `E_IO` (riesgo aceptado).
- Un fallo de E/S/permiso al leer la caché se trata como miss (caché
  best-effort). `cached: true` significa "existía y no se pidió `--force`", no
  "verificado"; `sha256` es el del archivo servido.
- Sin barrido, purga, TTL, daemon ni validación integral al arrancar o durante
  la ejecución; un archivo borrado por el cron externo se re-extrae una vez. La
  app solo limpia su **propio** staging huérfano (`tmp/staging/`); no toca
  `tmp/plugin-<driver>/` ni cachés del backend.
- Tamaño de los límites: 1 MiB = 1.048.576 bytes; un valor **estrictamente
  mayor** excede. Los límites se evalúan sobre el conjunto que la invocación
  devuelve (los aciertos cuentan con su tamaño real). Exceso con tamaño
  conocido ⇒ falla antes de escribir; desconocido ⇒ aborta al detectarlo,
  limpia staging y conserva la caché previa. Con varios fallos en `--all` se
  informa el primero en orden de índice.

#### Staging, permisos y publicación (RNF-13/RNF-14)

- Staging: `<home>/tmp/staging/session-<opaco>/` creado de forma perezosa (una
  invocación con solo aciertos no escribe nada); directorios `0700` y archivos
  `0600` en POSIX, nombre opaco (sin `original_name`), `fsync` antes de
  publicar y `os.replace` al directorio del mensaje. La sesión se borra en un
  `finally`; al abrir el área se descartan las sesiones huérfanas propias.
- Caché: `<home>/attachments/<driver>/<native_id>/<sanitized_name>` con
  `<home>/attachments`, `<driver>` y `<native_id>` en `0700`; archivos `0600`
  sin `+x`. En Windows se hereda la ACL del perfil y **no se relajan**
  permisos (`_SECURE_PERMISSIONS = False`).
- `tmp/` y `attachments/` deben estar en el mismo sistema de archivos; si no,
  la publicación falla con `E_IO` (DP-01) sin mecanismo alternativo.
- Costuras de test: `attachments.cache._SECURE_PERMISSIONS`, `_chmod`,
  `_ensure_private_dir`, `_create_staging_file`, `_write_chunk` y
  `_atomic_replace` permiten inyectar `EACCES`/`ENOSPC` fallos de `os.replace`
  sin parchear el módulo `os` global (mismo patrón que `output.LOCAL_ZONE`).

#### API de caché (congelada para M08)

```python
# attachments/cache.py
def cached_path(
    home: str | Path, uid: str, original_name: str, index: int,
    *, platform: str | None = None,
) -> Path | None: ...

class CacheHit:                  # frozen dataclass
    path: Path
    size_bytes: int
    sha256: str

class AttachmentCache:
    def __init__(self, home: str | Path, uid: str, *, platform: str | None = None) -> None: ...
    def message_dir(self) -> Path: ...
    def path_for(self, original_name: str, index: int) -> Path: ...
    def lookup(self, original_name: str, index: int, *, expected_size: int | None = None) -> CacheHit | None: ...
    def verify(self, hit: CacheHit) -> bool: ...
    def ensure_message_dir(self) -> Path: ...          # crea 0700; solo al publicar
    def staging(self) -> StagingArea: ...
    def publish(self, staged: StagedAttachment, original_name: str, index: int) -> Path: ...

class StagingArea:
    def __enter__(self) -> "StagingArea": ...
    def __exit__(self, *exc_info: object) -> None: ...
    def new_file(self) -> StagedAttachment: ...
    def close(self) -> None: ...

class StagedAttachment:
    path: Path
    size_bytes: int
    sha256: str
    def append(self, chunk: bytes) -> None: ...
    def finish(self) -> None: ...
    def publish(self, target: Path) -> None: ...
    def discard(self) -> None: ...
```

- `cached_path(...)` es el contrato de `show.attachments[].cached_path`
  (AC-07): devuelve la ruta determinista solo si el destino es un **archivo
  regular** (`lstat`, sin seguir symlinks); no crea, no abre ni lee nada. La
  regla de nombre (`classify_name`) la aplica `show` (M08), no este helper.
  `platform` es solo inyección de tests (M06/D9).
- M08 **no** debe reimplementar `stat`/symlink: `output_dir` =
  `message_dir(home, uid)` y `cached_path` = `cache.cached_path(...)`.
- M09/M10 no usan `AttachmentCache`: reciben `legacy_uid` y devuelven metadatos
  y bytes decodificados; nunca escriben en la caché (RF-47).

#### Errores del motor (C7, §11.7) y precedencia DP-01

| Código | Exit | Cuándo |
|---|---|---|
| `E_ATTACHMENT_BLOCKED` | 4 | Nombre peligroso de cualquier adjunto (fila 11) o *magic bytes* ejecutables de un adjunto a extraer (fila 13); mensaje/hint de §11.5 C/D. |
| `E_ATTACHMENT_TOO_LARGE` | 4 | `max_count`/`max_file_size_mb`/`max_total_size_mb`; plantillas de §11.3 (límite, índice y nombre cuando corresponde) y hint con `--index` para `--all`. |
| `E_ATTACHMENT_UNAVAILABLE` | 3 | `unavailable_reason`/`reason` del driver `not_local`, `not_downloaded`, `unsupported`, `network` (plantillas de §11.7). |
| `E_ATTACHMENT_UNREADABLE` | 3 | `corrupt`/`smime`/`unreadable` o error de lectura del stream; antes de publicar. |
| `E_PERMISSION` | 3 | Permisos del driver o de la caché/staging (`EACCES`). |
| `E_IO` | 3 | E/S al escribir el staging, publicar o por `tmp/` y `attachments/` en sistemas de archivos distintos (DP-01). |
| `E_CLIENT_TIMEOUT` | 3 | Vence el `deadline` inyectado por M08. |
| `E_CLIENT_BUSY` | 5 | `reason=busy` del driver (reintentable). |
| `E_PLUGIN_FAILED` | 3 | `reason` desconocido o metadatos inválidos del driver; nunca `E_INTERNAL` en la frontera de plugin. |
| `E_USAGE` | 2 | Índice solicitado fuera de rango o uid inválido (defensivo; M08 valida antes). |

**Precedencia DP-01:** los fallos de E/S de caché/staging son `E_IO` y
`E_PERMISSION` queda para permisos; la fila de `E_PERMISSION` de §11.7 que
menciona E/S de caché está superada por DP-01, §11.3 fila 15 y AC-12. Los
`message`/`hint` pueden contener uid y nombre (dueño: núcleo); el
`log_message` nunca contiene uid, `native_id`, nombres, rutas ni cuentas
(RNF-15). El motor no emite log (`event=end` es de M08).

## 4. Contrato JSON

> M03 emite por fin el **`uid` string prefijado** `"<driver>:<native_id>"` en
> `search`/`new`/`show` y en `state.json` (`schema: 2`), con migración
> determinista desde `schema: 1` y aceptación del uid legado en la entrada
> (PRD-v2.1 RF-40, §10.2, AC-05/AC-06). `native_order_key` sigue siendo
> interno (viaja en la fila del backend, no se emite). Los goldens con uid
> cambian **solo** en el uid; la forma de `show.attachments` y el chequeo
> `driver` de `doctor` son de M08/M02. En entradas de `show` se acepta además el
> uid legado (entero Apple Mail, hex mayúsculas Outlook), resuelto con el
> driver nativo; los warnings de 2.0.1 que citan el uid mantienen el valor
> nativo (no son contrato de este milestone).
>
> M04 **no cambia la forma** del JSON de `search`/`new`: la única diferencia es
> que pueden aparecer mensajes de varios drivers en la misma lista, fusionados y
> ordenados por `(date_received, driver, native_order_key)` (DESC en
> `search`, ASC en `new`), con `duplicate_count` calculado dentro de cada driver
> (PRD-v2.1 §10.2.7-9). El log `event=start` añade `drivers=` (fuera del
> contrato JSON). **M08** cierra la forma de `show.attachments` para todos los
> drivers: `{index, name, cached_path}` (AC-07) y el driver con
> `attachments: "none"` devuelve `[]`; es la única edición de forma/valor de
> esos goldens (M09/M10 no los reescriben). M08 añade el comando `attachment`
> con el payload de §11.2 y el `event=end` con conteos (§12.1).

Resumen de coordinación; el contrato completo es el PRD §12.5. Los ejemplos
están compactados en una línea por brevedad: la salida real es JSON
**formateado** (2 espacios, `output.dumps_json`) y siempre UTF-8. Los ejemplos
con `imap://` son los de Apple Mail; en Outlook `mailbox.url` es
`outlook://...` y el uid es `"outlook:<EntryID>"` (PRD §12.5, tabla de
diferencias).

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
Cada `<message>.uid` es `"apple_mail:<n>"` (macOS) o `"outlook:<EntryID>"`
(Windows).
`hint` (RF-15) es `null`/ausente cuando `truncated=false`; cuando
`truncated=true` es un string accionable, p. ej. `"refina los filtros o sube
--limit (máx. 200)"`, y además se emite
`W_RESULTS_TRUNCATED: <N> more messages match; refine the filters or raise --limit`.

### `new`
Igual que `search` más:
```json
{"cursor": {"previous": {"last_date_received": 0, "last_uid": "apple_mail:0", "lookback_seconds": 600}, "current": {"...": "apple_mail:1"}}}
```
`previous`/`current` pueden ser `null`.

### `show`
```json
{"message": {"uid": "apple_mail:83143", "message_id": "...", "subject": "...",
  "from": {"name": "", "address": ""}, "to": [{"name": "", "address": ""}],
  "cc": [], "date_sent": "<ISO>", "date_received": "<ISO>",
  "mailbox": {"account": {"uuid": "", "label": "", "email": ""},
              "name": "INBOX", "path": "INBOX", "url": "imap://..."},
  "is_read": false, "is_flagged": false, "has_attachments": false,
  "size_bytes": 202913,
  "headers": {"From": "", "To": "", "Cc": "", "Subject": "", "Date": "", "Message-ID": ""},
  "body_text": "", "body_truncated": false,
  "attachments": [{"index": 1, "name": "<original_name>", "cached_path": "<abs path>|null"}],
  "partial": true, "readable": true,
  "source": {"emlx_path": "/...", "partial": true}}}
```

`index` es la posición 1..N estable que comparte con `attachment`; `name` es el
nombre original del driver y `cached_path` la ruta absoluta del archivo de caché
(regular) o `null` (sin caché, nombre no seguro o entrada no regular). En S/MIME
`attachments` es `[]` y solo queda el `W_BODY_UNREADABLE` de 2.0.1 (D6). Un
driver con `attachments: "none"` devuelve `[]`; `show` nunca escribe.

### `attachment`
```json
{"uid": "apple_mail:83143",
 "output_dir": "/Users/<user>/.mailquery/attachments/apple_mail/83143",
 "count": 1,
 "attachments": [{"index": 2, "original_name": "Factura Octubre 2026.pdf",
   "sanitized_name": "02_Factura_Octubre_2026.pdf", "saved": true, "cached": false,
   "path": "/Users/<user>/.mailquery/attachments/apple_mail/83143/02_Factura_Octubre_2026.pdf",
   "size_bytes": 128450, "sha256": "<64 hex>"}],
 "warnings": []}
```
`ok`/`command`/`generated_at` los añade `cli` (§11.2). Un acierto de caché
devuelve `cached: true` y `saved: true` con el `size_bytes`/`sha256` del archivo
servido; `--force` re-extrae (`cached: false`). El error sigue el contrato
`{ok:false, command, error:{code,message,hint}}` de §11.5 C/D/G/H/E/F.

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

Chequeos comunes (los añade `cli.py`): `python`, `home`, `driver`, `config`,
`state`, `lock`. Los del backend (`MailBackend.doctor_checks()`) en Apple Mail
son `store`, `envelope_index`, `schema`, `readonly_strategy`, `accounts_db`; en
Outlook, `pywin32`, `outlook`, `stores`, `readonly_strategy` y
`object_model_guard` (PRD §12.8, §B.8; con Outlook cerrado, `outlook` falla
con `E_OUTLOOK_NOT_RUNNING` y su hint, sus dependientes salen `not evaluated`
y el exit sigue siendo 0). Orden de la lista (PRD-v2.1 §11.6, M02):

- macOS: `python`, `home`, `driver`, `store`, `envelope_index`, `schema`,
  `readonly_strategy`, `accounts_db`, `config`, `state`, `lock`.
- Windows: `python`, `home`, `driver`, `pywin32`, `outlook`, `stores`,
  `readonly_strategy`, `object_model_guard`, `config`, `state`, `lock`.

El chequeo `driver` (M02, común y con nombre estable) valida que todo driver
declarado en `[scope."<driver>:<cuenta>"]` (más el nativo cuando hay bloques
sin prefijo) esté instalado, declare `driver` válido/único y `plugin_api = 1` y
tenga capacidades válidas. Es la única comprobación que lista la metadata de
los drivers; `config` depende primero de ella (`not evaluated: driver failed`)
y después de `schema` (macOS) / `stores` (Windows) como hasta ahora.
`detail` (contrato C2): por cada driver, en orden de declaración (nativo
primero si hay bloques sin prefijo),
`<driver> (api=<1>; pkg <versión>; network=<true|false>; readonly=<structural|promise>; body_local=<true|false>; attachments=<local|remote|none>; native_order=<numeric|text>)`,
unidos por `; `; la versión es la de la distribución (`package_version()`,
`2.0.1` en esta fase) y el nativo se obtiene del backend seleccionado (así el
fake de Outlook sobre `platform="win32"` reporta `outlook` en cualquier host).
Sufijos: sin `config.toml` o sin ningún bloque `[scope]` ⇒
`; no declared drivers` (valida solo el nativo); config que no parsea ⇒
`; declared drivers: unknown (config failed)` (valida solo el nativo y el error
lo reporta `config`); un driver que no valida añade
`; <driver>: <CODE>: <message> (hint: <hint>)` y `driver` queda `ok=false`
(exit 0 siempre). Un plugin externo no añade chequeos propios.
El chequeo `config` valida el TOML y **la resolución de cada bloque `[scope]` y
su `mailbox_list`** del driver nativo contra el store y las etiquetas de cuenta
(por entrada, con el `code`/`hint` de cada error); un bloque de otro driver
declarado se reporta como `<clave> → declared for driver <driver>` hasta que el
motor multi-driver (M04) resuelva sus cuentas. Distingue config ausente de
config presente sin `[scope]` y, cuando no hay cuentas declaradas, lista las
disponibles con el formato `0 account block(s) declared; available: <label>, ...`
sin activarlas.

### Error
```json
{"ok": false, "command": "search", "error": {"code": "E_UNBOUNDED_SCAN", "message": "...", "hint": "..."}}
```
Sin `generated_at` (contrato de error del PRD §12.5). El objeto `error` es
siempre `{code, message, hint}` sin campos nuevos (M05/RF-50); en un error de
plugin `code`/`exit` salen del conjunto cerrado del núcleo, `message` usa la
plantilla de §11.7 (con el `detail` saneado tras `": "`) y `hint` es el del
plugin saneado o el defecto del motivo/código.

### Mensaje (`search`/`new`)
```json
{"uid": "apple_mail:83143", "message_id": "<...>", "duplicate_count": 1, "subject": "...",
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

`build_store(..., attachments=True)` (M09) añade los fixtures de adjuntos, sin
cambiar el store por defecto: tres adjuntos con un nombre repetido
(`UID_ATTACH_MULTI`), un mensaje por patrón de nombre hostil
(`HOSTILE_ATTACHMENT_NAMES`: traversal, separadores, `..`, `C:`, ADS, RLO,
`CON.fdp.exe`, doble extensión), contenido ejecutable (`MZ`), adjunto vacío de
0 B, `.partial.emlx` con un adjunto externalizado verificable y otro no
verificable, archivo de 1,5 MiB (`max_file_size_mb=1` en `LIMIT_1MB_CONFIG`),
nombres Unicode/largos, S/MIME con fila de adjuntos, `.emlx` ausente con fila
del índice y payload base64 corrupto. `FixtureMessage.attachments` es una tupla
de `FixtureAttachment(name, payload, externalized, external_file,
external_payload, corrupt)`; los fixtures 2.0.1 (`attachment_names`) se siguen
generando igual.

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
`tests/fixtures/expected/search_multidriver.json` y `new_multidriver.json`
(M04, TC-08) son las salidas de `search` y `new` con `apple_mail` + el doble de
plugin API 1 declarado (`[scope."graph:Graph (user@example.com)"]`). Semilla
determinista: `build_store()` (fixture base y su reloj) más dos mensajes del
plugin en `fx.now − 18 min` (P2) y `fx.now − 16 min` (P1), de modo que ambos
caen en la ventana de primera corrida de `new` (`D` = el mensaje más reciente de
Apple Mail, −15 min, con `lookback` de 600 s). El registro del CLI se inyecta
con los entry points internos más el del doble (`FakeEntryPoint`), sin instalar
nada; la comparación normaliza `<ISO>`, `<EPOCH>` y las rutas. Los goldens de un
solo driver no cambian en M04.
`tests/fixtures/expected/outlook/` (`mailboxes`, `search`, `show`,
`show_header_only`, `show_smime`, `new_first_run` y `doctor`; TC-02) son las
del backend Outlook sobre `FakeOutlook.default()`, con la misma normalización y
una zona local fija (`output.LOCAL_ZONE`, UTC−04:00); la config declara la
cuenta Exchange y el buzón compartido excluido. El backend se construye con
`tmp_root=<home>/tmp` (como hace `cli`) y con el `registry` y el
`security_center` del fake, así que `doctor` es determinista.
`tests/fixtures/expected/attachment_saved.json`, `attachment_cached.json`,
`attachment_blocked_name.json`, `attachment_blocked_content.json`,
`attachment_too_large.json` y `show_2714_with_cache.json` (M09, TC-08) son los
flujos de adjuntos sobre `build_store(attachments=True)` con `DEFAULT_CONFIG`.
Semilla: `attachment_saved` corre en un store nuevo (`cached:false`);
`attachment_cached` ejecuta antes una corrida de siembra (documentada en el
test) y compara la segunda (`cached:true`); `show_2714_with_cache` ejecuta
`attachment apple_mail:2714 --index 1` antes del `show`. Los payloads del
fixture son bytes fijos, así que `size_bytes` y `sha256` son estables; las
rutas se normalizan a `<ROOT>`. Los goldens existentes de `show`/`search`/`new`
no cambian en M09 (M08 es su dueño).

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

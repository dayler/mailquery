# Plugins, drivers y multi-driver

#### UT-DRV-01 — Esquema de `[scope]`

Requisitos: AC-03 · Archivo: `tests/test_config.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `[scope."apple_mail:you@icloud.com"]` ⇒ driver `apple_mail`, cuenta resuelta dentro de sus cuentas. |
| .02 | P | `[scope."you@icloud.com"]` ⇒ driver nativo del SO. |
| .03 | P | Etiqueta con `:` declarada con prefijo explícito funciona; sin prefijo ⇒ `E_DRIVER_UNKNOWN` (limitación documentada). |
| .04 | N | Driver con mayúsculas, guion, vacío o > 64 ⇒ `E_DRIVER_UNKNOWN`. |
| .05 | N | Driver bien formado pero no instalado ⇒ `E_DRIVER_UNKNOWN`; todos los comandos de datos fallan (no se ignora). |
| .06 | P | Dos bloques que resuelven a la misma `(driver, cuenta)` combinan `mailbox_list`. |

#### UT-DRV-02 — Resolución de cuentas por driver

Requisitos: AC-03 · Archivo: `tests/test_config.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Backend interno: label, email único y UUID completo/prefijo ≥ 8 dentro del driver. |
| .02 | P | Plugin: `label`/`uuid` opacos, incluido label corto (< 8) que en un backend interno sería ambiguo. |
| .03 | N | Cuenta inexistente ⇒ `E_CONFIG_ACCOUNT_UNKNOWN`; ambigua ⇒ `E_ACCOUNT_AMBIGUOUS`. |
| .04 | N | Store excluido de Outlook declarado ⇒ `W_STORE_EXCLUDED` con la etiqueta/ruta, sin abortar. |

#### UT-DRV-03 — Driver instalado no declarado

Requisitos: AC-03 · Archivo: `tests/test_config.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Los comandos de datos no consultan un driver instalado sin bloques `[scope]`. |
| .02 | N | El helper de alcance devuelve `E_ACCOUNT_NOT_IN_SCOPE` (exit 2) para un driver instalado sin bloque `[scope]`, con el hint de declarar la cuenta. Los comandos `show` y `attachment` con ese prefijo se prueban en UT-UID-02 y UT-ATC-02. |
| .03 | N | Un prefijo de driver no instalado ⇒ `E_DRIVER_UNKNOWN` (exit 2). |

#### UT-DRV-04 — `[attachments]`

Requisitos: AC-14, RF-40, RF-47 · Archivo: `tests/test_config.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Sin tabla ⇒ defaults `enabled=true`, `100`/`200`/`50`. |
| .02 | P | Valores válidos personalizados se aceptan y exponen. |
| .03 | N | `enabled` no booleano; `max_file_size_mb` 0, 501, `"100"`, `true`; `max_total_size_mb` 0, 1025; `max_count` 0, 501 ⇒ `E_CONFIG_INVALID`. |
| .04 | N | `max_total_size_mb < max_file_size_mb` ⇒ `E_CONFIG_INVALID` con hint. |
| .05 | N | Clave desconocida en `[attachments]` o sección desconocida ⇒ `E_CONFIG_INVALID`. |

#### UT-DRV-05 — `doctor driver`

Requisitos: AC-02, AC-18 · Archivo: `tests/test_cli.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Orden de chequeos de macOS y de Windows con `driver` tras `home`. |
| .02 | P | `detail` por driver con `api`, `pkg`, `network`, `readonly`, `body_local`, `attachments` y `native_order`. |
| .03 | N | Un driver declarado incompatible ⇒ `driver` `ok=false` con motivo/hint; `config` `not evaluated: driver failed`; exit 0. |
| .04 | N | `config.toml` inválido ⇒ `driver` valida solo el nativo con `declared drivers: unknown (config failed)`; el error lo reporta `config`. |
| .05 | P | Sin config o sin bloques ⇒ `driver` valida el nativo con `no declared drivers`. |
| .06 | N | Varios drivers declarados (nativo + plugin) ⇒ `detail` los lista todos; si uno falla, `driver` falla y `config` no se evalúa; la sección del plugin resuelve sus propios bloques. |
| .07 | N | `driver` y `schema`/`stores` fallan a la vez ⇒ `config` informa `not evaluated: driver failed` (el driver se evalúa primero); `schema`/`stores` conservan su dependencia del backend nativo. |
| .08 | P | `driver` aparece exactamente en la posición 3 de la lista ordenada, tanto en macOS como en Windows (plataforma parcheada). |

#### UT-ERR-01 — Mapeo `reason`→`code`/exit

Requisitos: AC-16 · Archivo: `tests/test_plugins.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Tabla completa en operación de adjuntos: `invalid_uid`/`not_found` ⇒ `E_USAGE` (2); `not_local`/`not_downloaded`/`unsupported`/`network` ⇒ `E_ATTACHMENT_UNAVAILABLE` (3); `corrupt`/`smime`/`unreadable` ⇒ `E_ATTACHMENT_UNREADABLE` (3); `permission`/`auth` ⇒ `E_PERMISSION` (3); `busy` ⇒ `E_CLIENT_BUSY` (5); `timeout` ⇒ `E_CLIENT_TIMEOUT` (3). |
| .02 | P | Tabla completa en el resto de operaciones: `invalid_uid`/`not_found` ⇒ `E_USAGE`; el resto de motivos de adjunto ⇒ `E_PLUGIN_FAILED`; `permission`/`auth`, `busy`, `timeout` conservan su código. |
| .03 | N | `reason` desconocido, vacío o no string ⇒ `E_PLUGIN_FAILED` (3), nunca `E_INTERNAL`. |
| .04 | N | El plugin intenta fijar `code`/`exit` (p. ej. atributo extra o excepción con código propio) ⇒ se ignora; el código pertenece siempre al conjunto cerrado del núcleo. |
| .05 | P | El objeto `error` es `{code, message, hint}` y `command` y `generated_at` siguen el contrato de salida (§12.5). |

#### UT-ERR-02 — Saneado, límites y plantillas

Requisitos: AC-16/AC-19 · Archivo: `tests/test_plugins.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `hint` de 301 bytes, `detail` de 201 y `log_message` de 201 se truncan a ≤ 300/200/200 bytes sin partir un carácter. |
| .02 | N | Controles (`\x00`, `\r`, `\n`, ANSI, `\u202e`) en `hint`/`detail`/`log_message` se eliminan. |
| .03 | P | El `message` usa la plantilla del motivo y añade el `detail` saneado después de `: `; table-driven con las plantillas de §12.6 (`not available in the local store`, `could not be retrieved from its origin`, `cannot be recovered by driver '<driver>'`, `is corrupt or unreadable`, `is S/MIME protected and cannot be extracted`, `cannot be read: permission denied`, `is temporarily unavailable`, `did not respond within the timeout`) y sus motivos (`not_local`, `not_downloaded`, `unsupported`, `network`, `corrupt`, `unreadable`, `smime`, `permission`, `busy`, `timeout`). |
| .04 | P | El log registra el `log_message` saneado y nunca el `hint` ni el `detail`. |
| .05 | N | `hint`/`detail` con uid, nombre de archivo, ruta, cuenta o término **nunca** llegan al log; el `log_message` se sanea (controles, ≤ 200 bytes). La obligación de que el plugin no incluya PII en `log_message` se prueba en el doble, no como saneado del núcleo. |
| .06 | P | Los `hint` de §12.6 se respetan: `E_DRIVER_UNKNOWN` lista los drivers instalados e indica `pipx inject mailquery <paquete>`; `E_PLUGIN_FAILED` sugiere `run "mailquery doctor"`; el hint de un motivo de adjunto es el del motivo. |

#### UT-ERR-03 — Fallos no mapeados

Requisitos: AC-16 · Archivo: `tests/test_multidriver.py`, `tests/test_plugins.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Excepción no mapeada en una operación ⇒ `E_PLUGIN_FAILED` (3), sin traceback de plugin en el JSON. |
| .02 | N | Tipos de retorno inválidos (fila no dict, `native_id` no string, lista de adjuntos mal formada) ⇒ `E_PLUGIN_FAILED`. |
| .03 | P | Un fallo inesperado del núcleo (no del plugin) sigue siendo `E_INTERNAL` (exit 1), sin cambio. |
| .04 | N | El comando falla sin resultados parciales y cierra los drivers abiertos. |

#### UT-ERR-04 — Timeout de metadatos

Requisitos: AC-17, RNF-21 · Archivo: `tests/test_multidriver.py`, `tests/test_plugins.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Una operación de metadatos de plugin que supera 30 s (plazo inyectado) ⇒ `E_CLIENT_TIMEOUT` (3), sin reintento automático. |
| .02 | N | El timeout no deja resultados parciales ni estado escrito. |
| .03 | P | Una operación por debajo del plazo no se interrumpe. |
| .04 | N | Una operación de metadatos del backend nativo también está envuelta: con plazo inyectado superado ⇒ `E_CLIENT_TIMEOUT` (3), sin tocar el watchdog COM de Outlook. |
| .05 | N | El timeout de una operación durante el merge cierra los drivers abiertos y no emite `messages[]` parcial. |

#### UT-MD-01 — Carga y fail-fast

Requisitos: AC-04 · Archivo: `tests/test_multidriver.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Solo se cargan los drivers declarados (más el nativo si hay bloques sin prefijo); los no declarados no se importan. |
| .02 | N | Un driver declarado no carga ⇒ el comando falla con su código y sin resultados parciales. |
| .03 | N | Un driver falla en runtime a mitad del merge ⇒ el comando falla con el código mapeado; no hay `messages[]` parcial. |
| .04 | P | Todos los drivers se cierran aunque el comando falle. |

#### UT-MD-02 — Merge y orden

Requisitos: AC-04 · Archivo: `tests/test_multidriver.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `search` con dos drivers: orden `(date_received DESC, driver ASC, native_order_key DESC)`. |
| .02 | P | `new` con dos drivers: orden ascendente; el cursor avanza con el último emitido. |
| .03 | P | Mismo `message_id` en dos drivers ⇒ dos resultados, `duplicate_count` independiente por driver. |
| .04 | P | Duplicado dentro de un driver sigue eligiendo la copia canónica (INBOX/carpeta normal) y `duplicate_count: 2`. |
| .05 | B | Misma fecha y mismo driver, distinto `native_order_key` numérico y textual ⇒ desempate estable y determinista. |
| .06 | B | Misma fecha y distinto driver ⇒ desempata por `driver` ascendente. |

#### UT-MD-03 — `mailboxes` multi-driver

Requisitos: AC-04 · Archivo: `tests/test_multidriver.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `accounts[]` (cada uno con su `mailboxes[]`) y `excluded_stores[]` concatenados en el orden de los bloques `[scope]`. |
| .02 | P | Un plugin devuelve `excluded_stores: []` y `accounts[]` con `label`/`uuid` opacos y sus carpetas en `mailboxes[]`. |
| .03 | B | Un driver sin cuentas declaradas no aporta bloques y no rompe el comando. |

#### UT-MD-04 — Cursor y lookback

Requisitos: AC-04 · Archivo: `tests/test_multidriver.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Un único cursor global; cada driver se consulta con el mismo `last_date_received` y `lookback`. |
| .02 | P | Primera corrida: ventana sobre el conjunto fusionado y anillo con uids prefijados. |
| .03 | N | `cursor.last_uid` de un driver instalado pero no declarado: el cursor se conserva, se usa la fecha como marca y los uids de ese driver no se comparan. |
| .04 | P | Los uids de drivers no declarados permanecen en el anillo sin romper `new`. |

#### UT-MD-05 — Límites y `scan`

Requisitos: AC-04 · Archivo: `tests/test_multidriver.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `--limit` se aplica tras el merge; `truncated`/`hint` se calculan sobre el resultado fusionado. |
| .02 | P | `scan.candidates` suma por driver; `scan.messages_read` suma las lecturas. |
| .03 | B | `--limit` mayor que el total ⇒ sin `truncated` ni `hint`. |

#### UT-MD-06 — Log multi-driver

Requisitos: AC-19 · Archivo: `tests/test_multidriver.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `event=start` registra `backend=<nativo>` y `drivers=<lista declarada>`. |
| .02 | N | El log no registra uids, `native_id`, cuentas, rutas, asuntos ni términos. |
| .03 | P | Un comando con solo un driver declarado registra `drivers=` con ese driver y `backend=` con el nativo. |

#### UT-MD-07 — `show` con driver externo declarado

Requisitos: AC-05, AC-07 · Archivo: `tests/test_multidriver.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `show <plugin>:<native_id>` carga el plugin declarado y devuelve uid prefijado, cuerpo (`body_local: true` o `false`) y `attachments[]` con `{index, name, cached_path}`; `cached_path` es `null` si no hay caché. |
| .02 | P | Un plugin con `body_local: false` obtiene el cuerpo del plugin; si no está disponible, aplica `W_BODY_NOT_LOCAL`/`W_BODY_UNREADABLE` (§12.10). |
| .03 | N | `show` de un plugin instalado pero no declarado ⇒ `E_ACCOUNT_NOT_IN_SCOPE` (exit 2) sin importar/cargar el plugin. |
| .04 | N | `show` de un plugin con `attachments: "none"` ⇒ `attachments: []`; no se llama a la operación de adjuntos. |
| .05 | N | `show` de un plugin con `attachments: "remote"` y `network: true` devuelve solo nombres (sin red en el núcleo); `show` no escribe ni descarga. |
| .06 | P | `native_order_key` del plugin se usa en el orden de `search`/`show` con la capacidad `native_order` declarada. |

#### UT-PL-01 — Registro de drivers

Requisitos: AC-01, RF-33 · Archivo: `tests/test_plugins.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | El grupo `mailquery.backends` expone `apple_mail` y `outlook`; el registro los lista con `driver`, `plugin_api` y versión **sin importar** los módulos. |
| .02 | P | Fallback de desarrollo: con el paquete sin instalar, los backends internos se resuelven igual. |
| .03 | P | Metadata inyectada: un plugin externo que cumple el contrato (driver válido, API 1, capacidades) se registra por la misma vía y aparece en el listado; no se exige `pip install` en CI. |
| .04 | N | Un plugin declara un nombre reservado (`apple_mail`/`outlook`) ⇒ `E_PLUGIN_INCOMPATIBLE`. |
| .05 | N | `driver` que no cumple `[a-z0-9_]{1,64}` (`Apple_Mail`, `apple-mail`, vacío, 65 caracteres) ⇒ `E_PLUGIN_INCOMPATIBLE`. |
| .06 | N | `plugin_api` ausente o `≠ 1` ⇒ `E_PLUGIN_INCOMPATIBLE`; el hint incluye esperado/encontrado. |
| .07 | N | Un plugin declarado no importa (dependencia faltante) ⇒ `E_PLUGIN_INCOMPATIBLE`; los demás drivers siguen siendo listables. |
| .08 | P | Carga perezosa: un comando con solo el driver nativo declarado no importa el resto; `--version` no importa ninguno. |
| .09 | P | Orden alfabético en `drivers:` con dos drivers (plugin fake + nativo) y filtrado por plataforma de los internos. |
| .10 | N | `driver` duplicado (interno + plugin o dos plugins) ⇒ `E_PLUGIN_INCOMPATIBLE`, exit 3. |

#### UT-PL-02 — Capacidades

Requisitos: AC-02, RF-36 · Archivo: `tests/test_plugins.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Mapa válido (`network`, `readonly`, `body_local`, `attachments`, `native_order`) aceptado y expuesto. |
| .02 | N | Falta una capacidad ⇒ `E_PLUGIN_INCOMPATIBLE`. |
| .03 | N | Valor fuera de enum (`attachments: "zip"`, `readonly: "yes"`, `native_order: "alpha"`) ⇒ `E_PLUGIN_INCOMPATIBLE`. |
| .04 | N | `attachments: "remote"` sin `network: true` ⇒ `E_PLUGIN_INCOMPATIBLE`. |
| .05 | N | `body_local: false` sin `network: true` ⇒ `E_PLUGIN_INCOMPATIBLE`. |
| .06 | P | Varios drivers, cada uno con su mapa, se validan por separado. |

#### UT-PL-03 — `--version`

Requisitos: AC-18 · Archivo: `tests/test_plugins.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Formato exacto: prefijo de la versión instalada (`mailquery.__version__`, sin literal) con `; drivers: <driver> <versión>,...` alfabético dentro del paréntesis. |
| .02 | P | En macOS lista los drivers internos disponibles (`apple_mail`; no `outlook`); en Windows al revés (plataforma parcheada). Un plugin externo se lista siempre. |
| .03 | N | Sin efectos: no crea `~/.mailquery`, no lee `config.toml`, no escribe log, no toma lock, no abre el store. |
| .04 | P | Un plugin instalado aparece listado aunque sea incompatible; `doctor` es quien reporta el problema. |
| .05 | N | No importa módulos de plugin (metadata de distribución); un plugin instalado sin metadata de plataforma no se filtra. |
| .06 | P | Sin paquete instalado (modo desarrollo), `--version` usa la versión de `__version__`/metadata de respaldo y no falla. |

#### UT-PL-04 — API de plugin y archivos autónomos

Requisitos: AC-01, RF-37 · Archivo: `tests/test_plugins.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `PluginContext(home, tmp_dir)` y `PluginError(reason, hint, detail, log_message)` con el enum cerrado de `reason`; el doble de plugin solo necesita el paquete `mailquery.plugins`. |
| .02 | N | El núcleo no lee `~/.mailquery/<driver>.toml` ni `~/.mailquery/logs/<driver>.log`: con esos archivos presentes, comandos y `doctor` se comportan igual. |
| .03 | N | El núcleo no crea, rota ni borra `<driver>.toml`, `logs/<driver>.log` ni `tmp/plugin-<driver>/`. |
| .04 | P | Escaneo de imports: `src/mailquery/plugins/**` y `backends/registry.py` solo usan stdlib y el propio paquete (RNF-12). |

# CLI y configuración

#### UT-CFG-01 — `max_size_mb`

Requisitos: RF-18, RF-19 · Archivo: `tests/test_config.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | B | 1 y 1024 ⇒ válidos. |

#### UT-CFG-02 — `retention_days`

Requisitos: RF-19 · Archivo: `tests/test_config.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | `[logging].retention_days = 7` ⇒ `E_CONFIG_INVALID` con el hint `retention_days was replaced by max_size_mb`. |

#### UT-CFG-03 — `[content]`

Requisitos: RF-63 · Archivo: `tests/test_config.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Sin tabla ⇒ `neutralize`; `neutralize`, `keep` y `strip` son válidos. |
| .02 | N | `url_display = "raw"` y `url_display = 1` ⇒ `E_CONFIG_INVALID`, exit 2, `hint` con `neutralize`, `keep` y `strip`, antes de abrir el store. |
| .03 | N | Una clave desconocida en `[content]` ⇒ `E_CONFIG_INVALID`, exit 2. |
| .04 | N | `content = 1` (valor que no es una tabla) ⇒ `E_CONFIG_INVALID`, exit 2, antes de abrir el store. |

#### UT-CFG-04 — `[attachments].timeout_seconds`

Requisitos: AC-43 · Archivo: `tests/test_config.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Sin clave ⇒ 60; 10 y 600 válidos. |
| .02 | N | 9, 601, `"60"`, `60.0` y `true` ⇒ `E_CONFIG_INVALID`, exit 2, también en `search` y `show`, antes del store. |
| .03 | B | Con un valor válido, `show` y `search` dan la misma salida que sin la clave. |

#### UT-CFG-05 — `[logging].json`

Requisitos: RF-88, AC-77 · Archivo: `tests/test_config.py`, `tests/test_cli.py`

**Tabla: Casos de UT-CFG-05**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Sin la clave ⇒ `json` es `false`; `true` y `false` se cargan como booleanos. |
| .02 | N | `json = "yes"` ⇒ `E_CONFIG_INVALID` (exit 2), y la ejecución lo registra en `mailquery.log` en texto. |
| .03 | N | `json = true` con otra clave inválida ⇒ `E_CONFIG_INVALID`, registrado en `mailquery.log` en texto, sin crear `mailquery.jsonl`. |

#### UT-CFG-06 — Configuración del log del servidor

Requisitos: RF-84 · Archivo: `tests/test_config.py`

**Tabla: Casos de UT-CFG-06**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `load_logging_config` toma `level`, `max_size_mb` y `json` de `[logging]` aunque el resto del archivo no sea válido. |
| .02 | B | Archivo ausente, TOML inválido o `[logging]` inválida ⇒ texto, `info` y 10 MB, sin lanzar. |

#### UT-CFG-07 — `[lock]`

Requisitos: RF-89, AC-80 · Archivo: `tests/test_config.py`

**Tabla: Casos de UT-CFG-07**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | [pendiente] Sin `[lock]`: `retries = 5`, `initial_delay_ms = 150` y `backoff_factor = 2`. Con una sección que solo declara `retries`, las otras dos claves valen su valor por defecto. |
| .02 | B | [pendiente] Se aceptan `retries` 0 y 10; `initial_delay_ms` 10 y 5000; `backoff_factor` 1, 1.5 y 10. |
| .03 | N | [pendiente] `retries` igual a `-1`, `11`, `"5"`, `5.0` o `true` ⇒ `E_CONFIG_INVALID` (exit 2) con el rango 0 a 10 en el `hint`: `valid range: 0..10` fuera de rango y `set retries to an integer between 0 and 10` con otro tipo. |
| .04 | N | [pendiente] `initial_delay_ms` igual a `9` o `5001` ⇒ `E_CONFIG_INVALID` con `valid range: 10..5000` en el `hint`. |
| .05 | N | [pendiente] `backoff_factor` igual a `0.5`, `11`, `"2"` o `true` ⇒ `E_CONFIG_INVALID` con el rango 1 a 10 en el `hint`: `valid range: 1..10` fuera de rango y `set backoff_factor to a number between 1 and 10` con otro tipo. |
| .06 | N | [pendiente] La clave `max_delay_ms` en `[lock]` ⇒ `E_CONFIG_INVALID` con `retries`, `initial_delay_ms` y `backoff_factor` en el `hint`. |
| .07 | N | [pendiente] Los `hint` de sección desconocida y de clave de primer nivel desconocida nombran `[lock]`, después de `[content]`. |
| .08 | P | [pendiente] `load_logging_config` con `[lock] retries = 11` devuelve la configuración del log sin fallar. |

#### UT-CLI-04 — Opciones que no existen

Requisitos: RF-16, RF-19, RF-24 · Archivo: `tests/test_cli.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | `--format`, `--config`, `--home`, `--quiet`, `--verbose`, `--no-color`, `--timeout` y `--backend` ⇒ `E_USAGE`, exit 2, cada una. |

#### UT-CLI-05 — `--log-level`

Requisitos: RF-18, PRD §12.1 · Archivo: `tests/test_cli.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `--log-level debug` sobreescribe `[logging].level`. |
| .02 | N | Después del subcomando ⇒ `E_USAGE`. |

#### UT-CLI-08 — UTF-8 y LF

Requisitos: RF-30 · Archivo: `tests/test_cli.py`

Por pipe en subprocess, con cp1252 y `PYTHONUTF8=0`.

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | JSON con texto no ASCII ⇒ bytes UTF-8. |
| .02 | P | JSON de error y resumen en `stderr` ⇒ UTF-8. |
| .03 | N | Ningún `\r\n` en `stdout` ni `stderr`. |

#### UT-CLI-09 — Códigos de salida y JSON de error

Requisitos: RF-22 · Archivo: `tests/test_cli.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Cada uno de los 23 códigos `E_*` ⇒ su exit (6 para `E_OUTLOOK_NOT_RUNNING`); forma `{ok: false, command, error: {code, message, hint}}` formateada, un solo JSON y resumen en `stderr`. |

#### UT-CLI-10 — `doctor`: dependencias en Apple Mail

Requisitos: RF-23 · Archivo: `tests/test_cli.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | `store` falla ⇒ `envelope_index` `not evaluated: store failed`; `schema` y `readonly_strategy` `not evaluated: envelope_index failed`; `config` con bloques `not evaluated: schema failed`; `python`, `home`, `accounts_db`, `state` y `lock` evaluados. |
| .02 | P | `store` falla sin bloques ⇒ `config` `ok=true` con `0 account block(s) declared; available accounts: unknown (schema failed)`. |
| .03 | N | `envelope_index` falla con `store` bien ⇒ `schema` y `readonly_strategy` `not evaluated: envelope_index failed`. |
| .04 | N | `schema` falla ⇒ resolución de `config` `not evaluated: schema failed`; una config con sintaxis inválida se reporta igual. |
| .05 | P | Sin bloques, dependencia bien y `accounts_db` caído ⇒ `available accounts: unknown (Accounts4.sqlite unavailable)`. |

#### UT-CLI-11 — `doctor`: `state`

Requisitos: RF-23 · Archivo: `tests/test_cli.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `lookback = "15min"` y sin `state.json` ⇒ el detalle de `doctor` (§12.8) con `15min`. |
| .02 | P | Con cursor ⇒ `ok=true`, `cursor last_date_received=<n> last_uid=<n>`. |

#### UT-CLI-12 — `doctor`: `envelope_index`

Requisitos: RF-23 · Archivo: `tests/test_cli.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Con `-shm` ⇒ abre la base viva; `readonly_strategy` `live_ro`. |
| .02 | N | Base ilegible (permiso) ⇒ `ok=false`. |

#### UT-CLI-13 — Home

Requisitos: RNF-05 · Archivo: `tests/test_cli.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | POSIX: home 0755 ⇒ `home` `ok=false`. |
| .02 | N | `win32` parcheado: crear el archivo de prueba lanza `PermissionError` ⇒ `ok=false`. |

#### UT-CLI-14 — Comando `mcp`

Requisitos: RF-84, RF-87, AC-75 · Archivo: `tests/test_cli.py`

**Tabla: Casos de UT-CLI-14**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `mailquery --help` lista `mcp` con el texto `serve the read commands as MCP tools over stdio`, y su línea `Output:` dice que `mcp serve` habla el protocolo MCP por stdout. |
| .02 | N | `mailquery mcp` ⇒ `E_USAGE`, exit 2, JSON de error con `"command": "mcp"`. |
| .03 | N | `mailquery mcp serve extra` ⇒ lo mismo. |
| .04 | P | `mailquery mcp --help` y `mailquery mcp serve --help` muestran `claude mcp add --scope user mailquery -- mailquery mcp serve` y la entrada genérica `mcpServers`. |
| .05 | P | `mailquery --log-level debug mcp serve` se acepta. |
| .06 | P | `cli.main` con `mcp serve` en el mismo proceso, con stdin y stdout sustituidos, responde a `initialize` y devuelve 0 al terminar stdin. |

#### UT-CLI-15 — Reintento del lock en los comandos

Requisitos: RF-89, AC-79, AC-80 · Archivo: `tests/test_cli.py`

**Tabla: Casos de UT-CLI-15**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | [pendiente] Lock retenido 2 s por otro proceso, sin `[lock]`: `search` termina con exit 0 tras liberarse y su salida es la de una ejecución sin espera salvo `generated_at`. |
| .02 | N | [pendiente] `retries = 2`, `initial_delay_ms = 100` y lock retenido 3 s: `E_LOCKED` (exit 5), no antes de 300 ms ni después de 2 s, con el `message` `another mailquery run is already in progress` y el `hint` `still held after 2 retries: <ruta>; retry later ([lock] in ~/.mailquery/config.toml sets the retries)`, comparados literalmente con la ruta del lock. |
| .03 | N | [pendiente] `retries = 0` y lock retenido: `E_LOCKED` sin esperar, con el `hint` `wait for the running invocation to finish and retry (the harness should only retry exit code 5)`. |
| .04 | P | [pendiente] `search`, `new`, `show`, `attachment` y `mailboxes` construyen el lock con `config.lock`. |
| .05 | N | [pendiente] Cada comando de datos con `retries = 11`: `E_CONFIG_INVALID` (exit 2) con el rango en el `hint`, sin tomar el lock. |
| .06 | P | [pendiente] `doctor` con el lock retenido: `held by another mailquery process` sin ninguna pausa, con cualquier `[lock]`; con `retries = 11`, el chequeo `config` informa el error y el chequeo `lock` responde sin esperar. |
| .07 | P | [pendiente] `mailquery --help` muestra, después de la línea `Configuration:`, la línea `Lock: a busy run lock is retried 5 times, pausing 150 ms and doubling each time ([lock] in config.toml)`. |
| .08 | P | [pendiente] Dos `new` lanzados a la vez, cada uno de menos de 2 s: los dos terminan con exit 0 y cada mensaje nuevo sale en uno solo. |
| .09 | N | [pendiente] El archivo del lock no se puede abrir: el comando da `E_PERMISSION` sin esperar. |

#### UT-INS-01 — Comprobación final de `install.ps1`

Requisitos: RNF-05 · Archivo: `tests/test_install_scripts.py`

Solo en `win32`, con `pipx` y `mailquery` falsos al inicio del `PATH`.

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | `import win32com` falla en el venv ⇒ muestra el problema con el hint `pipx reinstall mailquery`, exit ≠ 0. |
| .02 | N | `mailquery -v` falla o no muestra `backend outlook` ⇒ ídem. |
| .03 | P | Todo bien ⇒ exit 0 y `config.toml` sembrado con la ACL restringida. |

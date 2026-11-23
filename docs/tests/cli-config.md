# CLI, configuración, log y salida

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

#### UT-INS-01 — Comprobación final de `install.ps1`

Requisitos: RNF-05 · Archivo: `tests/test_install_scripts.py`

Solo en `win32`, con `pipx` y `mailquery` falsos al inicio del `PATH`.

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | `import win32com` falla en el venv ⇒ muestra el problema con el hint `pipx reinstall mailquery`, exit ≠ 0. |
| .02 | N | `mailquery -v` falla o no muestra `backend outlook` ⇒ ídem. |
| .03 | P | Todo bien ⇒ exit 0 y `config.toml` sembrado con la ACL restringida. |

#### UT-LOG-01 — Rotación

Requisitos: RF-18 · Archivo: `tests/test_logging.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | B | Con `max_size_mb = 1`, al superar 1 MB ⇒ `mailquery.log.1`. |
| .02 | B | 7 rotaciones ⇒ solo `.1`–`.5`; el más antiguo se borra. |

#### UT-LOG-02 — Permisos del log

Requisitos: RNF-05 · Archivo: `tests/test_logging.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | POSIX: `mailquery.log` 0600. |
| .02 | P | POSIX: rotados 0600. |
| .03 | P | Una ejecución terminada no deja abierto el archivo de log (limpieza segura en Windows). |

#### UT-LOG-03 — Formato

Requisitos: RF-18, RNF-07 · Archivo: `tests/test_cli.py`, `tests/test_logging.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `YYYY-MM-DD HH:MM:SS,mmm LEVEL logger run=…`. |
| .02 | P | `event=start command=… backend=apple_mail`. |
| .03 | P | Línea del store con estrategia y versión. |
| .04 | P | `event=end` con `exit_code` y conteos. |

#### UT-LOG-04 — Contenido

Requisitos: RF-18, RNF-05 · Archivo: `tests/test_logging.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Error ⇒ `code` + mensaje. |
| .02 | N | Con `--log-level debug` y etiquetas no disponibles, un error cuyo mensaje contiene asunto, dirección, nombre de persona, carpeta, etiqueta de cuenta, ruta, término de búsqueda y uid, tras un `search --text` ⇒ ninguno de esos datos, ni uuids de cuenta, cuerpo ni `snippet`, aparece en el log. |
| .03 | P | Warnings ⇒ número y códigos `W_*`, sin el detalle. |
| .04 | N | Error que no es `E_INTERNAL` ⇒ sin traceback. |

#### UT-OUT-01 — JSON formateado

Requisitos: RF-16 · Archivo: `tests/test_output.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Texto no ASCII (`ñ`, `á`, emoji) ⇒ sin escapes `\u`. |

#### UT-OUT-02 — Fechas

Requisitos: RNF-08, PRD §11.3 · Archivo: `tests/test_output.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | B | Epoch 1 ⇒ ISO 8601 con el offset local. |
| .02 | B | Epoch 0 ⇒ `null`. |
| .03 | N | `None` ⇒ `null`. |
| .04 | N | `1e20` ⇒ `null` (no representable). |

#### UT-OUT-03 — Limpieza de contenido

Requisitos: RNF-09, RF-52 · Archivo: `tests/test_output.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Caracteres de control en `snippet` ⇒ eliminados. |
| .02 | P | Secuencias ANSI en `body_text` de `show` ⇒ eliminadas. |

#### UT-SNI-01 — `--show-native-id` en `show`

Requisitos: RF-83, RF-73, AC-68, AC-70 · Archivo: `tests/test_show_native_id.py`

**Tabla: Casos de UT-SNI-01**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Con Apple Mail, `show <uid> --show-native-id` da la misma salida que sin la opción (salvo `generated_at`). |
| .02 | P | Con un plugin con `display_native_id`, `message.uid` es `<driver>:<forma nativa>`; las demás claves y valores, los textos de los warnings y `cached_path` son los mismos que sin la opción, y `cache.db` no cambia. |
| .03 | P | Con un plugin sin el gancho, la salida es la misma con la opción y sin ella. |
| .04 | N | Un plugin cuya forma nativa no cumple las reglas de un `<native_id>` ⇒ `E_PLUGIN_FAILED` (exit 3) y sin mensaje en la salida. |
| .05 | N | `search`, `new`, `attachment`, `mailboxes` y `doctor` con `--show-native-id` ⇒ `E_USAGE` (exit 2), sin crear el home. |
| .06 | N | Un `display_native_id` que supera el tope de 30 s (acortado en el test) ⇒ `E_CLIENT_TIMEOUT`. |
| .07 | P | `show --help` describe `--show-native-id` como opción de depuración. |
| .08 | B | Con `--fields subject`, el `uid` que siempre se entrega muestra la forma nativa. |

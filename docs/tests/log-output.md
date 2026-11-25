# Log y salida

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

#### UT-LOG-05 — Log en JSON

Requisitos: RF-88, RNF-05, AC-77 · Archivo: `tests/test_logging.py`, `tests/test_cli.py`

**Tabla: Casos de UT-LOG-05**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Sin la clave o con `false`, `search` escribe en `mailquery.log` con el formato de texto y no crea `mailquery.jsonl`; un `mailquery.jsonl` existente y sus rotados no cambian. |
| .02 | P | Con `true`, escribe solo en `mailquery.jsonl`; un `mailquery.log` existente no cambia. |
| .03 | P | Cada línea es un objeto con `ts` (ISO 8601 con milisegundos y desfase), `level`, `logger`, `run` y `fields`; `text` solo cuando el evento tiene texto sin forma `clave=valor`. |
| .04 | P | En `fields`, `exit_code` y `duration_ms` son números, `truncated` es booleano (también un valor `TRUE` o `False` en cualquier combinación de mayúsculas), un valor `-` es `null` y `checks` de `doctor` es texto (`3/5`). |
| .05 | P | `event=error` lleva su mensaje completo en `fields.message`, como texto también si es numérico, si parece un booleano (`true`) o si tiene espacios. |
| .06 | N | Con el escenario de UT-LOG-04.02, ninguna línea contiene asuntos, direcciones, uids ni rutas. |
| .07 | P | Un `E_INTERNAL` lleva su traceback en `traceback`. |
| .08 | B | Con `level = "warning"`, o con `--log-level warning`, no hay líneas `INFO` en `mailquery.jsonl`. |
| .09 | P | POSIX: `mailquery.jsonl` y sus rotados tienen permisos 0600. |
| .10 | B | Con `max_size_mb = 1`, `mailquery.jsonl` rota a `mailquery.jsonl.1` y se conservan 5 rotados; `mailquery.log` y sus rotados no cambian. |
| .11 | P | La misma ejecución en los dos formatos produce los mismos eventos, en el mismo orden y con los mismos campos. |
| .12 | N | El formato JSON solo se aplica al logger `mailquery` y sus hijos: un logger de otro nombre, como el de un plugin, no recibe el formateador JSON ni escribe en `mailquery.jsonl`. |

#### UT-LOG-06 — Ruta del log en los mensajes

Requisitos: RF-88, AC-75, AC-77 · Archivo: `tests/test_cli.py`, `tests/test_outlook.py`

**Tabla: Casos de UT-LOG-06**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | El `hint` de `E_INTERNAL` nombra `mailquery.jsonl` con `[logging].json = true` y `mailquery.log` sin ella. |
| .02 | P | Los `hint` de Outlook de un error COM interno y de un miembro bloqueado por el proxy de solo lectura nombran el archivo del formato activo. |
| .03 | P | La ayuda raíz nombra `mailquery.log` y `mailquery.jsonl`. |

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

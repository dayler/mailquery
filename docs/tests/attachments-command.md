# Comando attachment

#### UT-AM-01 — Bloqueo con fixtures reales

Requisitos: AC-09/AC-10 · Archivo: `tests/test_backends.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Mensaje con un adjunto hostil y otro seguro: `--index` del seguro, `--index` del hostil y `--all` ⇒ `E_ATTACHMENT_BLOCKED` (exit 4); nada escrito. |
| .02 | N | Nombres con traversal, separadores, `..`, `C:`, ADS, RLO/controles y reservado de Windows desde el fixture ⇒ bloqueo del mensaje. |
| .03 | N | Adjunto con `MZ` en los primeros bytes ⇒ bloqueo del mensaje; un archivo seguro del mismo mensaje no se escribe. |
| .04 | N | Mensaje con un adjunto no solicitado hostil: `--index` de un seguro ⇒ bloqueo (regla de todos los nombres). |
| .05 | P | Mensaje con todos los adjuntos permitidos ⇒ extracción correcta. |

#### UT-AM-02 — Índices, nombres y sanitización

Requisitos: AC-07/AC-11 · Archivo: `tests/test_backends.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Tres adjuntos con dos nombres repetidos ⇒ índices 1..N estables y distintos archivos `<NN>_<sanitized>`. |
| .02 | P | `show` y `attachment` devuelven el mismo `index` y el mismo `name` original para cada adjunto. |
| .03 | P | Sanitización sobre nombres Unicode/largos del fixture: NFKC, reemplazos, límites de 150/153 bytes y ruta final correcta. |
| .04 | P | `cached_path` de `show` apunta al archivo regular publicado. |

#### UT-AM-03 — Extracción y disponibilidad

Requisitos: AC-12/AC-15, AC-20 · Archivo: `tests/test_integration.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Primera extracción `cached: false`; segunda `cached: true`; `--force` re-extrae. |
| .02 | N | Adjunto cuyo `.emlx` no existe ⇒ `E_ATTACHMENT_UNAVAILABLE` (`not_local`). |
| .03 | N | Adjunto externalizado de `.partial.emlx` no verificable ⇒ `E_ATTACHMENT_UNAVAILABLE` (`unsupported`). |
| .04 | N | `--all` con un adjunto externalizado no verificable falla sin parciales; `--index` de un adjunto local seguro del mismo mensaje tiene éxito y no evalúa el externalizado no solicitado. |
| .05 | N | S/MIME cifrado ⇒ `E_ATTACHMENT_UNREADABLE` (`smime`), nunca `E_USAGE`; `show` devuelve `[]`. |
| .06 | N | MIME/base64 corrupto ⇒ `E_ATTACHMENT_UNREADABLE` (`corrupt`). |
| .07 | P | Adjunto de 0 bytes se guarda con `size_bytes: 0` y `sha256` del vacío. |
| .08 | P | Archivo de caché borrado antes de `attachment` ⇒ se re-extrae una vez. |
| .09 | N | Un fallo en `--all` no deja archivos parciales ni caché nueva incompleta. |

#### UT-AM-04 — Solo lectura e integración

Requisitos: AC-12, RNF-13 · Archivo: `tests/test_integration.py`

**Tabla: Casos de UT-AM-04**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Tras `attachment` (éxito, caché, bloqueo, límite), hashes y `mtime` del store no cambian. |
| .02 | P | Todas las escrituras quedan bajo `~/.mailquery` (`attachments/`, `tmp/`, log/lock/estado); staging limpio. |
| .03 | P | Directorios `0700` y archivos `0600` en POSIX; sin `+x` (condición POSIX explícita; en Windows se prueba la herencia de ACL y no se relajan permisos). |
| .04 | P | El backend declara las capacidades de RF-36 y `attachments: "local"`; `doctor` las muestra. |

#### UT-ATC-01 — `show.attachments`

Requisitos: AC-07 · Archivo: `tests/test_cli.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Tres adjuntos ⇒ `[{index:1,name:"factura.pdf",cached_path:null}, …]` con índices estables 1..N. |
| .02 | P | Con un archivo en caché (regular) ⇒ `cached_path` absoluto y correcto; sin caché ⇒ `null`. |
| .03 | N | Nombre no seguro ⇒ `cached_path: null` aunque exista un archivo con ese nombre calculado; `show` no bloquea por contenido. |
| .04 | N | `show` no crea caché de adjuntos, staging ni `state.json`; con Apple Mail no escribe nada más, y solo un driver que usa la librería puede escribir en la caché de ids nativos. |
| .05 | N | Driver con `attachments: "none"` ⇒ `attachments: []`. |
| .06 | N | S/MIME cifrado ⇒ `attachments: []`, sin `W_ATTACHMENTS_UNAVAILABLE`, conservando el warning de cuerpo de 2.0.1. |
| .07 | P | El `index` de `show` coincide con el de `attachment` para el mismo mensaje. |
| .08 | N | `[attachments].enabled = false` no afecta a `show`. |
| .09 | N | `cached_path: null` si el archivo en caché es symlink, directorio o dispositivo, aunque exista; solo archivos regulares cuentan. |
| .10 | P | Un adjunto que `attachment` bloquearía **por contenido** (`MZ`) pero con archivo regular en caché sigue mostrando `cached_path` no nulo: `show` no inspecciona contenido. |

#### UT-ATC-02 — Argumentos, uid y precedencia temprana

Requisitos: AC-08 · Archivo: `tests/test_cli.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Sin modo o con ambos ⇒ `E_USAGE` "attachment requires exactly one of --index or --all". |
| .02 | N | `--index 0`, `-1`, `abc`, `1.5` ⇒ `E_USAGE` "invalid --index <v>: expected a positive integer (1 or greater)". |
| .03 | N | uid malformado ⇒ `E_USAGE`; driver desconocido ⇒ `E_DRIVER_UNKNOWN`; ambos antes de crear el home, leer config o abrir el store, y sin escribir estado ni caché. |
| .04 | N | `config.toml` inválido ⇒ `E_CONFIG_INVALID`; driver de `[scope]` no instalado ⇒ `E_DRIVER_UNKNOWN`. |
| .05 | N | `enabled = false` ⇒ `E_ATTACHMENTS_DISABLED` (exit 2) antes de abrir el store; `show` no se ve afectado. |
| .06 | N | Driver instalado pero no declarado ⇒ `E_ACCOUNT_NOT_IN_SCOPE` (exit 2) sin cargar el driver; el hint indica declarar la cuenta. |
| .07 | N | `attachments: "none"` ⇒ `E_ATTACHMENT_UNAVAILABLE` (`unsupported`) antes de abrir el store. |
| .08 | P | Entrada con uid legado sin prefijo: `attachment 83143 --index 1` en macOS y `attachment <EntryID> --index 1` en Windows se resuelven con el driver nativo y devuelven `uid` prefijado. |
| .09 | N | Precedencia de filas adyacentes de la tabla de §12.11, table-driven: `--index 9` sobre mensaje con nombre bloqueado ⇒ `E_USAGE` (fila 10 antes que 11); `enabled=false` + `attachments:none` ⇒ `E_ATTACHMENTS_DISABLED` (fila 4 antes que 5); S/MIME + `--index 9` ⇒ `E_ATTACHMENT_UNREADABLE` (fila 8 antes que 10); uid con driver no instalado + `enabled=false` ⇒ `E_DRIVER_UNKNOWN` (fila 2 antes que 4). |

#### UT-ATC-03 — Validaciones con el store

Requisitos: AC-08 · Archivo: `tests/test_cli.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Mensaje inexistente, borrado u oculto ⇒ `E_USAGE` "message uid <uid> was not found". |
| .02 | N | Mensaje sin adjuntos (sin señal S/MIME/ilegible) ⇒ `E_USAGE` "message <uid> has no attachments". |
| .03 | N | S/MIME/ilegible con lista vacía ⇒ `E_ATTACHMENT_UNREADABLE` (exit 3) antes de la comprobación de “0 adjuntos”. |
| .04 | N | `--index N` mayor que M ⇒ `E_USAGE` con el texto de índice fuera de rango ("out of range: message ... has 3 attachment(s) (valid: 1..3)"). |
| .05 | P | `--index` válido y `--all` recuperan los adjuntos solicitados. |
| .06 | N | `--all` con varios fallos (nombre en índice 1, contenido en índice 2, límite en índice 3) informa el primer fallo en orden de índice y no devuelve parciales. |
| .07 | N | Un `--index` de un adjunto con nombre seguro pero no disponible no evalúa el resto de adjuntos no solicitados. |

#### UT-ATC-04 — JSON, caché y `--force` por CLI

Requisitos: AC-12 · Archivo: `tests/test_cli.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Forma exacta de la respuesta de §12.11: `uid` prefijado, `output_dir` absoluto, `count`, ocho campos por adjunto, `warnings: []`, y `content_notice` con el texto exacto justo después de `generated_at`. |
| .02 | P | Primera corrida `cached:false`; segunda sin `--force` `cached:true` con `size_bytes`/`sha256` del archivo; `--force` `cached:false`. |
| .03 | N | Mensaje bloqueado ⇒ `E_ATTACHMENT_BLOCKED` (exit 4), sin archivos, sin caché servida, con el `message`/`hint` de los ejemplos de bloqueo de §12.5. |
| .04 | N | Un fallo de límite o disponibilidad no devuelve resultados parciales. |
| .05 | N | `--all` devuelve `count` = número de adjuntos devueltos. |
| .06 | N | Un fallo de E/S del motor (`E_IO`) o de permisos (`E_PERMISSION`) sale por CLI con su exit 3 y sin archivos; no se convierte en `E_INTERNAL`. |

#### UT-ATC-05 — `[attachments]` y config

Requisitos: AC-14 · Archivo: `tests/test_cli.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | `enabled=false` ⇒ `E_ATTACHMENTS_DISABLED` (2) antes del store; `show` intacto. |
| .02 | N | Rangos inválidos y `max_total_size_mb < max_file_size_mb` ⇒ `E_CONFIG_INVALID`. |
| .03 | P | Valores personalizados válidos se aplican en el comando. |

#### UT-ATC-06 — Disponibilidad y motivos

Requisitos: AC-15 · Archivo: `tests/test_cli.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | `not_local`, `not_downloaded`, `unsupported`, `network` ⇒ `E_ATTACHMENT_UNAVAILABLE` (3) con el `message`/`hint` del motivo. |
| .02 | N | S/MIME/corrupto/ilegible ⇒ `E_ATTACHMENT_UNREADABLE` (3) y nunca `E_USAGE` por “sin adjuntos”. |
| .03 | N | `attachments: none` ⇒ `E_ATTACHMENT_UNAVAILABLE` antes del store. |
| .04 | P | Adjunto vacío (0 bytes) se guarda y devuelve `size_bytes: 0`, `sha256` del vacío. |

#### UT-ATC-07 — Timeout de extracción

Requisitos: AC-43, AC-45 · Archivo: `tests/test_cli.py`

**Tabla: Casos de UT-ATC-07**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Extracción cuyo plazo configurado vence (inyectado con `_attachment_timeout`) ⇒ `E_CLIENT_TIMEOUT` (3) con el mensaje y el hint de RF-49, sin reintento, staging limpio y sin archivos nuevos. |
| .02 | N | El timeout no escribe estado ni caché parcial. |

#### UT-ATC-08 — Log de `attachment`

Requisitos: AC-19 · Archivo: `tests/test_cli.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `event=end` de `attachment` con `exit_code`, `count`, `cached`, `bytes` y `duration_ms`. |
| .02 | N | El log no registra uid, `native_id`, `original_name`, `sanitized_name`, rutas, cuentas ni términos. |
| .03 | P | `event=start` conserva `command`, `backend` y `drivers`. |
| .04 | N | Un `attachment` fallido registra `event=error` y **no** emite `event=end`. |

#### UT-ATC-09 — Ayuda y exits

Requisitos: AC-21 · Archivo: `tests/test_cli.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | La ayuda raíz lista `doctor`, `mailboxes`, `search`, `new`, `show`, `attachment` y la línea de exits de §12.7. |
| .02 | P | `attachment --help` coincide con §12.7 (usage, positional, options, examples, notes), ≤ 100 columnas y sin ANSI. |
| .03 | P | La ayuda raíz y las seis ayudas de subcomando (7 invocaciones) pasan `parse_args`. |
| .04 | N | Ningún texto de ayuda dice “cinco comandos”/“five commands”, muestra un uid entero como formato de salida o promete escritura fuera de `~/.mailquery`. |
| .05 | P | `attachment` sin `<uid>` ⇒ `E_USAGE`, exit 2. |

#### UT-ATC-10 — `attachment` con driver externo declarado

Requisitos: AC-07, AC-15 · Archivo: `tests/test_cli.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `attachment <plugin>:<native_id> --index 1` con un plugin declarado `attachments: "local"` devuelve el contrato JSON completo y escribe el archivo en la caché; el uid de salida va prefijado. |
| .02 | P | `--all` con el plugin devuelve todos los adjuntos locales y `count` correcto. |
| .04 | N | Un plugin declara `attachments: "none"` ⇒ `E_ATTACHMENT_UNAVAILABLE` antes del store. |

> `UT-ATC-10.03` (rechazo de `"remote"`) se retiró; lo sustituyen UT-RMT-01 y UT-RMT-02 (§9).

#### UT-RMT-01 — Extracción desde un plugin `"remote"`

Requisitos: AC-40 · Archivo: `tests/test_remote_attachments.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Plugin falso `attachments: "remote"`, `network: true`: `attachment <driver>:<id> --index N` devuelve el JSON de §12.11 (con `content_notice`) y escribe el archivo en la caché. |
| .02 | P | `--all` devuelve todos los adjuntos con `count` correcto; bloqueo por nombre y por contenido y límites (`max_file_size_mb`, `max_total_size_mb`, `max_count`) dan el mismo código y texto que con un plugin `"local"` equivalente. |
| .03 | P | Segunda corrida: `cached: true` y el plugin no recibe peticiones de bytes; `--force` las vuelve a pedir. |
| .04 | B | El núcleo no abre conexiones (`socket.socket` parcheado para fallar durante toda la corrida). |
| .05 | P | El manifiesto escrito es igual al de un plugin `"local"` equivalente con los mismos bytes (salvo marcas de tiempo y el nombre del driver). |

#### UT-RMT-02 — Fallo de origen del plugin `"remote"`

Requisitos: AC-41 · Archivo: `tests/test_remote_attachments.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | `reason: network` ⇒ `E_ATTACHMENT_UNAVAILABLE`, exit 3, con la plantilla de ese motivo; nunca `unsupported`. |
| .02 | N | `reason: not_local` ⇒ ídem con su plantilla. |
| .03 | B | Staging limpio y ningún archivo nuevo en la caché. |
| .04 | B | `--all` con fallos de red en los adjuntos 2 y 3 ⇒ se informa el 2 (§10, punto 10). |
| .05 | N | `reason: network` lanzado en el segundo bloque (dentro del hilo del corte duro) ⇒ `E_ATTACHMENT_UNAVAILABLE` con su plantilla, no `E_CLIENT_TIMEOUT`. |

#### UT-RMT-03 — Driver `attachments: "none"`

Requisitos: AC-42 · Archivo: `tests/test_remote_attachments.py`

**Tabla: Casos de UT-RMT-03**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | ⇒ `E_ATTACHMENT_UNAVAILABLE` (`unsupported`, exit 3) antes de abrir el store, con el hint nuevo de RF-48 literal. |

#### UT-RMT-04 — Corte duro en plugins externos

Requisitos: AC-44 · Archivo: `tests/test_remote_attachments.py`

**Tabla: Casos de UT-RMT-04**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | El plugin se bloquea antes del primer bloque (espera un `threading.Event` que el test no activa hasta el final): con el tope inyectado a 1 s, `E_CLIENT_TIMEOUT` (exit 3) con el mensaje y el hint de RF-49; la espera del núcleo, medida con `time.monotonic()`, cumple `elapsed < tope + 1`. |
| .02 | N | El plugin se bloquea entre dos bloques: ídem. |
| .03 | B | `--all` con los adjuntos 2 y 3 bloqueados: se informa el 2. |
| .04 | B | Staging limpio y sin archivos nuevos; el hilo del plugin se libera al terminar el test (evento) y no queda ningún hilo vivo. |
| .05 | N | Con `timeout_seconds` inyectado mayor que `METADATA_TIMEOUT_SECONDS` (parcheado a 0,05 s), un plugin que tarda más de 0,05 s en crear el flujo no se corta antes del tope del adjunto y la extracción termina con éxito. |
| .06 | B | Plazo ya vencido antes de pedir el siguiente bloque ⇒ `E_CLIENT_TIMEOUT` sin nueva petición al plugin (un solo bloque solicitado); flujo vacío ⇒ sin error; `close()` del iterador que lanza al vencer el plazo ⇒ sigue siendo `E_CLIENT_TIMEOUT`. |

#### UT-RMT-05 — Topes que no cambian y lo que no consume el tope

Requisitos: AC-43, AC-45 · Archivo: `tests/test_remote_attachments.py`

**Tabla: Casos de UT-RMT-05**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Con `timeout_seconds = 10` y `= 600`, el tope de metadatos de un plugin sigue siendo `METADATA_TIMEOUT_SECONDS` y el de cada llamada COM sigue siendo `outlook_com.CALL_TIMEOUT_SECONDS`. |
| .02 | P | Apple Mail y Outlook (doble): el tope se comprueba entre bloques y al terminar la llamada (un flujo lento entre bloques con tope inyectado da `E_CLIENT_TIMEOUT`); la creación del flujo ocurre en el hilo principal, no en uno aparte. |
| .03 | B | Un acierto de caché no invoca la factoría del tope; A7 se ejecuta después y no lo consume (con un detector lento simulado y el tope ya vencido, la respuesta es de éxito). |
| .04 | P | `cli` pasa al motor el valor de `[attachments].timeout_seconds` (espía sobre la factoría con `timeout_seconds = 180`). |
| .05 | N | Doble de Outlook con el watchdog COM (`outlook_com.CALL_TIMEOUT_SECONDS` parcheado) vencido antes del tope del adjunto ⇒ `E_CLIENT_TIMEOUT` con el mensaje y el hint de RF-31, no los de RF-49. |

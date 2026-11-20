# Búsqueda y lectura sobre Apple Mail

#### UT-SR-01 — Comodines y acentos

Requisitos: RF-08, RF-09, RF-10 · Archivo: `tests/test_search.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Subcadena sin comodines. |
| .02 | P | `*factura*`. |
| .03 | P | `factura*` ⇒ coincide en cualquier posición del texto (patrón sin ancla). |
| .04 | P | `?actura`. |
| .05 | P | `FACTURA` ⇒ coincide (sin mayúsculas). |
| .06 | P | `fáctura` ⇒ coincide con `factura` (sin acentos). |
| .07 | P | `[`, `.` y `(` se tratan como literales. |

#### UT-SR-02 — Términos de filtro

Requisitos: RF-08, RF-09, RF-10 · Archivo: `tests/test_search.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `--subject "*a* *b*"` ⇒ a AND b. |
| .02 | N | `--text "reserva confirmada"` con "confirmada … reserva" ⇒ no coincide. |
| .03 | N | `--from`, `--to` y `--cc` `"Perez Juan"` con "Juan Perez" ⇒ no coincide. |

#### UT-SR-03 — Acotamiento de `--text` en macOS

Requisitos: RF-15 · Archivo: `tests/test_search.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | `--text x` sin filtros ⇒ `E_UNBOUNDED_SCAN`, exit 4; el mensaje nombra `--text` y el hint lista los filtros que acotan en macOS. |
| .02 | N | `--text x --from ""` ⇒ `E_UNBOUNDED_SCAN`. |
| .03 | N | `--text x --include-mailbox INBOX` ⇒ `E_UNBOUNDED_SCAN`. |
| .04 | P | `--text x --to y` ⇒ ejecuta; `scan.candidates` cuenta los mensajes tras `--to`. |
| .05 | B | Candidatos == `max_scan` ⇒ ejecuta. |
| .06 | B | Con varios drivers, `max_scan` se compara con la suma de los candidatos de todos ellos. |

#### UT-SR-04 — `--include-mailbox`

Requisitos: RF-13 · Archivo: `tests/test_search.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Carpeta inexistente ⇒ `E_MAILBOX_NOT_FOUND`, hint con las carpetas de todas las cuentas declaradas. |
| .02 | P | `--include-mailbox` resuelve la carpeta dentro de su propio driver. |

#### UT-SR-05 — `body` en `search`/`new`

Requisitos: RF-04, RF-05 · Archivo: `tests/test_search.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | `.emlx` que no se puede abrir (`PermissionError` simulado) ⇒ `false/false/false` + `W_BODY_UNREADABLE`. |
| .02 | N | Ruta no resoluble ⇒ ídem. |
| .03 | N | Mensaje sin carpeta ⇒ ídem. |
| .04 | N | Corrupto recuperable ⇒ `true/true/false` + `W_EMLX_CORRUPT`. |
| .05 | N | S/MIME cifrado ⇒ `true/false/false` + `W_BODY_UNREADABLE: S/MIME encrypted content is not supported`, sin `W_EMLX_CORRUPT`. |
| .06 | N | S/MIME firmado ⇒ ídem con `signed`. |
| .07 | B | Cuerpo de 200 y de 201 caracteres ⇒ `body.truncated` `false` y `true`. |
| .08 | N | HTML sin texto ⇒ `available=true`, `readable=true`, `snippet: ""` y `W_HTML_NO_TEXT`. |

#### UT-SR-06 — Etiquetas no disponibles

Requisitos: PRD §15.2 · Archivo: `tests/test_search.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `search` ⇒ `W_ACCOUNT_LABELS_UNAVAILABLE`. |
| .02 | P | `show` ⇒ ídem. |
| .03 | P | Primera corrida de `new` ⇒ `W_ACCOUNT_LABELS_UNAVAILABLE` y `W_FIRST_RUN` al final. |

#### UT-SR-07 — Primera corrida de `new`

Requisitos: RF-01, RF-02 · Archivo: `tests/test_search.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | B | Mensaje exactamente en `D − lookback` ⇒ incluido. |
| .02 | B | Mensaje un segundo antes ⇒ excluido. |
| .03 | B | Alcance con un solo mensaje ⇒ lo emite. |
| .04 | B | `--limit` menor que la ventana ⇒ los `--limit` más recientes, en orden ascendente. |
| .05 | N | `--peek` ⇒ emite y no escribe estado. |
| .06 | P | Sin `--peek` ⇒ cursor en el último emitido y uids en el anillo. |
| .07 | B | Cuentas declaradas sin mensajes ⇒ `count: 0`, `W_FIRST_RUN`, sin estado. |
| .08 | B | Sin cuentas declaradas ⇒ `W_NO_ACCOUNTS` y `W_FIRST_RUN`, en ese orden, sin estado. |
| .09 | P | `lookback = "1h"` ⇒ `W_FIRST_RUN` con `1h`. |

#### UT-SR-08 — Lookback

Requisitos: RF-01 · Archivo: `tests/test_search.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Cada corrida usa `[new].lookback` de la config actual, aunque el estado guarde otro, y lo guarda en `cursor.lookback_seconds`. |

#### UT-SR-09 — Fechas inválidas

Requisitos: RF-01, RNF-08 · Archivo: `tests/test_search.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Fecha nula en la primera corrida ⇒ no entra. |
| .02 | B | Fecha 0 ⇒ no entra. |
| .03 | N | Fecha 1e20 ⇒ no entra. |
| .04 | N | En corridas siguientes ⇒ no entran ni mueven el cursor. |
| .05 | P | `search` las muestra con `date_received: null` y no aborta. |

#### UT-SR-10 — Fechas futuras en `new`

Requisitos: RF-01 · Archivo: `tests/test_search.py`

Reloj inyectado.

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Primera corrida ⇒ no entra ni cuenta como "el más reciente". |
| .02 | N | Corrida siguiente ⇒ no entra ni mueve el cursor. |
| .03 | P | Cuando deja de ser futura ⇒ entra en esa corrida. |
| .04 | B | Fecha igual al momento de la corrida ⇒ entra. |
| .05 | P | `search` y `show` la muestran con su fecha. |

#### UT-SR-11 — `show` y alcance

Requisitos: RF-03 · Archivo: `tests/test_search.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | uid de una cuenta declarada en una carpeta de `mailbox_list` ⇒ éxito, campos en el orden de §12.4. |
| .02 | P | uid de una cuenta declarada fuera de `mailbox_list` ⇒ éxito. |
| .03 | N | Sin cuentas declaradas ⇒ `E_ACCOUNT_NOT_IN_SCOPE`. |
| .04 | N | uid inexistente ⇒ `E_USAGE` `message uid … was not found`. |
| .05 | N | uid de un mensaje borrado ⇒ ídem. |
| .06 | N | `[scope]` con una cuenta desconocida ⇒ el mismo error que `search`, aunque el mensaje no esté en esa cuenta. |
| .07 | N | `mailbox_list` con una carpeta inexistente ⇒ `E_MAILBOX_NOT_FOUND`. |
| .08 | B | Cuerpo de 20.000 y de 20.001 caracteres ⇒ `body_truncated` `false` y `true` (con `W_BODY_TRUNCATED`). |

#### UT-SR-12 — `show`: adjuntos con cuerpo ilegible

Requisitos: RF-03, RF-04 · Archivo: `tests/test_search.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | `.emlx` ausente con adjuntos en el `Envelope Index` ⇒ nombres del índice + `W_ATTACHMENTS_UNAVAILABLE`. |
| .02 | N | S/MIME firmado sin fila en `attachments` ⇒ `attachments: []`, sin los adjuntos del MIME ni `W_ATTACHMENTS_UNAVAILABLE`. |

#### UT-SR-13 — Consultas con la base bloqueada

Requisitos: PRD §17 · Archivo: `tests/test_search.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | B | Consulta de `search.py` bloqueada una vez ⇒ éxito tras un reintento a los 100 ms. |
| .02 | N | Bloqueo persistente ⇒ `E_DB_BUSY`, exit 5, hint no vacío. |
| .03 | N | Catálogo de carpetas bloqueado (`store.py:572-580`) ⇒ `E_DB_BUSY`. |

#### UT-SR-14 — INBOX

Requisitos: RF-07 · Archivo: `tests/test_search.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `inbox` de primer nivel en minúsculas ⇒ INBOX. |
| .02 | N | `Proyectos/Inbox` ⇒ no es INBOX, ni en `is_inbox` ni en el alcance. |

#### UT-SR-15 — Dedupe

Requisitos: RF-06 · Archivo: `tests/test_search.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Duplicado en una carpeta normal y un buzón agregado ⇒ canónico la carpeta normal. |
| .02 | B | `global_message_id` 0 ⇒ único, `duplicate_count: 1`. |

#### UT-SR-16 — Referencias de carpeta entre cuentas

Requisitos: RF-13, PRD §15.3 · Archivo: `tests/test_search.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Con `Proyectos/Inbox` en la cuenta, `INBOX` ⇒ la bandeja de la cuenta. |
| .02 | P | `--include-mailbox` se resuelve en el orden de los bloques: `INBOX` con dos cuentas declaradas ⇒ la de la primera. |
| .03 | P | Path o URL exactos que coinciden con el nombre de otra carpeta ⇒ gana el path o la URL, cada uno. |
| .04 | P | Dos carpetas con el mismo nombre en paths distintos ⇒ la primera de `mailboxes`. |

#### UT-SR-17 — Orden canónico de campos

Requisitos: RF-28, PRD §12.5 · Archivo: `tests/test_search.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Las claves de cada fila de `search` sobre el store sintético son exactamente `SEARCH_ROW_FIELDS`, en ese orden. |
| .02 | P | Las claves de `message` de `show` son exactamente `SHOW_FIELDS`, en ese orden, sobre el store sintético y sobre el doble de Outlook. |

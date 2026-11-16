# Outlook: datos y comandos

#### OL-06 — Stores candidatos

Requisitos: RF-29 · Archivo: `tests/test_outlook.py`

Cada caso declara la cuenta y ejecuta `search` y `show`.

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Exchange en caché ⇒ `Exchange (<smtp>)`. |
| .02 | P | IMAP ⇒ `IMAP (<smtp>)`. |
| .03 | P | POP3 sobre PST ⇒ `POP3 (<smtp>)`, no `PST (…)`. |
| .04 | P | EAS ⇒ `EAS (<smtp>)`. |
| .05 | P | PST local ⇒ `PST (<nombre>)`, `email: null`. |
| .06 | P | PST en disco extraíble ⇒ candidato. |

#### OL-07 — Stores excluidos

Requisitos: RF-34 · Archivo: `tests/test_outlook.py`

Cada caso en `mailboxes.excluded_stores` con `label`, `path` y `reason`.

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Compartido ⇒ `shared_mailbox`, `path: null`. |
| .02 | N | Carpetas públicas ⇒ `public_folders`. |
| .03 | N | Exchange en modo Online ⇒ `online_mode`. |
| .04 | N | Otro store de Exchange sin copia local ⇒ `online_mode`. |
| .05 | N | PST en UNC ⇒ `network_path` con la ruta. |
| .06 | N | PST en unidad mapeada ⇒ `network_path`. |
| .07 | N | Cuenta de otro tipo ⇒ `unsupported_account_type`. |
| .08 | N | Store ilegible con nombre ⇒ `unavailable` con su nombre. |
| .09 | N | Store ilegible sin nombre ⇒ `unavailable`, etiqueta `unknown`, `path: null`. |
| .10 | P | Un store `unavailable` no impide leer los demás. |
| .11 | N | El `CallLog` no registra carpetas ni items de stores excluidos. |

#### OL-08 — `account.uuid`

Requisitos: RF-03, PRD.md §11.3 · Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Los 16 bytes del `PR_RECORD_KEY` con formato UUID en mayúsculas. |

#### OL-09 — Cuentas declaradas excluidas

Requisitos: RF-34 · Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Declarada y excluida con `path` ⇒ `W_STORE_EXCLUDED: <etiqueta> at <ruta> is excluded: <reason>` en `search`. |
| .02 | N | Sin `path` ⇒ el mismo texto sin ` at <ruta>`. |
| .03 | N | El mismo warning en `show` y `mailboxes`. |
| .04 | B | Todas excluidas ⇒ `count: 0` con `W_STORE_EXCLUDED` y `W_NO_ACCOUNTS`. |

#### OL-10 — INBOX

Requisitos: RF-08, PRD.md §11.3 · Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Bandeja en español ⇒ `INBOX`. |
| .02 | P | Subcarpeta de la bandeja ⇒ `INBOX/Facturas`. |
| .03 | P | PST sin bandeja ⇒ solo `mailbox_list`, sin error. |

#### OL-11 — `path`, `name` y `url`

Requisitos: RF-03, PRD.md §11.3 · Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Separador `/`. |
| .02 | P | `%` y `/` dentro de un nombre ⇒ `%25` y `%2F`. |
| .03 | P | `name` = último segmento codificado. |
| .04 | P | `url` = `outlook://<uuid>/<path>` con los segmentos decodificados y percent-encoded según RFC 3986, también con caracteres no ASCII. |

#### OL-12 — Carpetas listadas y contadores

Requisitos: RF-03, PRD.md §11.3 · Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Carpetas de sincronización y sus subcarpetas ⇒ ocultas, también con nombres en otro idioma. |
| .02 | N | Calendario, contactos, tareas y carpetas de búsqueda ⇒ no se listan. |
| .03 | P | `total`/`unread` = items buscables: la convocatoria cuenta; acuse, tarea y borrado IMAP no. |

#### OL-13 — Referencias a la bandeja

Requisitos: RF-08, RF-14 · Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `INBOX` y `INBOX/…` en cualquier idioma. |

#### OL-14 — uid y orden

Requisitos: RF-27, RNF-04 · Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | uid = `EntryID` permanente en hex mayúsculas, no el id corto de la tabla. |
| .02 | B | Misma fecha ⇒ desempata por `uid` como string. |

#### OL-15 — Fechas

Requisitos: PRD.md §11.3 · Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Hora de entrega y de envío en UTC ⇒ ISO 8601 con el offset local, con una zona inyectada distinta de UTC. |
| .02 | B | Cambio de horario. |

#### OL-16 — Direcciones

Requisitos: RF-11, PRD.md §11.3 · Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Dirección SMTP del item. |
| .02 | N | DN interno de Exchange ⇒ no se usa. |
| .03 | N | Sin dirección SMTP ⇒ `address: ""` y se conserva `name`. |

#### OL-17 — Dedupe

Requisitos: RF-07 · Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Mismo Message-ID en dos carpetas ⇒ canónico INBOX, `duplicate_count: 2`. |
| .02 | N | Sin Message-ID o vacío ⇒ único. |

#### OL-18 — Items buscables

Requisitos: PRD.md §11.3 · Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Acuse y tarea ⇒ ignorados en `search`, `new` y `show`. |
| .02 | N | Borrado IMAP ⇒ ídem. |
| .03 | P | Convocatoria y S/MIME ⇒ incluidos. |

#### OL-19 — Marcas y adjuntos

Requisitos: RF-13 · Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Marcado no completado ⇒ `is_flagged=true`. |
| .02 | N | Marcado completado ⇒ `is_flagged=false`. |
| .03 | P | Adjunto visible ⇒ cuenta en `has_attachments` y se lista. |
| .04 | N | Adjunto oculto ⇒ no cuenta ni se lista. |

#### OL-20 — Cuerpo

Requisitos: RF-05, RF-06 · Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Item con `BodyFormat` HTML y el mismo texto en `Body` y `HTMLBody` ⇒ cuerpo del HTML, con la forma de la fila de `search` y de `show` y sus valores. |
| .02 | P | Texto vacío y HTML ⇒ HTML convertido; un item de reunión no tiene `BodyFormat` ni `HTMLBody` (`AttributeError`) ⇒ `Body`. |
| .03 | N | HTML sin texto ⇒ `available=true`, `readable=true`, `snippet: ""` y `W_HTML_NO_TEXT`. |
| .04 | N | Solo cabeceras ⇒ `false/false/false` + `W_BODY_NOT_LOCAL`, sin miembros de descarga. |
| .05 | N | S/MIME cifrado ⇒ `true/false/false` + `W_BODY_UNREADABLE` con su texto; el `CallLog` no registra miembros de cuerpo ni de adjuntos. |
| .06 | N | S/MIME firmado ⇒ ídem con `signed`. |
| .07 | N | Item que no se puede abrir ⇒ `false/false/false` + `W_BODY_UNREADABLE`. |

#### OL-21 — `show`: adjuntos con el item ilegible

Requisitos: RF-04, RF-05 · Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Con `has_attachments` ⇒ `attachments: []` + `W_ATTACHMENTS_UNAVAILABLE`. |
| .02 | N | Sin adjuntos ⇒ `attachments: []` sin el warning. |

#### OL-22 — `show`: cabeceras

Requisitos: RF-04, PRD.md §11.3 · Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Cabeceras de transporte. |
| .02 | P | Correo interno sin cabeceras ⇒ From/To/Cc/Subject/Date/Message-ID sintetizadas. |

#### OL-23 — `show`: resolución del uid

Requisitos: RF-04, RF-27 · Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Minúsculas ⇒ `E_USAGE` con `invalid uid …: expected an uppercase hexadecimal EntryID`, hint no vacío. |
| .02 | N | uid inválido con `pywin32` ausente ⇒ `E_USAGE` antes de conectar. |
| .03 | N | uid inexistente, también con un `EntryID` que no coincide con ningún store ⇒ `message uid … was not found` con hint que remite a `excluded_stores`. |
| .04 | N | Item que no es correo ⇒ not found. |
| .05 | N | Item en una carpeta oculta ⇒ not found. |
| .06 | N | Store excluido identificado por `PR_RECORD_KEY` ⇒ `E_ACCOUNT_NOT_IN_SCOPE` con el motivo, sin abrir items del store. |
| .07 | P | Cuenta declarada, carpeta fuera de `mailbox_list` ⇒ éxito. |

#### OL-24 — `--text`, `--to` y `--cc` en Windows

Requisitos: RF-17 · Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | `--to x` sin acotar ⇒ `E_UNBOUNDED_SCAN`; el mensaje nombra `--to`; el hint no lista `--to` ni `--cc`. |
| .02 | N | `--text x` sin acotar ⇒ `E_UNBOUNDED_SCAN`; el hint no lista `--to` ni `--cc`. |
| .03 | N | `--text x --to y` ⇒ `--to` no acota; una sola validación y un solo error. |
| .04 | N | `--to x --since 1y` con más candidatos que `max_scan` ⇒ `E_SCAN_TOO_LARGE`. |
| .05 | P | `--to x --since 1d` ⇒ ejecuta; `scan.mode = metadata`; `scan.candidates` = mensajes antes de aplicar `--to`; `scan.messages_read` = items abiertos; solo el mensaje devuelto con cuerpo legible lee sus cabeceras de transporte (1 lectura de `PR_TRANSPORT_MESSAGE_HEADERS`). |
| .06 | P | `--text` acotado ⇒ coincidencias en el cuerpo; `scan.mode = text`; cada candidato cuyo cuerpo se lee lee también sus cabeceras de transporte (3 lecturas, una por candidato legible). |
| .07 | P | `--text x --to y --since 1d` ⇒ `scan.candidates` = mensajes antes de aplicar `--to`; el filtro de destinatarios abre todos los items pero solo el que coincide lee su cuerpo y sus cabeceras de transporte (1 lectura). |

#### OL-25 — `new` en Windows

Requisitos: RF-01, RF-34 · Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | El estado guarda uids hex. |
| .02 | N | Segunda corrida ⇒ no reemite. |
| .03 | P | Mensaje movido dentro de la ventana ⇒ `new` termina con exit 0 y lo emite con su nuevo uid. |
| .04 | N | Cuenta declarada excluida ⇒ `W_STORE_EXCLUDED` antes de `W_FIRST_RUN`. |

#### OL-26 — `doctor` en Windows

Requisitos: RF-25, RF-34 · Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | `pywin32` falla ⇒ `outlook`, `stores`, `readonly_strategy` y la resolución de `config` `not evaluated`. |
| .02 | N | Outlook cerrado ⇒ `outlook` `ok=false`, exit 0. |
| .03 | P | Sin bloques y `stores` fallido ⇒ `config` `ok=true` con `0 account block(s) declared; available accounts: unknown (stores failed)`. |
| .04 | N | Cuenta declarada excluida ⇒ `W_STORE_EXCLUDED` en el `detail` de `config`, que sigue con `ok=true`. |

#### OL-28 — Campos neutros

Requisitos: RF-30 · Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `is_aggregate` siempre `false`. |
| .02 | P | `labels_available` siempre `true`. |

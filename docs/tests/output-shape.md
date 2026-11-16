# Forma de la salida

#### UT-FLD-01 — Fila por defecto

Requisitos: AC-O01 (delta `PRD-v2.2.md`) · Archivo: `tests/test_fields.py`

| Caso | Tipo | Verifica                                                                                                                                                                                                                                                                |
| ---- | ---- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| .01  | P    | Sin `--fields`, cada fila de `search` y `new` tiene exactamente `uid`, `subject`, `from`, `date_received`, `is_read` y `has_attachments`, en ese orden, con los mismos valores que la fila completa; se comprueba sobre el store sintético y sobre el doble de Outlook. |
| .02  | P    | Los campos fuera de `messages[]` son los de antes más `content_notice`; `hint`, `scan` y, en `new`, `cursor` no cambian.                                                                                                                                                |

#### UT-FLD-02 — Sin lectura de cuerpos

Requisitos: AC-O01 (delta `PRD-v2.2.md`) · Archivo: `tests/test_fields.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Apple Mail: sin `--text`, `search` y `new` no llaman a la extracción del cuerpo (espía sobre `emlx._extract_body_text`) y leen las cabeceras de cada mensaje devuelto; `scan.messages_read` = número de mensajes devueltos. |
| .02 | P | Outlook (doble): sin `--text`, el `CallLog` no tiene accesos a `Body`, `HTMLBody` ni `BodyFormat`; `items_opened` cuenta los items abiertos para las cabeceras de A6; un item S/MIME no se abre. |
| .03 | P | Con `--text`, el cuerpo se lee para filtrar como hoy, pero sin `--fields snippet` la fila no lleva `snippet` ni `body`. |
| .04 | P | Plugin falso con espías: con la fila por defecto, `search` y `new` no llaman a `load_snippet` ni a `load_body`; el plugin no tiene `load_headers` y no se calculan las señales del remitente. |
| .05 | B | Apple Mail, mensaje cuyo `.emlx` no existe: `load_headers` no lee (`read=False`), el mensaje no cuenta en `scan.messages_read` y su fila sale sin warnings del remitente ni del cuerpo. |
| .06 | P | `--to` como filtro sin `--fields to`: filtra por destinatarios (los lee) y la fila no lleva `to` ni `cc`; las URLs de los nombres de destinatarios no se cuentan. |

#### UT-FLD-03 — `--fields` en `search` y `new`

Requisitos: AC-O02 (delta `PRD-v2.2.md`) · Archivo: `tests/test_fields.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `--fields snippet` añade `snippet` al final de la fila por defecto. |
| .02 | P | `--fields all` da la fila completa de `PRD.md` sección 12.5 (`SEARCH_ROW_FIELDS`). |
| .03 | P | `--fields to,uid` y `--fields uid --fields to` dan la fila por defecto más `to`, en el orden canónico. |
| .04 | N | `--fields remitente` ⇒ `E_USAGE`, exit 2, mensaje y hint literales de PRD-v2.2 sección 8; `--fields ""` y `--fields uid,,to` ⇒ ídem con `''`. |
| .05 | B | El error ocurre antes de crear el home (el `HOME` temporal no tiene `.mailquery`) y sin abrir el store. |
| .06 | B | D-24: `--fields "to, uid"` equivale a `--fields to,uid`; `--fields ALL` y `--fields Snippet` ⇒ `E_USAGE` con `unknown field 'ALL'` / `unknown field 'Snippet'`; `--fields " "` ⇒ ídem con `''`. |

#### UT-FLD-04 — `show --fields`

Requisitos: AC-O03 (delta `PRD-v2.2.md`) · Archivo: `tests/test_fields.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `--fields attachments` → `message` con solo `uid` y `attachments`; ningún warning de cuerpo; en un mensaje S/MIME, `attachments: []` (se lee el cuerpo para aplicar la regla, sin entregarlo). |
| .02 | P | `--fields body_text` → no consulta los adjuntos (`attachments()` y `attachment_names()` del backend no se llaman). |
| .03 | P | `--fields headers` → `uid` y `headers` sin leer el cuerpo (Apple Mail con `load_headers`; Outlook sin `Body`/`HTMLBody`). |
| .04 | P | Sin `--fields` → los mismos campos y valores que antes más `content_notice`. |
| .05 | N | Campo desconocido ⇒ `E_USAGE` con la lista de `show`. |
| .06 | P | `--fields source` y `--fields partial`, cada uno solo: leen el cuerpo, entregan `uid` y ese campo, y emiten los warnings del cuerpo (cuerpo entregado según RF-74). |

#### UT-FLD-05 — Warnings según lo entregado

Requisitos: AC-O09 (delta `PRD-v2.2.md`) · Archivo: `tests/test_fields.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Mensaje con texto oculto y URLs en el cuerpo: `W_HIDDEN_CONTENT` y el conteo de las URLs del cuerpo solo con `--fields snippet`, `body` o `all` en `search`/`new`, y con `body_text` (o `body_truncated`, `partial`, `readable`, `source`) en `show`. |
| .02 | P | URL en el asunto: contada con la fila por defecto; URL en el nombre de un destinatario: contada solo con `--fields to`. |
| .03 | P | `W_SENDER_AUTH_FAILED` y `W_REPLY_TO_MISMATCH` aparecen con y sin `--fields`, también con `show --fields attachments`. |
| .04 | N | `W_BODY_UNREADABLE`, `W_EMLX_MISSING` (Apple Mail) y `W_BODY_NOT_LOCAL` (Outlook) solo con cuerpo entregado; con `--text` sin `snippet` no aparecen. |
| .05 | N | `W_ATTACHMENTS_UNAVAILABLE` solo si `show` entrega `attachments`. |

#### UT-FLD-06 — `new --fields`

Requisitos: AC-O08 (delta `PRD-v2.2.md`) · Archivo: `tests/test_fields.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `new --fields snippet` añade `snippet`. |
| .02 | B | El `state.json` tras `new --fields snippet` es igual al de `new` sin `--fields` sobre el mismo store (cursor y anillo). |

#### UT-FLD-07 — Compatibilidad final de F1

Requisitos: AC-H14 (delta `PRD-v2.2.md`) · Archivo: `tests/test_fields.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Con `--fields all` en `search`/`new` y sin `--fields` en `show`, están todos los campos existentes y la única clave nueva respecto de 2.0.x es `content_notice`. |

#### UT-GRP-01 — `--group-by from`

Requisitos: AC-O01, AC-O04 (delta `PRD-v2.2.md`) · Archivo: `tests/test_group_count.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Un grupo por remitente (dirección en minúsculas) con su `count` y sus 5 mensajes más recientes, de más reciente a más antiguo, sin `from` en las filas. |
| .02 | P | Los grupos van ordenados por su mensaje más reciente. |
| .03 | B | `--limit 0` → `messages: []` en cada grupo y `count` correcto. |
| .04 | P | `--fields snippet` añade `snippet` a las filas de los grupos. |
| .05 | P | La deduplicación se aplica antes de agrupar (el duplicado Gmail/INBOX del store sintético cuenta una vez). |
| .06 | P | Con `[search].default_limit = 20` en la configuración, `--group-by from` sin `--limit` da 5 mensajes por grupo (RF-72: `default_limit` no aplica). |

#### UT-GRP-02 — Dos claves y fechas

Requisitos: AC-O01, AC-O05 (delta `PRD-v2.2.md`) · Archivo: `tests/test_group_count.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `--group-by domain,month` y `--group-by domain --group-by month` dan el mismo resultado: un grupo plano por combinación con mensajes, con `domain` y `month` en ese orden (ejemplo de PRD-v2.2 sección 8). |
| .02 | P | `day`, `week`, `month` usan la zona local (`output.LOCAL_ZONE` inyectada): un mensaje a las 02:00 UTC cae en el día anterior con UTC−4. |
| .03 | B | Semana ISO en el cambio de año: 2026-12-31 y 2027-01-01 → `2026-W53`; 2027-01-04 → `2027-W01`. |
| .04 | B | Mensajes sin fecha (nula, 0 o no representable) forman el grupo `null` de `day`/`week`/`month` y van al final; mensajes sin dirección del remitente, el grupo `null` de `from`/`domain`. |
| .05 | P | `mailbox` da `{"account": <etiqueta>, "path": <ruta>}` sin `mailbox` en las filas; `account` da la etiqueta (o el `uuid` sin etiqueta). |
| .06 | B | A igualdad de mensaje más reciente, los grupos se ordenan por sus claves ascendentes; un grupo sin fechas va después de los que tienen. |
| .07 | B | Remitente con una dirección sin `@`: `from` = la dirección en minúsculas y `domain` = `null`. |
| .08 | B | `--group-by domain,month` con dos grupos del mismo dominio, uno con `month: null`: el grupo con `null` va después de los grupos sin claves `null`, ordenado por claves ascendentes con `null` al final. |

#### UT-GRP-03 — Errores de `--group-by` y `--limit`

Requisitos: AC-O05 (delta `PRD-v2.2.md`) · Archivo: `tests/test_group_count.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Tres claves, una repetida, una desconocida: `E_USAGE`, exit 2, con los mensajes y el hint literales. |
| .02 | N | `--limit 51` y `--limit -1` con `--group-by`: `E_USAGE` con el mensaje y el hint literales. |
| .03 | B | Los errores ocurren antes de crear el home y sin abrir el store. |
| .04 | B | `--limit 50` con `--group-by` es válido (hasta 50 mensajes por grupo). |
| .05 | N | D-24: `--group-by ""` y `--group-by from,` ⇒ `unknown key '' in --group-by`; `--group-by FROM` ⇒ `unknown key 'FROM' in --group-by`; `--group-by "from, month"` equivale a `--group-by from,month`. |

#### UT-GRP-04 — Más de 50 grupos

Requisitos: AC-O06 (delta `PRD-v2.2.md`) · Archivo: `tests/test_group_count.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Con 53 remitentes: 50 grupos, `truncated: true`, hint `3 more group(s); refine the filters`, warning `W_RESULTS_TRUNCATED: 3 more group(s); refine the filters`; `count` es el total de mensajes de los 53 grupos. |
| .02 | B | Exactamente 50 remitentes: 50 grupos, `truncated: false`, sin `W_RESULTS_TRUNCATED`. |
| .03 | B | 51 remitentes: 50 grupos, `truncated: true`, `1 more group(s); refine the filters`. |

#### UT-GRP-05 — `--count`

Requisitos: AC-O07, AC-O13 (delta `PRD-v2.2.md`) · Archivo: `tests/test_group_count.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Respuesta con exactamente `ok`, `command`, `generated_at`, `content_notice`, `count`, `hint`, `warnings`, `scan`, en ese orden; `hint: null` con resultados. |
| .02 | P | Con 250 mensajes (plugin falso) el `count` es 250, sin el límite de 200 ni de `--limit`, y después de deduplicar. |
| .03 | P | Cero resultados → `count: 0`, hint de RF-78, exit 0. |
| .04 | N | `--count` con `--fields`, con `--group-by` y con `--limit` ⇒ `E_USAGE` con el mensaje y el hint literales. |
| .05 | N | `--count --text x` sin filtro de acotamiento ⇒ `E_UNBOUNDED_SCAN`; con más candidatos que `[search].max_scan` ⇒ `E_SCAN_TOO_LARGE`. |

#### UT-GRP-06 — `new` sin agrupación ni recuento

Requisitos: AC-O08 (delta `PRD-v2.2.md`) · Archivo: `tests/test_group_count.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | `new --group-by from` y `new --count` ⇒ `E_USAGE`, exit 2, y `state.json` no cambia (ni se crea si no existía). |

#### UT-GRP-07 — Lecturas

Requisitos: AC-O01 (delta `PRD-v2.2.md`) · Archivo: `tests/test_group_count.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `--group-by` sin `--text`: ninguna extracción de cuerpo; cabeceras leídas solo de los mensajes emitidos (con `--limit 1`, una por grupo; con `--limit 0`, ninguna). |
| .02 | P | `--count` sin `--text`: ni cuerpos ni cabeceras; `scan.messages_read: 0` (Apple Mail y doble de Outlook, sin `--to`/`--cc`; el doble no abre ningún item). |
| .03 | P | `--group-by from --text <patrón>`: los cuerpos se leen para filtrar, los grupos solo contienen mensajes que cumplen el patrón y las filas no llevan `snippet` sin `--fields snippet`. |

#### UT-GRP-08 — `hint` de `search` sin resultados

Requisitos: AC-O13 (delta `PRD-v2.2.md`) · Archivo: `tests/test_group_count.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | macOS, Windows y plugin: dos cuentas declaradas con solo INBOX → `no messages matched in 2 folder(s) of 2 account(s); run "mailquery mailboxes" to see other folders, or add --include-mailbox`. |
| .02 | P | `<n>` cuenta INBOX, `mailbox_list` y `--include-mailbox`; también con `--group-by` y con `--count`; una cuenta declarada sin ninguna carpeta cuenta como leída con 0 carpetas. |
| .03 | B | Una cuenta declarada cuyo store está excluido (`W_STORE_EXCLUDED`) no cuenta en `<m>` ni sus carpetas en `<n>`. |
| .04 | N | Sin cuentas leídas (ninguna declarada o todas excluidas) → `hint: null` y `W_NO_ACCOUNTS`. |
| .05 | N | Con resultados, `hint` como antes; `new` sin correo nuevo → `hint: null`. |
| .06 | B | El hint no contiene nombres de carpetas ni de cuentas, y la secuencia de llamadas al driver es la misma que la de la misma búsqueda sin calcular el hint (comparación del `CallLog` del doble y de las llamadas del plugin falso). |
| .07 | B | D-23: una cuenta con INBOX también en `mailbox_list` y una carpeta en `mailbox_list` y en `--include-mailbox` cuenta cada carpeta una vez (`<n>` = carpetas únicas por cuenta). |

#### UT-GRP-09 — Warnings con `--count` y `--group-by`

Requisitos: AC-O09 (delta `PRD-v2.2.md`) · Archivo: `tests/test_group_count.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Con `--count`, solo warnings de alcance (`W_NO_ACCOUNTS`, `W_STORE_EXCLUDED`, `W_ACCOUNT_LABELS_UNAVAILABLE`), aunque los mensajes tengan URLs o fallos de autenticación (Apple Mail y plugin falso). |
| .02 | P | Con `--group-by`, `W_SENDER_AUTH_FAILED` de un mensaje emitido aparece; el conteo de URLs del cuerpo solo con `--fields snippet`. |

#### UT-GRP-10 — `content_notice` con cualquier opción

Requisitos: AC-H18 (delta `PRD-v2.2.md`) · Archivo: `tests/test_group_count.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `search --count` y `search --group-by from` de éxito llevan `content_notice` tras `generated_at`. |

#### UT-MBX-01 — Forma por defecto

Requisitos: AC-O14 (delta `PRD-v2.2.md`) · Archivo: `tests/test_mailboxes.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Sin `--fields`: claves de primer nivel exactamente `ok`, `command`, `generated_at`, `accounts`, `excluded_stores`, `warnings`, con el store sintético, el doble de Outlook y un plugin falso. |
| .02 | P | Cada cuenta tiene `uuid`, `label`, `email`, `declared` y `mailboxes`, en ese orden; cada carpeta solo `path` e `included`, con los mismos valores e igual orden que el catálogo plano anterior. |
| .03 | N | Ninguna carpeta lleva `account`; no hay `mailboxes` de primer nivel. |
| .04 | B | Una cuenta declarada sin carpetas tiene `mailboxes: []`; con dos drivers declarados, el orden de cuentas es el de `PRD.md` §11.3; una carpeta sin cuenta se agrupa en una cuenta con `uuid: ""`, `label: ""`, `email: null` y `declared: false`. |

#### UT-MBX-02 — Referencias copiadas

Requisitos: AC-O14 (delta `PRD-v2.2.md`) · Archivo: `tests/test_mailboxes.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Un `path` copiado de la salida resuelve en `mailbox_list` y en `--include-mailbox`. |
| .02 | P | El `name` y la `url` de `--fields name,url` siguen resolviendo en `mailbox_list` y en `--include-mailbox`. |

#### UT-MBX-03 — `--fields`

Requisitos: AC-O15 (delta `PRD-v2.2.md`) · Archivo: `tests/test_mailboxes.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `--fields name,url,total,unread` y `--fields total --fields name,url,unread` añaden esos campos en el orden `name`, `path`, `url`, `total`, `unread`, `included`, con los valores del catálogo anterior. |
| .02 | P | `--fields path,included` da exactamente la salida por defecto. |
| .03 | N | `--fields all`, `--fields carpeta` y `--fields ""` ⇒ `E_USAGE`, exit 2, con `unknown field '<nombre>' in --fields` y `valid fields: name, path, url, total, unread, included`, antes de crear el home y sin ejecutar el comando. |

#### UT-MBX-04 — Sin recuento sin `total` ni `unread`

Requisitos: AC-O15 (delta `PRD-v2.2.md`) · Archivo: `tests/test_mailboxes.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Apple Mail: sin `total`/`unread`, `_mailbox_counters` no se ejecuta (espía); con `--fields unread`, una vez. |
| .02 | P | Outlook (doble): sin contadores no se leen tablas de carpeta (`Folder.GetTable` no aparece); con `--fields total`, sí. |
| .03 | P | Plugin falso que entrega contadores: sin `--fields`, la salida no los incluye. |
| .04 | B | `search`, `new` y `show` en Apple Mail ya no ejecutan el recuento de carpetas (espía), con la misma salida que antes. |
| .05 | B | Apple Mail, mismo proceso: dos peticiones de contadores reutilizan el recuento (la consulta se ejecuta una vez). |
| .06 | N | Apple Mail: un error de SQLite durante el recuento diferido de `mailboxes --fields total` da el mismo error que el recuento al cargar el catálogo (`E_INTERNAL`, exit 1); sin contadores el comando no falla. |
| .07 | B | Plugin falso cuyas filas no traen contadores: `mailboxes --fields total` no falla y emite `null`; con contadores, los valores del plugin. |

#### UT-MBX-05 — Ayudas

Requisitos: AC-O15 (delta `PRD-v2.2.md`) · Archivo: `tests/test_mailboxes.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `mailboxes --help` describe `--fields` con `name, path, url, total, unread, included` y que los contadores solo se calculan con `--fields total` o `unread`. |
| .02 | P | La ayuda general muestra `list accounts and their folders (counters with --fields)` para `mailboxes`. |

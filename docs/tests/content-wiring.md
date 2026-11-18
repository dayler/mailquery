# Contenido no confiable en los comandos

#### UT-CW-01 — A2 en los campos de contenido

Requisitos: RF-52, RF-66 · Archivo: `tests/test_content_wiring.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Un mensaje con ANSI, C1, `U+200B`, `U+202E`, selectores y rellenos en `subject`, `from.name`, nombres de `to`/`cc` y cuerpo: `search` y `new` los devuelven saneados, incluido `snippet`. |
| .02 | P | `show` del mismo mensaje: `subject`, nombres, cada valor de `headers`, `body_text` y `attachments[].name` saneados. |
| .03 | P | `attachment`: `original_name` saneado; `sanitized_name` y `path` iguales a los del mismo nombre original (calculados con `sanitize_name` y la ruta de caché). |
| .04 | N | `uid`, `message_id`, `from.address`, `to[].address`, `mailbox.*`, `account.*`, `source.emlx_path` y `cached_path` salen sin cambios aunque contengan caracteres invisibles. |
| .05 | P | Una etiqueta de cuenta y un nombre de carpeta con `U+200B` copiados de `accounts[]` y de `accounts[].mailboxes[]` de `mailboxes` (con `--fields name,url`) resuelven en `config.toml` y en `--include-mailbox`. |

#### UT-CW-02 — A2 en warnings y errores

Requisitos: RF-52 · Archivo: `tests/test_content_wiring.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Un warning con un identificador con `U+202E` (`W_STORE_EXCLUDED` de un store excluido del plugin falso) sale saneado en `warnings[]`, mientras `excluded_stores[].label` sigue igual. |
| .02 | P | Un error cuyo `message` cita un valor del usuario con `U+202E` sale saneado en el JSON y en `stderr`; `code` y exit sin cambios. |
| .03 | B | `warnings[]` de `mailboxes`, `new` y `doctor --json` también pasan por A2 (todos los comandos). |
| .04 | N | Un error con `hint` nulo conserva `"hint": null` en el JSON tras A2. |

#### UT-CW-03 — Búsqueda con A2 a ambos lados

Requisitos: RF-52 · Archivo: `tests/test_content_wiring.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Asunto original `Factura​ de octubre`: `--subject "Factura de"` lo encuentra. |
| .02 | P | Patrón con `U+200B` (`--subject "Fac​tura"`) encuentra un asunto sin él. |
| .03 | P | `--text` con un cuerpo con `U+202E` en medio de la palabra; `--from`, `--to` y `--cc` con nombres con `U+202E`/`U+200B`. |
| .04 | N | Sin caracteres de A2, los resultados de `--subject` son los mismos que filtrar el resultado completo por subcadena. |

#### UT-CW-04 — Adjuntos con nombres con `Cf` o controles

Requisitos: RF-52 · Archivo: `tests/test_content_wiring.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Un adjunto con un selector de variación (`U+FE00`): el bloqueo, el `sanitized_name` y la ruta de caché son los mismos que `classify_name` y `sanitize_name` dan para el nombre original. |
| .02 | N | Un nombre con `U+200B` o un control C0 que hoy se bloquea sigue dando `E_ATTACHMENT_BLOCKED`, sin archivos. |

#### UT-CW-05 — `content_notice`

Requisitos: RF-66 · Archivo: `tests/test_content_wiring.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `search`, `new` y `show` de éxito (store sintético y doble de Outlook) tienen `content_notice` con el texto exacto, justo después de `generated_at`. |
| .02 | N | Las respuestas de error de esos comandos, `doctor --json` y `mailboxes` no lo tienen. |

#### UT-CW-06 — Compatibilidad

Requisitos: RF-52, RF-66 · Archivo: `tests/test_content_wiring.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Con la fila completa actual de `search`/`new` y `show` sin opciones, las claves son las de antes más `content_notice`, y es la única clave nueva. |
| .02 | B | `state.json` y el manifiesto de una corrida de `new` y de `attachment` conservan su forma y contenido (sin `content_notice`). |

#### UT-CW-07 — Cuerpo visible en los comandos

Requisitos: RF-53, RF-56 · Archivo: `tests/test_content_wiring.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Un mensaje con texto oculto en línea y por una hoja `<style>`: `search`, `new` y `show` dan una vez `W_HIDDEN_CONTENT: <n> hidden character(s) omitted from the body of <uid>` con el `<n>` de `html_body_to_text`; el mensaje se devuelve y el exit es 0. |
| .02 | P | `W_HIDDEN_CONTENT` va antes de `W_EXTERNAL_LINKS`; el detalle no contiene texto del mensaje. |
| .03 | N | Un mensaje sin texto omitido, de texto plano o de un plugin no da `W_HIDDEN_CONTENT`. |
| .04 | P | Un HTML todo oculto da `W_HTML_NO_TEXT` además de `W_HIDDEN_CONTENT`; `--text` con una palabra del texto oculto no encuentra el mensaje (Apple Mail y Outlook). |

#### UT-CW-08 — Modos de URL en los campos

Requisitos: RF-54 · Archivo: `tests/test_content_wiring.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Con `keep`, `neutralize` y `strip`: `subject`, `from.name`, `to[].name`, `cc[].name`, cada valor de `headers` (`show`), `body_text` y `snippet` se transforman igual que `render_urls` (incluido `Subject` en `headers` con `--strip-links`). |
| .02 | N | Nombres de adjuntos, `warnings[]`, textos de error, direcciones y `uid` no cambian en ningún modo. |
| .03 | P | Los filtros devuelven los mismos mensajes en los tres modos; `--subject evil.example` encuentra el asunto con la URL neutralizada o quitada. |
| .04 | B | `show` con una URL que hace superar 20.000 caracteres solo antes de acortarla: el truncado y `W_BODY_TRUNCATED` se calculan sobre el texto transformado. |

#### UT-CW-09 — `--strip-links` y precedencia

Requisitos: RF-54, RF-63 · Archivo: `tests/test_content_wiring.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Sin opción ni clave ⇒ `neutralize`. |
| .02 | P | `[content].url_display = "keep"` ⇒ `keep`; `"strip"` ⇒ `strip`. |
| .03 | P | `--strip-links` con `url_display = "keep"` ⇒ `strip` en `search`, `new` y `show`. |
| .04 | N | `doctor --strip-links`, `mailboxes --strip-links` y `attachment <uid> --all --strip-links` ⇒ `E_USAGE`, exit 2. |

#### UT-CW-10 — Señales de enlaces en los comandos

Requisitos: RF-55, RF-57, RF-58, RF-59 · Archivo: `tests/test_content_wiring.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Una URL en el asunto y otra en el cuerpo ⇒ `W_EXTERNAL_LINKS: 2 …`; la del asunto cuenta una vez aunque `headers` la repita (`show`). |
| .02 | P | La URL larga y el enlace de script: `W_EXTERNAL_LINKS: 2`, `W_SCRIPT_LINK: 1`, `W_LONG_URL: 1`, en ese orden, en los tres modos y en los tres comandos. |
| .03 | P | Homoglifos: `W_EXTERNAL_LINKS: 1` y `W_NON_ASCII_DOMAIN: 2` (URL + dirección); con `neutralize`, `xn--pypal-4ve.com` en el cuerpo y la dirección igual. |
| .04 | P | `search`, `new` y `show` dan los mismos conteos; en `new`, todos antes de `W_FIRST_RUN`. |
| .05 | N | Sin URLs en esos campos no aparece ninguno de los cuatro; un texto que empieza como un esquema sin cumplir la definición (`JavaScript: …`) no cuenta. |
| .06 | P | Cuerpo con `JAVASCRIPT:x`, `VbScript:x`, `DATA:text/html,x` y `ｊａｖａｓｃｒｉｐｔ：x` ⇒ `W_EXTERNAL_LINKS: 4` y `W_SCRIPT_LINK: 4` en los tres comandos; con `neutralize`, `JAVASCRIPT[:]x`, `VbScript[:]x`, `DATA[:]text/html,x` y `ｊａｖａｓｃｒｉｐｔ[:]x`. |
| .07 | P | Un mensaje con `W_BODY_UNREADABLE` y una URL en el asunto ⇒ `W_EXTERNAL_LINKS: 1` en `show`. |
| .08 | N | `attachment`, `mailboxes` y `doctor --json` no contienen `W_EXTERNAL_LINKS`, `W_SCRIPT_LINK`, `W_LONG_URL`, `W_NON_ASCII_DOMAIN`, `W_SENDER_AUTH_FAILED` ni `W_REPLY_TO_MISMATCH`. |
| .09 | P | Un mensaje de un plugin sin cuerpo legible con una URL en el asunto y otra en el nombre del remitente ⇒ `W_EXTERNAL_LINKS: 2`; no se emite `W_HIDDEN_CONTENT`. |

#### UT-CW-11 — Señales del remitente en los comandos

Requisitos: RF-60, RF-61 · Archivo: `tests/test_content_wiring.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | El ejemplo A6 en Apple Mail y en Outlook: `W_SENDER_AUTH_FAILED: spf=softfail dkim=none dmarc=fail in <uid>` y `W_REPLY_TO_MISMATCH: … in <uid>` en `search`, `new` y `show`, en ese orden y después de las señales de enlaces. |
| .02 | N | Todo `pass`, sin cabecera, con `Reply-To` del mismo dominio o con el fallo solo en la segunda `Authentication-Results`: sin warnings. |
| .03 | N | Un mensaje de un plugin y correo interno de Outlook sin cabeceras de transporte: sin warnings. |
| .04 | N | `headers` de `show` sigue con sus seis cabeceras (sin `Reply-To` ni `Authentication-Results`); el exit no cambia. |
| .05 | P | Un mensaje S/MIME de Apple Mail con `dmarc=fail` en la primera `Authentication-Results` ⇒ `W_SENDER_AUTH_FAILED` (la exclusión de S/MIME solo aplica al item de Outlook). |

#### UT-CW-12 — Logs sin contenido

Requisitos: RF-64 · Archivo: `tests/test_content_wiring.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Tras `search`, `new` y `show` de mensajes con URLs, dominio no ASCII, direcciones y A6, `~/.mailquery/logs/mailquery.log` (del `HOME` temporal) contiene los códigos `W_*` y no contiene ninguna URL, dominio, dirección ni texto del mensaje. |
| .02 | P | `W_SENDER_AUTH_FAILED` y `W_REPLY_TO_MISMATCH` se registran solo por código, sin sus detalles ni las direcciones. |

#### UT-CW-13 — Determinismo de punta a punta

Requisitos: RNF-18 · Archivo: `tests/test_content_wiring.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | B | La misma consulta dos veces, con cada modo, da el mismo JSON salvo `generated_at` y `scan.duration_ms`. |

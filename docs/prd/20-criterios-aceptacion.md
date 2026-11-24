---
aliases: ["Sección 20", "Criterios de aceptación"]
tags: [prd]
---

## 20. Criterios de aceptación

El producto se acepta cuando cumple todo lo siguiente:

1. **Solo lectura en macOS:** tras ejecutar todos los comandos sobre un store, ningún archivo del store cambia de contenido ni de `mtime` y no aparece ningún archivo nuevo en él.
2. **Solo lectura en Windows:** ningún comando modifica items, carpetas ni stores de Outlook, lo lanza ni provoca descargas; toda operación fuera de la lista blanca se rechaza antes de llegar a Outlook (§9.3); y tras ejecutar todos los comandos contra el Outlook real, los contadores de no leídos del alcance no cambian.
3. **Plugins, adjuntos, contenido no confiable, salida a medida, servidor MCP y log JSON:** los criterios AC-01…AC-78.

**AC-01.** `apple_mail` y `outlook` se registran como drivers con `driver` válido y único (`[a-z0-9_]{1,64}`) y `plugin_api = 1`; un plugin externo que cumpla el contrato se registra por la misma vía; un driver duplicado, reservado, inválido o con `plugin_api ≠ 1` ⇒ `E_PLUGIN_INCOMPATIBLE` (exit 3).

**AC-02.** Las capacidades declaradas (`network`, `readonly`, `body_local`, `attachments`, `native_order`) se validan; una capacidad inválida o ausente ⇒ `E_PLUGIN_INCOMPATIBLE`; `doctor` las muestra en el detalle del chequeo `driver`.

**AC-03.** `[scope."<driver>:<cuenta>"]` divide en el primer `:`; sin prefijo usa el driver nativo; un driver inválido o de más de 64 caracteres ⇒ `E_DRIVER_UNKNOWN` (exit 2); un driver no instalado ⇒ `E_DRIVER_UNKNOWN` (exit 2); un bloque de un driver no instalado hace fallar los comandos de datos (no se ignora); un driver instalado pero no declarado ⇒ `E_ACCOUNT_NOT_IN_SCOPE` (exit 2) sin cargarlo.

**AC-04.** Varios drivers declarados se consultan en la misma ejecución y se fusionan con el orden `(date_received, driver, native_order_key)`; no hay dedupe cross-driver; si un driver no carga o falla en runtime, el comando falla sin resultados parciales.

**AC-05.** Todo `uid` emitido (JSON y `state.json`) es `string` `"<driver>:<native_id>"`; el uid legado sin prefijo se acepta en entrada para el driver nativo; un uid malformado ⇒ `E_USAGE` y un driver desconocido ⇒ `E_DRIVER_UNKNOWN`, validados antes de abrir el cliente y sin leer ni escribir estado o caché.

**AC-06.** Un `state.json` `schema: 1` con uids enteros o hexadecimales en mayúsculas se migra de forma determinista por el tipo del valor, sin depender de la plataforma, y se persiste atómicamente en la siguiente corrida de `new` sin `--peek` que emite al menos un mensaje (`doctor` informa `schema: 1 (migration pending)` hasta entonces); un estado inválido ⇒ `E_STATE_CORRUPT` con hint; los anillos con drivers no instalados se podan y `doctor` lo reporta.

**AC-07.** `show` expone `attachments: [{"index", "name", "cached_path"}]` con `index` estable 1..N y `cached_path` calculado con el nombre sanitizado (o `null`); `show` no escribe nada salvo en la caché de ids nativos: la crea si no existe (RF-80) y borra la fila de un mensaje *ausente confirmado* (RF-81).

**AC-08.** `attachment` exige `--index` o `--all` mutuamente excluyentes; valida los casos de §12.11 en el orden indicado con los textos de referencia de §12.11 y el ejemplo G (incluido `--index 0`, mensaje inexistente, sin adjuntos, índice fuera de rango).

**AC-09.** Un mensaje con un adjunto de nombre hostil y otro seguro: `--index` del seguro, `--index` del hostil y `--all` fallan los tres con `E_ATTACHMENT_BLOCKED` (exit 4); no se escribe nada y no se sirve caché del mensaje.

**AC-10.** Un nombre con traversal, separadores, `..`, `C:`, ADS, RLO/controles, reservado de Windows o extensión del catálogo (simple o doble) ⇒ mensaje bloqueado; un `MZ`, ELF, Mach-O o `#!` en los primeros bytes de un adjunto a extraer ⇒ mensaje bloqueado; en ambos casos no se escribe ningún archivo, no hay resultados parciales y el `message`/`hint` no contienen controles.

**AC-11.** La sanitización cumple la tabla normativa de §10.3.3: NFKC, trim/dotfiles antes de los reemplazos, extensión ≤ 20 bytes sin partir un carácter, nombre sin prefijo ≤ 150 bytes UTF-8 y nombre final (prefijo incluido) ≤ 153; si el prefijo mide más de 3 bytes, la raíz se reduce; dos ejecuciones producen exactamente el mismo `sanitized_name`, la misma ruta y el mismo `cached_path`.

**AC-12.** La primera extracción devuelve `cached: false`; una segunda sin `--force` devuelve `cached: true` con `size_bytes`/`sha256` del archivo existente, verificado contra el manifiesto del mensaje (§10.3.4); un archivo que no coincide con su entrada no se sirve y se re-extrae; con `--force` re-extrae y devuelve `cached: false`; todo se escribe primero en staging y se publica de forma atómica, sin dejar parciales al abortar; un fallo de E/S ⇒ `E_IO` (exit 3) sin parciales.

**AC-13.** `max_file_size_mb`, `max_total_size_mb` y `max_count` se aplican con `>` estricto y MiB; los aciertos de caché cuentan para el total; un exceso con tamaño conocido falla antes de escribir; un exceso detectado en streaming limpia staging y conserva la caché previa; error `E_ATTACHMENT_TOO_LARGE` (exit 4).

**AC-14.** `enabled = false` ⇒ `E_ATTACHMENTS_DISABLED` (exit 2) antes de abrir el store; valores fuera de rango o `max_total_size_mb < max_file_size_mb` ⇒ `E_CONFIG_INVALID`; `show` no se ve afectado por `enabled`.

**AC-15.** Un adjunto no disponible ⇒ `E_ATTACHMENT_UNAVAILABLE` (exit 3) con el motivo correcto (`not_local`, `not_downloaded`, `unsupported`, `network`); un adjunto corrupto o un mensaje S/MIME ⇒ `E_ATTACHMENT_UNREADABLE` (exit 3) y un mensaje S/MIME no se reporta como “sin adjuntos” (nunca `E_USAGE`); un driver con `attachments: "none"` ⇒ `E_ATTACHMENT_UNAVAILABLE` antes de abrir el store.

**AC-16.** El protocolo de errores de plugin: `reason`/`hint`/`detail`/`log_message` se mapean a los códigos y exits de §12.6; un `reason` desconocido o una excepción no mapeada en runtime ⇒ `E_PLUGIN_FAILED` (exit 3), nunca `E_INTERNAL`; una capacidad inválida en la carga ⇒ `E_PLUGIN_INCOMPATIBLE`; el `code` del JSON pertenece siempre al conjunto cerrado del núcleo.

**AC-17.** Un timeout de metadatos (30 s) o de extracción de un adjunto (`[attachments].timeout_seconds`, RF-49) ⇒ `E_CLIENT_TIMEOUT` (exit 3), staging limpio y sin archivos nuevos.

**AC-18.** `doctor` incluye `driver` después de `home` con el detalle de capacidades y versiones; un fallo de driver marca `ok=false`, sus dependientes salen `not evaluated: driver failed` y `doctor` sigue saliendo con exit 0; `--version` conserva el formato base y añade `drivers: ...` sin leer config ni importar plugins.

**AC-19.** Los logs registran `backend=`/`drivers=` y los conteos de `attachment` sin uids, nombres, rutas, cuentas ni términos; el `log_message` del plugin se sanea y nunca se registran `hint`/`detail` con PII.

**AC-20.** La caché es best-effort: un archivo borrado entre `show` y `attachment` o durante la ejecución se re-extrae una vez; una caché vacía o inexistente no es un error; no hay barrido ni purga en la app.

**AC-21.** La ayuda raíz y la de `attachment` son coherentes con §12/§12.7; la línea de exits y los textos no contradicen este documento.

**AC-22.** Los campos de contenido de RF-52 (en `search`, `new`, `show`, `attachment` y en los errores) no contienen ANSI, C0 salvo `\n`/`\t`, DEL, C1, `Cf`, selectores de variación salvo `U+FE0E`/`U+FE0F` ni los rellenos Hangul de RF-52, y un emoji con `U+FE0F` se conserva; los identificadores y rutas de RF-52 salen sin cambios, y un nombre de carpeta o etiqueta de cuenta copiado de `mailboxes` sigue resolviendo en `config.toml`.

**AC-23.** El saneado conserva `\n` y `\t`, normaliza CRLF/CR a LF, es idempotente y no recorta el texto más allá de los límites existentes; la misma entrada y la misma configuración producen la misma salida en todo el procesamiento de F1 (RNF-18).

**AC-24.** Un término copiado de la salida encuentra el mensaje cuyo asunto, cuerpo o nombre original lo contiene con caracteres que elimina A2, y un patrón con esos caracteres también; el bloqueo, el `sanitized_name` y la caché de adjuntos trabajan sobre el nombre original también con nombres que contienen `Cf` o controles (RF-52).

**AC-25.** En Apple Mail y en Outlook, un mensaje con HTML y texto plano distintos da `body_text`, `snippet` y coincidencias de `--text` del HTML y nunca del texto plano; un mensaje sin HTML usa el texto plano; un HTML sin texto da cuerpo vacío y `W_HTML_NO_TEXT` aunque haya texto plano. Un elemento con `hidden`, `display:none`, `visibility:hidden`, `mso-hide:all`, `font-size` u `opacity` con un valor cero de RF-53 inline no aporta texto a `body_text`/`snippet` ni es encontrado por `--text`; el texto visible alrededor no cambia; el texto con `aria-hidden` o con un valor distinto de cero se conserva; un elemento oculto sin cierre omite hasta el final; un HTML todo oculto da `W_HTML_NO_TEXT`.

**AC-26.** Un elemento oculto por una regla de una hoja `<style>` del mensaje (clase, id, etiqueta o selector compuesto) se omite igual que uno oculto en línea; una regla dentro de `@media` no oculta nada; un `<link rel="stylesheet">` a una URL o a un archivo local no provoca ninguna conexión ni lectura de archivo; un CSS que la librería no puede procesar deja convertir el HTML original sin error. Un mensaje con texto omitido da una vez `W_HIDDEN_CONTENT` con su `uid` y el número correcto de caracteres en `search`, `new` y `show`, antes de `W_EXTERNAL_LINKS`; el mensaje se devuelve, el exit code no cambia y el detalle no contiene texto del mensaje; un mensaje sin texto omitido, de texto plano o de un plugin no lo da.

**AC-27.** Se detectan como URL los inicios (a)–(e) de RF-54, el esquema en ancho completo y el dominio con `[.]`, y no se detectan los textos de la última fila de los ejemplos de A4 (§12.5); `keep` no altera el texto; `neutralize` produce las sustituciones de RF-54, también en mayúsculas, y deja igual una URL ya neutralizada; con `neutralize`, una URL de 2.049 caracteres o más sale con sus primeros 256 caracteres y `…[+<n> characters]` con el `<n>` correcto, y una de 2.048 sale entera; `keep` nunca acorta; `strip` sustituye cada URL por `[link omitted]`; los tres modos se aplican igual a `subject`, `from.name`, `to[].name`, `cc[].name`, los valores de `headers`, `body_text` y `snippet`; los nombres de adjuntos, los warnings y los errores no se transforman; los filtros de `search` encuentran los mismos mensajes en los tres modos; ningún modo resuelve ni abre URLs.

**AC-28.** `--strip-links` en `search`, `new` y `show` fuerza `strip` y prevalece sobre `[content].url_display`; sin la opción ni la clave, el modo es `neutralize`; en `doctor`, `mailboxes` y `attachment` ⇒ `E_USAGE`.

**AC-29.** `W_EXTERNAL_LINKS` aparece una vez por mensaje con URLs en el asunto, los nombres o el cuerpo, con su `uid` y la suma correcta en los tres modos y en `search`, `new` y `show` (una URL en el asunto cuenta una vez aunque `headers` la repita); no aparece para mensajes sin URLs en esos campos ni en `attachment`, `mailboxes` o `doctor`; en `new` va antes de `W_FIRST_RUN`; su detalle no contiene URL, dominio ni texto del mensaje.

**AC-30.** `W_NON_ASCII_DOMAIN` aparece una vez por mensaje con la suma correcta de URLs (en el asunto, los nombres o el cuerpo) y direcciones (`from`, `to`, `cc`) cuyo dominio tiene caracteres no ASCII, en los tres modos y en `search`, `new` y `show`, en el orden de §12.12, punto 6; cuenta un dominio con alfabetos mezclados y uno entero en otro alfabeto, no cuenta la ruta ni el usuario de una URL ni un dominio ASCII; con `neutralize`, el dominio de la URL sale en punycode (RF-54) y la dirección no cambia; su detalle no contiene el dominio.

**AC-31.** `W_LONG_URL` aparece una vez por mensaje con el número correcto de URLs de más de 2.048 caracteres (una de 2.048 no cuenta) y `W_SCRIPT_LINK` una vez por mensaje con el número correcto de URLs `javascript:`, `vbscript:` o `data:` (también en mayúsculas; `javascript:` y `vbscript:` también con el esquema en ancho completo), que también cuentan en `W_EXTERNAL_LINKS`; los dos aparecen en los tres modos y en `search`, `new` y `show`, en el orden de §12.12, punto 6; no aparecen sin esas URLs, ni por un texto que empieza como un esquema de RF-54 sin cumplir su definición, ni en `attachment`, `mailboxes` o `doctor`; su detalle no contiene la URL.

**AC-32.** Con una primera `Authentication-Results` con `spf`, `dkim` o `dmarc` en `fail`, `softfail` o `permerror`, `search`, `new` y `show` dan una vez `W_SENDER_AUTH_FAILED` con los resultados presentes en el orden `spf`, `dkim`, `dmarc`; no lo dan con todo en `pass`, con `none`/`neutral` sin fallos, sin la cabecera, ni cuando el fallo solo está en una `Authentication-Results` posterior o en `ARC-Authentication-Results`; varias firmas DKIM con una en `pass` cuentan como `pass`; un resultado desconocido sale como `unknown` y el detalle no contiene otro texto de la cabecera. `W_REPLY_TO_MISMATCH` aparece una vez cuando alguna dirección de `Reply-To` es de otro dominio que `from.address` (sin distinguir mayúsculas) y no aparece sin `Reply-To` o con el mismo dominio; su detalle no contiene direcciones ni dominios; `headers` de `show` no cambia. Ninguno de los dos hace consultas de red, cambia el exit code ni aparece en `attachment`, `mailboxes` o `doctor`; con correo interno de Outlook sin cabeceras de transporte o con un plugin no aparecen.

**AC-33.** `attachment` da `W_ATTACHMENT_ACTIVE_CONTENT` por adjunto devuelto, extraído o desde la caché, con su índice y tipo: `pdf-javascript` para un PDF con `/JavaScript`, `/JS` o `/Launch`, también escritos con `#xx`; `office-macros` para un `.doc` o `.xls` con `_VBA_PROJECT` y para un ZIP con `vbaProject.bin`; `archive-executable` para un ZIP (también cifrado) con una entrada cuya extensión está en el catálogo, salvo `.bin`. Un PDF sin esos nombres, un documento sin macros, un `.docx`, `.xlsx` o `.pptx` sin macros (con entradas en carpetas o con archivos `.bin` propios del formato), un ZIP con solo PDF o un archivo que no es un ZIP legible no lo dan. El archivo se entrega igual, el exit code no cambia, el detalle no contiene nombres de archivo y no se descomprime ningún contenido; un adjunto que bloquea el catálogo sigue dando `E_ATTACHMENT_BLOCKED`.

**AC-34.** `[content].url_display` inválido o una clave desconocida en `[content]` ⇒ `E_CONFIG_INVALID` (exit 2).

**AC-35.** Con `--fields all` en `search` y `new` y sin `--fields` en `show`, además de los campos de §12.5 está `content_notice`; el bloqueo, la caché, el manifiesto, `state.json` y el trato a los plugins no cambian; `attachment` solo añade `W_ATTACHMENT_ACTIVE_CONTENT`.

**AC-36.** `css-inline` es una dependencia, declarada en `[project].dependencies` de `pyproject.toml` como `~=0.23.1`; una instalación limpia con `pipx install` la instala sin pasos adicionales; es instalable desde wheel, sin compilar, en macOS (`arm64`, `x86_64`) y en Windows x64 con Python de 64 o de 32 bits; `pipx runpip mailquery install --upgrade "css-inline~=0.23.1"` instala el último parche `0.23.x` sin pasar a `0.24`; no se añade acceso a red; los presupuestos p95 de §19 no cambian.

**AC-37.** Los logs no registran URLs, dominios, direcciones ni contenido; solo códigos `W_*`.

**AC-38.** `README.md` y `README.es.md` tienen la subsección de RF-65 con los pasos y comandos de §13.3 y el enlace a los avisos de `css-inline`; con `css-inline` ausente o que falla al cargarse, `search`, `new` y `show` funcionan y convierten el HTML sin pasar las hojas `<style>` a línea.

**AC-39.** Toda respuesta de éxito de `search`, `new`, `show` y `attachment`, con cualquier opción y en macOS y en Windows, lleva `content_notice` justo después de `generated_at` con el texto exacto de RF-66, y ninguna respuesta de error, de `doctor` ni de `mailboxes` lo lleva; la skill tiene la sección "Security rules" y `README.md` y `README.es.md` tienen la sección de RF-66 con la frase indicada, el enlace al anexo de seguridad y el enlace desde la sección de instalación de la skill.

**AC-40.** Con un plugin falso `attachments: "remote"` y `network: true`, `attachment --index N` y `--all` extraen los adjuntos con el JSON de §12.11 y con el bloqueo, los límites, la caché y el manifiesto iguales que con un driver `"local"`; una segunda ejecución sirve desde la caché sin pedir bytes al plugin y `--force` los vuelve a pedir; el núcleo no abre conexiones.

**AC-41.** Un plugin `"remote"` que informa `reason: network` (o `not_local`) ⇒ `E_ATTACHMENT_UNAVAILABLE` (exit 3) con la plantilla de ese motivo, nunca `unsupported`, staging limpio y sin archivos nuevos.

**AC-42.** Un driver `attachments: "none"` sigue respondiendo `E_ATTACHMENT_UNAVAILABLE` (`unsupported`, exit 3) antes de abrir el store, con el hint de RF-48.

**AC-43.** Sin `[attachments].timeout_seconds` el tope es 60 s; con un entero de 10 a 600, ese valor; fuera de rango o de otro tipo ⇒ `E_CONFIG_INVALID` (exit 2) antes del store, en cualquier comando; con un valor válido, `show` y los demás comandos se comportan igual.

**AC-44.** Un plugin externo que deja de entregar bytes antes del primer bloque o entre dos bloques hace que `attachment` termine con `E_CLIENT_TIMEOUT` (exit 3), con el mensaje y el hint de RF-49, al vencer el tope configurado (con 1 s de tolerancia), staging limpio y sin archivos nuevos; con `--all` se informa el primer adjunto en orden de índice.

**AC-45.** Los 30 s de metadatos y los 30 s por llamada COM de Outlook no cambian con ningún valor de `[attachments].timeout_seconds`; en Apple Mail y Outlook el tope se comprueba entre bloques y al terminar cada llamada (RNF-21), y A7 y un acierto de caché no consumen el tope.

**AC-46.** En macOS y en Windows, sin `--fields`, cada fila de `search` y `new` tiene exactamente `uid`, `subject`, `from`, `date_received`, `is_read` y `has_attachments`, en ese orden y con los valores de §12.5; los campos fuera de `messages[]` son los de RF-67, y el `hint` sigue RF-76; sin `--text` no se lee ningún cuerpo, solo las cabeceras de A6 de los mensajes devueltos; sin `--text` (ni `--to`/`--cc` en Windows, RF-15), `--group-by` no lee cuerpos y `--count` no lee cuerpos ni cabeceras (`scan.messages_read: 0`).

**AC-47.** `--fields snippet` añade `snippet` a la fila por defecto; `--fields all` da la fila completa de §12.5; `--fields to,uid` y `--fields uid --fields to` dan lo mismo, en el orden de §12.5; un campo desconocido o vacío ⇒ `E_USAGE` (exit 2) antes de abrir el store, con el mensaje y el hint de RF-68.

**AC-48.** `show <uid> --fields attachments` devuelve solo `uid` y `attachments`, sin entregar el cuerpo ni emitir warnings del cuerpo; `show <uid> --fields body_text` no consulta los adjuntos; sin `--fields`, `show` devuelve todos los campos de §12.4, con los valores y los warnings de F1.

**AC-49.** `search --group-by from` devuelve un grupo por remitente con su `count` y sus 5 mensajes más recientes, de más reciente a más antiguo y sin `from` en las filas; los grupos van ordenados por su mensaje más reciente; `--limit 0` da `messages: []`; `--fields snippet` añade `snippet` a las filas; la deduplicación se aplica antes de agrupar.

**AC-50.** `--group-by domain,month` y `--group-by domain --group-by month` dan un grupo plano por cada combinación con mensajes, con las dos claves en ese orden; `day`, `week` y `month` usan la zona horaria local y la semana ISO 8601 también en el cambio de año, y los mensajes sin fecha forman el grupo `null`, al final; tres claves, una repetida, una desconocida o `--limit` fuera de 0–50 ⇒ `E_USAGE` (exit 2) antes de abrir el store, con los mensajes y hints de RF-70.

**AC-51.** Con más de 50 grupos, la respuesta trae 50, `truncated: true`, el hint de RF-70 y `W_RESULTS_TRUNCATED`; `count` es el total de mensajes de todos los grupos.

**AC-52.** `search --count` devuelve solo `ok`, `command`, `generated_at`, `content_notice`, `count`, `hint`, `warnings` y `scan`, con el total después de deduplicar y sin el límite de 200 y `hint: null`; cero resultados ⇒ `count: 0`, el hint de RF-76 y exit 0; con `--fields`, `--group-by` o `--limit` ⇒ `E_USAGE`; con `--text` aplica RF-15.

**AC-53.** `new --fields snippet` añade `snippet` y el cursor avanza igual que sin `--fields`; `new --group-by from` y `new --count` ⇒ `E_USAGE` (exit 2) sin tocar el cursor.

**AC-54.** Un mensaje con texto oculto y URLs en el cuerpo da `W_HIDDEN_CONTENT` y cuenta esas URLs solo con `--fields snippet`, `body` o `all` en `search`/`new`, y con los campos de cuerpo de RF-72 (regla 2) en `show`; `W_SENDER_AUTH_FAILED` aparece con y sin `--fields`; con `--count` solo hay warnings de alcance. Los criterios de F1 sobre el cuerpo y los destinatarios (AC-22–AC-39) aplican en `search` y `new` cuando esos campos se entregan (RF-72).

**AC-55.** La ayuda de `search`, `new` y `show`, la skill, `README.md`, `README.es.md` y las recetas cumplen RF-73, y `doctor --help` describe `--failures` (RF-74).

**AC-56.** `doctor --json --failures` con todo correcto devuelve `ok: true`, `checks: []`, `not_evaluated: []` y `plugins: []`; con un chequeo que falla devuelve solo los chequeos que fallan, con su `detail`, y en `not_evaluated` los que dependían de ellos; en texto, `all checks passed` o una línea por fallo y la de `not evaluated`; el exit es 0 en todos los casos; sin `--failures`, `doctor` muestra el informe completo de §12.8, con el título de RF-75 y la sección de plugins de RF-79.

**AC-57.** La skill no contiene la regla de *preflight*, indica `doctor --json --failures` solo en los casos de RF-75 y `mailboxes` solo para editar la configuración o tras un `search` sin resultados, y sus ejemplos empiezan por `search`; el ejemplo de `doctor` en la ayuda general y el título del informe de texto de `doctor` lo describen como `environment and read-only diagnosis`; `README.md` y `README.es.md` describen `doctor` según RF-75.

**AC-58.** En macOS, en Windows y con un plugin, un `search` sin resultados devuelve `count: 0`, exit 0 y el hint de RF-76 con el número correcto de carpetas y cuentas (INBOX, `mailbox_list` y `--include-mailbox`), también con `--group-by` y con `--count`; una cuenta excluida no cuenta en el número de cuentas; sin cuentas leídas (ninguna declarada o todas excluidas), `hint` es `null` y aparece `W_NO_ACCOUNTS`; con resultados, `hint` no cambia; `new` sin correo nuevo da `hint: null`; el hint no contiene nombres de carpetas ni de cuentas, y calcularlo no añade llamadas al driver.

**AC-59.** En macOS, en Windows y con un plugin, `mailboxes` sin `--fields` devuelve solo `ok`, `command`, `generated_at`, `accounts`, `excluded_stores` y `warnings`; cada cuenta tiene `uuid`, `label`, `email`, `declared` y `mailboxes[]` con sus carpetas, cada una solo con `path` e `included` y con los valores y el orden de §11.3; ninguna carpeta lleva `account`; con varios drivers se respeta el orden de §11.3; un `path` copiado de la salida resuelve en `mailbox_list` y en `--include-mailbox`, y el nombre y la URL siguen resolviendo.

**AC-60.** `mailboxes --fields name,url,total,unread` y la opción repetida añaden esos campos a cada carpeta, en el orden de RF-78 y con los valores de §11.3; `--fields all`, un campo desconocido o vacío ⇒ `E_USAGE` (exit 2) antes de abrir el store, con el mensaje y el hint de RF-78; sin `total` ni `unread`, no se cuenta ningún mensaje y `mailboxes` cumple el presupuesto p95 de §19; `mailboxes --help` y la ayuda general cumplen RF-78.

**AC-61.** Con un plugin falso declarado, `doctor --json` da `plugins` con su `driver`, los chequeos de su `doctor_checks()` sin cambios y después `config` con la resolución de sus bloques `[scope]` (un bloque que no resuelve da el código y el hint del error); `checks[]` del primer nivel es igual que sin el plugin, salvo el detalle de `driver` y que `config` no lista sus bloques; sin plugins declarados, `plugins: []` y el texto no muestra `Plugins:`; un plugin que no pasa `driver` solo da `config` con `not evaluated: driver failed`; un `doctor_checks()` que lanza una excepción, devuelve algo inválido o no responde en 30 s da el chequeo `plugin` con `ok: false`; el texto muestra la sección `Plugins:`; `Result:` cuenta todos los chequeos y el exit es 0.

**AC-62.** Con `--failures`, solo salen los plugins con algún chequeo que falla o sin evaluar, con sus `checks` que fallan y su `not_evaluated`; si solo falla un plugin, el texto muestra solo `Plugins:` y el JSON da `checks: []` y `not_evaluated: []`; si no falla nada, `plugins: []` y el texto `all checks passed`.

**AC-63.** En Windows, todo `uid` que emite el driver `outlook` es `outlook:` más un id corto de 10 caracteres, con o sin sufijo; el mismo mensaje da el mismo `uid` en corridas sucesivas y, si ningún otro mensaje con su id corto se lee ni se registra después del borrado, también después de borrar `cache.db`; `show` y `attachment` lo resuelven; un `EntryID` como uid, con prefijo o sin él, un id corto en mayúsculas o los sufijos `-1` y `-02` ⇒ `E_USAGE` sin abrir ni crear la caché. En macOS el `uid` no cambia y, con solo el driver `apple_mail`, `cache.db` no se crea.

**AC-64.** Dos `native_id` del mismo driver con el mismo id corto reciben `seq` 1 y 2 y los uids `<driver>:<short_id>` y `<driver>:<short_id>-2`, también cuando llegan en la misma consulta; un `native_id` leído en dos consultas de una misma ejecución conserva su uid; cada uid resuelve a su mensaje, y `attachment` extrae los adjuntos de cada uno en su propio directorio, sin servir los del otro. Si se borra la fila del `seq` 2, un tercer `native_id` con ese id corto recibe el `seq` 2 otra vez.

**AC-65.** `search` (también con `--group-by`) y `new` (también con `--peek`) registran en la caché de ids nativos solo los mensajes que imprimen; `search --count` no registra filas; una respuesta sin mensajes no avisa al driver; si el registro falla, el comando falla sin imprimir mensajes ni escribir estado.

**AC-66.** Un `uid` cuyo mensaje está ausente confirmado (RF-81) ⇒ `message uid … was not found` y su fila desaparece de la caché. Con cada causa de *indeterminado* de RF-81, la fila sigue en la caché: hay un caso de prueba por cada causa. Ninguna fila cambia de `native_id`.

**AC-67.** Ninguna salida JSON tiene una propiedad `short_id` ni `seq`: las claves de las respuestas de `search`, `new`, `show`, `attachment`, `mailboxes` y `doctor` en Windows son las que fija la sección 12.5, las mismas que en macOS con solo el driver `apple_mail`.

**AC-68.** `show --show-native-id` muestra en Windows `outlook:<EntryID>` en `message.uid`; las claves del JSON, los demás valores, la caché de ids nativos y `cached_path` son los mismos que sin la opción; ese id nativo como entrada de `show` o de `attachment` ⇒ `E_USAGE`; `search`, `new`, `attachment`, `mailboxes` y `doctor` rechazan la opción con `E_USAGE`. Un plugin que devuelve una forma nativa que no cumple RF-38 ⇒ `E_PLUGIN_FAILED`. En macOS la salida de `show` es la misma con la opción y sin ella.

**AC-69.** El texto `mailquery` con 10 caracteres da el id corto `pmw3w06f5e`. Con el driver `outlook`: base bloqueada por otro proceso más de 5 s ⇒ `E_LOCKED` (exit 5); sin permiso sobre `cache.db` ⇒ `E_PERMISSION`; archivo que no es una base válida de la librería o conflicto al registrar ⇒ `E_IO`, con el hint de RF-80; archivo vacío ⇒ se inicializa. Desde el aviso de un plugin que no captura el error, los mismos fallos dan `E_CLIENT_BUSY`, `E_PERMISSION` y `E_PLUGIN_FAILED`. Un uid que no está en la caché o cuyo mensaje está ausente confirmado lleva el hint de repetir la búsqueda. `show` sin la carpeta `~/.mailquery/db/` ni `cache.db` ⇒ crea las dos, con la base vacía, y responde `message uid … was not found`. En macOS, la carpeta tiene permisos 0700, y `cache.db` y sus archivos auxiliares, 0600. La tabla de `cache.db` solo tiene las columnas de su estructura. `mailboxes`, `doctor` y `--version` no crean `cache.db`.

**AC-70.** Un plugin recibe en su contexto el acceso a la base de su driver, que se abre en su primera operación: con él registra y resuelve sus filas, también dentro de un gancho vigilado por el tope de 30 s, y no ve ni cambia las filas de otro driver. Un plugin sin los ganchos opcionales funciona igual: no recibe el aviso y `show --show-native-id` muestra su uid sin cambios. Un gancho de un plugin que supera el tope de 30 s ⇒ `E_CLIENT_TIMEOUT`, sin imprimir mensajes.

**AC-71.** `initialize` responde con `serverInfo.name` `mailquery`, `serverInfo.version` igual a `__version__` y la capacidad `tools` sin `listChanged`; si se pide `2025-06-18`, la respuesta lleva `2025-06-18`, y si se pide una versión no soportada, `2025-11-25`. `ping` devuelve un resultado vacío y `notifications/initialized` no recibe respuesta. `tools/list` devuelve exactamente `search`, `new`, `show`, `attachment`, `mailboxes` y `doctor`, en ese orden, cada una con la `description` de su subcomando, los parámetros de sus opciones según RF-85 (`log_level` en todas, `index` de `attachment` como `integer`, sin `json` en `doctor` y sin `show_native_id` en `show`) y `additionalProperties: false`. Cada línea escrita en stdout durante la sesión es un mensaje JSON-RPC 2.0. Un método desconocido recibe `-32601`; una línea que no es JSON, `-32700`; una petición sin `method` o un array vacío, `-32600`. Un lote con dos peticiones recibe un array con sus dos respuestas en orden, y un lote solo de notificaciones no recibe respuesta. Una línea terminada en `\r\n` se atiende igual, y en Windows cada línea escrita termina en `\n`.

**AC-72.** Con un ejecutor de llamadas sustituido que registra el argv y devuelve una salida dada, cada llamada produce el argv de la CLI equivalente: `-P -m mailquery`, `log_level` antes del comando, `--opción=valor`, un `array` como opción repetida, un `false` omitido, el `uid` detrás de `--` y `doctor` con `--json`. El texto del resultado es la salida dada sin el salto de línea final, e `isError` es `true` solo si el código de salida es distinto de 0. Con el ejecutor real, una llamada `search` con `{"since": "bogus"}` devuelve el mismo JSON que `mailquery search --since=bogus`, con `isError: true`, también con un `json.py` en el directorio de trabajo del servidor.

**AC-73.** Un parámetro desconocido, un `integer` con texto o un `show` sin `uid` devuelven `E_USAGE` con `command` igual a la herramienta, un `hint` que nombra el parámetro e `isError: true`, sin lanzar ningún proceso hijo; un `show` con `show_native_id` y un valor con NUL también devuelven `E_USAGE` sin proceso hijo; el JSON tiene el formato de la CLI (§12.5). Un `subject` cuyo valor empieza por `-` llega al proceso hijo como `--subject=<valor>`. Un `tools/call` con una herramienta desconocida recibe el error `-32602`.

**AC-74.** El servidor arranca y responde a `tools/list` sin `config.toml` y con un `config.toml` inválido. Un proceso hijo que no escribe un objeto JSON da `E_INTERNAL` con el `message`, el `hint` y el `command` de RF-86 e `isError: true`, y el servidor responde a la llamada siguiente. Con un `config.toml` inválido, una llamada devuelve `E_CONFIG_INVALID`; tras corregirlo, la llamada siguiente ya no lo devuelve, sin reiniciar el servidor. Dos peticiones escritas seguidas reciben sus respuestas en orden, y el segundo proceso hijo empieza después de que termina el primero. Al cerrar stdin con una llamada en curso, el servidor responde a esa llamada y termina con exit 0. Durante la sesión, el servidor no escribe nada en stderr.

**AC-75.** `mailquery --help` lista `mcp` con su texto; `mailquery mcp` y `mailquery mcp serve extra` terminan con `E_USAGE` (exit 2) y JSON de error con `"command": "mcp"`; `mailquery mcp --help` y `mailquery mcp serve --help` muestran la orden `claude mcp add --scope user mailquery -- mailquery mcp serve` y la entrada genérica `mcpServers`. La ayuda raíz nombra `mailquery.log` y `mailquery.jsonl` y dice que `mcp serve` no escribe un objeto JSON. Los dos README documentan el registro, las herramientas, la equivalencia entre parámetros y opciones y los permisos de la app que lanza el servidor; la skill describe el uso de las herramientas MCP y la CLI como alternativa. El log del servidor tiene `event=start command=mcp`, una línea `event=call` por llamada con `tool`, `exit_code` y `duration_ms` y sin valores de parámetros, y `event=end`.

**AC-76.** Las dependencias declaradas del paquete no cambian, y `mcp_server.py` solo importa módulos de la biblioteca estándar y de `mailquery`. Con un plugin instalado cuya carga falla, el servidor arranca y responde a `initialize` y `tools/list`: no carga plugins ni instancia drivers.

**AC-77.** Sin la clave `[logging].json`, o con `false`, una ejecución de `search` escribe en `mailquery.log` con el formato de §14 y no crea `mailquery.jsonl`. Con `true`, escribe solo en `mailquery.jsonl` y `mailquery.log` no cambia. Cada línea es un objeto JSON con `ts`, `level`, `logger`, `run` y `fields`; en `fields`, `exit_code` y `duration_ms` son números, `truncated` es booleano y un valor `-` es `null`, sin asuntos, direcciones, uids ni rutas. Un `event=error` lleva su mensaje completo en `fields.message`, como texto también si es numérico. Un `E_INTERNAL` lleva su traceback en `traceback`, y su `hint` nombra `mailquery.jsonl`; los `hint` de Outlook que nombran el log también. Con `level = "warning"` no hay líneas `INFO`. En POSIX el archivo tiene permisos `0600`. `mailquery.jsonl` rota a `mailquery.jsonl.1` y conserva 5 rotados. `json = "yes"` termina con `E_CONFIG_INVALID` (exit 2) y la ejecución lo registra en `mailquery.log` en texto; con `json = true` y otra clave inválida, también.

**AC-78.** Con el servidor en marcha, `max_size_mb = 1` y el archivo activo precargado justo por debajo del tope, la llamada siguiente lo rota sin errores en macOS y en Windows, en los dos formatos: aparece el primer rotado y la línea `event=call` del servidor está en el archivo activo nuevo.

---


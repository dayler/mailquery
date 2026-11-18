# Contenido no confiable: primitivas y cuerpo

#### UT-CNT-01 — Saneado del texto

Requisitos: RF-52 · Archivo: `tests/test_content.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Quita secuencias ANSI CSI (`\x1b[31m…\x1b[0m`). |
| .02 | P | `\r\n` y `\r` → `\n`. |
| .03 | P | Elimina C0 salvo `\n` y `\t`, y DEL; conserva `\n` y `\t`. |
| .04 | P | Elimina C1 `U+0080..U+009F` (extremos y uno intermedio). |
| .05 | P | Elimina `Cf`: `U+200B`, `U+200D`, `U+202E`, `U+2066`, `U+FEFF`, `U+00AD` y un *tag character* `U+E0041`. |
| .06 | P | Elimina `U+FE00`, `U+FE0D`, `U+E0100`, `U+E01EF`; conserva `U+FE0E` y `U+FE0F` (`"❤️"` sale igual). |
| .07 | P | Elimina los rellenos Hangul `U+115F`, `U+1160`, `U+3164` y `U+FFA0`. |
| .08 | B | Idempotente: `sanitize_text(sanitize_text(x)) == sanitize_text(x)` para cada muestra. |
| .09 | B | Sin normalización: `"é"` (e + acento combinante) y `"ｆ"` (ancho completo) no cambian. |
| .10 | B | El resto del texto no cambia (acentos, CJK, emoji sin `Cf`); el ejemplo de saneado de la sección 8 del PRD da sus tres salidas. |
| .11 | B | `max_chars` recorta como hoy y no recorta más allá. |
| .12 | P | Quita secuencias OSC terminadas en `ST` y en `BEL`; el texto visible se conserva. |
| .13 | B | `sanitize_text("")` devuelve `""`. |

#### UT-CNT-02 — HTML → texto con omisión en línea

Requisitos: RF-53, RF-56 · Archivo: `tests/test_content.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `hidden`, `hidden=""` y `hidden="hidden"` omiten el elemento y sus descendientes. |
| .02 | P | `style` con `display:none`, `visibility:hidden`, `mso-hide:all`, `font-size:0` u `opacity:0` omite; también con mayúsculas, espacios, `!important`, `0.0`, `.0`, `0px`, `0%`, `0em` y tras otra declaración (`color:red; display:none`). |
| .03 | N | No omiten: `font-size:0.8em`, `font-size:inherit`, `opacity:0.5`, `xdisplay:none`, `min-font-size:0` ni `display:none` dentro de un valor de otra propiedad. |
| .04 | N | `aria-hidden="true"` conserva el texto. |
| .05 | B | `<br hidden>`, `<img hidden>` e `<input style="display:none">` no omiten el texto siguiente. |
| .06 | B | Elemento oculto sin cierre por la vía de fallo del paso a línea: se omite hasta el final. |
| .07 | B | Anidación de la misma etiqueta: `<div hidden><div>a</div>b</div>c` da `c`. |
| .08 | P | El texto visible alrededor no cambia (ejemplo A3 «HTML oculto» de la sección 8 del PRD → `Factura adjunta.`). |
| .09 | B | Todo oculto → `text == ""` y `hidden_chars > 0`. |
| .10 | P | Conteo: el ejemplo de la hoja `<style>` da 30; un texto oculto con un `U+200B` cuenta sin él (el saneado va antes de contar). |
| .11 | B | Conteo con entidades y comentarios dentro del oculto: `<div hidden>a&nbsp;&amp;<!-- c -->b</div>` cuenta los caracteres ya decodificados y no cuenta el comentario. |
| .12 | B | Ramas del analizador: `<div hidden><span>x</div>y` da `y`; `<div hidden/>z` no omite `z`; `<script>` dentro de un oculto no aporta texto a ningún flujo; `style` mal formado (`display`, `;;`, sin `:`) no omite; un `</script>` huérfano no rompe la conversión. |

#### UT-CNT-03 — Hojas `<style>` y `css-inline`

Requisitos: RF-53, RNF-17 · Archivo: `tests/test_content.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Una regla de clase con `display:none` en `<style>` oculta el elemento (ejemplo A3 de la sección 8 del PRD). |
| .02 | P | Reglas por id, por etiqueta y con selector compuesto también ocultan. |
| .03 | N | Una regla dentro de `@media` no oculta nada. |
| .04 | N | `<link rel="stylesheet" href="file:///<tmp>/hide.css">` a un archivo local con `.x{display:none}`: el texto sigue presente. |
| .05 | N | `<link rel="stylesheet" href="http://127.0.0.1:<puerto>/hide.css">` con un `http.server` en un hilo de este test: el servidor recibe 0 peticiones y el texto sigue presente. |
| .06 | P | `import css_inline` falla (simulado): se convierte el HTML original sin excepción y la omisión en línea sigue funcionando; una segunda llamada no reintenta la importación. |
| .07 | P | `inline()` lanza una excepción (simulada): se convierte el HTML original sin excepción. |
| .08 | B | El inliner se construye con `load_remote_stylesheets=False` y sin `base_url` (espía sobre el constructor). |
| .09 | B | Determinismo: la misma entrada dos veces da el mismo `HtmlText`. |
| .10 | B | Regla de `<style>` con `display:none !important` y estilo en línea que la contradice: se omite (riesgo aceptado del PRD) y se cuenta. |
| .11 | N | `<style>@import url("http://127.0.0.1:<puerto>/hide.css");</style>` y `@import` a un `file:///<tmp>/hide.css` local con `.x{display:none}`: el servidor de .05 recibe 0 peticiones y el texto sigue presente. El fallo real de CSS se cubre en .07 porque ningún CSS probado hace lanzar a `css-inline` 0.23.1. |

#### UT-CNT-04 — Texto de `content_notice`

Requisitos: RF-66 · Archivo: `tests/test_content.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `CONTENT_NOTICE` es literalmente el texto de RF-66. |

#### UT-CNT-05 — Detección de URLs

Requisitos: RF-54, RF-57 · Archivo: `tests/test_content.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Cada inicio de RF-54 se detecta, también en mayúsculas (`HTTPS://`, `WWW.`, `HXXPS://`, `JAVASCRIPT:`, `DATA:`): `http`, `https`, `ftp`, `smb`, `file`, `javascript:`, `vbscript:`, `data:text/html…`, `www.`, `hxxp://`, `hxxps://` y la ruta UNC; `kind`, `scheme`, `script` y los offsets son los esperados. |
| .02 | P | `ｈｔｔｐｓ：／／evil.example/pay` y `ｈｘｘｐ：／／evil.example/pay` se detectan (inicios con esquema en ancho completo). |
| .03 | P | `evil[.]example/pay` se detecta como una sola URL de tipo `bracket_domain`, sin esquema y sin marca de script. |
| .04 | N | No son URL: `JavaScript: un lenguaje`, `Data: 12/11`, `metadata:x`, `facturas.example/f/1`, `mailto:a@b.example`, `tel:123`, `ms-word:ofe`, `http://` sin nada detrás, `data:12`, `data:text/html`, `\\`, `\\evil.example` sin `\` final, `\\evil\` sin nada detrás, `www.-x`, `www. x`, los inicios en ancho completo de `data:` y `www.`, `＼＼evil.example\share`, `a[.]`, `[.]b`, `[.]`, `xhttp://a` y la cadena vacía. |
| .05 | B | Terminación: espacio, `"`, `'`, `<` y `>` cortan la URL; dos URLs seguidas no se solapan. |
| .06 | P | `url_domain`: con usuario y puerto (`https://u:p@host.example:8080/x` → `host.example`), `www.` con puerto, UNC y `[.]` (`evil[.]example/pay` → `evil.example`); `None` para `javascript:`, `vbscript:` y `data:`. |
| .07 | P | `url_domain` con inicio en ancho completo (`ｈｔｔｐｓ：／／evil.example/pay`) y ya neutralizado (`hxxps://evil.example/pay`) → `evil.example`; `address_domain` de una dirección (también con dos separadas por coma), de `None`, de `""` o sin `@` da el dominio o `None`. |
| .08 | N | No son URL `www.` sin letra ni dígito detrás (`www.-x`, `www. x`, `www.`) y `[.]` sin letra o dígito a los dos lados (`a[.]`, `[.]b`, `[.]`, `...[.]...`). |

#### UT-CNT-06 — Modos de URL

Requisitos: RF-54 · Archivo: `tests/test_content.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `keep` deja el texto igual. |
| .02 | P | `neutralize`: cada fila de las tablas A4 de la sección 12.5 de PRD.md da el resultado indicado, también con el esquema en mayúsculas (`HTTPS://`, `WWW.`). |
| .03 | P | `strip`: cada URL → `[link omitted]` (filas de la sección 12.5 de PRD.md) y el resto del texto no cambia. |
| .04 | B | Una URL ya neutralizada, ASCII y de 2.048 caracteres o menos (`hxxps://…`, `evil[.]example/pay`) no cambia con `neutralize`. |
| .05 | B | Idempotencia: `render_urls(render_urls(x, "neutralize"), "neutralize") == render_urls(x, "neutralize")` para todas las muestras. |
| .06 | B | El texto fuera de las URLs no cambia en ningún modo; dos llamadas dan el mismo resultado; un texto sin URLs (incluidos caracteres con NFKC de varios caracteres) no cambia; `render_urls(x, "otro")` lanza `ValueError`. |
| .07 | P | Esquemas de script en mayúsculas y en ancho completo: `JAVASCRIPT:x` → `JAVASCRIPT[:]x`, `VbScript:x` → `VbScript[:]x`, `DATA:text/html,x` → `DATA[:]text/html,x`, `ｊａｖａｓｃｒｉｐｔ：x` → `ｊａｖａｓｃｒｉｐｔ[:]x`. |

#### UT-CNT-07 — Punycode y acortado

Requisitos: RF-54, RF-57 · Archivo: `tests/test_content.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `https://pаypal.com/login` (а cirílica) → `hxxps://xn--pypal-4ve.com/login`; solo cambian la etiqueta no ASCII y el esquema. |
| .02 | P | Dominio entero en otro alfabeto, dominio `www.` no ASCII y dominio con dos etiquetas no ASCII: cada etiqueta no ASCII en ACE y las etiquetas ASCII intactas. |
| .03 | B | URL de 2.048 caracteres sale entera; de 2.049 sale con 256 + `…[+1793 characters]`; el ejemplo de 5.000 da `…[+4744 characters]`. |
| .04 | B | `keep` nunca acorta ni cambia el dominio; `strip` da `[link omitted]` también para la URL larga. |
| .05 | B | El acortado se calcula sobre la URL ya neutralizada (con punycode): el `<n>` correcto cuando el ACE cambia la longitud (`…[+1800 characters]`). |
| .06 | P | URL ya neutralizada por el remitente (D-20): `hxxps://pаypal.com/x` → `hxxps://xn--pypal-4ve.com/x` (el esquema no cambia, el dominio sí); una `hxxps://` de 5.000 caracteres sale con sus primeros 256 + `…[+4744 characters]`. |
| .07 | P | ACE en el host de una ruta UNC no ASCII (`\\pаypal\share` → `[\\]xn--pypal-4ve\share`) y en un dominio `[.]` no ASCII (`pаypal[.]com/x` → `xn--pypal-4ve[.]com/x`). |

#### UT-CNT-08 — Conteos y textos de las señales

Requisitos: RF-55, RF-57–RF-59 · Archivo: `tests/test_content.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `count_url_signals` suma URLs de varios textos; una URL de script cuenta en `external` y en `script`; una de 2.049 cuenta en `long` y una de exactamente 2.048 no; sin entradas da ceros y dos llamadas coinciden. |
| .02 | P | `non_ascii_domains` cuenta una URL con alfabetos mezclados, una con dominio entero en otro alfabeto y una dirección `soporte@pаypal.com`; no cuenta usuario ni ruta no ASCII de la URL ni dominios ASCII parecidos (`paypa1.com`). |
| .03 | P | Los textos de los siete warnings son literalmente los de RF-55–RF-61 (con `<n>`, `<uid>` y `<resultados>`). |
| .04 | P | `content_warnings` devuelve solo los que aplican, en el orden `W_HIDDEN_CONTENT`, `W_EXTERNAL_LINKS`, `W_SCRIPT_LINK`, `W_LONG_URL`, `W_NON_ASCII_DOMAIN`, `W_SENDER_AUTH_FAILED`, `W_REPLY_TO_MISMATCH`; ninguno contiene URL, dominio ni dirección. |
| .05 | B | Sin URLs, sin oculto y sin señales del remitente → lista vacía. |
| .06 | P | `JAVASCRIPT:x`, `VbScript:x`, `DATA:text/html,x` y `ｊａｖａｓｃｒｉｐｔ：x` cuentan en `script` y en `external`. |

#### UT-CNT-09 — Señales del remitente

Requisitos: RF-60, RF-61 · Archivo: `tests/test_content.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | El ejemplo A6 de la sección 12.5 de PRD.md → `"spf=softfail dkim=none dmarc=fail"`. |
| .02 | N | Todo `pass`; `none`/`neutral` sin fallos; cabecera ausente (`None`) → `None`. |
| .03 | P | `permerror` y `fail` cuentan; mayúsculas (`SPF=FAIL`) → `spf=fail`; un mecanismo ausente no aparece en el resultado. |
| .04 | B | Varias firmas DKIM: una `pass` → `pass`; ninguna `pass` → la primera. |
| .05 | B | Resultado desconocido (`dkim=weird`) → `unknown`, y el resultado no contiene otro texto de la cabecera (comentarios, `header.from=…`, `header.d=…`, el servidor). |
| .06 | P | `reply_to_mismatch`: dominio distinto → `True` (también con varias direcciones y una distinta); el mismo dominio con otras mayúsculas → `False`. |
| .07 | N | Sin `Reply-To`, `from_address` sin `@`, `Reply-To` sin direcciones con dominio o mal formado (`"<<<"`, `""`) → `False`. |
| .08 | P | Valor plegado: `"mx.example;\r\n\tspf=pass smtp.mailfrom=a.example;\r\n\tdmarc=fail header.from=a.example"` → `"spf=pass dmarc=fail"`. |
| .09 | B | `sender_auth_failure("")`, una cabecera sin mecanismos reconocidos y `spf=temperror dkim=policy dmarc=pass` (sin fallo) → `None`. |

#### UT-BOD-01 — Cuerpo en Apple Mail

Requisitos: RF-53 · Archivo: `tests/test_body_sources.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `multipart/alternative` con texto plano y HTML distintos ⇒ `body_text` del HTML (`Factura adjunta.`), también en `BodyRow.body_text`. |
| .02 | P | Solo texto plano ⇒ texto plano. |
| .03 | N | HTML sin texto (solo `<img>`) con texto plano presente ⇒ `""` y `W_HTML_NO_TEXT`; el texto plano no aparece. |
| .04 | P | `multipart/mixed` con una parte `text/plain` y otra `text/html` de cuerpo ⇒ solo el HTML. |
| .05 | P | HTML con un elemento oculto ⇒ `hidden_chars` igual al de `html_body_to_text`; HTML todo oculto ⇒ `""`, `W_HTML_NO_TEXT` y `hidden_chars > 0`. |
| .06 | N | `text/plain` de cuerpo más una parte `text/html` con `Content-Disposition: attachment` ⇒ `body_text` del texto plano; el HTML adjunto no aporta texto. |

#### UT-BOD-02 — Cuerpo en Outlook (doble)

Requisitos: RF-53 · Archivo: `tests/test_body_sources.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `BodyFormat = 2` (`olFormatHTML`) con `Body` y `HTMLBody` distintos ⇒ texto del HTML, en `load_snippet` y en `load_body`. |
| .02 | P | `BodyFormat = 1` (texto plano) y `3` (RTF) ⇒ `Body`, aunque exista `HTMLBody`. |
| .03 | P | Item de reunión sin `BodyFormat` ni `HTMLBody` (`AttributeError`) ⇒ `Body`, sin error. |
| .04 | N | `BodyFormat = 2` con HTML sin texto y `Body` presente ⇒ `""` y `W_HTML_NO_TEXT`. |
| .05 | B | `BodyFormat` se lee por la lista blanca COM (sin violación del proxy de solo lectura, `mutations` y `forbidden` en cero) y no se abre ningún item más que uno por mensaje (`items_opened` y `GetItemFromID` = 1). |
| .06 | N | `HTMLBody` que lanza un error COM (no `AttributeError`), `BodyFormat` que lanza un error COM y `BodyFormat` que devuelve `None` ⇒ `Body`, sin error. |

#### UT-BOD-03 — Cabeceras del remitente en Apple Mail

Requisitos: RF-60, RF-61 · Archivo: `tests/test_body_sources.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Con dos `Authentication-Results` y una `ARC-Authentication-Results`, `authentication_results` es la primera (la de más arriba), en `load_body` y en `parse_emlx_headers`. |
| .02 | P | `Reply-To` se entrega crudo; sin la cabecera, `None`. |
| .03 | P | `load_headers` da las seis cabeceras de `show`, la primera `Authentication-Results` y `Reply-To` sin llamar a la extracción del cuerpo (espía sobre `emlx._extract_body_text`). |
| .04 | B | `parse_emlx_headers` no lee más allá del bloque de cabeceras (archivo con cuerpo de varios MiB: se leen como mucho 256 KiB); archivo ausente, ilegible o que es un directorio ⇒ vacío, `read=False`, sin excepción. |
| .05 | P | Primera `Authentication-Results` plegada con CRLF + tabulador y con `dmarc=fail` en una línea de continuación ⇒ el valor llega desplegado y contiene `dmarc=fail`, igual en `load_body` y en `load_headers`. |
| .06 | B | `parse_emlx_headers`: bloque sin línea vacía antes del tope de 256 KiB (devuelve lo leído hasta el tope, sin excepción), línea de longitud inválida, archivo vacío, sin salto de línea, longitud cero y bloque que no se puede parsear (vacío, `read=False`) y cabeceras con *encoded words* (se decodifican como en `parse_emlx`). |
| .07 | N | `load_headers` con un `.emlx` que no se resuelve, con una carpeta desconocida o con `resolve_path` que lanza ⇒ vacío y `read=False`; con un `.partial.emlx` ⇒ cabeceras leídas del parcial. |

#### UT-BOD-04 — Cabeceras del remitente en Outlook (doble)

Requisitos: RF-60, RF-61 · Archivo: `tests/test_body_sources.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Cabeceras de transporte con dos `Authentication-Results` y `Reply-To` ⇒ la primera y `Reply-To`, tanto en `load_body` como en `load_snippet`. |
| .02 | N | Correo interno sin cabeceras de transporte ⇒ `None` en las dos y `headers` vacías. |
| .03 | N | Item S/MIME: `load_headers` y `load_snippet` no abren el item (`CallLog` sin `GetItemFromID`) y devuelven vacío. |
| .04 | P | `load_headers` abre el item (cuenta en `items_opened`, un `GetItemFromID`) y no accede a `Body`, `HTMLBody` ni `Attachments`. |
| .05 | P | Cabeceras de transporte con la primera `Authentication-Results` plegada (CRLF + tabulador) y `dmarc=fail` en la línea de continuación ⇒ valor desplegado con `dmarc=fail`, en `load_headers` y en los dos cargadores del cuerpo. |
| .06 | N | `load_headers` con `GetItemFromID` que falla, o con la lectura de `PR_TRANSPORT_MESSAGE_HEADERS` que lanza ⇒ vacío y `read=False`, sin excepción. |

#### UT-BOD-05 — Punta a punta por `cli.main`

Requisitos: RF-53, RF-60, RF-61 · Archivo: `tests/test_body_sources.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `search --text <palabra solo del HTML> --since …` encuentra el mensaje; `--text <palabra solo del texto plano>` no lo encuentra (Apple Mail y Outlook). |
| .02 | P | `show` del mismo mensaje da `body_text` del HTML (Apple Mail y Outlook). |
| .03 | P | Con `css_inline` simulado ausente (parcheando `output._css_inline` y el import), `search`, `new` y `show` terminan con exit 0 y convierten el HTML original (la omisión en línea sigue). |

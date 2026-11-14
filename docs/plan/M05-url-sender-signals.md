# M05 — Primitivas A4 (URLs), A5 (señales de enlaces) y A6 (señales del remitente) en `output.py`

**Lote:** I2 · rama del lote `integration/i2-content` · **Oleada:** W2 (en paralelo con M06 y M07)
**Rama:** `feature/m05-url-sender-signals`, creada desde la punta de `integration/i2-content` · **Worktree:** `../mailquery-wt/m05`
**Estado:** 🟢 (integrado en `develop`; ver [`evidence/M05.md`](evidence/M05.md)) (leyenda y protocolo en [`00-master-plan.md`](00-master-plan.md))

## 1. Objetivo

Implementar en `src/mailquery/output.py`, como funciones puras, la detección de URLs y de sus dominios (RF-54, RF-57), los tres modos de visualización con punycode y acortado (RF-54), los conteos de las señales de enlaces (RF-55, RF-57–RF-59), la lectura del veredicto de `Authentication-Results` y la comparación de `Reply-To` (RF-60, RF-61), y los textos exactos de esos warnings. La conexión con `search`/`new`/`show` la hace M08.

## 2. Alcance

**Dentro (`src/mailquery/output.py`):**

1. `URL_MODES = ("neutralize", "keep", "strip")`.
2. `find_urls(text: str) -> list[UrlMatch]`, `UrlMatch` inmutable con `start`, `end`, `text`, `kind` (`"scheme"`, `"data"`, `"www"`, `"neutralized"`, `"unc"`, `"bracket_domain"`), `scheme` (minúsculas, con la forma NFKC del inicio cuando está en ancho completo) y `script: bool` (`javascript:`, `vbscript:`, `data:`). Reglas de RF-54:
   - inicio al principio del texto o tras un carácter que no es letra ni dígito; sin distinguir mayúsculas;
   - (a) `http://`, `https://`, `ftp://`, `smb://`, `file://`, `javascript:`, `vbscript:`; (b) `data:` + `tipo/subtipo` con las dos partes empezando por letra; (c) `www.` + letra o dígito; (d) `hxxp://`, `hxxps://`; (e) `\\` + host que empieza por letra o dígito + `\` + al menos un carácter;
   - los inicios de (a) y (d) también en ancho completo (cada carácter comparado por su forma NFKC; el texto no se normaliza);
   - al menos un carácter tras el inicio; termina antes del primer espacio en blanco, `"`, `'`, `<` o `>`;
   - también es URL la secuencia completa entre dos separadores (espacio en blanco, `"`, `'`, `<`, `>`) que contiene `[.]` entre dos letras o dígitos;
   - de izquierda a derecha, sin solapes; `mailto:`, `tel:`, `ms-word:` y dominios sin `www.` no son URL.
3. `url_domain(match) -> str | None` (RF-57): inicios con `//` → entre `//` y el primer `/`, `?`, `#` o el final, sin la parte hasta el último `@` ni la de `:` en adelante; `www.` → desde `www.` hasta el primer `/`, `?`, `#`, `:` o el final; UNC → el host; `[.]` → hasta el primer `/` con `[.]` leído como `.`; `javascript:`, `vbscript:`, `data:` → `None`. `address_domain(address) -> str | None`: la parte tras el último `@`.
4. `render_urls(text: str, mode: str) -> str` (RF-54):
   - `keep`: texto igual, nunca acorta;
   - `strip`: cada URL → `[link omitted]`;
   - `neutralize`: `http://`/`https://` (también en ancho completo) → `hxxp://`/`hxxps://`; en los demás esquemas el `:` → `[:]` (`file[:]//…`, `javascript[:]…`, `data[:]text/html…`, `ftp[:]//…`, `smb[:]//…`), también cuando el esquema está en ancho completo: el `:` o `：` del esquema pasa a `[:]` y el resto no cambia (`ｊａｖａｓｃｒｉｐｔ：x` → `ｊａｖａｓｃｒｉｐｔ[:]x`, D-22); `www.` → `www[.]`; UNC → empieza por `[\\]`; una URL ya neutralizada (`hxxp`, `[.]`) conserva su esquema sin cambios, pero también se le aplican el ACE y el acortado siguientes (D-20); cada etiqueta del dominio con caracteres no ASCII → `xn--` + Punycode de la etiqueta en minúsculas (D-04: códec `punycode`, no `idna`); si la URL original tiene más de 2.048 caracteres, se conservan los primeros 256 de la URL ya neutralizada y se añade `…[+<n> characters]`, con `<n>` = longitud de la URL neutralizada − 256.
   - El resto del texto no cambia; idempotente (aplicar `neutralize` dos veces da lo mismo).
   - Un `mode` fuera de `URL_MODES` lanza `ValueError` (la configuración y `--strip-links` nunca lo producen; la rama se prueba).
5. `UrlSignals` (conteo inmutable: `external`, `script`, `long`, `non_ascii_domains`) y `count_url_signals(texts: Iterable[str], addresses: Iterable[str]) -> UrlSignals`: suma sobre todos los textos las URLs (`external`), las de script (`script`, que también cuentan en `external`), las de más de 2.048 caracteres (`long`), y en `non_ascii_domains` cada URL y cada dirección cuyo dominio tiene algún carácter por encima de `U+007F`. Las direcciones solo se cuentan, nunca se transforman.
6. **A6:**
   - `sender_auth_failure(header_value: str | None) -> str | None`: de la primera cabecera `Authentication-Results` (la elige el backend, M06; el valor puede llegar plegado, con CRLF o LF seguido de espacio o tabulador, y se despliega antes de leerlo), toma `spf`, `dkim` y `dmarc` (`<mecanismo>=<resultado>`, sin distinguir mayúsculas; ignora comentarios entre paréntesis); con varias firmas DKIM, `pass` si alguna pasa y, si no, la primera; un resultado fuera de `pass`, `fail`, `softfail`, `neutral`, `none`, `temperror`, `permerror`, `policy` → `unknown`. Si alguno es `fail`, `softfail` o `permerror`, devuelve `"spf=softfail dkim=none dmarc=fail"` con los mecanismos presentes en ese orden y en minúsculas; si no, `None`.
   - `reply_to_mismatch(reply_to: str | None, from_address: str | None) -> bool`: `True` si alguna dirección de `Reply-To` (con `email.utils.getaddresses`) tiene dominio distinto del de `from_address`, sin distinguir mayúsculas; `False` sin `Reply-To`, sin `@` en `from_address`, sin direcciones con dominio o con un `Reply-To` mal formado del que `getaddresses` no saca direcciones.
7. Textos exactos de los warnings (funciones puras que M08 usa tal cual):
   - `W_HIDDEN_CONTENT: <n> hidden character(s) omitted from the body of <uid>`
   - `W_EXTERNAL_LINKS: <n> external link(s) in <uid>`
   - `W_SCRIPT_LINK: <n> javascript/vbscript/data link(s) in <uid>`
   - `W_LONG_URL: <n> URL(s) longer than 2048 characters in <uid>`
   - `W_NON_ASCII_DOMAIN: <n> domain(s) with non-ASCII characters in <uid>`
   - `W_SENDER_AUTH_FAILED: <resultados> in <uid>`
   - `W_REPLY_TO_MISMATCH: reply-to domain differs from the sender domain in <uid>`
   - y `content_warnings(uid, hidden_chars, signals, auth_failure, reply_mismatch) -> list[str]` que devuelve los que aplican en el orden de PRD-v2.2 sección 10, punto 8.

**Fuera:** decidir qué campos se transforman o se cuentan, `--strip-links`, `[content]` (M08); leer las cabeceras (M06); `W_ATTACHMENT_ACTIVE_CONTENT` (M09).

## 3. Dependencias y ACs

- **Entrada:** M03 (mismo archivo; `sanitize_text`).
- **Salida:** M08.
- **ACs:** AC-H02 (determinismo e idempotencia de los modos), AC-H06 (detección y modos), AC-H08, AC-H09, AC-H10 (conteos y textos), AC-H11 (lectura del veredicto y comparación de dominios).

## 4. Archivos

| Acción | Archivo |
|---|---|
| Modifica | `src/mailquery/output.py` |
| Modifica | `tests/test_content.py` (creado por M03; añade UT-CNT-05 a UT-CNT-09) |
| Modifica | `tests/fixtures/content_samples.py` (creado por M03; añade muestras de URL y de cabeceras) |
| Bloques para el orquestador | `docs/TEST-CATALOG.md` (secciones 7 y 8), `docs/INTERFACES.md` (contrato de `output.py`) |

## 5. Refactorizaciones previas

Ninguna.

## 6. Fases

| Fase | Tareas | Estado |
|---|---|---|
| F1 — Detección | `find_urls`, `url_domain`, `address_domain`; UT-CNT-05 | 🟢 |
| F2 — Modos | `render_urls` con punycode y acortado; UT-CNT-06, UT-CNT-07 | 🟢 |
| F3 — Conteos y textos | `count_url_signals`, textos de warnings, `content_warnings`; UT-CNT-08 | 🟢 |
| F4 — A6 | `sender_auth_failure`, `reply_to_mismatch`; UT-CNT-09 | 🟢 |
| F5 — Cierre | Suite completa, evidencia cruda, bloques | 🟢 |

## 7. Tests

Archivo `tests/test_content.py` (prefijo UT-CNT).

**UT-CNT-05 — Detección de URLs**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Cada inicio de (a) `http`, `https`, `ftp`, `smb`, `file`, `javascript`, `vbscript`, (b) `data:text/html…`, (c) `www.`, (d) `hxxp`/`hxxps`, (e) UNC se detecta, también en mayúsculas (`HTTPS://`, `WWW.`). |
| .02 | P | `ｈｔｔｐｓ：／／evil.example/pay` y `ｈｘｘｐ：／／…` se detectan. |
| .03 | P | `evil[.]example/pay` se detecta como URL entera entre separadores. |
| .04 | N | No son URL: `JavaScript: un lenguaje`, `Data: 12/11`, `metadata:x`, `facturas.example/f/1`, `mailto:a@b.example`, `tel:123`, `ms-word:ofe`, `http://` sin nada detrás, `data:12`, `\\` sin `\` final. |
| .05 | B | Terminación: corta en espacio, `"`, `'`, `<`, `>`; un inicio pegado a una letra (`xhttp://a`) no cuenta; dos URLs seguidas no se solapan. |
| .06 | P | `url_domain`: con usuario y puerto (`https://u:p@host.example:8080/x` → `host.example`), `www.` con puerto, UNC, `[.]` (`evil[.]example/pay` → `evil.example`), y `None` para `javascript:`/`vbscript:`/`data:`. |
| .07 | P | `url_domain` con inicios en ancho completo y ya neutralizados: `ｈｔｔｐｓ：／／evil.example/pay` y `hxxps://evil.example/pay` → `evil.example` (el `／／` de ancho completo cuenta como `//`). `address_domain(None)` y `address_domain("sin-arroba")` → `None`. |
| .08 | N | No son URL: `www.` seguido de un carácter que no es letra ni dígito (`www.-x`, `www. x`) y `[.]` sin letra o dígito a los dos lados (`a[.]`, `[.]b`, `[.]`). |

**UT-CNT-06 — Modos de URL**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `keep` deja el texto igual. |
| .02 | P | `neutralize`: cada fila de las dos tablas A4 de PRD-v2.2 sección 8 da exactamente el resultado indicado, también con el esquema en mayúsculas. |
| .03 | P | `strip`: cada URL → `[link omitted]` (filas de PRD-v2.2 sección 8). |
| .04 | B | Una URL ya neutralizada, ASCII y de 2.048 caracteres o menos (`hxxps://…`, `evil[.]example/pay`) no cambia con `neutralize`. |
| .05 | B | Idempotencia: `render_urls(render_urls(x, "neutralize"), "neutralize") == render_urls(x, "neutralize")` para todas las muestras. |
| .06 | B | El texto fuera de las URLs no cambia en ningún modo; determinismo con dos llamadas; `render_urls(x, "otro")` lanza `ValueError`. |
| .07 | P | Esquemas de script en mayúsculas y en ancho completo (D-22): `JAVASCRIPT:x` → `JAVASCRIPT[:]x`, `VbScript:x` → `VbScript[:]x`, `DATA:text/html,x` → `DATA[:]text/html,x`, `ｊａｖａｓｃｒｉｐｔ：x` → `ｊａｖａｓｃｒｉｐｔ[:]x`. |

**UT-CNT-07 — Punycode y acortado**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `https://pаypal.com/login` (а cirílica) → `hxxps://xn--pypal-4ve.com/login`; solo cambia la etiqueta no ASCII. |
| .02 | P | Dominio entero en otro alfabeto y dominio `www.` no ASCII → cada etiqueta no ASCII en ACE. |
| .03 | B | URL de 2.048 caracteres sale entera; de 2.049 sale con 256 + `…[+1793 characters]`; el ejemplo de 5.000 da `…[+4744 characters]`. |
| .04 | B | `keep` nunca acorta ni cambia el dominio; `strip` da `[link omitted]` también para la URL larga. |
| .05 | B | El acortado se calcula sobre la URL ya neutralizada (con punycode): `<n>` correcto cuando el ACE cambia la longitud. |
| .06 | P | URL ya neutralizada por el remitente (D-20): `hxxps://pаypal.com/x` → `hxxps://xn--pypal-4ve.com/x` (el esquema no cambia, el dominio sí); una `hxxps://` de 5.000 caracteres sale con sus primeros 256 + `…[+4744 characters]`. |
| .07 | P | ACE en el host de una ruta UNC no ASCII (`\\pаypal\share` → `[\\]xn--pypal-4ve\share`) y en un dominio `[.]` no ASCII (`pаypal[.]com/x` → `xn--pypal-4ve[.]com/x`). |

**UT-CNT-08 — Conteos y textos de las señales**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `count_url_signals` suma URLs de varios textos; una URL de script cuenta en `external` y en `script`; una de 2.049 cuenta en `long` y una de exactamente 2.048 no. |
| .02 | P | `non_ascii_domains` cuenta una URL con alfabetos mezclados, una con dominio entero en otro alfabeto y una dirección `soporte@pаypal.com`; no cuenta usuario ni ruta no ASCII de la URL ni dominios ASCII parecidos (`paypa1.com`). |
| .03 | P | Los textos de los siete warnings son literalmente los de RF-55–RF-61 (con `<n>`, `<uid>` y `<resultados>`). |
| .04 | P | `content_warnings` devuelve solo los que aplican, en el orden `W_HIDDEN_CONTENT`, `W_EXTERNAL_LINKS`, `W_SCRIPT_LINK`, `W_LONG_URL`, `W_NON_ASCII_DOMAIN`, `W_SENDER_AUTH_FAILED`, `W_REPLY_TO_MISMATCH`; ninguno contiene URL, dominio ni dirección. |
| .05 | B | Sin URLs, sin oculto y sin señales del remitente → lista vacía. |
| .06 | P | `JAVASCRIPT:x`, `VbScript:x`, `DATA:text/html,x` y `ｊａｖａｓｃｒｉｐｔ：x` cuentan en `script` y en `external`. |

**UT-CNT-09 — Señales del remitente**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | El ejemplo A6 de PRD-v2.2 sección 8 → `"spf=softfail dkim=none dmarc=fail"`. |
| .02 | N | Todo `pass`; `none`/`neutral` sin fallos; cabecera ausente (`None`) → `None`. |
| .03 | P | `permerror` y `fail` cuentan; mayúsculas (`SPF=FAIL`) → `spf=fail`; un mecanismo ausente no aparece en el resultado. |
| .04 | B | Varias firmas DKIM: una `pass` → `pass`; ninguna `pass` → la primera. |
| .05 | B | Resultado desconocido (`dkim=weird`) → `unknown`, y el resultado no contiene otro texto de la cabecera (comentarios, `header.from=…`). |
| .06 | P | `reply_to_mismatch`: dominio distinto → `True`; mismo dominio con otras mayúsculas → `False`; varias direcciones con una distinta → `True`. |
| .07 | N | Sin `Reply-To`, `from_address` sin `@`, `Reply-To` sin direcciones con dominio o mal formado (`"<<<"`) → `False`. |
| .08 | P | Valor plegado: `"mx.example;\r\n\tspf=pass smtp.mailfrom=a.example;\r\n\tdmarc=fail header.from=a.example"` → `"spf=pass dmarc=fail"`. |
| .09 | B | `sender_auth_failure("")` y una cabecera sin ningún mecanismo reconocido → `None`; `spf=temperror dkim=policy dmarc=pass` (sin fallo) → `None`. |

Comandos:

```bash
python -B -m unittest discover -s tests -t . -k test_ut_cnt_05_
python -B -m unittest discover -s tests -t . -k test_ut_cnt_06_
python -B -m unittest discover -s tests -t . -k test_ut_cnt_07_
python -B -m unittest discover -s tests -t . -k test_ut_cnt_08_
python -B -m unittest discover -s tests -t . -k test_ut_cnt_09_
python -B -m unittest tests.test_content -v
python -B -m coverage erase
python -B -m coverage run -m unittest discover -s tests -t .
python -B -m coverage report
python -B -m coverage report --include=src/mailquery/output.py --fail-under=85
```

## 8. Tests existentes afectados

Ninguno (solo se añaden funciones).

## 9. Documentación

- Bloque para `INTERFACES.md`, contrato de `output.py`: `URL_MODES`, `UrlMatch`, `find_urls`, `url_domain`, `address_domain`, `render_urls`, `UrlSignals`, `count_url_signals`, `sender_auth_failure`, `reply_to_mismatch`, textos de warnings y `content_warnings`.
- Bloques para `TEST-CATALOG.md`: sección 8, UT-CNT-05–UT-CNT-09; sección 7, filas parciales de AC-H02, AC-H06, AC-H08–AC-H11 (delta `PRD-v2.2.md`).
- README, skill, ayudas: sin cambios (M08).

## 10. Actualizaciones de `PRD-v2.2.md` (las escribe el orquestador)

- Registro de conciliación: fila "Cuerpo, `snippet`, asunto, nombres y `headers` (F1)" → nota "primitivas de A4/A5 implementadas"; estado sigue `Pendiente` hasta M08.
- Tabla de supersesión y checklist: sin cambios.

## 11. Datos crudos de evidencia a entregar

(a) suite completa con commit y conteo; (b) los cinco grupos `test_ut_cnt_05_`–`test_ut_cnt_09_` solos; (c) goldens: ninguno; (d) tests nuevos con IDs y AC; (e) `git diff --check` y `git diff --stat integration/i2-content...HEAD`; (f) riesgos, decisiones (p. ej. tratamiento de un `[.]` dentro de una URL con esquema) y pendientes; (g) cobertura: salida completa de `coverage report` y de `coverage report --include=src/mailquery/output.py --fail-under=85`, con el valor de `output.py` en la línea base del lote, sus líneas sin cubrir y la justificación de cada pragma nuevo. Más los bloques de la sección 9.

## 12. Definition of Done

- [x] Detección, dominios, modos, punycode, acortado, conteos, A6 y textos según RF-54–RF-61.
- [x] `neutralize` idempotente; todas las funciones deterministas.
- [x] UT-CNT-05–UT-CNT-09 verdes solos.
- [x] Suite completa sin fallos nuevos frente a la línea base del lote.
- [x] Cobertura (D-21): total ≥ 85 %; `python -B -m coverage report --include=src/mailquery/output.py --fail-under=85` verde; salida en la evidencia (g).
- [x] Informe final con los datos de la sección 11 y los bloques.

## 13. Registro de progreso

| Fecha | Fase | Nota |
|---|---|---|
| 2026-11-14 | F1 | `UrlMatch`, `find_urls`, `url_domain` y `address_domain`: inicios (a)–(e) sin distinguir mayúsculas y con los inicios con esquema en ancho completo comparados por su forma NFKC, `data:` con tipo MIME, `www.` con letra o dígito, UNC y token completo con `[.]`; dominios con usuario, puerto y `[.]` leído como `.`; UT-CNT-05 (8 casos) verde solo. |
| 2026-11-14 | F2 | `URL_MODES`, `render_urls` en `keep`/`neutralize`/`strip`, ACE con el códec `punycode` sobre la etiqueta en minúsculas, neutralización de esquemas (también en ancho completo y de los ya neutralizados) y acortado a 256 caracteres con el conteo sobre la URL neutralizada; UT-CNT-06 (7 casos) y UT-CNT-07 (7 casos) verdes solos. |
| 2026-11-14 | F3 | `UrlSignals`, `count_url_signals` (externos, script, largos y dominios no ASCII de URL y dirección), los siete textos `W_*` y `content_warnings` en el orden de los warnings; UT-CNT-08 (6 casos) verde solo. |
| 2026-11-14 | F4 | `sender_auth_failure` (despliegue de líneas, comentarios, `spf`/`dkim`/`dmarc`, varias firmas DKIM y resultados desconocidos) y `reply_to_mismatch` con `email.utils.getaddresses`; UT-CNT-09 (9 casos) verde solo. |
| 2026-11-14 | F5 | Suite completa `Ran 1172`, `FAILED (failures=2, skipped=7)` (los 2 fallos de p95 de SMOKE-NEW.07 de la línea base); `output.py` 99,5 %; sin goldens; sin pragmas nuevos; evidencia y bloques entregados al orquestador. |

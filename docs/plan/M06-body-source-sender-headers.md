# M06 — Cuerpo desde el HTML y cabeceras del remitente en los backends

**Lote:** I2 · rama del lote `integration/i2-content` · **Oleada:** W2 (en paralelo con M05 y M07)
**Rama:** `feature/m06-body-source-sender-headers`, creada desde la punta de `integration/i2-content` · **Worktree:** `../mailquery-wt/m06`
**Estado:** ⚪ (leyenda y protocolo en [`00-master-plan.md`](00-master-plan.md))

## 1. Objetivo

Que los backends nativos tomen el cuerpo del HTML cuando existe (RF-53; G-05), con la omisión y el conteo del contenido oculto de M03, y que entreguen la primera `Authentication-Results` y `Reply-To` (RF-60, RF-61), también sin leer el cuerpo (RNF-23, para F3). La emisión de warnings la hace M08; la selección de campos, M10.

## 2. Alcance

**Dentro:**

1. **Apple Mail (`src/mailquery/emlx.py`, `src/mailquery/backends/apple_mail.py`):**
   - `_extract_body_text`: si el mensaje tiene partes `text/html` de cuerpo (no adjuntos), el cuerpo es la unión con `"\n"` de los textos no vacíos de `output.html_body_to_text` de cada parte y `hidden_chars` la suma de sus conteos; si ninguna da texto, cuerpo `""` con `W_HTML_NO_TEXT` **sin recurrir al texto plano**; sin partes HTML, el texto plano como hoy. Aplica a todo el cuerpo sin analizar la estructura MIME (riesgo aceptado del PRD para `multipart/mixed`).
   - `EmlxMessage` añade `hidden_chars: int` (0 por defecto), `authentication_results: str | None` (valor crudo de la **primera** `Authentication-Results`, la de más arriba) y `reply_to: str | None`.
   - Nueva función `parse_emlx_headers(path) -> EmlxHeaders` que lee solo el bloque de cabeceras del mensaje (tras la línea de longitud del contenedor, hasta la primera línea vacía, con un tope de lectura de 256 KiB) y devuelve las seis cabeceras de `show` (`HEADER_NAMES`), la primera `Authentication-Results` y `Reply-To`; nunca lanza (archivo ilegible ⇒ vacío y `read=False`).
   - `AppleMailBackend.load_body` propaga `hidden_chars`, `authentication_results` y `reply_to` (Apple Mail no tiene `load_snippet`: `search._body_fields` usa `load_body`).
   - `parse_emlx_headers` y la lectura de cabeceras del cuerpo despliegan las líneas de continuación (CRLF o LF seguido de espacio o tabulador) antes de entregar el valor.
   - Hook interno nuevo `AppleMailBackend.load_headers(row) -> HeaderRow` (D-06): resuelve el `.emlx` de la carpeta física como hoy hace `load_body` y llama a `parse_emlx_headers`; no lee el cuerpo.
2. **Outlook (`src/mailquery/backends/outlook.py`, `src/mailquery/backends/outlook_com.py`):**
   - `BodyFormat` entra en la lista blanca de propiedades de solo lectura de `outlook_com.py` (junto a `Body` y `HTMLBody`).
   - `_item_text`: si `item.BodyFormat == 2` (`olFormatHTML`), el cuerpo es `output.html_body_to_text(item.HTMLBody)` (texto y `hidden_chars`); si el HTML no da texto, `""` con `W_HTML_NO_TEXT` aunque haya `Body`; si `BodyFormat` no es HTML, o `HTMLBody`/`BodyFormat` no existen en el item (reunión: `AttributeError`), el texto plano `Body` como hoy.
   - `_load_body` lee `PR_TRANSPORT_MESSAGE_HEADERS` también con `details=False` (para `search`/`new`) y de su análisis (con las líneas de continuación desplegadas) toma la primera `Authentication-Results` y `Reply-To`; sin cabeceras de transporte (correo interno), `None`. Un item S/MIME no se abre (como hoy).
   - Un error COM al leer `HTMLBody` o `BodyFormat` (distinto de `AttributeError`), o `BodyFormat` igual a `None`, se trata como "no HTML": el cuerpo es `Body` como hoy.
   - Hook interno nuevo `OutlookBackend.load_headers(row) -> HeaderRow`: S/MIME ⇒ no abre el item y devuelve vacío; si no, abre el item (cuenta en `items_opened`), lee solo `PR_TRANSPORT_MESSAGE_HEADERS` y devuelve las seis cabeceras, la primera `Authentication-Results` y `Reply-To`. No lee `Body`, `HTMLBody` ni adjuntos. Si `GetItemFromID` falla o la lectura de la propiedad lanza, devuelve vacío con `read=False`, sin excepción.
3. **Contrato interno (`src/mailquery/backends/base.py`):** `BodyRow` admite las claves opcionales `hidden_chars`, `authentication_results` y `reply_to`; nuevo `HeaderRow` (`TypedDict`: `headers`, `authentication_results`, `reply_to`, `read`). El núcleo lee estas claves con `.get`: un plugin no las entrega y `plugin_api = 1` no cambia (la validación del cuerpo de un plugin en `plugins/api.py` no se toca).
4. **`src/mailquery/plugins/api.py`:** `load_headers` se añade a `METADATA_OPERATIONS` para que el proxy de drivers lo envuelva igual que `load_snippet` (en un driver nativo la llamada sigue en línea).
5. **Dobles y fixtures:**
   - `tests/fakes/outlook.py`: el item admite `body_format` (por defecto `2` si tiene HTML y `1` si no) y cabeceras de transporte por item si hoy no se pueden fijar; `BodyFormat` se registra en el `CallLog` como las demás propiedades.
   - `tests/fixtures/make_fixtures.py`: `FixtureMessage` admite cabeceras extra (`extra_headers`) y un modo opcional para añadir mensajes de muestra de F1 (HTML y texto plano distintos, HTML oculto, cabeceras de autenticación) **sin cambiar el store por defecto**, para que los goldens no cambien.
6. **Simulación de la ausencia de `css-inline`:** UT-BOD-05.03 parchea la variable de módulo que define M03 en `output.py` (`output._css_inline`, con su centinela de "no intentado"); M06 no toca `output.py`.

**Fuera:** aplicar A2/A4 o emitir `W_HIDDEN_CONTENT`, `W_SENDER_AUTH_FAILED`, `W_REPLY_TO_MISMATCH` (M08); decidir cuándo leer el cuerpo o solo las cabeceras (M10); la documentación de usuario del cambio de cuerpo (la escribe M08, mismo lote, en "Body and warnings" de los README).

## 3. Dependencias y ACs

- **Entrada:** M03 (`html_body_to_text`).
- **Salida:** M08 (warnings), M10 (`load_headers` para la fila mínima y `show --fields`).
- **ACs:** AC-H04 (cuerpo desde HTML en Apple Mail y Outlook, `--text` sobre el HTML, HTML sin texto), AC-H11 (lectura de la primera `Authentication-Results` y de `Reply-To`; correo interno de Outlook sin cabeceras), AC-H17 (`search`, `new` y `show` funcionan sin `css-inline`).

## 4. Archivos

| Acción | Archivo |
|---|---|
| Modifica | `src/mailquery/emlx.py`, `src/mailquery/backends/apple_mail.py`, `src/mailquery/backends/outlook.py`, `src/mailquery/backends/outlook_com.py`, `src/mailquery/backends/base.py`, `src/mailquery/plugins/api.py` |
| Modifica | `tests/fakes/outlook.py`, `tests/fixtures/make_fixtures.py` |
| Crea | `tests/test_body_sources.py` |
| Modifica si los cambios los rompen | `tests/test_emlx.py`, `tests/test_outlook.py`, `tests/test_backends.py`, `tests/test_search.py`, `tests/test_plugins.py` |
| Bloques para el orquestador | `docs/TEST-CATALOG.md` (secciones 2, 4, 7, 8), `docs/INTERFACES.md` (`base.py`, `emlx.py`, `backends/apple_mail.py`, `backends/outlook.py`, `backends/outlook_com.py`, `plugins/api.py`, contrato de plugins: cuerpo) |

No toca `src/mailquery/output.py`, `tests/test_content.py` ni `tests/fixtures/content_samples.py` (son de M05 en esta oleada): si necesita muestras, las define en su propio archivo de tests.

## 5. Refactorizaciones previas

Ninguna.

## 6. Fases

| Fase | Tareas | Estado |
|---|---|---|
| F1 — Contrato interno | `BodyRow` opcional, `HeaderRow`, `load_headers` en `METADATA_OPERATIONS` | ⚪ |
| F2 — Apple Mail | HTML primero, `hidden_chars`, cabeceras A6, `parse_emlx_headers`, `load_headers`; fixtures opcionales; UT-BOD-01, UT-BOD-03 | ⚪ |
| F3 — Outlook | `BodyFormat` en la lista blanca, HTML primero, cabeceras A6 en `load_snippet`/`load_body`, `load_headers`; doble; UT-BOD-02, UT-BOD-04 | ⚪ |
| F4 — Punta a punta | UT-BOD-05 por `cli.main` | ⚪ |
| F5 — Cierre | Suite completa, tests existentes ajustados, evidencia cruda, bloques | ⚪ |

## 7. Tests

Archivo `tests/test_body_sources.py`, prefijo nuevo **UT-BOD** ("Origen del cuerpo y cabeceras del remitente").

**UT-BOD-01 — Cuerpo en Apple Mail**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `multipart/alternative` con texto plano e HTML distintos (ejemplo A3 de PRD-v2.2 sección 8) → `body_text` del HTML (`Factura adjunta.`). |
| .02 | P | Solo texto plano → texto plano. |
| .03 | N | HTML sin texto (solo `<img>`) con texto plano presente → `""` y `W_HTML_NO_TEXT`; el texto plano no aparece. |
| .04 | P | `multipart/mixed` con una parte `text/plain` y otra `text/html` de cuerpo → solo el HTML. |
| .05 | P | HTML con un elemento oculto → `hidden_chars` igual al de `html_body_to_text`; HTML todo oculto → `""`, `W_HTML_NO_TEXT` y `hidden_chars > 0`. |
| .06 | N | `text/plain` de cuerpo más una parte `text/html` con `Content-Disposition: attachment` → `body_text` del texto plano; el HTML adjunto no aporta texto. |

**UT-BOD-02 — Cuerpo en Outlook (doble)**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `BodyFormat = 2` con `Body` y `HTMLBody` distintos → texto del HTML. |
| .02 | P | `BodyFormat = 1` (y `3`, RTF) → `Body`. |
| .03 | P | Item de reunión sin `HTMLBody` → `Body`, sin error. |
| .04 | N | `BodyFormat = 2` con HTML sin texto y `Body` presente → `""` y `W_HTML_NO_TEXT`. |
| .05 | B | `BodyFormat` se lee por la lista blanca COM (sin violación del proxy de solo lectura) y no se abre ningún item más que hoy (`items_opened` igual). |
| .06 | N | `HTMLBody` que lanza un error COM (no `AttributeError`) y `BodyFormat` que devuelve `None` → `Body`, sin error. |

**UT-BOD-03 — Cabeceras del remitente en Apple Mail**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Con dos `Authentication-Results` y una `ARC-Authentication-Results`, `authentication_results` es la primera (la de más arriba). |
| .02 | P | `Reply-To` se entrega crudo; sin la cabecera, `None`. |
| .03 | P | `load_headers` da las seis cabeceras de `show`, la primera `Authentication-Results` y `Reply-To` sin llamar a la extracción del cuerpo (espía sobre `emlx._extract_body_text`). |
| .04 | B | `parse_emlx_headers` no lee más allá del bloque de cabeceras (archivo con cuerpo de varios MiB: se leen como mucho 256 KiB); archivo ausente o ilegible → vacío, `read=False`, sin excepción. |
| .05 | P | Primera `Authentication-Results` plegada con CRLF + tabulador y con `dmarc=fail` en una línea de continuación → el valor llega desplegado y contiene `dmarc=fail` (en `load_body` y en `load_headers`). |
| .06 | B | `parse_emlx_headers`: bloque sin línea vacía antes del tope de 256 KiB (devuelve lo leído hasta el tope, sin excepción), línea de longitud del contenedor inválida (vacío, `read=False`) y cabeceras con *encoded words* (se decodifican como en `parse_emlx`). |
| .07 | N | `load_headers` con un `.emlx` que no se resuelve → vacío y `read=False`; con un `.partial.emlx` → cabeceras leídas del parcial. |

**UT-BOD-04 — Cabeceras del remitente en Outlook (doble)**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Cabeceras de transporte con dos `Authentication-Results` y `Reply-To` → la primera y `Reply-To`, tanto en `load_body` como en `load_snippet`. |
| .02 | N | Correo interno sin cabeceras de transporte → `None` en las dos. |
| .03 | N | Item S/MIME: `load_headers` y `load_snippet` no abren el item (`CallLog` sin `GetItemFromID` para ese uid) y devuelven vacío. |
| .04 | P | `load_headers` abre el item (cuenta en `items_opened`) y no accede a `Body`, `HTMLBody` ni `Attachments`. |
| .05 | P | Cabeceras de transporte con la primera `Authentication-Results` plegada (CRLF + tabulador) y `dmarc=fail` en la línea de continuación → valor desplegado con `dmarc=fail`. |
| .06 | N | `load_headers` con `GetItemFromID` que falla, o con la lectura de `PR_TRANSPORT_MESSAGE_HEADERS` que lanza → vacío y `read=False`, sin excepción. |

**UT-BOD-05 — Punta a punta por `cli.main`**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `search --text <palabra solo del HTML> --since …` encuentra el mensaje; `--text <palabra solo del texto plano>` no lo encuentra (Apple Mail y Outlook). |
| .02 | P | `show` del mismo mensaje da `body_text` del HTML (Apple Mail y Outlook). |
| .03 | P | Con `css_inline` simulado ausente (parcheando `output._css_inline`, sección 2, punto 6), `search`, `new` y `show` terminan con exit 0 y convierten el HTML original (la omisión en línea sigue). |

Comandos:

```bash
python -B -m unittest discover -s tests -t . -k test_ut_bod_
python -B -m unittest tests.test_body_sources -v
python -B -m coverage erase
python -B -m coverage run -m unittest discover -s tests -t .
python -B -m coverage report --include="src/mailquery/emlx.py,src/mailquery/backends/apple_mail.py,src/mailquery/backends/outlook.py,src/mailquery/backends/outlook_com.py,src/mailquery/backends/base.py,src/mailquery/plugins/api.py" --fail-under=85
```

`backends/outlook_com.py` ya está por debajo del 85 % en la línea base (79,9 % en `cf164ff`): se aplica D-21 (c), sin bajar de la línea base del lote y con las líneas nuevas (`BodyFormat` en la lista blanca) cubiertas. `emlx.py` (ramas 81,4 %) y `apple_mail.py` no pueden quedar por debajo del 85 % combinado; UT-BOD-03.05–.07, UT-BOD-02.06 y UT-BOD-04.05–.06 cubren sus ramas nuevas.

## 8. Tests existentes afectados (previsibles)

- `tests/test_emlx.py`: casos que esperaban el texto plano cuando hay HTML. `test_parse_multipart_with_attachment_2714` sigue verde (las dos partes tienen el mismo texto), pero su comentario `# text/plain wins over the HTML alternative.` pasa a ser falso: se reescribe para describir que el cuerpo sale de la parte HTML.
- `tests/test_outlook.py`: OL-20 (cuerpo: hoy `Body` primero y `HTMLBody` si está vacío) y los casos que comparan el `CallLog` de `load_snippet`/`search`/`show` (nuevas lecturas de `BodyFormat` y de las cabeceras de transporte en `search`/`new`).
- `tests/test_search.py`: casos de cuerpo solo HTML o HTML sin texto, si su expectativa cambia.
- `tests/test_plugins.py`: casos que fijan el conjunto exacto de `METADATA_OPERATIONS`.
- Si un caso nuevo verificaría exactamente el mismo comportamiento que un caso heredado, se actualiza el heredado y no se crea el nuevo.
- Goldens: no deberían cambiar (los fixtures por defecto tienen el mismo texto en las partes plana y HTML, y el doble de Outlook igual). En W2 los goldens son de M07: si alguno cambia por este milestone, el subagente se detiene y lo devuelve al orquestador, que decide si M06 y M07 pasan a ejecutarse en secuencia.

Cada test ajustado se lista en la evidencia con el motivo.

## 9. Documentación

- Bloques para `INTERFACES.md`: `BodyRow` (claves opcionales) y `HeaderRow` en `base.py`; hook `load_headers` (nativos, opcional, buscado con `getattr`); `emlx.parse_emlx_headers` y prioridad del HTML; `BodyFormat` en la lista blanca COM; `load_headers` en `METADATA_OPERATIONS`; contrato de plugins: "el plugin entrega en `body_text` el texto que ve el destinatario, desde el HTML cuando existe y sin contenido oculto; el núcleo aplica A2, A4 y A5, no A3".
- Bloques para `TEST-CATALOG.md`: sección 2, prefijo `UT-BOD` → `tests/test_body_sources.py`; sección 4, nuevas capacidades del doble de Outlook y de `make_fixtures.py`; sección 8, UT-BOD-01–UT-BOD-05 y los casos existentes modificados; sección 7, filas parciales de AC-H04, AC-H11, AC-H17.
- README y skill: los actualiza M08 (sección "Body and warnings"); recetas y ayudas: sin cambios.

## 10. Actualizaciones de `PRD-v2.2.md` (las escribe el orquestador)

- Registro de conciliación: "Selección del cuerpo y conversión HTML → texto (F1)" → `Implementado` (documentos: pendiente de M08); "Cabeceras leídas (F1)" → `Implementado` (warnings pendientes); "Contrato de plugins: cuerpo (F1)" → `Implementado y documentado` (`INTERFACES.md`); "Responsabilidades de módulos (F1, F2, F3)" → nota del hook `load_headers` (A-08).
- Tabla de supersesión y checklist: sin cambios.

## 11. Datos crudos de evidencia a entregar

(a) suite completa con commit y conteo; (b) grupo `test_ut_bod_` solo; (c) goldens tocados (esperado: ninguno) y su justificación; (d) tests nuevos y existentes modificados con IDs y AC; (e) `git diff --check` y `git diff --stat integration/i2-content...HEAD`; (f) riesgos (coste de las lecturas de cabeceras en Outlook, RK-08), decisiones y pendientes; (g) cobertura: salida de `coverage report` completa y de la orden con `--include` de la sección 7, con los valores de la línea base del lote de esos módulos. Más los bloques de la sección 9.

## 12. Definition of Done

- [ ] Apple Mail y Outlook toman el cuerpo del HTML cuando existe, sin recurrir al texto plano si el HTML no da texto.
- [ ] `hidden_chars`, `authentication_results` y `reply_to` llegan en `BodyRow`; `load_headers` entrega cabeceras sin leer el cuerpo; S/MIME no se abre.
- [ ] `BodyFormat` en la lista blanca COM; el doble lo modela.
- [ ] Store por defecto y goldens sin cambios (o cambios justificados).
- [ ] UT-BOD-01–UT-BOD-05 verdes solos; tests existentes ajustados y listados.
- [ ] Suite completa sin fallos nuevos frente a la línea base del lote.
- [ ] Cobertura (D-21): total ≥ 85 %; `python -B -m coverage report --include=<archivos de src/ de la sección 4> --fail-under=85` verde o, para un módulo por debajo del 85 % en la línea base del lote, sin bajar de ese valor y con las líneas nuevas cubiertas; salida en la evidencia (g).
- [ ] Informe final con los datos de la sección 11 y los bloques.

## 13. Registro de progreso

| Fecha | Fase | Nota |
|---|---|---|
| — | — | — |

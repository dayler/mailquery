# M10 — Fila mínima, `--fields` y warnings según lo entregado

**Lote:** I3 · rama del lote `integration/i3-attachments-rows` · **Oleada:** W5 (sola)
**Rama:** `feature/m10-default-row-fields`, creada desde la punta de `integration/i3-attachments-rows` (con M09 integrado) · **Worktree:** `../mailquery-wt/m10`
**Estado:** 🟡 (fases F1–F7 cerradas; pendiente de integración) (leyenda y protocolo en [`00-master-plan.md`](00-master-plan.md))

## 1. Objetivo

Que `search` y `new` devuelvan por defecto la fila mínima de seis campos sin leer cuerpos (RF-69, RNF-23), que `--fields` añada campos en `search`/`new` (RF-70) y elija campos en `show` (RF-71), y que los warnings sigan lo que se entrega (RF-74 reglas 1–3). Incluye la documentación de RF-75 que corresponde a la fila y a `--fields`, y el punto 16 de las reglas de seguridad de la skill.

## 2. Alcance

**Dentro:**

1. **Opción (`src/mailquery/cli.py`):** `--fields` (`action="append"`, `metavar="LIST"`) en `search`, `new` y `show`; cada valor se parte por comas, se quitan los espacios alrededor de cada nombre y los nombres se comparan distinguiendo mayúsculas (D-24: `--fields "to, uid"` es válido; `--fields ALL` es un campo desconocido). Se valida en `_main` **antes de crear `~/.mailquery` y de abrir el store** (PRD-v2.2 sección 10, punto 12), igual que hoy la selección de `attachment`. Nombre desconocido o vacío ⇒ `E_USAGE` (exit 2), mensaje `unknown field '<nombre>' in --fields`, hint `valid fields: <lista del comando>`:
   - `search`/`new`: `uid, message_id, duplicate_count, subject, from, to, cc, date_sent, date_received, mailbox, is_read, is_flagged, has_attachments, size_bytes, snippet, body, all`;
   - `show`: `uid, message_id, subject, from, to, cc, date_sent, date_received, mailbox, is_read, is_flagged, has_attachments, size_bytes, headers, body_text, body_truncated, attachments, partial, readable, source, all`.
   Help de la opción y notas en los epílogos con esas listas; en `search`/`new` "adds fields to the default row (uid, subject, from, date_received, is_read, has_attachments)", en `show` "selects the fields of message (uid is always included)".
2. **Fila de `search`/`new` (`src/mailquery/search.py`, sobre el constructor de M02):**
   - `DEFAULT_ROW_FIELDS = ("uid", "subject", "from", "date_received", "is_read", "has_attachments")`; campos entregados = por defecto ∪ pedidos (`all` = `SEARCH_ROW_FIELDS`), siempre en el orden de `SEARCH_ROW_FIELDS`; los valores son los de hoy.
   - El cuerpo se lee solo si se entrega `snippet` o `body`, o si `--text` lo necesita para filtrar (en ese caso se reutiliza el texto ya leído, como hoy). Los destinatarios se leen solo si se entregan `to`/`cc` o los exige un filtro. `mailbox` y `duplicate_count` se siguen calculando (dedupe) aunque no se entreguen.
   - **Cabeceras de A6 de cada mensaje devuelto (RNF-23):** si el cuerpo se leyó, del `BodyRow`; si no, del hook `load_headers(row)` de M06 cuando el driver lo tiene (nativos; un plugin no). Estas lecturas cuentan en `scan.messages_read` (Apple Mail: una lectura por cabecera leída con `read=True`; Outlook: por `items_opened`).
   - `new`: el cursor avanza igual con cualquier `--fields` (sección 10, punto 15).
3. **`show --fields` (RF-71):** campos entregados = `uid` ∪ pedidos (`all` = `SHOW_FIELDS`; sin `--fields`, todos, como hoy), en el orden de `SHOW_FIELDS`. El cuerpo (`load_body`) solo se lee si se pide `body_text`, `body_truncated`, `partial`, `readable`, `source` o `attachments` (con `attachments`, solo para aplicar las reglas de S/MIME y de cuerpo ilegible, sin entregarlo). Los adjuntos solo se consultan si se pide `attachments`. `headers` sin campos de cuerpo se obtiene con `load_headers` (nativos) o se sintetiza como hoy (plugins). Las cabeceras de A6 salen del cuerpo o de `load_headers`.
4. **Warnings según lo entregado (RF-74, reglas 1–3):**
   - conteos de `W_EXTERNAL_LINKS`, `W_NON_ASCII_DOMAIN`, `W_LONG_URL`, `W_SCRIPT_LINK` solo sobre los campos entregados: `subject` y `from.name`/`from.address` si se entregan (en la fila por defecto, sí), `to`/`cc` solo si se entregan, el cuerpo completo solo si se entrega cuerpo (`snippet`/`body` en `search`/`new`; `body_text`, `body_truncated`, `partial`, `readable` o `source` en `show`);
   - `W_HIDDEN_CONTENT` y los warnings del estado del cuerpo (`W_BODY_TRUNCATED`, `W_HTML_NO_TEXT`, `W_BODY_UNREADABLE`, `W_EMLX_MISSING`, `W_EMLX_CORRUPT`, `W_BODY_NOT_LOCAL`) solo si se entrega cuerpo; con `--text` sin `snippet`/`body`, los warnings de cuerpo del escaneo no se emiten; `W_ATTACHMENTS_UNAVAILABLE` solo si `show` entrega `attachments`;
   - `W_SENDER_AUTH_FAILED` y `W_REPLY_TO_MISMATCH` siempre que el mensaje los justifica.
   El procesamiento de A2/A4 (sección 10, puntos 3 y 4 del PRD) solo se aplica a los campos entregados.
5. **Documentación:** sección 9.

**Fuera:** `--group-by`, `--count`, `hint` de RF-78 y la regla 4 de RF-74 (M11); `mailboxes --fields` (M12).

## 3. Dependencias y ACs

- **Entrada:** M02 (constantes y constructor), M06 (`load_headers`), M08 (warnings de F1), M09 (orden de archivos).
- **Salida:** M11 (agrupa y cuenta sobre esta fila), M12 (reutiliza el parser de `--fields`).
- **ACs:** AC-O01 (fila por defecto y lecturas sin `--text`), AC-O02, AC-O03, AC-O08 (`new --fields`), AC-O09 (reglas 1–3), AC-O10 (parte de `--fields`), AC-H14 (con `--fields all`), AC-H18 (punto 16 de la skill).

## 4. Archivos

| Acción | Archivo |
|---|---|
| Modifica | `src/mailquery/search.py`, `src/mailquery/cli.py` |
| Modifica | Goldens de filas: `tests/fixtures/expected/{search_default,search_all_mail,search_multidriver,new_first_run,new_seeded,new_multidriver}.json`, `tests/fixtures/expected/outlook/{search,new_first_run}.json` |
| Crea | `tests/test_fields.py` |
| Modifica (expectativas de fila, `snippet` y warnings de cuerpo) | `tests/test_search.py`, `tests/test_cli.py`, `tests/test_multidriver.py`, `tests/test_outlook.py`, `tests/test_integration.py`, `tests/test_plugins.py`, `tests/test_uid.py`, `tests/test_state.py`, `tests/test_emlx.py`, `tests/test_backends.py` (solo los que fallen) |
| Modifica (sección 8) | `tests/test_content_wiring.py` (las invocaciones de `search`/`new` de UT-CW-01, UT-CW-07, UT-CW-08, UT-CW-10 y UT-CW-12 añaden `--fields all`, sin quitar aserciones), `tests/test_smoke.py` (`_check_list_shape` de SMOKE-NEW.02/.03/.04), `tests/test_readonly.py` (invocaciones y barrido de TC-03.01) |
| Modifica si hace falta | `tests/fakes/outlook.py`, `tests/fixtures/make_fixtures.py`, `tests/fakes/plugin.py`, `tests/fakes/attachment_backend.py` (espías de lectura) |
| Modifica | `README.md`, `README.es.md`, `skills/mailquery/SKILL.md`, `docs/recipes/01-new-mail-digest.md`, `docs/recipes/02-search-invoices.md` |
| Bloques para el orquestador | `docs/TEST-CATALOG.md` (secciones 2, 3, 7, 8), `docs/INTERFACES.md` (`cli.py`, `search.py`, sección 4 "Mensaje") |

## 5. Refactorizaciones previas

Usa R-01 (M02).

## 6. Fases

| Fase | Tareas | Estado |
|---|---|---|
| F1 — Opción | Parser y validación temprana de `--fields`; ayudas; UT-FLD-03 (errores) | 🟢 |
| F2 — Fila por defecto | Selección de campos, lecturas condicionadas, `load_headers` para A6; UT-FLD-01, UT-FLD-02, UT-FLD-03, UT-FLD-06 | 🟢 |
| F3 — `show --fields` | UT-FLD-04 | 🟢 |
| F4 — Warnings | RF-74 reglas 1–3; UT-FLD-05 | 🟢 |
| F5 — Tests y goldens existentes | Ajuste de expectativas y goldens; UT-FLD-07 | 🟢 |
| F6 — Documentación | Sección 9; DOC-10 | 🟢 |
| F7 — Cierre | Suite completa, evidencia cruda, bloques | 🟢 |

## 7. Tests

Archivo `tests/test_fields.py`, prefijo nuevo **UT-FLD** ("Fila por defecto y `--fields`").

**UT-FLD-01 — Fila por defecto**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Sin `--fields`, cada fila de `search` y `new` tiene exactamente `uid`, `subject`, `from`, `date_received`, `is_read`, `has_attachments`, en ese orden, con los mismos valores que la fila completa (store sintético y doble de Outlook). |
| .02 | P | Los campos fuera de `messages[]` son los de antes más `content_notice`; `hint`, `scan` y, en `new`, `cursor` no cambian. |

**UT-FLD-02 — Sin lectura de cuerpos**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Apple Mail: sin `--text`, `search` y `new` no llaman a la extracción del cuerpo (espía sobre `emlx._extract_body_text`) y leen las cabeceras de cada mensaje devuelto; `scan.messages_read` = número de mensajes devueltos. |
| .02 | P | Outlook (doble): sin `--text`, el `CallLog` no tiene accesos a `Body`, `HTMLBody` ni `BodyFormat`; `items_opened` = mensajes devueltos (cabeceras de A6); un item S/MIME no se abre. |
| .03 | P | Con `--text`, el cuerpo se lee para filtrar como hoy, pero sin `--fields snippet` la fila no lleva `snippet` ni `body`. |
| .04 | P | Plugin falso con espías: con la fila por defecto, `search` y `new` no llaman a `load_snippet` ni a `load_body`; el plugin no tiene `load_headers` y no se calculan las señales del remitente. |
| .05 | B | Apple Mail, mensaje cuyo `.emlx` no existe: `load_headers` no lee (`read=False`), el mensaje no cuenta en `scan.messages_read` y su fila sale sin warnings del remitente ni del cuerpo. |
| .06 | P | `--to` como filtro sin `--fields to`: filtra por destinatarios (los lee) y la fila no lleva `to` ni `cc`; las URLs de los nombres de destinatarios no se cuentan. |

**UT-FLD-03 — `--fields` en `search` y `new`**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `--fields snippet` añade `snippet` al final de la fila por defecto. |
| .02 | P | `--fields all` da la fila completa de `PRD.md` sección 12.5 (`SEARCH_ROW_FIELDS`). |
| .03 | P | `--fields to,uid` y `--fields uid --fields to` dan la fila por defecto más `to`, en el orden canónico. |
| .04 | N | `--fields remitente` ⇒ `E_USAGE`, exit 2, mensaje y hint literales del ejemplo de PRD-v2.2 sección 8; `--fields ""` y `--fields uid,,to` ⇒ ídem con `''`. |
| .05 | B | El error ocurre antes de crear el home (el `HOME` temporal no tiene `.mailquery`) y sin abrir el store. |
| .06 | B | D-24: `--fields "to, uid"` equivale a `--fields to,uid`; `--fields ALL` y `--fields Snippet` ⇒ `E_USAGE` con `unknown field 'ALL'` / `unknown field 'Snippet'`; `--fields " "` ⇒ ídem con `''`. |

**UT-FLD-04 — `show --fields`**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `--fields attachments` → `message` con solo `uid` y `attachments`; ningún warning de cuerpo; en un mensaje S/MIME, `attachments: []` (se lee el cuerpo para aplicar la regla, sin entregarlo). |
| .02 | P | `--fields body_text` → no consulta los adjuntos (`attachments()` y `attachment_names()` del backend no se llaman). |
| .03 | P | `--fields headers` → `uid` y `headers` sin leer el cuerpo (Apple Mail con `load_headers`; Outlook sin `Body`/`HTMLBody`). |
| .04 | P | Sin `--fields` → los mismos campos y valores que antes más `content_notice`. |
| .05 | N | Campo desconocido ⇒ `E_USAGE` con la lista de `show`. |
| .06 | P | `--fields source` y `--fields partial`, cada uno solo: leen el cuerpo, entregan `uid` y ese campo, y emiten los warnings del cuerpo (cuerpo entregado según RF-74). |

**UT-FLD-05 — Warnings según lo entregado**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Mensaje con texto oculto y URLs en el cuerpo: `W_HIDDEN_CONTENT` y el conteo de las URLs del cuerpo solo con `--fields snippet`, `body` o `all` en `search`/`new`, y con `body_text` (o `body_truncated`, `partial`, `readable`, `source`) en `show`. |
| .02 | P | URL en el asunto: contada con la fila por defecto; URL en el nombre de un destinatario: contada solo con `--fields to`. |
| .03 | P | `W_SENDER_AUTH_FAILED` y `W_REPLY_TO_MISMATCH` aparecen con y sin `--fields`, también con `show --fields attachments`. |
| .04 | N | `W_BODY_UNREADABLE`, `W_EMLX_MISSING` (Apple Mail) y `W_BODY_NOT_LOCAL` (Outlook) solo con cuerpo entregado; con `--text` sin `snippet` no aparecen. |
| .05 | N | `W_ATTACHMENTS_UNAVAILABLE` solo si `show` entrega `attachments`. |

**UT-FLD-06 — `new --fields`**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `new --fields snippet` añade `snippet`. |
| .02 | B | El `state.json` tras `new --fields snippet` es igual al de `new` sin `--fields` sobre el mismo store (cursor y anillo). |

**UT-FLD-07 — Compatibilidad final de F1**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Con `--fields all` en `search`/`new` y sin `--fields` en `show`, están todos los campos existentes y la única clave nueva respecto de 2.0.x es `content_notice`. |

**DOC-10 — Documentación de la fila y de `--fields`** (nuevo) · `tests/test_fields.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `search --help`, `new --help` y `show --help` describen `--fields` con la lista de su comando. |
| .02 | P | Los dos README documentan la fila por defecto y `--fields` con ejemplos (`--fields snippet`, `--fields all`, `show <uid> --fields attachments`). |
| .03 | P | La skill explica la fila por defecto, `new --fields snippet` para resumir el correo nuevo, cuándo usar `new` y cuándo `search --unread`, y la regla de triaje sin contenido (punto 16). |
| .04 | P | `docs/recipes/01-new-mail-digest.md` usa `mailquery new --fields snippet`; ninguna receta consume un campo fuera de la fila por defecto sin pedirlo con `--fields`. |

Comandos:

```bash
python -B -m unittest discover -s tests -t . -k test_ut_fld_
python -B -m unittest discover -s tests -t . -k test_doc_10_
python -B -m unittest discover -s tests -t . -k test_tc_01_
python -B -m unittest discover -s tests -t . -k test_tc_02_
python -B -m unittest discover -s tests -t . -k test_tc_03_
python -B -m unittest discover -s tests -t . -k test_tc_04_
python -B -m unittest discover -s tests -t . -k test_tc_10_
python -B -m unittest discover -s tests -t . -k test_ut_cw_
python -B -m coverage erase
python -B -m coverage run -m unittest discover -s tests -t .
python -B -m coverage report
python -B -m coverage report --include="src/mailquery/search.py,src/mailquery/cli.py" --fail-under=85
```

## 8. Tests existentes afectados (previsibles)

Es el milestone con más expectativas afectadas (RK-01). Previsiblemente:

- Goldens de filas de TC-01, TC-02 y TC-10 (sección 4): las filas pasan a seis campos; `scan.messages_read` puede no cambiar (las cabeceras sustituyen al cuerpo como lectura).
- `tests/test_search.py`: casos UT-SR que leen `snippet`, `body`, `to`, `cc` o `mailbox` de las filas, o que esperan warnings de cuerpo en `search`/`new`.
- `tests/test_outlook.py`: OL-20, OL-24, OL-25, OL-28 y los que comparan el `CallLog` de `search`/`new`.
- `tests/test_multidriver.py`: UT-MD que leen campos fuera de la fila por defecto.
- `tests/test_integration.py`: TC-04 (recetas), TC-05 (paridad de forma).
- `tests/test_plugins.py`, `tests/test_uid.py`, `tests/test_state.py`: los que leen campos de las filas.

- `tests/test_content_wiring.py`: UT-CW-01, UT-CW-07, UT-CW-08, UT-CW-10 y UT-CW-12 (escritos por M07 y M08 con la fila completa) añaden `--fields all` a sus invocaciones de `search`/`new`, sin quitar aserciones.
- `tests/test_smoke.py`: `_check_list_shape` (SMOKE-NEW.02/.03/.04) valida la fila por defecto, y una segunda corrida con `--fields all` valida la fila completa.
- `tests/test_readonly.py`: TC-03.01 solo añade invocaciones; el barrido incluye `search --fields all`, `new --fields all` y `show <uid> --fields attachments`; OL-30 (`tests/test_outlook.py`) añade los mismos casos. Las aserciones de solo lectura (store sin cambios, escritura solo en `~/.mailquery`) no se tocan.

Reglas:

- Un test existente que verifica `snippet`, `body`, `to`, `cc`, `mailbox`, `duplicate_count`, `message_id` o warnings de cuerpo se ajusta añadiendo `--fields <campo>` (o `all`) a su invocación, nunca borrando la aserción; cada ajuste se lista en la evidencia.
- Goldens: el golden se compara con la corrida sin `--fields` (fila de seis campos); las aserciones de campos fuera de la fila y de warnings de cuerpo del mismo método pasan a una segunda corrida con `--fields all`. Afecta a TC-01.03, TC-01.04, TC-01.05, TC-01.06, TC-02.02, TC-02.06, TC-10.01 y TC-10.02, cuyo texto de `TEST-CATALOG.md` se actualiza en los bloques.
- La cobertura de `search.py` y `cli.py` no baja de la línea base del lote (D-21).

## 9. Documentación

- Ayudas de `search`, `new` y `show` (sección 2, punto 1).
- `README.md`, `README.es.md`: secciones de `search`, `new` y `show` con la fila por defecto, `--fields` (listas y ejemplos) y el ejemplo JSON de la fila mínima (ejemplo de PRD-v2.2 sección 8); "Body and warnings": los warnings del cuerpo solo salen cuando se entrega el cuerpo.
- `skills/mailquery/SKILL.md`: fila por defecto; `--fields snippet` (p. ej. `new --fields snippet` para resumir); cuándo `new` (procesar cada correo una vez) y cuándo `search --unread` (lo que la persona no ha leído); "Security rules", punto 16: triaje con la fila por defecto y pedir el cuerpo solo de los mensajes elegidos; los avisos del cuerpo solo salen con el cuerpo, los del remitente siempre.
- `docs/recipes/01-new-mail-digest.md`: `mailquery new --fields snippet` y sus "Campos JSON a consumir"; `docs/recipes/02-search-invoices.md`: `--fields` para cada campo que consuma fuera de la fila por defecto.
- Bloques para `INTERFACES.md`: `cli.py` (`--fields`, validación temprana), `search.py` (`DEFAULT_ROW_FIELDS`, lecturas condicionadas, `load_headers`), sección 4 "Mensaje (`search`/`new`)" y "`show`".
- Bloques para `TEST-CATALOG.md`: sección 2, prefijo `UT-FLD` → `tests/test_fields.py`; sección 3, goldens de filas mínimas; sección 8, UT-FLD-01–07, DOC-10 y casos existentes modificados (incluidos los textos de TC-01.03–.06, TC-02.02, TC-02.06, TC-10.01, TC-10.02, SMOKE-NEW.02–.04 y TC-03.01); sección 7, filas de AC-O01–AC-O03, AC-O08–AC-O10, AC-H14, AC-H18 (delta `PRD-v2.2.md`).

## 10. Actualizaciones de `PRD-v2.2.md` (las escribe el orquestador)

- Registro de conciliación: "Fila de `search` y `new`" (F3) y "Prompt injection" (F3) → `Implementado y documentado`; "Opciones de `search`, `new` y `show` y su ayuda" (F3) y "Warnings de `search`, `new` y `show`" (F3) → `Implementado y documentado` para `--fields` y las reglas 1–3 (faltan `--group-by`/`--count`); "Rendimiento" (F3) → `Implementado` (medición en M14); "Recetas, skill y README" (F3) → parte de `--fields`; "Skill y README" (F1) → punto 16 añadido. Nota con D-24 (formato de las listas de `--fields`), redactada sin citar el plan, en "Opciones de `search`, `new` y `show` y su ayuda" (F3).
- Checklist: CL-05 avanza (retirado "`snippet` en cada fila" en README, skill, recetas e `INTERFACES.md`).
- Tabla de supersesión: sin cambios.

## 11. Datos crudos de evidencia a entregar

(a) suite completa con commit y conteo; (b) grupos `test_ut_fld_`, `test_doc_10_`, `test_tc_01_`, `test_tc_02_`, `test_tc_03_`, `test_tc_04_`, `test_tc_10_` y `test_ut_cw_` solos (salidas de SMOKE según la regla de redacción de la regla 6 del plan maestro); (c) goldens modificados con su diff (filas a seis campos) y justificación; (d) tests nuevos y la lista completa de tests existentes ajustados con el motivo; (e) `git diff --check` y `git diff --stat integration/i3-attachments-rows...HEAD`; (f) riesgos, decisiones (p. ej. warnings del escaneo de `--text`) y pendientes; (g) cobertura: `coverage report` completo y de los módulos tocados, con la línea base del lote de esos módulos, las líneas sin cubrir y la justificación de cada pragma nuevo. Más los bloques de la sección 9.

## 12. Definition of Done

- [x] Fila por defecto de seis campos; `--fields` añade en `search`/`new` y elige en `show`; validación antes del home.
- [x] Sin cuerpo sin `snippet`/`body`/`--text`; cabeceras de A6 de los mensajes devueltos contadas en `scan.messages_read`.
- [x] Warnings según RF-74, reglas 1–3.
- [x] Goldens y tests existentes ajustados y listados, sin borrar aserciones (sección 8).
- [x] Ayudas, README, skill (incluido el punto 16) y recetas actualizados.
- [x] UT-FLD-01–07 y DOC-10 verdes solos.
- [x] Suite completa sin fallos nuevos frente a la línea base del lote.
- [x] Cobertura (D-21): total ≥ 85 %; `python -B -m coverage report --include=<archivos de src/ de la sección 4> --fail-under=85` verde o, para un módulo por debajo del 85 % en la línea base del lote, sin bajar de ese valor y con las líneas nuevas cubiertas; salida en la evidencia (g).
- [x] Informe final con los datos de la sección 11 y los bloques.

## 13. Registro de progreso

| Fecha | Fase | Nota |
|---|---|---|
| 2026-11-14 | F1 | `--fields` (`action=append`, lista separada por comas, espacios recortados, nombres con distinción de mayúsculas) en `search`, `new` y `show`; validación en `_main` antes de crear `~/.mailquery` y de abrir el store, con `unknown field '<nombre>' in --fields` y `valid fields: <lista del comando>`. UT-FLD-03.04–.06 verdes solos. |
| 2026-11-14 | F2 | `DEFAULT_ROW_FIELDS` de seis campos; campos entregados = por defecto ∪ pedidos (`all` = `SEARCH_ROW_FIELDS`) en el orden canónico; cuerpo solo con `snippet`/`body` o `--text`; destinatarios solo si se entregan; cabeceras A6 desde el `BodyRow` o desde `load_headers` contadas en `scan.messages_read`. UT-FLD-01, UT-FLD-02, UT-FLD-03 y UT-FLD-06 verdes solos. |
| 2026-11-14 | F3 | `show --fields`: `uid` siempre; cuerpo solo con `body_text`, `body_truncated`, `partial`, `readable`, `source` o `attachments`; adjuntos solo con `attachments`; `headers` sin cuerpo desde `load_headers` o sintetizadas. UT-FLD-04 verde solo. |
| 2026-11-14 | F4 | Warnings según RF-74 reglas 1–3: conteos de enlaces solo sobre campos entregados; warnings del estado del cuerpo y `W_HIDDEN_CONTENT` solo con cuerpo entregado; `W_ATTACHMENTS_UNAVAILABLE` solo con `attachments`; avisos del remitente siempre. UT-FLD-05 verde solo. |
| 2026-11-14 | F5 | UT-FLD-07 y expectativas heredadas ajustadas pidiendo los campos con `--fields`/`fields=("all",)`, sin borrar aserciones; 8 goldens de filas a seis campos actualizados y justificados; UT-CW, TC-01–TC-04, TC-10, OL-30 y TC-03 con las invocaciones nuevas. |
| 2026-11-14 | F6 | Ayudas y epílogos con las listas de campos; README/README.es con la fila por defecto, `--fields` y los warnings según lo entregado; skill con la fila, `new --fields snippet`, `new` frente a `search --unread` y la regla 16; recetas 01 (`mailquery new --fields snippet`) y 02 (`--fields` para cada campo consumido). DOC-10 verde solo. |
| 2026-11-14 | F7 | Suite completa `Ran 1323`, `FAILED (failures=2, skipped=7)` (los 2 fallos ambientales de la línea base: SMOKE-NEW.07 de `mailboxes` y `show`); cobertura total 90,7 % y módulos tocados `cli.py` 91,7 %, `search.py` 92,9 %; `git diff --check` limpio; evidencia y bloques en `.worktrees/reports/M10.md`. |

# M11 — `--group-by`, `--count` y `hint` de `search` sin resultados

**Lote:** I3 · rama del lote `integration/i3-attachments-rows` · **Oleada:** W6 (sola)
**Rama:** `feature/m11-group-by-count-hint`, creada desde la punta de `integration/i3-attachments-rows` (con M09 y M10 integrados) · **Worktree:** `../mailquery-wt/m11`
**Estado:** 🟡 (fases F1–F6 cerradas; pendiente de integración) (leyenda y protocolo en [`00-master-plan.md`](00-master-plan.md))

## 1. Objetivo

Añadir a `search` la agrupación con los últimos mensajes de cada grupo (RF-72) y el recuento sin filas (RF-73), con sus warnings (RF-74, reglas 4 y 5), y el `hint` de un `search` sin resultados con el alcance buscado (RF-78). Incluye la documentación de RF-75 de estas opciones.

## 2. Alcance

**Dentro:**

1. **Opciones (`src/mailquery/cli.py`, solo en `search`):**
   - `--group-by` (`action="append"`, `metavar="KEYS"`, partido por comas como `--fields` de M10: espacios alrededor de cada clave quitados y comparación distinguiendo mayúsculas, D-24): claves `from`, `domain`, `mailbox`, `account`, `day`, `week`, `month`, como mucho dos; una clave vacía (`--group-by ""`, `from,`) es la clave desconocida `''`.
   - `--count` (`store_true`).
   - Validación en `_main`, antes de crear el home y de abrir el store (PRD-v2.2 sección 10, punto 12), con `E_USAGE` (exit 2) y los textos literales de RF-72/RF-73:
     - más de dos claves → `--group-by accepts at most two keys`;
     - clave repetida → `duplicate key '<clave>' in --group-by`;
     - clave desconocida → `unknown key '<clave>' in --group-by`;
     - hint común: `valid keys: from, domain, mailbox, account, day, week, month; at most two`;
     - `--limit` fuera de 0–50 con `--group-by` → `invalid --limit <v> with --group-by: expected 0 to 50`, hint `use --limit between 0 and 50 messages per group`;
     - `--count` con `--fields`, `--group-by` o `--limit` → `--count cannot be combined with --fields, --group-by or --limit`, hint `use --count alone, or drop it to list the messages`.
   - `new` no define estas opciones: `new --group-by …` y `new --count` dan el `E_USAGE` de argparse (D-17) sin tocar el estado.
   - Help de las opciones y notas en el epílogo de `search`.
2. **Agrupación (`src/mailquery/search.py`), después de filtrar y deduplicar igual que hoy (sección 10, punto 13):**
   - Claves: `from` = dirección del remitente en minúsculas (sin dirección → `null`); `domain` = parte tras el último `@` (sin dirección o sin `@` → `null`); `mailbox` = `{"account": <etiqueta>, "path": <ruta>}` de la carpeta del mensaje canónico (sin etiqueta, el `uuid`); `account` = etiqueta de la cuenta (o `uuid`); `day` = `AAAA-MM-DD`, `week` = semana ISO 8601 `AAAA-Www`, `month` = `AAAA-MM`, sobre `date_received` en la zona local (`output.LOCAL_ZONE`); sin fecha → `null`.
   - Respuesta: `groups[]` en lugar de `messages[]`; cada grupo con sus claves en el orden pedido, `count` y `messages[]` (los más recientes del grupo, de más reciente a más antiguo, con la fila de M10, sin `from` si la clave es `from` ni `mailbox` si la clave es `mailbox`).
   - `--limit` = mensajes por grupo, 0–50, 5 por defecto; `search.default_limit` no aplica; con `0`, `messages: []`.
   - Orden: grupos sin ninguna clave `null` por su mensaje más reciente (desc), los grupos sin fechas después de los que tienen; a igualdad, por claves ascendentes (`mailbox` por cuenta y ruta); después, los grupos con alguna clave `null`, por claves ascendentes con `null` al final.
   - Como máximo 50 grupos: si hay más, `truncated: true`, `W_RESULTS_TRUNCATED: <n> more group(s); refine the filters` y hint `<n> more group(s); refine the filters`. `count` de la respuesta = total de mensajes que cumplen los filtros (también los de grupos no mostrados).
   - Lecturas: se recorren todos los mensajes con metadatos; se leen cabeceras de A6 (M10) solo de los mensajes emitidos en los grupos; sin cuerpos salvo `--text` (RNF-23).
3. **Recuento:** respuesta `{"ok", "command", "generated_at", "content_notice", "count", "hint", "warnings", "scan"}` (sin `messages` ni `truncated`); `count` = mensajes que cumplen los filtros tras deduplicar, sin `--limit`; `hint` = RF-78 con `count: 0` y `null` si no; sin lecturas de cuerpos ni cabeceras salvo `--text` (`scan.messages_read: 0`); con `--text` siguen el acotamiento y `[search].max_scan`.
4. **Warnings (RF-74):** regla 4: con `--count`, solo `W_NO_ACCOUNTS`, `W_STORE_EXCLUDED`, `W_ACCOUNT_LABELS_UNAVAILABLE`; regla 5: con `--group-by`, las reglas 1–3 de M10 se aplican a las filas de los grupos.
5. **`hint` sin resultados (RF-78):** cuando `search` termina con `count: 0` (también con `--group-by` o `--count`), `hint` = `no messages matched in <n> folder(s) of <m> account(s); run "mailquery mailboxes" to see other folders, or add --include-mailbox`, con `<m>` = cuentas leídas (no las excluidas con `W_STORE_EXCLUDED`) y `<n>` = sus carpetas buscadas (INBOX, `mailbox_list` y `--include-mailbox`), contadas una vez por cuenta aunque se repitan entre esas fuentes (D-23), del alcance ya resuelto, sin llamadas nuevas al driver; sin cuentas leídas (`W_NO_ACCOUNTS`), `hint: null`; con resultados, `hint` como hoy; `new` no cambia. El hint no contiene nombres.
6. **`content_notice`** con `--count` y `--group-by` (lo inserta `_success_payload` de M07; se verifica).
7. **Documentación:** sección 9.

**Fuera:** `--group-by`/`--count` en `new` (rechazados); agrupar por destinatario, asunto o conversación.

## 3. Dependencias y ACs

- **Entrada:** M10 (fila, `--fields`, lecturas, RF-74 reglas 1–3).
- **Salida:** M12, M14.
- **ACs:** AC-O01 (lecturas de `--group-by` y `--count`), AC-O04, AC-O05, AC-O06, AC-O07, AC-O08 (rechazo en `new`), AC-O09 (reglas 4 y 5), AC-O10 (parte de `--group-by`/`--count`), AC-O13, AC-H18 (`content_notice` con cualquier opción).

## 4. Archivos

| Acción | Archivo |
|---|---|
| Modifica | `src/mailquery/search.py`, `src/mailquery/cli.py` |
| Crea | `tests/test_group_count.py` |
| Modifica si hace falta | `tests/fakes/plugin.py` (muchas filas para más de 50 grupos y más de 200 mensajes), `tests/fakes/outlook.py`, `tests/fixtures/make_fixtures.py` (fechas en el cambio de año), `tests/test_search.py`, `tests/test_cli.py`, `tests/test_multidriver.py`, `tests/test_integration.py` (expectativas de `hint` con `count: 0`) |
| Modifica (barrido de solo lectura, sección 8) | `tests/test_readonly.py` (TC-03.01), `tests/test_outlook.py` (OL-30 y, si hace falta, expectativas de `hint`) |
| Modifica | `README.md`, `README.es.md`, `skills/mailquery/SKILL.md` |
| Modifica si hace falta (D-18, justificado en la evidencia (c)) | `tests/fixtures/expected/**` (goldens) |
| Bloques para el orquestador | `docs/TEST-CATALOG.md` (secciones 2, 7, 8), `docs/INTERFACES.md` (`cli.py`, `search.py`, sección 4 `search`) |

## 5. Refactorizaciones previas

Ninguna (usa las constantes de M02 y la fila de M10).

## 6. Fases

| Fase | Tareas | Estado |
|---|---|---|
| F1 — Opciones | Parser y validación temprana; UT-GRP-03, UT-GRP-06 | 🟢 |
| F2 — Agrupación | Claves, orden, tope de 50, lecturas; UT-GRP-01, UT-GRP-02, UT-GRP-04, UT-GRP-07 | 🟢 |
| F3 — Recuento | UT-GRP-05 | 🟢 |
| F4 — Warnings y `hint` | RF-74 reglas 4–5, RF-78; UT-GRP-08, UT-GRP-09, UT-GRP-10 | 🟢 |
| F5 — Documentación | Sección 9; DOC-11 | 🟢 |
| F6 — Cierre | Suite completa, evidencia cruda, bloques | 🟢 |

## 7. Tests

Archivo `tests/test_group_count.py`, prefijo nuevo **UT-GRP** ("`--group-by`, `--count` y `hint` sin resultados").

**UT-GRP-01 — `--group-by from`**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Un grupo por remitente (dirección en minúsculas) con su `count` y sus 5 mensajes más recientes, de más reciente a más antiguo, sin `from` en las filas. |
| .02 | P | Los grupos van ordenados por su mensaje más reciente. |
| .03 | B | `--limit 0` → `messages: []` en cada grupo y `count` correcto. |
| .04 | P | `--fields snippet` añade `snippet` a las filas de los grupos. |
| .05 | P | La deduplicación se aplica antes de agrupar (el duplicado Gmail/INBOX del store sintético cuenta una vez). |
| .06 | P | Con `[search].default_limit = 20` en la configuración, `--group-by from` sin `--limit` da 5 mensajes por grupo (RF-72: `default_limit` no aplica). |

**UT-GRP-02 — Dos claves y fechas**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `--group-by domain,month` y `--group-by domain --group-by month` dan el mismo resultado: un grupo plano por combinación con mensajes, con `domain` y `month` en ese orden (ejemplo de PRD-v2.2 sección 8). |
| .02 | P | `day`, `week`, `month` usan la zona local (`output.LOCAL_ZONE` inyectada): un mensaje a las 02:00 UTC cae en el día anterior con UTC−4. |
| .03 | B | Semana ISO en el cambio de año: 2026-12-31 y 2027-01-01 → `2026-W53`; 2027-01-04 → `2027-W01`. |
| .04 | B | Mensajes sin fecha forman el grupo `null` de `day`/`week`/`month` y van al final; mensajes sin dirección del remitente, el grupo `null` de `from`/`domain`. |
| .05 | P | `mailbox` da `{"account": <etiqueta>, "path": <ruta>}` sin `mailbox` en las filas; `account` da la etiqueta (o el `uuid` sin etiqueta). |
| .06 | B | A igualdad de mensaje más reciente, los grupos se ordenan por sus claves ascendentes; un grupo sin fechas va después de los que tienen. |
| .07 | B | Remitente con una dirección sin `@`: `from` = la dirección en minúsculas y `domain` = `null`. |
| .08 | B | `--group-by domain,month` con dos grupos del mismo dominio, uno con `month: null`: el grupo con `null` va después de los grupos sin claves `null`, ordenado por claves ascendentes con `null` al final. |

**UT-GRP-03 — Errores de `--group-by` y `--limit`**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Tres claves, una repetida, una desconocida: `E_USAGE`, exit 2, con los mensajes y el hint literales. |
| .02 | N | `--limit 51` y `--limit -1` con `--group-by`: `E_USAGE` con el mensaje y el hint literales. |
| .03 | B | Los errores ocurren antes de crear el home y sin abrir el store. |
| .04 | B | `--limit 50` con `--group-by` es válido (hasta 50 mensajes por grupo). |
| .05 | N | D-24: `--group-by ""` y `--group-by from,` ⇒ `unknown key '' in --group-by`; `--group-by FROM` ⇒ `unknown key 'FROM' in --group-by`; `--group-by "from, month"` equivale a `--group-by from,month`. |

**UT-GRP-04 — Más de 50 grupos**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Con 53 remitentes: 50 grupos, `truncated: true`, hint `3 more group(s); refine the filters`, warning `W_RESULTS_TRUNCATED: 3 more group(s); refine the filters`; `count` es el total de mensajes de los 53 grupos. |
| .02 | B | Exactamente 50 remitentes: 50 grupos, `truncated: false`, sin `W_RESULTS_TRUNCATED`. |
| .03 | B | 51 remitentes: 50 grupos, `truncated: true`, `1 more group(s); refine the filters`. |

**UT-GRP-05 — `--count`**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Respuesta con exactamente `ok`, `command`, `generated_at`, `content_notice`, `count`, `hint`, `warnings`, `scan`, en ese orden; `hint: null` con resultados. |
| .02 | P | Con 250 mensajes (plugin falso) el `count` es 250, sin el límite de 200 ni de `--limit`, y después de deduplicar. |
| .03 | P | Cero resultados → `count: 0`, hint de RF-78, exit 0. |
| .04 | N | `--count` con `--fields`, con `--group-by` y con `--limit` ⇒ `E_USAGE` con el mensaje y el hint literales. |
| .05 | N | `--count --text x` sin filtro de acotamiento ⇒ `E_UNBOUNDED_SCAN`; con más candidatos que `[search].max_scan` ⇒ `E_SCAN_TOO_LARGE`. |

**UT-GRP-06 — `new` sin agrupación ni recuento**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | `new --group-by from` y `new --count` ⇒ `E_USAGE`, exit 2, y `state.json` no cambia (ni se crea si no existía). |

**UT-GRP-07 — Lecturas**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `--group-by` sin `--text`: ninguna extracción de cuerpo; cabeceras leídas solo de los mensajes emitidos (con `--limit 1`, una por grupo). |
| .02 | P | `--count` sin `--text`: ni cuerpos ni cabeceras; `scan.messages_read: 0` (Apple Mail y doble de Outlook, sin `--to`/`--cc`). |
| .03 | P | `--group-by from --text <patrón>`: los cuerpos se leen para filtrar, los grupos solo contienen mensajes que cumplen el patrón y las filas no llevan `snippet` sin `--fields snippet`. |

**UT-GRP-08 — `hint` de `search` sin resultados**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | macOS, Windows y plugin: dos cuentas declaradas con solo INBOX → `no messages matched in 2 folder(s) of 2 account(s); run "mailquery mailboxes" to see other folders, or add --include-mailbox`. |
| .02 | P | `<n>` cuenta INBOX, `mailbox_list` y `--include-mailbox`; también con `--group-by` y con `--count`. |
| .03 | B | Una cuenta declarada cuyo store está excluido (`W_STORE_EXCLUDED`) no cuenta en `<m>` ni sus carpetas en `<n>`. |
| .04 | N | Sin cuentas leídas (ninguna declarada o todas excluidas) → `hint: null` y `W_NO_ACCOUNTS`. |
| .05 | N | Con resultados, `hint` como antes; `new` sin correo nuevo → `hint: null`. |
| .06 | B | El hint no contiene nombres de carpetas ni de cuentas, y la secuencia de llamadas al driver es la misma que la de la misma búsqueda sin calcular el hint (comparación del `CallLog` del doble y de las llamadas del plugin falso). |
| .07 | B | D-23: una cuenta con INBOX también en `mailbox_list` y una carpeta en `mailbox_list` y en `--include-mailbox` cuenta cada carpeta una vez (`<n>` = carpetas únicas por cuenta). |

**UT-GRP-09 — Warnings con `--count` y `--group-by`**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Con `--count`, solo warnings de alcance (`W_NO_ACCOUNTS`, `W_STORE_EXCLUDED`, `W_ACCOUNT_LABELS_UNAVAILABLE`), aunque los mensajes tengan URLs o fallos de autenticación. |
| .02 | P | Con `--group-by`, `W_SENDER_AUTH_FAILED` de un mensaje emitido aparece; el conteo de URLs del cuerpo solo con `--fields snippet`. |

**UT-GRP-10 — `content_notice` con cualquier opción**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `search --count` y `search --group-by from` de éxito llevan `content_notice` tras `generated_at`. |

**DOC-11 — Documentación de `--group-by` y `--count`** (nuevo) · `tests/test_group_count.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `search --help` describe `--group-by` con sus siete claves y `--count`. |
| .02 | P | Los dos README documentan `--group-by` y `--count` con ejemplos y el `hint` de cero resultados. |
| .03 | P | La skill explica `--group-by` y `--count`. |

Comandos:

```bash
python -B -m unittest discover -s tests -t . -k test_ut_grp_
python -B -m unittest discover -s tests -t . -k test_doc_11_
python -B -m unittest discover -s tests -t . -k test_tc_03_
python -B -m unittest discover -s tests -t . -k test_ol_30_
python -B -m coverage erase
python -B -m coverage run -m unittest discover -s tests -t .
python -B -m coverage report
python -B -m coverage report --include="src/mailquery/search.py,src/mailquery/cli.py" --fail-under=85
```

## 8. Tests existentes afectados (previsibles)

- Tests que esperan `hint: null` en un `search` con `count: 0` (`tests/test_search.py`, `tests/test_outlook.py`, `tests/test_multidriver.py`, `tests/test_cli.py`).
- Goldens: ninguno previsto (los goldens de `search` tienen resultados); si alguno tiene `count: 0`, se actualiza y se justifica.
- Barrido de solo lectura: TC-03.01 (`tests/test_readonly.py`) y OL-30 (`tests/test_outlook.py`) añaden `search --group-by from,month` y `search --count`, sin tocar las aserciones de solo lectura.
- Si un caso nuevo verificaría exactamente lo mismo que un caso heredado, se actualiza el heredado en lugar de crear el nuevo.

## 9. Documentación

- Ayuda y epílogo de `search` (sección 2, punto 1).
- `README.md`, `README.es.md`: `--group-by` (claves, `--limit` por grupo, tope de 50 grupos, ejemplo de PRD-v2.2 sección 8), `--count` (ejemplo) y el `hint` de `search` sin resultados; en Troubleshooting, la fila `count: 0 with no warnings` / `count: 0 sin warnings` explica que el `hint` indica cuántas carpetas y cuentas se buscaron y remite a `mailquery mailboxes` y `--include-mailbox`.
- `skills/mailquery/SKILL.md`: cuándo usar `--group-by` (p. ej. últimas facturas por proveedor) y `--count` ("¿cuántos no leídos?"); que `new` no los admite.
- Bloques para `INTERFACES.md`: `cli.py` (validación), `search.py` (agrupación, recuento, `hint`), sección 4 `search` (`groups[]` y forma de `--count`).
- Bloques para `TEST-CATALOG.md`: sección 2, prefijo `UT-GRP` → `tests/test_group_count.py`; sección 8, UT-GRP-01–10, DOC-11 y casos existentes modificados (TC-03.01 y OL-30 con las opciones nuevas); sección 7, filas de AC-O01, AC-O04–AC-O10, AC-O13, AC-H18 (delta `PRD-v2.2.md`).

## 10. Actualizaciones de `PRD-v2.2.md` (las escribe el orquestador)

- Registro de conciliación: "`--limit` de `search`" (F3), "Respuesta de `search` con `--group-by` o `--count`" (F3), "Valores fijos" (F3) y "`hint` de `search` sin resultados" (F3) → `Implementado y documentado`; "Opciones de `search`, `new` y `show` y su ayuda" (F3) y "Warnings de `search`, `new` y `show`" (F3) → completos; "Recetas, skill y README" (F3) → parte de `--group-by`/`--count`. Notas, redactadas sin citar el plan: D-17 (rechazo de `new --group-by`/`--count` por argparse) en "Opciones de `search`, `new` y `show` y su ayuda" (F3); D-23 (carpetas únicas por cuenta) en "`hint` de `search` sin resultados" (F3); D-24 (formato de la lista de `--group-by`) en "Opciones de `search`, `new` y `show` y su ayuda" (F3).
- Checklist: CL-05 avanza (retirados "`hint` siempre `null` sin truncado", "`W_RESULTS_TRUNCATED` solo por `--limit`" y "`search` solo con `messages[]`" en README, skill e `INTERFACES.md`).
- Tabla de supersesión: sin cambios.

## 11. Datos crudos de evidencia a entregar

(a) suite completa con commit y conteo; (b) grupos `test_ut_grp_`, `test_doc_11_`, `test_tc_03_` y `test_ol_30_` solos; (c) goldens tocados (esperado: ninguno); (d) tests nuevos y modificados con IDs y AC; (e) `git diff --check` y `git diff --stat integration/i3-attachments-rows...HEAD`; (f) riesgos (coste de agrupar en Outlook, en un plugin remoto), decisiones y pendientes; (g) cobertura: `coverage report` completo y de los módulos tocados, con la línea base del lote de esos módulos, las líneas sin cubrir y la justificación de cada pragma nuevo. Más los bloques de la sección 9.

## 12. Definition of Done

- [ ] `--group-by` y `--count` solo en `search`, validados antes del home con los textos literales.
- [ ] Grupos, orden, tope de 50, `count` total; recuento sin filas; lecturas según RNF-23.
- [ ] Warnings según RF-74 reglas 4 y 5; `hint` de RF-78 con el alcance resuelto y sin llamadas nuevas.
- [ ] Ayuda, README (incluida la fila de Troubleshooting) y skill actualizados.
- [ ] UT-GRP-01–10 y DOC-11 verdes solos.
- [ ] Suite completa sin fallos nuevos frente a la línea base del lote; TC-03.01 y OL-30 recorren `--group-by` y `--count`.
- [ ] Cobertura (D-21): total ≥ 85 %; `python -B -m coverage report --include=<archivos de src/ de la sección 4> --fail-under=85` verde o, para un módulo por debajo del 85 % en la línea base del lote, sin bajar de ese valor y con las líneas nuevas cubiertas; salida en la evidencia (g).
- [ ] Informe final con los datos de la sección 11 y los bloques.

## 13. Registro de progreso

| Fecha | Fase | Nota |
|---|---|---|
| 2026-11-14 | F1 — Opciones | `--group-by` (dos claves como mucho, lista separada por comas) y `--count` en `search`, con la validación temprana y los textos literales de RF-72/RF-73; rechazo de `new` por argparse. |
| 2026-11-14 | F2 — Agrupación | Siete claves, orden de grupos, tope de 50, `default_limit` ignorado, deduplicación previa y lecturas acotadas a las filas emitidas. |
| 2026-11-14 | F3 — Recuento | Respuesta de `--count` con sus ocho claves, total sin el límite de 200 y solo warnings de alcance. |
| 2026-11-14 | F4 — Warnings y `hint` | RF-74 reglas 4–5 y `hint` de RF-78 con el alcance ya resuelto, sin llamadas nuevas al driver. |
| 2026-11-14 | F5 — Documentación | Ayuda y epílogo de `search`, ambos README (incluida la fila de Troubleshooting) y la skill. |
| 2026-11-14 | F6 — Cierre | Suite completa `Ran 1373`, `FAILED (failures=2, skipped=7)` (los 2 SMOKE-NEW.07 ambientales); UT-GRP-01–10 y DOC-11 verdes solos; cobertura registrada en el informe. |

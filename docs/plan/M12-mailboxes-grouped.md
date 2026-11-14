# M12 — `mailboxes` agrupado por cuenta y `--fields`

**Lote:** I4 · rama del lote `integration/i4-mailboxes-doctor-close` · **Oleada:** W7 (sola)
**Rama:** `feature/m12-mailboxes-grouped`, creada desde la punta de `integration/i4-mailboxes-doctor-close` (abierta desde `develop` con el lote I3 mergeado) · **Worktree:** `../mailquery-wt/m12`
**Estado:** ⚪ (leyenda y protocolo en [`00-master-plan.md`](00-master-plan.md))

## 1. Objetivo

Que `mailboxes` agrupe las carpetas dentro de cada cuenta de `accounts[]`, con solo `path` e `included` por defecto (RF-79), que `--fields` añada `name`, `url`, `total` y `unread` (RF-80), y que sin contadores no se cuente ningún mensaje (RNF-23), en Apple Mail, Outlook y con plugins.

## 2. Alcance

**Dentro:**

1. **Salida (`src/mailquery/search.py`, `run_mailboxes`):** `{"ok", "command", "generated_at", "accounts", "excluded_stores", "warnings"}`; cada cuenta, en este orden, `uuid`, `label`, `email`, `declared` y `mailboxes[]` con sus carpetas; cada carpeta con `path` e `included` y, si se piden, `name`, `url`, `total`, `unread`, siempre en el orden `name`, `path`, `url`, `total`, `unread`, `included`. Cuentas, carpetas y `excluded_stores[]` en el orden de hoy, también con varios drivers (`PRD.md` sección 11.3); una cuenta sin carpetas tiene `mailboxes: []`. Sin `mailboxes[]` de primer nivel ni `account` en las carpetas. Warnings (`W_NO_ACCOUNTS`, `W_ACCOUNT_LABELS_UNAVAILABLE`) y `excluded_stores[]` sin cambios. Una carpeta cuya cuenta no aparece en `accounts[]` hoy se lista con su cuenta; si hubiera carpetas sin cuenta en `accounts[]`, se añade la cuenta como hoy se añade al recorrer las carpetas (mismo orden).
2. **Opción (`src/mailquery/cli.py`):** `mailboxes --fields` (`action="append"`, partido por comas, mismo parser que M10). Valores válidos `name`, `path`, `url`, `total`, `unread`, `included` (`path`/`included` no cambian nada); no hay `all`. Nombre desconocido o vacío, también `all` ⇒ `E_USAGE` (exit 2) antes de crear el home y de abrir el store, mensaje `unknown field '<nombre>' in --fields`, hint `valid fields: name, path, url, total, unread, included`. Help de `mailboxes` con la lista; la línea de `mailboxes` en la ayuda general pasa a `list accounts and their folders (counters with --fields)` y la `description` del subcomando (`List accounts, folders, counters and whether they are included in the configured scope.`) pasa a describir cuentas, carpetas e inclusión, con los contadores solo con `--fields total` o `unread`; el ejemplo del epílogo raíz (`accounts, folders and included flags`) se mantiene si sigue siendo cierto. El epílogo de `mailboxes` explica que los contadores solo se calculan con `--fields total` o `unread`.
3. **Sin recuento:**
   - **Apple Mail (`src/mailquery/store.py`, `src/mailquery/backends/apple_mail.py`):** hoy `EnvelopeStore._load_mailboxes` recalcula los contadores de todas las carpetas en cuanto se carga el catálogo (también en `search`, `new` y `show`). Se separan: el catálogo se carga sin contadores y `_mailbox_counters` se ejecuta una vez, solo cuando alguien los pide. `AppleMailBackend.mailboxes()` sigue devolviendo `total`/`unread` (contrato de la API) y se añade `AppleMailBackend.mailboxes_without_counters()` (como Outlook), que `config.listed_mailboxes` ya usa si existe; así `search`, `new` y `show` dejan de recontar como efecto secundario.
   - **Outlook:** `run_mailboxes` usa `mailboxes_without_counters()` (ya existe) salvo que se pidan `total` o `unread`.
   - **Plugins:** `mailboxes()` como hoy (`plugin_api = 1`); el núcleo omite los contadores no pedidos.
4. **Documentación:** sección 9.

**Fuera:** ocultar carpetas por tipo o vacías; `--fields all`; un default de `--fields` en `config.toml`.

## 3. Dependencias y ACs

- **Entrada:** M10 (parser de `--fields`); lote I3 mergeado.
- **Salida:** M13 (orden de archivos), M14 (p95 de `mailboxes` en SMOKE).
- **ACs:** AC-O14, AC-O15 (salvo la medición p95, que hace M14).

## 4. Archivos

| Acción | Archivo |
|---|---|
| Modifica | `src/mailquery/search.py` (`run_mailboxes`), `src/mailquery/cli.py`, `src/mailquery/store.py`, `src/mailquery/backends/apple_mail.py`, `src/mailquery/backends/outlook.py` (solo si hace falta para el modo sin contadores) |
| Modifica | Goldens `tests/fixtures/expected/mailboxes.json`, `tests/fixtures/expected/outlook/mailboxes.json` |
| Crea | `tests/test_mailboxes.py` |
| Modifica (expectativas de la forma de `mailboxes`) | `tests/test_search.py`, `tests/test_outlook.py`, `tests/test_multidriver.py`, `tests/test_cli.py`, `tests/test_integration.py`, `tests/test_store.py`, `tests/test_backends.py`, `tests/test_emlx.py` (solo los que fallen) |
| Modifica (sección 8) | `tests/test_readonly.py` (TC-03.01), `tests/test_smoke.py` (helpers y casos que leen `mailboxes`), `tests/test_content_wiring.py` (UT-CW-01.05) |
| Modifica si hace falta | `tests/fakes/outlook.py`, `tests/fixtures/make_fixtures.py`, `tests/fakes/plugin.py` (espías de recuento) |
| Modifica | `README.md`, `README.es.md`, `skills/mailquery/SKILL.md`, `docs/config.example.toml` (comentarios de `mailbox_list`), `docs/PERFORMANCE-BACKLOG.md`, `docs/recipes/*` (si muestran la salida de `mailboxes`) |
| Bloques para el orquestador | `docs/TEST-CATALOG.md` (secciones 2, 3, 7, 8), `docs/INTERFACES.md` (`store.py`, `backends/apple_mail.py`, `search.py`, `cli.py`, sección 4 `mailboxes`) |

## 5. Refactorizaciones previas

La separación del catálogo y los contadores en `store.py` (sección 2, punto 3) es parte de la funcionalidad (RF-80), no un refactor aparte: cambia cuándo se cuenta, no qué se cuenta.

## 6. Fases

| Fase | Tareas | Estado |
|---|---|---|
| F1 — Sin recuento | Catálogo sin contadores en `store.py`; `mailboxes_without_counters` en Apple Mail; UT-MBX-04 | ⚪ |
| F2 — Forma | `run_mailboxes` agrupado; goldens; UT-MBX-01, UT-MBX-02 | ⚪ |
| F3 — `--fields` | Opción, validación, ayudas; UT-MBX-03, UT-MBX-05 | ⚪ |
| F4 — Tests existentes | Ajuste de expectativas | ⚪ |
| F5 — Documentación | Sección 9; DOC-13 | ⚪ |
| F6 — Cierre | Suite completa, evidencia cruda, bloques | ⚪ |

## 7. Tests

Archivo `tests/test_mailboxes.py`, prefijo nuevo **UT-MBX** ("Salida de `mailboxes`").

**UT-MBX-01 — Forma por defecto**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Sin `--fields`: claves de primer nivel exactamente `ok`, `command`, `generated_at`, `accounts`, `excluded_stores`, `warnings` (store sintético, doble de Outlook y plugin falso). |
| .02 | P | Cada cuenta tiene `uuid`, `label`, `email`, `declared`, `mailboxes`, en ese orden; cada carpeta solo `path` e `included`, con los mismos valores e igual orden que la salida de antes (comparación con la lista plana anterior agrupada por cuenta). |
| .03 | N | Ninguna carpeta lleva `account`; no hay `mailboxes` de primer nivel. |
| .04 | B | Una cuenta sin carpetas tiene `mailboxes: []`; con dos drivers declarados, el orden de cuentas y de `excluded_stores[]` es el de `PRD.md` sección 11.3. |

**UT-MBX-02 — Referencias copiadas**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Un `path` copiado de la salida resuelve en `mailbox_list` y en `--include-mailbox`. |
| .02 | P | El `name` y la `url` (de `--fields name,url`) siguen resolviendo. |

**UT-MBX-03 — `--fields`**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `--fields name,url,total,unread` y `--fields total --fields name,url,unread` añaden esos campos en el orden `name`, `path`, `url`, `total`, `unread`, `included`, con los valores de antes. |
| .02 | P | `--fields path,included` da la salida por defecto. |
| .03 | N | `--fields all`, `--fields carpeta` y `--fields ""` ⇒ `E_USAGE`, exit 2, mensaje y hint literales de RF-80, antes de crear el home y sin abrir el store. |

**UT-MBX-04 — Sin recuento sin `total` ni `unread`**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Apple Mail: sin `total`/`unread`, la consulta de recuento (`store._mailbox_counters`) no se ejecuta (espía); con `--fields unread`, se ejecuta una vez. |
| .02 | P | Outlook (doble): sin contadores, no se leen las tablas de las carpetas (`CallLog` sin el recuento por carpeta); con `--fields total`, sí. |
| .03 | P | Plugin falso que entrega contadores: sin `--fields`, la salida no los incluye. |
| .04 | B | `search`, `new` y `show` en Apple Mail ya no ejecutan el recuento de carpetas (espía), con la misma salida que antes. |
| .05 | B | Apple Mail: dentro de un mismo proceso, una segunda petición de contadores reutiliza el recuento (la consulta se ejecuta una vez). |
| .06 | N | Apple Mail: un error de SQLite durante el recuento diferido de `mailboxes --fields total` da el mismo error que hoy da el recuento al cargar el catálogo (código y exit sin cambios). |
| .07 | B | Plugin falso que no entrega contadores: `mailboxes --fields total` no falla y da los mismos valores que hoy da la salida completa para ese plugin. |

**UT-MBX-05 — Ayudas**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `mailboxes --help` describe `--fields` con `name, path, url, total, unread, included`. |
| .02 | P | La ayuda general muestra `list accounts and their folders (counters with --fields)` para `mailboxes`. |

**DOC-13 — Documentación de `mailboxes`** (nuevo) · `tests/test_mailboxes.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Los dos README muestran la salida agrupada (ejemplo de PRD-v2.2 sección 8) y `--fields total,unread` para los contadores; ningún README describe un `mailboxes[]` de primer nivel con `account`. |
| .02 | P | La skill usa `mailboxes` sin `--fields` para ver carpetas y `--fields total,unread` solo cuando hacen falta los contadores. |
| .03 | P | `docs/config.example.toml` explica que `mailbox_list` acepta el `path` que muestra `mailboxes` (y el nombre o la URL de `--fields name,url`). |

**Goldens (TC-01, TC-02):** `mailboxes.json` y `outlook/mailboxes.json` pasan a la forma agrupada sin contadores.

Comandos:

```bash
python -B -m unittest discover -s tests -t . -k test_ut_mbx_
python -B -m unittest discover -s tests -t . -k test_doc_13_
python -B -m unittest discover -s tests -t . -k test_tc_01_
python -B -m unittest discover -s tests -t . -k test_tc_02_
python -B -m unittest discover -s tests -t . -k test_tc_03_
python -B -m unittest discover -s tests -t . -k test_ol_30_
python -B -m unittest discover -s tests -t . -k test_ut_cw_
python -B -m unittest tests.test_smoke -v
python -B -m coverage erase
python -B -m coverage run -m unittest discover -s tests -t .
python -B -m coverage report
python -B -m coverage report --include="src/mailquery/search.py,src/mailquery/cli.py,src/mailquery/store.py,src/mailquery/backends/apple_mail.py,src/mailquery/backends/outlook.py" --fail-under=85
```

## 8. Tests existentes afectados (previsibles)

- Goldens de `mailboxes` (TC-01, TC-02).
- UT-SR de `mailboxes` (`tests/test_search.py`), OL-11 y OL-12 (`tests/test_outlook.py`: `path`, `name`, `url` y contadores), UT-MD de `mailboxes` (`tests/test_multidriver.py`), TC-05 (paridad de forma), tests de `store.py` que esperen contadores en el catálogo cargado.
- `tests/test_readonly.py`: TC-03.01 comprueba `accounts` (cada cuenta con su `mailboxes`) en lugar de `mailboxes` de primer nivel, y el barrido añade `mailboxes --fields name,url,total,unread`; OL-30 (`tests/test_outlook.py`) añade el mismo caso. Las aserciones de solo lectura no se tocan.
- `tests/test_smoke.py`: los `setUpClass` de `SmokeTest`, `SmokeAttOutlook` y `SmokeAttAppleMail` y SMOKE-NEW.01 recorren `accounts[].mailboxes[]`; `_counters` (SMOKE-NEW.06) y SMOKE-ATT-OL.03 usan `mailboxes --fields url,total,unread`.
- `tests/test_content_wiring.py`: UT-CW-01.05 toma el nombre de carpeta de la salida agrupada.
- Regla: un test que verifica `name`, `url` o los contadores se ajusta pidiéndolos con `--fields`, nunca borrando la aserción; cada ajuste se lista en la evidencia.
- Si un caso nuevo de UT-MBX verificaría exactamente lo mismo que un caso heredado (TC-01.02, UT-MD-03), se actualiza el heredado en lugar de crear el nuevo.

## 9. Documentación

- Ayudas (sección 2, punto 2): línea de la ayuda general, `description` y epílogo de `mailboxes`.
- `README.md`, `README.es.md`: sección de `mailboxes` con la salida agrupada, `--fields` y el coste de los contadores; donde se diga "tal como lo muestra `mailboxes`" para `mailbox_list`/`--include-mailbox`, aclarar `path` (o nombre/URL con `--fields name,url`).
- `skills/mailquery/SKILL.md`: tabla de comandos (`mailboxes` = cuentas y sus carpetas; contadores con `--fields`) y uso de `mailboxes` según RF-80.
- `docs/config.example.toml`: comentarios de `mailbox_list`.
- `docs/PERFORMANCE-BACKLOG.md`: el pendiente de `mailboxes` queda limitado a `--fields total` o `unread` (RNF-23); la medición nueva se añade en M14.
- `docs/recipes/*`: si alguna muestra la salida de `mailboxes`, la forma nueva.
- Bloques para `INTERFACES.md`: `store.py` (catálogo sin contadores, recuento perezoso), `backends/apple_mail.py` (`mailboxes_without_counters`), `search.py` (`run_mailboxes`), `cli.py` (`mailboxes --fields`), sección 4 `mailboxes`.
- Bloques para `TEST-CATALOG.md`: sección 2, prefijo `UT-MBX` → `tests/test_mailboxes.py`; sección 3, goldens de `mailboxes`; sección 8, UT-MBX-01–05, DOC-13 y casos existentes modificados (incluidos los textos de TC-03.01, SMOKE-NEW.01, SMOKE-NEW.06, SMOKE-ATT-OL.03 y OL-30); sección 7, filas de AC-O14 y AC-O15.

## 10. Actualizaciones de `PRD-v2.2.md` (las escribe el orquestador)

- Registro de conciliación: "Salida de `mailboxes`" (F3) → `Implementado y documentado`; "Rendimiento" (F3) → nota del recuento perezoso en Apple Mail.
- Checklist: CL-05 avanza (retirados el `mailboxes[]` de primer nivel con `account`, los contadores siempre presentes y la línea de ayuda `list accounts, folders, counters and included folders` en README, skill, `config.example.toml` e `INTERFACES.md`); CL-06: pendiente de `PERFORMANCE-BACKLOG.md` limitado a los contadores.
- Tabla de supersesión: sin cambios.

## 11. Datos crudos de evidencia a entregar

(a) suite completa con commit y conteo; (b) grupos `test_ut_mbx_`, `test_doc_13_`, `test_tc_01_`, `test_tc_02_`, `test_tc_03_`, `test_ol_30_` y `test_ut_cw_` solos, y `tests.test_smoke` (según la regla de redacción de la regla 6 del plan maestro); (c) goldens de `mailboxes` con su diff y justificación; (d) tests nuevos y existentes ajustados con IDs, AC y motivo; (e) `git diff --check` y `git diff --stat integration/i4-mailboxes-doctor-close...HEAD`; (f) riesgos, decisiones y pendientes; (g) cobertura: `coverage report` completo y de los módulos tocados, con la línea base del lote de esos módulos (`store.py` 86,8 % y `apple_mail.py` 88,1 % en `cf164ff`, Windows), las líneas sin cubrir y la justificación de cada pragma nuevo. Más los bloques de la sección 9.

## 12. Definition of Done

- [ ] Salida agrupada por cuenta con `path` e `included` por defecto; `--fields` añade `name`, `url`, `total`, `unread`; sin `all`.
- [ ] Sin `total`/`unread` no se cuenta ningún mensaje en Apple Mail ni en Outlook; plugins sin contadores no pedidos.
- [ ] Ayudas, README, skill, `config.example.toml`, `PERFORMANCE-BACKLOG.md` y recetas actualizados.
- [ ] UT-MBX-01–05, DOC-13 y goldens verdes solos; `tests/test_readonly.py`, `tests/test_smoke.py` y `tests/test_content_wiring.py` ajustados a la forma agrupada.
- [ ] Suite completa sin fallos nuevos frente a la línea base del lote, incluidos SMOKE (en este Windows con Outlook clásico abierto), TC-03.01 y OL-30.
- [ ] Cobertura (D-21): total ≥ 85 %; `python -B -m coverage report --include=<archivos de src/ de la sección 4> --fail-under=85` verde o, para un módulo por debajo del 85 % en la línea base del lote, sin bajar de ese valor y con las líneas nuevas cubiertas; salida en la evidencia (g).
- [ ] Informe final con los datos de la sección 11 y los bloques.

## 13. Registro de progreso

| Fecha | Fase | Nota |
|---|---|---|
| — | — | — |

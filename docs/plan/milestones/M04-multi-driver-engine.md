# M04 — Motor multi-driver

| Campo | Valor |
|-------|-------|
| Fase | C — Núcleo de datos multi-driver |
| Depende de | M01, M02, M03 |
| Bloquea a | M05, M06–M11 |
| ACs | AC-04; AC-05 (routing de `show` por prefijo); AC-07 (parcial, `show` con plugin); AC-19 (log `event=start`) |
| Grupos de test | UT-MD-01..07; actualización de UT-SR-03/04/07/08/11 y de los golden tests donde aplique |
| Write scope | `src/mailquery/search.py` (merge multi-driver, cursor global y despacho de `show`), `src/mailquery/cli.py` (construcción/cierre de drivers, log de inicio y ruta de `show`), `src/mailquery/backends/registry.py` (helper de carga de declarados), `docs/INTERFACES.md`, `tests/fakes/plugin.py` (operaciones de `show`), `tests/test_multidriver.py` (nuevo), `tests/test_search.py`, `tests/test_integration.py`, `tests/fixtures/make_fixtures.py` (plugin de prueba), `tests/fixtures/expected/search_multidriver.json`, `tests/fixtures/expected/new_multidriver.json` (nuevos) |
| No tocar | `state.py`, `config.py`, `attachments/**`, `plugins/**` salvo lo ya congelado, `PRD.md`, `PRD-v2.1.md`, `docs/plan/**` |
| Estado | ⚪ |

## 1. Objetivo

Ejecutar `mailboxes`, `search` y `new` sobre **todos** los drivers declarados y fusionar los resultados con el orden total, el cursor global y las reglas de deduplicación del PRD-v2.1, con fail-fast ante el fallo de un driver. Además, `show <uid>` carga el driver del prefijo y usa sus operaciones (`find_message`/`load_body`, adjuntos con índice), incluido un plugin externo declarado. En este milestone entra el log `event=start` con `backend=` y `drivers=`.

## 2. Contexto normativo

- PRD-v2.1 §6.1 RF-36 (parte de alcance), RF-37 (ejecución multi-driver), RF-40 (routing de `show` por prefijo), §9.2 (flujo `show`), §10.2 puntos 7, 8 y 9 (orden total, cursor multi-driver, composición JSON), §11.9 (sin cambios), §12.1 (log `start`), §14 AC-04/AC-05/AC-07/AC-19.
- Base 2.0.1: `cli.py:457-497` (selección y ciclo de vida), `cli.py:550` (`event=start backend=`), `cli.py:579-591` (`event=end`), `search.py:266-273,402-410,1076-1105` (formas de salida), `search.py:361-364,965-1030` (orden y dedupe), `search.py:529-586` (`mailboxes`), `backends/__init__.py:15-72` (selección por plataforma).

## 3. Tareas

| ID | Tarea | Archivos | Detalle |
|----|-------|----------|---------|
| M04-T01 | Carga de drivers declarados | `cli.py`, `backends/registry.py` | El comando construye el registro (M01), resuelve la config (M02) y carga **solo** los drivers declarados en `[scope]` más el nativo cuando corresponde. Los drivers se abren antes de `event=start` y se cierran siempre (best-effort) al terminar. Un driver declarado que no carga ⇒ el comando falla con su código (`E_PLUGIN_INCOMPATIBLE`/`E_DRIVER_UNKNOWN`) y no devuelve resultados parciales. |
| M04-T02 | Merge y orden total | `search.py` | `search`/`new` consultan cada driver con los mismos filtros y fusionan: `search`/`show` con `(date_received DESC, driver ASC, native_order_key DESC)`, `new` con `(date_received ASC, driver ASC, native_order_key ASC)`. `native_order_key` llega como campo string en cada fila del backend (C1); se compara como entero si la capacidad es `numeric` (Apple Mail) o como texto si es `text` (Outlook y plugins por defecto), nunca por el texto del uid. No hay deduplicación cross-driver: el mismo `message_id` en dos drivers produce dos resultados con `duplicate_count` calculado dentro de cada driver; la deduplicación y la elección de copia canónica del PRD.md RF-07 se mantienen dentro de cada driver. |
| M04-T03 | Cursor global y lookback | `search.py`, `state.py` (solo lectura) | Un único `last_date_received`/`last_uid` global; el anillo guarda uids prefijados y filtra por uid. Cada driver declarado se consulta con el mismo `last_date_received` y `lookback`; la primera corrida emite la ventana `[más reciente − lookback, más reciente]` sobre el conjunto fusionado. Si el driver del `last_uid` está instalado pero ya no declarado, el cursor se conserva y se usa `last_date_received` como marca (no es `E_STATE_CORRUPT`); los uids de drivers no declarados permanecen en el anillo y no se comparan. El avance del cursor usa el orden total, no la comparación textual del uid. |
| M04-T04 | Composición de `mailboxes` | `search.py` | `accounts[]`, `mailboxes[]` y `excluded_stores[]` se concatenan en el orden de aparición de los bloques `[scope]` en la config; los plugins devuelven `excluded_stores: []`; `--limit` se aplica tras el merge; `scan.candidates` suma por driver; `truncated`/`hint` siguen el PRD.md §12.5. |
| M04-T05 | Fail-fast y cierre | `search.py`, `cli.py` | Si un driver declarado falla en runtime, el comando falla con el código correspondiente y no devuelve resultados parciales; las exclusiones de stores del backend interno siguen siendo warnings (`W_STORE_EXCLUDED`). Todos los drivers abiertos se cierran en el `finally`; un error de cierre no enmascara el resultado. |
| M04-T06 | Log de inicio multi-driver | `cli.py` | `event=start`: `command=... backend=<driver nativo> drivers=<lista declarada separada por comas>`; sin uids, cuentas, rutas ni términos. `event=end` conserva sus campos actuales. |
| M04-T07 | Tests y goldens | `tests/test_multidriver.py` (nuevo), `tests/fixtures/make_fixtures.py`, `tests/fixtures/expected/search_multidriver.json`, `new_multidriver.json`, `tests/test_search.py`, `tests/test_integration.py` | UT-MD-01..07 con el plugin de prueba de M01 como segundo driver; dos goldens nuevos con `apple_mail` + plugin de prueba; los goldens de un solo driver no cambian respecto de M03. |
| M04-T08 | Despacho de `show` por prefijo | `search.py`, `cli.py`, `tests/fakes/plugin.py` | `show <uid>` separa `driver`/`native_id`, carga el driver del prefijo (nativo o plugin declarado) y llama a `find_message`/`load_body` y a la operación de adjuntos del driver; el cuerpo puede venir del plugin si `body_local: false`; un driver no declarado ⇒ `E_ACCOUNT_NOT_IN_SCOPE` sin cargarlo; `attachments: "none"` ⇒ `[]`; un plugin declarado con `attachments: "local"` devuelve nombres/índices de su operación y `show` calcula `cached_path: null` (no escribe). No implementa el `attachment` (M08). |

## 4. Casos de prueba

### UT-MD-01 — Carga y fail-fast (AC-04)

- .01 P Solo se cargan los drivers declarados (más el nativo si hay bloques sin prefijo); los no declarados no se importan.
- .02 N Un driver declarado no carga ⇒ el comando falla con su código y sin resultados parciales.
- .03 N Un driver falla en runtime a mitad del merge ⇒ el comando falla con el código mapeado; no hay `messages[]` parcial.
- .04 P Todos los drivers se cierran aunque el comando falle.

### UT-MD-02 — Merge y orden (AC-04, §10.2.7)

- .01 P `search` con dos drivers: orden `(date_received DESC, driver ASC, native_order_key DESC)`.
- .02 P `new` con dos drivers: orden ascendente; el cursor avanza con el último emitido.
- .03 P Mismo `message_id` en dos drivers ⇒ dos resultados, `duplicate_count` independiente por driver.
- .04 P Duplicado dentro de un driver sigue eligiendo la copia canónica (INBOX/carpeta normal) y `duplicate_count: 2`.
- .05 B Misma fecha y mismo driver, distinto `native_order_key` numérico y textual ⇒ desempate estable y determinista.
- .06 B Misma fecha y distinto driver ⇒ desempata por `driver` ascendente.

### UT-MD-03 — `mailboxes` multi-driver (AC-04, §10.2.9)

- .01 P `accounts[]`, `mailboxes[]` y `excluded_stores[]` concatenados en el orden de los bloques `[scope]`.
- .02 P Un plugin devuelve `excluded_stores: []` y `accounts[]` con `label`/`uuid` opacos.
- .03 B Un driver sin cuentas declaradas no aporta bloques y no rompe el comando.

### UT-MD-04 — Cursor y lookback (AC-04, §10.2.8)

- .01 P Un único cursor global; cada driver se consulta con el mismo `last_date_received` y `lookback`.
- .02 P Primera corrida: ventana sobre el conjunto fusionado y anillo con uids prefijados.
- .03 N `cursor.last_uid` de un driver instalado pero no declarado: el cursor se conserva, se usa la fecha como marca y los uids de ese driver no se comparan.
- .04 P Los uids de drivers no declarados permanecen en el anillo sin romper `new`.

### UT-MD-05 — Límites y `scan` (AC-04, PRD.md §12.5)

- .01 P `--limit` se aplica tras el merge; `truncated`/`hint` se calculan sobre el resultado fusionado.
- .02 P `scan.candidates` suma por driver; `scan.messages_read` suma las lecturas.
- .03 B `--limit` mayor que el total ⇒ sin `truncated` ni `hint`.

### UT-MD-06 — Log multi-driver (AC-19, §12.1)

- .01 P `event=start` registra `backend=<nativo>` y `drivers=<lista declarada>`.
- .02 N El log no registra uids, `native_id`, cuentas, rutas, asuntos ni términos.
- .03 P Un comando con solo un driver declarado registra `drivers=` con ese driver y `backend=` con el nativo.

### UT-MD-07 — `show` con driver externo declarado (AC-05, AC-07)

- .01 P `show <plugin>:<native_id>` carga el plugin declarado y devuelve uid prefijado, cuerpo (`body_local: true` o `false`) y `attachments[]` con `{index, name, cached_path}`; `cached_path` es `null` si no hay caché.
- .02 P Un plugin con `body_local: false` obtiene el cuerpo del plugin; si no está disponible, aplica `W_BODY_NOT_LOCAL`/`W_BODY_UNREADABLE` como en PRD.md §12.10.
- .03 N `show` de un plugin instalado pero no declarado ⇒ `E_ACCOUNT_NOT_IN_SCOPE` (exit 2) sin importar/cargar el plugin.
- .04 N `show` de un plugin con `attachments: "none"` ⇒ `attachments: []`; no se llama a la operación de adjuntos.
- .05 N `show` de un plugin con `attachments: "remote"` y `network: true` devuelve solo nombres (sin red en el núcleo); `show` no escribe ni descarga.
- .06 P `native_order_key` del plugin se usa en el orden de `search`/`show` con la capacidad `native_order` declarada.

## 5. Documentación del milestone

- `docs/INTERFACES.md`: semántica multi-driver, orden total, cursor global, composición JSON, fail-fast, despacho de `show` por prefijo y formato del log `start`.

## 6. Criterios de cierre

1. Suite verde sin fallos nuevos; UT-MD verdes solos; goldens de un solo driver idénticos a M03.
2. Dos goldens nuevos (search/new) con `apple_mail` + plugin de prueba, deterministas.
3. El comando falla sin resultados parciales ante fallo de un driver; `show` carga el driver del prefijo, incluido un plugin declarado.
4. Sin cambios en `state.py` ni en el esquema de config; el log de inicio no incorpora PII.

## 7. Handoff y HITL

- Reportar: forma del merge y del cursor, goldens nuevos, forma final de `drivers=` en el log, fixture de plugin usado.
- HITL: solo si la ventana de la primera corrida con varios drivers no puede calcularse sin abrir todos los stores; `native_order_key` ya está en C1 y no se pregunta.

## 8. Riesgos del milestone

| Riesgo | Mitigación |
|---|---|
| El merge duplica el coste de `new` en la primera corrida | Es el comportamiento normativo; `--limit` se aplica después y el presupuesto de §12.2 es por driver interno, no global |
| El fixture de plugin no representa un driver real | Usa solo el contrato público C1 y declara `native_order` y capacidades explícitas; NO-1 de M01 |
| Un driver no declarado se abre por error | La carga usa únicamente `config` + registro; test .01 de UT-MD-01 |

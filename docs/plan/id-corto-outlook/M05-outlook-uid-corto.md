# M05 — Outlook: uid corto, asignación, registro y validación

- **Unidad:** `docs/changes/id-corto-outlook.md` (contribuye; no la completa sola).
- **Oleada / lote:** 3 / 2. **Rama del lote:** `feature/id-corto-outlook-lote-2`. **Rama del milestone:** `feature/id-corto-outlook-m05`, creada desde el tip de la rama del lote (con el lote 1 integrado).
- **Commit base:** `98e1316`. **Línea base de la suite:** `Ran 1497 tests`, `OK (skipped=7)`, 0 fallos; los 7 saltos son SMOKE/installer que no aplican en macOS.
- **Depende de:** M01 (`NativeIdCache`), M02 (`_entry_id`/`_uid_part`), M03 (aviso `printed_messages`, `bind_home`, `MessageNotFound`). **Lo usan:** M06 y M07.
- **ACs:** AC-63 (uid corto, estabilidad, resolución, validación, macOS sin cambios), AC-65 (registro de impresos en Outlook), AC-67 (claves del JSON), AC-69 (caché en Outlook: creación, errores, `show` sin base).

## Objetivo

Que el driver `outlook` emita y acepte como uid `outlook:<id corto>` (con sufijo cuando toca), asigne con la librería los uids de todas las filas que lee, registre en el aviso solo los impresos y resuelva en la caché los uids que recibe.

## Alcance

- `bind_home(home)` y el origen del home de D-06; apertura perezosa de la caché (D-11) con `NativeIdCache.open("outlook", home=…)` o `open_in_memory("outlook")`; cierre en `close()`.
- `SHORT_ID_LENGTH = 10` (D-12).
- `_uid_part`: en `query`, una llamada a `assign` por consulta con los `EntryID` leídos; la fila emite la parte asignada y conserva `native_order_key = EntryID`. Un mapa en memoria parte ↔ `EntryID` para la ejecución.
- `_entry_id`: mapa en memoria y, si no está, `resolve` en la caché; sin fila ⇒ "no está en la caché".
- `printed_messages(native_ids)`: traduce las partes a `EntryID` y llama a `register` una vez con todos.
- `display_native_id(native_id)`: devuelve el `EntryID` de esa parte (lo prueba M06 con la opción de M04).
- `parse_uid` y `parse_native_id`: solo la forma corta (10 caracteres del alfabeto, con o sin `-<entero ≥ 2 sin ceros>`), con los textos de D-05. Siguen siendo puros y sin conexión.
- `find_message` y las operaciones de adjuntos: un uid que no está en la caché lanza `MessageNotFound` con el hint de repetir la búsqueda (D-05, D-07). Con fila, siguen con el `EntryID` como hoy.
- Los fallos de la caché (`E_LOCKED`, `E_PERMISSION`, `E_IO`) se propagan sin cambiar.
- Actualizar los tests y goldens existentes que fijan uids largos.

## Fuera de alcance

- Ausente confirmado, borrado de filas, causas de indeterminado, colisiones de punta a punta, prueba de `--show-native-id` y SMOKE (M06). En M05, un `EntryID` resuelto cuyo item ya no existe sigue respondiendo como hoy (no encontrado con el hint actual) y no borra la fila.
- Documentación consumidora y versión (M07).

## Alcance de escritura

- `src/mailquery/backends/outlook.py`.
- `tests/fakes/outlook.py`, `tests/fakes/run_cli.py`, `tests/test_outlook.py`, `tests/test_uid.py`, `tests/test_backends.py`, `tests/test_cli.py`, `tests/test_integration.py`.
- Solo si fallan por el uid nuevo: `tests/test_body_sources.py`, `tests/test_content_wiring.py`, `tests/test_doctor.py`, `tests/test_fields.py`, `tests/test_group_count.py`, `tests/test_mailboxes.py`, `tests/test_search.py`, `tests/test_readonly.py`.
- `tests/fixtures/expected/outlook/*.json`, salvo `outlook/doctor.json`.
- Este archivo (fases y registro), `docs/plan/id-corto-outlook/work/M05-handoff.md`, `docs/plan/id-corto-outlook/work/M05-propuestas.md`.

## Especificación

Rangos de `docs/changes/id-corto-outlook.md` en el commit `384e5a8`:

- "Problema" y "Solución elegida": líneas 20–35. "Por qué el núcleo avisa de lo que imprime": líneas 37–48.
- "Lo que no cambia": líneas 94–101.
- "RF-80" (asignar, una parte por ejecución, registrar, conflicto, resolver, errores): líneas 109–143.
- "RF-81. Id corto en Outlook": líneas 145–165.
- "RF-82", condición "Outlook": línea 179. "RF-83", condiciones "Qué muestra" y "Sin gancho": líneas 189 y 195.
- "Requisitos existentes que cambian": líneas 200–212.
- "Caché de ids nativos", reglas del archivo: líneas 298–309.
- "Modelo de datos": líneas 311–315. "Comando `show` y errores": líneas 317–339.
- AC-63: línea 362. AC-65: línea 366. AC-67: línea 370. AC-69: línea 374.

## Puntos de entrada en el código

- `src/mailquery/backends/outlook.py` (commit `384e5a8`; busca por nombre lo que M02 movió): `_entry_id` y `_uid_part` (de M02), `__init__` (366), `query` (674), `find_message` (963), `_attachment_item` (903), `parse_uid` (1138), `parse_native_id` (1155), `NOT_FOUND_HINT` (130), `close` (1322), `_UID_PATTERN` (55).
- `src/mailquery/native_ids.py` (M01) y `MessageNotFound` en `src/mailquery/backends/base.py` (M03); llamada a `bind_home` en `cli._open_drivers` (M03).
- `tests/fakes/outlook.py`: `SCENARIOS` (2439), `fail_next` (1800), `FakeNameSpace._call_GetItemFromID` (1241).
- `tests/fakes/run_cli.py`: `main` (construye el backend con `tmp_root`).
- `tests/test_outlook.py`: `_backend` (575), helper de goldens (4330). `tests/test_integration.py`: goldens (160, 371).

## Refactorizaciones previas

M02 (frontera uid ↔ `EntryID`). En M05 solo cambian `_uid_part`, `_entry_id` y lo descrito en "Alcance".

## Decisiones aplicables

- **D-05. Textos literales.** En inglés, comparados literalmente por los tests:
  - `E_LOCKED`: mensaje `the native id cache is locked by another process`; hint `close the process that holds ~/.mailquery/db/cache.db and run the command again`.
  - `E_PERMISSION`: mensaje `no permission to read or write the native id cache`; hint `check the permissions of ~/.mailquery/db/ and ~/.mailquery/db/cache.db`.
  - `E_IO`: mensaje `cannot use the native id cache: <detalle>` (`<detalle>`: `not a valid native id cache`, `conflicting uid part` u otro texto sin datos de correo); hint `if you delete ~/.mailquery/db/cache.db, mailquery creates an empty one; uids already printed do not resolve until you repeat the search`.
  - Forma inválida en Windows: mensaje `invalid uid part '<id>': expected a short id` (`<id>` con `repr`); hint ``Outlook uids are short ids as printed by `mailquery search` and `mailquery new`; run `mailquery search` to find the uid of a message``.
  - Hint de repetir la búsqueda (uid fuera de la caché o mensaje ausente confirmado): ``the uid is not in the native id cache or its message no longer exists; run `mailquery search` or `mailquery new` again to get its current uid``.
- **D-06.** Home: `bind_home` > `tmp_root.parent` > base en memoria.
- **D-07.** `MessageNotFound(hint)` para el uid que no está en la caché.
- **D-11.** La caché se abre en la primera consulta o resolución; `mailboxes`, `doctor` y `--version` nunca la abren.
- **D-12.** `SHORT_ID_LENGTH = 10`, sin cambiarla en los tests (la entrada exige 10 caracteres). Para provocar colisiones, los tests sustituyen `mailquery.native_ids.short_id` dentro del proceso por una función que da el mismo id corto válido de 10 caracteres a dos o tres `EntryID` elegidos.
- Regla de RF-81: el id corto se calcula del `EntryID` en hexadecimal en mayúsculas; el `EntryID` nunca se acepta como uid.

## Fases

**Tabla: Fases de M05**

| Fase | Tareas | Estado |
|---|---|---|
| 1 | Home, apertura perezosa, cierre y `SHORT_ID_LENGTH` | 🟢 |
| 2 | Asignación en `query`, mapa de la ejecución, `_uid_part`/`_entry_id`, `printed_messages`, `display_native_id` | 🟢 |
| 3 | Validación corta en `parse_uid`/`parse_native_id`; uid fuera de la caché con `MessageNotFound` | 🟢 |
| 4 | Actualizar tests y goldens existentes (`MAILQUERY_UPDATE_GOLDENS=1` y revisión del diff de cada golden) | 🟢 |
| 5 | OL-31, OL-32, OL-33, UT-UID-03 | 🟢 |
| 6 | Suite completa, cobertura, diff, evidencia cruda | 🟢 |

## Tests

Grupos nuevos en `tests/test_outlook.py` (OL) y `tests/test_uid.py` (UT-UID-03), con el doble de Outlook y `HOME` temporal. Las definiciones ya están `[pendiente]` en `docs/tests/outlook-runtime.md` y `docs/tests/state-backends.md`.

#### OL-31 — uid corto de Outlook

Requisitos: RF-81, RF-80, AC-63, AC-67, AC-69 · Archivo: `tests/test_outlook.py`

**Tabla: Casos de OL-31**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Todo uid de `search`, `new` y `show`, y `cursor.current.last_uid`, es `outlook:` más 10 caracteres del alfabeto (18 en total), o con sufijo `-<n>`. |
| .02 | P | El mismo mensaje da el mismo uid en corridas sucesivas y también después de borrar `cache.db` cuando ningún otro mensaje con su id corto se registró. |
| .03 | P | `show` y `attachment` resuelven el uid impreso por `search` y por `new`. |
| .04 | P | El id corto es `short_id(<EntryID en mayúsculas>, 10)`; `native_order_key` sigue siendo el `EntryID` y el orden con la misma fecha no cambia. |
| .05 | P | Las claves de las respuestas de `search`, `new`, `show`, `attachment`, `mailboxes` y `doctor` en Windows son las mismas que en macOS con solo `apple_mail`, y ninguna salida tiene una clave `short_id` ni `seq` a ningún nivel. |
| .06 | P | `search`, `new`, `show` y `attachment` crean `~/.mailquery/db/cache.db` en un home nuevo, también `search --count`, que no registra filas; `mailboxes`, `doctor` y `--version` no lo crean. |

#### OL-32 — Validación y resolución del uid en Windows

Requisitos: RF-81, RF-25, RF-38, AC-63, AC-69 · Archivo: `tests/test_outlook.py`

**Tabla: Casos de OL-32**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Un `EntryID` como uid, con prefijo o sin él, en `show` y en `attachment` ⇒ `E_USAGE` con `invalid uid part '<id>': expected a short id` y el hint de D-05, sin crear el home ni la caché. |
| .02 | N | Id corto en mayúsculas, sufijos `-1`, `-02` y `-0`, 9 u 11 caracteres o un carácter fuera del alfabeto (`i`, `l`, `o`, `u`) ⇒ el mismo `E_USAGE`, sin crear la caché. |
| .03 | P | El uid legado sin prefijo (id corto) se resuelve con el driver nativo y `show` devuelve el uid prefijado; la forma con sufijo `-2` es válida. |
| .04 | N | Una forma válida que no está en la caché ⇒ `E_USAGE` con `message uid … was not found` y el hint de repetir la búsqueda, en `show` y en `attachment`. |
| .05 | N | `show` y `attachment` sin `~/.mailquery/db/` ni `cache.db` ⇒ crean los dos, con la base vacía, y responden `message uid … was not found` con el hint de repetir la búsqueda. |
| .06 | N | Con el driver `outlook`, en `search`, `show` y `attachment`: base bloqueada (tope acortado) ⇒ `E_LOCKED` (exit 5); sin permiso ⇒ `E_PERMISSION` (exit 3); archivo que no es una base válida ⇒ `E_IO` (exit 3) con el hint de D-05. |
| .07 | B | Con el driver `outlook`, un `cache.db` vacío (0 bytes) se inicializa y `search` responde con exit 0 y registra los impresos. |

#### OL-33 — Registro de impresos en Outlook

Requisitos: RF-82, RF-80, AC-65 · Archivo: `tests/test_outlook.py`

**Tabla: Casos de OL-33**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `search --limit 2` con 5 candidatos registra exactamente los 2 impresos. |
| .02 | P | `search --group-by from` registra exactamente los mensajes de los grupos impresos. |
| .03 | P | `new` registra los impresos; `new --peek` también y no escribe `state.json`. |
| .04 | N | `search --count` no registra filas (el archivo existe y sus tablas están vacías); una respuesta sin mensajes no registra nada. |
| .05 | N | Si el registro falla (conflicto inyectado o base bloqueada), el comando falla con `E_IO` o `E_LOCKED`, la salida no tiene mensajes y `new` no escribe `state.json`. |
| .06 | N | Un mensaje leído pero descartado por un filtro (`--from`) no se registra. |

#### UT-UID-03 — Apple Mail sin caché de ids nativos

Requisitos: RF-81, AC-63 · Archivo: `tests/test_uid.py`

**Tabla: Casos de UT-UID-03**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Con solo `apple_mail`, el uid sigue siendo `apple_mail:<n>` y, tras `search`, `new`, `show` y `attachment`, no existen `~/.mailquery/db/` ni `cache.db`. |

Tests que cambian (el orquestador ya marcó `[por actualizar]` los que tienen ID):

- OL-14.01: el uid es el id corto de 10 caracteres del `EntryID` permanente; `native_order_key` es el `EntryID` permanente en mayúsculas, no el id de la tabla.
- OL-23.01: un `EntryID` o un id corto en mayúsculas ⇒ `E_USAGE` con `invalid uid part '<id>': expected a short id` y hint no vacío.
- OL-23.03: un uid cuyo `EntryID` resuelto no coincide con ningún store ⇒ `message uid … was not found` con el hint que remite a `excluded_stores`.
- OL-25.01: el estado guarda los uids cortos `outlook:<parte del uid>`.
- UT-UID-01.05: entrada legada en Windows: id corto sin prefijo ⇒ `outlook`.
- UT-UID-02.03: `show <id corto>` sin prefijo en Windows se resuelve con el driver nativo.
- UT-ATC-01.04: `show` no crea caché de adjuntos, staging ni `state.json`; con Apple Mail no escribe nada más, y solo un driver que usa la librería puede escribir en la caché de ids nativos.
- TC-02.02–.06 y TC-09 (goldens de Outlook): solo cambian el uid, `last_uid` y el directorio de `cached_path`.
- Test sin ID de `tests/test_backends.py` sobre `OutlookBackend.parse_uid`: espera la forma corta.
- Cualquier otro test de los archivos del alcance que use un `EntryID` como uid de entrada pasa a sembrar la caché o a tomar el uid de un `search` previo; su expectativa no cambia.

Comandos:

- `$PY -B -m unittest discover -s tests -t . -k ol_31 > "$LOG/grupo-ol_31.log" 2>&1`; igual con `-k ol_32`, `-k ol_33`, `-k ut_uid_03`.
- Goldens: `MAILQUERY_UPDATE_GOLDENS=1 $PY -B -m unittest discover -s tests -t . -k tc_02 > "$LOG/goldens-tc02.log" 2>&1` (y `-k tc_09`), después `git diff --stat tests/fixtures/expected/outlook/` y revisión de cada cambio.
- Suite completa: la de `protocolo.md`.

## Documentación

Ninguna fuera del código: docstrings de `outlook.py` actualizados (uid corto, caché, home), sin citar la unidad ni el plan.

## Actualizaciones de la unidad

Las aplica el orquestador al cerrar el milestone.

- **Conciliación:** según `trazabilidad.md`, aporta a RC-01, RC-02, RC-03, RC-04, RC-05, RC-06, RC-09, RC-10, RC-12, RC-15, RC-16, RC-17, RC-18, RC-20, RC-21, RC-22, RC-27, RC-28, RC-35. Ninguna fila cambia de estado al cerrar este milestone: el orquestador las pasa todas a `implementado` en F4.
- **Documentos consumidores:** ninguno (M07).
- **Checklist:** ninguno cambia.
- **Desviaciones:** ninguna prevista.

## Gates

- `-k ol_31`, `-k ol_32`, `-k ol_33`, `-k ut_uid_03` y `-k tc_02` verdes.
- Suite completa sin fallos nuevos frente a la línea base; `tests/test_readonly.py` y OL-30 verdes.
- `git diff --check` limpio; `git diff --stat` dentro del alcance.
- Cobertura de `backends/outlook.py` informada (o "not run"); la puerta es el 85 % total de la CI.

## Datos crudos de evidencia

Los de `protocolo.md`, más: la lista de goldens regenerados con el tipo de valor que cambió en cada uno, y la lista de tests existentes cambiados con el motivo.

## Definition of Done

- El driver `outlook` emite, acepta y resuelve uids cortos; registra solo los impresos; la caché se abre solo en los comandos que la usan.
- OL-31, OL-32, OL-33 y UT-UID-03 pasan; los casos `[por actualizar]` de la lista pasan con su nueva expectativa; suite sin fallos nuevos.
- Fases en 🟢, registro al día, evidencia cruda escrita.

## Registro de progreso

**Tabla: Registro de progreso de M05**

| Fecha | Fase | Nota |
|---|---|---|
| 2026-11-23 | 1 | `bind_home`, caché perezosa con `NativeIdCache.open`/`open_in_memory`, cierre en `close()` y `SHORT_ID_LENGTH = 10`. |
| 2026-11-23 | 2 | `assign` una vez por `query`, mapa de la ejecución, `_entry_id` con `resolve`, `printed_messages` y `display_native_id`. |
| 2026-11-23 | 3 | `parse_uid`/`parse_native_id` aceptan solo la forma corta; uid sin fila ⇒ `MessageNotFound` con el hint de repetir la búsqueda. |
| 2026-11-23 | 4 | Tests y goldens de Outlook actualizados; tc_02 y tc_09 regenerados con `MAILQUERY_UPDATE_GOLDENS=1` y diff revisado. |
| 2026-11-23 | 5 | OL-31 .01–.06, OL-32 .01–.07, OL-33 .01–.06 y UT-UID-03 .01 en verde, cada uno solo. |
| 2026-11-23 | 6 | Suite completa `Ran 1517 tests`, `OK (skipped=7)`; cobertura de `backends/outlook.py` 89.1 %; diff limpio. |

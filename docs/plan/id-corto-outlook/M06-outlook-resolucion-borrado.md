# M06 — Outlook: resolución, ausente confirmado, colisiones y `--show-native-id`

- **Unidad:** `docs/changes/id-corto-outlook.md` (contribuye; no la completa sola).
- **Oleada / lote:** 4 / 2. **Rama del lote:** `feature/id-corto-outlook-lote-2`. **Rama del milestone:** `feature/id-corto-outlook-m06`, creada desde el tip de la rama del lote (con M04 y M05 integrados).
- **Commit base:** `c2459ea` (tip de `feature/id-corto-outlook-lote-2`, con M01–M05 integrados). **Línea base de la suite:** en `c2459ea`, `Ran 1525 tests`, `OK (skipped=8)`, 0 fallos; los 8 saltos son casos SMOKE/instalador que no aplican en macOS.
- **Depende de:** M04 (opción `--show-native-id`), M05 (uid corto, caché y resolución). **Lo usan:** nadie.
- **ACs:** AC-64 (colisiones de punta a punta y `seq` 3 tras borrar), AC-66 (ausente confirmado e indeterminado, un caso por causa), AC-68 (opción con Outlook), AC-69 (hint de repetir la búsqueda con un mensaje ausente confirmado).

## Objetivo

Completar la resolución de Outlook: borrar la fila solo cuando el mensaje está ausente confirmado, conservarla en cualquier otro caso, y probar de punta a punta las colisiones, la opción `--show-native-id` y el uid corto contra el Outlook real del equipo.

## Alcance

- Clasificación del resultado de abrir el `EntryID` resuelto, compartida por `find_message` y las operaciones de adjuntos:
  - **Ausente confirmado:** el store del `EntryID` es un candidato montado y legible y `GetItemFromID` en ese store falla con un HRESULT de `ITEM_NOT_FOUND_HRESULTS` (`MAPI_E_NOT_FOUND`, `MAPI_E_INVALID_ENTRYID`) ⇒ `discard` de la fila y `MessageNotFound` con el hint de repetir la búsqueda.
  - **Indeterminado:** cualquier otro resultado ⇒ la fila se conserva y el comando responde como hoy (D-18).
- Pruebas de colisión sustituyendo `mailquery.native_ids.short_id` dentro del proceso (D-12), incluido el directorio de adjuntos de cada parte del uid.
- Prueba de `--show-native-id` con Outlook.
- SMOKE-NEW.11 contra el cliente real.

## Fuera de alcance

- Cambios en el núcleo, en la opción o en la librería (M01, M03, M04).
- Documentación consumidora y versión (M07).

## Alcance de escritura

- `src/mailquery/backends/outlook.py`.
- `tests/fakes/outlook.py`, `tests/fakes/run_cli.py`, `tests/test_outlook.py`, `tests/test_smoke.py`.
- `tests/fixtures/expected/outlook/attachment_*.json`, solo si un caso de M06 cambia su valor (con justificación).
- Este archivo (fases y registro), `docs/plan/id-corto-outlook/work/M06-handoff.md`, `docs/plan/id-corto-outlook/work/M06-propuestas.md`.

## Especificación

Rangos de `docs/changes/id-corto-outlook.md` en el commit `384e5a8`:

- "RF-81. Id corto en Outlook" (resolución, hint, resultado de la consulta, borrado a demanda, garantía, sin actualizar ni buscar, sin otra purga, adjuntos con colisión): líneas 145–165.
- "RF-83", condiciones "Qué muestra" a "No sirve como entrada": líneas 189–192.
- "Comando `show` y errores": líneas 317–339.
- "Riesgos": líneas 348–358.
- AC-64: línea 364. AC-66: línea 368. AC-68: línea 372. AC-69: línea 374.
- "Decisiones", entradas sobre el `native_id` que ya no existe, el `seq` de una fila borrada, la ausencia confirmada y el hint: líneas 394, 399, 400 y 404.

## Puntos de entrada en el código

- `src/mailquery/backends/outlook.py` (commit `384e5a8`; busca por nombre lo que movieron M02 y M05): `ITEM_NOT_FOUND_HRESULTS` y `ITEM_UNOPENABLE_HRESULTS` (219–222), `_store_of` (521), `_open_item` (538), `_find_in_tables` (568), `find_message` (963), `_attachment_item` (903), `display_native_id` y `_entry_id` (M05).
- `tests/fakes/outlook.py`: `fail_next` (1800), `hang_next` (1829), `reject_next`, `SCENARIOS` (2439, incluido `not_running`), `FakeNameSpace._call_GetItemFromID` (1241), `StoreSpec` (1034), `FolderSpec` (961), `ItemSpec` (873).
- `tests/fakes/run_cli.py`: opciones `--scenario`, `--home`, `--hang`, `--timeout`.
- `tests/test_outlook.py`: `_OutlookCliCase` (609), `OutlookComErrorTests` (930), tests de OL-21 y OL-23.
- `tests/test_smoke.py`: `SmokeTest` (138), `test_smoke_new_05_show_json` (457), `test_smoke_new_10_doctor_failures` (641).

## Refactorizaciones previas

Ninguna nueva (usa la frontera de M02).

## Decisiones aplicables

- **D-05. Textos literales.** En inglés, comparados literalmente por los tests:
  - `E_LOCKED`: mensaje `the native id cache is locked by another process`; hint `close the process that holds ~/.mailquery/db/cache.db and run the command again`.
  - `E_PERMISSION`: mensaje `no permission to read or write the native id cache`; hint `check the permissions of ~/.mailquery/db/ and ~/.mailquery/db/cache.db`.
  - `E_IO`: mensaje `cannot use the native id cache: <detalle>` (`<detalle>`: `not a valid native id cache`, `conflicting uid part` u otro texto sin datos de correo); hint `if you delete ~/.mailquery/db/cache.db, mailquery creates an empty one; uids already printed do not resolve until you repeat the search`.
  - Forma inválida en Windows: mensaje `invalid uid part '<id>': expected a short id` (`<id>` con `repr`); hint ``Outlook uids are short ids as printed by `mailquery search` and `mailquery new`; run `mailquery search` to find the uid of a message``.
  - Hint de repetir la búsqueda (uid fuera de la caché o mensaje ausente confirmado): ``the uid is not in the native id cache or its message no longer exists; run `mailquery search` or `mailquery new` again to get its current uid``.
- **D-07.** `MessageNotFound(hint)`.
- **D-12.** `SHORT_ID_LENGTH = 10` no se cambia en los tests (la entrada exige 10 caracteres). Para provocar colisiones, los tests sustituyen `mailquery.native_ids.short_id` dentro del proceso (`mock.patch`) por una función que devuelve el mismo id corto válido de 10 caracteres (por ejemplo `k3f9q2m7xa`) para dos o tres `EntryID` elegidos y el cálculo real para el resto. No se hace en subproceso.
- **D-13.** El caso de timeout corre en subproceso con `tests/fakes/run_cli.py --hang …` y después lee `cache.db`.
- **D-18** (respuesta H-03 del dueño, desviación aprobada). Un item que existe pero no se puede abrir es *indeterminado*: la fila se conserva y `show` y `attachment` responden como hoy: `show` arma la fila desde las tablas de su carpeta (OL-21) y, si no aparece, "no encontrado" con el hint actual; `attachment` responde `E_ATTACHMENT_UNREADABLE`.

## Fases

**Tabla: Fases de M06**

| Fase | Tareas | Estado |
|---|---|---|
| 1 | Clasificación ausente confirmado / indeterminado en `find_message` y adjuntos; borrado solo con ausente confirmado | 🟢 |
| 2 | OL-35 (un caso por causa), con el doble y el subproceso para el timeout | 🟢 |
| 3 | OL-34 (colisiones) y OL-36 (`--show-native-id`) | 🟢 |
| 4 | SMOKE-NEW.11 | 🟢 |
| 5 | Suite completa, cobertura, diff, evidencia cruda | 🟡 |

## Tests

Grupos nuevos en `tests/test_outlook.py`, con el doble de Outlook y `HOME` temporal; la fila se siembra con un `search` previo. Las definiciones ya están `[pendiente]` en `docs/tests/outlook-runtime.md` (OL) y `docs/tests/smoke.md` (SMOKE-NEW.11).

#### OL-34 — Colisiones de id corto en Outlook

Requisitos: RF-80, RF-81, AC-64 · Archivo: `tests/test_outlook.py`

**Tabla: Casos de OL-34**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Dos mensajes con el mismo id corto en un mismo `search` reciben `outlook:<id>` y `outlook:<id>-2`, en el orden de su `EntryID`, y `show` de cada uno devuelve su mensaje. |
| .02 | P | `attachment` de cada uno extrae en `attachments/outlook/<id>/` y `attachments/outlook/<id>-2/` y nunca sirve los archivos del otro. |
| .03 | P | Un mensaje que el driver lee en dos consultas de una misma ejecución (primera corrida de `new`) conserva su uid. |
| .04 | P | Con la fila del `-2` borrada por ausencia confirmada, un tercer mensaje con ese id corto recibe `outlook:<id>-3` y `outlook:<id>-2` ya no se resuelve. |

#### OL-35 — Ausente confirmado e indeterminado

Requisitos: RF-81, AC-66, AC-69 · Archivo: `tests/test_outlook.py`

**Tabla: Casos de OL-35**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Store montado y `GetItemFromID` con `MAPI_E_NOT_FOUND` o `MAPI_E_INVALID_ENTRYID` ⇒ `message uid … was not found` con el hint de repetir la búsqueda y la fila desaparece, en `show` y en `attachment`; el directorio `attachments/outlook/<parte del uid>/` que existiera sigue en disco. |
| .02 | N | Outlook cerrado ⇒ el error actual de Outlook no abierto; la fila sigue. |
| .03 | N | Outlook que no responde (rechazo repetido) ⇒ `E_CLIENT_BUSY`; la fila sigue. |
| .04 | N | Sin conexión (`MAPI_E_NETWORK_ERROR`) ⇒ su error actual; la fila sigue. |
| .05 | N | Store del `EntryID` no montado (fuera del perfil) ⇒ `message uid … was not found` con el hint actual; la fila sigue. |
| .06 | N | Store ilegible ⇒ el comportamiento actual; la fila sigue. |
| .07 | N | Item que existe pero no se puede abrir (`E_FAIL`) ⇒ como hoy: `show` responde con la fila de las tablas de su carpeta y `attachment` con `E_ATTACHMENT_UNREADABLE` (D-18); la fila sigue. |
| .08 | N | Item que no es un correo ⇒ "no encontrado" con el hint actual; la fila sigue. |
| .09 | N | Item en una carpeta oculta ⇒ "no encontrado" con el hint actual; la fila sigue. |
| .10 | N | Item marcado para borrar ⇒ "no encontrado" con el hint actual; la fila sigue. |
| .11 | N | Otro error COM (`E_UNEXPECTED`) ⇒ su error actual; la fila sigue. |
| .12 | N | Timeout de COM (subproceso con `--hang`) ⇒ `E_CLIENT_TIMEOUT`; la fila sigue. |
| .13 | N | Store excluido ⇒ `E_ACCOUNT_NOT_IN_SCOPE`; la fila sigue. |
| .14 | N | Tras todos los casos anteriores, ninguna fila de `cache_native_ids` cambió de `native_id`. |
| .15 | N | Mensaje movido de carpeta (su `EntryID` cambia en el doble): su uid anterior ⇒ ausente confirmado, "no encontrado" con el hint de repetir la búsqueda y fila borrada; un `search` nuevo le da otro uid; ninguna fila cambió de `native_id`. |

#### OL-36 — `--show-native-id` en Outlook

Requisitos: RF-83, AC-68 · Archivo: `tests/test_outlook.py`

**Tabla: Casos de OL-36**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `show <uid> --show-native-id` ⇒ `message.uid` es `outlook:<EntryID>`; las demás claves y valores, `cache.db` y `cached_path` son los mismos que sin la opción. |
| .02 | N | Ese `outlook:<EntryID>`, o el `EntryID` sin prefijo, como entrada de `show` o de `attachment` ⇒ `E_USAGE`. |
| .03 | P | Los textos de warnings y errores siguen llevando el uid corto. |

#### SMOKE-NEW.11 — uid corto contra el cliente real

Requisitos: AC-63, AC-68, AC-69 · Archivo: `tests/test_smoke.py` (caso nuevo del grupo SMOKE-NEW)

**Tabla: Casos de SMOKE-NEW.11**

| Caso | Tipo | Verifica |
|---|---|---|
| .11 | P | En Windows con Outlook abierto: los uids de `search --since 1w` son `outlook:` más 10 caracteres del alfabeto (o con sufijo); `show` del primero responde con exit 0; existe `db/cache.db` en el HOME temporal; `show --show-native-id` da `outlook:` más hexadecimal en mayúsculas; los no leídos no cambian. En macOS: tras `search` y `show`, no existe `db/cache.db`. Donde no aplica, se salta con el motivo de la sección 6 de `infrastructure.md`. |

Tests que cambian:

- OL-30 (gate de solo lectura de Outlook, ya `[por actualizar]`): su barrido de comandos y opciones incluye `show --show-native-id`; la expectativa (cero mutaciones) no cambia.
- Si OL-21 o OL-23 necesitan otra siembra de la caché, cambian sus datos, no su expectativa.

Comandos:

- `$PY -B -m unittest discover -s tests -t . -k ol_34 > "$LOG/grupo-ol_34.log" 2>&1`; igual con `-k ol_35`, `-k ol_36`, `-k smoke_new_11`.
- Suite completa: la de `protocolo.md` (incluye los SMOKE, que en este equipo corren contra el Outlook real en solo lectura).

## Documentación

Ninguna fuera del código: docstrings de la clasificación y del borrado.

## Actualizaciones de la unidad

Las aplica el orquestador al cerrar el milestone.

- **Conciliación:** según `trazabilidad.md`, aporta a RC-01, RC-06, RC-15, RC-18, RC-21, RC-23, RC-27, RC-34, RC-35, RC-38. Ninguna fila cambia de estado al cerrar este milestone: el orquestador las pasa todas a `implementado` en F4.
- **Documentos consumidores:** ninguno.
- **Checklist:** CL-10 queda listo para verificarse al conciliar (OL-35 tiene un caso por causa); su estado no cambia hasta la conciliación.
- **Desviaciones:** ninguna prevista.

## Gates

- `-k ol_34`, `-k ol_35`, `-k ol_36` verdes; `-k smoke_new_11` verde o saltado con motivo.
- Suite completa sin fallos nuevos frente a la línea base; `tests/test_readonly.py` y OL-30 verdes.
- `git diff --check` limpio; `git diff --stat` dentro del alcance.
- Cobertura de `backends/outlook.py` informada (o "not run"); la puerta es el 85 % total de la CI.

## Datos crudos de evidencia

Los de `protocolo.md`, más: la tabla de causas de OL-35 con el código de error obtenido en cada una, y el resultado de SMOKE-NEW.11 (exit, longitudes de uid y recuentos; nunca valores de uid, `EntryID` ni datos del correo).

## Definition of Done

- Solo la ausencia confirmada borra filas; cada causa de indeterminado conserva la fila y el comportamiento actual.
- OL-34, OL-35, OL-36 y SMOKE-NEW.11 pasan (o SMOKE saltado con motivo); suite sin fallos nuevos.
- Fases en 🟢, registro al día, evidencia cruda escrita.

## Registro de progreso

**Tabla: Registro de progreso de M06**

| Fecha | Fase | Nota |
|---|---|---|
| 2026-11-23 | 1 | `_open_candidate` distingue ausente confirmado (store montado y legible, `GetItemFromID` con `MAPI_E_NOT_FOUND`/`MAPI_E_INVALID_ENTRYID`) de indeterminado; `_discard_absent` borra la fila; `find_message` y `_attachment_item` comparten la clasificación. |
| 2026-11-23 | 2 | OL-35.01–.15 verdes, un caso por causa; .12 en subproceso con `--hang NameSpace.GetItemFromID` y lectura de `cache.db`. OL-23.03 queda con el caso de store no montado, que es el de su definición; el item inexistente en store montado pasa a OL-35.01. |
| 2026-11-23 | 3 | OL-34.01–.04 verdes (colisión con `mock.patch` en proceso, ambos directorios de adjuntos, `seq` 3 tras borrar) y OL-36.01–.03 verdes. |
| 2026-11-23 | 4 | SMOKE-NEW.11 verde en este equipo (macOS): `search` y `show` reales no crean `db/cache.db`. |

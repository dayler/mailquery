# M02 — Refactor: frontera uid ↔ `EntryID` en el driver `outlook`

- **Unidad:** `docs/changes/id-corto-outlook.md` (contribuye; no la completa sola).
- **Oleada / lote:** 1 / 1. **Rama del lote:** `feature/id-corto-outlook-lote-1`. **Rama del milestone:** `feature/id-corto-outlook-m02`, creada desde el tip de la rama del lote.
- **Commit base:** (te lo da el orquestador al lanzar; lo copias aquí en tu primer commit). **Línea base de la suite:** (te la da el orquestador al lanzar, con los fallos y saltos conocidos; la copias aquí).
- **Depende de:** nada. **Lo usan:** M05 y M06.
- **ACs:** ninguno. Refactor sin cambio de comportamiento.

## Objetivo

Separar dentro de `OutlookBackend` la parte del uid que ve el núcleo del `EntryID` que el driver usa por dentro, con dos funciones de traducción que hoy son la identidad, para que M05 cambie el uid tocando solo esas dos funciones.

## Justificación

Hoy el `EntryID` es a la vez el uid emitido, la clave de orden y la clave de las cachés internas (`_uid_folders`, `_items`, `_last_item`, `_opened`, `_recipient_cache`) y lo que reciben `GetItemFromID` y la búsqueda en tablas. Cambiar el uid sin esta separación obligaría a tocar a la vez la emisión, la resolución y una docena de operaciones (riesgo R-01). El refactor es acotado (un archivo de código) y conserva el comportamiento: la suite existente pasa sin cambios.

## Alcance

- Dos métodos privados en `OutlookBackend`: `_entry_id(uid_part: str) -> str` y `_uid_part(entry_id: str) -> str`, ambos la identidad en este milestone.
- Cada operación que recibe un uid del núcleo lo traduce a `EntryID` al entrar: `membership`, `recipients`, `attachment_names`, `attachments`, `attachment_stream`, `find_message`, `load_body`, `load_headers`, `load_snippet`, `unreadable_attachments` (las que reciben una fila usan `row["native_order_key"]` o traducen `row["uid"]`).
- Cada fila emitida (`_message_row`) lleva `uid = _uid_part(entry_id)` y `native_order_key = entry_id`, explícitos.
- `_order_key` (orden de las filas de `query`, cerca del final del archivo) ordena por `native_order_key` en lugar de `row["uid"]`; hoy son el mismo valor, así que el orden no cambia.
- Las cachés internas y los mapas quedan indexados por `EntryID`; las respuestas al núcleo que llevan uids como claves (`membership`, `recipients`) usan la parte del uid.
- Los textos de warnings que llevan un uid (`_unopenable_warning` y similares) usan la parte del uid.
- Un test sin ID que sustituye las dos funciones por una traducción reversible que no conserva el orden y comprueba el recorrido completo llamando a las operaciones del backend.

## Fuera de alcance

- La caché de ids nativos, la validación nueva y cualquier cambio visible (M05, M06).
- Cambios en el núcleo o en otros drivers.

## Alcance de escritura

- `src/mailquery/backends/outlook.py`.
- `tests/test_outlook.py` (solo el test nuevo sin ID).
- Este archivo (fases y registro), `docs/plan/id-corto-outlook/work/M02-handoff.md`, `docs/plan/id-corto-outlook/work/M02-propuestas.md`.

## Especificación

Rangos de `docs/changes/id-corto-outlook.md` en el commit `384e5a8`:

- "Solución elegida": líneas 28–35.
- "Modelo de datos" (el orden total sigue siendo el `EntryID`): líneas 311–315.

## Puntos de entrada en el código

En `src/mailquery/backends/outlook.py` (commit `384e5a8`):

- `OutlookBackend.__init__` (línea 366): cachés internas.
- `_message_row` (línea 493): hoy `uid=uid, native_order_key=uid`.
- `_store_of` (línea 521), `_open_item` (línea 538), `_find_in_tables` (línea 568): trabajan con `EntryID`.
- `query` (línea 674), `membership` (719), `recipients` (743), `attachment_names` (777), `attachments` (790), `attachment_stream` (840), `_attachment_item` (903), `find_message` (963), `load_body` (998), `load_headers` (1018), `_load_body` (1046), `load_snippet` (1117), `unreadable_attachments` (1125).
- `_unopenable_warning` (línea 1982) y demás textos con uid.
- `_order_key` (líneas 2025–2028): hoy ordena por `row["uid"]`.
- `tests/test_outlook.py`, helper `_backend` (línea 575).

## Refactorizaciones previas

Este milestone es la refactorización.

## Decisiones aplicables

Ninguna de `decisiones.md` le aplica. Regla: ningún comportamiento observable cambia (salida JSON, logs, llamadas al doble de Outlook registradas en su `CallLog`, goldens).

## Fases

**Tabla: Fases de M02**

| Fase | Tareas | Estado |
|---|---|---|
| 1 | Inventario de los usos del uid en `outlook.py` (lista en la evidencia cruda) | ⚪ |
| 2 | `_entry_id`/`_uid_part`, traducción en cada operación de entrada y en la emisión; cachés por `EntryID` | ⚪ |
| 3 | Test sin ID con traducción reversible; suite completa sin cambios en tests existentes | ⚪ |
| 4 | Diff, evidencia cruda | ⚪ |

## Tests

- **Test nuevo sin ID** en `tests/test_outlook.py` (por ejemplo `test_uid_translation_boundary_round_trip`): con `mock.patch.object` sobre `_uid_part` y `_entry_id` con una traducción reversible que no conserva el orden (por ejemplo, el `EntryID` invertido), sobre el escenario `default` del doble y llamando directamente a las operaciones del backend (no a `cli.main`, porque la validación de entrada de hoy solo acepta hexadecimal en mayúsculas): `query` emite uids traducidos; `find_message`, `recipients`, `membership`, `attachments` y `load_body` de esos uids funcionan; `native_order_key` de cada fila sigue siendo el `EntryID`; el orden de `query` es el mismo que sin la traducción; el texto de un warning de item ilegible lleva la parte traducida.
- **Tests que cambian:** ninguno; si un test existente necesitara cambiar, el refactor no conserva el comportamiento y se devuelve como contradicción.
- Comandos: `$PY -B -m unittest tests.test_outlook > "$LOG/test_outlook.log" 2>&1` y la suite completa de `protocolo.md`.

## Documentación

Ninguna. Docstrings de las funciones nuevas en inglés.

## Actualizaciones de la unidad

- **Conciliación:** según `trazabilidad.md`, ninguna fila (prepara el código de RC-03, RC-12 y RC-15, que completan M05 y M06).
- **Documentos consumidores, checklist y desviaciones:** ninguno.

## Gates

- Suite completa sin fallos nuevos frente a la línea base y sin cambios en tests existentes.
- `git diff --stat <base>...HEAD`: solo `outlook.py`, `test_outlook.py` y los archivos propios del plan.
- `git diff --check <base>...HEAD` limpio.

## Datos crudos de evidencia

Los de `protocolo.md`, más el inventario de la fase 1 (función, línea y si recibe uid del núcleo, emite uid o usa `EntryID`).

## Definition of Done

- Toda entrada de uid del núcleo pasa por `_entry_id` y toda emisión por `_uid_part`; las cachés internas usan `EntryID`.
- El test de traducción reversible pasa; la suite completa pasa sin cambios en los tests existentes.
- Fases en 🟢, registro al día, evidencia cruda escrita.

## Registro de progreso

**Tabla: Registro de progreso de M02**

| Fecha | Fase | Nota |
|---|---|---|

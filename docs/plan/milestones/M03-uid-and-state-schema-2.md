# M03 — uid prefijado en comandos y `state.json` schema 2

| Campo | Valor |
|-------|-------|
| Fase | B — Identidad y configuración |
| Depende de | M01, M02 |
| Bloquea a | M04, M06–M11 |
| ACs | AC-05 (comandos y estado), AC-06 |
| Grupos de test | UT-ST-06, UT-ST-07, UT-UID-02; actualización de UT-CLI-07, UT-CLI-09, UT-CLI-11, UT-SR-07/08/11, TC-03, tests de Outlook (`message_of`/`show`/`uids`/`check_state_uid`) y de todos los tests que siembran uids |
| Write scope | `src/mailquery/state.py`, `src/mailquery/search.py` (emisión de uid, orden y cursor; no merge multi-driver), `src/mailquery/cli.py` (solo validación de uid de `show` y chequeo `state` de `doctor`), `src/mailquery/backends/base.py` y `backends/apple_mail.py`/`backends/outlook.py` (retirar `check_state_uid` y usar `parse_native_id`), `docs/INTERFACES.md`, `tests/test_state.py`, `tests/test_uid.py`, `tests/test_search.py`, `tests/test_cli.py`, `tests/test_backends.py` (solo `check_state_uid`), `tests/test_integration.py`, `tests/test_readonly.py` (solo TC-03), `tests/test_outlook.py` (uid, `show`, `message_of` y `check_state_uid`), `tests/fixtures/expected/**` (uid; ver §4) |
| No tocar | `config.py`, `plugins/**`, `attachments/**` (no existe aún), `PRD.md`, `PRD-v2.1.md`, `docs/plan/**` |
| Estado | ⚪ |

## 1. Objetivo

Cambiar la representación del `uid` a `string` opaco `"<driver>:<native_id>"` en todas las salidas y en `state.json` (schema 2), con migración determinista desde schema 1, y conservar la aceptación del uid legado en la entrada. Se mantiene un solo driver por comando: el merge multi-driver es M04.

## 2. Contexto normativo

- PRD-v2.1 §6.1 RF-37 (solo orden total), RF-40, §10.2 puntos 1, 4, 5, 6, 7 y 8 (uid, schema 2, migración, validación, orden total, cursor), §11.3 filas 1–2 y 7, §11.9 (sin cambios), §14 AC-05/AC-06.
- Base 2.0.1: `state.py:29-35` (`STATE_SCHEMA=1`), `state.py:96-123` (load), `state.py:125-182` (save atómico), `state.py:371-447` (validación), `state.py:184-232,450-462` (cursor/anillo), `state.py:469-477` (corrupto), `search.py:361-364` (`new` reordena ASC), `search.py:965-1030` (dedupe y orden), `search.py:471-493,518` (`show.attachments`), `cli.py:428-461` (validación de uid de `show`), `cli.py:969-990` (chequeo `state`), `backends/apple_mail.py:293-327`, `backends/outlook.py:877-908` (`parse_uid`/`check_state_uid`).

## 3. Tareas

| ID | Tarea | Archivos | Detalle |
|----|-------|----------|---------|
| M03-T01 | `state.json` schema 2 y migración | `state.py`, `backends/*.py` | `STATE_SCHEMA = 2`; el anillo y `cursor.last_uid` guardan uids prefijados. Al cargar `schema: 1`, migrar en memoria con una **función pura** determinista por el tipo del valor: entero ≥ 1 ⇒ `apple_mail:<n>`; string hexadecimal en mayúsculas ⇒ `outlook:<HEX>`; `0`, negativos, otros tipos o formatos ⇒ `E_STATE_CORRUPT` con el hint de renombrar. La migración no depende del SO ni del registro; la validación posterior de schema 2 sí (driver instalado). `--peek` migra en memoria y no escribe; la primera corrida de `new` que no sea `--peek` persiste schema 2 con la escritura atómica existente. Validación de schema 2: `cursor.last_uid` con driver no instalado ⇒ `E_STATE_CORRUPT` (hint: reinstalar el plugin o renombrar); los elementos de `emitted_uids` con driver no instalado se podan en silencio; un uid migrado que exceda 1024 caracteres ⇒ `E_STATE_CORRUPT`. El validador por backend (`check_state_uid`) se retira: la forma se valida con `uid.py` y el driver resuelve su parte nativa con `parse_native_id`; se conserva un shim temporal solo si un test existente no se puede actualizar en este milestone. |
| M03-T02 | Emisión de uid prefijado | `search.py` | `search`, `new` y `show` emiten `uid` string `"<driver>:<native_id>"`; `cursor.previous/current.last_uid` también. La deduplicación por `message_id` se mantiene **dentro del driver** (RF-07 de PRD.md); a igual fecha el desempate usa `(driver ASC, native_order_key DESC)` en `search`/`show` y `(driver ASC, native_order_key ASC)` en `new`, sin comparar el uid como texto; `native_order_key` llega en la fila del backend según C1 (M01). En este milestone el driver es único; M04 extiende el merge. |
| M03-T03 | Entrada de uid legado | `cli.py`, `search.py` | `show` valida el uid con el formato nuevo antes de crear el home/leer config/abrir store; acepta el uid legado sin prefijo resuelto con el driver nativo. Un uid malformado ⇒ `E_USAGE`; un driver no instalado ⇒ `E_DRIVER_UNKNOWN`. En `show`, un driver instalado pero no declarado en `[scope]` ⇒ `E_ACCOUNT_NOT_IN_SCOPE` sin cargarlo (helper de M02). |
| M03-T04 | Chequeo `state` de `doctor` | `cli.py` | Mientras la migración no se haya persistido, `state` muestra `schema: 1 (migration pending)`; después de persistida, schema 2. El chequeo conserva su `ok` y su detalle de cursor con el uid prefijado. Informa de los `emitted_uids` podados por driver no instalado (conteo y drivers, sin uids) y distingue el cursor inválido por driver no instalado. `doctor` no escribe estado. |
| M03-T05 | Tests y goldens | `tests/test_state.py`, `tests/test_uid.py`, `tests/test_search.py`, `tests/test_cli.py`, `tests/test_backends.py`, `tests/test_integration.py`, `tests/test_readonly.py`, `tests/test_outlook.py`, `tests/fixtures/expected/**` | UT-ST-06/07, UT-UID-02. Sembrar uids prefijados en los fixtures (`new_seeded`, seeds de `state`) y actualizar los goldens listados en §4. Radio de impacto enumerado (no genérico): `test_integration.py:297` (`assertIsInstance(uid, int)`), `DEFAULT_UID_ORDER` y las comparaciones de uid en `:453,530,548,624-646,667-677,700,717,735,746,760,769,774,790,898`; `test_search.py:354` (helper `uids()`) y las 21 comparaciones literales `:414-1071`; `test_state.py:61-71` (roundtrip schema 1), `:175` (schema 2 ya válido), `:226-246` (mensajes W0), `:405` (UT-ST-03.04); `test_cli.py:1344-1360` (UT-CLI-11.02, `last_uid=42`), `:1587` (uid entero en `show`) y `:758-784` (UT-CLI-09.01); `test_readonly.py:200-205` (TC-03.01); `test_outlook.py:877` (ya en M01), `:2218,2288,2548,2633` (`message_of`/`show`/`uids`), `:3542,3626` (`check_state_uid`). Los tests que hoy esperan `uid` entero o `check_state_uid` se renombran/ajustan, no se duplican; se añade un helper común `prefixed_uid` para construir expectativas. |
| M03-T06 | Documentación del contrato | `docs/INTERFACES.md` | Documentar `uid` string, schema 2, migración, validación, orden total de un driver y aceptación del uid legado. |

## 4. Casos de prueba

### UT-ST-06 — Migración schema 1 → 2 (AC-06)

- .01 P Función pura de migración: enteros ≥ 1 en `cursor.last_uid` y `emitted_uids` ⇒ `apple_mail:<n>`, sin depender del SO.
- .02 P Strings hexadecimales en mayúsculas ⇒ `outlook:<HEX>`; mayúsculas/minúsculas no se reinterpretan (un valor inválido cae en .03). Estos dos casos prueban la función pura o inyectan un registro con ambos drivers para que la validación posterior no dependa de la plataforma.
- .03 N Valor no entero, no hex en mayúsculas, `0`, negativo, `None`, lista ⇒ `E_STATE_CORRUPT` con hint de renombrar; un entero migrado cuyo driver no está instalado ⇒ `E_STATE_CORRUPT` en la validación de schema 2 (caso separado).
- .04 P `new --peek` migra en memoria, no escribe y responde con el cursor migrado.
- .05 P La siguiente corrida de `new` no `--peek` persiste schema 2 con la escritura atómica; el original solo se reemplaza al final.
- .06 P `doctor` informa `schema: 1 (migration pending)` hasta la persistencia y schema 2 después.
- .07 P Ciclo de vida DP-03 (estado): desinstalar un plugin deja su `cursor.last_uid` en `E_STATE_CORRUPT`, poda sus uids del anillo y `doctor state` informa la poda sin romper `new` por los elementos podados.

### UT-ST-07 — Validación schema 2 y poda (AC-06)

- .01 N `cursor.last_uid` que no es string prefijado, o con formato inválido, o > 1024 ⇒ `E_STATE_CORRUPT`.
- .02 N `cursor.last_uid` de un driver no instalado ⇒ `E_STATE_CORRUPT` con hint (reinstalar el plugin o renombrar el estado).
- .03 P `emitted_uids` con drivers no instalados se podan en silencio; `new` no falla y `doctor` lo reporta en el detalle de `state`.
- .04 N Un uid migrado de 1025 caracteres ⇒ `E_STATE_CORRUPT` (después de migrar en memoria).
- .05 P `schema` ausente, booleano o distinto de 1/2 ⇒ `E_STATE_CORRUPT`.

### UT-UID-02 — uid prefijado en comandos (AC-05)

- .01 P `search`, `new` y `show` emiten `uid` string con el prefijo del driver nativo; `new` emite `cursor.previous/current.last_uid` igual.
- .02 P Orden de `search`/`show` por `(date_received DESC, driver ASC, native_order_key DESC)` y de `new` ASC; con Apple Mail el orden numérico no cambia respecto de 2.0.1. `native_order_key` se toma de la fila del backend (C1), nunca del texto del uid.
- .03 P Entrada legada: `show 83143` en macOS y `show <EntryID hex>` en Windows se resuelven con el driver nativo y devuelven el uid prefijado.
- .04 N `show` malformado ⇒ `E_USAGE`; driver desconocido ⇒ `E_DRIVER_UNKNOWN`; ambos antes de crear el home, leer config o abrir el store, sin escribir estado ni caché.
- .05 N `show` con prefijo de un driver instalado pero no declarado ⇒ `E_ACCOUNT_NOT_IN_SCOPE` sin cargar el driver.
- .06 N Un `state.json` con uid legado válido no se reescribe en comandos de solo lectura (`search`, `show`, `mailboxes`, `doctor`).

### Actualizaciones de tests existentes

- `UT-CLI-07` (formato del uid de `show`): textos nuevos, casos de prefijo y legado; eliminar la expectativa de entero.
- `UT-CLI-09` (matriz de exit): se amplía en M01; aquí solo se comprueba que los códigos del uid (`E_USAGE`/`E_DRIVER_UNKNOWN`) conservan su exit.
- `UT-CLI-11.02` (`last_uid=42`): pasa a `apple_mail:42`.
- `UT-SR-07/08` (`new` y lookback): cursor y anillo prefijados; la semántica de la ventana no cambia.
- `UT-SR-11` (`show` y alcance): uid prefijado en la entrada y en la salida.
- `TC-03.01` (`tests/test_readonly.py:200-205`): uids enteros 2714/83170 y conjunto `{83160,83170}` pasan a prefijados.
- `tests/test_outlook.py`: `message_of`/`show`/`uids` (`:2218,2288,2548,2633`) y las construcciones de `StateStore(..., OutlookBackend.check_state_uid)` (`:3542,3626`) usan uid prefijado y el validador nuevo.
- `test_state.py`: roundtrip schema 1 (`:61-71`), `schema=2` válido (`:175`), mensajes W0 (`:226-246`) y UT-ST-03.04 (`:405`, entero corrupto en Windows) se sustituyen por la migración por tipo decidida (D8).
- Seeds de `test_integration.py` (`_seed_cursor`, `DEFAULT_UID_ORDER`), `golden new_seeded.json` y el helper `uids()` de `test_search.py`.

### Goldens que cambian en este milestone

`search_default.json`, `search_all_mail.json`, `new_first_run.json`, `new_seeded.json`, `show_2714.json`, `show_83170.json`, `show_83180.json`, `show_smime_encrypted.json`, `show_not_in_scope_error.json`, y los 5 de Outlook con uid (`outlook/new_first_run.json`, `outlook/search.json`, `outlook/show.json`, `outlook/show_header_only.json`, `outlook/show_smime.json`). `mailboxes` y `doctor` no cambian por este milestone (`doctor` ya cambió en M02). En este milestone el diff de los `show_*` es **solo el uid**; la forma/valor de `attachments` se cambia una sola vez en M08 (excepto `show_smime_encrypted`, que además cambia a `[]` en M08). M09 y M10 no editan estos goldens.

## 5. Documentación del milestone

- `docs/INTERFACES.md`: modelo de `uid`, schema 2, migración, validación, orden total de un driver, aceptación del uid legado y retirada de `check_state_uid`.

## 6. Criterios de cierre

1. Suite verde sin fallos nuevos; UT-ST, UT-UID y los tests renombrados verdes solos.
2. Un `state.json` schema 1 real del fixture migra a schema 2 y `new` produce el cursor prefijado correcto.
3. Los comandos de solo lectura no escriben estado; `--peek` no escribe; TC-03.01 verde con uids prefijados.
4. Los goldens con uid quedan actualizados y ningún test conserva comparaciones de uid entero ni `check_state_uid` (salvo el shim declarado).

## 7. Handoff y HITL

- Reportar: forma final de `state.json`, decisión sobre `check_state_uid` (retirado), goldens actualizados, tests renombrados.
- HITL: solo si un `state.json` schema 1 real del dueño contiene un tipo de uid no contemplado por D8 (no entero ≥ 1 ni hex mayúsculas); no se pregunta por `native_order_key`, que ya está en C1.

## 8. Riesgos del milestone

| Riesgo | Mitigación |
|---|---|
| Un `state.json` schema 1 con datos no representables deja al usuario sin cursor | `E_STATE_CORRUPT` con hint de renombrar; la siguiente corrida es primera corrida y emite la ventana (comportamiento del PRD.md §12.3) |
| Cambiar el orden rompe goldens de Apple Mail | El orden numérico de Apple Mail es el mismo; solo cambia la representación del uid |
| Tests de Outlook corren en los 3 SO con el fake | La emisión del prefijo es del núcleo; los goldens de Outlook se regeneran con el fake y no requieren Windows |

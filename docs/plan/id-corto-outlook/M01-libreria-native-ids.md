# M01 — Librería `native_ids.py`

- **Unidad:** `docs/changes/id-corto-outlook.md` (contribuye; no la completa sola).
- **Oleada / lote:** 1 / 1. **Rama del lote:** `feature/id-corto-outlook-lote-1`. **Rama del milestone:** `feature/id-corto-outlook-m01`, creada desde el tip de la rama del lote.
- **Commit base:** `ba07a59`. **Línea base de la suite:** commit `4361e96`, `Ran 1452 tests`, `OK (skipped=8)`, 0 fallos; los 8 saltos son casos SMOKE/instalador que no aplican en macOS.
- **Depende de:** nada. **Lo usan:** M03 (acceso de un plugin), M05 y M06 (driver `outlook`).
- **ACs:** AC-64 (reglas de `seq` en la librería), AC-69 (cálculo, creación, formato, errores, permisos y columnas), AC-70 (acceso de un plugin desde un hilo vigilado).

## Objetivo

Crear la librería del núcleo que calcula ids cortos y guarda la caché de ids nativos en `~/.mailquery/db/cache.db`, con sus errores y su acceso para plugins, sin que ningún comando la use todavía.

## Alcance

- `short_id`, la base SQLite con sus dos tablas y su versión de formato, la creación de carpeta y archivo, los permisos, `assign`, `register`, `resolve`, `discard`, la variante en memoria y `PluginNativeIds`.
- Los errores `E_LOCKED`, `E_PERMISSION` y `E_IO` con los textos de D-05, y su conversión al protocolo de RF-50 en `PluginNativeIds`.

## Fuera de alcance

- Conectar la librería al contexto de plugin y reexportar `short_id` (M03).
- Usarla en el driver `outlook` (M05, M06).
- Documentación consumidora (M07).

## Alcance de escritura

- `src/mailquery/native_ids.py` (nuevo).
- `tests/test_native_ids.py` (nuevo).
- Este archivo (fases y registro), `docs/plan/id-corto-outlook/work/M01-handoff.md`, `docs/plan/id-corto-outlook/work/M01-propuestas.md`.

## Especificación

Rangos de `docs/changes/id-corto-outlook.md` en el commit `384e5a8`:

- "RF-80. Librería de ids cortos y caché de ids nativos": líneas 109–143.
- "Arquitectura", diagrama y operaciones: líneas 225–268.
- "Caché de ids nativos" (tablas y reglas del archivo): líneas 270–309.
- "Requisitos existentes que cambian", punto RNF-05: línea 210.
- AC-64: línea 364. AC-69: línea 374. AC-70: línea 376.
- "Decisiones", entradas del 2026-11-22 sobre errores, `seq` y creación: líneas 397–403.

## Puntos de entrada en el código

- `src/mailquery/errors.py`, códigos `E_PERMISSION`/`E_IO` (líneas 34–51) y `MailqueryError` (línea 78): constructor de los errores.
- `src/mailquery/state.py`, `_chmod` (línea 646) y `RunLock` (línea 357): forma actual de aplicar 0700/0600 y de dar `E_LOCKED`.
- `src/mailquery/config.py`, `ensure_app_home` (línea 200): permisos del home.
- `src/mailquery/plugins/api.py`, `PluginError`, `Reason` (líneas 117–190), `call_driver` (línea 674) y `map_plugin_error` (línea 396): protocolo de RF-50 que usa `PluginNativeIds` y que los tests de UT-NID-04 atraviesan.
- `src/mailquery/uid.py`: estilo del módulo (puro, `__all__`, docstrings).

## Refactorizaciones previas

Ninguna.

## Decisiones aplicables

- **D-04. API de la librería.** En `src/mailquery/native_ids.py`:
  - `short_id(text: str, length: int) -> str`; `length` fuera de 1…51 o `text` que no es `str` ⇒ `ValueError`.
  - `cache_path(home: Path) -> Path` = `home / "db" / "cache.db"`.
  - `NativeIdCache.open(driver: str, *, home: Path) -> NativeIdCache` y `NativeIdCache.open_in_memory(driver: str) -> NativeIdCache`.
  - Métodos: `assign(native_ids: Sequence[str], *, length: int = 10) -> dict[str, str]`, `register(native_ids: Sequence[str]) -> None`, `resolve(uid_part: str) -> str | None`, `discard(native_id: str) -> None`, `close() -> None`.
  - `PluginNativeIds(home: Path, driver: str)`: acceso de un plugin con `assign`, `register`, `resolve`, `discard` y `close`; abre la base en la primera operación (D-08), es seguro entre hilos (D-15) y convierte sus fallos con el protocolo de RF-50: base ocupada ⇒ `PluginError(Reason.BUSY)`, sin permiso ⇒ `PluginError(Reason.PERMISSION)`, cualquier otro fallo ⇒ una excepción que no es `PluginError` (el núcleo la convierte en `E_PLUGIN_FAILED`).
  - `assign` llama a `short_id` por su nombre del módulo (`native_ids.short_id`), de modo que un test puede sustituirla con `mock.patch("mailquery.native_ids.short_id", …)`.
  - Clasificación de fallos: `E_PERMISSION` si `mkdir`/`chmod` lanzan `PermissionError`, o si `os.access` sobre la carpeta o el archivo existente niega lectura o escritura antes de conectar, o si SQLite falla con `SQLITE_PERM`, `SQLITE_READONLY` o `SQLITE_CANTOPEN` y `os.access` lo niega; `E_LOCKED` si SQLite sigue en `SQLITE_BUSY` o `SQLITE_LOCKED` al vencer `BUSY_TIMEOUT_SECONDS`; `E_IO` cualquier otro fallo, un archivo que no es SQLite, una versión de formato distinta de 0 (sin tablas) o 1, o un conflicto al registrar. Los tests inyectan el fallo de permiso sustituyendo `os.access` o la función interna `native_ids._connect`.
  - Archivo vacío: uno de 0 bytes, o una base con `user_version` 0 y sin tablas; se inicializa como uno nuevo.
  - Constantes: `ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"`, `FORMAT_VERSION = 1` (en `PRAGMA user_version`), `BUSY_TIMEOUT_SECONDS = 5.0` (leída en cada apertura para que un test la acorte).
- **D-05. Textos literales.** En inglés, comparados literalmente por los tests:
  - `E_LOCKED`: mensaje `the native id cache is locked by another process`; hint `close the process that holds ~/.mailquery/db/cache.db and run the command again`.
  - `E_PERMISSION`: mensaje `no permission to read or write the native id cache`; hint `check the permissions of ~/.mailquery/db/ and ~/.mailquery/db/cache.db`.
  - `E_IO`: mensaje `cannot use the native id cache: <detalle>` (`<detalle>`: `not a valid native id cache`, `conflicting uid part` u otro texto sin datos de correo); hint `if you delete ~/.mailquery/db/cache.db, mailquery creates an empty one; uids already printed do not resolve until you repeat the search`.
  - Forma inválida en Windows: mensaje `invalid uid part '<id>': expected a short id` (`<id>` con `repr`); hint ``Outlook uids are short ids as printed by `mailquery search` and `mailquery new`; run `mailquery search` to find the uid of a message``.
  - Hint de repetir la búsqueda (uid fuera de la caché o mensaje ausente confirmado): ``the uid is not in the native id cache or its message no longer exists; run `mailquery search` or `mailquery new` again to get its current uid``.
- **D-08.** `PluginNativeIds` abre la base en la primera operación, no al construirse.
- **D-14.** `native_ids.py` no importa `mailquery.plugins` en el nivel del módulo.
- **D-15.** `PluginNativeIds` usa `check_same_thread=False` y un `threading.Lock`.

Reglas de RF-80 que la implementación debe respetar literalmente: alfabeto `0123456789abcdefghjkmnpqrstvwxyz`, grupos de 5 bits desde el bit de mayor peso, sin relleno; parte del uid `<short_id>` o `<short_id>-<seq>` con `seq` > 1 en decimal sin ceros; `seq` siguiente al mayor de `cache_native_seq` y al mayor asignado en la ejecución, en el orden de `native_id` dentro de una misma consulta; `cache_native_seq` solo crece y se actualiza en la misma transacción que el registro; un archivo vacío se inicializa y uno con otra versión es inválido.

## Fases

**Tabla: Fases de M01**

| Fase | Tareas | Estado |
|---|---|---|
| 1 | `short_id` y constantes; UT-NID-01 | 🟢 |
| 2 | Apertura: carpeta, archivo, tablas, versión, permisos, base vacía, base inválida, sin permiso, base bloqueada; UT-NID-02 | 🟢 |
| 3 | `assign`, `register`, `resolve`, `discard`, `open_in_memory` y aislamiento por driver; UT-NID-03 | 🟢 |
| 4 | `PluginNativeIds`: apertura perezosa, hilos, conversión de errores; UT-NID-04 | 🟢 |
| 5 | Suite completa, cobertura, diff, evidencia cruda | 🟢 |

## Tests

Archivo `tests/test_native_ids.py`, con `unittest`, `HOME` temporal y nombres `test_ut_nid_<grupo>_<caso>_<descripción>`. Las definiciones ya están `[pendiente]` en `docs/tests/native-ids.md`.

#### UT-NID-01 — Cálculo del id corto

Requisitos: RF-80, AC-69

**Tabla: Casos de UT-NID-01**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `short_id("mailquery", 10)` ⇒ `pmw3w06f5e`. |
| .02 | B | Longitudes 1 y 51 dan ese número de caracteres; 0, 52, una longitud que no es entero o un texto que no es `str` ⇒ `ValueError`. |
| .03 | P | Solo caracteres del alfabeto; determinista; `short_id(t, n)` es el principio de `short_id(t, 51)`; coincide con una codificación de referencia escrita en el test (grupos de 5 bits desde el bit de mayor peso, sin relleno). |
| .04 | P | Un texto no ASCII se codifica en UTF-8 antes del `SHA-256`. |

#### UT-NID-02 — Apertura, creación y formato

Requisitos: RF-80, RNF-05, AC-69

**Tabla: Casos de UT-NID-02**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Sin `db/` ni `cache.db`, abrir crea los dos, con `cache_native_ids`, `cache_native_seq`, versión de formato 1 y sin filas. |
| .02 | B | Un `cache.db` vacío (0 bytes) se inicializa como uno nuevo. |
| .03 | P | Las tablas tienen solo las columnas de sus estructuras, con sus tipos, `NOT NULL`, la clave primaria (`driver`, `short_id`, `seq`) / (`driver`, `short_id`) y la restricción única (`driver`, `native_id`); no hay otras tablas de usuario. |
| .04 | P | En POSIX, la carpeta tiene permisos 0700, `cache.db` 0600 y el archivo auxiliar de la base que exista durante una escritura, 0600 (aserción condicional fuera de POSIX). |
| .05 | N | Archivo con otra versión de formato ⇒ `E_IO` (exit 3) con el mensaje y el hint de D-05; el archivo no cambia. |
| .06 | N | Archivo que no es una base SQLite ⇒ `E_IO` (exit 3) con el mensaje y el hint de D-05; el archivo no cambia. |
| .07 | N | Sin permiso sobre la carpeta o el archivo ⇒ `E_PERMISSION` (exit 3) con los textos de D-05: con `chmod` real en POSIX y con un fallo de permiso inyectado en los tres sistemas. |
| .08 | N | Base bloqueada por otra conexión más allá de `BUSY_TIMEOUT_SECONDS` (acortado en el test) ⇒ `E_LOCKED` (exit 5) con los textos de D-05; el valor por defecto de `BUSY_TIMEOUT_SECONDS` es 5. |
| .09 | P | Reabrir un archivo existente conserva sus filas y su versión. |

#### UT-NID-03 — Asignar, registrar, resolver y descartar

Requisitos: RF-80, AC-64

**Tabla: Casos de UT-NID-03**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `assign` de un `native_id` sin fila ⇒ su id corto sin sufijo; de uno registrado ⇒ la parte de su fila; `assign` no escribe en el archivo. |
| .02 | P | Dos `native_id` con el mismo id corto en un mismo `assign` (longitud corta en el test) ⇒ `seq` 1 y 2 en el orden de su `native_id`: `<id>` y `<id>-2`. |
| .03 | P | En una ejecución, un `native_id` asignado en dos llamadas conserva su primera parte; uno nuevo con el mismo id corto en la segunda llamada recibe el `seq` siguiente al mayor ya asignado; dos `native_id` distintos nunca reciben la misma parte. |
| .04 | P | `register` guarda a la vez todos los que aún no tienen fila, con su parte asignada, y actualiza `cache_native_seq` en la misma transacción; los ya registrados no cambian. |
| .05 | N | Parte ya registrada para otro `native_id`, `native_id` con otra parte o `native_id` no asignado en la ejecución ⇒ `E_IO` con `conflicting uid part` y no se guarda ninguna fila. |
| .06 | P | `resolve` de una parte registrada ⇒ su `native_id`; de una parte sin fila ⇒ `None`; no escribe. |
| .07 | P | `discard` borra la fila y el mayor `seq` del par se conserva: con la fila del `seq` 2 borrada, un tercer `native_id` con ese id corto recibe el `seq` 3. |
| .08 | P | Un driver no ve, no resuelve ni descarta las filas de otro; el mismo `native_id` puede tener una fila en cada driver. |
| .09 | B | El sufijo va en decimal sin ceros a la izquierda; nunca se produce `-1`; el `seq` 10 da `<id>-10`. |
| .10 | P | Tras registrar, la base solo contiene `driver`, `short_id`, `seq`, `native_id` y el mayor `seq` de cada par. |
| .11 | P | `open_in_memory` asigna, registra y resuelve igual y no crea ningún archivo. |

#### UT-NID-04 — Acceso de un plugin

Requisitos: RF-80, AC-69, AC-70

**Tabla: Casos de UT-NID-04**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Dentro de `call_driver` de un driver externo y sin que el código del plugin capture nada: base bloqueada ⇒ `E_CLIENT_BUSY` (exit 5); sin permiso ⇒ `E_PERMISSION` (exit 3); base inválida o conflicto al registrar ⇒ `E_PLUGIN_FAILED` (exit 3). |
| .02 | P | Las operaciones funcionan desde hilos trabajadores distintos (dos llamadas sucesivas de `call_driver` externo) y dentro de una llamada vigilada por el tope. |
| .03 | P | Construir `PluginNativeIds` no crea nada; la primera operación crea la carpeta y el archivo. |
| .04 | P | Ninguna operación permite elegir otro driver; las filas que escribe son de su driver. |
| .05 | P | `close()` libera la conexión: después, `cache.db` se puede borrar (también en Windows) y una operación posterior vuelve a abrir la base. |

Comandos:

- Grupo: `$PY -B -m unittest discover -s tests -t . -k ut_nid > "$LOG/grupo-ut_nid.log" 2>&1`.
- Suite completa: la de `protocolo.md`.

Tests que cambian: ninguno.

## Documentación

Ninguna fuera del código: docstrings y comentarios en inglés que describen el comportamiento, sin citar la unidad, el PRD ni el plan.

## Actualizaciones de la unidad

Las aplica el orquestador al cerrar el milestone.

- **Conciliación:** según `trazabilidad.md`, aporta a RC-06, RC-08, RC-09, RC-10, RC-11, RC-13, RC-16, RC-18, RC-24, RC-29, RC-36. Ninguna fila cambia de estado al cerrar este milestone: el orquestador las pasa todas a `implementado` en F4.
- **Documentos consumidores:** ninguno.
- **Checklist:** ninguno cambia (se verifica al conciliar).
- **Desviaciones:** ninguna prevista; una necesaria se propone y solo existe si el dueño la aprueba.

## Gates

- `-k ut_nid` verde.
- Suite completa sin fallos nuevos frente a la línea base.
- `git diff --check <base>...HEAD` limpio; `git diff --stat <base>...HEAD` solo con los dos archivos nuevos y los del plan propios.
- Cobertura de `src/mailquery/native_ids.py` ≥ 85 % (o "not run" si no hay `coverage`).

## Datos crudos de evidencia

Los de `protocolo.md`, más el tiempo de `-k ut_nid` (para vigilar R-07).

## Definition of Done

- `src/mailquery/native_ids.py` cumple D-04, D-05, D-08, D-14 y D-15.
- UT-NID-01…UT-NID-04 existen con un método por caso y pasan.
- Suite completa sin fallos nuevos; gates verdes; evidencia cruda escrita.
- Fases de este archivo en 🟢 y registro de progreso al día.

## Registro de progreso

**Tabla: Registro de progreso de M01**

| Fecha | Fase | Nota |
|---|---|---|
| 2026-11-23 | 1 | `short_id` y constantes en `src/mailquery/native_ids.py`; UT-NID-01 (4 casos) en verde, uno a uno. |
| 2026-11-23 | 2 | Apertura, creación, formato, permisos, base inválida y bloqueada; UT-NID-02 (9 casos) en verde, uno a uno. |
| 2026-11-23 | 3 | `assign`, `register`, `resolve`, `discard` e `open_in_memory`; UT-NID-03 (11 casos) en verde, uno a uno. |
| 2026-11-23 | 4 | `PluginNativeIds` con apertura perezosa, hilos y protocolo de RF-50; UT-NID-04 (5 casos) en verde, uno a uno. |
| 2026-11-23 | 5 | `-k ut_nid` (29 casos) en verde; suite completa 1481 tests `OK (skipped=7)`; cobertura de `native_ids.py` 90.7 %; diff y evidencia. |

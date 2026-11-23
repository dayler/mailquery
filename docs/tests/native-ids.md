# Ids nativos

Casos de la librería de ids cortos y de la caché de ids nativos.

#### UT-NID-01 — Cálculo del id corto

Requisitos: RF-80, AC-69 · Archivo: `tests/test_native_ids.py`

**Tabla: Casos de UT-NID-01**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `short_id("mailquery", 10)` ⇒ `pmw3w06f5e`. |
| .02 | B | Longitudes 1 y 51 dan ese número de caracteres; 0, 52, una longitud que no es entero o un texto que no es `str` ⇒ `ValueError`. |
| .03 | P | Solo caracteres del alfabeto; determinista; `short_id(t, n)` es el principio de `short_id(t, 51)`; coincide con una codificación de referencia escrita en el test (grupos de 5 bits desde el bit de mayor peso, sin relleno). |
| .04 | P | Un texto no ASCII se codifica en UTF-8 antes del `SHA-256`. |

#### UT-NID-02 — Apertura, creación y formato

Requisitos: RF-80, RNF-05, AC-69 · Archivo: `tests/test_native_ids.py`

**Tabla: Casos de UT-NID-02**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Sin `db/` ni `cache.db`, abrir crea los dos, con `cache_native_ids`, versión de formato 1 y sin filas. |
| .02 | B | Un `cache.db` vacío (0 bytes) se inicializa como uno nuevo. |
| .03 | P | La tabla tiene solo las columnas de su estructura, con sus tipos, `NOT NULL`, la clave primaria (`driver`, `short_id`, `seq`) y la restricción única (`driver`, `native_id`); no hay otras tablas de usuario. |
| .04 | P | En POSIX, la carpeta tiene permisos 0700, `cache.db` 0600 y el archivo auxiliar de la base que exista durante una escritura, 0600 (aserción condicional fuera de POSIX). |
| .05 | N | Archivo con otra versión de formato ⇒ `E_IO` (exit 3) con el mensaje `cannot use the native id cache: not a valid native id cache` y el hint de RF-80; el archivo no cambia. |
| .06 | N | Archivo que no es una base SQLite ⇒ `E_IO` (exit 3) con el mensaje `cannot use the native id cache: not a valid native id cache` y el hint de RF-80; el archivo no cambia. |
| .07 | N | Sin permiso sobre la carpeta o el archivo ⇒ `E_PERMISSION` (exit 3) con el mensaje `no permission to read or write the native id cache` y su hint: con `chmod` real en POSIX y con un fallo de permiso inyectado en los tres sistemas. |
| .08 | N | Base bloqueada por otra conexión más allá de `BUSY_TIMEOUT_SECONDS` (acortado en el test), al escribir o al abrirla ⇒ `E_LOCKED` (exit 5) con el mensaje y el hint de RF-80; el valor por defecto de `BUSY_TIMEOUT_SECONDS` es 5. |
| .09 | P | Reabrir un archivo existente conserva sus filas y su versión. |

#### UT-NID-03 — Asignar, registrar, resolver y descartar

Requisitos: RF-80, AC-64 · Archivo: `tests/test_native_ids.py`

**Tabla: Casos de UT-NID-03**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `assign` de un `native_id` sin fila ⇒ su id corto sin sufijo; de uno registrado ⇒ la parte de su fila; `assign` no escribe en el archivo. |
| .02 | P | Dos `native_id` con el mismo id corto en un mismo `assign` (longitud corta en el test) ⇒ `seq` 1 y 2 en el orden de su `native_id`: `<id>` y `<id>-2`. |
| .03 | P | En una ejecución, un `native_id` asignado en dos llamadas conserva su primera parte; uno nuevo con el mismo id corto en la segunda llamada recibe el `seq` siguiente al mayor ya asignado; dos `native_id` distintos nunca reciben la misma parte. |
| .04 | P | `register` guarda a la vez todos los que aún no tienen fila, con su parte asignada, en una transacción; los ya registrados no cambian. |
| .05 | N | Parte ya registrada para otro `native_id`, `native_id` con otra parte o `native_id` no asignado en la ejecución ⇒ `E_IO` con `conflicting uid part` y no se guarda ninguna fila. |
| .06 | P | `resolve` de una parte registrada ⇒ su `native_id`; de una parte sin fila ⇒ `None`; no escribe. |
| .07 | P | `discard` borra la fila y su `seq` queda libre: con la fila del `seq` 2 borrada, un tercer `native_id` con ese id corto recibe el `seq` 2. |
| .08 | P | Un driver no ve, no resuelve ni descarta las filas de otro; el mismo `native_id` puede tener una fila en cada driver. |
| .09 | B | El sufijo va en decimal sin ceros a la izquierda; nunca se produce `-1`; el `seq` 10 da `<id>-10`. |
| .10 | P | Tras registrar, la base solo contiene `driver`, `short_id`, `seq` y `native_id`. |
| .11 | P | `open_in_memory` asigna, registra y resuelve igual y no crea ningún archivo. |

#### UT-NID-04 — Acceso de un plugin

Requisitos: RF-80, AC-69, AC-70 · Archivo: `tests/test_native_ids.py`

**Tabla: Casos de UT-NID-04**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Dentro de `call_driver` de un driver externo y sin que el código del plugin capture nada: base bloqueada ⇒ `E_CLIENT_BUSY` (exit 5); sin permiso ⇒ `E_PERMISSION` (exit 3); base inválida o conflicto al registrar ⇒ `E_PLUGIN_FAILED` (exit 3). |
| .02 | P | Las operaciones funcionan desde hilos trabajadores distintos (dos llamadas sucesivas de `call_driver` externo) y dentro de una llamada vigilada por el tope. |
| .03 | P | Construir `PluginNativeIds` no crea nada; la primera operación crea la carpeta y el archivo. |
| .04 | P | Ninguna operación permite elegir otro driver; las filas que escribe son de su driver. |
| .05 | P | `close()` libera la conexión: después, `cache.db` se puede borrar (también en Windows) y una operación posterior vuelve a abrir la base. |

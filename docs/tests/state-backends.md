# Estado, store, backends y uid

#### UT-BE-01 — Selección del backend

Requisitos: RF-24 · Archivo: `tests/test_backends.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `win32` ⇒ Outlook. |
| .02 | P | Cualquier otra plataforma ⇒ Apple Mail. |

#### UT-BE-02 — Imports

Requisitos: RNF-02, ADR-14 · Archivo: `tests/test_backends.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Fuera de `win32`, tras importar todos los módulos, `win32com` no está en `sys.modules`. |
| .02 | P | Solo `outlook_com.py` importa `win32com`/`pythoncom` (AST). |
| .03 | N | Ningún otro import fuera de la stdlib. |
| .04 | N | Nadie invoca `osascript` ni AppleScript. |
| .05 | N | `search.py` y `config.py` no contienen SQL ni COM ni importan `store`, `emlx` o `accounts`. |

#### UT-BE-03 — Interfaz

Requisitos: RF-36 · Archivo: `tests/test_backends.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `MailBackend` declara exactamente las operaciones de la interfaz de backend. |
| .02 | N | Una subclase incompleta no se instancia. |

#### UT-BE-04 — Contrato de backend

Requisitos: RF-11, RF-12 · Archivo: `tests/test_backends.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | B | `query(since=…)` incluye el segundo exacto. |
| .02 | B | `query(until=…)` excluye el segundo exacto. |
| .03 | P | `query(unread=True)`. |
| .04 | P | `resolve_mailbox` por `INBOX`, nombre, path y URL; path o URL exactos ganan a un nombre; con dos carpetas del mismo nombre, la primera de `mailboxes`. |
| .05 | N | `resolve_mailbox` inexistente ⇒ `None`. |

#### UT-ST-01 — Lock

Requisitos: RF-20 · Archivo: `tests/test_state.py`

Los 7 tests de `RunLockTest`, en los 3 SO.

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `test_lock_path_and_modes`. |
| .02 | N | `test_second_acquisition_raises_e_locked`. |
| .03 | P | `test_lock_can_be_taken_again_after_release`. |
| .04 | P | `test_context_manager_releases_on_exit`. |
| .05 | P | `test_context_manager_releases_on_exception`. |
| .06 | P | `test_acquire_is_idempotent_per_instance`. |
| .07 | N | `test_release_without_acquire_is_safe`. |

#### UT-ST-02 — Validación de `state.json` en macOS

Requisitos: AC-06 · Archivo: `tests/test_state.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | `cursor: {}` ⇒ `E_STATE_CORRUPT`. |
| .02 | N | `last_date_received` negativo ⇒ ídem. |
| .06 | P | `cursor: null` ⇒ sin cursor. |

#### UT-ST-04 — `E_STATE_CORRUPT`

Requisitos: AC-06 · Archivo: `tests/test_state.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Hint: renombrar el archivo; la siguiente corrida es una primera corrida que emite la ventana. |

#### UT-ST-05 — Escritura del estado

Requisitos: RF-21 · Archivo: `tests/test_state.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | `ENOSPC` ⇒ `E_INTERNAL`, exit 1, cursor previo intacto. |
| .02 | N | `EACCES` ⇒ `E_PERMISSION`, cursor previo intacto. |

#### UT-ST-06 — Migración schema 1 → 2

Requisitos: AC-06 · Archivo: `tests/test_cli.py`, `tests/test_state.py`

**Tabla: Casos de UT-ST-06**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Función pura de migración: enteros ≥ 1 en `cursor.last_uid` y `emitted_uids` ⇒ `apple_mail:<n>`, sin depender del SO. |
| .02 | P | Strings hexadecimales en mayúsculas ⇒ `outlook:<HEX>`; mayúsculas/minúsculas no se reinterpretan (un valor inválido cae en.03). Estos dos casos prueban la función pura o inyectan un registro con ambos drivers para que la validación posterior no dependa de la plataforma. |
| .03 | N | Valor no entero, no hex en mayúsculas, `0`, negativo, `None`, lista ⇒ `E_STATE_CORRUPT` con hint de renombrar; un entero migrado cuyo driver no está instalado ⇒ `E_STATE_CORRUPT` en la validación de schema 2 (caso separado). |
| .04 | P | `new --peek` migra en memoria, no escribe y responde con el cursor migrado. |
| .05 | P | La siguiente corrida de `new` sin `--peek` que emite al menos un mensaje persiste schema 2 con la escritura atómica; una corrida sin mensajes no escribe estado; el original solo se reemplaza al final. |
| .06 | P | `doctor` informa `schema: 1 (migration pending)` hasta la persistencia y schema 2 después. |
| .07 | P | Ciclo de vida DP-03 (estado): desinstalar un plugin deja su `cursor.last_uid` en `E_STATE_CORRUPT`, poda sus uids del anillo y `doctor state` informa la poda sin romper `new` por los elementos podados. |

#### UT-ST-07 — Validación schema 2 y poda

Requisitos: AC-06 · Archivo: `tests/test_state.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | `cursor.last_uid` que no es string prefijado, o con formato inválido, o > 1024 ⇒ `E_STATE_CORRUPT`. |
| .02 | N | `cursor.last_uid` de un driver no instalado ⇒ `E_STATE_CORRUPT` con hint (reinstalar el plugin o renombrar el estado). |
| .03 | P | `emitted_uids` con drivers no instalados se podan en silencio; `new` no falla y `doctor` lo reporta en el detalle de `state`. |
| .04 | N | Un uid migrado de 1025 caracteres ⇒ `E_STATE_CORRUPT` (después de migrar en memoria). |
| .05 | P | `schema` ausente, booleano o distinto de 1/2 ⇒ `E_STATE_CORRUPT`. |

#### UT-STO-01 — Copias temporales

Requisitos: RNF-05 · Archivo: `tests/test_store.py`

POSIX, con los originales en 0644.

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Copia del `Envelope Index` y de su WAL ⇒ 0600. |
| .02 | P | Copia de `Accounts4.sqlite` ⇒ 0600. |

#### UT-UID-01 — Formato y parseo

Requisitos: AC-05, RF-38 · Archivo: `tests/test_uid.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `apple_mail:83143` ⇒ driver `apple_mail`, nativo `83143`; `outlook:ABC123` ⇒ driver `outlook`, nativo `ABC123`. |
| .02 | P | `native_id` acepta `[A-Za-z0-9._=-]`; el punto se acepta en posiciones interiores (`a.b`) pero se rechaza como primer carácter (`.a`) y la secuencia `..`; split en el primer `:` (`a:b:c` ⇒ nativo `b:c`, inválido por `:`). |
| .03 | N | Driver vacío, con mayúsculas, guion o > 64 ⇒ `E_USAGE` (el formato del uid es inválido); un driver válido pero no instalado ⇒ `E_DRIVER_UNKNOWN` (caso separado). |
| .04 | N | `native_id` con `/`, espacio, `:` o > 1024; punto inicial; `..`; cadena vacía ⇒ `E_USAGE`. |
| .05 | P | Entrada legada: entero sin prefijo en macOS ⇒ driver nativo `apple_mail` con ese nativo; hex mayúsculas sin prefijo en Windows ⇒ `outlook`. |
| .06 | N | La validación de un uid inválido ocurre antes de crear el home, leer la config y abrir el store; no escribe estado ni caché. |
| .07 | P | Identificador estable de ruta: 32 hex en minúsculas = primeros 32 caracteres de `SHA-256(uid UTF-8)`; determinista entre plataformas. |

#### UT-UID-02 — uid prefijado en comandos

Requisitos: AC-05 · Archivo: `tests/test_uid.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `search`, `new` y `show` emiten `uid` string con el prefijo del driver nativo; `new` emite `cursor.previous/current.last_uid` igual. |
| .02 | P | Orden de `search`/`show` por `(date_received DESC, driver ASC, native_order_key DESC)` y de `new` ASC; con Apple Mail el orden numérico no cambia respecto de 2.0.1. `native_order_key` se toma de la fila del backend, nunca del texto del uid. |
| .03 | P | Entrada legada: `show 83143` en macOS y `show <EntryID hex>` en Windows se resuelven con el driver nativo y devuelven el uid prefijado. |
| .04 | N | `show` malformado ⇒ `E_USAGE`; driver desconocido ⇒ `E_DRIVER_UNKNOWN`; ambos antes de crear el home, leer config o abrir el store, sin escribir estado ni caché. |
| .05 | N | `show` con prefijo de un driver instalado pero no declarado ⇒ `E_ACCOUNT_NOT_IN_SCOPE` sin cargar el driver. |
| .06 | N | Un `state.json` con uid legado válido no se reescribe en comandos de solo lectura (`search`, `show`, `mailboxes`, `doctor`). |

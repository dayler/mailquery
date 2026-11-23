# Outlook: ejecución y adjuntos

#### UT-OL-ATT-01 — Metadatos, índice y disponibilidad

Requisitos: AC-07/AC-15 · Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `show` y `attachment` comparten `index` 1..N y `name` original; adjuntos ocultos no se listan. |
| .02 | P | Un adjunto local devuelve tamaño esperado estable y se extrae. |
| .03 | N | Un adjunto no descargado (solo propiedades locales) ⇒ `E_ATTACHMENT_UNAVAILABLE` (`not_downloaded`), sin llamada de descarga y sin red. |
| .04 | N | S/MIME ⇒ `E_ATTACHMENT_UNREADABLE` (`smime`) y `show` devuelve `[]`. |
| .05 | N | Corrupto/ilegible ⇒ `E_ATTACHMENT_UNREADABLE` (`corrupt`/`unreadable`); tipo no soportado ⇒ `E_ATTACHMENT_UNAVAILABLE` (`unsupported`). |
| .06 | N | El `CallLog` no registra miembros de descarga ni de red durante los metadatos. |
| .07 | N | `show` de un item header-only con `has_attachments` ⇒ `attachments: []` y `W_ATTACHMENTS_UNAVAILABLE` (cuerpo ilegible), sin nombres del índice y sin `E_USAGE`; usa `outlook/show_header_only.json`. |
| .08 | B | El `Size` de Outlook, que incluye la sobrecarga de MAPI, nunca invalida la caché. |

#### UT-OL-ATT-02 — Materialización COM

Requisitos: AC-10/AC-12 · Archivo: `tests/test_outlook.py`

**Tabla: Casos de UT-OL-ATT-02**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Un adjunto local se materializa con `SaveAsFile` en el staging `0700`; el archivo es regular, no symlink, `0600`/ACL del perfil; el núcleo lo lee y lo publica con la validación del motor. |
| .02 | N | La materialización se rechaza si el archivo temporal no está dentro de `tmp/staging` o es un symlink ⇒ `E_ATTACHMENT_UNAVAILABLE` (`unsupported`) antes de publicar, sin código interno. |
| .03 | N | Un adjunto con contenido ejecutable en el archivo materializado ⇒ mensaje bloqueado, archivo temporal borrado, nada publicado. |
| .04 | P | El archivo temporal se borra también cuando la extracción falla o el timeout vence. |
| .05 | N | La lista blanca del proxy solo añade la operación de materialización `SaveAsFile` (`GetTemporaryFilePath` no se autoriza); cualquier otra operación sigue dando `E_INTERNAL` (OL-01). |
| .06 | N | `object_model_guard` no bloquea la operación de materialización (decisión interna, sin señal observable); el caso solo afirma timeout/permiso y lista blanca, y el riesgo queda documentado. |

#### UT-OL-ATT-03 — Errores, timeout y motivos

Requisitos: AC-15/AC-17 · Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | `E_ACCESSDENIED` en la materialización ⇒ `E_PERMISSION` (3). |
| .02 | N | Rechazo transitorio persistente ⇒ `E_CLIENT_BUSY` (5); el doble registra la secuencia de reintentos. |
| .03 | N | Una llamada COM de materialización que supera 30 s ⇒ `E_CLIENT_TIMEOUT` (3), staging limpio. |
| .04 | N | El tope configurado de extracción vence aunque cada llamada COM esté por debajo de 30 s ⇒ `E_CLIENT_TIMEOUT`. |
| .05 | N | Un fallo de materialización en `--all` no produce resultados parciales. |
| .06 | P | Un adjunto de 0 bytes se materializa y publica con `size_bytes: 0`. |

#### UT-OL-ATT-04 — Solo lectura y log

Requisitos: AC-19, RNF-13 · Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | 0 mutaciones del buzón y 0 asignaciones durante todas las extracciones; el `CallLog` muestra solo miembros de la lista blanca. |
| .02 | P | Ninguna escritura fuera de `~/.mailquery`: store, mensajes y flags intactos. |
| .03 | N | El log no registra uids, `EntryID`, `StoreID`, nombres, rutas ni cuentas. |
| .04 | P | `event=end` de `attachment` conserva `count`, `cached`, `bytes`, `duration_ms`. |

#### OL-01 — Proxy de solo lectura

Requisitos: RNF-01 · Archivo: `tests/test_outlook.py`

Cada caso negativo produce `E_INTERNAL` con hint no vacío, sin tocar el fake.

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Invocar `Delete`, `Move`, `Copy`, `Save`, `SaveAs`, `Send`, `Display`, `Close`, `Items.Remove`, `Folders.Add`, `AddressEntry`, `GetExchangeUser` o cualquier miembro fuera de la lista blanca, cada uno. |
| .02 | N | Asignar `UnRead` o cualquier otra propiedad. |
| .03 | N | Nombres dunder y privados. |
| .04 | P | Todo objeto devuelto está envuelto, también en colecciones. |

#### OL-02 — Detección del cliente

Requisitos: RF-26 · Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | `pywin32` no importable, también con Outlook sin registrar ⇒ `E_DEPENDENCY_MISSING`, exit 3, hint `pipx reinstall mailquery`. |
| .02 | N | Outlook no registrado ⇒ `E_CLIENT_UNSUPPORTED` con su hint. |
| .03 | N | `CurVer` 15.0 ⇒ `E_CLIENT_UNSUPPORTED`. |
| .04 | B | `CurVer` 16.0 ⇒ continúa. |
| .05 | N | Sin instancia ⇒ `E_OUTLOOK_NOT_RUNNING`, exit 6, con su hint. |
| .06 | P | Instancia en ejecución ⇒ conecta con `GetActiveObject`. |
| .07 | N | El `CallLog` nunca registra `Dispatch`, `DispatchEx` ni `EnsureDispatch`. |

#### OL-03 — Errores COM

Requisitos: RF-22, PRD §17 · Archivo: `tests/test_outlook.py`

Fallo inyectado en la primera llamada COM.

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | `E_ACCESSDENIED` ⇒ `E_PERMISSION`, exit 3, hint no vacío. |
| .02 | B | Rechazo transitorio una vez ⇒ éxito tras 100 ms. |
| .03 | N | Rechazo transitorio dos veces ⇒ `E_CLIENT_BUSY`, exit 5, hint no vacío. |
| .04 | N | HRESULT desconocido ⇒ `E_INTERNAL`, hint no vacío. |

#### OL-04 — Timeout

Requisitos: RF-31 · Archivo: `tests/test_outlook.py`

Plazo de 0,2 s, en subprocess con `run_cli.py`.

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | `search` colgado en la primera llamada COM ⇒ `E_CLIENT_TIMEOUT`, exit 3, hint que remite a `doctor`, JSON completo en `stdout`. |
| .02 | N | `new` colgado ⇒ ídem y el estado no se escribe. |
| .03 | N | `doctor` colgado en `outlook` ⇒ `outlook` `ok=false` con `timeout after 30 s: Outlook did not respond (possible security prompt)` literal; `stores`, `readonly_strategy` y la resolución de `config` `not evaluated`; el resto evaluado; exit 0; el JSON lleva `plugins: []` (o la sección de los plugins declarados). |
| .04 | N | `doctor` colgado en `stores` ⇒ `stores` con ese texto; resolución de `config` `not evaluated`; el resto evaluado; exit 0; el JSON lleva `plugins: []`. |
| .05 | B | Trabajo de Python entre llamadas más largo que el plazo, sin llamada COM en curso ⇒ sin timeout. |
| .06 | P | El error queda en el log. |

#### OL-05 — Caché de `pywin32`

Requisitos: RNF-01, PRD §9.3 · Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `win32com.__gen_path__` = `<home>/tmp/gen_py` antes de importar `win32com.client`. |
| .02 | N | En Windows real: ningún archivo de caché fuera de `<home>/tmp/gen_py`. |

#### OL-27 — `object_model_guard`

Requisitos: RF-23 · Archivo: `tests/test_outlook.py`

Con `registry` y `security_center` inyectados.

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Directiva que pregunta siempre o que deniega ⇒ falla. |
| .02 | P | Directiva que permite ⇒ pasa. |
| .03 | P | Sin directiva y antivirus activo ⇒ pasa. |
| .04 | N | Sin directiva y sin antivirus ⇒ falla. |
| .05 | N | Sin directiva y estado del antivirus no consultable ⇒ `ok=false`, `not evaluated: SecurityCenter2 unavailable`. |
| .06 | N | Con directiva ⇒ el antivirus no se consulta. |

#### OL-29 — Log

Requisitos: RNF-07 · Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `backend=outlook`. |
| .02 | P | Estrategia `com_readonly` y versión de Outlook. |
| .03 | N | Sin uids, `EntryID` ni `StoreID`. |

#### OL-30 — Gate de solo lectura de Outlook

Requisitos: RNF-01 · Archivo: `tests/test_outlook.py`

Barrido de los comandos con todos sus flags —incluido `--strip-links` en cada `search`, `new` y `show`, `show --show-native-id`, `search --group-by from,month`, `search --count`, `mailboxes`, `mailboxes --fields total,unread` y `mailboxes --fields name,url`, y `doctor`, `doctor --json`, `doctor --failures` y `doctor --json --failures`— sobre el fake de Outlook; bloqueante.

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | [por actualizar] Miembros invocados ⊆ lista blanca; el barrido incluye `show --show-native-id` y la expectativa no cambia. |
| .02 | N | 0 asignaciones. |
| .03 | N | 0 mutaciones. |
| .04 | N | Nunca aparecen errores ni warnings que no aplican al backend de Outlook, ni `E_INTERNAL`. |
| .05 | N | Las corridas de `attachment` escriben solo bajo `<home>` y dejan vacío el staging. |

#### OL-31 — uid corto de Outlook

Requisitos: RF-81, RF-80, AC-63, AC-67, AC-69 · Archivo: `tests/test_outlook.py`

**Tabla: Casos de OL-31**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | [pendiente] Todo uid de `search`, `new` y `show`, y `cursor.current.last_uid`, es `outlook:` más 10 caracteres del alfabeto (18 en total), o con sufijo `-<n>`. |
| .02 | P | [pendiente] El mismo mensaje da el mismo uid en corridas sucesivas y también después de borrar `cache.db` cuando ningún otro mensaje con su id corto se registró. |
| .03 | P | [pendiente] `show` y `attachment` resuelven el uid impreso por `search` y por `new`. |
| .04 | P | [pendiente] El id corto es `short_id(<EntryID en mayúsculas>, 10)`; `native_order_key` sigue siendo el `EntryID` y el orden con la misma fecha no cambia. |
| .05 | P | [pendiente] Las claves de las respuestas de `search`, `new`, `show`, `attachment`, `mailboxes` y `doctor` en Windows son las mismas que en macOS con solo `apple_mail`, y ninguna salida tiene una clave `short_id` ni `seq` a ningún nivel. |
| .06 | P | [pendiente] `search`, `new`, `show` y `attachment` crean `~/.mailquery/db/cache.db` en un home nuevo, también `search --count`, que no registra filas; `mailboxes`, `doctor` y `--version` no lo crean. |

#### OL-32 — Validación y resolución del uid en Windows

Requisitos: RF-81, RF-25, RF-38, AC-63, AC-69 · Archivo: `tests/test_outlook.py`

**Tabla: Casos de OL-32**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | [pendiente] Un `EntryID` como uid, con prefijo o sin él, en `show` y en `attachment` ⇒ `E_USAGE` con `invalid uid part '<id>': expected a short id` y el hint de D-05, sin crear el home ni la caché. |
| .02 | N | [pendiente] Id corto en mayúsculas, sufijos `-1`, `-02` y `-0`, 9 u 11 caracteres o un carácter fuera del alfabeto (`i`, `l`, `o`, `u`) ⇒ el mismo `E_USAGE`, sin crear la caché. |
| .03 | P | [pendiente] El uid legado sin prefijo (id corto) se resuelve con el driver nativo y `show` devuelve el uid prefijado; la forma con sufijo `-2` es válida. |
| .04 | N | [pendiente] Una forma válida que no está en la caché ⇒ `E_USAGE` con `message uid … was not found` y el hint de repetir la búsqueda, en `show` y en `attachment`. |
| .05 | N | [pendiente] `show` y `attachment` sin `~/.mailquery/db/` ni `cache.db` ⇒ crean los dos, con la base vacía, y responden `message uid … was not found` con el hint de repetir la búsqueda. |
| .06 | N | [pendiente] Con el driver `outlook`, en `search`, `show` y `attachment`: base bloqueada (tope acortado) ⇒ `E_LOCKED` (exit 5); sin permiso ⇒ `E_PERMISSION` (exit 3); archivo que no es una base válida ⇒ `E_IO` (exit 3) con el hint de D-05. |
| .07 | B | [pendiente] Con el driver `outlook`, un `cache.db` vacío (0 bytes) se inicializa y `search` responde con exit 0 y registra los impresos. |

#### OL-33 — Registro de impresos en Outlook

Requisitos: RF-82, RF-80, AC-65 · Archivo: `tests/test_outlook.py`

**Tabla: Casos de OL-33**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | [pendiente] `search --limit 2` con 5 candidatos registra exactamente los 2 impresos. |
| .02 | P | [pendiente] `search --group-by from` registra exactamente los mensajes de los grupos impresos. |
| .03 | P | [pendiente] `new` registra los impresos; `new --peek` también y no escribe `state.json`. |
| .04 | N | [pendiente] `search --count` no registra filas (el archivo existe y sus tablas están vacías); una respuesta sin mensajes no registra nada. |
| .05 | N | [pendiente] Si el registro falla (conflicto inyectado o base bloqueada), el comando falla con `E_IO` o `E_LOCKED`, la salida no tiene mensajes y `new` no escribe `state.json`. |
| .06 | N | [pendiente] Un mensaje leído pero descartado por un filtro (`--from`) no se registra. |

#### OL-34 — Colisiones de id corto en Outlook

Requisitos: RF-80, RF-81, AC-64 · Archivo: `tests/test_outlook.py`

**Tabla: Casos de OL-34**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | [pendiente] Dos mensajes con el mismo id corto en un mismo `search` reciben `outlook:<id>` y `outlook:<id>-2`, en el orden de su `EntryID`, y `show` de cada uno devuelve su mensaje. |
| .02 | P | [pendiente] `attachment` de cada uno extrae en `attachments/outlook/<id>/` y `attachments/outlook/<id>-2/` y nunca sirve los archivos del otro. |
| .03 | P | [pendiente] Un mensaje que el driver lee en dos consultas de una misma ejecución (primera corrida de `new`) conserva su uid. |
| .04 | P | [pendiente] Con la fila del `-2` borrada por ausencia confirmada, un tercer mensaje con ese id corto recibe `outlook:<id>-3` y `outlook:<id>-2` ya no se resuelve. |

#### OL-35 — Ausente confirmado e indeterminado

Requisitos: RF-81, AC-66, AC-69 · Archivo: `tests/test_outlook.py`

**Tabla: Casos de OL-35**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | [pendiente] Store montado y `GetItemFromID` con `MAPI_E_NOT_FOUND` o `MAPI_E_INVALID_ENTRYID` ⇒ `message uid … was not found` con el hint de repetir la búsqueda y la fila desaparece, en `show` y en `attachment`; el directorio `attachments/outlook/<parte del uid>/` que existiera sigue en disco. |
| .02 | N | [pendiente] Outlook cerrado ⇒ el error actual de Outlook no abierto; la fila sigue. |
| .03 | N | [pendiente] Outlook que no responde (rechazo repetido) ⇒ `E_CLIENT_BUSY`; la fila sigue. |
| .04 | N | [pendiente] Sin conexión (`MAPI_E_NETWORK_ERROR`) ⇒ su error actual; la fila sigue. |
| .05 | N | [pendiente] Store del `EntryID` no montado (fuera del perfil) ⇒ `message uid … was not found` con el hint actual; la fila sigue. |
| .06 | N | [pendiente] Store ilegible ⇒ el comportamiento actual; la fila sigue. |
| .07 | N | [pendiente] Item que existe pero no se puede abrir (`E_FAIL`) ⇒ como hoy: `show` responde con la fila de las tablas de su carpeta y `attachment` con `E_ATTACHMENT_UNREADABLE` (D-18); la fila sigue. |
| .08 | N | [pendiente] Item que no es un correo ⇒ "no encontrado" con el hint actual; la fila sigue. |
| .09 | N | [pendiente] Item en una carpeta oculta ⇒ "no encontrado" con el hint actual; la fila sigue. |
| .10 | N | [pendiente] Item marcado para borrar ⇒ "no encontrado" con el hint actual; la fila sigue. |
| .11 | N | [pendiente] Otro error COM (`E_UNEXPECTED`) ⇒ su error actual; la fila sigue. |
| .12 | N | [pendiente] Timeout de COM (subproceso con `--hang`) ⇒ `E_CLIENT_TIMEOUT`; la fila sigue. |
| .13 | N | [pendiente] Store excluido ⇒ `E_ACCOUNT_NOT_IN_SCOPE`; la fila sigue. |
| .14 | N | [pendiente] Tras todos los casos anteriores, ninguna fila de `cache_native_ids` cambió de `native_id`. |
| .15 | N | [pendiente] Mensaje movido de carpeta (su `EntryID` cambia en el doble): su uid anterior ⇒ ausente confirmado, "no encontrado" con el hint de repetir la búsqueda y fila borrada; un `search` nuevo le da otro uid; ninguna fila cambió de `native_id`. |

#### OL-36 — `--show-native-id` en Outlook

Requisitos: RF-83, AC-68 · Archivo: `tests/test_outlook.py`

**Tabla: Casos de OL-36**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | [pendiente] `show <uid> --show-native-id` ⇒ `message.uid` es `outlook:<EntryID>`; las demás claves y valores, `cache.db` y `cached_path` son los mismos que sin la opción. |
| .02 | N | [pendiente] Ese `outlook:<EntryID>`, o el `EntryID` sin prefijo, como entrada de `show` o de `attachment` ⇒ `E_USAGE`. |
| .03 | P | [pendiente] Los textos de warnings y errores siguen llevando el uid corto. |

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

Requisitos: RF-22, PRD.md §17 · Archivo: `tests/test_outlook.py`

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

Requisitos: RNF-01, PRD.md §9.3 · Archivo: `tests/test_outlook.py`

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

Barrido de los comandos con todos sus flags —incluido `--strip-links` en cada `search`, `new` y `show`, `search --group-by from,month`, `search --count`, `mailboxes`, `mailboxes --fields total,unread` y `mailboxes --fields name,url`, y `doctor`, `doctor --json`, `doctor --failures` y `doctor --json --failures`— sobre el fake de Outlook; bloqueante.

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Miembros invocados ⊆ lista blanca. |
| .02 | N | 0 asignaciones. |
| .03 | N | 0 mutaciones. |
| .04 | N | Nunca aparecen errores ni warnings que no aplican al backend de Outlook, ni `E_INTERNAL`. |
| .05 | N | Las corridas de `attachment` escriben solo bajo `<home>` y dejan vacío el staging. |

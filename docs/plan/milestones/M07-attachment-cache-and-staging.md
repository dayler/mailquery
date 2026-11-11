# M07 — Adjuntos: límites, staging, caché y publicación atómica

| Campo | Valor |
|-------|-------|
| Fase | D — Recuperación de adjuntos (núcleo) |
| Depende de | M05, M06 (y M01–M03 como contratos) |
| Bloquea a | M08–M11 |
| ACs | AC-12, AC-13, AC-15 (motivos en extracción), AC-20 |
| Grupos de test | UT-ATT-06..11 |
| Write scope | `src/mailquery/attachments/engine.py` y `src/mailquery/attachments/cache.py` (nuevos), `src/mailquery/attachments/**` (integración con M06), `src/mailquery/errors.py` (solo si falta un código), `docs/INTERFACES.md`, `tests/test_attachments.py`, `tests/fakes/attachment_driver.py` (nuevo) |
| No tocar | `cli.py`, `search.py`, `state.py`, `config.py`, `backends/apple_mail.py`, `backends/outlook.py`, `PRD.md`, `PRD-v2.1.md`, `docs/plan/**` |
| Estado | ⚪ |

## 1. Objetivo

Completar el motor de adjuntos: evaluar límites, escribir en staging con permisos correctos y publicar en la caché de forma atómica, con `--force`, aciertos de caché, SHA-256, tolerancia a borrados concurrentes y errores de E/S. Este milestone expone la operación que M08 conectará al comando `attachment`; no crea el comando ni toca los adaptadores de backend.

## 2. Contexto normativo

- PRD-v2.1 §6.2 RF-44–RF-49 (motor), §6.3 RF-51, §7 RNF-13/RNF-14, §10.3, §10.4 (ciclo de vida de la caché), §11.2 (campos de respuesta), §11.3 filas 11–15, §11.7 (`E_ATTACHMENT_TOO_LARGE`, `E_IO`, `E_PERMISSION`, `E_ATTACHMENT_UNAVAILABLE`, `E_ATTACHMENT_UNREADABLE`), §12.2 (presupuesto de acierto de caché), §14 AC-12/AC-13/AC-20.
- Base 2.0.1: `home` con `tmp/` y `logs/` ya existentes (`config.py:129-138`), escritura atómica de estado (`state.py:125-182`) como referencia de patrón, permisos 0700/0600 (`store.py`, `accounts.py`).
- Contratos de entrada: C1 (metadatos y stream de adjunto) y C6 (bloqueo/sanitización/rutas de M06). Config `[attachments]` de C2.

## 3. Tareas

| ID | Tarea | Archivos | Detalle |
|----|-------|----------|---------|
| M07-T01 | API del motor | `attachments/engine.py` (nuevo) | Clase `AttachmentsEngine(home, config, driver, clock=None)` con una operación `recover(uid, indices, force, deadline=None)`; el `deadline` es opcional y el motor lo aplica a la extracción (el valor de 120 s lo inyecta la CLI en M08, el motor no fija políticas de tiempo) que devuelve los registros de respuesta de §11.2 (`index`, `original_name`, `sanitized_name`, `saved`, `cached`, `path`, `size_bytes`, `sha256`) o lanza `MailqueryError` del núcleo. Orden interno conforme a §11.3: (1) pantalla de **nombres** de todo el mensaje (M06) antes de servir caché; (2) límites conocidos; (3) por cada adjunto solicitado: lectura del stream/*magic bytes* (M06), disponibilidad y timeout; (4) extracción a staging, validación y publicación. La pantalla de contenido ocurre en (3), nunca antes de (2). |
| M07-T02 | Límites `[attachments]` | `attachments/engine.py` | `max_count` (solo `--all`; incluye aciertos de caché), `max_file_size_mb` y `max_total_size_mb` (1 MiB = 1.048.576 bytes); un valor **estrictamente mayor** excede. Los límites se evalúan sobre el conjunto que la invocación devuelve; los aciertos de caché cuentan con su tamaño real. Exceso con tamaño conocido ⇒ falla antes de escribir; tamaño desconocido ⇒ aborta al detectarlo, limpia staging y conserva la caché previa. Si varios adjuntos de `--all` fallan, se informa el **primer fallo en orden de índice**. Error `E_ATTACHMENT_TOO_LARGE` (exit 4) con las plantillas de §11.3. |
| M07-T03 | Aciertos de caché y `--force` | `attachments/cache.py` (nuevo), `attachments/engine.py` | Si el archivo existe, es regular y no se pidió `--force`: devuelve `saved: true, cached: true`, `size_bytes` y `sha256` del archivo existente. Si el driver informa un tamaño esperado y no coincide, se trata como miss y se re-extrae. Con `--force`: re-extrae y reemplaza atómicamente (`cached: false`). Un archivo de caché que no sea regular (symlink, directorio) se trata como miss; la publicación nunca sigue un symlink. El bloqueo del mensaje se evalúa **antes** de servir caché. |
| M07-T04 | Staging y publicación atómica | `attachments/engine.py`, `attachments/cache.py` | Toda escritura va a un staging bajo `~/.mailquery/tmp/staging/` (directorio `0700`, archivos `0600` en POSIX, nombre opaco, sin nombre original); se publica con `os.replace` al validar el mensaje completo, con `tmp/` y `attachments/` en el mismo sistema de archivos. Ante un aborto previo a la publicación no queda ningún archivo nuevo ni parcial en la caché ni temporales propios en `tmp/`; un fallo a mitad de publicación puede dejar archivos nuevos **completos** (riesgo aceptado). La app limpia solo su propio staging huérfano; no toca archivos de plugins ni cachés del backend. |
| M07-T05 | Permisos | `attachments/cache.py` | Directorios `~/.mailquery/attachments`, `<driver>` y `<native_id>` con `0700`; archivos `0600` en POSIX y sin `+x`; en Windows se hereda la ACL del perfil (no se relajan permisos). Verificar que el staging también es `0700`/`0600`. |
| M07-T06 | Errores de E/S y permisos | `attachments/engine.py`, `attachments/cache.py` | `E_IO` (exit 3) para fallos de E/S de caché/staging (espacio, cuota, sistema de archivos, publicación fallida, `ENOSPC`); `E_PERMISSION` (exit 3) para `EACCES`/permisos de directorio o archivo; `E_ATTACHMENT_UNAVAILABLE`/`E_ATTACHMENT_UNREADABLE` para los motivos del driver durante la extracción; `E_CLIENT_TIMEOUT` si vence el `deadline` recibido; `E_INTERNAL` solo para fallos inesperados del núcleo. DP-01, §11.3 fila 15 y AC-12 prevalecen sobre la fila de `E_PERMISSION` de §11.7 que aún menciona E/S de caché; se deja constancia en `INTERFACES.md`. Ningún fallo deja parciales ni archivos nuevos incompletos. |
| M07-T07 | Caché efímera | `attachments/cache.py` | Sin barrido, validación integral ni purga al arrancar ni durante la ejecución; sin daemon ni TTL; un archivo ausente o borrado por el cron se trata como miss y se re-extrae una vez; `cached: true` significa “existía y no se pidió `--force`”, no “verificado”; `sha256` es el hash del archivo servido. |
| M07-T08 | Tests, doble y documentación | `tests/test_attachments.py`, `tests/fakes/attachment_driver.py` (nuevo), `docs/INTERFACES.md` | UT-ATT-06..11 con un driver de prueba que entrega bytes/sizes/faketimes y fallos inyectables (incluidos `PermissionError`, `ENOSPC`, timeouts y motivos); pruebas de permisos solo POSIX (aserción condicional); casos de primer fallo en `--all` y ciclo de vida de la caché. Documentar la API del motor, staging, publicación, caché, errores y la precedencia DP-01 sobre §11.7. |

## 4. Casos de prueba

### UT-ATT-06 — Límites (AC-13)

- .01 B Exactamente en el límite permitido; un byte más ⇒ excede; MiB = 1.048.576 bytes.
- .02 N `max_file_size_mb` excedido con tamaño conocido ⇒ `E_ATTACHMENT_TOO_LARGE` antes de escribir; nada nuevo en caché.
- .03 N `max_total_size_mb` excedido con tamaños conocidos ⇒ falla antes de escribir; los aciertos de caché cuentan con su tamaño real.
- .04 N `max_count` con `--all` incluye aciertos de caché; `--index` no está sujeto a `max_count`.
- .05 N Tamaño desconocido que excede durante el streaming ⇒ aborta, limpia staging y conserva la caché previa.
- .06 P Las plantillas de mensaje de §11.3 incluyen el límite, el índice y el nombre cuando corresponde; hint sugiere `--index`.
- .07 N Orden §11.3: mensaje con un nombre bloqueado y un adjunto solicitado que excede `max_file_size_mb` ⇒ `E_ATTACHMENT_BLOCKED` (nombre), no `E_ATTACHMENT_TOO_LARGE`; los nombres se evalúan antes que los límites.

### UT-ATT-07 — Staging y publicación atómica (AC-12)

- .01 P La primera extracción escribe primero en `tmp/staging` (`0700`, archivo `0600`) y aparece en la caché solo al publicar; `cached: false`.
- .02 N Un aborto por contenido, límite o lectura antes de publicar no deja archivos nuevos ni parciales en la caché ni staging propio.
- .03 N Un fallo de `os.replace`/E/S en la publicación ⇒ `E_IO` (exit 3); no se publica nada; staging limpio.
- .04 P Una extracción correcta publica todos los archivos solicitados y devuelve `saved: true` con tamaño y SHA-256 del archivo servido.
- .05 B Un fallo inyectado en `os.replace` deja el archivo anterior intacto (si existía) y no hay archivos truncados ni parciales visibles; la siguiente invocación reintenta la extracción.
- .06 N `PermissionError` (`EACCES`) al crear el directorio de caché o el archivo de staging ⇒ `E_PERMISSION` (exit 3), sin parciales.
- .07 N `ENOSPC`/fallo de E/S al escribir en staging o al publicar ⇒ `E_IO` (exit 3), sin parciales; el caso de `os.replace` está en .03.

### UT-ATT-08 — Caché, `--force` y tamaño esperado (AC-12/AC-20)

- .01 P Primera extracción `cached: false`; segunda invocación sin `--force` `cached: true` con `size_bytes`/`sha256` del archivo existente y sin re-extraer.
- .02 P `--force` re-extrae y devuelve `cached: false`, reemplazando atómicamente.
- .03 B Tamaño esperado del driver distinto del archivo en caché ⇒ se trata como miss y se re-extrae.
- .04 P Un mensaje bloqueado no devuelve ningún `cached_path` ni sirve caché aunque exista.
- .05 N Un archivo de caché que no es regular (symlink o directorio) se trata como miss; la publicación no sigue el symlink.
- .06 P La ruta publicada es `~/.mailquery/attachments/<driver>/<native_id>/<sanitized_name>` (el `sanitized_name` ya lleva `NN_`; no hay doble prefijo) y el `output_dir` es su directorio.

### UT-ATT-09 — Permisos (AC-12, RNF-13)

- .01 P POSIX: directorios `0700`, archivos `0600`, sin bit `+x`; el staging también.
- .02 P Windows (patched): no se relajan permisos; el archivo hereda la ACL del perfil.
- .03 N Un archivo previamente en caché conserva su hash/tamaño si la nueva extracción falla antes de publicar.

### UT-ATT-10 — Caché efímera y borrado concurrente (AC-20)

- .01 P Caché vacía o inexistente no es un error: se extrae.
- .02 P Un archivo borrado entre `show` y `attachment` (o durante la ejecución) se trata como miss y se re-extrae una vez.
- .03 N Si la re-extracción falla tras el borrado ⇒ `E_ATTACHMENT_UNAVAILABLE`.
- .04 N La app no barre ni purga la caché al arrancar ni durante la ejecución; no inspecciona contenido de la caché.
- .05 P Ciclo de vida DP-03 (caché): actualizar un plugin no cambia `config.toml`, `state.json` ni los archivos de caché (byte a byte); desinstalarlo conserva los archivos de caché intactos y no los borra.

### UT-ATT-11 — Motivos y errores durante la extracción (AC-15)

- .01 N El driver informa `not_local`/`not_downloaded`/`unsupported`/`network` al abrir el stream ⇒ `E_ATTACHMENT_UNAVAILABLE` con el motivo.
- .02 N Corrupto/S/MIME/ilegible ⇒ `E_ATTACHMENT_UNREADABLE` con el motivo, antes de la comprobación de “0 adjuntos” (esa comprobación es del comando, M08).
- .03 N `E_PERMISSION`, `E_CLIENT_BUSY` y `E_PLUGIN_FAILED` del driver se propagan con su código/exit.
- .04 P Un fallo en un adjunto de `--all` no produce resultados parciales: staging limpio y caché previa intacta.
- .05 N `--all` con fallos en los índices 2 y 3 informa el fallo del índice 2 (primer fallo en orden de índice), no el último ni un agregado.

## 5. Documentación del milestone

- `docs/INTERFACES.md`: API del motor, flujo de staging/publicación, rutas de caché, permisos, resultados de respuesta, errores y política de caché efímera.

## 6. Criterios de cierre

1. Suite verde sin fallos nuevos; UT-ATT verdes solos.
2. No queda ningún archivo nuevo ni parcial en caché ni staging tras fallos previos a la publicación (probado con inyección de fallos, incluidos `EACCES` y `ENOSPC`).
3. Permisos `0700`/`0600` verificados en POSIX; publicación atómica verificada; `E_IO`/`E_PERMISSION` con exit 3.
4. Sin cambios en `cli.py`, `search.py`, adaptadores ni config.

## 7. Handoff y HITL

- Reportar: firma de `recover`, flujo de staging/publicación, decisiones de límites y caché, tests.
- HITL: solo si el host del dueño tiene `~/.mailquery/tmp` y `~/.mailquery/attachments` en sistemas de archivos distintos; en ese caso la publicación puede fallar y se devuelve `E_IO` (DP-01) sin cambiar el mecanismo.

## 8. Riesgos del milestone

| Riesgo | Mitigación |
|---|---|
| Crash a mitad de publicación deja archivos completos | Aceptado y documentado (PRD §15); ningún archivo parcial |
| Caché manipulada por el usuario | `sha256` del archivo servido; si el driver informa tamaño y no coincide se re-extrae; riesgo aceptado |
| Rutas largas en Windows | Fallback de 32 hex desde M06/M01; probado en UT-ATT-04 |

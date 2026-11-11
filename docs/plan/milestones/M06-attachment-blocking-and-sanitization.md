# M06 — Adjuntos: bloqueo y sanitización

| Campo | Valor |
|-------|-------|
| Fase | D — Recuperación de adjuntos (núcleo) |
| Depende de | M01, M03, M04 |
| Bloquea a | M07, M08–M11 |
| ACs | AC-09, AC-10, AC-11; AC-15 (errores de lectura en la evaluación) |
| Grupos de test | UT-ATT-01..05 |
| Write scope | `src/mailquery/attachments/**` (nuevo: catálogo, bloqueo, sanitización y rutas), `src/mailquery/errors.py` (solo si falta algún código de §11.7), `docs/INTERFACES.md`, `tests/test_attachments.py` (nuevo), `tests/fixtures/attachment_samples.py` (nuevo: constructores de bytes y nombres) |
| No tocar | `cli.py`, `search.py`, `state.py`, `config.py`, `backends/**` (salvo nada), `PRD.md`, `PRD-v2.1.md`, `docs/plan/**` |
| Estado | ⚪ |

## 1. Objetivo

Implementar las funciones puras del núcleo de adjuntos: catálogo de extensiones peligrosas, reglas de bloqueo de nombres y *magic bytes*, decisión de bloqueo del **mensaje completo**, sanitización determinista del nombre y construcción de la ruta de caché. Este milestone no escribe en disco ni sirve caché; entrega la política que usarán M07 (caché/staging), M08 (`show`/`attachment`) y M09/M10 (adaptadores).

## 2. Contexto normativo

- PRD-v2.1 §6.2 RF-43, RF-45, RF-47, RF-48, RF-49 (solo la parte de evaluación); §10.3 completo (bloqueo, catálogo, nombre sanitizado); §10.4 (caché efímera: solo como contexto), §11.3 filas 8–13 y 15, §11.7 (`E_ATTACHMENT_BLOCKED`, `E_ATTACHMENT_TOO_LARGE`, `E_ATTACHMENT_UNAVAILABLE`, `E_ATTACHMENT_UNREADABLE`), §14 AC-09/AC-10/AC-11/AC-15.
- Base 2.0.1: `backends/base.py:98-101,111-121` (`AttachmentRow` solo `name`), `search.py:471-493,518` (`show.attachments`), `emlx.py:371-385` (nombres MIME), `outlook.py:729-740` (nombres y adjuntos ocultos).
- Contratos de entrada: C1 (operaciones de adjuntos del driver, entrega de bytes decodificados y `index` estable) y C3 (uid string).

## 3. Tareas

| ID | Tarea | Archivos | Detalle |
|----|-------|----------|---------|
| M06-T01 | Normalización y catálogo | `attachments/catalog.py` (nuevo) | Constante del catálogo de §10.3.2 por categorías, comparación case-insensitive, y normalización NFKC **una sola vez** (se conserva también la forma cruda para controles). |
| M06-T02 | Bloqueo de nombre | `attachments/blocking.py` (nuevo) | Reglas de §10.3.1 punto 1 sobre la forma normalizada y la cruda: NUL y categorías `Cc`/`Cf`/`Cs`/`Co` (incluye RLO `\u202e`); separadores `/` y `\`; segmentos `..`; prefijo de unidad y cualquier `:` (evita NTFS ADS); extensiones peligrosas simples o **encadenadas** (tras recortar puntos/espacios finales); nombres reservados `CON`, `PRN`, `AUX`, `NUL`, `COM1..9`, `LPT1..9` (raíz antes del primer punto, case-insensitive). Función pura `classify_name(original_name)` que devuelve la decisión y el motivo; no lanza por sí misma: el motor de M07 decide el código. |
| M06-T03 | Bloqueo de contenido | `attachments/blocking.py` | *Magic bytes* de §10.3.1 punto 2 sobre el **primer bloque decodificado** (máximo 512 bytes, antes de crear archivo): `MZ`, ELF, Mach-O 32/64 en sus cuatro variantes y universal, `#!`. No es recursivo: no se inspeccionan ZIP/OLE/PDF/imágenes ni firmas fuera del offset 0 (riesgo aceptado §15). Un flujo vacío (0 bytes) es válido. |
| M06-T04 | Sanitización y rutas | `attachments/sanitize.py` (nuevo), `attachments/paths.py` (nuevo) | `sanitize_name(original_name, index)`: NFKC; vacío ⇒ `attachment`; recorte de espacios/puntos y eliminación de puntos iniciales; sustitución de espacio y `<>:"/\|?*` por `_` sin colapsar; extensión ≤ 20 bytes sin partir carácter; raíz ≤ 150 bytes; **el nombre final incluye el prefijo `NN_`** y mide ≤ 153 bytes (si el prefijo mide > 3 bytes por índice ≥ 100, se reduce la raíz); todo determinista e idempotente. `message_dir(home, uid)` y `attachment_path(home, uid, sanitized_name)`: `~/.mailquery/attachments/<driver>/<native_id>/<sanitized_name>` (**una sola vez el prefijo**, porque ya forma parte de `sanitized_name`; nunca se vuelve a anteponer `NN_`). Si la ruta excede el límite de la plataforma (presupuesto conservador de 240 bytes en Windows; en POSIX el límite real de `PATH_MAX`/componente, D9) o el componente `<native_id>` excede el límite, se sustituye `<native_id>` por el identificador estable de 32 hex de `SHA-256(uid)` que expone M01. |
| M06-T05 | Evaluación del mensaje completo | `attachments/screening.py` (nuevo) | Dos funciones con el orden de §11.3: (a) `screen_names(entries)` evalúa **todos** los nombres de todos los adjuntos (no solo los solicitados) y devuelve la decisión de bloqueo con el índice/nombre causante; se ejecuta **antes** de los límites (M07). (b) `screen_content(entries, requested_indices, open_stream)` inspecciona solo el contenido de los solicitados (`--index N`: ese; `--all`: todos) y devuelve bloqueo, `E_ATTACHMENT_UNREADABLE` o el motivo de no disponibilidad; se ejecuta **después** de los límites y durante la extracción. Si un nombre dispara una regla, se bloquea el mensaje entero antes de mirar tamaños; si el contenido dispara, se bloquea el mensaje entero sin extracción parcial. No escribe ni abre rutas de caché. |
| M06-T06 | Tests, muestras y documentación | `tests/test_attachments.py` (nuevo), `tests/fixtures/attachment_samples.py` (nuevo), `docs/INTERFACES.md` | UT-ATT-01..05; muestras de bytes (MZ, ELF, Mach-O, `#!`, PDF/ZIP permitidos, vacío) y de nombres (tabla del catálogo, traversal, reservados, Unicode). Documentar las funciones, la decisión de bloqueo y la ruta de caché. |

## 4. Casos de prueba

### UT-ATT-01 — Bloqueo de nombre (AC-10, §10.3.1/§10.3.2)

- .01 N Cada extensión del catálogo, por categoría (subtests): ejecutables, scripts, instaladores, accesos directos/registro, intérpretes/bytecode, Office con macros ⇒ bloqueada.
- .02 N Extensiones encadenadas `factura.pdf.exe`, `reporte.pdf.bat.cmd` (también con puntos/espacios finales) ⇒ bloqueada.
- .03 N `../`, `/`, `\`, segmentos `..`, prefijo de unidad `C:`, cualquier `:` (ADS) ⇒ bloqueada.
- .04 N NUL o caracteres `Cc`/`Cf`/`Cs`/`Co` en el nombre crudo, incluido RLO `\u202e` ⇒ bloqueada.
- .05 N Nombres reservados `CON`, `PRN`, `AUX`, `NUL`, `COM1..COM9`, `LPT1..LPT9` (raíz antes del primer punto, cualquier caja) ⇒ bloqueada.
- .06 N Variantes NFKC (`ＣＯＮ`, fullwidth, ligaduras) que normalizan a una regla ⇒ bloqueada; la normalización se aplica una sola vez.
- .07 P Nombres permitidos: `Factura Octubre 2026.pdf`, `présupuesto #3.docx`, `reporte_2026.xlsx`, `factura.pdf` ⇒ permitidos.
- .08 B Nombre vacío o solo espacios/puntos: no bloquea por nombre; la sanitización decide `attachment`.
- .09 P Escaneo de imports: `src/mailquery/attachments/**` solo usa stdlib y el propio paquete (RNF-12); sin dependencias nuevas.

### UT-ATT-02 — Bloqueo de contenido (AC-10, §10.3.1/§10.3.2)

- .01 N `MZ`, `\x7fELF`, Mach-O 32/64 (cuatro variantes), universal y `#!` en los primeros bytes ⇒ bloqueado.
- .02 B Se leen como máximo 512 bytes; la firma solo cuenta en el offset 0; una firma en el offset 8 no bloquea.
- .03 B Un flujo vacío (0 bytes) es válido y no tiene firma.
- .04 P PDF, ZIP, OLE, PNG y texto no están en el catálogo y pasan el control de contenido (blocklist no exhaustiva; riesgo aceptado).
- .05 N Un flujo que no se puede leer ⇒ `E_ATTACHMENT_UNREADABLE`, sin extracción del mensaje.

### UT-ATT-03 — Bloqueo del mensaje completo (AC-09)

- .01 N Mensaje con un adjunto hostil y otro seguro: `--index` del seguro ⇒ bloqueo; `--index` del hostil ⇒ bloqueo; `--all` ⇒ bloqueo.
- .02 N El bloqueo por contenido de un adjunto solicitado bloquea también los demás solicitados.
- .03 N La decisión de bloqueo indica el índice y el nombre causante (`attachment 3 ('CON.fdp.exe') ...`), sin controles en el texto.
- .04 P Un mensaje con todos los nombres y contenidos seguros devuelve el plan de extracción de los solicitados.
- .05 N El contenido de un adjunto **no solicitado** no se inspecciona (solo su nombre); se validará si se pide en el futuro.
- .06 N Staging/caché no se tocan en este milestone: las funciones de pantalla no escriben (se verifica que no abren rutas ni crean archivos).

### UT-ATT-04 — Sanitización y ruta (AC-11, §10.3.3)

- .01 P `" invoice.pdf "` (índice 1) ⇒ `01_invoice.pdf`; `"Factura Octubre 2026.pdf"` (índice 2) ⇒ `02_Factura_Octubre_2026.pdf`.
- .02 P NFKC, recorte de espacios/puntos, eliminación de puntos iniciales (dotfiles), sustitución de espacio y `<>:"/\|?*` por `_` sin colapsar; nombre vacío ⇒ `attachment`.
- .03 B Extensión ≤ 20 bytes sin partir carácter; raíz ≤ 150 bytes; nombre final ≤ 153 bytes; índice ≥ 100 (prefijo > 3 bytes) reduce la raíz en la diferencia.
- .04 B El mismo `original_name` e `index` producen siempre el mismo `sanitized_name`; `attachment_path` recibe ese nombre ya prefijado y no vuelve a anteponer `NN_` (sin doble prefijo); no depende de la plataforma.
- .05 P Ruta: `~/.mailquery/attachments/<driver>/<native_id>/<sanitized_name>`, donde `<sanitized_name>` ya incluye `NN_`; se comprueba que no aparece un segundo prefijo.
- .06 B Ruta > límite de la plataforma (240 bytes en Windows; `PATH_MAX`/componente en POSIX) o componente `<native_id>` demasiado largo ⇒ identificador estable 32 hex `SHA-256(uid UTF-8)`; determinista y sin punto/espacio.
- .07 B Índices 1, 9, 99, 100 y 1000: prefijo `01_`… `1000_`; nombres finales ≤ límite.

### UT-ATT-05 — Motivos de no disponibilidad y errores de flujo (AC-15 parcial)

- .01 N Un adjunto solicitado marcado `not_local`, `not_downloaded`, `unsupported` o `network` por el driver ⇒ `E_ATTACHMENT_UNAVAILABLE` con el motivo.
- .02 N Un adjunto solicitado corrupto/S/MIME/ilegible según el driver ⇒ `E_ATTACHMENT_UNREADABLE` con el motivo, incluso si la lista de adjuntos queda vacía.
- .03 N Un error de lectura del stream de un solicitado ⇒ `E_ATTACHMENT_UNREADABLE` y ningún archivo del mensaje.
- .04 N Un mensaje con `attachments: []` sin señal de S/MIME/ilegible lo trata el comando como “sin adjuntos” (M08); la función de pantalla de nombres no convierte una lista vacía en bloqueo. El caso de mensaje vacío se prueba en M08.
- .05 P Un adjunto no solicitado con motivo de no disponibilidad no se evalúa.

## 5. Documentación del milestone

- `docs/INTERFACES.md`: catálogo, funciones de bloqueo (nombre/contenido), orden de evaluación (nombres → límites → contenido → disponibilidad), sanitización y ruta de caché; el núcleo es dueño de la validación y el driver solo entrega metadatos y bytes decodificados.

## 6. Criterios de cierre

1. Suite verde sin fallos nuevos; UT-ATT-01..05 verdes solos.
2. Las tablas de §10.3.2 y los ejemplos de §10.3.3 están cubiertos literalmente, incluida la ruta con un solo prefijo `NN_` y los límites por plataforma (D9).
3. Ninguna función del milestone escribe en disco ni lee la caché.
4. El motor no confunde “sin adjuntos” con “S/MIME/ilegible”: el motivo se propaga.
5. El orden nombres → límites → contenido → disponibilidad queda documentado en `INTERFACES.md` y probado en el borde nombre/tamaño.

## 7. Handoff y HITL

- Reportar: nombres/firmas de las funciones de M06, catálogo implementado, decisiones de normalización y pruebas.
- HITL: solo si un nombre o flujo no puede clasificarse sin abrir contenido no solicitado; el PRD manda bloquear y no se relaja la regla.

## 8. Riesgos del milestone

| Riesgo | Mitigación |
|---|---|
| Falsos positivos del catálogo (`install.sh`, correos de desarrollo) | Es el comportamiento normativo: se bloquea el mensaje completo; documentado en el PRD §15 |
| NFKC altera nombres legítimos | La sanitización se aplica solo a adjuntos permitidos; el caso de bloqueo usa NFKC + forma cruda y está cubierto por tests |
| Dependencia de la representación de bytes del driver | M06 solo consume el stream ya decodificado; los adaptadores (M09/M10) garantizan esa frontera |

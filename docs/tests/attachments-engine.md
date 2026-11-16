# Motor de adjuntos

#### UT-ATT-01 — Bloqueo de nombre

Requisitos: AC-10 · Archivo: `tests/test_attachments.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Cada extensión del catálogo, por categoría (subtests): ejecutables, scripts, instaladores, accesos directos/registro, intérpretes/bytecode, Office con macros ⇒ bloqueada. |
| .02 | N | Extensiones encadenadas `factura.pdf.exe`, `reporte.pdf.bat.cmd` (también con puntos/espacios finales) ⇒ bloqueada. |
| .03 | N | `../`, `/`, `\`, segmentos `..`, prefijo de unidad `C:`, cualquier `:` (ADS) ⇒ bloqueada. |
| .04 | N | NUL o caracteres `Cc`/`Cf`/`Cs`/`Co` en el nombre crudo, incluido RLO `\u202e` ⇒ bloqueada. |
| .05 | N | Nombres reservados `CON`, `PRN`, `AUX`, `NUL`, `COM1..COM9`, `LPT1..LPT9` (raíz antes del primer punto, cualquier caja) ⇒ bloqueada. |
| .06 | N | Variantes NFKC (`ＣＯＮ`, fullwidth, ligaduras) que normalizan a una regla ⇒ bloqueada; la normalización se aplica una sola vez. |
| .07 | P | Nombres permitidos: `Factura Octubre 2026.pdf`, `présupuesto #3.docx`, `reporte_2026.xlsx`, `factura.pdf` ⇒ permitidos. |
| .08 | B | Nombre vacío o solo espacios/puntos: no bloquea por nombre; la sanitización decide `attachment`. |
| .09 | P | Escaneo de imports: `src/mailquery/attachments/**` solo usa stdlib y el propio paquete (RNF-12); sin dependencias nuevas. |

#### UT-ATT-02 — Bloqueo de contenido

Requisitos: AC-10 · Archivo: `tests/test_attachments.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | `MZ`, `\x7fELF`, Mach-O 32/64 (cuatro variantes), universal y `#!` en los primeros bytes ⇒ bloqueado. |
| .02 | B | Se leen como máximo 512 bytes; la firma solo cuenta en el offset 0; una firma en el offset 8 no bloquea. |
| .03 | B | Un flujo vacío (0 bytes) es válido y no tiene firma. |
| .04 | P | PDF, ZIP, OLE, PNG y texto no están en el catálogo y pasan el control de contenido (blocklist no exhaustiva; riesgo aceptado). |
| .05 | N | Un flujo que no se puede leer ⇒ `E_ATTACHMENT_UNREADABLE`, sin extracción del mensaje. |

#### UT-ATT-03 — Bloqueo del mensaje completo

Requisitos: AC-09 · Archivo: `tests/test_attachments.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Mensaje con un adjunto hostil y otro seguro: `--index` del seguro ⇒ bloqueo; `--index` del hostil ⇒ bloqueo; `--all` ⇒ bloqueo. |
| .02 | N | El bloqueo por contenido de un adjunto solicitado bloquea también los demás solicitados. |
| .03 | N | La decisión de bloqueo indica el índice y el nombre causante (`attachment 3 ('CON.fdp.exe')...`), sin controles en el texto. |
| .04 | P | Un mensaje con todos los nombres y contenidos seguros devuelve el plan de extracción de los solicitados. |
| .05 | N | El contenido de un adjunto **no solicitado** no se inspecciona (solo su nombre); se validará si se pide en el futuro. |
| .06 | N | Las funciones de pantalla no escriben: no abren rutas ni crean archivos de staging o caché. |

#### UT-ATT-04 — Sanitización y ruta

Requisitos: AC-11 · Archivo: `tests/test_attachments.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `" invoice.pdf "` (índice 1) ⇒ `01_invoice.pdf`; `"Factura Octubre 2026.pdf"` (índice 2) ⇒ `02_Factura_Octubre_2026.pdf`. |
| .02 | P | NFKC, recorte de espacios/puntos, eliminación de puntos iniciales (dotfiles), sustitución de espacio y `<>:"/\\|?*` por `_` sin colapsar; nombre vacío ⇒ `attachment`. |
| .03 | B | Extensión ≤ 20 bytes sin partir carácter; raíz ≤ 150 bytes; nombre final ≤ 153 bytes; índice ≥ 100 (prefijo > 3 bytes) reduce la raíz en la diferencia. |
| .04 | B | El mismo `original_name` e `index` producen siempre el mismo `sanitized_name`; `attachment_path` recibe ese nombre ya prefijado y no vuelve a anteponer `NN_` (sin doble prefijo); no depende de la plataforma. |
| .05 | P | Ruta: `~/.mailquery/attachments/<driver>/<native_id>/<sanitized_name>`, donde `<sanitized_name>` ya incluye `NN_`; se comprueba que no aparece un segundo prefijo. |
| .06 | B | Ruta > límite de la plataforma (240 bytes en Windows; `PATH_MAX`/componente en POSIX) o componente `<native_id>` demasiado largo ⇒ identificador estable 32 hex `SHA-256(uid UTF-8)`; determinista y sin punto/espacio. |
| .07 | B | Índices 1, 9, 99, 100 y 1000: prefijo `01_`… `1000_`; nombres finales ≤ límite. |

#### UT-ATT-05 — Motivos de no disponibilidad y errores de flujo

Requisitos: AC-15 · Archivo: `tests/test_attachments.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Un adjunto solicitado marcado `not_local`, `not_downloaded`, `unsupported` o `network` por el driver ⇒ `E_ATTACHMENT_UNAVAILABLE` con el motivo. |
| .02 | N | Un adjunto solicitado corrupto/S/MIME/ilegible según el driver ⇒ `E_ATTACHMENT_UNREADABLE` con el motivo, incluso si la lista de adjuntos queda vacía. |
| .03 | N | Un error de lectura del stream de un solicitado ⇒ `E_ATTACHMENT_UNREADABLE` y ningún archivo del mensaje. |
| .04 | N | Un mensaje con `attachments: []` sin señal de S/MIME/ilegible lo trata el comando como “sin adjuntos”; la función de pantalla de nombres no convierte una lista vacía en bloqueo. El caso de mensaje vacío por CLI es UT-ATC-03.02. |
| .05 | P | Un adjunto no solicitado con motivo de no disponibilidad no se evalúa. |

#### UT-ATT-06 — Límites

Requisitos: AC-13 · Archivo: `tests/test_attachments.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | B | Exactamente en el límite permitido; un byte más ⇒ excede; MiB = 1.048.576 bytes. |
| .02 | N | `max_file_size_mb` excedido con tamaño conocido ⇒ `E_ATTACHMENT_TOO_LARGE` antes de escribir; nada nuevo en caché. |
| .03 | N | `max_total_size_mb` excedido con tamaños conocidos ⇒ falla antes de escribir; los aciertos de caché cuentan con su tamaño real. |
| .04 | N | `max_count` con `--all` incluye aciertos de caché; `--index` no está sujeto a `max_count`. |
| .05 | N | Tamaño desconocido que excede durante el streaming ⇒ aborta, limpia staging y conserva la caché previa. |
| .06 | P | Las plantillas de límite de §12.11 incluyen el límite, el índice y el nombre cuando corresponde; el hint sugiere `--index`. |
| .07 | N | Orden de §12.11: mensaje con un nombre bloqueado y un adjunto solicitado que excede `max_file_size_mb` ⇒ `E_ATTACHMENT_BLOCKED` (nombre), no `E_ATTACHMENT_TOO_LARGE`; los nombres se evalúan antes que los límites. |

#### UT-ATT-07 — Staging y publicación atómica

Requisitos: AC-12 · Archivo: `tests/test_attachments.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | La primera extracción escribe primero en `tmp/staging` (`0700`, archivo `0600`) y aparece en la caché solo al publicar; `cached: false`. |
| .02 | N | Un aborto por contenido, límite o lectura antes de publicar no deja archivos nuevos ni parciales en la caché ni staging propio. |
| .03 | N | Un fallo de `os.replace`/E/S en la publicación ⇒ `E_IO` (exit 3); no se publica nada; staging limpio. |
| .04 | P | Una extracción correcta publica todos los archivos solicitados y devuelve `saved: true` con tamaño y SHA-256 del archivo servido. |
| .05 | B | Un fallo inyectado en `os.replace` deja el archivo anterior intacto (si existía) y no hay archivos truncados ni parciales visibles; la siguiente invocación reintenta la extracción. |
| .06 | N | `PermissionError` (`EACCES`) al crear el directorio de caché o el archivo de staging ⇒ `E_PERMISSION` (exit 3), sin parciales. |
| .07 | N | `ENOSPC`/fallo de E/S al escribir en staging o al publicar ⇒ `E_IO` (exit 3), sin parciales; el caso de `os.replace` está en.03. |

#### UT-ATT-08 — Caché, `--force` y tamaño esperado

Requisitos: AC-12/AC-20 · Archivo: `tests/test_attachments.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Primera extracción `cached: false`; segunda invocación sin `--force` `cached: true` con `size_bytes`/`sha256` del archivo existente y sin re-extraer. |
| .02 | P | `--force` re-extrae y devuelve `cached: false`, reemplazando atómicamente. |
| .03 | B | Tamaño esperado del driver distinto del archivo en caché ⇒ se trata como miss y se re-extrae. |
| .04 | P | Un mensaje bloqueado no devuelve ningún `cached_path` ni sirve caché aunque exista. |
| .05 | N | Un archivo de caché que no es regular (symlink o directorio) se trata como miss; la publicación no sigue el symlink. |
| .06 | P | La ruta publicada es `~/.mailquery/attachments/<driver>/<native_id>/<sanitized_name>` (el `sanitized_name` ya lleva `NN_`; no hay doble prefijo) y el `output_dir` es su directorio. |

#### UT-ATT-09 — Permisos

Requisitos: AC-12, RNF-13 · Archivo: `tests/test_attachments.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | POSIX: directorios `0700`, archivos `0600`, sin bit `+x`; el staging también. |
| .02 | P | Windows (patched): no se relajan permisos; el archivo hereda la ACL del perfil. |
| .03 | N | Un archivo previamente en caché conserva su hash/tamaño si la nueva extracción falla antes de publicar. |

#### UT-ATT-10 — Caché efímera y borrado concurrente

Requisitos: AC-20 · Archivo: `tests/test_attachments.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Caché vacía o inexistente no es un error: se extrae. |
| .02 | P | Un archivo borrado entre `show` y `attachment` (o durante la ejecución) se trata como miss y se re-extrae una vez. |
| .03 | N | Si la re-extracción falla tras el borrado ⇒ `E_ATTACHMENT_UNAVAILABLE`. |
| .04 | N | La app no barre ni purga la caché al arrancar ni durante la ejecución; no inspecciona contenido de la caché. |
| .05 | P | Ciclo de vida DP-03 (caché): actualizar un plugin no cambia `config.toml`, `state.json` ni los archivos de caché (byte a byte); desinstalarlo conserva los archivos de caché intactos y no los borra. |

#### UT-ATT-11 — Motivos y errores durante la extracción

Requisitos: AC-15 · Archivo: `tests/test_attachments.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | El driver informa `not_local`/`not_downloaded`/`unsupported`/`network` al abrir el stream ⇒ `E_ATTACHMENT_UNAVAILABLE` con el motivo. |
| .02 | N | Corrupto/S/MIME/ilegible ⇒ `E_ATTACHMENT_UNREADABLE` con el motivo, antes de la comprobación de “0 adjuntos” (esa comprobación es del comando). |
| .03 | N | `E_PERMISSION`, `E_CLIENT_BUSY` y `E_PLUGIN_FAILED` del driver se propagan con su código/exit. |
| .04 | P | Un fallo en un adjunto de `--all` no produce resultados parciales: staging limpio y caché previa intacta. |
| .05 | N | `--all` con fallos en los índices 2 y 3 informa el fallo del índice 2 (primer fallo en orden de índice), no el último ni un agregado. |
| .06 | N | El plazo de extracción inyectado vence como `E_CLIENT_TIMEOUT`. |

#### UT-ATT-12 — Manifiesto por mensaje y archivos no verificados

Requisitos: RF-45, RF-51 · Archivo: `tests/test_attachments.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Cada archivo publicado se registra en el manifiesto con nombre, tamaño y SHA-256; las demás entradas se conservan. |
| .02 | N | Un archivo sin entrada en el manifiesto nunca se sirve: se reemplaza y se registra. |
| .03 | N | Un archivo sustituido con el mismo tamaño se detecta por SHA-256 y se reemplaza. |
| .04 | B | Un tamaño distinto del registrado es un fallo de caché antes de calcular ningún hash. |
| .05 | N | Si la nueva extracción falla, se borran el archivo no verificado y su entrada. |
| .06 | N | Un `--force` que falla conserva el archivo registrado y su entrada. |
| .07 | N | Un manifiesto ilegible, de otra versión o mal formado no es fiable: todos sus archivos quedan sin verificar. |
| .08 | N | Una entrada registrada con otro nombre sanitizado no es un acierto. |
| .09 | N | Un manifiesto que es enlace simbólico no se lee ni se sigue: se reemplaza. |
| .10 | N | Un directorio de mensaje o de driver que es enlace simbólico ⇒ `E_IO`; no se escribe nada. |
| .11 | N | A través de un directorio de mensaje enlazado no se sirve ni se borra nada. |
| .12 | N | Un directorio en la ruta de caché se conserva (sin borrado recursivo). |
| .13 | N | Un reemplazo que rechaza el sistema operativo (archivo abierto en Windows) ⇒ `E_IO`; el archivo no verificado nunca se sirve. |
| .14 | B | Un archivo publicado cuya entrada no se pudo escribir se vuelve a extraer en la siguiente corrida (manifiesto best-effort). |
| .15 | P | `cached_path` de `show` no lee el archivo ni el manifiesto: solo comprueba que el archivo existe y es regular. |

#### UT-ACT-01 — `pdf-javascript`

Requisitos: RF-62 · Archivo: `tests/test_active_content.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Un PDF con `/JavaScript`, `/JS` o `/Launch` seguido de espacio, `<<`, `(` o del final del archivo ⇒ `("pdf-javascript",)`. |
| .02 | P | Nombres con `#xx` (`/J#61vaScript`, `/#4A#53`, `/L#61unch`) ⇒ detectado. |
| .03 | N | `/JavaScriptX`, `/JSON`, `/Launcher` y `/javascript` (minúsculas) no cuentan. |
| .04 | N | `%PDF-` después del byte 1.024 ⇒ no es PDF y no se detecta. |
| .05 | N | Un PDF sin esos nombres ⇒ `()`. |
| .06 | B | `%PDF-` cuyo último byte es exactamente el byte 1.024 del archivo (empieza en el desplazamiento 1.019) ⇒ es PDF y se detecta. |
| .07 | B | Un `#xx` con hexadecimal inválido (`/J#zzavaScript`) no se decodifica ni cuenta; `/JS` justo al final del archivo, sin delimitador, cuenta. |

#### UT-ACT-02 — `office-macros`

Requisitos: RF-62 · Archivo: `tests/test_active_content.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `.doc` y `.xls` OLE con `_VBA_PROJECT` en UTF-16LE ⇒ detectado. |
| .02 | N | OLE sin `_VBA_PROJECT`; `_VBA_PROJECT` en ASCII dentro de un OLE; la cadena UTF-16LE en un archivo que no empieza por la firma OLE ⇒ no detectado. |
| .03 | P | ZIP con `xl/vbaProject.bin` y con `vbaProject.bin` en la raíz ⇒ detectado. |
| .04 | N | `.docx`, `.xlsx` y `.pptx` sin macros, con carpetas y entradas `.bin` propias del formato (`word/embeddings/oleObject1.bin`) ⇒ `()`. |

#### UT-ACT-03 — `archive-executable`

Requisitos: RF-62 · Archivo: `tests/test_active_content.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | ZIP con `docs/factura.pdf.exe` (extensión encadenada) y ZIP con `run.bat` ⇒ detectado. |
| .02 | P | ZIP cifrado con una entrada `.exe` ⇒ detectado; el bit de cifrado está activo en las cabeceras local y central y `zipfile` sigue listando el nombre. |
| .03 | P | Separador `\` en el nombre (`dir\x.scr`) ⇒ se toma el último segmento y se detecta. |
| .04 | N | ZIP con solo PDF, con solo `.bin` o con `..`/`:` en nombres inocuos ⇒ `()`. |
| .05 | N | Archivo que empieza por `PK\x03\x04` con el directorio central ilegible ⇒ `()`. |
| .06 | P | Entrada `RUN.EXE` (mayúsculas) ⇒ detectado, porque la extensión se compara sin distinguir mayúsculas. |
| .07 | N | Entrada de directorio terminada en `/` (`payload.exe/`): el último segmento está vacío; un ZIP solo con esa entrada ⇒ `()`. |
| .08 | N | `zipfile.ZipFile` lanza una excepción distinta de `BadZipFile` (`ValueError` u `OSError`, simulada con `mock.patch`) ⇒ `()` sin excepción. |

#### UT-ACT-04 — Propiedades del detector

Requisitos: RF-62 · Archivo: `tests/test_active_content.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Un ZIP con `vbaProject.bin` y un `.exe` da los dos tipos en el orden de `ACTIVE_CONTENT_TYPES`. |
| .02 | B | Nunca descomprime: con `ZipFile.open`, `read` y `extract` parcheados para fallar, todos los casos dan el mismo resultado y ninguna de las tres se llama. |
| .03 | B | Archivo vacío y archivo inexistente ⇒ `()` sin excepción. |
| .04 | B | Determinismo: dos llamadas sobre el mismo archivo dan el mismo resultado. |

#### UT-ACT-05 — `W_ATTACHMENT_ACTIVE_CONTENT` en `attachment`

Requisitos: AC-H12 (delta `PRD-v2.2.md`) · Archivo: `tests/test_active_content.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Ejemplo A7 de §8 (`factura.pdf` con `/JavaScript` índice 1, `docs.zip` con `factura.pdf.exe` índice 2): dos warnings con los textos literales, en el orden de `attachments[]`; los dos archivos se entregan; exit 0. |
| .02 | P | Servido desde la caché (segunda corrida): los mismos warnings. |
| .03 | N | El detalle no contiene nombres de archivo; un adjunto sin marcadores no da warning. |
| .04 | N | Un adjunto que bloquea el catálogo sigue dando `E_ATTACHMENT_BLOCKED` (exit 4). |
| .05 | P | Plugin `"remote"`: el mismo warning que con un driver local. |

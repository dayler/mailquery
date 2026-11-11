# M08 — Comando `attachment` y `show.attachments`

| Campo | Valor |
|-------|-------|
| Fase | D — Recuperación de adjuntos (núcleo) |
| Depende de | M05, M07 (y M02, M03 como contratos) |
| Bloquea a | M09–M11 |
| ACs | AC-07, AC-08, AC-12 (CLI), AC-14 (CLI), AC-15 (CLI), AC-17 (extracción), AC-19 (event=end), AC-21 (parcial) |
| Grupos de test | UT-ATC-01..10; actualización de UT-CLI-06/07/09, de las aserciones inline de `attachments` y de los golden tests de `show` |
| Write scope | `src/mailquery/cli.py`, `src/mailquery/search.py` (solo `run_show` y la composición de `attachments`), `docs/INTERFACES.md`, `tests/test_cli.py`, `tests/test_search.py` (solo `show`), `tests/test_integration.py`, `tests/test_outlook.py` (solo aserciones de `show.attachments`), `tests/fakes/attachment_backend.py` (nuevo), `tests/fixtures/expected/show_*.json`, `tests/fixtures/expected/outlook/show*.json` |
| No tocar | `state.py`, `config.py`, `attachments/**` (el motor ya expone `deadline` desde M07), `backends/apple_mail.py`, `backends/outlook.py`, `PRD.md`, `PRD-v2.1.md`, `docs/plan/**` |
| Estado | ⚪ |

## 1. Objetivo

Conectar el motor de adjuntos a la CLI: nuevo subcomando `mailquery attachment <uid>` con la precedencia de validaciones de §11.3, el contrato JSON de §11.2, los textos de error de referencia, la ayuda de §11.4 y el log `event=end` con conteos. Además, `show <uid>` cambia `message.attachments[]` a `{index, name, cached_path}` sin escribir nunca en disco.

## 2. Contexto normativo

- PRD-v2.1 §6.2 RF-42–RF-49 (comportamiento visible), §9.2 (flujo), §11.1/§11.2 (comando, sintaxis y campos), §11.3 completo (precedencia y textos), §11.4 (ayuda), §11.5 (ejemplos A–H), §11.7 (mensajes), §11.8 (sin warnings nuevos), §12.1 (`event=end`), §12.2 (presupuesto de caché), §14 AC-07/AC-08/AC-12/AC-14/AC-15/AC-17/AC-19/AC-21.
- Base 2.0.1: `cli.py:231-399` (parser y subparsers), `cli.py:62-150` (epílogos y ayuda raíz), `cli.py:419-480` (validación temprana de uid), `cli.py:579-591` (`event=end`), `search.py:498-525,1250-1271` (payload de `show`), `search.py:471-493` (`attachments` de `show`), `tests/test_cli.py:178-435` (ayuda y versión), `UT-CLI-07`.
- Contratos de entrada: C5 (errores/timeout) y C7 (motor y caché).

## 3. Tareas

| ID | Tarea | Archivos | Detalle |
|----|-------|----------|---------|
| M08-T01 | Subcomando `attachment` | `cli.py`, `docs/INTERFACES.md` | `mailquery attachment <uid> (--index N \| --all) [--force]`; `<uid>` obligatorio; `--index` entero ≥ 1; mutuamente excluyentes. La ayuda raíz pasa a seis comandos y conserva la línea de exits: `0 ok \| 2 usage or config error \| 3 environment error \| 4 rejected query or blocked attachments \| 5 busy or transient error \| 6 mail client not running`. La ayuda de `-h` sigue sin ser JSON. |
| M08-T02 | Precedencia de validaciones | `cli.py` | Implementar el orden de §11.3: filas 1–6 **antes de abrir el store** (1) argumentos; (2) sintaxis del uid y driver instalado (incluido el uid legado sin prefijo); (3) config (incluye `[attachments]`/`[scope]`); (4) `enabled = false` solo para `attachment`; (5) carga del driver, `plugin_api`, capacidades, `parse_native_id`; driver instalado pero no declarado ⇒ `E_ACCOUNT_NOT_IN_SCOPE` sin cargarlo; `attachments: none` ⇒ `E_ATTACHMENT_UNAVAILABLE` (`unsupported`) antes del store; (6) resolución de cuenta/alcance. Con el store abierto: (7) existencia del mensaje (no oculto/borrado); (8) señal S/MIME/ilegible del driver al listar adjuntos ⇒ `E_ATTACHMENT_UNREADABLE` antes de contar; (9) mensaje sin adjuntos ⇒ `E_USAGE`; (10) índice fuera de rango ⇒ `E_USAGE` con el texto del ejemplo G. Después, el motor evalúa bloqueo de nombres (11), límites conocidos (12), stream/magic bytes (13), disponibilidad/timeout (14) y escritura (15). |
| M08-T03 | Contrato JSON de `attachment` | `cli.py` | Envolver el resultado del motor en el contrato de §12.5 del PRD.md con `uid`, `output_dir` (ruta absoluta del directorio del mensaje), `count`, `attachments[]` (`index`, `original_name`, `sanitized_name`, `saved`, `cached`, `path`, `size_bytes`, `sha256`) y `warnings[]`. Un acierto de caché devuelve `cached: true` y `saved: true`. El JSON de error sigue siendo `{ok:false, command, error:{code,message,hint}}`. |
| M08-T04 | `show.attachments` | `search.py` | `message.attachments[]` = `{index, name, cached_path}` con `index` 1..N estable y `name` original. `cached_path` es absoluto y se calcula con el nombre sanitizado; es `null` si no hay archivo en caché, si el nombre no es seguro (solo regla de nombre), si el driver tiene `attachments: "none"` o si el archivo no es regular (symlink, directorio o dispositivo). Un adjunto bloqueable **por contenido** sigue mostrando `cached_path` si el archivo regular existe: `show` no inspecciona contenido. Un driver `none` devuelve `[]`; S/MIME devuelve `[]`, conserva `W_BODY_*` de 2.0.1 y retira `W_ATTACHMENTS_UNAVAILABLE` (D6). `show` no aplica `enabled` y no escribe en disco. |
| M08-T05 | Timeout de extracción | `cli.py` | La extracción completa de un adjunto tiene un tope de 120 s; al vencer ⇒ `E_CLIENT_TIMEOUT` (exit 3), sin reintento, staging limpio y sin archivos nuevos. En Outlook el tope total no amplía el límite de 30 s por llamada COM (RF-33 del PRD.md). La CLI pasa `deadline` al motor (API de M07) y se prueba con reloj/deadline falso. |
| M08-T06 | Log `event=end` de `attachment` | `cli.py` | `exit_code` (siempre 0 en `end`), `count`, `cached`, `bytes` (total) y `duration_ms`; solo se emite en éxito. Un fallo registra `event=error` como en 2.0.1 y no emite `event=end` (D7). Se mantiene la prohibición de uids, `native_id`, nombres, rutas, cuentas y términos. `event=start` ya registra `backend=`/`drivers=` desde M04. |
| M08-T07 | Ayuda y textos | `cli.py` | Texto de §11.4 para `attachment --help` (usage, positional, options, examples, notes) con ≤ 100 columnas y sin ANSI; los mensajes de error usan los textos de referencia de §11.3 en inglés. Actualizar los epílogos de la ayuda raíz (`--version`, seis comandos, exits): son la raíz más seis subcomandos (7 invocaciones). |
| M08-T08 | Tests y goldens | `tests/test_cli.py`, `tests/test_search.py`, `tests/test_integration.py`, `tests/test_outlook.py` (solo `show.attachments`), `tests/fakes/attachment_backend.py` (nuevo), `tests/fixtures/expected/show_*.json`, `tests/fixtures/expected/outlook/show*.json` | UT-ATC-01..10. Actualizar los goldens de `show` (forma **y** valor: `show_smime_encrypted`/`outlook/show_smime` pasan a `[]` y, en macOS, `show_smime_encrypted` pierde `W_ATTACHMENTS_UNAVAILABLE`) sin tocar los de M03; son la única edición de forma/valor (M09/M10 no los reescriben). Renombrar los tests de ayuda de 5 comandos (UT-CLI-06), los de formato de uid (UT-CLI-07), actualizar las aserciones inline de `attachments` en `tests/test_search.py`/`tests/test_integration.py` y extender UT-CLI-09 con los códigos de adjuntos. Añadir el doble `attachment_backend.py` para los casos de CLI. |

## 4. Casos de prueba

### UT-ATC-01 — `show.attachments` (AC-07)

- .01 P Tres adjuntos ⇒ `[{index:1,name:"factura.pdf",cached_path:null}, …]` con índices estables 1..N.
- .02 P Con un archivo en caché (regular) ⇒ `cached_path` absoluto y correcto; sin caché ⇒ `null`.
- .03 N Nombre no seguro ⇒ `cached_path: null` aunque exista un archivo con ese nombre calculado; `show` no bloquea por contenido.
- .04 N `show` nunca escribe: no crea caché, staging ni `state.json`; el `~/.mailquery` solo puede cambiar como en 2.0.1 (log/lock/estado de `new`).
- .05 N Driver con `attachments: "none"` ⇒ `attachments: []`.
- .06 N S/MIME cifrado ⇒ `attachments: []`, sin `W_ATTACHMENTS_UNAVAILABLE`, conservando el warning de cuerpo de 2.0.1.
- .07 P El `index` de `show` coincide con el de `attachment` para el mismo mensaje.
- .08 N `[attachments].enabled = false` no afecta a `show`.
- .09 N `cached_path: null` si el archivo en caché es symlink, directorio o dispositivo, aunque exista; solo archivos regulares cuentan.
- .10 P Un adjunto que `attachment` bloquearía **por contenido** (`MZ`) pero con archivo regular en caché sigue mostrando `cached_path` no nulo: `show` no inspecciona contenido.

### UT-ATC-02 — Argumentos, uid y precedencia temprana (AC-08)

- .01 N Sin modo o con ambos ⇒ `E_USAGE` "attachment requires exactly one of --index or --all".
- .02 N `--index 0`, `-1`, `abc`, `1.5` ⇒ `E_USAGE` "invalid --index <v>: expected a positive integer (1 or greater)".
- .03 N uid malformado ⇒ `E_USAGE`; driver desconocido ⇒ `E_DRIVER_UNKNOWN`; ambos antes de crear el home, leer config o abrir el store, y sin escribir estado ni caché.
- .04 N `config.toml` inválido ⇒ `E_CONFIG_INVALID`; driver de `[scope]` no instalado ⇒ `E_DRIVER_UNKNOWN`.
- .05 N `enabled = false` ⇒ `E_ATTACHMENTS_DISABLED` (exit 2) antes de abrir el store; `show` no se ve afectado.
- .06 N Driver instalado pero no declarado ⇒ `E_ACCOUNT_NOT_IN_SCOPE` (exit 2) sin cargar el driver; el hint indica declarar la cuenta.
- .07 N `attachments: "none"` ⇒ `E_ATTACHMENT_UNAVAILABLE` (`unsupported`) antes de abrir el store.
- .08 P Entrada con uid legado sin prefijo: `attachment 83143 --index 1` en macOS y `attachment <EntryID> --index 1` en Windows se resuelven con el driver nativo y devuelven `uid` prefijado.
- .09 N Precedencia de filas adyacentes, table-driven: `--index 9` sobre mensaje con nombre bloqueado ⇒ `E_USAGE` (fila 10 antes que 11); `enabled=false` + `attachments:none` ⇒ `E_ATTACHMENTS_DISABLED` (fila 4 antes que 5); S/MIME + `--index 9` ⇒ `E_ATTACHMENT_UNREADABLE` (fila 8 antes que 10); uid con driver no instalado + `enabled=false` ⇒ `E_DRIVER_UNKNOWN` (fila 2 antes que 4).

### UT-ATC-03 — Validaciones con el store (AC-08)

- .01 N Mensaje inexistente, borrado u oculto ⇒ `E_USAGE` "message uid <uid> was not found".
- .02 N Mensaje sin adjuntos (sin señal S/MIME/ilegible) ⇒ `E_USAGE` "message <uid> has no attachments".
- .03 N S/MIME/ilegible con lista vacía ⇒ `E_ATTACHMENT_UNREADABLE` (exit 3) antes de la comprobación de “0 adjuntos”.
- .04 N `--index N` mayor que M ⇒ `E_USAGE` con el texto del ejemplo G ("out of range: message ... has 3 attachment(s) (valid: 1..3)").
- .05 P `--index` válido y `--all` recuperan los adjuntos solicitados.
- .06 N `--all` con varios fallos (nombre en índice 1, contenido en índice 2, límite en índice 3) informa el primer fallo en orden de índice y no devuelve parciales.
- .07 N Un `--index` de un adjunto con nombre seguro pero no disponible no evalúa el resto de adjuntos no solicitados.

### UT-ATC-04 — JSON, caché y `--force` por CLI (AC-12)

- .01 P Forma exacta de §11.2: `uid` prefijado, `output_dir` absoluto, `count`, ocho campos por adjunto, `warnings: []`.
- .02 P Primera corrida `cached:false`; segunda sin `--force` `cached:true` con `size_bytes`/`sha256` del archivo; `--force` `cached:false`.
- .03 N Mensaje bloqueado ⇒ `E_ATTACHMENT_BLOCKED` (exit 4), sin archivos, sin caché servida, con el `message`/`hint` de §11.5 C/D.
- .04 N Un fallo de límite o disponibilidad no devuelve resultados parciales.
- .05 N `--all` devuelve `count` = número de adjuntos devueltos.
- .06 N Un fallo de E/S del motor (`E_IO`) o de permisos (`E_PERMISSION`) sale por CLI con su exit 3 y sin archivos; no se convierte en `E_INTERNAL`.

### UT-ATC-05 — `[attachments]` y config (AC-14)

- .01 N `enabled=false` ⇒ `E_ATTACHMENTS_DISABLED` (2) antes del store; `show` intacto.
- .02 N Rangos inválidos y `max_total_size_mb < max_file_size_mb` ⇒ `E_CONFIG_INVALID`.
- .03 P Valores personalizados válidos se aplican en el comando.

### UT-ATC-06 — Disponibilidad y motivos (AC-15)

- .01 N `not_local`, `not_downloaded`, `unsupported`, `network` ⇒ `E_ATTACHMENT_UNAVAILABLE` (3) con el `message`/`hint` del motivo.
- .02 N S/MIME/corrupto/ilegible ⇒ `E_ATTACHMENT_UNREADABLE` (3) y nunca `E_USAGE` por “sin adjuntos”.
- .03 N `attachments: none` ⇒ `E_ATTACHMENT_UNAVAILABLE` antes del store.
- .04 P Adjunto vacío (0 bytes) se guarda y devuelve `size_bytes: 0`, `sha256` del vacío.

### UT-ATC-07 — Timeout de extracción (AC-17)

- .01 N Extracción que supera 120 s (plazo inyectado) ⇒ `E_CLIENT_TIMEOUT` (3), sin reintento, staging limpio y sin archivos nuevos.
- .02 N El timeout no escribe estado ni caché parcial.

### UT-ATC-08 — Log de `attachment` (AC-19)

- .01 P `event=end` de `attachment` con `exit_code`, `count`, `cached`, `bytes` y `duration_ms`.
- .02 N El log no registra uid, `native_id`, `original_name`, `sanitized_name`, rutas, cuentas ni términos.
- .03 P `event=start` conserva `command`, `backend` y `drivers`.
- .04 N Un `attachment` fallido registra `event=error` y **no** emite `event=end` (D7).

### UT-ATC-09 — Ayuda y exits (AC-21)

`UT-ATC-09` **renombra** los casos de ayuda de `UT-CLI-06` (5 comandos) y los extiende a 6; no se mantienen ambos grupos.

- .01 P La ayuda raíz lista `doctor`, `mailboxes`, `search`, `new`, `show`, `attachment` y la línea de exits de §11.1.
- .02 P `attachment --help` coincide con §11.4 (usage, positional, options, examples, notes), ≤ 100 columnas y sin ANSI.
- .03 P La ayuda raíz y las seis ayudas de subcomando (7 invocaciones) pasan `parse_args`.
- .04 N Ningún texto de ayuda dice “cinco comandos”/“five commands”, muestra un uid entero como formato de salida o promete escritura fuera de `~/.mailquery`.
- .05 P `attachment` sin `<uid>` ⇒ `E_USAGE`, exit 2.

### UT-ATC-10 — `attachment` con driver externo declarado (AC-07, AC-15)

- .01 P `attachment <plugin>:<native_id> --index 1` con un plugin declarado `attachments: "local"` devuelve el contrato JSON completo y escribe el archivo en la caché; el uid de salida va prefijado.
- .02 P `--all` con el plugin devuelve todos los adjuntos locales y `count` correcto.
- .03 N Un plugin `attachments: "remote"` no puede materializar adjuntos: `attachment --index` ⇒ `E_ATTACHMENT_UNAVAILABLE` (`unsupported`), sin red en el núcleo.
- .04 N Un plugin declara `attachments: "none"` ⇒ `E_ATTACHMENT_UNAVAILABLE` antes del store.

## 5. Documentación del milestone

- `docs/INTERFACES.md`: contrato del comando (`attachment`), campos JSON, precedencia de errores, timeout de extracción, `show.attachments` y log `end`.
- Ayudas en código actualizadas; la documentación de usuario completa se hace en M11.

## 6. Criterios de cierre

1. Suite verde sin fallos nuevos; UT-ATC verdes solos; goldens de `show` actualizados solo en forma/valor de `attachments` (incluidos los de Outlook).
2. Todo el orden de §11.3 se prueba en al menos un caso y en las fronteras de filas; los textos literales coinciden.
3. `show` no escribe (verificado); `attachment` no produce parciales; los positivos con plugin declarado pasan.
4. Sin cambios en `state.py`, `config.py` ni en los adaptadores de backend.

## 7. Handoff y HITL

- Reportar: firma del subcomando, payloads, textos de error, goldens actualizados.
- HITL: no hay preguntas abiertas de comportamiento; si un borde de §11.3 no puede resolverse sin cambiar el contrato JSON, se detiene y se pregunta.

## 8. Riesgos del milestone

| Riesgo | Mitigación |
|---|---|
| Duplicar validaciones entre `cli.py` y el motor | Una sola secuencia en `cli.py` hasta el store; el motor solo hace bloqueo/límites/extracción |
| Cambiar `show.attachments` rompe goldens y consumidores | Segunda actualización del golden en este milestone y contrato documentado; M11 actualiza README/recetas/skills |
| `--all` con muchos adjuntos agota el tiempo | Límites de M07 y timeout de 120 s por adjunto; `--index` como escape |

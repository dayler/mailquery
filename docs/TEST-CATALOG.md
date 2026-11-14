# Catálogo de pruebas

Qué verifica cada caso con ID de la suite de `tests/`, qué requisito de [`PRD.md`](PRD.md) cubre y dónde vive. Las referencias `§N` son secciones de `PRD.md`; los IDs `RF-`, `RNF-`, `AC-` y `ADR-` son los de `PRD.md`.

## 1. Convenciones

- **Grupo y caso.** Un grupo (`UT-SR-07`) cubre un requisito; cada caso (`UT-SR-07.03`) es un método de test. Los grupos de SMOKE no llevan número (`SMOKE-NEW.07`).
- **Tipo.** **P** positivo; **N** negativo (entrada inválida, error o algo que no debe ocurrir); **B** borde (un límite del requisito).
- **Nombre del método.** `test_<grupo>_<caso>_<descripción>` en minúsculas y con `_`: `test_ut_sr_07_03_excludes_message_before_window`. Un caso puede repartirse en varios métodos con el mismo prefijo.
- **Ejecución.** Toda la suite: `python -B -m unittest discover -s tests -t . -v`. Un caso o un grupo: `-k ut_sr_07_03` o `-k ut_sr_07`.
- **Esperado.** Lo que fija `PRD.md`; los textos que el PRD fija se comparan literalmente.
- **Tests sin ID.** Los tests sin ID también son cobertura; su nombre describe lo que verifican.
- **Un ID, un comportamiento.** Un comportamiento ya probado se extiende o se renombra en su test; no se crea un grupo paralelo ni se reutiliza un ID para otra cosa.
- **Aislamiento.** Ningún test usa el `HOME`, el `~/.mailquery` ni el `config.toml` del usuario. Todo subproceso fija `HOME` y, en Windows, `USERPROFILE` a un directorio temporal.
- **Independencia.** Cada caso crea sus datos temporales y no depende del orden. Un fixture compartido en `setUpClass` solo se permite si es de solo lectura.
- **Plataforma.** Una diferencia de plataforma va dentro del test como aserción condicional. Los únicos saltos permitidos son los de la sección 5.
- **Red y herramientas.** Sin red externa, salvo `pipx install` en las SMOKE; UT-CNT-03.05 y UT-CNT-03.11 usan un servidor HTTP en `127.0.0.1` dentro del propio test. Solo `unittest`, sin otros frameworks de test.

## 2. Prefijos y archivos

| Prefijo | Qué cubre | Archivo |
|---|---|---|
| UT-OUT | Salida JSON, fechas y limpieza de contenido | `tests/test_output.py` |
| UT-CNT | Primitivas de contenido no confiable: saneado, cuerpo visible, hojas `<style>`, modos de URL y señales de enlaces y del remitente | `tests/test_content.py` |
| UT-BOD | Origen del cuerpo (HTML) y cabeceras del remitente en los backends | `tests/test_body_sources.py` |
| UT-CW | Contenido no confiable en los comandos: campos saneados, filtros con A2, warnings y errores saneados, `content_notice`, modos de URL y `--strip-links`, señales de enlaces y del remitente, logs sin contenido, determinismo y reglas de seguridad documentadas | `tests/test_content_wiring.py` |
| UT-FLD | Fila por defecto de `search`/`new` y `--fields` en `search`, `new` y `show` | `tests/test_fields.py` |
| UT-GRP | `--group-by`, `--count` y `hint` de `search` sin resultados | `tests/test_group_count.py` |
| UT-MBX | Salida de `mailboxes` agrupada por cuenta, su `--fields` y el recuento diferido | `tests/test_mailboxes.py` |
| UT-CLI | Opciones, códigos de salida y `doctor` | `tests/test_cli.py` |
| UT-CFG | Configuración | `tests/test_config.py` |
| UT-LOG | Log | `tests/test_logging.py`, `tests/test_cli.py` |
| UT-INS | Instalador de Windows | `tests/test_install_scripts.py` |
| UT-ST | `state.json`, lock y migración | `tests/test_state.py`, `tests/test_cli.py` |
| UT-SR | `search`, `new`, `show` y `mailboxes` sobre Apple Mail | `tests/test_search.py` |
| UT-STO | Copias temporales del store | `tests/test_store.py` |
| UT-BE | Selección e interfaz de backend | `tests/test_backends.py` |
| UT-PL | Registro de drivers, capacidades y API de plugin | `tests/test_plugins.py` |
| UT-UID | uid prefijado | `tests/test_uid.py` |
| UT-DRV | `[scope]`, `[attachments]` y chequeo `driver` | `tests/test_config.py`, `tests/test_cli.py` |
| UT-MD | Ejecución multi-driver | `tests/test_multidriver.py` |
| UT-ERR | Errores y timeouts de plugin | `tests/test_plugins.py`, `tests/test_multidriver.py` |
| UT-ATT | Motor de adjuntos: bloqueo, sanitización, caché y límites | `tests/test_attachments.py` |
| UT-ACT | Contenido activo en adjuntos: PDF, OLE y ZIP | `tests/test_active_content.py` |
| UT-ATC | Comando `attachment` y `show.attachments` | `tests/test_cli.py` |
| UT-RMT | Adjuntos de drivers `"remote"`, fallos de origen y tope duro de extracción | `tests/test_remote_attachments.py` |
| UT-AM | Adjuntos de Apple Mail | `tests/test_backends.py`, `tests/test_integration.py` |
| UT-OL-ATT | Adjuntos de Outlook | `tests/test_outlook.py` |
| OL | Backend de Outlook sobre el doble | `tests/test_outlook.py` |
| TC | Punta a punta por `cli.main`: goldens, gates de solo lectura, recetas, empaquetado | `tests/test_integration.py`, `tests/test_readonly.py`, `tests/test_outlook.py`, `tests/test_packaging.py` |
| PKG | Metadatos del paquete y entry points | `tests/test_packaging.py`, `tests/test_install_scripts.py` |
| DOC | READMEs, skill, ayudas y `config.example.toml` | `tests/test_integration.py`, `tests/test_packaging.py`, `tests/test_content_wiring.py`, `tests/test_remote_attachments.py` |
| INS-SMOKE | Instaladores | `tests/test_install_scripts.py` |
| SMOKE | Cliente de correo real del equipo | `tests/test_smoke.py` |

## 3. Goldens

Viven en `tests/fixtures/expected/` (Apple Mail) y `tests/fixtures/expected/outlook/` (Outlook). Se comparan estructuralmente después de normalizar los valores que dependen del equipo: `<ISO>`, `<HOME>`, `<ROOT>` y `<PYTHON>`.

| Grupo | Goldens |
|---|---|
| TC-01 | `doctor`, `mailboxes`, `new_first_run`, `new_seeded`, `search_default`, `search_all_mail`, `show_2714`, `show_83170`, `show_83180`, `show_not_in_scope_error`, `show_smime_encrypted` |
| TC-02 | `outlook/doctor`, `outlook/mailboxes`, `outlook/new_first_run`, `outlook/search`, `outlook/show`, `outlook/show_header_only`, `outlook/show_smime` |
| TC-08 | `attachment_saved`, `attachment_cached`, `attachment_blocked_name`, `attachment_blocked_content`, `attachment_too_large`, `show_2714_with_cache` |
| TC-09 | `outlook/attachment_saved`, `outlook/attachment_cached`, `outlook/attachment_unavailable`, `outlook/attachment_blocked` |
| TC-10 | `search_multidriver`, `new_multidriver` |

`attachment_cached` se genera con una primera corrida que siembra la caché; el test documenta esa semilla.

Los goldens de éxito de `search`, `new`, `show` y `attachment` llevan
`content_notice` justo después de `generated_at`; los de error, `doctor` y
`mailboxes` no lo llevan. Los goldens de fila de `search`/`new` (`search_default`,
`search_all_mail`, `search_multidriver`, `new_first_run`, `new_seeded`,
`new_multidriver`, `outlook/search` y `outlook/new_first_run`) comparan la fila por
defecto de seis campos (`uid`, `subject`, `from`, `date_received`, `is_read` y
`has_attachments`); la fila completa se valida en una segunda corrida con
`--fields all` dentro de los casos TC-01.03–.06, TC-02.02 y TC-10.01–.02. En el
resto de goldens, una actualización conserva los valores ya fijados.
Los goldens `mailboxes` y `outlook/mailboxes` comparan la forma agrupada por
cuenta sin contadores; los contadores, `name` y `url` se validan en una segunda
corrida con `--fields name,url,total,unread` dentro de TC-01.02 y TC-02.01.

## 4. Dobles y fixtures

- `tests/fakes/outlook.py`: Outlook falso con solo los miembros del modelo de objetos que usa el backend. Registra cada llamada en un `CallLog` y lleva contadores de mutación que deben quedar en cero. Cada item admite `body_format` (`olFormatHTML` cuando tiene HTML, texto plano si no), cabeceras de transporte propias y fallos de COM inyectables; `BodyFormat` se registra en el `CallLog` como las demás propiedades y un item de reunión, informe o tarea no lo tiene. Incluye stores, items, carpetas, fallos de COM, zona horaria inyectable y adjuntos (locales, no descargados, S/MIME, corruptos y materialización).
- `tests/fakes/plugin.py`: plugin de prueba con API 1, capacidades configurables, `native_order_key`, cuerpo, adjuntos y fallos inyectables. Es la única vía para probar un driver externo sin publicar uno real.
- `tests/fakes/attachment_backend.py`: backend inyectable en la CLI con capacidades, adjuntos, motivos y timeouts controlables.
- `tests/fakes/attachment_driver.py`: driver de adjuntos para los tests del motor; entrega bytes y motivos y nunca escribe en caché.
- `tests/fixtures/make_fixtures.py`: construye el store de Apple Mail de prueba, con adjuntos (varios, mismo nombre, nombres hostiles, contenido ejecutable, vacío, S/MIME, externalizados de `.partial.emlx` y uno de más de 1 MiB) o sin ellos (`attachments=False`). Un mensaje admite cabeceras MIME extra (`extra_headers`, también repetidas) y `build_store(body_samples=True)` añade las muestras de origen del cuerpo y cabeceras del remitente (texto plano y HTML distintos, HTML con elementos ocultos, HTML sin texto, todo el HTML oculto y cabeceras de autenticación) sin cambiar el store por defecto.
- `tests/fixtures/attachment_samples.py`: contenidos de muestra para el bloqueo por *magic bytes*.
- `tests/fixtures/content_samples.py`: textos y HTML de muestra para el saneado (ANSI, C0/C1, `Cf`, selectores de variación, rellenos), la conversión HTML → texto, la omisión de ocultos en línea y por hoja `<style>`, un cuerpo típico de 6 KB para la medición informativa del paso a línea, las muestras de URL (inicios, terminación, dominios, tablas de modos, punycode y URL largas) y las de `Authentication-Results` y `Reply-To`.
- `tests/fixtures/active_content_samples.py`: PDF, OLE y ZIP de muestra para el detector de contenido activo (con y sin marcadores, con `vbaProject.bin`, con ejecutables, con entradas `.bin` propias de Office y con un ZIP cuyo directorio central no se puede leer). El ZIP cifrado se fabrica activando el bit 0 de *general purpose flag* en las cabeceras local y central.

## 5. CI y saltos

`.github/workflows/tests.yml` corre la suite completa en cada pull request a `develop` y en cada push a `develop`: `ubuntu-latest`, `macos-latest` y `windows-latest` × Python 3.11–3.14, sin `fail-fast`, más los jobs de `install-scripts`. La matriz instala `css-inline` en los tres sistemas, `coverage` y, en Windows, `pywin32`; no instala el paquete: los casos de entry points usan metadatos inyectados o se saltan con motivo. La suite corre bajo `coverage` y un paso `Check coverage` falla por debajo del 85 % de cobertura total combinada de líneas y ramas. Cada job `test-suite` incluye también un paso `integration-tests` que re-ejecuta los TCs (`-k test_tc_`) para que se vean como paso propio; no añade jobs. El job `install-scripts` de Ubuntu comprueba con `pip download --only-binary=:all:` que las etiquetas `macosx_11_0_arm64`, `macosx_10_12_x86_64`, `win_amd64`, `win32` y `manylinux_2_17_x86_64` tienen wheel de `css-inline` `0.23.x`, sin compilar y sin saltar a `0.24`. `tests/test_readonly.py` es bloqueante.

Saltos permitidos (los únicos):

- `InstallShTest` sin `sh` e `InstallPs1Test` sin PowerShell.
- UT-INS-01 fuera de `win32`.
- OL-05.02 fuera de Windows.
- Aserciones de permisos POSIX fuera de POSIX, y enlaces simbólicos donde el sistema no los permite.
- Casos de entry points cuando el paquete no está instalado.
- SMOKE donde no aplica (sección 6).

Fuera de esos saltos, el número de tests es el mismo en los tres sistemas operativos.

## 6. SMOKE y equipos reales

Son las únicas pruebas que leen el Apple Mail o el Outlook instalado; el resto usa dobles. Son de solo lectura, usan `HOME`/`USERPROFILE` temporales y no tocan el `~/.mailquery` real. Detectan el entorno y se saltan, sin fallar, donde no aplican: en Linux, en Windows sin Outlook clásico abierto, en macOS sin `~/Library/Mail` y en los runners de CI.

- SMOKE-INSTALL y SMOKE-NEW: instalación con `pipx` y comandos de lectura contra el cliente real.
- SMOKE-ATT-AM (macOS) y SMOKE-ATT-OL (Windows): recuperación real de un adjunto local. No imponen umbrales de tiempo.
- Los presupuestos de rendimiento de §19 se miden en los equipos del dueño (SMOKE-NEW.07); los resultados y la deuda abierta están en [`PERFORMANCE-BACKLOG.md`](PERFORMANCE-BACKLOG.md).
- La materialización COM de Outlook (`Attachment.SaveAsFile`) solo se verifica en un equipo Windows real; en CI se usa el doble.

## 7. Matriz de criterios de aceptación

Cada criterio de §20 con los grupos que lo verifican.

| Criterio | Qué exige | Casos | Goldens |
|---|---|---|---|
| §20 punto 1 | Solo lectura en macOS | TC-03 | — |
| §20 punto 2 | Solo lectura en Windows | OL-01, OL-30 | — |
| AC-01 | Registro de drivers, `plugin_api = 1`; duplicado, reservado o inválido ⇒ `E_PLUGIN_INCOMPATIBLE` | UT-PL-01, PKG-01 | — |
| AC-02 | Capacidades válidas y mostradas por `doctor` | UT-PL-02, UT-DRV-05 | `doctor` |
| AC-03 | `[scope."<driver>:<cuenta>"]`, driver nativo por defecto, driver no declarado o no instalado | UT-DRV-01, UT-DRV-02, UT-DRV-03 | — |
| AC-04 | Ejecución multi-driver, orden, sin dedupe entre drivers, fallo sin resultados parciales | UT-MD-01 a UT-MD-07 | `search_multidriver`, `new_multidriver` |
| AC-05 | `uid` string prefijado en JSON y estado, uid legado aceptado, validación temprana | UT-UID-01, UT-UID-02, UT-SR-11, UT-MD-07 | `search_*`, `new_*`, `show_*` |
| AC-06 | Migración determinista del estado de schema 1 a 2, persistencia atómica, poda de anillos | UT-ST-06, UT-ST-07 | — |
| AC-07 | `show.attachments` con `index`, `name` y `cached_path`; `show` no escribe | UT-ATC-01, UT-MD-07, UT-ATC-10 | `show_*` |
| AC-08 | `attachment` con `--index`/`--all`, validaciones y textos | UT-ATC-02, UT-ATC-03 | — |
| AC-09 | Bloqueo del mensaje completo con un adjunto hostil y otro seguro | UT-ATT-03, UT-AM-01 | `attachment_blocked_name`, `attachment_blocked_content` |
| AC-10 | Bloqueo por nombre, traversal, reservados y *magic bytes* | UT-ATT-01, UT-ATT-02, UT-AM-01, UT-OL-ATT-02 | — |
| AC-11 | Sanitización determinista y límites de nombre; ruta y fallback de 32 hex | UT-ATT-04, UT-AM-02 | `attachment_saved` |
| AC-12 | Caché `cached`/`--force`, staging atómico, `E_IO` sin parciales, validación por manifiesto | UT-ATT-07, UT-ATT-08, UT-ATT-12, UT-ATC-04, TC-08, TC-09 | `attachment_saved`, `attachment_cached` |
| AC-13 | Límites con `>` estricto y MiB, la caché cuenta, exceso conocido o en streaming | UT-ATT-06 | `attachment_too_large` |
| AC-14 | `enabled = false` y rangos de `[attachments]`, incluido `timeout_seconds` | UT-DRV-04, UT-ATC-05, UT-CFG-04 | — |
| AC-15 | Disponibilidad (`not_local`, `not_downloaded`, `unsupported`, `network`), S/MIME, `attachments: none` y fallos de origen de un driver `"remote"` | UT-ATT-05, UT-ATT-11, UT-ATC-06, UT-ATC-10, UT-RMT-02, UT-OL-ATT-03 | `outlook/attachment_unavailable` |
| AC-16 | Protocolo de errores de plugin: `reason`, `hint`, `detail`, `log_message` y `code` del núcleo | UT-ERR-01, UT-ERR-02, UT-ERR-03 | — |
| AC-17 | Timeout de 30 s en metadatos y `[attachments].timeout_seconds` (60 s por defecto) por adjunto extraído, con corte duro en un plugin externo; COM y metadatos sin cambios | UT-ERR-04, UT-ATC-07, UT-OL-ATT-03, UT-RMT-04 | — |
| AC-18 | `doctor` con `driver`; `--version` con drivers | UT-PL-03, UT-DRV-05, PKG-02 | `doctor` |
| AC-19 | Logs `backend=`/`drivers=`, conteos de `attachment`, sin datos personales | UT-MD-06, UT-ERR-02, UT-ATC-08, UT-OL-ATT-04 | — |
| AC-20 | Caché best-effort, borrado concurrente, sin barrido ni purga | UT-ATT-10, SMOKE-ATT-AM, SMOKE-ATT-OL | — |
| AC-21 | Ayuda raíz con seis comandos, ayuda de `attachment` y línea de exits | UT-ATC-09, DOC-01 a DOC-06, TC-07 | — |
| AC-H12 (delta `PRD-v2.2.md`) | Aviso de contenido activo en PDF, OLE y ZIP sin descomprimir ni bloquear, también en `attachment` y desde la caché | UT-ACT-01, UT-ACT-02, UT-ACT-03, UT-ACT-04, UT-ACT-05 | — |
| AC-H14 (delta `PRD-v2.2.md`) | Compatibilidad: solo `content_notice` nuevo; el resto de campos, `state.json`, el manifiesto y la caché sin cambios (con `--fields all` en `search`/`new` y sin `--fields` en `show`) | UT-CW-06, UT-FLD-07 | — |
| AC-H15 | La única dependencia nueva es `css-inline~=0.23.1`, instalable desde wheel en macOS (`arm64`, `x86_64`) y en Windows x64 de 64 y 32 bits, con un rango de parches que no pasa a `0.24` y sin cambiar los p95 (delta `PRD-v2.2.md`) | TC-06.03, PKG-03, SMOKE-INSTALL.05, SMOKE-NEW.07; paso "Check css-inline wheels" de la CI | — |
| AC-H17 | Los dos README tienen la subsección de actualización de seguridad de `css-inline` con sus pasos, comandos y el enlace a los avisos, y `search`, `new` y `show` funcionan sin `css-inline` (delta `PRD-v2.2.md`) | DOC-07, UT-CNT-03, UT-BOD-05 | — |
| AC-H01 (delta `PRD-v2.2.md`) | A2 en los campos de contenido; identificadores intactos | UT-CNT-01 (parcial; completa con UT-CW-01, UT-CW-02) | — |
| AC-H02 (delta `PRD-v2.2.md`) | `\n`/`\t`, CRLF, idempotencia y determinismo | UT-CNT-01, UT-CNT-06, UT-CW-13 | — |
| AC-H03 (delta `PRD-v2.2.md`) | Búsqueda con A2 a ambos lados; bloqueo, `sanitized_name` y caché sin cambios con nombres con `Cf` o controles | UT-CW-03, UT-CW-04 | — |
| AC-H04 (delta `PRD-v2.2.md`) | Cuerpo desde HTML; omisión de ocultos en línea y por hoja; `W_HIDDEN_CONTENT`; cuerpo todo oculto con `W_HTML_NO_TEXT` y `--text` sin el oculto | UT-CNT-02, UT-BOD-01, UT-BOD-02, UT-BOD-05, UT-CW-07, SMOKE-NEW.09 | — |
| AC-H05 (delta `PRD-v2.2.md`) | Hojas `<style>`, `@media`, `<link>` sin E/S, fallo de CSS; `W_HIDDEN_CONTENT` en los comandos | UT-CNT-03, UT-CW-07 | — |
| AC-H18 (delta `PRD-v2.2.md`) | Texto exacto de `content_notice`; reglas de seguridad en la skill y los README, incluida la regla de triaje sin contenido (punto 16) | UT-CNT-04, UT-CW-05, UT-ATC-04.01, DOC-08, DOC-09, DOC-10, UT-GRP-10, SMOKE-NEW.08 | — |
| AC-H06 (delta `PRD-v2.2.md`) | Detección y modos de URL en todos los campos; truncado sobre el texto transformado; filtros iguales en los tres modos | UT-CNT-05, UT-CNT-06, UT-CNT-07, UT-CW-08 | — |
| AC-H08 (delta `PRD-v2.2.md`) | `W_EXTERNAL_LINKS` | UT-CNT-08, UT-CW-10 | — |
| AC-H09 (delta `PRD-v2.2.md`) | `W_NON_ASCII_DOMAIN` y punycode | UT-CNT-07, UT-CNT-08, UT-CW-10 | — |
| AC-H10 (delta `PRD-v2.2.md`) | `W_LONG_URL` y `W_SCRIPT_LINK` | UT-CNT-08, UT-CW-10 | — |
| AC-H11 (delta `PRD-v2.2.md`) | Primera `Authentication-Results` (resultados de `spf`, `dkim` y `dmarc`; varias firmas DKIM con una en `pass` cuentan como `pass`) y `Reply-To` de otro dominio; sin cabecera, en correo interno de Outlook o en un mensaje de un plugin no se emiten; `headers` de `show` no cambia | UT-BOD-03, UT-BOD-04, UT-CNT-09, UT-CW-11 | — |
| AC-H07 (delta `PRD-v2.2.md`) | `--strip-links` en `search`, `new` y `show`; prevalece sobre `[content].url_display`; sin opción ni clave el modo es `neutralize`; en `doctor`, `mailboxes` y `attachment` ⇒ `E_USAGE` | UT-CW-09 | — |
| AC-H13 (delta `PRD-v2.2.md`) | `[content].url_display` inválido, clave desconocida o `content` que no es tabla ⇒ `E_CONFIG_INVALID` (exit 2) antes de abrir el store | UT-CFG-03, DOC-06.02, DOC-06.04 | — |
| AC-H16 (delta `PRD-v2.2.md`) | Los logs no registran URLs, dominios, direcciones ni contenido; solo códigos `W_*` | UT-CW-12 | — |
| AC-D01 (delta `PRD-v2.2.md`) | Extracción desde un plugin `attachments: "remote"` con el mismo JSON, bloqueo, límites, caché y manifiesto que un `"local"`; sin red en el núcleo | UT-RMT-01 | `attachment_saved`, `attachment_cached`, `attachment_too_large`, `attachment_blocked_name`, `attachment_blocked_content` |
| AC-D02 (delta `PRD-v2.2.md`) | `reason: network`/`not_local` de un plugin `"remote"` ⇒ `E_ATTACHMENT_UNAVAILABLE` con su plantilla, sin archivos nuevos | UT-RMT-02 | — |
| AC-D03 (delta `PRD-v2.2.md`) | `attachments: "none"` sigue rechazado con el hint nuevo | UT-RMT-03 | — |
| AC-D04 (delta `PRD-v2.2.md`) | `[attachments].timeout_seconds`: 60 por defecto, 10–600, inválido ⇒ `E_CONFIG_INVALID` antes del store; documentado | UT-CFG-04, UT-RMT-05, DOC-06.05 | — |
| AC-D05 (delta `PRD-v2.2.md`) | Corte duro de un plugin externo bloqueado antes del primer bloque o entre bloques, con `--all` informando el primero | UT-RMT-04 | — |
| AC-D06 (delta `PRD-v2.2.md`) | Topes de 30 s intactos; nativos entre bloques y al terminar la llamada; A7 y aciertos de caché fuera del tope | UT-RMT-05, UT-OL-ATT-03.04 | — |
| AC-O01 (delta `PRD-v2.2.md`) | En macOS y en Windows, sin `--fields`, cada fila de `search` y `new` tiene exactamente `uid`, `subject`, `from`, `date_received`, `is_read` y `has_attachments`, en ese orden y con los valores de `PRD.md` §12.5; los campos fuera de `messages[]` son los de hoy más `content_notice`, y el `hint` sigue RF-78; sin `--text` no se lee ningún cuerpo, solo las cabeceras de A6 de los mensajes devueltos; sin `--text` (ni `--to`/`--cc` en Windows, `PRD.md` RF-17), `--group-by` no lee cuerpos y `--count` no lee cuerpos ni cabeceras (`scan.messages_read: 0`) | UT-FLD-01, UT-FLD-02 (parcial; completa con UT-GRP-07 y SMOKE-NEW.08) | `search_default`, `search_all_mail`, `search_multidriver`, `new_first_run`, `new_seeded`, `new_multidriver`, `outlook/search`, `outlook/new_first_run` |
| AC-O02 (delta `PRD-v2.2.md`) | `--fields snippet` añade `snippet` a la fila por defecto; `--fields all` da la fila completa de `PRD.md` §12.5; `--fields to,uid` y `--fields uid --fields to` dan lo mismo, en el orden de `PRD.md` §12.5; un campo desconocido o vacío ⇒ `E_USAGE` (exit 2) antes de abrir el store, con el mensaje y el hint de RF-70 | UT-FLD-03 | — |
| AC-O03 (delta `PRD-v2.2.md`) | `show <uid> --fields attachments` devuelve solo `uid` y `attachments`, sin entregar el cuerpo ni emitir warnings del cuerpo; `show <uid> --fields body_text` no consulta los adjuntos; sin `--fields`, `show` devuelve los mismos campos que hoy más `content_notice`, con los valores y los warnings de F1 | UT-FLD-04 | — |
| AC-O04 (delta `PRD-v2.2.md`) | `search --group-by from` devuelve un grupo por remitente con su `count` y sus 5 mensajes más recientes, de más reciente a más antiguo y sin `from` en las filas; los grupos van ordenados por su mensaje más reciente; `--limit 0` da `messages: []`; `--fields snippet` añade `snippet` a las filas; la deduplicación se aplica antes de agrupar | UT-GRP-01 | — |
| AC-O05 (delta `PRD-v2.2.md`) | `--group-by domain,month` y `--group-by domain --group-by month` dan un grupo plano por cada combinación con mensajes, con las dos claves en ese orden; `day`, `week` y `month` usan la zona horaria local y la semana ISO 8601 también en el cambio de año, y los mensajes sin fecha forman el grupo `null`, al final; tres claves, una repetida, una desconocida o `--limit` fuera de 0–50 ⇒ `E_USAGE` (exit 2) antes de abrir el store, con los mensajes y hints de RF-72 | UT-GRP-02, UT-GRP-03 | — |
| AC-O06 (delta `PRD-v2.2.md`) | Con más de 50 grupos, la respuesta trae 50, `truncated: true`, el hint de RF-72 y `W_RESULTS_TRUNCATED`; `count` es el total de mensajes de todos los grupos | UT-GRP-04 | — |
| AC-O07 (delta `PRD-v2.2.md`) | `search --count` devuelve solo `ok`, `command`, `generated_at`, `content_notice`, `count`, `hint`, `warnings` y `scan`, con el total después de deduplicar y sin el límite de 200 y `hint: null`; cero resultados ⇒ `count: 0`, el hint de RF-78 y exit 0; con `--fields`, `--group-by` o `--limit` ⇒ `E_USAGE`; con `--text` aplica `PRD.md` RF-17 | UT-GRP-05 | — |
| AC-O08 (delta `PRD-v2.2.md`) | `new --fields snippet` añade `snippet` y el cursor avanza igual que sin `--fields`; `new --group-by from` y `new --count` ⇒ `E_USAGE` (exit 2) sin tocar el cursor | UT-FLD-06 (parcial; completa con UT-GRP-06) | — |
| AC-O09 (delta `PRD-v2.2.md`) | Un mensaje con texto oculto y URLs en el cuerpo da `W_HIDDEN_CONTENT` y cuenta esas URLs solo con `--fields snippet`, `body` o `all` en `search`/`new`, y con los campos de cuerpo de RF-74 (regla 2) en `show`; `W_SENDER_AUTH_FAILED` aparece con y sin `--fields`; con `--count` solo hay warnings de alcance. Los criterios de F1 sobre el cuerpo y los destinatarios (AC-H01–AC-H18) aplican en `search` y `new` cuando esos campos se entregan (RF-74) | UT-FLD-05 (parcial; completa con UT-GRP-09) | — |
| AC-O10 (delta `PRD-v2.2.md`) | La ayuda de `search`, `new` y `show`, la skill, `README.md`, `README.es.md` y las recetas cumplen RF-75, y `doctor --help` describe `--failures` (RF-76) | DOC-10 (parcial; completa con DOC-11 y DOC-12) | — |
| AC-O13 (delta `PRD-v2.2.md`) | En macOS, en Windows y con un plugin, un `search` sin resultados devuelve `count: 0`, exit 0 y el hint de RF-78 con el número correcto de carpetas y cuentas (INBOX, `mailbox_list` y `--include-mailbox`), también con `--group-by` y con `--count`; una cuenta excluida no cuenta en el número de cuentas; sin cuentas leídas (ninguna declarada o todas excluidas), `hint` es `null` y aparece `W_NO_ACCOUNTS`; con resultados, `hint` no cambia; `new` sin correo nuevo da `hint: null`; el hint no contiene nombres de carpetas ni de cuentas, y calcularlo no añade llamadas al driver | UT-GRP-08 | — |
| AC-O14 (delta `PRD-v2.2.md`) | En macOS, en Windows y con un plugin, `mailboxes` sin `--fields` devuelve solo `ok`, `command`, `generated_at`, `accounts`, `excluded_stores` y `warnings`; cada cuenta tiene `uuid`, `label`, `email`, `declared` y `mailboxes[]` con sus carpetas, cada una solo con `path` e `included`, y con los mismos valores e igual orden que la lista plana anterior; ninguna carpeta lleva `account`; una cuenta sin carpetas tiene `mailboxes: []`; con varios drivers se respeta el orden de `PRD.md` §11.3; un `path` copiado resuelve en `mailbox_list` y en `--include-mailbox`, y el nombre y la URL de `--fields name,url` siguen resolviendo. | UT-MBX-01, UT-MBX-02, DOC-13 | `mailboxes`, `outlook/mailboxes` |
| AC-O15 (delta `PRD-v2.2.md`) | `mailboxes --fields name,url,total,unread` y la opción repetida añaden esos campos a cada carpeta, en el orden `name`, `path`, `url`, `total`, `unread`, `included` y con los valores de hoy; `--fields path,included` da la salida por defecto; `--fields all`, un campo desconocido o vacío ⇒ `E_USAGE` (exit 2) antes de crear el home y de abrir el store, con el mensaje y el hint de RF-80; sin `total` ni `unread` no se cuenta ningún mensaje (Apple Mail no recontar, Outlook no lee tablas de carpeta, plugin sin contadores pedidos) y el recuento se reutiliza dentro del proceso; `mailboxes --help` y la ayuda general cumplen RF-80. | UT-MBX-03, UT-MBX-04, UT-MBX-05, DOC-13, SMOKE-NEW.07 | — |

## 8. Casos

### Salida, CLI y configuración

#### UT-CFG-01 — `max_size_mb`

Archivo: `tests/test_config.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | B | 1 y 1024 ⇒ válidos. |

#### UT-CFG-02 — `retention_days`

Archivo: `tests/test_config.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | `[logging].retention_days = 7` ⇒ `E_CONFIG_INVALID` con el hint `retention_days was replaced by max_size_mb`. |

#### UT-CFG-03 — `[content]`

Requisitos: RF-63 · Archivo: `tests/test_config.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Sin tabla ⇒ `neutralize`; `neutralize`, `keep` y `strip` son válidos. |
| .02 | N | `url_display = "raw"` y `url_display = 1` ⇒ `E_CONFIG_INVALID`, exit 2, `hint` con `neutralize`, `keep` y `strip`, antes de abrir el store. |
| .03 | N | Una clave desconocida en `[content]` ⇒ `E_CONFIG_INVALID`, exit 2. |
| .04 | N | `content = 1` (valor que no es una tabla) ⇒ `E_CONFIG_INVALID`, exit 2, antes de abrir el store. |

#### UT-CFG-04 — `[attachments].timeout_seconds`

Requisitos: AC-D04 (delta `PRD-v2.2.md`) · Archivo: `tests/test_config.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Sin clave ⇒ 60; 10 y 600 válidos. |
| .02 | N | 9, 601, `"60"`, `60.0` y `true` ⇒ `E_CONFIG_INVALID`, exit 2, también en `search` y `show`, antes del store. |
| .03 | B | Con un valor válido, `show` y `search` dan la misma salida que sin la clave. |

#### UT-CLI-04 — Opciones que no existen

Archivo: `tests/test_cli.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | `--format`, `--config`, `--home`, `--quiet`, `--verbose`, `--no-color`, `--timeout` y `--backend` ⇒ `E_USAGE`, exit 2, cada una. |

#### UT-CLI-05 — `--log-level`

Archivo: `tests/test_cli.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `--log-level debug` sobreescribe `[logging].level`. |
| .02 | N | Después del subcomando ⇒ `E_USAGE`. |

#### UT-CLI-08 — UTF-8 y LF

Requisitos: RF-32 · Archivo: `tests/test_cli.py`

Por pipe en subprocess, con cp1252 y `PYTHONUTF8=0`.

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | JSON con texto no ASCII ⇒ bytes UTF-8. |
| .02 | P | JSON de error y resumen en `stderr` ⇒ UTF-8. |
| .03 | N | Ningún `\r\n` en `stdout` ni `stderr`. |

#### UT-CLI-09 — Códigos de salida y JSON de error

Requisitos: RF-24 · Archivo: `tests/test_cli.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Cada uno de los 23 códigos `E_*` ⇒ su exit (6 para `E_OUTLOOK_NOT_RUNNING`); forma `{ok: false, command, error: {code, message, hint}}` formateada, un solo JSON y resumen en `stderr`. |

#### UT-CLI-10 — `doctor`: dependencias en Apple Mail

Archivo: `tests/test_cli.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | `store` falla ⇒ `envelope_index` `not evaluated: store failed`; `schema` y `readonly_strategy` `not evaluated: envelope_index failed`; `config` con bloques `not evaluated: schema failed`; `python`, `home`, `accounts_db`, `state` y `lock` evaluados. |
| .02 | P | `store` falla sin bloques ⇒ `config` `ok=true` con `0 account block(s) declared; available accounts: unknown (schema failed)`. |
| .03 | N | `envelope_index` falla con `store` bien ⇒ `schema` y `readonly_strategy` `not evaluated: envelope_index failed`. |
| .04 | N | `schema` falla ⇒ resolución de `config` `not evaluated: schema failed`; una config con sintaxis inválida se reporta igual. |
| .05 | P | Sin bloques, dependencia bien y `accounts_db` caído ⇒ `available accounts: unknown (Accounts4.sqlite unavailable)`. |

#### UT-CLI-11 — `doctor`: `state`

Archivo: `tests/test_cli.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `lookback = "15min"` y sin `state.json` ⇒ el detalle de `doctor` (§12.8) con `15min`. |
| .02 | P | Con cursor ⇒ `ok=true`, `cursor last_date_received=<n> last_uid=<n>`. |

#### UT-CLI-12 — `doctor`: `envelope_index`

Archivo: `tests/test_cli.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Con `-shm` ⇒ abre la base viva; `readonly_strategy` `live_ro`. |
| .02 | N | Base ilegible (permiso) ⇒ `ok=false`. |

#### UT-CLI-13 — Home

Requisitos: RNF-05 · Archivo: `tests/test_cli.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | POSIX: home 0755 ⇒ `home` `ok=false`. |
| .02 | N | `win32` parcheado: crear el archivo de prueba lanza `PermissionError` ⇒ `ok=false`. |

#### UT-INS-01 — Comprobación final de `install.ps1`

Requisitos: RNF-05 · Archivo: `tests/test_install_scripts.py`

Solo en `win32`, con `pipx` y `mailquery` falsos al inicio del `PATH`.

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | `import win32com` falla en el venv ⇒ muestra el problema con el hint `pipx reinstall mailquery`, exit ≠ 0. |
| .02 | N | `mailquery -v` falla o no muestra `backend outlook` ⇒ ídem. |
| .03 | P | Todo bien ⇒ exit 0 y `config.toml` sembrado con la ACL restringida. |

#### UT-LOG-01 — Rotación

Requisitos: RF-20 · Archivo: `tests/test_logging.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | B | Con `max_size_mb = 1`, al superar 1 MB ⇒ `mailquery.log.1`. |
| .02 | B | 7 rotaciones ⇒ solo `.1`–`.5`; el más antiguo se borra. |

#### UT-LOG-02 — Permisos del log

Requisitos: RNF-05 · Archivo: `tests/test_logging.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | POSIX: `mailquery.log` 0600. |
| .02 | P | POSIX: rotados 0600. |
| .03 | P | Una ejecución terminada no deja abierto el archivo de log (limpieza segura en Windows). |

#### UT-LOG-03 — Formato

Archivo: `tests/test_cli.py`, `tests/test_logging.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `YYYY-MM-DD HH:MM:SS,mmm LEVEL logger run=…`. |
| .02 | P | `event=start command=… backend=apple_mail`. |
| .03 | P | Línea del store con estrategia y versión. |
| .04 | P | `event=end` con `exit_code` y conteos. |

#### UT-LOG-04 — Contenido

Archivo: `tests/test_logging.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Error ⇒ `code` + mensaje. |
| .02 | N | Con `--log-level debug` y etiquetas no disponibles, un error cuyo mensaje contiene asunto, dirección, nombre de persona, carpeta, etiqueta de cuenta, ruta, término de búsqueda y uid, tras un `search --text` ⇒ ninguno de esos datos, ni uuids de cuenta, cuerpo ni `snippet`, aparece en el log. |
| .03 | P | Warnings ⇒ número y códigos `W_*`, sin el detalle. |
| .04 | N | Error que no es `E_INTERNAL` ⇒ sin traceback. |

#### UT-OUT-01 — JSON formateado

Requisitos: RF-18 · Archivo: `tests/test_output.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Texto no ASCII (`ñ`, `á`, emoji) ⇒ sin escapes `\u`. |

#### UT-OUT-02 — Fechas

Archivo: `tests/test_output.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | B | Epoch 1 ⇒ ISO 8601 con el offset local. |
| .02 | B | Epoch 0 ⇒ `null`. |
| .03 | N | `None` ⇒ `null`. |
| .04 | N | `1e20` ⇒ `null` (no representable). |

#### UT-OUT-03 — Limpieza de contenido

Archivo: `tests/test_output.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Caracteres de control en `snippet` ⇒ eliminados. |
| .02 | P | Secuencias ANSI en `body_text` de `show` ⇒ eliminadas. |

#### UT-CNT-01 — Saneado del texto

Requisitos: RF-52 · Archivo: `tests/test_content.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Quita secuencias ANSI CSI (`\x1b[31m…\x1b[0m`). |
| .02 | P | `\r\n` y `\r` → `\n`. |
| .03 | P | Elimina C0 salvo `\n` y `\t`, y DEL; conserva `\n` y `\t`. |
| .04 | P | Elimina C1 `U+0080..U+009F` (extremos y uno intermedio). |
| .05 | P | Elimina `Cf`: `U+200B`, `U+200D`, `U+202E`, `U+2066`, `U+FEFF`, `U+00AD` y un *tag character* `U+E0041`. |
| .06 | P | Elimina `U+FE00`, `U+FE0D`, `U+E0100`, `U+E01EF`; conserva `U+FE0E` y `U+FE0F` (`"❤️"` sale igual). |
| .07 | P | Elimina los rellenos Hangul `U+115F`, `U+1160`, `U+3164` y `U+FFA0`. |
| .08 | B | Idempotente: `sanitize_text(sanitize_text(x)) == sanitize_text(x)` para cada muestra. |
| .09 | B | Sin normalización: `"é"` (e + acento combinante) y `"ｆ"` (ancho completo) no cambian. |
| .10 | B | El resto del texto no cambia (acentos, CJK, emoji sin `Cf`); el ejemplo de saneado de la sección 8 del PRD da sus tres salidas. |
| .11 | B | `max_chars` recorta como hoy y no recorta más allá. |
| .12 | P | Quita secuencias OSC terminadas en `ST` y en `BEL`; el texto visible se conserva. |
| .13 | B | `sanitize_text("")` devuelve `""`. |

#### UT-CNT-02 — HTML → texto con omisión en línea

Requisitos: RF-53, RF-56 · Archivo: `tests/test_content.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `hidden`, `hidden=""` y `hidden="hidden"` omiten el elemento y sus descendientes. |
| .02 | P | `style` con `display:none`, `visibility:hidden`, `mso-hide:all`, `font-size:0` u `opacity:0` omite; también con mayúsculas, espacios, `!important`, `0.0`, `.0`, `0px`, `0%`, `0em` y tras otra declaración (`color:red; display:none`). |
| .03 | N | No omiten: `font-size:0.8em`, `font-size:inherit`, `opacity:0.5`, `xdisplay:none`, `min-font-size:0` ni `display:none` dentro de un valor de otra propiedad. |
| .04 | N | `aria-hidden="true"` conserva el texto. |
| .05 | B | `<br hidden>`, `<img hidden>` e `<input style="display:none">` no omiten el texto siguiente. |
| .06 | B | Elemento oculto sin cierre por la vía de fallo del paso a línea: se omite hasta el final. |
| .07 | B | Anidación de la misma etiqueta: `<div hidden><div>a</div>b</div>c` da `c`. |
| .08 | P | El texto visible alrededor no cambia (ejemplo A3 «HTML oculto» de la sección 8 del PRD → `Factura adjunta.`). |
| .09 | B | Todo oculto → `text == ""` y `hidden_chars > 0`. |
| .10 | P | Conteo: el ejemplo de la hoja `<style>` da 30; un texto oculto con un `U+200B` cuenta sin él (el saneado va antes de contar). |
| .11 | B | Conteo con entidades y comentarios dentro del oculto: `<div hidden>a&nbsp;&amp;<!-- c -->b</div>` cuenta los caracteres ya decodificados y no cuenta el comentario. |
| .12 | B | Ramas del analizador: `<div hidden><span>x</div>y` da `y`; `<div hidden/>z` no omite `z`; `<script>` dentro de un oculto no aporta texto a ningún flujo; `style` mal formado (`display`, `;;`, sin `:`) no omite; un `</script>` huérfano no rompe la conversión. |

#### UT-CNT-03 — Hojas `<style>` y `css-inline`

Requisitos: RF-53, RNF-18 · Archivo: `tests/test_content.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Una regla de clase con `display:none` en `<style>` oculta el elemento (ejemplo A3 de la sección 8 del PRD). |
| .02 | P | Reglas por id, por etiqueta y con selector compuesto también ocultan. |
| .03 | N | Una regla dentro de `@media` no oculta nada. |
| .04 | N | `<link rel="stylesheet" href="file:///<tmp>/hide.css">` a un archivo local con `.x{display:none}`: el texto sigue presente. |
| .05 | N | `<link rel="stylesheet" href="http://127.0.0.1:<puerto>/hide.css">` con un `http.server` en un hilo de este test: el servidor recibe 0 peticiones y el texto sigue presente. |
| .06 | P | `import css_inline` falla (simulado): se convierte el HTML original sin excepción y la omisión en línea sigue funcionando; una segunda llamada no reintenta la importación. |
| .07 | P | `inline()` lanza una excepción (simulada): se convierte el HTML original sin excepción. |
| .08 | B | El inliner se construye con `load_remote_stylesheets=False` y sin `base_url` (espía sobre el constructor). |
| .09 | B | Determinismo: la misma entrada dos veces da el mismo `HtmlText`. |
| .10 | B | Regla de `<style>` con `display:none !important` y estilo en línea que la contradice: se omite (riesgo aceptado del PRD) y se cuenta. |
| .11 | N | `<style>@import url("http://127.0.0.1:<puerto>/hide.css");</style>` y `@import` a un `file:///<tmp>/hide.css` local con `.x{display:none}`: el servidor de .05 recibe 0 peticiones y el texto sigue presente. El fallo real de CSS se cubre en .07 porque ningún CSS probado hace lanzar a `css-inline` 0.23.1. |

#### UT-CNT-04 — Texto de `content_notice`

Requisitos: RF-66 · Archivo: `tests/test_content.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `CONTENT_NOTICE` es literalmente el texto de RF-66. |

#### UT-CNT-05 — Detección de URLs

Requisitos: RF-54, RF-57 (delta `PRD-v2.2.md`) · Archivo: `tests/test_content.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Cada inicio de RF-54 se detecta, también en mayúsculas (`HTTPS://`, `WWW.`, `HXXPS://`, `JAVASCRIPT:`, `DATA:`): `http`, `https`, `ftp`, `smb`, `file`, `javascript:`, `vbscript:`, `data:text/html…`, `www.`, `hxxp://`, `hxxps://` y la ruta UNC; `kind`, `scheme`, `script` y los offsets son los esperados. |
| .02 | P | `ｈｔｔｐｓ：／／evil.example/pay` y `ｈｘｘｐ：／／evil.example/pay` se detectan (inicios con esquema en ancho completo). |
| .03 | P | `evil[.]example/pay` se detecta como una sola URL de tipo `bracket_domain`, sin esquema y sin marca de script. |
| .04 | N | No son URL: `JavaScript: un lenguaje`, `Data: 12/11`, `metadata:x`, `facturas.example/f/1`, `mailto:a@b.example`, `tel:123`, `ms-word:ofe`, `http://` sin nada detrás, `data:12`, `data:text/html`, `\\`, `\\evil.example` sin `\` final, `\\evil\` sin nada detrás, `www.-x`, `www. x`, los inicios en ancho completo de `data:` y `www.`, `＼＼evil.example\share`, `a[.]`, `[.]b`, `[.]`, `xhttp://a` y la cadena vacía. |
| .05 | B | Terminación: espacio, `"`, `'`, `<` y `>` cortan la URL; dos URLs seguidas no se solapan. |
| .06 | P | `url_domain`: con usuario y puerto (`https://u:p@host.example:8080/x` → `host.example`), `www.` con puerto, UNC y `[.]` (`evil[.]example/pay` → `evil.example`); `None` para `javascript:`, `vbscript:` y `data:`. |
| .07 | P | `url_domain` con inicio en ancho completo (`ｈｔｔｐｓ：／／evil.example/pay`) y ya neutralizado (`hxxps://evil.example/pay`) → `evil.example`; `address_domain` de una dirección (también con dos separadas por coma), de `None`, de `""` o sin `@` da el dominio o `None`. |
| .08 | N | No son URL `www.` sin letra ni dígito detrás (`www.-x`, `www. x`, `www.`) y `[.]` sin letra o dígito a los dos lados (`a[.]`, `[.]b`, `[.]`, `...[.]...`). |

#### UT-CNT-06 — Modos de URL

Requisitos: RF-54 (delta `PRD-v2.2.md`) · Archivo: `tests/test_content.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `keep` deja el texto igual. |
| .02 | P | `neutralize`: cada fila de las tablas A4 de la sección 8 de PRD-v2.2 da el resultado indicado, también con el esquema en mayúsculas (`HTTPS://`, `WWW.`). |
| .03 | P | `strip`: cada URL → `[link omitted]` (filas de la sección 8 de PRD-v2.2) y el resto del texto no cambia. |
| .04 | B | Una URL ya neutralizada, ASCII y de 2.048 caracteres o menos (`hxxps://…`, `evil[.]example/pay`) no cambia con `neutralize`. |
| .05 | B | Idempotencia: `render_urls(render_urls(x, "neutralize"), "neutralize") == render_urls(x, "neutralize")` para todas las muestras. |
| .06 | B | El texto fuera de las URLs no cambia en ningún modo; dos llamadas dan el mismo resultado; un texto sin URLs (incluidos caracteres con NFKC de varios caracteres) no cambia; `render_urls(x, "otro")` lanza `ValueError`. |
| .07 | P | Esquemas de script en mayúsculas y en ancho completo: `JAVASCRIPT:x` → `JAVASCRIPT[:]x`, `VbScript:x` → `VbScript[:]x`, `DATA:text/html,x` → `DATA[:]text/html,x`, `ｊａｖａｓｃｒｉｐｔ：x` → `ｊａｖａｓｃｒｉｐｔ[:]x`. |

#### UT-CNT-07 — Punycode y acortado

Requisitos: RF-54, RF-57 (delta `PRD-v2.2.md`) · Archivo: `tests/test_content.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `https://pаypal.com/login` (а cirílica) → `hxxps://xn--pypal-4ve.com/login`; solo cambian la etiqueta no ASCII y el esquema. |
| .02 | P | Dominio entero en otro alfabeto, dominio `www.` no ASCII y dominio con dos etiquetas no ASCII: cada etiqueta no ASCII en ACE y las etiquetas ASCII intactas. |
| .03 | B | URL de 2.048 caracteres sale entera; de 2.049 sale con 256 + `…[+1793 characters]`; el ejemplo de 5.000 da `…[+4744 characters]`. |
| .04 | B | `keep` nunca acorta ni cambia el dominio; `strip` da `[link omitted]` también para la URL larga. |
| .05 | B | El acortado se calcula sobre la URL ya neutralizada (con punycode): el `<n>` correcto cuando el ACE cambia la longitud (`…[+1800 characters]`). |
| .06 | P | URL ya neutralizada por el remitente (D-20): `hxxps://pаypal.com/x` → `hxxps://xn--pypal-4ve.com/x` (el esquema no cambia, el dominio sí); una `hxxps://` de 5.000 caracteres sale con sus primeros 256 + `…[+4744 characters]`. |
| .07 | P | ACE en el host de una ruta UNC no ASCII (`\\pаypal\share` → `[\\]xn--pypal-4ve\share`) y en un dominio `[.]` no ASCII (`pаypal[.]com/x` → `xn--pypal-4ve[.]com/x`). |

#### UT-CNT-08 — Conteos y textos de las señales

Requisitos: RF-55, RF-57–RF-59 (delta `PRD-v2.2.md`) · Archivo: `tests/test_content.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `count_url_signals` suma URLs de varios textos; una URL de script cuenta en `external` y en `script`; una de 2.049 cuenta en `long` y una de exactamente 2.048 no; sin entradas da ceros y dos llamadas coinciden. |
| .02 | P | `non_ascii_domains` cuenta una URL con alfabetos mezclados, una con dominio entero en otro alfabeto y una dirección `soporte@pаypal.com`; no cuenta usuario ni ruta no ASCII de la URL ni dominios ASCII parecidos (`paypa1.com`). |
| .03 | P | Los textos de los siete warnings son literalmente los de RF-55–RF-61 (con `<n>`, `<uid>` y `<resultados>`). |
| .04 | P | `content_warnings` devuelve solo los que aplican, en el orden `W_HIDDEN_CONTENT`, `W_EXTERNAL_LINKS`, `W_SCRIPT_LINK`, `W_LONG_URL`, `W_NON_ASCII_DOMAIN`, `W_SENDER_AUTH_FAILED`, `W_REPLY_TO_MISMATCH`; ninguno contiene URL, dominio ni dirección. |
| .05 | B | Sin URLs, sin oculto y sin señales del remitente → lista vacía. |
| .06 | P | `JAVASCRIPT:x`, `VbScript:x`, `DATA:text/html,x` y `ｊａｖａｓｃｒｉｐｔ：x` cuentan en `script` y en `external`. |

#### UT-CNT-09 — Señales del remitente

Requisitos: RF-60, RF-61 (delta `PRD-v2.2.md`) · Archivo: `tests/test_content.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | El ejemplo A6 de la sección 8 de PRD-v2.2 → `"spf=softfail dkim=none dmarc=fail"`. |
| .02 | N | Todo `pass`; `none`/`neutral` sin fallos; cabecera ausente (`None`) → `None`. |
| .03 | P | `permerror` y `fail` cuentan; mayúsculas (`SPF=FAIL`) → `spf=fail`; un mecanismo ausente no aparece en el resultado. |
| .04 | B | Varias firmas DKIM: una `pass` → `pass`; ninguna `pass` → la primera. |
| .05 | B | Resultado desconocido (`dkim=weird`) → `unknown`, y el resultado no contiene otro texto de la cabecera (comentarios, `header.from=…`, `header.d=…`, el servidor). |
| .06 | P | `reply_to_mismatch`: dominio distinto → `True` (también con varias direcciones y una distinta); el mismo dominio con otras mayúsculas → `False`. |
| .07 | N | Sin `Reply-To`, `from_address` sin `@`, `Reply-To` sin direcciones con dominio o mal formado (`"<<<"`, `""`) → `False`. |
| .08 | P | Valor plegado: `"mx.example;\r\n\tspf=pass smtp.mailfrom=a.example;\r\n\tdmarc=fail header.from=a.example"` → `"spf=pass dmarc=fail"`. |
| .09 | B | `sender_auth_failure("")`, una cabecera sin mecanismos reconocidos y `spf=temperror dkim=policy dmarc=pass` (sin fallo) → `None`. |

#### UT-CW-01 — A2 en los campos de contenido

Requisitos: RF-52, RF-66 · Archivo: `tests/test_content_wiring.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Un mensaje con ANSI, C1, `U+200B`, `U+202E`, selectores y rellenos en `subject`, `from.name`, nombres de `to`/`cc` y cuerpo: `search` y `new` los devuelven saneados, incluido `snippet`. |
| .02 | P | `show` del mismo mensaje: `subject`, nombres, cada valor de `headers`, `body_text` y `attachments[].name` saneados. |
| .03 | P | `attachment`: `original_name` saneado; `sanitized_name` y `path` iguales a los del mismo nombre original (calculados con `sanitize_name` y la ruta de caché). |
| .04 | N | `uid`, `message_id`, `from.address`, `to[].address`, `mailbox.*`, `account.*`, `source.emlx_path` y `cached_path` salen sin cambios aunque contengan caracteres invisibles. |
| .05 | P | Una etiqueta de cuenta y un nombre de carpeta con `U+200B` copiados de `accounts[]` y de `accounts[].mailboxes[]` de `mailboxes` (con `--fields name,url`) resuelven en `config.toml` y en `--include-mailbox`. |

#### UT-CW-02 — A2 en warnings y errores

Requisitos: RF-52 · Archivo: `tests/test_content_wiring.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Un warning con un identificador con `U+202E` (`W_STORE_EXCLUDED` de un store excluido del plugin falso) sale saneado en `warnings[]`, mientras `excluded_stores[].label` sigue igual. |
| .02 | P | Un error cuyo `message` cita un valor del usuario con `U+202E` sale saneado en el JSON y en `stderr`; `code` y exit sin cambios. |
| .03 | B | `warnings[]` de `mailboxes`, `new` y `doctor --json` también pasan por A2 (todos los comandos). |
| .04 | N | Un error con `hint` nulo conserva `"hint": null` en el JSON tras A2. |

#### UT-CW-03 — Búsqueda con A2 a ambos lados

Requisitos: RF-52 · Archivo: `tests/test_content_wiring.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Asunto original `Factura​ de octubre`: `--subject "Factura de"` lo encuentra. |
| .02 | P | Patrón con `U+200B` (`--subject "Fac​tura"`) encuentra un asunto sin él. |
| .03 | P | `--text` con un cuerpo con `U+202E` en medio de la palabra; `--from`, `--to` y `--cc` con nombres con `U+202E`/`U+200B`. |
| .04 | N | Sin caracteres de A2, los resultados de `--subject` son los mismos que filtrar el resultado completo por subcadena. |

#### UT-CW-04 — Adjuntos con nombres con `Cf` o controles

Requisitos: RF-52 · Archivo: `tests/test_content_wiring.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Un adjunto con un selector de variación (`U+FE00`): el bloqueo, el `sanitized_name` y la ruta de caché son los mismos que `classify_name` y `sanitize_name` dan para el nombre original. |
| .02 | N | Un nombre con `U+200B` o un control C0 que hoy se bloquea sigue dando `E_ATTACHMENT_BLOCKED`, sin archivos. |

#### UT-CW-05 — `content_notice`

Requisitos: RF-66 · Archivo: `tests/test_content_wiring.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `search`, `new` y `show` de éxito (store sintético y doble de Outlook) tienen `content_notice` con el texto exacto, justo después de `generated_at`. |
| .02 | N | Las respuestas de error de esos comandos, `doctor --json` y `mailboxes` no lo tienen. |

#### UT-CW-06 — Compatibilidad

Requisitos: RF-52, RF-66 · Archivo: `tests/test_content_wiring.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Con la fila completa actual de `search`/`new` y `show` sin opciones, las claves son las de antes más `content_notice`, y es la única clave nueva. |
| .02 | B | `state.json` y el manifiesto de una corrida de `new` y de `attachment` conservan su forma y contenido (sin `content_notice`). |

#### UT-CW-07 — Cuerpo visible en los comandos

Requisitos: RF-53, RF-56 · Archivo: `tests/test_content_wiring.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Un mensaje con texto oculto en línea y por una hoja `<style>`: `search`, `new` y `show` dan una vez `W_HIDDEN_CONTENT: <n> hidden character(s) omitted from the body of <uid>` con el `<n>` de `html_body_to_text`; el mensaje se devuelve y el exit es 0. |
| .02 | P | `W_HIDDEN_CONTENT` va antes de `W_EXTERNAL_LINKS`; el detalle no contiene texto del mensaje. |
| .03 | N | Un mensaje sin texto omitido, de texto plano o de un plugin no da `W_HIDDEN_CONTENT`. |
| .04 | P | Un HTML todo oculto da `W_HTML_NO_TEXT` además de `W_HIDDEN_CONTENT`; `--text` con una palabra del texto oculto no encuentra el mensaje (Apple Mail y Outlook). |

#### UT-CW-08 — Modos de URL en los campos

Requisitos: RF-54 · Archivo: `tests/test_content_wiring.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Con `keep`, `neutralize` y `strip`: `subject`, `from.name`, `to[].name`, `cc[].name`, cada valor de `headers` (`show`), `body_text` y `snippet` se transforman igual que `render_urls` (incluido `Subject` en `headers` con `--strip-links`). |
| .02 | N | Nombres de adjuntos, `warnings[]`, textos de error, direcciones y `uid` no cambian en ningún modo. |
| .03 | P | Los filtros devuelven los mismos mensajes en los tres modos; `--subject evil.example` encuentra el asunto con la URL neutralizada o quitada. |
| .04 | B | `show` con una URL que hace superar 20.000 caracteres solo antes de acortarla: el truncado y `W_BODY_TRUNCATED` se calculan sobre el texto transformado. |

#### UT-CW-09 — `--strip-links` y precedencia

Requisitos: RF-54, RF-63 · Archivo: `tests/test_content_wiring.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Sin opción ni clave ⇒ `neutralize`. |
| .02 | P | `[content].url_display = "keep"` ⇒ `keep`; `"strip"` ⇒ `strip`. |
| .03 | P | `--strip-links` con `url_display = "keep"` ⇒ `strip` en `search`, `new` y `show`. |
| .04 | N | `doctor --strip-links`, `mailboxes --strip-links` y `attachment <uid> --all --strip-links` ⇒ `E_USAGE`, exit 2. |

#### UT-CW-10 — Señales de enlaces en los comandos

Requisitos: RF-55, RF-57, RF-58, RF-59 · Archivo: `tests/test_content_wiring.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Una URL en el asunto y otra en el cuerpo ⇒ `W_EXTERNAL_LINKS: 2 …`; la del asunto cuenta una vez aunque `headers` la repita (`show`). |
| .02 | P | La URL larga y el enlace de script: `W_EXTERNAL_LINKS: 2`, `W_SCRIPT_LINK: 1`, `W_LONG_URL: 1`, en ese orden, en los tres modos y en los tres comandos. |
| .03 | P | Homoglifos: `W_EXTERNAL_LINKS: 1` y `W_NON_ASCII_DOMAIN: 2` (URL + dirección); con `neutralize`, `xn--pypal-4ve.com` en el cuerpo y la dirección igual. |
| .04 | P | `search`, `new` y `show` dan los mismos conteos; en `new`, todos antes de `W_FIRST_RUN`. |
| .05 | N | Sin URLs en esos campos no aparece ninguno de los cuatro; un texto que empieza como un esquema sin cumplir la definición (`JavaScript: …`) no cuenta. |
| .06 | P | Cuerpo con `JAVASCRIPT:x`, `VbScript:x`, `DATA:text/html,x` y `ｊａｖａｓｃｒｉｐｔ：x` ⇒ `W_EXTERNAL_LINKS: 4` y `W_SCRIPT_LINK: 4` en los tres comandos; con `neutralize`, `JAVASCRIPT[:]x`, `VbScript[:]x`, `DATA[:]text/html,x` y `ｊａｖａｓｃｒｉｐｔ[:]x`. |
| .07 | P | Un mensaje con `W_BODY_UNREADABLE` y una URL en el asunto ⇒ `W_EXTERNAL_LINKS: 1` en `show`. |
| .08 | N | `attachment`, `mailboxes` y `doctor --json` no contienen `W_EXTERNAL_LINKS`, `W_SCRIPT_LINK`, `W_LONG_URL`, `W_NON_ASCII_DOMAIN`, `W_SENDER_AUTH_FAILED` ni `W_REPLY_TO_MISMATCH`. |
| .09 | P | Un mensaje de un plugin sin cuerpo legible con una URL en el asunto y otra en el nombre del remitente ⇒ `W_EXTERNAL_LINKS: 2`; no se emite `W_HIDDEN_CONTENT`. |

#### UT-CW-11 — Señales del remitente en los comandos

Requisitos: RF-60, RF-61 · Archivo: `tests/test_content_wiring.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | El ejemplo A6 en Apple Mail y en Outlook: `W_SENDER_AUTH_FAILED: spf=softfail dkim=none dmarc=fail in <uid>` y `W_REPLY_TO_MISMATCH: … in <uid>` en `search`, `new` y `show`, en ese orden y después de las señales de enlaces. |
| .02 | N | Todo `pass`, sin cabecera, con `Reply-To` del mismo dominio o con el fallo solo en la segunda `Authentication-Results`: sin warnings. |
| .03 | N | Un mensaje de un plugin y correo interno de Outlook sin cabeceras de transporte: sin warnings. |
| .04 | N | `headers` de `show` sigue con sus seis cabeceras (sin `Reply-To` ni `Authentication-Results`); el exit no cambia. |
| .05 | P | Un mensaje S/MIME de Apple Mail con `dmarc=fail` en la primera `Authentication-Results` ⇒ `W_SENDER_AUTH_FAILED` (la exclusión de S/MIME solo aplica al item de Outlook). |

#### UT-CW-12 — Logs sin contenido

Requisitos: RF-64 · Archivo: `tests/test_content_wiring.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Tras `search`, `new` y `show` de mensajes con URLs, dominio no ASCII, direcciones y A6, `~/.mailquery/logs/mailquery.log` (del `HOME` temporal) contiene los códigos `W_*` y no contiene ninguna URL, dominio, dirección ni texto del mensaje. |
| .02 | P | `W_SENDER_AUTH_FAILED` y `W_REPLY_TO_MISMATCH` se registran solo por código, sin sus detalles ni las direcciones. |

#### UT-CW-13 — Determinismo de punta a punta

Requisitos: RNF-19 · Archivo: `tests/test_content_wiring.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | B | La misma consulta dos veces, con cada modo, da el mismo JSON salvo `generated_at` y `scan.duration_ms`. |

#### UT-FLD-01 — Fila por defecto

Requisitos: AC-O01 (delta `PRD-v2.2.md`) · Archivo: `tests/test_fields.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Sin `--fields`, cada fila de `search` y `new` tiene exactamente `uid`, `subject`, `from`, `date_received`, `is_read` y `has_attachments`, en ese orden, con los mismos valores que la fila completa; se comprueba sobre el store sintético y sobre el doble de Outlook. |
| .02 | P | Los campos fuera de `messages[]` son los de antes más `content_notice`; `hint`, `scan` y, en `new`, `cursor` no cambian. |

#### UT-FLD-02 — Sin lectura de cuerpos

Requisitos: AC-O01 (delta `PRD-v2.2.md`) · Archivo: `tests/test_fields.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Apple Mail: sin `--text`, `search` y `new` no llaman a la extracción del cuerpo (espía sobre `emlx._extract_body_text`) y leen las cabeceras de cada mensaje devuelto; `scan.messages_read` = número de mensajes devueltos. |
| .02 | P | Outlook (doble): sin `--text`, el `CallLog` no tiene accesos a `Body`, `HTMLBody` ni `BodyFormat`; `items_opened` cuenta los items abiertos para las cabeceras de A6; un item S/MIME no se abre. |
| .03 | P | Con `--text`, el cuerpo se lee para filtrar como hoy, pero sin `--fields snippet` la fila no lleva `snippet` ni `body`. |
| .04 | P | Plugin falso con espías: con la fila por defecto, `search` y `new` no llaman a `load_snippet` ni a `load_body`; el plugin no tiene `load_headers` y no se calculan las señales del remitente. |
| .05 | B | Apple Mail, mensaje cuyo `.emlx` no existe: `load_headers` no lee (`read=False`), el mensaje no cuenta en `scan.messages_read` y su fila sale sin warnings del remitente ni del cuerpo. |
| .06 | P | `--to` como filtro sin `--fields to`: filtra por destinatarios (los lee) y la fila no lleva `to` ni `cc`; las URLs de los nombres de destinatarios no se cuentan. |

#### UT-FLD-03 — `--fields` en `search` y `new`

Requisitos: AC-O02 (delta `PRD-v2.2.md`) · Archivo: `tests/test_fields.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `--fields snippet` añade `snippet` al final de la fila por defecto. |
| .02 | P | `--fields all` da la fila completa de `PRD.md` sección 12.5 (`SEARCH_ROW_FIELDS`). |
| .03 | P | `--fields to,uid` y `--fields uid --fields to` dan la fila por defecto más `to`, en el orden canónico. |
| .04 | N | `--fields remitente` ⇒ `E_USAGE`, exit 2, mensaje y hint literales de PRD-v2.2 sección 8; `--fields ""` y `--fields uid,,to` ⇒ ídem con `''`. |
| .05 | B | El error ocurre antes de crear el home (el `HOME` temporal no tiene `.mailquery`) y sin abrir el store. |
| .06 | B | D-24: `--fields "to, uid"` equivale a `--fields to,uid`; `--fields ALL` y `--fields Snippet` ⇒ `E_USAGE` con `unknown field 'ALL'` / `unknown field 'Snippet'`; `--fields " "` ⇒ ídem con `''`. |

#### UT-FLD-04 — `show --fields`

Requisitos: AC-O03 (delta `PRD-v2.2.md`) · Archivo: `tests/test_fields.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `--fields attachments` → `message` con solo `uid` y `attachments`; ningún warning de cuerpo; en un mensaje S/MIME, `attachments: []` (se lee el cuerpo para aplicar la regla, sin entregarlo). |
| .02 | P | `--fields body_text` → no consulta los adjuntos (`attachments()` y `attachment_names()` del backend no se llaman). |
| .03 | P | `--fields headers` → `uid` y `headers` sin leer el cuerpo (Apple Mail con `load_headers`; Outlook sin `Body`/`HTMLBody`). |
| .04 | P | Sin `--fields` → los mismos campos y valores que antes más `content_notice`. |
| .05 | N | Campo desconocido ⇒ `E_USAGE` con la lista de `show`. |
| .06 | P | `--fields source` y `--fields partial`, cada uno solo: leen el cuerpo, entregan `uid` y ese campo, y emiten los warnings del cuerpo (cuerpo entregado según RF-74). |

#### UT-FLD-05 — Warnings según lo entregado

Requisitos: AC-O09 (delta `PRD-v2.2.md`) · Archivo: `tests/test_fields.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Mensaje con texto oculto y URLs en el cuerpo: `W_HIDDEN_CONTENT` y el conteo de las URLs del cuerpo solo con `--fields snippet`, `body` o `all` en `search`/`new`, y con `body_text` (o `body_truncated`, `partial`, `readable`, `source`) en `show`. |
| .02 | P | URL en el asunto: contada con la fila por defecto; URL en el nombre de un destinatario: contada solo con `--fields to`. |
| .03 | P | `W_SENDER_AUTH_FAILED` y `W_REPLY_TO_MISMATCH` aparecen con y sin `--fields`, también con `show --fields attachments`. |
| .04 | N | `W_BODY_UNREADABLE`, `W_EMLX_MISSING` (Apple Mail) y `W_BODY_NOT_LOCAL` (Outlook) solo con cuerpo entregado; con `--text` sin `snippet` no aparecen. |
| .05 | N | `W_ATTACHMENTS_UNAVAILABLE` solo si `show` entrega `attachments`. |

#### UT-FLD-06 — `new --fields`

Requisitos: AC-O08 (delta `PRD-v2.2.md`) · Archivo: `tests/test_fields.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `new --fields snippet` añade `snippet`. |
| .02 | B | El `state.json` tras `new --fields snippet` es igual al de `new` sin `--fields` sobre el mismo store (cursor y anillo). |

#### UT-FLD-07 — Compatibilidad final de F1

Requisitos: AC-H14 (delta `PRD-v2.2.md`) · Archivo: `tests/test_fields.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Con `--fields all` en `search`/`new` y sin `--fields` en `show`, están todos los campos existentes y la única clave nueva respecto de 2.0.x es `content_notice`. |

#### DOC-10 — Documentación de la fila y de `--fields`

Requisitos: AC-O10, AC-H18 (delta `PRD-v2.2.md`) · Archivo: `tests/test_fields.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `search --help`, `new --help` y `show --help` describen `--fields` con la lista de su comando. |
| .02 | P | Los dos README documentan la fila por defecto y `--fields` con ejemplos (`--fields snippet`, `--fields all`, `show apple_mail:2714 --fields attachments`). |
| .03 | P | La skill explica la fila por defecto, `new --fields snippet` para resumir el correo nuevo, cuándo usar `new` y cuándo `search --unread`, y la regla de triaje sin contenido (punto 16). |
| .04 | P | `docs/recipes/01-new-mail-digest.md` usa `mailquery new --fields snippet`; todas las líneas `mailquery search` de `02-search-invoices.md` piden con `--fields` los campos que consumen. |

#### UT-GRP-01 — `--group-by from`

Requisitos: AC-O01, AC-O04 (delta `PRD-v2.2.md`) · Archivo: `tests/test_group_count.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Un grupo por remitente (dirección en minúsculas) con su `count` y sus 5 mensajes más recientes, de más reciente a más antiguo, sin `from` en las filas. |
| .02 | P | Los grupos van ordenados por su mensaje más reciente. |
| .03 | B | `--limit 0` → `messages: []` en cada grupo y `count` correcto. |
| .04 | P | `--fields snippet` añade `snippet` a las filas de los grupos. |
| .05 | P | La deduplicación se aplica antes de agrupar (el duplicado Gmail/INBOX del store sintético cuenta una vez). |
| .06 | P | Con `[search].default_limit = 20` en la configuración, `--group-by from` sin `--limit` da 5 mensajes por grupo (RF-72: `default_limit` no aplica). |

#### UT-GRP-02 — Dos claves y fechas

Requisitos: AC-O01, AC-O05 (delta `PRD-v2.2.md`) · Archivo: `tests/test_group_count.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `--group-by domain,month` y `--group-by domain --group-by month` dan el mismo resultado: un grupo plano por combinación con mensajes, con `domain` y `month` en ese orden (ejemplo de PRD-v2.2 sección 8). |
| .02 | P | `day`, `week`, `month` usan la zona local (`output.LOCAL_ZONE` inyectada): un mensaje a las 02:00 UTC cae en el día anterior con UTC−4. |
| .03 | B | Semana ISO en el cambio de año: 2026-12-31 y 2027-01-01 → `2026-W53`; 2027-01-04 → `2027-W01`. |
| .04 | B | Mensajes sin fecha (nula, 0 o no representable) forman el grupo `null` de `day`/`week`/`month` y van al final; mensajes sin dirección del remitente, el grupo `null` de `from`/`domain`. |
| .05 | P | `mailbox` da `{"account": <etiqueta>, "path": <ruta>}` sin `mailbox` en las filas; `account` da la etiqueta (o el `uuid` sin etiqueta). |
| .06 | B | A igualdad de mensaje más reciente, los grupos se ordenan por sus claves ascendentes; un grupo sin fechas va después de los que tienen. |
| .07 | B | Remitente con una dirección sin `@`: `from` = la dirección en minúsculas y `domain` = `null`. |
| .08 | B | `--group-by domain,month` con dos grupos del mismo dominio, uno con `month: null`: el grupo con `null` va después de los grupos sin claves `null`, ordenado por claves ascendentes con `null` al final. |

#### UT-GRP-03 — Errores de `--group-by` y `--limit`

Requisitos: AC-O05 (delta `PRD-v2.2.md`) · Archivo: `tests/test_group_count.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Tres claves, una repetida, una desconocida: `E_USAGE`, exit 2, con los mensajes y el hint literales. |
| .02 | N | `--limit 51` y `--limit -1` con `--group-by`: `E_USAGE` con el mensaje y el hint literales. |
| .03 | B | Los errores ocurren antes de crear el home y sin abrir el store. |
| .04 | B | `--limit 50` con `--group-by` es válido (hasta 50 mensajes por grupo). |
| .05 | N | D-24: `--group-by ""` y `--group-by from,` ⇒ `unknown key '' in --group-by`; `--group-by FROM` ⇒ `unknown key 'FROM' in --group-by`; `--group-by "from, month"` equivale a `--group-by from,month`. |

#### UT-GRP-04 — Más de 50 grupos

Requisitos: AC-O06 (delta `PRD-v2.2.md`) · Archivo: `tests/test_group_count.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Con 53 remitentes: 50 grupos, `truncated: true`, hint `3 more group(s); refine the filters`, warning `W_RESULTS_TRUNCATED: 3 more group(s); refine the filters`; `count` es el total de mensajes de los 53 grupos. |
| .02 | B | Exactamente 50 remitentes: 50 grupos, `truncated: false`, sin `W_RESULTS_TRUNCATED`. |
| .03 | B | 51 remitentes: 50 grupos, `truncated: true`, `1 more group(s); refine the filters`. |

#### UT-GRP-05 — `--count`

Requisitos: AC-O07, AC-O13 (delta `PRD-v2.2.md`) · Archivo: `tests/test_group_count.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Respuesta con exactamente `ok`, `command`, `generated_at`, `content_notice`, `count`, `hint`, `warnings`, `scan`, en ese orden; `hint: null` con resultados. |
| .02 | P | Con 250 mensajes (plugin falso) el `count` es 250, sin el límite de 200 ni de `--limit`, y después de deduplicar. |
| .03 | P | Cero resultados → `count: 0`, hint de RF-78, exit 0. |
| .04 | N | `--count` con `--fields`, con `--group-by` y con `--limit` ⇒ `E_USAGE` con el mensaje y el hint literales. |
| .05 | N | `--count --text x` sin filtro de acotamiento ⇒ `E_UNBOUNDED_SCAN`; con más candidatos que `[search].max_scan` ⇒ `E_SCAN_TOO_LARGE`. |

#### UT-GRP-06 — `new` sin agrupación ni recuento

Requisitos: AC-O08 (delta `PRD-v2.2.md`) · Archivo: `tests/test_group_count.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | `new --group-by from` y `new --count` ⇒ `E_USAGE`, exit 2, y `state.json` no cambia (ni se crea si no existía). |

#### UT-GRP-07 — Lecturas

Requisitos: AC-O01 (delta `PRD-v2.2.md`) · Archivo: `tests/test_group_count.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `--group-by` sin `--text`: ninguna extracción de cuerpo; cabeceras leídas solo de los mensajes emitidos (con `--limit 1`, una por grupo; con `--limit 0`, ninguna). |
| .02 | P | `--count` sin `--text`: ni cuerpos ni cabeceras; `scan.messages_read: 0` (Apple Mail y doble de Outlook, sin `--to`/`--cc`; el doble no abre ningún item). |
| .03 | P | `--group-by from --text <patrón>`: los cuerpos se leen para filtrar, los grupos solo contienen mensajes que cumplen el patrón y las filas no llevan `snippet` sin `--fields snippet`. |

#### UT-GRP-08 — `hint` de `search` sin resultados

Requisitos: AC-O13 (delta `PRD-v2.2.md`) · Archivo: `tests/test_group_count.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | macOS, Windows y plugin: dos cuentas declaradas con solo INBOX → `no messages matched in 2 folder(s) of 2 account(s); run "mailquery mailboxes" to see other folders, or add --include-mailbox`. |
| .02 | P | `<n>` cuenta INBOX, `mailbox_list` y `--include-mailbox`; también con `--group-by` y con `--count`; una cuenta declarada sin ninguna carpeta cuenta como leída con 0 carpetas. |
| .03 | B | Una cuenta declarada cuyo store está excluido (`W_STORE_EXCLUDED`) no cuenta en `<m>` ni sus carpetas en `<n>`. |
| .04 | N | Sin cuentas leídas (ninguna declarada o todas excluidas) → `hint: null` y `W_NO_ACCOUNTS`. |
| .05 | N | Con resultados, `hint` como antes; `new` sin correo nuevo → `hint: null`. |
| .06 | B | El hint no contiene nombres de carpetas ni de cuentas, y la secuencia de llamadas al driver es la misma que la de la misma búsqueda sin calcular el hint (comparación del `CallLog` del doble y de las llamadas del plugin falso). |
| .07 | B | D-23: una cuenta con INBOX también en `mailbox_list` y una carpeta en `mailbox_list` y en `--include-mailbox` cuenta cada carpeta una vez (`<n>` = carpetas únicas por cuenta). |

#### UT-GRP-09 — Warnings con `--count` y `--group-by`

Requisitos: AC-O09 (delta `PRD-v2.2.md`) · Archivo: `tests/test_group_count.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Con `--count`, solo warnings de alcance (`W_NO_ACCOUNTS`, `W_STORE_EXCLUDED`, `W_ACCOUNT_LABELS_UNAVAILABLE`), aunque los mensajes tengan URLs o fallos de autenticación (Apple Mail y plugin falso). |
| .02 | P | Con `--group-by`, `W_SENDER_AUTH_FAILED` de un mensaje emitido aparece; el conteo de URLs del cuerpo solo con `--fields snippet`. |

#### UT-GRP-10 — `content_notice` con cualquier opción

Requisitos: AC-H18 (delta `PRD-v2.2.md`) · Archivo: `tests/test_group_count.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `search --count` y `search --group-by from` de éxito llevan `content_notice` tras `generated_at`. |

#### DOC-11 — Documentación de `--group-by` y `--count`

Requisitos: AC-O10 (delta `PRD-v2.2.md`) · Archivo: `tests/test_group_count.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `search --help` describe `--group-by` con sus siete claves y `--count`. |
| .02 | P | Los dos README documentan `--group-by` y `--count` con ejemplos (`domain,month`) y el `hint` de cero resultados. |
| .03 | P | La skill explica `--group-by` y `--count` y que `new` no los admite. |

#### UT-MBX-01 — Forma por defecto

Requisitos: AC-O14 (delta `PRD-v2.2.md`) · Archivo: `tests/test_mailboxes.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Sin `--fields`: claves de primer nivel exactamente `ok`, `command`, `generated_at`, `accounts`, `excluded_stores`, `warnings`, con el store sintético, el doble de Outlook y un plugin falso. |
| .02 | P | Cada cuenta tiene `uuid`, `label`, `email`, `declared` y `mailboxes`, en ese orden; cada carpeta solo `path` e `included`, con los mismos valores e igual orden que el catálogo plano anterior. |
| .03 | N | Ninguna carpeta lleva `account`; no hay `mailboxes` de primer nivel. |
| .04 | B | Una cuenta declarada sin carpetas tiene `mailboxes: []`; con dos drivers declarados, el orden de cuentas es el de `PRD.md` §11.3; una carpeta sin cuenta se agrupa en una cuenta con `uuid: ""`, `label: ""`, `email: null` y `declared: false`. |

#### UT-MBX-02 — Referencias copiadas

Requisitos: AC-O14 (delta `PRD-v2.2.md`) · Archivo: `tests/test_mailboxes.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Un `path` copiado de la salida resuelve en `mailbox_list` y en `--include-mailbox`. |
| .02 | P | El `name` y la `url` de `--fields name,url` siguen resolviendo en `mailbox_list` y en `--include-mailbox`. |

#### UT-MBX-03 — `--fields`

Requisitos: AC-O15 (delta `PRD-v2.2.md`) · Archivo: `tests/test_mailboxes.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `--fields name,url,total,unread` y `--fields total --fields name,url,unread` añaden esos campos en el orden `name`, `path`, `url`, `total`, `unread`, `included`, con los valores del catálogo anterior. |
| .02 | P | `--fields path,included` da exactamente la salida por defecto. |
| .03 | N | `--fields all`, `--fields carpeta` y `--fields ""` ⇒ `E_USAGE`, exit 2, con `unknown field '<nombre>' in --fields` y `valid fields: name, path, url, total, unread, included`, antes de crear el home y sin ejecutar el comando. |

#### UT-MBX-04 — Sin recuento sin `total` ni `unread`

Requisitos: AC-O15 (delta `PRD-v2.2.md`) · Archivo: `tests/test_mailboxes.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Apple Mail: sin `total`/`unread`, `_mailbox_counters` no se ejecuta (espía); con `--fields unread`, una vez. |
| .02 | P | Outlook (doble): sin contadores no se leen tablas de carpeta (`Folder.GetTable` no aparece); con `--fields total`, sí. |
| .03 | P | Plugin falso que entrega contadores: sin `--fields`, la salida no los incluye. |
| .04 | B | `search`, `new` y `show` en Apple Mail ya no ejecutan el recuento de carpetas (espía), con la misma salida que antes. |
| .05 | B | Apple Mail, mismo proceso: dos peticiones de contadores reutilizan el recuento (la consulta se ejecuta una vez). |
| .06 | N | Apple Mail: un error de SQLite durante el recuento diferido de `mailboxes --fields total` da el mismo error que el recuento al cargar el catálogo (`E_INTERNAL`, exit 1); sin contadores el comando no falla. |
| .07 | B | Plugin falso cuyas filas no traen contadores: `mailboxes --fields total` no falla y emite `null`; con contadores, los valores del plugin. |

#### UT-MBX-05 — Ayudas

Requisitos: AC-O15 (delta `PRD-v2.2.md`) · Archivo: `tests/test_mailboxes.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `mailboxes --help` describe `--fields` con `name, path, url, total, unread, included` y que los contadores solo se calculan con `--fields total` o `unread`. |
| .02 | P | La ayuda general muestra `list accounts and their folders (counters with --fields)` para `mailboxes`. |

#### DOC-13 — Documentación de `mailboxes`

Requisitos: AC-O14, AC-O15 (delta `PRD-v2.2.md`) · Archivo: `tests/test_mailboxes.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Los dos README muestran la salida agrupada (ejemplo de PRD-v2.2 sección 8) y `--fields total,unread` para los contadores; ningún README describe un `mailboxes[]` de primer nivel con `account`. |
| .02 | P | La skill usa `mailboxes` sin `--fields` para ver carpetas y `--fields total,unread` solo cuando hacen falta los contadores. |
| .03 | P | `docs/config.example.toml` explica que `mailbox_list` acepta el `path` que muestra `mailboxes` (y el nombre o la URL de `--fields name,url`). |

### Estado, búsqueda y store

#### UT-BE-01 — Selección del backend

Requisitos: RF-26 · Archivo: `tests/test_backends.py`

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

Archivo: `tests/test_backends.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `MailBackend` declara exactamente las operaciones de la interfaz de backend. |
| .02 | N | Una subclase incompleta no se instancia. |

#### UT-BE-04 — Contrato de backend

Requisitos: RF-12, RF-13 · Archivo: `tests/test_backends.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | B | `query(since=…)` incluye el segundo exacto. |
| .02 | B | `query(until=…)` excluye el segundo exacto. |
| .03 | P | `query(unread=True)`. |
| .04 | P | `resolve_mailbox` por `INBOX`, nombre, path y URL; path o URL exactos ganan a un nombre; con dos carpetas del mismo nombre, la primera de `mailboxes`. |
| .05 | N | `resolve_mailbox` inexistente ⇒ `None`. |

#### UT-SR-01 — Comodines y acentos

Archivo: `tests/test_search.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Subcadena sin comodines. |
| .02 | P | `*factura*`. |
| .03 | P | `factura*` ⇒ coincide en cualquier posición del texto (patrón sin ancla). |
| .04 | P | `?actura`. |
| .05 | P | `FACTURA` ⇒ coincide (sin mayúsculas). |
| .06 | P | `fáctura` ⇒ coincide con `factura` (sin acentos). |
| .07 | P | `[`, `.` y `(` se tratan como literales. |

#### UT-SR-02 — Términos de filtro

Archivo: `tests/test_search.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `--subject "*a* *b*"` ⇒ a AND b. |
| .02 | N | `--text "reserva confirmada"` con "confirmada … reserva" ⇒ no coincide. |
| .03 | N | `--from`, `--to` y `--cc` `"Perez Juan"` con "Juan Perez" ⇒ no coincide. |

#### UT-SR-03 — Acotamiento de `--text` en macOS

Requisitos: RF-17 · Archivo: `tests/test_search.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | `--text x` sin filtros ⇒ `E_UNBOUNDED_SCAN`, exit 4; el mensaje nombra `--text` y el hint lista los filtros que acotan en macOS. |
| .02 | N | `--text x --from ""` ⇒ `E_UNBOUNDED_SCAN`. |
| .03 | N | `--text x --include-mailbox INBOX` ⇒ `E_UNBOUNDED_SCAN`. |
| .04 | P | `--text x --to y` ⇒ ejecuta; `scan.candidates` cuenta los mensajes tras `--to`. |
| .05 | B | Candidatos == `max_scan` ⇒ ejecuta. |
| .06 | B | Con varios drivers, `max_scan` se compara con la suma de los candidatos de todos ellos. |

#### UT-SR-04 — `--include-mailbox`

Requisitos: RF-14 · Archivo: `tests/test_search.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Carpeta inexistente ⇒ `E_MAILBOX_NOT_FOUND`, hint con las carpetas de todas las cuentas declaradas. |
| .02 | P | `--include-mailbox` resuelve la carpeta dentro de su propio driver. |

#### UT-SR-05 — `body` en `search`/`new`

Requisitos: RF-05, RF-06 · Archivo: `tests/test_search.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | `.emlx` que no se puede abrir (`PermissionError` simulado) ⇒ `false/false/false` + `W_BODY_UNREADABLE`. |
| .02 | N | Ruta no resoluble ⇒ ídem. |
| .03 | N | Mensaje sin carpeta ⇒ ídem. |
| .04 | N | Corrupto recuperable ⇒ `true/true/false` + `W_EMLX_CORRUPT`. |
| .05 | N | S/MIME cifrado ⇒ `true/false/false` + `W_BODY_UNREADABLE: S/MIME encrypted content is not supported`, sin `W_EMLX_CORRUPT`. |
| .06 | N | S/MIME firmado ⇒ ídem con `signed`. |
| .07 | B | Cuerpo de 200 y de 201 caracteres ⇒ `body.truncated` `false` y `true`. |
| .08 | N | HTML sin texto ⇒ `available=true`, `readable=true`, `snippet: ""` y `W_HTML_NO_TEXT`. |

#### UT-SR-06 — Etiquetas no disponibles

Archivo: `tests/test_search.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `search` ⇒ `W_ACCOUNT_LABELS_UNAVAILABLE`. |
| .02 | P | `show` ⇒ ídem. |
| .03 | P | Primera corrida de `new` ⇒ `W_ACCOUNT_LABELS_UNAVAILABLE` y `W_FIRST_RUN` al final. |

#### UT-SR-07 — Primera corrida de `new`

Requisitos: RF-01, RF-02 · Archivo: `tests/test_search.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | B | Mensaje exactamente en `D − lookback` ⇒ incluido. |
| .02 | B | Mensaje un segundo antes ⇒ excluido. |
| .03 | B | Alcance con un solo mensaje ⇒ lo emite. |
| .04 | B | `--limit` menor que la ventana ⇒ los `--limit` más recientes, en orden ascendente. |
| .05 | N | `--peek` ⇒ emite y no escribe estado. |
| .06 | P | Sin `--peek` ⇒ cursor en el último emitido y uids en el anillo. |
| .07 | B | Cuentas declaradas sin mensajes ⇒ `count: 0`, `W_FIRST_RUN`, sin estado. |
| .08 | B | Sin cuentas declaradas ⇒ `W_NO_ACCOUNTS` y `W_FIRST_RUN`, en ese orden, sin estado. |
| .09 | P | `lookback = "1h"` ⇒ `W_FIRST_RUN` con `1h`. |

#### UT-SR-08 — Lookback

Archivo: `tests/test_search.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Cada corrida usa `[new].lookback` de la config actual, aunque el estado guarde otro, y lo guarda en `cursor.lookback_seconds`. |

#### UT-SR-09 — Fechas inválidas

Archivo: `tests/test_search.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Fecha nula en la primera corrida ⇒ no entra. |
| .02 | B | Fecha 0 ⇒ no entra. |
| .03 | N | Fecha 1e20 ⇒ no entra. |
| .04 | N | En corridas siguientes ⇒ no entran ni mueven el cursor. |
| .05 | P | `search` las muestra con `date_received: null` y no aborta. |

#### UT-SR-10 — Fechas futuras en `new`

Archivo: `tests/test_search.py`

Reloj inyectado.

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Primera corrida ⇒ no entra ni cuenta como "el más reciente". |
| .02 | N | Corrida siguiente ⇒ no entra ni mueve el cursor. |
| .03 | P | Cuando deja de ser futura ⇒ entra en esa corrida. |
| .04 | B | Fecha igual al momento de la corrida ⇒ entra. |
| .05 | P | `search` y `show` la muestran con su fecha. |

#### UT-SR-11 — `show` y alcance

Requisitos: RF-04 · Archivo: `tests/test_search.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | uid de una cuenta declarada en una carpeta de `mailbox_list` ⇒ éxito, campos en el orden de §12.4. |
| .02 | P | uid de una cuenta declarada fuera de `mailbox_list` ⇒ éxito. |
| .03 | N | Sin cuentas declaradas ⇒ `E_ACCOUNT_NOT_IN_SCOPE`. |
| .04 | N | uid inexistente ⇒ `E_USAGE` `message uid … was not found`. |
| .05 | N | uid de un mensaje borrado ⇒ ídem. |
| .06 | N | `[scope]` con una cuenta desconocida ⇒ el mismo error que `search`, aunque el mensaje no esté en esa cuenta. |
| .07 | N | `mailbox_list` con una carpeta inexistente ⇒ `E_MAILBOX_NOT_FOUND`. |
| .08 | B | Cuerpo de 20.000 y de 20.001 caracteres ⇒ `body_truncated` `false` y `true` (con `W_BODY_TRUNCATED`). |

#### UT-SR-12 — `show`: adjuntos con cuerpo ilegible

Archivo: `tests/test_search.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | `.emlx` ausente con adjuntos en el `Envelope Index` ⇒ nombres del índice + `W_ATTACHMENTS_UNAVAILABLE`. |
| .02 | N | S/MIME firmado sin fila en `attachments` ⇒ `attachments: []`, sin los adjuntos del MIME ni `W_ATTACHMENTS_UNAVAILABLE`. |

#### UT-SR-13 — Consultas con la base bloqueada

Archivo: `tests/test_search.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | B | Consulta de `search.py` bloqueada una vez ⇒ éxito tras un reintento a los 100 ms. |
| .02 | N | Bloqueo persistente ⇒ `E_DB_BUSY`, exit 5, hint no vacío. |
| .03 | N | Catálogo de carpetas bloqueado (`store.py:572-580`) ⇒ `E_DB_BUSY`. |

#### UT-SR-14 — INBOX

Archivo: `tests/test_search.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `inbox` de primer nivel en minúsculas ⇒ INBOX. |
| .02 | N | `Proyectos/Inbox` ⇒ no es INBOX, ni en `is_inbox` ni en el alcance. |

#### UT-SR-15 — Dedupe

Requisitos: RF-07 · Archivo: `tests/test_search.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Duplicado en una carpeta normal y un buzón agregado ⇒ canónico la carpeta normal. |
| .02 | B | `global_message_id` 0 ⇒ único, `duplicate_count: 1`. |

#### UT-SR-16 — Referencias de carpeta entre cuentas

Archivo: `tests/test_search.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Con `Proyectos/Inbox` en la cuenta, `INBOX` ⇒ la bandeja de la cuenta. |
| .02 | P | `--include-mailbox` se resuelve en el orden de los bloques: `INBOX` con dos cuentas declaradas ⇒ la de la primera. |
| .03 | P | Path o URL exactos que coinciden con el nombre de otra carpeta ⇒ gana el path o la URL, cada uno. |
| .04 | P | Dos carpetas con el mismo nombre en paths distintos ⇒ la primera de `mailboxes`. |

#### UT-SR-17 — Orden canónico de campos

Archivo: `tests/test_search.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Las claves de cada fila de `search` sobre el store sintético son exactamente `SEARCH_ROW_FIELDS`, en ese orden. |
| .02 | P | Las claves de `message` de `show` son exactamente `SHOW_FIELDS`, en ese orden, sobre el store sintético y sobre el doble de Outlook. |

#### UT-ST-01 — Lock

Requisitos: RF-22 · Archivo: `tests/test_state.py`

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

Archivo: `tests/test_state.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | `cursor: {}` ⇒ `E_STATE_CORRUPT`. |
| .02 | N | `last_date_received` negativo ⇒ ídem. |
| .06 | P | `cursor: null` ⇒ sin cursor. |

#### UT-ST-04 — `E_STATE_CORRUPT`

Archivo: `tests/test_state.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Hint: renombrar el archivo; la siguiente corrida es una primera corrida que emite la ventana. |

#### UT-ST-05 — Escritura del estado

Requisitos: RF-23 · Archivo: `tests/test_state.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | `ENOSPC` ⇒ `E_INTERNAL`, exit 1, cursor previo intacto. |
| .02 | N | `EACCES` ⇒ `E_PERMISSION`, cursor previo intacto. |

#### UT-ST-06 — Migración schema 1 → 2

Requisitos: AC-06 · Archivo: `tests/test_cli.py`, `tests/test_state.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Función pura de migración: enteros ≥ 1 en `cursor.last_uid` y `emitted_uids` ⇒ `apple_mail:<n>`, sin depender del SO. |
| .02 | P | Strings hexadecimales en mayúsculas ⇒ `outlook:<HEX>`; mayúsculas/minúsculas no se reinterpretan (un valor inválido cae en.03). Estos dos casos prueban la función pura o inyectan un registro con ambos drivers para que la validación posterior no dependa de la plataforma. |
| .03 | N | Valor no entero, no hex en mayúsculas, `0`, negativo, `None`, lista ⇒ `E_STATE_CORRUPT` con hint de renombrar; un entero migrado cuyo driver no está instalado ⇒ `E_STATE_CORRUPT` en la validación de schema 2 (caso separado). |
| .04 | P | `new --peek` migra en memoria, no escribe y responde con el cursor migrado. |
| .05 | P | La siguiente corrida de `new` no `--peek` persiste schema 2 con la escritura atómica; el original solo se reemplaza al final. |
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

### Plugins, drivers y multi-driver

#### UT-DRV-01 — Esquema de `[scope]`

Requisitos: AC-03 · Archivo: `tests/test_config.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `[scope."apple_mail:you@icloud.com"]` ⇒ driver `apple_mail`, cuenta resuelta dentro de sus cuentas. |
| .02 | P | `[scope."you@icloud.com"]` ⇒ driver nativo del SO. |
| .03 | P | Etiqueta con `:` declarada con prefijo explícito funciona; sin prefijo ⇒ `E_DRIVER_UNKNOWN` (limitación documentada). |
| .04 | N | Driver con mayúsculas, guion, vacío o > 64 ⇒ `E_DRIVER_UNKNOWN`. |
| .05 | N | Driver bien formado pero no instalado ⇒ `E_DRIVER_UNKNOWN`; todos los comandos de datos fallan (no se ignora). |
| .06 | P | Dos bloques que resuelven a la misma `(driver, cuenta)` combinan `mailbox_list`. |

#### UT-DRV-02 — Resolución de cuentas por driver

Requisitos: AC-03 · Archivo: `tests/test_config.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Backend interno: label, email único y UUID completo/prefijo ≥ 8 dentro del driver. |
| .02 | P | Plugin: `label`/`uuid` opacos, incluido label corto (< 8) que en un backend interno sería ambiguo. |
| .03 | N | Cuenta inexistente ⇒ `E_CONFIG_ACCOUNT_UNKNOWN`; ambigua ⇒ `E_ACCOUNT_AMBIGUOUS`. |
| .04 | N | Store excluido de Outlook declarado ⇒ `W_STORE_EXCLUDED` con la etiqueta/ruta, sin abortar. |

#### UT-DRV-03 — Driver instalado no declarado

Requisitos: AC-03 · Archivo: `tests/test_config.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Los comandos de datos no consultan un driver instalado sin bloques `[scope]`. |
| .02 | N | El helper de alcance devuelve `E_ACCOUNT_NOT_IN_SCOPE` (exit 2) para un driver instalado sin bloque `[scope]`, con el hint de declarar la cuenta. Los comandos `show` y `attachment` con ese prefijo se prueban en UT-UID-02 y UT-ATC-02. |
| .03 | N | Un prefijo de driver no instalado ⇒ `E_DRIVER_UNKNOWN` (exit 2). |

#### UT-DRV-04 — `[attachments]`

Requisitos: AC-14, RF-42/49 · Archivo: `tests/test_config.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Sin tabla ⇒ defaults `enabled=true`, `100`/`200`/`50`. |
| .02 | P | Valores válidos personalizados se aceptan y exponen. |
| .03 | N | `enabled` no booleano; `max_file_size_mb` 0, 501, `"100"`, `true`; `max_total_size_mb` 0, 1025; `max_count` 0, 501 ⇒ `E_CONFIG_INVALID`. |
| .04 | N | `max_total_size_mb < max_file_size_mb` ⇒ `E_CONFIG_INVALID` con hint. |
| .05 | N | Clave desconocida en `[attachments]` o sección desconocida ⇒ `E_CONFIG_INVALID`. |

#### UT-DRV-05 — `doctor driver`

Requisitos: AC-02, AC-18 · Archivo: `tests/test_cli.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Orden de chequeos de macOS y de Windows con `driver` tras `home`. |
| .02 | P | `detail` por driver con `api`, `pkg`, `network`, `readonly`, `body_local`, `attachments` y `native_order`. |
| .03 | N | Un driver declarado incompatible ⇒ `driver` `ok=false` con motivo/hint; `config` `not evaluated: driver failed`; exit 0. |
| .04 | N | `config.toml` inválido ⇒ `driver` valida solo el nativo con `declared drivers: unknown (config failed)`; el error lo reporta `config`. |
| .05 | P | Sin config o sin bloques ⇒ `driver` valida el nativo con `no declared drivers`. |
| .06 | N | Varios drivers declarados (nativo + plugin) ⇒ `detail` los lista todos; si uno falla, `driver` falla y `config` no se evalúa; los chequeos del nativo siguen su curso salvo dependencia. |
| .07 | N | `driver` y `schema`/`stores` fallan a la vez ⇒ `config` informa `not evaluated: driver failed` (el driver se evalúa primero); `schema`/`stores` conservan su dependencia del backend nativo. |
| .08 | P | `driver` aparece exactamente en la posición 3 de la lista ordenada, tanto en macOS como en Windows (plataforma parcheada). |

#### UT-ERR-01 — Mapeo `reason`→`code`/exit

Requisitos: AC-16 · Archivo: `tests/test_plugins.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Tabla completa en operación de adjuntos: `invalid_uid`/`not_found` ⇒ `E_USAGE` (2); `not_local`/`not_downloaded`/`unsupported`/`network` ⇒ `E_ATTACHMENT_UNAVAILABLE` (3); `corrupt`/`smime`/`unreadable` ⇒ `E_ATTACHMENT_UNREADABLE` (3); `permission`/`auth` ⇒ `E_PERMISSION` (3); `busy` ⇒ `E_CLIENT_BUSY` (5); `timeout` ⇒ `E_CLIENT_TIMEOUT` (3). |
| .02 | P | Tabla completa en el resto de operaciones: `invalid_uid`/`not_found` ⇒ `E_USAGE`; el resto de motivos de adjunto ⇒ `E_PLUGIN_FAILED`; `permission`/`auth`, `busy`, `timeout` conservan su código. |
| .03 | N | `reason` desconocido, vacío o no string ⇒ `E_PLUGIN_FAILED` (3), nunca `E_INTERNAL`. |
| .04 | N | El plugin intenta fijar `code`/`exit` (p. ej. atributo extra o excepción con código propio) ⇒ se ignora; el código pertenece siempre al conjunto cerrado del núcleo. |
| .05 | P | El objeto `error` es `{code, message, hint}` y `command` y `generated_at` siguen el contrato de salida (§12.5). |

#### UT-ERR-02 — Saneado, límites y plantillas

Requisitos: AC-16/AC-19 · Archivo: `tests/test_plugins.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `hint` de 301 bytes, `detail` de 201 y `log_message` de 201 se truncan a ≤ 300/200/200 bytes sin partir un carácter. |
| .02 | N | Controles (`\x00`, `\r`, `\n`, ANSI, `\u202e`) en `hint`/`detail`/`log_message` se eliminan. |
| .03 | P | El `message` usa la plantilla del motivo y añade el `detail` saneado después de `: `; table-driven con las plantillas de §12.6 (`not available in the local store`, `could not be retrieved from its origin`, `cannot be recovered by driver '<driver>'`, `is corrupt or unreadable`, `is S/MIME protected and cannot be extracted`, `cannot be read: permission denied`, `is temporarily unavailable`, `did not respond within the timeout`) y sus motivos (`not_local`, `not_downloaded`, `unsupported`, `network`, `corrupt`, `unreadable`, `smime`, `permission`, `busy`, `timeout`). |
| .04 | P | El log registra el `log_message` saneado y nunca el `hint` ni el `detail`. |
| .05 | N | `hint`/`detail` con uid, nombre de archivo, ruta, cuenta o término **nunca** llegan al log; el `log_message` se sanea (controles, ≤ 200 bytes). La obligación de que el plugin no incluya PII en `log_message` se prueba en el doble, no como saneado del núcleo. |
| .06 | P | Los `hint` de §12.6 se respetan: `E_DRIVER_UNKNOWN` lista los drivers instalados e indica `pipx inject mailquery <paquete>`; `E_PLUGIN_FAILED` sugiere `run "mailquery doctor"`; el hint de un motivo de adjunto es el del motivo. |

#### UT-ERR-03 — Fallos no mapeados

Requisitos: AC-16 · Archivo: `tests/test_multidriver.py`, `tests/test_plugins.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Excepción no mapeada en una operación ⇒ `E_PLUGIN_FAILED` (3), sin traceback de plugin en el JSON. |
| .02 | N | Tipos de retorno inválidos (fila no dict, `native_id` no string, lista de adjuntos mal formada) ⇒ `E_PLUGIN_FAILED`. |
| .03 | P | Un fallo inesperado del núcleo (no del plugin) sigue siendo `E_INTERNAL` (exit 1), sin cambio. |
| .04 | N | El comando falla sin resultados parciales y cierra los drivers abiertos. |

#### UT-ERR-04 — Timeout de metadatos

Requisitos: AC-17, RNF-16 · Archivo: `tests/test_multidriver.py`, `tests/test_plugins.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Una operación de metadatos de plugin que supera 30 s (plazo inyectado) ⇒ `E_CLIENT_TIMEOUT` (3), sin reintento automático. |
| .02 | N | El timeout no deja resultados parciales ni estado escrito. |
| .03 | P | Una operación por debajo del plazo no se interrumpe. |
| .04 | N | Una operación de metadatos del backend nativo también está envuelta: con plazo inyectado superado ⇒ `E_CLIENT_TIMEOUT` (3), sin tocar el watchdog COM de Outlook. |
| .05 | N | El timeout de una operación durante el merge cierra los drivers abiertos y no emite `messages[]` parcial. |

#### UT-MD-01 — Carga y fail-fast

Requisitos: AC-04 · Archivo: `tests/test_multidriver.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Solo se cargan los drivers declarados (más el nativo si hay bloques sin prefijo); los no declarados no se importan. |
| .02 | N | Un driver declarado no carga ⇒ el comando falla con su código y sin resultados parciales. |
| .03 | N | Un driver falla en runtime a mitad del merge ⇒ el comando falla con el código mapeado; no hay `messages[]` parcial. |
| .04 | P | Todos los drivers se cierran aunque el comando falle. |

#### UT-MD-02 — Merge y orden

Requisitos: AC-04 · Archivo: `tests/test_multidriver.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `search` con dos drivers: orden `(date_received DESC, driver ASC, native_order_key DESC)`. |
| .02 | P | `new` con dos drivers: orden ascendente; el cursor avanza con el último emitido. |
| .03 | P | Mismo `message_id` en dos drivers ⇒ dos resultados, `duplicate_count` independiente por driver. |
| .04 | P | Duplicado dentro de un driver sigue eligiendo la copia canónica (INBOX/carpeta normal) y `duplicate_count: 2`. |
| .05 | B | Misma fecha y mismo driver, distinto `native_order_key` numérico y textual ⇒ desempate estable y determinista. |
| .06 | B | Misma fecha y distinto driver ⇒ desempata por `driver` ascendente. |

#### UT-MD-03 — `mailboxes` multi-driver

Requisitos: AC-04 · Archivo: `tests/test_multidriver.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `accounts[]` (cada uno con su `mailboxes[]`) y `excluded_stores[]` concatenados en el orden de los bloques `[scope]`. |
| .02 | P | Un plugin devuelve `excluded_stores: []` y `accounts[]` con `label`/`uuid` opacos y sus carpetas en `mailboxes[]`. |
| .03 | B | Un driver sin cuentas declaradas no aporta bloques y no rompe el comando. |

#### UT-MD-04 — Cursor y lookback

Requisitos: AC-04 · Archivo: `tests/test_multidriver.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Un único cursor global; cada driver se consulta con el mismo `last_date_received` y `lookback`. |
| .02 | P | Primera corrida: ventana sobre el conjunto fusionado y anillo con uids prefijados. |
| .03 | N | `cursor.last_uid` de un driver instalado pero no declarado: el cursor se conserva, se usa la fecha como marca y los uids de ese driver no se comparan. |
| .04 | P | Los uids de drivers no declarados permanecen en el anillo sin romper `new`. |

#### UT-MD-05 — Límites y `scan`

Requisitos: AC-04 · Archivo: `tests/test_multidriver.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `--limit` se aplica tras el merge; `truncated`/`hint` se calculan sobre el resultado fusionado. |
| .02 | P | `scan.candidates` suma por driver; `scan.messages_read` suma las lecturas. |
| .03 | B | `--limit` mayor que el total ⇒ sin `truncated` ni `hint`. |

#### UT-MD-06 — Log multi-driver

Requisitos: AC-19 · Archivo: `tests/test_multidriver.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `event=start` registra `backend=<nativo>` y `drivers=<lista declarada>`. |
| .02 | N | El log no registra uids, `native_id`, cuentas, rutas, asuntos ni términos. |
| .03 | P | Un comando con solo un driver declarado registra `drivers=` con ese driver y `backend=` con el nativo. |

#### UT-MD-07 — `show` con driver externo declarado

Requisitos: AC-05, AC-07 · Archivo: `tests/test_multidriver.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `show <plugin>:<native_id>` carga el plugin declarado y devuelve uid prefijado, cuerpo (`body_local: true` o `false`) y `attachments[]` con `{index, name, cached_path}`; `cached_path` es `null` si no hay caché. |
| .02 | P | Un plugin con `body_local: false` obtiene el cuerpo del plugin; si no está disponible, aplica `W_BODY_NOT_LOCAL`/`W_BODY_UNREADABLE` (§12.10). |
| .03 | N | `show` de un plugin instalado pero no declarado ⇒ `E_ACCOUNT_NOT_IN_SCOPE` (exit 2) sin importar/cargar el plugin. |
| .04 | N | `show` de un plugin con `attachments: "none"` ⇒ `attachments: []`; no se llama a la operación de adjuntos. |
| .05 | N | `show` de un plugin con `attachments: "remote"` y `network: true` devuelve solo nombres (sin red en el núcleo); `show` no escribe ni descarga. |
| .06 | P | `native_order_key` del plugin se usa en el orden de `search`/`show` con la capacidad `native_order` declarada. |

#### UT-PL-01 — Registro de drivers

Requisitos: AC-01, RF-35 · Archivo: `tests/test_plugins.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | El grupo `mailquery.backends` expone `apple_mail` y `outlook`; el registro los lista con `driver`, `plugin_api` y versión **sin importar** los módulos. |
| .02 | P | Fallback de desarrollo: con el paquete sin instalar, los backends internos se resuelven igual. |
| .03 | P | Metadata inyectada: un plugin externo que cumple el contrato (driver válido, API 1, capacidades) se registra por la misma vía y aparece en el listado; no se exige `pip install` en CI. |
| .04 | N | Un plugin declara un nombre reservado (`apple_mail`/`outlook`) ⇒ `E_PLUGIN_INCOMPATIBLE`. |
| .05 | N | `driver` que no cumple `[a-z0-9_]{1,64}` (`Apple_Mail`, `apple-mail`, vacío, 65 caracteres) ⇒ `E_PLUGIN_INCOMPATIBLE`. |
| .06 | N | `plugin_api` ausente o `≠ 1` ⇒ `E_PLUGIN_INCOMPATIBLE`; el hint incluye esperado/encontrado. |
| .07 | N | Un plugin declarado no importa (dependencia faltante) ⇒ `E_PLUGIN_INCOMPATIBLE`; los demás drivers siguen siendo listables. |
| .08 | P | Carga perezosa: un comando con solo el driver nativo declarado no importa el resto; `--version` no importa ninguno. |
| .09 | P | Orden alfabético en `drivers:` con dos drivers (plugin fake + nativo) y filtrado por plataforma de los internos. |
| .10 | N | `driver` duplicado (interno + plugin o dos plugins) ⇒ `E_PLUGIN_INCOMPATIBLE`, exit 3. |

#### UT-PL-02 — Capacidades

Requisitos: AC-02, RF-38 · Archivo: `tests/test_plugins.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Mapa válido (`network`, `readonly`, `body_local`, `attachments`, `native_order`) aceptado y expuesto. |
| .02 | N | Falta una capacidad ⇒ `E_PLUGIN_INCOMPATIBLE`. |
| .03 | N | Valor fuera de enum (`attachments: "zip"`, `readonly: "yes"`, `native_order: "alpha"`) ⇒ `E_PLUGIN_INCOMPATIBLE`. |
| .04 | N | `attachments: "remote"` sin `network: true` ⇒ `E_PLUGIN_INCOMPATIBLE`. |
| .05 | N | `body_local: false` sin `network: true` ⇒ `E_PLUGIN_INCOMPATIBLE`. |
| .06 | P | Varios drivers, cada uno con su mapa, se validan por separado. |

#### UT-PL-03 — `--version`

Requisitos: AC-18 · Archivo: `tests/test_plugins.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Formato exacto: prefijo de la versión instalada (`mailquery.__version__`, sin literal) con `; drivers: <driver> <versión>,...` alfabético dentro del paréntesis. |
| .02 | P | En macOS lista los drivers internos disponibles (`apple_mail`; no `outlook`); en Windows al revés (plataforma parcheada). Un plugin externo se lista siempre. |
| .03 | N | Sin efectos: no crea `~/.mailquery`, no lee `config.toml`, no escribe log, no toma lock, no abre el store. |
| .04 | P | Un plugin instalado aparece listado aunque sea incompatible; `doctor` es quien reporta el problema. |
| .05 | N | No importa módulos de plugin (metadata de distribución); un plugin instalado sin metadata de plataforma no se filtra. |
| .06 | P | Sin paquete instalado (modo desarrollo), `--version` usa la versión de `__version__`/metadata de respaldo y no falla. |

#### UT-PL-04 — API de plugin y archivos autónomos

Requisitos: AC-01, RF-39 · Archivo: `tests/test_plugins.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `PluginContext(home, tmp_dir)` y `PluginError(reason, hint, detail, log_message)` con el enum cerrado de `reason`; el doble de plugin solo necesita el paquete `mailquery.plugins`. |
| .02 | N | El núcleo no lee `~/.mailquery/<driver>.toml` ni `~/.mailquery/logs/<driver>.log`: con esos archivos presentes, comandos y `doctor` se comportan igual. |
| .03 | N | El núcleo no crea, rota ni borra `<driver>.toml`, `logs/<driver>.log` ni `tmp/plugin-<driver>/`. |
| .04 | P | Escaneo de imports: `src/mailquery/plugins/**` y `backends/registry.py` solo usan stdlib y el propio paquete (RNF-12). |

#### UT-UID-01 — Formato y parseo

Requisitos: AC-05, RF-40 · Archivo: `tests/test_uid.py`

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

### Adjuntos

#### UT-AM-01 — Bloqueo con fixtures reales

Requisitos: AC-09/AC-10 · Archivo: `tests/test_backends.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Mensaje con un adjunto hostil y otro seguro: `--index` del seguro, `--index` del hostil y `--all` ⇒ `E_ATTACHMENT_BLOCKED` (exit 4); nada escrito. |
| .02 | N | Nombres con traversal, separadores, `..`, `C:`, ADS, RLO/controles y reservado de Windows desde el fixture ⇒ bloqueo del mensaje. |
| .03 | N | Adjunto con `MZ` en los primeros bytes ⇒ bloqueo del mensaje; un archivo seguro del mismo mensaje no se escribe. |
| .04 | N | Mensaje con un adjunto no solicitado hostil: `--index` de un seguro ⇒ bloqueo (regla de todos los nombres). |
| .05 | P | Mensaje con todos los adjuntos permitidos ⇒ extracción correcta. |

#### UT-AM-02 — Índices, nombres y sanitización

Requisitos: AC-07/AC-11 · Archivo: `tests/test_backends.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Tres adjuntos con dos nombres repetidos ⇒ índices 1..N estables y distintos archivos `<NN>_<sanitized>`. |
| .02 | P | `show` y `attachment` devuelven el mismo `index` y el mismo `name` original para cada adjunto. |
| .03 | P | Sanitización sobre nombres Unicode/largos del fixture: NFKC, reemplazos, límites de 150/153 bytes y ruta final correcta. |
| .04 | P | `cached_path` de `show` apunta al archivo regular publicado. |

#### UT-AM-03 — Extracción y disponibilidad

Requisitos: AC-12/AC-15, AC-20 · Archivo: `tests/test_integration.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Primera extracción `cached: false`; segunda `cached: true`; `--force` re-extrae. |
| .02 | N | Adjunto cuyo `.emlx` no existe ⇒ `E_ATTACHMENT_UNAVAILABLE` (`not_local`). |
| .03 | N | Adjunto externalizado de `.partial.emlx` no verificable ⇒ `E_ATTACHMENT_UNAVAILABLE` (`unsupported`). |
| .04 | N | `--all` con un adjunto externalizado no verificable falla sin parciales; `--index` de un adjunto local seguro del mismo mensaje tiene éxito y no evalúa el externalizado no solicitado. |
| .05 | N | S/MIME cifrado ⇒ `E_ATTACHMENT_UNREADABLE` (`smime`), nunca `E_USAGE`; `show` devuelve `[]`. |
| .06 | N | MIME/base64 corrupto ⇒ `E_ATTACHMENT_UNREADABLE` (`corrupt`). |
| .07 | P | Adjunto de 0 bytes se guarda con `size_bytes: 0` y `sha256` del vacío. |
| .08 | P | Archivo de caché borrado antes de `attachment` ⇒ se re-extrae una vez. |
| .09 | N | Un fallo en `--all` no deja archivos parciales ni caché nueva incompleta. |

#### UT-AM-04 — Solo lectura e integración

Requisitos: AC-12, RNF-13 · Archivo: `tests/test_integration.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Tras `attachment` (éxito, caché, bloqueo, límite), hashes y `mtime` del store no cambian. |
| .02 | P | Todas las escrituras quedan bajo `~/.mailquery` (`attachments/`, `tmp/`, log/lock/estado); staging limpio. |
| .03 | P | Directorios `0700` y archivos `0600` en POSIX; sin `+x` (condición POSIX explícita; en Windows se prueba la herencia de ACL y no se relajan permisos). |
| .04 | P | El backend declara las capacidades de RF-38 y `attachments: "local"`; `doctor` las muestra. |

#### UT-ATC-01 — `show.attachments`

Requisitos: AC-07 · Archivo: `tests/test_cli.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Tres adjuntos ⇒ `[{index:1,name:"factura.pdf",cached_path:null}, …]` con índices estables 1..N. |
| .02 | P | Con un archivo en caché (regular) ⇒ `cached_path` absoluto y correcto; sin caché ⇒ `null`. |
| .03 | N | Nombre no seguro ⇒ `cached_path: null` aunque exista un archivo con ese nombre calculado; `show` no bloquea por contenido. |
| .04 | N | `show` nunca escribe: no crea caché, staging ni `state.json`; el `~/.mailquery` solo puede cambiar como en 2.0.1 (log/lock/estado de `new`). |
| .05 | N | Driver con `attachments: "none"` ⇒ `attachments: []`. |
| .06 | N | S/MIME cifrado ⇒ `attachments: []`, sin `W_ATTACHMENTS_UNAVAILABLE`, conservando el warning de cuerpo de 2.0.1. |
| .07 | P | El `index` de `show` coincide con el de `attachment` para el mismo mensaje. |
| .08 | N | `[attachments].enabled = false` no afecta a `show`. |
| .09 | N | `cached_path: null` si el archivo en caché es symlink, directorio o dispositivo, aunque exista; solo archivos regulares cuentan. |
| .10 | P | Un adjunto que `attachment` bloquearía **por contenido** (`MZ`) pero con archivo regular en caché sigue mostrando `cached_path` no nulo: `show` no inspecciona contenido. |

#### UT-ATC-02 — Argumentos, uid y precedencia temprana

Requisitos: AC-08 · Archivo: `tests/test_cli.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Sin modo o con ambos ⇒ `E_USAGE` "attachment requires exactly one of --index or --all". |
| .02 | N | `--index 0`, `-1`, `abc`, `1.5` ⇒ `E_USAGE` "invalid --index <v>: expected a positive integer (1 or greater)". |
| .03 | N | uid malformado ⇒ `E_USAGE`; driver desconocido ⇒ `E_DRIVER_UNKNOWN`; ambos antes de crear el home, leer config o abrir el store, y sin escribir estado ni caché. |
| .04 | N | `config.toml` inválido ⇒ `E_CONFIG_INVALID`; driver de `[scope]` no instalado ⇒ `E_DRIVER_UNKNOWN`. |
| .05 | N | `enabled = false` ⇒ `E_ATTACHMENTS_DISABLED` (exit 2) antes de abrir el store; `show` no se ve afectado. |
| .06 | N | Driver instalado pero no declarado ⇒ `E_ACCOUNT_NOT_IN_SCOPE` (exit 2) sin cargar el driver; el hint indica declarar la cuenta. |
| .07 | N | `attachments: "none"` ⇒ `E_ATTACHMENT_UNAVAILABLE` (`unsupported`) antes de abrir el store. |
| .08 | P | Entrada con uid legado sin prefijo: `attachment 83143 --index 1` en macOS y `attachment <EntryID> --index 1` en Windows se resuelven con el driver nativo y devuelven `uid` prefijado. |
| .09 | N | Precedencia de filas adyacentes de la tabla de §12.11, table-driven: `--index 9` sobre mensaje con nombre bloqueado ⇒ `E_USAGE` (fila 10 antes que 11); `enabled=false` + `attachments:none` ⇒ `E_ATTACHMENTS_DISABLED` (fila 4 antes que 5); S/MIME + `--index 9` ⇒ `E_ATTACHMENT_UNREADABLE` (fila 8 antes que 10); uid con driver no instalado + `enabled=false` ⇒ `E_DRIVER_UNKNOWN` (fila 2 antes que 4). |

#### UT-ATC-03 — Validaciones con el store

Requisitos: AC-08 · Archivo: `tests/test_cli.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Mensaje inexistente, borrado u oculto ⇒ `E_USAGE` "message uid <uid> was not found". |
| .02 | N | Mensaje sin adjuntos (sin señal S/MIME/ilegible) ⇒ `E_USAGE` "message <uid> has no attachments". |
| .03 | N | S/MIME/ilegible con lista vacía ⇒ `E_ATTACHMENT_UNREADABLE` (exit 3) antes de la comprobación de “0 adjuntos”. |
| .04 | N | `--index N` mayor que M ⇒ `E_USAGE` con el texto de índice fuera de rango ("out of range: message ... has 3 attachment(s) (valid: 1..3)"). |
| .05 | P | `--index` válido y `--all` recuperan los adjuntos solicitados. |
| .06 | N | `--all` con varios fallos (nombre en índice 1, contenido en índice 2, límite en índice 3) informa el primer fallo en orden de índice y no devuelve parciales. |
| .07 | N | Un `--index` de un adjunto con nombre seguro pero no disponible no evalúa el resto de adjuntos no solicitados. |

#### UT-ATC-04 — JSON, caché y `--force` por CLI

Requisitos: AC-12 · Archivo: `tests/test_cli.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Forma exacta de la respuesta de §12.11: `uid` prefijado, `output_dir` absoluto, `count`, ocho campos por adjunto, `warnings: []`, y `content_notice` con el texto exacto justo después de `generated_at`. |
| .02 | P | Primera corrida `cached:false`; segunda sin `--force` `cached:true` con `size_bytes`/`sha256` del archivo; `--force` `cached:false`. |
| .03 | N | Mensaje bloqueado ⇒ `E_ATTACHMENT_BLOCKED` (exit 4), sin archivos, sin caché servida, con el `message`/`hint` de los ejemplos de bloqueo de §12.5. |
| .04 | N | Un fallo de límite o disponibilidad no devuelve resultados parciales. |
| .05 | N | `--all` devuelve `count` = número de adjuntos devueltos. |
| .06 | N | Un fallo de E/S del motor (`E_IO`) o de permisos (`E_PERMISSION`) sale por CLI con su exit 3 y sin archivos; no se convierte en `E_INTERNAL`. |

#### UT-ATC-05 — `[attachments]` y config

Requisitos: AC-14 · Archivo: `tests/test_cli.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | `enabled=false` ⇒ `E_ATTACHMENTS_DISABLED` (2) antes del store; `show` intacto. |
| .02 | N | Rangos inválidos y `max_total_size_mb < max_file_size_mb` ⇒ `E_CONFIG_INVALID`. |
| .03 | P | Valores personalizados válidos se aplican en el comando. |

#### UT-ATC-06 — Disponibilidad y motivos

Requisitos: AC-15 · Archivo: `tests/test_cli.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | `not_local`, `not_downloaded`, `unsupported`, `network` ⇒ `E_ATTACHMENT_UNAVAILABLE` (3) con el `message`/`hint` del motivo. |
| .02 | N | S/MIME/corrupto/ilegible ⇒ `E_ATTACHMENT_UNREADABLE` (3) y nunca `E_USAGE` por “sin adjuntos”. |
| .03 | N | `attachments: none` ⇒ `E_ATTACHMENT_UNAVAILABLE` antes del store. |
| .04 | P | Adjunto vacío (0 bytes) se guarda y devuelve `size_bytes: 0`, `sha256` del vacío. |

#### UT-ATC-07 — Timeout de extracción

Requisitos: AC-D04, AC-D06 (delta `PRD-v2.2.md`) · Archivo: `tests/test_cli.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Extracción cuyo plazo configurado vence (inyectado con `_attachment_timeout`) ⇒ `E_CLIENT_TIMEOUT` (3) con el mensaje y el hint de RF-68, sin reintento, staging limpio y sin archivos nuevos. |
| .02 | N | El timeout no escribe estado ni caché parcial. |

#### UT-ATC-08 — Log de `attachment`

Requisitos: AC-19 · Archivo: `tests/test_cli.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `event=end` de `attachment` con `exit_code`, `count`, `cached`, `bytes` y `duration_ms`. |
| .02 | N | El log no registra uid, `native_id`, `original_name`, `sanitized_name`, rutas, cuentas ni términos. |
| .03 | P | `event=start` conserva `command`, `backend` y `drivers`. |
| .04 | N | Un `attachment` fallido registra `event=error` y **no** emite `event=end`. |

#### UT-ATC-09 — Ayuda y exits

Requisitos: AC-21 · Archivo: `tests/test_cli.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | La ayuda raíz lista `doctor`, `mailboxes`, `search`, `new`, `show`, `attachment` y la línea de exits de §12.7. |
| .02 | P | `attachment --help` coincide con §12.7 (usage, positional, options, examples, notes), ≤ 100 columnas y sin ANSI. |
| .03 | P | La ayuda raíz y las seis ayudas de subcomando (7 invocaciones) pasan `parse_args`. |
| .04 | N | Ningún texto de ayuda dice “cinco comandos”/“five commands”, muestra un uid entero como formato de salida o promete escritura fuera de `~/.mailquery`. |
| .05 | P | `attachment` sin `<uid>` ⇒ `E_USAGE`, exit 2. |

#### UT-ATC-10 — `attachment` con driver externo declarado

Requisitos: AC-07, AC-15 · Archivo: `tests/test_cli.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `attachment <plugin>:<native_id> --index 1` con un plugin declarado `attachments: "local"` devuelve el contrato JSON completo y escribe el archivo en la caché; el uid de salida va prefijado. |
| .02 | P | `--all` con el plugin devuelve todos los adjuntos locales y `count` correcto. |
| .04 | N | Un plugin declara `attachments: "none"` ⇒ `E_ATTACHMENT_UNAVAILABLE` antes del store. |

> `UT-ATC-10.03` (rechazo de `"remote"`) se retiró; lo sustituyen UT-RMT-01 y UT-RMT-02 (§9).

#### UT-RMT-01 — Extracción desde un plugin `"remote"`

Requisitos: AC-D01 (delta `PRD-v2.2.md`) · Archivo: `tests/test_remote_attachments.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Plugin falso `attachments: "remote"`, `network: true`: `attachment <driver>:<id> --index N` devuelve el JSON de §12.11 (con `content_notice`) y escribe el archivo en la caché. |
| .02 | P | `--all` devuelve todos los adjuntos con `count` correcto; bloqueo por nombre y por contenido y límites (`max_file_size_mb`, `max_total_size_mb`, `max_count`) dan el mismo código y texto que con un plugin `"local"` equivalente. |
| .03 | P | Segunda corrida: `cached: true` y el plugin no recibe peticiones de bytes; `--force` las vuelve a pedir. |
| .04 | B | El núcleo no abre conexiones (`socket.socket` parcheado para fallar durante toda la corrida). |
| .05 | P | El manifiesto escrito es igual al de un plugin `"local"` equivalente con los mismos bytes (salvo marcas de tiempo y el nombre del driver). |

#### UT-RMT-02 — Fallo de origen del plugin `"remote"`

Requisitos: AC-D02 (delta `PRD-v2.2.md`) · Archivo: `tests/test_remote_attachments.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | `reason: network` ⇒ `E_ATTACHMENT_UNAVAILABLE`, exit 3, con la plantilla de ese motivo; nunca `unsupported`. |
| .02 | N | `reason: not_local` ⇒ ídem con su plantilla. |
| .03 | B | Staging limpio y ningún archivo nuevo en la caché. |
| .04 | B | `--all` con fallos de red en los adjuntos 2 y 3 ⇒ se informa el 2 (§10, punto 10). |
| .05 | N | `reason: network` lanzado en el segundo bloque (dentro del hilo del corte duro) ⇒ `E_ATTACHMENT_UNAVAILABLE` con su plantilla, no `E_CLIENT_TIMEOUT`. |

#### UT-RMT-03 — Driver `attachments: "none"`

Requisitos: AC-D03 (delta `PRD-v2.2.md`) · Archivo: `tests/test_remote_attachments.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | ⇒ `E_ATTACHMENT_UNAVAILABLE` (`unsupported`, exit 3) antes de abrir el store, con el hint nuevo de RF-67 literal. |

#### UT-RMT-04 — Corte duro en plugins externos

Requisitos: AC-D05 (delta `PRD-v2.2.md`) · Archivo: `tests/test_remote_attachments.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | El plugin se bloquea antes del primer bloque (espera un `threading.Event` que el test no activa hasta el final): con el tope inyectado a 1 s, `E_CLIENT_TIMEOUT` (exit 3) con el mensaje y el hint de RF-68; la espera del núcleo, medida con `time.monotonic()`, cumple `elapsed < tope + 1`. |
| .02 | N | El plugin se bloquea entre dos bloques: ídem. |
| .03 | B | `--all` con los adjuntos 2 y 3 bloqueados: se informa el 2. |
| .04 | B | Staging limpio y sin archivos nuevos; el hilo del plugin se libera al terminar el test (evento) y no queda ningún hilo vivo. |
| .05 | N | Con `timeout_seconds` inyectado mayor que `METADATA_TIMEOUT_SECONDS` (parcheado a 0,05 s), un plugin que tarda más de 0,05 s en crear el flujo no se corta antes del tope del adjunto y la extracción termina con éxito. |
| .06 | B | Plazo ya vencido antes de pedir el siguiente bloque ⇒ `E_CLIENT_TIMEOUT` sin nueva petición al plugin (un solo bloque solicitado); flujo vacío ⇒ sin error; `close()` del iterador que lanza al vencer el plazo ⇒ sigue siendo `E_CLIENT_TIMEOUT`. |

#### UT-RMT-05 — Topes que no cambian y lo que no consume el tope

Requisitos: AC-D04, AC-D06 (delta `PRD-v2.2.md`) · Archivo: `tests/test_remote_attachments.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Con `timeout_seconds = 10` y `= 600`, el tope de metadatos de un plugin sigue siendo `METADATA_TIMEOUT_SECONDS` y el de cada llamada COM sigue siendo `outlook_com.CALL_TIMEOUT_SECONDS`. |
| .02 | P | Apple Mail y Outlook (doble): el tope se comprueba entre bloques y al terminar la llamada (un flujo lento entre bloques con tope inyectado da `E_CLIENT_TIMEOUT`); la creación del flujo ocurre en el hilo principal, no en uno aparte. |
| .03 | B | Un acierto de caché no invoca la factoría del tope; A7 se ejecuta después y no lo consume (con un detector lento simulado y el tope ya vencido, la respuesta es de éxito). |
| .04 | P | `cli` pasa al motor el valor de `[attachments].timeout_seconds` (espía sobre la factoría con `timeout_seconds = 180`). |
| .05 | N | Doble de Outlook con el watchdog COM (`outlook_com.CALL_TIMEOUT_SECONDS` parcheado) vencido antes del tope del adjunto ⇒ `E_CLIENT_TIMEOUT` con el mensaje y el hint de RF-33, no los de RF-68. |

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
| .01 | P | Un adjunto local se materializa con `SaveAsFile`/`GetTemporaryFilePath` en el staging `0700`; el archivo es regular, no symlink, `0600`/ACL del perfil; el núcleo lo lee y lo publica con la validación del motor. |
| .02 | N | La materialización se rechaza si el archivo temporal no está dentro de `tmp/staging` o es un symlink ⇒ `E_ATTACHMENT_UNAVAILABLE` (`unsupported`) antes de publicar, sin código interno. |
| .03 | N | Un adjunto con contenido ejecutable en el archivo materializado ⇒ mensaje bloqueado, archivo temporal borrado, nada publicado. |
| .04 | P | El archivo temporal se borra también cuando la extracción falla o el timeout vence. |
| .05 | N | La lista blanca del proxy solo añade las dos operaciones de materialización; cualquier otra operación sigue dando `E_INTERNAL` (OL-01). |
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

### Outlook sobre el doble

#### OL-01 — Proxy de solo lectura

Archivo: `tests/test_outlook.py`

Cada caso negativo produce `E_INTERNAL` con hint no vacío, sin tocar el fake.

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Invocar `Delete`, `Move`, `Copy`, `Save`, `SaveAs`, `Send`, `Display`, `Close`, `Items.Remove`, `Folders.Add`, `AddressEntry`, `GetExchangeUser` o cualquier miembro fuera de la lista blanca, cada uno. |
| .02 | N | Asignar `UnRead` o cualquier otra propiedad. |
| .03 | N | Nombres dunder y privados. |
| .04 | P | Todo objeto devuelto está envuelto, también en colecciones. |

#### OL-02 — Detección del cliente

Requisitos: RF-28 · Archivo: `tests/test_outlook.py`

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

Archivo: `tests/test_outlook.py`

Fallo inyectado en la primera llamada COM.

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | `E_ACCESSDENIED` ⇒ `E_PERMISSION`, exit 3, hint no vacío. |
| .02 | B | Rechazo transitorio una vez ⇒ éxito tras 100 ms. |
| .03 | N | Rechazo transitorio dos veces ⇒ `E_CLIENT_BUSY`, exit 5, hint no vacío. |
| .04 | N | HRESULT desconocido ⇒ `E_INTERNAL`, hint no vacío. |

#### OL-04 — Timeout

Requisitos: RF-33 · Archivo: `tests/test_outlook.py`

Plazo de 0,2 s, en subprocess con `run_cli.py`.

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | `search` colgado en la primera llamada COM ⇒ `E_CLIENT_TIMEOUT`, exit 3, hint que remite a `doctor`, JSON completo en `stdout`. |
| .02 | N | `new` colgado ⇒ ídem y el estado no se escribe. |
| .03 | N | `doctor` colgado en `outlook` ⇒ `outlook` `ok=false` con `timeout after 30 s: Outlook did not respond (possible security prompt)` literal; `stores`, `readonly_strategy` y la resolución de `config` `not evaluated`; el resto evaluado; exit 0. |
| .04 | N | `doctor` colgado en `stores` ⇒ `stores` con ese texto; resolución de `config` `not evaluated`; el resto evaluado; exit 0. |
| .05 | B | Trabajo de Python entre llamadas más largo que el plazo, sin llamada COM en curso ⇒ sin timeout. |
| .06 | P | El error queda en el log. |

#### OL-05 — Caché de `pywin32`

Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `win32com.__gen_path__` = `<home>/tmp/gen_py` antes de importar `win32com.client`. |
| .02 | N | En Windows real: ningún archivo de caché fuera de `<home>/tmp/gen_py`. |

#### OL-06 — Stores candidatos

Requisitos: RF-29 · Archivo: `tests/test_outlook.py`

Cada caso declara la cuenta y ejecuta `search` y `show`.

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Exchange en caché ⇒ `Exchange (<smtp>)`. |
| .02 | P | IMAP ⇒ `IMAP (<smtp>)`. |
| .03 | P | POP3 sobre PST ⇒ `POP3 (<smtp>)`, no `PST (…)`. |
| .04 | P | EAS ⇒ `EAS (<smtp>)`. |
| .05 | P | PST local ⇒ `PST (<nombre>)`, `email: null`. |
| .06 | P | PST en disco extraíble ⇒ candidato. |

#### OL-07 — Stores excluidos

Requisitos: RF-34 · Archivo: `tests/test_outlook.py`

Cada caso en `mailboxes.excluded_stores` con `label`, `path` y `reason`.

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Compartido ⇒ `shared_mailbox`, `path: null`. |
| .02 | N | Carpetas públicas ⇒ `public_folders`. |
| .03 | N | Exchange en modo Online ⇒ `online_mode`. |
| .04 | N | Otro store de Exchange sin copia local ⇒ `online_mode`. |
| .05 | N | PST en UNC ⇒ `network_path` con la ruta. |
| .06 | N | PST en unidad mapeada ⇒ `network_path`. |
| .07 | N | Cuenta de otro tipo ⇒ `unsupported_account_type`. |
| .08 | N | Store ilegible con nombre ⇒ `unavailable` con su nombre. |
| .09 | N | Store ilegible sin nombre ⇒ `unavailable`, etiqueta `unknown`, `path: null`. |
| .10 | P | Un store `unavailable` no impide leer los demás. |
| .11 | N | El `CallLog` no registra carpetas ni items de stores excluidos. |

#### OL-08 — `account.uuid`

Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Los 16 bytes del `PR_RECORD_KEY` con formato UUID en mayúsculas. |

#### OL-09 — Cuentas declaradas excluidas

Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Declarada y excluida con `path` ⇒ `W_STORE_EXCLUDED: <etiqueta> at <ruta> is excluded: <reason>` en `search`. |
| .02 | N | Sin `path` ⇒ el mismo texto sin ` at <ruta>`. |
| .03 | N | El mismo warning en `show` y `mailboxes`. |
| .04 | B | Todas excluidas ⇒ `count: 0` con `W_STORE_EXCLUDED` y `W_NO_ACCOUNTS`. |

#### OL-10 — INBOX

Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Bandeja en español ⇒ `INBOX`. |
| .02 | P | Subcarpeta de la bandeja ⇒ `INBOX/Facturas`. |
| .03 | P | PST sin bandeja ⇒ solo `mailbox_list`, sin error. |

#### OL-11 — `path`, `name` y `url`

Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Separador `/`. |
| .02 | P | `%` y `/` dentro de un nombre ⇒ `%25` y `%2F`. |
| .03 | P | `name` = último segmento codificado. |
| .04 | P | `url` = `outlook://<uuid>/<path>` con los segmentos decodificados y percent-encoded según RFC 3986, también con caracteres no ASCII. |

#### OL-12 — Carpetas listadas y contadores

Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Carpetas de sincronización y sus subcarpetas ⇒ ocultas, también con nombres en otro idioma. |
| .02 | N | Calendario, contactos, tareas y carpetas de búsqueda ⇒ no se listan. |
| .03 | P | `total`/`unread` = items buscables: la convocatoria cuenta; acuse, tarea y borrado IMAP no. |

#### OL-13 — Referencias a la bandeja

Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `INBOX` y `INBOX/…` en cualquier idioma. |

#### OL-14 — uid y orden

Requisitos: RF-27, RNF-04 · Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | uid = `EntryID` permanente en hex mayúsculas, no el id corto de la tabla. |
| .02 | B | Misma fecha ⇒ desempata por `uid` como string. |

#### OL-15 — Fechas

Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Hora de entrega y de envío en UTC ⇒ ISO 8601 con el offset local, con una zona inyectada distinta de UTC. |
| .02 | B | Cambio de horario. |

#### OL-16 — Direcciones

Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Dirección SMTP del item. |
| .02 | N | DN interno de Exchange ⇒ no se usa. |
| .03 | N | Sin dirección SMTP ⇒ `address: ""` y se conserva `name`. |

#### OL-17 — Dedupe

Requisitos: RF-07 · Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Mismo Message-ID en dos carpetas ⇒ canónico INBOX, `duplicate_count: 2`. |
| .02 | N | Sin Message-ID o vacío ⇒ único. |

#### OL-18 — Items buscables

Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Acuse y tarea ⇒ ignorados en `search`, `new` y `show`. |
| .02 | N | Borrado IMAP ⇒ ídem. |
| .03 | P | Convocatoria y S/MIME ⇒ incluidos. |

#### OL-19 — Marcas y adjuntos

Requisitos: RF-13 · Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Marcado no completado ⇒ `is_flagged=true`. |
| .02 | N | Marcado completado ⇒ `is_flagged=false`. |
| .03 | P | Adjunto visible ⇒ cuenta en `has_attachments` y se lista. |
| .04 | N | Adjunto oculto ⇒ no cuenta ni se lista. |

#### OL-20 — Cuerpo

Requisitos: RF-05, RF-06 · Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Item con `BodyFormat` HTML y el mismo texto en `Body` y `HTMLBody` ⇒ cuerpo del HTML, con la forma de la fila de `search` y de `show` y sus valores. |
| .02 | P | Texto vacío y HTML ⇒ HTML convertido; un item de reunión no tiene `BodyFormat` ni `HTMLBody` (`AttributeError`) ⇒ `Body`. |
| .03 | N | HTML sin texto ⇒ `available=true`, `readable=true`, `snippet: ""` y `W_HTML_NO_TEXT`. |
| .04 | N | Solo cabeceras ⇒ `false/false/false` + `W_BODY_NOT_LOCAL`, sin miembros de descarga. |
| .05 | N | S/MIME cifrado ⇒ `true/false/false` + `W_BODY_UNREADABLE` con su texto; el `CallLog` no registra miembros de cuerpo ni de adjuntos. |
| .06 | N | S/MIME firmado ⇒ ídem con `signed`. |
| .07 | N | Item que no se puede abrir ⇒ `false/false/false` + `W_BODY_UNREADABLE`. |

#### OL-21 — `show`: adjuntos con el item ilegible

Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Con `has_attachments` ⇒ `attachments: []` + `W_ATTACHMENTS_UNAVAILABLE`. |
| .02 | N | Sin adjuntos ⇒ `attachments: []` sin el warning. |

#### OL-22 — `show`: cabeceras

Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Cabeceras de transporte. |
| .02 | P | Correo interno sin cabeceras ⇒ From/To/Cc/Subject/Date/Message-ID sintetizadas. |

#### OL-23 — `show`: resolución del uid

Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Minúsculas ⇒ `E_USAGE` con `invalid uid …: expected an uppercase hexadecimal EntryID`, hint no vacío. |
| .02 | N | uid inválido con `pywin32` ausente ⇒ `E_USAGE` antes de conectar. |
| .03 | N | uid inexistente, también con un `EntryID` que no coincide con ningún store ⇒ `message uid … was not found` con hint que remite a `excluded_stores`. |
| .04 | N | Item que no es correo ⇒ not found. |
| .05 | N | Item en una carpeta oculta ⇒ not found. |
| .06 | N | Store excluido identificado por `PR_RECORD_KEY` ⇒ `E_ACCOUNT_NOT_IN_SCOPE` con el motivo, sin abrir items del store. |
| .07 | P | Cuenta declarada, carpeta fuera de `mailbox_list` ⇒ éxito. |

#### OL-24 — `--text`, `--to` y `--cc` en Windows

Requisitos: RF-17 · Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | `--to x` sin acotar ⇒ `E_UNBOUNDED_SCAN`; el mensaje nombra `--to`; el hint no lista `--to` ni `--cc`. |
| .02 | N | `--text x` sin acotar ⇒ `E_UNBOUNDED_SCAN`; el hint no lista `--to` ni `--cc`. |
| .03 | N | `--text x --to y` ⇒ `--to` no acota; una sola validación y un solo error. |
| .04 | N | `--to x --since 1y` con más candidatos que `max_scan` ⇒ `E_SCAN_TOO_LARGE`. |
| .05 | P | `--to x --since 1d` ⇒ ejecuta; `scan.mode = metadata`; `scan.candidates` = mensajes antes de aplicar `--to`; `scan.messages_read` = items abiertos; solo el mensaje devuelto con cuerpo legible lee sus cabeceras de transporte (1 lectura de `PR_TRANSPORT_MESSAGE_HEADERS`). |
| .06 | P | `--text` acotado ⇒ coincidencias en el cuerpo; `scan.mode = text`; cada candidato cuyo cuerpo se lee lee también sus cabeceras de transporte (3 lecturas, una por candidato legible). |
| .07 | P | `--text x --to y --since 1d` ⇒ `scan.candidates` = mensajes antes de aplicar `--to`; el filtro de destinatarios abre todos los items pero solo el que coincide lee su cuerpo y sus cabeceras de transporte (1 lectura). |

#### OL-25 — `new` en Windows

Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | El estado guarda uids hex. |
| .02 | N | Segunda corrida ⇒ no reemite. |
| .03 | P | Mensaje movido dentro de la ventana ⇒ `new` termina con exit 0 y lo emite con su nuevo uid. |
| .04 | N | Cuenta declarada excluida ⇒ `W_STORE_EXCLUDED` antes de `W_FIRST_RUN`. |

#### OL-26 — `doctor` en Windows

Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | `pywin32` falla ⇒ `outlook`, `stores`, `readonly_strategy` y la resolución de `config` `not evaluated`. |
| .02 | N | Outlook cerrado ⇒ `outlook` `ok=false`, exit 0. |
| .03 | P | Sin bloques y `stores` fallido ⇒ `config` `ok=true` con `0 account block(s) declared; available accounts: unknown (stores failed)`. |
| .04 | N | Cuenta declarada excluida ⇒ `W_STORE_EXCLUDED` en el `detail` de `config`, que sigue con `ok=true`. |

#### OL-27 — `object_model_guard`

Archivo: `tests/test_outlook.py`

Con `registry` y `security_center` inyectados.

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Directiva que pregunta siempre o que deniega ⇒ falla. |
| .02 | P | Directiva que permite ⇒ pasa. |
| .03 | P | Sin directiva y antivirus activo ⇒ pasa. |
| .04 | N | Sin directiva y sin antivirus ⇒ falla. |
| .05 | N | Sin directiva y estado del antivirus no consultable ⇒ `ok=false`, `not evaluated: SecurityCenter2 unavailable`. |
| .06 | N | Con directiva ⇒ el antivirus no se consulta. |

#### OL-28 — Campos neutros

Requisitos: RF-30 · Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `is_aggregate` siempre `false`. |
| .02 | P | `labels_available` siempre `true`. |

#### OL-29 — Log

Requisitos: RNF-07 · Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `backend=outlook`. |
| .02 | P | Estrategia `com_readonly` y versión de Outlook. |
| .03 | N | Sin uids, `EntryID` ni `StoreID`. |

#### OL-30 — Gate de solo lectura de Outlook

Requisitos: RNF-01 · Archivo: `tests/test_outlook.py`

Barrido de los comandos con todos sus flags —incluido `--strip-links` en cada `search`, `new` y `show`, `search --group-by from,month`, `search --count`, y `mailboxes`, `mailboxes --fields total,unread` y `mailboxes --fields name,url`— sobre el fake de Outlook; bloqueante.

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Miembros invocados ⊆ lista blanca. |
| .02 | N | 0 asignaciones. |
| .03 | N | 0 mutaciones. |
| .04 | N | Nunca aparecen errores ni warnings que no aplican al backend de Outlook, ni `E_INTERNAL`. |
| .05 | N | Las corridas de `attachment` escriben solo bajo `<home>` y dejan vacío el staging. |

### Cuerpo y cabeceras del remitente (Apple Mail y Outlook)

#### UT-BOD-01 — Cuerpo en Apple Mail

Requisitos: RF-53 · Archivo: `tests/test_body_sources.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `multipart/alternative` con texto plano y HTML distintos ⇒ `body_text` del HTML (`Factura adjunta.`), también en `BodyRow.body_text`. |
| .02 | P | Solo texto plano ⇒ texto plano. |
| .03 | N | HTML sin texto (solo `<img>`) con texto plano presente ⇒ `""` y `W_HTML_NO_TEXT`; el texto plano no aparece. |
| .04 | P | `multipart/mixed` con una parte `text/plain` y otra `text/html` de cuerpo ⇒ solo el HTML. |
| .05 | P | HTML con un elemento oculto ⇒ `hidden_chars` igual al de `html_body_to_text`; HTML todo oculto ⇒ `""`, `W_HTML_NO_TEXT` y `hidden_chars > 0`. |
| .06 | N | `text/plain` de cuerpo más una parte `text/html` con `Content-Disposition: attachment` ⇒ `body_text` del texto plano; el HTML adjunto no aporta texto. |

#### UT-BOD-02 — Cuerpo en Outlook (doble)

Requisitos: RF-53 · Archivo: `tests/test_body_sources.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `BodyFormat = 2` (`olFormatHTML`) con `Body` y `HTMLBody` distintos ⇒ texto del HTML, en `load_snippet` y en `load_body`. |
| .02 | P | `BodyFormat = 1` (texto plano) y `3` (RTF) ⇒ `Body`, aunque exista `HTMLBody`. |
| .03 | P | Item de reunión sin `BodyFormat` ni `HTMLBody` (`AttributeError`) ⇒ `Body`, sin error. |
| .04 | N | `BodyFormat = 2` con HTML sin texto y `Body` presente ⇒ `""` y `W_HTML_NO_TEXT`. |
| .05 | B | `BodyFormat` se lee por la lista blanca COM (sin violación del proxy de solo lectura, `mutations` y `forbidden` en cero) y no se abre ningún item más que uno por mensaje (`items_opened` y `GetItemFromID` = 1). |
| .06 | N | `HTMLBody` que lanza un error COM (no `AttributeError`), `BodyFormat` que lanza un error COM y `BodyFormat` que devuelve `None` ⇒ `Body`, sin error. |

#### UT-BOD-03 — Cabeceras del remitente en Apple Mail

Requisitos: RF-60, RF-61 · Archivo: `tests/test_body_sources.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Con dos `Authentication-Results` y una `ARC-Authentication-Results`, `authentication_results` es la primera (la de más arriba), en `load_body` y en `parse_emlx_headers`. |
| .02 | P | `Reply-To` se entrega crudo; sin la cabecera, `None`. |
| .03 | P | `load_headers` da las seis cabeceras de `show`, la primera `Authentication-Results` y `Reply-To` sin llamar a la extracción del cuerpo (espía sobre `emlx._extract_body_text`). |
| .04 | B | `parse_emlx_headers` no lee más allá del bloque de cabeceras (archivo con cuerpo de varios MiB: se leen como mucho 256 KiB); archivo ausente, ilegible o que es un directorio ⇒ vacío, `read=False`, sin excepción. |
| .05 | P | Primera `Authentication-Results` plegada con CRLF + tabulador y con `dmarc=fail` en una línea de continuación ⇒ el valor llega desplegado y contiene `dmarc=fail`, igual en `load_body` y en `load_headers`. |
| .06 | B | `parse_emlx_headers`: bloque sin línea vacía antes del tope de 256 KiB (devuelve lo leído hasta el tope, sin excepción), línea de longitud inválida, archivo vacío, sin salto de línea, longitud cero y bloque que no se puede parsear (vacío, `read=False`) y cabeceras con *encoded words* (se decodifican como en `parse_emlx`). |
| .07 | N | `load_headers` con un `.emlx` que no se resuelve, con una carpeta desconocida o con `resolve_path` que lanza ⇒ vacío y `read=False`; con un `.partial.emlx` ⇒ cabeceras leídas del parcial. |

#### UT-BOD-04 — Cabeceras del remitente en Outlook (doble)

Requisitos: RF-60, RF-61 · Archivo: `tests/test_body_sources.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Cabeceras de transporte con dos `Authentication-Results` y `Reply-To` ⇒ la primera y `Reply-To`, tanto en `load_body` como en `load_snippet`. |
| .02 | N | Correo interno sin cabeceras de transporte ⇒ `None` en las dos y `headers` vacías. |
| .03 | N | Item S/MIME: `load_headers` y `load_snippet` no abren el item (`CallLog` sin `GetItemFromID`) y devuelven vacío. |
| .04 | P | `load_headers` abre el item (cuenta en `items_opened`, un `GetItemFromID`) y no accede a `Body`, `HTMLBody` ni `Attachments`. |
| .05 | P | Cabeceras de transporte con la primera `Authentication-Results` plegada (CRLF + tabulador) y `dmarc=fail` en la línea de continuación ⇒ valor desplegado con `dmarc=fail`, en `load_headers` y en los dos cargadores del cuerpo. |
| .06 | N | `load_headers` con `GetItemFromID` que falla, o con la lectura de `PR_TRANSPORT_MESSAGE_HEADERS` que lanza ⇒ vacío y `read=False`, sin excepción. |

#### UT-BOD-05 — Punta a punta por `cli.main`

Requisitos: RF-53, RF-60, RF-61 · Archivo: `tests/test_body_sources.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `search --text <palabra solo del HTML> --since …` encuentra el mensaje; `--text <palabra solo del texto plano>` no lo encuentra (Apple Mail y Outlook). |
| .02 | P | `show` del mismo mensaje da `body_text` del HTML (Apple Mail y Outlook). |
| .03 | P | Con `css_inline` simulado ausente (parcheando `output._css_inline` y el import), `search`, `new` y `show` terminan con exit 0 y convierten el HTML original (la omisión en línea sigue). |

### Punta a punta (`cli.main`)

#### TC-01 — Goldens de Apple Mail

Requisitos: RNF-11 · Archivo: `tests/test_integration.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `doctor` informa todos los chequeos documentados ⇒ golden `doctor`. |
| .02 | P | `mailboxes` con la forma agrupada por cuenta (cada cuenta con `uuid`, `label`, `email`, `declared` y `mailboxes[]`, cada carpeta solo con `path` e `included`) ⇒ golden `mailboxes`; una segunda corrida con `--fields name,url,total,unread` valida nombre, URL y contadores de cada carpeta. |
| .03 | P | `search` por defecto devuelve todos los mensajes distintos con la fila de seis campos ⇒ golden `search_default`; una segunda corrida con `--fields all` valida los campos fuera de la fila y los warnings de cuerpo. |
| .04 | P | `search` con All Mail deduplica al canónico de INBOX con la fila de seis campos ⇒ golden `search_all_mail`; `duplicate_count`, `snippet` y `mailbox` se comprueban con `--fields all`. |
| .05 | P | Primera corrida de `new` emite la ventana `[D - lookback, D]` con la fila de seis campos ⇒ golden `new_first_run`. |
| .06 | P | Corrida con estado sembrado emite los mensajes nuevos con la fila de seis campos y avanza el cursor ⇒ golden `new_seeded`. |
| .07 | P | `show` de un mensaje de texto con adjunto ⇒ golden `show_2714`. |
| .08 | N | `show` con el `.emlx` ausente ⇒ golden `show_83170`. |
| .09 | N | `show` con el `.emlx` corrupto ⇒ golden `show_83180`. |
| .10 | N | `show_smime_encrypted`: S/MIME cifrado con adjuntos en el `Envelope Index` (`extended=True`). |
| .11 | N | `show_not_in_scope_error` (`extended=True`). |

#### TC-02 — Goldens de Outlook

Requisitos: RF-30 · Archivo: `tests/test_integration.py`

Perfil del fake para goldens: una cuenta Exchange en caché con INBOX (un mensaje normal con adjunto, uno solo con cabeceras y uno S/MIME cifrado) y un buzón compartido excluido. Cada caso compara con el golden `outlook/<nombre>`.

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `mailboxes` con la forma agrupada sin contadores ⇒ golden `outlook/mailboxes`; una segunda corrida con `--fields name,url,total,unread` valida `name`, `url` y los contadores (INBOX 3/2). |
| .02 | P | `search` con la fila de seis campos ⇒ golden `outlook/search`; `date_sent` y las señales de contenido se comprueban con `--fields all`. |
| .03 | P | `show` |
| .04 | N | `show_header_only` |
| .05 | N | `show_smime` |
| .06 | P | `new` con la fila de seis campos ⇒ golden `outlook/new_first_run`. |
| .07 | P | `doctor` |

#### TC-03 — Gate de solo lectura de Apple Mail

Requisitos: RNF-01 · Archivo: `tests/test_readonly.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Barrido de todos los comandos con `extended=True`, incluidos la primera corrida de `new` con emisión, `show` fuera de alcance y los S/MIME, `--strip-links` en cada `search`, `new` y `show`, `search --fields all`, `search --group-by from,month`, `search --count`, `new --fields all`, `show <uid> --fields attachments`, `mailboxes` y `mailboxes --fields total,unread` y `--fields name,url`: hashes y `mtime` del store sin cambios y ningún archivo nuevo. |
| .02 | N | Los flujos de `attachment` (éxito, caché, bloqueo, límite, S/MIME y mensaje vacío) dejan el store sin cambios. |

#### TC-04 — Recetas

Archivo: `tests/test_integration.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Cada línea `mailquery …` de `01-new-mail-digest.md` termina con exit 0 en ambos backends; `<uid>` = `messages[0].uid` de `new --peek` (o el que indique la receta). |
| .02 | P | Cada línea de `02-search-invoices.md` termina con exit 0 en ambos backends; cuando use `attachment`, el `<uid>` viene de un mensaje con adjunto conocido (fixture o búsqueda `--has-attachments`), no de `messages[0]` genérico. |
| .03 | N | Las recetas no prometen extracción remota, `--out` ni ejecución de archivos. |

#### TC-05 — Paridad de forma JSON

Archivo: `tests/test_integration.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `search`, `new`, `show` y `mailboxes` tienen el mismo conjunto recursivo de claves en ambos backends. |
| .02 | P | `attachment` de éxito y de error tiene el mismo conjunto de claves en ambos backends (con `attachments: "local"`). |
| .03 | N | El objeto de error sigue siendo `{code, message, hint}` sin campos nuevos. |

#### TC-06 — Packaging

Requisitos: AC-01, AC-18 · Archivo: `tests/test_packaging.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `pyproject.toml` declara la versión vigente (sin bump), el console script y el grupo `mailquery.backends` con los dos backends internos. |
| .02 | P | `mailquery.__version__` coincide con la metadata del paquete; entry points resolubles con metadata inyectada. |
| .03 | P | Las dependencias de ejecución son exactamente `css-inline~=0.23.1` (sin marcador de plataforma) y `pywin32; sys_platform == "win32"`. |

#### TC-07 — Documentación y ayudas

Requisitos: AC-21 · Archivo: `tests/test_integration.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Recorre la ayuda raíz + 6 subcomandos (7 invocaciones) y todas parsean. |
| .02 | P | `attachment --help` coincide con §12.7. |
| .03 | N | Ninguna ayuda/documento dice `cinco comandos`/`five commands`, muestra uid entero o promete escritura fuera de `~/.mailquery`. |
| .04 | N | Ninguna ayuda ni documento muestra un uid entero ni promete escrituras fuera de `~/.mailquery`. |

#### TC-08 — Goldens de adjuntos Apple Mail

Archivo: `tests/test_integration.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `attachment --index 2` ⇒ `attachment_saved.json` (`cached:false`, ruta/tamaño/sha256). |
| .02 | P | Primera corrida que siembra la caché y segunda corrida ⇒ `attachment_cached.json` (`cached:true`, mismo hash); la siembra se documenta en el test. |
| .03 | N | Mensaje con adjunto de nombre hostil ⇒ `attachment_blocked_name.json` (exit 4, sin cambios en caché). |
| .04 | N | Mensaje con contenido ejecutable (`MZ`) ⇒ `attachment_blocked_content.json` (exit 4, sin cambios en caché). |
| .05 | N | `max_file_size_mb` excedido con tamaño conocido ⇒ `attachment_too_large.json` (exit 4). |
| .06 | P | `show` de un mensaje con caché previa ⇒ `show_2714_with_cache.json` con `cached_path` absoluto. |

#### TC-09 — Goldens de adjuntos Outlook

Archivo: `tests/test_outlook.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `attachment_saved.json` (`cached:false`, ruta/tamaño/hash). |
| .02 | P | `attachment_cached.json` (`cached:true`; primera corrida documentada que siembra la caché). |
| .03 | N | `attachment_unavailable.json` (`not_downloaded`, exit 3). |
| .04 | N | `attachment_blocked.json` (contenido ejecutable, exit 4). |
| .05 | P | Los goldens `outlook/show*.json` tienen la forma `attachments[{index, name, cached_path}]`. |

#### TC-10 — Goldens multi-driver

Requisitos: AC-04 · Archivo: `tests/test_integration.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `search` con `apple_mail` y el plugin de prueba declarados ⇒ golden `search_multidriver`: resultados fusionados en orden total con la fila de seis campos. |
| .02 | P | `new` sobre la ventana de primera corrida fusionada de los dos drivers ⇒ golden `new_multidriver` con la fila de seis campos. |

### Empaquetado y documentación

#### DOC-01 — `README.md`

Requisitos: AC-21 · Archivo: `tests/test_integration.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Contiene los seis comandos y ningún texto con “cinco comandos”/“five commands”. |
| .02 | P | Describe el `uid` como string prefijado y la aceptación del uid legado; no hay ejemplos con uid entero. |
| .03 | P | Documenta `[scope."<driver>:<cuenta>"]`, `[attachments]`, `attachment`, `show.attachments`, `doctor driver`, `--version drivers` y los exit codes/errores nuevos. |
| .04 | N | No contiene marcas obsoletas: `five commands`, `baseline` como concepto vigente, `retention_days`, uid entero en JSON, `attachments` solo con `name`, ni presenta `3.0.0` como versión publicada. |
| .05 | P | Los bloques de ejemplo de JSON y comandos coinciden con el contrato implementado (uid string, `cached_path`, `drivers:`). |

#### DOC-02 — `README.es.md`

Requisitos: AC-21 · Archivo: `tests/test_integration.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Misma estructura y mismo conjunto de comandos, flags, rutas y exit codes que `README.md`. |
| .02 | N | No contiene las mismas marcas obsoletas que DOC-01.04. |
| .03 | P | Los ejemplos de uid y de `attachment` usan el formato prefijado. |

#### DOC-03 — Coherencia entre documentos

Requisitos: AC-21 · Archivo: `tests/test_integration.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `README.md`, `README.es.md`, recetas, `SKILL.md`, `config.example.toml` y las ayudas coinciden en comandos, exits, formato de uid y ruta de caché. |
| .02 | N | Ningún documento promete escribir fuera de `~/.mailquery` ni abrir red desde el núcleo. |
| .03 | P | Donde se muestra `--version`, el ejemplo usa `mailquery.__version__` y la forma con `drivers:`; no se anuncia `3.0.0` como publicado. |

#### DOC-04 — `skills/mailquery/SKILL.md`

Requisitos: AC-21 · Archivo: `tests/test_integration.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Tabla de seis comandos con `attachment`; uid string; `show.attachments` con `cached_path`; errores nuevos. |
| .02 | P | Indica que el harness no debe ejecutar ni abrir los archivos recuperados y que el bloqueo es del mensaje completo. |
| .03 | N | No presenta el uid como entero ni omite `attachment`. |

#### DOC-05 — Ayudas del CLI

Requisitos: AC-21 · Archivo: `tests/test_integration.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | La ayuda raíz lista los seis comandos y la línea de exits de §12.7. |
| .02 | P | `attachment --help` coincide con §12.7 (usage, positional, options, examples, notes). |
| .03 | P | La ayuda raíz y las seis ayudas de subcomando (7 invocaciones) pasan `parse_args` (sin invocar el store). |
| .04 | N | Ninguna ayuda menciona cinco comandos ni un formato de uid entero. |

#### DOC-06 — `config.example.toml`

Requisitos: AC-21 · Archivo: `tests/test_integration.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Parsea con el cargador real, esquema cerrado, defaults documentados y `[attachments]` comentada. |
| .02 | P | Incluye un ejemplo de `[scope]` con prefijo y otro sin prefijo, la tabla `[content]` entre las secciones documentadas permitidas y ninguna sección desconocida. |
| .03 | N | No conserva claves de versiones anteriores. |
| .04 | P | El ejemplo contiene el bloque comentado `# [content]` con `# url_display = "neutralize"`; una copia en un temporal con ese bloque descomentado se carga con el cargador real y da `url_display == "neutralize"`. |
| .05 | P | Dentro del bloque comentado `# [attachments]` existe la línea `# timeout_seconds = 60 …`; una copia en un temporal con el bloque descomentado (como en DOC-06.01) da `timeout_seconds == 60` con el cargador real. El ejemplo sigue con todas las secciones comentadas. |

#### DOC-07 — Actualización de seguridad de `css-inline` en los README

Requisitos: AC-H17 (delta `PRD-v2.2.md`) · Archivo: `tests/test_packaging.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `README.md`: dentro de "Install, upgrade and uninstall" hay una subsección "Security update of `css-inline`" con `pipx runpip mailquery show css-inline`, `pipx runpip mailquery install --upgrade "css-inline~=0.23.1"`, `pipx reinstall mailquery`, `pipx runpip mailquery install "css-inline==` y la URL de los avisos. |
| .02 | P | `README.es.md`: lo mismo dentro de "Instalar, actualizar y desinstalar", subsección "Actualización de seguridad de `css-inline`". |
| .03 | P | Los dos README nombran `css-inline` en la introducción, en los requisitos y en las instrucciones de tests, y estas incluyen `coverage run` y `coverage report`. |
| .04 | N | Ningún README conserva "standard library only" / "solo biblioteca estándar". |

#### DOC-08 — Reglas de seguridad

Requisitos: AC-H18 (delta `PRD-v2.2.md`) · Archivo: `tests/test_content_wiring.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | La skill tiene la sección "Security rules" con una aserción por cada punto de comportamiento de RF-66 que le corresponde (1, 3, 5, 6, 8, 12, 13, 14 y 15): no seguir instrucciones del correo; no abrir URLs ni adjuntos sin petición; URLs neutralizadas por defecto y restauradas solo para el usuario; imágenes; triaje con metadatos; el nombre visible del remitente no prueba identidad; el texto de un enlace no es su destino; los siete warnings de F1 nombrados; tratar la salida como texto plano y escaparla antes de insertarla en HTML. |
| .02 | P | `README.md` tiene "Security for harness operators" con la frase literal de RF-66 y el enlace a `docs/security/threat-model.md`; la sección de instalación de la skill enlaza esa sección. |
| .03 | P | `README.es.md` tiene "Seguridad para quien opera el harness" con la frase literal en español, el enlace al anexo y el enlace desde la instalación de la skill. |
| .04 | P | `search --help`, `new --help` y `show --help` describen `--strip-links`; las ayudas de `doctor`, `mailboxes` y `attachment` no la mencionan. |
| .05 | P | La skill describe `content_notice` en "Output contract" y lista `--strip-links` entre las opciones de `search`, `new` y `show`. |
| .06 | P | `README.md` y `README.es.md` describen en su sección de seguridad los seis controles de quien opera el harness (puntos 2, 4, 7, 9, 10 y 11 de RF-66), con una aserción por control en cada idioma. |

#### DOC-09 — Documentación de F2 y A7

Requisitos: AC-H18 (delta `PRD-v2.2.md`), documentación de AC-D01/AC-D06 · Archivo: `tests/test_remote_attachments.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Los dos README documentan `timeout_seconds` (10–600, 60 por defecto), los drivers `"remote"` en `attachment` y `W_ATTACHMENT_ACTIVE_CONTENT`. |
| .02 | P | La skill nombra `W_ATTACHMENT_ACTIVE_CONTENT` en "Security rules", recupera los adjuntos de drivers `"remote"` y ya no dice que no se pueden recuperar. |

#### INS-SMOKE-01 — Instaladores

Archivo: `tests/test_install_scripts.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Sintaxis, `--help`, `--print-config` y `--dry-run` de `install.sh` y `install.ps1` y de `skills/install.*` siguen pasando. |
| .02 | P | La plantilla de configuración documenta `[attachments]` y sigue siendo TOML válida con defaults. |
| .03 | P | Se menciona `pipx inject mailquery <paquete>` para plugins y `mailquery -v` conserva `backend <nativo>`. |

#### PKG-01 — Empaquetado y entry points

Requisitos: AC-01 · Archivo: `tests/test_packaging.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `pyproject.toml` declara el grupo `mailquery.backends` con `apple_mail` y `outlook`. |
| .02 | P | Con el paquete instalado, `importlib.metadata` expone ambos entry points; sin instalación, la metadata inyectada y el fallback estático producen el mismo resultado. El caso instalado se salta con motivo si el paquete no está instalado (CI no lo instala). |
| .03 | P | `version` sigue sincronizada con `mailquery.__version__` y el console script `mailquery` no cambia. |

#### PKG-02 — Empaquetado

Archivo: `tests/test_install_scripts.py`, `tests/test_packaging.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `pyproject.toml` y `__version__` coinciden y siguen en la versión vigente (`2.0.1`, sin bump); grupo `mailquery.backends` con `apple_mail` y `outlook`; console script intacto. |
| .02 | P | Los tests de instaladores construyen `GOOD_VERSION` con `mailquery.__version__` pero como línea completa de `-v` (`mailquery <v> (backend outlook; Python 3.14.0; Windows 10.0.26200 AMD64)`), no solo la versión. |
| .03 | P | `SMOKE-INSTALL.02` acepta la salida de `-v` de la versión actual sin fijar un literal (se deriva de `__version__`). |

#### PKG-03 — Dependencia `css-inline`

Requisitos: AC-H15 (delta `PRD-v2.2.md`) · Archivo: `tests/test_packaging.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | La entrada de `css-inline` es literalmente `css-inline~=0.23.1`: rango de parches `0.23.x` desde `0.23.1`, sin `==`, sin `>=` abierto y sin marcador de plataforma. |
| .02 | N | `pywin32` es la única dependencia con marcador `sys_platform == "win32"`. |
| .03 | P | `[tool.coverage.report].fail_under = 85` y `[tool.coverage.run].branch = true`; `coverage` no está en `[project].dependencies`. |

### SMOKE contra el cliente de correo real

#### SMOKE-ATT-AM — Recuperación real de adjuntos en Apple Mail (macOS)

Archivo: `tests/test_smoke.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `show <uid>` de un mensaje con adjunto local ⇒ exit 0 y `attachments[]` con `index`/`name`. |
| .02 | P | `attachment <uid> --index 1` ⇒ exit 0, archivo `0600` bajo `~/.mailquery/attachments`, `sha256` coincide con el archivo, store sin cambios. |
| .03 | P | Segunda corrida ⇒ `cached:true` (sin umbral de tiempo). |
| .04 | B | Sin mensaje con adjunto local o sin Apple Mail ⇒ skip documentado (no fallo); la clase declara el skip por plataforma. |

#### SMOKE-ATT-OL — Recuperación real de adjuntos en Outlook clásico (Windows)

Archivo: `tests/test_smoke.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `show <uid>` de un mensaje con adjunto local ⇒ `attachments[]` con `index`/`name`. |
| .02 | P | `attachment <uid> --index 1` ⇒ exit 0, archivo bajo `~/.mailquery/attachments`, tamaño/hash coherentes, store y no leídos sin cambios. |
| .03 | P | `attachment` no cambia los contadores de las carpetas incluidas (`mailboxes --fields url,total,unread`) ni el store; la clase se salta por plataforma en `setUpClass` fuera de Windows. |

#### SMOKE-INSTALL — Instalación real con `pipx`

Archivo: `tests/test_smoke.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `pipx install.` con `PIPX_HOME`/`PIPX_BIN_DIR` temporales ⇒ exit 0. |
| .02 | P | `mailquery -v` ⇒ el backend de la plataforma. |
| .03 | P | Con `HOME`/`USERPROFILE` temporales (en macOS, `Library/Mail` y `Library/Accounts` del HOME temporal enlazan a los reales) y la primera cuenta de `mailquery mailboxes` declarada: `mailquery doctor --json` ⇒ todos los chequeos `ok=true`. |
| .04 | N | El `~/.mailquery` real del usuario no cambia. |
| .05 | P | Tras `pipx install .`, `pipx runpip mailquery show css-inline` con el mismo `PIPX_HOME` temporal ⇒ `Version: 0.23.<n>`. |

#### SMOKE-NEW — Comandos de lectura contra el cliente real

Archivo: `tests/test_smoke.py`

Con la instalación y la config de SMOKE-INSTALL.

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `mailboxes` ⇒ exit 0 y JSON del contrato de salida (§12.5): seis claves de primer nivel, cada cuenta con sus `mailboxes[]`, cada carpeta con `path` e `included` y ninguna clave `mailboxes` de primer nivel. |
| .02 | P | `new --peek --fields all` valida la fila completa; `new` valida la fila por defecto de seis campos y el contrato de salida; `cursor` no cambia con `--fields`. |
| .03 | P | `search --since 1w` valida la fila por defecto; la misma consulta con `--fields all` valida la fila completa. |
| .04 | P | `search --text "*e*" --since 1d` valida la fila por defecto y `scan.mode: text`; con `--fields all`, la fila completa. |
| .05 | P | `show <messages[0].uid del search>` ⇒ ídem. |
| .06 | N | `unread` de cada carpeta incluida (`mailboxes --fields url,total,unread`, sobre `accounts[].mailboxes[]`), antes y después ⇒ sin cambios. |
| .07 | P | `doctor` y cada comando anterior dentro del presupuesto de §19 de su plataforma (`search --text` solo si `scan.candidates ≤ 500`). |

## 9. IDs retirados

Estos IDs ya no tienen test y no se reutilizan:

| ID | Qué cubría | Lo sustituye |
|---|---|---|
| UT-CLI-01, UT-CLI-02, UT-CLI-03 | `--version`: formato, sin efectos y combinaciones | UT-PL-03 |
| UT-CLI-06 | Ayudas | UT-ATC-09 |
| UT-CLI-07 | Formato del uid de `show` (uid entero) | UT-ATC-02, UT-ATC-03, UT-UID-02 |
| UT-ST-02.03, .04, .05 y .07; UT-ST-03 | Validación de uids enteros y hexadecimales en `state.json` | UT-ST-06, UT-ST-07 |
| UT-ST-04.02 | `new` con estado corrupto | — |
| TC-05.04, .05 y .06 | Paridad de forma de `mailboxes`, error y `doctor` | TC-05.01 y TC-05.03 |
| TC-06.04 | `requires-python` ≥ 3.11 | — |
| TC-07.05 | Exits en las recetas | — |
| DOC-05.05 | Recorrido de las siete ayudas | DOC-05.03 |
| UT-ATC-10.03 | Un plugin `attachments: "remote"` no podía materializar adjuntos (`unsupported`) | UT-RMT-01, UT-RMT-02, UT-RMT-03 |

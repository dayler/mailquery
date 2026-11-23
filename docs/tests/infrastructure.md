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
Los goldens `doctor` (TC-01.01) y `outlook/doctor` (TC-02.07) llevan `plugins: []` después de
`checks`; sin plugins declarados el campo existe y queda vacío, y cada plugin declarado añade un
elemento con `driver` y `checks[]`.

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

- SMOKE-INSTALL y SMOKE-NEW: instalación con `pipx` y comandos de lectura contra el cliente real. SMOKE-NEW.08–.10 cubren `content_notice` y las opciones de salida, el cuerpo desde el HTML y `doctor --failures` sin plugins; SMOKE-NEW.11, el uid corto de Outlook y `show --show-native-id`.
- SMOKE-ATT-AM (macOS) y SMOKE-ATT-OL (Windows): recuperación real de un adjunto local. No imponen umbrales de tiempo.
- Los presupuestos de rendimiento de §19 se miden en los equipos del dueño (SMOKE-NEW.07): `doctor`, `mailboxes` sin contadores, `search` con la fila mínima, `search --fields snippet`, `new`, `show` y `search --text`; `mailboxes --fields total,unread` se mide de forma informativa, sin aserción. Los resultados y la deuda abierta están en [`PERFORMANCE-BACKLOG.md`](../PERFORMANCE-BACKLOG.md).
- La materialización COM de Outlook (`Attachment.SaveAsFile`) solo se verifica en un equipo Windows real; en CI se usa el doble.

# Documentación y empaquetado

#### DOC-10 — Documentación de la fila y de `--fields`

Requisitos: AC-55, AC-39 · Archivo: `tests/test_fields.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `search --help`, `new --help` y `show --help` describen `--fields` con la lista de su comando. |
| .02 | P | Los dos README documentan la fila por defecto y `--fields` con ejemplos (`--fields snippet`, `--fields all`, `show apple_mail:2714 --fields attachments`). |
| .03 | P | La skill explica la fila por defecto, `new --fields snippet` para resumir el correo nuevo, cuándo usar `new` y cuándo `search --unread`, y la regla de triaje sin contenido (punto 16). |
| .04 | P | `docs/recipes/01-new-mail-digest.md` usa `mailquery new --fields snippet`; todas las líneas `mailquery search` de `02-search-invoices.md` piden con `--fields` los campos que consumen. |

#### DOC-11 — Documentación de `--group-by` y `--count`

Requisitos: AC-55 · Archivo: `tests/test_group_count.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `search --help` describe `--group-by` con sus siete claves y `--count`. |
| .02 | P | Los dos README documentan `--group-by` y `--count` con ejemplos (`domain,month`) y el `hint` de cero resultados. |
| .03 | P | La skill explica `--group-by` y `--count` y que `new` no los admite. |

#### DOC-13 — Documentación de `mailboxes`

Requisitos: AC-59, AC-60 · Archivo: `tests/test_mailboxes.py`

**Tabla: Casos de DOC-13**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Los dos README muestran la salida agrupada (ejemplo del PRD sección 12.5) y `--fields total,unread` para los contadores; ningún README describe un `mailboxes[]` de primer nivel con `account`. |
| .02 | P | La skill usa `mailboxes` sin `--fields` para ver carpetas y `--fields total,unread` solo cuando hacen falta los contadores. |
| .03 | P | `docs/config.example.toml` explica que `mailbox_list` acepta el `path` que muestra `mailboxes` (y el nombre o la URL de `--fields name,url`). |

#### DOC-12 — Diagnóstico sin *preflight*

Requisitos: AC-55, AC-57 · Archivo: `tests/test_doctor.py`

**Tabla: Casos de DOC-12**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `doctor --help` describe `--failures` y el ejemplo `mailquery doctor --json --failures`; la ayuda general muestra `environment and read-only diagnosis`. |
| .02 | N | La skill, los README y la ayuda general no contienen "Preflight once per session", `# 1. preflight` ni `read-only preflight`, ni piden `doctor`/`mailboxes` antes de cada uso. |
| .03 | P | La skill indica `mailquery doctor --json --failures` en los casos de RF-75, `mailboxes` solo para editar la configuración o tras un `search` sin resultados, y su primer ejemplo es un `search`. |
| .04 | P | Los dos README describen `doctor` como verificación tras instalar o actualizar y como diagnóstico de un fallo, con `--failures` y la sección de plugins. |

#### DOC-01 — `README.md`

Requisitos: AC-21 · Archivo: `tests/test_integration.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Contiene los seis comandos y ningún texto con “cinco comandos”/“five commands”. |
| .02 | P | Describe el `uid` como string prefijado y la aceptación del uid legado; no hay ejemplos con uid entero. |
| .03 | P | Documenta `[scope."<driver>:<cuenta>"]`, `[attachments]`, `attachment`, `show.attachments`, `doctor driver`, `--version drivers` y los exit codes/errores nuevos. |
| .04 | N | No contiene marcas obsoletas: `five commands`, `baseline` como concepto vigente, `retention_days`, uid entero en JSON, `attachments` solo con `name`, `preflight`, `list accounts, folders, counters`, `standard library only`, ni presenta `3.0.0` como versión publicada. |
| .05 | P | Los bloques de ejemplo de JSON y comandos coinciden con el contrato implementado (uid string, `cached_path`, `drivers:`). |

#### DOC-02 — `README.es.md`

Requisitos: AC-21 · Archivo: `tests/test_integration.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Misma estructura y mismo conjunto de comandos, flags, rutas y exit codes que `README.md`. |
| .02 | N | No contiene las mismas marcas obsoletas que DOC-01.04, incluidas `solo biblioteca estándar` y `list accounts, folders, counters`. |
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
| .01 | P | La ayuda raíz lista los seis comandos, la línea de exits de §12.7 y la línea `environment and read-only diagnosis` de `doctor`. |
| .02 | P | `attachment --help` coincide con §12.7 (usage, positional, options, examples, notes). |
| .03 | P | La ayuda raíz y las seis ayudas de subcomando (7 invocaciones) pasan `parse_args` (sin invocar el store). |
| .04 | N | Ninguna ayuda menciona cinco comandos, un formato de uid entero, `preflight`, `list accounts, folders, counters` ni `standard library only`. |

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

Requisitos: AC-38 · Archivo: `tests/test_packaging.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `README.md`: dentro de "Install, upgrade and uninstall" hay una subsección "Security update of `css-inline`" con `pipx runpip mailquery show css-inline`, `pipx runpip mailquery install --upgrade "css-inline~=0.23.1"`, `pipx reinstall mailquery`, `pipx runpip mailquery install "css-inline==` y la URL de los avisos. |
| .02 | P | `README.es.md`: lo mismo dentro de "Instalar, actualizar y desinstalar", subsección "Actualización de seguridad de `css-inline`". |
| .03 | P | Los dos README nombran `css-inline` en la introducción, en los requisitos y en las instrucciones de tests, y estas incluyen `coverage run` y `coverage report`. |
| .04 | N | Ningún README conserva "standard library only" / "solo biblioteca estándar". |

#### DOC-08 — Reglas de seguridad

Requisitos: AC-39 · Archivo: `tests/test_content_wiring.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | La skill tiene la sección "Security rules" con una aserción por cada punto de comportamiento de RF-66 que le corresponde (1, 3, 5, 6, 8, 12, 13, 14 y 15): no seguir instrucciones del correo; no abrir URLs ni adjuntos sin petición; URLs neutralizadas por defecto y restauradas solo para el usuario; imágenes; triaje con metadatos; el nombre visible del remitente no prueba identidad; el texto de un enlace no es su destino; los siete warnings de F1 nombrados; tratar la salida como texto plano y escaparla antes de insertarla en HTML. |
| .02 | P | `README.md` tiene "Security for harness operators" con la frase literal de RF-66 y el enlace a `docs/security/threat-model.md`; la sección de instalación de la skill enlaza esa sección. |
| .03 | P | `README.es.md` tiene "Seguridad para quien opera el harness" con la frase literal en español, el enlace al anexo y el enlace desde la instalación de la skill. |
| .04 | P | `search --help`, `new --help` y `show --help` describen `--strip-links`; las ayudas de `doctor`, `mailboxes` y `attachment` no la mencionan. |
| .05 | P | La skill describe `content_notice` en "Output contract" y lista `--strip-links` entre las opciones de `search`, `new` y `show`. |
| .06 | P | `README.md` y `README.es.md` describen en su sección de seguridad los seis controles de quien opera el harness (puntos 2, 4, 7, 9, 10 y 11 de RF-66), con una aserción por control en cada idioma. |

#### DOC-09 — Documentación de F2 y A7

Requisitos: AC-39, documentación de AC-40/AC-45 · Archivo: `tests/test_remote_attachments.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Los dos README documentan `timeout_seconds` (10–600, 60 por defecto), los drivers `"remote"` en `attachment` y `W_ATTACHMENT_ACTIVE_CONTENT`. |
| .02 | P | La skill nombra `W_ATTACHMENT_ACTIVE_CONTENT` en "Security rules", recupera los adjuntos de drivers `"remote"` y ya no dice que no se pueden recuperar. |

#### DOC-14 — Estructura del PRD

Requisitos: — (estructura de la documentación) · Archivo: `tests/test_prd_structure.py`

**Tabla: Casos de DOC-14**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | B | Ningún archivo de `docs/prd/` supera 300 líneas. |
| .02 | P | Cada sección del Índice de la portada tiene un solo encabezado, en el archivo de su prefijo. |
| .03 | P | Los IDs O, CU, RF, RNF, ADR y AC son únicos y sin huecos en su capítulo dueño, y la portada tiene los próximos libres. |
| .04 | P | Toda referencia de sección de los capítulos corresponde a un encabezado. |
| .05 | P | Todo enlace relativo de `docs/prd/` apunta a un archivo existente y no lleva ancla. |
| .06 | P | La portada enlaza a todos los archivos de `docs/prd/`. |
| .07 | P | Toda tabla tiene su línea `**Tabla: …**`. |
| .08 | N | Ningún archivo de `docs/prd/` cita un plan. |
| .09 | P | Todo archivo de `docs/prd/` tiene frontmatter con `aliases` y la etiqueta `prd`. |
| .10 | P | Los términos del glosario están en orden alfabético dentro de cada grupo. |
| .11 | N | Ningún archivo de `docs/prd/` empieza por BOM. |

#### DOC-15 — Estructura de las unidades de cambio

Requisitos: — (estructura de la documentación) · Archivo: `tests/test_changes_structure.py`

**Tabla: Casos de DOC-15**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `docs/changes/` no tiene subcarpetas; los nombres de archivo de las unidades son válidos; las unidades y la plantilla tienen frontmatter con `aliases` y la etiqueta `cambio`, sin BOM. |
| .02 | P | Las unidades y la plantilla tienen título y un valor por campo de la cabecera (Tipo, Base, Fecha, Aprobación, Paquete); en las unidades, cada valor tiene su formato (la versión del paquete, sin sufijo de pre-release) y la clase del paquete es una de las que la tabla "Clases de cambio del paquete" del protocolo admite para el tipo de la unidad; las dos tablas de tipos del protocolo y la plantilla nombran los mismos tipos. |
| .03 | P | Las unidades y la plantilla tienen exactamente las secciones del protocolo, en su orden. |
| .04 | P | El estado de cada unidad tiene una forma válida; un borrador no tiene aprobación y los demás estados tienen quién aprobó y la fecha; una errata nunca está `implementado`; la plantilla es un borrador sin aprobación. |
| .05 | P | La sección "IDs" tiene las líneas "Crea" y "Elimina", con rangos válidos; los borradores solo crean marcadores y las demás unidades no tienen marcadores; en una unidad abierta, los IDs de "Crea" son exactamente los IDs nuevos que la unidad define con un párrafo que empieza por el ID en negrita, los criterios de aceptación en "Criterios de aceptación" y los demás en "Requerimiento", sin contar los que crea una unidad abierta de la que depende; en una unidad abierta sin dependencias abiertas, cada ID de "Elimina" está definido en el PRD; la plantilla tiene las dos líneas; los IDs reservados continúan desde los próximos libres de la portada, sin huecos ni repetidos. |
| .06 | P | "Dependencias" es `Ninguna` o una lista de nombres de unidad; una unidad abierta solo depende de unidades que existen, distintas de ella y sin ciclos. |
| .07 | P | Las unidades y la plantilla tienen contenido en "Requerimiento" y en "Criterios de aceptación", y ninguna línea cita un plan. |
| .08 | P | "Conciliación con el PRD" es `Ninguna`, solo en una unidad de tipo `defecto`, o la tabla "Conciliación con el PRD" con las columnas del protocolo (ID, Contrato, Archivo, Ancla, Qué cambia, Estado), al menos una fila, IDs `RC-01`… sin huecos y contrato y cambio sin vaciar; el estado de cada fila es uno de los que el protocolo admite para el estado de la unidad; en una unidad abierta, cada fila nombra un archivo del PRD entre comillas invertidas y al menos un ancla, y la fila de un archivo `(nuevo)` lleva `—`; en una unidad abierta sin dependencias abiertas, el archivo existe y cada ancla selecciona exactamente una línea suya (un ID, la línea que lo define; un texto, la línea que empieza por él o cuya primera celda empieza por él), y un archivo `(nuevo)` aún no existe. La plantilla trae la tabla con una fila `pendiente`. |
| .09 | P | "Checklist de conciliación" tiene la tabla con sus columnas, IDs `CL-01`… sin huecos, ninguna celda vacía y estados válidos; empieza por los ítems de la tabla "Ítems comunes del checklist de conciliación" del protocolo, en su orden; ningún ítem está `pendiente` en una unidad conciliada. La plantilla lista exactamente los ítems comunes. |
| .10 | P | "Documentos consumidores" es `Ninguno` o una lista con estados válidos, y ninguno está `pendiente` en una unidad implementada o conciliada. |
| .11 | P | Toda tabla del protocolo, de la plantilla y de las unidades tiene su línea `**Tabla: …**`. |
| .12 | P | Unidades de ejemplo válidas de cada forma (aprobada con IDs nuevos y decisiones, que depende de una conciliada que creó el mismo ID en su época; dependiente que define más IDs, dependiente con un ancla en un ID de su dependencia, borrador con marcadores, criterio de aceptación con ID, eliminación de un ID del PRD, filas en distinto estado, ancla de texto y contenido nuevo, archivo nuevo, implementada, sin documentos consumidores, errata, versión de parche, defecto sin conciliación, checklist con ítems propios o que no aplican, y conciliada) no producen ningún problema. |
| .13 | N | Cada defecto de estructura de una unidad de ejemplo lo informa su comprobación. |

#### PKG-01 — Empaquetado y entry points

Requisitos: AC-01 · Archivo: `tests/test_packaging.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `pyproject.toml` declara el grupo `mailquery.backends` con `apple_mail` y `outlook`. |
| .02 | P | Con el paquete instalado, `importlib.metadata` expone ambos entry points; sin instalación, la metadata inyectada y el fallback estático producen el mismo resultado. El caso instalado se salta con motivo si el paquete no está instalado (CI no lo instala). |
| .03 | P | `version` sigue sincronizada con `mailquery.__version__` y el console script `mailquery` no cambia. |

#### PKG-02 — Empaquetado

Requisitos: AC-18, RF-33, PRD §22.3 · Archivo: `tests/test_install_scripts.py`, `tests/test_packaging.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `pyproject.toml` y `__version__` coinciden y siguen en la versión vigente (`2.0.1`, sin bump); grupo `mailquery.backends` con `apple_mail` y `outlook`; console script intacto. |
| .02 | P | Los tests de instaladores construyen `GOOD_VERSION` con `mailquery.__version__` pero como línea completa de `-v` (`mailquery <v> (backend outlook; Python 3.14.0; Windows 10.0.26200 AMD64)`), no solo la versión. |
| .03 | P | `SMOKE-INSTALL.02` acepta la salida de `-v` de la versión actual sin fijar un literal (se deriva de `__version__`). |

#### PKG-03 — Dependencia `css-inline`

Requisitos: AC-36 · Archivo: `tests/test_packaging.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | La entrada de `css-inline` es literalmente `css-inline~=0.23.1`: rango de parches `0.23.x` desde `0.23.1`, sin `==`, sin `>=` abierto y sin marcador de plataforma. |
| .02 | N | `pywin32` es la única dependencia con marcador `sys_platform == "win32"`. |
| .03 | P | `[tool.coverage.report].fail_under = 85` y `[tool.coverage.run].branch = true`; `coverage` no está en `[project].dependencies`. |

#### DOC-16 — Documentos del uid corto de Outlook y de la versión

Requisitos: RF-73, RF-81, RF-83, AC-68 · Archivo: `tests/test_packaging.py`

**Tabla: Casos de DOC-16**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `README.md` y `README.es.md` describen `--show-native-id` como opción de depuración de `show`; `SKILL.md` no la menciona. |
| .02 | N | `README.md`, `README.es.md`, `SKILL.md`, `docs/INTERFACES.md`, `docs/recipes/` y `docs/security/` no contienen los textos obsoletos de CL-06: `expected an uppercase hexadecimal EntryID`, `mailquery show outlook:00000000A1B2C3D4`, "`show` never writes" / "`show` nunca escribe", "EntryID largo" / "long EntryID" como riesgo vigente de Outlook, "EntryID hexadecimal" como uid legado de Windows, ni un uid de ejemplo `outlook:` seguido de hexadecimal en mayúsculas; se admite el marcador `outlook:<EntryID>` solo en la descripción de `--show-native-id`. |
| .03 | P | `pyproject.toml` y `mailquery.__version__` dicen `3.0.0a2`, y los README anuncian `3.0.0a2` (`3.0.0-alpha.2`) sin mencionar `3.0.0a1`. |
| .04 | P | Los dos README describen la carpeta `~/.mailquery/db/` con `cache.db` y dicen que desinstalar no la borra. |

Tests que cambian:

- TC-01.01 y TC-02.07: goldens `doctor` y `outlook/doctor` con `pkg 3.0.0a2` (solo cambia la versión).
- DOC-10, DOC-11, DOC-12 u otros DOC existentes, solo si un texto que comprueban cambia; su expectativa se mantiene salvo lo que la unidad cambia.

Comandos:

- `$PY -B -m unittest discover -s tests -t . -k doc_16 > "$LOG/grupo-doc_16.log" 2>&1`; `-k tc_01_01`, `-k tc_02_07`, `-k doc_1` a log.
- Búsquedas de CL-06 y CL-11 (fuera de `docs/prd/` y de `docs/changes/`), con `git grep -n -F` de cada texto en `README.md`, `README.es.md`, `skills/`, `docs/INTERFACES.md`, `docs/recipes/` y `docs/security/`: `uppercase hexadecimal EntryID`, `outlook:00000000A1B2C3D4`, `` `show` never writes ``, `` `show` nunca escribe ``, `show never writes`, `EntryID largo`, `long EntryID`, `EntryID hexadecimal`, `3.0.0a1`. Resultado en la evidencia; `3.0.0a1` solo puede quedar en un registro histórico, y un resultado que no es un texto obsoleto se justifica allí.
- Suite completa: la de `protocolo.md`.

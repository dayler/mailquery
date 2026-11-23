# Definiciones de tests del plan servidor-mcp

Lo que F0 copia a `docs/tests/` antes de lanzar los milestones: grupos nuevos con todos sus casos `[pendiente]` y casos existentes marcados `[por actualizar]` con su texto nuevo. Los IDs de requisitos y criterios son los reservados al aprobar la unidad. Cada milestone cita los encabezados de sus grupos. Formato y reglas: `docs/tests/TEST-CATALOG.md`.

## 1. Archivos y prefijos

Reglas al copiar:

- Cada grupo se escribe con el formato de `TEST-CATALOG.md`: encabezado `#### <ID> — <título>`, línea `Requisitos: … · Archivo: …` y tabla de casos. La anotación "Milestone M<NN>" de cada grupo de este archivo es solo del plan: no se copia a `docs/tests/`, que no cita planes.
- Cada tabla de casos de un grupo nuevo, y cada tabla de un grupo existente que cambia (UT-ATC-09, DOC-01, DOC-04, DOC-05, DOC-16, TC-01, TC-02, TC-07 y la matriz), lleva encima su título `**Tabla: Casos de <ID>**` (la matriz conserva el suyo).
- Tras insertar, se cuentan las líneas de cada archivo (tope de 300, RP-09).

- `docs/tests/TEST-CATALOG.md`: nueva fila en "Prefijos y archivos de la suite": `UT-MCP` · Servidor MCP por stdio: protocolo, herramientas, argumentos, ejecución de llamadas, log del servidor y rotación · `tests/test_mcp_server.py` · [`mcp-server.md`](mcp-server.md). La fila `SMOKE` no cambia (SMOKE-MCP vive en `tests/test_smoke.py`). La fila `UT-CFG` añade `tests/test_cli.py` (UT-CFG-05.02–.03) y la fila `UT-LOG` añade `tests/test_outlook.py` (UT-LOG-06.02).
- `docs/tests/mcp-server.md` (nuevo, título `# Servidor MCP`): grupos UT-MCP-01 a UT-MCP-12 de la sección 2.
- `docs/tests/cli-config.md`: UT-CFG-05 y UT-CFG-06 detrás de UT-CFG-04; UT-CLI-14 detrás de UT-CLI-13; UT-LOG-05 y UT-LOG-06 detrás de UT-LOG-04 (sección 3).
- `docs/tests/docs-packaging.md`: DOC-17 y DOC-18 detrás de DOC-16 (sección 4); casos `[por actualizar]` de la sección 6.
- `docs/tests/smoke.md`: SMOKE-MCP al final (sección 5).
- `docs/tests/acceptance-matrix.md`: filas AC-71 a AC-78 detrás de AC-70 (sección 7) y fila AC-21 (sección 6).
- `docs/tests/attachments-command.md` y `docs/tests/end-to-end.md`: casos `[por actualizar]` de la sección 6.
- `docs/tests/infrastructure.md`, sección 6: una viñeta "SMOKE-MCP: el servidor MCP instalado con `pipx`, hablado por un cliente JSON-RPC de prueba, contra el cliente real; el plugin de prueba se pone en el `PYTHONPATH` del servidor."

## 2. `docs/tests/mcp-server.md`

Todos los grupos: `Archivo: tests/test_mcp_server.py`. Todos los casos empiezan por `[pendiente]`.

**UT-MCP-01 — Transporte y mensajes JSON-RPC.** Requisitos: RF-84, AC-71. Milestone M02.

- .01 P — Cada respuesta es un único objeto JSON-RPC 2.0 en una línea UTF-8 terminada en `\n`; nada más llega a stdout.
- .02 P — Una línea terminada en `\r\n` se atiende igual que la misma línea terminada en `\n`.
- .03 N — Una línea que no es JSON, o que no es UTF-8 válido ⇒ error `-32700` con `id` `null`.
- .04 N — Una petición sin `method` ⇒ `-32600`; un array vacío ⇒ `-32600` con `id` `null`.
- .05 N — Un método desconocido ⇒ `-32601` con el `id` de la petición.
- .06 P — Un lote con dos peticiones ⇒ un array con sus dos respuestas en orden; un lote solo de notificaciones ⇒ ninguna respuesta; un elemento que no es objeto ⇒ `-32600` dentro del array.
- .07 P — `notifications/initialized`, `notifications/cancelled` y una notificación desconocida ⇒ ninguna respuesta.
- .08 P — `tools/list` antes de `initialize` ⇒ la misma respuesta que después.
- .09 P — Con los flujos que arma la CLI sobre bytes, cada línea escrita termina en `\n` sin `\r` en todas las plataformas.

**UT-MCP-02 — `initialize` y `ping`.** Requisitos: RF-84, AC-71. Milestone M02.

- .01 P — `initialize` ⇒ `serverInfo` `{"name": "mailquery", "version": __version__}` y `capabilities.tools` sin `listChanged`.
- .02 P — Pedida cada una de `2024-11-05`, `2025-03-26`, `2025-06-18` y `2025-11-25` ⇒ `protocolVersion` igual a la pedida.
- .03 B — Pedida una versión no soportada, o ninguna ⇒ `2025-11-25`.
- .04 P — `ping` ⇒ resultado `{}`.
- .05 P — El contenido de `tools/list` y de `tools/call` es el mismo con cualquier versión negociada.

**UT-MCP-03 — Herramientas de `tools/list`.** Requisitos: RF-85, AC-71. Milestone M02.

- .01 P — Exactamente `search`, `new`, `show`, `attachment`, `mailboxes` y `doctor`, en ese orden; ninguna para `mcp` ni para `--version`.
- .02 P — La `description` de cada herramienta es la de su subcomando y la de cada parámetro, el `help` de su opción.
- .03 P — Cada opción larga es un parámetro sin guiones y con `_`: `include_mailbox`, `has_attachments`, `strip_links`, `group_by`, `from`.
- .04 P — Tipos: indicador ⇒ `boolean`; `limit` ⇒ `integer`; `index` de `attachment` ⇒ `integer`; opción repetible o con lista ⇒ `array` de `string`; una opción con `choices` ⇒ `string` con `enum`; el resto ⇒ `string`.
- .05 P — `log_level` está en todas las herramientas, opcional, `string` con el `enum` de `--log-level`.
- .06 N — `doctor` no tiene `json`; `show` no tiene `show_native_id`; ninguna tiene `help`.
- .07 P — `uid` es obligatorio en `show` y `attachment`; todas las herramientas tienen `additionalProperties: false`.
- .08 P — Una opción nueva añadida a un parser de prueba aparece en su herramienta sin otro cambio.

**UT-MCP-04 — Argumentos de la CLI.** Requisitos: RF-85, RF-86, AC-72, AC-73. Milestone M02.

- .01 P — El ejecutor recibe `[<intérprete>, "-P", "-m", "mailquery", …]` con el intérprete del servidor.
- .02 P — `log_level` va antes del comando (`--log-level=debug search …`).
- .03 P — Cada valor va como `--opción=valor`; un `array` da una opción por elemento; `true` da el indicador y `false` lo omite.
- .04 P — `uid` va al final, detrás de `--`.
- .05 P — `doctor` lleva siempre `--json`; con `failures: true`, también `--failures`.
- .06 P — `search` con `{"since": "1w", "unread": true, "fields": ["snippet"]}` ⇒ `search --since=1w --unread --fields=snippet`.
- .07 B — `subject` con un valor que empieza por `-` llega como `--subject=<valor>`.
- .08 P — `attachment` con `index: 2` ⇒ `--index=2` y el `uid` detrás de `--`.

**UT-MCP-05 — Resultado de una llamada.** Requisitos: RF-86, AC-72, AC-74. Milestone M02.

- .01 P — Exit 0 ⇒ un único bloque `text` con la salida estándar sin el salto final e `isError: false`.
- .02 P — Exit distinto de 0 ⇒ el mismo texto e `isError: true`.
- .03 N — Salida vacía, que no es JSON, con dos objetos o con un array ⇒ `E_INTERNAL` con `message` `the command did not write a JSON object`, `hint` ``run `mailquery doctor` and check the mailquery log``, `command` igual a la herramienta e `isError: true`.
- .04 N — Un proceso hijo que no se puede lanzar ⇒ el mismo `E_INTERNAL`.
- .05 P — Tras un `E_INTERNAL`, la llamada siguiente se atiende con normalidad.
- .06 P — El JSON de `E_INTERNAL` tiene las claves, el orden y el formato del JSON de error de la CLI.
- .07 P — El ejecutor real lanza el argv sin shell, con stdin vacío, stderr descartado, el entorno y el directorio de trabajo del servidor y, en Windows, sin ventana de consola (con el lanzamiento de procesos sustituido).

**UT-MCP-06 — Validación previa.** Requisitos: RF-86, AC-73. Milestone M02.

- .01 N — Un parámetro desconocido ⇒ `E_USAGE` con `command` igual a la herramienta, un `hint` que nombra el parámetro e `isError: true`, sin llamar al ejecutor.
- .02 N — Un `integer` con texto, un `boolean` con texto o un `array` con un elemento que no es texto ⇒ el mismo resultado.
- .03 N — `show` o `attachment` sin `uid` ⇒ el mismo resultado.
- .04 N — `show` con `show_native_id` ⇒ el mismo resultado.
- .05 N — Un valor con el carácter NUL ⇒ el mismo resultado.
- .06 B — Un argv que supera el límite de longitud de la plataforma ⇒ el mismo resultado.
- .07 N — `tools/call` con una herramienta que no está en `tools/list` ⇒ error JSON-RPC `-32602`.
- .08 P — El JSON de `E_USAGE` tiene las claves, el orden y el formato del JSON de error de la CLI.

**UT-MCP-07 — Llamadas en serie y cierre.** Requisitos: RF-84, RF-86, AC-74. Milestone M02.

- .01 P — Dos peticiones escritas seguidas ⇒ respuestas en orden, y la segunda ejecución empieza después de que termina la primera.
- .02 P — `ping` y `tools/list` escritos durante una llamada responden después de ella.
- .03 P — Fin de stdin con una llamada en curso ⇒ la llamada se responde y `serve` devuelve 0.
- .04 N — Durante la sesión no se escribe nada en stderr.

**UT-MCP-08 — Dependencias e importaciones.** Requisitos: RF-84, AC-76. Milestone M02.

- .01 P — `mcp_server.py` solo importa módulos de la biblioteca estándar y de `mailquery`.
- .02 P — `[project].dependencies` de `pyproject.toml` es exactamente la lista de la línea base.
- .03 N — Importar `mcp_server` y generar las herramientas no carga entry points ni instancia drivers.

**UT-MCP-09 — Servidor real.** Requisitos: RF-84, RF-86, AC-71, AC-72, AC-74. Milestone M05.

- .01 P — Sin `config.toml`, `mailquery mcp serve` responde a `initialize` y a `tools/list`.
- .02 P — Con un `config.toml` inválido, arranca y responde a `tools/list`; una llamada devuelve `E_CONFIG_INVALID` con `isError: true`; tras corregir el archivo, la llamada siguiente ya no lo devuelve, sin reiniciar.
- .03 P — `search` con `{"since": "bogus"}` ⇒ el mismo JSON que `mailquery search --since=bogus` (salvo `generated_at`) con `isError: true`, también con un `json.py` en el directorio de trabajo del servidor.
- .04 P — Al cerrar stdin con una llamada en curso, el servidor la responde y sale con exit 0; su stderr queda vacío.
- .05 P — Cada línea de la salida estándar del proceso termina en `\n` sin `\r`, también en Windows.
- .06 N — `attachment` con `index` y `all` a la vez ⇒ el mismo JSON `E_USAGE` que la CLI con `--index` y `--all`, con `isError: true`: las reglas entre opciones las valida el proceso hijo.
- .07 P — Dos servidores lanzados a la vez con el mismo HOME responden cada uno a `tools/list` y a una llamada, sin interferir.

**UT-MCP-10 — Plugin que no carga.** Requisitos: RF-84, AC-76. Milestone M05.

- .01 P — Con un plugin instalado cuya carga falla, el servidor responde a `initialize` y a `tools/list`.

**UT-MCP-11 — Log del servidor.** Requisitos: RF-84, RF-88, AC-75. Milestone M05.

- .01 P — El log tiene `event=start command=mcp`, una línea `event=call` por llamada con `tool`, `exit_code` y `duration_ms`, y `event=end` al cerrar stdin.
- .02 N — Ninguna línea del servidor contiene los valores de los parámetros de una llamada.
- .03 P — Entre dos eventos, el archivo de log del servidor no está abierto: se puede renombrar y borrar, también en Windows.
- .04 P — `--log-level` antes de `mcp` fija el nivel del log del servidor; con `[logging].json = true`, los eventos del servidor van a `mailquery.jsonl`; un cambio de `[logging]` durante la sesión no cambia el log del servidor, que lee la tabla una vez al arrancar.
- .05 N — Un fallo al escribir el log del servidor no escribe en stdout ni en stderr y el servidor sigue respondiendo.

**UT-MCP-12 — Rotación con el servidor en marcha.** Requisitos: RF-84, RF-88, AC-78. Milestone M05.

- .01 B — Formato de texto, `max_size_mb = 1` y `mailquery.log` precargado justo por debajo del tope: la llamada siguiente rota sin errores, aparece `mailquery.log.1` y la línea `event=call` está en el `mailquery.log` nuevo.
- .02 B — Lo mismo con `[logging].json = true`, `mailquery.jsonl` y `mailquery.jsonl.1`.

## 3. `docs/tests/cli-config.md`

**UT-CFG-05 — `[logging].json`.** Requisitos: RF-88, AC-77 · Archivo: `tests/test_config.py`, `tests/test_cli.py`. Milestone M04.

- .01 P — Sin la clave ⇒ `json` es `false`; `true` y `false` se cargan como booleanos.
- .02 N — `json = "yes"` ⇒ `E_CONFIG_INVALID` (exit 2), y la ejecución lo registra en `mailquery.log` en texto.
- .03 N — `json = true` con otra clave inválida ⇒ `E_CONFIG_INVALID`, registrado en `mailquery.log` en texto, sin crear `mailquery.jsonl`.

**UT-CFG-06 — Configuración del log del servidor.** Requisitos: RF-84 · Archivo: `tests/test_config.py`. Milestone M04.

- .01 P — `load_logging_config` toma `level`, `max_size_mb` y `json` de `[logging]` aunque el resto del archivo no sea válido.
- .02 B — Archivo ausente, TOML inválido o `[logging]` inválida ⇒ texto, `info` y 10 MB, sin lanzar.

**UT-CLI-14 — Comando `mcp`.** Requisitos: RF-84, RF-87, AC-75 · Archivo: `tests/test_cli.py`. Milestone M05.

- .01 P — `mailquery --help` lista `mcp` con el texto `serve the read commands as MCP tools over stdio`, y su línea `Output:` dice que `mcp serve` habla el protocolo MCP por stdout.
- .02 N — `mailquery mcp` ⇒ `E_USAGE`, exit 2, JSON de error con `"command": "mcp"`.
- .03 N — `mailquery mcp serve extra` ⇒ lo mismo.
- .04 P — `mailquery mcp --help` y `mailquery mcp serve --help` muestran `claude mcp add --scope user mailquery -- mailquery mcp serve` y la entrada genérica `mcpServers`.
- .05 P — `mailquery --log-level debug mcp serve` se acepta.
- .06 P — `cli.main` con `mcp serve` en el mismo proceso, con stdin y stdout sustituidos, responde a `initialize` y devuelve 0 al terminar stdin.

**UT-LOG-05 — Log en JSON.** Requisitos: RF-88, RNF-05, AC-77 · Archivo: `tests/test_logging.py`, `tests/test_cli.py`. Milestone M04.

- .01 P — Sin la clave o con `false`, `search` escribe en `mailquery.log` con el formato de texto y no crea `mailquery.jsonl`; un `mailquery.jsonl` existente y sus rotados no cambian.
- .02 P — Con `true`, escribe solo en `mailquery.jsonl`; un `mailquery.log` existente no cambia.
- .03 P — Cada línea es un objeto con `ts` (ISO 8601 con milisegundos y desfase), `level`, `logger`, `run` y `fields`; `text` solo cuando el evento tiene texto sin forma `clave=valor`.
- .04 P — En `fields`, `exit_code` y `duration_ms` son números, `truncated` es booleano (también un valor `TRUE` o `False` en cualquier combinación de mayúsculas), un valor `-` es `null` y `checks` de `doctor` es texto (`3/5`).
- .05 P — `event=error` lleva su mensaje completo en `fields.message`, como texto también si es numérico, si parece un booleano (`true`) o si tiene espacios.
- .06 N — Con el escenario de UT-LOG-04.02, ninguna línea contiene asuntos, direcciones, uids ni rutas.
- .07 P — Un `E_INTERNAL` lleva su traceback en `traceback`.
- .08 B — Con `level = "warning"`, o con `--log-level warning`, no hay líneas `INFO` en `mailquery.jsonl`.
- .09 P — POSIX: `mailquery.jsonl` y sus rotados tienen permisos 0600.
- .10 B — Con `max_size_mb = 1`, `mailquery.jsonl` rota a `mailquery.jsonl.1` y se conservan 5 rotados; `mailquery.log` y sus rotados no cambian.
- .11 P — La misma ejecución en los dos formatos produce los mismos eventos, en el mismo orden y con los mismos campos.
- .12 N — El formato JSON solo se aplica al logger `mailquery` y sus hijos: un logger de otro nombre, como el de un plugin, no recibe el formateador JSON ni escribe en `mailquery.jsonl`.

**UT-LOG-06 — Ruta del log en los mensajes.** Requisitos: RF-88, AC-75, AC-77 · Archivo: `tests/test_cli.py`, `tests/test_outlook.py`. Milestone M04.

- .01 P — El `hint` de `E_INTERNAL` nombra `mailquery.jsonl` con `[logging].json = true` y `mailquery.log` sin ella.
- .02 P — Los `hint` de Outlook de un error COM interno y de un miembro bloqueado por el proxy de solo lectura nombran el archivo del formato activo.
- .03 P — La ayuda raíz nombra `mailquery.log` y `mailquery.jsonl`.

## 4. `docs/tests/docs-packaging.md`

**DOC-17 — Documentación del servidor MCP.** Requisitos: RF-87, AC-75 · Archivo: `tests/test_packaging.py`. Milestone M05.

- .01 P — `README.md` y `README.es.md` contienen `claude mcp add --scope user mailquery -- mailquery mcp serve`, la entrada `mcpServers` con `"command": "mailquery"` y `"args": ["mcp", "serve"]`, las seis herramientas, la equivalencia de un parámetro con su opción (`include_mailbox` y `--include-mailbox`) y los permisos de la app que lanza el servidor (Acceso total al disco en macOS; misma sesión y nivel de integridad que Outlook en Windows).
- .02 P — `skills/mailquery/SKILL.md` dice que usa las herramientas MCP de `mailquery` si están disponibles y la CLI si no, con las mismas recetas y reglas, y que con MCP el código de salida se deduce de `error.code`.
- .03 N — `README.md`, `README.es.md`, `SKILL.md`, `skills/README.md` y las ayudas no contienen "six commands" ni "seis comandos".

**DOC-18 — Documentación del log en JSON.** Requisitos: RF-88, AC-77 · Archivo: `tests/test_packaging.py`, `tests/test_integration.py`. Milestone M04.

- .01 P — `README.md` y `README.es.md` documentan `[logging].json`, el archivo `mailquery.jsonl` y que cada ejecución escribe solo en el archivo del formato activo.
- .02 P — `docs/config.example.toml` tiene `# json = false` dentro del bloque comentado `[logging]`; una copia con el bloque descomentado se carga con el cargador real y da `json` `false`.

## 5. `docs/tests/smoke.md`

**SMOKE-MCP — Servidor MCP contra el cliente real.** Requisitos: RF-84, RF-86, AC-72, AC-74 · Archivo: `tests/test_smoke.py`. Milestone M07. Con la instalación y la configuración de SMOKE-INSTALL; un cliente JSON-RPC de prueba habla con `mailquery mcp serve` instalado.

- .01 P — `initialize` y `tools/list` ⇒ las seis herramientas.
- .02 P — `search` con `since: "1w"` ⇒ exit 0 en el JSON y filas por defecto; `show` del primer `uid` ⇒ `isError: false`.
- .03 P — `new` dos veces seguidas ⇒ el cursor avanza y la segunda no repite mensajes de la primera.
- .04 P — `attachment` con `index: 1` y `force: true` de un mensaje con adjunto local ⇒ `isError: false` y el archivo bajo `~/.mailquery/attachments` del HOME temporal; se salta con motivo si no hay adjunto local.
- .05 N — macOS: con la app que lanza el servidor sin Acceso total al disco ⇒ `E_PERMISSION`; Windows: con Outlook cerrado ⇒ `E_OUTLOOK_NOT_RUNNING`. Se salta con motivo si no se puede preparar la condición.
- .06 P — Con un plugin declarado junto al driver nativo ⇒ resultados de los dos drivers en `search`; con un plugin que falla ⇒ `E_PLUGIN_FAILED`. El plugin de prueba va en el `PYTHONPATH` del servidor, con su `dist-info`.
- .07 N — Los contadores de no leídos de las carpetas incluidas no cambian.

## 6. Casos existentes `[por actualizar]`

- `attachments-command.md`, UT-ATC-09: .01 "La ayuda raíz lista `doctor`, `mailboxes`, `search`, `new`, `show`, `attachment`, `mcp` y la línea de exits de §12.7."; .03 "La ayuda raíz, las siete ayudas de subcomando y `mcp serve --help` (9 invocaciones) pasan `parse_args`."; .04 "Ningún texto de ayuda dice “cinco comandos”/“five commands” ni “seis comandos”/“six commands”, muestra un uid entero como formato de salida o promete escritura fuera de `~/.mailquery`." Milestone M05.
- `docs-packaging.md`: DOC-01.01 "Contiene los siete comandos y ningún texto con “cinco comandos”/“five commands” ni “seis comandos”/“six commands”."; DOC-04.01 "Tabla de comandos con `attachment` y el uso de las herramientas MCP; uid string; `show.attachments` con `cached_path`; errores nuevos."; DOC-05.01 "La ayuda raíz lista los siete comandos, la línea de exits de §12.7 y la línea `environment and read-only diagnosis` de `doctor`."; DOC-05.03 "La ayuda raíz, las siete ayudas de subcomando y `mcp serve --help` (9 invocaciones) pasan `parse_args` (sin invocar el store)." Milestone M05.
- `docs-packaging.md`, DOC-16.03: "`pyproject.toml` y `mailquery.__version__` dicen `3.0.0a3`, y los README anuncian `3.0.0a3` (`3.0.0-alpha.3`) sin mencionar `3.0.0a2` ni `3.0.0a1`." Milestone M03.
- `end-to-end.md`, TC-01.01 y TC-02.07: "El golden `doctor` (`outlook/doctor`) cambia a `pkg 3.0.0a3` (solo la versión)." Milestone M03.
- `end-to-end.md`, TC-07.01: "Recorre la ayuda raíz + 7 subcomandos y `mcp serve --help` (9 invocaciones) y todas parsean." Milestone M05.
- `acceptance-matrix.md`, fila AC-21: "Ayuda raíz con siete comandos, ayuda de `attachment` y línea de exits"; casos `UT-ATC-09, UT-CLI-14, DOC-01 a DOC-06, DOC-17, TC-07`. Milestone M05.

## 7. Filas nuevas de `acceptance-matrix.md`

**Tabla: Filas nuevas de la matriz de criterios**

| Criterio | Qué exige | Casos | Goldens |
|---|---|---|---|
| AC-71 | `initialize`, versiones, `ping`, herramientas y esquemas, solo JSON-RPC en stdout, errores JSON-RPC, lotes y fin de línea | UT-MCP-01, UT-MCP-02, UT-MCP-03, UT-MCP-09.05 | — |
| AC-72 | argv equivalente a la CLI, resultado e `isError`, ejecutor real con `json.py` en el cwd | UT-MCP-04, UT-MCP-05, UT-MCP-09.03, SMOKE-MCP | — |
| AC-73 | Validación previa sin proceso hijo y `-32602` | UT-MCP-04.07, UT-MCP-06 | — |
| AC-74 | Arranque sin config, `E_INTERNAL` recuperable, config corregida sin reiniciar, serie, cierre de stdin, stderr vacío | UT-MCP-05, UT-MCP-07, UT-MCP-09, SMOKE-MCP | — |
| AC-75 | Ayudas, `E_USAGE` de `mcp`, README, skill y log del servidor | UT-CLI-14, UT-LOG-06.03, DOC-17, UT-MCP-11 | — |
| AC-76 | Sin dependencias nuevas, importaciones y plugin que no carga | UT-MCP-08, UT-MCP-10 | — |
| AC-77 | Log JSON, `hint` con el archivo activo y errores de configuración en texto | UT-LOG-05, UT-LOG-06, UT-CFG-05, DOC-18 | — |
| AC-78 | Rotación con el servidor en marcha en los dos formatos | UT-MCP-12 | — |

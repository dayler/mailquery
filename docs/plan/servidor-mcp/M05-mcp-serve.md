# M05 — Comando `mcp serve`, ayuda, README y skill

- **Unidad:** `docs/changes/servidor-mcp.md` (contribuye y no la completa sola).
- **Oleada / lote:** 3 / 2. **Rama del lote:** `feature/servidor-mcp-lote-2`. **Rama del milestone:** `feature/servidor-mcp-m05`, creada desde el tip de la rama del lote.
- **Commit base:** `ce19b37` (tip de `feature/servidor-mcp-lote-1` con M01–M04). **Línea base de la suite:** la del lote; los fallos conocidos son los SMOKE del entorno local.
- **Depende de:** M02 (`mcp_server.py`: `serve`, `tool_definitions`, `build_argv`, ejecutor real), M03 (versión `3.0.0a3` en el paquete y en los README), M04 (`load_logging_config`, `setup_logging(…, json=…)`, archivo activo). **Lo usan:** M06 (documentos técnicos), M07 (SMOKE).
- **ACs:** AC-72 (ejecutor real), AC-74 (proceso real), AC-75 (todo salvo la línea de logs de la ayuda, hecha en M04), AC-76 (plugin que no carga), AC-78; AC-71 (fin de línea del proceso real en Windows).

## Objetivo

Que `mailquery mcp serve` arranque el servidor de M02 con su propio log, que la ayuda, los README y la skill lo documenten, y que las pruebas con procesos reales cubran el arranque, el ejecutor real, el log del servidor y la rotación.

## Alcance

- `cli.py`: subcomando `mcp` con el subcomando obligatorio `serve` (DP-06); `mcp` en `COMMANDS`; despacho de `mcp serve` antes de tocar la configuración completa, el store o los drivers; texto de `mcp` en la ayuda raíz; línea `Output:` de la ayuda raíz; epílogos de `mcp --help` y `mcp serve --help` con el registro de Claude Code y la entrada genérica (RF-87); las ayudas de `mcp` y `mcp serve` tienen las secciones `Examples:`, `Options:` y `Notes:` como las demás, y sus ejemplos se pueden analizar con el parser (DP-18); el docstring del módulo (línea 6) deja de decir "six commands".
- Arranque del servidor: `load_logging_config(home)`, nivel con `--log-level` antes de `mcp`, log del servidor con el manejador de DP-07, `event=start command=mcp`, `serve` con los flujos de DP-10 y el ejecutor real, `event=end`, exit 0. Un fallo del log no impide arrancar ni escribe en stdout o stderr.
- `logging_setup.py`: configuración del log del servidor que abre y cierra el archivo en cada evento (DP-07), en texto o en JSON.
- Ajustes de `mcp_server.py` que la integración haga necesarios (por ejemplo, el logger del evento `event=call`), sin cambiar su interfaz.
- Tests con procesos reales: UT-MCP-09 a UT-MCP-12; UT-CLI-14 (con una prueba en proceso del despacho, UT-CLI-14.06, para que la cobertura de `cli.py` mida el código nuevo); DOC-17; casos `[por actualizar]` de DP-18, incluido TC-07.01.
- Documentación: los dos README, `skills/mailquery/SKILL.md` y `skills/README.md` (incluida su línea 73, que hoy dice "the six commands").

## Fuera de alcance

- `docs/INTERFACES.md`, `docs/security/threat-model.md`, `docs/ROADMAP.md` y `docs/recipes/`: M06.
- Los SMOKE contra el cliente real: M07.
- El PRD y `docs/tests/`.

## Alcance de escritura

- `src/mailquery/cli.py`, `src/mailquery/mcp_server.py`, `src/mailquery/logging_setup.py`.
- `tests/test_mcp_server.py`, `tests/test_cli.py`, `tests/test_integration.py`, `tests/test_packaging.py`.
- `README.md`, `README.es.md`, `skills/mailquery/SKILL.md`, `skills/README.md`.
- `docs/plan/servidor-mcp/M05-mcp-serve.md`, `docs/plan/servidor-mcp/work/M05-handoff.md`, `docs/plan/servidor-mcp/work/M05-propuestas.md`.

## Especificación

Rangos de `docs/changes/servidor-mcp.md` en el commit de la unidad aprobada (F0 anota aquí el commit; si las líneas se movieron, busca el encabezado):

- `### Solución elegida`, líneas 26–33, y `### Por qué un proceso hijo por llamada`, líneas 35–41.
- `**RF-84. Servidor MCP por stdio.**`, líneas 91–111.
- `**RF-86. Ejecución de una llamada.**`, líneas 136–152.
- `**RF-87. Registro en el harness y documentación.**`, líneas 154–166.
- `**RF-88. Log en formato JSON.**`, condición "Alcance" (línea 189).
- `### Riesgos`, líneas 291–301 (para la sección de permisos y problemas de los README).
- `## Criterios de aceptación`, AC-71, AC-72, AC-74, AC-75, AC-76 y AC-78, líneas 309–323.

Casos de test: `#### UT-MCP-09` a `#### UT-MCP-12` de `docs/tests/mcp-server.md`; `#### UT-CLI-14` de `docs/tests/cli-config.md`; `#### DOC-17` y los casos `[por actualizar]` de DOC-01, DOC-04 y DOC-05 de `docs/tests/docs-packaging.md`; `#### UT-ATC-09` de `docs/tests/attachments-command.md`; `#### TC-07` de `docs/tests/end-to-end.md` (caso .01 `[por actualizar]`).

## Puntos de entrada en el código

En `f868036` más M01–M04; si la línea se movió, búscala por el nombre:

- `src/mailquery/cli.py`: `COMMANDS` (84), `_ROOT_EPILOG` (122; línea `Output:` en 133), `build_parser` (381; subparsers en 407), `_main` (685; despacho por comando desde 710), `_guess_command` (2665).
- `src/mailquery/mcp_server.py` (de M02): `serve`, `tool_definitions`, el ejecutor real.
- `src/mailquery/logging_setup.py`: `setup_logging`, `log_event`, el nombre del archivo activo (de M04).
- `src/mailquery/config.py`: `load_logging_config` (de M04).
- `src/mailquery/output.py`: `configure_streams` (961).
- `tests/test_cli.py`: `ALL_COMMANDS` (249), UT-ATC-09 (270 y siguientes), lanzamiento de la CLI por subproceso con `PYTHONPATH` (1836).
- `tests/test_integration.py`: `COMMANDS` (1833), `_STALE_TEXT_PATTERNS` (1865), DOC-01 a DOC-05 (1931–2177), `test_tc_07_01_root_and_six_helps_parse` (2269).
- `tests/test_cli.py`: comprobación de las secciones y los ejemplos de cada ayuda (324–372), que usa `ALL_COMMANDS` y `expected_flags`.
- `src/mailquery/cli.py`: docstring del módulo (1–7).
- `tests/test_outlook.py`: plugin falso instalado con un `dist-info` en `PYTHONPATH` (1170), modelo de UT-MCP-10.
- `README.md`: "Skill for AI harnesses" (155), "Commands" (362), "Permissions" (954), "Troubleshooting" (982). `README.es.md`: los mismos bloques.
- `skills/mailquery/SKILL.md`: "Before using it" (13), "Commands" (65), "Rules for the agent" (175). `skills/README.md`: "Requirements for the skill to work" (58).

## Refactorizaciones previas

Ninguna.

## Decisiones aplicables

- **DP-06. Parser del comando `mcp` (M05).** `mcp` es un subcomando con subcomandos obligatorios; el único es `serve`, sin opciones propias. `cli.COMMANDS` incluye `mcp`, así `mailquery mcp` y `mailquery mcp serve extra` dan `E_USAGE` con `"command": "mcp"`. `tool_definitions` toma solo las seis herramientas, en el orden fijo de RF-85, aunque el parser tenga `mcp`.
- **DP-07. Log del servidor sin archivo abierto entre eventos (M05).** El servidor configura su log con un manejador que abre el archivo, escribe el evento, comprueba la rotación y lo cierra en cada evento; los procesos hijo usan el manejador de siempre. Un fallo al escribir no sale por stdout ni por stderr (el manejador no llama a `handleError` del módulo `logging` con salida a stderr).
- **DP-09. Ejecutor real (M02 lo implementa, M05 lo prueba con procesos reales).** `serve` arma el argv completo (el intérprete del servidor, `-P -m mailquery` y los argumentos de `build_argv`) y se lo pasa a `ToolRunner.run`; así el ejecutor sustituido de los tests registra también `-P -m mailquery`. El ejecutor real lanza ese argv sin shell, con stdin vacío, stdout capturado, stderr descartado, el entorno y el directorio de trabajo del servidor y, en Windows, sin ventana de consola; lee stdout como UTF-8 y mide `duration_ms`. La salida es válida si, sin el salto final, es exactamente un objeto JSON.
- **DP-10. Flujos del servidor (M02 y M05).** `serve(stdin, stdout, *, runner)` recibe flujos de texto, como dice la unidad. La CLI se los pasa en UTF-8 sobre los bytes de stdin y stdout: la lectura no traduce los finales de línea, la escritura usa siempre LF y vuelca tras cada mensaje. `serve` quita el final de línea (CR LF o LF) de cada línea leída. Cada mensaje del protocolo se escribe en una sola línea: JSON compacto, sin sangría ni saltos de línea, sin escapar los caracteres no ASCII, seguido de LF. Una línea que no se puede decodificar como UTF-8 recibe `-32700`. El JSON de la CLI que va dentro del bloque `text` de un resultado (la salida del proceso hijo, o el `E_USAGE` y el `E_INTERNAL` que arma el servidor con `to_payload` y `output.dumps_json`) conserva el formato de la CLI, con su sangría: es un texto dentro del mensaje, no el mensaje. El servidor no usa ninguna función que escriba directamente en `sys.stdout` (por ejemplo, `output.write_json`); escribe solo en el flujo que recibe.
- **DP-13. Importaciones (M02 y M05).** `mcp_server.py` importa `build_parser` de `mailquery.cli` dentro de la función que lo necesita, y `cli.py` importa `mailquery.mcp_server` solo al despachar `mcp serve`, para que no haya ciclo de importación. Ni el uno ni el otro cargan entry points ni instancian drivers al importarse.
- **DP-17. Documentación con su funcionalidad.** Cada milestone actualiza la documentación de lo que entrega, para que ninguno cierre con deuda de documentación: M03 las menciones de la versión, M04 el log JSON en los README y `config.example.toml`, M05 el registro, las herramientas y los permisos en los README, la ayuda y la skill, M06 los documentos técnicos.
- **DP-18. Tests que recorren `cli.COMMANDS`.** DOC-01.01, DOC-02.01, DOC-03.01, DOC-04.01, DOC-05.01, DOC-05.03, TC-07.01 y UT-ATC-09 recorren o cuentan `cli.COMMANDS`, y UT-ATC-09.03 exige `Examples:`, `Options:` y `Notes:` en la ayuda de cada comando de `ALL_COMMANDS`. M05 añade `mcp` a `COMMANDS` y en el mismo milestone pone al día esos tests, las ayudas de `mcp` y `mcp serve` (con esas secciones y ejemplos que se pueden analizar), los README y la skill, para no cerrar con la suite roja.
- **DP-19. Partición prevista de M05.** Si M05 alcanza `relaunch-split`, se parte en M05a (parser `mcp` sin tocar `COMMANDS`, despacho, ayudas de `mcp` y `mcp serve` sin ejemplo nuevo en la ayuda raíz, log del servidor, UT-CLI-14.01, .04, .05 y .06, UT-MCP-09 a UT-MCP-12) y M05b (`COMMANDS` y `ALL_COMMANDS` con `mcp`, ejemplo de la ayuda raíz, UT-CLI-14.02 y .03, README, skill, DOC-17 y los tests de DP-18), en ese orden y en el mismo worktree.
- **DP-20. AC-75 en la documentación.** Los DOC de AC-75 comprueban la presencia de la orden de registro, la entrada genérica, las herramientas, la equivalencia y los permisos. La claridad del texto la revisa el orquestador al cerrar M05 y la anota en `evidence/M05.md`.
- **DP-04. Archivo activo en los mensajes (M04).** `logging_setup` expone el nombre del archivo activo del proceso (`mailquery.log` o `mailquery.jsonl`, según la última configuración aplicada, y `mailquery.log` antes de configurar). Los `hint` que nombran el log (el de `E_INTERNAL` de `cli.py`, `HINT_INTERNAL` y `HINT_READONLY` de `backends/outlook_com.py`) se calculan al crear el error, no en la importación del módulo.
- **DP-05. Configuración del log del servidor (M04 la crea, M05 la usa).** `config.load_logging_config(home: Path) -> LoggingConfig` lee de `config.toml` solo la tabla `[logging]`, la valida con las reglas de `_parse_logging` y nunca lanza: si el archivo falta, no es TOML válido o `[logging]` no es válida, devuelve `LoggingConfig()` (texto, `info`, 10 MB). `LoggingConfig` gana el campo `json: bool = False`.
- **DP-23. Llamada del proceso hijo en las pruebas con procesos reales (M05).** Las pruebas con el servidor real usan una llamada cuyo proceso hijo configura el log, registra un evento y termina rápido sin tocar el cliente de correo ni la red: `attachment` con `all: true` y un `uid` con el formato del driver nativo de la plataforma (`apple_mail:<entero>` en Linux y macOS; `outlook:` más un id corto con formato válido en Windows), con `enabled = false` escrito de forma explícita en `[attachments]` del `config.toml` temporal (el valor por defecto es `true`). Esa llamada falla con `E_ATTACHMENTS_DISABLED` después de configurar el log y antes de abrir drivers, y registra `event=error`. La usan UT-MCP-09.01, .02 (tras corregir el archivo), .04 y .07, UT-MCP-10, UT-MCP-11 y UT-MCP-12. Dos excepciones: UT-MCP-09.03 usa `search` con `since: "bogus"`, que abre el driver nativo en solo lectura antes de validar `--since`, y solo afirma que el JSON es igual al de la CLI (salvo `generated_at`) y que `isError` es `true`, sea cual sea el error del entorno; UT-MCP-09.06 usa `attachment` con `index` y `all`, que falla con `E_USAGE` antes de crear el home. No se usa `doctor`, que intentaría el cliente real. El subagente confirma en el código que la llamada cumple esto y, si no, elige otra con las mismas propiedades y la anota.

Margen tuyo: la redacción de los epílogos de ayuda (en inglés, ≤ 100 columnas, sin ANSI, como el resto de ayudas) y de las secciones de los README y la skill. Anótalo en `work/M05-propuestas.md`.

## Fases

**Tabla: Fases de M05**

| Fase | Tareas | Estado |
|---|---|---|
| 1 | Parser `mcp` / `serve`, despacho, ayudas (raíz, `Output:`, `mcp --help`, `mcp serve --help`), sin añadir todavía un ejemplo `mailquery mcp serve` a la ayuda raíz (UT-ATC-09.03 exige que cada ejemplo sea de un comando de `ALL_COMMANDS`; el ejemplo entra en la fase 4); UT-CLI-14.01, .04, .05 y .06 | 🟢 |
| 2 | Log del servidor (DP-07), `event=start`/`event=end`, nivel y formato; UT-MCP-11 | 🟢 |
| 3 | Pruebas con procesos reales: UT-MCP-09, UT-MCP-10, UT-MCP-12 (en la matriz de CI de macOS y Windows) | 🟢 |
| 4 | `COMMANDS` y `ALL_COMMANDS` con `mcp`, y el ejemplo de la ayuda raíz; UT-CLI-14.02 y .03 (necesitan `mcp` en `COMMANDS`); tests de DP-18; README (los dos, mismo contenido, mismo commit): registro de Claude Code y genérico, herramientas, equivalencia parámetro-opción, permisos de la app que lanza el servidor, fila de problemas; `SKILL.md` y `skills/README.md`; DOC-17 | 🟢 |
| 5 | Suite completa, cobertura de `cli.py`, `mcp_server.py` y `logging_setup.py`, evidencia cruda y propuestas | 🟢 |

## Tests

- Grupos nuevos (casos `[pendiente]`): UT-MCP-09 a UT-MCP-12 en `tests/test_mcp_server.py`; UT-CLI-14 en `tests/test_cli.py`; DOC-17 en `tests/test_packaging.py`.
- Casos `[por actualizar]`: UT-ATC-09.01, .03 y .04 (`tests/test_cli.py`); DOC-01.01, DOC-04.01, DOC-05.01, DOC-05.03 y TC-07.01 (`tests/test_integration.py`); los métodos que llevan "six" o "seven" en el nombre se renombran con el número nuevo.
- Procesos reales: el servidor bajo prueba se lanza con el intérprete de los tests y las opciones `-B -P -m mailquery mcp serve`, `PYTHONPATH` con `src`, `HOME` y `USERPROFILE` temporales, y tope de 120 s por subproceso. `-P` es obligatorio también para el servidor: sin él, `-m` pone el directorio de trabajo en la ruta de módulos y el `json.py` de UT-MCP-09.03 rompería el propio servidor antes de lanzar ningún hijo. UT-MCP-09.03 compara con `search --since=bogus` lanzado igual (con `-P`), normalizando `generated_at`, y repite con un `json.py` que lanza una excepción en el directorio de trabajo del servidor. UT-MCP-09.06 usa `attachment` con `index` y `all` a la vez. UT-MCP-09.07 lanza dos servidores a la vez con el mismo HOME temporal. UT-MCP-10 crea un `dist-info` con un entry point `mailquery.backends` que falla al importarse, como `tests/test_outlook.py`. Las llamadas de los procesos hijo siguen DP-23. UT-MCP-12 precarga el archivo activo hasta `1 MiB − 64` bytes, para que la primera línea del proceso hijo (unos 155 bytes en texto) provoque la rotación en el hijo y no en el servidor, y comprueba que la línea `event=error` del hijo y la `event=call` del servidor están en el archivo activo nuevo.
- UT-MCP-11.03 y .05 se prueban en proceso (renombrar el archivo entre dos eventos; directorio de logs sin permiso de escritura o manejador que falla). UT-CLI-14.06 llama a `cli.main` en proceso con flujos sustituidos.
- Guardia de textos obsoletos: `_STALE_TEXT_PATTERNS` de `tests/test_integration.py` (línea 1865) rechaza en README, skill y ayudas, entre otros, "standard library only", "solo biblioteca estándar", "baseline" y "preflight". Para decir que el servidor no añade dependencias, usa otra redacción (por ejemplo, "no new dependencies" / "sin dependencias nuevas").
- Comandos: `python -B -m unittest discover -s tests -t . -k ut_mcp`, `-k ut_cli_14`, `-k ut_atc_09`, `-k doc_0`, `-k doc_17`, `-k tc_07` y la suite completa.

## Documentación

- `README.md` y `README.es.md` (mismo contenido, mismo commit): sección nueva "MCP server" / "Servidor MCP" con `claude mcp add --scope user mailquery -- mailquery mcp serve`, la entrada `mcpServers`, las seis herramientas, la equivalencia de parámetros y opciones con el ejemplo de RF-85, la ejecución por proceso hijo, el log del servidor y la depuración sin harness (`initialize` y `tools/list` escritos en una terminal); `mcp serve` en la lista de comandos; en "Permissions" / "Permisos", que el Acceso total al disco y la sesión de Outlook valen para la app que lanza el servidor; fila de problemas para `E_PERMISSION` desde el harness. Ningún "six commands" / "seis comandos".
- `skills/mailquery/SKILL.md`: si las herramientas MCP de `mailquery` están disponibles, las usa; si no, la CLI; mismas recetas, reglas de seguridad y lectura de errores; con MCP, el código de salida se deduce de `error.code`.
- `skills/README.md`: el registro como servidor MCP es opcional y complementa la skill.
- Ayudas de la CLI: raíz, `mcp --help`, `mcp serve --help`.

## Actualizaciones de la unidad

Propones al orquestador, en `work/M05-propuestas.md`:

- A `implementado`: RC-02, RC-03, RC-04, RC-05, RC-06, RC-08, RC-09, RC-10, RC-11, RC-14, RC-15, RC-17, RC-23, RC-24, RC-26, RC-29, RC-30, RC-31, RC-32, RC-34 y RC-36; y hallazgos para su "Qué cambia". RC-18, RC-19, RC-21 y RC-35 pasan a `implementado` en M06, cuando `docs/INTERFACES.md` y `docs/security/threat-model.md` los reflejan; aquí solo propones sus hallazgos.
- Documentos consumidores a `actualizado`: `README.md`, `README.es.md`, `skills/mailquery/SKILL.md`, `skills/README.md`, `docs/tests/attachments-command.md` (cuando el orquestador aplique la marca de UT-ATC-09); los de `docs/tests/` cuando el orquestador aplique las marcas.
- Marcas de UT-MCP-09 a UT-MCP-12, UT-CLI-14, DOC-17, UT-ATC-09, DOC-01, DOC-04, DOC-05, TC-07.01 y la fila AC-21 de la matriz.

## Gates

- `-k ut_mcp`, `-k ut_cli_14`, `-k ut_atc_09`, `-k doc_0`, `-k doc_17` y `-k tc_07` verdes.
- Suite completa sin fallos nuevos frente a la línea base.
- Cobertura de `cli.py`, `mcp_server.py` y `logging_setup.py` sin bajar respecto de la línea base del lote; `mcp_server.py` ≥ 90 %.
- `git diff --check` limpio y `git diff --stat` solo con los archivos del alcance de escritura.

## Datos crudos de evidencia

Los de la sección "Evidencia cruda" de [PROTOCOLO-PLAN.md](PROTOCOLO-PLAN.md), más: la salida de `mailquery --help`, `mailquery mcp --help` y `mailquery mcp serve --help`; una sesión de prueba manual (`initialize`, `tools/list`, una llamada `doctor`) con su transcripción redactada; las líneas del log del servidor de esa sesión; la duración de los grupos UT-MCP-09 a UT-MCP-12 en el equipo local.

## Definition of Done

- `mailquery mcp serve` sirve las seis herramientas y su log tiene `start`, `call` y `end`, en texto o en JSON, sin mantener el archivo abierto.
- UT-MCP-09 a UT-MCP-12, UT-CLI-14 y DOC-17 verdes; casos de DP-18 actualizados y verdes.
- README, skill y ayudas documentan el registro, las herramientas, la equivalencia y los permisos; sin "six commands" / "seis comandos".
- Suite completa sin fallos nuevos; `git diff --check` limpio; diff dentro del alcance; fases en 🟢, evidencia cruda y propuestas entregadas.

## Registro de progreso

**Tabla: Registro de progreso de M05**

| Fecha | Fase | Nota |
|---|---|---|
| 2026-11-23 | 1 | Parser `mcp`/`serve`, despacho, ayuda raíz con `mcp` y `Output:`, ayudas de `mcp` y `mcp serve`; UT-CLI-14.01, .04, .05 y .06 verdes. |
| 2026-11-23 | 2 | Log del servidor con manejador por evento, `event=start`/`event=end`, nivel y formato; UT-MCP-11 verde. |
| 2026-11-23 | 3 | Pruebas con procesos reales: UT-MCP-09, UT-MCP-10 y UT-MCP-12, también en macOS. |
| 2026-11-23 | 4 | `COMMANDS` y `ALL_COMMANDS` con `mcp`, ejemplo de la ayuda raíz, tests de DP-18, README (dos), `SKILL.md` y `skills/README.md`; DOC-17. |
| 2026-11-23 | 5 | Suite, cobertura, evidencia y propuestas. |

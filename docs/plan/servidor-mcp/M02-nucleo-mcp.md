# M02 — Núcleo del servidor MCP

- **Unidad:** `docs/changes/servidor-mcp.md` (contribuye y no la completa sola).
- **Oleada / lote:** 2 / 1. **Rama del lote:** `feature/servidor-mcp-lote-1`. **Rama del milestone:** `feature/servidor-mcp-m02`, creada desde el tip de la rama del lote.
- **Commit base:** (te lo da el orquestador al lanzar; lo copias aquí en tu primer commit). **Línea base de la suite:** (te la da el orquestador al lanzar, con los fallos y saltos conocidos; la copias aquí).
- **Depende de:** M01 (`logging_setup.log_event` para el evento `event=call`). **Lo usan:** M05 (despacho de `mcp serve`, configuración del log del servidor y pruebas con procesos reales).
- **ACs:** AC-71 (todo salvo el fin de línea del proceso real en Windows), AC-72 (parte del ejecutor sustituido), AC-73, AC-74 (en proceso: `E_INTERNAL`, serie, cierre de stdin, stderr), AC-76 (importaciones y dependencias).

## Objetivo

Crear `src/mailquery/mcp_server.py` con el protocolo MCP por stdio, las herramientas generadas del parser, la traducción de argumentos, el ejecutor de llamadas y el resultado, probado en proceso con un ejecutor sustituido.

## Alcance

- La interfaz de la unidad: `serve`, `tool_definitions`, `build_argv`, `ToolRunner`, `ToolOutcome`, más la implementación real de `ToolRunner` (DP-09).
- Protocolo: lectura y escritura por líneas (DP-10), `initialize`, `ping`, `tools/list`, `tools/call`, notificaciones, errores `-32700`, `-32600`, `-32601`, `-32602`, lotes (DP-12), versiones del protocolo.
- Esquemas desde `build_parser()` (DP-11) y validación previa sin proceso hijo, con el límite del argv de DP-08.
- Resultado de la llamada y `E_INTERNAL` del propio servidor, con el JSON de error de la CLI (el `to_payload` de `MailqueryError` y el serializador `dumps_json` de `output.py`).
- Atención en serie.
- Evento `event=call tool=<herramienta> exit_code=<n> duration_ms=<ms>` con `log_event` sobre el logger `mailquery.mcp`, sin valores de parámetros. La configuración del log del servidor (archivo, nivel, apertura por evento) es de M05.

## Fuera de alcance

- El subcomando `mcp serve` en `cli.py`, las ayudas, `event=start` y `event=end` del servidor, la lectura de `[logging]` y el manejador que cierra el log entre eventos: M05.
- Las pruebas con el proceso real del servidor y de los hijos (UT-MCP-09 a UT-MCP-12): M05.
- Documentación: README y skill en M05; `docs/INTERFACES.md` en M06.

## Alcance de escritura

- `src/mailquery/mcp_server.py` (nuevo), `tests/test_mcp_server.py` (nuevo).
- `docs/plan/servidor-mcp/M02-nucleo-mcp.md`, `docs/plan/servidor-mcp/work/M02-handoff.md`, `docs/plan/servidor-mcp/work/M02-propuestas.md`.

## Especificación

Rangos de `docs/changes/servidor-mcp.md` en el commit de la unidad aprobada (F0 anota aquí el commit; si las líneas se movieron, busca el encabezado):

- `### Decisiones de diseño de la unidad`, líneas 60–72.
- `**RF-84. Servidor MCP por stdio.**`, líneas 91–111.
- `**RF-85. Herramientas del servidor.**`, líneas 113–134.
- `**RF-86. Ejecución de una llamada.**`, líneas 136–152.
- `### Arquitectura`, líneas 244–289 (responsabilidades, interfaz del módulo y secuencia).
- `## Criterios de aceptación`, AC-71 a AC-74 y AC-76, líneas 309–319.

Casos de test: encabezados `#### UT-MCP-01` a `#### UT-MCP-08` de `docs/tests/mcp-server.md`.

## Puntos de entrada en el código

En `f868036`; si la línea se movió, búscala por el nombre:

- `src/mailquery/cli.py`: `build_parser` (381; subparsers en 407, `--log-level` en 399, `--index` de `attachment` en 634), `COMMANDS` (84). Solo lectura.
- `src/mailquery/errors.py`: `MailqueryError` y `to_payload`. Solo lectura.
- `src/mailquery/output.py`: `dumps_json` (956), el serializador de la CLI. Solo lectura. No uses `write_json` (969): escribe en `sys.stdout` y rompería el flujo del protocolo (DP-10).
- `src/mailquery/logging_setup.py`: `log_event` (de M01), `get_logger` (98). Solo lectura.
- `mailquery.__version__` en `src/mailquery/__init__.py`.

## Refactorizaciones previas

Ninguna.

## Decisiones aplicables

- **DP-08. Límite de longitud del argv (M02).** En Windows, la línea de comandos que resulta de citar el argv completo con las reglas de Windows no supera 32 767 caracteres. En POSIX, los bytes UTF-8 de los argumentos y de las variables de entorno, cada uno con su terminador, no superan el límite `ARG_MAX` del sistema (131 072 si no se puede consultar). Por encima, `E_USAGE` sin lanzar el proceso hijo, con un `hint` que nombra el parámetro más largo.
- **DP-09. Ejecutor real (M02 lo implementa, M05 lo prueba con procesos reales).** `serve` arma el argv completo (el intérprete del servidor, `-P -m mailquery` y los argumentos de `build_argv`) y se lo pasa a `ToolRunner.run`; así el ejecutor sustituido de los tests registra también `-P -m mailquery`. El ejecutor real lanza ese argv sin shell, con stdin vacío, stdout capturado, stderr descartado, el entorno y el directorio de trabajo del servidor y, en Windows, sin ventana de consola; lee stdout como UTF-8 y mide `duration_ms`. La salida es válida si, sin el salto final, es exactamente un objeto JSON.
- **DP-10. Flujos del servidor (M02 y M05).** `serve(stdin, stdout, *, runner)` recibe flujos de texto, como dice la unidad. La CLI se los pasa en UTF-8 sobre los bytes de stdin y stdout: la lectura no traduce los finales de línea, la escritura usa siempre LF y vuelca tras cada mensaje. `serve` quita el final de línea (CR LF o LF) de cada línea leída. Cada mensaje del protocolo se escribe en una sola línea: JSON compacto, sin sangría ni saltos de línea, sin escapar los caracteres no ASCII, seguido de LF. Una línea que no se puede decodificar como UTF-8 recibe `-32700`. El JSON de la CLI que va dentro del bloque `text` de un resultado (la salida del proceso hijo, o el `E_USAGE` y el `E_INTERNAL` que arma el servidor con `to_payload` y `output.dumps_json`) conserva el formato de la CLI, con su sangría: es un texto dentro del mensaje, no el mensaje. El servidor no usa ninguna función que escriba directamente en `sys.stdout` (por ejemplo, `output.write_json`); escribe solo en el flujo que recibe.
- **DP-11. Esquemas (M02).** El nombre del parámetro sale de la primera opción larga (`--from` ⇒ `from`, no de `dest`). La descripción de la herramienta es `description` del subparser; la de cada parámetro, el `help` de la opción. El tipo se decide así: `store_true` ⇒ `boolean`; `type=int` o `--index` de `attachment` ⇒ `integer`; `choices` ⇒ `string` con `enum`; `action="append"` ⇒ `array` de `string`; el resto ⇒ `string`. `uid` es el posicional de `show` y `attachment` y va en `required`. `log_level` toma el `enum` de `--log-level` del parser raíz.
- **DP-12. Lotes JSON-RPC (M02).** Cada elemento de un lote se atiende en orden como un mensaje suelto; las respuestas a sus peticiones van en un array en el mismo orden; un elemento que no es un objeto recibe `-32600` con `id` `null` dentro del array.
- **DP-13. Importaciones (M02 y M05).** `mcp_server.py` importa `build_parser` de `mailquery.cli` dentro de la función que lo necesita, y `cli.py` importa `mailquery.mcp_server` solo al despachar `mcp serve`, para que no haya ciclo de importación. Ni el uno ni el otro cargan entry points ni instancian drivers al importarse.

Margen tuyo: la estructura interna del módulo, los nombres privados y cómo se inyecta el logger en los tests; anótalo en `work/M02-propuestas.md`.

## Fases

**Tabla: Fases de M02**

| Fase | Tareas | Estado |
|---|---|---|
| 1 | Esqueleto del módulo con `ToolOutcome`, `ToolRunner` y `serve` sobre flujos de texto; transporte, `initialize`, `ping`, notificaciones, errores JSON-RPC y lotes; UT-MCP-01 y UT-MCP-02 | ⚪ |
| 2 | `tool_definitions` desde el parser; UT-MCP-03 | ⚪ |
| 3 | `build_argv`, validación previa, límite del argv y `-32602`; UT-MCP-04 y UT-MCP-06 | ⚪ |
| 4 | `tools/call`: argv completo, ejecutor real (DP-09), resultado, `E_INTERNAL`, serie, fin de stdin, evento `event=call`; UT-MCP-05 y UT-MCP-07 | ⚪ |
| 5 | Importaciones y dependencias; UT-MCP-08; cobertura de `mcp_server.py` ≥ 90 %; suite completa, evidencia cruda y propuestas | ⚪ |

## Tests

- Archivo nuevo `tests/test_mcp_server.py`, con `unittest`, una clase por grupo y métodos `test_ut_mcp_<gg>_<cc>_<descripción>` (convenciones de `docs/tests/TEST-CATALOG.md`).
- Grupos: UT-MCP-01 a UT-MCP-08 (encabezados en `docs/tests/mcp-server.md`, casos `[pendiente]`).
- El ejecutor sustituido es una clase del propio test que registra cada argv, devuelve un `ToolOutcome` dado y, para UT-MCP-07, marca inicio y fin con `threading.Event`, sin `sleep` como aserción, para que los tests no fallen de forma intermitente. El ejecutor real se prueba en proceso sustituyendo el lanzamiento de procesos (UT-MCP-05.07): sin shell, stdin vacío, stderr descartado, entorno y directorio heredados y, en Windows, sin ventana de consola.
- Los flujos se simulan con `io.StringIO` y, para UT-MCP-01.09, con `io.TextIOWrapper` sobre `io.BytesIO` configurado como en DP-10.
- UT-MCP-08.01 compara cada módulo que importa `mcp_server.py` con la lista de módulos de la biblioteca estándar del intérprete y el prefijo `mailquery`. UT-MCP-08.02 compara `[project].dependencies` con la lista literal de la línea base: `["css-inline~=0.23.1", "pywin32; sys_platform == \"win32\""]`. UT-MCP-08.03 sustituye la lectura de entry points del registro (`installed_entry_points`) y la creación de drivers por sustitutos que fallan si se llaman.
- Comando: `python -B -m unittest discover -s tests -t . -k ut_mcp` y la suite completa.

## Documentación

Ninguna en este milestone: el comando todavía no es invocable. M05 documenta el registro y las herramientas; M06, `docs/INTERFACES.md`.

## Actualizaciones de la unidad

Propones al orquestador, en `work/M02-propuestas.md`:

- Hallazgos para "Qué cambia" de RC-19 (responsabilidad de `mcp_server.py`) y RC-21 (flujo de una llamada), si la implementación descubre algo que el PRD deba reflejar. Las filas pasan a `implementado` en M05, cuando el comando existe.
- Marcas de UT-MCP-01 a UT-MCP-08 en `docs/tests/mcp-server.md`.

## Gates

- `python -B -m unittest discover -s tests -t . -k ut_mcp` verde.
- Suite completa sin fallos nuevos frente a la línea base.
- Cobertura de `src/mailquery/mcp_server.py` ≥ 90 % de líneas y ramas.
- `git diff --check` limpio y `git diff --stat` solo con los archivos del alcance de escritura.

## Datos crudos de evidencia

Los de la sección "Evidencia cruda" de [PROTOCOLO-PLAN.md](PROTOCOLO-PLAN.md), más: el JSON de `tools/list` completo generado en el tip del milestone (lo usa M05 para la documentación) y la lista de importaciones de `mcp_server.py`.

## Definition of Done

- `mcp_server.py` cumple la interfaz de la unidad y DP-08 a DP-13.
- UT-MCP-01 a UT-MCP-08 verdes, cada caso con su método.
- Cobertura de `mcp_server.py` ≥ 90 %; suite completa sin fallos nuevos; `git diff --check` limpio; diff dentro del alcance.
- Fases en 🟢, evidencia cruda y propuestas entregadas.

## Registro de progreso

**Tabla: Registro de progreso de M02**

| Fecha | Fase | Nota |
|---|---|---|

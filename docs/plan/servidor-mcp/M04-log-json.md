# M04 — Log en JSON (`[logging].json`)

- **Unidad:** `docs/changes/servidor-mcp.md` (contribuye y no la completa sola).
- **Oleada / lote:** 2 / 1. **Rama del lote:** `feature/servidor-mcp-lote-1`. **Rama del milestone:** `feature/servidor-mcp-m04`, creada desde el tip de la rama del lote.
- **Commit base:** `85b781d` (tip de `feature/servidor-mcp-lote-1` al lanzar). **Línea base de la suite:** `Ran 1576 tests`, `failures=3` y `skipped=7`; los tres fallos son SMOKE-INSTALL.04, SMOKE-NEW.07 y SMOKE-NEW.10, fallos locales del entorno SMOKE ajenos a este milestone.
- **Depende de:** M01 (`log_event` y los campos estructurados de cada evento). **Lo usan:** M05 (`load_logging_config`, archivo activo y formato JSON para el log del servidor), M06 (`docs/INTERFACES.md`).
- **ACs:** AC-77 completo; la parte de AC-75 "la ayuda raíz nombra `mailquery.log` y `mailquery.jsonl`".

## Objetivo

Añadir la clave `[logging].json`: con `true`, el núcleo escribe su log en `~/.mailquery/logs/mailquery.jsonl`, un objeto JSON por línea con los mismos eventos, nivel, rotación y permisos que el log de texto; sin ella, todo sigue igual.

## Alcance

- `config.py`: campo `json: bool = False` en `LoggingConfig`; `_parse_logging` acepta `json` (booleano; otro tipo ⇒ `E_CONFIG_INVALID` con el mensaje y el hint del resto de tipos incorrectos de `[logging]`) y lo añade a la lista de claves válidas; función nueva `load_logging_config` (DP-05).
- `logging_setup.py`: `setup_logging(home, level, max_size_mb, json=False)` elige `mailquery.log` o `mailquery.jsonl` y su formateador; formateador JSON (DP-03); el archivo del otro formato y sus rotados no se tocan; nombre del archivo activo (DP-04).
- `cli.py`: pasa `config.logging.json` a `setup_logging`; `_best_effort_logger` y la configuración de `doctor` sin configuración válida siguen en texto con los valores por defecto (RF-88 "Sin configuración válida"); `hint` de `E_INTERNAL` con el archivo activo; línea `logs go to` de la ayuda raíz con los dos archivos.
- `backends/outlook_com.py`: `HINT_INTERNAL` y `HINT_READONLY` con el archivo activo (DP-04).
- `docs/config.example.toml`: `# json = false` con su comentario en el bloque `# [logging]`.
- README (los dos): sección de configuración y sección "Logs and privacy" / "Logs y privacidad"; fila `E_INTERNAL` de la tabla de errores frecuentes.

## Fuera de alcance

- El log del servidor MCP y su apertura por evento: M05.
- La línea `Output:` de la ayuda raíz y el comando `mcp`: M05.
- `docs/INTERFACES.md` y `docs/security/threat-model.md`: M06.
- Los logs propios de los plugins (`~/.mailquery/logs/<driver>.log`).

## Alcance de escritura

- `src/mailquery/config.py`, `src/mailquery/logging_setup.py`, `src/mailquery/cli.py`, `src/mailquery/backends/outlook_com.py`.
- `tests/test_logging.py`, `tests/test_config.py`, `tests/test_cli.py`, `tests/test_outlook.py`, `tests/test_packaging.py`, `tests/test_integration.py`.
- `docs/config.example.toml`, `README.md`, `README.es.md`.
- `docs/plan/servidor-mcp/M04-log-json.md`, `docs/plan/servidor-mcp/work/M04-handoff.md`, `docs/plan/servidor-mcp/work/M04-propuestas.md`.

## Especificación

Rangos de `docs/changes/servidor-mcp.md` en el commit de la unidad aprobada (F0 anota aquí el commit; si las líneas se movieron, busca el encabezado):

- `### Alcance adicional`, líneas 50–54.
- `### Decisiones de diseño de la unidad`, líneas 60–72 (viñetas del log JSON y de la configuración sin validar).
- `### Lo que no cambia`, líneas 82–87.
- `**RF-88. Log en formato JSON.**`, líneas 168–197.
- `**RF-84. Servidor MCP por stdio.**`, condición "Configuración del servidor" (línea 102), solo para `load_logging_config`.
- `**AC-77.**`, línea 321; `**AC-75.**`, línea 317 (solo la frase de la ayuda raíz y los logs).

Casos de test: `#### UT-CFG-05`, `#### UT-CFG-06`, `#### UT-LOG-05` y `#### UT-LOG-06` de `docs/tests/cli-config.md`; `#### DOC-18` de `docs/tests/docs-packaging.md`.

## Puntos de entrada en el código

En `f868036` más M01; si la línea se movió, búscala por el nombre:

- `src/mailquery/config.py`: `LoggingConfig` (107), `load_config` (242), `_parse_config` (286), `_parse_logging` (367).
- `src/mailquery/logging_setup.py`: `LOG_FORMAT` (16), `_PrivateRotatingFileHandler` (46), `setup_logging` (58), `log_event` (de M01).
- `src/mailquery/cli.py`: `_ROOT_EPILOG` (122; línea `logs go to` en 135), `_run_command` (990; `setup_logging` en 1021, `E_INTERNAL` en 1105), `_best_effort_logger` (2613), `_doctor_log_settings` (2627).
- `src/mailquery/backends/outlook_com.py`: `HINT_INTERNAL` (130), `HINT_READONLY` (133), sus usos (255, 304).
- `tests/test_logging.py`: `_LogHomeTestCase` (45), `RotationTests` (62), `PermissionTests` (95).
- `tests/test_integration.py`: `test_doc_06_01_parses_with_the_real_loader_and_documents_attachments` (2197) como modelo de DOC-18.02.
- `docs/config.example.toml`: bloque `# [logging]` (29–31).
- `README.md`: "Configuration" (277), "Logs and privacy" (944), tabla de errores frecuentes (1008). `README.es.md`: los mismos bloques (966, 1029).

## Refactorizaciones previas

Ninguna además de M01. Los `hint` de Outlook pasan de constantes a valores calculados al crear el error (DP-04); es parte del requisito, no una refactorización aparte.

## Decisiones aplicables

- **DP-03. Formateador JSON (M04).** Objeto con `ts` (hora local ISO 8601 con milisegundos y desfase), `level`, `logger` (nombre del logger), `run`, `fields` (en el orden del evento), `text` solo si existe y `traceback` solo si existe (el de `log_event` o el de `exc_info`). Conversión de valores: `int` o texto de entero decimal ⇒ número; `bool` o texto `true`/`false` en cualquier combinación de mayúsculas ⇒ booleano; `-` ⇒ `null`; el resto, texto; `message` siempre texto. Un registro sin `extra` estructurado (por ejemplo, de una biblioteca) da solo `text` con el mensaje formateado.
- **DP-04. Archivo activo en los mensajes (M04).** `logging_setup` expone el nombre del archivo activo del proceso (`mailquery.log` o `mailquery.jsonl`, según la última configuración aplicada, y `mailquery.log` antes de configurar). Los `hint` que nombran el log (el de `E_INTERNAL` de `cli.py`, `HINT_INTERNAL` y `HINT_READONLY` de `backends/outlook_com.py`) se calculan al crear el error, no en la importación del módulo.
- **DP-05. Configuración del log del servidor (M04 la crea, M05 la usa).** `config.load_logging_config(home: Path) -> LoggingConfig` lee de `config.toml` solo la tabla `[logging]`, la valida con las reglas de `_parse_logging` y nunca lanza: si el archivo falta, no es TOML válido o `[logging]` no es válida, devuelve `LoggingConfig()` (texto, `info`, 10 MB). `LoggingConfig` gana el campo `json: bool = False`.
- **DP-17. Documentación con su funcionalidad.** Cada milestone actualiza la documentación de lo que entrega, para que ninguno cierre con deuda de documentación: M03 las menciones de la versión, M04 el log JSON en los README y `config.example.toml`, M05 el registro, las herramientas y los permisos en los README, la ayuda y la skill, M06 los documentos técnicos.

Margen tuyo: el nombre de la función del archivo activo y del formateador, y el texto del comentario de `config.example.toml` y de los README, en inglés y en español con el mismo contenido. Anótalo en `work/M04-propuestas.md`.

## Fases

**Tabla: Fases de M04**

| Fase | Tareas | Estado |
|---|---|---|
| 1 | `config.py`: clave `json`, `load_logging_config`; UT-CFG-05.01 y UT-CFG-06 | 🟢 |
| 2 | `logging_setup.py`: archivo activo, formateador JSON, rotación y permisos de `mailquery.jsonl`; UT-LOG-05.03–.05, .07–.12 | 🟢 |
| 3 | `cli.py`: `json` en `setup_logging`, errores de configuración en texto, `hint` de `E_INTERNAL`, línea de logs de la ayuda raíz; `outlook_com.py`: `hint` con el archivo activo; UT-LOG-05.01, .02, .06, UT-CFG-05.02–.03, UT-LOG-06 | 🟢 |
| 4 | `config.example.toml` y los dos README; DOC-18; DOC-06 sigue verde | 🟢 |
| 5 | Suite completa, cobertura de `logging_setup.py` y `config.py`, evidencia cruda y propuestas | ⚪ |

## Tests

- Grupos nuevos (casos `[pendiente]` en `docs/tests/`): UT-CFG-05 y UT-CFG-06 en `tests/test_config.py` (UT-CFG-05.02–.03 por `cli.main` en `tests/test_cli.py`); UT-LOG-05 en `tests/test_logging.py` y `tests/test_cli.py`; UT-LOG-06 en `tests/test_cli.py` (.01, .03) y `tests/test_outlook.py` (.02); DOC-18 en `tests/test_packaging.py` (.01) y `tests/test_integration.py` (.02).
- Métodos `test_ut_log_05_<cc>_<descripción>`, etc., con las convenciones de `docs/tests/TEST-CATALOG.md`; HOME temporal; aserciones de permisos POSIX solo en POSIX (salto permitido).
- UT-LOG-05.06 reutiliza el escenario de UT-LOG-04.02 con `json = true`.
- Deben seguir verdes sin cambios: UT-LOG-01 a UT-LOG-04, UT-CFG-01 a UT-CFG-04, DOC-06, el test de regresión de M01.
- Comandos: `python -B -m unittest discover -s tests -t . -k ut_log_0`, `-k ut_cfg_0`, `-k doc_06`, `-k doc_18` y la suite completa.

## Documentación

- `docs/config.example.toml`: `# json = false` en el bloque `# [logging]`, con un comentario de una línea (escribe `mailquery.jsonl` en JSON Lines en lugar de `mailquery.log`).
- `README.md` y `README.es.md`, mismo contenido en el mismo commit: la clave en la sección de configuración; en "Logs and privacy" / "Logs y privacidad", los dos archivos, que cada ejecución escribe solo el del formato activo, los campos del objeto JSON y el ejemplo de RF-88; la fila `E_INTERNAL` de la tabla de problemas nombra los dos archivos.

## Actualizaciones de la unidad

Propones al orquestador, en `work/M04-propuestas.md`:

- RC-07, RC-12, RC-13, RC-22, RC-27 y RC-28 a `implementado` (RC-20 pasa en M06, con `docs/INTERFACES.md`); la parte de logs de RC-24 queda para M05 (la fila entera pasa con M05).
- Documento consumidor `docs/config.example.toml` a `actualizado`; `docs/tests/cli-config.md` a `actualizado` cuando sus marcas estén aplicadas.
- Marcas de UT-CFG-05, UT-CFG-06, UT-LOG-05, UT-LOG-06 y DOC-18.

## Gates

- `-k ut_log_0`, `-k ut_cfg_0`, `-k doc_06` y `-k doc_18` verdes.
- Suite completa sin fallos nuevos frente a la línea base.
- Cobertura de `logging_setup.py` y `config.py` sin bajar respecto de la línea base.
- `git diff --check` limpio y `git diff --stat` solo con los archivos del alcance de escritura.

## Datos crudos de evidencia

Los de la sección "Evidencia cruda" de [PROTOCOLO-PLAN.md](PROTOCOLO-PLAN.md), más: una línea de `mailquery.jsonl` por cada tipo de evento (`start`, `end`, `error`, `internal_error` con `traceback`, store, `doctor`) generada por los tests, con los valores personales sustituidos por marcadores.

## Definition of Done

- Con la clave ausente o `false`, el log es byte a byte el de la línea base (test de regresión de M01 y UT-LOG-03 verdes).
- Con `true`, solo se escribe `mailquery.jsonl`, con los campos y tipos de RF-88, rotación, nivel y permisos.
- `json = "yes"` y una configuración inválida con `json = true` se registran en `mailquery.log` en texto.
- Los `hint` y la ayuda raíz nombran el archivo correcto.
- `config.example.toml` y los dos README documentan la clave.
- Suite completa sin fallos nuevos; `git diff --check` limpio; diff dentro del alcance; fases en 🟢, evidencia cruda y propuestas entregadas.

## Registro de progreso

**Tabla: Registro de progreso de M04**

| Fecha | Fase | Nota |
|---|---|---|
| 2026-11-23 | 1 | Clave `[logging].json`, `load_logging_config`, UT-CFG-05.01–.03 y UT-CFG-06 verdes. |
| 2026-11-23 | 2 | `active_log_filename`, `JsonFormatter`, `setup_logging(json=)` y el cableado de `cli.py`; UT-LOG-05.03–.05 y .07–.12 verdes (el `.08` y el `.11` también usan `cli.main`). |
| 2026-11-23 | 3 | `hint` de `E_INTERNAL` y de Outlook con el archivo activo, línea de logs de la ayuda raíz; UT-LOG-05.01, .02 y .06 y UT-LOG-06.01–.03 verdes. |
| 2026-11-23 | 4 | `[logging].json` en `config.example.toml` y en los dos README, fila `E_INTERNAL` con los dos archivos; DOC-18.01–.02 y DOC-06 verdes. |

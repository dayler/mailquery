# M06 — Documentos técnicos

- **Unidad:** `docs/changes/servidor-mcp.md` (contribuye y no la completa sola).
- **Oleada / lote:** 4 / 2. **Rama del lote:** `feature/servidor-mcp-lote-2`. **Rama del milestone:** `feature/servidor-mcp-m06`, creada desde el tip de la rama del lote.
- **Commit base:** `0ca8909`. **Línea base de la suite:** `Ran 1598 tests`, `failures=2`, `skipped=7`; los dos fallos son SMOKE-NEW.07 y SMOKE-NEW.10 (entorno SMOKE local, no de este milestone).
- **Depende de:** M04 (log JSON, `load_logging_config`, archivo activo) y M05 (`mcp serve`, `mcp_server.py` final, `log_event` en uso). **Lo usan:** F3 y F5 del plan.
- **ACs:** ninguno; prepara CL-05 y CL-06 de la unidad para los documentos técnicos.

## Objetivo

Poner al día los documentos técnicos consumidores con lo implementado en M01–M05: contratos internos, modelo de amenaza, hoja de ruta y recetas.

## Alcance

- `docs/INTERFACES.md` (en español, como está): layout con `mcp_server.py` y `tests/test_mcp_server.py`; dirección de dependencias (`cli` → `mcp_server` en el despacho; `mcp_server` → `cli.build_parser`, `errors`, `output`, `logging_setup`; sin drivers ni plugins); sección nueva `### mcp_server.py` con la interfaz pública del módulo y su comportamiento tal como están en el código (límite del argv, ejecutor real, flujos, esquemas, lotes e importaciones); `### logging_setup.py` con `log_event`, el formato JSON, `mailquery.jsonl`, el archivo activo y el log del servidor; `### config.py` con `json` y `load_logging_config`; `### cli.py` con `mcp serve`; sección 8 (desarrollo y pruebas) con la prueba manual del servidor.
- `docs/security/threat-model.md`: la superficie del servidor por stdio (sin red, proceso hijo por llamada, `-P`, entorno heredado del harness, stdin vacío para los plugins, permisos de la app que lanza el servidor) y la privacidad de `mailquery.jsonl`.
- `docs/ROADMAP.md`: el servidor MCP y el log JSON como hechos en `3.0.0`, sin plan ni fechas.
- `docs/recipes/`: comprobar si alguna receta dice que la CLI es la única vía; si es así, una frase que dice que la receta vale igual con las herramientas MCP y que el código de salida se deduce de `error.code`; si no, `sin cambio`.
- Barrido de CL-06 y CL-11 en los documentos consumidores que no son del PRD.

## Fuera de alcance

- README, skill, ayudas, `config.example.toml`: M03, M04 y M05.
- El PRD y `docs/tests/`.
- Cualquier cambio de código o de tests (salvo los DOC que una búsqueda demuestre rotos, que se devuelven al orquestador).

## Alcance de escritura

- `docs/INTERFACES.md`, `docs/security/threat-model.md`, `docs/ROADMAP.md`, `docs/recipes/01-new-mail-digest.md`, `docs/recipes/02-search-invoices.md`.
- `docs/plan/servidor-mcp/M06-documentos-tecnicos.md`, `docs/plan/servidor-mcp/work/M06-handoff.md`, `docs/plan/servidor-mcp/work/M06-propuestas.md`.

## Especificación

Rangos de `docs/changes/servidor-mcp.md` en el commit de la unidad aprobada (F0 anota aquí el commit; si las líneas se movieron, busca el encabezado):

- `### Solución elegida` y `### Por qué un proceso hijo por llamada`, líneas 26–41.
- `### Arquitectura`, líneas 244–289.
- `### Riesgos`, líneas 291–301.
- `**RF-88. Log en formato JSON.**`, condiciones "Campos", "Privacidad" y "Un solo archivo activo" (líneas 177–186).
- `## Checklist de conciliación`, CL-06 y CL-11 (líneas 424 y 429).

## Puntos de entrada en el código

Solo lectura, en el tip del lote 2 tras M05:

- `src/mailquery/mcp_server.py` (interfaz pública), `src/mailquery/logging_setup.py` (`log_event`, `setup_logging`, archivo activo, log del servidor), `src/mailquery/config.py` (`load_logging_config`), `src/mailquery/cli.py` (`build_parser`, despacho de `mcp serve`).
- `docs/INTERFACES.md`: "Layout del repositorio" (15), "Dirección de dependencias" (152), `### logging_setup.py` (407), `### config.py` (1143), `### cli.py` (1369), "Desarrollo y pruebas" (2373).
- `docs/security/threat-model.md`: "Frontera de confianza" (61), "Qué protege hoy" (78), "Catálogo de amenazas" (141), "Checklist de seguridad para el harness" (179).
- `docs/ROADMAP.md`: "Diseño objetivo" (108), "Para publicar 3.0.0" (284).

## Refactorizaciones previas

Ninguna.

## Decisiones aplicables

- **DP-17. Documentación con su funcionalidad.** Cada milestone actualiza la documentación de lo que entrega, para que ninguno cierre con deuda de documentación: M03 las menciones de la versión, M04 el log JSON en los README y `config.example.toml`, M05 el registro, las herramientas y los permisos en los README, la ayuda y la skill, M06 los documentos técnicos.
- Los documentos de `docs/` pueden estar en español (`CLAUDE.md`); estos ya lo están y siguen así. Cada tabla o figura nueva lleva su título.
- Ninguno cita el plan ni la unidad (`CLAUDE.md`, "Plans and permanent documents").

## Fases

**Tabla: Fases de M06**

| Fase | Tareas | Estado |
|---|---|---|
| 1 | `docs/INTERFACES.md` | 🟢 |
| 2 | `docs/security/threat-model.md` y `docs/ROADMAP.md` | ⚪ |
| 3 | Recetas: revisión y, si hace falta, la frase de MCP; TC-04 verde | ⚪ |
| 4 | Barrido: `grep -rniE "six commands\|seis comandos\|3\.0\.0a2\|3\.0\.0-alpha\.2" README.md README.es.md skills docs/INTERFACES.md docs/ROADMAP.md docs/recipes docs/security docs/config.example.toml` y búsqueda de `mailquery.log` como único archivo del log del núcleo en esos documentos; DOC-16.02 y DOC-03 verdes; suite completa, evidencia cruda y propuestas | ⚪ |

## Tests

- Sin grupos nuevos. Deben seguir verdes: TC-04 (recetas), DOC-03, DOC-16.02 (textos obsoletos en `docs/INTERFACES.md`, `docs/recipes/` y `docs/security/`), DOC-14 y DOC-15.
- Comandos: `python -B -m unittest discover -s tests -t . -k tc_04`, `-k doc_03`, `-k doc_16`, `-k doc_14`, `-k doc_15` y la suite completa.

## Documentación

La del alcance. `docs/INTERFACES.md` tiene más de 300 líneas: se busca cada sección por su encabezado y se lee por rangos.

## Actualizaciones de la unidad

Propones al orquestador, en `work/M06-propuestas.md`:

- Filas de conciliación a `implementado`: RC-18, RC-19, RC-20, RC-21 y RC-35, que dependen de `docs/INTERFACES.md` y `docs/security/threat-model.md`.
- Documentos consumidores: `docs/INTERFACES.md`, `docs/security/` y `docs/ROADMAP.md` a `actualizado`; `docs/recipes/` a `actualizado` o `sin cambio` según la fase 3.
- El resultado del barrido de la fase 4 para CL-06 y CL-11 (la parte de los documentos consumidores).

## Gates

- `-k tc_04`, `-k doc_03`, `-k doc_16`, `-k doc_14` y `-k doc_15` verdes.
- Suite completa sin fallos nuevos frente a la línea base.
- El barrido de la fase 4 sin resultados vigentes.
- `git diff --check` limpio y `git diff --stat` solo con los archivos del alcance de escritura.

## Datos crudos de evidencia

Los de la sección "Evidencia cruda" de [PROTOCOLO-PLAN.md](PROTOCOLO-PLAN.md), más: la salida del barrido de la fase 4 y, por documento, la lista de secciones cambiadas.

## Definition of Done

- Los cuatro documentos (o tres y recetas `sin cambio` justificado) describen el servidor MCP y el log JSON tal como están en el código.
- Barrido limpio; TC-04, DOC-03, DOC-14, DOC-15 y DOC-16 verdes.
- Suite completa sin fallos nuevos; `git diff --check` limpio; diff dentro del alcance; fases en 🟢, evidencia cruda y propuestas entregadas.

## Registro de progreso

**Tabla: Registro de progreso de M06**

| Fecha | Fase | Nota |
|---|---|---|
| 2026-11-23 | 1 | `docs/INTERFACES.md`: layout, dirección de dependencias, `mcp_server.py`, `logging_setup.py`, `config.py`, `cli.py` y prueba manual del servidor. |
